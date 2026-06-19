# -*- coding: utf-8 -*-
"""planning_data.py - free planning constraints from planning.data.gov.uk (no key, open data).

The official Government planning-data platform exposes a point-in-polygon query: ask which
designated areas a coordinate falls WITHIN. We use it for the constraints that genuinely bear on
a property's alterations and value:

  conservation-area     - external changes controlled; permitted development curtailed
  article-4-direction   - specific permitted-development rights removed (e.g. no cladding/windows)
  flood-risk-zone       - the statutory EA flood zone the site sits in
  green-belt            - development tightly restricted
  scheduled-monument    - heritage protection on/around the site
  park-and-garden       - registered historic park/garden (setting protection)

Contract (same as every client here): BEST-EFFORT. Never raises into the request path; on any
failure returns {"ok": False, "reason": ...}. Only reports designations the API actually returns
for the point - no guessing, no fabrication. Honest by construction: an empty result means "the
public record shows no such designation here", which the dossier states plainly.

  python planning_data.py 51.5074 -0.1278     # live smoke test
"""
import json
import sys
import urllib.parse
import urllib.request

BASE = "https://www.planning.data.gov.uk/entity.json"

# The polygon designations worth flagging on a home. Point datasets (e.g. individual listed
# buildings) are deliberately excluded - a point-in-polygon "contains" query does not match a
# point feature, and a noisy radius search would imply a precision we do not have.
DATASETS = [
    "conservation-area",
    "article-4-direction",
    "flood-risk-zone",
    "green-belt",
    "scheduled-monument",
    "park-and-garden",
]

# Plain-English label per dataset, for the dossier/report.
LABELS = {
    "conservation-area": "Conservation area",
    "article-4-direction": "Article 4 direction",
    "flood-risk-zone": "Flood-risk zone (planning)",
    "green-belt": "Green belt",
    "scheduled-monument": "Scheduled monument",
    "park-and-garden": "Registered park/garden",
}


def constraints(lat, lng, timeout=20):
    """Designations the point at (lat, lng) falls within. Returns
        {"ok": True, "items": [{"dataset","label","name","reference"}, ...],
         "by_dataset": {dataset: [names]}, "datasets": [dataset, ...]}
    or {"ok": False, "reason": ...}. Never raises. An OK result with items==[] is a real,
    meaningful answer (no designation recorded here)."""
    try:
        if lat is None or lng is None:
            return {"ok": False, "reason": "no coordinates"}
        q = [("longitude", f"{float(lng)}"), ("latitude", f"{float(lat)}"), ("limit", "50")]
        q += [("dataset", d) for d in DATASETS]
        url = BASE + "?" + urllib.parse.urlencode(q)
        req = urllib.request.Request(url, headers={"User-Agent": "Honestly/1.0 (+usehonestly.co.uk)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "reason": str(e)[:160]}
    items, by = [], {}
    for e in (data.get("entities") or []):
        ds = e.get("dataset")
        if ds not in LABELS:
            continue
        name = (e.get("name") or "").strip() or LABELS[ds]
        items.append({"dataset": ds, "label": LABELS[ds], "name": name,
                      "reference": e.get("reference")})
        by.setdefault(ds, []).append(name)
    return {"ok": True, "items": items, "by_dataset": by, "datasets": list(by.keys()),
            "source": "planning.data.gov.uk"}


def summary_line(res):
    """One honest line for a card/teaser, or None when there's nothing to say."""
    if not (res and res.get("ok")):
        return None
    items = res.get("items") or []
    if not items:
        return "No conservation area, Article 4, flood zone or green-belt designation recorded here."
    return "Designations on this site: " + "; ".join(sorted({i["label"] for i in items})) + "."


def main():
    lat = float(sys.argv[1]) if len(sys.argv) > 1 else 51.5074
    lng = float(sys.argv[2]) if len(sys.argv) > 2 else -0.1278
    res = constraints(lat, lng)
    print(json.dumps(res, indent=2)[:1500])
    print(summary_line(res))


if __name__ == "__main__":
    main()
