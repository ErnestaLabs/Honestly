#!/usr/bin/env python3
"""decision_models.py - transparent decision layers around the valuation.

These models sit BESIDE the figure. They do not move the valuation. They translate
one evidence-backed value range into decision consequences: finance pressure,
down-valuation exposure, and pre-survey risk. They are estimates, not lender
advice, not a survey, and not a RICS valuation.
"""
import math

DEFAULT_RATE = 0.0525      # launch assumption; user-facing copy calls it an estimate
DEFAULT_TERM_YEARS = 25


def money(n):
    try:
        return "£" + f"{int(round(n)):,}"
    except Exception:
        return "£0"


def _band(low, high, val):
    if val <= low:
        return "low"
    if val <= high:
        return "medium"
    return "high"


def monthly_payment(principal, annual_rate=DEFAULT_RATE, years=DEFAULT_TERM_YEARS):
    """Repayment mortgage estimate. Returns None for invalid inputs."""
    try:
        p = float(principal)
        if p <= 0:
            return 0
        r = float(annual_rate) / 12.0
        n = int(years) * 12
        if r <= 0:
            return p / n
        return p * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    except Exception:
        return None


def affordability(price, deposit=None, income=None, rate=DEFAULT_RATE, years=DEFAULT_TERM_YEARS):
    """Buyer affordability pressure from user-provided price/deposit/income.

    Outputs are deliberately simple and explainable. No lender-specific criteria,
    no guarantee, no hard decision.
    """
    if not price:
        return None
    try:
        price = int(price)
        deposit = int(deposit) if deposit else None
        income = int(income) if income else None
    except Exception:
        return None
    if not deposit and not income:
        return None
    loan = max(0, price - (deposit or 0))
    ltv = (loan / price * 100.0) if price else None
    multiple = (loan / income) if income else None
    monthly = monthly_payment(loan, annual_rate=rate, years=years)

    pressure_score = 0
    reasons = []
    if ltv is not None:
        if ltv >= 90:
            pressure_score += 2; reasons.append(f"{ltv:.0f}% LTV leaves little room if the lender values lower")
        elif ltv >= 80:
            pressure_score += 1; reasons.append(f"{ltv:.0f}% LTV is workable but sensitive to down-valuation")
        else:
            reasons.append(f"{ltv:.0f}% LTV gives more room")
    if multiple is not None:
        if multiple >= 4.75:
            pressure_score += 2; reasons.append(f"loan is about {multiple:.1f}x income")
        elif multiple >= 4.25:
            pressure_score += 1; reasons.append(f"loan is about {multiple:.1f}x income")
        else:
            reasons.append(f"loan is about {multiple:.1f}x income")
    grade = "High" if pressure_score >= 3 else ("Medium" if pressure_score >= 1 else "Low")
    return {
        "price": price,
        "deposit": deposit,
        "income": income,
        "loan": int(round(loan)),
        "ltv_pct": round(ltv, 1) if ltv is not None else None,
        "income_multiple": round(multiple, 2) if multiple is not None else None,
        "monthly_payment": int(round(monthly)) if monthly is not None else None,
        "rate_pct": round(rate * 100, 2),
        "term_years": years,
        "pressure": grade,
        "reasons": reasons[:3],
    }


def downvaluation_exposure(price, low, high, central, deposit=None):
    """How exposed a buyer is if a lender/surveyor lands below the agreed price."""
    if not price or not central:
        return None
    try:
        price, low, high, central = map(int, (price, low, high, central))
        deposit = int(deposit) if deposit else None
    except Exception:
        return None
    above_high = max(0, price - high)
    above_central = price - central
    if price <= high:
        grade = "Low"
        text = "The price sits inside the evidence-supported range."
    elif above_high <= max(15000, central * 0.04):
        grade = "Medium"
        text = f"The price is {money(above_high)} above the top of the evidence range."
    else:
        grade = "High"
        text = f"The price is {money(above_high)} above the top of the evidence range."
    cash_gap = max(0, above_central)
    if deposit and cash_gap:
        cash_text = f"If a lender landed near our central estimate, you may need about {money(cash_gap)} more cash or a lower price."
    elif cash_gap:
        cash_text = f"If a lender landed near our central estimate, the gap is about {money(cash_gap)}."
    else:
        cash_text = "A lender value near our central estimate would not create a price gap."
    return {
        "grade": grade,
        "above_high": above_high,
        "above_central": above_central,
        "cash_gap": cash_gap,
        "text": text,
        "cash_text": cash_text,
    }


def pre_survey_risk(summary, answers=None):
    """Pre-survey risk screen from transparent inputs.

    This is a question list, not a survey. It should help a buyer/seller know what
to ask before spending more money.
    """
    answers = answers or {}
    risk = 0
    reasons = []
    asks = []
    epc = (summary or {}).get("epc")
    try:
        epc_val = int(epc) if epc not in (None, "") else None
    except Exception:
        epc_val = None
    if epc_val is None:
        risk += 1; reasons.append("no EPC rating was available in the lite evidence")
        asks.append("Ask for the EPC certificate and any recent energy upgrade works")
    elif epc_val < 55:
        risk += 2; reasons.append(f"EPC {epc_val} suggests upgrade pressure")
        asks.append("Ask what insulation, heating and window upgrades have already been done")
    elif epc_val < 69:
        risk += 1; reasons.append(f"EPC {epc_val} is not poor, but still worth checking")

    finish = answers.get("finish") or "average"
    if finish == "needs_renovation":
        risk += 3; reasons.append("condition is marked as full renovation")
        asks += ["Ask for roof, damp, electrics and heating history", "Budget for invasive survey findings"]
    elif finish == "needs_modernising":
        risk += 2; reasons.append("condition is marked as dated / needs work")
        asks += ["Ask for boiler age and electrical certificate", "Check damp, roof and window condition before survey"]
    elif finish in ("high", "very_high"):
        asks.append("Ask for certificates and guarantees for recent works")

    conf = (summary or {}).get("confidence") or {}
    if conf.get("grade") in ("Low", "Fair"):
        risk += 1; reasons.append(f"valuation confidence is {conf.get('grade')}, so evidence is less tight")

    if not (summary or {}).get("sqm"):
        risk += 1; reasons.append("floor area is not confirmed in the lite evidence")
        asks.append("Ask for the floorplan and confirm measured floor area")

    grade = "High" if risk >= 5 else ("Medium" if risk >= 2 else "Low")
    if not asks:
        asks.append("Ask the seller/agent what a recent survey would likely flag")
    return {"grade": grade, "reasons": reasons[:4], "asks": asks[:4]}
