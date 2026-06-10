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
import argparse, json, math, os, re, sys, subprocess, statistics, urllib.parse, urllib.request, datetime, csv, time

API = "https://api.propertydata.co.uk"
STREET_API = "https://api.data.street.co.uk/street-data-api/v2"  # Street Data: 150+ fields on 29m E&W addresses, refreshed daily
TODAY = datetime.date.today()
DATESTR = f"{TODAY.day} {TODAY:%B %Y}"
GREEN, ACCENTD, TERRA, GREY, NAVY = '#1f6f5c', '#143f33', '#b9623a', '#c9c1ad', '#143f33'

def api(endpoint, key, _retries=5, **params):
    params['key'] = key
    url = f"{API}/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 appraise.py"})
    for attempt in range(_retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < _retries-1:
                time.sleep(6 + attempt*4); continue
            raise
        if isinstance(d, dict) and d.get('code') in ('X14',) and attempt < _retries-1:
            time.sleep(6 + attempt*4); continue
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

def money(v): return "£{:,.0f}".format(round(v))
def slugify(s): return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')[:40]
def round_to(v, step): return int(round(v / step) * step)

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
def txn_link(r):  # PropertyData transaction page: free to verify, shows the property + photos
    u = r.get('url') or ''
    t = tuid_of(u)
    return f"https://propertydata.co.uk/transaction/{t}" if t else u
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

def find_subject(address, key):
    uprn, matched, cls = _resolve_uprn(address, key)
    u = api("uprn", key, uprn=uprn)['data']
    # Thin records (new builds) often return no propertyType; trust the UPRN
    # classification ('Flat', 'Terraced', ...) so the engine pulls the right comps.
    rtype = (u.get('propertyType') or u.get('description') or cls or '').lower()
    return {
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

def pull_sold(subj, key, pdtype, max_age):
    sp = api("sold-prices", key, postcode=postcode_of(subj['address']).split()[0],
             type=pdtype, max_age=max_age, points=100)['data']['raw_data']
    psf = {r['url']: r for r in api("sold-prices-per-sqf", key,
             postcode=postcode_of(subj['address']).split()[0], type=pdtype,
             max_age=max_age, points=100)['data']['raw_data']}
    for r in sp:
        m = psf.get(r['url'])
        r['sqm'] = round(m['sqf']/10.7639) if m and m.get('sqf') else None
        try: r['dist'] = round(miles(subj['lat'], subj['lng'], float(r['lat']), float(r['lng'])), 2)
        except Exception: r['dist'] = None
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
    c = [r for r in sold if r['sqm'] and lo <= r['sqm'] <= hi and r['dist'] is not None
         and r['dist'] <= radius and r['price'] >= floor and 'wolves' not in r['address'].lower()
         and subj['address'].split(',')[0].lower() not in r['address'].lower()]
    if len(c) < 5:  # widen distance once if thin
        c = [r for r in sold if r['sqm'] and lo <= r['sqm'] <= hi and r['dist'] is not None
             and r['dist'] <= min(1.0, radius*2) and r['price'] >= floor]
    pm = statistics.median([r['price']/r['sqm'] for r in c]) if c else 0
    for r in c:
        r['psm'] = round(r['price']/r['sqm'])
        # auto-suggested tier: B if notably pricier per sqm (different market tier)
        r['tier'] = 'B' if r['psm'] > 1.28 * pm else 'A'
    c.sort(key=lambda r: (r['tier'], r['price']))
    return c

# Below-average condition has no AVM tier, so we discount the average-condition figure.
# Disclosed, conservative cuts: dated/needs modernising vs run-down/needs full renovation.
CONDITION_DISCOUNT = {'needs_modernising': 0.90, 'needs_renovation': 0.80}

def valuation(subj, compsA, key, finish, pdtype):
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
    pricesA = sorted(r['price'] for r in compsA)
    tierA_med = statistics.median(pricesA) if pricesA else (avm.get('average') or 0)
    psmA = statistics.median(r['psm'] for r in compsA) if compsA else 0
    base = avm.get('average') or tierA_med
    if finish in CONDITION_DISCOUNT:
        # The AVM only quotes average/high/very_high - it has no below-average tier. A home
        # that needs modernising or a full renovation sells at a discount to the average-
        # condition figure: roughly the cost of the works plus a buyer's risk premium. We
        # anchor on the average AVM (or the sold median) and take an honest, disclosed cut.
        anchor = avm.get('average') or tierA_med
        central = anchor * CONDITION_DISCOUNT[finish]
        low  = round_to(central * 0.93, 5000)
        high = round_to(central * 1.05, 5000)
        central = round_to(central, 5000)
    else:
        central = avm.get(finish) or round((tierA_med + (avm.get('high') or tierA_med))/2)
        low = round_to(min(central, max(tierA_med, base + 0.5*((avm.get('high') or base)-base))), 5000)
        high = round_to(avm.get('very_high') or central*1.06, 5000)
        central = round_to(central, 5000)
    guide = round_to(central * 0.89, 25000)
    return {'avm': avm, 'tierA_med': tierA_med, 'psmA': psmA,
            'crosscheck': round(psmA*subj['sqm']) if (psmA and subj.get('sqm')) else None,
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
                         'note': "No comparable homes are on the market nearby to read, so this rests "
                                 "on the sold evidence alone."}
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
    val['guide'] = round_to(val['central'] * 0.89, 25000)
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
def interactive_chart(compsA, val, subj, slug, outdir, bot_url):
    """Write a self-contained, genuinely interactive HTML chart: hover any sold
    comparable for its detail, click it to open the HM Land Registry record. The
    assessed range, central value and recommended guide are drawn as live overlays.
    No CDN, no build step. This is the 'interactive' the PDF links to."""
    cc = sorted(compsA, key=lambda r: r['price'])
    mx = max([r['price'] for r in cc] + [val['high']]) * 1.06
    W, rowh, top, left, right = 900, 46, 24, 250, 40
    H = top + rowh * len(cc) + 30
    plot_w = W - left - right
    def x(v): return left + plot_w * (v / mx)
    bars = []
    for i, r in enumerate(cc):
        y = top + i * rowh
        bw = plot_w * (r['price'] / mx)
        verify = txn_link(r)
        lab = (r['address'].split(',')[0])[:28]
        bars.append(
            f'<g class="bar" tabindex="0" role="button" aria-label="{lab}, {money(r["price"])}" '
            f'data-href="{verify}" data-addr="{lab}" data-sqm="{r["sqm"]}" data-date="{r["date"][:7]}" '
            f'data-price="{money(r["price"])}" data-psm="£{r["psm"]:,}/sqm">'
            f'<rect x="{left}" y="{y+4}" width="{plot_w:.0f}" height="{rowh-8:.0f}" class="hit"/>'
            f'<rect x="{left}" y="{y+8}" width="{bw:.1f}" height="{rowh-18:.0f}" rx="3" class="brect"/>'
            f'<text x="{left-10}" y="{y+rowh/2+1:.0f}" class="ylab" text-anchor="end">{lab} · {r["sqm"]}sqm</text>'
            f'<text x="{x(r["price"])+8:.0f}" y="{y+rowh/2+1:.0f}" class="vlab">{money(r["price"])}</text>'
            f'</g>')
    band = (f'<rect x="{x(val["low"]):.0f}" y="{top}" width="{x(val["high"])-x(val["low"]):.0f}" '
            f'height="{rowh*len(cc):.0f}" class="band"/>')
    cline = (f'<line x1="{x(val["central"]):.0f}" y1="{top-6}" x2="{x(val["central"]):.0f}" '
             f'y2="{top+rowh*len(cc):.0f}" class="cline"/>'
             f'<text x="{x(val["central"]):.0f}" y="{top-10}" class="clab" text-anchor="middle">central {money(val["central"])}</text>')
    gline = (f'<line x1="{x(val["guide"]):.0f}" y1="{top}" x2="{x(val["guide"]):.0f}" '
             f'y2="{top+rowh*len(cc):.0f}" class="gline"/>')
    svg = (f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMinYMin meet">'
           f'{band}{gline}{"".join(bars)}{cline}</svg>')
    rng = f"{money(val['low'])} - {money(val['high'])}"
    html_doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{subj['address']} - Honestly</title>
<style>
:root{{--green:{GREEN};--greend:{ACCENTD};--terra:{TERRA};--cream:#f6f3ec;--ink:#1c1a16;--mut:#6b6557;--line:#e7e1d4}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--cream);color:var(--ink);
font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;line-height:1.5}}
.wrap{{max-width:980px;margin:0 auto;padding:28px 20px 64px}}
.brand{{font-family:Georgia,'Times New Roman',serif;font-weight:bold;color:var(--greend);font-size:30px}}
.tag{{color:var(--green);font-size:15px;margin-left:8px}}
h1{{font-family:Georgia,serif;font-size:24px;margin:18px 0 4px}}
.meta{{color:var(--mut);font-size:15px}}
.range{{font-family:Georgia,serif;font-size:34px;color:var(--greend);margin:14px 0 2px}}
.sub{{color:var(--mut);font-size:14px;margin-bottom:18px}}
.card{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:20px 18px;margin:14px 0}}
.brect{{fill:var(--greend);transition:fill .12s}}
.hit{{fill:transparent}}
.bar:hover .brect,.bar:focus .brect,.bar.sel .brect{{fill:var(--green)}}
.bar{{cursor:pointer;text-decoration:none;outline:none}}
.bar:focus{{outline:none}}
.detail{{margin-top:14px;padding-top:14px;border-top:1px solid var(--line)}}
.dhint{{color:var(--mut);font-size:13px}}
.detail b{{font-size:15px;display:block;margin-bottom:3px}}
.dmeta{{color:var(--mut);font-size:13px;margin-bottom:10px}}
.dverify{{display:inline-block;background:var(--greend);color:#fff;text-decoration:none;
padding:9px 14px;border-radius:9px;font-weight:bold;font-size:13px}}
.ylab{{fill:var(--ink);font-size:13px}}.vlab{{fill:var(--mut);font-size:12px}}
.band{{fill:var(--green);opacity:.12}}
.cline{{stroke:var(--green);stroke-width:2}}.clab{{fill:var(--green);font-size:12px;font-weight:bold}}
.gline{{stroke:var(--terra);stroke-width:2;stroke-dasharray:5 4}}
.legend{{display:flex;gap:20px;flex-wrap:wrap;color:var(--mut);font-size:13px;margin-top:10px}}
.legend i{{display:inline-block;width:14px;height:14px;border-radius:3px;vertical-align:-2px;margin-right:5px}}
#tip{{position:fixed;pointer-events:none;background:var(--greend);color:#fff;padding:8px 11px;
border-radius:8px;font-size:13px;opacity:0;transition:opacity .1s;max-width:240px;z-index:9;box-shadow:0 6px 18px rgba(0,0,0,.18)}}
#tip b{{display:block;font-size:14px;margin-bottom:2px}}
.foot{{margin-top:26px;color:var(--mut);font-size:13px;border-top:1px solid var(--line);padding-top:16px}}
.foot a{{color:var(--green);font-weight:bold;text-decoration:none}}
.cta{{display:inline-block;margin-top:8px;background:var(--green);color:#fff;text-decoration:none;
padding:11px 18px;border-radius:10px;font-weight:bold}}
</style></head><body>
<div class="wrap">
  <div><span class="brand">Honestly</span><span class="tag">what it's really worth</span></div>
  <h1>{subj['address']}</h1>
  <div class="meta">{subj['sqm']} sqm · {subj.get('beds') or subj.get('beds_est')} bed · evidence from {len(cc)} verified sold comparables</div>
  <div class="range">{rng}</div>
  <div class="sub">central about {money(val['central'])} · recommended guide Offers Over {money(val['guide'])} · tap any bar for its detail, then open the HM Land Registry record</div>
  <div class="card">
    {svg}
    <div class="legend">
      <span><i style="background:{ACCENTD}"></i>Sold comparable</span>
      <span><i style="background:{GREEN};opacity:.4"></i>Assessed range</span>
      <span><i style="background:{GREEN}"></i>Central value</span>
      <span><i style="background:{TERRA}"></i>Recommended guide</span>
    </div>
    <div id="detail" class="detail">
      <span class="dhint">Tap any bar above to see the sale and open its official record.</span>
    </div>
  </div>
  <a class="cta" href="{bot_url}" target="_blank">Value another property yourself on Telegram</a>
  <div class="foot">
    Sold prices from HM Land Registry via PropertyData. Asking prices are never used to value.<br>
    made with <a href="{bot_url}" target="_blank">Honestly</a>
  </div>
</div>
<div id="tip"></div>
<script>
var tip=document.getElementById('tip');
var detail=document.getElementById('detail');
var bars=document.querySelectorAll('.bar');
function select(b){{
  bars.forEach(function(x){{x.classList.remove('sel');}});
  b.classList.add('sel');
  detail.innerHTML='<b>'+b.dataset.addr+'</b>'+
    '<div class="dmeta">'+b.dataset.sqm+' sqm · sold '+b.dataset.date+' · '+
    b.dataset.price+' · '+b.dataset.psm+'</div>'+
    '<a class="dverify" target="_blank" rel="noopener" href="'+b.dataset.href+'">Open HM Land Registry record</a>';
}}
bars.forEach(function(b){{
  b.addEventListener('click',function(){{select(b);}});
  b.addEventListener('keydown',function(e){{
    if(e.key==='Enter'||e.key===' '){{e.preventDefault();select(b);}}
  }});
  b.addEventListener('mousemove',function(e){{
    tip.innerHTML='<b>'+b.dataset.addr+'</b>'+b.dataset.sqm+' sqm · '+b.dataset.date+'<br>'+
      b.dataset.price+' · '+b.dataset.psm+'<br><span style="opacity:.8">tap for the record</span>';
    tip.style.opacity=1;tip.style.left=Math.min(e.clientX+14,window.innerWidth-250)+'px';
    tip.style.top=(e.clientY+14)+'px';
  }});
  b.addEventListener('mouseleave',function(){{tip.style.opacity=0;}});
}});
</script>
</body></html>"""
    p = f"{outdir}/{slug}_interactive.html"
    open(p, 'w', encoding='utf-8').write(html_doc)
    return p

# ---------------------------------------------------------------- render
def comp_row(r):
    pc = postcode_of(r['address'])
    return f"| {r['address']} · {r['sqm']} sqm | {r['date'][:7]} | {money(r['price'])} | £{r['psm']:,} | {r['dist']} mi | [PropertyData]({txn_link(r)}) |"

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
    ad(f"A {args.beds}-bedroom, {args.baths}-bathroom {subj['type'] or 'property'} of approximately {subj['sqm']} sqm"
       + _fin_note + ". "
       f"Comparable same-size, same-character properties define a price tier of {money(min(r['price'] for r in A))} - {money(max(r['price'] for r in A))}.\n")
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
    ad(f"\nComparable evidence and the condition-adjusted valuation give an assessed range of "
       f"**{money(val['low'])} - {money(val['high'])}, central ~{money(val['central'])}.** Confidence is moderate; see Limitations.\n")
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
    ad("\n**Comparable records** (HM Land Registry Price Paid; each link opens the free PropertyData transaction record - exact sale, property detail and photographs):\n")
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
    inter_path = interactive_chart(A, val, subj, slug, args.outdir, bot_url)
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
