#!/usr/bin/env python3
"""Offline tests for vision.py - the Vision network layer (_annotate) and key are stubbed.

The honesty point under test: vision PROPOSES the condition sub-survey signals from photos
and never decides; it is conservative (no premium credit without clear premium-material
evidence), it leaves overall condition (c_state) for the human, the derived tier matches
the engine's existing derive_finish path, and it degrades to {ok: False} / never raises.
"""
import unittest
from unittest import mock
import vision


def _resp(*per_image_labels):
    """Build a Vision annotate response from lists of (description, score) per image."""
    return {"responses": [
        {"labelAnnotations": [{"description": d, "score": s} for d, s in labels]}
        for labels in per_image_labels
    ]}


_PREMIUM_KITCHEN = _resp([("Countertop", 0.96), ("Marble", 0.91), ("Kitchen", 0.95),
                          ("Cabinetry", 0.88), ("Property", 0.80)])
_LUX_BATH = _resp([("Bathroom", 0.95), ("Marble", 0.90), ("Plumbing fixture", 0.85)])
_PLAIN = _resp([("Property", 0.97), ("Building", 0.93), ("Window", 0.88),
                ("Floor", 0.80)])
_KEY = "test-key"


class TestLabelFlatten(unittest.TestCase):
    def test_keeps_best_score_and_drops_weak(self):
        resp = _resp([("Marble", 0.6), ("Marble", 0.92), ("Wall", 0.50)])
        labels = vision._labels(resp)
        self.assertIn(("marble", 0.92), labels)
        self.assertNotIn("wall", dict(labels))     # 0.50 below the 0.70 threshold


class TestSignalsConservative(unittest.TestCase):
    def test_premium_kitchen_lifts_kitchen_only(self):
        sig = vision._signals_from_labels(vision._labels(_PREMIUM_KITCHEN))
        self.assertEqual(sig["c_kitchen"], 2)
        self.assertIsNone(sig["c_bath"])           # no bathroom evidence -> no bath credit
        self.assertEqual(sig["c_premium"], 1)      # one premium material kind (marble)
        self.assertIsNone(sig["c_state"])          # never inferred from photos

    def test_plain_photos_give_no_lift(self):
        sig = vision._signals_from_labels(vision._labels(_PLAIN))
        self.assertIsNone(sig["c_kitchen"])
        self.assertIsNone(sig["c_bath"])
        self.assertIsNone(sig["c_premium"])

    def test_premium_material_without_room_does_not_credit_room(self):
        sig = vision._signals_from_labels(vision._labels(_resp([("Hardwood", 0.9)])))
        self.assertIsNone(sig["c_kitchen"])
        self.assertIsNone(sig["c_bath"])
        self.assertEqual(sig["c_premium"], 1)


class TestDeriveMatchesEngine(unittest.TestCase):
    def test_derive_uses_bot_path_when_available(self):
        # one high-end lift -> 'high' under the engine rule (c_state absent defaults liveable)
        self.assertEqual(vision._derive({"c_kitchen": 2}), "high")

    def test_two_lifts_make_very_high(self):
        self.assertEqual(vision._derive({"c_kitchen": 2, "c_premium": 2}), "very_high")

    def test_no_signals_default_average(self):
        self.assertEqual(vision._derive({"c_state": None}), "average")

    def test_fallback_mirror_when_bot_unimportable(self):
        with mock.patch.dict("sys.modules", {"bot": None}):   # force ImportError in _derive
            self.assertEqual(vision._derive({"c_kitchen": 2}), "high")
            self.assertEqual(vision._derive({"c_kitchen": 2, "c_bath": 2}), "very_high")


class TestAssess(unittest.TestCase):
    def test_premium_kitchen_proposes_high(self):
        with mock.patch.object(vision, "_key", return_value=_KEY), \
             mock.patch.object(vision, "_annotate", return_value=_PREMIUM_KITCHEN):
            r = vision.assess(["a.jpg"])
        self.assertTrue(r["ok"])
        self.assertEqual(r["proposed_tier"], "high")
        self.assertEqual(r["signals"]["c_kitchen"], 2)
        self.assertIn("confirm", r["note"].lower())
        self.assertIn(r["confidence"], ("low", "medium"))   # photos never exceed medium

    def test_plain_photos_propose_average(self):
        with mock.patch.object(vision, "_key", return_value=_KEY), \
             mock.patch.object(vision, "_annotate", return_value=_PLAIN):
            r = vision.assess(["a.jpg", "b.jpg", "c.jpg"])
        self.assertTrue(r["ok"])
        self.assertEqual(r["proposed_tier"], "average")

    def test_confidence_capped_at_medium(self):
        big = _resp(*([("Countertop", 0.96), ("Marble", 0.92), ("Kitchen", 0.95),
                       ("Bathroom", 0.9), ("Hardwood", 0.9)] for _ in range(4)))
        with mock.patch.object(vision, "_key", return_value=_KEY), \
             mock.patch.object(vision, "_annotate", return_value=big):
            r = vision.assess(["a.jpg", "b.jpg", "c.jpg", "d.jpg"])
        self.assertEqual(r["proposed_tier"], "very_high")
        self.assertEqual(r["confidence"], "medium")

    def test_no_images_degrades(self):
        self.assertFalse(vision.assess([])["ok"])

    def test_no_key_degrades(self):
        with mock.patch.object(vision, "_key", return_value=None):
            r = vision.assess(["a.jpg"])
        self.assertFalse(r["ok"])
        self.assertIn("key", r["reason"])

    def test_caps_image_count(self):
        captured = {}
        def fake(urls, key, timeout=40):
            captured["n"] = len(urls)
            return _PLAIN
        with mock.patch.object(vision, "_key", return_value=_KEY), \
             mock.patch.object(vision, "_annotate", side_effect=fake):
            vision.assess([f"{i}.jpg" for i in range(20)], max_images=8)
        self.assertEqual(captured["n"], 8)

    def test_auth_rejected_degrades(self):
        import urllib.error
        err = urllib.error.HTTPError("u", 403, "no", {}, None)
        with mock.patch.object(vision, "_key", return_value=_KEY), \
             mock.patch.object(vision, "_annotate", side_effect=err):
            r = vision.assess(["a.jpg"])
        self.assertFalse(r["ok"])
        self.assertIn("auth rejected", r["reason"])

    def test_network_error_never_raises(self):
        with mock.patch.object(vision, "_key", return_value=_KEY), \
             mock.patch.object(vision, "_annotate", side_effect=Exception("boom")):
            r = vision.assess(["a.jpg"])
        self.assertFalse(r["ok"])
        self.assertIn("boom", r["reason"])

    def test_unexpected_response_degrades(self):
        with mock.patch.object(vision, "_key", return_value=_KEY), \
             mock.patch.object(vision, "_annotate", return_value={"oops": 1}):
            r = vision.assess(["a.jpg"])
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
