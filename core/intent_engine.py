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


# ── Score computation ──────────────────────────────────────────────────────
def calculate_sell_probability(postcode: str, property_id: str) -> int:
    """Compute the 0–100 'Likely to Sell' score for a property.

    Reads all stored intent signals for the property and applies the
    scoring algorithm. The score is cached in Redis with a 1-hour TTL.

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
