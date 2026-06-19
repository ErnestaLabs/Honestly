#!/usr/bin/env python3
"""demand.py - area demand from official transaction velocity x sentiment.

Assembles two signals the field keeps separate:
  1. HARD count - how many homes ACTUALLY changed hands in the subject postcode and
     its nearest neighbours over a fixed window, straight from HM Land Registry Price
     Paid Data (land_registry.ppd_postcode). Subject vs nearby gives a RELATIVE
     liquidity read: is this pocket busier, in line, or quieter than the streets
     around it.
  2. SOFT chatter - the qualitative read from the `hit` MCP via reddit_intel.for_area,
     shown beside the count so the two can agree or visibly disagree.

This is a demand READ that sits BESIDE the valuation figure, with its sources. It is
NOT a price input - it never feeds valuation(). It may only ever influence the
headline through the existing capped+disclosed apply_market steer, and only if
disclosed line-by-line. Default is context-only.

Every external call is guarded; the whole thing degrades to {'ok': False, 'reason'}
or a partial read, and NEVER raises - a slow registry or a down MCP must not break a
valuation. Heavy (several SPARQL calls): belongs off the request path / cached, not
on the bot card hot path.

CLI:
  python demand.py "SE15 6JH"
  python demand.py "SE15 6JH" 24 6
  python demand.py selftest
"""
import sys, json, statistics, datetime

import geo
import land_registry as lr
try:
    import reddit_intel
except Exception:                                # reddit_intel pulls the MCP shim; optional
    reddit_intel = None


def _cutoff(window_months):
    """ISO date `window_months` ago. ISO strings compare lexicographically, so a
    plain >= on 'YYYY-MM-DD' is a correct date filter."""
    today = datetime.date.today()
    y, m = today.year, today.month - window_months
    while m <= 0:
        m += 12; y -= 1
    return f"{y:04d}-{m:02d}-{today.day:02d}"


def _count_window(postcode, cutoff, limit=100):
    """Recorded sales for one postcode on/after the cutoff. (count, ok)."""
    r = lr.ppd_postcode(postcode, limit=limit, timeout=20, use_cache=True)
    if not r.get("ok"):
        return 0, False
    n = sum(1 for s in r.get("sales", []) if (s.get("date") or "") >= cutoff)
    return n, True


def _label(subj_count, nbr_counts):
    """Relative liquidity label from the subject count vs the neighbour distribution.
    Returns (label, ratio_or_None). Honest about thin samples upstream."""
    nbrs = [c for c in nbr_counts if c is not None]
    if not nbrs:
        return ("no comparable neighbours", None)
    nmed = statistics.median(nbrs)
    if nmed == 0:
        return (("active where the cluster is quiet" if subj_count > 0
                 else "quiet, like the cluster"), None)
    ratio = subj_count / nmed
    if ratio >= 1.5:
        return ("busier than nearby streets", round(ratio, 2))
    if ratio <= 0.67:
        return ("quieter than nearby streets", round(ratio, 2))
    return ("in line with nearby streets", round(ratio, 2))


def _sector_of(postcode):
    """Postcode SECTOR: outward + space + first inward digit, e.g. 'SE15 6JH' -> 'SE15 6'.
    None if the postcode has no inward part to take a sector from."""
    parts = (postcode or "").upper().split()
    if len(parts) == 2 and parts[1]:
        return f"{parts[0]} {parts[1][0]}"
    return None


def for_postcode(postcode, window_months=24, ring=6, audience="buyer"):
    """Area demand read for a postcode. One wide Postcodes.io ring serves two reads:
    a RELATIVE liquidity label (subject vs its nearest `ring` postcodes) and a meaningful
    SECTOR volume (every recorded sale across the postcode sector, e.g. SE15 6, in one
    indexed HMLR count) - because unit-postcode counts alone are far too sparse to read
    demand from. Attaches the qualitative sentiment cross-check. Never raises."""
    # widen the ring enough to enumerate the whole sector, not just the closest handful;
    # the relative read still uses only the nearest `ring`, so its behaviour is unchanged.
    g = geo.nearest(postcode, limit=100, radius=1000)
    if not g.get("ok"):
        g = geo.nearest(postcode, limit=ring + 1)        # fall back to the tight ring
    if not g.get("ok"):
        return {"ok": False, "reason": f"geo: {g.get('reason')}"}
    neighbours = g["neighbours"]
    subj_pc = neighbours[0]["postcode"]
    cutoff = _cutoff(window_months)

    subj_count, subj_ok = _count_window(subj_pc, cutoff)
    if not subj_ok:
        return {"ok": False, "reason": "registry unavailable for subject postcode"}

    nbr = []                                     # the ring, excluding the subject itself
    for n in neighbours[1:ring + 1]:
        c, ok = _count_window(n["postcode"], cutoff)
        if ok:
            nbr.append({"postcode": n["postcode"], "dist_m": n.get("dist_m"), "count": c})

    nbr_counts = [x["count"] for x in nbr]
    label, ratio = _label(subj_count, nbr_counts)
    area_total = subj_count + sum(nbr_counts)

    # SECTOR volume: count every sale across the postcode sector in one indexed query.
    # This is the meaningful denominator the sparse unit counts can't give. Best-effort -
    # a down registry just omits the sector block and we fall back to the ring read.
    sector = None
    sector_prefix = _sector_of(subj_pc)
    if sector_prefix:
        members = [n["postcode"] for n in neighbours
                   if (n.get("postcode") or "").upper().startswith(sector_prefix)]
        if members:
            try:
                sc = lr.ppd_count(members, since=cutoff, use_cache=True)
            except Exception:
                sc = {"ok": False}               # a raising count never breaks the read
            if sc.get("ok"):
                sector = {"sector": sector_prefix, "count": sc["count"],
                          "postcodes_sampled": sc["n_postcodes"]}

    # Confidence prefers the sector volume (a real sample); falls back to the thin ring
    # total only when the sector count is unavailable. Honest about thin samples either way.
    if sector:
        sc_n = sector["count"]
        confidence = "low" if sc_n < 15 else ("medium" if sc_n < 40 else "good")
    else:
        confidence = "low" if area_total < 10 else ("medium" if area_total < 30 else "good")

    out = {
        "ok": True, "postcode": subj_pc,
        "window_months": window_months, "since": cutoff,
        "subject_count": subj_count,
        "neighbour_counts": nbr,
        "neighbour_median": (statistics.median(nbr_counts) if nbr_counts else None),
        "area_total": area_total,
        "sector": sector,
        "relative": label, "ratio": ratio, "confidence": confidence,
        "source": "HM Land Registry Price Paid Data (counts) via Postcodes.io ring + sector",
    }

    # qualitative cross-check - shown beside the count, never blended into it
    if reddit_intel is not None:
        try:
            area = (g.get("postcode") or subj_pc).split()[0]   # outcode, e.g. SE15
            intel = reddit_intel.for_area(area, audience=audience, postcode=subj_pc)
            if intel:
                out["sentiment"] = {
                    "read": intel.get("sentiment"),
                    "signal_count": intel.get("signal_count"),
                    "source": "Reddit market chatter via hit MCP",
                }
        except Exception:
            pass

    nbr_n = len(nbr)
    sector_lead = ""
    if sector:
        sector_lead = (f"{sector['count']} recorded sales across the {sector['sector']} "
                       f"sector since {cutoff[:7]} ({sector['postcodes_sampled']} postcodes). ")
    out["note"] = (
        sector_lead
        + f"{subj_count} in {subj_pc} itself; {label}"
        + (f" (about {ratio}x the {nbr_n}-postcode neighbour median)." if ratio else ".")
        + f" Demand read, beside the figure - it does not move the valuation."
        + (" Thin sample, treat as directional." if confidence == "low" else "")
    )
    return out


def brief(d):
    """One-line text for a card/report, or '' if there is nothing solid to show."""
    if not d or not d.get("ok"):
        return ""
    s = d.get("sentiment") or {}
    tail = f" Chatter: {s['read']}." if s.get("read") else ""
    sec = d.get("sector") or {}
    vol = (f"{sec['count']} sales across {sec['sector']}" if sec
           else f"{d['subject_count']} sales")
    return f"Area demand: {d['relative']} ({vol} since {d['since'][:7]}, "\
           f"confidence {d['confidence']}).{tail}"


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    if sys.argv[1] == "selftest":
        d = for_postcode("SE15 6JH")
        print("demand SE15 6JH:", "ok" if d.get("ok") else d.get("reason"))
        if d.get("ok"):
            print("  ", brief(d))
        return
    pc = sys.argv[1]
    win = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    ring = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    print(json.dumps(for_postcode(pc, win, ring), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
