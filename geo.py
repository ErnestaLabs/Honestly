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
import os, sys, json, urllib.parse, urllib.request, urllib.error

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


def nearest(postcode, limit=10):
    """The nearest postcodes to a given one, closest first, with metre distances.
    The first entry is usually the postcode itself (distance 0). Returns
    {ok, postcode, neighbours:[{postcode, dist_m, lat, lng}, ...]} or
    {ok: False, reason}. Never raises."""
    pc = _norm_pc(postcode)
    if not pc:
        return {"ok": False, "reason": "no postcode given"}
    path = f"/postcodes/{urllib.parse.quote(pc)}/nearest?limit={int(limit)}"
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


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "lookup":
        print(json.dumps(lookup(sys.argv[2]), indent=2, ensure_ascii=False))
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
