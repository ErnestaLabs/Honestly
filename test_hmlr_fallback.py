#!/usr/bin/env python3
"""Offline tests for the free HM Land Registry sold fallback - no network.

The defect this locks: central, commercial-heavy England/Wales outcodes (M2, B2) carry
plenty of recorded residential sales, but the PAID PropertyData feed returns nothing for
them, so the district published a false 'no sold records'. The fix: when PropertyData has
no sold rows after widening, fall back to the FREE official HMLR Price Paid register, which
holds those sales. These tests assert the fallback builds a real sold block from synthetic
register rows, maps property types correctly, drops commercial 'other', credits HMLR (not
PropertyData) in the provenance flags, and never fires for Scotland (HMLR Price Paid is
England & Wales only).
"""
import unittest

import market_district as md


_REGISTER_ROWS = [
    {"address": "FLAT 1, A TOWER", "price": 385000, "date": "2025-09-01",
     "category": "Standard price paid transaction", "type": "flat-maisonette", "postcode": "M2 4AA"},
    {"address": "FLAT 2, A TOWER", "price": 395000, "date": "2024-03-10",
     "category": "Additional price paid transaction", "type": "flat-maisonette", "postcode": "M2 4AA"},
    {"address": "3 SOME STREET", "price": 950000, "date": "2023-06-20",
     "category": "Standard price paid transaction", "type": "terraced", "postcode": "M2 4AB"},
    {"address": "4 OTHER ROAD", "price": 377000, "date": "2020-01-05",
     "category": "Standard price paid transaction", "type": "detached", "postcode": "M2 4AC"},
    # commercial - must be dropped from a homes median
    {"address": "FIFTH FLOOR, BIG BLOCK", "price": 3361680, "date": "2022-11-18",
     "category": "Additional price paid transaction", "type": "other", "postcode": "M2 4AD"},
    # unpriced / untyped - must be skipped, never raise
    {"address": "NO PRICE", "price": None, "date": "2025-01-01",
     "category": "Standard price paid transaction", "type": "flat-maisonette", "postcode": "M2 4AA"},
]


class HmlrFallbackBuildsRealBlock(unittest.TestCase):
    def setUp(self):
        self._enum = md.geo.outcode_postcodes
        self._area = md.land_registry.ppd_area
        md.geo.outcode_postcodes = lambda oc, **k: {"ok": True, "outcode": oc,
                                                    "postcodes": ["M2 4AA", "M2 4AB", "M2 4AC", "M2 4AD"]}
        md.land_registry.ppd_area = lambda pcs, **k: {"ok": True, "count": len(_REGISTER_ROWS),
                                                      "n_postcodes": len(pcs), "sales": list(_REGISTER_ROWS)}

    def tearDown(self):
        md.geo.outcode_postcodes = self._enum
        md.land_registry.ppd_area = self._area

    def test_builds_homes_median_dropping_commercial(self):
        b = md._sold_block_hmlr("M2", "England")
        self.assertTrue(b.get("ok"), b)
        self.assertEqual(b["fallback"], "hmlr_direct")
        self.assertIn("Land Registry", b["source"])
        # 4 residential rows kept (2 flats, 1 terraced, 1 detached); 'other' + unpriced dropped
        self.assertEqual(b["total"], 4)
        # the £3.36m commercial sale must NOT be in the price range
        self.assertLess(b["price_high"], 1_000_000)
        # the free register carries no floor area, so price-per-sqm is honestly absent
        self.assertIsNone(b["psm_median"])
        self.assertEqual(b["recency"]["window_months"], md._HMLR_WINDOW_MONTHS)

    def test_type_mapping_to_our_slugs(self):
        b = md._sold_block_hmlr("M2", "England")
        by = {r["type"]: r["n"] for r in b["by_type"]}
        self.assertEqual(by["flat"], 2)
        self.assertEqual(by["terraced_house"], 1)
        self.assertEqual(by["detached_house"], 1)
        self.assertEqual(by["semi_detached_house"], 0)

    def test_scotland_never_uses_hmlr_price_paid(self):
        b = md._sold_block_hmlr("EH2", "Scotland")
        self.assertFalse(b.get("ok"))
        self.assertFalse(b.get("errored"))           # a coverage boundary, not an outage
        self.assertIn("does not cover", b["reason"])
        # crucially NOT confirmed-absent: HMLR cannot speak for Scotland, so EH2 must keep
        # deferring to PropertyData (its only Registers-of-Scotland source), never be skipped
        # as 'genuinely empty' on the strength of a register that does not cover it.
        self.assertFalse(b.get("confirmed_absent"))

    def test_no_residential_rows_is_honest_absence(self):
        md.land_registry.ppd_area = lambda pcs, **k: {"ok": True, "count": 1, "n_postcodes": 1,
                                                      "sales": [{"price": 100, "date": "2025-01-01",
                                                                 "type": "other", "postcode": "M2 4AD"}]}
        b = md._sold_block_hmlr("M2", "England")
        self.assertFalse(b.get("ok"))
        self.assertFalse(b.get("errored"))
        self.assertIn("no residential sales", b["reason"])
        # the register was actually queried and is empty for this E&W district -> CONFIRMED
        # absence, which the gather wiring uses to override a PropertyData provider error so
        # the gate skips the district honestly instead of deferring it forever.
        self.assertTrue(b.get("confirmed_absent"))

    def test_enumeration_failure_is_retryable_error(self):
        md.geo.outcode_postcodes = lambda oc, **k: {"ok": False, "reason": "postcodes.io down"}
        b = md._sold_block_hmlr("M2", "England")
        self.assertFalse(b.get("ok"))
        self.assertTrue(b.get("errored"))            # an outage, retry another day


if __name__ == "__main__":
    unittest.main()
