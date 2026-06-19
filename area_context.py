#!/usr/bin/env python3
"""area_context.py - one aggregator that gathers all the free/keyed CONTEXT around a
property and returns it in one structured dict the PDF and the interactive HTML both
iterate. This is the data producer behind the Location, Area, Safety, Environment,
Planning, Material (council-tax) and Narrative sections.

Honesty contract: everything here sits BESIDE the figure as sourced context. Nothing in
this module is an input to engine.value(). Every underlying client is best-effort and
returns {ok: False, reason} when its service is down; this aggregator simply collects
whichever ones succeeded, so a slow or dead source omits its panel and never blocks or
delays a valuation.

Surface:
  gather(subject, summary=None, anchors=None) -> {
      "sections": {                       # keyed by the DELIVERABLE_MAP html_panel
          "location":    {...} | None,
          "area":        {...} | None,
          "safety":      {...} | None,
          "environment": {...} | None,
          "planning":    {...} | None,
          "solar":       {...} | None,    # Google Solar roof potential (building-level)
          "material":    {...} | None,    # council-tax band context
          "narrative":   {...} | None,    # Gemini, grounded + guarded
      },
      "present": {citation_id: True, ...}, # flags brand.references() reads
      "lat": ..., "lng": ..., "postcode": ...,
  }

subject is the resolved subject dict (address/lat/lng/postcode/tax). summary is the
engine.summary() dict (needed only for the Gemini narrative grounding). anchors is an
optional list of (label, "lat,lng") travel-time destinations; if omitted, connectivity
falls back to the nearest mapped station from Overpass.

CLI:
  python area_context.py defoe        # the Barbican sample, all live
  python area_context.py 51.519 -0.093 "EC2Y 8DN" C
"""
import sys, json

import geo, police, flood, air_quality, planning, overpass, council_tax
try:
    import planning_data            # free planning.data.gov.uk point constraints (conservation/A4/flood-zone/green-belt)
except Exception:
    planning_data = None
try:
    import solar
except Exception:                       # solar is optional (needs a Google key)
    solar = None
try:
    import maps_tools
except Exception:                       # maps is optional (needs a key)
    maps_tools = None
try:
    import ai
except Exception:
    ai = None


def _coords(subject):
    """Resolve lat/lng/postcode from the subject, filling coordinates from Postcodes.io
    when the subject only carries a postcode."""
    lat, lng = subject.get("lat"), subject.get("lng")
    pc = subject.get("postcode") or subject.get("pc")
    src = None
    if (lat is None or lng is None) and pc:
        g = geo.lookup(pc)
        if g.get("ok"):
            lat, lng = g["lat"], g["lng"]
            pc = g.get("postcode") or pc
            src = g.get("source")
    return lat, lng, pc, src


def _location(subject, lat, lng, pc, geo_src, anvals):
    """Postcodes.io geo + Address Validation + Distance Matrix travel times."""
    out = {"postcode": pc, "lat": lat, "lng": lng, "source": geo_src,
           "validated": None, "legs": [], "rows": []}
    present = {}
    if lat and lng:
        present["postcodes_io"] = True
    # verified/normalised address
    if maps_tools:
        v = maps_tools.validate_address(subject.get("address") or "")
        if v.get("ok"):
            out["validated"] = {"formatted": v.get("formatted"),
                                "note": v.get("components_note")}
            present["addr_val"] = True
    # travel times: to provided anchors, else to the nearest mapped station
    if maps_tools and lat and lng and anvals:
        origin = f"{lat},{lng}"
        dests = [a[1] for a in anvals]
        dm = maps_tools.distance_matrix(origin, dests, mode="transit")
        if dm.get("ok"):
            for (label, _), leg in zip(anvals, dm["legs"]):
                if leg.get("text"):
                    out["legs"].append({"label": label, "time": leg["text"],
                                        "dist": leg.get("dist_text")})
            if out["legs"]:
                present["distance_mx"] = True
    out["rows"] = out["legs"]
    if not (out["legs"] or out["validated"] or (lat and lng)):
        return None, present
    return out, present


def gather(subject, summary=None, anchors=None):
    """Collect all context around the subject. Returns the structured dict above."""
    subject = subject or {}
    lat, lng, pc, geo_src = _coords(subject)
    sections, present = {}, {}

    # --- Location & connectivity
    loc, p = _location(subject, lat, lng, pc, geo_src, anchors or [])
    sections["location"] = loc
    present.update(p)

    if lat is not None and lng is not None:
        # --- Area & amenities (Overpass)
        am = overpass.amenities(lat, lng)
        if am.get("ok"):
            sections["area"] = am
            present["overpass"] = True
            # backfill nearest-station connectivity if Distance Matrix had no anchors
            if sections.get("location") and not sections["location"]["legs"] and am.get("transport"):
                t = am["transport"][0]
                sections["location"]["legs"].append(
                    {"label": f"Nearest station: {t['name']}", "time": None,
                     "dist": f"~{t['dist_m']} m"})
                sections["location"]["rows"] = sections["location"]["legs"]
        else:
            sections["area"] = None

        # --- Safety (Police.uk)
        cr = police.crimes(lat, lng)
        if cr.get("ok"):
            sections["safety"] = cr
            present["police"] = True
        else:
            sections["safety"] = None

        # --- Environment (Flood + Air quality)
        fl = flood.floods(lat, lng)
        aq = air_quality.air(lat, lng)
        env = {}
        if fl.get("ok"):
            env["flood"] = fl; present["flood"] = True
        if aq.get("ok"):
            env["air"] = aq; present["air_quality"] = True
        sections["environment"] = env or None

        # --- Planning (PlanIt)
        pl = planning.nearby(lat, lng)
        if pl.get("ok"):
            sections["planning"] = pl
            present["planning"] = True
        else:
            sections["planning"] = None

        # --- Planning CONSTRAINTS (planning.data.gov.uk: conservation area / Article 4 / flood
        # zone / green belt the property falls within). Free open data, no key. An OK-but-empty
        # result is meaningful ("no designation recorded here") and still stored.
        if planning_data:
            pc_con = planning_data.constraints(lat, lng)
            if pc_con.get("ok"):
                sections["planning_constraints"] = pc_con
                present["planning_data"] = True
            else:
                sections["planning_constraints"] = None
        else:
            sections["planning_constraints"] = None

        # --- Solar & energy (Google Solar, building-level roof potential)
        if solar:
            so = solar.roof(lat, lng)
            if so.get("ok"):
                sections["solar"] = so
                present["google_solar"] = True
            else:
                sections["solar"] = None
        else:
            sections["solar"] = None
    else:
        for k in ("area", "safety", "environment", "planning", "solar"):
            sections[k] = None

    # --- Material: council-tax band context (no network)
    band = subject.get("tax") or subject.get("council_tax")
    if band:
        ct = council_tax.band_context(band)
        if ct.get("ok"):
            sections["material"] = ct
            present["council_tax"] = True
        else:
            sections["material"] = None
    else:
        sections["material"] = None

    # --- Narrative (Gemini, grounded in summary, honesty-guarded)
    if ai and summary:
        nar = ai.narrative(summary, audience=summary.get("audience", "owner"))
        if nar.get("ok"):
            sections["narrative"] = nar
            present["gemini"] = True
        else:
            sections["narrative"] = {"ok": False, "reason": nar.get("reason")}
    else:
        sections["narrative"] = None

    return {"sections": sections, "present": present,
            "lat": lat, "lng": lng, "postcode": pc}


# London anchors used by the Defoe House sample (label, "lat,lng")
_LONDON_ANCHORS = [
    ("Bank station", "51.5134,-0.0890"),
    ("Liverpool Street", "51.5178,-0.0823"),
    ("King's Cross St Pancras", "51.5308,-0.1238"),
    ("Canary Wharf", "51.5054,-0.0235"),
]


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    if sys.argv[1] == "defoe":
        subject = {"address": "Defoe House, Barbican, London EC2Y 8DN",
                   "postcode": "EC2Y 8DN", "tax": "G"}
        res = gather(subject, summary=None, anchors=_LONDON_ANCHORS)
    else:
        lat = float(sys.argv[1]); lng = float(sys.argv[2])
        pc = sys.argv[3] if len(sys.argv) > 3 else None
        band = sys.argv[4] if len(sys.argv) > 4 else None
        subject = {"address": pc or "", "lat": lat, "lng": lng, "postcode": pc, "tax": band}
        res = gather(subject, summary=None, anchors=_LONDON_ANCHORS)
    # compact print: which sections came back, and the present-ids
    print("present:", sorted(res["present"].keys()))
    for name, sec in res["sections"].items():
        if not sec:
            print(f"  {name:12s}: (not available)")
        elif isinstance(sec, dict) and sec.get("ok") is False:
            print(f"  {name:12s}: degraded - {sec.get('reason')}")
        else:
            lines = sec.get("lines") if isinstance(sec, dict) else None
            print(f"  {name:12s}: ok", ("| " + " ".join(lines[:1])) if lines else "")


if __name__ == "__main__":
    main()
