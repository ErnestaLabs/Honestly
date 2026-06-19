#!/usr/bin/env python3
"""Offline tests for macro_live.py - no network, no real cache file touched.

Honesty point: live macro momentum is a bounded z-score that sits BESIDE the figure
and never moves it. signal() is offline-safe (serves cache instantly, refreshes only
when stale, falls back to stale/None on failure) and never raises into a valuation.
"""
import unittest
from unittest import mock
import macro_live as ml


def _series(values, start_year=2023, start_month=1):
    """Build [(YYYY-MM, value), ...] from a flat list of monthly values."""
    out, y, m = [], start_year, start_month
    for v in values:
        out.append((f"{y:04d}-{m:02d}", float(v)))
        m += 1
        if m > 12:
            m = 1; y += 1
    return out


class TestMaths(unittest.TestCase):
    def test_z_needs_history(self):
        self.assertIsNone(ml._z(_series([1, 2, 3])))      # < 12 readings

    def test_z_zero_when_flat(self):
        z = ml._z(_series([5.0] * 24))
        self.assertEqual(z[0], 0.0)                       # sd == 0 -> z 0
        self.assertEqual(z[1], 5.0)

    def test_z_positive_when_latest_above_mean(self):
        vals = [1.0] * 23 + [10.0]                        # last reading well above the run
        z = ml._z(_series(vals), smooth=1)
        self.assertGreater(z[0], 0)

    def test_align_real_subtracts_cpi_on_shared_months(self):
        awe = _series([5.0, 6.0, 7.0])
        cpi = _series([2.0, 2.0, 2.0])
        real = ml._align_real(awe, cpi)
        self.assertEqual([v for _, v in real], [3.0, 4.0, 5.0])

    def test_dir_words(self):
        self.assertEqual(ml._dir(5.0, 4.0), "above")
        self.assertEqual(ml._dir(3.0, 4.0), "below")
        self.assertEqual(ml._dir(4.0, 4.0), "in line with")


class TestCompute(unittest.TestCase):
    def test_compute_builds_bounded_payload(self):
        mort = _series([4.0] * 20 + [6.0] * 4)
        cpi = _series([3.0] * 24)
        awe = _series([5.0] * 24)
        unemp = _series([4.0] * 24)
        with mock.patch.object(ml, "_boe_mortgage", return_value=mort), \
             mock.patch.object(ml, "_ons", side_effect=lambda c, d, t: {
                 "d7g7": cpi, "kac3": awe, "mgsx": unemp}[c]):
            p = ml._compute()
        self.assertIn("score", p)
        self.assertLessEqual(abs(p["score"]), 2.0)        # bounded -2..+2
        self.assertIn(p["lean"], ("supportive", "soft", "balanced"))
        self.assertEqual(len(p["drivers"]), 3)
        self.assertTrue(any("beside the figure" in ln for ln in p["lines"]))

    def test_compute_raises_on_thin_history(self):
        thin = _series([4.0, 4.1, 4.2])                   # < 12 -> _z None -> ValueError
        with mock.patch.object(ml, "_boe_mortgage", return_value=thin), \
             mock.patch.object(ml, "_ons", return_value=thin):
            with self.assertRaises(ValueError):
                ml._compute()


class TestSignalCache(unittest.TestCase):
    def test_fresh_cache_served_without_network(self):
        cache = {"saved": ml.time.time(), "payload": {"score": 0.3, "lean": "balanced"}}
        with mock.patch.object(ml, "_read_cache", return_value=cache), \
             mock.patch.object(ml, "refresh", side_effect=AssertionError("must not refresh")):
            out = ml.signal()
        self.assertEqual(out["lean"], "balanced")

    def test_stale_cache_triggers_refresh(self):
        stale = {"saved": ml.time.time() - 10 * 3600 * 24, "payload": {"score": 0.0}}
        fresh = {"score": 1.0, "lean": "supportive"}
        with mock.patch.object(ml, "_read_cache", return_value=stale), \
             mock.patch.object(ml, "refresh", return_value=fresh):
            out = ml.signal()
        self.assertEqual(out, fresh)

    def test_falls_back_to_stale_when_refresh_fails(self):
        stale = {"saved": ml.time.time() - 10 * 3600 * 24, "payload": {"score": 0.5}}
        with mock.patch.object(ml, "_read_cache", return_value=stale), \
             mock.patch.object(ml, "refresh", return_value=None):
            out = ml.signal()
        self.assertEqual(out["score"], 0.5)               # keeps stale rather than nothing

    def test_no_cache_and_failed_refresh_returns_none(self):
        with mock.patch.object(ml, "_read_cache", return_value=None), \
             mock.patch.object(ml, "refresh", return_value=None):
            self.assertIsNone(ml.signal())

    def test_refresh_swallows_network_error(self):
        with mock.patch.object(ml, "_compute", side_effect=ml.urllib.error.URLError("down")):
            self.assertIsNone(ml.refresh())


if __name__ == "__main__":
    unittest.main(verbosity=2)
