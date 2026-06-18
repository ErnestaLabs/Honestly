#!/usr/bin/env python3
"""payments/stars_handler.py - Telegram Stars (XTR) payment integration.

Telegram requires sendInvoice to use XTR (Telegram Stars), not GBP.
This module handles the GBP → XTR conversion and payment flow.

Currency conversion:
  £1 GBP = 50 XTR (Telegram's rate)
  The catalog.py only knows GBP. This module is the only place
  that speaks XTR.

Payment flow:
  1. User taps a product button in the Mini App
  2. Bot sends an invoice with XTR amount
  3. User pays in Stars
  4. Telegram sends pre_checkout_query + successful_payment
  5. We verify, execute the product, and deliver
"""
from __future__ import annotations
import json
import os
import time
from typing import Optional

# ──────────────────────────────────────────────────────────── constants

# £1 GBP = 50 XTR (Telegram Stars)
# This is the conversion rate used for ALL pricing.
# The UI and catalog.py only know GBP. This module converts to XTR
# only when calling the Telegram payment API.
GBP_TO_XTR = 50

# Minimum XTR amount for a Telegram invoice (1 XTR)
MIN_XTR = 1

# ──────────────────────────────────────────────────────────── conversion

def gbp_to_xtr(gbp: float) -> int:
    """Convert GBP to XTR (Telegram Stars). Rounds up to minimum 1."""
    xtr = int(round(gbp * GBP_TO_XTR))
    return max(MIN_XTR, xtr)


def xtr_to_gbp(xtr: int) -> float:
    """Convert XTR back to GBP (for audit/display)."""
    return round(xtr / GBP_TO_XTR, 2)


# ──────────────────────────────────────────────────────────── invoice builder

def build_invoice(
    product_id: str,
    gbp_price: float,
    user_tier: str = "free",
    discount_pct: float = 0.0,
) -> dict:
    """Build a Telegram sendInvoice payload for a product.

    Applies tier discounts and converts to XTR for the invoice.

    Returns: the payload for sendInvoice (chat_id must be added by caller).
    """
    from products.catalog import get_product

    product = get_product(product_id)
    if not product:
        return {"ok": False, "error": f"Unknown product: {product_id}"}

    # Apply tier discount
    effective_gbp = gbp_price * (1 - discount_pct / 100)
    xtr_amount = gbp_to_xtr(effective_gbp)

    return {
        "ok": True,
        "title": product.name,
        "description": product.description,
        "payload": json.dumps({
            "product_id": product_id,
            "gbp_price": effective_gbp,
            "xtr_amount": xtr_amount,
            "tier": user_tier,
            "ts": int(time.time()),
        }),
        "provider_token": "",  # Empty for XTR payments
        "currency": "XTR",
        "prices": [{"label": product.name, "amount": xtr_amount}],
        "start_parameter": f"honestly_{product_id}",
    }


def build_subscription_invoice(tier: str) -> dict:
    """Build a Telegram sendInvoice payload for a subscription.

    Args:
        tier: "plus" or "pro"

    Returns: the payload for sendInvoice.
    """
    from auth.entitlements import TIER_PRICE_GBP

    gbp = TIER_PRICE_GBP.get(tier, 0)
    if gbp == 0:
        return {"ok": False, "error": "Free tier has no subscription"}

    xtr_amount = gbp_to_xtr(gbp)
    tier_names = {"plus": "Honestly Plus", "pro": "Honestly Pro"}
    tier_descriptions = {
        "plus": "3 AVMs/day, Room posting, ad-free, £5 monthly credit",
        "pro": "Unlimited AVMs, custom branding, advanced maps, £10 monthly credit",
    }

    return {
        "ok": True,
        "title": tier_names.get(tier, tier),
        "description": tier_descriptions.get(tier, ""),
        "payload": json.dumps({
            "type": "subscription",
            "tier": tier,
            "gbp_price": gbp,
            "xtr_amount": xtr_amount,
            "ts": int(time.time()),
        }),
        "provider_token": "",
        "currency": "XTR",
        "prices": [{"label": tier_names.get(tier, tier), "amount": xtr_amount}],
        "subscription_period": 2592000,  # 30 days in seconds
        "start_parameter": f"honestly_sub_{tier}",
    }


# ──────────────────────────────────────────────────────────── payment verification

def verify_payment(payload_str: str, paid_xtr: int) -> dict:
    """Verify a successful Telegram payment.

    Checks that the paid XTR amount matches the expected GBP price.

    Returns: {"ok": bool, "product_id": str, "gbp_charged": float}
    """
    try:
        payload = json.loads(payload_str)
    except Exception:
        return {"ok": False, "error": "Invalid payload JSON"}

    expected_xtr = gbp_to_xtr(payload.get("gbp_price", 0))
    if paid_xtr != expected_xtr:
        return {"ok": False, "error": f"XTR mismatch: expected {expected_xtr}, got {paid_xtr}"}

    return {
        "ok": True,
        "product_id": payload.get("product_id"),
        "tier": payload.get("tier"),
        "gbp_charged": xtr_to_gbp(paid_xtr),
        "type": payload.get("type", "product"),
    }


# ──────────────────────────────────────────────────────────── monthly credit grant

def grant_monthly_credits(user_id: str, tier: str, redis_client=None) -> float:
    """Grant monthly credits to a user based on their tier.

    Called when a subscription is activated or renewed.
    Credits are added to the ProductEngine credit account.

    Returns: the amount granted in GBP.
    """
    from auth.entitlements import TIER_CREDITS
    from products.engine import ProductEngine, CreditAccount

    grant = TIER_CREDITS.get(tier, 0)
    if grant <= 0:
        return 0

    engine = ProductEngine(redis_client)
    account = engine._get_credit_account(user_id)

    # Only grant once per month
    current_month = time.strftime("%Y-%m")
    if account.last_grant_date == current_month:
        return 0  # already granted this month

    account.last_grant_date = current_month
    account.balance_gbp += grant
    account.monthly_grant_gbp = grant
    engine._save_credit_account(user_id, account)

    return grant
