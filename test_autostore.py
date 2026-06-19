#!/usr/bin/env python3
"""Offline tests for engine._autostore - 'everytime we run a valuation store value and update'.

These prove the persistence hook the user asked for, with NO valuation and NO network: we
call engine._autostore directly with a synthetic result dict, monkeypatch engine.summary to
a known payload, and point store at a throwaway SQLite file. The four things under test:
  1. Gated OFF by default  - with HONESTLY_AUTOSTORE unset, nothing is written (so the
     offline test suite and any import-time caller never touch the DB).
  2. Gated ON               - with the flag set, the full summary + headline figures persist.
  3. Deterministic token    - re-running the same address+tier UPDATES the row in place
     (INSERT OR REPLACE on a stable token), never piling up duplicate rows.
  4. Never raises           - a result with no subject/address is a clean no-op."""
import os, hashlib, tempfile, unittest
import engine
import store


def _expected_token(addr, tier):
    return "v_" + hashlib.sha1(f"{addr}|{tier}".encode("utf-8")).hexdigest()[:22]


class AutostoreBase(unittest.TestCase):
    ADDR = "58 Cronin Street, London, SE15 6JH"

    def setUp(self):
        # Throwaway DB per test - the same swap pattern store._selftest uses.
        fd, self._dbpath = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(self._dbpath)
        self._old_db, self._old_inited = store.DB_PATH, store._INITED
        store.DB_PATH, store._INITED = self._dbpath, False

        # Stub engine.summary so the hook has a known, stable payload without a real valuation.
        self._old_summary = engine.summary
        engine.summary = lambda result, audience=None, tier=None: {
            "address": self.ADDR, "audience": audience, "tier": tier,
            "low": 498000, "high": 552000, "central": 525000, "guide": 499000,
            "investment": False}

        self._old_flag = os.environ.get("HONESTLY_AUTOSTORE")
        os.environ.pop("HONESTLY_AUTOSTORE", None)

    def tearDown(self):
        engine.summary = self._old_summary
        store.DB_PATH, store._INITED = self._old_db, self._old_inited
        if self._old_flag is None:
            os.environ.pop("HONESTLY_AUTOSTORE", None)
        else:
            os.environ["HONESTLY_AUTOSTORE"] = self._old_flag
        try:
            os.remove(self._dbpath)
        except OSError:
            pass

    def _result(self, addr=None):
        return {"subject": {"address": addr if addr is not None else self.ADDR,
                            "investment": False}, "finish": "average"}


class TestAutostoreGating(AutostoreBase):
    def test_flag_off_writes_nothing(self):
        # HONESTLY_AUTOSTORE unset (popped in setUp) -> the hook returns before any DB touch.
        engine._autostore(self._result(), "pro")
        self.assertIsNone(store.get_appraisal(_expected_token(self.ADDR, "pro")))

    def test_flag_on_persists_summary_and_figures(self):
        os.environ["HONESTLY_AUTOSTORE"] = "1"
        engine._autostore(self._result(), "pro")
        row = store.get_appraisal(_expected_token(self.ADDR, "pro"))
        self.assertIsNotNone(row)
        self.assertEqual(row["central"], 525000)
        self.assertEqual(row["guide"], 499000)
        self.assertEqual(row["tier"], "pro")
        self.assertEqual(row["address"], self.ADDR)
        self.assertEqual(row["summary"]["central"], 525000)   # full payload stored as JSON


class TestAutostoreDeterministicToken(AutostoreBase):
    def test_rerun_same_address_tier_updates_in_place(self):
        os.environ["HONESTLY_AUTOSTORE"] = "1"
        tok = _expected_token(self.ADDR, "pro")
        engine._autostore(self._result(), "pro")
        # second run with a moved figure - same address+tier -> same token -> one row, updated
        engine.summary = lambda result, audience=None, tier=None: {
            "address": self.ADDR, "audience": audience, "tier": tier,
            "low": 500000, "high": 560000, "central": 530000, "guide": 505000,
            "investment": False}
        engine._autostore(self._result(), "pro")
        row = store.get_appraisal(tok)
        self.assertEqual(row["central"], 530000)              # updated, not the first value
        with store._conn() as c:
            n = c.execute("SELECT COUNT(*) AS n FROM appraisals WHERE token=?",
                          (tok,)).fetchone()["n"]
        self.assertEqual(n, 1)                                # exactly one row, no duplicate

    def test_different_tier_is_a_distinct_row(self):
        os.environ["HONESTLY_AUTOSTORE"] = "1"
        engine._autostore(self._result(), "pro")
        engine._autostore(self._result(), "lite")
        self.assertIsNotNone(store.get_appraisal(_expected_token(self.ADDR, "pro")))
        self.assertIsNotNone(store.get_appraisal(_expected_token(self.ADDR, "lite")))


class TestAutostoreSafety(AutostoreBase):
    def test_no_subject_is_clean_noop(self):
        os.environ["HONESTLY_AUTOSTORE"] = "1"
        engine._autostore({"subject": None}, "pro")          # must not raise
        engine._autostore({}, "pro")

    def test_no_address_is_clean_noop(self):
        os.environ["HONESTLY_AUTOSTORE"] = "1"
        engine._autostore(self._result(addr=None) if False else
                          {"subject": {"investment": False}}, "pro")
        self.assertIsNone(store.get_appraisal(_expected_token(self.ADDR, "pro")))


if __name__ == "__main__":
    unittest.main()
