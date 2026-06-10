#!/usr/bin/env python3
"""engine.py - the valuation engine. One honest number, three audiences.

Sold evidence anchors the value (what buyers have actually paid); a condition-adjusted
AVM and a bounded, fully-disclosed live-market adjustment steer it to what the market
will pay today. Together they produce ONE assessed range. Then a view, filtered to what
each audience actually needs:

  --as vendor   a defensible value, so no agent can inflate it to win the listing
  --as buyer    what to pay, so you don't overpay
  --as agent    everything + competitive positioning + a door-knock route

A home is worth what the market will pay - so we don't anchor on sold data alone. Sold
prices are the floor of fact but they lag the market by months; the live comparable stock
(how fast it sells, how long it sits) steers the figure within a tight cap. Every input
traces to a free, verifiable source. That honesty is the product: free tools quote a
black-box algorithm; we show the comparable sales, the live market, and our working.

Optional audience inputs turn the screw:
  --quoted £N   (vendor) an agent quoted you this - here's what the evidence supports
  --asking £N   (buyer)  this is the asking price - here's your overpay / headroom

Usage:
  set PROPERTYDATA_KEY=...
  python engine.py "58 Cronin Street, London SE15 6JH" --beds 4 --as vendor
  python engine.py "58 Cronin Street, London SE15 6JH" --beds 4 --as buyer --asking 575000
  python engine.py "58 Cronin Street, London SE15 6JH" --beds 4 --as agent --finish high --investment
  python engine.py "58 Cronin Street, London SE15 6JH" --beds 4 --json
"""
import argparse, os, sys, json, statistics
from appraise import (api, money, round_to, postcode_of, txn_link, tuid_of,
                      listing_link, pos_loc, find_subject, pull_sold,
                      candidate_comps, valuation, pull_listings, positioning,
                      apply_market, DATESTR)
from macro import outlook

# ---------------------------------------------------------------- core
def value(address, key, beds=None, baths=1, finish="average",
          investment=False, ptype=None, radius=0.5, maxage=24):
    """The engine. Returns one structured result - the single source of truth
    every audience view reads from. No view ever recomputes a number."""
    subj = find_subject(address, key)
    subj["beds"] = beds or subj["beds_est"]
    subj["baths"] = baths
    subj["investment"] = investment
    pdtype = ptype or ("flat" if ("flat" in subj["type"] or "maison" in subj["type"])
                       else "terraced_house")
    sold = pull_sold(subj, key, pdtype, maxage)
    comps = candidate_comps(sold, subj, radius)
    A = [r for r in comps if r["tier"] == "A"] or comps
    if not A:
        sys.exit("No comparable evidence found - widen --radius or check the address.")
    val = valuation(subj, A, key, finish, pdtype)
    pos = positioning(subj, val, pull_listings(subj, key, pdtype))
    apply_market(val, pos)          # sold evidence is the anchor; the live market is the steer
    return {"subject": subj, "valuation": val, "compsA": A,
            "positioning": pos, "pdtype": pdtype, "finish": finish}

# ---------------------------------------------------------------- shared summary
def nice_addr(addr):
    """Title-case the street, keep the postcode uppercase."""
    import re
    t = addr.title() if addr.isupper() else addr
    pc = postcode_of(addr)
    if pc:
        t = re.sub(re.escape(pc.title()), pc, t)
    return t

def summary(r, audience="agent", asking=None, quoted=None, n=5):
    """The ONE honest summary every surface renders - bot card, Mini App, web link.
    Plain data only (no HTML), so each surface presents it its own way but the
    numbers and the message never drift between them."""
    s, v, pos = r["subject"], r["valuation"], r["positioning"]
    sold_med = round_to(statistics.median([c["price"] for c in r["compsA"]]), 1000)
    rows = sorted(r["compsA"], key=lambda c: (c.get("dist") if c.get("dist") is not None else 9, -c["price"]))[:n]
    evidence = [{"address": c["address"].split(",")[0], "full_address": c["address"], "sqm": c["sqm"],
                 "price": c["price"], "price_str": money(c["price"]), "date": c["date"][:7],
                 "verify": txn_link(c)} for c in rows]
    out = {
        "audience": audience,
        "address": nice_addr(s["address"]),
        "uprn": s.get("uprn"), "lat": s.get("lat"), "lng": s.get("lng"),
        "sqm": s.get("sqm"), "beds": s.get("beds"), "epc": s.get("epc"),
        "investment": s.get("investment", False),
        "last_sold": s.get("last_sold"), "last_sold_date": s.get("last_sold_date"),
        "low": v["low"], "high": v["high"], "central": v["central"], "guide": v["guide"],
        "range_str": f"{money(v['low'])} - {money(v['high'])}",
        "psm": int(v["psmA"]) if v.get("psmA") else None,
        "sold_median": sold_med, "sold_median_str": money(sold_med),
        "evidence": evidence,
        "market": v.get("market"),
        "sold_anchor": v.get("sold_anchor"),
        "sold_anchor_str": money(v["sold_anchor"]) if v.get("sold_anchor") else None,
        "macro": outlook(v["central"], audience),   # forward context, sits beside the figure - never moves it
        # (live macro momentum is attached just below, guarded - it must never break a valuation)
        "verdict": None,
        "positioning": None,
    }
    # live macro momentum (BoE + ONS), attached beside the facts. Best-effort: a slow
    # or down stats API must never break or delay a valuation, so it is fully guarded.
    if out["macro"]:
        try:
            from macro_live import signal as _macro_signal
            sig = _macro_signal()
            if sig:
                out["macro"]["momentum"] = sig
        except Exception:
            pass
    # audience-specific guide framing
    if audience == "buyer":
        out["guide_label"] = "Sensible opening offer"
        out["guide_value_str"] = money(round_to(v["guide"], 1000))
    else:
        out["guide_label"] = "Realistic guide" if audience == "vendor" else "Recommended guide"
        out["guide_value_str"] = f"Offers Over {money(v['guide'])}"
    # the honesty check (only when the user gives the number they were told)
    if quoted and audience == "vendor":
        d = quoted - v["high"]
        out["verdict"] = ({"tone": "warn",
                           "text": f"An agent quoted you {money(quoted)} - that's {money(d)} above the assessed value. "
                                   f"A high quote wins the instruction, not the sale."}
                          if d > 0 else
                          {"tone": "ok", "text": f"{money(quoted)} sits within the assessed range - a fair, defensible number."})
    if asking and audience == "buyer":
        over = asking - v["high"]
        out["verdict"] = ({"tone": "warn",
                           "text": f"Asked at {money(asking)} - about {money(over)} over the assessed value. "
                                   f"That's your negotiating headroom, in writing."}
                          if over > 0 else
                          {"tone": "ok", "text": f"Asked at {money(asking)} - at or below the assessed value."})
    if pos and pos["stuck"]:
        note = ("That's where you have leverage." if audience == "buyer"
                else "Overpricing doesn't win - it waits.")
        out["positioning"] = {
            "stuck": len(pos["stuck"]), "listings": len(pos["band"]),
            "median_ask": pos["median"], "median_ask_str": money(pos["median"]),
            "note": (f"{len(pos['stuck'])} comparable homes priced higher have sat unsold 90+ days "
                     f"(median ask {money(pos['median'])} vs sold ~{money(sold_med)}). {note}")}
    return out

# ---------------------------------------------------------------- shared bits
def _evidence_rows(A, n=5):
    """The n closest comparable SOLD sales - the firmest evidence, with verify links."""
    rows = sorted(A, key=lambda r: (r.get("dist") if r.get("dist") is not None else 9, -r["price"]))[:n]
    out = ["| Comparable | Size | Sold for | When | Verify |", "|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['address'].split(',')[0]} | {r['sqm']} sqm | {money(r['price'])} | "
                   f"{r['date'][:7]} | [record]({txn_link(r)}) |")
    return rows, "\n".join(out)

def _ask_vs_sold(A, pos):
    """The honest gap: what comparable homes ACTUALLY sold for vs what's being ASKED today."""
    sold_med = round_to(statistics.median([r["price"] for r in A]), 1000)
    ask_med = pos["median"] if pos else None
    return sold_med, ask_med

# ---------------------------------------------------------------- vendor view
def vendor_view(r, quoted=None):
    s, v, pos = r["subject"], r["valuation"], r["positioning"]
    rows, ev = _evidence_rows(r["compsA"])
    sold_med, ask_med = _ask_vs_sold(r["compsA"], pos)
    L = [f"# What the data says your home is worth\n",
         f"### {s['address']}\n",
         f"Anchored in {len(r['compsA'])} comparable homes that actually **sold** near you, then "
         f"steered for what the live market is doing now - not an agent's guess. Every figure links to its source.\n",
         "| | |", "|---|---|",
         f"| **What it's worth** | **{money(v['low'])} - {money(v['high'])}** (most likely ~{money(v['central'])}) |",
         f"| **Realistic guide to list at** | **Offers Over {money(v['guide'])}** |"]
    if s.get("last_sold"):
        L.append(f"| You last paid | {money(s['last_sold'])} ({s['last_sold_date']}) |")
    L.append("")
    if quoted:
        diff = quoted - v["high"]
        if diff > 0:
            L.append(f"> **An agent quoted you {money(quoted)}.** The sold evidence supports up to "
                     f"**{money(v['high'])}** - that quote is **{money(diff)} above** what comparable homes "
                     f"have completed at. A high quote wins the instruction; it doesn't win the sale. "
                     f"Homes that over-ask sit, then reduce. See below.\n")
        else:
            L.append(f"> **An agent quoted you {money(quoted)}.** That sits within the evidence-backed range - "
                     f"a fair, defensible number.\n")
    L += ["## The evidence - what homes like yours sold for\n", ev, ""]
    if ask_med and ask_med > sold_med:
        L.append(f"\n**Asking ≠ achieved.** Comparable homes are *listed* at a median **{money(ask_med)}**, "
                 f"but the ones that *sold* completed at a median **{money(sold_med)}**. The difference is the "
                 f"gap between hope and a buyer's signature.\n")
    if pos and pos["stuck"]:
        worst = pos["stuck"][0]
        L.append(f"**The overpricing trap.** {len(pos['stuck'])} of {len(pos['band'])} homes in your price band "
                 f"have sat unsold for 90+ days - the longest {money(worst['price'])}, listed "
                 f"{worst.get('days_on_market')} days. Price to the evidence and you sell; price to ego and you wait.\n")
    # net in pocket
    fee = round(v["central"] * 0.024)
    net = v["central"] - fee
    L += ["## What you'd actually pocket\n", "| On a sale at | Agent fee (2%+VAT) | In your pocket |",
          "|---|---|---|"]
    if s.get("investment"):
        L[-2] = "| On a sale at | Fee (2%+VAT) | Indicative CGT | In your pocket |"
        L[-1] = "|---|---|---|---|"
        gain = max(0, v["central"] - (s.get("last_sold") or 0) - fee - 3000)
        cgt = round(gain * 0.24)
        L.append(f"| {money(v['central'])} | {money(fee)} | {money(cgt)} | {money(net - cgt)} |")
        L.append("\n*Indicative CGT at 24% after the £3,000 allowance; refurbishment & purchase costs are "
                 "deductible and not included. Not tax advice.*")
    else:
        L.append(f"| {money(v['central'])} | {money(fee)} | {money(net)} |")
    L.append(f"\n*Comparative market appraisal: HM Land Registry sold evidence via PropertyData, steered "
             f"for live market conditions, {DATESTR}. Not a RICS Red Book valuation.*")
    return "\n".join(L)

# ---------------------------------------------------------------- buyer view
def buyer_view(r, asking=None):
    s, v, pos = r["subject"], r["valuation"], r["positioning"]
    rows, ev = _evidence_rows(r["compsA"])
    sold_med, ask_med = _ask_vs_sold(r["compsA"], pos)
    L = [f"# What the data says this home is worth\n",
         f"### {s['address']}\n",
         f"Before you offer: {len(r['compsA'])} comparable homes nearby actually **sold** at these prices, and "
         f"this is what today's market supports. An asking price is what a seller hopes for. Check every link yourself.\n",
         "| | |", "|---|---|",
         f"| **Fair value** | **{money(v['low'])} - {money(v['high'])}** (most likely ~{money(v['central'])}) |",
         f"| **A sensible opening offer** | **{money(round_to(v['guide'], 1000))}** |"]
    L.append("")
    if asking:
        over = asking - v["high"]
        if over > 0:
            L.append(f"> **It's being asked at {money(asking)}.** Comparable sold evidence tops out around "
                     f"**{money(v['high'])}** - paying the asking price means paying about **{money(over)} over** "
                     f"the evidence. That's your negotiating headroom, in writing.\n")
        else:
            head = v["central"] - asking
            L.append(f"> **It's being asked at {money(asking)}.** That's at or below fair value - if the condition "
                     f"matches the comparables, it's keenly priced" +
                     (f" (roughly {money(head)} under the likely value)." if head > 0 else ".") + "\n")
    L += ["## The evidence - what comparable homes sold for\n", ev, ""]
    if ask_med and ask_med > sold_med:
        L.append(f"\n**Don't anchor to the asking price.** Homes here are *listed* at a median **{money(ask_med)}** "
                 f"but *sell* at a median **{money(sold_med)}** - a {money(ask_med - sold_med)} gap. Sellers ask high; "
                 f"buyers who know the sold prices pay right.\n")
    if pos and pos["stuck"]:
        L.append(f"**Where you have leverage.** {len(pos['stuck'])} comparable homes have been on the market 90+ days "
                 f"without selling - overpriced stock that hasn't moved. A long listing is a buyer's friend: the "
                 f"seller is closer to accepting a realistic offer than they were on day one.\n")
    L.append(f"\n*HM Land Registry sold evidence via PropertyData, steered for live market conditions, {DATESTR}. "
             "Independent of the seller and their agent.*")
    return "\n".join(L)

# ---------------------------------------------------------------- agent view
def agent_view(r, with_route=True):
    s, v, pos = r["subject"], r["valuation"], r["positioning"]
    rows, ev = _evidence_rows(r["compsA"], n=8)
    sold_med, ask_med = _ask_vs_sold(r["compsA"], pos)
    L = [f"# Instant appraisal - {s['address']}\n",
         f"*{DATESTR} · {s['sqm']} sqm · {s.get('beds')} bed · EPC {s.get('epc')} · "
         f"{'investment (CGT)' if s.get('investment') else 'residence'}*\n",
         "| | |", "|---|---|",
         f"| Assessed range | **{money(v['low'])} - {money(v['high'])}** (central {money(v['central'])}) |",
         f"| Recommended guide | **Offers Over {money(v['guide'])}** |",
         f"| £/sqm (Tier A median) | £{v['psmA']:,} → cross-check {money(v['crosscheck']) if v['crosscheck'] else 'n/a'} |"]
    if s.get("last_sold"):
        L.append(f"| Last sold | {money(s['last_sold'])} ({s['last_sold_date']}) |")
    L += ["", "## Comparable evidence (sold)\n", ev, ""]
    # the listing-pitch weapon: factual competitive positioning
    if pos:
        L.append("## Competitive positioning - the listing-pitch weapon\n")
        L.append(f"Live band {money(pos['lo_p'])} - {money(pos['hi_p'])}: **{len(pos['band'])}** comparable listings, "
                 f"median asking **{money(pos['median'])}**, average **{pos['mean_dom']} days** on market.\n")
        if pos["stuck"]:
            L.append(f"**{len(pos['stuck'])} stuck 90+ days** - the over-asking competition, every figure verifiable:")
            L.append("\n| Asking | Days listed | Where | Listing |\n|---|---|---|---|")
            for x in pos["stuck"][:5]:
                pname, plink = listing_link(x.get("url"))
                cell = f"[{pname}]({plink})" if plink else " - "
                L.append(f"| {money(x['price'])} | {x.get('days_on_market')} | {pos_loc(x['address'])} | {cell} |")
            L.append("")
        L.append(f"Pitch: *\"{len(pos['stuck'])} homes in this band have sat unsold for months at these prices. "
                 f"Priced to the sold evidence at Offers Over {money(v['guide'])}, yours doesn't join them - it draws "
                 f"the offers they're waiting for.\"* Every claim links to the live portal page.\n")
    # door-knock route (Google Routes - live)
    if with_route:
        L += _route_block(s, rows)
    L.append(f"\n*HM Land Registry sold evidence via PropertyData, steered for live market conditions. "
             f"Run the full executive PDF with appraise.py.*")
    return "\n".join(L)

def _route_block(subj, comp_rows):
    """Door-knock canvassing route through the subject + nearby comparable addresses.
    Uses the live Google Routes API (optimised order). Degrades cleanly if unavailable."""
    try:
        import maps_tools
    except Exception:
        return []
    stops = [subj["address"]] + [c["address"] for c in comp_rows[:6]]
    seen, uniq = set(), []
    for a in stops:
        k = a.split(",")[0].lower()
        if k not in seen:
            seen.add(k); uniq.append(a)
    if len(uniq) < 2:
        return []
    res = maps_tools.route(uniq, optimize=True)
    if not res.get("ok"):
        return ["## Door-knock route\n", f"*Route unavailable: {res.get('reason')}*\n"]
    mins = int(res["duration"].rstrip("s") or 0) // 60
    L = ["## Door-knock route - optimised canvassing run\n",
         f"{len(res['ordered_stops'])} doors, {res['km']} km, ~{mins} min on foot/by car, shortest order:\n"]
    for i, stop in enumerate(res["ordered_stops"], 1):
        L.append(f"{i}. {pos_loc(stop)}")
    L.append("\n*Knock the comparable street first - you've just valued it; you're the local expert at the door.*\n")
    return L

# ---------------------------------------------------------------- CLI
def main():
    try: sys.stdout.reconfigure(encoding="utf-8")  # pound signs and arrows on a Windows console
    except Exception: pass
    ap = argparse.ArgumentParser(description="Instant honest valuation - one engine, three audiences.")
    ap.add_argument("address")
    ap.add_argument("--key", default=os.environ.get("PROPERTYDATA_KEY"))
    ap.add_argument("--beds", type=int)
    ap.add_argument("--baths", type=int, default=1)
    ap.add_argument("--type", default=None)
    ap.add_argument("--finish", default="average", choices=["average", "high", "very_high"])
    ap.add_argument("--investment", action="store_true")
    ap.add_argument("--radius", type=float, default=0.5)
    ap.add_argument("--maxage", type=int, default=24)
    ap.add_argument("--as", dest="audience", default="agent", choices=["agent", "vendor", "buyer"])
    ap.add_argument("--quoted", type=int, help="(vendor) price an agent quoted - checked against evidence")
    ap.add_argument("--asking", type=int, help="(buyer) the asking price - checked for overpay")
    ap.add_argument("--no-route", action="store_true", help="(agent) skip the door-knock route")
    ap.add_argument("--json", action="store_true", help="emit the raw engine result (the API shape)")
    args = ap.parse_args()
    if not args.key:  # fall back to .env (server-side secret store)
        try:
            from maps_tools import _load_env
            _load_env(); args.key = os.environ.get("PROPERTYDATA_KEY")
        except Exception:
            pass
    if not args.key:
        sys.exit("Set PROPERTYDATA_KEY env var, pass --key, or add it to .env")

    r = value(args.address, args.key, beds=args.beds, baths=args.baths, finish=args.finish,
              investment=args.investment, ptype=args.type, radius=args.radius, maxage=args.maxage)

    if args.json:
        out = {"subject": {k: r["subject"].get(k) for k in
                           ("address", "uprn", "lat", "lng", "sqm", "beds", "type", "epc",
                            "tax", "last_sold", "last_sold_date", "investment")},
               "valuation": {k: r["valuation"].get(k) for k in
                             ("low", "central", "high", "guide", "psmA", "crosscheck", "avm")},
               "evidence": [{"address": c["address"], "sqm": c["sqm"], "price": c["price"],
                             "date": c["date"], "psm": c.get("psm"), "verify": txn_link(c)}
                            for c in sorted(r["compsA"], key=lambda x: -x["price"])],
               "positioning": ({"band_lo": r["positioning"]["lo_p"], "band_hi": r["positioning"]["hi_p"],
                                "median_ask": r["positioning"]["median"],
                                "mean_days_on_market": r["positioning"]["mean_dom"],
                                "stuck_90d": len(r["positioning"]["stuck"]),
                                "listings": len(r["positioning"]["band"])} if r["positioning"] else None)}
        print(json.dumps(out, indent=2, default=str))
        return

    if args.audience == "vendor":
        print(vendor_view(r, quoted=args.quoted))
    elif args.audience == "buyer":
        print(buyer_view(r, asking=args.asking))
    else:
        print(agent_view(r, with_route=not args.no_route))

if __name__ == "__main__":
    main()
