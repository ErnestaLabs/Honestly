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
        "psm": 6176,
        "verdict": {"tone": "ok", "text": "Priced fairly versus the evidence"},
        "evidence": [{"address": "60 Cronin Street", "sqm": 82,
                      "price_str": "£520,000", "date": "2024-03",
                      "verify": "https://propertydata.co.uk/transaction/ABC123"}],
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
        """Pick the audience and tap through the whole intake to the valuation."""
        bot.handle(self.cb(f"aud:{aud}", uid, chat))
        bot.handle(self.cb(f"q:beds:{beds}", uid, chat))
        bot.handle(self.cb(f"q:baths:{baths}", uid, chat))
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

    def test_first_valuation_is_the_full_kit_free(self):
        # a brand-new, non-subscribed user's FIRST valuation is the whole kit, no charge
        bot.PENDING[1] = {"address": "58 Cronin Street SE15 6JH"}
        self.run_wizard("vendor")
        docpaths = [p[1] for p in self.docs]
        self.assertIn("report.pdf", docpaths)               # real PDF, not a teaser image
        self.assertIn("Evidence", self.all_say_text())       # figures delivered
        self.assertTrue(bot.had_first(1))                    # the free taste is now spent
        self.assertIn("That one was on us", self.all_say_text())   # the packs explained
        self.assertIn(1, bot.AWAIT_TESTI)                    # testimonial invited

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
        self.assertIn("Valuation pack", t)               # the packs are offered directly
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
        self.assertIn("Evidence", self.all_say_text())

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
        # the first thing they see is a question, not a valuation
        self.assertIn("Question 1 of", self.last_say())
        self.assertIn("bedrooms", self.last_say())
        self.assertNotIn("answers", seen)                    # engine not called yet

    def test_questions_asked_in_order(self):
        bot.PENDING[1] = {"address": "x"}
        bot.handle(self.cb("aud:agent"))
        self.assertIn("bedrooms", self.last_say())
        bot.handle(self.cb("q:beds:2"))
        self.assertIn("bathrooms", self.last_say())
        bot.handle(self.cb("q:baths:1"))
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
        self.assertEqual(seen["answers"]["beds"], 3)
        self.assertEqual(seen["answers"]["baths"], 2)
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
        bot.handle(self.cb("q:beds:2"))
        bot.handle(self.cb("q:baths:1"))
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
        bot.handle(self.cb("q:beds:2"))
        bot.handle(self.cb("q:baths:1"))
        self.tap_condition("average")
        bot.handle(self.msg("dunno"))                        # not a figure
        self.assertIn("525000", self.last_say())             # gentle reprompt with an example
        self.assertIn(1, bot.PENDING)                        # still mid-intake, not abandoned

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
        self.assertIn("Valuation pack", self.all_say_text()) # the packs are offered instead

    def test_pay_with_credit_unlocks_full_kit_and_spends(self):
        bot.redeem_code(1, "TAUK")
        bot.PENDING[1] = {"address": "x", "r": make_r()}
        bot.handle(self.cb("pay:vendor"))
        self.assertEqual(bot.free_credits(1), 0)             # credit spent
        self.assertIn("Evidence", self.all_say_text())       # figures delivered
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
        self.assertIn("Evidence", self.all_say_text())       # figures + report delivered
        self.assertIn("report.pdf", [p[1] for p in self.docs])
        self.assertNotIn("Subject line", self.all_say_text())   # email is in the full pack only

    def test_full_pack_payment_delivers_email_too(self):
        bot.PENDING[1] = {"address": "x", "r": make_r()}
        bot.handle(self._payment("buy:agent:full"))
        self.assertIn("Subject line", self.all_say_text())   # the email template is included
        self.assertIn("Action plan", self.all_say_text())    # and the plan

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
        self.assertIn("Evidence", txt)                      # the valuation actually delivered

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
        self.assertIn("Evidence", self.all_say_text())

    def test_products_failure_does_not_break_core_report(self):
        # a personalised product (plan / targets / email) throwing must never sink the report
        bot.products.plan_of_action = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        bot.products.target_listings = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("api down"))
        self.assertTrue(bot.deliver_full(1, make_r(), "vendor"))
        self.assertIn("Evidence", self.all_say_text())

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
        self.assertIn("Evidence", self.all_say_text())
        self.assertEqual(self.docs, [])                      # no document went out

    def test_full_report_sends_pdf_and_interactive(self):
        bot.deliver_full(1, make_r(), "agent")
        mimes = [d[3] for d in self.docs]
        self.assertIn("application/pdf", mimes)
        self.assertIn("text/html", mimes)

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
    def test_card_quotes_the_figures(self):
        out = bot.card(make_r(), "vendor")
        self.assertIn("£500,000 - £550,000", out)
        self.assertIn("Evidence", out)
        self.assertIn("verify", out)

    def test_card_has_honesty_footer(self):
        out = bot.card(make_r(), "buyer")
        self.assertIn("sold evidence", out)
        self.assertIn("market will pay", out)

    def test_card_agent_shows_psm(self):
        out = bot.card(make_r(), "agent")
        self.assertIn("/sqm", out)

    def test_card_shows_the_glass_box_working(self):
        # the exact arithmetic chain is on the card, not just in the PDF
        out = bot.card(make_r(), "vendor")
        self.assertIn("How we got here", out)
        self.assertIn("£530,000", out)       # sold median
        self.assertIn("£540,000", out)       # condition-adjusted anchor
        self.assertIn("-2.8%", out)          # live-market steer
        self.assertIn("£525,000", out)       # assessed central

    def test_card_shows_market_steer(self):
        # the value is not anchored on sold data alone - the live-market steer is shown
        out = bot.card(make_r(), "vendor")
        self.assertIn("Softening market", out)
        self.assertIn("live conditions", out)
        self.assertIn("£540,000", out)          # the pre-adjustment sold anchor

    def test_card_shows_macro_backdrop(self):
        # upcoming rates + stamp duty sit beside the figure as forward context
        out = bot.card(make_r(), "buyer")
        self.assertIn("Market backdrop", out)
        self.assertIn("Bank Rate 3.75%", out)
        self.assertIn("next call 18 Jun", out)
        self.assertIn("£16,250", out)           # property-specific stamp duty

    def test_card_shows_live_momentum(self):
        # the live BoE+ONS momentum read renders beside the figure, clearly not in it
        out = bot.card(make_r(), "buyer")
        self.assertIn("Momentum", out)
        self.assertIn("leaning soft", out)
        self.assertIn("Beside the figure, not in it", out)


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
        self.assertEqual(appraise.txn_link({"url": url}),
                         "https://propertydata.co.uk/transaction/AB12CD34")


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

    def test_parses_and_sorts_by_distance(self):
        out = self.products.nearby_schools(self._r(), "k", n=6)
        self.assertEqual(out[0]["name"], "Near Primary")   # closest first
        self.assertEqual(out[1]["name"], "Far School")
        self.assertEqual(out[0]["ofsted_url"], "https://reports.ofsted.gov.uk/near")

    def test_brief_links_ofsted_and_disclaims_rating(self):
        brief = self.products.schools_brief(self.products.nearby_schools(self._r(), "k"))
        self.assertIn("Schools nearby", brief)
        self.assertIn("verify on Ofsted", brief)
        self.assertIn("reports.ofsted.gov.uk/near", brief)

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
    """The NTSELAT Material Information starter: known facts rendered, unknown fields
    honestly flagged 'Confirm with seller', never fabricated."""

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
        # We hold none of: utilities, broadband, flood risk -> must say confirm, never blank/fake
        out = self._render({"address": "x"})
        self.assertIn("Confirm with seller", out)

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
