#!/usr/bin/env python3
"""Offline tests for price_ledger.py - the Pro price-influence ledger (build #71).

The honesty contract under test (PRODUCT_SPEC sections 4 + 6):
  * Exactly the three real movers carry moves_figure=True: the sold/AVM anchor, the condition
    lever, and the capped live-market steer. NOTHING else is allowed to claim it moved the
    figure (the Chimnie AVM may, but ONLY when explicitly anchored).
  * Every factor carries a source and a direction; the ledger READS what is in the summary +
    area context and never invents a value - a factor with no data is simply absent.
  * The steer direction follows the real sign of market.pct; it is the only area signal in
    the number.
  * Degrades honestly: an incomplete figure returns {ok: False}.
  * lines() renders with no stray "None".
No network, no spend.
"""
import unittest

import price_ledger
import engine
from unittest import mock


def _summary(**over):
    d = {
        "low": 590000, "high": 650000, "central": 620000, "guide": 600000,
        "sold_anchor_str": "£610,000", "sold_median_str": "£605,000", "epc": "C",
        "market": {"pct": 3.0, "label": "Rising market", "note": "disclosed +3% steer."},
        "positioning": {"stuck": 2, "listings": 5, "median_ask": 640000},
        "macro": {"momentum": {"headline": "Bank Rate held; prices rising modestly."}},
        "crosscheck": {"official_median": 608000, "official_median_str": "£608,000",
                       "divergence_pct": -0.5, "source": "HM Land Registry PPD (SPARQL, OGL)"},
        "street_enrichment": {"epc_rating": "C", "epc_potential": "B", "lease_term": "Freehold",
                              "flood_risk": "Very Low", "neighbour_psm_median": 6700,
                              "neighbour_sale_count": 9},
        "chimnie_enrichment": {"avm_estimate": 615000, "avm_confidence": 0.86, "anchored": False,
                               "solar_potential": "Medium", "subsidence": "No risk recorded",
                               "rebuild_cost": 410000},
    }
    d.update(over)
    return d


CTX = {"sections": {
    "environment": {"flood": {"severity": "Very Low"}, "air": {"band": "Low", "aqi": 2}},
    "safety": {"total": 41, "month": "2026-04"},
    "planning": {"total": 7},
    "area": {"counts": {"shop": 12}, "radius_m": 800,
             "transport": [{"name": "Peckham Rye", "dist_m": 300}]},
    "location": {"legs": [{"label": "City", "time": "24 min"}]},
}}


class TestPriceLedger(unittest.TestCase):
    def test_incomplete_figure_degrades(self):
        self.assertFalse(price_ledger.build({"low": 1})["ok"])
        self.assertFalse(price_ledger.build(None)["ok"])

    def test_exactly_three_movers_by_default(self):
        led = price_ledger.build(_summary())
        keys = {m["key"] for m in led["movers"]}
        self.assertEqual(keys, {"anchor", "condition", "market_steer"})
        # the Chimnie AVM is NOT a mover unless explicitly anchored
        self.assertNotIn("chimnie_avm", keys)

    def test_only_movers_have_moves_figure_true(self):
        led = price_ledger.build(_summary(), context=CTX)
        for f in led["factors"]:
            if f["key"] in ("anchor", "condition", "market_steer"):
                self.assertTrue(f["moves_figure"], f["key"])
            else:
                self.assertFalse(f["moves_figure"], f["key"])

    def test_commercial_second_model_is_not_a_mover(self):
        d = _summary()
        d["chimnie_enrichment"] = dict(d["chimnie_enrichment"], anchored=True)
        led = price_ledger.build(d)
        keys = {f["key"] for f in led["factors"]}
        self.assertNotIn("chimnie_avm", keys)
        self.assertNotIn("chimnie_avm", {m["key"] for m in led["movers"]})

    def test_steer_direction_follows_pct_sign(self):
        up = price_ledger.build(_summary(market={"pct": 4.0, "label": "Rising"}))
        dn = price_ledger.build(_summary(market={"pct": -3.0, "label": "Softening"}))
        flat = price_ledger.build(_summary(market={"pct": 0.0, "label": "Balanced"}))
        sdir = lambda led: next(f for f in led["movers"] if f["key"] == "market_steer")["direction"]
        self.assertEqual(sdir(up), "up")
        self.assertEqual(sdir(dn), "down")
        self.assertEqual(sdir(flat), "neutral")

    def test_every_factor_has_source_and_direction(self):
        led = price_ledger.build(_summary(), context=CTX)
        for f in led["factors"]:
            self.assertTrue(f["source"], f["key"])
            self.assertIn(f["direction"], ("anchor", "up", "down", "neutral", "context"), f["key"])

    def test_absent_data_means_absent_factor(self):
        # a bare figure with no enrichment and no context: only the movers that need no extra
        # data (anchor, condition, steer) appear; no fabricated area/enrichment factors.
        led = price_ledger.build({"low": 590000, "high": 650000, "central": 620000,
                                  "guide": 600000, "market": {"pct": 0.0, "label": "Balanced"}})
        keys = {f["key"] for f in led["factors"]}
        self.assertEqual(keys, {"anchor", "condition", "market_steer"})
        for absent in ("flood", "crime", "planning", "solar", "lease", "amenities", "demand"):
            self.assertNotIn(absent, keys)

    def test_short_lease_is_a_drag_long_or_freehold_is_not(self):
        short = _summary()
        short["street_enrichment"] = dict(short["street_enrichment"], lease_term="62 years")
        led = price_ledger.build(short)
        lease = next(f for f in led["factors"] if f["key"] == "lease")
        self.assertEqual(lease["direction"], "down")
        # freehold (default) is neutral, not a premium claim
        led2 = price_ledger.build(_summary())
        lease2 = next(f for f in led2["factors"] if f["key"] == "lease")
        self.assertEqual(lease2["direction"], "neutral")

    def test_poor_epc_is_a_drag_good_epc_supports(self):
        good = price_ledger.build(_summary())
        poor = _summary()
        poor["street_enrichment"] = dict(poor["street_enrichment"], epc_rating="F")
        poor["epc"] = "F"
        bad = price_ledger.build(poor)
        gdir = next(f for f in good["factors"] if f["key"] == "epc")["direction"]
        bdir = next(f for f in bad["factors"] if f["key"] == "epc")["direction"]
        self.assertEqual(gdir, "up")
        self.assertEqual(bdir, "down")

    def test_context_adds_area_factors(self):
        bare = price_ledger.build(_summary())
        rich = price_ledger.build(_summary(), context=CTX)
        bare_keys = {f["key"] for f in bare["factors"]}
        rich_keys = {f["key"] for f in rich["factors"]}
        for added in ("flood", "air_quality", "crime", "planning", "connectivity", "amenities"):
            self.assertIn(added, rich_keys)
        self.assertTrue(rich_keys > bare_keys)

    def test_raw_crime_count_is_context_not_a_direction(self):
        led = price_ledger.build(_summary(), context=CTX)
        crime = next(f for f in led["factors"] if f["key"] == "crime")
        self.assertEqual(crime["direction"], "context")   # a raw count has no honest polarity

    def test_lines_render_without_none(self):
        led = price_ledger.build(_summary(), context=CTX)
        out = "\n".join(price_ledger.lines(led))
        self.assertIn("Price-influence ledger", out)
        self.assertIn("Moved the figure", out)
        self.assertNotIn("None", out)

    def test_lines_empty_on_unavailable(self):
        self.assertEqual(price_ledger.lines({"ok": False}), [])
        self.assertEqual(price_ledger.lines(None), [])


class TestLedgerWiredIntoSummary(unittest.TestCase):
    """The ledger is attached to the Pro summary and absent from Lite - and attaching it never
    moves the figure (honesty rule 1)."""
    def setUp(self):
        for name, val in (("outlook", None), ("txn_link", "")):
            p = mock.patch.object(engine, name, return_value=val)
            p.start(); self.addCleanup(p.stop)

    def _result(self):
        return {
            "subject": {"address": "58 Cronin Street, London SE15 6JH", "beds": 4, "sqm": 92},
            "valuation": {"low": 590000, "high": 650000, "central": 620000, "guide": 600000,
                          "psmA": 6700, "market": {"pct": 2.0, "label": "Rising market",
                                                   "note": "disclosed +2% steer."},
                          "sold_anchor": 610000},
            "positioning": None, "compsA": [], "n_candidates": 8, "n_screened": 5,
        }

    def test_pro_carries_ledger_lite_does_not(self):
        lite = engine.summary(self._result(), audience="vendor", tier="lite")
        pro = engine.summary(self._result(), audience="vendor", tier="pro")
        self.assertNotIn("price_ledger", lite)
        self.assertIn("price_ledger", pro)
        self.assertTrue(pro["price_ledger"]["ok"])
        # the figure is untouched by attaching the ledger
        self.assertEqual((pro["low"], pro["high"], pro["central"], pro["guide"]),
                         (590000, 650000, 620000, 600000))


if __name__ == "__main__":
    unittest.main(verbosity=2)
