import math
import tempfile
import unittest
from pathlib import Path

import avm_v2
from tools import avm_backtest, build_avm_fixture


class TestAVMV2ResearchHarness(unittest.TestCase):
    def test_sentiment_features_use_min_sample_neutral(self):
        posts = [{"text": "great transport", "entities": ["transport"], "sentiment": 1.0}]
        f = avm_v2.sentiment_features(posts)
        self.assertEqual(f["status"], "insufficient_sample_neutral")
        self.assertEqual(f["sentiment_multiplier"], 1.0)

    def test_sentiment_features_weight_decay_and_multiplier(self):
        posts = [
            {"date": "2026-06-10", "text": "great safe transport", "entities": ["transport"], "sentiment": 0.8},
            {"date": "2026-06-10", "text": "bad noise", "entities": ["noise"], "sentiment": -0.2},
        ] * 5
        f = avm_v2.sentiment_features(posts, today=__import__("datetime").date(2026, 6, 15))
        self.assertEqual(f["status"], "usable")
        self.assertGreater(f["s_avg"], 0)
        self.assertGreater(f["sentiment_multiplier"], 1.0)
        self.assertLessEqual(f["sentiment_multiplier"], 1.10)

    def test_candidate_modes_are_bounded_and_structured(self):
        base = {"low": 100000, "central": 120000, "high": 140000}
        sent = {"status": "usable", "sentiment_multiplier": 1.1, "sentiment_volatility": 0.5}
        mult = avm_v2.candidate_from_baseline(base, sent, mode="sentiment_multiplier")
        unc = avm_v2.candidate_from_baseline(base, sent, mode="sentiment_uncertainty")
        self.assertEqual(mult["central"], 130000)
        self.assertEqual(unc["central"], 120000)
        self.assertGreater(unc["high"] - unc["low"], base["high"] - base["low"])

    def test_score_predictions(self):
        rows = [
            {"target_price": 100000, "confidence_score": 80, "prediction": {"low": 90000, "central": 100000, "high": 110000}, "sentiment": {"s_avg": 0.2}, "time_on_market_days": 20},
            {"target_price": 200000, "confidence_score": 50, "prediction": {"low": 170000, "central": 220000, "high": 240000}, "sentiment": {"s_avg": -0.2}, "time_on_market_days": 60},
        ]
        m = avm_v2.score_predictions(rows)
        self.assertEqual(m["scored_n"], 2)
        self.assertIsNotNone(m["mape"])
        self.assertIsNotNone(m["coverage"])

    def test_backtest_cli_runner_no_engine(self):
        result = avm_backtest.run("research/avm_v2_fixture_cases.json", use_engine=False)
        self.assertEqual(result["schema"], "honestly_avm_v2_backtest_v1")
        self.assertIn("baseline", result["metrics"])
        self.assertIn("sentiment_multiplier", result["metrics"])
        self.assertEqual(result["case_count"], 10)

    def test_fixture_builder_from_rows(self):
        fixture = build_avm_fixture.build([{
            "case_id": "x1",
            "address": "1 Test Street, London SE15 6JH",
            "target_price": "500000",
            "low": "450000",
            "central": "500000",
            "high": "550000",
            "confidence_score": "70",
            "time_on_market_days": "20",
        }], with_engine_baseline=False)
        self.assertEqual(fixture["schema"], "honestly_avm_v2_fixture_v1")
        self.assertEqual(len(fixture["cases"]), 1)
        self.assertEqual(fixture["cases"][0]["baseline"]["central"], 500000)


if __name__ == "__main__":
    unittest.main()
