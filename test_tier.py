#!/usr/bin/env python3
"""Offline tests for the PRODUCT tier flag (lite | pro) in engine.summary() - build #68.

The locked product contract under test:
  * The FIGURE is identical in both tiers - sold evidence anchors low/high/central/guide
    either way. Lite is never thinner on the number, only on the surrounding arsenal.
  * Tier is the single source of truth for which decision context renders BESIDE the figure.
    Commercial same-data aggregator enrichment is never rendered.
  * Lite is the default - the free, excellent, lead-gen valuation.
  * tier is normalised (anything that is not "pro" is "lite"); out["tier"] always reflects it.

These make no network call and spend nothing - the macro/HMLR layers are neutralised, and
the enrichment is pre-attached to the subject exactly as appraise.find_subject would.
"""
import unittest
from unittest import mock

import engine


def _result():
    """A minimal engine.value() result. Commercial enrichment, if present on old fixtures,
    must not render in either tier."""
    comps = [
        {"address": "1 Cronin Street, London SE15 6JH", "sqm": 90, "price": 600000,
         "date": "2025-09-01", "score": 0.9, "dist": 0.1, "match": "strong"},
        {"address": "3 Cronin Street, London SE15 6JH", "sqm": 88, "price": 580000,
         "date": "2025-07-01", "score": 0.8, "dist": 0.2, "match": "good"},
    ]
    return {
        "subject": {
            "address": "58 Cronin Street, London SE15 6JH", "beds": 4, "sqm": 92,
            "street": {"confident": True,
                       "enrichment": {"council_tax_annual": 1611.0, "flood_risk": "Very Low"},
                       "neighbour_sales": [{"psm": 6600}, {"psm": 6800}]},
            "chimnie": {"source": "Chimnie (UK Property Data Bureau)",
                        "avm": {"estimate": 525000, "low": 498000, "high": 552000,
                                "confidence": 0.86},
                        "enrichment": {"council_tax_annual": 1611.0, "flood_risk": "Very Low",
                                       "solar_potential": "Medium"}},
        },
        "valuation": {"low": 590000, "high": 650000, "central": 620000, "guide": 600000,
                      "psmA": 6700, "market": None, "sold_anchor": 610000},
        "positioning": None,
        "compsA": comps,
        "n_candidates": 8, "n_screened": 5,
    }


def _figure(out):
    return (out["low"], out["high"], out["central"], out["guide"])


class TestTierFlag(unittest.TestCase):
    def setUp(self):
        # neutralise the macro + HMLR layers so these are pure-offline and deterministic
        for name, val in (("outlook", None), ("txn_link", "")):
            p = mock.patch.object(engine, name, return_value=val)
            p.start(); self.addCleanup(p.stop)
        # the figure summary() must reproduce in BOTH tiers
        self.baseline = (590000, 650000, 620000, 600000)

    def test_default_is_lite(self):
        out = engine.summary(_result(), audience="agent")
        self.assertEqual(out["tier"], "lite")

    def test_lite_hides_paid_enrichment(self):
        out = engine.summary(_result(), audience="agent", tier="lite")
        self.assertEqual(out["tier"], "lite")
        self.assertNotIn("street_enrichment", out)
        self.assertNotIn("chimnie_enrichment", out)

    def test_pro_never_renders_commercial_enrichment(self):
        out = engine.summary(_result(), audience="agent", tier="pro")
        self.assertEqual(out["tier"], "pro")
        self.assertNotIn("street_enrichment", out)
        self.assertNotIn("chimnie_enrichment", out)
        self.assertNotIn("patma_crosscheck", out)

    def test_figure_identical_across_tiers(self):
        lite = engine.summary(_result(), audience="agent", tier="lite")
        pro = engine.summary(_result(), audience="agent", tier="pro")
        self.assertEqual(_figure(lite), self.baseline)
        self.assertEqual(_figure(pro), self.baseline)
        self.assertEqual(_figure(lite), _figure(pro))   # tier never moves the number

    def test_scenario_matrix_is_pro_only(self):
        lite = engine.summary(_result(), audience="vendor", tier="lite")
        pro = engine.summary(_result(), audience="vendor", tier="pro")
        self.assertNotIn("scenario", lite)            # Lite never carries the matrix
        self.assertIn("scenario", pro)
        sc = pro["scenario"]
        self.assertTrue(sc["ok"])
        # the matrix prices are the same assessed figures - it invents nothing
        self.assertEqual(sc["selling"][0]["price"], self.baseline[0])   # floor = low
        self.assertEqual(sc["selling"][2]["price"], self.baseline[1])   # ceiling = high
        # and attaching the matrix never moved the figure
        self.assertEqual(_figure(pro), self.baseline)

    def test_tier_is_normalised(self):
        # anything that is not exactly "pro" (case-insensitive) collapses to lite - no
        # surface can accidentally light up the paid arsenal with a stray value.
        for junk in ("PRO ", "Pro", "pro"):
            self.assertEqual(engine.summary(_result(), tier=junk)["tier"], "pro")
        for junk in ("LITE", "free", "", None, "premium", "deluxe"):
            self.assertEqual(engine.summary(_result(), tier=junk)["tier"], "lite")


if __name__ == "__main__":
    unittest.main(verbosity=2)
