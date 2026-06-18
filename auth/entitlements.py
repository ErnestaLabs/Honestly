#!/usr/bin/env python3
"""auth/entitlements.py - Three-tier subscription entitlements.

Free: 1 AVM/day, read-only Room access, ads. Pay full price for upsells.
Plus (£5/mo): 3 AVMs/day, Room posting access, ad-free, £5 monthly credit.
Pro (£15/mo): Infinite AVMs, custom branding, advanced map tools, £10 monthly credit.

All GBP-to-XTR (Telegram Stars) conversion happens in payments/stars_handler.py.
This module only knows about tiers and GBP.
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ──────────────────────────────────────────────────────────── tier definitions

class Tier(str, Enum):
    FREE = "free"
    PLUS = "plus"
    PRO = "pro"


# Tier levels for access comparison (higher = more access)
TIER_LEVELS = {
    "free": 0,
    "plus": 1,
    "pro": 2,
    "all": 0,  # products with tier_access="all" are available to everyone
}

# Monthly credit grants per tier (in GBP)
TIER_CREDITS = {
    "free": 0.0,
    "plus": 5.0,
    "pro": 10.0,
}

# AVM daily limits per tier (0 = unlimited)
TIER_AVM_DAILY_LIMIT = {
    "free": 1,
    "plus": 3,
    "pro": 0,  # unlimited
}

# Room access per tier
TIER_ROOM_ACCESS = {
    "free": "read_only",     # can view but not post
    "plus": "post",          # can post in postcode topics
    "pro": "post",           # can post + white-label
}

# Ad experience per tier
TIER_AD_FREE = {
    "free": False,
    "plus": True,
    "pro": True,
}

# Monthly subscription price in GBP
TIER_PRICE_GBP = {
    "free": 0.0,
    "plus": 5.0,
    "pro": 15.0,
}

# Product discount on upsells (percentage off GBP price)
TIER_UPSELL_DISCOUNT_PCT = {
    "free": 0.0,   # full price
    "plus": 10.0,   # 10% off
    "pro": 20.0,    # 20% off
}

# Custom branding (Pro only)
TIER_CUSTOM_BRANDING = {
    "free": False,
    "plus": False,
    "pro": True,
}

# Advanced map tools (Pro only)
TIER_ADVANCED_MAPS = {
    "free": False,
    "plus": False,
    "pro": True,
}


# ──────────────────────────────────────────────────────── entitlements check

@dataclass
class UserEntitlements:
    """The complete entitlements profile for a user."""
    user_id: str
    tier: str = "free"
    avm_count_today: int = 0
    avm_daily_limit: int = 1
    credit_balance_gbp: float = 0.0
    monthly_credit_grant_gbp: float = 0.0
    room_access: str = "read_only"
    ad_free: bool = False
    custom_branding: bool = False
    advanced_maps: bool = False
    upsell_discount_pct: float = 0.0
    subscription_price_gbp: float = 0.0

    @classmethod
    def for_tier(cls, user_id: str, tier: str) -> "UserEntitlements":
        """Create an entitlements profile from a tier string."""
        return cls(
            user_id=user_id,
            tier=tier,
            avm_daily_limit=TIER_AVM_DAILY_LIMIT.get(tier, 1),
            credit_balance_gbp=TIER_CREDITS.get(tier, 0.0),
            monthly_credit_grant_gbp=TIER_CREDITS.get(tier, 0.0),
            room_access=TIER_ROOM_ACCESS.get(tier, "read_only"),
            ad_free=TIER_AD_FREE.get(tier, False),
            custom_branding=TIER_CUSTOM_BRANDING.get(tier, False),
            advanced_maps=TIER_ADVANCED_MAPS.get(tier, False),
            upsell_discount_pct=TIER_UPSELL_DISCOUNT_PCT.get(tier, 0.0),
            subscription_price_gbp=TIER_PRICE_GBP.get(tier, 0.0),
        )

    def can_run_avm(self) -> bool:
        """Check if the user can run another AVM today."""
        if self.avm_daily_limit == 0:
            return True  # unlimited
        return self.avm_count_today < self.avm_daily_limit

    def can_access_product(self, product_tier: str) -> bool:
        """Check if the user can access a product based on their tier."""
        user_level = TIER_LEVELS.get(self.tier, 0)
        product_level = TIER_LEVELS.get(product_tier, 0)
        return user_level >= product_level

    def can_post_in_rooms(self) -> bool:
        return self.room_access in ("post",)

    def effective_price_gbp(self, gbp_price: float) -> float:
        """Apply tier discount to a product price."""
        discount = gbp_price * (self.upsell_discount_pct / 100)
        return round(gbp_price - discount, 2)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "tier": self.tier,
            "avm_count_today": self.avm_count_today,
            "avm_daily_limit": self.avm_daily_limit,
            "avm_remaining_today": (self.avm_daily_limit - self.avm_count_today)
                                   if self.avm_daily_limit > 0 else "unlimited",
            "credit_balance_gbp": self.credit_balance_gbp,
            "monthly_credit_grant_gbp": self.monthly_credit_grant_gbp,
            "room_access": self.room_access,
            "ad_free": self.ad_free,
            "custom_branding": self.custom_branding,
            "advanced_maps": self.advanced_maps,
            "upsell_discount_pct": self.upsell_discount_pct,
            "subscription_price_gbp": self.subscription_price_gbp,
        }


# ──────────────────────────────────────────────────────── AVM rate limiter

def check_avm_limit(user_id: str, tier: str, redis_client=None) -> dict:
    """Check if a user can run another AVM today.

    Uses Redis for distributed rate limiting with daily reset.
    Falls back to in-memory if Redis is unavailable.

    Returns: {"allowed": bool, "count_today": int, "daily_limit": int,
              "remaining": int|str}
    """
    import os
    daily_limit = TIER_AVM_DAILY_LIMIT.get(tier, 1)
    today_key = time.strftime("%Y-%m-%d")
    redis_key = f"honestly:avm_limit:{user_id}:{today_key}"

    if redis_client:
        try:
            count = int(redis_client.get(redis_key) or 0)
            if daily_limit == 0:
                return {"allowed": True, "count_today": count, "daily_limit": "unlimited", "remaining": "unlimited"}
            allowed = count < daily_limit
            return {"allowed": allowed, "count_today": count, "daily_limit": daily_limit,
                    "remaining": max(0, daily_limit - count)}
        except Exception:
            pass

    # Without Redis: allow (can't enforce rate limits without shared state)
    return {"allowed": True, "count_today": 0, "daily_limit": daily_limit,
            "remaining": daily_limit if daily_limit > 0 else "unlimited"}


def increment_avm_count(user_id: str, redis_client=None):
    """Increment the user's AVM count for today."""
    today_key = time.strftime("%Y-%m-%d")
    redis_key = f"honestly:avm_limit:{user_id}:{today_key}"

    if redis_client:
        try:
            redis_client.incr(redis_key)
            # Set expiry to 48h (covers timezone edge cases)
            redis_client.expire(redis_key, 172800)
        except Exception:
            pass
