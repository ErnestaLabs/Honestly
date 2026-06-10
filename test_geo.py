#!/usr/bin/env python3
"""Offline tests for geo.py - the Postcodes.io network layer is stubbed."""
import os
import unittest
from unittest import mock
import urllib.error
import geo


_LOOKUP_JSON = {"result": {
    "postcode": "SE15 6JH", "latitude": 51.4673, "longitude": -0.0653,
    "admin_district": "Southwark", "admin_ward": "Peckham",
    "region": "London", "country": "England", "outcode": "SE15",
}}
_NEAREST_JSON = {"result": [
    {"postcode": "SE15 6JH", "distance": 0.0, "latitude": 51.4673, "longitude": -0.0653},
    {"postcode": "SE15 6JG", "distance": 121.4, "latitude": 51.4675, "longitude": -0.0650},
    {"postcode": "SE15 6JF", "distance": 204.8, "latitude": 51.4679, "longitude": -0.0644},
]}


def _httperror(code):
    return urllib.error.HTTPError("http://x", code, "msg", {}, None)


class TestBases(unittest.TestCase):
    def test_public_always_present(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEO_BASE", None)
            self.assertEqual(geo._bases(), [geo.PUBLIC])

    def test_local_first_when_set(self):
        with mock.patch.dict(os.environ, {"GEO_BASE": "http://localhost:8000/"}):
            self.assertEqual(geo._bases(), ["http://localhost:8000", geo.PUBLIC])


class TestLookup(unittest.TestCase):
    def test_parses(self):
        with mock.patch.object(geo, "_fetch", return_value=_LOOKUP_JSON):
            r = geo.lookup("SE15 6JH")
        self.assertTrue(r["ok"])
        self.assertEqual(r["district"], "Southwark")
        self.assertEqual(r["lat"], 51.4673)
        self.assertEqual(r["outcode"], "SE15")

    def test_no_postcode(self):
        self.assertFalse(geo.lookup("")["ok"])

    def test_404_is_not_found(self):
        with mock.patch.object(geo, "_fetch", side_effect=_httperror(404)):
            r = geo.lookup("ZZ99 9ZZ")
        self.assertFalse(r["ok"])
        self.assertIn("not found", r["reason"])

    def test_network_error_degrades_never_raises(self):
        with mock.patch.object(geo, "_fetch", side_effect=Exception("boom")):
            r = geo.lookup("SE15 6JH")
        self.assertFalse(r["ok"])
        self.assertIn("boom", r["reason"])


class TestNearest(unittest.TestCase):
    def test_parses_neighbours(self):
        with mock.patch.object(geo, "_fetch", return_value=_NEAREST_JSON):
            r = geo.nearest("SE15 6JH", 3)
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["neighbours"]), 3)
        self.assertEqual(r["neighbours"][0]["postcode"], "SE15 6JH")
        self.assertEqual(r["neighbours"][0]["dist_m"], 0)
        self.assertEqual(r["neighbours"][1]["dist_m"], 121)   # rounded

    def test_empty_result_degrades(self):
        with mock.patch.object(geo, "_fetch", return_value={"result": []}):
            r = geo.nearest("SE15 6JH")
        self.assertFalse(r["ok"])

    def test_no_postcode(self):
        self.assertFalse(geo.nearest("")["ok"])

    def test_network_error_degrades(self):
        with mock.patch.object(geo, "_fetch", side_effect=Exception("down")):
            r = geo.nearest("SE15 6JH")
        self.assertFalse(r["ok"])


class TestFetchFallback(unittest.TestCase):
    def test_falls_back_to_public_when_local_fails(self):
        calls = []

        def fake_get(url, timeout=15):
            calls.append(url)
            if "localhost" in url:
                raise Exception("local down")
            return _LOOKUP_JSON

        with mock.patch.dict(os.environ, {"GEO_BASE": "http://localhost:8000"}), \
             mock.patch.object(geo, "_get_json", side_effect=fake_get):
            d = geo._fetch("/postcodes/SE15%206JH")
        self.assertEqual(d, _LOOKUP_JSON)
        self.assertTrue(any("localhost" in u for u in calls))
        self.assertTrue(any("api.postcodes.io" in u for u in calls))


if __name__ == "__main__":
    unittest.main(verbosity=2)
