#!/usr/bin/env python3
"""Offline tests for overpass.py - the network layer (_run) is stubbed.

Honesty point: amenity/transport counts are area context beside the figure; the client
classifies OSM elements into buckets, lists nearest named stops, and degrades to
{ok: False} / never raises when the endpoint is down.
"""
import unittest
from unittest import mock
import overpass


_ELEMENTS = {"elements": [
    {"tags": {"railway": "station", "name": "Old Street"}, "lat": 51.5258, "lon": -0.0876},
    {"tags": {"railway": "station", "name": "Moorgate"}, "lat": 51.5186, "lon": -0.0886},
    {"tags": {"highway": "bus_stop"}, "lat": 51.519, "lon": -0.093},
    {"tags": {"amenity": "school", "name": "A School"}, "lat": 51.52, "lon": -0.094},
    {"tags": {"shop": "supermarket", "name": "Tesco"}, "lat": 51.52, "lon": -0.092},
    {"tags": {"amenity": "cafe"}, "lat": 51.519, "lon": -0.0925},
    {"tags": {"leisure": "park", "name": "Bunhill"}, "center": {"lat": 51.523, "lon": -0.0905}},
    {"tags": {"amenity": "pharmacy"}, "lat": 51.5195, "lon": -0.0931},
]}


class TestAmenities(unittest.TestCase):
    def test_counts_and_classifies(self):
        with mock.patch.object(overpass, "_run", return_value=_ELEMENTS):
            r = overpass.amenities(51.519, -0.0935)
        self.assertTrue(r["ok"])
        c = r["counts"]
        self.assertEqual(c["Stations"], 2)
        self.assertEqual(c["Bus stops"], 1)
        self.assertEqual(c["Schools"], 1)
        self.assertEqual(c["Supermarkets"], 1)
        self.assertEqual(c["Cafes & restaurants"], 1)
        self.assertEqual(c["Green space"], 1)
        self.assertEqual(c["GP & pharmacy"], 1)

    def test_transport_sorted_nearest_first(self):
        with mock.patch.object(overpass, "_run", return_value=_ELEMENTS):
            r = overpass.amenities(51.519, -0.0935)
        names = [t["name"] for t in r["transport"]]
        self.assertEqual(names[0], "Moorgate")     # closer than Old Street to the point
        self.assertTrue(all("dist_m" in t for t in r["transport"]))

    def test_no_coordinates_degrades(self):
        self.assertFalse(overpass.amenities(None, None)["ok"])

    def test_empty_reports_none_found(self):
        with mock.patch.object(overpass, "_run", return_value={"elements": []}):
            r = overpass.amenities(51.519, -0.0935)
        self.assertTrue(r["ok"])
        self.assertFalse(any(r["counts"].values()))
        self.assertTrue(any("No mapped amenities" in ln for ln in r["lines"]))

    def test_http_error_degrades(self):
        import urllib.error
        err = urllib.error.HTTPError("u", 504, "timeout", {}, None)
        with mock.patch.object(overpass, "_run", side_effect=err):
            r = overpass.amenities(51.519, -0.0935)
        self.assertFalse(r["ok"])
        self.assertIn("504", r["reason"])

    def test_network_error_never_raises(self):
        with mock.patch.object(overpass, "_run", side_effect=Exception("boom")):
            r = overpass.amenities(51.519, -0.0935)
        self.assertFalse(r["ok"])
        self.assertIn("boom", r["reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
