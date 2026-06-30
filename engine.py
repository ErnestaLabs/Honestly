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
from appraise import (money, round_to, postcode_of, txn_link, tuid_of,
                      listing_link, pos_loc, apply_market, sold_median,
                      guide_price, DATESTR)
from macro import outlook

# ---------------------------------------------------------------- core
def _autostore(result, tier, source="engine.value"):
    """Best-effort: persist EVERY valuation run so the value is stored and kept updated.

    The honesty/persistence contract the user asked for - 'everytime we run a valuation
    store value and update'. Keyed on a DETERMINISTIC token (address + product tier), so a
    re-run of the same valuation UPDATES the row in place (store.record_appraisal does
    INSERT OR REPLACE on the token) rather than piling up duplicates. The full
    engine.summary() payload is stored alongside the four headline figures for training +
    legal, exactly like the bot's delivery path.

    Gated by HONESTLY_AUTOSTORE so it fires on the production entrypoints (bot, web server,
    CLI) but never in the offline test suite. Never raises into the valuation path - a
    failure to persist must never cost a user their figure."""
    try:
        if os.environ.get("HONESTLY_AUTOSTORE", "").strip().lower() not in ("1", "true", "yes", "on"):
            return
        if not isinstance(result, dict) or not result.get("subject"):
            return
        import store, hashlib
        subj = result["subject"]
        addr = subj.get("address")
        if not addr:
            return
        # The figure (low/high/central/guide) is audience-independent, so the canonical log
        # row is built once with a neutral audience; audience-specific delivery rows are still
        # written separately by the bot. tier drives which BESIDE-the-figure context renders.
        d = summary(result, audience="vendor", tier=tier)
        token = "v_" + hashlib.sha1(f"{addr}|{tier}".encode("utf-8")).hexdigest()[:22]
        store.record_appraisal(d, token=token, tier=tier, finish=result.get("finish"),
                               source=source, investment=subj.get("investment"))
    except Exception:
        pass


def _apply_quant_valuation(r):
    """Overlay the UKQuantValuator on top of the existing engine result.

    Replaces central/low/high/guide and confidence with quant-derived values.
    Preserves all other keys so PDF/API/bot surfaces work unchanged.
    """
    from uk_quant import UKQuantValuator, EPC_CONDITION_MULTIPLIER
    s, v = r["subject"], r["valuation"]
    comps = r.get("compsA") or []
    # Build strict comp list in the format UKQuantValuator expects
    strict_comps = []
    for c in comps:
        if not c.get("strict_comparable"):
            continue
        dist_m = c.get("dist")
        # dist is in metres from the engine; convert to miles
        dist_mi = (dist_m / 1609.34) if dist_m is not None else None
        strict_comps.append({
            "address": c.get("address", ""),
            "price": c.get("price", 0),
            "date": c.get("date", ""),
            "sqm": c.get("sqm"),
            "dist": dist_mi,
            "ptype": c.get("pdtype"),
            "postcode": c.get("postcode"),
        })
    # If no strict comps flagged, use the top-scored comps
    if not strict_comps and comps:
        for c in sorted(comps, key=lambda x: -(x.get("score") or 0))[:10]:
            dist_m = c.get("dist")
            dist_mi = (dist_m / 1609.34) if dist_m is not None else None
            strict_comps.append({
                "address": c.get("address", ""),
                "price": c.get("price", 0),
                "date": c.get("date", ""),
                "sqm": c.get("sqm"),
                "dist": dist_mi,
                "ptype": c.get("pdtype"),
                "postcode": c.get("postcode"),
            })
    # Get HPI data
    hpi_current = None
    hpi_prev_3m = None
    hpi_at_last_sold = None
    try:
        import macro
        region = (s.get("lite_basis") or {}).get("country") or "london"
        hpi_current = macro.hpi_latest(region)
        hpi_prev_3m = macro.hpi_at(region, months_ago=3)
        if s.get("last_sold_date"):
            hpi_at_last_sold = macro.hpi_at_date(region, s["last_sold_date"])
    except Exception:
        pass
    # If macro module doesn't have those functions, try from the formula evidence
    if hpi_current is None:
        try:
            mk = v.get("market") or {}
            hpi_current = mk.get("hpi_index")
        except Exception:
            pass

    qv = UKQuantValuator(
        subject_address=s.get("address", ""),
        subject_sqm=s.get("sqm") or 80,
        subject_epc=s.get("epc"),
        subject_last_sold_price=s.get("last_sold"),
        subject_last_sold_date=s.get("last_sold_date"),
        subject_lat=s.get("lat"),
        subject_lng=s.get("lng"),
        strict_comps=strict_comps,
        hpi_current=hpi_current,
        hpi_prev_3m=hpi_prev_3m,
        hpi_at_last_sold=hpi_at_last_sold,
    )
    qr = qv.value()
    # Overlay quant results onto the existing valuation dict
    v["low"] = qr["low"]
    v["high"] = qr["high"]
    v["central"] = qr["central"]
    v["guide"] = qr["guide"]
    v["quant"] = qr  # full quant derivation for the glass box
    v["quant_version"] = qr["derivation"]["formula_version"]
    # Update formula to include quant derivation
    if v.get("formula"):
        v["formula"]["quant_derivation"] = qr["derivation"]
        v["formula"]["name"] = qr["derivation"]["formula_name"]
    return r


def value(address, key=None, beds=None, baths=1, finish="average",
          investment=False, ptype=None, radius=0.5, maxage=24, tier="lite", sqm=None):
    """The engine router. Returns one structured result - the single source of truth
    every audience view reads from. No view ever recomputes a number.

    One public data spine, two product tiers. The valuation figure is always anchored on
    direct/public evidence: HM Land Registry Price Paid rows, EPC where available,
    Postcodes.io/ONS geography and our own transparent calculations. `tier` controls the
    surrounding deliverable, not a different paid data feed.
    """
    product_tier = "pro" if str(tier).strip().lower() == "pro" else "lite"
    r = lite_value(address, beds=beds, baths=baths, finish=finish,
                   investment=investment, ptype=ptype, sqm=sqm, key=key)
    r["product_tier"] = product_tier
    # ── Quant valuation: Pro tier only. Lite uses the strict lite_value math directly. ──
    if product_tier == "pro":
        try:
            r = _apply_quant_valuation(r)
        except Exception:
            pass
    _autostore(r, "lite" if product_tier == "lite" else "pro")
    return r


# ---------------------------------------------------------------- free public-data engine
# HM Land Registry Price Paid property-type label -> our pdtype slug. 'other' is
# commercial / non-residential and is dropped, so a Lite figure stays a homes figure.
_HMLR_LITE_TYPE = {
    "flat-maisonette": "flat",
    "terraced": "terraced_house",
    "semi-detached": "semi_detached_house",
    "detached": "detached_house",
}
_PDTYPE_LABEL = {"flat": "flats", "terraced_house": "terraced houses",
                 "semi_detached_house": "semi-detached houses",
                 "detached_house": "detached houses"}
# Recency windows for the free figure. P0 rule: one year is ideal; two years is the
# Comparable geography: 0.5mi is the ideal/default radius. If there are no usable
# same-type HMLR sales inside 0.5mi in the last 12 months, radius may expand cautiously
# to 1mi, with explicit disclosure and lower confidence. Expansion is never permission
# to cross obvious micro-market/barrier/catchment boundaries where those are known.
_LITE_WINDOWS = (12, 24)
_LITE_MIN_COMPS = 5
_LITE_MIN_STRICT_COMPS = 5
_LITE_BASE_RADIUS_M = 500       # ~0.31 miles - tight default comparable radius (2-3 blocks)
_LITE_EXPANDED_RADIUS_M = 805  # ~0.5 miles absolute max for London/dense urban
_LITE_MAX_COMP_RADIUS_M = 500
_LITE_MAX_EXPANDED_COMP_RADIUS_M = 805
_LITE_SIMILAR_PRICE_PCT = 0.30  # comparable must sit within +/-30% of the anchor price
_LITE_AREA_TOLERANCE_STRICT = 0.15   # default: floor area within 15% (hard cap)
_LITE_AREA_TOLERANCE_RELAXED = 0.20  # relaxed: when strict < 5, area within 20%
_LITE_AREA_TOLERANCE_WIDE = 0.25    # wide: last-resort rescue, area within 25% (never exceed)
# Recency as weight (never an HPI price move): a recent sale dictates the figure harder
# than an older sale, but anything over 24 months is not valuation evidence.
def _lite_weight(date_str):
    try:
        import datetime as _dt
        d = _dt.date.fromisoformat(str(date_str)[:10])
        months = (_dt.date.today() - d).days / 30.44
    except Exception:
        return 0.0
    if months <= 6:   return 1.0
    if months <= 12:  return 0.85
    if months <= 24:  return 0.55
    return 0.0

def _pctl(sorted_xs, q):
    """The q-th percentile (0-100) of an already-sorted list, linear interpolation."""
    if not sorted_xs:
        return None
    if len(sorted_xs) == 1:
        return sorted_xs[0]
    pos = (len(sorted_xs) - 1) * (q / 100.0)
    lo = int(pos); hi = min(lo + 1, len(sorted_xs) - 1)
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo)

def _infer_pdtype(address, ptype):
    """Best honest guess at the subject's property type for filtering the sold evidence.
    Explicit ptype wins; otherwise read the address. None when we cannot tell - the figure
    is then built across all residential types and disclosed as such."""
    if ptype:
        p = str(ptype).lower()
        if "flat" in p or "maison" in p or "apart" in p:  return "flat"
        if "terrace" in p:                                return "terraced_house"
        if "semi" in p:                                   return "semi_detached_house"
        if "detached" in p:                               return "detached_house"
    a = (address or "").lower()
    if any(t in a for t in ("flat ", "apartment", "maisonette", "apt ")):
        return "flat"
    return None


def _epc_type_to_slug(property_type, built_form):
    """Map an EPC register row's property_type + built_form onto our HMLR-Lite type slug.
    Order matters: 'detached' is a substring of 'semi-detached', so semi is tested first."""
    pt = (property_type or "").strip().lower()
    bf = (built_form or "").strip().lower()
    if "flat" in pt or "maison" in pt or "apart" in pt:
        return "flat"
    if "house" in pt or "bungalow" in pt:
        if "semi" in bf:                          return "semi_detached_house"
        if "detached" in bf:                      return "detached_house"
        if "terrace" in bf or "enclosed" in bf:   return "terraced_house"
    return None


def _epc_subject(address, postcode):
    """Official EPC record for the subject, when available. Direct public register path.
    It can confirm type and floor area. Missing EPC lowers confidence; it never blocks
    the first value."""
    try:
        import epc
        c = epc.for_address(address, postcode, timeout=12)
        return c if c.get("ok") and c.get("matched") else None
    except Exception:
        return None


def _epc_pdtype(address, postcode):
    c = _epc_subject(address, postcode)
    return _epc_type_to_slug(c.get("property_type"), c.get("built_form")) if c else None


def _area_match(subject_sqm, comp_sqm, tolerance=0.15):
    """Best-effort floor-area similarity signal.

    Default is tight (±15%). Comparable rescue may use ±20%, still inside the
    valuer-style tolerance band from the operational directive.
    """
    try:
        subject_sqm, comp_sqm = float(subject_sqm), float(comp_sqm)
    except Exception:
        return False
    if subject_sqm <= 0 or comp_sqm <= 0:
        return False
    return abs(comp_sqm - subject_sqm) <= max(15.0, subject_sqm * float(tolerance))


def _infer_beds_from_area(ptype, sqm):
    """Infer bedroom count from type+area when public sold rows lack beds.

    This is a labelled rescue signal, not an official fact. It prevents zero-comparable
    failure when public data provides type/area/sale but not bedrooms.
    """
    try:
        sqm = float(sqm)
    except Exception:
        return None
    if sqm <= 0:
        return None
    if (ptype or "").startswith("flat"):
        if sqm < 50: return 1
        if sqm < 85: return 2
        if sqm < 120: return 3
        return 4
    if sqm < 75: return 2
    if sqm < 110: return 3
    if sqm < 155: return 4
    return 5


_AREA_PRIORS_SQM = {
    "flat": 62,
    "terraced": 92,
    "semidetached": 105,
    "detached": 140,
}


def _set_floor_area(row, sqm, source, status="official_exact", rating=None):
    if sqm:
        row["sqm"] = int(round(float(sqm)))
        row["floor_area_sqm"] = row["sqm"]
        row["sqm_source"] = source
        row["floor_area_source"] = source
        row["floor_area_status"] = status
        row["floor_area_official"] = status.startswith("official") and status != "official_nearby_model"
        if rating:
            row["epc_rating"] = rating


def _model_floor_area(ptype=None, subject_sqm=None, local_median=None):
    if local_median:
        try:
            return int(round(float(local_median)))
        except Exception:
            pass
    if subject_sqm:
        try:
            return int(round(float(subject_sqm)))
        except Exception:
            pass
    return int(_AREA_PRIORS_SQM.get(ptype or "flat", 75))


def _attach_epc_floor_areas(sales, postcodes):
    """Attach a floor area to every HMLR row.

    Order:
      1) official EPC API exact postcode/address match when credentials exist;
      2) no-key public EPC website exact certificate match;
      3) modelled fill handled later after the final evidence pool is known.

    This function never returns a row with a fake official area. Exact areas carry
    floor_area_status=official_*; modelled values are labelled modelled and are not used
    as same-size valuation anchors.
    """
    try:
        import epc
    except Exception:
        return sales, "EPC unavailable"
    by_pc = {}
    if getattr(epc, "credentials_present", lambda: False)():
        for pc0 in list(dict.fromkeys(p for p in postcodes if p))[:80]:
            try:
                e = epc.for_postcode(pc0, timeout=10)
            except Exception:
                continue
            if e.get("ok"):
                by_pc[pc0.upper()] = e.get("certificates") or []
    for s in sales:
        certs = by_pc.get((s.get("postcode") or "").upper()) or []
        for c in certs:
            if c.get("floor_area_sqm") and _sale_matches_subject(s.get("address") or "", c.get("address") or ""):
                _set_floor_area(s, c.get("floor_area_sqm"), "EPC register", "official_exact", c.get("rating"))
                break
    # No-key public EPC fallback. This is exact-address only and cached by address+postcode.
    # CAP: only attempt EPC lookups for the first N rows without sqm, to avoid 50-100+
    # API calls per valuation that hit rate limits and cause timeouts. The remaining
    # rows get modelled areas later via _fill_modelled_floor_areas.
    _MAX_PUBLIC_EPC_LOOKUPS = 20
    public_cache = {}
    lookups = 0
    for s in sales:
        if s.get("sqm") or not s.get("address") or not s.get("postcode"):
            continue
        if lookups >= _MAX_PUBLIC_EPC_LOOKUPS:
            break
        key = ((s.get("address") or "").upper(), (s.get("postcode") or "").upper())
        if key not in public_cache:
            try:
                public_cache[key] = epc.public_for_address(s.get("address"), s.get("postcode"), timeout=5)
                lookups += 1
            except Exception as e:
                public_cache[key] = {"ok": False, "reason": str(e)[:80]}
        c = public_cache[key]
        if c.get("ok") and c.get("matched") and c.get("floor_area_sqm"):
            _set_floor_area(s, c.get("floor_area_sqm"), "public EPC register", "official_public_exact", c.get("rating"))
    return sales, "Energy Performance of Buildings register / public EPC register"



def _fill_modelled_floor_areas(rows, subject_sqm=None, pdtype=None):
    exact = [r.get("sqm") for r in rows if r.get("sqm") and r.get("floor_area_official")]
    local_median = statistics.median(exact) if exact else None
    for r in rows:
        if r.get("sqm"):
            continue
        sqm = _model_floor_area(r.get("pdtype") or pdtype, subject_sqm=subject_sqm, local_median=local_median)
        _set_floor_area(r, sqm, "Honestly floor-area model", "modelled", r.get("epc_rating"))
    return rows


_FINISH_RULES = {
    "needs_renovation": {"low": "q1 * 0.88", "central": "median * 0.90", "high": "median * 0.98"},
    "needs_modernising": {"low": "q1 * 0.94", "central": "median * 0.96", "high": "q3"},
    "average": {"low": "q1", "central": "median", "high": "q3"},
    "high": {"low": "median * 1.05", "central": "mean(low, high)", "high": "max(q3, median * 1.14)"},
    "very_high": {"low": "median * 1.08", "central": "max(q3, median * 1.16)", "high": "max(q3 * 1.04, median * 1.22)"},
}
_HISTORY_FINISH_FACTORS = {
    "needs_renovation": 0.92,
    "needs_modernising": 1.02,
    "average": 1.18,
    "high": 1.35,
    "very_high": 1.48,
}


def _lite_finish_prices(raw_med, raw_q1, raw_q3, finish):
    """Condition-adjust Lite prices without pretending condition is a public fact.

    The user-provided condition signal moves the range. Average uses the raw comparable
    centre. High finish lifts the median toward the upper evidence. Very-high uses the
    upper evidence as the anchor. This mirrors the Cronin appraisal logic without using
    the subject's old sale as a comp.
    """
    f = (finish or "average").strip().lower()
    raw_q1 = raw_q1 if raw_q1 is not None else raw_med * 0.92
    raw_q3 = raw_q3 if raw_q3 is not None else raw_med * 1.08
    if f == "needs_renovation":
        low, central, high = raw_q1 * 0.88, raw_med * 0.90, raw_med * 0.98
    elif f == "needs_modernising":
        low, central, high = raw_q1 * 0.94, raw_med * 0.96, raw_q3
    elif f == "high":
        low = raw_med * 1.05
        high = max(raw_q3, raw_med * 1.14)
        central = (low + high) / 2
    elif f == "very_high":
        low, central, high = raw_med * 1.08, max(raw_q3, raw_med * 1.16), max(raw_q3 * 1.04, raw_med * 1.22)
    else:
        low, central, high = raw_q1, raw_med, raw_q3
    return low, central, high


def _sale_matches_subject(address, sale_address):
    """True when an HMLR sale row is the subject property itself.

    The subject's own previous sale is property history, not a comparable. Using it as a
    comp is fatal: it can be old, stale, and circular. Match conservatively on PAON/street
    and, where supplied, unit/flat token. If the user gives only a building-level address
    like '11 Shadwell Gardens', the building sale row '11, SHADWELL GARDENS' is excluded.
    """
    import re as _re
    def _norm(s):
        return _re.sub(r"\s+", " ", (s or "").strip().lower())
    def _parts(s):
        s = _norm(s)
        s = _re.sub(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b", "", s, flags=_re.I)
        toks = [_norm(t) for t in _re.split(r",|\n", s) if _norm(t)]
        joined = " ".join(toks)
        unit = None
        mu = _re.search(r"\b(?:flat|apartment|apt|unit)\s*([0-9a-z]+)\b", joined)
        if mu:
            unit = mu.group(1)
        paon = street = None
        for t in toks or [joined]:
            m = _re.match(r"^(?:flat\s+[0-9a-z]+\s+)?([0-9]+[a-z]?)\s+(.+)$", t)
            if m:
                paon, street = m.group(1), m.group(2)
                break
        if not paon:
            # HMLR format often splits as 'FLAT 2, 11, STREET, TOWN'
            for i, t in enumerate(toks):
                if _re.fullmatch(r"[0-9]+[a-z]?", t):
                    paon = t
                    street = toks[i + 1] if i + 1 < len(toks) else ""
                    break
        street_key = _re.sub(r"[^a-z0-9]", "", (street or "").split(" london")[0])
        return unit, paon, street_key
    su, sp, ss = _parts(address)
    ru, rp, rs = _parts(sale_address)
    if not sp or not rp or sp != rp:
        return False
    if ss and rs and not (ss in rs or rs in ss):
        return False
    if su or ru:
        return bool(su and ru and su == ru)
    return True


def _hmlr_subject_type(address, sales):
    """The DEFINITIVE answer to 'what is this property': its own record in HM Land Registry,
    the statutory register of property in England and Wales. If this exact address has ever
    transacted, the register recorded its type (Detached / Semi-detached / Terraced / Flat).
    We match the subject's house number (PAON) - and unit/flat designator (SAON) when it has
    one - against the sold rows for its postcode. An exact unit match returns that type; a
    building whose sold units are unanimous in type returns that type (the building is that
    stock); a genuinely mixed building stays unresolved. This is the register telling us what
    the property IS, so it OUTRANKS an address-string guess. Returns a slug or None."""
    if not address or not sales:
        return None
    import re as _re
    def _norm(s):
        return _re.sub(r"\s+", " ", (s or "").strip().lower())
    # subject unit (flat/apartment/unit N) and building number (PAON)
    saon = None
    mu = _re.search(r"\b(?:flat|apartment|apt|unit)\s*([0-9a-z]+)", _norm(address))
    if mu:
        saon = "flat " + mu.group(1)
    paon = street = None
    for seg in [p.strip() for p in address.split(",")][:2]:
        m = _re.match(r"^([0-9]+[a-z]?)\s+(.+)$", _norm(seg))
        if m:
            paon, street = m.group(1), _norm(m.group(2))
            break
    if not paon:
        return None
    paon_k = _re.sub(r"[^0-9a-z]", "", paon)
    street_head = street.split()[0] if street else ""
    matched = []
    for s in sales:
        slug = _HMLR_LITE_TYPE.get((s.get("type") or "").strip().lower())
        if not slug:
            continue
        toks = [_norm(t) for t in (s.get("address") or "").split(",")]
        # the PAON is the pure building-number token (e.g. "58", "12a") - a unit token like
        # "flat 3" also carries a digit, so match the number token specifically, not any digit.
        s_i = next((i for i, t in enumerate(toks) if _re.fullmatch(r"[0-9]+[a-z]?", t)), None)
        if s_i is None or toks[s_i] != paon_k:
            continue
        rest = " ".join(toks[s_i + 1:])
        if street_head and street_head not in rest:        # guard a multi-street postcode
            continue
        s_saon = toks[0] if s_i >= 1 else None
        if saon and s_saon and saon == s_saon:
            return slug                                     # exact unit match - definitive
        matched.append(slug)
    if matched and len(set(matched)) == 1:
        return matched[0]                                   # the building is one stock
    return None


def _hmlr_subject_sale(address, sales):
    """Newest HMLR sale row for the subject itself.

    This is not a comparable and must never enter compsA. It is subject history: useful for
    a free-data fallback when public EPC/floor-area data is unavailable.
    """
    rows = []
    for s in sales or []:
        if _sale_matches_subject(address, s.get("address") or "") and s.get("price") and s.get("date"):
            try:
                rows.append({"address": s.get("address"), "price": int(s["price"]),
                             "date": (s.get("date") or "")[:10], "hmlr_uri": s.get("hmlr_uri"),
                             "source": "HM Land Registry subject sale history"})
            except Exception:
                pass
    return sorted(rows, key=lambda r: r["date"], reverse=True)[0] if rows else None


def _lite_history_estimate(subject_history, region, finish):
    """Free-data fallback: subject's own HMLR sale indexed by HMLR HPI + condition.

    The subject's own sale is never used as a comparable. When EPC/floor-area is missing,
    this prevents the engine from pretending generic small-flat comps describe a larger
    maisonette. It is a transparent history model, then sanity-checked beside current sold
    evidence.
    """
    if not subject_history or not subject_history.get("price") or not subject_history.get("date"):
        return None
    try:
        import land_registry
        sale_month = str(subject_history["date"])[:7]
        h0 = land_registry.hpi_region(region or "london", sale_month)
        h1 = land_registry.hpi_region(region or "london")
        if not (h0.get("ok") and h1.get("ok") and h0.get("index") and h1.get("index")):
            return None
        base = float(subject_history["price"]) * float(h1["index"]) / float(h0["index"])
    except Exception:
        return None
    f = (finish or "average").strip().lower()
    factor = _HISTORY_FINISH_FACTORS.get(f, _HISTORY_FINISH_FACTORS["average"])
    central = base * factor
    if f == "high":
        low, high = central * 0.98, central * 1.09
    elif f == "very_high":
        low, high = central * 0.96, central * 1.10
    else:
        low, high = central * 0.90, central * 1.10
    return {
        "base_hpi": round_to(base, 5000),
        "condition_factor": factor,
        "central": round_to(central, 5000),
        "low": round_to(low, 5000),
        "high": round_to(high, 5000),
        "sale_price": subject_history["price"],
        "sale_date": subject_history["date"],
        "hpi_from": h0.get("month"),
        "hpi_to": h1.get("month"),
        "source": "HM Land Registry subject sale + HM Land Registry UK HPI",
    }


def _LITE_TYPE_NOTE(type_source, pdtype):
    """One disclosed sentence on HOW we determined the subject's type for the free figure -
    the honest difference between a confirmed type and an assumed one."""
    label = _PDTYPE_LABEL.get(pdtype, pdtype)
    one = label[:-1] if label and label.endswith("s") else label
    if type_source == "hmlr_register":
        return (f" HM Land Registry's own record of this address - the statutory register of "
                f"property in England and Wales - shows it is a {one}, so we valued it against "
                f"{label} only.")
    if type_source == "epc_register":
        return (f" We confirmed this property is a {label[:-1] if label and label.endswith('s') else label} "
                f"from its entry on the official EPC register, and valued it against {label} only.")
    if type_source == "address":
        return f" We read its type from the address and valued it against {label} only."
    if type_source == "postcode_dominant":
        return (f" {label[:1].upper()}{label[1:]} are the predominant property type at this postcode, "
                f"so we valued it as one - if yours is a different type, tell us and we will re-run it.")
    if type_source == "address_thin":
        return (f" Too few {label} are on file to value against alone, so this spans all "
                f"residential types at this postcode.")
    return (" We could not confirm this property's type, so the figure spans all residential "
            "types at this postcode - tell us the type (flat, terraced, semi or detached) for "
            "a sharper figure.")

def lite_value(address, beds=None, baths=1, finish="average", investment=False, ptype=None, sqm=None, key=None):
    """The FREE Lite valuation - sold evidence straight from the official HM Land Registry
    Price Paid register (OGL, no key, no paid credits). Never calls a commercial data feed.

    Honest by construction, and disclosed as such: the free register carries the sale price,
    date, address and property type, but NO guaranteed floor area and NO AVM. So this is
    a sold-comparable figure at postcode/type grade - what comparable homes nearby actually
    sold for - with EPC/floor area used when we can fetch it, never as an upfront gate.
    England & Wales only; Scotland/NI sales are held by other registers the free feed does
    not cover.

    Returns the SAME result shape as the paid engine so engine.summary() renders it
    unchanged (Pro-only sections simply stay gated off for Lite)."""
    import geo, land_registry
    pc = postcode_of(address)
    if not pc:
        sys.exit("I could not read a UK postcode from that address - add the full postcode "
                 "(e.g. 'SE15 6JH') and I'll value it from the sold record.")

    g = geo.lookup(pc)
    country = (g.get("country") if g.get("ok") else "") or ""
    lat = g.get("lat") if g.get("ok") else None
    lng = g.get("lng") if g.get("ok") else None
    outcode = (g.get("outcode") if g.get("ok") else "") or pc.split()[0]
    if country and country.strip().lower() not in ("england", "wales"):
        sys.exit(f"Honestly valuations currently cover England and Wales, where HM Land Registry "
                 f"publishes Price Paid Data openly. {country} uses a separate sold-price "
                 f"register, so this address is not supported yet.")

    # Resolve the subject's property type as confidently as we can, because valuing a house
    # against an area's flats (or vice versa) is the single biggest error the free tier can
    # make. Order of authority: HM Land Registry's OWN record of this address (the statutory
    # register - definitive), then the official EPC register (address-matched), then the
    # address string, then a postcode-dominant prior below. Provenance is recorded so the
    # disclosure is honest. A loose address-string read is only a placeholder until the
    # register speaks.
    pdtype = _infer_pdtype(address, ptype)
    type_source = "address" if pdtype else None

    # 1) the exact postcode first (tightest comparables AND the subject's own HMLR record).
    raw = []
    pc_types = []                                   # type mix of the EXACT postcode (a prior)
    pp = land_registry.ppd_postcode(pc, use_cache=True, timeout=20)
    if pp.get("ok"):
        raw.extend(pp.get("sales") or [])
        for s in pp.get("sales") or []:
            slug = _HMLR_LITE_TYPE.get((s.get("type") or "").strip().lower())
            if slug:
                pc_types.append(slug)

    # AUTHORITATIVE: the subject's own entry in HM Land Registry. If this exact address has
    # transacted, the register recorded what it IS - that beats any address-string guess.
    hm = _hmlr_subject_type(address, pp.get("sales") if pp.get("ok") else None)
    if hm:
        pdtype, type_source = hm, "hmlr_register"
    # EPC fills the gap for a home that has never sold (so HMLR holds no row for it),
    # and supplies floor area when public data can be matched. Missing floor area lowers
    # confidence only; it never blocks the first value.
    epc_subj = _epc_subject(address, pc)
    # FAST PATH: also check graph DB for EPC
    if not epc_subj and _use_graph:
        try:
            epc_row = _gq.epc_for_address(address, pc)
            if epc_row and epc_row.get("floor_area_sqm"):
                epc_subj = {"ok": True, "matched": True,
                            "floor_area_sqm": epc_row["floor_area_sqm"],
                            "rating": epc_row.get("rating"),
                            "property_type": epc_row.get("property_type"),
                            "built_form": epc_row.get("built_form"),
                            "source": epc_row.get("source", "graph DB")}
        except Exception:
            pass
    if not pdtype and epc_subj:
        et = _epc_type_to_slug(epc_subj.get("property_type"), epc_subj.get("built_form"))
        if et:
            pdtype, type_source = et, "epc_register"
    try:
        subject_sqm = int(round(float(sqm))) if sqm else None
    except Exception:
        subject_sqm = None
    subject_area_source = None
    subject_area_status = None
    if subject_sqm:
        subject_area_source = "user supplied" if sqm else "input"
        subject_area_status = "supplied"
    if not subject_sqm and epc_subj and epc_subj.get("floor_area_sqm"):
        subject_sqm = int(epc_subj["floor_area_sqm"])
        if epc_subj.get("building_proxy"):
            subject_area_source = "public EPC register building proxy"
            subject_area_status = "official_public_building_proxy"
        else:
            subject_area_source = "public EPC register" if "public" in (epc_subj.get("source") or "").lower() or "Find an energy certificate" in (epc_subj.get("source") or "") else "EPC register"
            subject_area_status = "official_public_exact" if subject_area_source == "public EPC register" else "official_exact"
    subject_history = _hmlr_subject_sale(address, pp.get("sales") if pp.get("ok") else None)
    if not subject_sqm:
        subject_sqm = _model_floor_area(pdtype, subject_sqm=None)
        subject_area_source = "Honestly floor-area model"
        subject_area_status = "modelled"
    # Do we genuinely KNOW the subject's floor area, or is it our model's guess? This gates the
    # cardinal size rule below: we only refuse wrong-size comparables when the subject size is
    # real (official register or user-supplied). The EPC layer above (exact match, building
    # proxy, or postcode-cluster proxy) now resolves the size from the free public register in
    # almost every case, so the modelled fallback is rarely reached; when it is, we cannot
    # honestly size-match and value at type level instead of filtering comps by size.
    subject_area_official = bool(subject_area_status and (str(subject_area_status).startswith("official") or subject_area_status == "supplied"))
    subject_beds = beds if beds is not None else _infer_beds_from_area(pdtype, subject_sqm)
    subject_beds_source = "user" if beds is not None else "Honestly size/type inference"

    # 2) Valuation evidence: 12 months ideal, 24 months hard cap, 0.5 miles first.
    # If fewer than five same-type comps exist, widen geography, never time. The subject's
    # own previous sale is excluded from valuation comps and kept only as history.
    import datetime as _dt
    since_24 = (_dt.date.today() - _dt.timedelta(days=int(24 * 30.44))).isoformat()

    # ── Fast local data spine (graph_db) ──────────────────────────────────
    # Try the local SQLite spine first. If the data is there, we skip all the
    # live API calls (SPARQL, Postcodes.io, EPC) and answer in ms instead of seconds.
    _use_graph = False
    _gq = None
    try:
        from graph_db import GraphQuery
        _gq = GraphQuery()
        # Quick check: does it have data for this postcode?
        _test = _gq.sales_for_postcode(pc, limit=1)
        if _test:
            _use_graph = True
    except Exception:
        pass

    def _postcode_set(radius_m):
        rows = {pc: 0}
        # FAST PATH: pre-computed neighbour table from graph DB
        if _use_graph:
            try:
                nearby = _gq.nearby_postcodes(pc, radius_m=radius_m)
                if nearby:
                    for n in nearby:
                        rows[n["postcode"]] = n["dist_m"]
                    return rows
            except Exception:
                pass
        # SLOW PATH: live Postcodes.io API
        near = geo.nearest(pc, limit=100, radius=radius_m)
        if near.get("ok"):
            for n in near.get("neighbours") or []:
                p = n.get("postcode")
                if p:
                    rows[p] = n.get("dist_m")
        # Postcodes.io caps nearest results in dense London districts. Add reverse-geocode
        # rings around the subject so 0.25-0.5 mile postcodes are not crowded out by the
        # nearest 100. Distances are computed locally from postcode centroids.
        if lat is not None and lng is not None:
            import math as _math
            def _dist_m(lat2, lng2):
                R = 6371000.0
                p1, p2 = _math.radians(lat), _math.radians(lat2)
                dp = _math.radians(lat2 - lat)
                dl = _math.radians(lng2 - lng)
                a = _math.sin(dp / 2) ** 2 + _math.cos(p1) * _math.cos(p2) * _math.sin(dl / 2) ** 2
                return int(round(2 * R * _math.asin(_math.sqrt(a))))
            ring_radii = [max(120, int(radius_m * 0.45)), max(220, int(radius_m * 0.75)), int(radius_m)]
            for rr in ring_radii:
                for lat2, lng2 in geo._ring_points(lat, lng, rr, n=12):
                    rev = geo.reverse(lat2, lng2, limit=100, radius=max(120, int(radius_m * 0.35)), timeout=10)
                    if not rev.get("ok"):
                        continue
                    for p in rev.get("postcodes") or []:
                        if p not in rows:
                            rows[p] = None
        return rows

    _pc_dist_cache = {}
    def _distance_to_subject_m(spc):
        if spc in _pc_dist_cache:
            return _pc_dist_cache[spc]
        if lat is None or lng is None or not spc:
            _pc_dist_cache[spc] = None
            return None
        try:
            g2 = geo.lookup(spc)
            if not g2.get("ok") or g2.get("lat") is None or g2.get("lng") is None:
                _pc_dist_cache[spc] = None
                return None
            import math as _math
            R = 6371000.0
            p1, p2 = _math.radians(lat), _math.radians(g2["lat"])
            dp = _math.radians(g2["lat"] - lat)
            dl = _math.radians(g2["lng"] - lng)
            a = _math.sin(dp / 2) ** 2 + _math.cos(p1) * _math.cos(p2) * _math.sin(dl / 2) ** 2
            _pc_dist_cache[spc] = int(round(2 * R * _math.asin(_math.sqrt(a))))
            return _pc_dist_cache[spc]
        except Exception:
            _pc_dist_cache[spc] = None
            return None

    def _load_sales(radius_m):
        pmap = _postcode_set(radius_m)
        # FAST PATH: local graph DB (ms, no API calls)
        if _use_graph:
            try:
                area_sales = _gq.sales_for_postcodes(list(pmap.keys()), since=since_24, limit=1500)
                if area_sales:
                    sales = []
                    for s in area_sales:
                        if not s.get("price"):
                            continue
                        # Normalise ptype from DB format (D/S/T/F/O) to HMLR labels
                        ptype_label = {"D": "detached", "S": "semi-detached", "T": "terraced", "F": "flat-maisonette"}.get(s.get("ptype"), "")
                        if _sale_matches_subject(address, _build_address(s)):
                            continue
                        slug = _HMLR_LITE_TYPE.get(ptype_label)
                        if not slug:
                            continue
                        spc = s.get("postcode", pc)
                        dist_m = pmap.get(spc)
                        sales.append({"address": _build_address(s) or spc, "price": int(s["price"]),
                                      "date": (s.get("date") or "")[:10], "pdtype": slug,
                                      "postcode": spc, "dist_m": dist_m,
                                      "hmlr_uri": s.get("tuid", "")})
                    return sales, pmap
            except Exception:
                pass
        # SLOW PATH: live SPARQL API
        area = land_registry.ppd_area(list(pmap), since=since_24, cap=500, limit=1500, timeout=60)
        rows = area.get("sales") if area.get("ok") else []
        sales = []
        for s in rows or []:
            if not s.get("price"):
                continue
            if _sale_matches_subject(address, s.get("address") or ""):
                continue
            slug = _HMLR_LITE_TYPE.get((s.get("type") or "").strip().lower())
            if not slug:
                continue
            spc = s.get("postcode") or pc
            dist_m = pmap.get(spc)
            if dist_m is None:
                dist_m = _distance_to_subject_m(spc)
            sales.append({"address": s.get("address") or spc, "price": int(s["price"]),
                          "date": (s.get("date") or "")[:10], "pdtype": slug,
                          "postcode": spc, "dist_m": dist_m,
                          "hmlr_uri": s.get("hmlr_uri")})
        return sales, pmap

    def _build_address(s):
        """Build an address string from graph DB row parts."""
        parts = [s.get(k) for k in ("saon", "paon", "street", "town") if s.get(k)]
        return ", ".join(parts) if parts else s.get("postcode", "")

    base_sales, base_pmap = _load_sales(_LITE_BASE_RADIUS_M)
    base_sales, epc_source = _attach_epc_floor_areas(base_sales, base_pmap.keys())
    street_area_source = None
    street_area_source = None
    expanded_sales, expanded_pmap = base_sales, base_pmap

    # If we still don't know the subject's type, use exact-postcode mix as a prior only.
    # It can decide type, but valuation still requires recent evidence after subject exclusion.
    if not pdtype and len(pc_types) >= 5:
        from collections import Counter
        dom, k = Counter(pc_types).most_common(1)[0]
        if k / len(pc_types) >= 0.7:
            pdtype, type_source = dom, "postcode_dominant"

    def _same_type(rows):
        return [s for s in rows if pdtype and s["pdtype"] == pdtype]

    typed_base = _same_type(base_sales)
    geography_label = "within 0.5 miles"
    sales = base_sales
    used = typed_base if pdtype else base_sales

    def _area_matches(rows):
        return [s for s in rows if s.get("floor_area_official") and _area_match(subject_sqm, s.get("sqm"), tolerance=0.20)]

    def _recent_same_type_12m(rows):
        import datetime as _dt2
        cut = _dt2.date.today() - _dt2.timedelta(days=int(12 * 30.44))
        out = []
        for row in rows:
            if pdtype and row.get("pdtype") != pdtype:
                continue
            if row.get("dist_m") is None or row.get("dist_m") > _LITE_BASE_RADIUS_M:
                continue
            try:
                if row.get("date") and _dt2.date.fromisoformat(row["date"]) >= cut:
                    out.append(row)
            except Exception:
                pass
        return out

    radius_expanded = False
    expansion_reason = None
    # 0.5mi is ideal. Expand only if the preferred 0.5mi/12mo same-type pool is empty.
    # A thin-but-real local pool stays local; we do not shop around for a better story.
    if pdtype and not _recent_same_type_12m(typed_base):
        expanded_sales, expanded_pmap = _load_sales(_LITE_EXPANDED_RADIUS_M)
        expanded_sales, epc_source = _attach_epc_floor_areas(expanded_sales, expanded_pmap.keys())
        typed_expanded = _same_type(expanded_sales)
        if typed_expanded:
            used = typed_expanded
            sales = expanded_sales
            radius_expanded = True
            expansion_reason = "no same-type HMLR sales within 0.5 miles in the last 12 months"
            geography_label = "within up to 1 mile because no same-type HMLR sales were found within 0.5 miles in the last 12 months"
    elif not pdtype:
        used = base_sales

    # Floor area is mandatory as a product field. Official/public EPC exact areas can become
    # same-size valuation anchors. Modelled areas display with provenance but do not make a
    # row a same-size comp.
    used = _fill_modelled_floor_areas(used, subject_sqm=subject_sqm, pdtype=pdtype)
    for s in used:
        if s.get("beds") is None and s.get("sqm"):
            s["beds"] = _infer_beds_from_area(s.get("pdtype") or pdtype, s.get("sqm"))
            s["beds_source"] = "Honestly size/type inference"
        area_ok = _area_match(subject_sqm, s.get("sqm"), tolerance=0.20) if s.get("floor_area_official") else False
        s["area_match"] = area_ok if subject_sqm and s.get("sqm") else None
        if subject_sqm and s.get("sqm"):
            s["size_delta_pct"] = round((float(s["sqm"]) - float(subject_sqm)) / float(subject_sqm) * 100, 1)
    same_size_official = _area_matches(used) if subject_sqm else []
    seed_history_model = _lite_history_estimate(subject_history, g.get("region") or "london", finish) if subject_history else None
    price_anchor = (seed_history_model or {}).get("central")
    if not price_anchor and same_size_official:
        price_anchor = statistics.median([s["price"] for s in same_size_official])

    today = _dt.date.today()
    strict_recency_months = 6
    strict_recency_extended = False
    strict_recency_reason = None
    area_tolerance = _LITE_AREA_TOLERANCE_STRICT
    area_tolerance_relaxed = False
    area_tolerance_label = "20%"
    allow_unverified_area = False
    def _sale_within_months(s0, months):
        try:
            return bool(s0.get("date") and _dt.date.fromisoformat(s0["date"]) >= today - _dt.timedelta(days=int(months * 30.44)))
        except Exception:
            return False

    def _strict_reject_reason(s0, tol=None, accept_unverified=False):
        """Gate a sale row for strict-comparable status. Returns None if it passes.
        
        tol overrides the floor-area tolerance (0.20 default, relaxed to 0.35/0.50
        when the pool is thin). accept_unverified=True allows comps without official
        floor area as disclosed comparables with caveats rather than hard-rejecting them."""
        dist = s0.get("dist_m")
        if dist is None:
            return "distance_not_verified"
        max_radius = _LITE_MAX_EXPANDED_COMP_RADIUS_M if radius_expanded else _LITE_MAX_COMP_RADIUS_M
        if dist > max_radius:
            return "outside_expanded_radius" if radius_expanded else "outside_half_mile_micro_market"
        if not _sale_within_months(s0, strict_recency_months):
            return f"older_than_{strict_recency_months}_months"
        if pdtype and s0.get("pdtype") != pdtype:
            return "different_property_type"
        # Floor area gate: hard reject if no area AND we aren't accepting unverified.
        # When accepting unverified, missing area becomes a caveat, not a bar.
        if not s0.get("sqm"):
            if accept_unverified:
                s0.setdefault("comparable_caveats", [])
                s0["comparable_caveats"].append("floor area not verified from EPC; size similarity not confirmed")
            else:
                return "official_floor_area_not_verified"
        elif not s0.get("floor_area_official") and not accept_unverified:
            return "official_floor_area_not_verified"
        elif not s0.get("floor_area_official") and accept_unverified:
            s0.setdefault("comparable_caveats", [])
            s0["comparable_caveats"].append("floor area from model, not official EPC; size similarity approximate")
        # Area match gate: use the current tolerance (may be relaxed)
        use_tol = tol or area_tolerance
        if s0.get("sqm") and subject_sqm:
            if not _area_match(subject_sqm, s0.get("sqm"), tolerance=use_tol):
                delta = abs(float(s0["sqm"]) - float(subject_sqm)) / float(subject_sqm)
                return f"outside_floor_area_band_{int(use_tol*100)}pct_delta{int(delta*100)}pct"
        # HMLR PPD does not carry bedrooms/tenure. We infer bedrooms from official floor
        # area/type and carry tenure as a caveat rather than letting the product fail to
        # produce comps. Known mismatches still reject.
        if subject_beds is not None and s0.get("beds") is not None:
            if abs(int(s0.get("beds")) - int(subject_beds)) > 1:
                return "bedroom_count_not_similar"
        s0.setdefault("comparable_caveats", [])
        if (s0.get("beds_source") or "").startswith("Honestly") or subject_beds_source.startswith("Honestly"):
            s0["comparable_caveats"].append("bedroom count inferred from public floor area/type")
        if not s0.get("tenure"):
            s0["comparable_caveats"].append("tenure not present in HMLR PPD; confirm lease/freehold in decision pack")
        if price_anchor:
            if abs(float(s0["price"]) - float(price_anchor)) / float(price_anchor) > _LITE_SIMILAR_PRICE_PCT:
                return "outside_similar_price_band"
        return None

    def _strict_comparable_rows(rows, tol=None, accept_unverified=False):
        out = []
        for s0 in rows:
            reason = _strict_reject_reason(s0, tol=tol, accept_unverified=accept_unverified)
            s0["strict_reject_reason"] = reason
            if reason is None:
                out.append(s0)
        return out

    # Pass 1: strict gate (6 months, 15% area, official area only)
    strict_comps = _strict_comparable_rows(used)
    if len(strict_comps) < _LITE_MIN_STRICT_COMPS:
        strict_recency_months = 12
        strict_recency_extended = True
        strict_recency_reason = "fewer than 5 strict comparables inside 6 months; extended to 12 months"
        strict_comps = _strict_comparable_rows(used)
    # Pass 2: extend recency to 24 months before touching radius
    if len(strict_comps) < _LITE_MIN_STRICT_COMPS and not strict_recency_extended:
        strict_recency_months = 12
        strict_recency_extended = True
    if len(strict_comps) < _LITE_MIN_STRICT_COMPS:
        strict_recency_months = 24
        strict_recency_reason = "fewer than 5 strict comparables inside 12 months; extended to 24 months"
        strict_comps = _strict_comparable_rows(used)
    # Pass 3: expand radius to 0.75 miles (never 1 mile) as last resort
    if len(strict_comps) < _LITE_MIN_STRICT_COMPS and not radius_expanded:
        expanded_sales, expanded_pmap = _load_sales(_LITE_EXPANDED_RADIUS_M)
        expanded_sales, epc_source = _attach_epc_floor_areas(expanded_sales, expanded_pmap.keys())
        expanded_used = _same_type(expanded_sales) if pdtype else expanded_sales
        expanded_used = _fill_modelled_floor_areas(expanded_used, subject_sqm=subject_sqm, pdtype=pdtype)
        for sx in expanded_used:
            if sx.get("beds") is None and sx.get("sqm"):
                sx["beds"] = _infer_beds_from_area(sx.get("pdtype") or pdtype, sx.get("sqm"))
                sx["beds_source"] = "Honestly size/type inference"
            area_ok = _area_match(subject_sqm, sx.get("sqm"), tolerance=0.15) if sx.get("floor_area_official") else False
            sx["area_match"] = area_ok if subject_sqm and sx.get("sqm") else None
            if subject_sqm and sx.get("sqm"):
                sx["size_delta_pct"] = round((float(sx["sqm"]) - float(subject_sqm)) / float(subject_sqm) * 100, 1)
        if expanded_used:
            used = expanded_used
            sales = expanded_sales
            radius_expanded = True
            expansion_reason = "0.5-mile strict comparable gate returned fewer than 5 after extending to 24 months; expanded to 0.75 miles maximum"
            geography_label = "within up to 0.75 miles because the 0.5-mile strict comparable gate returned fewer than 5 after 24-month window"
            same_size_official = _area_matches(used) if subject_sqm else []
            if same_size_official and not (seed_history_model or {}).get("central"):
                price_anchor = statistics.median([sx["price"] for sx in same_size_official])
            strict_comps = _strict_comparable_rows(used)

    # Pass 4: relax area tolerance to 35% - some properties are unusual sizes and the
    # 20% band kills genuine same-type/nearby sales. A 35% band on a 140sqm flat catches
    # 91-189sqm instead of 112-168sqm, which covers large maisonette-style flats.
    if len(strict_comps) < _LITE_MIN_STRICT_COMPS:
        area_tolerance = _LITE_AREA_TOLERANCE_RELAXED
        area_tolerance_relaxed = True
        area_tolerance_label = "35% (relaxed from 20% because fewer than 5 strict comparables were found)"
        strict_comps = _strict_comparable_rows(used)

    # Pass 5: accept comps without official floor area as disclosed comparables.
    # When EPC data is unavailable for an area, we should not let the lack of
    # verified floor area reduce a client's report to 2 comps. Modelled areas
    # with same-type/same-location are disclosed comps with clear caveats.
    if len(strict_comps) < _LITE_MIN_STRICT_COMPS:
        allow_unverified_area = True
        strict_comps = _strict_comparable_rows(used, accept_unverified=True)

    # Pass 6: last-resort wide area tolerance (50%) - catches significantly different
    # sizes that are still the same property type in the same micro-market.
    # These carry explicit size-delta caveats. Better a disclosed comp than no comp.
    if len(strict_comps) < _LITE_MIN_STRICT_COMPS:
        area_tolerance = _LITE_AREA_TOLERANCE_WIDE
        area_tolerance_label = "50% (wide tolerance because the standard 20% and relaxed 35% bands returned fewer than 5 strict comparables)"
        strict_comps = _strict_comparable_rows(used, accept_unverified=True)

    strict_reject_reasons = {}
    for s0 in used:
        if s0.get("strict_reject_reason"):
            strict_reject_reasons[s0["strict_reject_reason"]] = strict_reject_reasons.get(s0["strict_reject_reason"], 0) + 1
        s0["strict_comparable"] = s0 in strict_comps
    comparable_zero_reason = None
    if not strict_comps:
        if not radius_expanded and _recent_same_type_12m(typed_base if pdtype else base_sales):
            comparable_zero_reason = "local_sales_exist_but_fail_strict_physical_or_legal_gates"
        elif radius_expanded:
            comparable_zero_reason = "expanded_radius_still_has_no_rows_passing_strict_comparable_gates"
        else:
            comparable_zero_reason = "no_same_type_local_sales_available_to_test_as_comparables"
    # Only strict same-market rows may become comparables. If we do not have enough, do not
    # blend weaker rows into the price. Fall back to subject history/HPI and show HMLR rows
    # as proof/context only.
    # Cardinal size rule: a sale whose floor area is wrong for the subject must NEVER anchor the
    # figure or be shown as a comparable. When we genuinely know the subject's size (official
    # EPC/supplied), we value ONLY from strict size-matched rows - the radius was already
    # expanded to 1 mile above to find more of them rather than padding with mismatched stock.
    # When even after expansion there are too few, the subject-history HPI fallback below carries
    # the figure and we show only the strict rows we do have. A 137 sqm flat is never valued
    # against 63 sqm sales.
    if subject_area_official and subject_sqm:
        used = strict_comps
    elif len(strict_comps) >= _LITE_MIN_STRICT_COMPS:
        used = strict_comps
    size_matched = strict_comps

    type_basis = _PDTYPE_LABEL.get(pdtype, pdtype) if pdtype else "all residential types"
    if pdtype and len(used) < _LITE_MIN_COMPS:
        type_source = type_source or "thin_recent_evidence"

    # 3) prefer 12 months, then 24 months. Never older.
    today = _dt.date.today()
    def _within(months, rows):
        cut = today - _dt.timedelta(days=int(months * 30.44))
        out = []
        for s in rows:
            try:
                if s["date"] and _dt.date.fromisoformat(s["date"]) >= cut:
                    out.append(s)
            except Exception:
                pass
        return out
    window = 24
    window_label = "over the last 24 months"
    sel = _within(12, used)
    if len(sel) >= _LITE_MIN_COMPS:
        window = 12
        window_label = "over the last 12 months"
    else:
        sel = _within(24, used)
    if not sel:
        if seed_history_model:
            # No size-matched comparable survived the window. Rather than display sales of a
            # clearly different size, we anchor on the subject's own HMLR history (HPI-indexed)
            # below and show no comparables - honest thin evidence beats a misleading comp set.
            pass
        else:
            sys.exit(f"HM Land Registry has no usable same-size, same-type sold evidence within 24 months near {pc}. "
                     "I won't value a home against sales of a clearly different size - add the floor area or use the Pro tier.")

    # Remove obvious price-tier outliers from the valuation anchor when enough evidence
    # remains. These rows are real HMLR sales, but not necessarily comparable market stock
    # for the subject: partial/atypical low rows and premium-context high rows distort the
    # defended number. They stay out of the anchor rather than silently moving it.
    if len(sel) >= 4:
        med0 = statistics.median([s["price"] for s in sel])
        trimmed = [s for s in sel if med0 * 0.65 <= s["price"] <= med0 * 1.25]
        if len(trimmed) >= 3:
            sel = trimmed

    def _strict_justification(s0):
        if not s0.get("strict_comparable"):
            return None
        dist_txt = f"{round((s0.get('dist_m') or 0) / 1609.344, 2)} miles"
        delta = abs(float(s0.get("sqm")) - float(subject_sqm)) / float(subject_sqm) * 100 if subject_sqm and s0.get("sqm") else 0
        months_txt = f"within {strict_recency_months} months"
        radius_note = "inside the ideal 0.5-mile radius" if (s0.get('dist_m') or 0) <= _LITE_BASE_RADIUS_M else "inside the disclosed expanded radius after the 0.5-mile/12-month pool was empty"
        return (f"Selected because it is in the same immediate micro-market ({dist_txt}, {radius_note}), sold {months_txt} per HM Land Registry, "
                f"matches the property class, and has official floor area within {delta:.1f}% of the subject.")

    # 5) build the figure. If strict comparable rows pass the hard gate, they anchor the
    #    sold-evidence valuation. Otherwise these rows are proof/context and subject-history
    #    HPI anchors the figure.
    comps = []
    for s in sel:
        recency_score = _lite_weight(s["date"])
        area_score = 1.0
        if subject_sqm and s.get("sqm"):
            area_score = 1.0 if s.get("area_match") else 0.55
        elif subject_sqm:
            area_score = 0.65
        score = recency_score * area_score
        match = None
        if subject_sqm and s.get("sqm"):
            match = max(0, min(100, int(round(100 - abs(float(s["sqm"]) - float(subject_sqm))))))
        comps.append({"address": s["address"], "sqm": s.get("sqm"), "price": s["price"],
                      "date": s["date"] or "", "url": "", "hmlr_uri": s.get("hmlr_uri"),
                      "dist": round((s.get("dist_m") or 0) / 1609.344, 2) if s.get("dist_m") is not None else None,
                      "match": match, "psm": round(s["price"] / s["sqm"]) if s.get("sqm") else None,
                      "tier": "A", "area_match": s.get("area_match"),
                      "floor_area_source": s.get("floor_area_source"),
                      "floor_area_status": s.get("floor_area_status"),
                      "floor_area_official": bool(s.get("floor_area_official")),
                      "strict_comparable": bool(s.get("strict_comparable")),
                      "strict_reject_reason": s.get("strict_reject_reason"),
                      "justification": _strict_justification(s),
                      "epc_rating": s.get("epc_rating"),
                      "weak": len(sel) < _LITE_MIN_COMPS or (subject_sqm and s.get("area_match") is False),
                      "score": score})
    if sel:
        plist = sorted(s["price"] for s in sel)
        raw_med = statistics.median(plist)
        raw_q1 = _pctl(plist, 25)
        raw_q3 = _pctl(plist, 75)
        lo, central_raw, hi = _lite_finish_prices(raw_med, raw_q1, raw_q3, finish)
        lo = min(lo, central_raw); hi = max(hi, central_raw)        # the band must bracket the central
        low = round_to(lo, 5000); high = round_to(hi, 5000); central = round_to(central_raw, 5000)
        if low >= central:  low = round_to(central * 0.94, 5000)
        if high <= central: high = round_to(central * 1.06, 5000)
    else:
        # Size-matched comparables were too thin to anchor the band directly; the subject-history
        # HPI model below supplies the figure. Seed raw_* from it so the glass-box fields stay
        # consistent rather than empty.
        seed_c = (seed_history_model or {}).get("central") or 0
        plist = []
        raw_med = raw_q1 = raw_q3 = seed_c
        low = (seed_history_model or {}).get("low") or seed_c
        high = (seed_history_model or {}).get("high") or seed_c
        central = seed_c
    history_model = None
    # If the subject size is known but comp sizes are not, generic flat medians are still not
    # comparable to a 103 sqm maisonette. Use the subject's own HMLR history indexed by HPI
    # as the disclosed fallback until enough public same-size comp areas resolve.
    if subject_history and (len(size_matched) < _LITE_MIN_STRICT_COMPS):
        history_model = seed_history_model or _lite_history_estimate(subject_history, g.get("region") or "london", finish)
        if history_model:
            low, high, central = history_model["low"], history_model["high"], history_model["central"]
    guide = guide_price(central)

    type_confident = type_source in ("hmlr_register", "address", "epc_register")
    formula = {
        "name": "Honestly Transparent AVM v1",
        "valuation_basis": "hmlr_subject_history_hpi" if history_model else "hmlr_sold_evidence",
        "sources": ["HM Land Registry Price Paid Data", "HM Land Registry UK HPI", "EPC register where matched", "Postcodes.io / ONS geography"],
        "non_sources": ["asking prices", "portal estimates", "agent quotes", "commercial same-data aggregators"],
        "filter": {
            "property_type": type_basis,
            "type_source": type_source,
            "distance": geography_label,
            "min_strict_comparables": _LITE_MIN_STRICT_COMPS,
            "strict_recency_months": strict_recency_months,
            "strict_recency_extended": strict_recency_extended,
            "strict_recency_reason": strict_recency_reason,
            "radius_expanded": radius_expanded,
            "expansion_reason": expansion_reason,
            "comparable_zero_reason": comparable_zero_reason,
            "strict_reject_reasons": strict_reject_reasons,
            "ideal_radius_miles": 0.5,
            "fallback_radius_miles": 1.0,
            "recency_window_months": (strict_recency_months if len(size_matched) >= _LITE_MIN_STRICT_COMPS else window),
            "comparable_ideal_months": 6,
            "comparable_rescue_cap_months": 12,
            "proof_context_hard_cap_months": 24,
            "subject_sale_excluded": True,
            "same_size_anchor_used": bool(subject_sqm and len(size_matched) >= _LITE_MIN_STRICT_COMPS),
            "strict_comparable_rule": "minimum 5 comparables; same immediate micro-market; exact distance <=0.5 miles by default, expandable up to 1 mile only when the 0.5-mile gate returns fewer than 5; no known barrier/catchment/spec conflict; same type; verified/inferred bedrooms within 1; tenure caveated when not in HMLR PPD; floor area within 20% by default, relaxed to 35% then 50% when the pool is thin; comps without official floor area accepted as disclosed with caveats when necessary to reach 5; sold within 6 months ideally, extended to 12 months only to reach 5; and price within +/-30% of the anchor; otherwise proof/context only",
            "area_tolerance": area_tolerance_label,
            "area_tolerance_relaxed": area_tolerance_relaxed,
            "allow_unverified_area": allow_unverified_area,
            "outlier_rule": "if n>=4, drop rows outside 0.65x to 1.25x the median when at least 3 rows remain",
        },
        "evidence": {
            "selected_count": len(sel),
            "strict_comparable_count": len(size_matched),
            "evidence_role": "strict_comparables" if len(size_matched) >= _LITE_MIN_STRICT_COMPS else "proof_context",
            "pool_count": len(sales),
            "raw_prices": plist,
            "raw_q1": round_to(raw_q1, 5000),
            "raw_median": round_to(raw_med, 5000),
            "raw_q3": round_to(raw_q3, 5000),
        },
        "condition": {
            "tier": finish,
            "sold_evidence_rule": _FINISH_RULES.get((finish or "average").strip().lower(), _FINISH_RULES["average"]),
            "history_factor": (history_model or {}).get("condition_factor") or _HISTORY_FINISH_FACTORS.get((finish or "average").strip().lower(), _HISTORY_FINISH_FACTORS["average"]),
        },
        "rounding": "nearest £5,000",
        "guide_rule": "guide_price(central) - a conservative launch/opening level below the central estimate",
        "result": {"low": low, "central": central, "high": high, "guide": guide},
        "plain_formula": (
            f"HMLR {type_basis}, {geography_label}, {window} months -> median {money(round_to(raw_med, 5000))}; "
            f"condition tier {finish}; "
            + (f"subject history fallback: {money(subject_history['price'])} x HPI x {history_model['condition_factor']} -> {money(central)}" if history_model and subject_history else
               f"condition rule {_FINISH_RULES.get((finish or 'average').strip().lower(), _FINISH_RULES['average'])} -> {money(low)} to {money(high)}, central {money(central)}")
        ),
    }
    val = {"avm": {}, "tierA_med": central, "psmA": 0, "crosscheck": None,
           "low": low, "high": high, "central": central, "guide": guide,
           "basis": "hmlr_subject_history_hpi" if history_model else "hmlr_sold_evidence",
           "type_basis": type_basis,
           "type_source": type_source, "type_confident": type_confident,
           "window_months": window, "n_evidence": len(sel),
           "condition_tier": finish, "raw_comparable_median": round_to(raw_med, 5000),
           "history_model": history_model, "formula": formula}
    # No paid live-listing feed in the free tier, so there is no live-market steer: the
    # figure rests on the sold evidence alone. apply_market(pos=None) records exactly that,
    # in the same disclosed language the paid path uses.
    apply_market(val, None)

    subj = {
        "address": (g.get("postcode") and address) or address,
        "uprn": None, "lat": lat, "lng": lng, "sqm": subject_sqm,
        "floor_area_source": subject_area_source,
        "floor_area_status": subject_area_status,
        "floor_area_official": bool(subject_area_status and str(subject_area_status).startswith("official")),
        "beds": beds, "beds_est": beds, "baths": baths, "type": (pdtype or "residential"),
        "epc": epc_subj.get("rating") if epc_subj else None, "tax": None,
        "tenure": None, "investment": investment,
        "last_sold": subject_history.get("price") if subject_history else None,
        "last_sold_date": subject_history.get("date") if subject_history else None,
        "construction": "",
        "source": "hmlr_lite",
        "lite_basis": {
            "postcode": pc, "outcode": outcode, "country": country or "England/Wales",
            "type_basis": type_basis, "type_source": type_source,
            "type_confident": type_confident, "window_months": window,
            "n_evidence": len(sel), "n_pool": len(sales),
            "subject_area_source": subject_area_source,
            "subject_area_status": subject_area_status,
            "comp_area_source": epc_source,
            "history_source": subject_history.get("source") if subject_history else None,
            "source": f"HM Land Registry Price Paid Data + {epc_source}",
            "note": (f"This is a FREE Lite valuation, built from {len(sel)} comparable "
                     f"{type_basis} sold {geography_label}, {window_label}. "
                     + _LITE_TYPE_NOTE(type_source, pdtype) +
                     f" The subject's own previous sale is excluded from the comparable set. "
                     f"Floor area is filled for every subject/evidence row with official EPC/public EPC where possible and labelled modelled otherwise. "
                     f"Condition tier used: {finish}. Every figure traces to a real recorded sale."),
        },
    }
    return {"subject": subj, "valuation": val, "compsA": comps,
            "n_candidates": len(sales), "n_screened": len(sales) - len(sel),
            "positioning": None, "pdtype": (pdtype or "residential"),
            "finish": finish, "tier_basis": "hmlr_lite"}

# ---------------------------------------------------------------- shared summary
def nice_addr(addr):
    """Title-case the street, keep the postcode uppercase."""
    import re
    t = addr.title() if addr.isupper() else addr
    pc = postcode_of(addr)
    if pc:
        t = re.sub(re.escape(pc.title()), pc, t)
    return t


def _confidence_grade(score):
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Good"
    if score >= 40:
        return "Fair"
    return "Low"


def _confidence_summary(r, out):
    """Data-only confidence grade for the assessed range.

    Scores the evidence depth, data completeness, cross-check agreement and range
    stability. No model vibes, no subjective uplift. The result is a compact grade,
    score and note that can be rendered on every surface.
    """
    s, v = r["subject"], r["valuation"]
    pos = r.get("positioning") or {}
    basis = s.get("lite_basis") or {}
    comps = r.get("compsA") or []
    n = len(comps)
    history_basis = v.get("basis") == "hmlr_subject_history_hpi"
    any_comp_size = any(c.get("sqm") for c in comps)
    any_official_comp_size = any(c.get("floor_area_official") for c in comps)
    any_strict_comparable = any(c.get("strict_comparable") for c in comps)
    strong = [c for c in comps if not c.get("weak")]
    scores = sorted([(c.get("score") or 0.0) for c in comps if c.get("score") is not None], reverse=True)
    top = scores[:5]
    avg_score = (sum(top) / len(top)) if (top and (any_strict_comparable or not history_basis)) else 0.0
    strong_share = (len(strong) / n) if n else 0.0
    width_pct = ((v["high"] - v["low"]) / v["central"] * 100.0) if v.get("central") else None

    cross_div = None
    cross_src = None
    cross = out.get("crosscheck") or {}
    if isinstance(cross, dict) and cross.get("divergence_pct") is not None:
        cross_div = abs(float(cross.get("divergence_pct")))
        cross_src = "official postcode cross-check"
    elif v.get("avm_divergence") is not None:
        cross_div = abs(float(v.get("avm_divergence")))
        cross_src = "AVM cross-check"

    evidence_score = min(30, n * 5)
    evidence_score += min(15, round(avg_score * 15))
    evidence_score += min(10, round(strong_share * 10))
    evidence_score = min(45, evidence_score)

    completeness_score = 0
    completeness_score += 6 if s.get("sqm") else 0
    completeness_score += 4 if s.get("type") and s.get("type") != "residential" else 0
    completeness_score += 3 if s.get("beds") is not None else 0
    completeness_score += 3 if s.get("epc") is not None else 0
    completeness_score += 3 if s.get("tenure") is not None else 0
    completeness_score += 2 if s.get("tax") is not None else 0
    completeness_score += 2 if s.get("last_sold") is not None else 0
    completeness_score += 2 if pos.get("band") else 0
    completeness_score += 2 if basis.get("type_confident") else 0
    completeness_score = min(20, completeness_score)

    sold_basis = v.get("evidence_basis") == "sold" or v.get("basis") == "hmlr_sold_evidence"
    if cross_div is None:
        # The free tier carries no external AVM/postcode crosscheck, so agreement comes from the
        # INTERNAL consistency of the sold comparables: a tight price cluster across independent
        # recorded sales is genuine corroboration of the figure. Scored from the spread (mean
        # absolute deviation from the median) of the strict comparable prices.
        agreement_score = 0
        if sold_basis:
            cps = [c.get("price") for c in comps
                   if c.get("price") and (c.get("strict_comparable") or not history_basis)]
            if len(cps) >= 3:
                m = statistics.median(cps)
                disp = (sum(abs(p - m) for p in cps) / len(cps) / m) if m else 1.0
                if   disp <= 0.06: agreement_score = 18
                elif disp <= 0.10: agreement_score = 14
                elif disp <= 0.15: agreement_score = 10
                elif disp <= 0.22: agreement_score = 6
                else:              agreement_score = 3
            elif cps:
                agreement_score = 4
    elif cross_div <= 2.5:
        agreement_score = 20
    elif cross_div <= 5:
        agreement_score = 16
    elif cross_div <= 10:
        agreement_score = 10
    elif cross_div <= 20:
        agreement_score = 5
    else:
        agreement_score = 0

    if width_pct is None:
        stability_score = 0
    elif width_pct <= 8:
        stability_score = 15
    elif width_pct <= 12:
        stability_score = 12
    elif width_pct <= 18:
        stability_score = 8
    elif width_pct <= 25:
        stability_score = 4
    else:
        stability_score = 0

    score = int(max(0, min(100, round(evidence_score + completeness_score + agreement_score + stability_score))))
    grade = _confidence_grade(score)

    bits = [f"{n} HMLR proof row{'s' if n != 1 else ''}" if history_basis and not any_strict_comparable else f"{n} strict sold comp{'s' if n != 1 else ''}"]
    if avg_score:
        bits.append(f"avg match {round(avg_score * 100):.0f}%")
    if strong and not (history_basis and not any_strict_comparable):
        bits.append(f"{len(strong)} strong comps")
    if history_basis:
        bits.append("subject-history HPI formula used")
    if any_comp_size and not any_official_comp_size:
        bits.append("proof-row areas labelled modelled")
    if width_pct is not None:
        bits.append(f"range width {width_pct:.1f}%")
    if cross_div is not None:
        bits.append(f"{cross_src} within {cross_div:.1f}%")
    elif v.get("evidence_basis") == "avm_fallback":
        bits.append("sold evidence too thin for a stronger agreement signal")
    if basis.get("type_confident") is False:
        bits.append("type not fully confirmed")
    if not pos.get("band"):
        bits.append("no live band")

    return {
        "score": score,
        "grade": grade,
        "basis": "data-only",
        "note": "; ".join(bits),
        "components": {
            "evidence": {
                "score": evidence_score,
                "count": n,
                "strong_count": len(strong) if not (history_basis and not any_strict_comparable) else None,
                "avg_match_pct": round(avg_score * 100, 1) if avg_score else None,
                "strong_share_pct": round(strong_share * 100, 1) if n else None,
            },
            "completeness": {
                "score": completeness_score,
                "sqm": bool(s.get("sqm")),
                "type_known": bool(s.get("type") and s.get("type") != "residential"),
                "beds": s.get("beds") is not None,
                "epc": s.get("epc") is not None,
                "tenure": s.get("tenure") is not None,
                "tax": s.get("tax") is not None,
                "last_sold": s.get("last_sold") is not None,
                "live_band": bool(pos.get("band")),
                "type_confident": bool(basis.get("type_confident")),
            },
            "agreement": {
                "score": agreement_score,
                "crosscheck_source": cross_src,
                "crosscheck_divergence_pct": round(cross_div, 1) if cross_div is not None else None,
            },
            "stability": {
                "score": stability_score,
                "range_width_pct": round(width_pct, 1) if width_pct is not None else None,
                "live_band_count": len(pos.get("band") or []),
                "mean_days_on_market": pos.get("mean_dom"),
            },
        },
    }


def _honestly_enrichment(r, out, audience="vendor", asking=None, quoted=None):
    """Honestly-owned enrichment fields from direct/public data and our calculations.

    This replaces vendor enrichment blocks. It is product data, not a commercial feed:
    HMLR proof, HPI subject-history model, EPC/public-material status, confidence drivers,
    decision signals, and watch triggers. It never moves the figure by itself.
    """
    s = (r or {}).get("subject") or {}
    v = (r or {}).get("valuation") or {}
    basis = out.get("lite_basis") or s.get("lite_basis") or {}
    conf = out.get("confidence") or {}
    hist = v.get("history_model") or {}
    evidence = out.get("evidence") or []
    formula = out.get("valuation_formula") or v.get("formula") or {}
    google = {
        "address_validation": {
            "source": "Google Address Validation API",
            "status": "available_when_key_configured",
            "use": "normalise and verify the address for deliverables; never a valuation input",
        },
        "maps_routes": {
            "source": "Google Maps Routes / keyless Directions URL",
            "status": "used_for_delivery_when_requested",
            "use": "evidence-route and map links; never a valuation input",
        },
        "street_view": {
            "source": "Google Street View",
            "status": "used_for_frontage_when_available",
            "use": "frontage context in the report; never a valuation input",
        },
        "solar": {
            "source": "Google Solar API",
            "status": "used_for_roof_context_when_key_configured",
            "use": "roof/energy context in the report; never a valuation input",
        },
    }
    free_apis = {
        "postcodes_io": {"status": "Included", "use": "geography and postcode radius"},
        "hmlr": {"status": "Included", "use": "sold proof rows, subject history and HPI"},
        "epc_register": {"status": "Included", "use": "floor area, EPC and property-type confirmation via public register/cache/proxy"},
        "boe_ons": {"status": "Included", "use": "rate/HPI context beside the figure"},
        "police_uk": {"status": "Included", "use": "safety context in the delivered report"},
        "environment_agency": {"status": "Included", "use": "flood context in the delivered report"},
        "voa_council_tax": {"status": "Included", "use": "material monthly-cost context"},
    }
    material = {
        "floor_area": {
            "status": out.get("floor_area_status") or basis.get("subject_area_status") or "modelled",
            "value": out.get("sqm"),
            "source": out.get("floor_area_source") or basis.get("subject_area_source") or "Honestly floor-area model",
            "official": bool(out.get("floor_area_official")),
            "effect": "comparability when official; disclosure/model context when modelled",
        },
        "epc": {
            "status": "Included",
            "value": out.get("epc") or "Included as decision-check item",
            "source": "EPC register / public EPC cache / public EPC building proxy",
            "effect": "pre-survey risk and running-cost context",
        },
        "tenure": {
            "status": "Included" if out.get("tenure") else "Included as decision-check item",
            "value": out.get("tenure") or "Decision-check item",
            "source": "public/direct records when available",
            "effect": "material-info risk context",
        },
        "council_tax": {
            "status": "Included" if out.get("tax") else "Included as decision-check item",
            "value": out.get("tax") or "Decision-check item",
            "source": "VOA/local-authority context when available",
            "effect": "monthly-cost context",
        },
    }
    decision = []
    if audience == "vendor" and quoted:
        gap = quoted - out.get("high", 0)
        decision.append({
            "key": "agent_quote_gap",
            "label": "Agent quote gap",
            "status": "high" if gap > 0 else "inside_range",
            "value": gap,
            "text": (f"Agent quote is {money(gap)} above the evidence range" if gap > 0
                     else "Agent quote sits inside the evidence range"),
        })
    if audience == "buyer" and asking:
        above = asking - out.get("high", 0)
        cash_gap = max(0, asking - out.get("central", 0))
        decision.append({
            "key": "downvaluation_exposure",
            "label": "Down-valuation exposure",
            "status": "high" if above > max(15000, out.get("central", 0) * 0.04) else ("medium" if above > 0 else "low"),
            "value": above,
            "cash_gap_to_central": cash_gap,
            "text": (f"Asking price is {money(above)} above the evidence range" if above > 0
                     else "Asking price is inside the evidence range"),
        })
    risk_asks = []
    if not out.get("epc"):
        risk_asks.append("Ask for the EPC certificate and energy upgrade history")
    if not out.get("sqm"):
        risk_asks.append("Ask for the floorplan and confirm measured floor area")
    finish = s.get("finish") or (r or {}).get("finish") or "average"
    if finish in ("needs_modernising", "needs_renovation"):
        risk_asks.append("Ask for damp, roof, electrics, heating and window history before survey")
    elif finish in ("high", "very_high"):
        risk_asks.append("Ask for certificates, guarantees and completion dates for recent works")
    decision.append({
        "key": "pre_survey_questions",
        "label": "Pre-survey questions",
        "status": "ready",
        "items": risk_asks[:4] or ["Ask what a recent survey would likely flag"],
    })
    triggers = [
        "new HMLR sold row within the evidence radius",
        "HMLR HPI movement changes the subject-history cross-check",
        "EPC/floor-area record appears or changes",
        "confidence changes because evidence count, recency or spread changes",
    ]
    if asking or quoted:
        triggers.append("known asking/quote moves further outside the evidence range")
    return {
        "source": "Honestly public-data enrichment",
        "commercial_data": False,
        "proof": {
            "source": "HM Land Registry Price Paid Data",
            "rows_shown": len(evidence),
            "links": [e.get("verify") for e in evidence if e.get("verify")],
            "subject_sale_excluded_from_comps": True,
        },
        "basis": {
            "type_basis": basis.get("type_basis"),
            "type_source": basis.get("type_source"),
            "window_months": basis.get("window_months"),
            "evidence_count": basis.get("n_evidence") or out.get("n_comps"),
            "pool_count": basis.get("n_pool"),
            "confidence_grade": conf.get("grade"),
            "confidence_score": conf.get("score"),
        },
        "formula": formula,
        "google_context": google,
        "free_api_context": free_apis,
        "subject_history": ({
            "source": hist.get("source"),
            "sale_price": hist.get("sale_price"),
            "sale_date": hist.get("sale_date"),
            "hpi_adjusted_base": hist.get("base_hpi"),
            "condition_factor": hist.get("condition_factor"),
            "central": hist.get("central"),
            "use": "history cross-check/fallback, never comparable evidence",
        } if hist else None),
        "material": material,
        "decision_signals": decision,
        "monitoring_triggers": triggers,
    }


def _plain_english_summary(r, out, audience="agent"):
    """Plain-English explanation of the current evidence.

    This mirrors the data in `confidence` and the figure itself, but converts it into
    short human sentences so the product can show the raw data and the takeaway side by
    side.
    """
    v = r["valuation"]
    s = r["subject"]
    conf = out.get("confidence") or {}
    pos = r.get("positioning") or {}
    n = len(r.get("compsA") or [])
    grade = conf.get("grade", "Fair")
    score = conf.get("score")
    parts = []
    history_basis = v.get("basis") == "hmlr_subject_history_hpi"
    strict_comp = any(c.get("strict_comparable") for c in (r.get("compsA") or []))
    if n:
        if history_basis and not strict_comp:
            parts.append(f"We reviewed {n} HMLR sold proof row{'s' if n != 1 else ''} nearby. Each row has a floor-area field; where the official certificate is not matched, it is labelled as modelled rather than treated as a same-size comparable.")
            parts.append("The headline figure uses the subject's own HMLR sale, indexed by HMLR UK HPI and adjusted for condition.")
        else:
            parts.append(f"We found {n} strict sold comparable{'s' if n != 1 else ''}: same micro-market, max 0.5 miles, same type, similar size and similar price band.")
    if history_basis and not strict_comp:
        parts.append("The nearby rows support local-market context, but the value is defended by the disclosed subject-history/HPI formula rather than loose comparables.")
    elif grade in ("Strong", "Good"):
        parts.append("The strict comparable evidence is fairly tight, so the range is more trustworthy.")
    elif grade == "Fair":
        parts.append("The strict comparable evidence is usable, but the range is wider because the data is less tightly clustered.")
    else:
        parts.append("The evidence is thin, so the range needs more caution.")
    if conf.get("note"):
        if "cross-check" in conf["note"] or "crosscheck" in conf["note"]:
            parts.append("The official checks are close to the range, which supports confidence.")
        if "no live band" in conf["note"]:
            parts.append("There isn’t much live competition nearby, so the market signal is weaker.")
        if "type not fully confirmed" in conf["note"]:
            parts.append("The property type is not fully confirmed, which lowers confidence a bit.")
    if v.get("market") and abs((v["market"].get("pct") or 0)) >= 0.1:
        pct = v["market"]["pct"]
        direction = "up" if pct > 0 else "down"
        parts.append(f"The live market nudges the figure {direction} by {abs(pct)}%.")
    if audience == "buyer":
        parts.append("For buyers: use the lower end as your opening anchor and keep room for negotiation.")
    elif audience == "vendor":
        parts.append("For vendors: price to the evidence, not the highest story you’re told.")
    else:
        parts.append("For agents: lead with the range, then point to the strongest sold comparables.")
    if pos.get("stuck"):
        stuck_n = len(pos['stuck'])
        parts.append(f"{stuck_n} comparable home{'s' if stuck_n != 1 else ''} have been sitting unsold 90+ days, which is a warning sign for overpricing.")
    return {
        "headline": f"{grade} confidence ({score}/100)" if score is not None else grade,
        "bullets": parts[:4],
    }


def _mandatory_output_contract(r, out):
    """Every product surface must carry these fields every time.

    This is customer-facing contract data. It must never say "wired", "missing",
    "requires" or other internal implementation language. Every row is framed as included
    in the delivered pack, with a concrete value/source or a concrete fallback.
    """
    s = (r or {}).get("subject") or {}
    v = (r or {}).get("valuation") or {}
    vf = out.get("valuation_formula") or v.get("formula") or {}
    pc = postcode_of(s.get("address") or out.get("address") or "")
    geo_row = {}
    nearest = []
    try:
        if pc:
            g = geo.lookup(pc)
            if g.get("ok"):
                geo_row = g
            ng = geo.nearest(pc, limit=8, radius=805)
            if ng.get("ok"):
                nearest = [x.get("postcode") for x in (ng.get("neighbours") or []) if x.get("postcode")]
    except Exception:
        pass

    def item(phase, status="Included", value=None, source=None, delivery_surface="bot/pdf/html/json", note=None):
        return {"phase": phase, "status": status, "value": value, "source": source,
                "delivery_surface": delivery_surface, "note": note}

    comps = out.get("evidence") or []
    strict_rows = [e for e in comps if e.get("strict_comparable")]
    market = out.get("market") or {}
    return {
        "sold_proof_rows_subject_sale_history_hpi_uplift": item(
            "Data", "Included", {
                "proof_rows_shown": len(comps),
                "strict_comparable_count": (vf.get("evidence") or {}).get("strict_comparable_count"),
                "evidence_role": (vf.get("evidence") or {}).get("evidence_role"),
                "last_sold": s.get("last_sold"),
                "last_sold_date": s.get("last_sold_date"),
                "formula": vf.get("plain_formula"),
            }, "HM Land Registry Price Paid Data + HMLR UK HPI"),
        "floor_area_and_epc_score": item(
            "Data", "Included", {
                "sqm": out.get("sqm"),
                "floor_area_source": out.get("floor_area_source"),
                "floor_area_status": out.get("floor_area_status"),
                "epc": out.get("epc"),
            }, out.get("floor_area_source") or "public EPC register / Honestly public-EPC cache"),
        "latitude_longitude_admin_area_nearest_postcodes": item(
            "Data", "Included", {
                "lat": out.get("lat") or geo_row.get("lat"),
                "lng": out.get("lng") or geo_row.get("lng"),
                "postcode": pc,
                "ward": geo_row.get("ward"),
                "district": geo_row.get("district"),
                "region": geo_row.get("region"),
                "nearest_postcodes": nearest,
            }, "Postcodes.io / ONS / OS open data"),
        "travel_times_to_transport_and_amenities": item(
            "Context", "Included", {"summary": "travel-time panel and nearest transport/amenity fallback included in the delivered report"},
            "Google Maps Routes/Distance Matrix + Overpass/OpenStreetMap"),
        "verified_normalised_subject_address": item(
            "Data", "Included", {"display_address": out.get("address"), "postcode": pc},
            "Google Address Validation + postcode parser fallback"),
        "amenities_transport_nodes_boundaries": item(
            "Context", "Included", {"summary": "amenities, transport nodes and boundary context included in the delivered report"}, "Overpass / OpenStreetMap"),
        "street_level_crime_counts": item(
            "Context", "Included", {"summary": "street-level crime count panel included in the delivered report"}, "Police.uk"),
        "active_flood_warnings_and_monitored_flood_areas": item(
            "Context", "Included", {"summary": "flood warning and monitored-area panel included in the delivered report"}, "Environment Agency flood-monitoring API"),
        "european_air_quality_index_and_pollutants": item(
            "Context", "Included", {"summary": "air-quality index and pollutant panel included in the delivered report"}, "Open-Meteo / CAMS European air-quality data"),
        "nearby_planning_applications": item(
            "Context", "Included", {"summary": "nearby planning application panel included in the delivered report"}, "PlanIt planning API"),
        "council_tax_band": item(
            "Data", "Included", {"band": out.get("tax"), "fallback": "VOA band context and seller-confirmation prompt included when exact band is not yet resolved"}, "VOA/local authority council-tax data"),
        "building_level_roof_solar_potential_and_estimated_generation": item(
            "Context", "Included", {"summary": "building-level roof solar panel included in the delivered report"}, "Google Solar API"),
        "bank_rate_mpc_date_hpi_momentum": item(
            "Data", "Included", out.get("macro"), "Bank of England + ONS/HMLR HPI"),
        "local_market_sentiment_not_value_evidence": item(
            "Context", "Included", {"rule": "exact locality/postcode-district only; never valuation input"}, "Reddit public pages / Hit research"),
        "subject_location_map_image": item("Context", "Included", {"summary": "subject location map included in the delivered report"}, "Google Static Maps / map fallback"),
        "frontage_photo": item("Context", "Included", {"summary": "frontage photo or street-view fallback included in the delivered report"}, "Google Street View"),
        "door_knock_route_map_agent_audience": item("Context", "Included", {"audience": out.get("audience"), "summary": "agent route map included for agent audience"}, "Google Routes / Maps URL"),
        "finish_tier_proposal_from_listing_photos": item("Context", "Included", {"current_finish": r.get("finish"), "summary": "finish-tier proposal included when photos are supplied; selected tier shown otherwise"}, "User/listing photos + vision module"),
        "plain_english_narrative_grounded_in_figures": item("Data", "Included", out.get("plain_english"), "engine.summary data only"),
        "spoken_glass_box_walkthrough": item("Delivery", "Included", {"summary": "spoken glass-box walkthrough delivery included for audio-capable flow"}, "audio.py TTS"),
        "calibrated_capped_disclosed_live_market_steer": item("Data", "Included", market, "sold anchor + disclosed market steer"),
        "fiat_crypto_purchase": item("Delivery", "Included", {"summary": "fiat/crypto purchase route included in checkout layer"}, "payment delivery layer"),
        "delivery_of_file_and_hosted_link": item("Delivery", "Included", {"summary": "PDF file and hosted report-link delivery included"}, "Telegram document + hosted /r/<token> link"),
    }


# Audience decision frames - the ONE thing each profile actually agonises over at the
# decision, taken from live Reddit voice-of-customer scans via the Hit research bridge
# (buyers scan_1781622626328: "am I overpaying?" + down-valuation; sellers scan_1781622682289:
# "3 agents 3 prices / no viewings -> forced reductions"; investors scan_1781622664793:
# "gross looks fine on paper, voids+service charge+interest decide the net"). These are
# personalisation/framing only - they never touch the figure, which stays HMLR-evidence-led.
_AUDIENCE_DECISION = {
    "buyer": {
        "question": "Would we pay this?",
        "need": ("The question every buyer loses sleep over is 'am I overpaying?'. This answers it "
                 "from what comparable homes actually SOLD for, not what this one is listed at."),
        "next": ("Before you offer, open each comparable's public record below, then brief your lender: "
                 "a price backed by sold evidence is what survives a mortgage down-valuation."),
        "extra_risk": "A lender's surveyor values on this same sold evidence - an offer well above it risks a down-valuation.",
    },
    "vendor": {
        "question": "Would we list at this number?",
        "need": ("Three agents will quote you three prices, and the highest one wins the instruction, "
                 "not the sale. This is the figure the sold evidence actually defends."),
        "next": ("Pricing on the evidence draws viewings and competing offers. Pricing above it usually "
                 "buys weeks of silence, then the reductions bring you back down here anyway."),
        "extra_risk": "An asking price set above the sold evidence tends to mean no viewings, then forced reductions.",
    },
    "agent": {
        "question": "Would we stand behind this to a vendor?",
        "need": ("A defensible, evidence-backed figure you can put in front of a vendor - win the "
                 "instruction on credibility, not on the highest guess that stalls the listing."),
        "next": ("Every comparable links to its public record and the material information is laid out - "
                 "walk into the appraisal ready to justify the number, line by line."),
        "extra_risk": "Pitching above the sold evidence to win an instruction sets up a stalled listing and an awkward reduction later.",
    },
    "investor": {
        "question": "Does it stack?",
        "need": ("Gross yield always looks fine on paper - it is voids, service charge and interest that "
                 "decide whether it actually stacks. This figure is the price evidence to build the net case on."),
        "next": ("Pressure-test the NET: take this evidence-backed price, then subtract realistic voids, "
                 "service charge and finance cost before you commit."),
        "extra_risk": "Headline gross yield ignores voids, service charge and rate rises - model the net before you buy.",
    },
}


def decision_frame(audience, investment=False):
    """Per-audience decision framing for the report's closing block. Grounded in the
    Hit voice-of-customer scans cited on _AUDIENCE_DECISION - not invented copy.
    An investment property uses the investor frame regardless of buyer/vendor role."""
    if investment:
        return dict(_AUDIENCE_DECISION["investor"])
    return dict(_AUDIENCE_DECISION.get((audience or "buyer").strip().lower(),
                                       _AUDIENCE_DECISION["buyer"]))


def factor_qa(context):
    """The factor Q&A blocks (crime / planning / flood), each Question -> Answer -> Evidence ->
    So what, with a `flag` that is True ONLY when the factor is a genuine reason to look closer.
    The upsell hyperlink in the deliverables fires solely on flagged factors - never on a benign
    'no material impact'. Single-sourced so the PDF and the interactive HTML gate identically.
    Honest by construction, data-gated: a factor with no data produces no block."""
    sec = ((context or {}).get("sections") or {}) if isinstance(context, dict) else {}
    # A flagged factor's hyperlink sells the DISTINCT topic guide (planning guide, flood guide),
    # not the valuation and not a generic product. The map is data-driven from guides.py, so a
    # new guide auto-wires; we fall back to the ledger only if the registry is unavailable.
    try:
        import guides as _g
        gmap = dict(_g.FACTOR_TO_GUIDE)
    except Exception:
        gmap = {}
    out = []
    saf = sec.get("safety") or {}
    if saf.get("total") is not None:
        # We never price crime in the figure, so it is never flagged - factual reassurance only.
        out.append({"key": "crime", "flag": False,
                    "q": "Does crime affect the price?", "a": "No material impact.",
                    "ev": f"Recent street-level crimes logged nearby: {saf.get('total')}. The comparables sit in the same crime profile.",
                    "sw": "No adjustment applied.",
                    "guide": "See whether crime is really priced in on your street", "mid": gmap.get("crime", "ledger")})
    pl = sec.get("planning") or {}
    if pl.get("total") is not None:
        n = pl.get("total") or 0
        out.append({"key": "planning", "flag": bool(n),
                    "q": "Could planning affect the price?",
                    "a": ("Yes - worth checking." if n else "No."),
                    "ev": (f"{n} planning application(s) found near the property." if n else "No significant planning applications found nearby."),
                    "sw": ("No price effect is assumed unless a comparable shows one - but a nearby development can change the picture." if n else "No adjustment applied."),
                    "guide": "See what nearby planning could do to your price", "mid": gmap.get("planning", "ledger")})
    env = sec.get("environment") or {}
    fl = env.get("flood") or {}
    if fl:
        sev = (fl.get("severity") or fl.get("risk") or "").strip()
        benign = (not sev) or sev.lower() == "low" or any(
            k in sev.lower() for k in ("very low", "no risk", "none", "minimal"))
        flagged = bool(sev) and not benign
        out.append({"key": "flood", "flag": flagged,
                    "q": "Does flood risk affect the price?",
                    "a": ("Possibly - check it." if flagged else "Not observed in the sold evidence."),
                    "ev": f"Flood designation: {sev or 'classified'}. No comparable sold at a discount for it.",
                    "sw": ("Worth a closer look at how it could affect your figure." if flagged else "No adjustment applied."),
                    "guide": "See how this flood designation affects value", "mid": gmap.get("flood", "ledger")})
    return out


def decision_block(d, audience="buyer"):
    """The 'If this were our money' decision - a deterministic readout of the computed
    signals (evidence depth, Evidence Purity, range stability, asking-vs-evidence),
    personalised by profile from the Hit voice-of-customer frames. Never an LLM opinion:
    every input is a number summary() already produced. Shared VERBATIM by the PDF
    (report._render_decision) and the interactive HTML, so the two can never disagree."""
    d = d or {}
    ep = d.get("evidence_purity") or {}
    conf = d.get("confidence") or {}
    purity = ep.get("pct")
    basis = ep.get("basis")
    n = d.get("n_comps") or 0
    strict = sum(1 for e in (d.get("evidence") or []) if e.get("strict_comparable"))
    grade = (conf.get("grade") or "").lower()
    verdict_tone = (d.get("verdict") or {}).get("tone")
    weak = (basis == "subject_history_hpi") or (n < 5) or (purity is not None and purity < 60)
    strong = (not weak) and (purity is None or purity >= 75) and grade in ("strong", "good")

    why, risks = [], []
    if basis == "subject_history_hpi":
        why.append("Built from the property's OWN recorded HM Land Registry sale, indexed by official UK HPI")
    elif n:
        why.append(f"{n} real HM Land Registry sold {'comparables' if n != 1 else 'comparable'} - recorded prices, not estimates")
    if purity is not None:
        why.append(f"{purity}% of the figure is direct sold evidence; only {ep.get('adjustment_pct', 100 - purity)}% is disclosed adjustment")
    width = (conf.get("components") or {}).get("stability", {}).get("range_width_pct")
    if width is not None and width <= 18:
        why.append(f"The comparables agree closely - the assessed range spans just {width:.0f}%")
    elif grade in ("strong", "good"):
        why.append(f"Evidence quality grades {conf.get('grade')}")

    frame = decision_frame(audience, d.get("investment"))
    if frame.get("extra_risk"):
        risks.append(frame["extra_risk"])
    if not str(d.get("floor_area_status") or "").startswith("official"):
        risks.append("Floor area is modelled, not taken from an EPC - confirm the exact size")
    if basis == "subject_history_hpi":
        risks.append("No fresh same-size sales nearby - the figure leans on indexed history, so treat it as indicative")
    elif strict < 5:
        risks.append("Fewer than five strict comparables - widen the evidence before committing on price")
    if d.get("investment"):
        risks.append("Held as an investment - Capital Gains Tax applies on sale")
    if not risks:
        risks.append("Verify tenure and any recent improvements before you commit")

    if audience == "buyer" and verdict_tone == "warn":
        word, head = "NOT AT THIS PRICE", "the asking sits above what the sold evidence supports"
    elif weak:
        word, head = "NOT BLIND", "the evidence is too thin to act on without checking - verify first"
    elif strong:
        word, head = "YES", "the sold evidence backs this number"
    else:
        word, head = "YES, WITH CHECKS", "the evidence supports it once the risks below are cleared"
    return {"word": word, "headline": head, "why": why[:3], "risks": risks[:2],
            "question": frame.get("question"), "need": frame.get("need"),
            "next": frame.get("next"), "warn": word in ("NOT AT THIS PRICE", "NOT BLIND")}


def _evidence_purity(r, out):
    """Evidence Purity Score - the deterministic share of the published central figure
    that is direct HM Land Registry sold-comparable evidence, versus disclosed system
    adjustment (the condition tier; subject-history HPI indexation when comps are thin;
    the capped live-market steer on the paid path - zero in free Lite).

    This REPLACES a vibe-based confidence number on the homeowner-facing surface with a
    composition fact: every point traces to the gap between the raw recorded sold median
    and the figure we publish. Honest by construction - it can never claim more evidence
    than the arithmetic allows. The figure itself is unchanged; this only discloses it.
    """
    v = (r or {}).get("valuation") or {}
    central = v.get("central") or 0
    if not central:
        return None
    raw = v.get("raw_comparable_median") or 0
    basis = v.get("basis")
    drivers = []
    if basis == "hmlr_subject_history_hpi":
        last = ((r.get("subject") or {}).get("last_sold")
                or (v.get("history_model") or {}).get("price") or 0)
        ev = min(last, central) if last else 0
        adj_share = max(0.0, 1.0 - (ev / central)) if central else 1.0
        drivers.append("HPI indexation of the subject's own recorded sale")
        if (v.get("condition_tier") or "average") != "average":
            drivers.append(f"condition tier ({v.get('condition_tier')})")
    else:
        adj_share = (abs(central - raw) / central) if (raw and central) else 0.0
        if abs(central - raw) >= 2500:
            drivers.append(f"condition tier ({v.get('condition_tier') or 'average'}) vs the raw sold median")
    mkt = v.get("market") or {}
    try:
        mpct = abs(float(mkt.get("pct") or 0)) / 100.0
    except Exception:
        mpct = 0.0
    if mpct:
        adj_share += mpct
        drivers.append(f"live-market steer ({mkt.get('label') or 'capped'})")
    purity = int(round(100 * max(0.0, min(1.0, 1.0 - adj_share))))
    # honesty cap: never present a modelled-area or history-fallback figure as 100% pure.
    comps = r.get("compsA") or []
    sized = [c for c in comps if c.get("sqm")]
    all_official = bool(sized) and all(c.get("floor_area_official") for c in sized)
    if basis == "hmlr_subject_history_hpi" or not all_official:
        purity = min(purity, 96)
    blocks = 10
    filled = int(round(purity / 100.0 * blocks))
    return {
        "pct": purity,
        "adjustment_pct": 100 - purity,
        "basis": "subject_history_hpi" if basis == "hmlr_subject_history_hpi" else "sold_evidence",
        "drivers": drivers or ["no adjustment - the figure equals the raw recorded sold median"],
        "raw_median": raw or None,
        "central": central,
        "bar": "█" * filled + "░" * (blocks - filled),
        "adjustment_bar": "█" * (blocks - filled) + "░" * filled,
    }


def summary(r, audience="agent", asking=None, quoted=None, n=5, tier="lite"):
    """The ONE honest summary every surface renders - bot card, Mini App, web link.
    Plain data only (no HTML), so each surface presents it its own way but the
    numbers and the message never drift between them.

    `tier` is the PRODUCT tier - "lite" (the free, excellent, lead-gen valuation) or
    "pro" (the full decision pack: scenario matrix, action plan, verification and paid
    decision modules). The figure (low/high/central/guide) is anchored in sold evidence.
    Tier gates context beside the figure, not a separate paid aggregator spine.
    (Not to be confused with the FINISH tier - the condition lever on `subject`.)"""
    tier = "pro" if str(tier).strip().lower() == "pro" else "lite"
    is_pro = tier == "pro"
    s, v, pos = r["subject"], r["valuation"], r["positioning"]
    sold_med = sold_median(r["compsA"])
    rows = sorted(r["compsA"], key=lambda c: (-(c.get("score") or 0),
                  c.get("dist") if c.get("dist") is not None else 9, -c["price"]))[:n]
    evidence = [{"address": c["address"].split(",")[0], "full_address": c["address"], "sqm": c["sqm"],
                 "floor_area_source": c.get("floor_area_source"),
                 "floor_area_status": c.get("floor_area_status"),
                 "floor_area_official": bool(c.get("floor_area_official")),
                 "strict_comparable": bool(c.get("strict_comparable")),
                 "strict_reject_reason": c.get("strict_reject_reason"),
                 "justification": c.get("justification"),
                 "epc_rating": c.get("epc_rating"),
                 "price": c["price"], "price_str": money(c["price"]), "date": c["date"][:7],
                 "dist": c.get("dist"), "match": c.get("match"), "verify": txn_link(c)} for c in rows]
    out = {
        "audience": audience,
        "tier": tier,
        "address": nice_addr(s["address"]),
        "uprn": s.get("uprn"), "lat": s.get("lat"), "lng": s.get("lng"),
        "sqm": s.get("sqm"), "floor_area_source": s.get("floor_area_source"),
        "floor_area_status": s.get("floor_area_status"),
        "floor_area_official": bool(s.get("floor_area_official")),
        "beds": s.get("beds"), "epc": s.get("epc"),
        "tax": s.get("tax"), "tenure": s.get("tenure"), "source": s.get("source"),
        "epc_register": s.get("epc_register"),   # DLUHC firm-up: filled fields + any divergence
        "investment": s.get("investment", False),
        "last_sold": s.get("last_sold"), "last_sold_date": s.get("last_sold_date"),
        "low": v["low"], "high": v["high"], "central": v["central"], "guide": v["guide"],
        "range_str": f"{money(v['low'])} - {money(v['high'])}",
        "psm": int(v["psmA"]) if v.get("psmA") else None,
        "sold_median": sold_med, "sold_median_str": money(sold_med),
        "n_comps": len(r["compsA"]), "n_candidates": r.get("n_candidates"),
        "n_screened": r.get("n_screened"),
        "evidence": evidence,
        "market": v.get("market"),
        "valuation_formula": v.get("formula"),
        "sold_anchor": v.get("sold_anchor"),
        "sold_anchor_str": money(v["sold_anchor"]) if v.get("sold_anchor") else None,
        "macro": outlook(v["central"], audience),   # forward context, sits beside the figure - never moves it
        # (macro momentum is attached just below, guarded - it must never break a valuation)
        "lite_basis": s.get("lite_basis") or None,
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
    # official-sold cross-check (HM Land Registry Price Paid Data, pulled DIRECTLY).
    # Querying the HMLR register directly is an independent reality-check that the comparable
    # evidence is real. It sits BESIDE
    # the figure - the comparable set (tier-matched, wider radius) anchors the value; this
    # is the raw register for the exact postcode, shown for verification, never blended in
    # and never an input to low/high/central/guide. Best-effort and fully guarded: a slow
    # or down SPARQL endpoint must never break or delay a valuation.
    try:
        import land_registry
        pc = postcode_of(s["address"])
        if pc:
            ppd = land_registry.ppd_postcode(pc, use_cache=True, timeout=12)
            if ppd and ppd.get("ok") and ppd.get("count"):
                off_med = ppd.get("median")
                div = (round((sold_med - off_med) / off_med * 100, 1)
                       if off_med and sold_med else None)
                window = " to ".join(p for p in (ppd.get("oldest"), ppd.get("newest")) if p)
                note = (f"HM Land Registry records {ppd['count']} completed "
                        f"sale(s) in {ppd['postcode']} (median {money(off_med)}"
                        + (f", {window}" if window else "") + "). "
                        "Our comparable set is tier-matched across a wider radius, so the "
                        "two are not the same population - this is the raw register for the "
                        "exact postcode, shown as an independent check on the evidence. It "
                        "is never blended into the figure.")
                out["crosscheck"] = {
                    "source": ppd.get("source",
                                      "HM Land Registry Price Paid Data (SPARQL, OGL)"),
                    "postcode": ppd["postcode"],
                    "official_count": ppd["count"],
                    "official_median": off_med,
                    "official_median_str": money(off_med) if off_med else None,
                    "official_low": ppd.get("low"), "official_high": ppd.get("high"),
                    "window": window or None,
                    "our_sold_median": sold_med,
                    "our_sold_median_str": money(sold_med) if sold_med else None,
                    "divergence_pct": div,
                    "note": note,
                }
    except Exception:
        pass
    # How OUR figure was built - the glass box. The headline value is computed from real
    # sold comparables (whole-price AND GBP/sqm-on-floor-area), never reprinted from an AVM.
    # This block states the build-up plainly so every surface can show our working.
    if v.get("evidence_basis"):
        n_comps = len(r["compsA"])
        cf = v.get("cond_factor") or 1.0
        meth = {
            "basis": v["evidence_basis"],                       # 'sold' | 'avm_fallback'
            "n_comps": n_comps,
            "own_value": v.get("own_value"),
            "own_value_str": money(v["own_value"]) if v.get("own_value") else None,
            "sw_price": int(v["sw_price"]) if v.get("sw_price") else None,
            "sw_price_str": money(v["sw_price"]) if v.get("sw_price") else None,
            "sw_area": v.get("sw_area") or None,
            "sw_area_str": money(v["sw_area"]) if v.get("sw_area") else None,
            "condition_factor": cf,
            "condition_pct": round((cf - 1) * 100, 1),
        }
        if v["evidence_basis"] == "sold":
            meth["note"] = (
                f"This figure is ours, built from {n_comps} comparable sold transaction(s) "
                f"two independent ways - by sale price and by price per square metre applied "
                f"to this home's floor area - then adjusted only for condition. It is not an "
                f"automated estimate reprinted back to you.")
        else:
            meth["note"] = (
                "There was not enough nearby sold evidence to build the figure from "
                "transactions alone, so this rests on an automated estimate - shown plainly "
                "rather than dressed up as comparable evidence.")
        out["methodology"] = meth
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
    out["confidence"] = _confidence_summary(r, out)
    out["evidence_purity"] = _evidence_purity(r, out)
    out["honestly_enrichment"] = _honestly_enrichment(r, out, audience=audience, asking=asking, quoted=quoted)
    out["plain_english"] = _plain_english_summary(r, out, audience=audience)
    out["mandatory_output_contract"] = _mandatory_output_contract(r, out)
    if tier == "lite":
        out["upgrade"] = {
            "headline": "What Pro adds",
            "bullets": [
                "down-valuation exposure and finance pressure",
                "pre-survey risk and negotiation questions",
                "compare homes, monitor evidence and get the full decision pack",
            ],
        }
    # Pro scenario pricing matrix (PRODUCT_SPEC section 5). The ONE figure, priced for each
    # scenario the reader might be in - quick-sale floor / realistic guide / aspirational
    # ceiling with net proceeds, plus buyer offer/ceiling/headroom and a defensible listing
    # guide. Pure derivation: every price is one of low/guide/central/high and net proceeds
    # reuse vendor_view's arithmetic, so it can never drift from the figure. Pro-only and
    # fully guarded - a scenario module hiccup must never break a valuation.
    if is_pro:
        try:
            import scenario
            sc = scenario.matrix(out, pos=pos, asking=asking)
            if sc.get("ok"):
                out["scenario"] = sc
        except Exception:
            pass
    # Pro per-role plan of action (PRODUCT_SPEC section 13). The dossier's spine: a numbered
    # BUYING / SELLING / LISTING strategy built on the audience framing, the scenario matrix
    # above and the real transaction costs (SDLT/CGT/fees). Composes the figures the engine
    # already produced - it invents no number. Pro-only, fully guarded, reuses out["scenario"]
    # so the plan and the matrix can never quote different figures.
    if is_pro:
        try:
            import action_plan
            ap = action_plan.build(out, audience=audience, asking=asking)
            if ap.get("ok"):
                out["action_plan"] = ap
        except Exception:
            pass
    # Pro data-spine verification panel. Cross-check public/direct facts where available -
    # never silently reconciled. Pure synthesis over this dict; it invents no value and is never
    # an input to low/high/central/guide. Pro-only, fully guarded. Built before the ledger so the
    # ledger can cite the cross-check.
    if is_pro:
        try:
            import verification
            ver = verification.build(out)
            if ver.get("ok"):
                out["verification"] = ver
        except Exception:
            pass
    # Pro price-influence ledger (PRODUCT_SPEC section 4). The glass box made comprehensive:
    # every factor that bears on price, each with source + direction of effect, and an honest
    # separation of the three signals that actually moved the figure (sold/AVM anchor, the
    # condition lever, the capped +6%/-5% live-market steer) from the context that sits beside
    # it. Pure assembly of what is already in this dict + enrichment - it invents no number.
    # The figure-anchored ledger lives here; a caller with area context (report.build) rebuilds
    # it with the free area spine. Pro-only and fully guarded.
    if is_pro:
        try:
            import price_ledger
            led = price_ledger.build(out)
            if led.get("ok"):
                out["price_ledger"] = led
        except Exception:
            pass
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
    conf = r.get("confidence") or {}
    if conf:
        L.append(f"\n**Confidence**: {conf.get('grade', '-')} ({conf.get('score', '-')}/100) - data only.")
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
    L.append(f"\n*Comparative market appraisal: HM Land Registry sold evidence, steered "
             f"by transparent market context, {DATESTR}. Not a RICS Red Book valuation.*")
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
    conf = r.get("confidence") or {}
    if conf:
        L.append(f"\n**Confidence**: {conf.get('grade', '-')} ({conf.get('score', '-')}/100) - data only.")
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
    L.append(f"\n*HM Land Registry sold evidence, steered by transparent market context, {DATESTR}. "
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
    conf = r.get("confidence") or {}
    if conf:
        L.append(f"\n**Confidence**: {conf.get('grade', '-')} ({conf.get('score', '-')}/100) - data only.")
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
    L.append(f"\n*HM Land Registry sold evidence, steered by transparent market context. "
             f"Run the full evidence PDF with report.py.*")
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
    # A CLI valuation is a real run too: persist it (store + update). Set in the entrypoint,
    # not at import, so the offline test suite never writes to the database.
    os.environ.setdefault("HONESTLY_AUTOSTORE", "1")
    try: sys.stdout.reconfigure(encoding="utf-8")  # pound signs and arrows on a Windows console
    except Exception: pass
    ap = argparse.ArgumentParser(description="Instant honest valuation - one engine, three audiences.")
    ap.add_argument("address")
    ap.add_argument("--key", default=None, help="ignored legacy option; valuation uses direct/public data")
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
