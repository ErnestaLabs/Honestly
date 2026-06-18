#!/usr/bin/env python3
"""test_uk_quant.py - Unit tests for the Quant UK Valuation Engine.

Every formula step is tested against hand-calculated expected values.
No fuzzy assertions - exact math or bust.
"""
import math
import statistics
import unittest

from uk_quant import (
    UKQuantValuator,
    _weight,
    _coefficient_of_variation,
    weighted_median,
    EPC_CONDITION_MULTIPLIER,
    STEER_CAP_UP,
    STEER_CAP_DOWN,
    RANGE_MIN_VARIANCE,
    RANGE_MAX_VARIANCE,
    CONFIDENCE_FALLBACK_CAP,
)


class TestWeight(unittest.TestCase):
    """Step 1 helper: W = (1 - dist/0.5) × (1 - months/12)"""

    def test_perfect_comp(self):
        """0 miles, 0 months → W = 1.0"""
        self.assertAlmostEqual(_weight(0, 0), 1.0)

    def test_max_distance(self):
        """0.5 miles, 0 months → W = 0"""
        self.assertAlmostEqual(_weight(0.5, 0), 0.0)

    def test_max_recency(self):
        """0 miles, 12 months → W = 0"""
        self.assertAlmostEqual(_weight(0, 12), 0.0)

    def test_midpoint(self):
        """0.25 miles, 6 months → W = 0.5 × 0.5 = 0.25"""
        self.assertAlmostEqual(_weight(0.25, 6), 0.25)

    def test_beyond_bounds_clamps_zero(self):
        """0.8 miles → negative distance factor, clamps to 0"""
        self.assertAlmostEqual(_weight(0.8, 0), 0.0)

    def test_beyond_recency_clamps_zero(self):
        """18 months → negative recency factor, clamps to 0"""
        self.assertAlmostEqual(_weight(0, 18), 0.0)


class TestWeightedMedian(unittest.TestCase):
    """Weighted median must interpolate correctly at the 50th percentile
    of the cumulative weight distribution."""

    def test_simple_even_weights(self):
        """Equal weights → same as regular median.
        [100, 200, 300, 400] with equal weights → midpoint between 200 and 300 = 250."""
        values = [100, 200, 300, 400]
        weights = [1, 1, 1, 1]
        self.assertAlmostEqual(weighted_median(values, weights), 250)  # (200+300)/2

    def test_single_dominant_weight(self):
        """One value has overwhelming weight → returns that value."""
        values = [100, 200, 300]
        weights = [0.01, 0.98, 0.01]
        self.assertAlmostEqual(weighted_median(values, weights), 200)

    def test_weight_pulled_low(self):
        """Two low values with high weight vs one high with low weight."""
        values = [100, 150, 500]
        weights = [0.4, 0.4, 0.2]
        # Cumulative: 100→0.4, 150→0.8 (>0.5), so median = 150
        self.assertAlmostEqual(weighted_median(values, weights), 150)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            weighted_median([], [])

    def test_all_zero_weights_falls_back(self):
        """All weights zero → unweighted median."""
        values = [100, 200, 300]
        weights = [0, 0, 0]
        self.assertAlmostEqual(weighted_median(values, weights), 200)


class TestEPCConditionMultiplier(unittest.TestCase):
    """Step 2: EPC → C must match the formally defined constants."""

    def test_epc_a(self):
        self.assertAlmostEqual(EPC_CONDITION_MULTIPLIER["A"], 1.05)

    def test_epc_b(self):
        self.assertAlmostEqual(EPC_CONDITION_MULTIPLIER["B"], 1.05)

    def test_epc_c(self):
        self.assertAlmostEqual(EPC_CONDITION_MULTIPLIER["C"], 1.00)

    def test_epc_d(self):
        self.assertAlmostEqual(EPC_CONDITION_MULTIPLIER["D"], 0.96)

    def test_epc_e(self):
        self.assertAlmostEqual(EPC_CONDITION_MULTIPLIER["E"], 0.92)

    def test_epc_f(self):
        self.assertAlmostEqual(EPC_CONDITION_MULTIPLIER["F"], 0.92)

    def test_epc_unknown(self):
        self.assertAlmostEqual(EPC_CONDITION_MULTIPLIER[None], 1.00)

    def test_valuator_accessor(self):
        self.assertAlmostEqual(UKQuantValuator.condition_multiplier("C"), 1.00)
        self.assertAlmostEqual(UKQuantValuator.condition_multiplier("A"), 1.05)
        self.assertAlmostEqual(UKQuantValuator.condition_multiplier(None), 1.00)


class TestMarketSteer(unittest.TestCase):
    """Step 3: S = HPI_now / HPI_prev3m - 1, capped [+6%, -5%]."""

    def _make_valuator(self, hpi_current, hpi_prev_3m, **kw):
        defaults = dict(
            subject_address="1 Test St",
            subject_sqm=100,
            subject_epc="C",
            subject_last_sold_price=300000,
            subject_last_sold_date="2020-01-01",
            subject_lat=51.5,
            subject_lng=-0.1,
            strict_comps=[],
        )
        defaults.update(kw)
        return UKQuantValuator(
            hpi_current=hpi_current,
            hpi_prev_3m=hpi_prev_3m,
            **defaults,
        )

    def test_flat_market(self):
        """HPI unchanged → steer = 0."""
        v = self._make_valuator(100, 100)
        self.assertAlmostEqual(v._market_steer(), 0.0)

    def test_upward_market(self):
        """5% rise → steer = 0.05 (within cap)."""
        v = self._make_valuator(105, 100)
        self.assertAlmostEqual(v._market_steer(), 0.05)

    def test_upward_capped(self):
        """10% rise → capped at 0.06."""
        v = self._make_valuator(110, 100)
        self.assertAlmostEqual(v._market_steer(), 0.06)

    def test_downward_market(self):
        """3% fall → steer = -0.03 (within cap)."""
        v = self._make_valuator(97, 100)
        self.assertAlmostEqual(v._market_steer(), -0.03)

    def test_downward_capped(self):
        """8% fall → capped at -0.05."""
        v = self._make_valuator(92, 100)
        self.assertAlmostEqual(v._market_steer(), -0.05)

    def test_no_hpi(self):
        """Missing HPI → None."""
        v = self._make_valuator(None, None)
        self.assertIsNone(v._market_steer())

    def test_zero_prev(self):
        """Zero previous HPI → None (avoid division by zero)."""
        v = self._make_valuator(100, 0)
        self.assertIsNone(v._market_steer())


class TestFallbackValue(unittest.TestCase):
    """Step 4: Last Sold × (HPI_now / HPI_then) × C."""

    def _make_valuator(self, last_sold, hpi_at_last, hpi_now, epc="C", **kw):
        defaults = dict(
            subject_address="1 Test St",
            subject_sqm=100,
            subject_epc=epc,
            subject_last_sold_price=last_sold,
            subject_last_sold_date="2020-01-01",
            subject_lat=51.5,
            subject_lng=-0.1,
            strict_comps=[],
        )
        defaults.update(kw)
        return UKQuantValuator(
            hpi_current=hpi_now,
            hpi_at_last_sold=hpi_at_last,
            **defaults,
        )

    def test_basic_hpi_uplift(self):
        """£300k sold when HPI=100, now HPI=120 → £300k × 1.2 × 1.00 = £360k."""
        v = self._make_valuator(300000, 100, 120)
        self.assertEqual(v._fallback_value(), 360000)

    def test_epc_d_discount(self):
        """EPC D: £300k × 1.2 × 0.96 = £345,600."""
        v = self._make_valuator(300000, 100, 120, epc="D")
        self.assertEqual(v._fallback_value(), 345600)

    def test_no_hpi_falls_to_raw(self):
        """No HPI data → just last_sold × C."""
        v = self._make_valuator(300000, None, None, epc="C")
        self.assertEqual(v._fallback_value(), 300000)


class TestRange(unittest.TestCase):
    """Step 5: Volatility-based range with safety nets."""

    def _make_valuator(self, comps, sqm=100, **kw):
        defaults = dict(
            subject_address="1 Test St",
            subject_sqm=sqm,
            subject_epc="C",
            subject_last_sold_price=300000,
            subject_last_sold_date="2020-01-01",
            subject_lat=51.5,
            subject_lng=-0.1,
            strict_comps=comps,
        )
        defaults.update(kw)
        return UKQuantValuator(**defaults)

    def test_minimum_variance_enforced(self):
        """Even with zero spread comps, range must be ≥ 5% of central."""
        comps = [
            {"price": 500000, "date": "2025-01-01", "sqm": 100, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 500000, "date": "2025-02-01", "sqm": 100, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 500000, "date": "2025-03-01", "sqm": 100, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 500000, "date": "2025-04-01", "sqm": 100, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 500000, "date": "2025-05-01", "sqm": 100, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
        ]
        v = self._make_valuator(comps, sqm=100)
        result = v.value()
        central = result["central"]
        # Range width must be at least 5% of central on each side
        self.assertGreaterEqual(central - result["low"], central * RANGE_MIN_VARIANCE * 0.99)
        self.assertGreaterEqual(result["high"] - central, central * RANGE_MIN_VARIANCE * 0.99)

    def test_maximum_variance_enforced(self):
        """Range must be ≤ 20% of central on each side."""
        comps = [
            {"price": 200000, "date": "2025-01-01", "sqm": 100, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 800000, "date": "2025-02-01", "sqm": 100, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 500000, "date": "2025-03-01", "sqm": 100, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 300000, "date": "2025-04-01", "sqm": 100, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 700000, "date": "2025-05-01", "sqm": 100, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
        ]
        v = self._make_valuator(comps, sqm=100)
        result = v.value()
        central = result["central"]
        self.assertLessEqual(central - result["low"], central * RANGE_MAX_VARIANCE * 1.01)
        self.assertLessEqual(result["high"] - central, central * RANGE_MAX_VARIANCE * 1.01)

    def test_range_brackets_central(self):
        """Low ≤ central ≤ high, always."""
        comps = [
            {"price": 400000, "date": "2025-01-01", "sqm": 80, "dist": 0.2, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 450000, "date": "2025-02-01", "sqm": 85, "dist": 0.3, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 380000, "date": "2025-03-01", "sqm": 75, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 420000, "date": "2025-04-01", "sqm": 82, "dist": 0.15, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 460000, "date": "2025-05-01", "sqm": 90, "dist": 0.25, "ptype": "F", "postcode": "SW16 2RQ"},
        ]
        v = self._make_valuator(comps, sqm=85)
        result = v.value()
        self.assertLessEqual(result["low"], result["central"])
        self.assertLessEqual(result["central"], result["high"])


class TestConfidence(unittest.TestCase):
    """Step 6: Quantitative confidence score."""

    def _make_valuator(self, n_comps, sqm_values=None, distances=None, **kw):
        """Build a valuator with n_comps synthetic strict comps."""
        comps = []
        for i in range(n_comps):
            sqm = (sqm_values or [100] * n_comps)[i] if sqm_values else 100
            dist = (distances or [0.1] * n_comps)[i] if distances else 0.1
            price = sqm * 5000  # £5k/sqm = £500k for 100sqm
            comps.append({
                "price": price,
                "date": "2025-03-01",
                "sqm": sqm,
                "dist": dist,
                "ptype": "F",
                "postcode": "SW16 2RQ",
            })
        defaults = dict(
            subject_address="1 Test St",
            subject_sqm=100,
            subject_epc="C",
            subject_last_sold_price=500000,
            subject_last_sold_date="2020-01-01",
            subject_lat=51.5,
            subject_lng=-0.1,
            strict_comps=comps,
        )
        defaults.update(kw)
        return UKQuantValuator(**defaults)

    def test_five_uniform_comps_high_confidence(self):
        """5 identical comps at 0.1 miles → high score (~100)."""
        v = self._make_valuator(5)
        result = v.value()
        self.assertGreaterEqual(result["confidence_score"], 80)
        self.assertEqual(result["confidence_grade"], "Strong")

    def test_three_comps_lower(self):
        """3 comps → -20 penalty → score ≤ 80."""
        v = self._make_valuator(3)
        result = v.value()
        self.assertLessEqual(result["confidence_score"], 80)

    def test_one_comp_fallback(self):
        """1 comp (<3) → fallback used, confidence capped at 40."""
        v = self._make_valuator(1)
        result = v.value()
        self.assertTrue(result["used_fallback"])
        self.assertLessEqual(result["confidence_score"], CONFIDENCE_FALLBACK_CAP)

    def test_zero_comps_fallback(self):
        """0 comps → fallback, confidence capped at 40."""
        v = self._make_valuator(0)
        result = v.value()
        self.assertTrue(result["used_fallback"])
        self.assertLessEqual(result["confidence_score"], CONFIDENCE_FALLBACK_CAP)

    def test_distant_comp_penalty(self):
        """Nearest comp > 0.3 miles → -5 penalty."""
        v_near = self._make_valuator(5, distances=[0.1] * 5)
        v_far = self._make_valuator(5, distances=[0.5] * 5)
        r_near = v_near.value()
        r_far = v_far.value()
        self.assertGreaterEqual(r_near["confidence_score"], r_far["confidence_score"])

    def test_high_dispersion_lowers_confidence(self):
        """Comps with spread £/sqm → lower confidence than uniform."""
        uniform = self._make_valuator(5, sqm_values=[100, 100, 100, 100, 100])
        spread = self._make_valuator(5, sqm_values=[60, 80, 100, 120, 140])
        r_uniform = uniform.value()
        r_spread = spread.value()
        self.assertGreaterEqual(r_uniform["confidence_score"], r_spread["confidence_score"])

    def test_score_bounded_0_100(self):
        """Score never goes below 0 or above 100."""
        v = self._make_valuator(0)
        result = v.value()
        self.assertGreaterEqual(result["confidence_score"], 0)
        self.assertLessEqual(result["confidence_score"], 100)


class TestFullPipeline(unittest.TestCase):
    """End-to-end: hand-calculate a valuation and verify every output."""

    def test_hand_calculated_valuation(self):
        """5 comps, EPC C, flat market, 100 sqm.

        Comps (all flats, near, recent):
          A: 0.1mi, 2mo, 80sqm, £400,000 → £5,000/sqm
          B: 0.2mi, 4mo, 90sqm, £450,000 → £5,000/sqm
          C: 0.15mi, 1mo, 85sqm, £425,000 → £5,000/sqm
          D: 0.3mi, 6mo, 95sqm, £475,000 → £5,000/sqm
          E: 0.25mi, 3mo, 88sqm, £440,000 → £5,000/sqm

        All at exactly £5,000/sqm → weighted median = £5,000/sqm
        Subject: 100 sqm → Raw Anchor = £500,000
        EPC C → C = 1.00 → Adjusted = £500,000
        Flat market → S = 0 → Assessed = £500,000
        σ = 0 (all same £/sqm) → range at minimum 5% = £475,000 - £525,000
        Confidence: 5 comps → no missing penalty; CV=0 → no dispersion penalty
        → ~100/100
        """
        comps = [
            {"price": 400000, "date": "2025-04-01", "sqm": 80, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 450000, "date": "2025-02-01", "sqm": 90, "dist": 0.2, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 425000, "date": "2025-05-01", "sqm": 85, "dist": 0.15, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 475000, "date": "2024-12-01", "sqm": 95, "dist": 0.3, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 440000, "date": "2025-03-01", "sqm": 88, "dist": 0.25, "ptype": "F", "postcode": "SW16 2RQ"},
        ]
        v = UKQuantValuator(
            subject_address="1 Test Street, London",
            subject_sqm=100,
            subject_epc="C",
            subject_last_sold_price=400000,
            subject_last_sold_date="2020-01-01",
            subject_lat=51.5,
            subject_lng=-0.1,
            strict_comps=comps,
            hpi_current=100,
            hpi_prev_3m=100,
        )
        result = v.value()

        # Central should be exactly £500,000
        self.assertEqual(result["central"], 500000)

        # Range: σ=0 so minimum 5% variance
        self.assertAlmostEqual(result["low"], 475000, delta=1000)
        self.assertAlmostEqual(result["high"], 525000, delta=1000)

        # Confidence should be near 100
        self.assertGreaterEqual(result["confidence_score"], 90)

        # Not using fallback
        self.assertFalse(result["used_fallback"])

        # Derivation must have 5 steps (no fallback step since N >= 3)
        self.assertEqual(len(result["derivation"]["formula_steps"]), 5)

        # Verify fallback version has 6 steps
        comps_few = comps[:2]
        v_fb = UKQuantValuator(
            "1 Test", 100, "C", 400000, "2020-01-01", 51.5, -0.1, comps_few,
            hpi_current=100, hpi_prev_3m=100, hpi_at_last_sold=100,
        )
        r_fb = v_fb.value()
        self.assertTrue(r_fb["used_fallback"])
        self.assertEqual(len(r_fb["derivation"]["formula_steps"]), 6)

    def test_epc_a_uplift(self):
        """Same comps but EPC A → central 5% higher."""
        comps = [
            {"price": 400000, "date": "2025-04-01", "sqm": 80, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 450000, "date": "2025-02-01", "sqm": 90, "dist": 0.2, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 425000, "date": "2025-05-01", "sqm": 85, "dist": 0.15, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 475000, "date": "2024-12-01", "sqm": 95, "dist": 0.3, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 440000, "date": "2025-03-01", "sqm": 88, "dist": 0.25, "ptype": "F", "postcode": "SW16 2RQ"},
        ]
        v_c = UKQuantValuator("1 Test", 100, "C", 400000, "2020-01-01", 51.5, -0.1, comps, 100, 100)
        v_a = UKQuantValuator("1 Test", 100, "A", 400000, "2020-01-01", 51.5, -0.1, comps, 100, 100)
        r_c = v_c.value()
        r_a = v_a.value()
        # EPC A = 1.05, EPC C = 1.00
        self.assertAlmostEqual(r_a["central"], r_c["central"] * 1.05, delta=1000)

    def test_market_steer_applied(self):
        """6% upward steer → central 6% higher than flat."""
        comps = [
            {"price": 400000, "date": "2025-04-01", "sqm": 80, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 450000, "date": "2025-02-01", "sqm": 90, "dist": 0.2, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 425000, "date": "2025-05-01", "sqm": 85, "dist": 0.15, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 475000, "date": "2024-12-01", "sqm": 95, "dist": 0.3, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 440000, "date": "2025-03-01", "sqm": 88, "dist": 0.25, "ptype": "F", "postcode": "SW16 2RQ"},
        ]
        v_flat = UKQuantValuator("1 Test", 100, "C", 400000, "2020-01-01", 51.5, -0.1, comps, 100, 100)
        v_up = UKQuantValuator("1 Test", 100, "C", 400000, "2020-01-01", 51.5, -0.1, comps, 106, 100)
        r_flat = v_flat.value()
        r_up = v_up.value()
        # 6% steer: central should be 6% higher
        expected_uplift = r_flat["central"] * 0.06
        self.assertAlmostEqual(r_up["central"] - r_flat["central"], expected_uplift, delta=1000)

    def test_fallback_caps_confidence(self):
        """2 comps → fallback → confidence ≤ 40."""
        comps = [
            {"price": 400000, "date": "2025-04-01", "sqm": 80, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 450000, "date": "2025-02-01", "sqm": 90, "dist": 0.2, "ptype": "F", "postcode": "SW16 2RQ"},
        ]
        v = UKQuantValuator(
            "1 Test", 100, "C", 400000, "2020-01-01", 51.5, -0.1, comps,
            hpi_current=120, hpi_prev_3m=110, hpi_at_last_sold=100, hpi_now=120,
        )
        result = v.value()
        self.assertTrue(result["used_fallback"])
        self.assertLessEqual(result["confidence_score"], 40)

    def test_output_contract_keys(self):
        """Result dict must have all keys the PDF/API expects."""
        comps = [
            {"price": 400000, "date": "2025-04-01", "sqm": 80, "dist": 0.1, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 450000, "date": "2025-02-01", "sqm": 90, "dist": 0.2, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 425000, "date": "2025-05-01", "sqm": 85, "dist": 0.15, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 475000, "date": "2024-12-01", "sqm": 95, "dist": 0.3, "ptype": "F", "postcode": "SW16 2RQ"},
            {"price": 440000, "date": "2025-03-01", "sqm": 88, "dist": 0.25, "ptype": "F", "postcode": "SW16 2RQ"},
        ]
        v = UKQuantValuator("1 Test", 100, "C", 400000, "2020-01-01", 51.5, -0.1, comps, 100, 100)
        result = v.value()
        required_keys = ["low", "high", "central", "guide", "confidence_score", "confidence_grade",
                         "n_strict_comps", "used_fallback", "derivation"]
        for k in required_keys:
            self.assertIn(k, result, f"Missing key: {k}")
        # Derivation sub-keys
        d = result["derivation"]
        for dk in ["epc_multiplier", "epc_rating", "market_steer", "formula_version", "formula_steps"]:
            self.assertIn(dk, d, f"Missing derivation key: {dk}")


class TestCoefficientOfVariation(unittest.TestCase):
    def test_zero_for_single(self):
        self.assertAlmostEqual(_coefficient_of_variation([100]), 0.0)

    def test_zero_for_empty(self):
        self.assertAlmostEqual(_coefficient_of_variation([]), 0.0)

    def test_uniform(self):
        self.assertAlmostEqual(_coefficient_of_variation([100, 100, 100]), 0.0)

    def test_known_values(self):
        # σ of [80, 100, 120] = 20, μ = 100, CV = 0.2
        values = [80, 100, 120]
        cv = _coefficient_of_variation(values)
        self.assertAlmostEqual(cv, 0.2, places=2)


if __name__ == "__main__":
    unittest.main()
