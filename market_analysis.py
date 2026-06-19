#!/usr/bin/env python3
"""market_analysis.py - the Honestly general market read for an area.

One aggregator that combines the market-CONTEXT layers - UK property-subreddit sentiment
(via the Hit MCP seam), mortgage / Bank-Rate context, the UK House Price Index, local
demand, and the valuation's own live-listing dynamics - into one structured, sourced,
Honestly-branded record, then caches it.

Honesty contract (identical to area_context.py and the rest of the system):
  * Everything here sits BESIDE the figure as sourced context. NOTHING in this module is an
    input to engine.value(); it never moves a valuation.
  * Every line restates only numbers that are present in a source payload - no figure is
    invented to make the read flow.
  * Reddit is cited as social-media sentiment, never as evidence of value.
  * The company boundary holds: Reddit is reached only through reddit_intel (which speaks the
    Hit MCP protocol). The output carries NO Hit branding - it is Honestly's read.
  * Best-effort: every underlying source can fail; a dead source omits its block and the
    aggregator still returns whatever succeeded. It never raises into the request path, and
    it is produced OFF the request path (scheduled / first-touch), so it never delays a
    valuation.

Surface:
  gather(district, *, postcode=None, region=None, price=None, positioning=None,
         audience="buyer", persist=True) -> {
      "ok": bool,                 # True if at least one source contributed a line
      "district": str,            # e.g. "SE15"
      "audience": str,
      "sentiment": str | None,    # social sentiment read, for context only
      "blocks": {reddit, macro, hpi, demand, positioning},  # raw source payloads
      "lines": [ {text, source, category} ],                # the synthesised, sourced read
      "fetched_at": float,
  }
  brief(rec) -> str               # a plain-text block for a card / report / panel

CLI:
  python market_analysis.py SE15 --postcode "SE15 5DQ" --region london --price 480000
  python market_analysis.py selftest        # offline degradation check (never raises)
"""
import sys
import time

# Every dependency is optional and best-effort; a missing/broken one drops its block.
try:
    import reddit_intel
except Exception:                       # pragma: no cover - import guard
    reddit_intel = None
try:
    import macro
except Exception:                       # pragma: no cover
    macro = None
try:
    import macro_live
except Exception:                       # pragma: no cover
    macro_live = None
try:
    import land_registry
except Exception:                       # pragma: no cover
    land_registry = None
try:
    import demand
except Exception:                       # pragma: no cover
    demand = None
try:
    import store
except Exception:                       # pragma: no cover
    store = None


def _line(text, source, category):
    """A single sourced read. text is the plain sentence; source names the provider so the
    References list and the panel can attribute it; category groups it in the panel."""
    return {"text": text.strip(), "source": source, "category": category}


# --------------------------------------------------------------- source: Reddit sentiment
def _reddit_block(district, postcode, audience):
    """Social-media sentiment for the area. Context only - never a value input. Cited as
    'UK property subreddits', not Hit (the company boundary)."""
    if reddit_intel is None:
        return None, []
    try:
        intel = reddit_intel.for_area(district, audience=audience, postcode=postcode or "")
    except Exception:
        return None, []
    if not intel or not intel.get("threads"):
        return None, []
    lines = []
    sent = intel.get("sentiment") or "neutral"
    n = intel.get("signal_count") or len(intel.get("threads") or [])
    themes = [t for t in (intel.get("themes") or []) if t]
    theme_tail = f" Recurring themes: {', '.join(themes[:4])}." if themes else ""
    lines.append(_line(
        f"Social sentiment in UK property subreddits reads {sent} across {n} recent "
        f"discussion(s) touching this area.{theme_tail} This is community chatter for "
        f"context, not evidence of value.",
        "UK property subreddits (social sentiment)", "sentiment"))
    return intel, lines


# --------------------------------------------------------------- source: macro / mortgage
def _macro_block(price):
    """Bank Rate + stamp-duty context (human-maintained, self-suppresses when stale) plus
    live BoE/ONS momentum. Beside the figure - it does not move it."""
    block = {}
    lines = []
    if macro is not None:
        try:
            out = macro.outlook(price=price, audience="buyer")
        except Exception:
            out = None
        if out and not out.get("stale"):
            block["outlook"] = out
            for ln in (out.get("lines") or [])[:3]:
                if ln:
                    lines.append(_line(ln, "Bank of England (Bank Rate) and HMRC (SDLT)",
                                       "macro"))
    if macro_live is not None:
        try:
            sig = macro_live.signal()
        except Exception:
            sig = None
        if sig:
            block["live"] = sig
            for ln in (sig.get("lines") or [])[:3]:
                if ln:
                    lines.append(_line(ln, "Bank of England and ONS (live momentum)",
                                       "macro"))
    return (block or None), lines


# --------------------------------------------------------------- source: UK House Price Index
def _hpi_block(region):
    """The UK HPI series for the region: average price and annual change. Sourced context;
    HPI never moves the figure."""
    if land_registry is None or not region:
        return None, []
    try:
        h = land_registry.hpi_region(region)
    except Exception:
        return None, []
    if not h or not h.get("ok"):
        return None, []
    ac = h.get("annual_change_pct")
    avg = h.get("average_price")
    bits = []
    if avg is not None:
        bits.append(f"the average {h['region'].replace('-', ' ')} home stood at "
                    f"£{int(round(avg)):,}")
    if ac is not None:
        dir_word = "up" if ac >= 0 else "down"
        bits.append(f"{dir_word} {abs(ac):.1f}% year on year")
    if not bits:
        return h, []
    month = h.get("month") or ""
    line = (f"On the UK House Price Index ({month}), {', '.join(bits)}. The HPI is a "
            f"trend backdrop reported beside the sold evidence - it never moves the figure.")
    return h, [_line(line, "UK House Price Index (HM Land Registry, OGL)", "trend")]


# --------------------------------------------------------------- source: local demand
def _demand_block(postcode, audience):
    """Relative transaction liquidity for the area, from official counts. Context only."""
    if demand is None or not postcode:
        return None, []
    try:
        d = demand.for_postcode(postcode, audience=audience)
    except Exception:
        return None, []
    if not d or not d.get("ok"):
        return None, []
    note = d.get("note") or demand.brief(d)
    if not note:
        return d, []
    return d, [_line(note, "HM Land Registry Price Paid Data (transaction counts)",
                     "demand")]


# --------------------------------------------------------------- source: live positioning
def _positioning_block(pos):
    """The valuation's own live-listing dynamics, passed in (never re-fetched here): days on
    market, share under offer, share stuck 90+ days. Restated, not recomputed."""
    if not pos or not isinstance(pos, dict):
        return None, []
    lines = []
    dom = pos.get("mean_dom") or pos.get("avg_dom") or pos.get("days_on_market")
    under = pos.get("under_offer_share_pct") or pos.get("under_offer_pct")
    stuck = pos.get("stuck_share_pct") or pos.get("stuck_pct")
    bits = []
    if dom is not None:
        bits.append(f"listings here sit a median {int(round(float(dom)))} days on the market")
    if under is not None:
        bits.append(f"{under}% are under offer")
    if stuck is not None:
        bits.append(f"{stuck}% have been listed 90+ days")
    if not bits:
        return pos, []
    lines.append(_line(
        "Live positioning: " + "; ".join(bits) + ". Asking-side dynamics, reported beside "
        "the sold evidence - not blended into it.",
        "Live listings (PropertyData)", "positioning"))
    return pos, lines


# --------------------------------------------------------------- the aggregator
def gather(district, *, postcode=None, region=None, price=None, positioning=None,
           audience="buyer", persist=True):
    """Build the Honestly market read for `district`. Best-effort: collects whichever sources
    succeed, never raises. Persists one categorised, provenance-stamped record when a store is
    available and persist=True."""
    district = (district or "").strip().upper()
    blocks = {}
    lines = []
    sentiment = None

    reddit, rl = _reddit_block(district, postcode, audience)
    if reddit is not None:
        blocks["reddit"] = reddit
        sentiment = reddit.get("sentiment")
    lines += rl

    mac, ml = _macro_block(price)
    if mac is not None:
        blocks["macro"] = mac
    lines += ml

    hpi, hl = _hpi_block(region)
    if hpi is not None:
        blocks["hpi"] = hpi
    lines += hl

    dem, dl = _demand_block(postcode, audience)
    if dem is not None:
        blocks["demand"] = dem
    lines += dl

    pos, pl = _positioning_block(positioning)
    if pos is not None:
        blocks["positioning"] = pos
    lines += pl

    rec = {
        "ok": bool(lines),
        "district": district,
        "audience": audience,
        "sentiment": sentiment,
        "blocks": blocks,
        "lines": lines,
        "fetched_at": time.time(),
    }

    if persist and store is not None and lines:
        try:
            store.record_market_analysis(
                district, "market_read",
                source="market_analysis.gather",
                query={"postcode": postcode, "region": region, "price": price,
                       "audience": audience},
                payload=blocks, lines=[ln["text"] for ln in lines],
                sentiment=sentiment, ttl_hours=24)
        except Exception:
            pass                                # persistence is best-effort, never fatal
    return rec


def brief(rec):
    """A plain-text market read for a bot card / report / HTML panel, or '' if empty."""
    if not rec or not rec.get("ok"):
        return ""
    out = ["General market analysis (context, never a valuation input):"]
    for ln in rec.get("lines", []):
        out.append(f"- {ln['text']} [{ln['source']}]")
    return "\n".join(out)


# --------------------------------------------------------------- CLI / selftest
def _selftest():
    """Degradation check: with NO live sources reachable, gather() must NOT raise and must
    return a well-formed {ok: False} record. We force the offline path deterministically by
    nulling every source module for the duration of the check, so the result does not depend
    on whether the network/keys happen to be present on this machine."""
    global reddit_intel, macro, macro_live, land_registry, demand, store
    saved = (reddit_intel, macro, macro_live, land_registry, demand, store)
    try:
        reddit_intel = macro = macro_live = land_registry = demand = store = None
        # 1. every source dead -> never raises, ok is False, lines is empty
        rec = gather("ZZ99", postcode="ZZ99 9ZZ", region="london", price=480000,
                     audience="buyer", persist=True)   # persist=True must be a no-op (store None)
        assert isinstance(rec, dict), "gather did not return a dict"
        assert rec["district"] == "ZZ99"
        assert isinstance(rec["lines"], list) and rec["lines"] == [], \
            "lines should be empty when every source is down"
        assert rec["ok"] is False, "ok must be False when no source contributed"
        assert rec["blocks"] == {}, "no blocks should survive a full outage"
        assert brief(rec) == "", "brief() must be empty for an empty read"
        # 2. positioning is pure data - it must synthesise with every source still dead
        rec2 = gather("SE15", positioning={"mean_dom": 77, "under_offer_share_pct": 21,
                                           "stuck_share_pct": 13}, persist=False)
        assert any(l["category"] == "positioning" for l in rec2["lines"]), \
            "positioning block did not render from pure data"
        assert rec2["ok"] is True
        # 3. no figure appears that was not handed in (77 / 21 / 13 only)
        pos_text = next(l["text"] for l in rec2["lines"] if l["category"] == "positioning")
        assert "77" in pos_text and "21%" in pos_text and "13%" in pos_text
        # 4. no Hit branding leaks into the output (company boundary holds)
        blob = brief(rec2).lower()
        for banned in ("hit", "hitman", "_hit_sdk", "call_tool_sync"):
            assert banned not in blob, f"company-boundary leak: '{banned}' in output"
    finally:
        reddit_intel, macro, macro_live, land_registry, demand, store = saved
    print("market_analysis selftest: OK (offline degradation verified)")
    print(brief(rec2))
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        return _selftest()
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 0
    district = args[0]
    kw = {}
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--postcode" and i + 1 < len(args):
            kw["postcode"] = args[i + 1]; i += 2
        elif a == "--region" and i + 1 < len(args):
            kw["region"] = args[i + 1]; i += 2
        elif a == "--price" and i + 1 < len(args):
            kw["price"] = int(args[i + 1]); i += 2
        else:
            i += 1
    rec = gather(district, persist=False, **kw)
    print(brief(rec) or f"No market read available for {district} (all sources quiet).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
