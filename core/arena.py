#!/usr/bin/env python3
"""core/arena.py - The Arena: Daily Vibe Checks and Leaderboards.

Retention engine using Redis for all state:
  1. Daily Vibe Check: micro-score from reddit_intel + HMLR momentum
  2. Leaderboards: Redis Sorted Sets by postcode

Scale: 1M users. Redis only - no in-memory fallback for sorted sets
(leaderboards need shared state to be meaningful).
"""
from __future__ import annotations

import json
import logging
import os
import statistics
import time
from typing import Optional

log = logging.getLogger(__name__)

REDIS_PREFIX = "honestly:arena"

# Vibe Score TTL (seconds)
VIBE_TTL = 86400  # 24 hours

# Leaderboard key pattern
LB_KEY = f"{REDIS_PREFIX}:lb"     # {postcode} -> sorted set of user_id:score


def _redis():
    try:
        import redis
        return redis.Redis(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", 6379)),
            db=int(os.environ.get("REDIS_DB", 0)),
            decode_responses=True,
        )
    except Exception:
        return None


# ──────────────────────────────────────────────────────── daily vibe check

def calculate_vibe(postcode: str) -> dict:
    """Calculate the daily Vibe Score for a postcode.

    Combines:
      1. Reddit chatter sentiment (from reddit_intel.py) - weight 40%
      2. HMLR price momentum (from graph_db.py) - weight 60%

    Returns a 0-100 Vibe Score and a trend label (Hot/Rising/Steady/Cooling/Cold).
    Cached in Redis for 24 hours per postcode.
    """
    pc = postcode.upper().strip()
    outcode = pc.split()[0] if " " in pc else pc[:4]
    vibe_key = f"{REDIS_PREFIX}:vibe:{pc}"

    # Check cache first
    r = _redis()
    if r:
        try:
            cached = r.get(vibe_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    # ── Signal 1: Price momentum (weight 60%) ──────────────────────
    momentum_score = None  # -100 to +100
    momentum_pct = None
    try:
        from graph_db import GraphQuery
        gq = GraphQuery()

        # Recent 3 months
        three_mo_ago = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 90 * 86400))
        recent = gq.sales_for_postcode(pc, since=three_mo_ago, limit=100)

        # Previous 3 months (3-6 months ago)
        six_mo_ago = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 180 * 86400))
        all_recent = gq.sales_for_postcode(pc, since=six_mo_ago, limit=200)

        prev = [s for s in all_recent if s.get("date", "9999") < three_mo_ago]

        if recent and prev:
            recent_prices = [s["price"] for s in recent if s.get("price")]
            prev_prices = [s["price"] for s in prev if s.get("price")]
            if recent_prices and prev_prices:
                r_med = statistics.median(recent_prices)
                p_med = statistics.median(prev_prices)
                if p_med > 0:
                    momentum_pct = round((r_med / p_med - 1) * 100, 1)
                    # Map to -100..+100 scale: each 1% momentum = 20 points
                    momentum_score = max(-100, min(100, momentum_pct * 20))

        gq.close()
    except Exception as e:
        log.debug("Momentum calculation failed for %s: %s", pc, e)

    # ── Signal 2: Reddit sentiment (weight 40%) ─────────────────────
    sentiment_score = None  # -100 to +100
    sentiment_detail = {}
    try:
        from reddit_intel import for_area
        chatter = for_area(outcode, limit=30)
        if isinstance(chatter, dict) and chatter.get("posts"):
            posts = chatter["posts"]
            positive_words = ("great", "love", "amazing", "good", "excellent",
                              "booming", "up and coming", "improving", "investment")
            negative_words = ("terrible", "awful", "hate", "avoid", "dangerous",
                              "declining", "crime", "overpriced", "ripoff")
            pos = sum(1 for p in posts if any(w in str(p).lower() for w in positive_words))
            neg = sum(1 for p in posts if any(w in str(p).lower() for w in negative_words))
            total = len(posts)
            if total > 0:
                raw = ((pos - neg) / total) * 100
                sentiment_score = max(-100, min(100, raw))
                sentiment_detail = {
                    "posts_analysed": total,
                    "positive": pos,
                    "negative": neg,
                    "raw_score": round(raw, 1),
                }
    except Exception as e:
        log.debug("Sentiment calculation failed for %s: %s", pc, e)

    # ── Composite Vibe Score ────────────────────────────────────────
    composite = None
    signals_available = []
    if momentum_score is not None:
        signals_available.append(("momentum", momentum_score, 0.6))
    if sentiment_score is not None:
        signals_available.append(("sentiment", sentiment_score, 0.4))

    if signals_available:
        # Normalise weights when one signal is missing
        total_weight = sum(w for _, _, w in signals_available)
        composite = round(sum(s * (w / total_weight) for _, s, w in signals_available), 1)
        # Rescale from -100..+100 to 0..100
        composite = round((composite + 100) / 2, 1)

    # ── Trend label ────────────────────────────────────────────────
    trend = "Steady"
    if composite is not None:
        if composite >= 80:
            trend = "Hot"
        elif composite >= 65:
            trend = "Rising"
        elif composite >= 35:
            trend = "Steady"
        elif composite >= 20:
            trend = "Cooling"
        else:
            trend = "Cold"

    result = {
        "postcode": pc,
        "vibe_score": composite,
        "trend": trend,
        "momentum_pct": momentum_pct,
        "momentum_signal": momentum_score,
        "sentiment_signal": sentiment_score,
        "sentiment_detail": sentiment_detail,
        "signals_used": [s for s, _, _ in signals_available],
        "calculated_at": int(time.time()),
    }

    # Cache it
    if r:
        try:
            r.set(vibe_key, json.dumps(result), ex=VIBE_TTL)
        except Exception:
            pass

    return result


def get_cached_vibe(postcode: str) -> dict | None:
    """Return the most recently cached vibe for a postcode, or None."""
    r = _redis()
    if not r:
        return None
    try:
        data = r.get(f"{REDIS_PREFIX}:vibe:{postcode.upper().strip()}")
        return json.loads(data) if data else None
    except Exception:
        return None


# ──────────────────────────────────────────────────────── leaderboards

def update_leaderboard(user_id: str, postcode: str, points: float):
    """Add points to a user's score on their postcode leaderboard.

    Uses Redis Sorted Set: ZADD honestly:arena:lb:{postcode} {score} {user_id}
    Score accumulates (ZADD with the default GT/MIN behaviour would replace;
    we use ZINCRBY to accumulate).

    Points sources:
      - AVM run: +10
      - Upsell purchase: +50
      - Daily login: +5
      - Room post: +3
    """
    r = _redis()
    if not r:
        return
    try:
        key = f"{LB_KEY}:{postcode.upper().strip()}"
        r.zincrby(key, points, user_id)
    except Exception as e:
        log.debug("Leaderboard update failed: %s", e)


def get_postcode_leaderboard(postcode: str, limit: int = 10) -> list[dict]:
    """Get the top users by score for a postcode leaderboard.

    Uses ZREVRANGE for descending score order.
    Returns: [{"user_id": str, "score": float, "rank": int}, ...]
    """
    r = _redis()
    if not r:
        return []
    try:
        key = f"{LB_KEY}:{postcode.upper().strip()}"
        results = r.zrevrangebyscore(key, "+inf", "-inf", withscores=True, start=0, num=limit)
        return [
            {"user_id": uid, "score": round(score, 1), "rank": i + 1}
            for i, (uid, score) in enumerate(results)
        ]
    except Exception:
        return []


def get_user_rank(user_id: str, postcode: str) -> dict | None:
    """Get a specific user's rank and score on their postcode leaderboard."""
    r = _redis()
    if not r:
        return None
    try:
        key = f"{LB_KEY}:{postcode.upper().strip()}"
        score = r.zscore(key, user_id)
        if score is None:
            return None
        rank = r.zrevrank(key, user_id)
        return {
            "user_id": user_id,
            "postcode": postcode.upper().strip(),
            "score": round(score, 1),
            "rank": (rank + 1) if rank is not None else None,
        }
    except Exception:
        return None


# ──────────────────────────────────────────────── points helpers

def award_avm_points(user_id: str, postcode: str):
    """Award points for running an AVM."""
    update_leaderboard(user_id, postcode, 10)


def award_upsell_points(user_id: str, postcode: str):
    """Award points for purchasing an upsell."""
    update_leaderboard(user_id, postcode, 50)


def award_daily_login_points(user_id: str, postcode: str):
    """Award points for daily app open (once per day per postcode)."""
    r = _redis()
    if not r:
        return
    today = time.strftime("%Y-%m-%d")
    key = f"{REDIS_PREFIX}:daily_login:{user_id}:{postcode}:{today}"
    try:
        if r.setnx(key, "1"):
            r.expire(key, 172800)  # 48h TTL
            update_leaderboard(user_id, postcode, 5)
    except Exception:
        pass


def award_room_post_points(user_id: str, postcode: str):
    """Award points for posting in a room topic."""
    update_leaderboard(user_id, postcode, 3)
