#!/usr/bin/env python3
"""Offline tests for scenario.py - the Pro scenario pricing matrix (build #69).

The honesty contract under test:
  * INVENTS NO NUMBER - every price the matrix prints is one of the real assessed figures
    (low / guide / central / high). Nothing else may appear as a price.
  * Net proceeds reproduce engine.vendor_view's arithmetic EXACTLY (2%+VAT fee; 24% CGT
    after the £3,000 allowance only when investment).
  * Buyer headroom is exactly asking - high.
  * Speed is grounded in the real positioning evidence (stuck-stock count), never a count
    of days pulled from nowhere.
  * Degrades honestly: an incomplete figure returns {ok: False}, never a fabricated matrix.
No network, no spend.
"""
import unittest
import scenario


D = {"low": 590000, "high": 650000, "central": 620000, "guide": 600000,
     "investment": False, "last_sold": 450000, "audience": "vendor"}
POS = {"band": [1, 2, 3, 4, 5], "mean_dom": 58, "stuck": [1, 2], "fresh": [1],
       "under_offer": [3], "median": 640000}

ALLOWED = {D["low"], D["high"], D["central"], D["guide"],
           # the buyer opening offer is guide rounded to the nearest 1,000 - still derived
           scenario.round_to(D["guide"], 1000)}


class TestScenarioMatrix(unittest.TestCase):
    def test_incomplete_figure_degrades(self):
        self.assertFalse(scenario.matrix({"low": 1})["ok"])
        self.assertFalse(scenario.matrix(None)["ok"])

    def test_every_selling_price_is_a_real_assessed_figure(self):
        m = scenario.matrix(D, pos=POS)
        prices = {r["price"] for r in m["selling"]}
        self.assertTrue(prices <= ALLOWED, f"invented price(s): {prices - ALLOWED}")
        # the three scenarios map to floor / guide / ceiling exactly
        self.assertEqual(m["selling"][0]["price"], D["low"])
        self.assertEqual(m["selling"][1]["price"], D["guide"])
        self.assertEqual(m["selling"][2]["price"], D["high"])

    def test_net_matches_engine_arithmetic(self):
        m = scenario.matrix(D, pos=POS)
        for r in m["selling"]:
            fee = round(r["price"] * 0.024)
            self.assertEqual(r["fee"], fee)
            self.assertEqual(r["net"], r["price"] - fee)   # no CGT for owner-occupier
            self.assertIsNone(r["cgt"])

    def test_cgt_only_when_investment(self):
        inv = dict(D, investment=True)
        m = scenario.matrix(inv, pos=POS)
        for r in m["selling"]:
            fee = round(r["price"] * 0.024)
            gain = max(0, r["price"] - inv["last_sold"] - fee - 3000)
            self.assertEqual(r["cgt"], round(gain * 0.24))
            self.assertEqual(r["net"], r["price"] - fee - r["cgt"])

    def test_buyer_headroom_is_asking_minus_high(self):
        m = scenario.matrix(D, pos=POS, asking=675000)
        self.assertEqual(m["buying"]["headroom"], 675000 - D["high"])
        self.assertEqual(m["buying"]["ceiling"], D["high"])
        self.assertEqual(m["buying"]["fair_value"], D["central"])

    def test_buyer_block_omits_headroom_without_asking(self):
        m = scenario.matrix(D, pos=POS)
        self.assertNotIn("headroom", m["buying"])

    def test_listing_guide_and_ceiling_are_real_figures(self):
        m = scenario.matrix(D, pos=POS)
        self.assertEqual(m["listing"]["defensible_guide"], D["guide"])
        self.assertEqual(m["listing"]["ceiling"], D["high"])
        # the ceiling figure is named in the trap note (compare digits-only on both sides)
        self.assertIn(str(D["high"]),
                      m["listing"]["trap_note"].replace(",", "").replace("£", ""))

    def test_ceiling_speed_note_cites_stuck_stock_when_present(self):
        m = scenario.matrix(D, pos=POS)
        note = m["selling"][2]["speed_note"]
        self.assertIn("2 comparable", note)        # POS has 2 stuck listings
        self.assertIn("90+ days", note)

    def test_market_note_is_lifted_not_modelled(self):
        m = scenario.matrix(D, pos=POS)
        mk = m["market_note"]
        self.assertEqual(mk["mean_dom"], 58)
        self.assertEqual(mk["stuck"], 2)
        self.assertEqual(mk["fresh"], 1)
        self.assertEqual(mk["listings"], 5)

    def test_no_positioning_still_builds_matrix(self):
        m = scenario.matrix(D)            # pos absent
        self.assertTrue(m["ok"])
        self.assertIsNone(m["market_note"])
        # ceiling note falls back to the no-stuck-evidence wording
        self.assertIn("longer wait", m["selling"][2]["speed_note"])

    def test_lines_render_for_each_role(self):
        m = scenario.matrix(D, pos=POS, asking=675000)
        for aud in ("vendor", "buyer", "agent"):
            out = "\n".join(scenario.lines(m, aud))
            self.assertIn("Scenario pricing", out)
            self.assertNotIn("None", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
