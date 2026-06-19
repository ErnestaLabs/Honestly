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
        {"tx": {"value": "http://landregistry.data.gov.uk/data/ppi/transaction/TX58/current"},
         "paon": {"value": "58"}, "street": {"value": "CRONIN STREET"},
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
        self.assertEqual(r["sales"][0]["hmlr_uri"],
                         "http://landregistry.data.gov.uk/data/ppi/transaction/TX58/current")

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


_COUNT_JSON = {"results": {"bindings": [{"n": {"value": "47"}}]}}


class TestPPDCount(unittest.TestCase):
    def test_parses_count(self):
        with mock.patch.object(lr, "_post_sparql", return_value=_COUNT_JSON) as m:
            r = lr.ppd_count(["SE15 6JH", "SE15 6JG", "SE15 6JF"])
        self.assertTrue(r["ok"])
        self.assertEqual(r["count"], 47)
        self.assertEqual(r["n_postcodes"], 3)
        self.assertIsNone(r["since"])
        # postcodes are bound via VALUES (indexed), not a STRSTARTS prefix scan
        q = m.call_args[0][0]
        self.assertIn("VALUES ?postcode", q)
        self.assertIn('"SE15 6JH"', q)
        self.assertNotIn("STRSTARTS", q)

    def test_since_adds_date_filter(self):
        with mock.patch.object(lr, "_post_sparql", return_value=_COUNT_JSON) as m:
            r = lr.ppd_count(["SE15 6JH"], since="2024-06-01")
        self.assertEqual(r["since"], "2024-06-01")
        q = m.call_args[0][0]
        self.assertIn('FILTER(?date >= "2024-06-01"^^xsd:date)', q)

    def test_no_since_omits_filter(self):
        with mock.patch.object(lr, "_post_sparql", return_value=_COUNT_JSON) as m:
            lr.ppd_count(["SE15 6JH"])
        self.assertNotIn("FILTER", m.call_args[0][0])

    def test_normalises_and_dedupes(self):
        with mock.patch.object(lr, "_post_sparql", return_value=_COUNT_JSON) as m:
            r = lr.ppd_count(["se156jh", "SE15 6JH", "  se15 6jg "])
        self.assertEqual(r["n_postcodes"], 2)   # the two SE15 6JH spellings collapse to one
        q = m.call_args[0][0]
        self.assertIn('"SE15 6JH"', q)
        self.assertIn('"SE15 6JG"', q)

    def test_caps_the_values_list(self):
        many = [f"SE15 {i}AA" for i in range(200)]
        with mock.patch.object(lr, "_post_sparql", return_value=_COUNT_JSON):
            r = lr.ppd_count(many, cap=150)
        self.assertEqual(r["n_postcodes"], 150)

    def test_empty_input_degrades(self):
        r = lr.ppd_count([])
        self.assertFalse(r["ok"])
        self.assertIn("no postcodes", r["reason"])

    def test_no_bindings_is_ok_zero(self):
        with mock.patch.object(lr, "_post_sparql", return_value={"results": {"bindings": []}}):
            r = lr.ppd_count(["SE15 6JH"])
        self.assertTrue(r["ok"])
        self.assertEqual(r["count"], 0)

    def test_unparseable_count_degrades(self):
        bad = {"results": {"bindings": [{"n": {"value": "not-a-number"}}]}}
        with mock.patch.object(lr, "_post_sparql", return_value=bad):
            r = lr.ppd_count(["SE15 6JH"])
        self.assertFalse(r["ok"])
        self.assertIn("unparseable", r["reason"])

    def test_http_error_degrades(self):
        import urllib.error
        err = urllib.error.HTTPError("u", 503, "down", {}, None)
        with mock.patch.object(lr, "_post_sparql", side_effect=err):
            r = lr.ppd_count(["SE15 6JH"])
        self.assertFalse(r["ok"])
        self.assertIn("503", r["reason"])

    def test_network_error_degrades_never_raises(self):
        with mock.patch.object(lr, "_post_sparql", side_effect=Exception("boom")):
            r = lr.ppd_count(["SE15 6JH"])
        self.assertFalse(r["ok"])
        self.assertIn("boom", r["reason"])

    def test_cache_round_trips_and_avoids_second_call(self):
        lr._COUNT_CACHE.clear()
        with mock.patch.object(lr, "_post_sparql", return_value=_COUNT_JSON) as m:
            r1 = lr.ppd_count(["SE15 6JH", "SE15 6JG"], use_cache=True)
            r2 = lr.ppd_count(["SE15 6JG", "SE15 6JH"], use_cache=True)  # order-insensitive key
        self.assertEqual(r1, r2)
        self.assertEqual(m.call_count, 1)       # second read served from cache
        lr._COUNT_CACHE.clear()


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
