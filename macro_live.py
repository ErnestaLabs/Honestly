#!/usr/bin/env python3
"""macro_live.py - LIVE macro momentum, fed from official UK statistics.

macro.py carries hand-checked, dated FACTS (Bank Rate, the next MPC date, SDLT).
This module adds the one thing a human can't keep current by hand: a live read of
where the macro drivers of house-price demand are *relative to their recent norm*.

It pulls three official series and turns them into a single, bounded momentum score:

  - 2-year fixed mortgage rate (Bank of England IADB, series IUMBV34)
        higher vs its norm  ->  weaker demand   (sign -)
  - real pay growth = AWE total pay - CPI       (ONS KAC3 minus ONS D7G7)
        higher vs its norm  ->  stronger budgets (sign +)
  - unemployment rate (ONS MGSX)
        higher vs its norm  ->  weaker demand   (sign -)

Each driver becomes a z-score against its own trailing window; the signed average
is Score_t. We translate that into a plain-English lean and a couple of sourced
lines. CRITICAL, same rule as macro.py: this NEVER moves the valuation figure. It
sits beside it. A z-score is a description of the weather, not a forecast of the
price - forecasting macro into the number would be the exact black-box guess this
product exists to replace. So we surface it as context, bounded and disclosed.

Offline-safe by design: signal() reads a local cache and returns instantly. It
refreshes from the network only when the cache is missing or stale, on a strict
time budget, and falls back to whatever it has (or None) if the fetch fails. A
valuation must never hang or break because a stats API was slow.

Sources (all free, no key):
  BoE IADB    https://www.bankofengland.co.uk/boeapps/database/
  ONS series  https://www.ons.gov.uk/.../timeseries/<cdid>/<dataset>/data
"""
import os, json, time, statistics, urllib.request, urllib.error
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "macro_live_cache.json")

WINDOW = 36            # trailing months the z-score is measured against
SMOOTH = 3             # latest reading = mean of the last N months (de-noise)
REFRESH_HOURS = 18     # read cache up to this old; refresh past it
FETCH_TIMEOUT = 6      # seconds per series; the whole refresh is best-effort
LEAN_BAND = 0.40       # |Score| below this reads as broadly balanced

_UA = {"User-Agent": "honestly-macro/1.0 (+https://t.me/usehonestly_bot)"}

# ---- ONS series: (cdid, dataset, topic_path). Website JSON mirror, not the dead
# api host. The topic path is NOT cosmetic - ONS resolves the series under it, so
# each series must sit under its correct theme or the request 404s.
ONS = {
    "cpi":  ("d7g7", "mm23", "economy/inflationandpriceindices"),                       # CPI annual rate, %
    "awe":  ("kac3", "lms",  "employmentandlabourmarket/peopleinwork/earningsandworkinghours"),  # AWE total pay yoy 3m, %
    "unemp":("mgsx", "lms",  "employmentandlabourmarket/peoplenotinwork/unemployment"), # unemployment rate 16+, SA, %
}


# ----------------------------------------------------------------- fetch layer
def _get(url, timeout=FETCH_TIMEOUT):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _boe_mortgage():
    """2yr fixed 75% LTV mortgage rate, monthly. Returns [(YYYY-MM, value), ...]."""
    d2 = date.today(); d1 = date(d2.year - 5, d2.month, 1)
    url = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
           "?csv.x=yes&Datefrom={f}&Dateto={t}&SeriesCodes=IUMBV34&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N"
           .format(f=d1.strftime("%d/%b/%Y"), t=d2.strftime("%d/%b/%Y")))
    out = []
    for ln in _get(url).splitlines()[1:]:          # skip 'DATE,IUMBV34'
        ln = ln.strip()
        if not ln or "," not in ln:
            continue
        d, _, v = ln.partition(",")
        try:
            dt = datetime.strptime(d.strip(), "%d %b %Y")
            out.append((dt.strftime("%Y-%m"), float(v)))
        except ValueError:
            continue
    return out


_MON = {m: i for i, m in enumerate(
    ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"], 1)}

def _ons(cdid, dataset, topic):
    """One ONS monthly series as [(YYYY-MM, value), ...]. `topic` is the theme path
    the series lives under (ONS requires it; it is not cosmetic)."""
    url = ("https://www.ons.gov.uk/{t}/timeseries/{c}/{d}/data"
           .format(t=topic, c=cdid, d=dataset))
    j = json.loads(_get(url))
    out = []
    for m in j.get("months", []):
        try:
            yr, mon = m["date"].split()
            out.append(("%s-%02d" % (yr, _MON[mon.upper()[:3]]), float(m["value"])))
        except (KeyError, ValueError):
            continue
    out.sort()
    return out


# ----------------------------------------------------------------- maths
def _z(series, window=WINDOW, smooth=SMOOTH):
    """Signed z-score of the latest (smoothed) reading vs its trailing window.
    Returns (z, latest, mean). None if there isn't enough history."""
    vals = [v for _, v in series][-window:]
    if len(vals) < 12:
        return None
    latest = statistics.fmean(vals[-smooth:]) if len(vals) >= smooth else vals[-1]
    mean = statistics.fmean(vals)
    sd = statistics.pstdev(vals)
    if sd == 0:
        return (0.0, latest, mean)
    return ((latest - mean) / sd, latest, mean)


def _align_real(awe, cpi):
    """Real pay growth series (AWE - CPI) over the months both cover."""
    c = dict(cpi)
    return [(k, v - c[k]) for k, v in awe if k in c]


def _round(x, n=2):
    return round(x, n)


# ----------------------------------------------------------------- compute
def _compute():
    """Pull all series and build the momentum payload. Raises on network failure."""
    mort = _boe_mortgage()
    cpi  = _ons(*ONS["cpi"])
    awe  = _ons(*ONS["awe"])
    unemp= _ons(*ONS["unemp"])
    real = _align_real(awe, cpi)

    zm = _z(mort)
    zr = _z(real)
    zu = _z(unemp)
    if not (zm and zr and zu):
        raise ValueError("insufficient macro history to score")

    # signed drivers: effect on house-price demand momentum
    drivers = [
        {"key": "mortgage", "label": "2-year fixed mortgage rate",
         "value": _round(zm[1]), "avg": _round(zm[2]), "z": _round(zm[0]), "sign": -1, "unit": "%"},
        {"key": "realpay",  "label": "real pay growth (pay minus inflation)",
         "value": _round(zr[1]), "avg": _round(zr[2]), "z": _round(zr[0]), "sign": +1, "unit": "%"},
        {"key": "unemp",    "label": "unemployment rate",
         "value": _round(zu[1]), "avg": _round(zu[2]), "z": _round(zu[0]), "sign": -1, "unit": "%"},
    ]
    score = statistics.fmean(d["sign"] * d["z"] for d in drivers)
    score = max(-2.0, min(2.0, score))                  # bounded, like everything here

    if score >= LEAN_BAND:
        lean, word = "supportive", "leaning supportive"
    elif score <= -LEAN_BAND:
        lean, word = "soft", "leaning soft"
    else:
        lean, word = "balanced", "broadly balanced"

    headline = (f"Live macro momentum is {word} for prices "
                f"(score {score:+.2f} on a -2 to +2 scale).")

    lines = [headline, _mortgage_line(zm), _realpay_line(zr, awe, cpi), _unemp_line(zu)]
    lines.append("These are demand conditions over the next 6 to 12 months. They sit "
                 "beside the figure, not inside it - the number is built from sold evidence.")

    return {
        "as_of": date.today().isoformat(),
        "fetched_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "score": _round(score),
        "lean": lean,
        "headline": headline,
        "drivers": drivers,
        "lines": lines,
        "sources": {
            "mortgage": "Bank of England IADB IUMBV34",
            "cpi": "ONS D7G7", "awe": "ONS KAC3", "unemployment": "ONS MGSX",
        },
    }


def _dir(latest, mean, eps=0.05):
    if latest > mean + eps:   return "above"
    if latest < mean - eps:   return "below"
    return "in line with"


def _mortgage_line(z):
    v, m = z[1], z[2]
    return (f"2-year fixed mortgage rate is {v:.2f}%, {_dir(v, m)} its 3-year average of "
            f"{m:.2f}% - {'a drag on' if v > m + 0.05 else 'supportive of'} affordability.")


def _realpay_line(z, awe, cpi):
    rp = z[1]
    aw = awe[-1][1] if awe else None
    cp = cpi[-1][1] if cpi else None
    base = f"Real pay growth is about {rp:+.1f}%"
    if aw is not None and cp is not None:
        base += f" (pay {aw:.1f}% against {cp:.1f}% inflation)"
    base += "; " + ("rising real incomes lift buyer budgets." if rp > 0
                    else "incomes are not keeping pace with prices, which squeezes budgets.")
    return base


def _unemp_line(z):
    v, m = z[1], z[2]
    if v > m + 0.05:
        tail = "a softening labour market that takes some support away from demand."
    else:
        tail = "a firm labour market that underpins demand."
    return f"Unemployment is {v:.1f}%, {_dir(v, m)} its 3-year average of {m:.1f}% - {tail}"


# ----------------------------------------------------------------- cache + public API
def _read_cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(payload):
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"saved": time.time(), "payload": payload}, f, indent=2)
    os.replace(tmp, CACHE)


def _age_hours(cache):
    return (time.time() - cache.get("saved", 0)) / 3600.0 if cache else 1e9


def refresh():
    """Fetch + compute + cache. Returns the payload, or None on failure (cache kept)."""
    try:
        payload = _compute()
        _write_cache(payload)
        return payload
    except (urllib.error.URLError, ValueError, OSError, json.JSONDecodeError):
        return None


def signal():
    """The live macro-momentum block for a valuation, or None if unavailable.
    Offline-safe: serves cache instantly; refreshes only when stale, best-effort."""
    cache = _read_cache()
    if cache and _age_hours(cache) < REFRESH_HOURS:
        return cache.get("payload")
    fresh = refresh()                       # cache missing or stale -> try once
    if fresh:
        return fresh
    return cache.get("payload") if cache else None   # fall back to stale, else nothing


if __name__ == "__main__":
    import sys
    if "--refresh" in sys.argv:
        p = refresh()
        print("refreshed" if p else "refresh FAILED (kept cache)")
        if p: print(json.dumps(p, indent=2))
    else:
        print(json.dumps(signal(), indent=2))
