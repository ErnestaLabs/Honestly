#!/usr/bin/env python3
"""overpass.py - nearby amenities & transport via OSM Overpass (keyless, ODbL).

Area context that sits BESIDE the figure - never an input to the valuation. Given a
lat/lng it counts the amenities and transport nodes near the property and lists the
closest named transport stops. Best-effort: every call degrades to {'ok': False,
'reason': ...} and never raises.

Self-host first: the plan stands up `drolbr/Overpass-API` (GB extract) on the VPS, so
this points at $OVERPASS_BASE when set and falls back to the public overpass-api.de
endpoint - the same best-effort posture as geo.py / macro_live.

Source: OpenStreetMap contributors (ODbL), queried via the Overpass API.

Surfaces:
  amenities(lat, lng, radius_m=800) -> {ok, counts:{...}, transport:[...], lines:[...]}

CLI:
  python overpass.py amenities 51.519 -0.093
  python overpass.py selftest
"""
import os, sys, json, math, urllib.parse, urllib.request, urllib.error

PUBLIC = "https://overpass-api.de/api/interpreter"
_UA = {"User-Agent": "honestly-overpass/1.0 (+https://t.me/usehonestly_bot)"}
_SRC = "OpenStreetMap contributors (ODbL), via the Overpass API"

# amenity/leisure/shop tags we surface, grouped into human buckets
_BUCKETS = {
    "Stations": ('node["railway"="station"]', 'node["station"="subway"]',
                 'node["railway"="tram_stop"]'),
    "Bus stops": ('node["highway"="bus_stop"]',),
    "Schools": ('node["amenity"="school"]', 'way["amenity"="school"]'),
    "Supermarkets": ('node["shop"="supermarket"]', 'way["shop"="supermarket"]'),
    "Cafes & restaurants": ('node["amenity"~"cafe|restaurant"]',),
    "Green space": ('way["leisure"="park"]', 'node["leisure"="park"]'),
    "GP & pharmacy": ('node["amenity"~"doctors|pharmacy|clinic"]',),
}


def _bases():
    local = os.environ.get("OVERPASS_BASE")
    return ([local.rstrip("/")] if local else []) + [PUBLIC]


def _haversine_m(lat1, lng1, lat2, lng2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _run(ql, timeout=40):
    last = None
    data = urllib.parse.urlencode({"data": ql}).encode()
    for base in _bases():
        try:
            req = urllib.request.Request(base, data=data,
                                         headers={"Accept": "application/json", **_UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last = e
    raise last if last else RuntimeError("no overpass base")


def amenities(lat, lng, radius_m=800):
    """Count amenities within radius_m and list the nearest named transport stops.
    Returns {ok, counts, transport, lines} or {ok: False, reason}. Never raises."""
    if lat is None or lng is None:
        return {"ok": False, "reason": "no coordinates"}
    parts = []
    for queries in _BUCKETS.values():
        for q in queries:
            parts.append(f'{q}(around:{int(radius_m)},{lat},{lng});')
    ql = f"[out:json][timeout:40];({''.join(parts)});out center tags;"
    try:
        d = _run(ql)
    except urllib.error.HTTPError as e:
        return {"ok": False, "reason": f"Overpass HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    els = d.get("elements") or []
    counts = {k: 0 for k in _BUCKETS}
    transport = []
    for el in els:
        tags = el.get("tags") or {}
        elat = el.get("lat") or (el.get("center") or {}).get("lat")
        elng = el.get("lon") or (el.get("center") or {}).get("lon")
        # classify into a bucket by tag
        if tags.get("railway") in ("station", "tram_stop") or tags.get("station") == "subway":
            counts["Stations"] += 1
            if tags.get("name") and elat and elng:
                transport.append({"name": tags["name"], "kind": "station",
                                  "dist_m": round(_haversine_m(lat, lng, elat, elng))})
        elif tags.get("highway") == "bus_stop":
            counts["Bus stops"] += 1
        elif tags.get("amenity") == "school":
            counts["Schools"] += 1
        elif tags.get("shop") == "supermarket":
            counts["Supermarkets"] += 1
        elif tags.get("amenity") in ("cafe", "restaurant"):
            counts["Cafes & restaurants"] += 1
        elif tags.get("leisure") == "park":
            counts["Green space"] += 1
        elif tags.get("amenity") in ("doctors", "pharmacy", "clinic"):
            counts["GP & pharmacy"] += 1
    transport = sorted(transport, key=lambda t: t["dist_m"])[:6]
    lines = []
    if counts.get("Stations"):
        nearest = transport[0] if transport else None
        if nearest:
            lines.append(f"Nearest station: {nearest['name']} (~{nearest['dist_m']} m).")
    top = "; ".join(f"{k}: {v}" for k, v in counts.items() if v)
    if top:
        lines.append(f"Within {radius_m} m - {top}.")
    if not any(counts.values()):
        lines.append(f"No mapped amenities found within {radius_m} m.")
    return {"ok": True, "counts": counts, "transport": transport, "radius_m": radius_m,
            "lines": lines, "source": _SRC}


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    if sys.argv[1] == "amenities":
        print(json.dumps(amenities(float(sys.argv[2]), float(sys.argv[3])), indent=2, ensure_ascii=False))
    elif sys.argv[1] == "selftest":
        a = amenities(51.5194, -0.0935)  # Barbican area
        if a.get("ok"):
            print("overpass ok | counts", a["counts"], "| transport", len(a["transport"]))
        else:
            print("overpass degraded:", a.get("reason"))
    else:
        print("unknown command:", sys.argv[1])


if __name__ == "__main__":
    main()
