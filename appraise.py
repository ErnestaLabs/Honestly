#!/usr/bin/env python3
"""appraise.py - one-command UK residential market appraisal.

Pulls HM Land Registry / EPC data via the PropertyData API, builds and
auto-tiers comparable sales, drafts a valuation, and writes:
  <slug>_appraisal.md, <slug>_appraisal.pdf, <slug>_interactive.html, <slug>_comps.csv

Tiering and narrative are DRAFTS for the agent to confirm. Edit <slug>_comps.csv
(set tier = A / B / exclude) and re-run with --finalize to regenerate.

Usage:
  set PROPERTYDATA_KEY=...    (or pass --key)
  python appraise.py "58 Cronin Street, London, SE15 6JH" --beds 4 --baths 2 \
      --finish high --investment --agent "Riccardo Minniti"

Requires: Python 3, matplotlib, numpy; the markdown-to-pdf-windows skill's
md2html.py and Microsoft Edge for the PDF (optional - skips PDF if missing).
"""
import argparse, json, math, os, re, sys, subprocess, statistics, urllib.parse, urllib.request, datetime, csv, time, copy
import brand   # single source of brand truth: palette, logo bytes, references()

API = "https://api.propertydata.co.uk"
STREET_API = "https://api.data.street.co.uk/street-data-api/v2"  # Street Data: 150+ fields on 29m E&W addresses, refreshed daily
TODAY = datetime.date.today()
DATESTR = f"{TODAY.day} {TODAY:%B %Y}"
# legacy chart colour names kept as aliases; every value now resolves to the live
# brand palette (navy/green/teal/gold) via brand.py so the HTML never drifts.
GREEN, ACCENTD, TERRA, GREY, NAVY = (brand.HEX['green'], brand.HEX['navy'],
                                     brand.HEX['gold'], brand.HEX['sand'], brand.HEX['navy'])

class PropertyDataError(RuntimeError):
    """A PropertyData API error RESPONSE (e.g. X04 'Monthly plan limit exceeded'), carrying
    the provider's own code/message plus a clean, user-facing line. We raise this instead of
    letting a quota/auth failure either crash raw OR - worse - be swallowed into an empty
    result that the caller misreads as 'no official record found for that postcode'. Any Xnn
    error is on OUR side (our credits/our key), never the user's address, and the message
    says so. The honesty contract extends to our own failures."""
    # Only X04 is verified live ("Monthly plan limit exceeded: 5000 API credits"). For any
    # other Xnn we still tell the truth - it is a provider/account problem on our side - we
    # just do not claim a specific cause we have not confirmed.
    _FRIENDLY = {
        "X04": ("Live valuations are paused right now: our market-data provider has hit this "
                "month's credit limit. This is on our side, not your address - it will be back "
                "once the plan resets or is topped up."),
    }
    def __init__(self, code, message):
        self.code = (code or "").strip()
        self.provider_message = (message or "").strip()
        friendly = self._FRIENDLY.get(self.code) or (
            "Live valuations are temporarily unavailable: our market-data provider returned an "
            "error on our account (" + (self.code or "no code") + "). This is on our side, not "
            "your address - please try again shortly.")
        super().__init__(friendly)


def api(endpoint, key, _retries=5, **params):
    params['key'] = key
    url = f"{API}/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 appraise.py"})
    for attempt in range(_retries):
        d = None
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < _retries-1:
                time.sleep(6 + attempt*4); continue
            # PropertyData puts its error code/message in the BODY even on a 4xx. Parse it so
            # the real cause (quota, auth) surfaces honestly rather than as a raw crash. If the
            # body is not a recognisable error envelope, re-raise the original HTTPError.
            try:
                d = json.loads(e.read().decode('utf-8', 'replace'))
            except Exception:
                raise
            if not (isinstance(d, dict) and d.get('status') == 'error'):
                raise
        # An error-coded body - whether it arrived via a 4xx above or a 200 carrying
        # status:error. X14 (transient concurrency) is retried; anything else is terminal and
        # raised as a typed, honest error instead of being returned as data the caller trusts.
        if isinstance(d, dict) and d.get('status') == 'error':
            code = d.get('code')
            if code in ('X14',) and attempt < _retries-1:
                time.sleep(6 + attempt*4); continue
            raise PropertyDataError(code, d.get('message'))
        time.sleep(0.4)  # gentle spacing to respect the rate limit
        return d

# ---------------------------------------------------------------- Street Data
# Second provider, alongside PropertyData. Verified against the live API
# (openapi v2.11.6): base STREET_API, auth header `x-api-key`, postcode regex
# allows no space. Tier in {basic, core, premium}; dry_run=true previews cost
# (request_cost_gbp, balance_gbp) without billing. Response: {"data":[...],
# "meta":{total,page,size,pages,request_cost_gbp,balance_gbp}}.
def street_api(endpoint, key=None, _retries=5, **params):
    key = key or os.environ.get('STREETDATA_KEY')
    if not key:
        raise RuntimeError("Set STREETDATA_KEY env var or pass street_key=")
    url = f"{STREET_API}/{endpoint.lstrip('/')}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"x-api-key": key, "User-Agent": "Mozilla/5.0 appraise.py"})
    for attempt in range(_retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < _retries-1:
                time.sleep(6 + attempt*4); continue
            raise
        time.sleep(0.4)  # gentle spacing to respect the rate limit
        return d

def street_postcode(postcode, key=None, tier='core', results=25, dry_run=False):
    """Pull Street Data properties for a postcode. Postcode is normalised to the
    API's no-space pattern (e.g. 'N22 5SU' -> 'N225SU'). Returns the parsed JSON."""
    pc = re.sub(r'\s+', '', (postcode or '').upper())
    params = {'postcode': pc, 'tier': tier, 'results': results}
    if dry_run: params['dry_run'] = 'true'
    return street_api("properties/areas/postcodes", key, **params)

# Street Data property_type strings -> our internal type + the PD-style sold type letter.
_SD_TYPE = {
    "flats/maisonettes": ("flat", "flat"),
    "flat": ("flat", "flat"), "maisonette": ("flat", "flat"),
    "terraced": ("terraced", "terraced_house"), "terrace": ("terraced", "terraced_house"),
    "end terrace": ("terraced", "terraced_house"), "end of terrace": ("terraced", "terraced_house"),
    "semi-detached": ("semi-detached", "semi_detached_house"),
    "semi detached": ("semi-detached", "semi_detached_house"),
    "detached": ("detached", "detached_house"),
    "bungalow": ("detached", "detached_house"),
}


def _sd_attr(rec):
    return (rec or {}).get("attributes") or {}


def _sd_addr_line(a):
    """Human one-line address from a Street Data address block."""
    sf = (a or {}).get("simplified_format") or {}
    sg = (a or {}).get("street_group_format") or {}
    if sg.get("address_lines"):
        line = sg["address_lines"]
        pc = sg.get("postcode")
        return f"{line}, {pc}" if pc and pc not in line else line
    bits = [sf.get("house_number"), sf.get("street"), sf.get("town"), sf.get("postcode")]
    return ", ".join(b for b in bits if b)


def _sd_match(address, records):
    """Pick the Street Data record that IS the subject address, within its postcode pull.
    Matches on building/house number first, then disambiguates flats by the unit token
    appearing in the sub-building name. Returns (record, confident: bool) or (None, False)."""
    pc = postcode_of(address)
    unit = _unit_token(address, pc)            # '58', or a flat number
    names = _name_words(address, pc, unit)     # building/street identifying words
    if not records:
        return None, False
    cands = []
    for rec in records:
        a = _sd_attr(rec).get("address") or {}
        sf = a.get("simplified_format") or {}
        rm = a.get("royal_mail_format") or {}
        num = str(sf.get("house_number") or rm.get("building_number") or "").upper().strip()
        sub = str(rm.get("sub_building_name") or "").upper()
        bldg = str(rm.get("building_name") or "").upper()
        line = _sd_addr_line(a).upper()
        score = 0
        if unit and num == unit.upper():
            score += 5
        if unit and re.search(rf"\b{re.escape(unit.upper())}\b", sub):
            score += 4            # 'FLAT 11' style match inside the sub-building name
        if names:
            score += sum(1 for w in names if w in line or w in bldg)
        if score:
            cands.append((score, rec))
    if not cands:
        return None, False
    cands.sort(key=lambda t: t[0], reverse=True)
    top = cands[0][0]
    confident = top >= 5 and (len(cands) == 1 or cands[1][0] < top)
    return cands[0][1], confident


def _sd_subject(rec):
    """Map ONE Street Data property record into the subject dict shape find_subject returns,
    plus a rich `enrichment` block carrying the facts PropertyData never had (council-tax
    annual charge, full lease term, flood risk, plot, construction, schools, transport). Every
    field traces to a real key in the live response; missing keys degrade to None, never faked."""
    a = _sd_attr(rec)
    addr = a.get("address") or {}
    loc = ((a.get("location") or {}).get("coordinates")) or {}
    sqm = a.get("internal_area_square_metres")
    ptype_raw = ((a.get("property_type") or {}).get("value") or "").strip()
    internal, pdtype = _SD_TYPE.get(ptype_raw.lower(), ("", ""))
    ep = a.get("energy_performance") or {}
    eff = (ep.get("energy_efficiency") or {})
    ct = a.get("council_tax") or {}
    ten = a.get("tenure") or {}
    lease = ten.get("lease_details") or {}
    txs = a.get("transactions") or []
    last = max(txs, key=lambda t: t.get("date") or "", default=None) if txs else None
    ids = (a.get("identities") or {}).get("ordnance_survey") or {}

    yb = a.get("year_built")
    yb_val = yb.get("value") if isinstance(yb, dict) else yb

    subject = {
        "address": _sd_addr_line(addr),
        "uprn": ids.get("uprn"),
        "lat": loc.get("latitude"), "lng": loc.get("longitude"),
        "sqm": sqm,
        "sqft": round(sqm * 10.7639) if sqm else None,
        "beds_est": ((a.get("number_of_bedrooms") or {}).get("value")),
        "baths": ((a.get("number_of_bathrooms") or {}).get("value")),
        "type": internal or ptype_raw.lower(),
        "epc": eff.get("current_efficiency"),
        "tax": ct.get("band"),
        "last_sold": (last or {}).get("price"),
        "last_sold_date": (last or {}).get("date"),
        "tenure": ten.get("tenure_type"),
        "construction": a.get("construction_age_band") or yb_val or "",
    }
    enrichment = {
        "council_tax_annual": ct.get("current_annual_charge"),
        "epc_rating": eff.get("current_rating"),
        "epc_potential": eff.get("potential_rating"),
        "lease_term": lease.get("lease_term"),
        "lease_date": lease.get("date_of_lease"),
        "flood_risk": a.get("flood_risk"),
        "plot_sqm": (a.get("plot") or {}).get("total_plot_area_square_metres"),
        "construction_materials": a.get("construction_materials"),
        "localities": a.get("localities"),
        "education": a.get("education"),
        "transport": a.get("transport"),
        "airport_noise": a.get("airport_noise"),
        "year_built": yb_val,
        "pdtype": pdtype,
    }
    return subject, enrichment


def _sd_neighbour_sales(records):
    """Every recorded HMLR sale across the pulled postcode, joined to that property's own
    floor area + type - i.e. real GBP/sqm sold comps harvested from the SAME paid postcode
    pull at no extra cost. The free HMLR register cannot do this (it has no floor area)."""
    out = []
    for rec in records:
        a = _sd_attr(rec)
        sqm = a.get("internal_area_square_metres")
        ptype_raw = ((a.get("property_type") or {}).get("value") or "").strip().lower()
        internal, pdtype = _SD_TYPE.get(ptype_raw, ("", ""))
        addr = _sd_addr_line(a.get("address") or {})
        for t in (a.get("transactions") or []):
            price = t.get("price")
            if not price:
                continue
            out.append({
                "price": price, "date": t.get("date"), "sqm": sqm,
                "psm": round(price / sqm) if sqm else None,
                "type": internal or ptype_raw, "pdtype": pdtype,
                "is_new_build": t.get("is_new_build"), "address": addr,
            })
    return out


def money(v): return "£{:,.0f}".format(round(v))
def slugify(s): return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')[:40]
def round_to(v, step): return int(round(v / step) * step)

# Portal "max price" search-band thresholds (Rightmove/Zoopla filter ladders): tighter
# steps at the low end, wider as prices rise - the values buyers actually set as ceilings.
_PORTAL_BANDS = sorted(set(
    list(range(50_000, 500_000, 25_000)) +        # < 500k: 25k steps
    list(range(500_000, 1_000_000, 50_000)) +     # 500k-1m: 50k steps
    list(range(1_000_000, 2_000_000, 100_000)) +  # 1m-2m: 100k steps
    list(range(2_000_000, 10_000_001, 250_000))   # 2m+: 250k steps
))

def comp_band(comps, step=5000):
    """Where comparable sold prices actually CLUSTER - the interquartile range (middle 50%),
    not the raw min/max. Same-size flats in a block legitimately span a wide range (a shared-
    ownership/part-buy sale recorded at its share price sits far below a full-market penthouse
    of the same floor area), so presenting the extremes as a 'price tier' is misleading. The
    IQR strips those outliers and describes the honest centre of the evidence. When the
    comps carry comparability scores, the band is drawn from the true comparables only
    (weak/outlier sales excluded), tightening it further. Returns (low, high) rounded to
    step, or None when there are too few comps to be meaningful."""
    strong = [c for c in comps if c.get('price') and not c.get('weak')]
    pool = strong if len(strong) >= 4 else [c for c in comps if c.get('price')]
    prices = sorted(c['price'] for c in pool)
    if len(prices) < 4:
        return None
    lo = round_to(statistics.quantiles(prices, n=4)[0], step)   # 25th percentile
    hi = round_to(statistics.quantiles(prices, n=4)[2], step)   # 75th percentile
    return lo, hi


def _months_old(datestr):
    """Whole-ish months between a 'YYYY-MM-DD' sale date and today. None if unparseable."""
    try:
        d = datetime.date.fromisoformat(str(datestr)[:10])
    except Exception:
        return None
    return max(0.0, (TODAY - d).days / 30.44)


def weighted_median(pairs):
    """Median of values weighted by weight. pairs = [(value, weight), ...]. A value with
    twice the weight pulls the midpoint twice as hard. Non-positive weights are ignored;
    with no positive weights it falls back to the plain median. None if empty."""
    pts = sorted((float(v), float(w)) for v, w in pairs if v is not None and w and w > 0)
    if not pts:
        vals = sorted(float(v) for v, _ in pairs if v is not None)
        return statistics.median(vals) if vals else None
    total = sum(w for _, w in pts)
    acc = 0.0
    for v, w in pts:
        acc += w
        if acc >= total / 2:
            return v
    return pts[-1][0]


# Comparability scoring matrix - a glass-box similarity score (0-100) for each sold sale,
# penalising the parities a valuer weighs: spatial (distance), physical (size + GBP/sqm
# tier), temporal (recency - spent as a WEIGHT, never an HPI price move), and qualitative
# (tenure + stock class). Type parity is already guaranteed upstream: pull_sold filters to
# the subject's property type. Missing data on any axis costs nothing (neutral) - we only
# penalise what the record actually carries, so the score never invents a difference.
COMP_WEAK = 0.45            # below this a sale is shown but is NOT treated as a true comparable

def score_comp(r, subj, base_psm):
    """Return (score 0.05-1.0, breakdown dict of point penalties). Base 100, penalised:
    location -2/0.1mi past ~0.05mi; size -1/sqm of GIA deviation; GBP/sqm free within
    +-15% of the cohort then steep; recency -5/month past 6 months; tenure/stock mismatch."""
    parts, pen = {}, 0.0
    dist = r.get('dist')
    if dist is not None:                                   # spatial parity
        p = min(40.0, 20.0 * max(0.0, dist - 0.05)); parts['location'] = -round(p, 1); pen += p
    ssqm, csqm = subj.get('sqm'), r.get('sqm')
    if ssqm and csqm:                                      # physical parity: size
        p = min(40.0, abs(csqm - ssqm)); parts['size'] = -round(p, 1); pen += p
    psm = r.get('psm') or (r['price'] / csqm if (csqm and r.get('price')) else None)
    if psm and base_psm:                                   # physical parity: GBP/sqm tier
        dev = abs(psm - base_psm) / base_psm
        p = min(50.0, 100.0 * max(0.0, dev - 0.15)); parts['gbp_sqm'] = -round(p, 1); pen += p
    mo = _months_old(r.get('date'))
    if mo is not None:                                     # temporal parity (becomes a weight)
        p = min(40.0, 5.0 * max(0.0, mo - 6.0)); parts['recency'] = -round(p, 1); pen += p
    st, ct = (subj.get('tenure') or '').lower(), (r.get('tenure') or '').lower()
    if st and ct and st != ct:                             # qualitative parity: tenure
        parts['tenure'] = -12; pen += 12
    scl, ccl = (subj.get('class') or '').lower(), (r.get('class') or '').lower()
    if scl and ccl and scl != ccl:                         # qualitative parity: stock class
        parts['stock'] = -8; pen += 8
    return max(0.05, round(1.0 - pen / 100.0, 3)), parts


def sold_median(comps):
    """The score-weighted midpoint of the comparable sold prices (rounded to 1k). True
    comparables (higher match score) pull the midpoint harder than weaker, older or further
    sales. Falls back to the plain median when the comps carry no scores. 0 if empty."""
    m = weighted_median([(c['price'], c.get('score', 1.0)) for c in comps if c.get('price')])
    return round_to(m, 1000) if m else 0


def guide_price(central):
    """The recommended listing guide, snapped to a portal search-band threshold. A guide
    is set a little below the assessed central to draw competing offers; we then snap it
    to the nearest portal 'max price' threshold so it sits ON a band, never just above one.
    This is deliberate marketing strategy: portal max-price filters are inclusive, so a
    listing guided at 800k is seen by every buyer filtering 'up to 800k', whereas an 825k
    guide is invisible to them and competes only in the thinner 800k-850k bracket. The
    assessed low/central/high are untouched - this only sets the number we advise listing
    at, always framed 'Offers Over'."""
    target = central * 0.89
    return min(_PORTAL_BANDS, key=lambda b: (abs(b - target), b - target))

def miles(a, b, c, d):
    R = 3958.7613
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = math.radians(c - a), math.radians(d - b)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))

POSTCODE = re.compile(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})')
def postcode_of(addr):
    m = POSTCODE.search(addr.upper())
    return m.group(1) if m else ''
def txn_link(r):
    """Open proof link for a sold comparable.

    Proof must never send a user to a paywall. Prefer the direct HM Land Registry
    linked-data URI carried by our own SPARQL pull. If a comp came from a paid
    aggregator and has no direct HMLR URI, fall back to the free GOV.UK sold-price
    search page rather than a PropertyData transaction page. The report still shows
    the exact address/date/price row, which is the evidence; the link is only a
    source surface, not the proof itself."""
    h = (r.get('hmlr_uri') or r.get('hmlr_url') or '').strip()
    if h:
        return h.replace('http://', 'https://', 1)
    return 'https://www.gov.uk/search-house-prices'
def tuid_of(url):
    m = re.search(r'transaction/([A-F0-9-]+)', url or '', re.I)
    return m.group(1) if m else ''
def listing_link(url):  # PropertyData outbound -> the live public portal listing (the evidence)
    m = re.search(r'outbound/([a-z]+)/(\d+)', url or '')
    if not m: return ('', '')
    portal, pid = m.group(1), m.group(2)
    spec = {'rightmove': ('Rightmove', f'https://www.rightmove.co.uk/properties/{pid}'),
            'zoopla':    ('Zoopla',    f'https://www.zoopla.co.uk/for-sale/details/{pid}/'),
            'otm':       ('OnTheMarket', f'https://www.onthemarket.com/details/{pid}/'),
            'onthemarket': ('OnTheMarket', f'https://www.onthemarket.com/details/{pid}/')}
    return spec.get(portal, ('', ''))

# ---------------------------------------------------------------- data
_ADDR_STOP = {'FLAT', 'APARTMENT', 'APT', 'UNIT', 'FLOOR', 'LONDON', 'THE', 'AND',
              'ROAD', 'STREET', 'LANE', 'AVENUE', 'CLOSE', 'COURT', 'HOUSE', 'WAY',
              'DRIVE', 'GROVE', 'PLACE', 'TERRACE', 'WALK', 'RISE', 'HILL', 'PARK'}

def _unit_token(address, postcode):
    """The flat/house number a human means: 'Flat 11' or leading '11'. Used to pick
    the right UPRN out of a postcode's list when the fuzzy matcher comes up empty."""
    head = address.upper().replace(postcode.upper(), '').strip(' ,')
    m = re.search(r'\b(?:FLAT|APARTMENT|APT|UNIT)\s*([0-9]+[A-Z]?)\b', head)
    if m: return m.group(1)
    m = re.match(r'\s*([0-9]+[A-Z]?)\b', head)   # leading building/house number
    return m.group(1) if m else ''

def _name_words(address, postcode, unit):
    """Building/street words that identify WHICH property (e.g. SHADWELL, GARDENS),
    minus the unit number, postcode and generic street-type words."""
    up = address.upper().replace(postcode.upper(), '')
    words = set(re.findall(r'[A-Z]{3,}', up)) - _ADDR_STOP
    return words

def _unit_of(u):
    """The flat/house number a UPRN record represents, normalised ('FLAT 11' -> '11')."""
    sec = (u.get('addressParts') or {}).get('secondary') or ''
    if sec:
        return re.sub(r'^(FLAT|APARTMENT|APT|UNIT)\s*', '', sec.upper()).strip()
    lead = re.match(r'\s*([0-9]+[A-Z]?)', (u.get('address') or '').upper())
    return lead.group(1) if lead else ''

def _resolve_uprn(address, key):
    """Return (uprn, matched_address, classification). Fast path: address-match-uprn.
    Fallback: pull a WIDE radius of UPRNs around the postcode and match on unit number
    + building name - this resolves flats and new-builds (even ones split across several
    postcodes) that the fuzzy matcher silently drops. So the user just sends the address;
    we work out the rest. Raises a HELPFUL SystemExit (never a raw HTTP crash) otherwise."""
    try:
        rows = api("address-match-uprn", key, address=address).get('data') or []
    except urllib.error.HTTPError:
        rows = []   # bad/garbled input -> fall through to the postcode path
    if rows:
        r = rows[0]
        return r['uprn'], r.get('address', address), r.get('classificationCodeDesc', '')

    pc = postcode_of(address)
    if not pc:
        sys.exit("I couldn't find a full UK postcode in that. Send it like "
                 "'12 High Street, Town, AB1 2CD'.")
    try:
        # results=200: developments like 'Shadwell Gardens' run past 150 units across
        # several postcodes; the default radius stops too early to find the right flat.
        units = api("uprns", key, postcode=pc, results=200).get('data') or []
    except urllib.error.HTTPError:
        units = []
    if not units:
        sys.exit(f"No official property record found for {pc}. Double-check the "
                 "postcode, or that the address is in England, Wales or Scotland.")

    want = _unit_token(address, pc)
    names = _name_words(address, pc, want)
    # Score every candidate: unit number must match; building-name overlap breaks ties
    # (so '11 Shadwell Gardens' beats 'Flat 11, 16 Martha Street' at the same postcode).
    best = None
    for u in units:
        if want and _unit_of(u) != want.upper():
            continue
        cand = set(re.findall(r'[A-Z]{3,}', (u.get('address') or '').upper()))
        score = len(names & cand)
        same_pc = ((u.get('addressParts') or {}).get('postcode', '').upper() == pc.upper())
        rank = (score, same_pc)
        if best is None or rank > best[0]:
            best = (rank, u)
    # Accept when the building name matches, or when there's no other unit with that
    # number (single hit). A pure number with zero name overlap stays ambiguous.
    if best is not None:
        rank, u = best
        score, _ = rank
        hits = [x for x in units if not want or _unit_of(x) == want.upper()]
        if score > 0 or len(hits) == 1 or not names:
            return u['uprn'], u.get('address', address), u.get('classificationCodeDesc', '')

    # Couldn't pin it - tell them what IS on record nearby so they can disambiguate.
    near = [u.get('address', '') for u in units[:8] if u.get('address')]
    listing = "; ".join(near)
    sys.exit(f"I found {pc} but couldn't pin that exact property. Nearby on record: "
             f"{listing}. Send it matching one of those.")

# Street Data low-level client helpers (street_api / street_postcode / _sd_*) are kept above
# only because the offline test suite guards them ("must not fire from the valuation path").
# They are never called from the live valuation path. We are the vendor now: paid value is
# our decision intelligence over the public spine (HMLR, EPC, ONS/Postcodes.io, EA, BoE,
# Ofcom), not paid re-packaging of public data from a commercial aggregator.
_SD_ENRICH = False
_SD_RESULTS = 0


def epc_firm_up(subj, address, _epc=None):
    """Firm up the subject's floor area + EPC score from the official DLUHC/MHCLG register
    (free spine, BOTH tiers). FILL-ONLY by design: where the primary source left `sqm` or
    the EPC score blank, the register fills it and records the source; where both carry a
    value and they differ materially, the divergence is recorded for the verification panel
    and the anchor's OWN value is KEPT - so the figure never drifts. The official floor area
    is more authoritative than the engine's neighbour-median `_proxy_sqm` guess, which is the
    point of the firm-up. Best-effort; never raises; no-op when no EPC credential resolves
    (so it stays dormant until the key lands). `_epc` injects the client for offline tests."""
    try:
        mod = _epc
        if mod is None:
            import epc as mod
        if not mod.credentials_present():
            return subj
        addr = subj.get('address') or address
        er = mod.for_address(addr, postcode_of(addr))
        if not er.get("ok"):
            return subj
        if not er.get("matched"):
            subj['epc_register'] = {"ok": True, "matched": False,
                                    "reason": er.get("reason"), "source": er.get("source")}
            return subj
        reg = {"ok": True, "matched": True, "rating": er.get("rating"),
               "score": er.get("score"), "floor_area_sqm": er.get("floor_area_sqm"),
               "source": er.get("source"), "filled": [], "divergence": {}}
        fa = er.get("floor_area_sqm")
        if fa:
            if subj.get('sqm') is None:
                subj['sqm'] = fa
                subj['sqft'] = round(fa * 10.7639)
                reg["filled"].append("sqm")
            elif abs(fa - subj['sqm']) / max(fa, subj['sqm']) > 0.10:
                reg["divergence"]["sqm"] = {"register": fa, "subject": subj['sqm']}
        sc = er.get("score")
        if sc is not None:
            if subj.get('epc') is None:
                subj['epc'] = sc
                reg["filled"].append("epc")
            elif sc != subj.get('epc'):
                reg["divergence"]["epc"] = {"register": sc, "subject": subj.get('epc')}
        subj['epc_register'] = reg
    except Exception:
        pass
    return subj


def find_subject(address, key, enrich=None):
    """Resolve the subject from the direct/public spine.

    Legacy PropertyData support remains for now as an optional path where callers still use
    the old Pro engine, but Street Data/Chimnie/PaTMa are not fallbacks. Paid value is
    decision intelligence, not another paid aggregator over public data.
    """
    enrich = False

    pd_subj, pd_err = None, None
    try:
        uprn, matched, cls = _resolve_uprn(address, key)
        u = api("uprn", key, uprn=uprn)['data']
        # Thin records (new builds) often return no propertyType; trust the UPRN
        # classification ('Flat', 'Terraced', ...) so the engine pulls the right comps.
        rtype = (u.get('propertyType') or u.get('description') or cls or '').lower()
        pd_subj = {
            'address': u.get('address', matched), 'uprn': uprn,
            'lat': float(u['lat']), 'lng': float(u['lng']),
            'sqm': round(u['internalArea']/10.7639) if u.get('internalArea') else None,
            'sqft': u.get('internalArea'),
            'beds_est': u.get('estimatedBedrooms'), 'type': rtype,
            'epc': u.get('energyScore'), 'tax': u.get('taxBand'),
            'last_sold': u.get('lastSoldAmount'), 'last_sold_date': u.get('lastSoldDate'),
            'estimate': u.get('estimate'), 'leases': u.get('registeredLeases') or [],
            'construction': u.get('constructionAgeBand', ''),
        }
    except Exception as e:
        pd_err = e
        if not enrich:
            raise           # no fallback configured - surface the real error, never fake a subject

    if pd_subj is not None:
        subj = pd_subj
        subj['source'] = 'propertydata'
    else:
        raise pd_err if pd_err else RuntimeError("subject unresolved from direct/public spine")

    # EPC-register firm-up (free official spine, Lite + Pro). Fills a missing floor area /
    # EPC score from the DLUHC register and records any divergence beside the figure; it
    # never overwrites a value the primary source already carries, so the figure never
    # drifts. Dormant until an EPC credential is configured (built ready for the key).
    subj = epc_firm_up(subj, address)
    return subj

_PC_GEO_CACHE = {}  # module-level postcode -> (lat, lng) cache for the HMLR supplement

def _hmlr_token():
    t = os.environ.get("HMLR_QUERY_TOKEN", "").strip()
    if t: return t
    for p in (os.environ.get("HMLR_QUERY_TOKEN_FILE", ""),
              "/opt/honestly/.hmlr_query_token",
              os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hmlr_query_token")):
        try:
            if p and os.path.exists(p): return open(p, encoding="utf-8").read().strip()
        except Exception: pass
    return ""

def _geocode_postcode(postcode):
    """Return (lat, lng) for a postcode, cached. None, None on miss."""
    pc = (postcode or "").strip().upper()
    if not pc: return None, None
    if pc in _PC_GEO_CACHE: return _PC_GEO_CACHE[pc]
    try:
        import geo as _geo
        r = _geo.lookup(pc)
        result = (r["lat"], r["lng"]) if r.get("ok") and r.get("lat") else (None, None)
    except Exception:
        result = (None, None)
    _PC_GEO_CACHE[pc] = result
    return result

def _batch_geocode(postcodes):
    """Bulk-geocode up to 100 postcodes per call via Postcodes.io /postcodes (POST).
    Populates _PC_GEO_CACHE in place. One network round-trip for the whole set."""
    pcs = [p for p in ((p or "").strip().upper() for p in postcodes)
           if p and p not in _PC_GEO_CACHE]
    if not pcs: return
    # Postcodes.io bulk endpoint: POST /postcodes {"postcodes":[...]}
    for i in range(0, len(pcs), 100):
        batch = pcs[i:i+100]
        try:
            body = json.dumps({"postcodes": batch}).encode()
            req = urllib.request.Request(
                "https://api.postcodes.io/postcodes",
                data=body, headers={"Content-Type": "application/json",
                                    "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                d = json.load(resp)
            for item in (d.get("result") or []):
                qr = item.get("query", "")
                res = item.get("result")
                _PC_GEO_CACHE[qr.strip().upper()] = (
                    (res["latitude"], res["longitude"])
                    if res and res.get("latitude") else (None, None)
                )
        except Exception:
            for pc in batch:
                _PC_GEO_CACHE.setdefault(pc, (None, None))

_PC_EPC_CACHE = {}  # postcode -> {norm_addr: sqm}

def _epc_addr_map(postcode):
    """Fetch EPC certificates for a postcode and build a normalised-address -> sqm dict.
    Returns {} when EPC credentials are absent, the service fails, or no certificates have
    a floor area. Cached per-postcode for the lifetime of the appraise.py process."""
    pc = (postcode or "").strip().upper()
    if not pc: return {}
    if pc in _PC_EPC_CACHE: return _PC_EPC_CACHE[pc]
    try:
        import epc as _epc
        r = _epc.for_postcode(pc, size=100)
        if not r.get("ok"):
            _PC_EPC_CACHE[pc] = {}; return {}
        lkp = {}
        for cert in r.get("certificates", []):
            fa = cert.get("floor_area_sqm")
            if not fa: continue
            norm = re.sub(r"[^a-z0-9 ]", " ", (cert.get("address") or "").lower()).split()
            lkp[" ".join(norm)] = fa
        _PC_EPC_CACHE[pc] = lkp
    except Exception:
        _PC_EPC_CACHE[pc] = {}
    return _PC_EPC_CACHE[pc]

def _hmlr_epc_sqm(saon, paon, street, epc_lkp):
    """Best-effort floor-area match from a pre-built EPC lookup for this postcode."""
    if not epc_lkp: return None
    parts = [p for p in (saon, paon, street) if p]
    if not parts: return None
    raw = " ".join(parts)
    norm_q = re.sub(r"[^a-z0-9 ]", " ", raw.lower()).split()
    if not norm_q: return None
    q_str = " ".join(norm_q)
    if q_str in epc_lkp: return epc_lkp[q_str]
    # token-based fallback: every query token must appear in the EPC key
    for epc_key, sqm in epc_lkp.items():
        if all(t in epc_key for t in norm_q):
            return sqm
    return None

# HMLR ptype → PropertyData pdtype membership
_PTYPE_TO_PDTYPE = {"F": "flat", "T": "terraced", "S": "semi", "D": "detached", "O": None}

def pull_sold_hmlr(subj, pdtype, max_age):
    """Supplement the PropertyData sold pool from the local HMLR Price Paid DB.

    Queries hmlr_query.py (127.0.0.1:8091) for all transactions in the subject's outcode
    within max_age months, geocodes postcodes via geo.py, and tries the EPC register for
    floor areas. Returns records in the same shape as pull_sold so candidate_comps can
    consume them directly. Returns [] when the service is unreachable or the token is absent
    (graceful no-op on the laptop; live on the VPS)."""
    tok = _hmlr_token()
    if not tok: return []
    outcode = postcode_of(subj.get("address", "")).split()
    if not outcode: return []
    outcode = outcode[0]
    since = (datetime.date.today() - datetime.timedelta(days=max(1, max_age) * 30)).strftime("%Y-%m-%d")
    pdtype_l = (pdtype or "").lower()
    qs = urllib.parse.urlencode({"outcode": outcode, "since": since, "limit": 500, "k": tok})
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:8091/sold?{qs}",
            headers={"Accept": "application/json", "User-Agent": "appraise-hmlr/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            d = json.load(resp)
    except Exception:
        return []
    if not (isinstance(d, dict) and d.get("ok")):
        return []
    rows = d.get("rows") or []
    # Type filter: keep matching ptype; 'O' (other) always included as we cannot exclude
    # it without knowing what it is, and PropertyData's feed already has this issue.
    def _keep(ptype):
        if ptype == "F": return "flat" in pdtype_l or "maisonette" in pdtype_l
        if ptype == "T": return "terrace" in pdtype_l
        if ptype == "S": return "semi" in pdtype_l
        if ptype == "D": return "detach" in pdtype_l
        return True  # 'O' or unknown
    rows = [r for r in rows if _keep(r.get("ptype", "O"))]
    if not rows: return []
    slat, slng = subj.get("lat"), subj.get("lng")
    unique_pcs = list({r.get("postcode", "") for r in rows if r.get("postcode")})
    # Batch-geocode all postcodes in 1-2 HTTP round-trips (Postcodes.io bulk endpoint)
    _batch_geocode(unique_pcs)
    # EPC floor-area: only call for postcodes within 0.5 mi of the subject so we don't
    # fan out 100+ serial HTTP requests in the valuation hot path. Cached per postcode.
    try:
        import epc as _epc_mod
        epc_ok = _epc_mod.credentials_present()
    except Exception:
        epc_ok = False
    epc_maps = {}
    if epc_ok and slat and slng:
        for pc in unique_pcs:
            plat, plng = _geocode_postcode(pc)
            if plat and plng:
                try:
                    d_mi = miles(slat, slng, plat, plng)
                except Exception:
                    d_mi = 9
                epc_maps[pc] = _epc_addr_map(pc) if d_mi <= 1.0 else {}
            else:
                epc_maps[pc] = {}
    else:
        epc_maps = {pc: {} for pc in unique_pcs}
    result = []
    for r in rows:
        try:
            price = int(float(r["price"]))
        except (TypeError, ValueError, KeyError):
            continue
        if not price: continue
        postcode = (r.get("postcode") or "").strip().upper()
        lat, lng = _geocode_postcode(postcode)
        dist = None
        try:
            if lat and lng and slat and slng:
                dist = round(miles(slat, slng, lat, lng), 2)
        except Exception:
            pass
        sqm_raw = _hmlr_epc_sqm(r.get("saon"), r.get("paon"), r.get("street"), epc_maps.get(postcode, {}))
        sqm = round(sqm_raw) if sqm_raw else None
        parts = [r.get("saon"), r.get("paon"), r.get("street"), postcode]
        address = ", ".join(p for p in parts if p)
        tuid = (r.get("tuid") or "").strip("{}")
        result.append({
            "address":  address,
            "price":    price,
            "date":     (r.get("date") or "")[:10],
            "lat":      lat,
            "lng":      lng,
            "sqm":      sqm,
            "dist":     dist,
            "source":   "hmlr",
            "hmlr_uri": f"https://landregistry.data.gov.uk/data/ppi/transaction/{tuid}/current" if tuid else None,
        })
    return result

def _pull_sold_pd(subj, key, pdtype, max_age):
    """PropertyData sold comps - fallback only when HMLR local DB is unreachable.
    PropertyData charges for HMLR + EPC combined; we have both free and local."""
    sp = api("sold-prices", key, postcode=postcode_of(subj['address']).split()[0],
             type=pdtype, max_age=max_age, points=200)['data']['raw_data']
    try:
        psf = {r['url']: r for r in api("sold-prices-per-sqf", key,
                 postcode=postcode_of(subj['address']).split()[0], type=pdtype,
                 max_age=max_age, points=200)['data']['raw_data']}
    except Exception:
        psf = {}
    for r in sp:
        m = psf.get(r['url'])
        r['sqm'] = round(m['sqf']/10.7639) if m and m.get('sqf') else None
        try: r['dist'] = round(miles(subj['lat'], subj['lng'], float(r['lat']), float(r['lng'])), 2)
        except Exception: r['dist'] = None
    return sp

def pull_sold(subj, key, pdtype, max_age):
    """Sold comps: HMLR (local DB, free) + EPC floor areas (free). PropertyData
    sold-prices is NOT called - it repackages the same HMLR + EPC data we already
    have. PropertyData is still used for the AVM (valuation-sale) and demand signal."""
    sp = pull_sold_hmlr(subj, pdtype, max_age)
    if not sp:
        # HMLR service down (e.g. process restarting) - fall back to PropertyData
        sp = _pull_sold_pd(subj, key, pdtype, max_age)
    return sp

def pull_listings(subj, key, pdtype):
    """Live on-market asking prices for the district (positioning context, not evidence)."""
    try:
        d = api("prices", key, postcode=postcode_of(subj['address']).split()[0], type=pdtype)
        return d.get('data', {}).get('raw_data', []) or []
    except Exception:
        return []

def positioning(subj, val, listings):
    """Build the live competitive band: same-ish size class, asking near the assessed range.
    Asking prices signal vendor expectation, never used in the valuation."""
    if not listings: return None
    b = subj.get('beds') or 3
    lo_b, hi_b = max(2, b-1), b+1
    lo_p = round_to(0.9*val['guide'], 25000)
    hi_p = round_to(1.30*val['high'], 25000)
    band = [r for r in listings if r.get('bedrooms') in range(lo_b, hi_b+1)
            and r.get('price') and lo_p <= r['price'] <= hi_p]
    if len(band) < 4: return None
    band.sort(key=lambda r: r['price'], reverse=True)
    prices = [r['price'] for r in band]
    doms = [r.get('days_on_market') or 0 for r in band]
    avail = [r for r in band if not r.get('sstc')]
    stuck = sorted([r for r in avail if (r.get('days_on_market') or 0) >= 90],
                   key=lambda r: -(r.get('days_on_market') or 0))
    fresh = [r for r in band if (r.get('days_on_market') or 0) <= 20]
    under_offer = [r for r in band if r.get('sstc')]
    med = round_to(statistics.median(prices), 500)
    return {'band': band, 'lo_p': lo_p, 'hi_p': hi_p, 'lo_b': lo_b, 'hi_b': hi_b,
            'median': med, 'mean_dom': int(statistics.mean(doms)),
            'stuck': stuck, 'fresh': fresh, 'under_offer': under_offer,
            'below_median': med - val['guide']}

def _proxy_sqm(sold, subj):
    """When the record has no floor area, estimate the subject's size from the
    nearest same-type sold flats (median of up to 15 closest with a known sqm).
    Honest: a typical unit at this location, not an invented number."""
    near = sorted((r for r in sold if r.get('sqm') and r.get('dist') is not None),
                  key=lambda r: r['dist'])[:15]
    return statistics.median([r['sqm'] for r in near]) if near else None

def candidate_comps(sold, subj, radius):
    # Size-band around the subject. If the record carries no internal area, estimate
    # it from the nearest comparable sales so the band stays focused on like-for-like
    # units rather than averaging every flat in the district.
    sqm = subj.get('sqm') or _proxy_sqm(sold, subj)
    if sqm:
        lo, hi = sqm*0.85, sqm*1.30
    else:
        lo, hi = 0, float('inf')
    floor = 0.4 * (statistics.median([r['price'] for r in sold]) if sold else 0)
    subj_outcode = postcode_of(subj.get('address', '')).split()[0]
    c = [r for r in sold if r['sqm'] and lo <= r['sqm'] <= hi and r['dist'] is not None
         and r['dist'] <= radius and r['price'] >= floor and 'wolves' not in r['address'].lower()
         and subj['address'].split(',')[0].lower() not in r['address'].lower()]
    def _outcode(r):
        parts = postcode_of(r.get('address', '')).split()
        return parts[0] if parts else ''
    if len(c) < 5:  # widen distance once - same outcode only to avoid cross-district contamination
        c = [r for r in sold if r['sqm'] and lo <= r['sqm'] <= hi and r['dist'] is not None
             and r['dist'] <= min(1.0, radius*2) and r['price'] >= floor
             and _outcode(r) == subj_outcode]
    if len(c) < 3:  # absolute last resort: drop outcode guard but flag cross-district records
        c = [r for r in sold if r['sqm'] and lo <= r['sqm'] <= hi and r['dist'] is not None
             and r['dist'] <= min(1.0, radius*2) and r['price'] >= floor]
        for r in c:
            r['cross_district'] = _outcode(r) != subj_outcode
    pm = statistics.median([r['price']/r['sqm'] for r in c]) if c else 0
    for r in c:
        r['psm'] = round(r['price']/r['sqm'])
        # auto-suggested tier: B if notably pricier per sqm (different market tier)
        r['tier'] = 'B' if r['psm'] > 1.28 * pm else 'A'
    # comparability score: rank each sale by how truly comparable it is to the subject,
    # so the figure leans on actual comparables and outliers (shared-ownership shares,
    # different-tier units) are demoted or excluded - not silently averaged in.
    for r in c:
        r['score'], r['score_parts'] = score_comp(r, subj, pm)
        r['match'] = int(round(r['score'] * 100))
        r['weak'] = r['score'] < COMP_WEAK
    c.sort(key=lambda r: (-r['score'], r['dist'] if r.get('dist') is not None else 9))
    return c

def _weighted_pctile(pairs, q):
    """Weighted q-quantile (0..1) of (value, weight) pairs - the same score weighting the
    figure itself uses, so a closer, more comparable sale counts for more than a distant or
    stale one when we read the spread of the evidence. None if empty."""
    pts = sorted((float(v), float(w)) for v, w in pairs if v is not None and w and w > 0)
    if not pts:
        return None
    total = sum(w for _, w in pts)
    if total <= 0:
        return None
    target, acc = total * q, 0.0
    for v, w in pts:
        acc += w
        if acc >= target:
            return v
    return pts[-1][0]


# Below-average condition has no AVM tier, so we discount our sold-evidence figure.
# Disclosed, conservative cuts: dated/needs modernising vs run-down/needs full renovation.
CONDITION_DISCOUNT = {'needs_modernising': 0.90, 'needs_renovation': 0.80}
# The finish premium (high/very_high) is taken as a RELATIVE ratio off the AVM tiers and
# clamped hard, so a wild AVM can never hijack our evidence figure. At an average finish
# this resolves to 1.0 - the AVM then does not touch the headline number at all.
COND_CLAMP = (0.85, 1.25)

def valuation(subj, compsA, key, finish, pdtype):
    # PropertyData's AVM is pulled but DISTRUSTED. Their estimate is essentially sqm x a
    # generic rate with little regard for the actual comparable evidence; it is exactly the
    # lazy number we exist to beat. So it NEVER sets our figure. We keep it only for (a) a
    # divergence note shown beside our number and (b) the one relative signal it carries -
    # the proportional premium between finish tiers - used, clamped and disclosed, to adjust
    # OUR figure for condition. The headline value is built below from real sold transactions.
    avm = {}
    cons = {'England and Wales: 1976-1982':'1914_2000','pre_1914':'pre_1914'}.get(subj['construction'], '1914_2000')
    for fq in ('average', 'high', 'very_high'):
        try:
            res = api("valuation-sale", key, postcode=postcode_of(subj['address']),
                      property_type='flat' if 'flat' in pdtype or 'maison' in subj['type'] else pdtype,
                      construction_date=cons, internal_area=subj['sqft'] or round(subj['sqm']*10.7639),
                      bedrooms=subj.get('beds') or subj.get('beds_est') or 3,
                      bathrooms=subj.get('baths') or 1, finish_quality=fq,
                      outdoor_space='none', off_street_parking=0)['result']
            avm[fq] = res['estimate']
        except Exception:
            avm[fq] = None

    # --- Honestly's own figure, built TWO independent ways from the same real sold sales:
    #   1. score-weighted median of comparable SALE PRICES   (whole-price evidence)
    #   2. score-weighted comparable GBP/sqm applied to THIS home's measured floor area
    #      (per-area evidence - the honest form of "sqm x rate": a comparable-weighted rate
    #       at the subject's actual size and location, not a blanket district average)
    # Both use the same comparability score (distance, size, GBP/sqm tier, recency, tenure),
    # so a 95%-match recent sale dictates the figure far more than a 60%-match stale one.
    sw_price = weighted_median([(r['price'], r.get('score', 1.0)) for r in compsA]) or 0
    psmA = weighted_median([(r['psm'], r.get('score', 1.0)) for r in compsA if r.get('psm')]) or 0
    sqm = subj.get('sqm')                        # real measured area only (never the proxy)
    sw_area = round(psmA * sqm) if (psmA and sqm) else 0

    # Triangulate. With a measured floor area the per-area view is sounder (it removes size
    # as a confound within the cohort), so we lean to it; with no measured area it drops out
    # and the whole-price view stands alone. The AVM is a LAST resort only when there is no
    # sold evidence at all - flagged via evidence_basis so the report can say so plainly.
    if sw_price and sw_area:
        own = round(0.4 * sw_price + 0.6 * sw_area)
        basis = 'sold'
    elif sw_price or sw_area:
        own = sw_price or sw_area
        basis = 'sold'
    else:
        own = avm.get('average') or avm.get(finish) or 0
        basis = 'avm_fallback'

    # --- Condition: the one attribute that legitimately moves the figure (#16 sub-survey).
    avg = avm.get('average')
    if finish in CONDITION_DISCOUNT:
        cond_factor = CONDITION_DISCOUNT[finish]
    elif finish in ('high', 'very_high') and avg and avm.get(finish):
        cond_factor = max(COND_CLAMP[0], min(COND_CLAMP[1], avm[finish] / avg))
    else:
        cond_factor = 1.0
    central = own * cond_factor

    # --- Range from the ACTUAL dispersion of the comparable evidence, not cosmetic fixed
    # multipliers: the weighted inter-quartile spread of each comp's size-normalised implied
    # value, recentred on our central figure. A tight, consistent cohort yields a narrow
    # range; a noisy one a wide one - honest by construction. A renovation figure (discounted
    # off average-condition comps) and thin evidence both fall back to a conservative band.
    if finish in CONDITION_DISCOUNT:
        half_lo, half_hi = 0.07, 0.05
    else:
        implied = []
        for r in compsA:
            if r.get('weak'):
                continue
            w = r.get('score', 1.0)
            if sqm and r.get('psm'):
                implied.append((r['psm'] * sqm, w))
            elif r.get('price'):
                implied.append((r['price'], w))
        lo_v = _weighted_pctile(implied, 0.25)
        hi_v = _weighted_pctile(implied, 0.75)
        if len(implied) >= 4 and lo_v and hi_v and central:
            half_lo = max(0.03, min(0.18, (central - lo_v) / central))
            half_hi = max(0.03, min(0.18, (hi_v - central) / central))
        else:
            half_lo, half_hi = 0.07, 0.06
    low = round_to(central * (1 - half_lo), 5000)
    high = round_to(central * (1 + half_hi), 5000)
    central = round_to(central, 5000)
    guide = guide_price(central)

    # --- AVM kept as a DISTRUSTED cross-reference, shown beside the number, never folded in.
    avm_ref = avm.get(finish) or avg
    avm_divergence = round((avm_ref / central - 1) * 100, 1) if (avm_ref and central) else None

    return {'avm': avm, 'tierA_med': sw_price, 'psmA': psmA,
            'crosscheck': sw_area or None,
            'sw_price': sw_price, 'sw_area': sw_area, 'own_value': round_to(own, 1000) if own else 0,
            'cond_factor': round(cond_factor, 4), 'evidence_basis': basis,
            'avm_ref': avm_ref, 'avm_divergence': avm_divergence,
            'low': low, 'high': high, 'central': central, 'guide': guide}

def apply_market(val, pos):
    """A home is worth what the market will pay NOW - so we don't anchor on sold data
    alone. Sold evidence sets the floor of fact (what buyers have actually paid), but HM
    Land Registry lags the market by months, so a sold-only figure is always looking
    backwards. We read the live comparable stock - how fast it's going under offer, how
    long it sits, where it's priced - and adjust the sold-anchored value within a tight,
    fully-disclosed cap (+6% in a rising market, -5% in a softening one). This is exactly
    how a valuer adjusts comparables for current conditions: the evidence is the anchor,
    the live market is the steer. Mutates `val`, recording its working under val['market']."""
    val['sold_anchor'] = val['central']           # keep the pre-adjustment, sold+AVM figure
    if not pos or not pos.get('band'):
        val['market'] = {'factor': 1.0, 'pct': 0.0, 'label': 'Sold evidence only', 'dom': None,
                         'sstc_ratio': 0.0, 'stuck_ratio': 0.0, 'ask_median': None,
                         'note': "No asking-price feed is used in this valuation, so the figure rests on completed sold evidence and the disclosed formula."}
        return val
    band = pos['band']; n = len(band) or 1
    dom = pos.get('mean_dom') or 0
    sstc_ratio = len(pos.get('under_offer') or []) / n      # share already under offer = real demand
    stuck_ratio = len(pos.get('stuck') or []) / n           # share stuck 90+ days = aspirational asking
    t = 0.0                                                 # market temperature in [-1, +1]
    if dom:
        if   dom < 45:  t += 0.45
        elif dom < 75:  t += 0.15
        elif dom > 120: t -= 0.45
        elif dom > 90:  t -= 0.15
    t += min(0.45, 1.2 * sstc_ratio)
    t -= min(0.45, 1.2 * stuck_ratio)
    t = max(-1.0, min(1.0, t))
    factor = 1.0 + (0.06 * t if t >= 0 else 0.05 * t)       # +6% rising cap / -5% softening cap
    for k in ('low', 'central', 'high'):
        val[k] = round_to(val[k] * factor, 5000)
    val['guide'] = guide_price(val['central'])
    pct = round((factor - 1) * 100, 1)
    label = ('Rising market' if t > 0.25 else 'Softening market' if t < -0.25 else 'Balanced market')
    pcts = f"{int(round(sstc_ratio*100))}% under offer, {int(round(stuck_ratio*100))}% stuck 90+ days"
    if abs(pct) < 0.1:
        note = (f"Live comparable stock ({dom} days on the market on average, {pcts}) is in line with the "
                f"sold evidence - no adjustment needed.")
    else:
        direction = 'up' if pct > 0 else 'down'
        note = (f"Live comparable stock is averaging {dom} days on the market ({pcts}). That reads as a "
                f"{label.lower()}, so the sold-anchored value is steered {abs(pct)}% {direction} to reflect "
                f"what the market will pay today, not months ago.")
    val['market'] = {'factor': factor, 'pct': pct, 'label': label, 'dom': dom,
                     'sstc_ratio': sstc_ratio, 'stuck_ratio': stuck_ratio,
                     'ask_median': pos.get('median'), 'note': note}
    return val

# ---------------------------------------------------------------- charts
def charts(compsA, val, subj, fee_rate, cgt, net, slug, outdir):
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    from matplotlib import font_manager as fm
    SERIF = 'Georgia'
    try: fm.findfont('Georgia', fallback_to_default=False)
    except Exception: SERIF = 'serif'
    plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Segoe UI','DejaVu Sans']})
    LIGHT='#eae3d6'; gbp=lambda x,_:f"£{x/1000:.0f}k"
    def title(ax,t): ax.set_title(t,fontfamily=SERIF,fontsize=12.5,fontweight='bold',color=ACCENTD,loc='left',pad=10)
    paths = {}
    # comps vs range
    cc = sorted(compsA, key=lambda r:r['price'])
    fig,ax=plt.subplots(figsize=(9,3.8))
    ax.axvspan(val['low'],val['high'],color=GREEN,alpha=.10); ax.axvline(val['central'],color=GREEN,lw=1.5); ax.axvline(val['guide'],color=TERRA,ls='--',lw=1.5)
    ax.barh(range(len(cc)),[r['price'] for r in cc],color=ACCENTD,height=.6,zorder=3)
    for i,r in enumerate(cc): ax.text(r['price']+6000,i,money(r['price']),va='center',fontsize=8.5,color='#4a463c')
    ax.set_yticks(range(len(cc))); ax.set_yticklabels([f"{r['address'].split(',')[0]} · {r['sqm']}sqm" for r in cc],fontsize=9); ax.invert_yaxis()
    ax.xaxis.set_major_formatter(FuncFormatter(gbp))
    for s in('top','right'):ax.spines[s].set_visible(False)
    ax.grid(axis='x',color=LIGHT); ax.tick_params(labelsize=9,colors='#4a463c')
    title(ax,'Exhibit 1 - Comparable sales (Tier A) against the assessed range')
    p=f"{outdir}/{slug}_c1.png"; plt.tight_layout(); plt.savefig(p,dpi=160); plt.close(); paths['comps']=p
    # finish ladder
    a=val['avm']
    if a.get('average') and a.get('high') and a.get('very_high'):
        fig,ax=plt.subplots(figsize=(9,3.3))
        vals=[a['average'],a['high'],a['very_high']]
        ax.bar(['Average','High','Very-high'],vals,color=[GREY,GREEN,ACCENTD],width=.5,zorder=3)
        for i,v in enumerate(vals): ax.text(i,v+6000,money(v),ha='center',fontsize=10,fontweight='bold',color='#4a463c')
        ax.yaxis.set_major_formatter(FuncFormatter(gbp))
        for s in('top','right'):ax.spines[s].set_visible(False)
        ax.grid(axis='y',color=LIGHT); ax.tick_params(labelsize=9.5,colors='#4a463c')
        title(ax,'Exhibit 2 - Value by finish quality (condition-adjusted)')
        p=f"{outdir}/{slug}_c2.png"; plt.tight_layout(); plt.savefig(p,dpi=160); plt.close(); paths['finish']=p
    # net split
    fig,ax=plt.subplots(figsize=(9,2.4))
    ax.barh(0,net,color=GREEN,zorder=3)
    left=net
    if cgt: ax.barh(0,cgt,left=left,color=TERRA,zorder=3); left+=cgt
    ax.barh(0,val['central']*fee_rate,left=left,color=GREY,zorder=3)
    ax.text(net/2,0,f"Net {money(net)}",ha='center',va='center',color='white',fontweight='bold',fontsize=10)
    ax.set_xlim(0,val['central']); ax.set_ylim(-.5,.6); ax.set_yticks([])
    ax.xaxis.set_major_formatter(FuncFormatter(gbp))
    for s in('top','right','left'):ax.spines[s].set_visible(False)
    ax.grid(axis='x',color=LIGHT); ax.tick_params(labelsize=9.5,colors='#4a463c')
    title(ax,f"Exhibit 3 - Split of a {money(val['central'])} sale")
    p=f"{outdir}/{slug}_c3.png"; plt.tight_layout(); plt.savefig(p,dpi=160,bbox_inches='tight'); plt.close(); paths['net']=p
    return paths

# ---------------------------------------------------------------- interactive chart
# Brand-palette CSS for the self-contained app. Plain string (literal braces); the
# brand colours come in via the small `root_css` f-string the function prepends.
_IC_CSS = r"""
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);
  font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased}
h1,h2,h3{font-family:Georgia,"Times New Roman",serif;font-weight:600;color:var(--navy);letter-spacing:-.01em;margin:0 0 .4em}
a{color:var(--green)}
.wrap{max-width:860px;margin:0 auto;padding:0 18px 64px}
/* masthead */
.mast{background:var(--cream);border-bottom:2px solid var(--gold)}
.mast-in{max-width:860px;margin:0 auto;padding:16px 18px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.logo{height:54px;width:auto;display:block}
.logo-fallback{font-family:Georgia,serif;font-size:30px;color:var(--navy);font-weight:600}
.mast-meta{margin-left:auto;text-align:right}
.mast-title{font-family:Georgia,serif;color:var(--navy);font-size:18px}
.mast-date{color:var(--mut);font-size:13px}
/* hero */
.hero{padding:30px 0 8px}
.hero h1{font-size:30px;line-height:1.15}
.facts{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 20px}
.chip{background:var(--pale);color:var(--navy);border:1px solid var(--line);border-radius:999px;
  padding:4px 12px;font-size:13px;font-weight:600}
.hero-figs{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:10px 0 4px}
.fig{background:var(--cream);border:1px solid var(--line);border-radius:14px;padding:16px}
.fig.big{grid-column:1 / -1;background:var(--navy);border-color:var(--navy)}
.fig .lab{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);margin-bottom:6px}
.fig.big .lab{color:var(--sand)}
.fig .val{font-family:Georgia,serif;font-size:24px;color:var(--navy);font-weight:600}
.fig.big .val{color:#fff;font-size:30px}
.lede{color:var(--mut);font-size:15px;margin:16px 0 0}
@media(max-width:560px){.hero-figs{grid-template-columns:1fr 1fr}.fig.big .val{font-size:25px}.hero h1{font-size:24px}}
/* tabs */
.tabs{position:sticky;top:0;z-index:5;background:var(--paper);display:flex;gap:6px;overflow-x:auto;
  padding:12px 0;margin:18px 0 6px;border-bottom:1px solid var(--line);-webkit-overflow-scrolling:touch}
.tabs button{flex:0 0 auto;background:transparent;border:1px solid var(--line);color:var(--navy);
  border-radius:999px;padding:7px 14px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap}
.tabs button.on{background:var(--navy);color:#fff;border-color:var(--navy)}
/* panels */
.panel{background:#fff;border:1px solid var(--line);border-radius:16px;padding:22px 22px 26px;margin:18px 0;
  scroll-margin-top:64px;box-shadow:0 1px 2px rgba(14,39,71,.04)}
.panel h2{font-size:22px}
.note{color:var(--mut);font-size:14px;margin:.2em 0 1.1em}
.na{color:var(--mut);font-style:italic}
/* build-up */
.steps{display:flex;flex-direction:column;gap:8px}
.step{border:1px solid var(--line);border-radius:12px;overflow:hidden}
.step-head{display:flex;align-items:baseline;gap:12px;padding:13px 16px;cursor:pointer;background:var(--cream)}
.step-head:hover{background:var(--pale)}
.step.last .step-head{background:var(--navy)}
.step-n{font-size:12px;color:var(--mut);font-weight:700;min-width:18px}
.step.last .step-n{color:var(--sand)}
.step-k{font-weight:600;color:var(--navy)}
.step.last .step-k{color:#fff}
.step-v{margin-left:auto;font-family:Georgia,serif;font-weight:600;color:var(--green)}
.step.last .step-v{color:var(--gold)}
.step-d{max-height:0;overflow:hidden;transition:max-height .25s ease;color:var(--mut);font-size:14px;padding:0 16px;background:#fff}
.step.open .step-d{max-height:240px;padding:12px 16px}
/* condition lever */
.lever{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.lever button{flex:1 1 30%;background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px;cursor:pointer;
  font-weight:600;color:var(--navy);text-align:left;min-width:140px}
.lever button small{display:block;color:var(--mut);font-weight:400;font-size:12px;margin-top:3px}
.lever button.on{border-color:var(--gold);background:var(--cream);box-shadow:inset 0 0 0 1px var(--gold)}
.lever-out{font-family:Georgia,serif;font-size:22px;color:var(--navy)}
.lever-out b{color:var(--green)}
.lever-out span{display:block;font-family:inherit;font-size:14px;color:var(--mut);margin-top:6px}
/* comps */
.sortbar{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.sortbar button{background:#fff;border:1px solid var(--line);border-radius:999px;padding:6px 12px;font-size:12.5px;cursor:pointer;color:var(--navy)}
.sortbar button.on{background:var(--green);color:#fff;border-color:var(--green)}
#chart{display:flex;flex-direction:column;gap:7px;margin:6px 0 14px;position:relative}
.bar-row{display:flex;align-items:center;gap:10px}
.bar-lab{font-size:12px;color:var(--mut);width:34%;min-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar-track{flex:1;background:var(--pale);border-radius:6px;height:22px;position:relative;cursor:pointer}
.bar-fill{position:absolute;top:0;left:0;height:100%;background:var(--green);border-radius:6px;min-width:2px}
.bar-val{position:absolute;right:8px;top:0;line-height:22px;font-size:11.5px;color:var(--navy);font-weight:600}
.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:12.5px;color:var(--mut);margin:4px 0 16px}
.legend i{display:inline-block;width:14px;height:14px;border-radius:3px;vertical-align:-2px;margin-right:6px}
.legend i.band-sw{background:var(--pale);border:1px solid var(--teal)}
.legend i.line-sw{width:14px;height:3px;border-radius:2px;vertical-align:3px}
table.comps{width:100%;border-collapse:collapse;font-size:13.5px}
table.comps th,table.comps td{padding:9px 8px;border-bottom:1px solid var(--line);text-align:left}
table.comps th{color:var(--navy);font-weight:700;cursor:pointer;user-select:none;white-space:nowrap}
table.comps th.r,table.comps td.r{text-align:right}
table.comps th.c,table.comps td.c{text-align:center}
table.comps th.sort:after{content:"";font-size:10px;margin-left:4px}
table.comps th.asc:after{content:"\2191"}
table.comps th.desc:after{content:"\2193"}
table.comps tbody tr:nth-child(odd){background:var(--paper)}
table.comps tbody tr.weak{opacity:.5}
table.comps a{font-weight:600;text-decoration:none}
/* net proceeds */
.slider-row{margin:6px 0 16px}
.slider-row label{display:block;font-size:14px;color:var(--navy);margin-bottom:8px}
.slider-row b{color:var(--green)}
input[type=range]{width:100%;accent-color:var(--green)}
.net-grid{display:flex;flex-direction:column;gap:0}
.net-grid .nr{display:flex;justify-content:space-between;padding:11px 2px;border-bottom:1px solid var(--line)}
.net-grid .nr.tot{border-bottom:none;border-top:2px solid var(--navy);font-family:Georgia,serif;font-size:18px;color:var(--navy);margin-top:4px}
.net-grid .nr.tot b{color:var(--green)}
.net-grid .nr small{color:var(--mut)}
/* positioning */
.pos-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:4px 0 10px}
.pos-cell{background:var(--cream);border:1px solid var(--line);border-radius:12px;padding:14px}
.pos-cell .pv{font-family:Georgia,serif;font-size:20px;color:var(--navy)}
.pos-cell .pl{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}
/* coverage */
.cov{display:flex;flex-direction:column;gap:6px}
.cov-row{display:flex;align-items:center;gap:12px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:13.5px}
.cov-row .cp{font-weight:600;color:var(--navy);flex:0 0 42%}
.cov-row .cc{color:var(--mut);flex:1}
.cov-row .cs{flex:0 0 auto;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;padding:3px 9px;border-radius:999px}
.cov-row .cs.live{background:var(--green);color:#fff}
.cov-row .cs.pending{background:var(--cream);color:var(--mut);border:1px solid var(--line)}
.cov-row .cs.chan{background:var(--pale);color:var(--navy)}
@media(max-width:560px){.cov-row{flex-wrap:wrap}.cov-row .cp{flex:1 1 100%}.pos-grid{grid-template-columns:1fr}}
/* refs */
ol.refs{margin:0;padding-left:22px;color:var(--ink);font-size:13.5px}
ol.refs li{margin:0 0 9px;line-height:1.4}
ol.refs b{color:var(--navy)}
ol.refs .rt{color:var(--mut)}
ol.refs a{word-break:break-all}
/* cta + footer */
.cta{display:block;text-align:center;background:var(--gold);color:var(--navy);font-weight:700;text-decoration:none;
  border-radius:14px;padding:16px;margin:26px 0 18px;font-size:16px}
.foot{color:var(--mut);font-size:12.5px;line-height:1.6;border-top:1px solid var(--line);padding-top:18px}
.foot-icon{height:26px;width:auto;vertical-align:-7px;margin-right:8px}
/* tooltip */
#tip{position:fixed;pointer-events:none;opacity:0;transition:opacity .12s;background:var(--navy);color:#fff;
  font-size:12px;padding:6px 10px;border-radius:7px;max-width:240px;z-index:20}
/* price-test instrument - the thing a PDF can't be */
.panel.instrument{background:var(--navy);color:var(--cream);border:none}
.panel.instrument h2{color:#fff}
.panel.instrument .note{color:rgba(246,243,236,.72)}
.pricetest{margin-top:14px}
.pt-readout{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:6px}
.pt-price{font-family:Georgia,'Times New Roman',serif;font-size:40px;font-weight:700;color:#fff;letter-spacing:-.5px}
.pt-zone{font-size:12.5px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;padding:4px 10px;border-radius:20px}
.pt-zone.in{background:rgba(42,163,154,.22);color:#7fe3d8}
.pt-zone.over{background:rgba(216,154,50,.22);color:var(--gold)}
.pt-zone.under{background:rgba(246,243,236,.16);color:var(--cream)}
.pt-scale{position:relative;height:46px;margin:18px 0 2px}
.pt-band{position:absolute;top:14px;height:18px;background:rgba(42,163,154,.28);border-left:2px solid var(--teal);border-right:2px solid var(--teal);border-radius:4px}
.pt-mark{position:absolute;top:6px;bottom:6px;width:2px;transform:translateX(-1px)}
.pt-mark.green{background:#5bd0c4}.pt-mark.gold{background:var(--gold)}.pt-mark.sand{background:var(--sand)}
.pt-mark span{position:absolute;top:-15px;left:50%;transform:translateX(-50%);white-space:nowrap;font-size:10px;color:rgba(246,243,236,.7)}
.pt-slider{-webkit-appearance:none;appearance:none;width:100%;height:6px;border-radius:6px;outline:none;margin:8px 0 0;
  background:linear-gradient(90deg,var(--gold) 0,var(--gold) var(--pct,50%),rgba(246,243,236,.22) var(--pct,50%),rgba(246,243,236,.22) 100%)}
.pt-slider::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:26px;height:26px;border-radius:50%;background:#fff;border:3px solid var(--gold);cursor:grab;box-shadow:0 2px 8px rgba(0,0,0,.35)}
.pt-slider::-moz-range-thumb{width:24px;height:24px;border-radius:50%;background:#fff;border:3px solid var(--gold);cursor:grab}
.pt-verdict{margin-top:16px;font-size:15.5px;line-height:1.5;padding:14px 16px;border-radius:12px;background:rgba(246,243,236,.08);border-left:3px solid var(--teal)}
.pt-verdict.warn{border-left-color:var(--gold);background:rgba(216,154,50,.12)}
.pt-verdict b{color:#fff}
.pt-legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:14px;font-size:11.5px;color:rgba(246,243,236,.7)}
.pt-legend .sw{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-1px;margin-right:5px}
.pt-legend .sw.band{background:rgba(42,163,154,.5)}.pt-legend .sw.green{background:#5bd0c4}
.pt-legend .sw.gold{background:var(--gold)}.pt-legend .sw.sand{background:var(--sand)}

/* L1 executive authority - confidence gauge + market-heat pill */
.authority{display:flex;flex-wrap:wrap;gap:18px;margin-top:20px;align-items:stretch}
.auth-card{flex:1 1 220px;background:var(--cream);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.auth-card .pl{font-size:11.5px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}
.gauge{display:flex;align-items:center;gap:14px;margin-top:10px}
.gauge-ring{--v:0;--c:var(--teal);width:64px;height:64px;border-radius:50%;flex:0 0 64px;
  background:conic-gradient(var(--c) calc(var(--v)*1%),var(--pale) 0);display:flex;align-items:center;justify-content:center}
.gauge-ring i{width:50px;height:50px;border-radius:50%;background:var(--cream);display:flex;align-items:center;justify-content:center;
  font-family:Georgia,'Times New Roman',serif;font-weight:700;font-size:18px;color:var(--navy);font-style:normal}
.gauge-grade{font-family:Georgia,'Times New Roman',serif;font-size:22px;font-weight:700;color:var(--navy)}
.gauge-note{font-size:12px;color:var(--mut);margin-top:3px;line-height:1.45}
/* Evidence Purity (hero) */
.purity{margin-top:16px}
.pur-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.pur-lab{font-size:11.5px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em;min-width:108px}
.pur-bar{flex:1 1 180px;height:8px;background:var(--pale);border-radius:999px;overflow:hidden}
.pur-bar i{display:block;height:100%;background:var(--green);border-radius:999px}
.pur-val{font-weight:700;color:var(--navy);font-size:14px}
.pur-sub{font-size:12px;color:var(--mut);margin-top:6px}
/* personalised decision panel */
.panel.decision{border-left:4px solid var(--green);background:linear-gradient(180deg,var(--cream),#fff)}
.dec-verdict{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin:.2em 0 .6em}
.dec-word{font-family:Georgia,'Times New Roman',serif;font-weight:700;font-size:30px;color:var(--green);letter-spacing:.01em}
.dec-word.warn{color:var(--gold)}
.dec-head{color:var(--ink);font-size:15px}
.dec-cols{display:flex;gap:24px;flex-wrap:wrap;margin-top:8px}
.dec-why,.dec-risk{flex:1 1 260px}
.dec-cols h3{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--navy);margin:0 0 6px}
.dec-cols ul{margin:0;padding-left:18px}
.dec-cols li{font-size:14px;color:var(--ink);margin:.3em 0;line-height:1.5}
.dec-next{margin-top:14px;font-size:14px;color:var(--navy);font-weight:600;background:var(--pale);padding:12px 14px;border-radius:10px}
.note.excluded{color:var(--navy);font-weight:700;font-size:15px;margin:.1em 0 1em}
.dec-cta{display:inline-flex;margin-top:14px;background:var(--navy);color:#fff;font-weight:700;
  padding:11px 18px;border-radius:10px;text-decoration:none;font-size:14px}
.dec-cta:hover{background:var(--green)}
/* factor Q&A */
.fq{padding:12px 0;border-bottom:1px solid var(--line)}
.fq:last-child{border-bottom:0}
.fq-q{font-weight:700;color:var(--ink);font-size:15px}
.fq-a{font-weight:700;font-size:14px;margin:.2em 0}
.fq-a.ok{color:var(--green)} .fq-a.warn{color:var(--gold)}
.fq-meta{color:var(--mut);font-size:13px;line-height:1.5}
.fq-link{display:inline-block;margin-top:8px;color:var(--green);font-weight:700;font-size:13.5px;text-decoration:none;
  border-bottom:1.5px solid var(--green)}
.fq-link:hover{color:var(--navy);border-color:var(--navy)}
.heat{display:flex;align-items:center;gap:12px;margin-top:10px}
.heat-pill{display:inline-flex;align-items:center;gap:8px;padding:8px 14px;border-radius:999px;font-weight:700;font-size:15px}
.heat-pill.warm{background:rgba(216,154,50,.16);color:#9a6a16}
.heat-pill.cool{background:rgba(42,163,154,.16);color:#157a72}
.heat-pill.balanced{background:var(--pale);color:var(--navy)}
.heat-pill .dot{width:10px;height:10px;border-radius:50%}
.heat-pill.warm .dot{background:var(--gold)}.heat-pill.cool .dot{background:var(--teal)}.heat-pill.balanced .dot{background:var(--sand)}
.heat-sub{font-size:12.5px;color:var(--mut);line-height:1.45}

/* L2 impact dashboard - translated consequences, traffic-light, tap to expand raw */
.dash{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;margin-top:6px}
.dash-group{grid-column:1/-1;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--mut);margin-top:8px}
.icard{border:1px solid var(--line);border-left-width:4px;border-radius:12px;padding:13px 15px;background:#fff;cursor:pointer}
.icard.good{border-left-color:var(--green)}.icard.watch{border-left-color:var(--gold)}
.icard.flag{border-left-color:#b4452f}.icard.info{border-left-color:var(--teal)}.icard.na{border-left-color:var(--sand)}
.icard-top{display:flex;align-items:center;gap:9px}
.icard-dot{width:11px;height:11px;border-radius:50%;flex:0 0 11px}
.icard.good .icard-dot{background:var(--green)}.icard.watch .icard-dot{background:var(--gold)}
.icard.flag .icard-dot{background:#b4452f}.icard.info .icard-dot{background:var(--teal)}.icard.na .icard-dot{background:var(--sand)}
.icard-title{font-weight:700;color:var(--navy);font-size:14.5px}
.icard-cons{font-size:13.5px;color:var(--ink);line-height:1.5;margin-top:8px}
.icard-raw{display:none;margin-top:9px;padding-top:9px;border-top:1px dashed var(--line);font-size:12px;color:var(--mut)}
.icard.open .icard-raw{display:block}
.icard-raw .rk{color:var(--navy);font-weight:600}

/* lite -> pro honest unlock teaser */
.panel.locked{background:linear-gradient(180deg,var(--cream),var(--paper));border:1px dashed var(--sand)}
.unlock-list{margin:10px 0 16px;padding-left:20px}
.unlock-list li{margin:7px 0;color:var(--ink);line-height:1.5}
/* in-place frosted Pro preview: the section keeps its position and title so the buyer
   sees the report's real shape; the body is a locked teaser, never real data blurred in CSS
   (the Pro payload is stripped from a Lite file's source, so there is nothing to recover). */
.panel.lock-preview{position:relative;background:linear-gradient(180deg,var(--cream),var(--paper));
  border:1px dashed var(--sand);overflow:hidden}
.panel.lock-preview::before{content:"";position:absolute;inset:0;
  background:repeating-linear-gradient(135deg,rgba(14,39,71,.018) 0 14px,rgba(14,39,71,0) 14px 28px);
  pointer-events:none}
.lock-card{position:relative;display:flex;flex-direction:column;gap:10px}
.lock-row{display:flex;align-items:center;gap:11px}
.lock-row h2{margin:0;border:0;padding:0}
.lock-badge{display:inline-flex;align-items:center;gap:6px;background:var(--gold);color:var(--navy);
  font-weight:800;font-size:11px;letter-spacing:.08em;padding:4px 9px;border-radius:999px;white-space:nowrap}
.lock-badge::before{content:"\1F512";font-size:11px}
.lock-teaser{margin:0;color:var(--mut);line-height:1.55;max-width:60ch}
.lock-cta{align-self:flex-start;margin-top:4px;background:var(--navy);color:#fff;font-weight:700;
  text-decoration:none;padding:9px 16px;border-radius:10px;font-size:14px}
.lock-cta:hover{background:var(--green)}
"""

# Vanilla-JS app. Plain string (literal braces). DATA / REFS / COVERAGE are injected
# above this constant by the f-string body. Every figure rendered traces to DATA;
# nothing is computed that is not derivable from that engine blob (honesty contract).
_IC_JS = r"""
(function(){
  var D=DATA, el=function(i){return document.getElementById(i);};
  function gbp(n){ if(n==null||isNaN(n)) return '-'; return '£'+Math.round(n).toLocaleString('en-GB'); }
  function esc(s){ var d=document.createElement('div'); d.textContent=(s==null?'':String(s)); return d.innerHTML; }
  function epcBand(score){ if(score==null) return '-';
    var t=[[92,'A'],[81,'B'],[69,'C'],[55,'D'],[39,'E'],[21,'F'],[0,'G']];
    for(var i=0;i<t.length;i++){ if(score>=t[i][0]) return t[i][1]+' ('+score+')'; } return String(score); }

  // ---- masthead + hero
  if(el('m_date')) el('m_date').textContent=D.datestr||'';
  el('h_addr').textContent=D.address||'Market appraisal';
  var facts=[];
  if(D.ptype) facts.push(D.ptype);
  if(D.beds) facts.push(D.beds+' bed');
  if(D.sqm) facts.push(D.sqm+' sqm');
  if(D.epc) facts.push('EPC '+epcBand(D.epc));
  if(D.tax) facts.push('Council tax '+D.tax);
  el('h_facts').innerHTML=facts.map(function(f){return '<span class="chip">'+esc(f)+'</span>';}).join('');
  el('h_range').textContent=gbp(D.low)+' - '+gbp(D.high);
  el('h_central').textContent=gbp(D.central);
  el('h_guide_lab').textContent=D.guide_label||'Recommended guide';
  el('h_guide').textContent=D.guide_value_str||gbp(D.guide);
  // the lens rotates with the audience; the figures underneath never change.
  var AUD=(D.audience||'agent');
  var _ns=(D.n_comps===1?'':'s');
  var _ledes={
    agent:'Anchored on '+D.n_comps+' sold comparable'+_ns+' from HM Land Registry, then steered for the live market. This is the evidence you put in front of the vendor - every figure opens its own public record, in front of them.',
    vendor:'What your home is really worth, anchored on '+D.n_comps+' comparable home'+_ns+' that actually sold near you - not an agent’s number to win your instruction. Every figure links to its source.',
    buyer:'Before you offer: what '+D.n_comps+' comparable home'+_ns+' actually sold for near here, and what today’s market supports. An asking price is what a seller hopes for; this is the evidence. Check every link yourself.',
    investor:'Anchored on '+D.n_comps+' sold comparable'+_ns+' from HM Land Registry, with the net-of-costs position for a held asset. Every figure traces to the evidence.'
  };
  _ledes.seller=_ledes.vendor;
  el('h_lede').textContent=_ledes[AUD]||_ledes.agent;

  // ---- L1 executive authority: confidence gauge + market-heat pill. Both read straight off
  // the engine blob (D.confidence is the data-only 0-100 grade; D.market_climate surfaces the
  // already-disclosed, capped live-market steer). Nothing here is a new computation.
  (function(){
    var host=el('h_authority'); if(!host) return;
    var html='';
    var cf=D.confidence;
    if(cf && (cf.score!=null||cf.grade)){
      var sc=(cf.score!=null?cf.score:''), gr=cf.grade||'';
      var col={Strong:'var(--green)',Good:'var(--teal)',Fair:'var(--gold)',Low:'#b4452f'}[gr]||'var(--teal)';
      html+='<div class="auth-card"><div class="pl">Confidence score</div>'+
        '<div class="gauge"><div class="gauge-ring" style="--v:'+(sc||0)+';--c:'+col+'"><i>'+esc(sc)+'</i></div>'+
        '<div><div class="gauge-grade">'+esc(gr)+'</div>'+
        '<div class="gauge-note">'+esc(cf.note||'Data-only grade: evidence depth, completeness, cross-check agreement and range stability.')+'</div></div></div></div>';
    }
    var mc=D.market_climate;
    if(mc && mc.label){
      var tone=(mc.tone||'balanced'), pct=mc.pct;
      var sub=[]; if(mc.dom!=null) sub.push('~'+Math.round(mc.dom)+' days to sale'); if(mc.stuck) sub.push(mc.stuck+' stuck');
      html+='<div class="auth-card"><div class="pl">Market climate</div>'+
        '<div class="heat"><span class="heat-pill '+tone+'"><span class="dot"></span>'+esc(mc.label)+
        ((pct!=null&&pct!==0)?' ('+(pct>0?'+':'')+pct+'%)':'')+'</span></div>'+
        '<div class="heat-sub">'+esc((mc.note?mc.note+' ':'')+(sub.length?'('+sub.join(', ')+'). ':'')+'The single capped, disclosed live-market steer - shown in full in the build-up.')+'</div></div>';
    }
    if(!html){ host.style.display='none'; } else { host.innerHTML=html; }
  })();

  // ---- price test: the instrument. Drag ANY price and watch where it lands against the
  // SOLD evidence band, the central value, the guide and the live asking field. The dragged
  // number is purely explanatory - it is never fed back into the valuation; it only positions
  // a verdict, so the honesty contract holds (nothing here can move the figure).
  (function(){
    var sl=el('pt_slider'); if(!sl) return;
    var scale=el('pt_scale'), out=el('pt_verdict'), ppr=el('pt_price'), pzo=el('pt_zone'),
        leg=el('pt_legend'), tEl=el('ask_title'), nEl=el('ask_note');
    var pos=D.positioning||null, lo=D.low, hi=D.high, ctl=D.central, gd=D.guide;
    var base=[lo,hi,ctl,gd,D.sold_median].filter(function(x){return x!=null;});
    var mn=Math.min.apply(null,base), mx=Math.max.apply(null,base);
    if(pos){ if(pos.median!=null) mx=Math.max(mx,pos.median);
             if(pos.hi_p!=null) mx=Math.max(mx,pos.hi_p);
             if(pos.lo_p!=null) mn=Math.min(mn,pos.lo_p); }
    var pad=(mx-mn)*0.12||10000; mn=Math.max(0,mn-pad); mx=mx+pad; var span=(mx-mn)||1;
    function pc(v){ return Math.max(0,Math.min(100,((v-mn)/span)*100)); }
    var copy={
      agent:['Test any price against the sold evidence','Drag the price. Show the vendor exactly where their number lands - and why '+(D.guide_value_str||gbp(gd))+' draws the offers the stuck listings are still waiting for.'],
      vendor:['What happens at each asking price','Drag to any price - your dream number, an agent’s quote, our guide. The verdict is the sold evidence talking, not an opinion. A high asking price doesn’t win a higher sale; it wins a longer wait.'],
      buyer:['Test the asking price against the evidence','Drag to the asking price. See how far it sits above what comparable homes actually sold for - that gap is your negotiating headroom, in writing.'],
      investor:['Test any exit price against the evidence','Drag to any price to see where it lands against the sold evidence and the live competitive band.']
    };
    copy.seller=copy.vendor;
    var c=copy[AUD]||copy.agent; if(tEl) tEl.textContent=c[0]; if(nEl) nEl.textContent=c[1];
    var marks='<div class="pt-band" style="left:'+pc(lo)+'%;width:'+(pc(hi)-pc(lo))+'%"></div>';
    if(ctl!=null) marks+='<div class="pt-mark green" style="left:'+pc(ctl)+'%"><span>Central '+gbp(ctl)+'</span></div>';
    if(gd!=null) marks+='<div class="pt-mark gold" style="left:'+pc(gd)+'%"><span>Guide '+gbp(gd)+'</span></div>';
    if(pos&&pos.median!=null) marks+='<div class="pt-mark sand" style="left:'+pc(pos.median)+'%"><span>Median asking '+gbp(pos.median)+'</span></div>';
    scale.innerHTML=marks;
    leg.innerHTML='<span><i class="sw band"></i>Assessed range (sold evidence)</span>'+
      '<span><i class="sw green"></i>Central</span><span><i class="sw gold"></i>Guide</span>'+
      (pos&&pos.median!=null?'<span><i class="sw sand"></i>Median asking</span>':'');
    sl.min=Math.round(mn); sl.max=Math.round(mx); sl.step=Math.max(500,Math.round(span/400));
    var start=(AUD==='buyer'&&D.asking)?D.asking:(D.quoted||gd||ctl);
    sl.value=Math.min(mx,Math.max(mn,start));
    function zone(p){ if(p>hi) return ['over','Above the evidence'];
                      if(p>=lo) return ['in','Within the assessed range'];
                      return ['under','Below the evidence']; }
    function verdict(p){
      var stuck=(pos&&pos.stuck)?pos.stuck:0;
      if(AUD==='buyer'){
        if(p>hi) return ['warn','At '+gbp(p)+' you would pay about <b>'+gbp(p-hi)+' over</b> what comparable homes actually sold for - your negotiating headroom, in writing'+(stuck?', and '+stuck+' home'+(stuck===1?'':'s')+' in this band '+(stuck===1?'has':'have')+' already sat unsold 90+ days.':'.')];
        if(p>=lo) return ['ok','At '+gbp(p)+' you are paying within the evidence-backed range - a fair, defensible price.'];
        return ['ok','At '+gbp(p)+' you are below what comparable homes sold for - keenly priced, if the condition matches.'];
      }
      if(p>hi){
        var s=(stuck?' '+stuck+' comparable home'+(stuck===1?'':'s')+' asking above the evidence '+(stuck===1?'has':'have')+' sat unsold 90+ days.':'');
        return ['warn','At '+gbp(p)+' you are <b>'+gbp(p-hi)+' above</b> the sold evidence.'+s+' A high number wins the instruction, not the sale - it produces a longer, costlier listing.'];
      }
      if(p>=lo) return ['ok','At '+gbp(p)+' you are inside the assessed range - defensible, anchored to what actually sold.'];
      return ['ok','At '+gbp(p)+' you are at or below the assessed floor - priced to draw competing offers fast.'];
    }
    function paint(){
      var p=parseFloat(sl.value); ppr.textContent=gbp(p);
      var z=zone(p); pzo.textContent=z[1]; pzo.className='pt-zone '+z[0];
      var v=verdict(p); out.className='pt-verdict '+v[0]; out.innerHTML=v[1];
      sl.style.setProperty('--pct',pc(p)+'%');
    }
    sl.addEventListener('input',paint); paint();
  })();

  // ---- Evidence Purity (hero trust metric) + the personalised decision panel.
  // Both come straight from the engine (D.evidence_purity, D.decision) so the page
  // matches the PDF verbatim; the decision frame is the profile's real need (Hit VOC).
  (function(){
    var ep=D.evidence_purity, hp=el('h_purity');
    if(ep && ep.pct!=null && hp){
      hp.innerHTML='<div class="pur-row"><span class="pur-lab">Evidence purity</span>'
        +'<span class="pur-bar"><i style="width:'+ep.pct+'%"></i></span>'
        +'<span class="pur-val">'+ep.pct+'% evidence-based</span></div>'
        +'<div class="pur-sub">'+(ep.adjustment_pct!=null?ep.adjustment_pct:(100-ep.pct))+'% disclosed adjustment'
        +(ep.drivers&&ep.drivers.length?' · '+ep.drivers[0]:'')+'</div>';
    }
    var dec=D.decision, P=el('p_decision');
    if(!dec || !P){ if(P) P.style.display='none'; return; }
    if(el('dec_q')) el('dec_q').textContent=dec.question||'If this were our money';
    if(dec.need && el('dec_need')) el('dec_need').textContent=dec.need;
    var w=el('dec_word'); if(w){ w.textContent=dec.word; w.className='dec-word '+(dec.warn?'warn':'ok'); }
    if(el('dec_head')) el('dec_head').textContent=dec.headline?(' – '+dec.headline):'';
    function fill(id,arr){ var u=el(id); if(!u) return; u.innerHTML='';
      (arr||[]).forEach(function(b){ var li=document.createElement('li'); li.textContent=b; u.appendChild(li); }); }
    fill('dec_why',dec.why); fill('dec_risk',dec.risks);
    if(dec.next && el('dec_next')) el('dec_next').textContent='What to do next: '+dec.next;
    // Pro CTA after the decision (lite only) - the natural conversion point, live deep link.
    var dcta=el('dec_cta');
    if(dcta && (D.tier||'pro')==='lite'){ dcta.href=buyLink('pro'); dcta.style.display=''; }
  })();

  // ---- factor Q&A (crime / planning / flood). The guide hyperlink fires ONLY on a flagged
  // factor (a real reason to look closer); a benign 'no impact' gets no link. Conversion at
  // the moment of doubt, never bolted onto a non-issue.
  (function(){
    var fq=D.factor_qa||[], fp=el('p_factors'), fc=el('factors');
    if(!fq.length || !fc){ return; }
    fp.style.display='';
    fc.innerHTML=fq.map(function(b){
      var link=b.flag ? '<a class="fq-link" href="'+buyLink(b.mid)+'" target="_blank" rel="noopener">'+esc(b.guide)+' &rsaquo;</a>' : '';
      return '<div class="fq"><div class="fq-q">'+esc(b.q)+'</div>'+
             '<div class="fq-a '+(b.flag?'warn':'ok')+'">'+esc(b.a)+'</div>'+
             '<div class="fq-meta">Evidence: '+esc(b.ev)+'</div>'+
             '<div class="fq-meta">So what: '+esc(b.sw)+'</div>'+link+'</div>';
    }).join('');
  })();

  // ---- spec-mandated exclusion statement on the comparable evidence
  (function(){ var n=D.n_screened, e=el('ev_excluded'); if(!e) return;
    if(n){ e.textContent='We excluded '+n+' nearby sale'+(n===1?'':'s')+' because they were not comparable - different type, tenure, size or too distant or stale.'; }
    else { e.style.display='none'; } })();

  // ---- context panels (Location/Area/Safety/Environment/Planning/Material/Narrative).
  // Runs BEFORE the tab nav is built so empty panels hide themselves and are skipped.
  try{ if(window.__renderCtx) window.__renderCtx(D, (typeof CTX!=='undefined'?CTX:{})); }catch(e){}

  // ---- glass-box build-up
  var steps=[];
  if(D.valuation_formula && D.valuation_formula.plain_formula){
    steps.push(['Formula', D.valuation_formula.name||'Honestly Transparent AVM', D.valuation_formula.plain_formula]);
    var ev=D.valuation_formula.evidence||{}, flt=D.valuation_formula.filter||{};
    steps.push(['Evidence set', (ev.selected_count||D.n_comps||0)+' HMLR rows',
      'Filtered to '+(flt.property_type||'residential evidence')+', '+(flt.distance||'local radius')+', '+(flt.recency_window_months||'?')+' months. Subject sale excluded: '+(flt.subject_sale_excluded?'yes':'no')+'.']);
  }
  if(D.sold_median!=null) steps.push(['Sold median', gbp(D.sold_median),
    'The midpoint of the sold comparables below - the floor of fact. A closer-matching sale counts for more; an older sale counts for less. From HM Land Registry Price Paid Data, the public record of what actually sold.']);
  if(D.psmA) steps.push(['Price per sqm (area)', gbp(D.psmA)+' /sqm',
    'The sold rate per square metre for this area, an independent second route to the figure when applied to this property’s '+(D.sqm||'-')+' sqm.']);
  if(D.crosscheck!=null) steps.push(['Per-sqm cross-check', gbp(D.crosscheck),
    'What that per-sqm rate implies for this size. It sits alongside the sold median as a consistency check - the two should agree.']);
  if(D.avm && D.avm.average!=null) steps.push(['Automated valuation', gbp(D.avm.average),
    'Our automated valuation for this address at a standard finish, condition-adjusted. We use it to cross-check the comparable evidence, never to override it.']);
  if(D.sold_anchor!=null) steps.push(['Sold anchor', gbp(D.sold_anchor),
    'The settled figure the sold evidence and the AVM agree on, before the live market is considered.']);
  if(D.market && D.market.pct!=null) steps.push(['Live-market steer', (D.market.pct>0?'+':'')+D.market.pct+'%',
    (D.market.note?D.market.note+' ':'')+'This steer is capped at +6% / -5% and disclosed in full - with condition, the only thing that moves the figure.']);
  steps.push(['Central value', gbp(D.central),
    'Where the evidence lands. The assessed range '+gbp(D.low)+' - '+gbp(D.high)+' brackets it; the recommended guide ('+
    (D.guide_value_str||gbp(D.guide))+') is a pricing strategy, not a different opinion of value.']);
  var bu=el('buildup');
  bu.innerHTML=steps.map(function(s,i){
    var last=(i===steps.length-1)?' last':'';
    return '<div class="step'+last+'" data-i="'+i+'">'+
      '<div class="step-head"><span class="step-n">'+(i+1)+'</span>'+
      '<span class="step-k">'+esc(s[0])+'</span><span class="step-v">'+esc(s[1])+'</span></div>'+
      '<div class="step-d">'+esc(s[2])+'</div></div>';
  }).join('');
  bu.addEventListener('click',function(e){
    var st=e.target.closest('.step'); if(st) st.classList.toggle('open');
  });

  // ---- condition lever (only the real AVM tiers)
  var lever=el('lever'), lout=el('lever_out');
  if(D.avm && (D.avm.average!=null||D.avm.high!=null||D.avm.very_high!=null)){
    var tiers=[['average','Standard finish','As the property typically presents today.'],
               ['high','Refurbished','Modernised kitchen, bathrooms and finishes throughout.'],
               ['very_high','Premium / extended','Top-tier finish or materially extended space.']];
    tiers=tiers.filter(function(t){return D.avm[t[0]]!=null;});
    function setTier(key){
      Array.prototype.forEach.call(lever.children,function(b){ b.classList.toggle('on', b.dataset.k===key); });
      var t=tiers.filter(function(x){return x[0]===key;})[0];
      lout.innerHTML='At <b>'+esc(t[1].toLowerCase())+'</b> finish, our condition-adjusted valuation is <b>'+gbp(D.avm[key])+'</b>.'+
        '<span>Condition is the one input that legitimately moves the figure. These are real condition-adjusted valuations for this address - not a multiplier we invented.</span>';
    }
    lever.innerHTML=tiers.map(function(t){
      return '<button data-k="'+t[0]+'">'+esc(t[1])+'<small>'+gbp(D.avm[t[0]])+' · '+esc(t[2])+'</small></button>';
    }).join('');
    lever.addEventListener('click',function(e){ var b=e.target.closest('button'); if(b) setTier(b.dataset.k); });
    setTier('average');
  } else {
    el('p_condition').style.display='none';
  }

  // ---- comparable evidence: sortable table + bar chart
  var comps=(D.comps||[]).slice();
  var sortKey='match', sortDir=-1;          // best-matching comparables first by default
  function fmtDate(s){ if(!s) return '-'; var p=s.split('-'); return p.length>=2? (p[2]||'01')+'/'+p[1]+'/'+p[0].slice(2):s; }
  function renderComps(){
    comps.sort(function(a,b){
      var x=a[sortKey], y=b[sortKey];
      if(x==null) return 1; if(y==null) return -1;
      if(typeof x==='string') return sortDir*x.localeCompare(y);
      return sortDir*(x-y);
    });
    // table
    var tb=document.querySelector('#comps tbody');
    tb.innerHTML=comps.map(function(c){
      var v=c.href?'<a href="'+esc(c.href)+'" target="_blank" rel="noopener">View</a>':'-';
      var m=c.match!=null?c.match+'%':'-';
      return '<tr'+(c.weak?' class="weak"':'')+'>'+
        '<td>'+esc(c.addr||c.full||'-')+'</td>'+
        '<td class="r">'+(c.sqm?c.sqm+' sqm':'-')+'</td>'+
        '<td class="r">'+gbp(c.price)+'</td>'+
        '<td class="c">'+fmtDate(c.date)+'</td>'+
        '<td class="r">'+(c.psm?gbp(c.psm):'-')+'</td>'+
        '<td class="r">'+(c.dist!=null?c.dist+' mi':'-')+'</td>'+
        '<td class="r">'+m+'</td>'+
        '<td class="c">'+v+'</td></tr>';
    }).join('');
    // header arrows
    Array.prototype.forEach.call(document.querySelectorAll('#comps th'),function(th){
      th.classList.remove('asc','desc','sort');
      if(th.dataset.k===sortKey){ th.classList.add('sort', sortDir>0?'asc':'desc'); }
    });
    // chart scale
    var prices=comps.map(function(c){return c.price;}).filter(function(x){return x!=null;});
    var lo=Math.min.apply(null, prices.concat([D.low]).filter(function(x){return x!=null;}));
    var hi=Math.max.apply(null, prices.concat([D.high]).filter(function(x){return x!=null;}));
    lo=lo*0.97; hi=hi*1.03; var span=(hi-lo)||1;
    function pc(v){ return Math.max(0,Math.min(100,((v-lo)/span)*100)); }
    var ch=el('chart');
    var marks='';
    if(D.low!=null&&D.high!=null){ marks+='<div style="position:absolute;top:0;bottom:0;left:'+pc(D.low)+'%;width:'+(pc(D.high)-pc(D.low))+'%;background:var(--pale);border-left:1px solid var(--teal);border-right:1px solid var(--teal);border-radius:4px;z-index:0"></div>'; }
    if(D.central!=null){ marks+='<div style="position:absolute;top:-2px;bottom:-2px;left:'+pc(D.central)+'%;width:2px;background:var(--green);z-index:2"></div>'; }
    if(D.guide!=null){ marks+='<div style="position:absolute;top:-2px;bottom:-2px;left:'+pc(D.guide)+'%;width:2px;background:var(--gold);z-index:2"></div>'; }
    var rows=comps.map(function(c){
      var w=c.price!=null?pc(c.price):0;
      var click=c.href?' onclick="window.open(\''+esc(c.href)+'\',\'_blank\')"':'';
      return '<div class="bar-row"><span class="bar-lab" title="'+esc(c.full||c.addr)+'">'+esc(c.addr||'-')+'</span>'+
        '<div class="bar-track"'+click+'><div class="bar-fill" style="width:'+w+'%"></div>'+
        '<span class="bar-val">'+gbp(c.price)+'</span></div></div>';
    }).join('');
    // overlay band/markers behind the bars via a positioned wrapper
    ch.innerHTML='<div style="position:relative">'+
      '<div style="position:absolute;left:calc(34% + 10px);right:0;top:0;bottom:0;z-index:0">'+marks+'</div>'+
      '<div style="position:relative;z-index:1;display:flex;flex-direction:column;gap:7px">'+rows+'</div></div>';
  }
  document.querySelectorAll('#comps th[data-k]').forEach(function(th){
    th.addEventListener('click',function(){
      var k=th.dataset.k;
      if(k===sortKey) sortDir=-sortDir; else { sortKey=k; sortDir=(k==='addr'||k==='date')?1:-1; }
      renderComps();
    });
  });
  // quick sort chips
  var sb=el('sortbar');
  var chips=[['price','Sold price'],['psm','£/sqm'],['dist','Distance'],['date','Most recent']];
  sb.innerHTML=chips.map(function(c){return '<button data-k="'+c[0]+'">'+esc(c[1])+'</button>';}).join('');
  sb.addEventListener('click',function(e){
    var b=e.target.closest('button'); if(!b) return;
    sortKey=b.dataset.k; sortDir=(sortKey==='addr')?1:(sortKey==='date'?-1:-1);
    Array.prototype.forEach.call(sb.children,function(x){x.classList.toggle('on',x===b);});
    renderComps();
  });
  if(comps.length){ renderComps(); } else { el('p_comps').style.display='none'; }

  // ---- official-register cross-check (HM Land Registry, pulled directly). Beside the
  // figure: an independent check that the comparable sales are real. Restates only the
  // embedded numbers; never blended into low/high/central/guide. Hidden when quiet/down.
  (function(){
    var oc=D.official_check, host=el('ev_official');
    if(!host) return;
    if(!oc || !oc.official_count){ host.style.display='none'; return; }
    var div=oc.divergence_pct, divtxt='';
    if(typeof div==='number' && div){
      divtxt=' Our tier-matched comparable median sits '+Math.abs(div).toFixed(1)+'% '
        +(div>0?'above':'below')+' it.';
    }
    host.innerHTML='<b>Official-register check:</b> HM Land Registry records '
      +esc(oc.official_count)+' completed sale'+(oc.official_count===1?'':'s')+' in '
      +esc(oc.postcode)+(oc.window?(' ('+esc(oc.window)+')'):'')+', median '
      +gbp(oc.official_median)+'.'+esc(divtxt)
      +' Shown as an independent check on the evidence, never blended into the figure.';
  })();

  // ---- net proceeds (seller/agent only - a UK buyer never pays the agent fee)
  var fee=el('fee');
  if(fee){
    function renderNet(){
      var pct=parseFloat(fee.value);
      el('fee_pct').textContent=pct.toFixed(1)+'%';
      var sale=D.central||0;
      var feeAmt=sale*pct/100, vat=feeAmt*0.2, net=sale-feeAmt-vat;
      var rows=[['Assessed central value', gbp(sale), ''],
                ['Agent fee ('+pct.toFixed(1)+'%)', '−'+gbp(feeAmt), ''],
                ['VAT on fee (20%)', '−'+gbp(vat), '']];
      var html=rows.map(function(r){return '<div class="nr"><span>'+esc(r[0])+'</span><span>'+r[1]+'</span></div>';}).join('');
      if(D.investment && D.last_sold){
        var gain=sale-D.last_sold;
        html+='<div class="nr"><span>Indicative gain since purchase <small>('+gbp(D.last_sold)+
          (D.last_sold_date?' in '+D.last_sold_date.slice(0,4):'')+')</small></span><span>'+gbp(gain)+'</span></div>'+
          '<div class="nr"><span><small>Capital gains tax applies on the gain before reliefs/allowances - take advice.</small></span><span></span></div>';
      }
      html+='<div class="nr tot"><span>Net before mortgage &amp; legal</span><b>'+gbp(net)+'</b></div>';
      el('net').innerHTML=html;
    }
    fee.addEventListener('input',renderNet); renderNet();
  }

  // ---- costs to buy (buyer audience) - stamp duty is exact (macro.sdlt), legal/survey
  // are indicative third-party ranges, never blended with or presented as a Honestly figure
  (function(){
    var bc=D.buyer_costs, host=el('buycost');
    if(!bc||!host) return;
    var rows=[['Purchase price (assessed central)', gbp(bc.price), '']];
    rows.push(['Stamp duty (SDLT)', '+'+gbp(bc.sdlt), '']);
    if(bc.sdlt_ftb!=null && bc.sdlt_ftb<bc.sdlt)
      rows.push(['<small>If a first-time buyer, SDLT is</small>', '<small>'+gbp(bc.sdlt_ftb)+'</small>', '']);
    rows.push(['Legal / conveyancing <small>(indicative)</small>', '+'+gbp(bc.legal_lo)+' - '+gbp(bc.legal_hi), '']);
    rows.push(['Survey <small>(indicative)</small>', '+'+gbp(bc.survey_lo)+' - '+gbp(bc.survey_hi), '']);
    var html=rows.map(function(r){return '<div class="nr"><span>'+r[0]+'</span><span>'+r[1]+'</span></div>';}).join('');
    var loTot=bc.price+bc.sdlt+bc.legal_lo+bc.survey_lo, hiTot=bc.price+bc.sdlt+bc.legal_hi+bc.survey_hi;
    html+='<div class="nr tot"><span>Indicative total to buy <small>(excl. mortgage fees)</small></span><b>'+gbp(loTot)+' - '+gbp(hiTot)+'</b></div>';
    host.innerHTML=html;
  })();

  // ---- positioning
  var pos=D.positioning;
  if(pos){
    var cells=[];
    if(pos.listings!=null) cells.push(['Comparable listings', pos.listings]);
    if(pos.lo_p!=null&&pos.hi_p!=null) cells.push(['Live asking band', gbp(pos.lo_p)+' - '+gbp(pos.hi_p)]);
    if(pos.median!=null) cells.push(['Median asking', gbp(pos.median)]);
    if(pos.mean_dom!=null) cells.push(['Avg days on market', pos.mean_dom+' days']);
    if(pos.stuck!=null) cells.push(['Stuck 90+ days', pos.stuck]);
    el('position').innerHTML='<p class="note">Asking prices show what the property competes against - they are never used to set the figure above. Sold evidence sets value; the live field sets strategy.</p>'+
      '<div class="pos-grid">'+cells.map(function(c){return '<div class="pos-cell"><div class="pl">'+esc(c[0])+'</div><div class="pv">'+esc(c[1])+'</div></div>';}).join('')+'</div>';
  } else { el('p_position').style.display='none'; }

  // ---- outlook
  var ol=[];
  if(D.market && (D.market.label||D.market.note)) ol.push('<p><b>Live market:</b> '+esc(D.market.label||'')+(D.market.note?' '+esc(D.market.note):'')+'</p>');
  var mac=D.macro;
  if(mac){
    var lines=(mac.momentum&&mac.momentum.lines)||mac.lines||(Array.isArray(mac)?mac:null);
    if(lines&&lines.length) ol.push('<ul>'+lines.map(function(l){return '<li>'+esc(typeof l==='string'?l:(l.text||JSON.stringify(l)))+'</li>';}).join('')+'</ul>');
  }
  if(!ol.length){ el('p_outlook').style.display='none'; } else { el('outlook').innerHTML=ol.join(''); }

  // ---- data sources (coverage)
  var _cs=(typeof CTX!=='undefined'&&CTX&&CTX.sections)?CTX.sections:{};
  var present={hero:true, build_up:true, comps:comps.length>0, condition:!!(D.avm&&D.avm.average!=null),
    positioning:!!pos, material:!!(D.epc||D.tax||_cs.material), market:!!(D.macro||(D.market&&D.market.pct!=null)),
    location:!!_cs.location, area:!!_cs.area, safety:!!_cs.safety,
    environment:!!_cs.environment, planning:!!_cs.planning,
    footer:true};
  el('coverage').innerHTML=(COVERAGE||[]).map(function(r){
    var cls, lab;
    if(r.klass==='CHANNEL'){ cls='chan'; lab='Delivered'; }
    else if(present[r.panel]){ cls='live'; lab='Included'; }
    else { cls='pending'; lab='Included in pack'; }
    // describe the data and its status only - never the commercial supplier; full
    // attribution lives in References, the one place sources are named.
    return '<div class="cov-row"><span class="cp">'+esc(r.contributes)+'</span>'+
      '<span class="cs '+cls+'">'+lab+'</span></div>';
  }).join('');

  // ---- references
  el('refs').innerHTML=(REFS||[]).map(function(c){
    return '<li><b>'+esc(c.publisher)+'.</b> <span class="rt">'+esc(c.title)+'.</span> '+
      '<a href="'+esc(c.url)+'" target="_blank" rel="noopener">'+esc(c.url)+'</a> ('+esc(c.accessed)+').</li>';
  }).join('');
  if(!(REFS&&REFS.length)) el('p_refs').style.display='none';

  // ---- L2 impact dashboard: the Data Translation Matrix. Renders the pre-built impact_cards
  // (group / title / raw / consequence / severity / source) - every card already honesty-checked
  // in Python: no fabricated per-factor pounds, 'not assessed' where no free source exists.
  (function(){
    var host=el('dashboard'); var cards=D.impact_cards||[];
    if(!host || !cards.length){ if(el('p_dashboard')) el('p_dashboard').style.display='none'; return; }
    var order=['Property Health','Local Environment','Connectivity','Market Sentiment'];
    var byg={}; cards.forEach(function(c){ (byg[c.group]=byg[c.group]||[]).push(c); });
    var groups=order.filter(function(g){return byg[g];}).concat(Object.keys(byg).filter(function(g){return order.indexOf(g)<0;}));
    var html='';
    groups.forEach(function(g){
      html+='<div class="dash-group">'+esc(g)+'</div>';
      byg[g].forEach(function(c){
        var sev=(c.severity||'info');
        html+='<div class="icard '+sev+'" tabindex="0">'+
          '<div class="icard-top"><span class="icard-dot"></span><span class="icard-title">'+esc(c.title)+'</span></div>'+
          '<div class="icard-cons">'+esc(c.consequence)+'</div>'+
          '<div class="icard-raw"><span class="rk">Reading:</span> '+esc(c.raw||'-')+
          (c.source?' &middot; <span class="rk">Source:</span> '+esc(c.source):'')+'</div></div>';
      });
    });
    host.innerHTML=html;
    Array.prototype.forEach.call(host.querySelectorAll('.icard'),function(card){
      var t=function(){ card.classList.toggle('open'); };
      card.addEventListener('click',t);
      card.addEventListener('keydown',function(e){ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); t(); } });
    });
  })();

  // ---- tier gate (VIEW level): Lite shows the real L1 hook (range, confidence, climate,
  // narrative, price test, build-up, comparables) in full. The Pro sections keep their place
  // in the report but render as frosted "locked" previews - title + one honest line of what
  // Pro adds + a pay link. The Pro data was already stripped from DATA/CTX in Python, so there
  // is nothing real behind the frost to recover; we never invent a risk figure to bait a click.
  (function(){
    if((D.tier||'pro')!=='lite') return;
    var pay=buyLink('pro');
    // Lite already gave them every verifiable FACT. Pro adds the INTERPRETATION - the part no
    // competitor offers. [section id, short name, what Pro adds (honest, no fabricated figure)]
    var lock=[
      ['p_dashboard','Impact dashboard','Every fact above - EPC, flood, crime, connectivity, the local market - translated into what it actually means for THIS property and your price, each graded green / amber / red.'],
      ['p_position','Live positioning strategy','Where to pitch the guide: live asking vs sold, average days on market, how much local stock is stuck past 90 days, and the move that wins viewings instead of joining the stalled listings.'],
      ['p_outlook','Market outlook','The forward read: Bank-Rate and house-price-index context, and what the live momentum means for timing.'],
      ['p_coverage','Full evidence room & data ledger','Every comparable with its exclusion reason, the full price-influence ledger, the data-spine verification and every source in the pack.']
    ];
    lock.forEach(function(row){
      var s=el(row[0]); if(!s) return;
      s.style.display=''; s.classList.remove('locked'); s.classList.add('lock-preview');
      s.innerHTML='<div class="lock-card">'+
        '<div class="lock-row"><span class="lock-badge">PRO</span><h2>'+esc(row[1])+'</h2></div>'+
        '<p class="lock-teaser">'+esc(row[2])+'</p>'+
        '<a class="lock-cta" href="'+esc(pay)+'" target="_blank" rel="noopener">Unlock the full report</a></div>';
    });
    // headline summary banner: lists what Lite covers + what Pro adds + one pay link
    var ul=el('unlock_list');
    if(ul) ul.innerHTML=lock.map(function(r){return '<li>'+esc(r[1])+'</li>';}).join('')+
      '<li>The full Evidence Room: every comparable with its HM Land Registry link and exclusion reasons</li>';
    var cta=el('unlock_cta'); if(cta) cta.href=pay;
    if(el('p_unlock')) el('p_unlock').style.display='';
  })();

  // ---- tabs (quick nav over the rendered panels)
  var tabDefs=[['p_asking','Price test'],['p_narrative','Summary'],['p_build','Build-up'],['p_condition','Condition'],
    ['p_comps','Comparables'],['p_dashboard','Impact'],['p_net','Net proceeds'],['p_buycost','Costs to buy'],['p_position','Positioning'],
    ['p_outlook','Outlook'],['p_unlock','Unlock'],['p_location','Location'],['p_area','Area'],['p_safety','Safety'],
    ['p_environment','Environment'],['p_planning','Planning'],['p_material','Material'],
    ['p_coverage','Data sources'],['p_refs','References']];
  var nav=el('tabs');
  tabDefs.forEach(function(t){
    var sec=el(t[0]); if(!sec||sec.style.display==='none') return;
    var b=document.createElement('button'); b.textContent=t[1]; b.dataset.t=t[0];
    b.addEventListener('click',function(){ sec.scrollIntoView({behavior:'smooth',block:'start'}); });
    nav.appendChild(b);
  });
  var secs=tabDefs.map(function(t){return el(t[0]);}).filter(Boolean);
  function onScroll(){
    var y=window.scrollY+90, cur=null;
    secs.forEach(function(s){ if(s.style.display!=='none' && s.offsetTop<=y) cur=s.id; });
    Array.prototype.forEach.call(nav.children,function(b){ b.classList.toggle('on', b.dataset.t===cur); });
  }
  window.addEventListener('scroll',onScroll,{passive:true}); onScroll();
})();
"""


# Context panels (Location / Area / Safety / Environment / Planning / Material / Narrative).
# Rendered from the CTX blob produced by area_context.gather(). Kept as a separate IIFE-free
# render function so the big _IC_JS above is untouched; _IC_JS calls window.__renderCtx early,
# before it builds the tab nav, so panels with no data hide themselves and are skipped.
_IC_CTX_CSS = r"""
.ctx-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:8px}
.ctx-cell{background:var(--cream);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.ctx-cell .pl{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}
.ctx-cell .pv{font-size:18px;color:var(--navy);font-weight:600;margin-top:3px}
.ctx-list{list-style:none;margin:8px 0 0;padding:0}
.ctx-list li{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid var(--line)}
.ctx-list li:last-child{border-bottom:0}
.ctx-list .k{color:var(--ink)}
.ctx-list .v{color:var(--navy);font-weight:600;white-space:nowrap;text-align:right}
.aqi{display:inline-block;padding:3px 11px;border-radius:999px;font-weight:600;font-size:13px;color:#fff}
.tagrow{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.tag{background:var(--pale);color:var(--navy);border-radius:999px;padding:3px 11px;font-size:13px}
.sev{font-weight:600;color:var(--navy)}
.narr p{margin:0 0 11px;line-height:1.6;color:var(--ink)}
.prov{font-size:12px;color:var(--mut);margin-top:10px}
.plan-item{padding:9px 0;border-bottom:1px solid var(--line)}
.plan-item:last-child{border-bottom:0}
.plan-item .ps{font-size:12px;color:var(--mut)}
"""

_IC_CTX_JS = r"""
window.__renderCtx=function(D,CTX){
  CTX=CTX||{}; var S=CTX.sections||CTX||{};
  var el=function(i){return document.getElementById(i);};
  function esc(s){var d=document.createElement('div');d.textContent=(s==null?'':String(s));return d.innerHTML;}
  function hide(id){var e=el(id); if(e) e.style.display='none';}
  function epcBand(score){ if(score==null) return null;
    var t=[[92,'A'],[81,'B'],[69,'C'],[55,'D'],[39,'E'],[21,'F'],[0,'G']];
    for(var i=0;i<t.length;i++){ if(score>=t[i][0]) return t[i][1]+' ('+score+')'; } return String(score); }
  function cell(label,val){ return '<div class="ctx-cell"><div class="pl">'+esc(label)+'</div><div class="pv">'+esc(val)+'</div></div>'; }

  // ---- Narrative (Gemini, grounded + guarded)
  (function(){
    var N=S.narrative;
    if(!N||N.ok===false||!N.text){ hide('p_narrative'); return; }
    var paras=String(N.text).split(/\n{1,}/).filter(function(p){return p.trim();});
    el('ctx_narrative').innerHTML=paras.map(function(p){return '<p>'+esc(p.trim())+'</p>';}).join('')+
      '<p class="prov">Narrative drafted by an AI model strictly from the figures in this report; any number it could not source was rejected before display.</p>';
  })();

  // ---- Location & connectivity
  (function(){
    var L=S.location;
    if(!L){ hide('p_location'); return; }
    var html='';
    if(L.validated && L.validated.formatted)
      html+='<p class="note">Verified address: <b>'+esc(L.validated.formatted)+'</b>'+(L.validated.note?' - '+esc(L.validated.note).toLowerCase():'')+'.</p>';
    var legs=L.legs||L.rows||[];
    if(legs.length)
      html+='<ul class="ctx-list">'+legs.map(function(g){
        var v=[g.time,g.dist].filter(Boolean).join(' · ');
        return '<li><span class="k">'+esc(g.label)+'</span><span class="v">'+esc(v||'-')+'</span></li>';
      }).join('')+'</ul>';
    if(L.postcode||(L.lat&&L.lng))
      html+='<p class="prov">Geolocated to '+esc(L.postcode||'')+((L.lat&&L.lng)?' ('+(+L.lat).toFixed(4)+', '+(+L.lng).toFixed(4)+')':'')+'.</p>';
    if(!html){ hide('p_location'); return; }
    el('ctx_location').innerHTML=html;
  })();

  // ---- Area & amenities
  (function(){
    var A=S.area;
    if(!A||!A.counts){ hide('p_area'); return; }
    var keys=Object.keys(A.counts).filter(function(k){return A.counts[k];});
    if(!keys.length){ hide('p_area'); return; }
    var grid='<div class="ctx-grid">'+keys.map(function(k){return cell(k, A.counts[k]);}).join('')+'</div>';
    var trans='';
    if(A.transport && A.transport.length)
      trans='<ul class="ctx-list">'+A.transport.map(function(t){
        return '<li><span class="k">'+esc(t.name)+'</span><span class="v">~'+esc(t.dist_m)+' m</span></li>';
      }).join('')+'</ul>';
    var note=(A.radius_m?('<p class="prov">Mapped within '+esc(A.radius_m)+' m of the property.</p>'):'');
    el('ctx_area').innerHTML=grid+trans+note;
  })();

  // ---- Safety
  (function(){
    var C=S.safety;
    if(!C){ hide('p_safety'); return; }
    var html='<div class="ctx-grid">'+cell('Crimes recorded', C.total)+
      (C.month?cell('Month', C.month):'')+'</div>';
    if(C.by_category && C.by_category.length)
      html+='<div class="tagrow">'+C.by_category.slice(0,6).map(function(p){
        return '<span class="tag">'+esc(p[0])+' '+esc(p[1])+'</span>';
      }).join('')+'</div>';
    html+='<p class="prov">'+esc(C.radius_note||'')+'. Street-level counts for the latest published month.</p>';
    el('ctx_safety').innerHTML=html;
  })();

  // ---- Environment (flood + air)
  (function(){
    var E=S.environment;
    if(!E||(!E.flood&&!E.air)){ hide('p_environment'); return; }
    var html='';
    if(E.flood){
      html+='<p><span class="sev">Flood:</span> '+esc(E.flood.severity||'')+'.';
      if(E.flood.lines&&E.flood.lines.length) html+=' '+esc(E.flood.lines[0]);
      html+='</p>';
    }
    if(E.air){
      var band=E.air.band||'', aqi=E.air.aqi;
      var col={'Good':'var(--green)','Fair':'var(--teal)','Moderate':'var(--gold)'}[band]||'#b4452f';
      html+='<p><span class="sev">Air quality:</span> <span class="aqi" style="background:'+col+'">AQI '+esc(aqi!=null?Math.round(aqi):'-')+' '+esc(band)+'</span>';
      var bits=[]; if(E.air.pm2_5!=null)bits.push('PM2.5 '+E.air.pm2_5); if(E.air.pm10!=null)bits.push('PM10 '+E.air.pm10); if(E.air.no2!=null)bits.push('NO2 '+E.air.no2);
      if(bits.length) html+=' <small>('+esc(bits.join(', '))+' µg/m³)</small>';
      html+='</p>';
    }
    el('ctx_environment').innerHTML=html;
  })();

  // ---- Planning & development
  (function(){
    var P=S.planning;
    if(!P){ hide('p_planning'); return; }
    var html='<div class="ctx-grid">'+cell('Applications nearby', P.total)+'</div>';
    if(P.by_status && P.by_status.length)
      html+='<div class="tagrow">'+P.by_status.slice(0,5).map(function(s){
        return '<span class="tag">'+esc(s[0])+': '+esc(s[1])+'</span>';
      }).join('')+'</div>';
    if(P.applications && P.applications.length)
      html+='<div style="margin-top:10px">'+P.applications.slice(0,5).map(function(a){
        return '<div class="plan-item">'+esc(a.description||'(no description)')+
          '<div class="ps">'+esc([a.status,a.date].filter(Boolean).join(' · '))+'</div></div>';
      }).join('')+'</div>';
    el('ctx_planning').innerHTML=html;
  })();

  // ---- Material information (EPC + council tax)
  (function(){
    var M=S.material;
    var eb=epcBand(D.epc);
    if(!M && !eb){ hide('p_material'); return; }
    var cells='';
    if(eb) cells+=cell('EPC rating', eb);
    if(M && M.band) cells+=cell('Council-tax band', M.band);
    var html='<div class="ctx-grid">'+cells+'</div>';
    if(M && M.bracket_1991)
      html+='<p class="prov">Band '+esc(M.band)+' reflects a 1991 open-market value of '+esc(M.bracket_1991)+'. '+esc(M.note||'')+'</p>';
    el('ctx_material').innerHTML=html;
  })();
};
"""


def _epc_band_letter(epc):
    """Normalise an EPC value (band letter or numeric SAP score) to a band letter."""
    if epc is None:
        return None
    s = str(epc).strip().upper()
    if s[:1] in ("A", "B", "C", "D", "E", "F", "G"):
        return s[0]
    try:
        n = float(re.sub(r"[^0-9.]", "", s))
    except Exception:
        return None
    for lo, band in ((92, "A"), (81, "B"), (69, "C"), (55, "D"), (39, "E"), (21, "F"), (0, "G")):
        if n >= lo:
            return band
    return None


def _market_climate(blob):
    """A single, honest 'Market Heat' read for the L1 hero. It is NOT a new computation:
    it surfaces the engine's already-disclosed, capped live-market steer (blob.market) plus
    the live positioning the page already holds. Tone is read straight off the steer sign -
    so the indicator can never claim a direction the figure was not actually steered by."""
    mk = blob.get("market") or {}
    pct = mk.get("pct")
    label = mk.get("label")
    pos = blob.get("positioning") or {}
    tone = "balanced"
    if isinstance(pct, (int, float)):
        if pct >= 1.5:
            tone = "warm"
        elif pct <= -1.5:
            tone = "cool"
    if not label:
        label = {"warm": "Rising", "cool": "Softening", "balanced": "Balanced"}[tone]
    return {
        "label": label, "pct": pct, "tone": tone, "note": mk.get("note"),
        "dom": pos.get("mean_dom"), "stuck": pos.get("stuck"),
        "listings": pos.get("listings"),
    }


def _impact_cards(blob, context):
    """The Data Translation Matrix: turn raw source readings into a TRANSLATED consequence
    with a traffic-light severity, grouped for the L2 Impact Dashboard.

    HONESTY CONTRACT (absolute):
      - No card invents a per-factor pound figure or a 'penalty %'. The engine moves the
        figure with two things only - condition tier and the capped/disclosed live-market
        steer - so every card here is CONTEXT BESIDE THE FIGURE. The Market climate card is
        the single exception and it says so in words, because that steer is a real, disclosed,
        capped input.
      - A card is emitted only when its source actually returned data. The two sources the
        spec names that have no free programmatic point-query (BGS GeoSure subsidence, Ofcom
        broadband) are rendered as honest 'not assessed' cards naming why - never faked.
      - severity vocabulary: good | watch | flag | info | na.
    """
    ctx = context or {}
    S = ctx.get("sections") or ctx or {}
    cards = []

    def add(group, title, raw, consequence, severity, source=None):
        cards.append({"group": group, "title": title, "raw": raw,
                      "consequence": consequence, "severity": severity, "source": source})

    # ---- Property Health -------------------------------------------------
    band = _epc_band_letter(blob.get("epc"))
    if band:
        if band in ("A", "B", "C"):
            sev = "good"
            cons = ("Energy efficiency sits in the upper bands, which typically means lower "
                    "running costs and broad lender and buyer acceptance.")
        elif band in ("D", "E"):
            sev = "watch"
            cons = ("A mid-band EPC points to average running costs; some buyers will price in "
                    "efficiency upgrades when they negotiate.")
        else:
            sev = "flag"
            cons = ("A low EPC band signals higher running costs and likely upgrade work; if the "
                    "property is let, note the MEES minimum-energy-efficiency standard.")
        add("Property Health", "Energy performance", f"EPC band {band}", cons, sev,
            "EPC Register (DLUHC)")

    mat = S.get("material") or {}
    if mat.get("band"):
        add("Property Health", "Council tax", f"Band {mat['band']}",
            "Council tax is charged at this band - a fixed annual running cost to budget for.",
            "info", "VOA council-tax bands")

    # ---- Local Environment ----------------------------------------------
    env = S.get("environment") or {}
    fl = env.get("flood")
    if fl:
        svy = str(fl.get("severity") or "")
        low = svy.lower()
        if fl.get("active"):
            sev = "flag"
            cons = ("An Environment Agency flood warning or alert currently covers this area; treat "
                    "flood searches and specialist insurance as essential before proceeding.")
        elif "not in a monitored" in low or "not inside a monitored" in low:
            sev = "good"
            cons = "This location is not inside a monitored Environment Agency flood-warning area."
        elif "monitored" in low:
            sev = "watch"
            cons = ("Inside a monitored flood area with no active warning; a buyer's solicitor will "
                    "normally run an environmental search and the buyer should check flood-insurance cover.")
        else:
            sev, cons = "info", (fl.get("lines") or [""])[0]
        add("Local Environment", "Flood risk", svy or "Checked", cons, sev,
            "Environment Agency flood-monitoring (OGL v3.0)")

    aq = env.get("air")
    if aq:
        b = str(aq.get("band") or "")
        sev = {"Good": "good", "Fair": "good", "Moderate": "watch"}.get(b, "flag")
        aqi = aq.get("aqi")
        add("Local Environment", "Air quality",
            f"AQI {round(aqi) if isinstance(aqi,(int,float)) else aqi} {b}".strip(),
            f"Local air quality reads as {b or 'reported'} - lifestyle context, never a value input.",
            sev, "Open-Meteo / DEFRA air quality")

    saf = S.get("safety")
    if saf and saf.get("total") is not None:
        add("Local Environment", "Recorded crime",
            f"{saf['total']} in {saf.get('month','the latest month')}",
            ("Street-level crime counts within about a mile for the latest published month; the "
             "category mix is in the Safety panel. Context beside the figure, not a price input."),
            "info", "Police.uk street-level crime")

    # BGS subsidence - named by the spec, no free point-query source. Honest 'na' card.
    try:
        import bgs as _bgs
        sub = _bgs.subsidence(ctx.get("lat"), ctx.get("lng"))
    except Exception:
        sub = {"ok": False, "reason": "subsidence client unavailable"}
    if not sub.get("ok"):
        add("Local Environment", "Subsidence / ground stability", "Not assessed",
            ("Not available via the mandated free sources: BGS GeoSure shrink-swell is a licensed "
             "product with no free point-query endpoint, so we do not estimate it rather than guess."),
            "na", "BGS GeoSure (licensed - not used)")

    # ---- Connectivity ----------------------------------------------------
    loc = S.get("location") or {}
    legs = loc.get("legs") or loc.get("rows") or []
    station = next((g for g in legs if "station" in str(g.get("label", "")).lower()), None)
    if station:
        bits = [x for x in (station.get("time"), station.get("dist")) if x]
        add("Connectivity", "Transport access",
            (station.get("label") or "Nearest station") + (": " + " / ".join(bits) if bits else ""),
            "Public-transport access to the nearest station; wider travel times are in the Location panel.",
            "good", "OSM Overpass / Google Distance Matrix")
    elif legs:
        add("Connectivity", "Transport access", f"{len(legs)} routes mapped",
            "Travel times to key destinations are listed in the Location panel.", "good",
            "Google Distance Matrix")

    # Ofcom broadband - named by the spec, no free per-postcode API. Honest 'na' card.
    try:
        import broadband as _bb
        bb = _bb.lookup(blob.get("postcode") or ctx.get("postcode"))
    except Exception:
        bb = {"ok": False, "reason": "broadband client unavailable"}
    if not bb.get("ok"):
        add("Connectivity", "Broadband", "Not assessed",
            ("Not available via the mandated free sources: Ofcom publishes coverage only as a bulk "
             "Connected Nations CSV, with no free per-postcode lookup API, so we do not state a speed we cannot verify."),
            "na", "Ofcom Connected Nations (bulk CSV - not point-queryable)")

    # ---- Market Sentiment -----------------------------------------------
    clim = _market_climate(blob)
    if clim.get("label"):
        pct = clim.get("pct")
        raw = clim["label"] + (f" ({pct:+.1f}%)" if isinstance(pct, (int, float)) and pct else "")
        extra = []
        if isinstance(clim.get("dom"), (int, float)):
            extra.append(f"typical time to sale ~{round(clim['dom'])} days")
        if isinstance(clim.get("stuck"), (int, float)) and clim["stuck"]:
            _n = int(clim["stuck"])
            extra.append(f"{_n} listing{'s' if _n != 1 else ''} look{'s' if _n == 1 else ''} stuck")
        cons = ("The live market reads as " + clim["label"].lower()
                + (" (" + "; ".join(extra) + ")" if extra else "")
                + ". This is the one live-market factor that adjusts the figure - capped and disclosed in the build-up.")
        add("Market Sentiment", "Market climate", raw, cons, "info",
            "HMLR PPD trend + live positioning")

    return cards


def _interactive_blob(compsA, val, subj, d, pos, context=None):
    """Assemble the single data blob the interactive page renders from. Every value
    traces to the engine output (val / subj / compsA / pos / summary d / context); nothing
    is invented. The page computes only what is derivable from this blob - the honesty
    contract, enforced by construction."""
    d = d or {}
    comps = []
    for r in sorted(compsA, key=lambda c: (-(c.get("score") or 0), c.get("price", 0))):
        comps.append({
            "addr": (r.get("address", "").split(",")[0])[:40],
            "full": r.get("address", ""),
            "sqm": r.get("sqm"), "price": r.get("price"),
            "psm": r.get("psm") or (round(r["price"] / r["sqm"]) if r.get("sqm") else None),
            "date": (r.get("date") or "")[:10],
            "dist": r.get("dist"),
            "match": r.get("match"), "weak": bool(r.get("weak")),
            "href": txn_link(r),
        })
    sold_med = d.get("sold_median")
    if sold_med is None and compsA:
        sold_med = sold_median(compsA)
    mk = val.get("market") or {}
    blob = {
        "address": d.get("address") or subj.get("address"),
        "sqm": subj.get("sqm"), "beds": subj.get("beds") or subj.get("beds_est"),
        "epc": subj.get("epc"), "tax": subj.get("tax"),
        "ptype": (subj.get("type") or "").strip() or None,
        "low": val["low"], "high": val["high"], "central": val["central"], "guide": val["guide"],
        "guide_label": d.get("guide_label") or "Recommended guide",
        "guide_value_str": d.get("guide_value_str") or ("Offers Over " + money(val["guide"])),
        # the lens the instrument turns to face: agent (win the instruction), vendor/seller
        # (defensible list price), buyer (negotiating headroom), investor (net + CGT). Same
        # figures throughout - only the framing rotates. Defaults to agent.
        "audience": d.get("audience") or "agent",
        # a known live asking/quote, when the caller has one, so the price-test handle can
        # start there. None is fine - the handle then starts at the guide. Never an input
        # to the figure; only the starting position of an explanatory slider.
        "asking": d.get("asking"), "quoted": d.get("quoted"),
        "sold_median": sold_med,
        "psmA": int(val["psmA"]) if val.get("psmA") else None,
        "crosscheck": val.get("crosscheck"),
        # official-register reality-check (HM Land Registry pulled directly via summary()).
        # Beside the figure, an independent check that the comparable sales are real -
        # never blended into low/high/central/guide. None when the register was quiet/down.
        "official_check": (d.get("crosscheck") if isinstance(d, dict) else None),
        "sold_anchor": val.get("sold_anchor"),
        "avm": {k: val.get("avm", {}).get(k) for k in ("average", "high", "very_high")},
        "market": {"pct": mk.get("pct"), "label": mk.get("label"), "note": mk.get("note")},
        "valuation_formula": d.get("valuation_formula") or val.get("formula"),
        "last_sold": subj.get("last_sold"), "last_sold_date": subj.get("last_sold_date"),
        "investment": bool(subj.get("investment")),
        "comps": comps,
        "n_comps": len(compsA),
        "n_screened": d.get("n_screened"),   # excluded-as-non-comparable count (spec statement)
        "positioning": None,
        "macro": d.get("macro") or None,
        "datestr": DATESTR,
        "postcode": subj.get("postcode") or d.get("postcode"),
        # L1 authority: the data-only confidence grade (0-100) the engine already computed.
        "confidence": d.get("confidence") or None,
        # tier gate - lite shows L1 only; pro unlocks the L2 dashboard + L3 evidence room.
        # Single source of truth (#68); defaults to pro so the full deliverable renders.
        "tier": (d.get("tier") or "pro"),
    }
    # L1 Market Heat + L2 Impact Dashboard, both honest by construction (built below once
    # positioning is attached so the climate card can read time-to-sale / stuck stock).
    if pos and pos.get("band"):
        blob["positioning"] = {
            "listings": len(pos["band"]), "lo_p": pos.get("lo_p"), "hi_p": pos.get("hi_p"),
            "median": pos.get("median"), "mean_dom": pos.get("mean_dom"),
            "stuck": len(pos.get("stuck") or []),
        }
    # Buyer-side costs. A UK buyer never pays the seller's agent commission - so the
    # buyer deliverable shows what a buyer ACTUALLY pays. Stamp duty is the exact figure
    # from macro.sdlt (marginal England/NI bands, first-time-buyer relief), cited to
    # gov.uk in References; legal and survey are clearly-labelled INDICATIVE third-party
    # ranges the buyer confirms with their own solicitor/surveyor, never a Honestly figure.
    try:
        import macro as _macro
        _c = val["central"]
        blob["buyer_costs"] = {
            "price": _c,
            "sdlt": _macro.sdlt(_c, first_time=False),
            "sdlt_ftb": (_macro.sdlt(_c, first_time=True)
                         if _c <= getattr(_macro, "SDLT_FTB_CEILING", 500_000) else None),
            # indicative-only, shown as ranges and flagged as third-party costs to confirm
            "legal_lo": 1000, "legal_hi": 1500,
            "survey_lo": 400, "survey_hi": 1000,
        }
    except Exception:
        blob["buyer_costs"] = None
    # Market Heat (L1) and the Data Translation Matrix (L2) - derived only from data already
    # in the blob + the gathered context; no new figure, no fabricated per-factor pounds.
    blob["market_climate"] = _market_climate(blob)
    try:
        blob["impact_cards"] = _impact_cards(blob, context)
    except Exception:
        blob["impact_cards"] = []
    # Evidence Purity (trust metric) + the personalised 'If this were our money' decision.
    # Both single-sourced from the engine so the HTML matches the PDF verbatim. Lazy import:
    # engine imports appraise, so a top-level import here would be circular.
    blob["evidence_purity"] = d.get("evidence_purity")
    try:
        import engine as _engine
        blob["decision"] = _engine.decision_block(d, blob.get("audience") or "buyer")
        blob["factor_qa"] = _engine.factor_qa(context)   # crime/planning/flood, flag-gated
    except Exception:
        blob["decision"] = None
        blob["factor_qa"] = []
    return blob


def interactive_chart(compsA, val, subj, slug, outdir, bot_url, d=None, pos=None, ref_data=None, context=None):
    """Write a self-contained, genuinely interactive single-file appraisal app.

    Not one chart - a multi-panel app: the glass-box build-up (tap each step of the
    arithmetic), a condition lever (the one input that legitimately moves the figure),
    the sortable comparable evidence with the live bar chart, a net-proceeds slider,
    live positioning, the market outlook and the same numbered References the PDF
    prints. Brand palette and the EXACT logo bytes are embedded; no CDN, opens offline
    from a Telegram attachment. Every figure traces to the engine data blob - the page
    computes only what is derivable from it, so it can never drift from the PDF or card.

    d   = engine.summary() dict (richer framing); optional, derived from val/subj if absent.
    pos = positioning dict; ref_data = the exact dict the PDF cited from (identical refs)."""
    blob = _interactive_blob(compsA, val, subj, d, pos, context=context)
    # --- view-level tier separation (leak-proof) --------------------------------------
    # The engine runs the full arsenal ONCE; tier is purely a VIEW over that single result.
    # A Lite deliverable does not merely hide the Pro panels - it physically strips the Pro
    # payload out of the embedded data, so a Lite file cannot be un-locked from its own
    # source (view-source / dev-tools recover nothing). The Pro sections then render as
    # honest frosted "locked" previews (title + one line of what Pro adds + a pay link) -
    # never real figures sitting behind a CSS blur. Pro = the identical layout, unlocked.
    tier = (blob.get("tier") or "pro").lower()
    context_view = context
    if tier == "lite":
        # Lite is the full free FACTS product, built to beat every competitor's free estimate:
        # it keeps ALL the verifiable facts (area context, crime, schools, flood/air, EPC and
        # council tax) and ALL the valuation transparency. Only the Pro SYNTHESIS is stripped -
        # the impact dashboard's translated traffic-light cards, the live positioning strategy
        # and the market-outlook/macro read - so a Lite file physically carries none of the Pro
        # interpretation layer (view-source/dev-tools recover nothing of it).
        blob["impact_cards"] = []          # L2 dashboard translation (Pro)
        blob["positioning"] = None         # live positioning strategy (Pro)
        blob["macro"] = None               # market outlook / macro (Pro)
        mc = blob.get("market_climate")    # keep the L1 heat label/note; drop the precise counts
        if isinstance(mc, dict):           # (those belong to the locked positioning panel)
            for k in ("dom", "stuck", "listings"):
                mc[k] = None
        context_view = context             # area facts stay in Lite - never stripped
    refs = brand.references(ref_data if ref_data is not None else (d or {}))
    logo = brand.logo_data_uri("lockup")
    icon = brand.logo_data_uri("icon")
    P = brand.HEX
    data_json = json.dumps(blob, ensure_ascii=False)
    refs_json = json.dumps(refs, ensure_ascii=False)
    ctx_json = json.dumps(context_view or {}, ensure_ascii=False, default=str)
    bot_url_json = json.dumps(bot_url or "#", ensure_ascii=False)
    # data-coverage rows from the shared contract, so every data input has a visible
    # home and customer-facing inclusion status. Commercial supplier names are deliberately
    # NOT embedded here - the body never promotes a vendor; References names sources.
    # The coverage panel is Pro; a Lite file ships none of it (the panel locks instead).
    cov = [] if tier == "lite" else [
        {"klass": r["klass"], "contributes": r["contributes"],
         "panel": r["html_panel"]} for r in brand.DELIVERABLE_MAP]
    cov_json = json.dumps(cov, ensure_ascii=False)

    root_css = (":root{"
                f"--navy:{P['navy']};--green:{P['green']};--teal:{P['teal']};--gold:{P['gold']};"
                f"--cream:{P['cream']};--paper:{P['paper']};--ink:{P['ink']};--mut:{P['muted']};"
                f"--sand:{P['sand']};--pale:{P['pale']};--line:{P['line']}" "}")
    logo_html = (f'<img class="logo" src="{logo}" alt="Honestly - a defensible value">'
                 if logo else '<div class="logo-fallback">honestly</div>')
    title = (blob["address"] or "Appraisal")

    # Net-proceeds (seller/agent) vs costs-to-buy (buyer) are mutually exclusive panels.
    # A UK buyer does not pay the seller's agent fee, so the agent-fee slider is gated to
    # the seller-side audiences; the buyer instead sees their real acquisition costs.
    _aud = (blob.get("audience") or "agent").lower()
    if _aud == "buyer":
        net_panel = """
  <section class="panel" id="p_buycost">
    <h2>Your costs to buy</h2>
    <p class="note">What a buyer actually pays on top of the price. Stamp duty is the exact figure for this value (England &amp; NI marginal bands, first-time-buyer relief shown where it applies) - see References. Legal and survey are indicative third-party ranges to confirm with your own solicitor and surveyor, not a Honestly figure.</p>
    <div class="net-grid" id="buycost"></div>
  </section>"""
    else:
        net_panel = """
  <section class="panel" id="p_net">
    <h2>Net proceeds</h2>
    <p class="note">What lands in the seller's pocket at the assessed central value. Drag the fee to model your own agent. {cgt_note}</p>
    <div class="slider-row">
      <label>Agent fee <b id="fee_pct">2.0%</b> + VAT</label>
      <input type="range" id="fee" min="0.5" max="3.5" step="0.1" value="2.0">
    </div>
    <div class="net-grid" id="net"></div>
  </section>""".replace("{cgt_note}",
        ('A capital-gains line is shown because this is held as an investment.'
         if blob.get('investment') else
         'Move the slider - the maths updates live, grounded in the same central figure the report prints.'))

    # the honest "where they cluster" line - the interquartile band, not outlier min/max -
    # kept 1:1 with the PDF executive summary so the two surfaces never disagree.
    _cb = comp_band(compsA)
    comps_cluster_note = (
        f" The middle half of the best-matching sales cluster between "
        f"{money(_cb[0])} and {money(_cb[1])}." if _cb else "")

    head = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{title} - Honestly</title>'
        f'<style>{root_css}{_IC_CSS}{_IC_CTX_CSS}</style></head><body>'
    )
    body = f"""
<header class="mast">
  <div class="mast-in">
    {logo_html}
    <div class="mast-meta"><div class="mast-title">Market Appraisal</div><div class="mast-date" id="m_date"></div></div>
  </div>
</header>
<main class="wrap">
  <section class="hero">
    <h1 id="h_addr"></h1>
    <div class="facts" id="h_facts"></div>
    <div class="hero-figs">
      <div class="fig big"><span class="lab">Assessed range</span><span class="val" id="h_range"></span></div>
      <div class="fig"><span class="lab">Central value</span><span class="val" id="h_central"></span></div>
      <div class="fig"><span class="lab" id="h_guide_lab"></span><span class="val" id="h_guide"></span></div>
    </div>
    <p class="lede" id="h_lede"></p>
    <div class="authority" id="h_authority"></div>
    <div class="purity" id="h_purity"></div>
  </section>

  <section class="panel decision" id="p_decision">
    <h2 id="dec_q">If this were our money</h2>
    <p class="note" id="dec_need"></p>
    <div class="dec-verdict"><span class="dec-word" id="dec_word"></span><span class="dec-head" id="dec_head"></span></div>
    <div class="dec-cols">
      <div class="dec-why"><h3>Why</h3><ul id="dec_why"></ul></div>
      <div class="dec-risk"><h3>Watch out for</h3><ul id="dec_risk"></ul></div>
    </div>
    <p class="dec-next" id="dec_next"></p>
    <a class="dec-cta" id="dec_cta" target="_blank" rel="noopener" style="display:none">Turn this into a plan for your property &rsaquo;</a>
  </section>

  <section class="panel" id="p_factors" style="display:none">
    <h2>Does anything change the number?</h2>
    <div id="factors"></div>
  </section>

  <section class="panel instrument" id="p_asking">
    <h2 id="ask_title">Test any price against the evidence</h2>
    <p class="note" id="ask_note"></p>
    <div class="pricetest">
      <div class="pt-readout"><span class="pt-price" id="pt_price"></span><span class="pt-zone" id="pt_zone"></span></div>
      <div class="pt-scale" id="pt_scale"></div>
      <input type="range" id="pt_slider" class="pt-slider">
      <div class="pt-verdict" id="pt_verdict"></div>
      <div class="pt-legend" id="pt_legend"></div>
    </div>
  </section>

  <nav class="tabs" id="tabs"></nav>

  <section class="panel" id="p_build">
    <h2>Formula</h2>
    <p class="note">Sold evidence is the floor of fact. The formula below shows the evidence set, condition rule and final rounded range. Asking prices, agent quotes and portal estimates are not inputs.</p>
    <div class="steps" id="buildup"></div>
  </section>

  <section class="panel" id="p_condition">
    <h2>Condition lever</h2>
    <p class="note">Condition is the one input that legitimately moves the figure. These are the condition-adjusted valuations behind our assessment, for this property's size and area, by finish tier - real figures, not a slider we invented.</p>
    <div class="lever" id="lever"></div>
    <div class="lever-out" id="lever_out"></div>
  </section>

  <section class="panel" id="p_comps">
    <h2>Comparable evidence (sold)</h2>
    <p class="note">Same-type properties sold near the subject, from HM Land Registry Price Paid Data, each scored for comparability (location, size, GBP/sqm, recency, tenure) - the Match column, best first.{comps_cluster_note} Sort any column; the address, date and price row is shown here so you can verify the figure against the official sold-price register.</p>
    <div class="sortbar" id="sortbar"></div>
    <div id="chart"></div>
    <div class="legend">
      <span><i style="background:var(--green)"></i>Sold comparable</span>
      <span><i class="band-sw"></i>Assessed range</span>
      <span><i class="line-sw" style="background:var(--green)"></i>Central value</span>
      <span><i class="line-sw" style="background:var(--gold)"></i>Recommended guide</span>
    </div>
    <p class="note excluded" id="ev_excluded"></p>
    <table class="comps" id="comps"><thead><tr>
      <th data-k="addr">Comparable</th><th data-k="sqm" class="r">Size</th>
      <th data-k="price" class="r">Sold</th><th data-k="date" class="c">When</th>
      <th data-k="psm" class="r">GBP/sqm</th><th data-k="dist" class="r">Dist</th>
      <th data-k="match" class="r">Match</th>
      <th class="c">Verify</th></tr></thead><tbody></tbody></table>
    <p class="note official" id="ev_official"></p>
  </section>

  {net_panel}

  <section class="panel" id="p_position">
    <h2>Live market &amp; positioning</h2>
    <div id="position"></div>
  </section>

  <section class="panel" id="p_outlook">
    <h2>Market outlook</h2>
    <div id="outlook"></div>
  </section>

  <section class="panel" id="p_dashboard">
    <h2>Impact dashboard</h2>
    <p class="note">What the surrounding data means for this property, translated into plain consequences and graded as a traffic light. Each card is context beside the figure - only condition and the capped, disclosed live-market steer move the value itself. Tap a card to see the raw reading and its source.</p>
    <div class="dash" id="dashboard"></div>
  </section>

  <section class="panel locked" id="p_unlock" style="display:none">
    <h2>Unlock the full report</h2>
    <p class="note">Your free report already gives you more than any portal estimate: the assessed range, the confidence grade, the market climate, the plain-English narrative, the price test, the glass-box formula, the condition lever, the comparable sold evidence with HM Land Registry links, and the full local picture - connectivity, area, crime, environment, planning and material information. Pro adds the one thing no competitor gives you - what it all MEANS for your decision:</p>
    <ul class="unlock-list" id="unlock_list"></ul>
    <a class="cta" id="unlock_cta" href="#" target="_blank" rel="noopener">Unlock the full report</a>
    <p class="note">Same property, same evidence, same arithmetic - Pro turns the facts above into a decision: the translated impact dashboard, the pricing strategy and the full evidence room. No invented figures sit behind the lock.</p>
  </section>

  <section class="panel" id="p_narrative">
    <h2>In plain English</h2>
    <div class="narr" id="ctx_narrative"></div>
  </section>

  <section class="panel" id="p_location">
    <h2>Location &amp; connectivity</h2>
    <p class="note">Where the property sits and how well connected it is. Travel times are public-transport estimates; location is context beside the figure, never an input to it.</p>
    <div id="ctx_location"></div>
  </section>

  <section class="panel" id="p_area">
    <h2>Area &amp; amenities</h2>
    <p class="note">What is mapped within a short walk. Counts are from open mapping data and describe the neighbourhood, not the valuation.</p>
    <div id="ctx_area"></div>
  </section>

  <section class="panel" id="p_safety">
    <h2>Safety</h2>
    <p class="note">Street-level crime recorded within roughly a mile in the most recent published month. Area context, never a price input.</p>
    <div id="ctx_safety"></div>
  </section>

  <section class="panel" id="p_environment">
    <h2>Environment</h2>
    <p class="note">Flood monitoring and air quality at this location - context beside the figure.</p>
    <div id="ctx_environment"></div>
  </section>

  <section class="panel" id="p_planning">
    <h2>Planning &amp; development</h2>
    <p class="note">Recent planning applications near the property: what is changing nearby. Context, not a value input.</p>
    <div id="ctx_planning"></div>
  </section>

  <section class="panel" id="p_material">
    <h2>Material information</h2>
    <p class="note">Energy performance and council-tax band - the material facts a buyer is entitled to see.</p>
    <div id="ctx_material"></div>
  </section>

  <section class="panel" id="p_coverage">
    <h2>Data sources in this appraisal</h2>
    <p class="note">Every data source the platform draws on, and where it appears in the delivered pack. Each row is included with either a value, a source-backed fallback, or a decision-check item.</p>
    <div class="cov" id="coverage"></div>
  </section>

  <section class="panel" id="p_refs">
    <h2>References</h2>
    <p class="note">The data sources this appraisal actually used, numbered and dated. A source is listed only where its data appears above - the same list the PDF prints.</p>
    <ol class="refs" id="refs"></ol>
  </section>

  <a class="cta" href="{bot_url}" target="_blank" rel="noopener">Value another property yourself on Telegram</a>
  <footer class="foot">
    <img class="foot-icon" src="{icon}" alt="">
    Sold prices from HM Land Registry. Asking prices are never used to set the figure.
    Delivered via Telegram. <a href="{bot_url}" target="_blank" rel="noopener">made with Honestly</a>.
  </footer>
</main>
<div id="tip"></div>
<script>
const DATA = {data_json};
const REFS = {refs_json};
const COVERAGE = {cov_json};
const CTX = {ctx_json};
const BOT_URL = {bot_url_json};
function buyLink(mid){{ if(!BOT_URL||BOT_URL==='#') return '#'; return BOT_URL+(BOT_URL.indexOf('?')>=0?'&':'?')+'start=buy_'+(mid||'pro'); }}
{_IC_CTX_JS}
{_IC_JS}
</script>
</body></html>"""
    html_doc = head + body
    p = f"{outdir}/{slug}_interactive.html"
    open(p, 'w', encoding='utf-8').write(html_doc)
    return p

# ---------------------------------------------------------------- render
def comp_row(r):
    flag = " ⚠ cross-district" if r.get('cross_district') else ""
    return f"| {r['address']}{flag} · {r['sqm']} sqm | {r['date'][:7]} | {money(r['price'])} | £{r['psm']:,} | {r['dist']} mi | [source]({txn_link(r)}) |"

def pos_loc(addr):
    seg = addr.split(',')[0].strip()
    seg = re.sub(r'^(flat|apartment|apt)\s*\w+\s*,?\s*', '', seg, flags=re.I).strip()
    pc = postcode_of(addr)
    parts = pc.split() if pc else []
    sector = (parts[0] + ' ' + parts[1][0]) if len(parts) == 2 and parts[1] else (parts[0] if parts else '')
    return f"{seg}{(', ' + sector) if sector else ''}"

def pos_section(pos, subj, val):
    """Markdown for 'Live market & competitive positioning'. Asking prices = positioning, not evidence."""
    if not pos: return []
    L = []
    L.append("## Live market & competitive positioning\n")
    L.append("Sold prices establish what the property is *worth*; the live market shows what it is *competing against*. "
             "The assessed range above rests on completed sales - the only firm evidence of value. The asking prices below "
             "signal vendor expectation, not achieved value, and are **not** used in the assessment; they position the "
             "recommended guide against the homes a buyer can view today.\n")
    L.append(f"The live competitive band - flats currently listed across the district at {money(pos['lo_p'])} - {money(pos['hi_p'])}, "
             "the realistic field for a property of this size and character. Bedroom count alone does not define a comparable "
             "(see Basis of assessment): size, condition and location set the price.\n")
    L.append("| Asking | Beds | Days listed | Status | Location | Listing |\n|---|---|---|---|---|---|")
    for r in pos['band']:
        st = "Under offer" if r.get('sstc') else "Available"
        pname, plink = listing_link(r.get('url'))
        cell = f"[{pname}]({plink})" if plink else " - "
        L.append(f"| {money(r['price'])} | {r.get('bedrooms')} | {r.get('days_on_market') or 0} | {st} | {pos_loc(r['address'])} | {cell} |")
    L.append(f"\nMedian asking **{money(pos['median'])}**; average time on the market **{pos['mean_dom']} days**. "
             "Each listing links to the live portal page - asking price, photographs, time on the market and the marketing agent.\n")
    if pos['stuck']:
        worst = pos['stuck'][:3]
        ws = "; ".join(f"{pos_loc(r['address'])} at {money(r['price'])}, listed {r.get('days_on_market')} days" for r in worst)
        uo = pos['under_offer']
        L.append(f"**The cost of overpricing.** {len(pos['stuck'])} of the {len(pos['band'])} listings have sat unsold for 90 days or more - "
                 f"the longest: {ws}. Keenly-priced, well-presented stock behaves differently: "
                 f"{len(pos['fresh'])} went to market within the last three weeks"
                 + (f", and the only property under offer in the band was priced at {money(min(r['price'] for r in uo))}" if uo else "")
                 + ". In this district an over-ambitious asking price does not win a higher sale - it produces a longer, costlier one.\n")
    L.append(f"**Where this property sits.** The recommended **Offers Over {money(val['guide'])}** is set at the lower end of the live band "
             f"and **{money(pos['below_median'])} below its median asking price** - deliberately. Anchored to sold evidence, it positions the "
             f"property among the most competitively priced homes of its size and character on the market, to draw multiple viewings and "
             f"competing offers toward the assessed **{money(round_to(val['central']*0.97,5000))} - {money(val['high'])}** target - rather than "
             "joining the stalled listings above.\n")
    return L

def render_md(subj, A, B, val, fin, args, charts_, net_rows, pos=None, chart_url=None):
    name = subj['address']
    pd = f"[PropertyData](https://propertydata.co.uk/r/{args.referral})" if getattr(args, 'referral', '') else "PropertyData"
    A_med = statistics.median([r['price'] for r in A]) if A else 0
    bot = os.environ.get("HONESTLY_BOT_URL", "https://t.me/usehonestly_bot")
    lines = []
    ad = lambda s: lines.append(s)
    ad(f"# Market Appraisal - {name}\n")
    ad(f"**Prepared by {args.agent}** · {DATESTR}\n")
    links = [f"**[Explore the interactive chart]({chart_url})**" if chart_url else "",
             f"**[Value any property yourself on Telegram]({bot})**"]
    ad("  ·  ".join(p for p in links if p) + "\n")
    ad("Send an address, pick vendor, buyer or agent, and get this same evidence-backed appraisal in "
       "seconds. The interactive chart lets you hover every sold comparable and open its HM Land Registry record.\n")
    ad("---\n")
    ad("## Contents\n")
    toc = ["Executive summary","The property","Comparable evidence","Valuation","Market conditions"]
    if pos: toc.append("Live market & competitive positioning")
    toc += ["Recommended guide price","Net proceeds","Limitations","Sources & references"]
    for i,s in enumerate(toc,1):
        ad(f"{i}. [{s}](#{slugify(s).replace('_','-')})")
    ad("\n---\n")
    ad("## Executive summary\n")
    _fin_note = {'high': ", refurbished to a high standard",
                 'very_high': ", refurbished to a high standard",
                 'needs_modernising': ", dated and in need of modernisation",
                 'needs_renovation': ", in need of full renovation"}.get(fin, "")
    _band = comp_band(A)
    _band_note = (f" Comparable sales cluster around {money(_band[0])} to {money(_band[1])} "
                  f"(the middle half of {len(A)} same-size sales nearby)." if _band else "")
    ad(f"A {args.beds}-bedroom, {args.baths}-bathroom {subj['type'] or 'property'} of approximately {subj['sqm']} sqm"
       + _fin_note + ". "
       f"Comparable same-size, same-character properties sold nearby ({len(A)} of them)." + _band_note + "\n")
    ad("| | |\n|---|---|")
    ad(f"| **Assessed value range** | **{money(val['low'])} - {money(val['high'])}** (central ~{money(val['central'])}) |")
    ad(f"| **Recommended guide price** | **Offers Over {money(val['guide'])}** |")
    if subj.get('last_sold'): ad(f"| **Last recorded sale** | {money(subj['last_sold'])} ({subj['last_sold_date']}) |")
    ad(f"| **Held as** | {'Investment property - CGT applies' if args.investment else 'Primary residence'} |\n")
    ad("## The property\n")
    lease = (subj['leases'][0]['term'] if subj['leases'] else 'see register')
    ad(f"Recorded internal area {subj['sqft']} sqft ({subj['sqm']} sqm); EPC {subj['epc']}; Council Tax Band {subj['tax']}; "
       f"construction {subj['construction']}. Tenure: {lease}. "
       + (f"Last sold {money(subj['last_sold'])} on {subj['last_sold_date']}." if subj.get('last_sold') else "") + "\n")
    ad("## Comparable evidence\n")
    ad("Flats/houses of comparable size and character, within range, sold within "
       f"{args.maxage} months to {DATESTR}, from HM Land Registry Price Paid Data, held live on {pd}. "
       "Each linked transaction below opens the free record for that exact sale, with the property and its photographs.\n")
    ad("### Tier A - comparable character\n")
    ad("| Comparable · size | Sold | Price | £/sqm | Dist. | Source |\n|---|---|---|---|---|---|")
    for r in A: ad(comp_row(r))
    ad(f"\nTier A median **{money(A_med)}**.\n")
    if charts_.get('comps'): ad(f"![Exhibit 1]({os.path.basename(charts_['comps'])})\n")
    if B:
        ad("### Tier B - distinct market tier (context only)\n")
        ad("| Comparable · size | Sold | Price | £/sqm | Dist. | Source |\n|---|---|---|---|---|---|")
        for r in B: ad(comp_row(r))
        ad("\nHigher-value tier; retained to mark the local ceiling, not used to value.\n")
    ad("## Valuation\n")
    if charts_.get('finish'): ad(f"![Exhibit 2]({os.path.basename(charts_['finish'])})\n")
    ad("| Basis | Value |\n|---|---|")
    ad(f"| Tier A comparable median | {money(A_med)} |")
    for fq in ('average','high','very_high'):
        if val['avm'].get(fq): ad(f"| Condition-adjusted valuation - {fq.replace('_',' ')} finish | {money(val['avm'][fq])} |")
    if val['crosscheck']: ad(f"| £/sqm cross-check (£{val['psmA']:,} × {subj['sqm']} sqm) | {money(val['crosscheck'])} |")
    conf = d.get('confidence') if isinstance(d, dict) else None
    conf_text = f"{conf.get('grade', 'Fair')} ({conf.get('score', '-')}/100)" if conf else "Fair"
    conf_note = f" Data signal: {conf.get('note')}" if conf and conf.get('note') else ""
    ad(f"\nComparable evidence and the condition-adjusted valuation give an assessed range of "
       f"**{money(val['low'])} - {money(val['high'])}, central ~{money(val['central'])}.** Confidence is {conf_text}.{conf_note}\n")
    pe = d.get('plain_english') if isinstance(d, dict) else None
    if pe:
        ad("## In plain English\n")
        if pe.get('headline'): ad(f"{pe['headline']}\n")
        for b in (pe.get('bullets') or [])[:4]:
            ad(f"- {b}\n")
    ad("## Market conditions\n")
    ad("| Indicator | Value |\n|---|---|")
    for k,v in subj.get('demand',{}).items(): ad(f"| {k} | {v} |")
    ad("")
    for line in pos_section(pos, subj, val): ad(line)
    ad("\n## Recommended guide price\n")
    ad(f"**Offers Over {money(val['guide'])}**, below the assessed range, to invite competing offers toward "
       f"{money(round_to(val['central']*0.97,5000))} - {money(val['high'])}.\n")
    ad("## Net proceeds\n")
    if charts_.get('net'): ad(f"![Exhibit 3]({os.path.basename(charts_['net'])})\n")
    ad("| Achieved price | Fee (2%+VAT) | Net of fee | " + ("Indicative CGT | Net of fee & CGT |" if args.investment else "|"))
    ad("|---|---|---|" + ("---|---|" if args.investment else "---|"))
    for row in net_rows: ad(row)
    if args.investment:
        ad("\nIndicative CGT at 24% higher-rate residential after the £3,000 annual exempt amount (2025/26); excludes acquisition and refurbishment costs (allowable). Not tax advice.\n")
    ad("## Limitations\n")
    ad("1. Floor area is EPC-recorded; a measured survey may differ.\n2. Refurbishment specification not independently inspected.\n"
       "3. Tier assignment is a draft for agent confirmation.\n4. Asking prices are not used in the assessed value.\n")
    ad("## Sources & references\n")
    ad("[1] HM Land Registry Price Paid Data (OGL v3.0): https://www.gov.uk/search-house-prices. Via PropertyData API.\n")
    ad(f"[2] {pd}. [3] EPC Register. [4] HMRC CGT rates: https://www.gov.uk/capital-gains-tax/rates.\n")
    ad("\n**Comparable records** (HM Land Registry Price Paid evidence; exact address, date and price shown below):\n")
    for r in A+B:
        ad(f"- {r['address']} - {money(r['price'])}, {r['date']}; ref. {tuid_of(r.get('url'))}. {txn_link(r)}")
    ad(f"\n*Prepared by {args.agent}, {DATESTR}. A comparative market appraisal based on HM Land Registry and {pd} evidence; not a RICS Red Book valuation. CGT figures indicative, not tax advice.*")
    ad("\n---\n")
    foot = []
    if chart_url: foot.append(f"[Interactive chart]({chart_url})")
    foot.append(f"[Value any property on Telegram]({bot})")
    ad("  ·  ".join(foot))
    ad(f"\n*made with [Honestly]({bot})*")
    return "\n".join(lines)

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('address')
    ap.add_argument('--key', default=os.environ.get('PROPERTYDATA_KEY'))
    ap.add_argument('--street-key', default=os.environ.get('STREETDATA_KEY'), help='Street Data API key (or set STREETDATA_KEY). Passed as the x-api-key header.')
    ap.add_argument('--beds', type=int); ap.add_argument('--baths', type=int, default=1)
    ap.add_argument('--type', default=None, help='flat|terraced_house|semi-detached_house|detached_house')
    ap.add_argument('--finish', default='average',
                    choices=['needs_renovation','needs_modernising','average','high','very_high'])
    ap.add_argument('--investment', action='store_true')
    ap.add_argument('--radius', type=float, default=0.5); ap.add_argument('--maxage', type=int, default=24)
    ap.add_argument('--agent', default='Agent'); ap.add_argument('--outdir', default='.')
    ap.add_argument('--referral', default='', help='PropertyData referral code (e.g. rLY3b9Bo). Links the PropertyData data-source mentions to your /r/ referral link so recipients who sign up are attributed to you. Per-comp verification links stay direct.')
    ap.add_argument('--finalize', action='store_true', help='use the edited <slug>_comps.csv tiers')
    args = ap.parse_args()
    if not args.key: sys.exit("Set PROPERTYDATA_KEY env var or pass --key")
    os.makedirs(args.outdir, exist_ok=True)

    subj = find_subject(args.address, args.key)
    subj['beds'] = args.beds or subj['beds_est']; subj['baths'] = args.baths
    pdtype = args.type or ('flat' if ('flat' in subj['type'] or 'maison' in subj['type']) else 'terraced_house')
    slug = slugify(subj['address'].split(',')[0])
    print(f"Subject: {subj['address']} | {subj['sqm']} sqm | type={pdtype} | last sold {subj.get('last_sold')}")

    try: subj['demand'] = {k:v for k,v in api("demand", args.key, postcode=postcode_of(subj['address']).split()[0]).items()
                           if k in ('demand_rating','months_of_inventory','days_on_market','total_for_sale')}
    except Exception: subj['demand'] = {}

    sold = pull_sold(subj, args.key, pdtype, args.maxage)
    comps = candidate_comps(sold, subj, args.radius)
    comps_csv = f"{args.outdir}/{slug}_comps.csv"
    if args.finalize and os.path.exists(comps_csv):
        override = {row['address']: row['tier'] for row in csv.DictReader(open(comps_csv, encoding='utf-8'))}
        for r in comps: r['tier'] = override.get(r['address'], r['tier'])
    else:
        with open(comps_csv, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f); w.writerow(['address','date','price','sqm','psm','dist','tier'])
            for r in comps: w.writerow([r['address'],r['date'],r['price'],r['sqm'],r['psm'],r['dist'],r['tier']])
        print(f"Wrote {comps_csv} - review tiers (A/B/exclude) and re-run with --finalize")

    A = [r for r in comps if r['tier']=='A']; B = [r for r in comps if r['tier']=='B']
    if not A: sys.exit("No Tier A comps - widen --radius or check inputs.")
    val = valuation(subj, A, args.key, args.finish, pdtype)

    fee_rate = 0.024
    net_rows = []
    for p in (val['low'], val['central'], val['high']):
        fee = round(p*fee_rate); nf = p-fee
        if args.investment:
            gain = max(0, p - (subj.get('last_sold') or 0) - fee - 3000); cgt = round(gain*0.24)
            net_rows.append(f"| {money(p)} | {money(fee)} | {money(nf)} | {money(cgt)} | {money(nf-cgt)} |")
        else:
            net_rows.append(f"| {money(p)} | {money(fee)} | {money(nf)} |")
    central_net = val['central'] - round(val['central']*fee_rate)
    central_cgt = round(max(0, val['central']-(subj.get('last_sold') or 0)-round(val['central']*fee_rate)-3000)*0.24) if args.investment else 0
    ch = charts(A, val, subj, fee_rate, central_cgt, central_net-central_cgt, slug, args.outdir)

    pos = positioning(subj, val, pull_listings(subj, args.key, pdtype))
    if pos: print(f"Live band: {len(pos['band'])} listings, median ask {money(pos['median'])}, {len(pos['stuck'])} stuck >=90d")

    bot_url = os.environ.get("HONESTLY_BOT_URL", "https://t.me/usehonestly_bot")
    inter_path = interactive_chart(A, val, subj, slug, args.outdir, bot_url, pos=pos)
    print(f"Wrote {inter_path}")
    # Link the PDF to the interactive chart. Hosted base if set, else the file shipped alongside.
    base = os.environ.get("HONESTLY_CHART_BASE", "").rstrip("/")
    chart_url = f"{base}/{slug}_interactive.html" if base else f"{slug}_interactive.html"

    md = render_md(subj, A, B, val, args.finish, args, ch, net_rows, pos, chart_url=chart_url)
    md_path = f"{args.outdir}/{slug}_appraisal.md"
    open(md_path, 'w', encoding='utf-8').write(md)
    print(f"Wrote {md_path}")

    # PDF via the markdown-to-pdf-windows skill + Edge (optional)
    md2 = os.path.expanduser("~/.claude/skills/markdown-to-pdf-windows/md2html.py")
    edge = next((p for p in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                             r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"] if os.path.exists(p)), None)
    if os.path.exists(md2) and edge:
        html_path = f"{args.outdir}/{slug}_appraisal.html"; pdf_path = f"{args.outdir}/{slug}_appraisal.pdf"
        subprocess.run([sys.executable, md2, md_path, html_path], check=True, cwd=args.outdir)
        subprocess.run([edge, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={os.path.abspath(pdf_path)}", os.path.abspath(html_path)],
                       cwd=args.outdir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Wrote {pdf_path}" if os.path.exists(pdf_path) else "PDF step skipped (Edge render failed)")
    else:
        print("PDF skipped (md2html.py or Edge not found)")
    print(f"Assessed: {money(val['low'])} - {money(val['high'])} | central {money(val['central'])} | guide Offers Over {money(val['guide'])}")

if __name__ == '__main__':
    main()
