#!/usr/bin/env python3
"""maps_tools.py - server-side Google Maps Platform helpers for the appraisal engine.

The API key is read from the environment (GOOGLE_MAPS_API_KEY) or the local .env
and NEVER returned to a client. Every call degrades gracefully: if an API is not
yet enabled on the project it returns a structured {'ok': False, 'reason': ...}
instead of raising, so the engine keeps working while APIs are switched on.

MVP surface (nothing else):
  geocode(address)            -> lat/lng + formatted address      [Geocoding API]
  street_view(location, out)  -> frontage photo (or 'none')       [Street View Static + free metadata]
  static_map(out, ...)        -> map/route image for the PDF      [Maps Static API]
  route(stops, optimize=True) -> optimised door-knock order       [Routes API]   (LIVE)
  places_search(query)        -> address lookup                   [Places API (New)] (LIVE)

CLI:
  python maps_tools.py geocode "58 Cronin Street, London SE15 6JH"
  python maps_tools.py streetview "58 Cronin Street, London SE15 6JH" frontage.jpg
  python maps_tools.py staticmap map.png --center "51.4732,-0.0712" --zoom 15
  python maps_tools.py route "SE15 6JH" "SE15 5LE" "SE15 6HB" "SE15 5FA"
  python maps_tools.py places "Cronin Street Peckham"
  python maps_tools.py selftest
"""
import os, sys, json, urllib.parse, urllib.request, urllib.error

GEO = "https://maps.googleapis.com/maps/api"
ROUTES = "https://routes.googleapis.com/directions/v2:computeRoutes"
PLACES = "https://places.googleapis.com/v1/places:searchText"
ADDR_VALIDATE = "https://addressvalidation.googleapis.com/v1:validateAddress"
_MARK = "0x15807f"   # brand green for map markers/route lines

def _load_env():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(here):
        with open(here, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

def key():
    _load_env()
    k = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not k:
        sys.exit("GOOGLE_MAPS_API_KEY not set (env or .env)")
    return k

def _get_json(url):
    try:
        with urllib.request.urlopen(url, timeout=25) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read().decode("utf-8", "ignore"))
        except Exception: return {"status": f"HTTP_{e.code}"}
    except Exception as e:
        return {"status": "ERROR", "error_message": str(e)[:120]}

def _post_json(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read().decode("utf-8", "ignore"))
        except Exception: return {"error": {"code": e.code}}
    except Exception as e:
        return {"error": {"message": str(e)[:120]}}

def _not_activated(d):
    msg = json.dumps(d)
    return "not activated" in msg or "REQUEST_DENIED" in msg

# ---------------------------------------------------------------- Geocoding
def geocode(address):
    d = _get_json(f"{GEO}/geocode/json?" + urllib.parse.urlencode({"address": address, "key": key()}))
    st = d.get("status")
    if st == "OK":
        r = d["results"][0]; loc = r["geometry"]["location"]
        return {"ok": True, "lat": loc["lat"], "lng": loc["lng"],
                "formatted": r["formatted_address"], "place_id": r["place_id"]}
    return {"ok": False, "reason": "Geocoding API not enabled" if _not_activated(d) else (d.get("error_message") or st),
            "status": st}

# ---------------------------------------------------------------- Street View
def street_view_available(location, source="outdoor"):
    """FREE metadata check - does Street View imagery exist for this address? Implements
    the 'no photograph available -> say so' rule without paying for an image.

    source defaults to 'outdoor', which restricts to the official Google Street View car
    collection and EXCLUDES user/business-contributed indoor photo spheres - so a request at
    a commercial centroid can never come back as the inside of a furniture showroom. We also
    surface the pano's copyright so the caller can reject anything that is not Google's."""
    q = {"location": location, "key": key()}
    if source:
        q["source"] = source
    d = _get_json(f"{GEO}/streetview/metadata?" + urllib.parse.urlencode(q))
    st = d.get("status")
    if st == "OK":
        return {"ok": True, "available": True, "date": d.get("date"),
                "pano_id": d.get("pano_id"), "copyright": d.get("copyright", "")}
    if st == "ZERO_RESULTS":
        return {"ok": True, "available": False}
    return {"ok": False, "reason": "Street View Static API not enabled" if _not_activated(d) else st, "status": st}

def street_view(location, out, size="640x400", fov=80, heading=None, pitch=10, source="outdoor"):
    meta = street_view_available(location, source=source)
    if not meta.get("ok"):
        return {"ok": False, "reason": meta["reason"]}
    if not meta["available"]:
        return {"ok": True, "available": False, "note": "No Street View imagery for this address"}
    # belt-and-braces: even with source=outdoor, refuse any panorama not attributed to Google
    # (a third-party credit means a contributed photo sphere, not the roadside car).
    cr = (meta.get("copyright") or "")
    if cr and "google" not in cr.lower():
        return {"ok": True, "available": False,
                "note": f"nearest panorama is third-party imagery ({cr.strip()}), not roadside Street View"}
    p = {"location": location, "size": size, "fov": fov, "pitch": pitch, "key": key()}
    if source: p["source"] = source
    if heading is not None: p["heading"] = heading
    url = f"{GEO}/streetview?" + urllib.parse.urlencode(p)
    try:
        with urllib.request.urlopen(url, timeout=25) as r:
            data = r.read()
        if not r.headers.get("Content-Type", "").startswith("image"):
            return {"ok": False, "reason": "non-image response (API not enabled?)"}
        open(out, "wb").write(data)
        return {"ok": True, "available": True, "path": out, "bytes": len(data), "date": meta.get("date")}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}

# ---------------------------------------------------------------- Static map
def static_map(out, center=None, zoom=15, size="640x400", markers=None, path=None, maptype="roadmap"):
    p = [("size", size), ("maptype", maptype), ("key", key()), ("scale", "2")]
    if center: p.append(("center", center)); p.append(("zoom", str(zoom)))
    for i, m in enumerate(markers or []):
        label = chr(65 + i) if i < 26 else ""
        p.append(("markers", f"color:{_MARK}|label:{label}|{m}"))
    if path:  # encoded or pipe-joined lat,lng list -> a route line
        p.append(("path", f"weight:4|color:{_MARK}ff|{path}"))
    url = f"{GEO}/staticmap?" + urllib.parse.urlencode(p)
    try:
        with urllib.request.urlopen(url, timeout=25) as r:
            data = r.read()
        if not r.headers.get("Content-Type", "").startswith("image"):
            return {"ok": False, "reason": "Maps Static API not enabled"}
        open(out, "wb").write(data)
        return {"ok": True, "path": out, "bytes": len(data)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "reason": "Maps Static API not enabled" if e.code == 403 else f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}

# ---------------------------------------------------------------- Routes (LIVE)
def route(stops, optimize=True, mode="DRIVE"):
    """Optimised multi-stop order for door-knocking. stops = list of address strings;
    first is origin, last is destination, the middle are reordered for the shortest run."""
    if len(stops) < 2:
        return {"ok": False, "reason": "need >=2 stops"}
    body = {"origin": {"address": stops[0]}, "destination": {"address": stops[-1]},
            "travelMode": mode}
    inter = stops[1:-1]
    if inter:
        body["intermediates"] = [{"address": a} for a in inter]
        body["optimizeWaypointOrder"] = bool(optimize)
    fields = "routes.distanceMeters,routes.duration,routes.optimizedIntermediateWaypointIndex,routes.polyline.encodedPolyline"
    d = _post_json(ROUTES, body, {"X-Goog-Api-Key": key(), "X-Goog-FieldMask": fields})
    if "routes" not in d:
        return {"ok": False, "reason": d.get("error", {}).get("message", "no route")[:140]}
    r = d["routes"][0]
    order = r.get("optimizedIntermediateWaypointIndex")
    ordered = stops
    if order is not None:
        ordered = [stops[0]] + [inter[i] for i in order] + [stops[-1]]
    km = r.get("distanceMeters", 0) / 1000
    dur = r.get("duration", "0s")
    return {"ok": True, "ordered_stops": ordered, "km": round(km, 2), "duration": dur,
            "polyline": r.get("polyline", {}).get("encodedPolyline")}

# ---------------------------------------------------------------- Shareable map links (KEYLESS)
# These build standard Google Maps URLs that open the real, interactive Google Maps
# app/site for the user. They take NO API key and MUST NOT - the key is unrestricted
# and server-side only; it never crosses into anything a user can see. Spec:
# https://developers.google.com/maps/documentation/urls/get-started
def _stop(s):
    """Normalise a stop to a URL-safe token: prefer 'lat,lng', else the address string."""
    if isinstance(s, (tuple, list)) and len(s) == 2:
        return f"{s[0]},{s[1]}"
    return str(s).strip()

def directions_url(stops, mode="walking"):
    """A real, tappable Google Maps directions link through the given stops, in order.
    stops = list of 'lat,lng' strings, (lat,lng) tuples, or address strings; first is the
    origin, last the destination, the rest are waypoints. Opens live Google Maps with a
    pannable, zoomable route the user can navigate. KEYLESS by design. The keyless URL
    scheme caps waypoints at 9, so we keep at most 11 stops (origin + 9 + destination)."""
    pts = [_stop(s) for s in stops if _stop(s)]
    if len(pts) < 2:
        if not pts:
            return None
        return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(pts[0])
    if len(pts) > 11:                       # origin + 9 waypoints + destination
        pts = pts[:10] + [pts[-1]]
    origin, destination, waypoints = pts[0], pts[-1], pts[1:-1]
    q = {"api": "1", "origin": origin, "destination": destination, "travelmode": mode}
    if waypoints:
        q["waypoints"] = "|".join(waypoints)
    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(q, safe="|,")

# ---------------------------------------------------------------- Places (LIVE)
def places_search(query):
    d = _post_json(PLACES, {"textQuery": query},
                   {"X-Goog-Api-Key": key(),
                    "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.id"})
    if "places" not in d:
        return {"ok": False, "reason": d.get("error", {}).get("message", "no places")[:140]}
    return {"ok": True, "results": [
        {"name": p.get("displayName", {}).get("text"), "address": p.get("formattedAddress"),
         "lat": p.get("location", {}).get("latitude"), "lng": p.get("location", {}).get("longitude"),
         "place_id": p.get("id")} for p in d["places"][:5]]}

# ---------------------------------------------------------------- Distance Matrix (LIVE)
def distance_matrix(origin, destinations, mode="transit"):
    """Travel time + distance from one origin to each destination. origin and each
    destination is a 'lat,lng' string or an address. mode is transit|walking|driving|
    bicycling. Returns {ok, mode, legs:[{to, text, seconds, metres}, ...]} or
    {ok: False, reason}. Context only - never an input to the figure. Never raises."""
    if not origin or not destinations:
        return {"ok": False, "reason": "need an origin and >=1 destination"}
    dests = destinations if isinstance(destinations, (list, tuple)) else [destinations]
    p = {"origins": origin, "destinations": "|".join(str(x) for x in dests),
         "mode": mode, "units": "metric", "key": key()}
    d = _get_json(f"{GEO}/distancematrix/json?" + urllib.parse.urlencode(p))
    st = d.get("status")
    if st != "OK":
        return {"ok": False, "reason": "Distance Matrix API not enabled" if _not_activated(d)
                else (d.get("error_message") or st), "status": st}
    row = (d.get("rows") or [{}])[0].get("elements", [])
    legs = []
    for to, el in zip(dests, row):
        if el.get("status") != "OK":
            legs.append({"to": str(to), "text": None, "seconds": None, "metres": None,
                         "status": el.get("status")})
            continue
        legs.append({"to": str(to),
                     "text": el.get("duration", {}).get("text"),
                     "seconds": el.get("duration", {}).get("value"),
                     "metres": el.get("distance", {}).get("value"),
                     "dist_text": el.get("distance", {}).get("text")})
    return {"ok": True, "mode": mode, "legs": legs,
            "source": "Google Distance Matrix API"}

# ---------------------------------------------------------------- Address Validation (LIVE)
def validate_address(address, region="GB"):
    """Verify and normalise a subject address before paid provider calls. Returns
    {ok, formatted, complete, has_unconfirmed, postcode, components_note, source} or
    {ok: False, reason}. Context/provenance only. Never raises."""
    if not address:
        return {"ok": False, "reason": "no address"}
    lines = address if isinstance(address, (list, tuple)) else [address]
    body = {"address": {"regionCode": region, "addressLines": list(lines)}}
    d = _post_json(f"{ADDR_VALIDATE}?key={urllib.parse.quote(key())}", body, {})
    if "result" not in d:
        msg = d.get("error", {}).get("message", "")
        return {"ok": False, "reason": "Address Validation API not enabled"
                if ("not" in msg and "enabl" in msg) or "PERMISSION" in json.dumps(d)
                else (msg or "no result")[:140]}
    res = d["result"]
    addr = res.get("address", {})
    verdict = res.get("verdict", {})
    postal = (res.get("address", {}).get("postalAddress", {}) or {})
    return {"ok": True,
            "formatted": addr.get("formattedAddress"),
            "complete": bool(verdict.get("addressComplete")),
            "has_unconfirmed": bool(verdict.get("hasUnconfirmedComponents")),
            "has_inferred": bool(verdict.get("hasInferredComponents")),
            "postcode": postal.get("postalCode"),
            "components_note": ("Some components were unconfirmed"
                                if verdict.get("hasUnconfirmedComponents")
                                else "All components confirmed"),
            "source": "Google Address Validation API"}

# ---------------------------------------------------------------- CLI
def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "geocode":
        print(json.dumps(geocode(sys.argv[2]), indent=2))
    elif cmd == "streetview":
        print(json.dumps(street_view(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "frontage.jpg"), indent=2))
    elif cmd == "staticmap":
        kw = dict(zip(sys.argv[3::2], sys.argv[4::2])) if len(sys.argv) > 3 else {}
        print(json.dumps(static_map(sys.argv[2], center=kw.get("--center"),
              zoom=int(kw.get("--zoom", 15))), indent=2))
    elif cmd == "route":
        print(json.dumps(route(sys.argv[2:]), indent=2))
    elif cmd == "places":
        print(json.dumps(places_search(sys.argv[2]), indent=2))
    elif cmd == "distance":
        print(json.dumps(distance_matrix(sys.argv[2], sys.argv[3:]), indent=2))
    elif cmd == "validate":
        print(json.dumps(validate_address(sys.argv[2]), indent=2))
    elif cmd == "selftest":
        print("Geocoding   :", geocode("SE15 6JH"))
        print("StreetViewMD:", street_view_available("58 Cronin Street, London SE15 6JH"))
        print("StaticMap   :", static_map("_selftest_map.png", center="51.4732,-0.0712"))
        print("Route       :", route(["SE15 6JH", "SE15 5LE", "SE15 6HB", "SE15 5FA"]))
        print("Places      :", places_search("Cronin Street Peckham"))
        print("Distance    :", distance_matrix("51.5194,-0.0935", ["51.5074,-0.1278"], mode="transit"))
        print("Validate    :", validate_address("Defoe House, Barbican, London EC2Y 8DN"))
    else:
        print("unknown command:", cmd); print(__doc__)

if __name__ == "__main__":
    main()
