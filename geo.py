#!/usr/bin/env python3
"""geo.py - postcode geography via Postcodes.io (keyless, OGL/MIT).

Resolves a UK postcode to lat/lng + admin areas, and lists the nearest postcodes
to it. Used to normalise an address before any paid provider call and to build the
"nearby areas" set the demand read compares against.

Self-host first: the plan stands up `ideal-postcodes/postcodes.io` on the VPS, so
this points at http://localhost:8000 when GEO_BASE is set, and falls back to the
public api.postcodes.io if the local service is down - the same best-effort posture
as macro_live. Every call degrades to {'ok': False, 'reason': ...} instead of
raising, so the engine keeps working if the endpoint is slow or down.

Surfaces:
  lookup(postcode)          -> {ok, postcode, lat, lng, district, ward, region, ...}
  nearest(postcode, limit)  -> {ok, postcode, neighbours:[{postcode, dist_m}, ...]}

CLI:
  python geo.py lookup "SE15 6JH"
  python geo.py nearest "SE15 6JH" 10
  python geo.py selftest
"""
import os, sys, json, math, urllib.parse, urllib.request, urllib.error

PUBLIC = "https://api.postcodes.io"
_UA = {"User-Agent": "honestly-geo/1.0 (+https://t.me/usehonestly_bot)"}


def _bases():
    """Local self-host first (if GEO_BASE set), then the public endpoint. The
    public endpoint is always included as a fallback so a down VPS service never
    blocks a valuation."""
    local = os.environ.get("GEO_BASE")
    return ([local.rstrip("/")] if local else []) + [PUBLIC]


def _get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"Accept": "application/json", **_UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _norm_pc(postcode):
    """Trim only - Postcodes.io is space/case tolerant on the path segment."""
    return (postcode or "").strip()


def _fetch(path, timeout=15):
    """Try each base in order; return the first JSON body or raise the last error."""
    last = None
    for base in _bases():
        try:
            return _get_json(f"{base}{path}", timeout=timeout)
        except Exception as e:                  # try the next base (local -> public)
            last = e
    raise last if last else RuntimeError("no geo base configured")


def lookup(postcode):
    """Resolve a postcode to coordinates and admin areas. {ok: False, reason} if the
    postcode is unknown or the service is unreachable. Never raises."""
    pc = _norm_pc(postcode)
    if not pc:
        return {"ok": False, "reason": "no postcode given"}
    path = f"/postcodes/{urllib.parse.quote(pc)}"
    try:
        d = _fetch(path)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"ok": False, "reason": f"postcode not found: {pc}"}
        return {"ok": False, "reason": f"Postcodes.io HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    res = d.get("result") or {}
    if not res.get("postcode"):
        return {"ok": False, "reason": f"no record for {pc}"}
    return {
        "ok": True, "postcode": res.get("postcode"),
        "lat": res.get("latitude"), "lng": res.get("longitude"),
        "district": res.get("admin_district"), "ward": res.get("admin_ward"),
        "region": res.get("region"), "country": res.get("country"),
        "outcode": res.get("outcode"),
        "source": "Postcodes.io (ONS/OS open data, OGL)",
    }


def nearest(postcode, limit=10, radius=None):
    """The nearest postcodes to a given one, closest first, with metre distances.
    The first entry is usually the postcode itself (distance 0). `radius` (metres, max
    2000) widens the search beyond Postcodes.io's small default ring - needed to reach a
    whole postcode sector, not just the closest handful. Returns
    {ok, postcode, neighbours:[{postcode, dist_m, lat, lng}, ...]} or
    {ok: False, reason}. Never raises."""
    pc = _norm_pc(postcode)
    if not pc:
        return {"ok": False, "reason": "no postcode given"}
    path = f"/postcodes/{urllib.parse.quote(pc)}/nearest?limit={int(limit)}"
    if radius:
        path += f"&radius={int(radius)}"
    try:
        d = _fetch(path)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"ok": False, "reason": f"postcode not found: {pc}"}
        return {"ok": False, "reason": f"Postcodes.io HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    rows = d.get("result") or []
    neighbours = []
    for r in rows:
        p = r.get("postcode")
        if not p:
            continue
        neighbours.append({
            "postcode": p,
            "dist_m": round(r["distance"]) if r.get("distance") is not None else None,
            "lat": r.get("latitude"), "lng": r.get("longitude"),
        })
    if not neighbours:
        return {"ok": False, "reason": f"no nearby postcodes for {pc}"}
    return {"ok": True, "postcode": neighbours[0]["postcode"],
            "neighbours": neighbours,
            "source": "Postcodes.io (ONS/OS open data, OGL)"}


def outcode(code):
    """Resolve a postcode DISTRICT (outcode, e.g. 'SE15') to its centroid and admin
    areas via Postcodes.io's /outcodes endpoint. Used by the daily district blog,
    which works at outcode granularity (no single subject property). Admin fields come
    back as lists for an outcode (a district can span several wards/boroughs), so we
    keep the first of each as the primary label. {ok: False, reason} on miss. Never
    raises. HPI/geography only - never an input to any valuation."""
    oc = (code or "").strip().upper()
    if not oc:
        return {"ok": False, "reason": "no outcode given"}
    path = f"/outcodes/{urllib.parse.quote(oc)}"
    try:
        d = _fetch(path)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"ok": False, "reason": f"outcode not found: {oc}"}
        return {"ok": False, "reason": f"Postcodes.io HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    res = d.get("result") or {}
    if not res.get("outcode"):
        return {"ok": False, "reason": f"no record for {oc}"}

    def _first(v):
        return v[0] if isinstance(v, list) and v else (v or None)

    return {
        "ok": True, "outcode": res.get("outcode"),
        "lat": res.get("latitude"), "lng": res.get("longitude"),
        "district": _first(res.get("admin_district")),
        "ward": _first(res.get("admin_ward")),
        "region": _first(res.get("region")),
        "country": _first(res.get("country")),
        "districts": res.get("admin_district") or [],
        "source": "Postcodes.io (ONS/OS open data, OGL)",
    }


def reverse(lat, lng, limit=5, radius=None, timeout=15):
    """Nearest live postcodes to a coordinate (Postcodes.io reverse geocode), closest
    first. `radius` (metres, max 2000) widens the search beyond the small default ring -
    needed to sweep a whole central district. Returns {ok, postcodes:[...]} or
    {ok: False, reason}. Never raises."""
    if lat is None or lng is None:
        return {"ok": False, "reason": "no coordinate given"}
    path = f"/postcodes?lon={float(lng)}&lat={float(lat)}&limit={int(limit)}"
    if radius:
        path += f"&radius={int(radius)}"
    try:
        d = _fetch(path, timeout=timeout)
    except urllib.error.HTTPError as e:
        return {"ok": False, "reason": f"Postcodes.io HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    rows = d.get("result") or []
    pcs = [r.get("postcode") for r in rows if r.get("postcode")]
    if not pcs:
        return {"ok": False, "reason": "no postcode at this coordinate"}
    return {"ok": True, "postcodes": pcs,
            "source": "Postcodes.io (ONS/OS open data, OGL)"}


def _ring_points(lat, lng, metres, n=8):
    """`n` points evenly spaced on a circle of `metres` radius about (lat, lng), N first
    then clockwise. Metres-to-degrees uses a flat-earth step (fine at city scale)."""
    dlat = metres / 111320.0
    dlng = metres / (111320.0 * max(0.2, math.cos(math.radians(lat))))
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        pts.append((lat + dlat * math.cos(a), lng + dlng * math.sin(a)))
    return pts


def outcode_postcodes(code, radius=2000, limit=100, timeout=15):
    """Enumerate the live member postcodes of a postcode DISTRICT (outcode).

    Postcodes.io's stored outcode centroid is sometimes geographically WRONG for tight
    central districts - B2's sits ~1.1km north of the real B2, inside B4/B19 - and a dense
    city centre crowds the true members out of a single reverse-ring (100 nearer B4/B19
    postcodes fill the limit before any B2 appears). So this scans outward from the centroid
    - the centroid itself, then rings at 1.1km and 2km - reverse-geocoding each point until
    one returns postcodes whose outcode matches the target, then densifies around that
    verified member's own coordinate to gather the full member set. Robust to a mislocated
    centroid, not just to the normal case. Returns {ok, outcode, postcodes:[...]} or
    {ok: False, reason}. Never raises.

    IMPORTANT: ok:False here means enumeration FAILED (retryable) - never that the district
    is empty. The free HMLR sold-fallback treats it as an outage, never as confirmed absence,
    so a transient geo miss can never be published as 'no sold data'."""
    oc = (code or "").strip().upper()
    if not oc:
        return {"ok": False, "reason": "no outcode given"}
    o = outcode(oc)
    if not o.get("ok") or o.get("lat") is None:
        return {"ok": False, "reason": o.get("reason", f"no centroid for {oc}")}
    clat, clng = o["lat"], o["lng"]

    def _members_at(lat, lng, r):
        rev = reverse(lat, lng, limit=limit, radius=r, timeout=timeout)
        if not rev.get("ok"):
            return []
        return [p for p in rev["postcodes"] if (p or "").split()[0].upper() == oc]

    members = set()
    cluster = None
    # scan outward until a point actually sees the target outcode - this is what survives a
    # centroid that lands in a neighbouring district.
    scan = [(clat, clng)] + _ring_points(clat, clng, 1100) + _ring_points(clat, clng, 2000)
    for (lat, lng) in scan:
        hit = _members_at(lat, lng, radius)
        if hit:
            members.update(hit)
            seed = lookup(hit[0])            # densify around a verified member's coordinate
            cluster = (seed["lat"], seed["lng"]) if seed.get("ok") and seed.get("lat") is not None \
                else (lat, lng)
            break
    if cluster is None:
        return {"ok": False, "reason": f"could not locate {oc} near its centroid"}
    # a tighter ring at the cluster centre maximises true members before neighbours crowd in
    members.update(_members_at(cluster[0], cluster[1], min(int(radius), 1200)))
    out = sorted(members)
    if not out:
        return {"ok": False, "reason": f"no member postcodes resolved for {oc}"}
    return {"ok": True, "outcode": oc, "postcodes": out,
            "source": "Postcodes.io (ONS/OS open data, OGL)"}


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "lookup":
        print(json.dumps(lookup(sys.argv[2]), indent=2, ensure_ascii=False))
    elif cmd == "outcode":
        print(json.dumps(outcode(sys.argv[2]), indent=2, ensure_ascii=False))
    elif cmd == "nearest":
        lim = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        print(json.dumps(nearest(sys.argv[2], lim), indent=2, ensure_ascii=False))
    elif cmd == "selftest":
        l = lookup("SE15 6JH")
        print("lookup SE15 6JH :", "ok" if l.get("ok") else l.get("reason"),
              "|", l.get("district"), "| lat", l.get("lat"))
        n = nearest("SE15 6JH", 8)
        print("nearest SE15 6JH:", "ok" if n.get("ok") else n.get("reason"),
              "| neighbours", len(n.get("neighbours", [])) if n.get("ok") else 0)
    else:
        print("unknown command:", cmd); print(__doc__)


if __name__ == "__main__":
    main()
