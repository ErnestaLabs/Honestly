"""core/intent_engine.py — Intent tracking and sell-probability scoring engine.

The moat. Tracks user engagement signals across the valuation lifecycle and
computes a 0–100 "Likely to Sell" score per property. This powers the
Agent Pro dashboard and underpins predictive instruction intelligence.

Architecture:
  - Signals are written to Redis sorted sets with TTL (fast path).
  - Scores are materialised on read: we recompute from raw signals each time,
    so the algorithm can evolve without a backfill.
  - Redis key namespace: honestly:intent:{user_id}:{postcode}:{property_id}

Scoring algorithm (0–100, hard cap at 100):
  Base:                               0
  +20  valuation_run                   (user ran an AVM)
  +30  upsell_purchased                (bought Anger/Fear trigger product)
  +20  repeated_valuation_3plus        (ran valuation on same property 3+ times)
  +30  returned_7_days                 (came back within 7 days of first run)
  Cap at 100.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ── Redis connection (lazy singleton) ──────────────────────────────────────
_REDIS = None
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Signal type constants
SIGNAL_VALUATION_RUN = "valuation_run"
SIGNAL_REPORT_DOWNLOADED = "report_downloaded"
SIGNAL_UPSELL_PURCHASED = "upsell_purchased"
SIGNAL_RETURNED_7_DAYS = "returned_7_days"

# Scoring weights
WEIGHT_VALUATION_RUN = 20
WEIGHT_UPSELL_PURCHASED = 30
WEIGHT_REPEATED_VALUATION_3PLUS = 20
WEIGHT_RETURNED_7_DAYS = 30
SCORE_CAP = 100

# TTL for signal data (90 days)
SIGNAL_TTL_S = 90 * 86400

# Agent alert threshold (score >= this triggers push to agents)
AGENT_ALERT_THRESHOLD = 80

# Agent alert rate-limit window (48 hours — one alert per agent per property)
AGENT_ALERT_COOLDOWN_S = 48 * 3600

# Key prefixes
_PREFIX_SIGNAL = "honestly:intent:signal:"
_PREFIX_TIMELINE = "honestly:intent:timeline:"
_PREFIX_SCORE = "honestly:intent:score:"


def _redis():
    """Lazy-init Redis connection."""
    global _REDIS
    if _REDIS is None:
        import redis as redis_mod
        _REDIS = redis_mod.Redis.from_url(REDIS_URL, decode_responses=True)
    return _REDIS


# ── Key helpers ────────────────────────────────────────────────────────────
def _signal_key(postcode: str, property_id: str) -> str:
    return f"{_PREFIX_SIGNAL}{postcode}:{property_id}"


def _timeline_key(user_id: str, postcode: str, property_id: str) -> str:
    return f"{_PREFIX_TIMELINE}{user_id}:{postcode}:{property_id}"


def _score_key(postcode: str, property_id: str) -> str:
    return f"{_PREFIX_SCORE}{postcode}:{property_id}"


# ── Event tracking ─────────────────────────────────────────────────────────
def log_intent_signal(
    user_id: str,
    postcode: str,
    property_id: str,
    signal_type: str,
    metadata: Optional[dict] = None,
) -> bool:
    """Log an intent signal for a user+property combination.

    Stores the signal in a Redis set (for fast dedup) and a sorted set
    (for timeline queries). Both have a 90-day TTL.

    Args:
        user_id: Telegram user ID or anonymous session ID.
        postcode: Outcode (e.g. SW16).
        property_id: Property identifier (full postcode or address hash).
        signal_type: One of the SIGNAL_* constants.
        metadata: Optional extra data (e.g. {"product_id": "lowball_counter_email"}).

    Returns:
        True if the signal was recorded, False on error.
    """
    try:
        r = _redis()
        now = time.time()
        signal_data = json.dumps({
            "user_id": user_id,
            "signal_type": signal_type,
            "ts": now,
            "metadata": metadata or {},
        })

        # Store in the per-property signal set (for score computation)
        score_key = _signal_key(postcode, property_id)
        r.sadd(score_key, signal_data)
        r.expire(score_key, SIGNAL_TTL_S)

        # Store in the per-user timeline (for per-user queries)
        timeline_key = _timeline_key(user_id, postcode, property_id)
        r.zadd(timeline_key, {signal_data: now})
        r.expire(timeline_key, SIGNAL_TTL_S)

        log.debug(
            "Intent signal: user=%s postcode=%s property=%s type=%s",
            user_id, postcode, property_id, signal_type,
        )
        return True

    except Exception as e:
        log.warning("Failed to log intent signal: %s", e)
        return False


# ── Agent push alert (B2B) ────────────────────────────────────────────────
# When a property's sell probability crosses AGENT_ALERT_THRESHOLD (80),
# all Pro Agents subscribed to that postcode get a Telegram push.
# Rate-limited: one alert per agent per property per 48 hours.

_AGENT_ALERT_LOCK_PREFIX = "honestly:intent:agent_alert_lock:"
_AGENT_SUB_PREFIX = "honestly:agent:sub:"

AGENT_PUSH_THRESHOLD_DEFAULT = 80


def _fire_agent_push_alerts(
    postcode: str,
    property_id: str,
    score: int,
    signals: list[dict],
):
    """Fire push notifications to Pro Agents subscribed to this postcode.

    Runs in a background thread so it never blocks the score computation.
    Each agent gets at most one alert per property per 48 hours.
    """
    try:
        import threading
        threading.Thread(
            target=_do_agent_push,
            args=(postcode, property_id, score, signals),
            daemon=True,
        ).start()
    except Exception as e:
        log.debug("Failed to spawn agent push thread: %s", e)


def _do_agent_push(
    postcode: str,
    property_id: str,
    score: int,
    signals: list[dict],
):
    """Actual agent notification logic (runs in daemon thread)."""
    try:
        r = _redis()
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            return

        # Find all Pro Agents subscribed to this postcode
        agent_subscribers = r.smembers(f"{_AGENT_SUB_PREFIX}{postcode}")
        if not agent_subscribers:
            return

        # Count unique users who engaged (for the message — no PII exposed)
        unique_users = len(set(s.get("user_id", "?") for s in signals))
        signal_labels = _summarise_signals(signals)

        for agent_user_id in agent_subscribers:
            agent_user_id = agent_user_id.strip()
            if not agent_user_id:
                continue

            # Rate limit: 48h cooldown per agent per property
            lock_key = f"{_AGENT_ALERT_LOCK_PREFIX}{agent_user_id}:{postcode}:{property_id}"
            already_sent = r.get(lock_key)
            if already_sent:
                continue
            r.setex(lock_key, AGENT_ALERT_COOLDOWN_S, "1")

            # Build the push message — no PII
            message = (
            "\U0001f6a8 High Intent Alert!\n\n"
                f"Property in {postcode} just hit a {score}% sell probability.\n\n"
                f"Signals: {signal_labels}\n"
                f"Unique engaged users: {unique_users}\n\n"
                f"Check your Agent Dashboard for full details:"
                f"https://usehonestly.co.uk/agent/intel?postcode={postcode}"
            )

            _send_telegram_message(bot_token, agent_user_id, message)

    except Exception as e:
        log.debug("Agent push failed: %s", e)


def _summarise_signals(signals: list[dict]) -> str:
    """Build a human-readable summary of the signal types."""
    signal_types = [s.get("signal_type", "?") for s in signals]
    label_map = {
        SIGNAL_VALUATION_RUN: "valuation run",
        SIGNAL_UPSELL_PURCHASED: "upsell purchased",
        SIGNAL_RETURNED_7_DAYS: "returned within 7d",
        SIGNAL_REPORT_DOWNLOADED: "report downloaded",
    }
    seen = set()
    labels = []
    for st in signal_types:
        label = label_map.get(st, st)
        if label not in seen:
            seen.add(label)
            labels.append(label)
    return ", ".join(labels)


def _send_telegram_message(bot_token: str, chat_id: str, text: str):
    """Send a message via the Telegram Bot API."""
    try:
        import urllib.request
        import urllib.parse

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": text,
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
                log.debug("Agent push sent to %s", chat_id)
            else:
                log.debug("Agent push failed for %s: %s", chat_id, result)
    except Exception as e:
        log.debug("Telegram send failed: %s", e)


# ── Agent subscription management ──────────────────────────────────────────
def register_agent_postcode_subscription(agent_user_id: str, postcode: str) -> bool:
    """Register a Pro Agent to receive push alerts for a postcode."""
    try:
        r = _redis()
        r.sadd(f"{_AGENT_SUB_PREFIX}{postcode}", agent_user_id)
        return True
    except Exception as e:
        log.warning("Failed to register agent sub: %s", e)
        return False


def unregister_agent_postcode_subscription(agent_user_id: str, postcode: str) -> bool:
    """Remove an agent from a postcode's alert list."""
    try:
        r = _redis()
        r.srem(f"{_AGENT_SUB_PREFIX}{postcode}", agent_user_id)
        return True
    except Exception as e:
        log.warning("Failed to unregister agent sub: %s", e)
        return False


def get_agent_subscribed_postcodes(agent_user_id: str) -> list[str]:
    """Return all postcodes an agent is subscribed to.

    Scans Redis for sets containing this agent's ID.
    """
    postcodes = []
    try:
        r = _redis()
        cursor = 0
        while cursor is not None:
            cursor, keys = r.scan(
                cursor=cursor, match=f"{_AGENT_SUB_PREFIX}*", count=200
            )
            for key in keys:
                if r.sismember(key, agent_user_id):
                    pc = key.replace(_AGENT_SUB_PREFIX, "")
                    postcodes.append(pc)
            if cursor == 0:
                break
    except Exception as e:
        log.warning("Failed to get agent subs: %s", e)
    return postcodes


# ── Score computation ──────────────────────────────────────────────────────
def calculate_sell_probability(postcode: str, property_id: str) -> int:
    """Compute the 0–100 'Likely to Sell' score for a property.

    Reads all stored intent signals for the property and applies the
    scoring algorithm. The score is cached in Redis with a 1-hour TTL.

    If the new score crosses AGENT_ALERT_THRESHOLD (80), fires push
    notifications to all Pro Agents subscribed to this postcode.

    Args:
        postcode: Outcode (e.g. SW16).
        property_id: Property identifier.

    Returns:
        Integer score 0–100.
    """
    try:
        r = _redis()
        score_key = _signal_key(postcode, property_id)

        # Fetch all signals for this property
        signals = r.smembers(score_key)
        if not signals:
            return 0

        # Parse signals
        parsed_signals = []
        for s in signals:
            try:
                parsed_signals.append(json.loads(s))
            except (json.JSONDecodeError, TypeError):
                continue

        if not parsed_signals:
            return 0

        score = 0

        # ── +20 if any valuation_run exists ──────────────────────────
        if any(s["signal_type"] == SIGNAL_VALUATION_RUN for s in parsed_signals):
            score += WEIGHT_VALUATION_RUN

        # ── +30 if any upsell_purchased exists ───────────────────────
        if any(s["signal_type"] == SIGNAL_UPSELL_PURCHASED for s in parsed_signals):
            score += WEIGHT_UPSELL_PURCHASED

        # ── +20 if the same user ran 3+ valuations (count per user) ──
        from collections import Counter
        user_val_counts = Counter(
            s["user_id"] for s in parsed_signals
            if s["signal_type"] == SIGNAL_VALUATION_RUN
        )
        if any(count >= 3 for count in user_val_counts.values()):
            score += WEIGHT_REPEATED_VALUATION_3PLUS

        # ── +30 if any user returned within 7 days ───────────────────
        now = time.time()
        seven_days_ago = now - (7 * 86400)
        for s in parsed_signals:
            signal_ts = s.get("ts", 0)
            if signal_ts >= seven_days_ago:
                score += WEIGHT_RETURNED_7_DAYS
                break

        # ── Cap at 100 ───────────────────────────────────────────────
        score = min(score, SCORE_CAP)

        # Cache score with short TTL
        cache_key = _score_key(postcode, property_id)
        r.setex(cache_key, 3600, score)

        # ── Fire agent push alert if score crosses threshold ─────────
        if score >= AGENT_ALERT_THRESHOLD:
            _fire_agent_push_alerts(postcode, property_id, score, parsed_signals)

        return score

    except Exception as e:
        log.warning("Failed to calculate sell probability: %s", e)
        return 0


# ── Aggregation queries (used by Agent Pro API) ────────────────────────────
def get_high_intent_properties(
    postcodes: list[str],
    threshold: int = 60,
    limit: int = 50,
) -> list[dict]:
    """Return properties with sell_probability above threshold.

    Scans Redis signal sets for the given postcodes and returns
    non-PII property intelligence.

    Args:
        postcodes: List of outcode strings the agent monitors.
        threshold: Minimum score (default 60).
        limit: Max results.

    Returns:
        List of dicts with property_id, postcode, sell_probability, signals.
    """
    results = []
    try:
        r = _redis()
        for pc in postcodes:
            # Scan keys matching this postcode
            pattern = f"{_PREFIX_SIGNAL}{pc}:*"
            cursor = 0
            while cursor is not None:
                cursor, keys = r.scan(cursor=cursor, match=pattern, count=200)
                for key in keys:
                    property_id = key.split(":")[-1]
                    score = calculate_sell_probability(pc, property_id)
                    if score >= threshold:
                        signals = r.smembers(key)
                        signal_types = []
                        for s in signals:
                            try:
                                data = json.loads(s)
                                signal_types.append(data["signal_type"])
                            except (json.JSONDecodeError, TypeError, KeyError):
                                continue
                        results.append({
                            "property_id": property_id,
                            "postcode": pc,
                            "sell_probability": score,
                            "signal_count": len(signals),
                            "signal_types": list(set(signal_types)),
                        })
                if cursor == 0:
                    break
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break

    except Exception as e:
        log.warning("Failed to query high-intent properties: %s", e)

    # Sort by score descending
    results.sort(key=lambda r: r["sell_probability"], reverse=True)
    return results[:limit]


def get_postcode_stats(postcode: str) -> dict:
    """Aggregate market statistics for a postcode area.

    Returns:
        Dict with:
          - total_signals: total raw signals logged
          - unique_properties: number of unique properties tracked
          - unique_users: number of unique users who interacted
          - avg_sell_probability: mean sell score across all properties
          - high_intent_count: properties with score >= 60
          - valuations_7d: number of valuation runs in the last 7 days
          - recent_confidence_scores: list of confidence scores from recent runs
    """
    try:
        r = _redis()
        pattern = f"{_PREFIX_SIGNAL}{postcode}:*"
        cursor = 0
        all_signals = []
        unique_users = set()
        unique_properties = set()
        valuations_7d = 0
        seven_days_ago = time.time() - (7 * 86400)

        while cursor is not None:
            cursor, keys = r.scan(cursor=cursor, match=pattern, count=500)
            for key in keys:
                property_id = key.split(":")[-1]
                unique_properties.add(property_id)
                signals = r.smembers(key)
                for s in signals:
                    try:
                        data = json.loads(s)
                        all_signals.append(data)
                        unique_users.add(data.get("user_id"))
                        if (data.get("signal_type") == SIGNAL_VALUATION_RUN
                                and data.get("ts", 0) >= seven_days_ago):
                            valuations_7d += 1
                    except (json.JSONDecodeError, TypeError):
                        continue
            if cursor == 0:
                break

        # Compute average sell probability across all tracked properties
        total_score = 0
        scored_count = 0
        high_intent = 0
        for prop in unique_properties:
            s = calculate_sell_probability(postcode, prop)
            total_score += s
            scored_count += 1
            if s >= 60:
                high_intent += 1

        return {
            "postcode": postcode,
            "total_signals": len(all_signals),
            "unique_properties": len(unique_properties),
            "unique_users": len(unique_users),
            "avg_sell_probability": round(total_score / scored_count, 1) if scored_count else 0,
            "high_intent_count": high_intent,
            "valuations_7d": valuations_7d,
            "tracked_properties": scored_count,
        }

    except Exception as e:
        log.warning("Failed to get postcode stats: %s", e)
        return {
            "postcode": postcode,
            "total_signals": 0,
            "unique_properties": 0,
            "unique_users": 0,
            "avg_sell_probability": 0,
            "high_intent_count": 0,
            "valuations_7d": 0,
            "tracked_properties": 0,
        }
