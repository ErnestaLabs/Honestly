#!/usr/bin/env python3
"""Test suite for the Honestly bot.

Covers the logic that actually matters: entitlements, promo codes, the money
paths (pay / credit / subscribe), refund-on-failure guarantees, update routing,
address parsing, card rendering and the engine's pure helpers.

Network (Telegram), the valuation engine and Maps are all stubbed, so this runs
offline and deterministically. No real .env, token or API calls are touched.

Run:  python -m unittest test_bot -v   (or: python test_bot.py)
"""
import os, sys, json, base64, tempfile, unittest
from unittest import mock

# Isolate the whole suite from the real persistence DB BEFORE store.py is imported
# (directly or via bot/server) - tests that exercise delivery write through store.py,
# and must never touch the production honestly.db. A throwaway path keeps them clean.
os.environ.setdefault("HONESTLY_DB", os.path.join(tempfile.gettempdir(), "honestly_test.db"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot
import appraise


# ----------------------------------------------------------------- fixtures
def make_r(n_comps=4):
    """A minimal engine result shaped like what deliver_full / teaser read."""
    comps = [{"address": f"{60+i} Cronin Street, London SE15 6JH"} for i in range(n_comps)]
    return {"subject": {"address": "58 Cronin Street, London SE15 6JH"},
            "compsA": comps}

def make_summary(*_a, **_k):
    """Deterministic stand-in for engine.summary() with every field card() reads."""
    return {
        "address": "58 Cronin Street, London SE15 6JH",
        "sqm": 85, "beds": 2, "epc": "C",
        "range_str": "£500,000 - £550,000",
        "central": 525000,
        "sold_median": 530000, "sold_median_str": "£530,000",
        "sold_anchor": 540000, "sold_anchor_str": "£540,000",
        "market": {"factor": 0.972, "pct": -2.8, "label": "Softening market", "dom": 110,
                   "sstc_ratio": 0.1, "stuck_ratio": 0.35, "ask_median": 560000,
                   "note": "Live stock is slow; steered down."},
        "macro": {"as_of": "2026-06-06", "stale": False, "base_rate": 3.75,
                  "next_mpc": "2026-06-18", "next_mpc_str": "18 Jun",
                  "rate_note": "Bank Rate has held at 3.75% since December 2025.",
                  "sdlt_standard": 16250, "sdlt_ftb": None,
                  "lines": ["Bank Rate has held at 3.75% since December 2025.",
                            "Stamp duty at this level is about £16,250."],
                  "momentum": {"as_of": "2026-06-07", "score": -0.79, "lean": "soft",
                               "headline": "Live macro momentum is leaning soft for prices (score -0.79 on a -2 to +2 scale).",
                               "lines": ["Live macro momentum is leaning soft for prices (score -0.79 on a -2 to +2 scale).",
                                         "Unemployment is 5.0%, above its 3-year average of 4.5%."],
                               "sources": {"mortgage": "Bank of England IADB IUMBV34"}}},
        "guide_label": "Guide", "guide_value_str": "Offers over £500,000",
        "psm": 6176, "n_comps": 7,
        "evidence_purity": {"pct": 88, "adjustment_pct": 12},
        "confidence": {"grade": "Good", "score": 72},
        "plain_english": {"headline": "A defensible two-bed flat valuation.", "bullets": []},
        "verdict": {"tone": "ok", "text": "Priced fairly versus the evidence"},
        "evidence": [{"address": "60 Cronin Street", "sqm": 82,
                      "price_str": "£520,000", "date": "2024-03",
                      "verify": "https://landregistry.data.gov.uk/data/ppi/transaction/ABC123/current"}],
        "positioning": {"note": "Below the local average for the street"},
    }


class BotTestBase(unittest.TestCase):
    def setUp(self):
        # isolate persistent state in a temp file
        self._tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp.close()
        self._orig_state = bot.STATE
        bot.STATE = self._tmp.name

        # reset in-memory state
        bot.PENDING.clear()
        bot.AWAIT_TESTI.clear()

        # record every outbound side effect instead of hitting the network
        self.says = []       # (chat, text, keyboard)
        self.tgs = []        # (method, params)
        self.photos = []     # (chat, path, caption)
        self.docs = []       # (chat, path, caption, mime)

        self._saved = {}
        def patch(name, fn):
            self._saved[name] = getattr(bot, name)
            setattr(bot, name, fn)

        patch("say", lambda chat, text, keyboard=None: (self.says.append((chat, text, keyboard)) or {"ok": True}))
        patch("tg", lambda method, **p: (self.tgs.append((method, p)) or {"ok": True, "result": {"username": "usehonestly_bot"}}))
        patch("tg_photo", lambda chat, path, caption="", keyboard=None: (self.photos.append((chat, path, caption)) or {"ok": True}))
        patch("tg_document", lambda chat, path, caption="", keyboard=None, mime="application/pdf": (self.docs.append((chat, path, caption, mime)) or {"ok": True}))

        # stub the heavy bits: engine + image + PDF + maps
        self._saved["engine_summary"] = bot.engine.summary
        bot.engine.summary = make_summary
        self._saved["cardimg_render"] = bot.cardimg.render
        bot.cardimg.render = lambda d, audience, slug="x": ("clear.png", "locked.png")
        import report as _report
        self._saved["report_build"] = (_report, _report.build)
        _report.build = lambda r, audience, **k: ("report.pdf", "report_interactive.html")
        self._saved["run_value"] = bot.run_value
        bot.run_value = lambda chat, address, answers=None: make_r()
        self._saved["street_view"] = bot.maps_tools.street_view
        bot.maps_tools.street_view = lambda addr, out: {"ok": True, "available": False}
        self._saved["route"] = bot.maps_tools.route
        bot.maps_tools.route = lambda stops, optimize=True, mode="DRIVE": {"ok": False}
        # the personalised products module talks to the PropertyData listings API and
        # Maps - stub all four so delivery is offline and deterministic.
        self._saved["pl_targets"] = bot.products.target_listings
        bot.products.target_listings = lambda r, key, audience, n=20: [
            {"address": "70 Cronin Street, London SE15 6JH", "loc": "70 Cronin Street",
             "price": 540000, "price_str": "£540,000", "beds": 2, "dom": 120,
             "status": "Available", "portal": "Rightmove",
             "link": "https://rightmove/x", "coord": None}]
        self._saved["pl_map"] = bot.products.target_map
        bot.products.target_map = lambda targets, subj, out="_targets.png": None
        self._saved["pl_plan"] = bot.products.plan_of_action
        bot.products.plan_of_action = lambda d, r, audience: ["<b>Action plan</b>", "1. Do the thing."]
        self._saved["pl_email"] = bot.products.email_template
        bot.products.email_template = lambda d, r, audience: {"subject": "Subject line", "body": "Email body."}
        self._saved["pl_schools"] = bot.products.nearby_schools
        bot.products.nearby_schools = lambda r, key, n=6: [
            {"name": "Cronin Primary", "phase": "Primary", "type": "Academy",
             "sector": "state", "pupils": 300, "distance": 0.2,
             "ofsted_url": "https://reports.ofsted.gov.uk/x"}]
        # audio walkthrough is best-effort and key-gated; stub it off so the suite is
        # deterministic and never reaches Voxtral, regardless of any local MISTRAL_API_KEY.
        import audio as _audio_mod
        self._saved["audio_walk"] = (_audio_mod, _audio_mod.save_walkthrough)
        _audio_mod.save_walkthrough = lambda d, path, key=None, fmt="mp3": None
        # area context is gathered on the report path (bot delivers PDF+HTML with the
        # Area/Safety/Environment/Planning sections). Stub it off so the suite is offline
        # and deterministic and never reaches Overpass / Police / Flood / Gemini.
        import area_context as _ctx_mod
        self._saved["area_ctx"] = (_ctx_mod, _ctx_mod.gather)
        _ctx_mod.gather = lambda subject, summary=None, anchors=None: None
        # deliver_* are reassigned by some tests to simulate failure; snapshot them
        # so every test starts from the real implementation.
        self._saved["deliver_full"] = bot.deliver_full
        self._saved["deliver_components"] = bot.deliver_components

    def tearDown(self):
        for name, fn in self._saved.items():
            if name == "engine_summary": bot.engine.summary = fn
            elif name == "cardimg_render": bot.cardimg.render = fn
            elif name == "street_view": bot.maps_tools.street_view = fn
            elif name == "route": bot.maps_tools.route = fn
            elif name == "report_build":
                mod, orig = fn; mod.build = orig
            elif name == "pl_targets": bot.products.target_listings = fn
            elif name == "pl_map": bot.products.target_map = fn
            elif name == "pl_plan": bot.products.plan_of_action = fn
            elif name == "pl_email": bot.products.email_template = fn
            elif name == "pl_schools": bot.products.nearby_schools = fn
            elif name == "audio_walk":
                mod, orig = fn; mod.save_walkthrough = orig
            elif name == "area_ctx":
                mod, orig = fn; mod.gather = orig
            else: setattr(bot, name, fn)
        bot.STATE = self._orig_state
        try: os.unlink(self._tmp.name)
        except OSError: pass

    # helpers to build updates
    def msg(self, text, uid=1, chat=1):
        return {"message": {"text": text, "chat": {"id": chat},
                            "from": {"id": uid, "first_name": "Test"}}}
    def cb(self, data, uid=1, chat=1):
        return {"callback_query": {"id": "c1", "data": data,
                                   "from": {"id": uid},
                                   "message": {"chat": {"id": chat}}}}
    # condition-survey taps that DERIVE each finish tier (state, kitchen, bath, premium)
    _FINISH_TAPS = {
        "needs_renovation":  ("0", "0", "0", "0"),
        "needs_modernising": ("1", "0", "0", "0"),
        "average":           ("2", "1", "0", "0"),   # uplift 1 -> average
        "high":              ("2", "2", "1", "0"),   # uplift 3 -> high
        "very_high":         ("3", "2", "2", "2"),   # uplift 6 -> very_high
    }
    def tap_condition(self, finish="average", uid=1, chat=1):
        """Tap through the condition sub-survey so it derives `finish`."""
        s, k, b, p = self._FINISH_TAPS.get(finish, self._FINISH_TAPS["average"])
        bot.handle(self.cb(f"q:c_state:{s}", uid, chat))
        bot.handle(self.cb(f"q:c_kitchen:{k}", uid, chat))
        bot.handle(self.cb(f"q:c_bath:{b}", uid, chat))
        bot.handle(self.cb(f"q:c_premium:{p}", uid, chat))
    def run_wizard(self, aud, uid=1, chat=1, beds="2", baths="1",
                   finish="average", investment="0", money="skip"):
        """Pick the audience and tap through the whole intake to the valuation.

        `beds`/`baths` stay accepted for older tests/callers but are no longer asked before
        first value; public facts are fetched/inferred, not used as conversion gates.
        """
        bot.handle(self.cb(f"aud:{aud}", uid, chat))
        self.tap_condition(finish, uid, chat)
        if aud in ("vendor", "agent"):
            bot.handle(self.cb(f"q:investment:{investment}", uid, chat))
        if aud == "vendor":
            bot.handle(self.cb(f"q:quoted:{money}", uid, chat))
        if aud == "buyer":
            bot.handle(self.cb(f"q:asking:{money}", uid, chat))
    def capture_run_value(self):
        """Swap run_value for a recorder so tests can assert what the engine was asked."""
        seen = {}
        def rec(chat, address, answers=None):
            seen["address"] = address
            seen["answers"] = dict(answers or {})
            return make_r()
        bot.run_value = rec
        return seen
    def last_say(self):
        return self.says[-1][1] if self.says else ""
    def all_say_text(self):
        return " || ".join(t for _, t, _ in self.says)
    def tg_methods(self):
        return [m for m, _ in self.tgs]


# ----------------------------------------------------------------- entitlements
class TestEntitlements(BotTestBase):
    def test_unknown_user_not_subscribed(self):
        self.assertFalse(bot.subscribed(999))

    def test_grant_sub_makes_subscribed(self):
        bot.grant_sub(7)
        self.assertTrue(bot.subscribed(7))

    def test_expired_sub_is_not_subscribed(self):
        e = bot.load_ent(); e["7"] = {"sub_until": "2000-01-01T00:00:00"}; bot.save_ent(e)
        self.assertFalse(bot.subscribed(7))

    def test_bump_paid_counts_up(self):
        self.assertEqual(bot.bump_paid(3), 1)
        self.assertEqual(bot.bump_paid(3), 2)
        self.assertEqual(bot.bump_paid(4), 1)

    def test_state_persists_to_disk(self):
        bot.grant_sub(11)
        with open(bot.STATE, encoding="utf-8") as f:
            raw = json.load(f)
        self.assertIn("11", raw)
        self.assertIn("sub_until", raw["11"])


# ----------------------------------------------------------------- promo codes
class TestPromoCodes(BotTestBase):
    def test_invalid_code(self):
        self.assertEqual(bot.redeem_code(1, "NOPE"), "invalid")

    def test_redeem_grants_one_credit(self):
        self.assertEqual(bot.redeem_code(1, "TAUK"), "ok")
        self.assertEqual(bot.free_credits(1), 1)

    def test_redeem_is_case_insensitive(self):
        self.assertEqual(bot.redeem_code(1, "tauk"), "ok")
        self.assertEqual(bot.free_credits(1), 1)

    def test_cannot_redeem_twice(self):
        bot.redeem_code(1, "TAUK")
        self.assertEqual(bot.redeem_code(1, "TAUK"), "used")
        self.assertEqual(bot.free_credits(1), 1)   # still only one

    def test_use_credit_spends(self):
        bot.redeem_code(1, "TAUK")
        self.assertTrue(bot.use_credit(1))
        self.assertEqual(bot.free_credits(1), 0)
        self.assertFalse(bot.use_credit(1))         # nothing left

    def test_refund_credit_restores(self):
        bot.redeem_code(1, "TAUK")
        bot.use_credit(1)
        bot.refund_credit(1)
        self.assertEqual(bot.free_credits(1), 1)

    def test_prophet_grants_permanent_access(self):
        self.assertFalse(bot.subscribed(1))
        self.assertEqual(bot.redeem_code(1, "PROPHET"), "comp")
        self.assertTrue(bot.subscribed(1))             # always unlocked, like an active sub

    def test_prophet_is_case_insensitive(self):
        self.assertEqual(bot.redeem_code(1, "prophet"), "comp")
        self.assertTrue(bot.subscribed(1))

    def test_prophet_does_not_expire(self):
        bot.redeem_code(1, "PROPHET")
        # even with no sub_until (or an expired one), comp keeps access on
        e = bot.load_ent(); e["1"]["sub_until"] = "2000-01-01T00:00:00"; bot.save_ent(e)
        self.assertTrue(bot.subscribed(1))

    def test_prophet_grants_no_consumable_credits(self):
        bot.redeem_code(1, "PROPHET")
        self.assertEqual(bot.free_credits(1), 0)        # it's unlimited access, not a credit balance

    def test_prophet_cannot_redeem_twice(self):
        bot.redeem_code(1, "PROPHET")
        self.assertEqual(bot.redeem_code(1, "PROPHET"), "used")


# ----------------------------------------------------------------- routing
class TestRouting(BotTestBase):
    def test_start_has_no_pricing(self):
        bot.handle(self.msg("/start"))
        t = self.last_say()
        self.assertIn("Honestly", t)
        self.assertNotIn("£9.99", t)
        self.assertNotIn("⭐", t)

    def test_start_offers_miniapp_button_when_url_set(self):
        # with HONESTLY_WEBAPP_URL configured, /start pins a web_app launch button
        orig = bot.webapp_url; self.addCleanup(setattr, bot, "webapp_url", orig)
        bot.webapp_url = lambda: "https://app.usehonestly.co.uk"
        bot.handle(self.msg("/start"))
        kb = self.says[-1][2] or []
        urls = [b.get("web_app", {}).get("url") for row in kb for b in row]
        self.assertIn("https://app.usehonestly.co.uk", urls)

    def test_start_has_no_button_when_url_unset(self):
        orig = bot.webapp_url; self.addCleanup(setattr, bot, "webapp_url", orig)
        bot.webapp_url = lambda: ""
        bot.handle(self.msg("/start"))
        self.assertIsNone(self.says[-1][2])                  # plain text, no keyboard

    def test_help_lists_commands(self):
        bot.handle(self.msg("/help"))
        self.assertIn("/code", self.last_say())

    def test_subscribe_sends_invoice(self):
        bot.handle(self.msg("/subscribe"))
        self.assertIn("sendInvoice", self.tg_methods())

    def test_subscribe_when_subscribed_says_so(self):
        bot.grant_sub(1)
        bot.handle(self.msg("/subscribe"))
        self.assertIn("already subscribed", self.last_say())

    def test_code_without_arg_prompts(self):
        bot.handle(self.msg("/code"))
        self.assertIn("TAUK", self.last_say())

    def test_code_with_arg_applies(self):
        bot.handle(self.msg("/code TAUK"))
        self.assertIn("Code applied", self.last_say())
        self.assertEqual(bot.free_credits(1), 1)

    def test_code_reuse_reports_used(self):
        bot.handle(self.msg("/code TAUK"))
        bot.handle(self.msg("/code TAUK"))
        self.assertIn("already used", self.last_say())

    def test_bare_code_applies(self):
        bot.handle(self.msg("TAUK"))
        self.assertIn("Code applied", self.last_say())
        self.assertEqual(bot.free_credits(1), 1)

    def test_prophet_code_unlocks_unlimited(self):
        bot.handle(self.msg("/code PROPHET"))
        self.assertIn("Unlimited access", self.last_say())
        self.assertTrue(bot.subscribed(1))

    def test_short_text_prompts_for_address(self):
        bot.handle(self.msg("hi"))
        self.assertIn("UK address", self.last_say())

    def test_address_sets_pending_and_offers_audience(self):
        bot.handle(self.msg("58 Cronin Street, London SE15 6JH"))
        self.assertIn(1, bot.PENDING)
        self.assertEqual(bot.PENDING[1]["address"], "58 Cronin Street, London SE15 6JH")
        # the audience keyboard went out
        kb = self.says[-1][2]
        self.assertTrue(kb and any("Vendor" in b["text"] for b in kb[0]))

    def test_address_strips_conversational_filler(self):
        bot.handle(self.msg("okay do 11 Shadwell Gardens E1 2QG"))
        self.assertEqual(bot.PENDING[1]["address"], "11 Shadwell Gardens E1 2QG")

    def test_value_prefix_stripped(self):
        bot.handle(self.msg("value 58 Cronin Street SE15 6JH"))
        self.assertEqual(bot.PENDING[1]["address"], "58 Cronin Street SE15 6JH")

    # ---- landing-site widget hand-off: /start <base64url v1|audience|address> ----
    @staticmethod
    def _landing(audience, address):
        # encode exactly as site/index.html does: base64url, padding stripped
        raw = ("v1|%s|%s" % (audience, address)).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    def test_decode_start_payload_roundtrips(self):
        aud, addr = bot.decode_start_payload(self._landing("buyer", "58 Cronin Street SE15 6JH"))
        self.assertEqual((aud, addr), ("buyer", "58 Cronin Street SE15 6JH"))

    def test_decode_start_payload_garbage_is_none(self):
        self.assertIsNone(bot.decode_start_payload("not-a-real-payload!!"))
        self.assertIsNone(bot.decode_start_payload(""))

    def test_landing_widget_seeds_address_and_audience_skips_who_are_you(self):
        # arriving from the site, the bot already knows the address + audience: it must NOT
        # ask "Who are you?" and must jump straight into the intake wizard
        bot.handle(self.msg("/start " + self._landing("vendor", "58 Cronin Street SE15 6JH")))
        self.assertEqual(bot.PENDING[1]["address"], "58 Cronin Street SE15 6JH")
        self.assertEqual(bot.PENDING[1]["audience"], "vendor")
        joined = self.all_say_text()
        self.assertNotIn("Who are you?", joined)
        self.assertIn("Question 1 of", joined)              # we're mid-intake, not cold

    def test_landing_widget_honours_buyer_audience(self):
        bot.handle(self.msg("/start " + self._landing("buyer", "11 Shadwell Gardens E1 2QG")))
        self.assertEqual(bot.PENDING[1]["audience"], "buyer")

    def test_landing_widget_empty_address_falls_through_to_greeting(self):
        # the >64-char fallback sends 'v1|audience|' with no address - we can't pick up, so
        # we greet normally and never seed a half-built PENDING
        bot.handle(self.msg("/start " + self._landing("vendor", "")))
        self.assertNotIn(1, bot.PENDING)
        self.assertIn("Honestly", self.last_say())

    def test_unrecognised_start_arg_falls_through_to_greeting(self):
        bot.handle(self.msg("/start totally-bogus-arg"))
        self.assertNotIn(1, bot.PENDING)
        self.assertIn("Honestly", self.last_say())

    def test_empty_update_is_safe(self):
        self.assertIsNone(bot.handle({}))


# ----------------------------------------------------------------- audience + first-taste/deliver
class TestAudienceFlow(BotTestBase):
    def test_audience_without_pending_asks_for_address(self):
        bot.handle(self.cb("aud:vendor"))
        self.assertIn("address first", self.last_say())

    def test_first_valuation_is_free_lite_then_pro_offer(self):
        # a brand-new, non-subscribed user's FIRST valuation is the FREE Lite report - the
        # figure + sold evidence, delivered - and the Pro offer is presented AFTER it. We
        # never give the full Decision pack away; Lite is the hook, Pro is the upgrade.
        bot.PENDING[1] = {"address": "58 Cronin Street SE15 6JH"}
        self.run_wizard("vendor")
        docpaths = [p[1] for p in self.docs]
        self.assertIn("report.pdf", docpaths)               # the Lite report is delivered
        self.assertIn("evidence-based", self.all_say_text())       # the figure/evidence reached them
        self.assertTrue(bot.had_first(1))                    # first valuation recorded
        self.assertIn(1, bot.AWAIT_TESTI)                    # testimonial invited
        # the Pro offer is presented AFTER the free Lite - a buy CTA appears (not before)
        buys = [b.get("callback_data", "") for _, _, kb in self.says if kb for row in kb for b in row
                if b.get("callback_data", "").startswith("buy:")]
        self.assertTrue(buys, "Pro offer (buy CTA) must follow the free Lite valuation")
        self.assertNotIn("That one was on us", self.all_say_text())  # no full-kit giveaway

    def test_no_teaser_image_is_ever_sent(self):
        # the rendered locked/clear teaser pic is gone for good - products, not pictures
        bot.PENDING[1] = {"address": "58 Cronin Street SE15 6JH"}
        self.run_wizard("vendor")
        self.assertNotIn("locked.png", [p[1] for p in self.photos])

    def test_subscriber_second_valuation_auto_delivers_full_kit(self):
        # a Pro subscriber who's spent the free taste gets the full kit drawn from the
        # monthly allowance - no packs to pick, no extra charge per valuation
        bot.grant_sub(1); bot.mark_first(1)
        bot.PENDING[1] = {"address": "58 Cronin Street SE15 6JH"}
        self.run_wizard("vendor")
        docpaths = [p[1] for p in self.docs]
        self.assertIn("report.pdf", docpaths)            # full kit delivered
        self.assertIn("on Pro", self.all_say_text())     # allowance acknowledged
        buys = [b.get("callback_data", "") for _, _, kb in self.says if kb for row in kb for b in row
                if b.get("callback_data", "").startswith("buy:")]
        self.assertEqual(buys, [])                       # not asked to buy - it's included

    def test_non_member_after_free_taste_can_buy_a_pack(self):
        # free taste spent, no membership: single valuations are bought outright - no gate
        bot.mark_first(1)
        bot.PENDING[1] = {"address": "58 Cronin Street SE15 6JH"}
        self.run_wizard("vendor")
        t = self.all_say_text()
        self.assertIn("Evidence pack", t)                # the packs are offered directly
        self.assertNotIn("membership-based", t)          # no mandatory membership wall
        buys = [b["callback_data"] for _, _, kb in self.says if kb for row in kb for b in row
                if b["callback_data"].startswith("buy:")]
        self.assertEqual(set(buys), {"buy:vendor:consumer", "buy:vendor:full"})

    def test_first_valuation_full_report_even_for_a_member(self):
        # everyone's first valuation is the free taste - including a paying member
        bot.grant_sub(1)
        bot.PENDING[1] = {"address": "58 Cronin Street SE15 6JH"}
        self.run_wizard("agent")
        # full report: the detailed PDF document + the interactive HTML + figures card
        docpaths = [p[1] for p in self.docs]
        self.assertIn("report.pdf", docpaths)
        self.assertIn("report_interactive.html", docpaths)
        self.assertIn("evidence-based", self.all_say_text())

    def test_comp_gets_full_kit_every_time(self):
        # the owner (PROPHET) is the only one who gets the full kit free on every valuation
        bot.redeem_code(1, "PROPHET"); bot.mark_first(1)     # past the free taste
        bot.PENDING[1] = {"address": "58 Cronin Street SE15 6JH"}
        self.run_wizard("agent")
        docpaths = [p[1] for p in self.docs]
        self.assertIn("report.pdf", docpaths)                # still the full kit, no ladder
        buys = [b.get("callback_data", "") for _, _, kb in self.says if kb for row in kb for b in row
                if b.get("callback_data", "").startswith("buy:")]
        self.assertEqual(buys, [])


# ----------------------------------------------------------------- interactive intake wizard
class TestWizard(BotTestBase):
    def test_money_parser(self):
        self.assertEqual(bot._parse_money("£525,000"), 525000)
        self.assertEqual(bot._parse_money("525000"), 525000)
        self.assertEqual(bot._parse_money("525k"), 525000)
        self.assertEqual(bot._parse_money("0.5m"), 500000)
        self.assertIsNone(bot._parse_money("not a number"))
        self.assertIsNone(bot._parse_money(""))
        self.assertIsNone(bot._parse_money("12"))            # below the floor

    def test_audience_starts_wizard_not_valuation(self):
        seen = self.capture_run_value()
        bot.PENDING[1] = {"address": "58 Cronin Street SE15 6JH"}
        bot.handle(self.cb("aud:vendor"))
        # the first thing they see is high-leverage context, not a valuation or public-data gate
        self.assertIn("Question 1 of", self.last_say())
        self.assertIn("condition", self.last_say())
        self.assertNotIn("answers", seen)                    # engine not called yet

    def test_questions_asked_in_order(self):
        bot.PENDING[1] = {"address": "x"}
        bot.handle(self.cb("aud:agent"))
        self.assertIn("condition", self.last_say())      # condition sub-survey starts
        bot.handle(self.cb("q:c_state:2"))
        self.assertIn("kitchen", self.last_say())
        bot.handle(self.cb("q:c_kitchen:1"))
        self.assertIn("bathrooms", self.last_say())
        bot.handle(self.cb("q:c_bath:0"))
        self.assertIn("premium", self.last_say())
        bot.handle(self.cb("q:c_premium:0"))
        self.assertIn("investment", self.last_say())

    def test_tapped_answers_thread_into_engine(self):
        seen = self.capture_run_value()
        bot.PENDING[1] = {"address": "58 Cronin Street SE15 6JH"}
        self.run_wizard("agent", beds="3", baths="2", finish="high", investment="1")
        self.assertNotIn("beds", seen["answers"])
        self.assertNotIn("baths", seen["answers"])
        self.assertEqual(seen["answers"]["finish"], "high")
        self.assertIs(seen["answers"]["investment"], True)

    def test_typed_asking_price_threads_through(self):
        seen = self.capture_run_value()
        bot.grant_sub(1)                                     # subscriber -> deliver_full
        captured = {}
        bot.deliver_full = lambda chat, r, aud, asking=None, quoted=None: (
            captured.update(asking=asking, quoted=quoted) or True)
        bot.PENDING[1] = {"address": "58 Cronin Street SE15 6JH"}
        # buyer is asked the asking price as a typed figure; send it as a message mid-intake
        bot.handle(self.cb("aud:buyer"))
        self.tap_condition("average")
        self.assertIn("asking price", self.last_say())       # now awaiting a typed figure
        bot.handle(self.msg("£610,000"))                     # typed, not a button
        self.assertEqual(captured["asking"], 610000)

    def test_skip_leaves_figure_unset(self):
        seen = self.capture_run_value()
        bot.grant_sub(1)
        captured = {}
        bot.deliver_full = lambda chat, r, aud, asking=None, quoted=None: (
            captured.update(asking=asking, quoted=quoted) or True)
        bot.PENDING[1] = {"address": "58 Cronin Street SE15 6JH"}
        self.run_wizard("vendor", money="skip")
        self.assertIsNone(captured["quoted"])
        self.assertNotIn("quoted", seen["answers"])

    def test_garbage_figure_reprompts(self):
        bot.PENDING[1] = {"address": "x"}
        bot.handle(self.cb("aud:buyer"))
        self.tap_condition("average")
        bot.handle(self.msg("dunno"))                        # not a figure
        self.assertIn("525000", self.last_say())             # gentle reprompt with an example
        self.assertIn(1, bot.PENDING)                        # still mid-intake, not abandoned

    def test_no_public_data_or_finance_gates_before_first_value(self):
        seen = self.capture_run_value()
        bot.PENDING[1] = {"address": "58 Cronin Street SE15 6JH"}
        bot.handle(self.cb("aud:buyer"))
        self.tap_condition("average")
        self.assertIn("asking price", self.last_say())
        bot.handle(self.cb("q:asking:skip"))
        all_text = self.all_say_text().lower()
        self.assertNotIn("floor area", all_text)
        self.assertNotIn("deposit", all_text)
        self.assertNotIn("household income", all_text)
        self.assertIn("answers", seen)

    def test_wizard_without_pending_asks_for_address(self):
        bot.handle(self.cb("q:beds:2"))
        self.assertIn("address first", self.last_say())


# ----------------------------------------------------- condition sub-survey -> finish tier
class TestConditionSurvey(BotTestBase):
    """The condition sub-survey must map to one of the engine's five finish tiers,
    deterministically, and move the figure ONLY through that finish_quality path."""

    def test_derives_into_engine_tiers_only(self):
        # whatever the signals, the derived tier is one the engine actually accepts
        for tier in ("needs_renovation", "needs_modernising", "average", "high", "very_high"):
            s, k, b, p = BotTestBase._FINISH_TAPS[tier]
            ans = {"c_state": int(s), "c_kitchen": int(k), "c_bath": int(b), "c_premium": int(p)}
            got, _ = bot.derive_finish(ans)
            self.assertEqual(got, tier)
            self.assertIn(got, appraise.CONDITION_DISCOUNT.keys() | {"average", "high", "very_high"})

    def test_no_signals_defaults_to_average_silently(self):
        tier, disclosure = bot.derive_finish({})
        self.assertEqual(tier, "average")
        self.assertIsNone(disclosure)                # nothing to disclose, figure unmoved

    def test_explicit_finish_is_respected_untouched(self):
        # landing handoff / direct pick already set finish: never override it
        tier, disclosure = bot.derive_finish({"finish": "high", "c_state": 0})
        self.assertEqual(tier, "high")
        self.assertIsNone(disclosure)

    def test_renovation_floor_dominates_fittings(self):
        # a gut job does not earn high-spec credit even if someone ticks premium materials
        tier, _ = bot.derive_finish({"c_state": 0, "c_kitchen": 2, "c_bath": 2, "c_premium": 2})
        self.assertEqual(tier, "needs_renovation")

    def test_marble_neighbour_outranks_plain_same_size(self):
        # the user's case: identical size, premium finish must price ABOVE plain
        plain, _ = bot.derive_finish({"c_state": 2, "c_kitchen": 0, "c_bath": 0, "c_premium": 0})
        marble, _ = bot.derive_finish({"c_state": 2, "c_kitchen": 2, "c_bath": 2, "c_premium": 2})
        self.assertEqual(plain, "average")
        self.assertEqual(marble, "very_high")
        self.assertGreater(bot.FINISH_TIERS.index(marble), bot.FINISH_TIERS.index(plain))

    def test_mid_range_fittings_stay_average(self):
        # modern mid-range kitchen + bath is what an average home already has: not high-spec
        tier, _ = bot.derive_finish({"c_state": 2, "c_kitchen": 1, "c_bath": 1, "c_premium": 0})
        self.assertEqual(tier, "average")

    def test_one_genuinely_high_end_element_lifts_to_high(self):
        tier, _ = bot.derive_finish({"c_state": 2, "c_kitchen": 2, "c_bath": 1, "c_premium": 0})
        self.assertEqual(tier, "high")

    def test_full_refurb_is_at_least_high(self):
        tier, _ = bot.derive_finish({"c_state": 4, "c_kitchen": 0, "c_bath": 0, "c_premium": 0})
        self.assertEqual(tier, "high")

    def test_disclosure_names_tier_and_states_it_moves_the_figure(self):
        _, disclosure = bot.derive_finish({"c_state": 2, "c_kitchen": 2, "c_bath": 2, "c_premium": 2})
        self.assertIn("PREMIUM", disclosure)
        self.assertIn("moves your figure", disclosure)
        self.assertIn("premium materials", disclosure)   # the premium signal is named
        self.assertIn("luxury bathrooms", disclosure)    # the marble/stone bath signal

    def test_wizard_threads_derived_tier_into_engine_and_discloses(self):
        seen = self.capture_run_value()
        bot.PENDING[1] = {"address": "58 Cronin Street SE15 6JH"}
        self.run_wizard("agent", finish="very_high")
        self.assertEqual(seen["answers"]["finish"], "very_high")   # derived, then valued
        self.assertIn("PREMIUM", self.all_say_text())              # disclosed in chat


# ----------------------------------------------------------------- buy / credit / refund
class TestPayPaths(BotTestBase):
    def test_buy_sends_pack_invoice(self):
        # buying a single valuation needs no membership - tapping the pack raises its invoice
        bot.PENDING[1] = {"address": "x", "r": make_r()}
        bot.handle(self.cb("buy:vendor:consumer"))
        self.assertIn("sendInvoice", self.tg_methods())
        inv = next(p for m, p in self.tgs if m == "sendInvoice")
        self.assertEqual(inv["payload"], "buy:vendor:consumer")
        self.assertEqual(inv["prices"][0]["amount"], bot._stars(300))   # intro price applied
        self.assertEqual(inv["provider_token"], "")          # Stars: empty provider token
        self.assertEqual(inv["currency"], "XTR")

    def test_buy_full_pack_priced_correctly(self):
        bot.PENDING[1] = {"address": "x", "r": make_r()}
        bot.handle(self.cb("buy:agent:full"))
        inv = next(p for m, p in self.tgs if m == "sendInvoice")
        self.assertEqual(inv["prices"][0]["amount"], bot._stars(600))   # the full pack, intro applied

    def test_pay_without_credit_shows_packs_not_invoice(self):
        bot.PENDING[1] = {"address": "x", "r": make_r()}
        bot.handle(self.cb("pay:vendor"))
        self.assertNotIn("sendInvoice", self.tg_methods())   # no auto-charge
        self.assertIn("Evidence pack", self.all_say_text())  # the packs are offered instead

    def test_pay_with_credit_unlocks_full_kit_and_spends(self):
        bot.redeem_code(1, "TAUK")
        bot.PENDING[1] = {"address": "x", "r": make_r()}
        bot.handle(self.cb("pay:vendor"))
        self.assertEqual(bot.free_credits(1), 0)             # credit spent
        self.assertIn("evidence-based", self.all_say_text())       # figures delivered
        self.assertIn("report.pdf", [p[1] for p in self.docs])   # full kit, real PDF

    def test_credit_refunded_when_delivery_fails(self):
        bot.redeem_code(1, "TAUK")
        bot.PENDING[1] = {"address": "x", "r": make_r()}
        bot.deliver_components = lambda *a, **k: False        # simulate a delivery failure
        bot.handle(self.cb("pay:vendor"))
        self.assertEqual(bot.free_credits(1), 1)             # credit handed back
        self.assertIn("put your free unlock back", self.all_say_text())

    def test_credit_refunded_when_pending_lost(self):
        # user had a credit and tapped reveal, but the process restarted -> PENDING gone
        bot.redeem_code(1, "TAUK")
        bot.handle(self.cb("pay:vendor"))
        self.assertEqual(bot.free_credits(1), 1)             # not robbed of the credit


# ----------------------------------------------------------------- payments (Stars)
class TestPayments(BotTestBase):
    def _payment(self, payload, uid=1, chat=1):
        return {"message": {"chat": {"id": chat}, "from": {"id": uid},
                            "successful_payment": {"invoice_payload": payload}}}

    def test_pre_checkout_is_answered_ok(self):
        bot.handle({"pre_checkout_query": {"id": "p1"}})
        self.assertIn("answerPreCheckoutQuery", self.tg_methods())

    def test_subscription_payment_grants_sub(self):
        bot.handle(self._payment("sub"))
        self.assertTrue(bot.subscribed(1))

    def test_pack_payment_delivers_only_its_components(self):
        # the consumer pack is PDF + HTML: the report goes out, the email template does not
        bot.PENDING[1] = {"address": "x", "r": make_r()}
        bot.handle(self._payment("buy:vendor:consumer"))
        self.assertIn("evidence-based", self.all_say_text())       # figures + report delivered
        self.assertIn("report.pdf", [p[1] for p in self.docs])
        self.assertNotIn("Subject line", self.all_say_text())   # email is in the full pack only

    def test_full_pack_payment_delivers_email_too(self):
        bot.PENDING[1] = {"address": "x", "r": make_r()}
        bot.handle(self._payment("buy:agent:full"))
        self.assertIn("Subject line", self.all_say_text())   # the email template is included
        self.assertIn("Action plan", self.all_say_text())    # and the plan

    def test_report_path_threads_area_context_into_build(self):
        # the bot must gather area context and hand it to report.build, so the PDF and the
        # HTML render the Area/Safety/Environment/Planning sections identically. Without this
        # the two surfaces drift: the HTML panels light up but the PDF sections are blank.
        import area_context as _ctx, report as _report
        sentinel = {"sections": {}, "present": {"overpass": True}}
        orig_gather = _ctx.gather
        _ctx.gather = lambda subject, summary=None, anchors=None: sentinel
        self.addCleanup(setattr, _ctx, "gather", orig_gather)
        captured = {}
        orig_build = _report.build
        _report.build = lambda r, audience, **k: (
            captured.update(k) or ("report.pdf", "report_interactive.html"))
        self.addCleanup(setattr, _report, "build", orig_build)
        bot.PENDING[1] = {"address": "x", "r": make_r()}
        bot.handle(self._payment("buy:vendor:consumer"))
        self.assertIs(captured.get("context"), sentinel)   # gathered context reached the builder

    def test_paid_pack_failure_grants_retry_credit(self):
        bot.PENDING[1] = {"address": "x", "r": make_r()}
        bot.deliver_components = lambda *a, **k: False
        bot.handle(self._payment("buy:vendor:full"))
        self.assertEqual(bot.free_credits(1), 1)             # paid user gets a free retry
        self.assertIn("free unlock", self.all_say_text())

    def _patch(self, name, fn):
        """Swap a bot attribute for this test only, restoring it afterwards."""
        orig = getattr(bot, name); self.addCleanup(setattr, bot, name, orig)
        setattr(bot, name, fn)

    def test_miniapp_purchase_delivers_the_pack(self):
        # a Mini App purchase carries a self-contained intent (written by server.py); on
        # payment the bot re-runs the engine on those inputs and delivers - no PENDING needed
        self._patch("run_value", lambda chat, address, answers=None: make_r())
        self._patch("consume_intent", lambda sid: {
            "uid": 1, "address": "58 Cronin Street SE15 6JH", "audience": "agent",
            "pack": "full", "beds": 3, "finish": "average", "investment": False})
        bot.handle(self._payment("mbuy:abc123"))
        self.assertIn("report.pdf", [p[1] for p in self.docs])   # the full pack delivered
        self.assertIn("Subject line", self.all_say_text())        # incl. the email (full pack only)

    def test_widget_handoff_delivers_with_details_no_wizard(self):
        # /start run_<sid> carries the full intake; the bot must deliver straight away and
        # NEVER ask the wizard's questions ("Who are you?" / "Question 1 of")
        self._patch("run_value", lambda chat, address, answers=None: make_r())
        self._patch("consume_intent", lambda sid: {
            "uid": 1, "address": "58 Cronin Street SE15 6JH", "audience": "vendor",
            "beds": 2, "finish": "high", "investment": False})
        bot.handle(self.msg("/start run_abc123"))
        txt = self.all_say_text()
        self.assertNotIn("Who are you?", txt)
        self.assertNotIn("Question 1 of", txt)
        self.assertIn("evidence-based", txt)                      # the valuation actually delivered

    def test_widget_handoff_passes_real_inputs_to_engine(self):
        captured = {}
        self._patch("run_value", lambda chat, address, answers=None:
                    captured.update(address=address, answers=answers or {}) or make_r())
        self._patch("consume_intent", lambda sid: {
            "uid": 1, "address": "58 Cronin Street SE15 6JH", "audience": "agent",
            "beds": 4, "finish": "very_high", "investment": True})
        bot.handle(self.msg("/start run_xyz"))
        self.assertEqual(captured["address"], "58 Cronin Street SE15 6JH")
        self.assertEqual(captured["answers"].get("beds"), 4)
        self.assertEqual(captured["answers"].get("finish"), "very_high")
        self.assertTrue(captured["answers"].get("investment"))

    def test_widget_handoff_expired_intent_is_graceful(self):
        self._patch("consume_intent", lambda sid: None)     # link expired / already spent
        bot.handle(self.msg("/start run_gone"))
        self.assertIn("expired", self.all_say_text().lower())

    def test_widget_handoff_uid_mismatch_does_not_deliver(self):
        self._patch("run_value", lambda chat, address, answers=None: make_r())
        self._patch("consume_intent", lambda sid: {
            "uid": 999, "address": "58 Cronin Street SE15 6JH", "audience": "vendor"})
        bot.handle(self.msg("/start run_abc", uid=1))
        self.assertNotIn("Evidence", self.all_say_text())   # someone else's intent never delivers

    def test_miniapp_purchase_uid_mismatch_is_refunded(self):
        # an intent that doesn't belong to the paying user must never deliver
        self._patch("run_value", lambda chat, address, answers=None: make_r())
        self._patch("consume_intent", lambda sid: {
            "uid": 999, "address": "x", "audience": "agent", "pack": "full"})
        bot.handle(self._payment("mbuy:abc", uid=1))
        self.assertNotIn("report.pdf", [p[1] for p in self.docs])
        self.assertEqual(bot.free_credits(1), 1)                  # retry credit, not robbed
        self.assertIn("free unlock", self.all_say_text())


# ----------------------------------------------------------------- referrals
class TestReferrals(BotTestBase):
    def test_referral_code_is_stable(self):
        self.assertEqual(bot.referral_code(1), bot.referral_code(1))

    def test_invite_returns_deep_link(self):
        bot.handle(self.msg("/invite"))
        t = self.last_say()
        self.assertIn("ref_", t)
        self.assertIn(bot.referral_code(1), t)

    def test_no_self_referral(self):
        code = bot.referral_code(1)
        self.assertFalse(bot.attach_referral(1, code))

    def test_unknown_code_does_not_attach(self):
        self.assertFalse(bot.attach_referral(2, "ZZZZZZ"))

    def test_referral_pays_out_once(self):
        a, b = 100, 200
        self.assertTrue(bot.attach_referral(b, bot.referral_code(a)))
        self.assertEqual(bot.convert_referral(b), a)     # first conversion credits the inviter
        self.assertIsNone(bot.convert_referral(b))        # second time: nothing more
        self.assertEqual(bot.free_credits(a), 1)
        self.assertEqual(bot.ref_earned(a), 1)

    def test_invite_link_then_first_pack_credits_inviter(self):
        a, b = 100, 200
        code = bot.referral_code(a)
        bot.handle(self.msg(f"/start ref_{code}", uid=b, chat=b))
        self.assertEqual(bot.load_ent()[str(b)].get("referred_by"), a)
        # b completes their first paid pack
        bot.PENDING[b] = {"address": "x", "r": make_r()}
        bot.handle({"message": {"chat": {"id": b}, "from": {"id": b},
                                "successful_payment": {"invoice_payload": "buy:vendor:consumer"}}})
        self.assertEqual(bot.free_credits(a), 1)          # inviter earned a free valuation
        self.assertTrue(any(c == a and "invited" in t for c, t, _ in self.says))   # and was told


# ----------------------------------------------------------------- deliver_full robustness
class TestDeliverFull(BotTestBase):
    def test_returns_true_on_success(self):
        self.assertTrue(bot.deliver_full(1, make_r(), "vendor"))

    def test_maps_failure_does_not_break_core_report(self):
        bot.maps_tools.street_view = lambda a, o: (_ for _ in ()).throw(RuntimeError("maps down"))
        # core report must still succeed and return True
        self.assertTrue(bot.deliver_full(1, make_r(), "vendor"))
        self.assertIn("evidence-based", self.all_say_text())

    def test_products_failure_does_not_break_core_report(self):
        # a personalised product (plan / targets / email) throwing must never sink the report
        bot.products.plan_of_action = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        bot.products.target_listings = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("api down"))
        self.assertTrue(bot.deliver_full(1, make_r(), "vendor"))
        self.assertIn("evidence-based", self.all_say_text())

    def test_components_subset_delivers_only_what_was_bought(self):
        # a report-only delivery sends the PDF but not the plan/email of the full pack
        bot.deliver_components(1, make_r(), "agent", ["report"])
        self.assertIn("report.pdf", [p[1] for p in self.docs])
        self.assertNotIn("Action plan", self.all_say_text())
        self.assertNotIn("Subject line", self.all_say_text())

    def test_map_component_is_an_interactive_google_maps_link(self):
        # the map is a real, openable Google Maps route - never a static picture again
        bot.deliver_components(1, make_r(), "agent", ["map"])
        urls = [b["url"] for _, _, kb in self.says if kb for row in kb for b in row if "url" in b]
        self.assertTrue(any("google.com/maps" in u for u in urls), urls)
        pics = [p[1] for p in self.photos]
        self.assertNotIn("_route.png", pics)
        self.assertNotIn("_targets.png", pics)

    def test_pdf_build_failure_still_delivers_figures(self):
        # if the PDF can't be built, the in-chat figures card is the safety net so a
        # paid user is never left empty-handed (and the caller doesn't refund).
        import report as _report
        _report.build = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fpdf2 missing"))
        self.assertTrue(bot.deliver_full(1, make_r(), "vendor"))
        self.assertIn("evidence-based", self.all_say_text())
        self.assertEqual(self.docs, [])                      # no document went out

    def test_full_report_sends_pdf_and_interactive(self):
        bot.deliver_full(1, make_r(), "agent")
        mimes = [d[3] for d in self.docs]
        self.assertIn("application/pdf", mimes)
        self.assertIn("text/html", mimes)

    def test_interactive_delivery_mints_and_sends_hosted_link(self):
        # the hosted /r/<token> link must be minted, threaded INTO report.build (so the PDF
        # can print a clickable link, not a 'open the attached file' dead-end), AND shown in
        # the HTML caption. This is the bug the user hit: a report that promised a link, then
        # had none.
        import report as _report
        captured = {}
        orig = _report.build
        def _spy(r, audience, **k):
            captured["link"] = k.get("link")
            return orig(r, audience, **k)
        _report.build = _spy
        # a hosted link is only emitted when a server is actually configured as reachable;
        # set HONESTLY_PUBLIC_URL to stand in for the deployed /r/ server.
        prev = os.environ.get("HONESTLY_PUBLIC_URL")
        os.environ["HONESTLY_PUBLIC_URL"] = "https://share.example.com"
        try:
            bot.deliver_components(1, make_r(), "agent", ["report", "html"])
        finally:
            if prev is None: os.environ.pop("HONESTLY_PUBLIC_URL", None)
            else: os.environ["HONESTLY_PUBLIC_URL"] = prev
        self.assertTrue(captured.get("link"), "no link passed into report.build")
        self.assertIn("/r/", captured["link"])
        # and the same link rides in the interactive HTML caption that goes to the user
        html_caps = [c for _, _, c, mime in self.docs if mime == "text/html"]
        self.assertTrue(html_caps and captured["link"] in html_caps[0],
                        f"link not in caption: {html_caps}")

    def test_no_hosted_link_when_no_server_configured(self):
        # the honesty fix: with no HONESTLY_PUBLIC_URL and no Mini App origin, we must NOT
        # invent a usehonestly.co.uk link that has no DNS / no running server behind it.
        # public_base() returns "" and the delivery falls back to the offline-file message.
        prev = {k: os.environ.pop(k, None) for k in ("HONESTLY_PUBLIC_URL", "HONESTLY_WEBAPP_URL")}
        try:
            self.assertEqual(bot.public_base(), "")
            import report as _report
            captured = {}
            orig = _report.build
            def _spy(r, audience, **k):
                captured["link"] = k.get("link")
                return orig(r, audience, **k)
            _report.build = _spy
            bot.deliver_components(1, make_r(), "agent", ["report", "html"])
            self.assertIsNone(captured.get("link"), "emitted a link with no server configured")
            # no caption claims a hosted URL
            html_caps = [c for _, _, c, mime in self.docs if mime == "text/html"]
            self.assertFalse(any("/r/" in c for c in html_caps), html_caps)
        finally:
            for k, v in prev.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v

    def test_public_base_only_when_server_configured(self):
        prev = {k: os.environ.pop(k, None) for k in ("HONESTLY_PUBLIC_URL", "HONESTLY_WEBAPP_URL")}
        try:
            # nothing configured -> no link, never a guessed domain
            self.assertEqual(bot.public_base(), "")
            # a live Mini App origin is a real deployed server.py (serves /r/ too)
            os.environ["HONESTLY_WEBAPP_URL"] = "https://app.usehonestly.co.uk/webapp?x=1"
            self.assertEqual(bot.public_base(), "https://app.usehonestly.co.uk")
            # explicit override wins
            os.environ["HONESTLY_PUBLIC_URL"] = "https://share.example.com/"
            self.assertEqual(bot.public_base(), "https://share.example.com")
        finally:
            for k, v in prev.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v

    def test_delivery_includes_schools_brief(self):
        # every audience gets the honest schools context, with an Ofsted link
        bot.deliver_full(1, make_r(), "buyer")
        texts = "\n".join(t[1] for t in self.says)
        self.assertIn("Schools nearby", texts)
        self.assertIn("Cronin Primary", texts)
        self.assertIn("reports.ofsted.gov.uk", texts)
        self.assertIn("verify on Ofsted", texts)   # we never assert the rating ourselves


# ----------------------------------------------------------------- card rendering
class TestCard(BotTestBase):
    # The chat card is now a CLEAN HEADLINE - the number, the trust signal, a pointer to the
    # full report. The detail (formula, market steer, macro, momentum, every comparable) lives
    # in the attached PDF/interactive report (covered by the report tests), NOT dumped in chat.
    def test_card_quotes_the_figures(self):
        out = bot.card(make_r(), "vendor")
        self.assertIn("£500,000 - £550,000", out)
        self.assertIn("525,000", out)            # central
        self.assertIn("Offers over £500,000", out)  # guide

    def test_card_shows_trust_signal(self):
        out = bot.card(make_r(), "vendor")
        self.assertIn("88% evidence-based", out)
        self.assertIn("7 sold comparable", out)

    def test_card_points_to_the_full_report(self):
        out = bot.card(make_r(), "buyer")
        self.assertIn("full report", out.lower())

    def test_card_agent_shows_attributes(self):
        out = bot.card(make_r(), "agent")
        self.assertIn("sqm", out)
        self.assertIn("bed", out)

    def test_card_is_clean_not_a_wall(self):
        # the detail belongs in the PDF - the chat headline must NOT dump the macro backdrop,
        # the momentum read or the raw comparable rows.
        out = bot.card(make_r(), "vendor")
        self.assertNotIn("Bank Rate", out)
        self.assertNotIn("Momentum", out)
        self.assertNotIn("Market backdrop", out)
        # short and scannable: a headline, not a thesis
        self.assertLess(len(out.splitlines()), 12)


# ----------------------------------------------------------------- engine pure helpers
class TestEngineHelpers(unittest.TestCase):
    def test_money_formats_gbp(self):
        self.assertEqual(appraise.money(525000), "£525,000")
        self.assertEqual(appraise.money(525000.4), "£525,000")

    def test_round_to_step(self):
        self.assertEqual(appraise.round_to(523400, 25000), 525000)
        self.assertEqual(appraise.round_to(511000, 25000), 500000)

    def test_postcode_extraction(self):
        self.assertEqual(appraise.postcode_of("58 Cronin Street, London SE15 6JH"), "SE15 6JH")
        self.assertEqual(appraise.postcode_of("no postcode here"), "")

    def test_tuid_and_txn_link(self):
        url = "https://x/transaction/AB12CD34"
        self.assertEqual(appraise.tuid_of(url), "AB12CD34")
        self.assertEqual(appraise.txn_link({"hmlr_uri": "http://landregistry.data.gov.uk/data/ppi/transaction/AB12/current"}),
                         "https://landregistry.data.gov.uk/data/ppi/transaction/AB12/current")
        self.assertEqual(appraise.txn_link({"url": url}),
                         "https://www.gov.uk/search-house-prices")


# ----------------------------------------------------------------- subject resolution
class TestSubjectResolution(unittest.TestCase):
    """The defect that made the bot look broken: real flats / new-builds that the
    fuzzy address matcher silently drops. find_subject must fall back to the
    postcode's UPRN list, match the unit number, and never crash on thin records."""

    def setUp(self):
        self._orig_api = appraise.api
        self.calls = []
        appraise.api = self._fake_api

    def tearDown(self):
        appraise.api = self._orig_api

    # A wide UPRN radius like the real /uprns?results=200 returns: the right flat 11
    # sits among same-numbered units on OTHER streets - building name must break the tie.
    UPRNS = [
        {"uprn": 111, "address": "FLAT 11, 16, MARTHA STREET, LONDON, E1 2ER",
         "addressParts": {"secondary": "FLAT 11", "postcode": "E1 2ER"},
         "lat": "51.5", "lng": "-0.05", "classificationCodeDesc": "Flat"},
        {"uprn": 11, "address": "FLAT 11, SHADWELL GARDENS, CABLE STREET, LONDON, E1 2QG",
         "addressParts": {"secondary": "FLAT 11", "postcode": "E1 2QG"},
         "lat": "51.5", "lng": "-0.05", "classificationCodeDesc": "Flat"},
        {"uprn": 13, "address": "FLAT 13, SHADWELL GARDENS, CABLE STREET, LONDON, E1 2QG",
         "addressParts": {"secondary": "FLAT 13", "postcode": "E1 2QG"},
         "lat": "51.5", "lng": "-0.05", "classificationCodeDesc": "Flat"},
    ]

    def _fake_api(self, endpoint, key, _retries=5, **params):
        self.calls.append(endpoint)
        if endpoint == "address-match-uprn":
            return {"data": []}                       # fuzzy matcher finds nothing
        if endpoint == "uprns":
            return {"data": self.UPRNS if params.get("postcode") == "E1 2QG" else []}
        if endpoint == "uprn":
            # thin new-build record: no propertyType, no area, no beds
            return {"data": {"address": f"FLAT {params['uprn']}, SHADWELL GARDENS, E1 2QG",
                             "lat": "51.5", "lng": "-0.05", "internalArea": None,
                             "estimatedBedrooms": None, "propertyType": None}}
        raise AssertionError("unexpected endpoint " + endpoint)

    def test_plain_address_resolves_correct_building(self):
        # user just types the address - no 'Flat', no commas - and gets the RIGHT one
        subj = appraise.find_subject("11 Shadwell Gardens E1 2QG", "K")
        self.assertEqual(subj["uprn"], 11)            # Shadwell, not Martha Street
        self.assertIn("uprns", self.calls)            # fallback used
        self.assertEqual(subj["type"], "flat")        # classification carried through
        self.assertIsNone(subj["sqm"])                # thin record, no crash

    def test_uprns_pulled_wide(self):
        appraise.find_subject("11 Shadwell Gardens E1 2QG", "K")
        # must request a wide radius or large developments are missed
        self.assertTrue(any(c == "uprns" for c in self.calls))

    def test_truly_absent_unit_is_helpful_not_a_crash(self):
        with self.assertRaises(SystemExit) as cm:
            appraise.find_subject("99 Shadwell Gardens E1 2QG", "K")
        msg = str(cm.exception)
        self.assertIn("E1 2QG", msg)
        self.assertIn("SHADWELL", msg.upper())        # shows nearby real records

    def test_no_postcode_gives_helpful_message(self):
        with self.assertRaises(SystemExit) as cm:
            appraise.find_subject("just some words", "K")
        self.assertIn("postcode", str(cm.exception).lower())

    def test_unknown_postcode_is_not_a_crash(self):
        with self.assertRaises(SystemExit) as cm:
            appraise.find_subject("1 Nowhere Lane ZZ1 9ZZ", "K")
        self.assertIn("ZZ1 9ZZ", str(cm.exception))

    def test_unit_token_parsing(self):
        self.assertEqual(appraise._unit_token("Flat 13 Shadwell Gardens E1 2QG", "E1 2QG"), "13")
        self.assertEqual(appraise._unit_token("11 Shadwell Gardens E1 2QG", "E1 2QG"), "11")
        self.assertEqual(appraise._unit_token("Apartment 4B, X Road, E1 2QG", "E1 2QG"), "4B")


class TestCommercialAggregatorDisabled(unittest.TestCase):
    """Commercial same-data aggregators must not be valuation fallbacks.

    Paid value is decision intelligence over our direct public spine, not paying another
    provider for HMLR/EPC-derived facts.
    """

    SD_RECORDS = [{"attributes": {
        "address": {"simplified_format": {"house_number": "58", "street": "Cronin Street",
                                          "town": "London", "postcode": "SE15 6JH"},
                    "royal_mail_format": {"building_number": "58"}},
        "identities": {"ordnance_survey": {"uprn": "100022"}},
        "location": {"coordinates": {"latitude": 51.473, "longitude": -0.066}},
        "internal_area_square_metres": 103, "property_type": {"value": "Terraced"},
        "number_of_bedrooms": {"value": 3}, "number_of_bathrooms": {"value": 1},
        "energy_performance": {"energy_efficiency": {"current_efficiency": 64,
                               "current_rating": "D", "potential_rating": "B"}},
        "council_tax": {"band": "B", "current_annual_charge": 1611.0},
        "tenure": {"tenure_type": "Freehold", "lease_details": {}},
        "transactions": [{"price": 525000, "date": "2021-09-15", "is_new_build": False}],
    }}]

    def test_enrich_off_never_calls_streetdata(self):
        called = {"n": 0}
        def boom(*a, **k):
            called["n"] += 1
            raise AssertionError("street_postcode must not fire when enrich is off")
        with mock.patch.object(appraise, "street_postcode", boom), \
             mock.patch.object(appraise, "_resolve_uprn", side_effect=RuntimeError("PD quota X14")):
            with self.assertRaises(RuntimeError):
                appraise.find_subject("58 Cronin Street, SE15 6JH", "K", enrich=False)
        self.assertEqual(called["n"], 0)

    def test_pd_down_does_not_fall_back_to_streetdata_subject(self):
        called = {"n": 0}
        def boom(*a, **k):
            called["n"] += 1
            raise AssertionError("street_postcode must not fire")
        with mock.patch.object(appraise, "_resolve_uprn", side_effect=RuntimeError("PD quota X14")), \
             mock.patch.object(appraise, "street_postcode", boom):
            with self.assertRaises(RuntimeError):
                appraise.find_subject("58 Cronin Street, SE15 6JH", "K", enrich=True)
        self.assertEqual(called["n"], 0)


class TestCompBanding(unittest.TestCase):
    """candidate_comps must not divide-by / multiply a None subject size."""
    SOLD = [{"price": 400000 + i*1000, "sqm": 50 + i, "dist": 0.1 + i*0.01,
             "address": f"{i} Some Street"} for i in range(20)]

    def test_band_with_known_size(self):
        subj = {"sqm": 55, "address": "X, E1 2QG"}
        c = appraise.candidate_comps(self.SOLD, subj, 0.5)
        self.assertTrue(all(r.get("psm") for r in c))

    def test_band_with_unknown_size_uses_proxy(self):
        subj = {"sqm": None, "address": "X, E1 2QG"}
        c = appraise.candidate_comps(self.SOLD, subj, 0.5)   # must not raise
        self.assertTrue(len(c) >= 1)

    def test_proxy_sqm_from_nearest(self):
        self.assertIsNotNone(appraise._proxy_sqm(self.SOLD, {"sqm": None}))
        self.assertIsNone(appraise._proxy_sqm([], {"sqm": None}))


# ----------------------------------------------------------- comparability scoring
class TestComparabilityScore(unittest.TestCase):
    """score_comp / weighted_median / sold_median: the glass-box similarity matrix.
    A score penalises only what the record actually carries; missing fields are neutral."""

    def test_perfect_comp_scores_near_one(self):
        subj = {"sqm": 84, "tenure": "leasehold", "class": "flat"}
        r = {"dist": 0.0, "sqm": 84, "psm": 10000, "price": 840000,
             "date": str(appraise.TODAY), "tenure": "leasehold", "class": "flat"}
        score, parts = appraise.score_comp(r, subj, 10000)
        self.assertGreater(score, 0.95)
        self.assertAlmostEqual(sum(abs(x) for x in parts.values()), 0.0, places=1)

    def test_penalties_accumulate_and_clamp(self):
        # far, wrong size, wrong gbp/sqm, ancient, wrong tenure -> very weak, never below floor
        subj = {"sqm": 84, "tenure": "leasehold", "class": "flat"}
        r = {"dist": 2.0, "sqm": 200, "psm": 30000, "price": 6000000,
             "date": "2010-01-01", "tenure": "freehold", "class": "flat"}
        score, parts = appraise.score_comp(r, subj, 10000)
        self.assertGreaterEqual(score, 0.05)
        self.assertLess(score, appraise.COMP_WEAK)
        self.assertIn("location", parts)
        self.assertIn("recency", parts)
        self.assertEqual(parts["tenure"], -12)

    def test_missing_fields_are_neutral(self):
        # a bare record (no date/tenure/class) must not be punished for absent data
        subj = {"sqm": 84}
        r = {"dist": 0.0, "sqm": 84, "psm": 10000, "price": 840000}
        score, parts = appraise.score_comp(r, subj, 10000)
        self.assertGreater(score, 0.95)
        self.assertNotIn("recency", parts)
        self.assertNotIn("tenure", parts)

    def test_weighted_median_pulls_toward_heavy_weight(self):
        # equal spread, heavier weight on the top value -> midpoint lands on it
        pairs = [(100, 1), (200, 1), (300, 9)]
        self.assertEqual(appraise.weighted_median(pairs), 300)

    def test_weighted_median_falls_back_to_plain_median(self):
        self.assertEqual(appraise.weighted_median([(100, 0), (200, 0), (300, 0)]), 200)
        self.assertIsNone(appraise.weighted_median([]))

    def test_sold_median_rounds_to_thousand(self):
        comps = [{"price": 401234, "score": 1.0}, {"price": 399876, "score": 1.0}]
        m = appraise.sold_median(comps)
        self.assertEqual(m % 1000, 0)


# ----------------------------------------------------------------- persistence (store.py)
import store as _store_mod

class _StoreTempMixin:
    """Point store.py at a throwaway DB for the duration of a test, never the real one."""
    def setUp(self):
        import tempfile
        fd, self._dbpath = tempfile.mkstemp(suffix=".db")
        os.close(fd); os.remove(self._dbpath)
        self._prev_path, self._prev_inited = _store_mod.DB_PATH, _store_mod._INITED
        _store_mod.DB_PATH, _store_mod._INITED = self._dbpath, False

    def tearDown(self):
        _store_mod.DB_PATH, _store_mod._INITED = self._prev_path, self._prev_inited
        for p in (self._dbpath, self._dbpath + "-wal", self._dbpath + "-shm"):
            try:
                if os.path.exists(p): os.remove(p)
            except Exception:
                pass

    SUMMARY = {"address": "1 Test Street, London EC1V 1AE", "audience": "agent",
               "low": 900000, "high": 1080000, "central": 915000, "guide": 800000,
               "investment": False}


class TestStore(_StoreTempMixin, unittest.TestCase):
    def test_appraisal_roundtrip_and_district(self):
        tok = _store_mod.record_appraisal(self.SUMMARY, finish="average",
                                          source="test", tier="prophet")
        self.assertTrue(tok)
        got = _store_mod.get_appraisal(tok)
        self.assertEqual(got["central"], 915000)
        self.assertEqual(got["postcode"], "EC1V 1AE")
        self.assertEqual(got["postcode_district"], "EC1V")
        self.assertEqual(got["summary"]["guide"], 800000)

    def test_district_helper(self):
        self.assertEqual(_store_mod.district_of("EC1V 1AE"), "EC1V")
        self.assertEqual(_store_mod.district_of("Flat 1, 2 Road, London EC1V 1AE"), "EC1V")
        self.assertIsNone(_store_mod.district_of("nowhere in particular"))

    def test_token_lifecycle(self):
        tok = _store_mod.record_appraisal(self.SUMMARY)
        _store_mod.record_deliverable(tok, "html", path="/tmp/x.html", body="<html>BODY</html>")
        link = _store_mod.mint_token(tok, ttl_days=90)
        res = _store_mod.resolve_token(link)
        self.assertTrue(res["ok"])
        self.assertEqual(res["html"], "<html>BODY</html>")
        self.assertEqual(res["address"], self.SUMMARY["address"])
        # unknown / revoked
        self.assertEqual(_store_mod.resolve_token("garbage")["reason"], "unknown")
        self.assertTrue(_store_mod.revoke_token(link))
        self.assertEqual(_store_mod.resolve_token(link)["reason"], "revoked")

    def test_token_expiry(self):
        tok = _store_mod.record_appraisal(self.SUMMARY)
        _store_mod.record_deliverable(tok, "html", body="<html>x</html>")
        link = _store_mod.mint_token(tok, ttl_days=None)  # permanent...
        with _store_mod._conn() as c:                      # ...then force it stale
            c.execute("UPDATE tokens SET expires_at=? WHERE token=?", (1.0, link))
        self.assertEqual(_store_mod.resolve_token(link)["reason"], "expired")

    def test_market_analysis_cache_and_ttl(self):
        _store_mod.record_market_analysis("EC1V", "sentiment", source="hit_scan",
                                          payload={"raw": 1}, lines=["demand firm"],
                                          sentiment="warm", ttl_hours=24)
        ma = _store_mod.get_market_analysis("EC1V", "sentiment")
        self.assertEqual(ma["lines"], ["demand firm"])
        self.assertEqual(ma["sentiment"], "warm")
        # a zero-ttl record is never fresh
        _store_mod.record_market_analysis("EC1V", "stale", source="x", ttl_hours=0.0)
        self.assertIsNone(_store_mod.get_market_analysis("EC1V", "stale", fresh_only=True))

    def test_events_audit_trail(self):
        tok = _store_mod.record_appraisal(self.SUMMARY)
        _store_mod.record_deliverable(tok, "pdf", path="/tmp/x.pdf")
        kinds = {e["kind"] for e in _store_mod.recent_events(limit=50)}
        self.assertIn("valuation_requested", kinds)
        self.assertIn("deliverable_built", kinds)

    def test_best_effort_never_raises(self):
        # a broken DB path must degrade to None/[] , not raise into the request path
        _store_mod.DB_PATH, _store_mod._INITED = os.path.join(self._dbpath, "cant", "exist.db"), False
        self.assertIsNone(_store_mod.record_appraisal(self.SUMMARY))
        self.assertIsNone(_store_mod.get_appraisal("x"))
        self.assertEqual(_store_mod.resolve_token("x")["ok"], False)
        self.assertEqual(_store_mod.recent_events(), [])


class TestHostedLink(_StoreTempMixin, unittest.TestCase):
    """The /r/<token> route serves the byte-identical stored HTML; bad tokens get a
    branded page. Driven through a real localhost server, the way it runs in production."""
    def test_route_serves_and_gates(self):
        import server, threading, urllib.request
        from http.server import ThreadingHTTPServer
        tok = _store_mod.record_appraisal(self.SUMMARY)
        body = "<html><body>INTERACTIVE-REPORT-MARKER</body></html>"
        _store_mod.record_deliverable(tok, "html", body=body)
        link = _store_mod.mint_token(tok)

        srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/r/{link}", timeout=5) as r:
                self.assertEqual(r.status, 200)
                self.assertIn("INTERACTIVE-REPORT-MARKER", r.read().decode("utf-8"))
            # an unknown token -> branded 404, never a stack trace, never another report
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/r/nope", timeout=5)
                self.fail("expected 404")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 404)
                self.assertIn("find that report", e.read().decode("utf-8"))
        finally:
            srv.shutdown(); srv.server_close()


class TestWorkspace(_StoreTempMixin, unittest.TestCase):
    """The Pro workspace endpoints: /api/portfolio lists THIS user's saved properties (newest
    first), /api/property returns one they own (with its /r link) and refuses one they don't.
    Auth is exercised by stubbing validate_init_data, the way a signed Telegram launch resolves."""
    def _post(self, port, path, payload):
        import urllib.request, urllib.error
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_portfolio_and_property(self):
        import server, threading
        from http.server import ThreadingHTTPServer
        # two properties for our user (newest last-inserted), one for someone else
        t_old = _store_mod.record_appraisal(
            {"address": "1 Mine Road, London EC1V 1AE", "central": 500000,
             "evidence_purity": {"pct": 88}}, chat_id="999")
        t_new = _store_mod.record_appraisal(
            {"address": "2 Mine Road, London EC1V 1AE", "central": 600000}, chat_id="999")
        _store_mod.record_deliverable(t_new, "html", body="<html>R</html>")
        share = _store_mod.mint_token(t_new)
        t_other = _store_mod.record_appraisal(
            {"address": "9 Theirs Road, London EC1V 1AE", "central": 700000}, chat_id="555")

        prev = server.validate_init_data
        server.validate_init_data = lambda s: {"id": "999", "first_name": "Pat"}
        srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        port = srv.server_address[1]
        th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
        try:
            code, data = self._post(port, "/api/portfolio", {"initData": "x"})
            self.assertEqual(code, 200)
            toks = [p["token"] for p in data["properties"]]
            self.assertEqual(set(toks), {t_old, t_new})           # only OUR rows
            self.assertNotIn(t_other, toks)                       # never another user's
            self.assertEqual(data["properties"][0]["token"], t_new)  # newest first
            by = {p["token"]: p for p in data["properties"]}
            self.assertEqual(by[t_old]["purity"], 88)             # purity read from summary
            self.assertEqual(by[t_new]["share_token"], share)

            code, prop = self._post(port, "/api/property", {"initData": "x", "token": t_new})
            self.assertEqual(code, 200)
            self.assertEqual(prop["central"], 600000)
            self.assertEqual(prop["report_url"], f"/r/{share}")

            code, _ = self._post(port, "/api/property", {"initData": "x", "token": t_other})
            self.assertEqual(code, 403)                           # not theirs
            code, _ = self._post(port, "/api/property", {"initData": "x", "token": "nope"})
            self.assertEqual(code, 404)
        finally:
            server.validate_init_data = prev
            srv.shutdown(); srv.server_close()

    def test_portfolio_requires_signed_launch(self):
        import server, threading
        from http.server import ThreadingHTTPServer
        prev = server.validate_init_data
        server.validate_init_data = lambda s: None               # an unsigned / forged launch
        srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        port = srv.server_address[1]
        th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
        try:
            code, _ = self._post(port, "/api/portfolio", {"initData": "forged"})
            self.assertEqual(code, 403)
        finally:
            server.validate_init_data = prev
            srv.shutdown(); srv.server_close()


class TestCatalogue(unittest.TestCase):
    """The 30-product catalogue + the hybrid Pro economics (included / credits / standalone Stars)
    + the flagship dossier - all offline, all data-gated, all charm-priced."""
    def test_registry_pricing_and_dossier_selftests(self):
        import catalogue, due_diligence
        self.assertEqual(catalogue.selftest(), "ok")
        self.assertEqual(due_diligence.selftest(), "ok")

    def test_hybrid_purchase_mode(self):
        import catalogue
        flag = catalogue.get("buyer_001"); pack = catalogue.get("buyer_002"); read = catalogue.get("buyer_009")
        self.assertTrue(flag["included"] and read["included"] and not pack["included"])
        orig_sub, orig_bal = bot.subscribed, bot.credit_balance
        try:
            bot.subscribed = lambda u: False                 # non-subscriber: always standalone Stars
            self.assertEqual(catalogue.purchase_mode(7, flag), "stars")
            self.assertEqual(catalogue.purchase_mode(7, pack), "stars")
            bot.subscribed = lambda u: True                  # subscriber: flagship/read free
            bot.credit_balance = lambda u: 5
            self.assertEqual(catalogue.purchase_mode(7, flag), "included")
            self.assertEqual(catalogue.purchase_mode(7, read), "included")
            self.assertEqual(catalogue.purchase_mode(7, pack), "credits")   # 2cr <= 5
            bot.credit_balance = lambda u: 1                 # 1 < 2cr -> falls back to Stars
            self.assertEqual(catalogue.purchase_mode(7, pack), "stars")
        finally:
            bot.subscribed, bot.credit_balance = orig_sub, orig_bal

    def test_credit_pool_grant_spend_refund(self):
        import tempfile
        prev = bot.STATE
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd); os.remove(path)
        bot.STATE = path
        try:
            uid = "4242"
            bot.grant_sub(uid)                               # a renewal grants the monthly pool
            self.assertEqual(bot.credit_balance(uid), bot.MONTHLY_CREDITS)
            self.assertTrue(bot.subscribed(uid))
            self.assertTrue(bot.spend_credits(uid, 2))
            self.assertEqual(bot.credit_balance(uid), bot.MONTHLY_CREDITS - 2)
            bot.refund_credits(uid, 2)
            self.assertEqual(bot.credit_balance(uid), bot.MONTHLY_CREDITS)
            self.assertFalse(bot.spend_credits(uid, 999))    # can't overspend
            self.assertEqual(bot.credit_balance(uid), bot.MONTHLY_CREDITS)
            bot.grant_sub(uid)                               # renewal resets the pool
            self.assertEqual(bot.credit_balance(uid), bot.MONTHLY_CREDITS)
        finally:
            for p in (path,):
                try:
                    if os.path.exists(p): os.remove(p)
                except Exception: pass
            bot.STATE = prev


class TestPropertyGraph(unittest.TestCase):
    """The property knowledge graph: builds Property/Transaction/Area nodes + SOLD/IN_AREA/
    COMPARABLE_TO edges from real-shaped HMLR sales, deduplicates a property sold twice, is
    idempotent on re-ingest, and answers comparables/area queries. All offline."""
    def test_graph_build_dedup_idempotent_queries(self):
        import property_graph
        property_graph.selftest()    # self-contained: temp DB, raises on any failure


# ----------------------------------------------------------------- resilience wiring
class TestResilience(unittest.TestCase):
    def test_ipv4_only_patch_is_installed(self):
        import socket
        self.assertIs(socket.getaddrinfo, bot._ipv4_only)

    def test_single_instance_lock_blocks_second(self):
        s1 = bot._single_instance_lock(port=58983)
        with self.assertRaises(SystemExit):
            bot._single_instance_lock(port=58983)
        s1.close()


# ----------------------------------------------------------------- schools / Ofsted
class TestSchools(unittest.TestCase):
    """nearby_schools parses PropertyData's schools shape, sorts by distance, links to
    the official Ofsted report, and degrades to [] - never raising, never inventing a rating."""

    _RESP = {"status": "success", "data": {"state": {"nearest": [
        {"name": "Far School", "phase": "Secondary", "type": "Academy",
         "num_pupils": 900, "distance": "0.80",
         "url": "https://reports.ofsted.gov.uk/far"},
        {"name": "Near Primary", "phase": "Primary", "type": "Community",
         "num_pupils": 210, "distance": "0.15",
         "url": "https://reports.ofsted.gov.uk/near"}]}}}

    def setUp(self):
        import products, appraise
        self.products = products
        self._orig = appraise.api
        appraise.api = lambda endpoint, key, **p: dict(self._RESP)

    def tearDown(self):
        import appraise
        appraise.api = self._orig

    def _r(self):
        return {"subject": {"address": "58 Cronin Street, London SE15 6JH"}}

    def test_nearby_schools_does_not_call_commercial_api(self):
        out = self.products.nearby_schools(self._r(), "k", n=6)
        self.assertEqual(out, [])

    def test_brief_empty_until_direct_public_school_client_lands(self):
        brief = self.products.schools_brief(self.products.nearby_schools(self._r(), "k"))
        self.assertEqual(brief, "")

    def test_empty_when_no_postcode(self):
        self.assertEqual(self.products.nearby_schools({"subject": {"address": "nowhere"}}, "k"), [])

    def test_never_raises_on_api_failure(self):
        import appraise
        appraise.api = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("api down"))
        self.assertEqual(self.products.nearby_schools(self._r(), "k"), [])
        appraise.api = self._orig

    def test_brief_empty_on_no_schools(self):
        self.assertEqual(self.products.schools_brief([]), "")


# ----------------------------------------------------------------- NTSELAT material info
class _RecPDF:
    """A recording fake PDF: captures every string the renderer emits, no fpdf2."""
    def __init__(self):
        self.text = []
        self._y = 40.0
    def get_y(self):           return self._y
    def add_page(self):        self._y = 22.0
    def ln(self, *a):          self._y += (a[0] if a else 1)
    def set_fill_color(self, *a):  pass
    def set_text_color(self, *a):  pass
    def set_draw_color(self, *a):  pass
    def set_line_width(self, *a):  pass
    def set_font(self, *a):    pass
    def set_xy(self, *a):      pass
    def rect(self, *a):        pass
    def line(self, *a):        pass
    def cell(self, w, h, txt="", *a, **k):       self.text.append(str(txt))
    def multi_cell(self, w, h, txt="", *a, **k): self.text.append(str(txt))
    def h2(self, txt):         self.text.append(str(txt))
    def body(self, txt, *a, **k):                self.text.append(str(txt))


class TestMaterialInformation(unittest.TestCase):
    """The NTSELAT Material Information starter: known facts rendered, disclosure-only
    fields become decision-check items, never fabricated."""

    def _render(self, subject):
        import report
        pdf = _RecPDF()
        report._render_material_information(pdf, subject, {"central": 525000})
        return "\n".join(pdf.text)

    def test_renders_ntselat_heading_and_parts(self):
        out = self._render({"address": "58 Cronin Street, London SE15 6JH",
                            "tax": "D", "epc": 72, "sqm": 70, "type": "flat"})
        self.assertIn("Material information (NTSELAT)", out)
        self.assertIn("Part A - Tenure", out)
        self.assertIn("Part A - Council tax band", out)
        self.assertIn("Part C - Flood risk", out)

    def test_known_facts_are_shown(self):
        out = self._render({"address": "x", "tax": "D", "epc": 72,
                            "sqm": 70, "type": "flat"})
        self.assertIn("D", out)              # council tax band we hold
        self.assertIn("score 72", out)       # EPC we hold
        self.assertIn("£525,000", out)       # assessed central value

    def test_unknown_fields_flagged_not_invented(self):
        # We hold none of: utilities, broadband, flood risk -> must be included as usable checks, never blank/fake
        out = self._render({"address": "x"})
        self.assertIn("Decision-check item", out)
        self.assertNotIn("Confirm with seller", out)

    def test_no_em_dash_in_output(self):
        out = self._render({"address": "x", "tax": "C"})
        self.assertNotIn("—", out)      # em dash banned in copy


# ----------------------------------------------------------------- audio walkthrough
class TestAudio(unittest.TestCase):
    """The Voxtral spoken walkthrough: the script reproduces the engine's figures and
    the glass-box chain verbatim, never invents a number, and synthesis degrades to
    None (no key / failure) so it can never block a valuation."""

    _D = {"audience": "vendor", "address": "11 Shadwell Gardens, London E1 2QG",
          "range_str": "£500,000 - £560,000", "central": 530000,
          "sold_median": 525000, "sold_anchor": 472500,
          "market": {"pct": 3.2, "label": "rising"}, "comparable_count": 4}

    def setUp(self):
        import audio
        self.audio = audio

    def test_script_reproduces_the_figures_verbatim(self):
        s = self.audio.walkthrough_script(self._D)
        self.assertIn("530,000 pounds", s)        # central, verbatim
        self.assertIn("525,000 pounds", s)        # sold median
        self.assertIn("472,500 pounds", s)        # condition-adjusted anchor
        self.assertIn("500,000 pounds to 560,000 pounds", s)  # the range
        self.assertIn("3.2 percent above", s)     # live market steer

    def test_script_states_the_chain_and_disclaims(self):
        s = self.audio.walkthrough_script(self._D)
        self.assertIn("median of the sold comparables", s)
        self.assertIn("Land Registry", s)
        self.assertIn("not a formal", s)          # never claims to be a RICS valuation
        self.assertIn("4 comparables", s)

    def test_script_empty_without_a_central_figure(self):
        # nothing honest to say -> say nothing, never narrate an invented number
        self.assertEqual(self.audio.walkthrough_script({"audience": "vendor"}), "")

    def test_no_em_dash_in_spoken_script(self):
        self.assertNotIn("—", self.audio.walkthrough_script(self._D))

    def test_synthesize_returns_none_without_key(self):
        saved = os.environ.pop("MISTRAL_API_KEY", None)
        try:
            self.assertIsNone(self.audio.synthesize("hello", key=None))
            self.assertIsNone(self.audio.walkthrough(self._D, key=None))
        finally:
            if saved is not None:
                os.environ["MISTRAL_API_KEY"] = saved

    def test_synthesize_returns_none_on_empty_text(self):
        self.assertIsNone(self.audio.synthesize("", key="x"))

    def test_save_walkthrough_returns_none_without_key(self):
        saved = os.environ.pop("MISTRAL_API_KEY", None)
        try:
            path = self.audio.save_walkthrough(self._D, "_should_not_exist.mp3", key=None)
            self.assertIsNone(path)
            self.assertFalse(os.path.exists("_should_not_exist.mp3"))
        finally:
            if saved is not None:
                os.environ["MISTRAL_API_KEY"] = saved


if __name__ == "__main__":
    unittest.main(verbosity=2)
