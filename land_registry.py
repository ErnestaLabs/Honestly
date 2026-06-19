#!/usr/bin/env python3
"""land_registry.py - HM Land Registry open data, direct (OGL, no API key).

An INDEPENDENT official check that sits BESIDE the figure - never inside it. The
valuation is anchored on PropertyData's sold evidence; this module pulls the same
underlying truth (Price Paid Data) straight from HM Land Registry's own SPARQL
endpoint, so a buyer can hand a desk valuer a sold list that came from the
registry itself, not from any third party. That is the down-valuation evidence
pack: "the registry shows these exact sold prices on this postcode."

Two surfaces:
  ppd_postcode(postcode)      -> official sold transactions for a postcode   [SPARQL]
  hpi_region(region, month)   -> UK House Price Index for a region/month      [REST]

Same posture as maps_tools.py: every call degrades to {'ok': False, 'reason': ...}
instead of raising, so the engine keeps working if the endpoint is slow or down.

Sources (Open Government Licence, no key):
  PPD SPARQL  http://landregistry.data.gov.uk/landregistry/query
  UK HPI      http://landregistry.data.gov.uk/data/ukhpi/region/<slug>/month/<YYYY-MM>

CLI:
  python land_registry.py ppd "SE15 6JH"
  python land_registry.py hpi london 2026-03
  python land_registry.py selftest
"""
import os, sys, json, re, time, statistics, urllib.parse, urllib.request, urllib.error

SPARQL = "http://landregistry.data.gov.uk/landregistry/query"
HPI = "http://landregistry.data.gov.uk/data/ukhpi/region"
_UA = {"User-Agent": "honestly-landregistry/1.0 (+https://t.me/usehonestly_bot)"}

# Canonical Price Paid query: every residential transaction recorded against a
# postcode, newest first. Verified against HM Land Registry's own SPARQL console.
_PPD_Q = """\
PREFIX xsd:      <http://www.w3.org/2001/XMLSchema#>
PREFIX lrppi:    <http://landregistry.data.gov.uk/def/ppi/>
PREFIX skos:     <http://www.w3.org/2004/02/skos/core#>
PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>
SELECT ?tx ?paon ?saon ?street ?town ?postcode ?amount ?date ?category ?type
WHERE {
  VALUES ?postcode { "%s"^^xsd:string }
  ?addr lrcommon:postcode ?postcode .
  ?tx lrppi:propertyAddress ?addr ;
      lrppi:pricePaid ?amount ;
      lrppi:transactionDate ?date ;
      lrppi:transactionCategory/skos:prefLabel ?category .
  OPTIONAL { ?tx lrppi:propertyType/skos:prefLabel ?type }
  OPTIONAL { ?addr lrcommon:paon ?paon }
  OPTIONAL { ?addr lrcommon:saon ?saon }
  OPTIONAL { ?addr lrcommon:street ?street }
  OPTIONAL { ?addr lrcommon:town ?town }
}
ORDER BY DESC(?date)
LIMIT %d
"""


# The official HM Land Registry linked-data URI for a single Price Paid transaction.
# Following it in a browser returns the registry's OWN record of that exact sale
# (price, address, date, type). Verified resolving (HTTP 200, real record content).
_PPI_TX = "http://landregistry.data.gov.uk/data/ppi/transaction/%s/current"


def transaction_uri(tuid):
    """Build the official HMLR verification URL for a Price Paid transaction from its
    unique identifier (the PPD 'Transaction unique identifier'; braces are stripped,
    case-insensitive). This is the link a reader follows to confirm a sold comparable
    against the source register - the spine of the honesty contract: every figure we
    show as evidence traces to the registry's own page. Returns None when no id given."""
    t = (tuid or "").strip().strip("{}").strip()
    return (_PPI_TX % t) if t else None


def _norm_pc(postcode):
    """Upper-case, single internal space - the form HMLR stores postcodes in."""
    pc = re.sub(r"\s+", "", (postcode or "").upper())
    if len(pc) > 3:                       # split the inward code (last 3 chars)
        pc = pc[:-3] + " " + pc[-3:]
    return pc


def _post_sparql(query, timeout=30):
    body = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(
        SPARQL, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/sparql-results+json", **_UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"Accept": "application/json", **_UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _b(row, key):
    """Pull a binding's value, or None."""
    v = row.get(key)
    return v.get("value") if v else None


def _addr(row):
    parts = [_b(row, "saon"), _b(row, "paon"), _b(row, "street"), _b(row, "town")]
    return ", ".join(p for p in parts if p)


# Opt-in result cache for the valuation hot path. Registry data only changes
# monthly, so a few hours' TTL spares HMLR repeated identical SPARQL on the same
# postcode and keeps card renders instant. Off by default so the offline tests
# stay deterministic; engine.summary turns it on.
_PPD_CACHE = {}
_PPD_CACHE_TTL = 6 * 3600


# ---- LOCAL fast path: the VPS-ingested Price Paid SQLite, served read-only by hmlr_query.py
# on 127.0.0.1:8091. A local indexed lookup answers in single-digit ms; the public SPARQL
# endpoint takes seconds (the "slow valuations" cause). We try local FIRST, fall back to SPARQL
# on miss/empty/error/no-token, so correctness never depends on the ingest having reached this
# postcode yet. Same dict shape both ways -> engine.summary doesn't know or care which served it.
_LOCAL_URL = os.environ.get("HMLR_LOCAL_URL", "http://127.0.0.1:8091")
_LOCAL_TIMEOUT = float(os.environ.get("HMLR_LOCAL_TIMEOUT", "2.5"))


def _local_token():
    """The shared read token for the local query service: env first, then the token file the
    deploy writes next to the service. Returns '' when neither is present (local path disabled)."""
    t = os.environ.get("HMLR_QUERY_TOKEN", "").strip()
    if t:
        return t
    for p in (os.environ.get("HMLR_QUERY_TOKEN_FILE", ""),
              "/opt/honestly/.hmlr_query_token",
              os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hmlr_query_token")):
        try:
            if p and os.path.exists(p):
                return open(p, encoding="utf-8").read().strip()
        except Exception:
            pass
    return ""


def _local_sold(postcode, limit=100):
    """Query the local Price Paid service for an exact postcode. Returns sales in the SAME shape
    as the SPARQL path (address/price/date/type/postcode/hmlr_uri), or None to signal 'fall back
    to SPARQL' (no token, service down, or zero rows). Never raises."""
    tok = _local_token()
    if not tok:
        return None
    pc = _norm_pc(postcode)
    qs = urllib.parse.urlencode({"postcode": pc, "limit": int(limit), "k": tok})
    url = f"{_LOCAL_URL.rstrip('/')}/sold?{qs}"
    try:
        d = _get_json(url, timeout=_LOCAL_TIMEOUT)
    except Exception:
        return None
    if not (isinstance(d, dict) and d.get("ok")):
        return None
    rows = d.get("rows") or []
    if not rows:
        return None                      # not ingested yet for this pc -> let SPARQL try
    _PTYPE = {"F": "Flat/Maisonette", "T": "Terraced", "S": "Semi-Detached", "D": "Detached"}
    sales = []
    for r in rows:
        try:
            amount = int(float(r.get("price")))
        except (TypeError, ValueError):
            continue
        parts = [r.get("saon"), r.get("paon"), r.get("street"), r.get("town")]
        sales.append({
            "address": ", ".join(p for p in parts if p),
            "price": amount, "date": (r.get("date") or "")[:10],
            "category": None, "type": _PTYPE.get(r.get("ptype"), r.get("ptype")),
            "postcode": r.get("postcode"),
            "hmlr_uri": transaction_uri(r.get("tuid")),
        })
    return sales or None


def ppd_postcode(postcode, limit=100, timeout=30, use_cache=False):
    """Official HM Land Registry sold transactions for a postcode, newest first.
    Returns {ok, postcode, count, median, oldest, newest, sales:[...]} or
    {ok: False, reason}. Never raises. timeout bounds the SPARQL call; use_cache
    serves a recent identical result without re-querying (valuation hot path)."""
    pc = _norm_pc(postcode)
    if not pc:
        return {"ok": False, "reason": "no postcode given"}
    ck = (pc, int(limit))
    if use_cache:
        hit = _PPD_CACHE.get(ck)
        if hit and (time.time() - hit[0]) < _PPD_CACHE_TTL:
            return hit[1]
    # FAST PATH: the locally-ingested Price Paid DB (single-digit ms). Falls through to SPARQL
    # if the service is down, the token is absent, or this postcode isn't ingested yet.
    local = _local_sold(pc, limit)
    if local:
        prices = [s["price"] for s in local]
        dates = sorted(s["date"] for s in local if s["date"])
        out = {
            "ok": True, "postcode": pc, "count": len(local),
            "median": int(statistics.median(prices)),
            "low": min(prices), "high": max(prices),
            "oldest": dates[0] if dates else None,
            "newest": dates[-1] if dates else None,
            "sales": local,
            "source": "HM Land Registry Price Paid Data (local ingest, OGL)",
        }
        if use_cache:
            _PPD_CACHE[ck] = (time.time(), out)
        return out
    try:
        d = _post_sparql(_PPD_Q % (pc, int(limit)), timeout=timeout)
    except urllib.error.HTTPError as e:
        return {"ok": False, "reason": f"HMLR SPARQL HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    rows = (d.get("results") or {}).get("bindings") or []
    sales = []
    for r in rows:
        try:
            amount = int(float(_b(r, "amount")))
        except (TypeError, ValueError):
            continue
        date = (_b(r, "date") or "")[:10]
        sales.append({
            "address": _addr(r), "price": amount, "date": date,
            "category": _b(r, "category"), "type": _b(r, "type"),
            "postcode": _b(r, "postcode"),
            "hmlr_uri": _b(r, "tx"),
        })
    if not sales:
        out = {"ok": True, "postcode": pc, "count": 0, "sales": [],
               "reason": "no transactions on record for this postcode"}
        if use_cache:
            _PPD_CACHE[ck] = (time.time(), out)
        return out
    prices = [s["price"] for s in sales]
    dates = sorted(s["date"] for s in sales if s["date"])
    out = {
        "ok": True, "postcode": pc, "count": len(sales),
        "median": int(statistics.median(prices)),
        "low": min(prices), "high": max(prices),
        "oldest": dates[0] if dates else None,
        "newest": dates[-1] if dates else None,
        "sales": sales,
        "source": "HM Land Registry Price Paid Data (SPARQL, OGL)",
    }
    if use_cache:
        _PPD_CACHE[ck] = (time.time(), out)
    return out


# Aggregate count across an EXPLICIT set of postcodes, in one indexed query. A bare
# prefix scan (FILTER STRSTARTS over every address) times out on the public endpoint;
# binding the exact postcodes via VALUES keeps it on the postcode index, so a whole
# sector counts in well under a second. land_registry stays geography-free: the caller
# (demand.py) enumerates the sector's postcodes via Postcodes.io and hands them in.
_COUNT_Q = """\
PREFIX xsd:      <http://www.w3.org/2001/XMLSchema#>
PREFIX lrppi:    <http://landregistry.data.gov.uk/def/ppi/>
PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>
SELECT (COUNT(?tx) AS ?n) WHERE {
  VALUES ?postcode { %s }
  ?addr lrcommon:postcode ?postcode .
  ?tx lrppi:propertyAddress ?addr ;
      lrppi:transactionDate ?date .%s
}
"""

_COUNT_CACHE = {}


def ppd_count(postcodes, since=None, cap=150, timeout=30, use_cache=False):
    """Count recorded PPD transactions across an EXPLICIT set of postcodes (one indexed
    VALUES query), optionally on/after `since` ('YYYY-MM-DD'). For sector/area volume,
    where a single postcode is far too sparse to read demand from. The caller supplies
    the postcode set; this stays geography-free. Returns
    {ok, count, n_postcodes, since} or {ok: False, reason}. Never raises."""
    pcs = []
    seen = set()
    for p in (postcodes or []):
        n = _norm_pc(p)
        if n and n not in seen:
            seen.add(n); pcs.append(n)
    pcs = pcs[:int(cap)]                          # bound the VALUES list for a fast query
    if not pcs:
        return {"ok": False, "reason": "no postcodes given"}
    ck = (frozenset(pcs), since)
    if use_cache:
        hit = _COUNT_CACHE.get(ck)
        if hit and (time.time() - hit[0]) < _PPD_CACHE_TTL:
            return hit[1]
    vals = " ".join('"%s"^^xsd:string' % p for p in pcs)
    dfilter = ('\n  FILTER(?date >= "%s"^^xsd:date)' % since) if since else ""
    try:
        d = _post_sparql(_COUNT_Q % (vals, dfilter), timeout=timeout)
    except urllib.error.HTTPError as e:
        return {"ok": False, "reason": f"HMLR SPARQL HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    rows = (d.get("results") or {}).get("bindings") or []
    try:
        count = int(rows[0]["n"]["value"]) if rows else 0
    except (KeyError, TypeError, ValueError):
        return {"ok": False, "reason": "unparseable count response"}
    out = {"ok": True, "count": count, "n_postcodes": len(pcs), "since": since,
           "source": "HM Land Registry Price Paid Data (SPARQL count, OGL)"}
    if use_cache:
        _COUNT_CACHE[ck] = (time.time(), out)
    return out


# Full sold ROWS across an explicit postcode set, newest first, in one indexed VALUES
# query. ppd_count returns only a number; this returns the transactions themselves, so a
# whole district can be aggregated into a median + by-type breakdown from the FREE official
# register when the paid feed has a gap. Same geography-free contract as ppd_count: the
# caller enumerates the postcodes (e.g. via Postcodes.io) and hands them in.
_AREA_Q = """\
PREFIX xsd:      <http://www.w3.org/2001/XMLSchema#>
PREFIX lrppi:    <http://landregistry.data.gov.uk/def/ppi/>
PREFIX skos:     <http://www.w3.org/2004/02/skos/core#>
PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>
SELECT ?tx ?paon ?saon ?street ?town ?postcode ?amount ?date ?category ?type
WHERE {
  VALUES ?postcode { %s }
  ?addr lrcommon:postcode ?postcode .
  ?tx lrppi:propertyAddress ?addr ;
      lrppi:pricePaid ?amount ;
      lrppi:transactionDate ?date ;
      lrppi:transactionCategory/skos:prefLabel ?category .
  OPTIONAL { ?tx lrppi:propertyType/skos:prefLabel ?type }
  OPTIONAL { ?addr lrcommon:paon ?paon }
  OPTIONAL { ?addr lrcommon:saon ?saon }
  OPTIONAL { ?addr lrcommon:street ?street }
  OPTIONAL { ?addr lrcommon:town ?town }%s
}
ORDER BY DESC(?date)
LIMIT %d
"""

_AREA_CACHE = {}


def ppd_area(postcodes, since=None, cap=150, limit=600, timeout=45, use_cache=False):
    """Official HMLR sold TRANSACTIONS across an EXPLICIT set of postcodes (one indexed
    VALUES query), newest first, optionally on/after `since` ('YYYY-MM-DD'). Returns the
    rows themselves so a caller can build a district median + by-type breakdown straight
    from the free register. Geography-free: the caller supplies the postcode set. Returns
    {ok, count, n_postcodes, since, sales:[{address, price, date, category, type, postcode}]}
    or {ok: False, reason}. Never raises. HMLR Price Paid covers England & Wales only."""
    pcs, seen = [], set()
    for p in (postcodes or []):
        n = _norm_pc(p)
        if n and n not in seen:
            seen.add(n); pcs.append(n)
    pcs = pcs[:int(cap)]
    if not pcs:
        return {"ok": False, "reason": "no postcodes given"}
    ck = (frozenset(pcs), since, int(limit))
    if use_cache:
        hit = _AREA_CACHE.get(ck)
        if hit and (time.time() - hit[0]) < _PPD_CACHE_TTL:
            return hit[1]
    vals = " ".join('"%s"^^xsd:string' % p for p in pcs)
    dfilter = ('\n  FILTER(?date >= "%s"^^xsd:date)' % since) if since else ""
    try:
        d = _post_sparql(_AREA_Q % (vals, dfilter, int(limit)), timeout=timeout)
    except urllib.error.HTTPError as e:
        return {"ok": False, "reason": f"HMLR SPARQL HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    rows = (d.get("results") or {}).get("bindings") or []
    sales = []
    for r in rows:
        try:
            amount = int(float(_b(r, "amount")))
        except (TypeError, ValueError):
            continue
        sales.append({
            "address": _addr(r), "price": amount, "date": (_b(r, "date") or "")[:10],
            "category": _b(r, "category"), "type": _b(r, "type"),
            "postcode": _b(r, "postcode"),
            "hmlr_uri": _b(r, "tx"),
        })
    out = {"ok": True, "count": len(sales), "n_postcodes": len(pcs), "since": since,
           "sales": sales,
           "source": "HM Land Registry Price Paid Data (SPARQL, OGL)"}
    if use_cache:
        _AREA_CACHE[ck] = (time.time(), out)
    return out


_REFMON = {m: i for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}


def _month_from_ref(ref):
    """'Mon, 01 Dec 2025' -> '2025-12'. None if unparseable."""
    m = re.search(r"(\d{2})\s+([A-Za-z]{3})\s+(\d{4})", ref or "")
    if not m:
        return None
    mon = _REFMON.get(m.group(2).title())
    return f"{m.group(3)}-{mon:02d}" if mon else None


def _latest_month(slug, timeout=20):
    """Newest published YYYY-MM for a region, read from the HPI listing. None on fail."""
    try:
        d = _get_json(f"{HPI}/{urllib.parse.quote(slug)}.json", timeout=timeout)
    except Exception:
        return None
    items = d.get("result", {}).get("items") or []
    months = []
    for it in items:
        # listing items are URI strings ending '/month/YYYY-MM' (newest first),
        # but some responses nest the record as a dict with refPeriodStart.
        if isinstance(it, str):
            m = re.search(r"/month/(\d{4}-\d{2})", it)
            if m:
                months.append(m.group(1))
        elif isinstance(it, dict):
            ref = it.get("refPeriodStart")
            if isinstance(ref, dict):
                ref = ref.get("@value") or ref.get("value")
            ym = _month_from_ref(ref)
            if ym:
                months.append(ym)
    return max(months) if months else None


def hpi_region(region, month=None):
    """UK House Price Index for a region slug (e.g. 'london', 'east-of-england')
    and a YYYY-MM month (omit for the latest published). Returns {ok, ...} with the
    average price and annual change, or {ok: False, reason}. Never raises. Sits
    beside the figure - HPI never moves the valuation."""
    slug = re.sub(r"\s+", "-", (region or "").strip().lower())
    if not slug:
        return {"ok": False, "reason": "no region given"}
    if not month:
        month = _latest_month(slug)
        if not month:
            return {"ok": False, "reason": "could not resolve latest HPI month "
                    "(check region slug, e.g. 'london', 'east-of-england')"}
    url = f"{HPI}/{urllib.parse.quote(slug)}/month/{month}.json"
    try:
        d = _get_json(url)
    except urllib.error.HTTPError as e:
        return {"ok": False, "reason": f"UK HPI HTTP {e.code} (check region slug)"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    pt = d.get("result", {}).get("primaryTopic") or {}
    if not pt.get("averagePrice"):
        return {"ok": False, "reason": f"no HPI record for {slug} {month}"}

    def _num(key):
        v = pt.get(key)
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return {
        "ok": True, "region": slug, "month": month,
        "ref_period": pt.get("refPeriodStart"),
        "average_price": _num("averagePrice"),
        "index": _num("housePriceIndex"),
        "annual_change_pct": _num("percentageAnnualChange"),
        "monthly_change_pct": _num("percentageChange"),
        "source": "UK House Price Index (HM Land Registry, OGL)",
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "ppd":
        print(json.dumps(ppd_postcode(sys.argv[2]), indent=2, ensure_ascii=False))
    elif cmd == "hpi":
        month = sys.argv[3] if len(sys.argv) > 3 else None
        print(json.dumps(hpi_region(sys.argv[2], month), indent=2, ensure_ascii=False))
    elif cmd == "selftest":
        r = ppd_postcode("SE15 6JH")
        print("PPD SE15 6JH :", "ok" if r.get("ok") else r.get("reason"),
              "| count", r.get("count"), "| median", r.get("median"))
        h = hpi_region("london")
        print("HPI london   :", "ok" if h.get("ok") else h.get("reason"),
              "| avg", h.get("average_price"), "| yoy", h.get("annual_change_pct"))
    else:
        print("unknown command:", cmd); print(__doc__)


if __name__ == "__main__":
    main()
