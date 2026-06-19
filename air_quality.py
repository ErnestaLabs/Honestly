#!/usr/bin/env python3
"""air_quality.py - local air quality via the Open-Meteo Air Quality API (keyless).

Area context that sits BESIDE the figure - never an input to the valuation. Given a
lat/lng it reports the current European AQI plus the headline pollutants (PM2.5, PM10,
NO2). Best-effort: every call degrades to {'ok': False, 'reason': ...} and never raises.

Source: Open-Meteo Air Quality API, which serves the Copernicus Atmosphere Monitoring
Service (CAMS) European air-quality model. Cited as Open-Meteo / CAMS - NOT DEFRA, because
that is the actual data path. (Describe only what the source does.)

Surfaces:
  air(lat, lng) -> {ok, aqi, band, pm2_5, pm10, no2, lines:[...]}

CLI:
  python air_quality.py air 51.519 -0.093
  python air_quality.py selftest
"""
import sys, json, urllib.parse, urllib.request, urllib.error

API = "https://air-quality-api.open-meteo.com/v1/air-quality"
_UA = {"User-Agent": "honestly-air/1.0 (+https://t.me/usehonestly_bot)"}
_SRC = "Open-Meteo Air Quality API (Copernicus CAMS European model)"


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"Accept": "application/json", **_UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _band(aqi):
    """European AQI bands (EEA): 0-20 good, 20-40 fair, 40-60 moderate, 60-80 poor,
    80-100 very poor, 100+ extremely poor."""
    if aqi is None:
        return None
    for hi, lab in ((20, "Good"), (40, "Fair"), (60, "Moderate"),
                    (80, "Poor"), (100, "Very poor")):
        if aqi <= hi:
            return lab
    return "Extremely poor"


def air(lat, lng):
    """Current European AQI + headline pollutants for a point. Returns
    {ok, aqi, band, pm2_5, pm10, no2, lines} or {ok: False, reason}. Never raises."""
    if lat is None or lng is None:
        return {"ok": False, "reason": "no coordinates"}
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lng,
        "current": "european_aqi,pm2_5,pm10,nitrogen_dioxide",
    })
    try:
        d = _get_json(f"{API}?{q}")
    except urllib.error.HTTPError as e:
        return {"ok": False, "reason": f"Open-Meteo HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    cur = d.get("current") or {}
    if not cur:
        return {"ok": False, "reason": "no air-quality reading"}
    aqi = cur.get("european_aqi")
    band = _band(aqi)
    pm25, pm10, no2 = cur.get("pm2_5"), cur.get("pm10"), cur.get("nitrogen_dioxide")
    lines = []
    if aqi is not None:
        lines.append(f"Current European AQI {round(aqi)} - {band}.")
    bits = []
    if pm25 is not None: bits.append(f"PM2.5 {pm25} ug/m3")
    if pm10 is not None: bits.append(f"PM10 {pm10} ug/m3")
    if no2 is not None: bits.append(f"NO2 {no2} ug/m3")
    if bits:
        lines.append("; ".join(bits) + ".")
    return {"ok": True, "aqi": aqi, "band": band, "pm2_5": pm25, "pm10": pm10,
            "no2": no2, "lines": lines, "source": _SRC}


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    if sys.argv[1] == "air":
        print(json.dumps(air(float(sys.argv[2]), float(sys.argv[3])), indent=2, ensure_ascii=False))
    elif sys.argv[1] == "selftest":
        a = air(51.5194, -0.0935)  # Barbican area
        if a.get("ok"):
            print("air ok | aqi", a["aqi"], a["band"], "| pm2.5", a["pm2_5"])
        else:
            print("air degraded:", a.get("reason"))
    else:
        print("unknown command:", sys.argv[1])


if __name__ == "__main__":
    main()
