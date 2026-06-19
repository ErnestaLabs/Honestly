#!/usr/bin/env python3
"""Offline tests for solar.py - the Google Solar roof-potential client (build #72).

No network, no spend: the Google Solar HTTP call is mocked at solar._get_json, and the
key check is exercised by toggling the environment. The honesty contract under test:
  * building-level figures are labelled as whole-roof and a domestic-sized array is the
    decision-relevant subset (never the whole roof attributed to one dwelling);
  * the findClosest snap distance is computed and a far snap is flagged as indicative;
  * the potential band is OUR disclosed read of domestic generation, stated in band_rule;
  * every failure path degrades to {ok: False, reason} and never raises.
"""
import unittest
from unittest import mock

import solar


def _resp(max_panels=19, cap=400, area=37.0, co2=479.0, sunshine=1046.0,
          configs=None, centre=(51.4732, -0.0712), quality="HIGH",
          imd=(2024, 8, 11)):
    if configs is None:
        configs = [{"panelsCount": n, "yearlyEnergyDcKwh": n * 366.0}
                   for n in (4, 6, 8, 10, 12, 14, 16, 18, 19)]
    return 200, {
        "center": {"latitude": centre[0], "longitude": centre[1]},
        "imageryQuality": quality,
        "imageryDate": {"year": imd[0], "month": imd[1], "day": imd[2]},
        "solarPotential": {
            "maxArrayPanelsCount": max_panels,
            "maxArrayAreaMeters2": area,
            "panelCapacityWatts": cap,
            "carbonOffsetFactorKgPerMwh": co2,
            "maxSunshineHoursPerYear": sunshine,
            "solarPanelConfigs": configs,
        },
    }


class TestHelpers(unittest.TestCase):
    def test_band_thresholds(self):
        self.assertEqual(solar._band(4000), "High")
        self.assertEqual(solar._band(3500), "High")
        self.assertEqual(solar._band(2500), "Medium")
        self.assertEqual(solar._band(2000), "Medium")
        self.assertEqual(solar._band(1500), "Low")
        self.assertEqual(solar._band(0), "None")
        self.assertEqual(solar._band(None), "None")

    def test_domestic_config_picks_largest_within_cap(self):
        cfgs = [{"panelsCount": n, "yearlyEnergyDcKwh": n * 300.0}
                for n in (4, 10, 16, 19)]
        d = solar._domestic_config(cfgs, 16)
        self.assertEqual(d["panelsCount"], 16)

    def test_domestic_config_falls_back_to_smallest_when_all_exceed_cap(self):
        cfgs = [{"panelsCount": n, "yearlyEnergyDcKwh": n * 300.0} for n in (40, 80, 120)]
        d = solar._domestic_config(cfgs, 16)
        self.assertEqual(d["panelsCount"], 40)

    def test_haversine_zero_and_positive(self):
        self.assertAlmostEqual(solar._haversine_m(51.47, -0.07, 51.47, -0.07), 0.0, places=3)
        self.assertGreater(solar._haversine_m(51.47, -0.07, 51.48, -0.07), 1000)


class TestRoofDegrades(unittest.TestCase):
    def test_no_coordinates(self):
        self.assertFalse(solar.roof(None, None)["ok"])

    def test_no_key(self):
        with mock.patch.object(solar, "_load_env", lambda: None), \
             mock.patch.dict("os.environ", {}, clear=True):
            r = solar.roof(51.47, -0.07)
        self.assertFalse(r["ok"])
        self.assertIn("GOOGLE_MAPS_API_KEY", r["reason"])

    def test_404_is_no_building(self):
        import urllib.error
        def boom(url, timeout=25):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        with mock.patch.object(solar, "_load_env", lambda: None), \
             mock.patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "x"}), \
             mock.patch.object(solar, "_get_json", boom):
            r = solar.roof(51.47, -0.07)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "no building roof found")


class TestRoofParse(unittest.TestCase):
    def _roof(self, **over):
        with mock.patch.object(solar, "_load_env", lambda: None), \
             mock.patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "x"}), \
             mock.patch.object(solar, "_get_json", lambda u, timeout=25: _resp(**over)):
            return solar.roof(51.4732, -0.0712)

    def test_parses_domestic_and_whole_roof(self):
        r = self._roof()
        self.assertTrue(r["ok"])
        self.assertEqual(r["domestic_panels"], 16)            # largest <= cap of 16
        self.assertEqual(r["domestic_kwh_yr"], round(16 * 366.0))
        self.assertEqual(r["domestic_kwp"], round(16 * 400 / 1000.0, 2))
        self.assertEqual(r["max_panels"], 19)                 # whole-roof maximum
        self.assertEqual(r["potential"], "High")              # 5856 kWh -> High
        self.assertIn("kWh a year", " ".join(r["lines"]))

    def test_co2_offset_derived_from_domestic_generation(self):
        r = self._roof()
        self.assertEqual(r["co2_offset_kg_yr"], round(479.0 * r["domestic_kwh_yr"] / 1000.0))

    def test_band_rule_disclosed(self):
        r = self._roof()
        self.assertIn("Honestly's own read", r["band_rule"])

    def test_near_snap_not_flagged(self):
        r = self._roof(centre=(51.4732, -0.0712))
        self.assertLess(r["snap_distance_m"], solar._FAR_SNAP_M)
        self.assertFalse(r["far_snap"])
        self.assertFalse(any("neighbouring building" in ln for ln in r["lines"]))

    def test_far_snap_flagged_as_indicative(self):
        # a centre ~150 m away -> far snap -> indicative note appears
        r = self._roof(centre=(51.4745, -0.0712))
        self.assertGreater(r["snap_distance_m"], solar._FAR_SNAP_M)
        self.assertTrue(r["far_snap"])
        self.assertTrue(any("neighbouring building" in ln for ln in r["lines"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
