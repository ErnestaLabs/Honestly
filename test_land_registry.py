#!/usr/bin/env python3
"""Offline tests for land_registry.py - fully stubbed, deterministic, no network.

Mirrors test_bot.py's posture: the network layer (_post_sparql / _get_json) is
patched, so these run anywhere and never depend on HM Land Registry being up.
The live behaviour is checked separately via `python land_registry.py selftest`.
"""
import unittest
from unittest import mock
import land_registry as lr


# ---- canned SPARQL + REST payloads -------------------------------------------
_PPD_JSON = {
    "results": {"bindings": [
        {"paon": {"value": "58"}, "street": {"value": "CRONIN STREET"},
         "town": {"value": "LONDON"}, "amount": {"value": "310000"},
         "date": {"value": "2025-08-12"}, "category": {"value": "Standard Price Paid"},
         "type": {"value": "Terraced"}},
        {"paon": {"value": "60"}, "street": {"value": "CRONIN STREET"},
         "town": {"value": "LONDON"}, "amount": {"value": "285000"},
         "date": {"value": "2024-02-01"}, "category": {"value": "Standard Price Paid"},
         "type": {"value": "Terraced"}},
        {"paon": {"value": "62"}, "amount": {"value": "297500"},
         "date": {"value": "2023-11-09"}, "category": {"value": "Standard Price Paid"}},
    ]}
}
_HPI_MONTH_JSON = {
    "result": {"primaryTopic": {
        "refPeriodStart": "Sun, 01 Mar 2026", "averagePrice": 542065,
        "housePriceIndex": 95.0, "percentageAnnualChange": -2.1,
        "percentageChange": -0.4,
    }}
}
_HPI_LIST_JSON = {
    "result": {"items": [
        "http://landregistry.data.gov.uk/data/ukhpi/region/london/month/2026-03",
        "http://landregistry.data.gov.uk/data/ukhpi/region/london/month/2026-02",
        "http://landregistry.data.gov.uk/data/ukhpi/region/london/month/2026-01",
    ]}
}


class TestNormPostcode(unittest.TestCase):
    def test_inserts_single_space(self):
        self.assertEqual(lr._norm_pc("se156jh"), "SE15 6JH")
        self.assertEqual(lr._norm_pc("  N22 5SU "), "N22 5SU")
        self.assertEqual(lr._norm_pc("SW1A1AA"), "SW1A 1AA")

    def test_empty(self):
        self.assertEqual(lr._norm_pc(""), "")
        self.assertEqual(lr._norm_pc(None), "")


class TestPPD(unittest.TestCase):
    def test_parses_and_aggregates(self):
        with mock.patch.object(lr, "_post_sparql", return_value=_PPD_JSON):
            r = lr.ppd_postcode("SE15 6JH")
        self.assertTrue(r["ok"])
        self.assertEqual(r["count"], 3)
        self.assertEqual(r["median"], 297500)   # median of 310000/285000/297500
        self.assertEqual(r["low"], 285000)
        self.assertEqual(r["high"], 310000)
        self.assertEqual(r["oldest"], "2023-11-09")
        self.assertEqual(r["newest"], "2025-08-12")
        self.assertEqual(r["sales"][0]["address"], "58, CRONIN STREET, LONDON")
        self.assertEqual(r["sales"][0]["price"], 310000)

    def test_empty_bindings_is_ok_zero(self):
        with mock.patch.object(lr, "_post_sparql", return_value={"results": {"bindings": []}}):
            r = lr.ppd_postcode("ZZ99 9ZZ")
        self.assertTrue(r["ok"])
        self.assertEqual(r["count"], 0)
        self.assertEqual(r["sales"], [])

    def test_no_postcode(self):
        self.assertFalse(lr.ppd_postcode("")["ok"])

    def test_network_error_degrades_never_raises(self):
        with mock.patch.object(lr, "_post_sparql", side_effect=Exception("boom")):
            r = lr.ppd_postcode("SE15 6JH")
        self.assertFalse(r["ok"])
        self.assertIn("boom", r["reason"])

    def test_garbage_amount_skipped(self):
        bad = {"results": {"bindings": [
            {"amount": {"value": "not-a-number"}, "date": {"value": "2025-01-01"}},
            {"amount": {"value": "250000"}, "date": {"value": "2025-01-02"}},
        ]}}
        with mock.patch.object(lr, "_post_sparql", return_value=bad):
            r = lr.ppd_postcode("SE15 6JH")
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["median"], 250000)


class TestHPI(unittest.TestCase):
    def test_month_from_ref(self):
        self.assertEqual(lr._month_from_ref("Sun, 01 Mar 2026"), "2026-03")
        self.assertEqual(lr._month_from_ref("Mon, 01 Dec 2025"), "2025-12")
        self.assertIsNone(lr._month_from_ref("garbage"))

    def test_latest_month_from_uri_items(self):
        with mock.patch.object(lr, "_get_json", return_value=_HPI_LIST_JSON):
            self.assertEqual(lr._latest_month("london"), "2026-03")

    def test_region_explicit_month(self):
        with mock.patch.object(lr, "_get_json", return_value=_HPI_MONTH_JSON):
            r = lr.hpi_region("london", "2026-03")
        self.assertTrue(r["ok"])
        self.assertEqual(r["average_price"], 542065.0)
        self.assertEqual(r["annual_change_pct"], -2.1)
        self.assertEqual(r["month"], "2026-03")

    def test_region_resolves_latest_when_no_month(self):
        # first _get_json call = listing, second = the month record
        with mock.patch.object(lr, "_get_json", side_effect=[_HPI_LIST_JSON, _HPI_MONTH_JSON]):
            r = lr.hpi_region("london")
        self.assertTrue(r["ok"])
        self.assertEqual(r["month"], "2026-03")
        self.assertEqual(r["average_price"], 542065.0)

    def test_no_region(self):
        self.assertFalse(lr.hpi_region("")["ok"])

    def test_unresolvable_month_degrades(self):
        with mock.patch.object(lr, "_get_json", return_value={"result": {"items": []}}):
            r = lr.hpi_region("nowhere-land")
        self.assertFalse(r["ok"])
        self.assertIn("could not resolve", r["reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
