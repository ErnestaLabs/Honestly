# -*- coding: utf-8 -*-
"""Monetization funnel: the micro-upsell catalogue, pricing, the intelligent suggester, the
Mini-App payload and the purchase routing. These guard the funnel so a future change can't
silently break an upsell, mis-price one, or stop surfacing/selling it."""
import unittest

import bot
import server


class TestMicroCatalogue(unittest.TestCase):
    def test_at_least_15_micro_upsells_besides_pro(self):
        self.assertGreaterEqual(len(bot.MICRO), 15, "the goal requires >=15 micro-upsells besides Pro")

    def test_every_micro_is_well_formed_and_unique(self):
        ids = [m["id"] for m in bot.MICRO]
        self.assertEqual(len(ids), len(set(ids)), "duplicate micro ids")
        for m in bot.MICRO:
            self.assertTrue(m.get("name") and m.get("blurb"), m)
            self.assertGreater(m.get("stars", 0), 0, m)

    def test_every_micro_has_a_delivery_branch(self):
        # honesty: we never list a micro we cannot ship. Each id is either handled explicitly in
        # deliver_micro/_deliver_ctx_micro, OR is a guide delivered generically from the guides
        # registry (declarative - no per-id branch by design).
        import inspect
        src = inspect.getsource(bot.deliver_micro) + inspect.getsource(bot._deliver_ctx_micro)
        guide_ids = set(getattr(getattr(bot, "_guides", None), "GUIDE_TOPIC_BY_MICRO", {}) or {})
        for m in bot.MICRO:
            if m["id"] in guide_ids:
                continue  # generic guide dispatch
            self.assertIn(f'"{m["id"]}"', src, f'no delivery branch for micro {m["id"]}')

    def test_micro_price_applies_intro_and_formats(self):
        for m in bot.MICRO:
            s, star, gbp = bot.micro_price(m)
            self.assertIsInstance(s, int)
            self.assertTrue(star.startswith("⭐"))
            self.assertTrue(gbp.startswith("£"))
            if bot.INTRO:
                self.assertLessEqual(s, m["stars"])  # intro discount never raises the price


class TestSuggester(unittest.TestCase):
    def _ctx(self, **sections):
        return {"sections": sections}

    def test_audience_fit_is_respected(self):
        r = {"subject": {}, "valuation": {"central": 500000}, "positioning": None}
        picks = bot.suggest_micros({}, r, "buyer", None, n=8)
        for m in picks:
            self.assertTrue(bot._micro_fits(m, "buyer"), f"{m['id']} surfaced to buyer but doesn't fit")

    def test_flood_signal_promotes_the_guide_not_the_free_fact(self):
        # The raw 'environment' fact is delivered FREE in Lite, so it must never be re-sold.
        # A flood signal now promotes the paid INTERPRETATION (flood_guide) instead.
        r = {"subject": {}, "valuation": {"central": 500000}, "positioning": None}
        ctx = self._ctx(environment={"flood": {"severity": "Monitored, no active warning"}})
        ids = [m["id"] for m in bot.suggest_micros({}, r, "vendor", ctx, n=4)]
        self.assertIn("flood_guide", ids)
        self.assertNotIn("environment", ids)

    def test_lite_included_facts_are_never_sold(self):
        for gid in bot.LITE_INCLUDED:
            self.assertNotIn(gid, {m["id"] for m in bot.sellable_micros()})

    def test_stuck_stock_promotes_scenario_for_vendor(self):
        r = {"subject": {}, "valuation": {"central": 500000}, "positioning": {"stuck": [1, 2], "mean_dom": 80}}
        ids = [m["id"] for m in bot.suggest_micros({}, r, "vendor", None, n=4)]
        self.assertIn("scenario", ids)

    def test_returns_at_most_n(self):
        r = {"subject": {}, "valuation": {"central": 500000}, "positioning": None}
        self.assertLessEqual(len(bot.suggest_micros({}, r, "agent", None, n=3)), 3)


class TestMiniAppPayload(unittest.TestCase):
    def test_packs_payload_lists_micros(self):
        p = server.packs_payload("vendor")
        self.assertIn("micros", p)
        self.assertGreaterEqual(len(p["micros"]), 10)
        for m in p["micros"]:
            for k in ("id", "name", "stars", "gbp", "blurb"):
                self.assertIn(k, m)

    def test_payload_filters_by_audience(self):
        # 'map' fits agent/vendor, not buyer - so a buyer must not be offered it
        buyer_ids = {m["id"] for m in server.packs_payload("buyer")["micros"]}
        agent_ids = {m["id"] for m in server.packs_payload("agent")["micros"]}
        self.assertNotIn("map", buyer_ids)
        self.assertIn("map", agent_ids)


class TestPurchaseRouting(unittest.TestCase):
    def setUp(self):
        self._saved = (bot.run_value, bot.deliver_micro, bot.engine.summary)
        bot.run_value = lambda chat, address, answers=None: {"subject": {}, "valuation": {}, "positioning": None, "compsA": []}
        bot.engine.summary = lambda r, audience, **k: {"central": 500000}
        self.calls = []
        bot.deliver_micro = lambda chat, r, aud, mid, **k: (self.calls.append((aud, mid)) or True)

    def tearDown(self):
        bot.run_value, bot.deliver_micro, bot.engine.summary = self._saved

    def test_micro_intent_routes_to_deliver_micro(self):
        intent = {"uid": 7, "address": "1 Test Road SE15 6JH", "audience": "vendor", "micro": "scenario"}
        ok = bot.deliver_intent(99, 7, intent)
        self.assertTrue(ok)
        self.assertEqual(self.calls, [("vendor", "scenario")])

    def test_unknown_micro_id_invoice_is_guarded(self):
        sent = []
        _say = bot.say
        bot.say = lambda chat, text, keyboard=None: (sent.append(text) or {"ok": True})
        try:
            bot.invoice_micro(1, "vendor", "does_not_exist")
        finally:
            bot.say = _say
        self.assertTrue(any("isn't available" in s for s in sent))


if __name__ == "__main__":
    unittest.main()
