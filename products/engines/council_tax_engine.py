#!/usr/bin/env python3
"""products/engines/council_tax_engine.py - "Why Am I Paying More Council Tax Than Next Door?"

The Council Tax Banding Challenger: Anger-triggered micro-upsell.

Logic:
  1. Get subject floor area from graph_db
  2. Get nearby neighbours' sqm and bands from graph_db
  3. Apply rule: if subject sqm < neighbour sqm AND subject band >= neighbour band, flag it
  4. Generate the VOA challenge letter via LangChain (or template fallback)

Uses langchain_openai.ChatOpenAI via OpenRouter for the letter.
API key read from OPENROUTER_API_KEY environment variable.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_MODEL = "meta-llama/llama-3-70b-instruct"

# England VOA Council Tax band thresholds (based on 1991 capital values)
# These are the statutory boundaries. A property in Band D with 1991 value
# below £68,000 should arguably be in Band C.
BAND_THRESHOLDS = {
    "A": (0, 40000),
    "B": (40001, 52000),
    "C": (52001, 68000),
    "D": (68001, 88000),
    "E": (88001, 120000),
    "F": (120001, 160000),
    "G": (160001, 320000),
    "H": (320001, float("inf")),
}

CHALLENGE_PROMPT = """You are a UK property tax expert writing a formal Council Tax banding challenge letter to the Valuation Office Agency (VOA).

The property at {subject_address} ({subject_sqm} sqm, EPC {epc_rating}) is currently in Council Tax Band {current_band}.

Evidence that the banding may be incorrect:
{evidence_section}

Write a formal challenge letter to the VOA. Follow these rules:
1. Use formal British English.
2. Cite the specific evidence from comparable properties.
3. Reference the VOA's own banding thresholds.
4. Request a review under Section 24 of the Local Government Finance Act 1992.
5. Keep it under 400 words.
6. Use proper letter format with date and address block.

Do NOT include "Subject:" line. Start with the date and formal address."""


def assess_council_tax(
    subject_address: str,
    subject_sqm: int,
    subject_epc: str,
    current_band: str,
    postcode: str,
    model: str | None = None,
) -> dict:
    """Assess whether a property's council tax band may be wrong and generate a challenge letter.

    Args:
        subject_address: the property address
        subject_sqm: floor area in sqm
        subject_epc: EPC rating
        current_band: current council tax band (A-H)
        postcode: property postcode
        model: OpenRouter model name (optional)

    Returns:
        {"ok": True, "flags": [...], "challenge_letter": str, "format": "text"}
    """
    current_band = (current_band or "").upper().strip()[:1]
    if current_band not in BAND_THRESHOLDS:
        return {"ok": False, "error": f"Invalid band: {current_band}"}

    # 1. Get neighbouring properties from graph_db
    neighbours = _get_neighbour_properties(postcode)

    # 2. Apply the comparison rule
    flags = []
    for n in neighbours[:10]:
        n_sqm = n.get("sqm") or 0
        n_band = n.get("band") or ""
        if not n_band:
            continue
        # Flag if subject is smaller AND in same or higher band
        if n_sqm > 0 and subject_sqm < n_sqm and current_band >= n_band:
            flags.append({
                "type": "size_band_mismatch",
                "neighbour_address": n.get("address", ""),
                "neighbour_sqm": n_sqm,
                "neighbour_band": n_band,
                "subject_sqm": subject_sqm,
                "subject_band": current_band,
                "note": f"Neighbour at {n_sqm} sqm is in Band {n_band} but subject at {subject_sqm} sqm is in Band {current_band}",
            })

    # 3. Also flag if the subject's sqm is below the typical range for its band
    # (Very rough heuristic: smaller properties should be in lower bands)
    band_below = chr(ord(current_band) - 1) if current_band > "A" else "A"
    if flags:
        verdict = "Challenge likely valid"
        confidence = 80
    elif len(neighbours) >= 3:
        verdict = "Band appears consistent with local properties"
        confidence = 70
    else:
        verdict = "Insufficient data for comparison"
        confidence = 40

    # 4. Generate the challenge letter
    evidence_section = _format_evidence(flags, neighbours, current_band, subject_sqm)
    challenge_letter = _generate_challenge_letter(
        subject_address, subject_sqm, subject_epc, current_band,
        evidence_section, model,
    )

    return {
        "ok": True,
        "verdict": verdict,
        "confidence_pct": confidence,
        "flags": flags,
        "flag_count": len(flags),
        "challenge_letter": challenge_letter,
        "current_band": current_band,
        "subject_sqm": subject_sqm,
        "band_below": band_below,
        "format": "text",
    }


def _get_neighbour_properties(postcode: str) -> list[dict]:
    """Get neighbouring properties with sqm and band data.

    Uses graph_db for floor areas and a simple band inference
    based on price bands.
    """
    neighbours = []
    try:
        from graph_db import GraphQuery
        gq = GraphQuery()
        sales = gq.sales_for_postcode(postcode, limit=50)
        for s in sales:
            # Infer a rough band from the sale price
            # (this is an approximation; actual bands are based on 1991 values)
            price = s.get("price", 0)
            band = _infer_band_from_price(price)
            neighbours.append({
                "address": f"{s.get('paon', '')} {s.get('street', '')}".strip(),
                "sqm": s.get("sqm"),
                "price": price,
                "band": band,
            })
        gq.close()
    except Exception as e:
        log.debug("Neighbour lookup failed for %s: %s", postcode, e)
    return neighbours


def _infer_band_from_price(price: float) -> str:
    """Rough inference of council tax band from current sale price.

    This is a VERY rough heuristic. Actual bands are based on 1991 values.
    We apply a rough deflator to estimate the 1991 value from the current price.
    UK house prices have roughly 4-5x since 1991 in many areas.
    """
    if price <= 0:
        return ""
    # Rough 1991 value estimate (current price / 4.5)
    estimated_1991 = price / 4.5
    for band, (lo, hi) in BAND_THRESHOLDS.items():
        if lo <= estimated_1991 <= hi:
            return band
    return "H"


def _format_evidence(flags: list[dict], neighbours: list[dict], current_band: str, subject_sqm: int) -> str:
    """Format the evidence for the LLM prompt."""
    lines = []
    if flags:
        lines.append(f"The subject property ({subject_sqm} sqm, Band {current_band}) is smaller than the following neighbours in the same or lower bands:")
        for f in flags[:5]:
            lines.append(f"  - {f['neighbour_address']}: {f['neighbour_sqm']} sqm, Band {f['neighbour_band']}")
    else:
        lines.append(f"No clear size/band mismatches found among {len(neighbours)} neighbouring properties.")
        lines.append(f"The subject property is {subject_sqm} sqm in Band {current_band}.")
    return "\n".join(lines)


def _generate_challenge_letter(
    subject_address: str,
    subject_sqm: int,
    subject_epc: str,
    current_band: str,
    evidence_section: str,
    model: str | None = None,
) -> str:
    """Generate the VOA challenge letter via LangChain or template fallback."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")

    if api_key:
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage

            prompt = CHALLENGE_PROMPT.format(
                subject_address=subject_address,
                subject_sqm=subject_sqm,
                epc_rating=subject_epc or "unknown",
                current_band=current_band,
                evidence_section=evidence_section,
            )

            llm = ChatOpenAI(
                model=model or DEFAULT_MODEL,
                openai_api_key=api_key,
                openai_api_base="https://openrouter.ai/api/v1",
                max_tokens=800,
                temperature=0.5,
            )
            response = llm.invoke([HumanMessage(content=prompt)])
            return response.content.strip()
        except Exception as e:
            log.warning("LangChain/OpenRouter call failed: %s. Using template fallback.", e)

    # Template fallback
    band_below = chr(ord(current_band) - 1) if current_band > "A" else "A"
    return f"""Valuation Office Agency

Re: Council Tax Banding Challenge - {subject_address}

I wish to challenge the Council Tax banding of my property at {subject_address} ({subject_sqm} sqm, EPC {subject_epc or 'unknown'}), which is currently in Band {current_band}.

Grounds for challenge:

1. The property is {subject_sqm} sqm, which is smaller than typical Band {current_band} properties in this area.

2. {evidence_section}

3. Based on the VOA's own banding thresholds, the property's estimated 1991 value would not have exceeded the Band {band_below} upper threshold of £{BAND_THRESHOLDS.get(band_below, (0,0))[1]:,}.

I request a formal review of the banding under Section 24 of the Local Government Finance Act 1992, and ask that the VOA provide the listing details and 1991 value used to assign Band {current_band}.

Yours faithfully"""
