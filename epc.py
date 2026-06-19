#!/usr/bin/env python3
"""epc.py - floor area + energy rating straight from the official EPC register.

Today the subject's floor area and EPC score arrive via PropertyData. This pulls them
INDEPENDENTLY from the official Energy Performance of Buildings register (DLUHC/MHCLG),
so the figures can be corroborated and gaps filled. The internal floor area
(`total-floor-area`, m2) firms up the GBP/sqm cross-check; the rating feeds the NTSELAT
Material-Information block. Area context beside the figure - it is NEVER an input to
valuation(); it only firms up `sqm`, which the engine already uses, and never overwrites
a value the primary source already carries (fill-only; see appraise.epc_firm_up).

REGISTER MIGRATION (verified 2026-06, per the live docs - read source before describing):
  * The legacy host `epc.opendatacommunities.org` now 301-redirects its docs/swagger/files
    to the replacement service. Its `/api/v1/domestic/search` endpoint (HTTP Basic auth,
    snake-case fields `total-floor-area` / `current-energy-efficiency`) is still documented
    in the current api.gov.uk catalogue, so the legacy path is kept as a fallback.
  * The replacement programmatic API is
    `https://api.get-energy-performance-data.communities.gov.uk/api/domestic/search`
    (Bearer-token auth; camelCase fields, e.g. `currentEnergyEfficiencyBand`; page_size /
    current_page pagination; 6000 req / 5 min). VERIFIED: the search response carries the
    EPC BAND (a letter) and address/uprn, but NOT the numeric score or floor area - those
    live on the single-certificate endpoint, whose field names are not yet verified, so we
    do not invent them. From the new API we firm up the RATING; floor area + numeric score
    come via the legacy search, whose field names ARE the stable, ecosystem-wide register
    column names (the same headers as the bulk CSV downloads).

Auth (read via the .env loader, never printed, never sent to a client):
  * Bearer (new API)  - EPC_TOKEN, or EPC_KEY when no EPC_EMAIL is set. Preferred.
  * Basic  (legacy)   - EPC_AUTH (pre-encoded base64 of "email:apikey"), or EPC_EMAIL +
                        EPC_KEY. Used when no bearer token is configured.
  * Neither set       -> {'ok': False, 'reason': 'EPC credentials not set'}. Built "ready
                        for key": it never raises and never blocks a valuation, exactly like
                        geo.py / police.py / land_registry.py.

Surfaces:
  for_postcode(postcode)        -> {ok, postcode, count, certificates:[...]}
  for_address(address, postcode)-> {ok, matched, address, rating, score, floor_area_sqm, ...}
  credentials_present()         -> bool (does any usable credential resolve?)

CLI:
  python epc.py postcode "SE15 6JH"
  python epc.py address "58 Cronin Street" "SE15 6JH"
  python epc.py selftest
"""
import os, sys, json, base64, re, urllib.parse, urllib.request, urllib.error
from pathlib import Path

# Legacy Basic-auth host (documented in the api.gov.uk catalogue; fallback) and the new
# Bearer-token register API (preferred when a token is configured).
API_LEGACY = "https://epc.opendatacommunities.org/api/v1/domestic/search"
API_NEW = "https://api.get-energy-performance-data.communities.gov.uk/api/domestic/search"
API = API_LEGACY                      # back-compat module constant
PUBLIC_BASE = "https://find-energy-certificate.service.gov.uk"
_UA = {"User-Agent": "honestly-epc/1.0 (+https://t.me/usehonestly_bot)"}
_CACHE_PATH = Path(__file__).with_name("data") / "epc_public_cache.json"


def _load_env():
    """Mirror maps_tools._load_env so the CLI/selftest can read .env standalone."""
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(here):
        with open(here, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def _auth():
    """Return the legacy Basic-auth header value, or None if no Basic credentials are
    configured. Accepts a pre-encoded EPC_AUTH, or builds it from EPC_EMAIL + EPC_KEY."""
    _load_env()
    pre = os.environ.get("EPC_AUTH")
    if pre:
        return pre if pre.lower().startswith("basic ") else f"Basic {pre}"
    email = os.environ.get("EPC_EMAIL")
    key = os.environ.get("EPC_KEY")
    if email and key:
        token = base64.b64encode(f"{email}:{key}".encode()).decode()
        return f"Basic {token}"
    return None


def _bearer():
    """Return the Bearer token for the new register API, or None. EPC_TOKEN/EPC_BEARER take
    precedence; otherwise EPC_KEY ALONE (no EPC_EMAIL) is treated as a bearer token, so the
    single 'EPC_KEY' credential named in the spec maps to the current API by default."""
    _load_env()
    tok = os.environ.get("EPC_TOKEN") or os.environ.get("EPC_BEARER")
    if tok:
        return tok.strip()
    if os.environ.get("EPC_KEY") and not os.environ.get("EPC_EMAIL"):
        return os.environ["EPC_KEY"].strip()
    return None


def _creds():
    """(scheme, authorization_header, base_url) for whichever credential is configured.
    Prefers the new Bearer register API; falls back to the legacy Basic-auth host. Returns
    ('none', None, None) when nothing usable is set."""
    tok = _bearer()
    if tok:
        return "bearer", f"Bearer {tok}", API_NEW
    basic = _auth()
    if basic:
        return "basic", basic, API_LEGACY
    return "none", None, None


def credentials_present():
    """True when a usable EPC credential (bearer or basic) resolves."""
    return _creds()[0] != "none"


def _get_json(url, auth, timeout=20):
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "Authorization": auth, **_UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "ignore")
    return json.loads(body) if body.strip() else {"rows": []}


def _num(v):
    """First number in a value like '79' or '79.5 m2', else None."""
    if v is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(v))
    return float(m.group()) if m else None


def _g(row, *keys):
    """First present, non-empty value among candidate keys (tolerates the legacy snake-case
    and the new camelCase field names without inventing either - a miss returns None)."""
    for k in keys:
        if isinstance(row, dict) and row.get(k) not in (None, ""):
            return row[k]
    return None


def _rows_of(d):
    """The certificate list from either register's response shape. Legacy returns
    {'rows': [...]}; the new API nests certificates under a different key plus a pagination
    object - so we take the first list found among the known candidate keys, or a top-level
    list, else None (an unexpected shape, surfaced honestly rather than guessed)."""
    if isinstance(d, list):
        return d
    if not isinstance(d, dict):
        return None
    for k in ("rows", "data", "results", "certificates", "assessments"):
        v = d.get(k)
        if isinstance(v, list):
            return v
    return None


def _addr_of(row):
    """Single-line address: the legacy `address`, else assembled from the new API's
    addressLine1-4 (+ postTown), else ''."""
    a = _g(row, "address", "addressLine1")
    if _g(row, "address"):
        return str(_g(row, "address")).strip()
    parts = [row.get(k) for k in ("addressLine1", "addressLine2", "addressLine3",
                                  "addressLine4", "postTown")]
    parts = [str(p).strip() for p in parts if p]
    return ", ".join(parts).strip() if parts else (str(a).strip() if a else "")


def _cert(row):
    """Normalise one register row to the fields the deliverables use, tolerating both the
    legacy snake-case and the new camelCase field names."""
    fa = _num(_g(row, "total-floor-area", "totalFloorArea", "total_floor_area"))
    sc = _num(_g(row, "current-energy-efficiency", "currentEnergyEfficiency",
                 "current_energy_efficiency"))
    rating = _g(row, "current-energy-rating", "currentEnergyEfficiencyBand",
                "currentEnergyRating", "current_energy_rating")
    pot = _g(row, "potential-energy-rating", "potentialEnergyEfficiencyBand",
             "potentialEnergyRating")
    return {
        "address": _addr_of(row),
        "postcode": str(_g(row, "postcode") or "").strip().upper(),
        "rating": (str(rating).strip().upper() or None) if rating else None,
        "potential_rating": (str(pot).strip().upper() or None) if pot else None,
        "score": int(sc) if sc is not None else None,          # 1-100 efficiency score
        "floor_area_sqm": round(fa) if fa is not None else None,
        "property_type": (str(_g(row, "property-type", "propertyType") or "").strip() or None),
        "built_form": (str(_g(row, "built-form", "builtForm") or "").strip() or None),
        "lodged": (str(_g(row, "lodgement-date", "registrationDate", "lodgementDate")
                       or "").strip() or None),
        "uprn": _g(row, "uprn"),
    }


def for_postcode(postcode, size=100, timeout=20):
    """Every lodged EPC certificate in a postcode (area fill / cross-check). Returns
    {ok, postcode, count, certificates:[...]} or {ok: False, reason}. Never raises."""
    pc = (postcode or "").strip()
    if not pc:
        return {"ok": False, "reason": "no postcode given"}
    scheme, auth, base = _creds()
    if scheme == "none":
        return {"ok": False, "reason": "EPC credentials not set"}
    # The two register hosts spell the page-size parameter differently.
    q = {"postcode": pc}
    q["page_size" if scheme == "bearer" else "size"] = min(int(size), 5000)
    url = f"{base}?" + urllib.parse.urlencode(q)
    try:
        d = _get_json(url, auth, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"ok": False, "reason": "EPC auth rejected"}
        if e.code == 404:
            return {"ok": True, "postcode": pc.upper(), "count": 0, "certificates": [],
                    "source": "Energy Performance of Buildings register (DLUHC/MHCLG, OGL)"}
        if e.code == 429:
            return {"ok": False, "reason": "EPC register rate-limited (429)"}
        return {"ok": False, "reason": f"EPC register HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    rows = _rows_of(d)
    if rows is None:
        return {"ok": False, "reason": "unexpected EPC response"}
    certs = [_cert(r) for r in rows]
    return {
        "ok": True, "postcode": pc.upper(), "count": len(certs),
        "certificates": certs,
        "source": "Energy Performance of Buildings register (DLUHC/MHCLG, OGL v3.0)",
    }


def _norm_addr(s):
    """Uppercase, drop punctuation, collapse spaces - for tolerant address matching."""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", (s or "").upper())).strip()


def _lead_number(s):
    """Leading building number/PAON token, e.g. '58' from '58 Cronin Street'. None if none."""
    m = re.match(r"\s*(\d+[A-Za-z]?)\b", s or "")
    return m.group(1).upper() if m else None


def _public_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"Accept": "text/html", **_UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    import html as _html
    return re.sub(r"\s+", " ", _html.unescape(s)).strip()


def _public_certificate(path_or_url, timeout=20):
    url = path_or_url if str(path_or_url).startswith("http") else PUBLIC_BASE + path_or_url
    try:
        page = _public_get(url, timeout=timeout)
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    text = _strip_html(page)
    fa = None
    m = re.search(r"Total floor area\s+(\d+(?:\.\d+)?)\s+square metres", text, re.I)
    if m:
        fa = round(float(m.group(1)))
    ptype = None
    m = re.search(r"Property type\s+(.+?)\s+Total floor area", text, re.I)
    if m:
        ptype = m.group(1).strip()
    rating = score = potential = None
    m = re.search(r"energy rating is\s+([A-G])\b", text, re.I)
    if m:
        rating = m.group(1).upper()
    m = re.search(r"energy rating is\s+[A-G]\s+with a score of\s+(\d+)", text, re.I)
    if m:
        score = int(m.group(1))
    m = re.search(r"potential energy rating of\s+([A-G])", text, re.I)
    if m:
        potential = m.group(1).upper()
    return {
        "ok": True, "matched": True, "rating": rating, "score": score,
        "potential_rating": potential, "floor_area_sqm": fa,
        "property_type": ptype, "built_form": None,
        "address": None, "postcode": None,
        "certificate_url": url,
        "source": "Find an energy certificate service (DLUHC/MHCLG public register)",
    }


def _cache_key(address, postcode):
    return f"{_norm_addr(address)}|{(postcode or '').strip().upper()}"


def _load_public_cache():
    try:
        if _CACHE_PATH.exists():
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_public_cache(cache):
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        pass


def _building_phrase(address):
    """Return a strict building/street phrase like '86 CHANDLER WAY'.

    Used only for public-EPC cache rescue when the user gives a building address but the
    certificates are flat-level, or when the supplied postcode is adjacent/wrong. This is
    still public EPC data, but the result is labelled as a building-level proxy.
    """
    norm = _norm_addr(address)
    toks = norm.split()
    # Drop common unit words before looking for the building number.
    skip = {"FLAT", "APARTMENT", "APT", "UNIT", "ROOM"}
    i = 0
    while i < len(toks) and toks[i] in skip:
        i += 2 if i + 1 < len(toks) else 1
    # Find first numeric token that is likely the building number.
    start = None
    for j in range(i, len(toks)):
        if re.fullmatch(r"\d+[A-Z]?", toks[j]):
            start = j
            break
    if start is None:
        return None
    parts = []
    for t in toks[start:]:
        if t in {"LONDON", "UK", "ENGLAND"} or re.fullmatch(r"[A-Z]{1,2}\d[A-Z]?", t):
            break
        parts.append(t)
        if len(parts) >= 5:
            break
    return " ".join(parts) if len(parts) >= 2 else None


def _public_cache_building_proxy(address, postcode=""):
    phrase = _building_phrase(address)
    if not phrase:
        return None
    cache = _load_public_cache()
    rows = []
    needle = f" {phrase} "
    for _key, val in cache.items():
        addr = _norm_addr(val.get("address") or _key)
        padded = f" {addr} "
        if needle in padded and val.get("floor_area_sqm"):
            rows.append(val)
    if not rows:
        return None
    import statistics as _statistics
    areas = sorted(int(r["floor_area_sqm"]) for r in rows if r.get("floor_area_sqm"))
    if not areas:
        return None
    ratings = [r.get("rating") for r in rows if r.get("rating")]
    rating = max(set(ratings), key=ratings.count) if ratings else None
    ptypes = [r.get("property_type") for r in rows if r.get("property_type")]
    ptype = max(set(ptypes), key=ptypes.count) if ptypes else None
    return {
        "ok": True,
        "matched": True,
        "building_proxy": True,
        "rating": rating,
        "score": None,
        "potential_rating": None,
        "floor_area_sqm": int(round(_statistics.median(areas))),
        "property_type": ptype,
        "built_form": None,
        "address": f"{phrase} (building-level public EPC median from {len(rows)} certificates)",
        "postcode": (postcode or "").strip().upper() or None,
        "certificate_url": rows[0].get("certificate_url"),
        "source": "Find an energy certificate service (DLUHC/MHCLG public register, building-level EPC proxy)",
        "certificate_count": len(rows),
        "area_values_sqm": areas,
    }


def _label_building(label):
    """Building/street key for a public-register label, e.g.
    'Flat 20, Bray Apartments, London, W3 7BB' -> 'BRAY APARTMENTS';
    '14 Acacia Road, London, W3 7BB' -> 'ACACIA ROAD'. Returns None when no stable
    building/street phrase remains (e.g. a bare number)."""
    toks = _norm_addr(_strip_html(label)).split()
    skip = {"FLAT", "APARTMENT", "APT", "UNIT", "ROOM", "FLOOR"}
    i = 0
    while i < len(toks) and (toks[i] in skip or re.fullmatch(r"\d+[A-Z]?", toks[i])):
        i += 1
    parts = []
    for t in toks[i:]:
        if t in {"LONDON", "UK", "ENGLAND"} or re.fullmatch(r"[A-Z]{1,2}\d[A-Z]?", t) or re.fullmatch(r"\d[A-Z]{2}", t):
            break
        parts.append(t)
    if len(parts) >= 2 and not all(re.fullmatch(r"\d+[A-Z]?", p) for p in parts):
        return " ".join(parts)
    return None


def _public_postcode_cluster_proxy(links, postcode, timeout=12, cache=None, max_fetch=12, want_no=None):
    """Fallback when no single certificate matches the subject: use the postcode's OWN public
    EPC certificates. If they form a coherent named-building cluster, return the median floor
    area as a labelled building-level proxy. This is real, free register data - never a model.

    This rescue is for a subject that is a flat in a name-registered building (e.g. 'Flat 12,
    Canaletto Tower') where the certificates are flat-level and no single one matches by number.
    It is NOT for a numbered street dwelling: when the subject carries a leading house number
    (want_no) and that number is absent from the register, collapsing the street's mixed houses
    into one median would be a wrong-size match - exactly the comp we must refuse. We return None
    so the caller honestly reports unmatched rather than inheriting a street median. A
    heterogeneous postcode (no dominant building) also returns None. Fetches a capped number of
    certificates live and caches them so repeat lookups are instant."""
    if not links:
        return None
    # A numbered street dwelling must resolve to its own certificate or report unmatched; we
    # never give house 999 the median size of the rest of the street.
    if want_no:
        return None
    if cache is None:
        cache = _load_public_cache()
    pc = (postcode or "").strip().upper()
    buildings = {}
    for href, label_html in links:
        bk = _label_building(_strip_html(label_html))
        if bk:
            buildings.setdefault(bk, []).append((href, _strip_html(label_html)))
    if not buildings:
        return None
    bk, members = max(buildings.items(), key=lambda kv: len(kv[1]))
    # require a real cluster that dominates the postcode, so a heterogeneous street is not
    # collapsed into one misleading median
    if len(members) < 3 or len(members) < 0.5 * len(links):
        return None
    areas, ptypes, ratings, dirty, fetched = [], [], [], False, 0
    for href, label in members:
        key = _cache_key(label, pc)
        row = cache.get(key)
        if not (row and row.get("floor_area_sqm")) and fetched < max_fetch:
            cert = _public_certificate(href, timeout=timeout)
            fetched += 1
            if cert.get("ok") and cert.get("floor_area_sqm"):
                cert.update({"address": label, "postcode": pc, "matched": True})
                cache[key] = cert; row = cert; dirty = True
        if row and row.get("floor_area_sqm"):
            areas.append(int(row["floor_area_sqm"]))
            if row.get("property_type"): ptypes.append(row["property_type"])
            if row.get("rating"): ratings.append(row["rating"])
        if len(areas) >= 8:
            break
    if dirty:
        _save_public_cache(cache)
    if len(areas) < 2:
        return None
    import statistics as _statistics
    areas_sorted = sorted(areas)
    rating = max(set(ratings), key=ratings.count) if ratings else None
    ptype = max(set(ptypes), key=ptypes.count) if ptypes else None
    return {
        "ok": True, "matched": True, "building_proxy": True, "postcode_cluster": True,
        "rating": rating, "score": None, "potential_rating": None,
        "floor_area_sqm": int(round(_statistics.median(areas_sorted))),
        "property_type": ptype, "built_form": None,
        "address": f"{bk} (building-level public EPC median from {len(areas_sorted)} certificates)",
        "postcode": pc or None,
        "certificate_url": members[0][0] if members else None,
        "source": "Find an energy certificate service (DLUHC/MHCLG public register, building-level EPC proxy)",
        "certificate_count": len(areas_sorted),
        "area_values_sqm": areas_sorted,
    }


def public_for_address(address, postcode, timeout=20):
    """No-key public EPC website fallback. Returns the same shape as for_address().

    Successful public-register matches are cached locally. The public GOV.UK service can
    throttle repeated scraping; a cached public certificate is better than degrading a
    known floor area to a modelled estimate.
    """
    pc = (postcode or "").strip()
    if not pc:
        return {"ok": False, "reason": "no postcode given"}
    key = _cache_key(address, pc)
    cache = _load_public_cache()
    if key in cache:
        return dict(cache[key])
    proxy = _public_cache_building_proxy(address, pc)
    if proxy:
        return proxy
    try:
        url = PUBLIC_BASE + "/find-a-certificate/search-by-postcode?" + urllib.parse.urlencode({"postcode": pc})
        page = _public_get(url, timeout=timeout)
    except Exception as e:
        if key in cache:
            return dict(cache[key])
        proxy = _public_cache_building_proxy(address, pc)
        if proxy:
            return proxy
        return {"ok": False, "reason": str(e)[:120]}
    links = re.findall(r'<a[^>]+href="(/energy-certificate/[^"]+)"[^>]*>([\s\S]*?)</a>', page, re.I)
    if not links:
        proxy = _public_cache_building_proxy(address, pc)
        if proxy:
            return proxy
        return {"ok": True, "matched": False, "postcode": pc.upper(), "reason": "no public EPC certificates in postcode",
                "source": "Find an energy certificate service (DLUHC/MHCLG public register)"}
    want = _norm_addr(address)
    want_no = _lead_number(address)
    want_tokens = set(want.split())
    best = None
    best_score = 0.0
    for href, label_html in links:
        label = _strip_html(label_html)
        cand = _norm_addr(label)
        cand_no = _lead_number(label)
        if want_no and cand_no and want_no != cand_no:
            continue
        ctoks = set(cand.split())
        overlap = len(want_tokens & ctoks)
        score = overlap + (5 if want_no and cand_no == want_no else 0)
        if score > best_score:
            best_score = score; best = (href, label)
    if not best or best_score < 4:
        proxy = _public_cache_building_proxy(address, pc)
        if proxy:
            return proxy
        # No single cert matches (e.g. subject given as a street address but the building is
        # name-registered as flats). Use the postcode's own public certificates - free register
        # data - rather than degrading the subject size to a model.
        proxy = _public_postcode_cluster_proxy(links, pc, timeout=timeout, cache=cache, want_no=want_no)
        if proxy:
            return proxy
        return {"ok": True, "matched": False, "postcode": pc.upper(), "reason": "no confident public EPC address match",
                "source": "Find an energy certificate service (DLUHC/MHCLG public register)"}
    cert = _public_certificate(best[0], timeout=timeout)
    if cert.get("ok"):
        cert.update({"address": best[1], "postcode": pc.upper(), "matched": True})
        if cert.get("floor_area_sqm"):
            cache[key] = cert
            _save_public_cache(cache)
    return cert


def for_address(address, postcode, timeout=20):
    """Best EPC certificate for a specific address in a postcode. Matches on the leading
    building number plus token overlap - honest about confidence, never guesses silently.
    Returns {ok, matched, ...} where matched is False when no confident row is found.
    Never raises."""
    base = for_postcode(postcode, timeout=timeout)
    if not base.get("ok"):
        # Public no-key fallback. This is slower than the API but free and user-visible.
        pub = public_for_address(address, postcode, timeout=timeout)
        return pub if pub.get("ok") else base
    certs = base["certificates"]
    if not certs:
        pub = public_for_address(address, postcode, timeout=timeout)
        if pub.get("ok") and pub.get("matched"):
            return pub
        return {"ok": True, "matched": False, "postcode": base["postcode"],
                "reason": "no certificates in postcode", "source": base["source"]}

    want = _norm_addr(address)
    want_no = _lead_number(address)
    want_tokens = set(want.split())
    best, best_score = None, 0.0
    for c in certs:
        cand = _norm_addr(c["address"])
        cand_no = _lead_number(c["address"])
        # building number is the strong key; require it to agree when both have one
        if want_no and cand_no and want_no != cand_no:
            continue
        tokens = set(cand.split())
        overlap = len(want_tokens & tokens) / max(1, len(want_tokens))
        score = overlap + (0.5 if (want_no and cand_no and want_no == cand_no) else 0.0)
        if score > best_score:
            best, best_score = c, score

    # confident only with a number match or strong token overlap; else report unmatched
    confident = best is not None and (best_score >= 1.0 or
                                      (want_no and _lead_number(best["address"]) == want_no))
    if not confident:
        pub = public_for_address(address, postcode, timeout=timeout)
        if pub.get("ok") and pub.get("matched"):
            return pub
        return {"ok": True, "matched": False, "postcode": base["postcode"],
                "reason": "no confident address match", "candidates": len(certs),
                "source": base["source"]}
    out = dict(best)
    out.update({"ok": True, "matched": True, "match_score": round(best_score, 2),
                "source": base["source"]})
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "postcode":
        print(json.dumps(for_postcode(sys.argv[2]), indent=2, ensure_ascii=False))
    elif cmd == "address":
        print(json.dumps(for_address(sys.argv[2], sys.argv[3]), indent=2, ensure_ascii=False))
    elif cmd == "selftest":
        scheme = _creds()[0]
        if scheme == "none":
            print("epc selftest: no credentials set - degraded path is the live behaviour here.")
            r = for_postcode("SE15 6JH")
            print("  for_postcode ->", "ok" if r.get("ok") else r.get("reason"))
            print("  client is built and ready; provide EPC_TOKEN (new API) or EPC_EMAIL+"
                  "EPC_KEY (legacy) to go live.")
            return
        print(f"epc selftest: credential scheme = {scheme} "
              f"({'new Bearer register API' if scheme == 'bearer' else 'legacy Basic-auth host'})")
        r = for_postcode("SE15 6JH")
        print("for_postcode SE15 6JH:", "ok" if r.get("ok") else r.get("reason"),
              "| count", r.get("count"))
        a = for_address("58 Cronin Street", "SE15 6JH")
        print("for_address 58 Cronin Street:",
              ("matched | EPC " + str(a.get("rating")) + " | " + str(a.get("floor_area_sqm")) + " sqm")
              if a.get("matched") else ("unmatched: " + str(a.get("reason"))))
    else:
        print("unknown command:", cmd); print(__doc__)


if __name__ == "__main__":
    main()
