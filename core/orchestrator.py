#!/usr/bin/env python3
"""core/orchestrator.py - The Core Orchestrator.

Master script that runs when a user hits "Value my property" in the Mini App.

Flow:
  1. Run UKQuantValuator to get the AVM math
  2. Award Arena leaderboard points (async, non-blocking)
  3. Return the final payload: AVM data + applicable product triggers

The AVM computation and the Arena point increment run concurrently
via asyncio.gather to keep latency low.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

log = logging.getLogger(__name__)


def run_valuation(
    address: str,
    user_id: str = "anonymous",
    user_tier: str = "free",
    beds: int | None = None,
    sqm: float | None = None,
    ptype: str | None = None,
    finish: str = "average",
) -> dict:
    """Synchronous entry point. Runs the full orchestration pipeline.

    Returns the complete valuation payload with AVM data + product triggers.
    """
    return asyncio.run(_run_valuation_async(
        address=address,
        user_id=user_id,
        user_tier=user_tier,
        beds=beds,
        sqm=sqm,
        ptype=ptype,
        finish=finish,
    ))


async def _run_valuation_async(
    address: str,
    user_id: str = "anonymous",
    user_tier: str = "free",
    beds: int | None = None,
    sqm: float | None = None,
    ptype: str | None = None,
    finish: str = "average",
) -> dict:
    """Async orchestrator. Runs AVM + Arena points concurrently.

    Step 1: UKQuantValuator (via engine.py) produces the AVM math.
    Step 2: Arena leaderboard gets +10 points for the user's postcode.
    Step 3: Product triggers are derived from the AVM results.

    Steps 1 and 2 run via asyncio.gather for concurrent execution.
    Step 3 is dependent on Step 1 and runs after.
    """
    t0 = time.time()

    # ── Step 1 + Step 2: Concurrent ────────────────────────────────
    avm_task = asyncio.to_thread(_compute_avm, address, beds, sqm, ptype, finish)
    arena_task = asyncio.to_thread(_award_arena_points, address, user_id)

    avm_result, _ = await asyncio.gather(avm_task, arena_task)

    # ── Step 3: Derive product triggers ─────────────────────────────
    triggers = _derive_product_triggers(avm_result, user_tier)

    # ── Step 4: Contextual affiliate offers (marketplace layer) ─────
    marketplace_offers = []
    if avm_result.get("ok"):
        try:
            from monetization.router import get_marketplace_offers
            marketplace_offers = get_marketplace_offers(avm_result)
        except Exception as e:
            log.debug("Marketplace offers failed: %s", e)

    # ── Step 5: Log intent signal (async, best-effort) ──────────────
    postcode = avm_result.get("postcode", "")
    if postcode and user_id != "anonymous":
        try:
            from core.intent_engine import log_intent_signal
            log_intent_signal(
                user_id=user_id,
                postcode=postcode,
                property_id=postcode,
                signal_type="valuation_run",
                metadata={"address": address},
            )
        except Exception as e:
            log.debug("Intent signal logging failed: %s", e)

    elapsed = time.time() - t0
    log.info("Orchestrator completed for %s in %.1fs", address, elapsed)

    return {
        "ok": avm_result.get("ok", False),
        "avm": avm_result,
        "product_triggers": triggers,
        "marketplace_offers": marketplace_offers,
        "user_id": user_id,
        "user_tier": user_tier,
        "elapsed_s": round(elapsed, 2),
    }


# ──────────────────────────────────────────────────────────── step 1: AVM

def _compute_avm(
    address: str,
    beds: int | None,
    sqm: float | None,
    ptype: str | None,
    finish: str,
) -> dict:
    """Run the full AVM pipeline via engine.py (which now uses UKQuantValuator).

    Returns a normalised payload with the key valuation figures.
    """
    try:
        from engine import value, summary
        r = value(address, beds=beds, sqm=sqm, ptype=ptype, finish=finish)
        sm = summary(r, audience="seller")
        return {
            "ok": True,
            "address": sm.get("address"),
            "central": sm.get("central"),
            "low": sm.get("low"),
            "high": sm.get("high"),
            "guide": sm.get("guide"),
            "confidence_score": sm.get("confidence_score"),
            "confidence_grade": sm.get("confidence_grade"),
            "sqm": sm.get("sqm"),
            "epc": sm.get("epc"),
            "postcode": sm.get("postcode"),
            "evidence": sm.get("evidence", []),
            "valuation_formula": sm.get("valuation_formula"),
            "quant_derivation": (sm.get("valuation_formula") or {}).get("quant_derivation"),
            "last_sold": sm.get("last_sold"),
            "last_sold_date": sm.get("last_sold_date"),
            "type": sm.get("type"),
            "n_comps": sm.get("n_comps"),
        }
    except Exception as e:
        log.error("AVM computation failed for %s: %s", address, e)
        return {"ok": False, "error": str(e), "address": address}


# ──────────────────────────────────────────────────────────── step 2: arena

def _award_arena_points(address: str, user_id: str) -> bool:
    """Award +10 leaderboard points for the user on their postcode.

    Best-effort: a failure here must never block the valuation.
    """
    try:
        from core.arena import award_avm_points
        from engine import postcode_of
        pc = postcode_of(address)
        if pc and user_id != "anonymous":
            award_avm_points(user_id, pc)
            return True
    except Exception as e:
        log.debug("Arena points failed for %s: %s", address, e)
    return False


# ──────────────────────────────────────────────────────────── step 3: triggers

def _derive_product_triggers(avm_result: dict, user_tier: str) -> list[dict]:
    """Derive which micro-upsells are relevant based on the AVM results.

    Returns a list of trigger dicts, each with:
      - product_id: the catalog product slug
      - reason: why this product is relevant
      - relevance_score: 0-100 how strongly we should suggest it

    Trigger logic maps AVM signals to emotional moments:
      - Low confidence → Fear triggers (Deal Autopsy, Leasehold X-Ray)
      - High £/sqm vs low comps → Anger triggers (Lowball Counter, Council Tax)
      - Few comps → FOMO triggers (Stealth Sniper, Gentrification Radar)
      - Large sqm → Greed triggers (Planning Oracle, Extension Blueprint)
    """
    from auth.entitlements import UserEntitlements
    triggers = []
    entitlements = UserEntitlements.for_tier("u", user_tier)

    if not avm_result.get("ok"):
        return triggers

    confidence = avm_result.get("confidence_score", 50)
    n_comps = avm_result.get("n_comps", 0)
    sqm = avm_result.get("sqm") or 0
    epc = avm_result.get("epc") or ""
    ptype = avm_result.get("type") or ""

    # ── Anger: Lowball Counter-Email ────────────────────────────────
    # Triggered when confidence is low OR the range is wide
    # (suggests the market might undervalue this property)
    if confidence < 60:
        triggers.append({
            "product_id": "lowball_counter_email",
            "reason": "Your confidence score suggests the market may undervalue this property. Get a data-backed counter-offer email.",
            "relevance_score": min(100, 100 - confidence),
        })

    # ── Fear: Leasehold Trap X-Ray ─────────────────────────────────
    # Triggered for flats (most common leasehold type)
    if "flat" in (ptype or "").lower() or "maisonette" in (ptype or "").lower():
        triggers.append({
            "product_id": "leasehold_trap_xray",
            "reason": "Flats are commonly leasehold. Check for hidden traps before you commit.",
            "relevance_score": 85,
        })

    # ── Laziness: Planning Permission Oracle ────────────────────────
    # Triggered for houses (not flats) with development potential
    if "flat" not in (ptype or "").lower() and sqm > 0:
        triggers.append({
            "product_id": "planning_permission_oracle",
            "reason": f"Check if you can extend this {sqm} sqm property under Permitted Development.",
            "relevance_score": 70,
        })

    # ── Anger: Council Tax Challenger ───────────────────────────────
    # Triggered when EPC is poor (D or below) - often correlates with
    # overbanding because the property is in worse condition than the band assumes
    if epc and epc.upper() in ("D", "E", "F", "G"):
        triggers.append({
            "product_id": "council_tax_challenger",
            "reason": f"EPC {epc.upper()} suggests the property may be in worse condition than the council tax band assumes.",
            "relevance_score": 75,
        })

    # ── FOMO: Gentrification Radar ──────────────────────────────────
    # Triggered when few comps exist (thin market = hidden potential)
    if n_comps < 8:
        triggers.append({
            "product_id": "gentrification_radar",
            "reason": "Few recent sales nearby. Is this area about to boom? Check the 5-year forecast.",
            "relevance_score": 65,
        })

    # ── Greed: Neighbor Extension Blueprint ─────────────────────────
    # Triggered for houses with extension potential
    if "flat" not in (ptype or "").lower():
        triggers.append({
            "product_id": "neighbor_extension_blueprint",
            "reason": "See what extensions your neighbours got approved. Know the rules before you build.",
            "relevance_score": 55,
        })

    # Sort by relevance (highest first) and filter by tier access
    triggers.sort(key=lambda t: t["relevance_score"], reverse=True)
    triggers = [t for t in triggers if entitlements.can_access_product(
        _get_product_tier(t["product_id"])
    )]

    return triggers


def _get_product_tier(product_id: str) -> str:
    """Get the tier access level for a product."""
    from products.catalog import get_product
    p = get_product(product_id)
    return p.tier_access if p else "all"
