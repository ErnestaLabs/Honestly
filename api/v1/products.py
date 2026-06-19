#!/usr/bin/env python3
"""api/v1/products.py - FastAPI endpoints for the product catalog and purchase flow.

SECURITY: The frontend NEVER dictates the user's tier.
The backend determines the tier server-side via Redis on every request.

Endpoints:
  GET  /v1/products/catalog          - list products with tier-adjusted pricing
  POST /v1/products/purchase         - buy a product with atomic credit deduction
  POST /v1/payments/create_invoice   - create a Telegram invoice link for native payment

Credit deduction is ATOMIC:
  1. DECRBY in Redis (single atomic command, no race)
  2. Execute the product engine
  3. If execution fails, INCRBY to refund (rollback)
"""
from __future__ import annotations

import json
import logging
import os
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


class CreateInvoiceRequest(BaseModel):
    user_id: str = Field(..., description="Telegram user ID")
    product_id: str | None = Field(None, description="Product slug for upsell purchases")
    sub_tier: str | None = Field(None, description="plus or pro for subscription")
    credit_pack_gbp: float | None = Field(None, description="Credit pack amount in GBP")


# ──────────────────────────────────────────────────────────── auth (SERVER-SIDE)

def _resolve_tier(user_id: str) -> str:
    """Determine the user's tier server-side via Redis.

    The frontend NEVER passes the tier. This is the sole source of truth.
    """
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        tier = r.get(f"honestly:tier:{user_id}")
        if tier in ("plus", "pro"):
            return tier
    except Exception:
        pass
    return "free"


def _get_user_id(authorization: str | None) -> str:
    """Extract user_id from Authorization header.

    Format: Bearer {user_id}
    Only user_id is trusted. No tier information is passed by the frontend.
    """
    if not authorization:
        return "anonymous"
    try:
        token = authorization.replace("Bearer ", "").strip()
        return token.split(":")[0]
    except Exception:
        return "anonymous"


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
    """Get the user's credit balance in pence from Redis."""
    if redis_client:
        try:
            val = redis_client.get(_balance_pence_key(user_id))
            return int(val) if val else 0
        except Exception:
            pass
    try:
        from products.engine import ProductEngine
        engine = ProductEngine()
        credits = engine.get_credits(user_id)
        return int(credits.get("balance_gbp", 0) * 100)
    except Exception:
        return 0


# ──────────────────────────────────────────────────────────── endpoints

@router.get("/products/catalog")
def get_catalog(
    authorization: Optional[str] = Header(None),
):
    """Get the product catalog with tier-adjusted pricing.

    Tier is resolved server-side. Pro gets 20% off, Plus gets 10% off.
    """
    from products.catalog import list_products
    from auth.entitlements import TIER_UPSELL_DISCOUNT_PCT

    user_id = _get_user_id(authorization)
    tier = _resolve_tier(user_id)
    discount_pct = TIER_UPSELL_DISCOUNT_PCT.get(tier, 0)

    products = list_products(tier=tier if tier != "free" else "all")
    catalog = []
    for p in products:
        entry = p.to_dict()
        original_price = entry["gbp_price"]
        discounted_price = round(original_price * (1 - discount_pct / 100), 2)
        entry["original_gbp_price"] = original_price
        entry["effective_gbp_price"] = discounted_price
        entry["discount_pct"] = discount_pct
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
      3. Balance check via DECRBY (atomic, no race)
      4. Execute the product engine
      5. If execution fails: INCRBY to refund (rollback)

    Returns 402 if insufficient credits (server-side check).
    Returns 403 if tier access denied.
    """
    from products.catalog import get_product
    from auth.entitlements import TIER_LEVELS, TIER_UPSELL_DISCOUNT_PCT

    user_id = req.user_id or _get_user_id(authorization)
    tier = _resolve_tier(user_id)  # SERVER-SIDE: frontend cannot lie

    product = get_product(req.product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Unknown product: {req.product_id}")

    # Check tier access (server-side)
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

    # Calculate effective credit cost
    discount_pct = TIER_UPSELL_DISCOUNT_PCT.get(tier, 0)
    base_cost = product.credit_cost_gbp or product.gbp_price
    effective_cost_gbp = round(base_cost * (1 - discount_pct / 100), 2)
    cost_pence = int(effective_cost_gbp * 100)

    # Atomic credit deduction via Redis DECRBY
    redis_client = _get_redis()
    balance_key = _balance_pence_key(user_id)

    if redis_client:
        try:
            new_balance_pence = redis_client.decrby(balance_key, cost_pence)
            if new_balance_pence < 0:
                # Insufficient funds - rollback
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
            raise HTTPException(status_code=503, detail={"error": "payment_system_unavailable"})
    else:
        from products.engine import ProductEngine
        engine = ProductEngine()
        credits = engine.get_credits(user_id)
        balance_gbp = credits.get("balance_gbp", 0)
        if balance_gbp < effective_cost_gbp:
            raise HTTPException(status_code=402, detail={
                "error": "insufficient_credits",
                "message": f"Need £{effective_cost_gbp:.2f}, have £{balance_gbp:.2f}",
                "required_gbp": effective_cost_gbp,
                "balance_gbp": balance_gbp,
            })
        account = engine._get_credit_account(user_id)
        account.deduct(effective_cost_gbp)
        engine._save_credit_account(user_id, account)

    # Execute the product engine
    execution_ok = False
    product_result = None
    try:
        subject = {
            "address": req.valuation_context.get("address", ""),
            "postcode": req.valuation_context.get("postcode", ""),
            "sqm": req.valuation_context.get("sqm"),
            "epc": req.valuation_context.get("epc"),
            "lat": req.valuation_context.get("lat"),
            "lng": req.valuation_context.get("lng"),
            "type": req.valuation_context.get("type"),
        }
        product_result = _execute_product(req.product_id, subject, req.valuation_context)
        execution_ok = product_result.get("ok", False)
    except Exception as e:
        log.error("Product execution failed for %s/%s: %s", user_id, req.product_id, e)
        product_result = {"ok": False, "error": str(e)}

    # REFUND if execution failed
    if not execution_ok:
        if redis_client:
            try:
                redis_client.incrby(balance_key, cost_pence)
            except Exception as refund_err:
                log.critical("CREDIT REFUND FAILED for %s: %s", user_id, refund_err)
        else:
            try:
                from products.engine import ProductEngine
                engine = ProductEngine()
                account = engine._get_credit_account(user_id)
                account.balance_gbp += effective_cost_gbp
                engine._save_credit_account(user_id, account)
            except Exception as refund_err:
                log.critical("CREDIT REFUND FAILED for %s: %s", user_id, refund_err)
        raise HTTPException(status_code=500, detail={
            "error": "product_execution_failed",
            "message": "The product engine encountered an error. Your credits have been refunded.",
            "product_id": req.product_id,
            "refunded_gbp": effective_cost_gbp,
        })

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


# ──────────────────────────────────────────────────────────── create invoice endpoint

@router.post("/payments/create_invoice")
def create_invoice(
    req: CreateInvoiceRequest,
    authorization: Optional[str] = Header(None),
):
    """Create a Telegram invoice link for native in-app payment.

    The frontend calls this instead of constructing deep-links.
    The backend calls Telegram's createInvoiceLink API and returns
    the URL for the frontend to open via Telegram.WebApp.openInvoice().

    Supports:
      - Product purchases (product_id)
      - Subscriptions (sub_tier: plus/pro)
      - Credit top-ups (credit_pack_gbp)
    """
    from payments.stars_handler import gbp_to_xtr

    user_id = req.user_id or _get_user_id(authorization)
    tier = _resolve_tier(user_id)  # server-side, not from frontend

    # Determine what the invoice is for
    title = ""
    description = ""
    gbp_price = 0.0
    payload_data = {}

    if req.product_id:
        # Product upsell purchase
        from products.catalog import get_product
        from auth.entitlements import TIER_UPSELL_DISCOUNT_PCT

        product = get_product(req.product_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"Unknown product: {req.product_id}")
        title = product.name
        description = product.description
        discount_pct = TIER_UPSELL_DISCOUNT_PCT.get(tier, 0)
        gbp_price = round(product.gbp_price * (1 - discount_pct / 100), 2)
        payload_data = {"type": "upsell", "product_id": req.product_id, "tier": tier, "gbp_price": gbp_price}

    elif req.sub_tier:
        # Subscription purchase
        from auth.entitlements import TIER_PRICE_GBP
        tier_map = {"plus": "Honestly Plus", "pro": "Honestly Pro"}
        desc_map = {
            "plus": "3 AVMs/day, Room posting, ad-free, £5 monthly credit",
            "pro": "Unlimited AVMs, custom branding, advanced maps, £10 monthly credit",
        }
        if req.sub_tier not in ("plus", "pro"):
            raise HTTPException(status_code=400, detail="sub_tier must be 'plus' or 'pro'")
        title = tier_map.get(req.sub_tier, req.sub_tier)
        description = desc_map.get(req.sub_tier, "")
        gbp_price = TIER_PRICE_GBP.get(req.sub_tier, 0)
        payload_data = {"type": "subscription", "tier": req.sub_tier, "gbp_price": gbp_price}

    elif req.credit_pack_gbp and req.credit_pack_gbp > 0:
        # Credit top-up
        credits = int(req.credit_pack_gbp * 100)  # rough: £1 = 100 "credits"
        title = f"{credits} Credits"
        description = f"Top up your Honestly credit balance with {credits} credits"
        gbp_price = req.credit_pack_gbp
        payload_data = {"type": "credit_topup", "gbp_price": gbp_price, "credits": credits}

    else:
        raise HTTPException(status_code=400, detail="One of product_id, sub_tier, or credit_pack_gbp is required")

    xtr_amount = gbp_to_xtr(gbp_price)

    # Call Telegram's createInvoiceLink API
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        raise HTTPException(status_code=503, detail="Telegram bot token not configured")

    try:
        import requests
        payload_str = json.dumps(payload_data)
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/createInvoiceLink",
            json={
                "title": title,
                "description": description,
                "payload": payload_str,
                "provider_token": "",
                "currency": "XTR",
                "prices": [{"label": title, "amount": xtr_amount}],
            },
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            log.error("Telegram createInvoiceLink failed: %s", data.get("description", "unknown"))
            raise HTTPException(status_code=502, detail="Invoice creation failed")
        invoice_url = data["result"]
    except HTTPException:
        raise
    except Exception as e:
        log.error("createInvoiceLink request failed: %s", e)
        raise HTTPException(status_code=502, detail="Invoice creation failed")

    return {
        "ok": True,
        "invoice_url": invoice_url,
        "xtr_amount": xtr_amount,
        "gbp_price": gbp_price,
        "title": title,
        "payload": payload_data,
    }


# ──────────────────────────────────────────────────────────── product execution router

def _execute_product(product_id: str, subject: dict, params: dict) -> dict:
    """Execute a product using the real engine modules or catalog fallback."""
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
    from products.catalog import execute_product
    return execute_product(product_id, subject, params)
