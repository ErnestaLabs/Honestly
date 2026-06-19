#!/usr/bin/env python3
"""Offline tests for market_analysis.py - every source module is stubbed.

The honesty points under test (plan Verification item 6):
  * gather() never raises, even when every source is down.
  * It degrades to {ok: False} with no lines / no blocks when nothing is reachable.
  * Every rendered figure traces to a source payload - nothing is invented.
  * The company boundary holds: no Hit branding ever appears in the output, and
    Reddit is cited only as social-media sentiment.
  * positioning is pure pass-in data and renders with zero network.
  * persistence is best-effort: a raising store is swallowed, never fatal.
"""
import unittest
from unittest import mock
import market_analysis as ma


def _all_sources_dead():
    """Patch every optional source module to None for the duration of a `with` block."""
    return mock.patch.multiple(
        ma, reddit_intel=None, macro=None, macro_live=None,
        land_registry=None, demand=None, store=None)


class TestFullOutage(unittest.TestCase):
    def test_gather_never_raises_and_degrades(self):
        with _all_sources_dead():
            rec = ma.gather("ZZ99", postcode="ZZ99 9ZZ", region="london",
                            price=480000, persist=True)
        self.assertIsInstance(rec, dict)
        self.assertEqual(rec["district"], "ZZ99")
        self.assertEqual(rec["lines"], [])
        self.assertEqual(rec["blocks"], {})
        self.assertIs(rec["ok"], False)
        self.assertIsNone(rec["sentiment"])

    def test_brief_empty_on_outage(self):
        with _all_sources_dead():
            rec = ma.gather("ZZ99", persist=False)
        self.assertEqual(ma.brief(rec), "")
        self.assertEqual(ma.brief(None), "")
        self.assertEqual(ma.brief({"ok": False}), "")


class TestPositioningIsPureData(unittest.TestCase):
    POS = {"mean_dom": 77, "under_offer_share_pct": 21, "stuck_share_pct": 13}

    def test_positioning_renders_with_every_source_dead(self):
        with _all_sources_dead():
            rec = ma.gather("SE15", positioning=self.POS, persist=False)
        self.assertIs(rec["ok"], True)
        pos = [l for l in rec["lines"] if l["category"] == "positioning"]
        self.assertEqual(len(pos), 1)
        text = pos[0]["text"]
        # only the numbers handed in appear - nothing invented
        self.assertIn("77", text)
        self.assertIn("21%", text)
        self.assertIn("13%", text)
        self.assertEqual(pos[0]["source"], "Live listings (PropertyData)")

    def test_empty_positioning_contributes_nothing(self):
        with _all_sources_dead():
            rec = ma.gather("SE15", positioning={}, persist=False)
        self.assertIs(rec["ok"], False)
        self.assertEqual(rec["lines"], [])


class TestCompanyBoundary(unittest.TestCase):
    def test_reddit_cited_as_social_sentiment_not_hit(self):
        intel = {"sentiment": "cautious", "signal_count": 9,
                 "threads": [{"t": 1}], "themes": ["overpaying", "negotiation"]}
        fake = mock.Mock()
        fake.for_area.return_value = intel
        with mock.patch.multiple(ma, reddit_intel=fake, macro=None, macro_live=None,
                                 land_registry=None, demand=None, store=None):
            rec = ma.gather("SE15", postcode="SE15 5DQ", persist=False)
        self.assertIs(rec["ok"], True)
        self.assertEqual(rec["sentiment"], "cautious")
        blob = ma.brief(rec).lower()
        for banned in ("hit", "hitman", "_hit_sdk", "call_tool_sync"):
            self.assertNotIn(banned, blob, f"company-boundary leak: {banned}")
        self.assertIn("social sentiment", blob)
        self.assertIn("not evidence of value", blob)

    def test_reddit_with_no_threads_contributes_nothing(self):
        fake = mock.Mock()
        fake.for_area.return_value = {"sentiment": "neutral", "threads": []}
        with mock.patch.multiple(ma, reddit_intel=fake, macro=None, macro_live=None,
                                 land_registry=None, demand=None, store=None):
            rec = ma.gather("SE15", persist=False)
        self.assertIs(rec["ok"], False)


class TestSourcesRaisingAreSwallowed(unittest.TestCase):
    def test_each_source_raising_is_caught(self):
        boom = mock.Mock()
        boom.for_area.side_effect = Exception("mcp down")
        boom.outlook.side_effect = Exception("macro down")
        boom.signal.side_effect = Exception("live down")
        boom.hpi_region.side_effect = Exception("hmlr down")
        boom.for_postcode.side_effect = Exception("demand down")
        with mock.patch.multiple(ma, reddit_intel=boom, macro=boom, macro_live=boom,
                                 land_registry=boom, demand=boom, store=None):
            rec = ma.gather("SE15", postcode="SE15 5DQ", region="london",
                            price=480000, persist=False)
        # everything blew up but the read still came back clean and empty
        self.assertIs(rec["ok"], False)
        self.assertEqual(rec["lines"], [])

    def test_persist_failure_is_not_fatal(self):
        store = mock.Mock()
        store.record_market_analysis.side_effect = Exception("db locked")
        with mock.patch.multiple(ma, reddit_intel=None, macro=None, macro_live=None,
                                 land_registry=None, demand=None, store=store):
            rec = ma.gather("SE15",
                            positioning={"mean_dom": 50, "under_offer_share_pct": 30},
                            persist=True)
        self.assertIs(rec["ok"], True)   # a raising store never breaks the read
        store.record_market_analysis.assert_called_once()


class TestHpiBlock(unittest.TestCase):
    def test_hpi_renders_only_present_numbers(self):
        lr = mock.Mock()
        lr.hpi_region.return_value = {"ok": True, "region": "london",
                                      "month": "2026-04", "average_price": 534221.6,
                                      "annual_change_pct": -1.3}
        with mock.patch.multiple(ma, reddit_intel=None, macro=None, macro_live=None,
                                 land_registry=lr, demand=None, store=None):
            rec = ma.gather("SE15", region="london", persist=False)
        line = next(l for l in rec["lines"] if l["category"] == "trend")
        self.assertIn("£534,222", line["text"])     # rounded, comma-grouped
        self.assertIn("down 1.3%", line["text"])
        self.assertIn("never moves the figure", line["text"])

    def test_hpi_not_ok_contributes_nothing(self):
        lr = mock.Mock()
        lr.hpi_region.return_value = {"ok": False, "reason": "no series"}
        with mock.patch.multiple(ma, reddit_intel=None, macro=None, macro_live=None,
                                 land_registry=lr, demand=None, store=None):
            rec = ma.gather("SE15", region="london", persist=False)
        self.assertIs(rec["ok"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
