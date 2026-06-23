"""core/alerts_engine.py — Plus-tier price change alerts and retention engine.

Drives user retention by notifying tracked property owners of market momentum
shifts. Each alert notification naturally drives the user back to the app,
which feeds the returned_7_days signal into the intent engine.

Architecture:
  - Tracked properties stored in Redis (fast path, no Postgres dependency).
  - Daily check compares current market momentum against the saved baseline.
  - If momentum shifted > 2%, enqueue a Telegram notification.
  - The notification link leads to an updated appraisal → intent signal.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ── Redis key namespace ──────────────────────────────────
_PREFIX_TRACKED = "honestly:alerts:tracked:"       # hash: user_id -> property data
_PREFIX_MOMENTUM = "honestly:alerts:momentum:"      # key: postcode -> baseline index
_PREFIX_QUEUE = "honestly:alerts:notify_queue"      # list: pending Telegram messages
_PREFIX_SENT = "honestly:alerts:sent:"              # set: dedup notification IDs

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _redis():
    import redis as redis_mod
    return redis_mod.Redis.from_url(REDIS_URL, decode_responses=True)


# ── Track a property ───────────────────────────────────────────────────────
def track_property(
    user_id: str,
    property_id: str,
    postcode: str,
    assessed_value: float,
    address: str = "",
) -> bool:
    """Register a Plus/Pro user to track a property for price alerts.

    Stores the current assessed_value as the baseline. The daily check
    compares future market data against this baseline.

    Args:
        user_id: Telegram user ID.
        property_id: Property identifier (full postcode or address hash).
        postcode: Postcode outcode (e.g. SW16).
        assessed_value: Current AVM central value in GBP.
        address: Human-readable address (for the alert message).

    Returns:
        True if successfully tracked, False on error.
    """
    try:
        r = _redis()
        key = f"{_PREFIX_TRACKED}{user_id}"
        now = time.time()

        # Store as a JSON blob in a hash per user (keyed by property_id)
        entry = json.dumps({
            "property_id": property_id,
            "postcode": postcode,
            "assessed_value": assessed_value,
            "address": address,
            "tracked_at": now,
            "baseline_assessed_value": assessed_value,
            "last_notified_value": None,
            "last_notified_at": None,
        })
        r.hset(key, property_id, entry)
        r.expire(key, 365 * 86400)  # 1 year TTL (auto-clean stale tracks)

        # Also keep a set of all tracked postcodes for the daily scanner
        r.sadd("honestly:alerts:tracked_postcodes", postcode)
        r.expire("honestly:alerts:tracked_postcodes", 365 * 86400)

        log.info(
            "Property tracked: user=%s property=%s postcode=%s value=£%.0f",
            user_id, property_id, postcode, assessed_value,
        )
        return True

    except Exception as e:
        log.warning("Failed to track property: %s", e)
        return False


# ── Get tracked properties for a user ──────────────────────────────────────
def get_tracked_properties(user_id: str) -> list[dict]:
    """Return all properties tracked by a given user."""
    try:
        r = _redis()
        key = f"{_PREFIX_TRACKED}{user_id}"
        entries = r.hgetall(key)
        result = []
        for prop_id, data_json in entries.items():
            try:
                data = json.loads(data_json)
                result.append(data)
            except (json.JSONDecodeError, TypeError):
                continue
        return result
    except Exception as e:
        log.warning("Failed to get tracked properties for %s: %s", user_id, e)
        return []


def untrack_property(user_id: str, property_id: str) -> bool:
    """Remove a property from a user's tracking list."""
    try:
        r = _redis()
        key = f"{_PREFIX_TRACKED}{user_id}"
        r.hdel(key, property_id)
        return True
    except Exception as e:
        log.warning("Failed to untrack property: %s", e)
        return False


# ── Momentum check and alert generation ────────────────────────────────────
def check_daily_alerts() -> int:
    """Check all tracked properties for market momentum shifts > 2%.

    This is designed to be called by APScheduler daily at 08:00 UTC.
    It scans all tracked properties, checks current market momentum
    against the saved baseline, and enqueues Telegram notifications
    for properties that have shifted significantly.

    Returns:
        Number of alerts enqueued.
    """
    t0 = time.time()
    alerts_enqueued = 0
    processed = 0

    try:
        r = _redis()
        tracked_postcodes = r.smembers("honestly:alerts:tracked_postcodes")
        if not tracked_postcodes:
            log.info("No tracked postcodes — skipping daily alert check")
            return 0

        # Get all tracked users
        cursor = 0
        user_keys = []
        while cursor is not None:
            cursor, keys = r.scan(
                cursor=cursor, match=f"{_PREFIX_TRACKED}*", count=500
            )
            user_keys.extend(keys)
            if cursor == 0:
                break

        for user_key in user_keys:
            user_id = user_key.replace(_PREFIX_TRACKED, "")
            entries = r.hgetall(user_key)
            for prop_id, data_json in entries.items():
                processed += 1
                try:
                    data = json.loads(data_json)
                    postcode = data.get("postcode", "")
                    baseline = data.get("baseline_assessed_value", 0)

                    # Quick market momentum check
                    current_index = _get_postcode_momentum(postcode)
                    if current_index is None:
                        continue

                    # Calculate percentage change
                    if baseline > 0:
                        change_pct = round(
                            (current_index - baseline) / baseline * 100, 1
                        )
                    else:
                        change_pct = 0

                    # Threshold: > 2% shift triggers an alert
                    if abs(change_pct) > 2.0:
                        # Check dedup (don't notify for the same shift twice)
                        dedup_key = (
                            f"{_PREFIX_SENT}{user_id}:{prop_id}:{postcode}"
                        )
                        dedup_id = f"{change_pct:.1f}_{int(time.time() / 86400)}"
                        already_sent = r.sismember(dedup_key, dedup_id)
                        if already_sent:
                            continue

                        # Enqueue notification
                        direction = "increased" if change_pct > 0 else "decreased"
                        emoji = "📈" if change_pct > 0 else "📉"
                        address_display = data.get(
                            "address", f"your tracked property in {postcode}"
                        )
                        message = (
                            f"{emoji} Market Update for {postcode}!\n\n"
                            f"{address_display}\n\n"
                            f"The market momentum in {postcode} has {direction} "
                            f"by {abs(change_pct):.1f}% since you last checked.\n\n"
                            f"Your estimated value has shifted from "
                            f"£{baseline:,.0f} to £{current_index:,.0f}.\n\n"
                            f"👉 Tap here to see your updated appraisal: "
                            f"https://usehonestly.co.uk/appraisal?property={prop_id}"
                        )

                        notification = json.dumps({
                            "user_id": user_id,
                            "property_id": prop_id,
                            "postcode": postcode,
                            "change_pct": change_pct,
                            "baseline_value": baseline,
                            "current_value": current_index,
                            "message": message,
                            "created_at": time.time(),
                        })
                        r.rpush(_PREFIX_QUEUE, notification)
                        r.sadd(dedup_key, dedup_id)
                        r.expire(dedup_key, 86400)  # dedup for 24h
                        alerts_enqueued += 1

                except (json.JSONDecodeError, TypeError, KeyError) as e:
                    log.debug("Skipping alert entry: %s", e)
                    continue

        elapsed = time.time() - t0
        log.info(
            "Alert check complete: %d properties scanned, %d alerts enqueued in %.1fs",
            processed, alerts_enqueued, elapsed,
        )

    except Exception as e:
        log.warning("Daily alert check failed: %s", e)

    return alerts_enqueued


# ── Momentum data: current market index per postcode ───────────────────────
def _get_postcode_momentum(postcode: str) -> float | None:
    """Get the current market momentum index for a postcode.

    Uses the HMLR sales data via graph_db.py to compute a median price
    for the postcode. Falls back to a cached value in Redis.

    This is a lightweight query — NOT a full AVM — just a median of
    recent sales to detect directional shifts.
    """
    try:
        # Check Redis cache first
        r = _redis()
        cache_key = f"{_PREFIX_MOMENTUM}{postcode}"
        cached = r.get(cache_key)
        if cached:
            return float(cached)

        # Query HMLR data for last 3 months of sales
        from graph_db import GraphQuery
        from datetime import datetime, timedelta

        gq = GraphQuery()
        three_months_ago = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

        rows = gq.db.execute(
            "SELECT price FROM hmlr_sales "
            "WHERE postcode LIKE ? AND date>=? "
            "ORDER BY date DESC LIMIT 50",
            (f"{postcode}%", three_months_ago),
        ).fetchall()

        gq.close()

        if not rows:
            return None

        prices = sorted([r[0] for r in rows])
        median = prices[len(prices) // 2]

        # Cache for 24 hours
        r.setex(cache_key, 86400, str(median))
        return float(median)

    except Exception as e:
        log.debug("Could not get momentum for %s: %s", postcode, e)
        return None


# ── Notification dispatch (called by a separate process) ───────────────────
def pop_and_send_notifications(batch_size: int = 50) -> int:
    """Pop pending notifications from the queue and send via Telegram.

    This polls the Redis list and sends messages via the bot's Telegram API.
    Intended to be called every few minutes, or by a separate consumer.

    Args:
        batch_size: Max notifications to process in one call.

    Returns:
        Number of notifications sent.
    """
    sent = 0
    try:
        r = _redis()
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            log.warning("TELEGRAM_BOT_TOKEN not set — cannot send alerts")
            return 0

        import urllib.request
        import urllib.parse

        for _ in range(batch_size):
            raw = r.lpop(_PREFIX_QUEUE)
            if not raw:
                break
            try:
                notif = json.loads(raw)
                user_id = notif["user_id"]
                message = notif["message"]

                # Send via Telegram Bot API
                url = (
                    f"https://api.telegram.org/bot{bot_token}/sendMessage"
                )
                payload = urllib.parse.urlencode({
                    "chat_id": user_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": "true",
                }).encode()

                req = urllib.request.Request(
                    url, data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read().decode())
                    if result.get("ok"):
                        sent += 1
                    else:
                        log.warning(
                            "Telegram send failed for %s: %s",
                            user_id, result,
                        )

            except Exception as e:
                log.debug("Failed to send alert notification: %s", e)
                continue

        if sent > 0:
            log.info("Sent %d alert notifications", sent)

    except Exception as e:
        log.warning("Notification dispatch failed: %s", e)

    return sent
