# -*- coding: utf-8 -*-
"""The conversion layer: flag-gated factor upsells + the deep-link purchase trigger.

Guards two rules the funnel depends on:
  1. A factor's upsell hyperlink fires ONLY when the factor is genuinely flagged (planning
     apps exist, real flood risk) - never on a benign 'no material impact' (crime, very-low
     flood). Bolting a paid link on a non-issue kills trust.
  2. A guide/Pro deep link (?start=buy_<x>) lands the reader on the RELEVANT offer ready to
     buy when they have a valuation in-chat, and primes them (never a dead bot) when cold.
"""
import unittest

import bot
import engine


class TestFactorFlagGating(unittest.TestCase):
    def _qa(self, sections):
        return {b["key"]: b for b in engine.factor_qa({"sections": sections})}

    def test_crime_is_never_flagged(self):
        qa = self._qa({"safety": {"total": 500}})
        self.assertFalse(qa["crime"]["flag"])   # we never price crime -> no upsell, ever

    def test_planning_flagged_only_when_applications_exist(self):
        self.assertTrue(self._qa({"planning": {"total": 3}})["planning"]["flag"])
        self.assertFalse(self._qa({"planning": {"total": 0}})["planning"]["flag"])

    def test_flood_flagged_only_on_real_risk(self):
        self.assertFalse(self._qa({"environment": {"flood": {"severity": "Very low risk"}}})["flood"]["flag"])
        self.assertFalse(self._qa({"environment": {"flood": {"severity": "Low"}}})["flood"]["flag"])
        self.assertTrue(self._qa({"environment": {"flood": {"severity": "Flood warning area"}}})["flood"]["flag"])

    def test_flagged_blocks_carry_a_guide_and_product(self):
        for b in engine.factor_qa({"sections": {"planning": {"total": 2}}}):
            self.assertTrue(b["guide"] and b["mid"])

    def test_no_data_no_block(self):
        self.assertEqual(engine.factor_qa({"sections": {}}), [])


class TestBuyDeepLink(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.packs = []
        self.invoices = []
        self._say = bot.say
        self._pp = bot.present_packs
        self._inv = bot.invoice_micro
        self._wa = bot.webapp_url
        bot.say = lambda chat, text, keyboard=None: (self.sent.append(text) or {"ok": True})
        bot.present_packs = lambda chat, r, aud, uid=None: self.packs.append((aud, uid))
        bot.invoice_micro = lambda chat, aud, mid: self.invoices.append((aud, mid))
        bot.webapp_url = lambda: None
        bot.PENDING.clear()

    def tearDown(self):
        bot.say, bot.present_packs, bot.invoice_micro, bot.webapp_url = (
            self._say, self._pp, self._inv, self._wa)
        bot.PENDING.clear()

    def test_buy_pro_with_valuation_presents_packs(self):
        bot.PENDING[7] = {"address": "1 Test Rd SE15", "audience": "vendor", "r": {"compsA": []}}
        self.assertTrue(bot.begin_buy(99, 7, "pro"))
        self.assertEqual(self.packs, [("vendor", 7)])

    def test_buy_pro_cold_primes_not_dead(self):
        self.assertTrue(bot.begin_buy(99, 7, "pro"))
        self.assertFalse(self.packs)
        self.assertTrue(self.sent and "address" in self.sent[-1].lower())

    def test_buy_micro_with_valuation_invoices(self):
        bot.PENDING[7] = {"address": "1 Test Rd SE15", "audience": "buyer", "r": {"compsA": []}}
        self.assertTrue(bot.begin_buy(99, 7, "ledger"))
        self.assertEqual(self.invoices, [("buyer", "ledger")])

    def test_buy_micro_cold_primes_no_invoice(self):
        self.assertTrue(bot.begin_buy(99, 7, "ledger"))
        self.assertFalse(self.invoices)
        self.assertTrue(self.sent)

    def test_unknown_code_falls_through(self):
        self.assertFalse(bot.begin_buy(99, 7, "wat"))


class TestGuideEngine(unittest.TestCase):
    """The automated guide-upsell engine: a flagged factor sells a DISTINCT topic guide
    (never the valuation), declared once in guides.py and auto-wired into catalogue + delivery."""

    def test_flagged_factor_sells_its_own_guide_not_the_valuation(self):
        fq = {b["key"]: b for b in engine.factor_qa({"sections": {
            "planning": {"total": 3}, "environment": {"flood": {"severity": "Flood warning area"}}}})}
        self.assertEqual(fq["planning"]["mid"], "planning_guide")
        self.assertEqual(fq["flood"]["mid"], "flood_guide")

    def test_guides_auto_added_to_catalogue(self):
        for gid in ("planning_guide", "flood_guide", "lease_guide"):
            self.assertIn(gid, bot.MICRO_BY)

    def test_guide_is_data_gated_and_distinct(self):
        import guides
        body = guides.build("planning", {"planning": {"total": 3, "by_status": [("Approved", 2)]}})
        self.assertTrue(body and any("check" in x.lower() for x in body))
        self.assertIsNone(guides.build("planning", {"planning": {"total": 0}}))   # no data, no charge

    def test_new_guide_needs_no_dispatch_branch(self):
        # the generic dispatch resolves any '<topic>_guide' id from the registry
        import guides
        self.assertEqual(set(guides.GUIDE_TOPIC_BY_MICRO),
                         {f"{t}_guide" for t in guides.TOPICS})


if __name__ == "__main__":
    unittest.main(verbosity=2)
