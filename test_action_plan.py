#!/usr/bin/env python3
"""Offline tests for action_plan.py - the Pro per-role plan of action (build #70).

The honesty contract under test:
  * The plan INVENTS NO NUMBER. Every price it quotes is one of the real assessed figures
    (via the scenario matrix); every cost traces to a real source - buyer SDLT is exactly
    macro.sdlt(opening_offer); the seller net is exactly the scenario realistic-row net.
  * It reuses the scenario matrix already on the summary, so the plan and the matrix can
    never quote different figures.
  * It degrades honestly: no usable figure -> {ok: False}, never a fabricated plan.
  * lines() renders for every role with no stray "None".
No network, no spend.
"""
import unittest

import macro
import scenario
import action_plan


D = {"low": 590000, "high": 650000, "central": 620000, "guide": 600000,
     "investment": False, "last_sold": 450000, "audience": "vendor",
     "macro": {"momentum": {"headline": "Bank Rate held at 4.0%; momentum is flat."}}}
POS = {"band": [1, 2, 3, 4, 5], "mean_dom": 58, "stuck": [1, 2], "fresh": [1],
       "under_offer": [3], "median": 640000}


def _summary(audience="vendor", investment=False, asking=None):
    """A Pro summary dict carrying its scenario matrix exactly as engine.summary() attaches
    it - so build() exercises the reuse path, not the recompute path."""
    d = dict(D, audience=audience, investment=investment)
    d["scenario"] = scenario.matrix(d, pos=POS, asking=asking)
    return d


class TestActionPlan(unittest.TestCase):
    def test_degrades_without_a_figure(self):
        self.assertFalse(action_plan.build(None)["ok"])
        # a summary whose figure is incomplete cannot produce a scenario, so no plan
        self.assertFalse(action_plan.build({"low": 1, "audience": "vendor"})["ok"])

    def test_reuses_the_attached_scenario_matrix(self):
        d = _summary("vendor")
        plan = action_plan.build(d, audience="vendor")
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["tier"], "pro")
        self.assertEqual(plan["role"], "selling")

    def test_role_maps_from_audience(self):
        self.assertEqual(action_plan.build(_summary("buyer"), audience="buyer")["role"],
                         "buying")
        self.assertEqual(action_plan.build(_summary("vendor"), audience="vendor")["role"],
                         "selling")
        self.assertEqual(action_plan.build(_summary("agent"), audience="agent")["role"],
                         "listing")

    def test_buyer_sdlt_is_exactly_macro_sdlt_of_the_opening_offer(self):
        d = _summary("buyer", asking=675000)
        plan = action_plan.build(d, audience="buyer", asking=675000)
        opening = d["scenario"]["buying"]["opening_offer"]
        self.assertEqual(plan["costs"]["price"], opening)
        self.assertEqual(plan["costs"]["sdlt"], macro.sdlt(opening, first_time=False))

    def test_buyer_cash_in_totals_are_price_plus_real_costs(self):
        d = _summary("buyer")
        plan = action_plan.build(d, audience="buyer")
        c = plan["costs"]
        self.assertEqual(c["cash_in_lo"], c["price"] + c["sdlt"] + c["legal_lo"] + c["survey_lo"])
        self.assertEqual(c["cash_in_hi"], c["price"] + c["sdlt"] + c["legal_hi"] + c["survey_hi"])

    def test_seller_net_is_exactly_the_realistic_scenario_row(self):
        d = _summary("vendor")
        plan = action_plan.build(d, audience="vendor")
        realistic = d["scenario"]["selling"][1]   # the realistic guide row
        self.assertEqual(plan["costs"]["price"], realistic["price"])
        self.assertEqual(plan["costs"]["fee"], realistic["fee"])
        self.assertEqual(plan["costs"]["net"], realistic["net"])
        self.assertIsNone(plan["costs"]["cgt"])   # owner-occupier

    def test_seller_cgt_only_when_investment(self):
        d = _summary("vendor", investment=True)
        plan = action_plan.build(d, audience="vendor")
        realistic = d["scenario"]["selling"][1]
        self.assertEqual(plan["costs"]["cgt"], realistic["cgt"])
        self.assertIsNotNone(plan["costs"]["cgt"])

    def test_no_price_is_invented_in_buyer_costs(self):
        # buyer opening offer is the scenario opening (guide rounded to 1,000) - nothing else
        d = _summary("buyer")
        plan = action_plan.build(d, audience="buyer")
        self.assertEqual(plan["costs"]["price"], d["scenario"]["buying"]["opening_offer"])

    def test_lines_render_for_each_role_without_none(self):
        for aud in ("buyer", "vendor", "agent"):
            d = _summary(aud, asking=675000)
            out = "\n".join(action_plan.lines(action_plan.build(d, audience=aud, asking=675000)))
            self.assertIn("Plan of action", out)
            self.assertNotIn("None", out)

    def test_lines_empty_on_unavailable_plan(self):
        self.assertEqual(action_plan.lines({"ok": False}), [])
        self.assertEqual(action_plan.lines(None), [])

    def test_momentum_headline_is_woven_in_when_present(self):
        d = _summary("vendor")
        out = "\n".join(action_plan.lines(action_plan.build(d, audience="vendor")))
        self.assertIn("Bank Rate held at 4.0%", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
