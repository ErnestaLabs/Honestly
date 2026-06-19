#!/usr/bin/env python3
"""realtime/rooms_router.py - The Arena: Native Telegram Forum Topics.

Single Supergroup with Topics (Forum view). Each postcode gets its own
topic. Users are routed based on subscription tier:
  - Free: link to the "Lobby" topic (ads pinned, read-only)
  - Plus/Pro: direct link to the postcode topic (can post)

Tech: Telegram Bot API only. No custom WebSockets.
State: Redis for message_thread_id cache, cooldown, and membership.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from typing import Optional

from auth.entitlements import UserEntitlements, TIER_ROOM_ACCESS

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────── config

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ARENA_SUPERGROUP_ID = os.environ.get("ARENA_SUPERGROUP_ID", "")

# Redis key prefixes
_RK = "honestly:rooms"
RK_TOPIC = f"{_RK}:topic"          # {postcode} -> thread_id
RK_LOBBY = f"{_RK}:lobby"          # single key -> lobby thread_id
RK_MEMBER = f"{_RK}:member"        # {user_id}:{postcode} -> timestamp

# TTLs
TOPIC_CACHE_TTL = 0                 # topic mappings are permanent
MEMBERSHIP_TTL = 86400              # 24h membership cache


# ──────────────────────────────────────────────────────────── redis

def _redis():
    """Get a Redis client. Returns None if unavailable."""
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


# ──────────────────────────────────────────────────────────── telegram api

def _tg(method: str, params: dict | None = None) -> dict:
    """Call a Telegram Bot API method. Returns the parsed JSON result."""
    if not BOT_TOKEN:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not set"}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(params or {}).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        log.warning("TG API %s error %s: %s", method, e.code, body)
        return {"ok": False, "error": f"HTTP {e.code}", "body": body}
    except Exception as e:
        log.warning("TG API %s exception: %s", method, e)
        return {"ok": False, "error": str(e)}


# ──────────────────────────────────────────────────────────── deep link

def _deep_link(thread_id: int) -> str:
    """Generate a t.me/c/ deep link to a specific topic in the supergroup.

    Format: https://t.me/c/{supergroup_id_no_minus}/{message_thread_id}
    The -100 prefix on supergroup IDs is stripped for the link.
    """
    sg = ARENA_SUPERGROUP_ID.lstrip("-").removeprefix("100")
    return f"https://t.me/c/{sg}/{thread_id}"


# ──────────────────────────────────────────────────────────── room CRUD

def get_or_create_room(postcode: str) -> dict:
    """Get or create a forum topic for a postcode.

    1. Check Redis cache (RK_TOPIC:{postcode})
    2. If miss, call createForumTopic on the Arena supergroup
    3. Cache the message_thread_id in Redis
    4. Return {ok, postcode, message_thread_id, deep_link, cached}

    Returns:
        dict with ok=True/False and room details.
    """
    pc = postcode.upper().strip()
    if not ARENA_SUPERGROUP_ID:
        return {"ok": False, "error": "ARENA_SUPERGROUP_ID not configured"}

    r = _redis()

    # 1. Cache check
    cache_key = f"{RK_TOPIC}:{pc}"
    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                tid = int(cached)
                return {
                    "ok": True,
                    "postcode": pc,
                    "message_thread_id": tid,
                    "deep_link": _deep_link(tid),
                    "cached": True,
                }
        except Exception:
            pass

    # 2. Create via Bot API
    result = _tg("createForumTopic", {
        "chat_id": ARENA_SUPERGROUP_ID,
        "name": f"\U0001f3e0 {pc}",
        "icon_custom_emoji_id": "5381768525250817",  # house emoji
    })

    if not result.get("ok"):
        # If the topic already exists, try to find it via getUpdates
        # (createForumTopic returns error for duplicates in some cases)
        desc = result.get("description", result.get("error", "unknown"))
        return {"ok": False, "postcode": pc, "error": desc}

    tid = result["result"]["message_thread_id"]

    # 3. Cache it
    if r:
        try:
            r.set(cache_key, str(tid))
        except Exception:
            pass

    return {
        "ok": True,
        "postcode": pc,
        "message_thread_id": tid,
        "deep_link": _deep_link(tid),
        "cached": False,
    }


def get_lobby_topic() -> dict:
    """Get or create the Lobby topic for free users (ads pinned here).

    Same pattern as get_or_create_room but for the single Lobby topic.
    """
    if not ARENA_SUPERGROUP_ID:
        return {"ok": False, "error": "ARENA_SUPERGROUP_ID not configured"}

    r = _redis()

    # Cache check
    if r:
        try:
            cached = r.get(RK_LOBBY)
            if cached:
                tid = int(cached)
                return {
                    "ok": True,
                    "topic": "Lobby",
                    "message_thread_id": tid,
                    "deep_link": _deep_link(tid),
                    "cached": True,
                }
        except Exception:
            pass

    # Create
    result = _tg("createForumTopic", {
        "chat_id": ARENA_SUPERGROUP_ID,
        "name": "\U0001f4e2 Lobby",
        "icon_custom_emoji_id": "5360300790789200",  # speech bubble
    })

    if not result.get("ok"):
        desc = result.get("description", result.get("error", "unknown"))
        return {"ok": False, "topic": "Lobby", "error": desc}

    tid = result["result"]["message_thread_id"]

    # Cache it
    if r:
        try:
            r.set(RK_LOBBY, str(tid))
        except Exception:
            pass

    return {
        "ok": True,
        "topic": "Lobby",
        "message_thread_id": tid,
        "deep_link": _deep_link(tid),
        "cached": False,
    }


# ──────────────────────────────────────────────────── entitlements gating

def get_room_link(postcode: str, user_id: str, user_tier: str = "free") -> dict:
    """Route a user to the correct room based on their subscription tier.

    Free: link to the Lobby topic (ads pinned, read-only).
    Plus/Pro: direct link to the postcode topic.

    Also records membership for leaderboard scoring.
    """
    pc = postcode.upper().strip()
    access = TIER_ROOM_ACCESS.get(user_tier, "read_only")

    if access == "read_only":
        result = get_lobby_topic()
    else:
        result = get_or_create_room(pc)

    # Record membership
    if result.get("ok"):
        r = _redis()
        if r:
            try:
                mk = f"{RK_MEMBER}:{user_id}:{pc}"
                r.set(mk, str(int(time.time())), ex=MEMBERSHIP_TTL)
            except Exception:
                pass

    return result


# ──────────────────────────────────────────────── posting to rooms

def post_valuation_to_room(thread_id: int, valuation_payload: dict) -> dict:
    """Post a mini AVM summary card to a specific forum topic.

    Uses HTML parse_mode for reliable rendering across Telegram clients.

    The card shows:
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
    conf = valuation_payload.get("confidence_score", "-")
    grade = valuation_payload.get("confidence_grade", "")
    sqm = valuation_payload.get("sqm", "?")
    epc = valuation_payload.get("epc", "?")
    report_url = valuation_payload.get("report_url", "")

    # HTML-formatted card (reliable across all TG clients)
    lines = [
        f"<b>\U0001f3e0 { _esc(address)}</b>",
        f"  \U0001f4b0 Assessed: <b>\u00a3{central:,}</b>",
        f"  \U0001f4ca Range: \u00a3{low:,} - \u00a3{high:,}",
        f"  \U0001f3af Confidence: {conf}/100 ({_esc(grade)})",
        f"  \U0001f4cf {sqm} sqm | EPC {epc}",
    ]

    # Top 3 comps
    evidence = valuation_payload.get("evidence", [])[:3]
    if evidence:
        lines.append("")
        lines.append("<i>Recent sold evidence:</i>")
        for e in evidence:
            ea = _esc(e.get("address", "?"))
            ep = e.get("price", 0)
            ed = e.get("date", "?")
            lines.append(f"  \u2022 {ea}: \u00a3{ep:,} ({ed})")

    if report_url:
        lines.append(f"\n<a href=\"{_esc(report_url)}\">\U0001f4c4 Full report</a>")

    text = "\n".join(lines)

    result = _tg("sendMessage", {
        "chat_id": ARENA_SUPERGROUP_ID,
        "message_thread_id": thread_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    })

    return {
        "ok": result.get("ok", False),
        "message_id": (result.get("result") or {}).get("message_id"),
    }


def _esc(s: str) -> str:
    """Escape HTML special characters."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ──────────────────────────────────────────────── room listing

def list_rooms_for_outcode(outcode: str, limit: int = 20) -> list[dict]:
    """List cached rooms for an outcode (e.g. 'SW16').

    Scans Redis keys matching RK_TOPIC:{outcode}* to find
    all postcodes in the outcode that have active rooms.
    """
    r = _redis()
    if not r:
        return []
    rooms = []
    try:
        pattern = f"{RK_TOPIC}:{outcode}*"
        for key in r.scan_iter(match=pattern, count=100):
            pc = key.split(":")[-1]
            tid = r.get(key)
            if tid:
                rooms.append({
                    "postcode": pc,
                    "message_thread_id": int(tid),
                    "deep_link": _deep_link(int(tid)),
                })
    except Exception:
        pass
    return rooms[:limit]
