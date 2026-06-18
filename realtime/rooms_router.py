#!/usr/bin/env python3
"""realtime/rooms_router.py - The Arena: Native Telegram Forum Topics.

A single Supergroup with Topics (Forum view) enabled. Each postcode gets
its own topic. Users are routed based on their subscription tier:
  - Free: link to the "Lobby" topic (ads pinned)
  - Plus/Pro: direct link to the postcode topic

Tech: Telegram Bot API only. No custom WebSockets.
Caching: Redis for message_thread_id lookups.
"""
from __future__ import annotations
import json
import os
import time
from typing import Optional

# ──────────────────────────────────────────────────────────── config

ARENA_SUPERGROUP_ID = os.environ.get("ARENA_SUPERGROUP_ID", "")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
REDIS_PREFIX = "honestly:rooms"

# Topic names
LOBBY_TOPIC_NAME = "Lobby"
LOBBY_TOPIC_ID_CACHE_KEY = f"{REDIS_PREFIX}:lobby_topic_id"


def _get_redis():
    """Get a Redis client, or None if unavailable."""
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


def _tg_api(method: str, params: dict) -> dict:
    """Call a Telegram Bot API method."""
    import urllib.request
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(params).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ──────────────────────────────────────────────────────── room management

def get_or_create_room(postcode: str) -> dict:
    """Get or create a forum topic for a postcode in the Arena supergroup.

    Returns: {"ok": bool, "postcode": str, "message_thread_id": int,
              "deep_link": str}
    """
    pc = postcode.upper().strip()
    if not ARENA_SUPERGROUP_ID:
        return {"ok": False, "error": "ARENA_SUPERGROUP_ID not configured"}

    r = _get_redis()

    # Check cache
    cache_key = f"{REDIS_PREFIX}:topic:{pc}"
    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                thread_id = int(cached)
                return {
                    "ok": True,
                    "postcode": pc,
                    "message_thread_id": thread_id,
                    "deep_link": _deep_link(thread_id),
                    "cached": True,
                }
        except Exception:
            pass

    # Create the topic via Bot API
    result = _tg_api("createForumTopic", {
        "chat_id": ARENA_SUPERGROUP_ID,
        "name": f" postcode {pc}",
        "icon_custom_emoji_id": "5381768525250817",  # house emoji
    })

    if not result.get("ok"):
        return {"ok": False, "error": result.get("description", "createForumTopic failed")}

    thread_id = result["result"]["message_thread_id"]

    # Cache it
    if r:
        try:
            r.set(cache_key, str(thread_id))
        except Exception:
            pass

    return {
        "ok": True,
        "postcode": pc,
        "message_thread_id": thread_id,
        "deep_link": _deep_link(thread_id),
        "cached": False,
    }


def _deep_link(thread_id: int) -> str:
    """Generate a deep link to the topic in the Arena supergroup."""
    # Telegram deep link format: https://t.me/c/{supergroup_id_no_minus}/{thread_id}
    sg_id = ARENA_SUPERGROUP_ID.lstrip("-")
    return f"https://t.me/c/{sg_id}/{thread_id}"


def get_lobby_topic() -> dict:
    """Get or create the Lobby topic (where free users go and ads are pinned)."""
    r = _get_redis()

    # Check cache
    if r:
        try:
            cached = r.get(LOBBY_TOPIC_ID_CACHE_KEY)
            if cached:
                return {
                    "ok": True,
                    "topic": "Lobby",
                    "message_thread_id": int(cached),
                    "deep_link": _deep_link(int(cached)),
                }
        except Exception:
            pass

    # Create the Lobby topic
    result = _tg_api("createForumTopic", {
        "chat_id": ARENA_SUPERGROUP_ID,
        "name": LOBBY_TOPIC_NAME,
        "icon_custom_emoji_id": "5360300790789200",  # speech bubble
    })

    if not result.get("ok"):
        return {"ok": False, "error": result.get("description", "Failed to create Lobby topic")}

    thread_id = result["result"]["message_thread_id"]

    # Cache it
    if r:
        try:
            r.set(LOBBY_TOPIC_ID_CACHE_KEY, str(thread_id))
        except Exception:
            pass

    return {
        "ok": True,
        "topic": "Lobby",
        "message_thread_id": thread_id,
        "deep_link": _deep_link(thread_id),
    }


# ──────────────────────────────────────────────────── entitlements gating

def get_room_link(postcode: str, user_tier: str = "free") -> dict:
    """Get the room link for a user based on their tier.

    Free users: link to the Lobby topic (ads pinned).
    Plus/Pro users: direct link to the postcode topic.
    """
    if user_tier in ("plus", "pro"):
        return get_or_create_room(postcode)
    else:
        return get_lobby_topic()


# ──────────────────────────────────────────────── posting to rooms

def post_valuation_to_room(thread_id: int, valuation_payload: dict) -> dict:
    """Post a mini AVM summary card to a specific forum topic.

    The message is formatted as a compact card with:
      - Address, central value, range, confidence
      - Top 3 strict comps
      - Deep link to the full report
    """
    if not ARENA_SUPERGROUP_ID:
        return {"ok": False, "error": "ARENA_SUPERGROUP_ID not configured"}

    address = valuation_payload.get("address", "Property")
    central = valuation_payload.get("central", 0)
    low = valuation_payload.get("low", 0)
    high = valuation_payload.get("high", 0)
    confidence = valuation_payload.get("confidence_score", "?")
    grade = valuation_payload.get("confidence_grade", "")
    sqm = valuation_payload.get("sqm", "?")
    epc = valuation_payload.get("epc", "?")
    report_url = valuation_payload.get("report_url", "")

    # Format the card
    text = (
        f"*{address}*\n"
        f"  Assessed: £{central:,}\n"
        f"  Range: £{low:,} - £{high:,}\n"
        f"  Confidence: {confidence}/100 ({grade})\n"
        f"  {sqm} sqm | EPC {epc}\n"
    )

    # Add top comps
    evidence = valuation_payload.get("evidence", [])[:3]
    if evidence:
        text += "\n_Recent sold evidence:_\n"
        for e in evidence:
            text += f"  - {e.get('address', '?')}: £{e.get('price', 0):,} ({e.get('date', '?')})\n"

    if report_url:
        text += f"\n[Full report]({report_url})"

    # Send via Bot API
    result = _tg_api("sendMessage", {
        "chat_id": ARENA_SUPERGROUP_ID,
        "message_thread_id": thread_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    })

    return {"ok": result.get("ok", False), "message_id": result.get("result", {}).get("message_id")}
