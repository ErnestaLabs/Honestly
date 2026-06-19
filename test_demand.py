#!/usr/bin/env python3
"""Offline tests for demand.py - geo, land_registry and reddit_intel are stubbed.

The honesty point under test: demand is a beside-the-figure read assembled from
official transaction counts plus sentiment, and it NEVER raises even when every
dependency is down.
"""
import datetime
import unittest
from unittest import mock
import demand


def _recent(days_ago):
    return (datetime.date.today() - datetime.timedelta(days=days_ago)).isoformat()


_NEAREST = {"ok": True, "postcode": "SE15 6JH", "neighbours": [
    {"postcode": "SE15 6JH", "dist_m": 0},
    {"postcode": "SE15 6JG", "dist_m": 120},
    {"postcode": "SE15 6JF", "dist_m": 200},
    {"postcode": "SE15 6JE", "dist_m": 260},
]}


def _ppd_factory(counts):
    """Return a fake ppd_postcode that yields `counts[pc]` recent sales per postcode."""
    def fake(pc, **kw):
        n = counts.get(pc, 0)
        return {"ok": True, "postcode": pc,
                "sales": [{"date": _recent(30 + i)} for i in range(n)]}
    return fake


class TestLabel(unittest.TestCase):
    def test_busier(self):
        self.assertEqual(demand._label(6, [2, 2, 2])[0], "busier than nearby streets")

    def test_quieter(self):
        self.assertEqual(demand._label(1, [3, 3, 3])[0], "quieter than nearby streets")

    def test_in_line(self):
        self.assertEqual(demand._label(3, [3, 3, 3])[0], "in line with nearby streets")

    def test_active_in_quiet_cluster(self):
        self.assertEqual(demand._label(2, [0, 0])[0], "active where the cluster is quiet")

    def test_no_neighbours(self):
        self.assertEqual(demand._label(5, [])[0], "no comparable neighbours")


class TestCutoff(unittest.TestCase):
    def test_cutoff_is_in_the_past_and_iso(self):
        c = demand._cutoff(24)
        self.assertRegex(c, r"^\d{4}-\d{2}-\d{2}$")
        self.assertLess(c, datetime.date.today().isoformat())


_SECTOR_OK = {"ok": True, "count": 47, "n_postcodes": 4,
              "source": "HM Land Registry Price Paid Data (SPARQL count, OGL)"}
_SECTOR_DOWN = {"ok": False, "reason": "HMLR SPARQL HTTP 503"}


class TestSectorOf(unittest.TestCase):
    def test_sector_extraction(self):
        self.assertEqual(demand._sector_of("SE15 6JH"), "SE15 6")
        self.assertEqual(demand._sector_of("se15 6jh"), "SE15 6")
        self.assertEqual(demand._sector_of("N1 9GU"), "N1 9")

    def test_no_inward_part_returns_none(self):
        self.assertIsNone(demand._sector_of("SE15"))
        self.assertIsNone(demand._sector_of(""))
        self.assertIsNone(demand._sector_of(None))


class TestForPostcode(unittest.TestCase):
    def test_busier_area_with_sentiment(self):
        counts = {"SE15 6JH": 6, "SE15 6JG": 2, "SE15 6JF": 2, "SE15 6JE": 2}
        with mock.patch.object(demand.geo, "nearest", return_value=_NEAREST), \
             mock.patch.object(demand.lr, "ppd_postcode", side_effect=_ppd_factory(counts)), \
             mock.patch.object(demand.lr, "ppd_count", return_value=_SECTOR_OK), \
             mock.patch.object(demand.reddit_intel, "for_area",
                               return_value={"sentiment": "positive", "signal_count": 7}):
            d = demand.for_postcode("SE15 6JH")
        self.assertTrue(d["ok"])
        self.assertEqual(d["subject_count"], 6)
        self.assertEqual(d["relative"], "busier than nearby streets")
        self.assertEqual(d["area_total"], 12)
        self.assertEqual(d["sector"]["count"], 47)
        self.assertEqual(d["sector"]["sector"], "SE15 6")
        self.assertEqual(d["confidence"], "good")        # sector volume drives confidence
        self.assertEqual(d["sentiment"]["read"], "positive")
        self.assertIn("does not move the valuation", d["note"])
        self.assertIn("SE15 6 sector", d["note"])

    def test_geo_failure_degrades(self):
        with mock.patch.object(demand.geo, "nearest",
                               return_value={"ok": False, "reason": "postcode not found"}):
            d = demand.for_postcode("ZZ99 9ZZ")
        self.assertFalse(d["ok"])
        self.assertIn("geo", d["reason"])

    def test_subject_registry_failure_degrades(self):
        with mock.patch.object(demand.geo, "nearest", return_value=_NEAREST), \
             mock.patch.object(demand.lr, "ppd_postcode",
                               return_value={"ok": False, "reason": "HMLR down"}):
            d = demand.for_postcode("SE15 6JH")
        self.assertFalse(d["ok"])

    def test_sentiment_source_raising_is_swallowed(self):
        counts = {"SE15 6JH": 3, "SE15 6JG": 3, "SE15 6JF": 3, "SE15 6JE": 3}
        with mock.patch.object(demand.geo, "nearest", return_value=_NEAREST), \
             mock.patch.object(demand.lr, "ppd_postcode", side_effect=_ppd_factory(counts)), \
             mock.patch.object(demand.lr, "ppd_count", return_value=_SECTOR_OK), \
             mock.patch.object(demand.reddit_intel, "for_area", side_effect=Exception("mcp down")):
            d = demand.for_postcode("SE15 6JH")
        self.assertTrue(d["ok"])                 # never raises on a down MCP
        self.assertNotIn("sentiment", d)
        self.assertEqual(d["relative"], "in line with nearby streets")

    def test_low_confidence_flagged_on_thin_sector(self):
        counts = {"SE15 6JH": 1, "SE15 6JG": 1, "SE15 6JF": 0, "SE15 6JE": 0}
        thin = {"ok": True, "count": 6, "n_postcodes": 4}      # sector volume still thin
        with mock.patch.object(demand.geo, "nearest", return_value=_NEAREST), \
             mock.patch.object(demand.lr, "ppd_postcode", side_effect=_ppd_factory(counts)), \
             mock.patch.object(demand.lr, "ppd_count", return_value=thin), \
             mock.patch.object(demand.reddit_intel, "for_area", return_value={}):
            d = demand.for_postcode("SE15 6JH")
        self.assertEqual(d["confidence"], "low")
        self.assertIn("directional", d["note"])

    def test_sector_down_falls_back_to_ring(self):
        counts = {"SE15 6JH": 3, "SE15 6JG": 3, "SE15 6JF": 3, "SE15 6JE": 3}
        with mock.patch.object(demand.geo, "nearest", return_value=_NEAREST), \
             mock.patch.object(demand.lr, "ppd_postcode", side_effect=_ppd_factory(counts)), \
             mock.patch.object(demand.lr, "ppd_count", return_value=_SECTOR_DOWN), \
             mock.patch.object(demand.reddit_intel, "for_area", return_value={}):
            d = demand.for_postcode("SE15 6JH")
        self.assertTrue(d["ok"])                 # sector down never breaks the read
        self.assertIsNone(d["sector"])
        self.assertNotIn("sector since", d["note"])   # no sector lead when unavailable
        # confidence falls back to the ring total (12 -> medium)
        self.assertEqual(d["confidence"], "medium")

    def test_sector_count_raising_is_swallowed(self):
        counts = {"SE15 6JH": 3, "SE15 6JG": 3, "SE15 6JF": 3, "SE15 6JE": 3}
        with mock.patch.object(demand.geo, "nearest", return_value=_NEAREST), \
             mock.patch.object(demand.lr, "ppd_postcode", side_effect=_ppd_factory(counts)), \
             mock.patch.object(demand.lr, "ppd_count", side_effect=Exception("sparql down")), \
             mock.patch.object(demand.reddit_intel, "for_area", return_value={}):
            d = demand.for_postcode("SE15 6JH")
        self.assertTrue(d["ok"])
        self.assertIsNone(d["sector"])


class TestBrief(unittest.TestCase):
    def test_brief_empty_on_failure(self):
        self.assertEqual(demand.brief({"ok": False}), "")
        self.assertEqual(demand.brief(None), "")

    def test_brief_renders(self):
        d = {"ok": True, "relative": "busier than nearby streets", "subject_count": 6,
             "since": "2024-06-01", "confidence": "good", "sentiment": {"read": "positive"}}
        b = demand.brief(d)
        self.assertIn("busier than nearby streets", b)
        self.assertIn("Chatter: positive", b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
