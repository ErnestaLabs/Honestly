#!/usr/bin/env python3
"""products/engine.py - The 300-Product Engine.

Pairs a psychological trigger with a data vector and an open-source tool
to deliver immediate, high-value micro-upsells.

Architecture:
  ProductEngine.execute(product_id, user, subject, params)
    → checks entitlements (tier, credits, cooldown)
    → executes the product's execution_function
    → deducts credits
    → returns the result

Scalability: new products are one ProductTemplate instantiation in catalog.py,
not a new script. The engine handles billing, gating, and delivery uniformly.
"""
from __future__ import annotations
import json
import time
from dataclasses import dataclass
from typing import Any, Optional

from products.catalog import (
    CATALOG, CATALOG_BY_ID, ProductTemplate, EmotionTrigger,
    get_product, list_products, execute_product,
)


# ──────────────────────────────────────────────────────────── engine config

# Redis key prefixes (assumes Redis is available)
_REDIS_PREFIX = "honestly:products"
_COOLDOWN_PREFIX = f"{_REDIS_PREFIX}:cooldown"
_CREDIT_PREFIX = f"{_REDIS_PREFIX}:credits"
_PURCHASE_PREFIX = f"{_REDIS_PREFIX}:purchases"


# ──────────────────────────────────────────────────────────── credit system

@dataclass
class CreditAccount:
    """A user's credit balance and transaction history."""
    user_id: str
    balance_gbp: float = 0.0
    monthly_grant_gbp: float = 0.0
    last_grant_date: Optional[str] = None

    def can_afford(self, amount_gbp: float) -> bool:
        return self.balance_gbp >= amount_gbp

    def deduct(self, amount_gbp: float) -> bool:
        if not self.can_afford(amount_gbp):
            return False
        self.balance_gbp -= amount_gbp
        return True

    def grant_monthly(self, tier: str) -> float:
        """Apply the monthly credit grant based on subscription tier."""
        from auth.entitlements import TIER_CREDITS
        grant = TIER_CREDITS.get(tier, 0)
        if grant > 0:
            self.monthly_grant_gbp = grant
            self.balance_gbp += grant
        return grant


class ProductEngine:
    """The 300-Product Engine. Executes micro-upsells with entitlement gating.

    Uses Redis for:
      - Cooldown tracking (prevent accidental double-buys)
      - Credit balances (monthly grants + per-product deduction)
      - Purchase history (audit trail)
    Falls back to in-memory dicts if Redis is unavailable.
    """

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._fallback_cooldowns = {}  # user_id:product_id -> timestamp
        self._fallback_credits = {}    # user_id -> CreditAccount
        self._fallback_purchases = []  # list of purchase records

    def execute(
        self,
        product_id: str,
        user_id: str,
        user_tier: str,
        subject: dict,
        params: dict | None = None,
    ) -> dict:
        """Execute a product for a user.

        Steps:
          1. Validate product exists
          2. Check tier access
          3. Check cooldown
          4. Check credits / process payment
          5. Execute the product function
          6. Record purchase
          7. Return result

        Returns: {"ok": bool, "output": ..., "format": ..., "charged_gbp": float}
        """
        params = params or {}
        # 1. Validate
        product = get_product(product_id)
        if not product:
            return {"ok": False, "error": f"Unknown product: {product_id}"}

        # 2. Tier access
        from auth.entitlements import TIER_LEVELS
        user_level = TIER_LEVELS.get(user_tier, 0)
        product_level = TIER_LEVELS.get(product.tier_access, 0)
        if user_level < product_level:
            return {"ok": False, "error": f"This product requires {product.tier_access} tier or above"}

        # 3. Cooldown
        cooldown_key = f"{user_id}:{product_id}:{subject.get('address', '')}"
        if self._is_on_cooldown(cooldown_key, product.cooldown_hours):
            return {"ok": False, "error": f"This product is on cooldown for {product.cooldown_hours}h per address"}

        # 4. Credits / payment
        credit_cost = product.credit_cost_gbp or product.gbp_price
        account = self._get_credit_account(user_id)
        if not account.can_afford(credit_cost):
            return {"ok": False, "error": f"Insufficient credits. Need £{credit_cost:.2f}, have £{account.balance_gbp:.2f}"}
        account.deduct(credit_cost)

        # 5. Execute
        result = execute_product(product_id, subject, params)

        # 6. Record purchase
        self._record_purchase(user_id, product_id, credit_cost, result.get("ok", False))
        self._set_cooldown(cooldown_key, product.cooldown_hours)
        self._save_credit_account(user_id, account)

        # 7. Return
        result["charged_gbp"] = credit_cost
        result["remaining_credits_gbp"] = round(account.balance_gbp, 2)
        return result

    def get_catalog(self, tier: str = "all", trigger: str | None = None) -> list[dict]:
        """Get the product catalog filtered for a user's tier and optional trigger."""
        products = list_products(tier=tier, trigger=trigger)
        return [p.to_dict() for p in products]

    def get_credits(self, user_id: str) -> dict:
        """Get a user's credit balance."""
        account = self._get_credit_account(user_id)
        return {"balance_gbp": round(account.balance_gbp, 2), "monthly_grant_gbp": account.monthly_grant_gbp}

    # ──────────────────────────────────────────────── Redis helpers

    def _is_on_cooldown(self, key: str, hours: int) -> bool:
        if self.redis:
            try:
                ts = self.redis.get(f"{_COOLDOWN_PREFIX}:{key}")
                if ts and (time.time() - float(ts)) < hours * 3600:
                    return True
                return False
            except Exception:
                pass
        # Fallback
        ts = self._fallback_cooldowns.get(key)
        if ts and (time.time() - ts) < hours * 3600:
            return True
        return False

    def _set_cooldown(self, key: str, hours: int):
        if self.redis:
            try:
                self.redis.setex(f"{_COOLDOWN_PREFIX}:{key}", hours * 3600, str(time.time()))
                return
            except Exception:
                pass
        self._fallback_cooldowns[key] = time.time()

    def _get_credit_account(self, user_id: str) -> CreditAccount:
        if self.redis:
            try:
                data = self.redis.get(f"{_CREDIT_PREFIX}:{user_id}")
                if data:
                    d = json.loads(data)
                    return CreditAccount(**d)
            except Exception:
                pass
        # Fallback
        if user_id not in self._fallback_credits:
            self._fallback_credits[user_id] = CreditAccount(user_id=user_id)
        return self._fallback_credits[user_id]

    def _save_credit_account(self, user_id: str, account: CreditAccount):
        if self.redis:
            try:
                self.redis.set(
                    f"{_CREDIT_PREFIX}:{user_id}",
                    json.dumps({"user_id": account.user_id,
                                "balance_gbp": account.balance_gbp,
                                "monthly_grant_gbp": account.monthly_grant_gbp,
                                "last_grant_date": account.last_grant_date}),
                )
                return
            except Exception:
                pass
        self._fallback_credits[user_id] = account

    def _record_purchase(self, user_id: str, product_id: str, amount_gbp: float, success: bool):
        record = {
            "user_id": user_id,
            "product_id": product_id,
            "amount_gbp": amount_gbp,
            "success": success,
            "timestamp": time.time(),
        }
        if self.redis:
            try:
                self.redis.rpush(f"{_PURCHASE_PREFIX}:{user_id}", json.dumps(record))
                return
            except Exception:
                pass
        self._fallback_purchases.append(record)
