#!/usr/bin/env python3
"""api/v1/community.py - FastAPI endpoints for Rooms and Arena.

Endpoints:
  GET /rooms/{postcode}          - deep link to the Telegram room
  GET /arena/vibe/{postcode}     - daily Vibe Score
  GET /arena/leaderboard/{postcode} - top 10 users for that postcode

All endpoints authenticate the user and gate access by tier.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

router = APIRouter(prefix="/v1", tags=["community"])

# ──────────────────────────────────────────────────────────── auth helper

def _get_tier(authorization: str | None) -> str:
    """Extract user tier from the Authorization header.

    In production, this would validate a JWT or session token.
    For now, the header format is: Bearer {user_id}:{tier}
    """
    if not authorization:
        return "free"
    try:
        token = authorization.replace("Bearer ", "").strip()
        # Format: user_id:tier or just user_id
        parts = token.split(":")
        if len(parts) == 2:
            return parts[1].lower()
        return "free"
    except Exception:
        return "free"


def _get_user_id(authorization: str | None) -> str:
    """Extract user_id from the Authorization header."""
    if not authorization:
        return "anonymous"
    try:
        token = authorization.replace("Bearer ", "").strip()
        return token.split(":")[0]
    except Exception:
        return "anonymous"


# ──────────────────────────────────────────────────────────── rooms

@router.get("/rooms/{postcode}")
def get_room(
    postcode: str,
    authorization: Optional[str] = Header(None),
):
    """Get the deep link to the Telegram room for a postcode.

    Free users: link to the Lobby topic (ads pinned, read-only).
    Plus/Pro users: direct link to the postcode topic.
    """
    user_id = _get_user_id(authorization)
    tier = _get_tier(authorization)

    from realtime.rooms_router import get_room_link
    result = get_room_link(postcode, user_id, tier)

    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error", "Room unavailable"))

    return {
        "postcode": result.get("postcode", postcode.upper()),
        "deep_link": result.get("deep_link"),
        "message_thread_id": result.get("message_thread_id"),
        "access": "full" if tier in ("plus", "pro") else "lobby",
        "tier": tier,
    }


# ──────────────────────────────────────────────────────────── vibe

@router.get("/arena/vibe/{postcode}")
def get_vibe(
    postcode: str,
    authorization: Optional[str] = Header(None),
):
    """Get the daily Vibe Score for a postcode.

    Available to all tiers. Returns the cached score if available,
    otherwise calculates a fresh one.
    """
    tier = _get_tier(authorization)
    user_id = _get_user_id(authorization)

    from core.arena import calculate_vibe, get_cached_vibe, award_daily_login_points

    # Award daily login points
    award_daily_login_points(user_id, postcode)

    # Check cache first
    result = get_cached_vibe(postcode)
    if not result:
        result = calculate_vibe(postcode)

    if result.get("vibe_score") is None:
        return {
            "postcode": postcode.upper(),
            "vibe_score": None,
            "trend": "unknown",
            "note": "Insufficient data for this postcode",
        }

    return result


# ──────────────────────────────────────────────────────────── leaderboard

@router.get("/arena/leaderboard/{postcode}")
def get_leaderboard(
    postcode: str,
    authorization: Optional[str] = Header(None),
    limit: int = Query(default=10, ge=1, le=100),
):
    """Get the leaderboard for a postcode.

    Returns the top users by score. All tiers can view.
    """
    tier = _get_tier(authorization)
    user_id = _get_user_id(authorization)

    from core.arena import get_postcode_leaderboard, get_user_rank

    board = get_postcode_leaderboard(postcode, limit=limit)
    user_rank = get_user_rank(user_id, postcode)

    return {
        "postcode": postcode.upper(),
        "leaderboard": board,
        "user_rank": user_rank,
        "tier": tier,
    }
