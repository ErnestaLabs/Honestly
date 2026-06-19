#!/usr/bin/env python3
"""market_district.py - real district-level transaction intelligence for the daily blog.

Given a city (from cities.py) and one of its postcode districts (an outcode, e.g.
"SE15"), this gathers that district's OWN real data from the live providers and returns
one structured model. The blog template renders that model; only the data varies, so two
districts never share numbers. This is the cardinal rule made mechanical: every figure on
a published page is pulled live for that exact district - never a template number reused
from another area (the Alaska lesson is law here).

Sources, each best-effort and grounded in existing working code:
  * PropertyData `sold-prices` (+ `sold-prices-per-sqf`)  -> volume, median, £/sqm,
    by-type and by-bed breakdown, recency windows, price spread, an evidence sample.
    HM Land Registry Price Paid Data under the bonnet (OGL).
  * PropertyData `prices` (live listings)                 -> asking median, days on
    market, stuck stock (90+ days), under-offer share, available stock.
  * UK House Price Index (HM Land Registry, OGL)          -> the city's regional index:
    average price, annual and monthly change. Context beside the figures, never an input.
  * HM Land Registry Price Paid (direct, OGL)             -> an independent sold check.
  * area_context.gather on the district centroid          -> location, amenities, safety,
    environment, planning - the free spine, beside the numbers.

Honesty posture (ABSOLUTE): nothing here values a property. There is no subject and no
valuation. Every block degrades to an honest "not available" state when its source is
down; nothing is invented to fill a gap. The HPI and area context sit beside the
transaction facts as sourced context, never blended into them.

CLI:
  python market_district.py SE15            # gather + print a compact summary
  python market_district.py SE15 --json     # full JSON model
"""
import os, sys, json, random, statistics, datetime

import cities
import geo

# Load .env into os.environ so PROPERTYDATA_KEY is available whether we are imported by
# the pipeline or run from the CLI - same loader the rest of the app uses, best-effort.
try:
    import maps_tools
    maps_tools._load_env()
except Exception:                                   # pragma: no cover - best effort
    pass

try:
    import appraise
except Exception:                                   # pragma: no cover - import guard
    appraise = None
try:
    import land_registry
except Exception:                                   # pragma: no cover
    land_registry = None


def _tx_uri(tuid):
    """Official HM Land Registry per-transaction verification URL from a Price Paid
    transaction id. Single source of truth is land_registry.transaction_uri; this thin
    wrapper keeps building the link even when land_registry failed to import, so a sold
    row is never shown as evidence without the link to confirm it on the register."""
    if land_registry is not None:
        return land_registry.transaction_uri(tuid)
    t = (tuid or "").strip().strip("{}").strip()
    return ("http://landregistry.data.gov.uk/data/ppi/transaction/%s/current" % t) if t else None
try:
    import demand as demand_mod
except Exception:                                   # pragma: no cover
    demand_mod = None
try:
    import area_context
except Exception:                                   # pragma: no cover
    area_context = None


# PropertyData's sold-prices endpoint is keyed by property type, so to read a whole
# district we query each residential type and aggregate. These are the four PD residential
# type slugs; the API label we show the reader is the second element.
TYPES = [
    ("flat", "Flats"),
    ("terraced_house", "Terraced houses"),
    ("semi_detached_house", "Semi-detached houses"),
    ("detached_house", "Detached houses"),
]


def _key():
    return os.environ.get("PROPERTYDATA_KEY")


def _to_date(s):
    """Parse a 'YYYY-MM-DD' (or longer) date string to a date, or None."""
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


# ------------------------------------------------------------------ sold prices
def _is_quota_error(exc):
    """True when a PropertyData call failed because the PAID monthly credit plan is exhausted
    (HTTP 403, code X04 'Monthly plan limit exceeded'). This is categorically different from a
    transient outage: retrying does NOT help until the plan resets, and it is emphatically NOT
    evidence that a district has no sales. The pipeline must report it honestly as a paid-feed
    cap, never as 'provider down, will retry' or 'no data'. Any other 403 (e.g. a bad key) is
    also a hard wall, not a retryable blip, so we treat a bare 403 as a quota/auth cap too."""
    if getattr(exc, "code", None) != 403:
        return False
    try:
        body = exc.read().decode("utf-8", "replace")
        return ("x04" in body.lower()) or ("plan limit" in body.lower()) or True
    except Exception:
        return True


def _pull_sold_type(outcode, pdtype, key, max_age):
    """Sold rows for one outcode + type at one time window, with £/sqm merged in where the
    per-sqf dataset exists. Returns (rows, status):
      status == "ok"    -> the call succeeded; rows may be a genuine empty list (no sales of
                           this type in this window) - that IS real information.
      status == "quota" -> the PAID PropertyData plan is out of monthly credits (403 X04). A
                           paid cap, not absence; the caller surfaces it honestly so a district
                           is never logged as 'no sales' because the wallet ran dry.
      status == "error" -> the provider call failed (a 404/422/timeout). This is NOT proof of
                           absence; PropertyData 404s a window that happens to hold no rows, so
                           the caller must widen the window before concluding the district has
                           no history. A fetch artifact is never recorded as 'no sales here'."""
    if appraise is None:
        return [], "error"
    try:
        sp = appraise.api("sold-prices", key, postcode=outcode, type=pdtype,
                          max_age=max_age, points=100)["data"]["raw_data"]
    except Exception as e:
        return [], ("quota" if _is_quota_error(e) else "error")
    if not sp:
        return [], "ok"                              # genuine empty result for this window
    try:
        psf = {r["url"]: r for r in appraise.api(
            "sold-prices-per-sqf", key, postcode=outcode, type=pdtype,
            max_age=max_age, points=100)["data"]["raw_data"]}
    except Exception:
        psf = {}
    for r in sp:
        m = psf.get(r.get("url"))
        r["sqm"] = round(m["sqf"] / 10.7639) if m and m.get("sqf") else None
        r["pdtype"] = pdtype
    return sp, "ok"


# When the requested window comes back empty, widen to these before ever concluding the
# district has no sales. Central, commercial-heavy outcodes (EH2, M2, B2) have sparse RECENT
# residential transactions, so a 24-month query 404s even though years 3-5 are full of sales.
# This is the rule that favours success: widen until real rows appear; only a genuine empty
# result at the widest window is true absence. (The Scotland data still comes through here -
# PropertyData carries Registers of Scotland sales that the free HMLR endpoint does not.)
_SOLD_WINDOWS = (48, 120)


def _sold_block(outcode, key, max_age):
    """Aggregate the whole district's sold picture across all residential types, favouring
    success. Widens the time window (requested -> 48 -> 120 months) until real rows appear,
    and labels the page with the window that actually produced them. A provider error at a
    narrow window is never recorded as 'no sales in this district' - we widen and retry."""
    windows = []
    for w in (int(max_age),) + _SOLD_WINDOWS:
        if w not in windows:
            windows.append(w)
    windows.sort()

    rows, by_type, used_window, any_error, quota = [], [], int(max_age), False, False
    for w in windows:
        rows, by_type, any_error = [], [], False
        for pdtype, label in TYPES:
            t_rows, status = _pull_sold_type(outcode, pdtype, key, w)
            if status in ("error", "quota"):
                any_error = True
                if status == "quota":
                    quota = True
            if not t_rows:
                by_type.append({"type": pdtype, "label": label, "n": 0,
                                "median": None, "psm_median": None})
                continue
            prices = [r["price"] for r in t_rows if r.get("price")]
            psms = [round(r["price"] / r["sqm"]) for r in t_rows
                    if r.get("price") and r.get("sqm")]
            by_type.append({
                "type": pdtype, "label": label, "n": len(t_rows),
                "median": _median(prices), "psm_median": _median(psms),
            })
            rows.extend(t_rows)
        used_window = w
        if rows:
            break                                    # this window yielded sales - stop widening
    max_age = used_window                            # the window the figures below describe

    if not rows:
        # Only true absence reaches here: the widest window returned genuine empty results.
        # Separate a provider that kept erroring (retry another day, NOT confirmed empty) from
        # a district the registry simply holds no sales for - the pipeline gates on this.
        if any_error:
            if quota:
                # The paid wallet ran dry, not the registry. Say so plainly so the ledger and
                # the gate never read this as a transient outage or as 'no sales here'. For an
                # England/Wales district the gather wiring still rescues this via the FREE HMLR
                # register; only Scotland/NI (no free Price Paid coverage) are actually stuck.
                return {"ok": False, "errored": True, "quota_exhausted": True,
                        "reason": "PropertyData paid monthly credit limit exhausted (HTTP 403 "
                                  "X04) - the paid feed is capped, not a district without sales"}
            return {"ok": False, "errored": True,
                    "reason": "sold lookup failed at every window (provider error, "
                              "not confirmed absence)"}
        return {"ok": False, "errored": False,
                "reason": f"no sold records on file for this district "
                          f"(checked back {windows[-1]} months)"}

    prices = [r["price"] for r in rows if r.get("price")]
    psms = [round(r["price"] / r["sqm"]) for r in rows
            if r.get("price") and r.get("sqm")]
    dates = [_to_date(r.get("date")) for r in rows]
    dates = [d for d in dates if d]
    today = datetime.date.today()

    def _since(months):
        cut = today - datetime.timedelta(days=int(months * 30.44))
        return sum(1 for d in dates if d >= cut)

    # bedroom mix (where the row carries a bed count)
    beds = {}
    for r in rows:
        b = r.get("bedrooms")
        if b:
            beds[b] = beds.get(b, 0) + 1

    # a small, honest evidence sample: most recent sales with a known £/sqm first
    sample = sorted(
        [r for r in rows if r.get("price")],
        key=lambda r: (_to_date(r.get("date")) or datetime.date.min),
        reverse=True,
    )[:12]
    sample = [{
        "price": r.get("price"), "sqm": r.get("sqm"),
        "psm": (round(r["price"] / r["sqm"]) if r.get("price") and r.get("sqm") else None),
        "type": r.get("pdtype"), "beds": r.get("bedrooms"),
        "date": (str(r.get("date"))[:10] if r.get("date") else None),
        "url": r.get("url"),
    } for r in sample]

    return {
        "ok": True,
        "total": len(rows),
        "median_price": _median(prices),
        "psm_median": _median(psms),
        "price_low": min(prices) if prices else None,
        "price_high": max(prices) if prices else None,
        "by_type": by_type,
        "beds_mix": dict(sorted(beds.items())),
        "recency": {"last_12m": _since(12), "last_24m": _since(24),
                    "window_months": max_age},
        "newest": max(dates).isoformat() if dates else None,
        "oldest": min(dates).isoformat() if dates else None,
        "sample": sample,
        "source": "HM Land Registry Price Paid Data via PropertyData (OGL)",
    }


# HMLR Price Paid property-type labels -> our four residential type slugs. 'other' is
# commercial/non-residential and is dropped, so the district median stays a homes median.
_HMLR_TYPE_MAP = {
    "flat-maisonette": ("flat", "Flats"),
    "terraced": ("terraced_house", "Terraced houses"),
    "semi-detached": ("semi_detached_house", "Semi-detached houses"),
    "detached": ("detached_house", "Detached houses"),
}
# How far back the free-register fallback reads, to mirror the paid block's widest window.
_HMLR_WINDOW_MONTHS = 120

# The locally-mirrored full Price Paid register (hmlr_ingest.py keeps it whole and current on
# the VPS). When present it is the fastest, free, quota-proof sold source for England & Wales -
# it holds EVERY transaction since 1995, so a central outcode is dense, not thin. Absent on the
# laptop, so callers fall through to the SPARQL fallback / PropertyData unchanged.
_HMLR_DB = os.environ.get("HMLR_DB_PATH", "/opt/honestly/data/hmlr_ppd.db")
# HMLR PPD single-letter property type -> our four residential slugs. 'O' (other) is
# commercial/non-residential and is dropped so the district median stays a homes median.
_PPD_TYPE_MAP = {
    "F": ("flat", "Flats"),
    "T": ("terraced_house", "Terraced houses"),
    "S": ("semi_detached_house", "Semi-detached houses"),
    "D": ("detached_house", "Detached houses"),
}


def _assemble_sold_from_rows(rows, *, source, fallback, window):
    """Build the standard sold-block model from already-collected HMLR rows. Each row is a
    dict with price, date, pdtype (and optional sqm/url). One source of truth shared by both
    free-register paths (local mirror + direct SPARQL) so their output can never drift."""
    by_type = []
    for pdtype, label in TYPES:
        t_rows = [r for r in rows if r["pdtype"] == pdtype]
        prices = [r["price"] for r in t_rows]
        by_type.append({"type": pdtype, "label": label, "n": len(t_rows),
                        "median": _median(prices) if prices else None,
                        "psm_median": None})
    prices = [r["price"] for r in rows]
    dates = [_to_date(r.get("date")) for r in rows]
    dates = [d for d in dates if d]
    today = datetime.date.today()

    def _since(months):
        cut = today - datetime.timedelta(days=int(months * 30.44))
        return sum(1 for d in dates if d >= cut)

    sample = sorted(rows, key=lambda r: (_to_date(r.get("date")) or datetime.date.min),
                    reverse=True)[:12]
    # Carry the official HMLR verification link (and postcode/address where present) onto
    # every evidence row: a sold price is never shown without the means to confirm it.
    sample = [{"price": r["price"], "sqm": None, "psm": None, "type": r["pdtype"],
               "beds": None, "date": (str(r.get("date"))[:10] if r.get("date") else None),
               "postcode": r.get("postcode"), "address": r.get("address"),
               "url": r.get("url")} for r in sample]
    return {
        "ok": True,
        "total": len(rows),
        "median_price": _median(prices),
        "psm_median": None,                          # the free register carries no floor area
        "price_low": min(prices), "price_high": max(prices),
        "by_type": by_type,
        "beds_mix": {},
        "recency": {"last_12m": _since(12), "last_24m": _since(24),
                    "window_months": window},
        "newest": max(dates).isoformat() if dates else None,
        "oldest": min(dates).isoformat() if dates else None,
        "sample": sample,
        "fallback": fallback,
        "source": source,
    }


# The VPS register query service (hmlr_query.py behind nginx /hmlr/). When set, the laptop
# blog pipeline asks the VPS for an outcode's rows instead of opening a local DB file, so it
# never has to download the 5.47 GB register. The token gates the service; both are read from
# the environment / a local secret file - never hardcoded, never from .env.
_HMLR_QUERY_URL = os.environ.get("HMLR_QUERY_URL")

# A local JSON cache of the VPS register, written by hmlr_pull.py in ONE read-only SSH query
# for just the outcodes we publish. This is the laptop's quota-proof, no-download path: the
# 5.47 GB register stays on the VPS, the laptop holds only the few MB of rows it needs. Keyed
# by outcode -> [{price,date,ptype}]. Highest priority source when present.
_HMLR_CACHE_PATH = os.environ.get(
    "HMLR_CACHE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "hmlr_cache.json"))
_HMLR_CACHE = None


def _hmlr_cache():
    """Lazy-load the local register cache once. Returns {} when absent/unreadable so callers
    fall through cleanly (never raises)."""
    global _HMLR_CACHE
    if _HMLR_CACHE is None:
        try:
            import json as _json
            with open(_HMLR_CACHE_PATH, encoding="utf-8") as f:
                d = _json.load(f)
            _HMLR_CACHE = d.get("outcodes", {}) if d.get("ok") else {}
        except Exception:
            _HMLR_CACHE = {}
    return _HMLR_CACHE


def _hmlr_query_token():
    t = os.environ.get("HMLR_QUERY_TOKEN")
    if t:
        return t.strip()
    for p in (os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hmlr_query_token"),
              ".hmlr_query_token"):
        try:
            return open(p, encoding="utf-8").read().strip()
        except OSError:
            continue
    return ""


def _fetch_remote_sold(outcode, since):
    """Pull an outcode's residential sold rows from the VPS register service. Returns a list
    of raw {price, date, ptype} dicts, or None on any failure (caller falls through)."""
    import urllib.parse, urllib.request, json as _json
    base = _HMLR_QUERY_URL.rstrip("/")
    qs = urllib.parse.urlencode({"outcode": outcode, "since": since,
                                 "k": _hmlr_query_token()})
    try:
        with urllib.request.urlopen(f"{base}/sold?{qs}", timeout=30) as r:
            d = _json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None
    if not d.get("ok"):
        return None
    return d.get("rows", [])


def _sold_block_localdb(outcode, country):
    """Fastest, free, quota-proof district sold picture from the full HM Land Registry Price
    Paid register - via the VPS query service (HMLR_QUERY_URL) when set, else a co-located DB
    file. Same shape as _sold_block. England & Wales only. Returns {ok: False} (never raises)
    when neither source is present or the outcode is empty, so callers fall through to the
    SPARQL fallback / PropertyData exactly as before."""
    import sqlite3
    c = (country or "").strip().lower()
    if c and c not in ("england", "wales", "england and wales"):
        return {"ok": False, "errored": False, "uncovered": True,
                "reason": f"HM Land Registry Price Paid does not cover {country}"}
    since = (datetime.date.today()
             - datetime.timedelta(days=int(_HMLR_WINDOW_MONTHS * 30.44))).isoformat()

    raw = None
    cache = _hmlr_cache()
    if cache:
        # The local cache holds the full window pulled from the VPS register; filter to window.
        rows_for_oc = cache.get(outcode.upper())
        if rows_for_oc is not None:
            raw = [r for r in rows_for_oc if not since or (r.get("date") or "") >= since]
    if raw is None and _HMLR_QUERY_URL:
        raw = _fetch_remote_sold(outcode, since)         # ask the VPS-hosted register
        if raw is None:
            return {"ok": False, "errored": True,
                    "reason": "VPS HMLR register query failed (service unreachable)"}
    elif raw is None and os.path.exists(_HMLR_DB):
        try:
            cx = sqlite3.connect(f"file:{_HMLR_DB}?mode=ro", uri=True, timeout=30)
            recs = cx.execute(
                "SELECT tuid, price, deed_date, postcode, ptype FROM ppd "
                "WHERE outcode=? AND deed_date>=? AND ptype IN ('F','T','S','D') "
                "ORDER BY deed_date DESC", (outcode, since)).fetchall()
            cx.close()
        except sqlite3.Error as e:
            return {"ok": False, "errored": True,
                    "reason": f"local HMLR query failed: {str(e)[:80]}"}
        raw = [{"tuid": u, "price": p, "date": d, "postcode": pc, "ptype": t}
               for (u, p, d, pc, t) in recs]
    else:
        return {"ok": False, "errored": False, "reason": "no HMLR mirror configured"}

    rows = []
    for r in raw:
        m = _PPD_TYPE_MAP.get((r.get("ptype") or "").upper())
        if not m or not r.get("price"):
            continue
        rows.append({"price": r["price"], "date": r.get("date"),
                     "pdtype": m[0], "sqm": None,
                     "postcode": r.get("postcode"),
                     "url": _tx_uri(r.get("tuid"))})
    if not rows:
        # The whole register was queried for this E&W outcode and holds no residential sale in
        # the window - confirmed absence (an all-commercial core), not a fetch artifact.
        return {"ok": False, "errored": False, "confirmed_absent": True,
                "reason": f"no residential sales on the HMLR register for this district "
                          f"(checked back {_HMLR_WINDOW_MONTHS} months)"}
    return _assemble_sold_from_rows(
        rows, window=_HMLR_WINDOW_MONTHS, fallback="hmlr_localdb",
        source="HM Land Registry Price Paid Data (free official register, local mirror, OGL)")


def _sold_block_hmlr(outcode, country):
    """Free fallback for the district sold picture, straight from the official HM Land
    Registry Price Paid register (England & Wales only). Used when the paid PropertyData
    feed has no sold rows for a district after widening - central, commercial-heavy
    outcodes (M2, B2) are dense with sales the paid feed simply does not return. We
    enumerate the district's postcodes via Postcodes.io and aggregate the register's own
    transactions, so the figure is real and the source is the authoritative free one.

    Returns the SAME shape as _sold_block so every downstream consumer is unchanged, with a
    distinct `source`. Scotland/NI never reach here (HMLR Price Paid does not cover them).
    Returns {ok: False, ...} - never raises - so a registry hiccup degrades cleanly."""
    if land_registry is None:
        return {"ok": False, "errored": True, "reason": "land_registry unavailable"}
    c = (country or "").strip().lower()
    if c and c not in ("england", "wales", "england and wales"):
        return {"ok": False, "errored": False, "uncovered": True,
                "reason": f"HM Land Registry Price Paid does not cover {country}"}
    enum = geo.outcode_postcodes(outcode)
    if not enum.get("ok"):
        return {"ok": False, "errored": True,
                "reason": f"could not enumerate {outcode} postcodes ({enum.get('reason')})"}
    since = (datetime.date.today()
             - datetime.timedelta(days=int(_HMLR_WINDOW_MONTHS * 30.44))).isoformat()
    area = land_registry.ppd_area(enum["postcodes"], since=since, cap=150,
                                  limit=800, timeout=45)
    if not area.get("ok"):
        return {"ok": False, "errored": True,
                "reason": f"HMLR area lookup failed ({area.get('reason')})"}

    # keep only residential rows we can map to a type; drop commercial 'other'
    rows = []
    for s in area.get("sales", []):
        t = (s.get("type") or "").strip().lower()
        m = _HMLR_TYPE_MAP.get(t)
        if not m or not s.get("price"):
            continue
        # the SPARQL surface already carries the official transaction URI (?tx) and the
        # postcode/address - thread them so every sold row links back to the register.
        rows.append({"price": s["price"], "date": s.get("date"),
                     "pdtype": m[0], "sqm": None,
                     "postcode": s.get("postcode"), "address": s.get("address"),
                     "url": s.get("hmlr_uri") or _tx_uri(s.get("tuid"))})
    if not rows:
        # The free authoritative register was actually queried across every enumerated member
        # postcode and holds no residential sale - this is CONFIRMED absence for an England/
        # Wales district (e.g. B2, an all-commercial city core), not a provider hiccup. The
        # flag lets the caller override a PropertyData 404-error guess with this real finding.
        return {"ok": False, "errored": False, "confirmed_absent": True,
                "reason": f"no residential sales on the HMLR register for this district "
                          f"(checked back {_HMLR_WINDOW_MONTHS} months)"}

    return _assemble_sold_from_rows(
        rows, window=_HMLR_WINDOW_MONTHS, fallback="hmlr_direct",
        source="HM Land Registry Price Paid Data (free official register, OGL)")


def _free_sold(outcode, country):
    """The district's sold picture from the FREE official HM Land Registry Price Paid
    register - the single sold source for the blog. The paid vendors are retired: they
    resold this exact OGL register and computed the medians/splits we now compute ourselves
    in _assemble_sold_from_rows, so they add nothing we cannot get for free.

    Tries the fast local/VPS mirror first, then the direct SPARQL enumeration; both return
    the same shape. England & Wales are fully covered. Scotland/NI are not in Price Paid, so
    the block comes back {ok: False, uncovered: True} and the page is skipped honestly -
    never invented, never deferred forever as a phantom 'feed down'."""
    hmlr = _sold_block_localdb(outcode, country)
    if not hmlr.get("ok") and not hmlr.get("confirmed_absent") and not hmlr.get("uncovered"):
        hmlr = _sold_block_hmlr(outcode, country)
    return hmlr


# ------------------------------------------------------------------ live listings
def _listings_block(outcode, key):
    """The district's live on-market picture: asking median, days on market, stuck stock,
    under-offer share. Asking signals vendor expectation - context, never evidence."""
    if appraise is None:
        return {"ok": False, "reason": "provider layer unavailable"}
    rows, any_error = [], False
    for pdtype, _ in TYPES:
        try:
            d = appraise.api("prices", key, postcode=outcode, type=pdtype)
            for r in (d.get("data", {}).get("raw_data", []) or []):
                r["pdtype"] = pdtype                 # tag type so the selector can read it
                rows.append(r)
        except Exception:
            any_error = True                         # a fetch failure, not proof of an empty market
            continue
    if not rows:
        # Distinguish a provider error (retryable) from a district with genuinely no live
        # stock, so an outage is never recorded as 'nothing on the market here'.
        if any_error:
            return {"ok": False, "errored": True,
                    "reason": "listings lookup failed (provider error, not confirmed empty)"}
        return {"ok": False, "errored": False,
                "reason": "no live listings for this district"}
    prices = [r["price"] for r in rows if r.get("price")]
    doms = [r.get("days_on_market") or 0 for r in rows]
    avail = [r for r in rows if not r.get("sstc")]
    stuck = [r for r in avail if (r.get("days_on_market") or 0) >= 90]
    fresh = [r for r in rows if (r.get("days_on_market") or 0) <= 20]
    under_offer = [r for r in rows if r.get("sstc")]
    # a slim per-listing list for the "listings to watch" selector; dropped from the model
    # after the picks are made (the resolved picks are self-contained, so re-renders are stable).
    slim = [{"price": r.get("price"), "beds": r.get("bedrooms"),
             "dom": r.get("days_on_market") or 0, "sstc": bool(r.get("sstc")),
             "type": r.get("pdtype"), "address": r.get("address"), "url": r.get("url")}
            for r in rows if r.get("price")]
    return {
        "ok": True, "n": len(rows),
        "asking_median": _median(prices),
        "asking_low": min(prices) if prices else None,
        "asking_high": max(prices) if prices else None,
        "mean_dom": int(statistics.mean(doms)) if doms else None,
        "available_n": len(avail), "stuck_n": len(stuck),
        "fresh_n": len(fresh), "under_offer_n": len(under_offer),
        "_rows": slim,
        "source": "Live on-market listings via PropertyData",
    }


# ------------------------------------------------------------------ listings to watch
# Three live listings surfaced each day - one each for buyers, sellers and agents - drawn at
# random from all the listings that genuinely qualify on each measure. Randomised among
# qualifiers so it is defensible: a listing can be featured by default but never guaranteed,
# and nothing here is paid placement. Asking prices are context, never evidence of value.
WATCH_DISCOUNT = 0.05   # >=5% below the local sold median to count as a genuine keen price
WATCH_PREMIUM = 0.05    # >=5% above the local sold median to count as priced-to-sit
WATCH_STALE = 90        # days on market that mark a listing as stalled


def _watch_link(url):
    """Resolve a PropertyData outbound listing URL to (portal_name, public_url). Empty when
    it is not a recognised portal link - those listings are not featured, so every card is
    genuinely clickable. Outbound verify link only; the listing data is PropertyData's."""
    if appraise is not None:
        try:
            name, link = appraise.listing_link(url)
            if name and link:
                return name, link
        except Exception:
            pass
    return "", ""


def _watch_ref(listing, sold):
    """The sold median this listing's asking price is judged against: its own property type
    where we have it, else the district-wide median. Returns (median, basis_label)."""
    if not (sold or {}).get("ok"):
        return None, ""
    by = {b["type"]: b for b in sold.get("by_type", [])}
    bt = by.get(listing.get("type"))
    if bt and bt.get("median"):
        return bt["median"], bt["label"].lower()
    if sold.get("median_price"):
        return sold["median_price"], "the district"
    return None, ""


def _watch_block(rows, sold, rng):
    """Pick up to three standout live listings (buyers / sellers / agents) and freeze the
    choice into the model. rng is seeded from district+date, so the draw is stable across
    re-renders (numbers never drift) yet not a fixed 'always the most extreme' ranking."""
    # keep only genuinely clickable listings (resolvable portal link + a price)
    linkable = []
    for r in rows:
        if not r.get("price"):
            continue
        name, link = _watch_link(r.get("url"))
        if link:
            r = dict(r)
            r["_portal"], r["_link"] = name, link
            linkable.append(r)
    if not linkable:
        return {"ok": False, "reason": "no linkable live listings to feature"}

    avail = [r for r in linkable if not r.get("sstc")]

    def ratio(r):
        ref, _ = _watch_ref(r, sold)
        return (r["price"] / ref) if ref else None

    # qualifying pools (genuine standouts), each with an honest fallback for thin districts
    buyer_q = [r for r in avail if (ratio(r) or 9) <= 1 - WATCH_DISCOUNT] \
        or sorted(avail, key=lambda r: r["price"])[:5]
    seller_q = [r for r in avail
                if (ratio(r) or 0) >= 1 + WATCH_PREMIUM and (r.get("dom") or 0) >= WATCH_STALE] \
        or [r for r in avail if (ratio(r) or 0) >= 1 + WATCH_PREMIUM] \
        or sorted(avail, key=lambda r: (r.get("dom") or 0), reverse=True)[:5]
    agent_q = [r for r in avail if (r.get("dom") or 0) >= WATCH_STALE] \
        or sorted(avail, key=lambda r: (r.get("dom") or 0), reverse=True)[:5]

    specs = [("buyers", "bargain", "The keen price", buyer_q),
             ("sellers", "overpriced", "Priced to sit", seller_q),
             ("agents", "stalled", "The stalled instruction", agent_q)]
    picks, used = [], set()
    for audience, key, headline, pool in specs:
        options = [r for r in pool if r["_link"] not in used]
        if not options:
            continue
        choice = rng.choice(options)
        used.add(choice["_link"])
        ref, basis = _watch_ref(choice, sold)
        vs = round((choice["price"] / ref - 1) * 100) if ref and choice.get("price") else None
        picks.append({
            "audience": audience, "reason_key": key, "headline": headline,
            "price": choice.get("price"), "beds": choice.get("beds"),
            "type": choice.get("type"), "dom": choice.get("dom"),
            "sstc": bool(choice.get("sstc")), "address": choice.get("address"),
            "portal": choice["_portal"], "link": choice["_link"],
            "ref_median": ref, "ref_basis": basis, "vs_median_pct": vs,
            "pool_size": len(pool),
        })
    if not picks:
        return {"ok": False, "reason": "no listings qualified to feature"}
    return {
        "ok": True, "picks": picks,
        "method": ("Three live listings that stand out for buyers, sellers and agents, "
                   "drawn at random from every listing that qualifies on each measure."),
        "source": "Live on-market listings via PropertyData; links to the public portal listing",
    }


# ------------------------------------------------------------------ rent + yield
# PropertyData's /rents and /yields are keyed by type AND bedroom count, so a whole-district
# read means querying a representative bed count per type. These four profiles are the most
# liquid configuration of each type in UK stock; every figure is LABELLED with its bed count
# (e.g. "2-bed flat") so we never imply it speaks for all flats. Rent is real long-let listing
# data; gross yield is PropertyData's own published estimate (before costs and voids). Yield is
# a transparent rent-to-price ratio shown beside its inputs - never a valuation of any property.
RENT_PROFILE = [
    ("flat", "Flats", 2),
    ("terraced_house", "Terraced houses", 3),
    ("semi_detached_house", "Semi-detached houses", 3),
    ("detached_house", "Detached houses", 4),
]


def _pct_num(s):
    """Parse PropertyData's '5.2%' gross-yield string to a float 5.2, or None."""
    if s is None:
        return None
    try:
        return round(float(str(s).strip().rstrip("%")), 1)
    except (ValueError, TypeError):
        return None


def _rent_block(outcode, key):
    """The district's rental picture: typical long-let rent and PropertyData's gross yield,
    per type at a representative bed count. Best-effort; a type with no rental dataset (a 404)
    is simply skipped. Returns ok=False when nothing comes back. Rent context, not value."""
    if appraise is None:
        return {"ok": False, "reason": "provider layer unavailable"}
    rows = []
    for pdtype, label, beds in RENT_PROFILE:
        weekly = rng = None
        rent_n = 0
        try:
            d = appraise.api("rents", key, postcode=outcode, type=pdtype, bedrooms=beds)
            ll = (d.get("data") or {}).get("long_let") or {}
            if ll.get("average"):
                weekly = ll["average"]
                rent_n = ll.get("points_analysed") or 0
                rng = ll.get("80pc_range")
        except Exception:
            pass
        gross_yield = None
        yield_n = 0
        try:
            d = appraise.api("yields", key, postcode=outcode, type=pdtype, bedrooms=beds)
            ll = (d.get("data") or {}).get("long_let") or {}
            gross_yield = _pct_num(ll.get("gross_yield"))
            yield_n = ll.get("points_analysed") or 0
        except Exception:
            pass
        if weekly is None and gross_yield is None:
            continue
        rows.append({
            "type": pdtype, "label": label, "beds": beds,
            "weekly": weekly,
            "monthly": (round(weekly * 52 / 12) if weekly else None),
            "range_week": rng if (isinstance(rng, list) and len(rng) == 2) else None,
            "rent_n": rent_n,
            "gross_yield": gross_yield, "yield_n": yield_n,
        })
    if not rows:
        return {"ok": False, "reason": "no rental data for this district"}
    yields = [r["gross_yield"] for r in rows if r.get("gross_yield") is not None]
    weeklies = [r["weekly"] for r in rows if r.get("weekly") is not None]
    return {
        "ok": True,
        "rows": rows,
        "headline_yield": _median(yields) if yields else None,
        "headline_weekly": _median(weeklies) if weeklies else None,
        "unit": "gbp_per_week",
        "source": ("Live long-let rental listings via PropertyData; gross yield is "
                   "PropertyData's estimate, before letting costs and void periods"),
    }


# ------------------------------------------------------------------ HPI + PPD direct
def _hpi_block(city):
    if land_registry is None:
        return {"ok": False, "reason": "land_registry unavailable"}
    try:
        return land_registry.hpi_region(city["hpi_region"])
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}


def _ppd_block(outcode):
    """Independent HM Land Registry sold check (direct, OGL). Best-effort at outcode
    level; degrades quietly when the direct query returns nothing."""
    if land_registry is None:
        return {"ok": False, "reason": "land_registry unavailable"}
    try:
        return land_registry.ppd_postcode(outcode)
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}


# ------------------------------------------------------------------ the gather
def gather(city, district, *, key=None, max_age_months=24, with_area=True):
    """Build the full real-data model for one (city, district). Never raises; every block
    is independently best-effort and self-labels when its source is unavailable."""
    key = key or _key()
    outcode = (district or "").strip().upper()
    g = geo.outcode(outcode)
    out = {
        "ok": True,
        "city": {"slug": city["slug"], "name": city["name"],
                 "series": city["series"], "strapline": city.get("strapline", ""),
                 "country": city.get("country", ""), "hpi_region": city["hpi_region"]},
        "district": outcode,
        "slug": cities.slug_for(city["slug"], outcode),
        "generated_at": datetime.date.today().isoformat(),
        "geo": g if g.get("ok") else {"ok": False, "reason": g.get("reason")},
        "present": {},
    }

    # The sold picture - the spine of every blog page - comes straight from the FREE official
    # HM Land Registry Price Paid register (OGL). The paid vendors are retired: they resold
    # this same register and computed the medians/splits we now compute ourselves, so they buy
    # us nothing. England & Wales are fully covered; Scotland/NI are not in Price Paid and come
    # back uncovered, so those districts skip honestly rather than invent a figure.
    country = g.get("country") if g.get("ok") else ""
    out["sold"] = _free_sold(outcode, country)
    # Live asking prices and rents are portal data - they are NOT published in any free
    # official register and cannot be computed from completed sales. We do not pay a vendor
    # for them and we do not invent them: the blocks self-label as unavailable, and the
    # authoritative sold register carries the report on its own.
    out["listings"] = {"ok": False, "reason": "live asking-price listings are not in any free "
                       "official register; this report is built on completed HM Land Registry "
                       "sales, not asking prices"}
    out["rent"] = {"ok": False, "reason": "rental listings are not in any free official "
                   "register; the completed-sales record carries this report"}

    out["hpi"] = _hpi_block(city)
    out["ppd"] = _ppd_block(outcode)

    # listings to watch - three audience picks drawn at random from the qualifying pools, then
    # frozen into the model so re-renders never drift. Seeded by district+date: stable for the
    # day, different across districts and days, never a fixed "always the most extreme" ranking.
    lb = out.get("listings") or {}
    if lb.get("ok") and lb.get("_rows"):
        rng = random.Random(f"{outcode}:{out['generated_at']}")
        out["watch"] = _watch_block(lb["_rows"], out.get("sold") or {}, rng)
    else:
        out["watch"] = {"ok": False, "reason": lb.get("reason", "no live listings")}
    lb.pop("_rows", None)   # the resolved picks are self-contained; drop the raw rows

    # demand read - best-effort; needs a full postcode, so only attempt when geo gave us a
    # representative one is not available at outcode level. We skip rather than guess.
    out["demand"] = {"ok": False, "reason": "district-level demand derived from sold volume"}

    # area context on the district centroid (free spine: location, amenities, safety,
    # environment, planning). Pass coords through as the subject so gather can resolve.
    if with_area and area_context is not None and g.get("ok") and g.get("lat") and g.get("lng"):
        try:
            subj = {"lat": g["lat"], "lng": g["lng"], "postcode": outcode,
                    "address": f"{outcode}, {g.get('district') or city['name']}"}
            ac = area_context.gather(subj)
            out["area"] = ac.get("sections")
            out["area_present"] = ac.get("present", {})
        except Exception as e:
            out["area"] = None
            out["area_present"] = {}
            out["area_error"] = str(e)[:120]
    else:
        out["area"] = None
        out["area_present"] = {}

    # provenance flags the references builder reads
    pres = out["present"]
    if out["sold"].get("ok"):
        # Credit the source the sold figure actually came from: the free HMLR register when
        # the fallback fired, PropertyData otherwise. The references builder reads these.
        if out["sold"].get("fallback") in ("hmlr_direct", "hmlr_localdb"):
            pres["hmlr_direct"] = True
        else:
            pres["pd_sold"] = True
    if out["listings"].get("ok"):
        pres["pd_listings"] = True
    if out.get("rent", {}).get("ok"):
        pres["pd_rent"] = True
    if out.get("watch", {}).get("ok"):
        pres["watch"] = True
    if out["hpi"].get("ok"):
        pres["hmlr_direct"] = True
    if out["ppd"].get("ok") and (out["ppd"].get("count") or 0) > 0:
        pres["hmlr_direct"] = True
    if g.get("ok"):
        pres["postcodes_io"] = True
    for k, cid in (("overpass", "overpass"), ("police", "police"),
                   ("flood", "flood"), ("air_quality", "air_quality"),
                   ("planning", "planning")):
        if out.get("area_present", {}).get(k):
            pres[cid] = True

    return out


# ------------------------------------------------------------------ CLI
def _fmt_gbp(v):
    return ("£{:,.0f}".format(v)) if v else "n/a"


def _summary(m):
    c = m["city"]
    print(f"{c['series']} - {m['district']} ({c['name']})  [{m['generated_at']}]")
    g = m.get("geo") or {}
    if g.get("ok"):
        print(f"  geo      : {g.get('district')}, {g.get('region')}  "
              f"({g.get('lat')}, {g.get('lng')})")
    else:
        print(f"  geo      : unavailable ({g.get('reason')})")
    s = m.get("sold") or {}
    if s.get("ok"):
        print(f"  sold     : {s['total']} sales, median {_fmt_gbp(s['median_price'])}, "
              f"£/sqm {_fmt_gbp(s['psm_median'])}, "
              f"{s['recency']['last_12m']} in last 12m")
        for bt in s.get("by_type", []):
            if bt["n"]:
                print(f"             - {bt['label']:<22} {bt['n']:>3}  "
                      f"med {_fmt_gbp(bt['median'])}  £/sqm {_fmt_gbp(bt['psm_median'])}")
    else:
        print(f"  sold     : unavailable ({s.get('reason')})")
    l = m.get("listings") or {}
    if l.get("ok"):
        print(f"  listings : {l['n']} on market, asking median {_fmt_gbp(l['asking_median'])}, "
              f"mean DOM {l['mean_dom']}, stuck {l['stuck_n']}, under offer {l['under_offer_n']}")
    else:
        print(f"  listings : unavailable ({l.get('reason')})")
    rt = m.get("rent") or {}
    if rt.get("ok"):
        hy = rt.get("headline_yield")
        print(f"  rent     : headline {_fmt_gbp(rt.get('headline_weekly'))}/wk, "
              f"gross yield {hy if hy is not None else 'n/a'}%")
        for r in rt.get("rows", []):
            wk = f"£{r['weekly']:,.0f}/wk" if r.get("weekly") else "rent n/a"
            gy = f"{r['gross_yield']}%" if r.get("gross_yield") is not None else "yield n/a"
            print(f"             - {r['beds']}-bed {r['label']:<20} {wk:>12}  {gy}")
    else:
        print(f"  rent     : unavailable ({rt.get('reason')})")
    h = m.get("hpi") or {}
    if h.get("ok"):
        print(f"  hpi      : {h['region']} avg {_fmt_gbp(h.get('average_price'))}, "
              f"yoy {h.get('annual_change_pct')}%  ({h.get('month')})")
    else:
        print(f"  hpi      : unavailable ({h.get('reason')})")
    a = m.get("area") or {}
    if a:
        lit = [k for k, v in (m.get("area_present") or {}).items() if v]
        print(f"  area     : {', '.join(lit) if lit else 'none lit'}")
    else:
        print("  area     : unavailable")
    pres = sorted(m.get("present", {}).keys())
    print(f"  present  : {', '.join(pres)}")


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    district = sys.argv[1].upper()
    as_json = "--json" in sys.argv[2:]
    city = cities.city_of_district(district)
    if not city:
        sys.exit(f"unknown district {district} (not in any city's rotation). "
                 f"Run: python cities.py")
    m = gather(city, district)
    if as_json:
        print(json.dumps(m, indent=2, ensure_ascii=False, default=str))
    else:
        _summary(m)


if __name__ == "__main__":
    main()
