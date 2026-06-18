#!/usr/bin/env python3
"""core/arena.py - The Arena: Daily Vibe Checks and Leaderboards.

Retention engine using Redis Sorted Sets for leaderboard rankings
and daily micro-score updates based on local market sentiment.

1. Daily Vibe Check: Micro-score update based on reddit_intel.py chatter
   and hmlr_query.py momentum.
2. Leaderboards: Redis Sorted Sets ranking users by Portfolio Value in
   their postcode.
"""
from __future__ import annotations
import json
import os
import time
from typing import Optional

REDIS_PREFIX = "honestly:arena"


def _get_redis():
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

def daily_vibe_check(postcode: str) -> dict:
    """Generate a daily micro-score for a postcode based on:
      1. Reddit chatter sentiment (from reddit_intel.py)
      2. HMLR price momentum (from graph_db.py)
      3. Macro signals (from macro_live.py)

    Returns a compact score card that can be pushed to the Arena topic.
    """
    pc = postcode.upper().strip()
    outcode = pc.split()[0] if " " in pc else pc[:4]
    vibe = {
        "postcode": pc,
        "timestamp": int(time.time()),
        "price_momentum": None,
        "sentiment_score": None,
        "composite_vibe": None,
        "vibe_label": None,
    }

    # 1. Price momentum from graph DB
    try:
        from graph_db import GraphQuery
        gq = GraphQuery()
        recent = gq.sales_for_postcode(pc, since="2025-01-01", limit=50)
        older = gq.sales_for_postcode(pc, limit=100)
        if recent and older:
            import statistics
            recent_med = statistics.median(s["price"] for s in recent if s.get("price"))
            older_med = statistics.median(s["price"] for s in older if s.get("price"))
            if older_med > 0:
                momentum_pct = round((recent_med / older_med - 1) * 100, 1)
                vibe["price_momentum"] = momentum_pct
        gq.close()
    except Exception:
        pass

    # 2. Reddit sentiment
    try:
        from reddit_intel import area_chatter
        chatter = area_chatter(outcode, limit=30)
        if isinstance(chatter, dict) and chatter.get("posts"):
            positive = sum(1 for p in chatter["posts"]
                         if any(w in str(p).lower() for w in ("great", "love", "amazing", "good", "excellent")))
            negative = sum(1 for p in chatter["posts"]
                         if any(w in str(p).lower() for w in ("terrible", "awful", "hate", "avoid", "dangerous")))
            total = len(chatter["posts"])
            if total > 0:
                vibe["sentiment_score"] = round((positive - negative) / total * 100, 1)
    except Exception:
        pass

    # 3. Composite vibe
    scores = []
    if vibe["price_momentum"] is not None:
        scores.append(min(100, max(-100, vibe["price_momentum"] * 10)))
    if vibe["sentiment_score"] is not None:
        scores.append(min(100, max(-100, vibe["sentiment_score"])))
    if scores:
        composite = round(sum(scores) / len(scores), 1)
        vibe["composite_vibe"] = composite
        if composite >= 50:
            vibe["vibe_label"] = "Hot"
        elif composite >= 20:
            vibe["vibe_label"] = "Rising"
        elif composite >= -20:
            vibe["vibe_label"] = "Steady"
        elif composite >= -50:
            vibe["vibe_label"] = "Cooling"
        else:
            vibe["vibe_label"] = "Cold"

    # Cache the vibe check
    r = _get_redis()
    if r:
        try:
            r.set(f"{REDIS_PREFIX}:vibe:{pc}", json.dumps(vibe), ex=86400)  # 24h TTL
        except Exception:
            pass

    return vibe


def get_cached_vibe(postcode: str) -> dict | None:
    """Get the most recently cached vibe check for a postcode."""
    r = _get_redis()
    if not r:
        return None
    try:
        data = r.get(f"{REDIS_PREFIX}:vibe:{postcode.upper().strip()}")
        return json.loads(data) if data else None
    except Exception:
        return None


# ──────────────────────────────────────────────────────── leaderboards

def update_portfolio_score(user_id: str, postcode: str, portfolio_value: float):
    """Update a user's portfolio score on the leaderboard for their postcode.

    Uses Redis Sorted Sets: ZADD arena:leaderboard:{postcode} {score} {user_id}
    """
    r = _get_redis()
    if not r:
        return
    try:
        key = f"{REDIS_PREFIX}:leaderboard:{postcode.upper().strip()}"
        r.zadd(key, {user_id: portfolio_value})
    except Exception:
        pass


def get_leaderboard(postcode: str, limit: int = 10) -> list[dict]:
    """Get the top users by portfolio value for a postcode.

    Returns: [{"user_id": str, "portfolio_value": float, "rank": int}, ...]
    """
    r = _get_redis()
    if not r:
        return []
    try:
        key = f"{REDIS_PREFIX}:leaderboard:{postcode.upper().strip()}"
        # ZREVRANGE returns members in descending score order
        results = r.zrevrangebyscore(key, "+inf", "-inf", withscores=True, start=0, num=limit)
        return [{"user_id": uid, "portfolio_value": score, "rank": i + 1}
                for i, (uid, score) in enumerate(results)]
    except Exception:
        return []


def get_user_rank(user_id: str, postcode: str) -> dict | None:
    """Get a user's rank and portfolio value on their postcode leaderboard."""
    r = _get_redis()
    if not r:
        return None
    try:
        key = f"{REDIS_PREFIX}:leaderboard:{postcode.upper().strip()}"
        score = r.zscore(key, user_id)
        if score is None:
            return None
        rank = r.zrevrank(key, user_id)
        return {"user_id": user_id, "portfolio_value": score, "rank": (rank or 0) + 1}
    except Exception:
        return None
