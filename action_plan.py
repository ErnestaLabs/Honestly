#!/usr/bin/env python3
"""action_plan.py - the Pro per-role plan of action (PRODUCT_SPEC section 13, build #70).

This is the dossier's spine: a written, numbered strategy keyed to the reader's role -
BUYING, SELLING or LISTING. It does not invent advice or numbers; it composes the figures
the engine already produced (via the scenario pricing matrix, scenario.py) with the real
costs the reader will face - SDLT from the banded HMRC calculator (macro.sdlt), the agent
fee and CGT from the same arithmetic the PDF prints - and the live-positioning leverage and
macro timing already in engine.summary(). Every price and cost traces to a source; the plan
strategises around the figure, it never creates a new one.

Built on the existing `audience` framing threaded through engine.summary() (buyer / vendor /
agent), extended from the short products.plan_of_action into a full, costed, scenario-anchored
plan. Pro-only and best-effort: returns {ok: False} rather than raise.

  build(d, r=None, audience=None, asking=None) -> structured plan dict
  lines(plan) -> ready markdown for any text surface
"""
import macro
import scenario
from appraise import money

# legal + survey ranges - the same indicative figures the PDF's buyer-costs table prints,
# kept in one place so the two never disagree. These are ranges, shown as ranges, never a
# single fabricated precise fee.
_LEGAL_LO, _LEGAL_HI = 1000, 1500
_SURVEY_LO, _SURVEY_HI = 400, 1000


def _buyer_costs(price):
    """Real cash-in costs for a purchase at `price`: banded SDLT (standard + first-time),
    plus indicative legal and survey ranges. All sourced, none invented."""
    std = macro.sdlt(price, first_time=False)
    ftb = (macro.sdlt(price, first_time=True)
           if price <= getattr(macro, "SDLT_FTB_CEILING", 500_000) else None)
    ftb = ftb if (ftb is not None and ftb < std) else None
    lo_total = price + std + _LEGAL_LO + _SURVEY_LO
    hi_total = price + std + _LEGAL_HI + _SURVEY_HI
    return {
        "price": price, "price_str": money(price),
        "sdlt": std, "sdlt_str": money(std),
        "sdlt_ftb": ftb, "sdlt_ftb_str": (money(ftb) if ftb is not None else None),
        "legal_lo": _LEGAL_LO, "legal_hi": _LEGAL_HI,
        "survey_lo": _SURVEY_LO, "survey_hi": _SURVEY_HI,
        "cash_in_lo": lo_total, "cash_in_lo_str": money(lo_total),
        "cash_in_hi": hi_total, "cash_in_hi_str": money(hi_total),
        "source": "HMRC SDLT (England & NI, marginal bands; first-time-buyer relief); "
                  "legal and survey shown as indicative ranges",
    }


def _seller_costs(realistic_row):
    """Real costs out for a sale at the realistic guide: the agent fee and (for an
    investment) CGT, lifted straight from the scenario row so they match the PDF exactly."""
    return {
        "price": realistic_row["price"], "price_str": realistic_row["price_str"],
        "fee": realistic_row["fee"], "fee_str": realistic_row["fee_str"],
        "cgt": realistic_row["cgt"], "cgt_str": realistic_row["cgt_str"],
        "net": realistic_row["net"], "net_str": realistic_row["net_str"],
        "source": "2%+VAT agent fee" + (", indicative 24% CGT after the £3,000 allowance"
                                        if realistic_row["cgt"] is not None else ""),
    }


def build(d, r=None, audience=None, asking=None):
    """Compose the role-specific action plan. Reuses the scenario matrix already on the Pro
    summary (or computes it) so the plan and the matrix can never quote different numbers."""
    if not isinstance(d, dict):
        return {"ok": False, "reason": "no summary"}
    audience = audience or d.get("audience") or "vendor"
    m = d.get("scenario")
    if not (isinstance(m, dict) and m.get("ok")):
        pos = (r or {}).get("positioning") if isinstance(r, dict) else None
        m = scenario.matrix(d, pos=pos, asking=asking)
    if not m.get("ok"):
        return {"ok": False, "reason": "scenario unavailable"}

    mom = (d.get("macro") or {}).get("momentum")
    mk = m.get("market_note") or {}
    stuck = mk.get("stuck") or 0
    role = {"buyer": "buying", "vendor": "selling", "agent": "listing"}.get(audience, "selling")

    floor, guide, ceiling = m["selling"][0], m["selling"][1], m["selling"][2]
    steps, costs, title = [], None, ""

    if role == "buying":
        b = m["buying"]
        costs = _buyer_costs(b["opening_offer"])
        title = "Plan of action - buying"
        steps = [
            f"Open at {b['opening_offer_str']}. It is anchored to what comparable homes "
            f"actually sold for (fair value ~{b['fair_value_str']}), not to the asking price.",
            "Put the sold evidence in writing with the offer. A seller can argue with an "
            "opinion; they cannot argue with completed Land Registry sales.",
        ]
        if b.get("headroom_note"):
            steps.append(b["headroom_note"])
        if stuck:
            steps.append(f"Use your leverage: {stuck} comparable home(s) priced above this "
                         f"have sat unsold 90+ days. A long listing means the seller is "
                         f"closer to yes than on day one.")
        steps.append(f"Hold a firm walk-away ceiling at {b['ceiling_str']} - the top of the "
                     f"sold evidence. Above it you are paying for the seller's hope.")
        steps.append("Make the offer subject to survey and have a mortgage agreement in "
                     "principle ready - a clean, fast buyer is worth a price concession.")
        steps.append(
            f"Budget the full cash-in, not just the price: stamp duty about {costs['sdlt_str']}"
            + (f" (or {costs['sdlt_ftb_str']} as a first-time buyer)" if costs["sdlt_ftb"] else "")
            + f", plus legal ({money(costs['legal_lo'])}-{money(costs['legal_hi'])}) and a "
            f"survey ({money(costs['survey_lo'])}-{money(costs['survey_hi'])}). All-in around "
            f"{costs['cash_in_lo_str']}-{costs['cash_in_hi_str']}.")

    elif role == "selling":
        costs = _seller_costs(guide)
        title = "Plan of action - selling"
        steps = [
            f"List at {guide['price_str']}, not at the highest number an agent quotes you. "
            f"It is the evidence-backed level - it balances price against time on market.",
            f"Know your three outcomes before you start: a quick sale near {floor['price_str']} "
            f"({floor['net_str']} in pocket), the realistic guide at {guide['price_str']} "
            f"({guide['net_str']}), or holding out toward {ceiling['price_str']} "
            f"({ceiling['net_str']}) and accepting a longer wait.",
            "Interview agents with this report in hand. Ask each to justify their figure "
            "against the sold comparables - the evidence is your defence against an inflated "
            "quote that wins the instruction but not the sale.",
            "Spend on presentation, not asking price: declutter, fix the obvious, get the "
            "photography right. Condition moves the achievable figure more than the headline "
            "number does.",
        ]
        if stuck:
            steps.append(f"{stuck} comparable home(s) priced above you are stuck unsold. Price "
                         f"deliberately below them and you take their buyers.")
        else:
            steps.append("Launch at the guide and review demand at two weeks - viewings and "
                         "offers, not the asking price, tell you whether it is right.")
        net_line = (f"After a 2%+VAT agent fee"
                    + (f" and indicative CGT of {costs['cgt_str']}" if costs["cgt"] else "")
                    + f", a sale at {guide['price_str']} nets about {costs['net_str']}.")
        steps.append("Budget your costs out: " + net_line)

    else:  # listing (agent)
        ls = m["listing"]
        costs = _seller_costs(guide)
        title = "Plan of action - listing & winning the instruction"
        steps = [
            f"Lead with evidence, not a number. Open on the comparable sales, then land the "
            f"assessment: most likely {m['most_likely_str']} (range {m['range_str']}).",
            f"Recommend listing at {ls['defensible_guide_str']}. The sold evidence supports it; "
            f"a higher quote wins the instruction, not the sale.",
            f"Set the vendor's expectations across the three outcomes: quick sale near "
            f"{floor['price_str']}, realistic at {guide['price_str']}, top of the defensible "
            f"range {ceiling['price_str']} with a longer wait.",
        ]
        if stuck:
            steps.append(f"Use the {stuck} stuck listing(s) above this price as live proof "
                         f"that over-asking sits. That is your close.")
        else:
            steps.append("Show how a correctly-priced launch draws offers in the first two "
                         "weeks, while over-priced stock stalls.")
        steps.append("Work the street: you have just valued this road, so you are the local "
                     "expert at every door. Target the longest-listed homes first - a "
                     "reduction conversation is an instruction conversation.")

    if mom and mom.get("headline"):
        steps.append(f"Frame the timing honestly: {mom['headline']}")

    return {
        "ok": True, "tier": "pro", "audience": audience, "role": role,
        "title": title, "steps": steps, "costs": costs,
        "basis": ("Strategy composed from the assessed figure, the scenario pricing matrix, "
                  "the live competitive positioning and the real transaction costs (SDLT, "
                  "agent fee, CGT). No figure or cost is invented."),
    }


def lines(plan):
    """Numbered markdown for a text surface. Reads ONLY from the plan dict."""
    if not plan or not plan.get("ok"):
        return []
    L = [f"<b>{plan['title']}</b>"]
    for i, step in enumerate(plan["steps"], 1):
        L.append(f"{i}. {step}")
    L.append(f"\n<i>{plan['basis']}</i>")
    return L


if __name__ == "__main__":
    demo = {"low": 590000, "high": 650000, "central": 620000, "guide": 600000,
            "investment": False, "last_sold": 450000, "audience": "buyer",
            "macro": {"momentum": {"headline": "Bank Rate held at 4.0%; momentum is flat."}},
            "scenario": scenario.matrix(
                {"low": 590000, "high": 650000, "central": 620000, "guide": 600000,
                 "investment": False, "last_sold": 450000},
                pos={"band": [1, 2, 3, 4], "mean_dom": 58, "stuck": [1], "fresh": [1],
                     "under_offer": [], "median": 640000}, asking=675000)}
    for aud in ("buyer", "vendor", "agent"):
        print(f"\n===== {aud} =====")
        print("\n".join(lines(build(demo, audience=aud, asking=675000))))
