#!/usr/bin/env python3
"""bgs.py - ground stability / shrink-swell subsidence risk from BGS open data.

Source investigation (June 2026):
  The British Geological Survey (BGS) produces the GeoSure shrink-swell dataset —
  the authoritative source for clay shrink-swell subsidence risk in Great Britain
  at 1:50,000 scale. After verifying all BGS open-data and web-service channels,
  no free, commercially-usable, programmatic point-query endpoint exists:

  1. BGS GeoSure shrink-swell (polygon dataset) — LICENSED / PAID.
     Pricing from £0.06–£0.91/km² depending on theme bundle; requires a licence
     agreement negotiated with BGS. Not open for commercial use.
     https://www.bgs.ac.uk/datasets/bgs-geosure-shrink-swell/

  2. BGS GeoSure OGC WMS (data.gov.uk) — PERSONAL / NON-COMMERCIAL ONLY.
     The only publicly listed WMS covering GeoSure covers just the Loughborough
     and Kilmarnock map sheets (OneGeology-Europe contribution) and is explicitly
     for personal, non-commercial use. Not usable here.
     https://www.data.gov.uk/dataset/4997fbf6-e3f8-4bbd-bdf9-7c582addbf94/bgs-geosure-ogc-wxs2

  3. BGS GeoIndex Onshore Hazards WMS — OGL, but NO shrink-swell layer.
     Endpoint: https://map.bgs.ac.uk/arcgis/services/GeoIndex_Onshore/hazards/MapServer/WmsServer
     Layers: Landslides, Modern earthquakes, Historical earthquakes, Monitoring stations.
     No shrink-swell, ground stability, or clay layer present.

  4. BGS WFS services — OGL, but NO GeoSure layer.
     Only Mineral Statistics and UK Bedrock Geology are available via WFS.
     https://www.bgs.ac.uk/technologies/web-services/web-feature-services-wfs/

  5. BGS GeoSure 5 km hex grid — OGL / FREE, but BULK DOWNLOAD ONLY.
     Available as Shapefile/GeoPackage via OS Data Hub; no live queryable
     WMS or WFS endpoint exists for point-based lookup.
     https://osdatahub.os.uk/downloads/open/GB-Hex-5km-GeoSure

  Conclusion: the subsidence() function returns an honest not-available result.
  The full public contract is kept intact so the UI can display a 'not available'
  panel state cleanly. If BGS ever publish a free point-query endpoint for
  GeoSure shrink-swell, replace the body of subsidence() to call it.

Licence (for any BGS open layers used in future): Open Government Licence v3.0
  https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/
  Attribution: "Contains British Geological Survey materials © UKRI [year]"

Surfaces:
  subsidence(lat, lng) -> {ok, shrink_swell, band, source, url, raw}
                       or {ok: False, reason: str}

CLI:
  python bgs.py subsidence 51.4663 -0.0666
  python bgs.py selftest
"""
import sys, json

_NOT_AVAILABLE_REASON = (
    "BGS GeoSure shrink-swell is a licensed product; "
    "no free programmatic point-query source for subsidence risk is available. "
    "See module docstring for full source investigation."
)
_DATASET_URL = "https://www.bgs.ac.uk/datasets/bgs-geosure-shrink-swell/"


def subsidence(lat, lng):
    """Return ground-stability / shrink-swell subsidence risk at a point from free BGS open data.
    Returns {"ok": True, "shrink_swell": "low"|"moderate"|"high"|str, "band": str|None,
             "source": str, "url": str, "raw": dict} on success,
             else {"ok": False, "reason": str}. Never raises."""
    # No free, commercially-usable point-query endpoint exists for BGS GeoSure
    # shrink-swell as of June 2026. See module docstring for the full investigation.
    # Return an honest not-available result; callers and the UI handle this state.
    return {"ok": False, "reason": _NOT_AVAILABLE_REASON}


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    if sys.argv[1] == "subsidence":
        if len(sys.argv) < 4:
            print("usage: python bgs.py subsidence <lat> <lng>"); return
        print(json.dumps(subsidence(float(sys.argv[2]), float(sys.argv[3])),
                         indent=2, ensure_ascii=False))
    elif sys.argv[1] == "selftest":
        r = subsidence(51.4663, -0.0666)  # SE15 Peckham point
        if r.get("ok"):
            print("subsidence ok | shrink_swell", r["shrink_swell"],
                  "| band", r.get("band"), "| source", r.get("source"))
        else:
            print("subsidence not available:", r.get("reason"))
    else:
        print("unknown command:", sys.argv[1])


if __name__ == "__main__":
    # Quick self-test: SE15 Peckham point
    result = subsidence(51.4663, -0.0666)
    print(json.dumps(result, indent=2, ensure_ascii=False))
