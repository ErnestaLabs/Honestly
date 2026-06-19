#!/usr/bin/env python3
"""planning.py - nearby planning applications via PlanIt.org.uk (keyless open API).

Area context that sits BESIDE the figure - never an input to the valuation. Given a
lat/lng it pulls recent planning applications within a small radius and summarises them
by status. Best-effort: every call degrades to {'ok': False, 'reason': ...} and never
raises, so a slow or down endpoint can never block a valuation.

Source: PlanIt (planit.org.uk), an independent aggregator that scrapes UK local-authority
planning portals into one JSON API. Cited as PlanIt - NOT "Planning Portal", because PlanIt
is the actual source queried. (Describe only what the source does.)

Surfaces:
  nearby(lat, lng, krad_km=0.5, recent=12) -> {ok, total, applications:[...], by_status, lines}

CLI:
  python planning.py nearby 51.519 -0.093
  python planning.py selftest
"""
import sys, json, urllib.parse, urllib.request, urllib.error
from collections import Counter

API = "https://www.planit.org.uk/api/applics/json"
_UA = {"User-Agent": "honestly-planning/1.0 (+https://t.me/usehonestly_bot)"}
_SRC = "PlanIt (planit.org.uk), aggregating UK local-authority planning registers"


def _get_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"Accept": "application/json", **_UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def nearby(lat, lng, krad_km=0.5, recent=12):
    """Recent planning applications within krad_km of a point. recent caps how many of the
    newest are returned in detail. Returns {ok, total, applications, by_status, lines} or
    {ok: False, reason}. Never raises."""
    if lat is None or lng is None:
        return {"ok": False, "reason": "no coordinates"}
    q = urllib.parse.urlencode({
        "lat": lat, "lng": lng, "krad": krad_km,
        "pg_sz": max(recent, 50), "select": "name,description,app_state,app_type,start_date,address",
    })
    try:
        d = _get_json(f"{API}?{q}")
    except urllib.error.HTTPError as e:
        return {"ok": False, "reason": f"PlanIt HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    records = d.get("records") if isinstance(d, dict) else d
    if not isinstance(records, list):
        return {"ok": False, "reason": "unexpected response"}
    if not records:
        return {"ok": True, "total": 0, "applications": [], "by_status": [],
                "lines": [f"No planning applications recorded within {krad_km} km."],
                "source": _SRC}
    apps = []
    for r in records[:recent]:
        if not isinstance(r, dict):
            continue
        apps.append({
            "description": (r.get("description") or "")[:200],
            "status": r.get("app_state") or "Unknown",
            "type": r.get("app_type"),
            "date": r.get("start_date"),
            "address": r.get("address"),
        })
    statuses = Counter((r.get("app_state") or "Unknown") for r in records if isinstance(r, dict))
    lines = [f"{len(records)} planning application(s) within {krad_km} km in the recent window."]
    top = "; ".join(f"{s}: {n}" for s, n in statuses.most_common(4))
    if top:
        lines.append(top + ".")
    return {"ok": True, "total": len(records), "applications": apps,
            "by_status": statuses.most_common(), "lines": lines, "source": _SRC}


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    if sys.argv[1] == "nearby":
        print(json.dumps(nearby(float(sys.argv[2]), float(sys.argv[3])), indent=2, ensure_ascii=False))
    elif sys.argv[1] == "selftest":
        p = nearby(51.5194, -0.0935)  # Barbican area
        if p.get("ok"):
            print("planning ok | total", p["total"], "| statuses", p["by_status"][:3])
        else:
            print("planning degraded:", p.get("reason"))
    else:
        print("unknown command:", sys.argv[1])


if __name__ == "__main__":
    main()
