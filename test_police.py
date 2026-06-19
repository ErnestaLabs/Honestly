#!/usr/bin/env python3
"""Offline tests for police.py - the network layer (_get_json) is stubbed.

Honesty point: street-level crime is area context beside the figure; the client
summarises by category and degrades to {ok: False} / never raises when the endpoint
is down.
"""
import unittest
from unittest import mock
import police


_ROWS = [
    {"category": "anti-social-behaviour", "month": "2026-04"},
    {"category": "anti-social-behaviour", "month": "2026-04"},
    {"category": "violent-crime", "month": "2026-04"},
    {"category": "burglary", "month": "2026-04"},
]


class TestCrimes(unittest.TestCase):
    def test_summarises_by_category(self):
        with mock.patch.object(police, "_get_json", return_value=_ROWS):
            r = police.crimes(51.5194, -0.0935)
        self.assertTrue(r["ok"])
        self.assertEqual(r["total"], 4)
        self.assertEqual(r["month"], "2026-04")
        top = dict(r["by_category"])
        self.assertEqual(top["Anti social behaviour"], 2)
        self.assertEqual(r["by_category"][0][0], "Anti social behaviour")  # most common first

    def test_no_coordinates_degrades(self):
        self.assertFalse(police.crimes(None, None)["ok"])

    def test_empty_is_ok_zero(self):
        with mock.patch.object(police, "_get_json", return_value=[]):
            r = police.crimes(51.5, -0.09)
        self.assertTrue(r["ok"])
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["by_category"], [])

    def test_unexpected_response_degrades(self):
        with mock.patch.object(police, "_get_json", return_value={"oops": 1}):
            r = police.crimes(51.5, -0.09)
        self.assertFalse(r["ok"])

    def test_http_error_degrades(self):
        import urllib.error
        err = urllib.error.HTTPError("u", 503, "down", {}, None)
        with mock.patch.object(police, "_get_json", side_effect=err):
            r = police.crimes(51.5, -0.09)
        self.assertFalse(r["ok"])
        self.assertIn("503", r["reason"])

    def test_network_error_never_raises(self):
        with mock.patch.object(police, "_get_json", side_effect=Exception("boom")):
            r = police.crimes(51.5, -0.09)
        self.assertFalse(r["ok"])
        self.assertIn("boom", r["reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
