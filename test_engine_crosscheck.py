#!/usr/bin/env python3
"""Offline tests for the HM Land Registry official-sold cross-check in engine.summary().

The honesty point under test (plan task #15): the direct-HMLR cross-check sits BESIDE the
figure as an independent reality-check on the comparable evidence. It must:
  * appear under summary()["crosscheck"] when the register returns sales,
  * NEVER move low / high / central / guide (byte-identical across success, failure, absence),
  * be fully guarded - a raising or down SPARQL endpoint never breaks the valuation.
"""
import unittest
from unittest import mock

import engine
import land_registry


def _result():
    """A minimal, self-consistent engine.value() result for summary() to render."""
    comps = [
        {"address": "1 Cronin Street, London SE15 6JH", "sqm": 90, "price": 600000,
         "date": "2025-09-01", "score": 0.9, "dist": 0.1, "match": "strong"},
        {"address": "3 Cronin Street, London SE15 6JH", "sqm": 88, "price": 580000,
         "date": "2025-07-01", "score": 0.8, "dist": 0.2, "match": "good"},
        {"address": "5 Bird in Bush Rd, London SE15 1QR", "sqm": 95, "price": 620000,
         "date": "2025-05-01", "score": 0.7, "dist": 0.3, "match": "fair"},
    ]
    return {
        "subject": {"address": "58 Cronin Street, London SE15 6JH", "beds": 4, "sqm": 92},
        "valuation": {"low": 590000, "high": 650000, "central": 620000, "guide": 600000,
                      "psmA": 6700, "market": None, "sold_anchor": 610000},
        "positioning": None,
        "compsA": comps,
        "n_candidates": 8, "n_screened": 5,
    }


def _figure(out):
    return (out["low"], out["high"], out["central"], out["guide"])


class TestCrossCheck(unittest.TestCase):
    def setUp(self):
        # neutralise the macro layer so these tests are pure-offline and deterministic
        self._p_outlook = mock.patch.object(engine, "outlook", return_value=None)
        self._p_txn = mock.patch.object(engine, "txn_link", return_value="")
        self._p_outlook.start()
        self._p_txn.start()
        self.addCleanup(self._p_outlook.stop)
        self.addCleanup(self._p_txn.stop)
        # the figure summary() must reproduce regardless of the cross-check outcome
        self.baseline = (590000, 650000, 620000, 600000)

    def test_crosscheck_attached_when_register_has_sales(self):
        ppd = {"ok": True, "postcode": "SE15 6JH", "count": 7, "median": 605000,
               "low": 540000, "high": 690000, "oldest": "2023-01-01",
               "newest": "2025-10-01",
               "source": "HM Land Registry Price Paid Data (SPARQL, OGL)"}
        with mock.patch.object(land_registry, "ppd_postcode", return_value=ppd) as m:
            out = engine.summary(_result(), audience="agent")
        m.assert_called_once()
        self.assertEqual(_figure(out), self.baseline)          # figure untouched
        cc = out["crosscheck"]
        self.assertEqual(cc["official_count"], 7)
        self.assertEqual(cc["official_median"], 605000)
        self.assertEqual(cc["postcode"], "SE15 6JH")
        self.assertIn("2023-01-01 to 2025-10-01", cc["note"])
        self.assertIn("never blended into the figure", cc["note"])
        # divergence is (our_sold_median - official) / official * 100, a pure restatement
        self.assertEqual(cc["divergence_pct"],
                         round((cc["our_sold_median"] - 605000) / 605000 * 100, 1))

    def test_no_crosscheck_when_register_empty(self):
        ppd = {"ok": True, "postcode": "SE15 6JH", "count": 0, "sales": [],
               "reason": "no transactions on record for this postcode"}
        with mock.patch.object(land_registry, "ppd_postcode", return_value=ppd):
            out = engine.summary(_result(), audience="buyer")
        self.assertEqual(_figure(out), self.baseline)
        self.assertNotIn("crosscheck", out)

    def test_no_crosscheck_when_register_not_ok(self):
        ppd = {"ok": False, "reason": "HMLR SPARQL HTTP 503"}
        with mock.patch.object(land_registry, "ppd_postcode", return_value=ppd):
            out = engine.summary(_result(), audience="vendor")
        self.assertEqual(_figure(out), self.baseline)
        self.assertNotIn("crosscheck", out)

    def test_raising_register_is_swallowed_and_figure_stable(self):
        with mock.patch.object(land_registry, "ppd_postcode",
                               side_effect=Exception("SPARQL timeout")):
            out = engine.summary(_result(), audience="agent")
        self.assertEqual(_figure(out), self.baseline)          # never raised
        self.assertNotIn("crosscheck", out)

    def test_figure_identical_with_and_without_crosscheck(self):
        ppd = {"ok": True, "postcode": "SE15 6JH", "count": 4, "median": 615000,
               "low": 600000, "high": 640000, "oldest": "2024-02-01",
               "newest": "2025-08-01"}
        with mock.patch.object(land_registry, "ppd_postcode", return_value=ppd):
            with_cc = engine.summary(_result(), audience="agent")
        with mock.patch.object(land_registry, "ppd_postcode",
                               side_effect=Exception("down")):
            without_cc = engine.summary(_result(), audience="agent")
        self.assertEqual(_figure(with_cc), _figure(without_cc))
        self.assertEqual(_figure(with_cc), self.baseline)


if __name__ == "__main__":
    unittest.main(verbosity=2)
