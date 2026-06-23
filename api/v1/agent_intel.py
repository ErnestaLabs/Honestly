"""api/v1/agent_intel.py — Agent Pro B2B dashboard API.

High-ticket product endpoints that estate agents pay £14.99/mo for.
Delivers predictive property instruction intelligence without exposing user PII.

Endpoints:
  GET /api/v1/agent/intel/feed
    Returns properties with sell_probability > 60 in the agent's subscribed
    postcodes. No PII — just property_id, postcode, score, and signal types.

  GET /api/v1/agent/intel/stats/{postcode}
    Aggregate market intelligence for a postcode area.

Authentication:
  All endpoints require a valid Pro-tier API key passed as
  the X-API-Key header. The key is validated against the
  agent_pro keys stored in Redis.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from auth.entitlements import UserEntitlements
from core.intent_engine import (
    get_high_intent_properties,
    get_postcode_stats,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/agent/intel", tags=["agent"])

# Redis prefix for agent API keys
_AGENT_KEY_PREFIX = "honestly:agent:apikey:"


def _validate_agent_api_key(api_key: str) -> dict:
    """Validate an agent API key against Redis store.

    Returns agent metadata dict on success, raises 401 on failure.
    The key format is: hkey_<random_40_chars>
    We store the SHA-256 hash of the key for security.
    """
    if not api_key or not api_key.startswith("hkey_"):
        raise HTTPException(status_code=401, detail="Invalid API key format")

    try:
        import redis as redis_mod
        r = redis_mod.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )
        # Hash the key for lookup
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        agent_data = r.get(f"{_AGENT_KEY_PREFIX}{key_hash}")
        if not agent_data:
            raise HTTPException(status_code=401, detail="Invalid API key")

        import json
        agent = json.loads(agent_data)

        # Verify Pro tier
        if agent.get("tier") != "pro":
            raise HTTPException(
                status_code=403,
                detail="Agent Pro subscription required. Upgrade at usehonestly.co.uk",
            )

        return agent

    except HTTPException:
        raise
    except Exception as e:
        log.warning("Agent API key validation failed: %s", e)
        raise HTTPException(status_code=401, detail="Authentication failed")


# ── Agent feed ─────────────────────────────────────────────────────────────
@router.get("/feed")
def agent_intel_feed(
    api_key: str = Header(..., alias="X-API-Key"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    min_score: int = Query(60, ge=0, le=100, description="Minimum sell probability"),
):
    """Return high-intent properties for the agent's monitored postcodes.

    No PII is returned — only the property identifier, postcode, intent
    score, and the signal types that triggered the score. This is the
    core B2B value prop: agents pay to know which properties are "hot"
    before anyone else does.

    Response format:
    ```json
    {
        "ok": true,
        "agent_id": "ag_1234",
        "monitored_postcodes": ["SW16", "SE27"],
        "results": [
            {
                "property_id": "SW16 2JY",
                "postcode": "SW16",
                "sell_probability": 80,
                "signal_count": 4,
                "signal_types": ["valuation_run", "returned_7_days"]
            }
        ],
        "result_count": 1,
        "threshold": 60
    }
    ```
    """
    agent = _validate_agent_api_key(api_key)
    postcodes = agent.get("postcodes", [])
    if not postcodes:
        return {
            "ok": True,
            "agent_id": agent.get("agent_id"),
            "monitored_postcodes": [],
            "results": [],
            "result_count": 0,
            "threshold": min_score,
            "message": "No postcodes configured. Update your subscription postcodes.",
        }

    results = get_high_intent_properties(
        postcodes=postcodes,
        threshold=min_score,
        limit=limit,
    )

    return {
        "ok": True,
        "agent_id": agent.get("agent_id"),
        "monitored_postcodes": postcodes,
        "results": results,
        "result_count": len(results),
        "threshold": min_score,
    }


# ── Postcode stats ─────────────────────────────────────────────────────────
@router.get("/stats/{postcode}")
def agent_postcode_stats(
    postcode: str,
    api_key: str = Header(..., alias="X-API-Key"),
):
    """Aggregate market intelligence for a postcode area.

    Returns anonymised, aggregated data that helps agents decide
    which postcodes to monitor:
      - Total intent signals logged
      - Unique properties tracked
      - Unique users who ran valuations
      - Average sell probability across all tracked properties
      - Count of high-intent properties (score >= 60)
      - Valuation volume in the last 7 days

    The agent must have this postcode in their monitored list.
    """
    agent = _validate_agent_api_key(api_key)
    monitored = agent.get("postcodes", [])

    # Check the agent monitors this postcode (or is an admin)
    pc_upper = postcode.upper().strip()
    if monitored and pc_upper not in monitored and agent.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail=f"Postcode {pc_upper} not in your monitored list. "
                   f"Update your subscription to add it.",
        )

    stats = get_postcode_stats(pc_upper)

    return {
        "ok": True,
        "agent_id": agent.get("agent_id"),
        "stats": stats,
    }


# ── Agent API key management (internal/admin) ─────────────────────────────
def register_agent_api_key(
    agent_id: str,
    api_key: str,
    postcodes: list[str],
    tier: str = "pro",
    role: str = "agent",
) -> bool:
    """Register a new agent API key in Redis.

    This is called by the admin panel or subscription webhook when an
    agent subscribes to Pro. Not exposed as a public endpoint.

    Args:
        agent_id: Unique agent identifier (e.g. ag_1234).
        api_key: The raw API key (hkey_...). We store a hash.
        postcodes: List of postcode outcodes to monitor.
        tier: Subscription tier (default: pro).
        role: Agent role (agent, admin).

    Returns:
        True on success.
    """
    try:
        import json
        import redis as redis_mod
        r = redis_mod.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        agent_data = json.dumps({
            "agent_id": agent_id,
            "postcodes": [p.upper().strip() for p in postcodes],
            "tier": tier,
            "role": role,
            "created_at": __import__("time").time(),
        })
        r.setex(f"{_AGENT_KEY_PREFIX}{key_hash}", 365 * 86400, agent_data)
        log.info("Registered agent API key: agent=%s postcodes=%s", agent_id, postcodes)
        return True
    except Exception as e:
        log.warning("Failed to register agent API key: %s", e)
        return False
