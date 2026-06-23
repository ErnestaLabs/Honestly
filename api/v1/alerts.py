"""api/v1/alerts.py — Plus-tier price alert tracking endpoints.

Allows Plus/Pro users to track properties for price change notifications.
Each track call kicks off a daily check that feeds returned_7_days signals
into the intent engine.

Endpoints:
  POST /api/v1/alerts/track       — Start tracking a property
  DELETE /api/v1/alerts/track     — Stop tracking a property
  GET  /api/v1/alerts/tracked     — List all tracked properties for the user

Authentication:
  Requires Plus or Pro tier (resolved server-side via user_id header).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from core.alerts_engine import (
    track_property,
    untrack_property,
    get_tracked_properties,
)
from core.intent_engine import (
    log_intent_signal,
    SIGNAL_RETURNED_7_DAYS,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])

# Tier requirement
REQUIRED_TIER = "plus"  # Plus or Pro


def _resolve_tier(user_id: str) -> str:
    """Resolve the user's tier server-side via Redis."""
    try:
        import os
        import redis as redis_mod
        r = redis_mod.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )
        tier = r.get(f"honestly:user:{user_id}:tier")
        return tier or "free"
    except Exception:
        return "free"


def _require_plus_or_pro(user_id: str):
    """Check tier access. Raises 403 if not Plus/Pro."""
    tier = _resolve_tier(user_id)
    if tier not in ("plus", "pro"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tier_access_denied",
                "message": "Price alerts require Plus or Pro subscription",
                "required_tier": "plus",
                "current_tier": tier,
                "upgrade_url": "https://usehonestly.co.uk/upgrade",
            },
        )
    return tier


# ── Track a property ───────────────────────────────────────────────────────

@router.post("/track")
def api_track_property(
    property_id: str,
    postcode: str,
    assessed_value: float,
    address: str = "",
    authorization: Optional[str] = Header(None),
):
    """Start tracking a property for price change alerts.

    Requires Plus or Pro tier. Stores the current assessed_value as
    the baseline for comparison. Once tracked, the daily alert check
    will monitor market momentum and notify the user of shifts > 2%.

    The alert message includes a link back to the appraisal, which
    naturally generates a returned_7_days intent signal.
    """
    user_id = _resolve_user_id(authorization)
    tier = _require_plus_or_pro(user_id)

    ok = track_property(
        user_id=user_id,
        property_id=property_id.strip().upper(),
        postcode=postcode.strip().upper(),
        assessed_value=assessed_value,
        address=address.strip(),
    )

    if ok:
        # Log a returned_7_days intent signal (user is engaging with tracking)
        log_intent_signal(
            user_id=user_id,
            postcode=postcode.upper().strip(),
            property_id=property_id.strip().upper(),
            signal_type=SIGNAL_RETURNED_7_DAYS,
            metadata={"action": "track_property"},
        )

        return {
            "ok": True,
            "property_id": property_id.strip().upper(),
            "postcode": postcode.strip().upper(),
            "tier": tier,
            "message": (
                f"Now tracking {property_id}. You'll receive a notification "
                "if the market momentum shifts by more than 2%."
            ),
        }

    raise HTTPException(status_code=500, detail={"error": "tracking_failed"})


# ── Untrack a property ─────────────────────────────────────────────────────

@router.delete("/track")
def api_untrack_property(
    property_id: str,
    authorization: Optional[str] = Header(None),
):
    """Stop tracking a property."""
    user_id = _resolve_user_id(authorization)
    _require_plus_or_pro(user_id)

    ok = untrack_property(
        user_id=user_id,
        property_id=property_id.strip().upper(),
    )

    if ok:
        return {
            "ok": True,
            "message": f"Stopped tracking {property_id.upper()}.",
        }

    raise HTTPException(status_code=500, detail={"error": "untrack_failed"})


# ── List tracked properties ────────────────────────────────────────────────

@router.get("/tracked")
def api_get_tracked(
    authorization: Optional[str] = Header(None),
):
    """List all properties tracked by the current user."""
    user_id = _resolve_user_id(authorization)
    _require_plus_or_pro(user_id)

    properties = get_tracked_properties(user_id)

    # Strip internal fields, keep what the user needs to see
    safe = []
    for p in properties:
        safe.append({
            "property_id": p.get("property_id"),
            "postcode": p.get("postcode"),
            "address": p.get("address", ""),
            "tracked_at": p.get("tracked_at"),
            "baseline_value": p.get("baseline_assessed_value"),
        })

    return {
        "ok": True,
        "properties": safe,
        "count": len(safe),
    }


# ── Helper: resolve user ID from auth header ──────────────────────────────

def _resolve_user_id(authorization: Optional[str]) -> str:
    """Extract user ID from the X-Authorization or fallback.

    The Telegram Mini App sends the user ID in the initData or custom header.
    For now, we require an explicit X-User-ID header for alert operations.
    """
    if authorization and authorization.startswith("tg_user_"):
        return authorization.replace("tg_user_", "")
    # Fallback: if the middleware already validated initData, the user_id
    # is embedded. For simplicity, require the header.
    raise HTTPException(
        status_code=401,
        detail={
            "error": "auth_required",
            "message": "X-User-ID header is required",
        },
    )
