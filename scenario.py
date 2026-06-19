#!/usr/bin/env python3
"""scenario.py - the Pro scenario pricing matrix (PRODUCT_SPEC section 5, build #69).

Pro turns one number into a decision matrix: the same defensible figure priced for each
scenario the reader might be in. This module is PURE DERIVATION - every price it prints is
one of the real figures the engine already produced (`low` / `guide` / `central` / `high`);
net proceeds use the EXACT fee/CGT arithmetic of `engine.vendor_view`, so the figures can
never drift from the PDF; and "speed" is a qualitative descriptor grounded in the live
positioning evidence (the band's real mean days-on-market, the count of stuck 90+ and fresh
listings) - never a fabricated day count. It invents no number. Honesty rule #2: the matrix
reframes and strategises around the figure, it never creates a new one.

Inputs:
  d   = the engine.summary() dict (carries low/high/central/guide, investment, last_sold,
        audience, and the reduced positioning). The single source of truth.
  pos = the RAW positioning dict (r["positioning"]) when available - it carries mean_dom,
        stuck, fresh, under_offer, median. Optional; the matrix degrades honestly without it.
  asking = the live asking price when the reader supplied one (buyer headroom). Optional.

Returns {ok: True, ...} or {ok: False, reason}. Best-effort: never raises into a report.
"""
from appraise import money, round_to

_FEE_RATE = 0.024            # 2% + VAT - the exact rate engine.vendor_view prints
_CGT_RATE = 0.24             # residential CGT, higher rate
_CGT_ALLOWANCE = 3000        # annual exempt amount used in engine.vendor_view


def _net(price, investment, last_sold):
    """Net in pocket for a sale at `price`, mirroring engine.vendor_view EXACTLY so the
    matrix and the PDF's 'what you'd actually pocket' table can never disagree."""
    fee = round(price * _FEE_RATE)
    net = price - fee
    cgt = None
    if investment:
        gain = max(0, price - (last_sold or 0) - fee - _CGT_ALLOWANCE)
        cgt = round(gain * _CGT_RATE)
        net = price - fee - cgt
    return fee, cgt, net


def _row(key, label, price, speed, speed_note, investment, last_sold):
    fee, cgt, net = _net(price, investment, last_sold)
    return {
        "key": key, "label": label,
        "price": price, "price_str": money(price),
        "fee": fee, "fee_str": money(fee),
        "cgt": cgt, "cgt_str": (money(cgt) if cgt is not None else None),
        "net": net, "net_str": money(net),
        "speed": speed, "speed_note": speed_note,
    }


def _market_note(pos):
    """An honest, positioning-grounded read of how the live band is behaving. Every figure
    here is lifted straight from the real positioning dict - none is modelled."""
    if not pos:
        return None
    band = pos.get("band") or []
    if not band:
        return None
    return {
        "listings": len(band),
        "mean_dom": pos.get("mean_dom"),
        "stuck": len(pos.get("stuck") or []),
        "fresh": len(pos.get("fresh") or []),
        "under_offer": len(pos.get("under_offer") or []),
        "median_ask": pos.get("median"),
        "median_ask_str": (money(pos["median"]) if pos.get("median") else None),
    }


def matrix(d, pos=None, asking=None):
    """Build the full scenario matrix from the real figures. Returns all three role views
    (selling / buying / listing); the renderer or action plan picks the relevant one."""
    if not isinstance(d, dict):
        return {"ok": False, "reason": "no summary"}
    lo, hi = d.get("low"), d.get("high")
    central, guide = d.get("central"), d.get("guide")
    if not all(isinstance(x, (int, float)) for x in (lo, hi, central, guide)):
        return {"ok": False, "reason": "figure incomplete"}

    investment = bool(d.get("investment"))
    last_sold = d.get("last_sold")
    mk = _market_note(pos)

    # ---- speed descriptors, grounded in the positioning evidence (never a day count)
    stuck_n = mk["stuck"] if mk else 0
    ceiling_speed_note = (
        f"At the top of the defensible range - {stuck_n} comparable home(s) priced this "
        f"high have sat unsold 90+ days. Expect a longer wait, then pressure to reduce."
        if stuck_n else
        "At the top of the defensible range - priced for the best offer, not the fastest. "
        "Expect a longer wait."
    )

    # ---- SELLING: quick-sale floor / realistic guide / aspirational ceiling
    selling = [
        _row("quick_sale", "Quick-sale floor", lo, "fast",
             "Priced at the bottom of the defensible range - typically attracts the "
             "fastest interest and competing offers.", investment, last_sold),
        _row("realistic", "Realistic guide", guide, "balanced",
             "The evidence-backed level - balances price against time on market. The "
             "number you can defend to a buyer or a mortgage valuer.", investment, last_sold),
        _row("aspirational", "Aspirational ceiling", hi, "slow",
             ceiling_speed_note, investment, last_sold),
    ]

    # ---- BUYING: sensible opening offer / fair value / walk-away ceiling / headroom
    opening = round_to(guide, 1000)
    buying = {
        "opening_offer": opening, "opening_offer_str": money(opening),
        "fair_value": central, "fair_value_str": money(central),
        "ceiling": hi, "ceiling_str": money(hi),
        "note": ("Open near the guide, hold firm below the ceiling - paying above the top "
                 "of the sold evidence is paying above what comparable homes have achieved."),
    }
    if isinstance(asking, (int, float)) and asking > 0:
        headroom = asking - hi
        buying["asking"] = asking
        buying["asking_str"] = money(asking)
        buying["headroom"] = headroom
        buying["headroom_str"] = money(abs(headroom))
        buying["headroom_note"] = (
            f"Asked at {money(asking)} - about {money(headroom)} above the assessed "
            f"ceiling. That gap is your negotiating headroom, in writing."
            if headroom > 0 else
            f"Asked at {money(asking)} - at or below the assessed ceiling; if condition "
            f"matches the comparables, it is keenly priced."
        )

    # ---- LISTING: instruction-winning-but-defensible guide
    listing = {
        "defensible_guide": guide, "defensible_guide_str": f"Offers Over {money(guide)}",
        "most_likely": central, "most_likely_str": money(central),
        "ceiling": hi, "ceiling_str": money(hi),
        "trap_note": (
            "A higher quote wins the instruction, not the sale. Listing above "
            f"{money(hi)} - the top of the sold evidence - risks the home sitting, then "
            "reducing. Price to the evidence and it sells; price to ego and it waits."),
    }

    return {
        "ok": True,
        "tier": "pro",
        "most_likely": central, "most_likely_str": money(central),
        "range_str": f"{money(lo)} - {money(hi)}",
        "selling": selling,
        "buying": buying,
        "listing": listing,
        "market_note": mk,
        "basis": ("Derived from the assessed range and the live competitive positioning. "
                  "Every price shown is one of the assessed figures (floor, guide, "
                  "most-likely, ceiling); no figure is invented. Net proceeds use a 2%+VAT "
                  "agent fee" + (" and indicative 24% CGT after the £3,000 allowance"
                  if investment else "") + "."),
    }


# convenience text renderers for the bot / plain-text surfaces -------------------------
def lines(m, audience=None):
    """Compact markdown for a text surface (bot card / plan). Renders the role matching
    `audience` when given, otherwise the selling view. Reads ONLY from the matrix dict."""
    if not m or not m.get("ok"):
        return []
    L = ["## Scenario pricing\n",
         f"Most likely achieved: **{m['most_likely_str']}** (assessed range {m['range_str']}).\n"]
    role = {"buyer": "buying", "vendor": "selling", "agent": "listing"}.get(audience, "selling")
    if role in ("selling",):
        cgt = any(r["cgt"] is not None for r in m["selling"])
        head = "| Scenario | Price | Fee | " + ("CGT | " if cgt else "") + "In pocket | Speed |"
        L.append(head)
        L.append("|---|---|---|" + ("---|" if cgt else "") + "---|---|")
        for r in m["selling"]:
            cgt_cell = (f" {r['cgt_str']} |" if cgt else "")
            L.append(f"| {r['label']} | {r['price_str']} | {r['fee_str']} |{cgt_cell} "
                     f"{r['net_str']} | {r['speed']} |")
    elif role == "buying":
        b = m["buying"]
        L.append(f"- Sensible opening offer: **{b['opening_offer_str']}**")
        L.append(f"- Fair value (most likely): **{b['fair_value_str']}**")
        L.append(f"- Walk-away ceiling: **{b['ceiling_str']}**")
        if b.get("headroom_note"):
            L.append(f"\n> {b['headroom_note']}")
        L.append(f"\n{b['note']}")
    else:  # listing
        ls = m["listing"]
        L.append(f"- Defensible guide to list at: **{ls['defensible_guide_str']}**")
        L.append(f"- Most likely achieved: **{ls['most_likely_str']}**")
        L.append(f"- Ceiling you can defend: **{ls['ceiling_str']}**")
        L.append(f"\n> {ls['trap_note']}")
    if m.get("market_note") and m["market_note"].get("mean_dom") is not None:
        mk = m["market_note"]
        L.append(f"\n*Live band: {mk['listings']} comparable listings, typically "
                 f"{mk['mean_dom']} days on market"
                 + (f"; {mk['stuck']} stuck 90+ days" if mk['stuck'] else "")
                 + (f"; {mk['fresh']} fresh (<=20 days)" if mk['fresh'] else "") + ".*")
    L.append(f"\n*{m['basis']}*")
    return L


if __name__ == "__main__":
    # tiny smoke render against a synthetic summary - no network, no spend
    demo = {"low": 590000, "high": 650000, "central": 620000, "guide": 600000,
            "investment": False, "last_sold": 450000, "audience": "vendor"}
    pos = {"band": [1, 2, 3, 4], "mean_dom": 58, "stuck": [1], "fresh": [1, 2],
           "under_offer": [], "median": 640000}
    m = matrix(demo, pos=pos, asking=675000)
    print("\n".join(lines(m, "vendor")))
    print("\n--- buyer ---")
    print("\n".join(lines(m, "buyer")))
