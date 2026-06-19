#!/usr/bin/env python3
"""flood.py - flood context via the Environment Agency Flood Monitoring API (keyless, OGL v3.0).

Area context that sits BESIDE the figure - never an input to the valuation. Given a
lat/lng it finds the flood-warning areas the property falls near and reports whether any
of them currently carry an active flood warning or alert. Best-effort: every call degrades
to {'ok': False, 'reason': ...} and never raises, so a slow or down endpoint can never
block a valuation.

Note on scope: this is the Environment Agency's real-time flood-MONITORING service (active
warnings + the warning areas that cover a point). It is the public, keyless feed. It is not
the "Flood Map for Planning" long-term risk classification, which is a separate licensed
dataset - so the copy says "active warnings / monitored flood areas", not "flood risk band".

Surfaces:
  floods(lat, lng, dist_km=5) -> {ok, nearby_areas, active, severity, lines:[...]}

CLI:
  python flood.py floods 51.519 -0.093
  python flood.py selftest
"""
import sys, json, urllib.parse, urllib.request, urllib.error

API = "https://environment.data.gov.uk/flood-monitoring"
_UA = {"User-Agent": "honestly-flood/1.0 (+https://t.me/usehonestly_bot)"}
_SRC = "Environment Agency real-time flood-monitoring API (OGL v3.0)"

# EA severity levels: 1 severe flood warning, 2 flood warning, 3 flood alert, 4 no longer in force
_SEV = {1: "Severe flood warning", 2: "Flood warning", 3: "Flood alert",
        4: "Warning no longer in force"}


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"Accept": "application/json", **_UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def floods(lat, lng, dist_km=5):
    """Monitored flood areas near a point and any active warning over them. dist_km is
    the search radius. Returns {ok, nearby_areas, active:[...], severity, lines} or
    {ok: False, reason}. Never raises."""
    if lat is None or lng is None:
        return {"ok": False, "reason": "no coordinates"}
    # 1) flood areas whose coverage is near the point
    q = urllib.parse.urlencode({"lat": lat, "long": lng, "dist": dist_km})
    try:
        areas = (_get_json(f"{API}/id/floodAreas?{q}") or {}).get("items", [])
    except urllib.error.HTTPError as e:
        return {"ok": False, "reason": f"flood-monitoring HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    area_codes = {a.get("fwdCode") or a.get("notation") for a in areas if isinstance(a, dict)}
    area_codes.discard(None)
    # 2) currently active warnings, intersected with the nearby areas
    try:
        active_all = (_get_json(f"{API}/id/floods") or {}).get("items", [])
    except Exception:
        active_all = []
    active = []
    worst = None
    for w in active_all:
        if not isinstance(w, dict):
            continue
        code = (w.get("floodArea") or {}).get("notation") or w.get("eaAreaName")
        sev = w.get("severityLevel")
        if code in area_codes:
            active.append({"area": (w.get("description") or code),
                           "severity": _SEV.get(sev, str(sev)),
                           "level": sev, "message": (w.get("message") or "")[:240]})
            if sev and (worst is None or sev < worst):
                worst = sev
    lines = []
    if not area_codes:
        lines.append("This location is not inside a monitored Environment Agency flood-warning area.")
        severity = "Not in a monitored flood-warning area"
    elif active:
        severity = _SEV.get(worst, "Active warning")
        lines.append(f"{len(active)} active flood warning(s)/alert(s) cover this area right now.")
    else:
        severity = "Monitored, no active warning"
        lines.append(f"Inside {len(area_codes)} monitored flood area(s); no warning is currently active.")
    return {"ok": True, "nearby_areas": len(area_codes), "active": active,
            "severity": severity, "lines": lines, "source": _SRC}


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    if sys.argv[1] == "floods":
        print(json.dumps(floods(float(sys.argv[2]), float(sys.argv[3])), indent=2, ensure_ascii=False))
    elif sys.argv[1] == "selftest":
        f = floods(51.5194, -0.0935)  # Barbican area
        if f.get("ok"):
            print("floods ok | areas", f["nearby_areas"], "| active", len(f["active"]),
                  "|", f["severity"])
        else:
            print("floods degraded:", f.get("reason"))
    else:
        print("unknown command:", sys.argv[1])


if __name__ == "__main__":
    main()
