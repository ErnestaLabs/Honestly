#!/usr/bin/env python3
"""api/v1/products.py - FastAPI endpoints for the product catalog and purchase flow.

Endpoints:
  GET  /v1/products/catalog          - list products with tier-adjusted pricing
  POST /v1/products/purchase         - buy a product with atomic credit deduction

Credit deduction is ATOMIC:
  1. Check balance
  2. DECRBY in Redis (atomic)
  3. Execute the product engine
  4. If execution fails, INCRBY to refund (rollback)
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["products"])

# Redis key for credit balances (pence, integer - no float rounding issues)
_CREDIT_PENCE_PREFIX = "honestly:credits:pence:"


# ──────────────────────────────────────────────────────────── request models

class PurchaseRequest(BaseModel):
    user_id: str = Field(..., description="Telegram user ID")
    product_id: str = Field(..., description="Product slug from catalog")
    valuation_context: dict = Field(
        default_factory=dict,
        description="Context from the AVM run (address, comps, sqm, etc.)",
    )


# ──────────────────────────────────────────────────────────── auth helper

def _get_tier(authorization: str | None) -> str:
    if not authorization:
        return "free"
    try:
        token = authorization.replace("Bearer ", "").strip()
        parts = token.split(":")
        if len(parts) >= 2:
            return parts[1].lower()
        return "free"
    except Exception:
        return "free"


# ──────────────────────────────────────────────────────────── Redis helpers

def _get_redis():
    """Get a Redis client, or None if unavailable."""
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        r.ping()
        return r
    except Exception:
        return None


def _balance_pence_key(user_id: str) -> str:
    return f"{_CREDIT_PENCE_PREFIX}{user_id}"


def _get_balance_pence(user_id: str, redis_client=None) -> int:
    """Get the user's credit balance in pence from Redis.

    Falls back to the ProductEngine credit account if Redis is unavailable.
    """
    if redis_client:
        try:
            val = redis_client.get(_balance_pence_key(user_id))
            return int(val) if val else 0
        except Exception:
            pass

    # Fallback: read from ProductEngine
    try:
        from products.engine import ProductEngine
        engine = ProductEngine()
        credits = engine.get_credits(user_id)
        return int(credits.get("balance_gbp", 0) * 100)
    except Exception:
        return 0


def _set_balance_pence(user_id: str, pence: int, redis_client=None):
    """Set the user's credit balance in pence in Redis."""
    if redis_client:
        try:
            redis_client.set(_balance_pence_key(user_id), str(pence))
        except Exception:
            pass


# ──────────────────────────────────────────────────────────── endpoints

@router.get("/products/catalog")
def get_catalog(
    authorization: Optional[str] = Header(None),
):
    """Get the product catalog with tier-adjusted pricing.

    Pro users get 20% off, Plus users get 10% off.
    Free users pay full price.
    """
    from products.catalog import list_products
    from auth.entitlements import TIER_UPSELL_DISCOUNT_PCT

    tier = _get_tier(authorization)
    discount_pct = TIER_UPSELL_DISCOUNT_PCT.get(tier, 0)

    products = list_products(tier=tier if tier != "free" else "all")
    catalog = []
    for p in products:
        entry = p.to_dict()
        # Apply tier discount
        original_price = entry["gbp_price"]
        discounted_price = round(original_price * (1 - discount_pct / 100), 2)
        entry["original_gbp_price"] = original_price
        entry["effective_gbp_price"] = discounted_price
        entry["discount_pct"] = discount_pct
        # Convert to XTR for the Mini App UI
        from payments.stars_handler import gbp_to_xtr
        entry["xtr_price"] = gbp_to_xtr(discounted_price)
        entry["credit_cost_gbp"] = p.credit_cost_gbp or p.gbp_price
        catalog.append(entry)

    return {
        "ok": True,
        "tier": tier,
        "discount_pct": discount_pct,
        "products": catalog,
    }


@router.post("/products/purchase")
def purchase_product(
    req: PurchaseRequest,
    authorization: Optional[str] = Header(None),
):
    """Purchase a product with atomic credit deduction.

    ATOMIC FLOW:
      1. Validate product exists and user has tier access
      2. Calculate the effective credit cost (with tier discount)
      3. Check balance in Redis (GET)
      4. Atomically deduct credits (DECRBY - single Redis command, no race)
      5. Execute the product engine
      6. If execution fails: INCRBY to refund (rollback)
      7. Return the product result

    Returns 402 if insufficient credits.
    Returns 403 if tier access denied.
    Returns 500 if the product engine fails (with credit refund).
    """
    from products.catalog import get_product
    from auth.entitlements import TIER_LEVELS, TIER_UPSELL_DISCOUNT_PCT

    tier = _get_tier(authorization)
    user_id = req.user_id

    # Step 1: Validate product
    product = get_product(req.product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Unknown product: {req.product_id}")

    # Step 2: Check tier access
    user_level = TIER_LEVELS.get(tier, 0)
    product_level = TIER_LEVELS.get(product.tier_access, 0)
    if user_level < product_level:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tier_access_denied",
                "message": f"This product requires {product.tier_access} tier or above",
                "required_tier": product.tier_access,
                "current_tier": tier,
            },
        )

    # Step 3: Calculate effective credit cost
    discount_pct = TIER_UPSELL_DISCOUNT_PCT.get(tier, 0)
    base_cost = product.credit_cost_gbp or product.gbp_price
    effective_cost_gbp = round(base_cost * (1 - discount_pct / 100), 2)
    cost_pence = int(effective_cost_gbp * 100)

    # Step 4: Atomic credit deduction via Redis DECRBY
    redis_client = _get_redis()
    balance_key = _balance_pence_key(user_id)

    if redis_client:
        try:
            # DECRBY is atomic in Redis - no race condition possible
            new_balance_pence = redis_client.decrby(balance_key, cost_pence)

            if new_balance_pence < 0:
                # Insufficient funds - roll back the deduction
                redis_client.incrby(balance_key, cost_pence)
                current_balance_gbp = (new_balance_pence + cost_pence) / 100
                raise HTTPException(
                    status_code=402,
                    detail={
                        "error": "insufficient_credits",
                        "message": f"Need £{effective_cost_gbp:.2f}, have £{current_balance_gbp:.2f}",
                        "required_gbp": effective_cost_gbp,
                        "balance_gbp": round(current_balance_gbp, 2),
                        "product_id": req.product_id,
                        "upgrade_prompt": "Top up credits or upgrade your tier for a discount",
                    },
                )
        except HTTPException:
            raise
        except Exception as e:
            log.error("Redis DECRBY failed for %s: %s", user_id, e)
            # Fallback: use ProductEngine's in-memory credit system
            raise HTTPException(
                status_code=503,
                detail={"error": "payment_system_unavailable", "message": "Credit system temporarily unavailable"},
            )
    else:
        # No Redis - use ProductEngine's credit system (non-atomic but functional)
        from products.engine import ProductEngine
        engine = ProductEngine()
        credits = engine.get_credits(user_id)
        balance_gbp = credits.get("balance_gbp", 0)
        if balance_gbp < effective_cost_gbp:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_credits",
                    "message": f"Need £{effective_cost_gbp:.2f}, have £{balance_gbp:.2f}",
                    "required_gbp": effective_cost_gbp,
                    "balance_gbp": balance_gbp,
                    "product_id": req.product_id,
                },
            )
        # Deduct via ProductEngine
        account = engine._get_credit_account(user_id)
        account.deduct(effective_cost_gbp)
        engine._save_credit_account(user_id, account)

    # Step 5: Execute the product engine
    execution_ok = False
    product_result = None
    try:
        # Build the subject dict from the valuation context
        subject = {
            "address": req.valuation_context.get("address", ""),
            "postcode": req.valuation_context.get("postcode", ""),
            "sqm": req.valuation_context.get("sqm"),
            "epc": req.valuation_context.get("epc"),
            "lat": req.valuation_context.get("lat"),
            "lng": req.valuation_context.get("lng"),
            "type": req.valuation_context.get("type"),
        }
        params = req.valuation_context

        # Use the real engine from products/engines/ if available,
        # otherwise fall back to the catalog execution function
        product_result = _execute_product(req.product_id, subject, params)
        execution_ok = product_result.get("ok", False)
    except Exception as e:
        log.error("Product execution failed for %s/%s: %s", user_id, req.product_id, e)
        product_result = {"ok": False, "error": str(e)}

    # Step 6: If execution failed, REFUND the credits
    if not execution_ok:
        if redis_client:
            try:
                # Atomic refund via INCRBY
                redis_client.incrby(balance_key, cost_pence)
                log.info("Credit refund: +%d pence for %s (product %s failed)",
                         cost_pence, user_id, req.product_id)
            except Exception as refund_err:
                log.critical("CREDIT REFUND FAILED for %s: %s. Manual intervention required.",
                             user_id, refund_err)
        else:
            # Refund via ProductEngine
            try:
                from products.engine import ProductEngine
                engine = ProductEngine()
                account = engine._get_credit_account(user_id)
                account.balance_gbp += effective_cost_gbp
                engine._save_credit_account(user_id, account)
            except Exception as refund_err:
                log.critical("CREDIT REFUND FAILED for %s: %s", user_id, refund_err)

        raise HTTPException(
            status_code=500,
            detail={
                "error": "product_execution_failed",
                "message": "The product engine encountered an error. Your credits have been refunded.",
                "product_id": req.product_id,
                "refunded_gbp": effective_cost_gbp,
                "original_error": product_result.get("error", "Unknown error"),
            },
        )

    # Step 7: Return the product result
    final_balance_pence = 0
    if redis_client:
        try:
            final_balance_pence = int(redis_client.get(balance_key) or 0)
        except Exception:
            pass

    return {
        "ok": True,
        "product_id": req.product_id,
        "product_name": product.name,
        "result": product_result,
        "charged_gbp": effective_cost_gbp,
        "discount_pct": discount_pct,
        "remaining_credits_gbp": round(final_balance_pence / 100, 2) if redis_client else None,
    }


def _execute_product(product_id: str, subject: dict, params: dict) -> dict:
    """Execute a product using the real engine from products/engines/ if available,
    otherwise fall back to the catalog execution function.

    This routes to the dedicated engine modules (lowball_engine, planning_oracle_engine,
    council_tax_engine) when the product_id matches, giving us the real implementations.
    """
    # Route to the dedicated engine modules
    if product_id == "lowball_counter_email":
        from products.engines.lowball_engine import generate_counter_email
        return generate_counter_email(
            subject_address=subject.get("address", ""),
            assessed_value=int(params.get("central", 0)),
            low_range=int(params.get("low", 0)),
            high_range=int(params.get("high", 0)),
            confidence_score=int(params.get("confidence_score", 50)),
            confidence_grade=params.get("confidence_grade", "Fair"),
            sqm=int(params.get("sqm", 0) or 0),
            epc_rating=params.get("epc", ""),
            lowball_offer=int(params.get("lowball_offer", 0)),
            evidence=params.get("evidence", []),
        )

    elif product_id == "planning_permission_oracle":
        from products.engines.planning_oracle_engine import assess_permitted_development
        return assess_permitted_development(
            address=subject.get("address", ""),
            ptype=subject.get("type", ""),
            sqm=int(params.get("sqm", 0) or 0),
            lat=params.get("lat"),
            lng=params.get("lng"),
            roof_type=params.get("roof_type"),
            conservation_area=params.get("conservation_area"),
        )

    elif product_id == "council_tax_challenger":
        from products.engines.council_tax_engine import assess_council_tax
        return assess_council_tax(
            subject_address=subject.get("address", ""),
            subject_sqm=int(params.get("sqm", 0) or 0),
            subject_epc=params.get("epc", ""),
            current_band=params.get("current_band", "D"),
            postcode=subject.get("postcode", ""),
        )

    # Fallback: use the catalog's execution function
    from products.catalog import execute_product
    return execute_product(product_id, subject, params)
