"""monetization/router.py — Contextual affiliate marketplace injector.

NerdWallet-style placement engine. After the AVM runs, this module
inspects the valuation context and injects the highest-CPA affiliate
offers as a marketplace_offers array in the payload.

Affiliate logic:
  - assessed_value > £500,000  → Premium Mortgage Broker
  - epc_rating < C              → Boiler Upgrade Scheme / Green Homes Grant
  - property_type == "flat"     → Leasehold Conveyancer
  - confidence_score < 50       → Second Opinion Surveyor

Each offer is a dict with:
  - provider_name: Human-readable name
  - offer_type: Category (mortgage, energy, conveyancing, survey)
  - description: Short pitch
  - cpa_cents: CPA in pence/cents (for analytics)
  - url: Affiliate link (placeholder — replace with real affiliate IDs)
  - relevance_score: 0–100 how well this fits the user's context
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


def get_marketplace_offers(avm: dict) -> list[dict]:
    """Inspect AVM context and return the most relevant affiliate offers.

    Args:
        avm: The AVM result dict from the orchestrator. Must contain
             at minimum: central (assessed value), epc, type, confidence_score.

    Returns:
        List of offer dicts, empty if no offers match.
    """
    offers = []

    if not avm or not avm.get("ok"):
        return offers

    assessed_value = avm.get("central") or 0
    epc_rating = (avm.get("epc") or "").upper().strip()
    property_type = (avm.get("type") or "").lower()
    confidence_score = avm.get("confidence_score") or 50

    # ── Premium Mortgage Broker (assessed_value > £500k) ──────────────
    if assessed_value > 500_000:
        offers.append({
            "provider_name": "Habito Premium",
            "offer_type": "mortgage",
            "description": (
                f"With a valuation of £{assessed_value:,.0f}, a specialist "
                "broker can find you the best rates. Compare tailored mortgage "
                "deals for high-value properties."
            ),
            "cpa_cents": 2500,  # £25 CPA
            "url": "https://usehonestly.co.uk/offers/mortgage",
            "relevance_score": 85,
            "trigger": "high_value",
        })

    # ── Boiler Upgrade / Green Grant (EPC < C) ───────────────────────
    if epc_rating and epc_rating in ("D", "E", "F", "G"):
        offers.append({
            "provider_name": "Boiler Upgrade Scheme",
            "offer_type": "energy",
            "description": (
                f"Your EPC rating is {epc_rating}. You may qualify for a "
                "£7,500 government grant to upgrade your heating system. "
                "Check eligibility in 2 minutes."
            ),
            "cpa_cents": 1500,  # £15 CPA
            "url": "https://usehonestly.co.uk/offers/boiler-upgrade",
            "relevance_score": 90,
            "trigger": "poor_epc",
        })

    # ── Leasehold Conveyancer (flats) ────────────────────────────────
    if "flat" in property_type or "maisonette" in property_type:
        offers.append({
            "provider_name": "Leasehold Advice",
            "offer_type": "conveyancing",
            "description": (
                "Flats are commonly leasehold. Get a specialist conveyancer "
                "to review ground rent, service charges, and lease terms "
                "before you commit."
            ),
            "cpa_cents": 2000,  # £20 CPA
            "url": "https://usehonestly.co.uk/offers/leasehold-conveyancer",
            "relevance_score": 75,
            "trigger": "leasehold",
        })

    # ── Second Opinion Surveyor (low confidence) ─────────────────────
    if confidence_score < 50:
        offers.append({
            "provider_name": "RICS Surveyor Match",
            "offer_type": "survey",
            "description": (
                f"Our confidence score is {confidence_score}/100. A local "
                "RICS surveyor can provide a detailed building survey to "
                "confirm the property's condition and value."
            ),
            "cpa_cents": 3000,  # £30 CPA
            "url": "https://usehonestly.co.uk/offers/surveyor",
            "relevance_score": 80,
            "trigger": "low_confidence",
        })

    # Sort by relevance_score descending
    offers.sort(key=lambda o: o["relevance_score"], reverse=True)

    log.debug("Generated %d marketplace offers for property", len(offers))
    return offers
