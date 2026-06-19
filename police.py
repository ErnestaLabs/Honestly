#!/usr/bin/env python3
"""police.py - street-level crime context via data.police.uk (keyless, OGL v3.0).

Area context that sits BESIDE the figure - never an input to the valuation. Given a
lat/lng it pulls the latest published month of street-level crime within the police
API's ~1 mile radius and summarises it by category. Best-effort: every call degrades
to {'ok': False, 'reason': ...} and never raises, so a slow or down endpoint can never
block a valuation.

Surfaces:
  crimes(lat, lng, month=None) -> {ok, month, total, by_category:[(cat,n)...], radius_note}

CLI:
  python police.py crimes 51.519 -0.093
  python police.py selftest
"""
import sys, json, urllib.parse, urllib.request, urllib.error
from collections import Counter

API = "https://data.police.uk/api"
_UA = {"User-Agent": "honestly-police/1.0 (+https://t.me/usehonestly_bot)"}


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"Accept": "application/json", **_UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _pretty(cat):
    return (cat or "other").replace("-", " ").replace("_", " ").strip().capitalize()


def crimes(lat, lng, month=None):
    """Latest-month street-level crime around a point. month is 'YYYY-MM' or None for
    the most recent the API has published. Returns category counts, never raises."""
    if lat is None or lng is None:
        return {"ok": False, "reason": "no coordinates"}
    q = {"lat": lat, "lng": lng}
    if month:
        q["date"] = month
    url = f"{API}/crimes-street/all-crime?" + urllib.parse.urlencode(q)
    try:
        rows = _get_json(url)
    except urllib.error.HTTPError as e:
        return {"ok": False, "reason": f"data.police.uk HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    if not isinstance(rows, list):
        return {"ok": False, "reason": "unexpected response"}
    if not rows:
        return {"ok": True, "month": month, "total": 0, "by_category": [],
                "radius_note": "within ~1 mile of the property",
                "source": "Home Office / data.police.uk (OGL v3.0)"}
    cats = Counter(_pretty(r.get("category")) for r in rows)
    seen_month = (rows[0].get("month") if rows else None) or month
    return {
        "ok": True, "month": seen_month, "total": len(rows),
        "by_category": cats.most_common(),
        "radius_note": "within ~1 mile of the property",
        "source": "Home Office / data.police.uk (OGL v3.0)",
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    if sys.argv[1] == "crimes":
        print(json.dumps(crimes(float(sys.argv[2]), float(sys.argv[3])), indent=2, ensure_ascii=False))
    elif sys.argv[1] == "selftest":
        c = crimes(51.5194, -0.0935)  # Barbican area
        if c.get("ok"):
            print("crimes ok | month", c["month"], "| total", c["total"],
                  "| top", c["by_category"][:3])
        else:
            print("crimes degraded:", c.get("reason"))
    else:
        print("unknown command:", sys.argv[1])


if __name__ == "__main__":
    main()
