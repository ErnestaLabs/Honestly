#!/usr/bin/env python3
"""bot/webhook.py - Telegram payment webhook handlers.

Handles two Telegram payment signals:
  1. pre_checkout_query  - must answer within 10 seconds or payment fails
  2. successful_payment  - fulfilment after the user pays in Stars (XTR)

Payment payloads (JSON strings):
  - sub_plus       → Plus subscription (£5/mo = 250 XTR)
  - sub_pro        → Pro subscription (£15/mo = 750 XTR)
  - credits_500    → £10 credit top-up (500 XTR)
  - credits_250    → £5 credit top-up (250 XTR)
  - upsell_{id}    → Direct product purchase (product-specific XTR)
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

log = logging.getLogger(__name__)

# Redis key prefixes
_TIER_PREFIX = "honestly:tier:"
_EXPIRY_PREFIX = "honestly:tier_expiry:"
_CREDIT_PENCE_PREFIX = "honestly:credits:pence:"
_ENTITLEMENT_PREFIX = "honestly:entitlements:"


# ──────────────────────────────────────────────────────────── Redis helper

def _get_redis():
    """Get a Redis client, or None if unavailable."""
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        r.ping()
        return r
    except Exception:
        return None


# ──────────────────────────────────────────────────────────── pre_checkout_query

async def handle_pre_checkout(update: dict, bot_client=None) -> dict:
    """Handle a Telegram pre_checkout_query.

    Telegram requires an answerPreCheckoutQuery within 10 seconds.
    We always approve immediately. The actual fulfilment happens
    in the successful_payment handler.

    Returns: the answerPreCheckoutQuery payload to send back.
    """
    query_id = update.get("pre_checkout_query", {}).get("id", "")
    log.info("pre_checkout_query received: %s", query_id)

    return {
        "method": "answerPreCheckoutQuery",
        "pre_checkout_query_id": query_id,
        "ok": True,
    }


# ──────────────────────────────────────────────────────────── successful_payment

async def handle_successful_payment(update: dict, bot_client=None) -> dict:
    """Handle a Telegram successful_payment message.

    Extracts the payload and routes to the appropriate handler:
      - sub_plus / sub_pro → subscription activation
      - credits_500 / credits_250 → credit top-up
      - upsell_{id} → direct product entitlement

    Args:
        update: the Telegram update containing the successful_payment
        bot_client: optional bot client for sending confirmation messages

    Returns: a summary of what was processed.
    """
    message = update.get("message", {})
    payment = message.get("successful_payment", {})
    user_id = str(message.get("from", {}).get("id", ""))

    payload_str = payment.get("invoice_payload", "")
    paid_xtr = payment.get("total_amount", 0)
    currency = payment.get("currency", "")

    if currency != "XTR":
        log.warning("Non-XTR payment received: %s", currency)
        return {"ok": False, "error": "non_xtr_payment"}

    # Parse the payload
    try:
        payload = json.loads(payload_str)
    except Exception:
        log.error("Invalid payment payload: %s", payload_str[:200])
        return {"ok": False, "error": "invalid_payload"}

    log.info("successful_payment: user=%s, payload=%s, xtr=%d", user_id, payload.get("type"), paid_xtr)

    # Route to the appropriate handler
    payload_type = payload.get("type", "")

    if payload_type == "subscription":
        result = _handle_subscription(user_id, payload, paid_xtr)
    elif payload_type == "credit_topup":
        result = _handle_credit_topup(user_id, payload, paid_xtr)
    elif payload_type.startswith("upsell_"):
        result = _handle_upsell_purchase(user_id, payload, paid_xtr)
    else:
        # Generic product purchase
        product_id = payload.get("product_id", "")
        if product_id:
            result = _handle_upsell_purchase(user_id, payload, paid_xtr)
        elif payload_type in ("sub_plus", "sub_pro"):
            # Legacy format: payload type IS the subscription tier
            result = _handle_subscription(user_id, {"tier": payload_type.replace("sub_", "")}, paid_xtr)
        elif payload_type.startswith("credits_"):
            result = _handle_credit_topup(user_id, payload, paid_xtr)
        else:
            log.error("Unknown payment payload type: %s", payload_type)
            return {"ok": False, "error": f"unknown_payload_type: {payload_type}"}

    return result


# ──────────────────────────────────────────────────────────── subscription handler

def _handle_subscription(user_id: str, payload: dict, paid_xtr: int) -> dict:
    """Handle a Plus or Pro subscription payment.

    Steps:
      1. Verify the XTR amount matches the tier price
      2. Set the user's tier in Redis
      3. Set the expiry date (30 days from now)
      4. Grant monthly credits
    """
    from auth.entitlements import TIER_PRICE_GBP
    from payments.stars_handler import gbp_to_xtr, grant_monthly_credits

    tier = payload.get("tier", "")
    if tier not in ("plus", "pro"):
        return {"ok": False, "error": f"invalid_tier: {tier}"}

    # Step 1: Verify XTR amount
    expected_gbp = TIER_PRICE_GBP.get(tier, 0)
    expected_xtr = gbp_to_xtr(expected_gbp)
    if paid_xtr != expected_xtr:
        log.warning("XTR mismatch for %s sub: expected %d, got %d", tier, expected_xtr, paid_xtr)
        # Still process - the user already paid, just log the discrepancy

    # Step 2 + 3: Set tier and expiry in Redis
    redis_client = _get_redis()
    expiry_ts = int(time.time()) + 30 * 86400  # 30 days from now

    if redis_client:
        try:
            redis_client.set(f"{_TIER_PREFIX}{user_id}", tier)
            redis_client.set(f"{_EXPIRY_PREFIX}{user_id}", str(expiry_ts))
            log.info("Tier set: user=%s, tier=%s, expires=%d", user_id, tier, expiry_ts)
        except Exception as e:
            log.error("Failed to set tier in Redis for %s: %s", user_id, e)
    else:
        log.warning("Redis unavailable - tier not persisted for %s", user_id)

    # Step 4: Grant monthly credits
    granted = grant_monthly_credits(user_id, tier, redis_client)

    return {
        "ok": True,
        "type": "subscription",
        "user_id": user_id,
        "tier": tier,
        "expiry_ts": expiry_ts,
        "credits_granted_gbp": granted,
        "paid_xtr": paid_xtr,
    }


# ──────────────────────────────────────────────────────────── credit top-up handler

def _handle_credit_topup(user_id: str, payload: dict, paid_xtr: int) -> dict:
    """Handle a credit top-up payment.

    Adds the purchased credit amount to the user's Redis balance.
    """
    from payments.stars_handler import xtr_to_gbp

    # Calculate GBP equivalent (using the configured rate)
    gbp_amount = xtr_to_gbp(paid_xtr)
    pence_to_add = int(gbp_amount * 100)

    redis_client = _get_redis()
    if redis_client:
        try:
            new_balance_pence = redis_client.incrby(f"{_CREDIT_PENCE_PREFIX}{user_id}", pence_to_add)
            log.info("Credit top-up: user=%s, +£%.2f, new_balance=%d pence",
                     user_id, gbp_amount, new_balance_pence)
        except Exception as e:
            log.error("Failed to add credits in Redis for %s: %s", user_id, e)
            return {"ok": False, "error": "credit_add_failed"}
    else:
        # Fallback: use ProductEngine
        try:
            from products.engine import ProductEngine
            engine = ProductEngine()
            account = engine._get_credit_account(user_id)
            account.balance_gbp += gbp_amount
            engine._save_credit_account(user_id, account)
        except Exception as e:
            log.error("Failed to add credits via ProductEngine for %s: %s", user_id, e)
            return {"ok": False, "error": "credit_add_failed"}

    return {
        "ok": True,
        "type": "credit_topup",
        "user_id": user_id,
        "added_gbp": gbp_amount,
        "added_pence": pence_to_add,
        "paid_xtr": paid_xtr,
    }


# ──────────────────────────────────────────────────────────── upsell purchase handler

def _handle_upsell_purchase(user_id: str, payload: dict, paid_xtr: int) -> dict:
    """Handle a direct upsell product purchase via Telegram payment.

    Adds the product entitlement to the user's profile so they can
    access it without spending credits.
    """
    from payments.stars_handler import xtr_to_gbp

    product_id = payload.get("product_id", "")
    if not product_id:
        return {"ok": False, "error": "missing_product_id"}

    # Validate the product exists
    from products.catalog import get_product
    product = get_product(product_id)
    if not product:
        return {"ok": False, "error": f"unknown_product: {product_id}"}

    gbp_charged = xtr_to_gbp(paid_xtr)

    # Add the product entitlement to the user's profile in Redis
    redis_client = _get_redis()
    if redis_client:
        try:
            entitlement_key = f"{_ENTITLEMENT_PREFIX}{user_id}:{product_id}"
            redis_client.set(entitlement_key, json.dumps({
                "product_id": product_id,
                "purchased_ts": int(time.time()),
                "paid_xtr": paid_xtr,
                "paid_gbp": gbp_charged,
            }))
            log.info("Upsell entitlement: user=%s, product=%s, xtr=%d",
                     user_id, product_id, paid_xtr)
        except Exception as e:
            log.error("Failed to set entitlement in Redis for %s/%s: %s",
                      user_id, product_id, e)
    else:
        log.warning("Redis unavailable - entitlement not persisted for %s/%s",
                     user_id, product_id)

    return {
        "ok": True,
        "type": "upsell_purchase",
        "user_id": user_id,
        "product_id": product_id,
        "product_name": product.name,
        "paid_xtr": paid_xtr,
        "paid_gbp": gbp_charged,
    }
