#!/usr/bin/env python3
"""products/engines/lowball_engine.py - "Are They Taking The Piss?"

The Lowball Counter-Email: Anger-triggered micro-upsell.

A seller receives a lowball offer. This engine:
  1. Pulls the full AVM valuation and strict comps
  2. Formats a structured prompt with the evidence
  3. Calls LangChain ChatOpenAI via OpenRouter
  4. Returns a fiercely worded, professional counter-offer email

Uses langchain_openai.ChatOpenAI pointed at OpenRouter.
API key read from OPENROUTER_API_KEY environment variable.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

# Default OpenRouter model (cheap, fast, good enough for email generation)
DEFAULT_MODEL = "meta-llama/llama-3-70b-instruct"


# ──────────────────────────────────────────────────────── prompt template

COUNTER_EMAIL_PROMPT = """You are a UK property valuation expert writing a counter-offer email on behalf of a seller.

The seller's property at {subject_address} has received an offer of £{lowball_offer:,}.

Our independent AVM (Automated Valuation Model), backed by HM Land Registry sold evidence, values this property at:
  - Assessed Value: £{assessed_value:,}
  - Range: £{low_range:,} - £{high_range:,}
  - Confidence: {confidence_score}/100 ({confidence_grade})
  - Floor Area: {sqm} sqm
  - EPC Rating: {epc_rating}

Strict sold comparables from HM Land Registry Price Paid Data:
{comps_section}

Write a professional but firm counter-offer email from the seller to their estate agent.

Rules:
1. Reference specific sold comparables by address and price.
2. State the assessed value clearly.
3. Be forensic and data-backed, not emotional or aggressive.
4. Keep it under 300 words.
5. Include a suggested counter-offer figure near the assessed value.
6. Close with a clear call to action.
7. Use British English spelling.

Do NOT include a subject line. Start with "Dear Agent," and end with "Kind regards." """


def _format_comps(evidence: list[dict]) -> str:
    """Format the sold comparables into a readable list for the prompt."""
    if not evidence:
        return "  No strict comparables available."
    lines = []
    for i, e in enumerate(evidence[:5], 1):
        addr = e.get("address", "Unknown")
        price = e.get("price", 0)
        date = e.get("date", "Unknown")
        sqm = e.get("sqm", "?")
        line = f"  {i}. {addr}: £{price:,} ({date[:7] if len(date) >= 7 else date}, {sqm} sqm)"
        lines.append(line)
    return "\n".join(lines)


# ──────────────────────────────────────────────────────── main execution

def generate_counter_email(
    subject_address: str,
    assessed_value: int,
    low_range: int,
    high_range: int,
    confidence_score: int,
    confidence_grade: str,
    sqm: int,
    epc_rating: str,
    lowball_offer: int,
    evidence: list[dict],
    model: str | None = None,
) -> dict:
    """Generate a counter-offer email using LangChain + OpenRouter.

    Args:
        subject_address: the property address
        assessed_value: the AVM central value in GBP
        low_range: lower bound of the AVM range
        high_range: upper bound of the AVM range
        confidence_score: 0-100 confidence
        confidence_grade: Strong/Good/Fair/Low
        sqm: floor area in sqm
        epc_rating: EPC band (A-G)
        lowball_offer: the offer the seller received
        evidence: list of comparable sale dicts with address/price/date/sqm
        model: OpenRouter model name (optional)

    Returns:
        {"ok": True, "email_text": str, "model": str, "format": "text"}
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return _fallback_email(
            subject_address, assessed_value, low_range, high_range,
            confidence_score, confidence_grade, sqm, epc_rating,
            lowball_offer, evidence,
        )

    # Build the prompt
    comps_section = _format_comps(evidence)
    prompt = COUNTER_EMAIL_PROMPT.format(
        subject_address=subject_address,
        lowball_offer=lowball_offer,
        assessed_value=assessed_value,
        low_range=low_range,
        high_range=high_range,
        confidence_score=confidence_score,
        confidence_grade=confidence_grade,
        sqm=sqm or "?",
        epc_rating=epc_rating or "unknown",
        comps_section=comps_section,
    )

    # Call LangChain ChatOpenAI via OpenRouter
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        llm = ChatOpenAI(
            model=model or DEFAULT_MODEL,
            openai_api_key=api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            max_tokens=600,
            temperature=0.7,
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        email_text = response.content.strip()
        used_model = model or DEFAULT_MODEL
    except Exception as e:
        log.warning("LangChain/OpenRouter call failed: %s. Using template fallback.", e)
        return _fallback_email(
            subject_address, assessed_value, low_range, high_range,
            confidence_score, confidence_grade, sqm, epc_rating,
            lowball_offer, evidence,
        )

    return {
        "ok": True,
        "email_text": email_text,
        "model": used_model,
        "format": "text",
        "lowball_offer": lowball_offer,
        "assessed_value": assessed_value,
        "gap_pct": round((1 - lowball_offer / max(1, assessed_value)) * 100, 1),
    }


# ──────────────────────────────────────────────────────── template fallback

def _fallback_email(
    subject_address: str,
    assessed_value: int,
    low_range: int,
    high_range: int,
    confidence_score: int,
    confidence_grade: str,
    sqm: int,
    epc_rating: str,
    lowball_offer: int,
    evidence: list[dict],
) -> dict:
    """Template-based fallback when the LLM is unavailable.

    Generates a professional counter-offer using the data directly,
    without any AI generation. Always works offline.
    """
    gap_pct = round((1 - lowball_offer / max(1, assessed_value)) * 100, 1)
    comps_section = _format_comps(evidence)

    email = f"""Dear Agent,

Thank you for forwarding the offer of £{lowball_offer:,} on {subject_address}.

Based on an independent analysis of HM Land Registry Price Paid Data, this property is assessed at £{assessed_value:,} (range: £{low_range:,} - £{high_range:,}, confidence {confidence_score}/100, {confidence_grade}). The property comprises {sqm or '?'} sqm with an EPC rating of {epc_rating or 'unknown'}.

The offer of £{lowball_offer:,} represents a {gap_pct}% discount to the assessed value, which falls below the lower bound of our evidence-backed range.

Recent sold comparables supporting this assessment:
{comps_section}

I would welcome an offer closer to £{assessed_value:,}, which reflects the sold evidence from comparable properties in the immediate area.

Kind regards."""

    return {
        "ok": True,
        "email_text": email.strip(),
        "model": "template_fallback",
        "format": "text",
        "lowball_offer": lowball_offer,
        "assessed_value": assessed_value,
        "gap_pct": gap_pct,
    }
