#!/usr/bin/env python3
"""solar.py - roof solar potential via the Google Solar API (buildingInsights:findClosest).

Area context that sits BESIDE the figure - never an input to the valuation. Given a
lat/lng it reports what the building's roof could physically host: usable panel count and
area, the estimated annual generation of a sensible domestic array, the lifetime CO2 offset
and the imagery provenance. Best-effort: every call degrades to {'ok': False, 'reason': ...}
and never raises.

Honesty notes (Describe only what the source does):
  * buildingInsights is BUILDING-LEVEL. findClosest snaps to the nearest building, so the
    response can describe a neighbour. We compute and disclose the snap distance from the
    requested point to the building Google actually returned, and flag a far snap.
  * For a flat in a block the whole-roof figures belong to the block, not the dwelling. We
    label the figures as whole-roof, building-level, and report a domestic-sized array as
    the decision-relevant subset rather than implying one flat owns the whole roof.
  * The 'potential' band (High/Medium/Low/None) is HONESTLY OURS, derived from the estimated
    domestic annual generation with the rule stated in the output - it is not a Google field.

Surface:
  roof(lat, lng, domestic_max_panels=16) -> {
      ok, potential, max_panels, max_array_area_m2, panel_capacity_watts,
      domestic_panels, domestic_kwp, domestic_kwh_yr, co2_offset_kg_yr,
      sunshine_hours_max, imagery_quality, imagery_date, snap_distance_m, lines, source }

CLI:
  python solar.py roof 51.4732 -0.0712
  python solar.py selftest
"""
import os, sys, json, math, urllib.parse, urllib.request, urllib.error

API = "https://solar.googleapis.com/v1/buildingInsights:findClosest"
_SRC = "Google Solar API (buildingInsights)"
# domestic generation -> potential band. OUR read, disclosed in the output. kWh/yr.
_BANDS = ((3500, "High"), (2000, "Medium"), (1, "Low"))
# a snap further than this from the requested point likely describes a neighbouring building
_FAR_SNAP_M = 60.0


def _load_env():
    """Reuse maps_tools' loader so the GOOGLE_MAPS_API_KEY is read from env or local .env.
    The key is NEVER returned to a client or printed."""
    try:
        import maps_tools
        maps_tools._load_env()
    except Exception:
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(here):
            with open(here, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())


def _get_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.load(r)


def _haversine_m(lat1, lng1, lat2, lng2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def _band(domestic_kwh):
    if not domestic_kwh or domestic_kwh <= 0:
        return "None"
    for floor, lab in _BANDS:
        if domestic_kwh >= floor:
            return lab
    return "None"


def _domestic_config(configs, cap):
    """The largest panel configuration that does not exceed a sensible domestic install
    (cap panels). If the whole roof holds fewer than cap, that is the domestic config."""
    best = None
    for c in configs or []:
        n = c.get("panelsCount")
        if n is None or n > cap:
            continue
        if best is None or n > best.get("panelsCount", -1):
            best = c
    if best is None and configs:
        # every config exceeds the cap - fall back to the smallest available
        best = min(configs, key=lambda c: c.get("panelsCount", 1 << 30))
    return best


def roof(lat, lng, domestic_max_panels=16):
    """Roof solar potential for the building nearest a point. Returns the structured dict
    above or {ok: False, reason}. Never raises."""
    if lat is None or lng is None:
        return {"ok": False, "reason": "no coordinates"}
    _load_env()
    k = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not k:
        return {"ok": False, "reason": "GOOGLE_MAPS_API_KEY not set"}
    q = urllib.parse.urlencode({"location.latitude": lat, "location.longitude": lng,
                                "requiredQuality": "LOW", "key": k})
    try:
        st, d = _get_json(f"{API}?{q}")
    except urllib.error.HTTPError as e:
        # 404 is the honest "no building roof here" answer Google gives for open ground
        reason = "no building roof found" if e.code == 404 else f"Solar API HTTP {e.code}"
        return {"ok": False, "reason": reason}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}

    sp = d.get("solarPotential") or {}
    if not sp:
        return {"ok": False, "reason": "no solar potential for this building"}

    cap_w = sp.get("panelCapacityWatts")
    configs = sp.get("solarPanelConfigs") or []
    dom = _domestic_config(configs, domestic_max_panels)
    dom_panels = dom.get("panelsCount") if dom else None
    dom_kwh = round(dom["yearlyEnergyDcKwh"]) if dom and dom.get("yearlyEnergyDcKwh") else None
    dom_kwp = round(dom_panels * cap_w / 1000.0, 2) if (dom_panels and cap_w) else None

    co2_factor = sp.get("carbonOffsetFactorKgPerMwh")
    co2_yr = round(co2_factor * dom_kwh / 1000.0) if (co2_factor and dom_kwh) else None

    # snap distance: how far the building Google returned sits from the point we asked about
    centre = d.get("center") or {}
    snap = None
    if centre.get("latitude") is not None and centre.get("longitude") is not None:
        snap = round(_haversine_m(lat, lng, centre["latitude"], centre["longitude"]), 1)

    imd = d.get("imageryDate") or {}
    imagery_date = (f"{imd.get('year')}-{imd.get('month'):02d}-{imd.get('day'):02d}"
                    if imd.get("year") else None)

    band = _band(dom_kwh)

    lines = []
    far = snap is not None and snap > _FAR_SNAP_M
    if dom_panels and dom_kwh:
        lines.append(
            f"A {dom_panels}-panel domestic array (~{dom_kwp} kWp) could generate about "
            f"{dom_kwh:,} kWh a year - {band.lower()} solar potential.")
    if sp.get("maxArrayPanelsCount"):
        area = sp.get("maxArrayAreaMeters2")
        lines.append(
            f"Whole-roof maximum (building-level): up to {sp['maxArrayPanelsCount']} panels"
            + (f" across ~{round(area)} m2 of usable roof." if area else "."))
    if co2_yr:
        lines.append(f"That domestic array offsets roughly {co2_yr:,} kg of CO2 a year.")
    if imagery_date:
        lines.append(f"From Google Solar roof imagery dated {imagery_date} "
                     f"({d.get('imageryQuality', 'quality unknown').lower()} quality).")
    if far:
        lines.append(f"Note: the nearest mapped roof is ~{round(snap)} m from the address, so "
                     f"these figures may describe a neighbouring building - treat as indicative.")

    return {
        "ok": True,
        "potential": band,
        "max_panels": sp.get("maxArrayPanelsCount"),
        "max_array_area_m2": (round(sp["maxArrayAreaMeters2"]) if sp.get("maxArrayAreaMeters2") else None),
        "panel_capacity_watts": cap_w,
        "domestic_panels": dom_panels,
        "domestic_kwp": dom_kwp,
        "domestic_kwh_yr": dom_kwh,
        "co2_offset_kg_yr": co2_yr,
        "sunshine_hours_max": (round(sp["maxSunshineHoursPerYear"])
                               if sp.get("maxSunshineHoursPerYear") else None),
        "imagery_quality": d.get("imageryQuality"),
        "imagery_date": imagery_date,
        "snap_distance_m": snap,
        "far_snap": far,
        "lines": lines,
        "source": _SRC,
        "band_rule": ("Potential band is Honestly's own read of the estimated domestic annual "
                      "generation: High >=3,500 kWh, Medium >=2,000 kWh, Low below that."),
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    if sys.argv[1] == "roof":
        print(json.dumps(roof(float(sys.argv[2]), float(sys.argv[3])), indent=2, ensure_ascii=False))
    elif sys.argv[1] == "selftest":
        r = roof(51.4732, -0.0712)  # 58 Cronin Street, Peckham SE15 6JH
        if r.get("ok"):
            print("solar ok | potential", r["potential"], "| domestic",
                  r["domestic_panels"], "panels ->", r["domestic_kwh_yr"], "kWh/yr",
                  "| max", r["max_panels"], "panels | snap", r["snap_distance_m"], "m")
            for ln in r["lines"]:
                print("  -", ln)
        else:
            print("solar degraded:", r.get("reason"))
    else:
        print("unknown command:", sys.argv[1])


if __name__ == "__main__":
    main()
