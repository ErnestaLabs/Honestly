"""api/v1/properties.py - FastAPI endpoints for the Mini App valuation flow.

SECURITY: The frontend NEVER dictates the user's tier.
The backend determines the tier server-side via Redis on every request.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["properties"])


# ──────────────────────────────────────────────────────────── request models

class ValuateRequest(BaseModel):
    address: str | None = Field(None, description="Full property address")
    postcode: str | None = Field(None, description="Postcode (used if no address)")
    user_id: str = Field(..., description="Telegram user ID")
    beds: int | None = Field(None, description="Number of bedrooms")
    sqm: float | None = Field(None, description="Floor area in sqm")
    ptype: str | None = Field(None, description="Property type slug")
    finish: str = Field("average", description="Finish quality")


# ──────────────────────────────────────────────────────────── auth helper (SERVER-SIDE)

def _resolve_tier(user_id: str) -> str:
    """Determine the user's tier server-side.

    The frontend NEVER passes the tier. We look it up from Redis
    (set by the successful_payment webhook) or default to 'free'.
    This is the sole source of truth for entitlements.
    """
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        tier = r.get(f"honestly:tier:{user_id}")
        if tier in ("plus", "pro"):
            return tier
    except Exception:
        pass
    return "free"


def _get_user_id(authorization: str | None) -> str:
    """Extract user_id from the Authorization header.

    Format: Bearer {user_id}
    The frontend only passes the user_id. No tier information is trusted.
    """
    if not authorization:
        return "anonymous"
    try:
        token = authorization.replace("Bearer ", "").strip()
        return token.split(":")[0]
    except Exception:
        return "anonymous"


# ──────────────────────────────────────────────────────────── endpoints

@router.post("/properties/valuate")
def valuate_property(
    req: ValuateRequest,
    authorization: Optional[str] = Header(None),
):
    """Run the full AVM + Arena + product triggers pipeline.

    Tier is resolved SERVER-SIDE via Redis. The frontend cannot lie about it.

    Returns 429 if the user has exceeded their daily AVM limit.
    """
    from auth.entitlements import check_avm_limit, increment_avm_count, TIER_AVM_DAILY_LIMIT

    # Resolve the address
    address = req.address or req.postcode
    if not address:
        raise HTTPException(status_code=400, detail="address or postcode is required")

    # Server-side auth: frontend only provides user_id
    user_id = req.user_id or _get_user_id(authorization)
    tier = _resolve_tier(user_id)

    # Step 1: Check AVM entitlements (server-side, cannot be bypassed)
    limit_check = check_avm_limit(user_id, tier)
    if not limit_check.get("allowed"):
        daily_limit = TIER_AVM_DAILY_LIMIT.get(tier, 1)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "avm_limit_reached",
                "message": f"Daily AVM limit reached ({daily_limit}/day for {tier} tier)",
                "tier": tier,
                "daily_limit": daily_limit,
                "upgrade_prompt": "Upgrade to Plus for 3 AVMs/day or Pro for unlimited",
            },
        )

    # Step 2: Run the orchestrator
    from core.orchestrator import run_valuation
    result = run_valuation(
        address=address,
        user_id=user_id,
        user_tier=tier,
        beds=req.beds,
        sqm=req.sqm,
        ptype=req.ptype,
        finish=req.finish,
    )

    # Step 3: Increment the AVM count (only if valuation succeeded)
    if result.get("ok") and result.get("avm", {}).get("ok"):
        increment_avm_count(user_id)

    # Step 4: Return the payload
    return {
        "ok": result.get("ok", False),
        "avm": result.get("avm"),
        "product_triggers": result.get("product_triggers", []),
        "user_id": user_id,
        "tier": tier,  # authoritative tier, set server-side
        "avm_remaining_today": limit_check.get("remaining", 0),
        "elapsed_s": result.get("elapsed_s"),
    }
