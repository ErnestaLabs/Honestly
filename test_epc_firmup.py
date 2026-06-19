#!/usr/bin/env python3
"""Offline tests for appraise.epc_firm_up - the DLUHC register floor-area/EPC firm-up that
runs for BOTH tiers inside find_subject (PRODUCT_SPEC section 7 item 7).

The honesty contract under test:
  * FILL-ONLY - a missing sqm/EPC is filled from the official register; a value the primary
    source already carries is NEVER overwritten, so the figure cannot drift;
  * where both sources carry a value and they differ materially, the divergence is recorded
    beside the figure (not silently reconciled);
  * dormant with no credential, honest on an unmatched address, and never raises.
"""
import unittest
import appraise


class _FakeEpc:
    """A stand-in epc client; tests inject the exact register response they want to assert."""
    def __init__(self, present=True, result=None):
        self._present = present
        self._result = result or {}

    def credentials_present(self):
        return self._present

    def for_address(self, address, postcode):
        return self._result


_MATCH = {"ok": True, "matched": True, "rating": "C", "score": 72,
          "floor_area_sqm": 79, "source": "EPC register (DLUHC/MHCLG, OGL v3.0)"}


def _subj(**over):
    s = {"address": "58 Cronin Street, London SE15 6JH", "sqm": None, "sqft": None,
         "epc": None}
    s.update(over)
    return s


class TestFillOnly(unittest.TestCase):
    def test_fills_missing_sqm_and_epc(self):
        s = appraise.epc_firm_up(_subj(), "", _epc=_FakeEpc(result=_MATCH))
        self.assertEqual(s["sqm"], 79)
        self.assertEqual(s["sqft"], round(79 * 10.7639))
        self.assertEqual(s["epc"], 72)
        reg = s["epc_register"]
        self.assertTrue(reg["matched"])
        self.assertIn("sqm", reg["filled"])
        self.assertIn("epc", reg["filled"])
        self.assertEqual(reg["divergence"], {})

    def test_keeps_present_sqm_and_records_divergence(self):
        # subject already has 65 sqm from PropertyData; register says 79 (>10% apart)
        s = appraise.epc_firm_up(_subj(sqm=65, sqft=700, epc=80), "",
                                 _epc=_FakeEpc(result=_MATCH))
        self.assertEqual(s["sqm"], 65)            # NOT overwritten - figure never drifts
        self.assertEqual(s["sqft"], 700)
        self.assertEqual(s["epc"], 80)
        reg = s["epc_register"]
        self.assertEqual(reg["filled"], [])
        self.assertEqual(reg["divergence"]["sqm"], {"register": 79, "subject": 65})
        self.assertEqual(reg["divergence"]["epc"], {"register": 72, "subject": 80})

    def test_present_and_close_sqm_no_divergence(self):
        # 76 vs 79 is within 10% - corroborated, no divergence flagged
        s = appraise.epc_firm_up(_subj(sqm=76, sqft=818, epc=72), "",
                                 _epc=_FakeEpc(result=_MATCH))
        self.assertEqual(s["sqm"], 76)
        self.assertNotIn("sqm", s["epc_register"]["divergence"])
        self.assertNotIn("epc", s["epc_register"]["divergence"])  # 72 == 72


class TestDegrades(unittest.TestCase):
    def test_no_credentials_is_a_noop(self):
        s = appraise.epc_firm_up(_subj(), "", _epc=_FakeEpc(present=False))
        self.assertIsNone(s["sqm"])
        self.assertNotIn("epc_register", s)

    def test_unmatched_records_honest_state_no_fill(self):
        unm = {"ok": True, "matched": False, "reason": "no confident address match",
               "source": "EPC register"}
        s = appraise.epc_firm_up(_subj(), "", _epc=_FakeEpc(result=unm))
        self.assertIsNone(s["sqm"])
        self.assertFalse(s["epc_register"]["matched"])

    def test_not_ok_is_a_noop(self):
        s = appraise.epc_firm_up(_subj(), "", _epc=_FakeEpc(result={"ok": False,
                                 "reason": "EPC auth rejected"}))
        self.assertIsNone(s["sqm"])
        self.assertNotIn("epc_register", s)

    def test_never_raises_on_client_explosion(self):
        class Boom:
            def credentials_present(self): return True
            def for_address(self, *a): raise RuntimeError("register down")
        s = appraise.epc_firm_up(_subj(), "", _epc=Boom())
        self.assertIsNone(s["sqm"])          # untouched, no exception


if __name__ == "__main__":
    unittest.main(verbosity=2)
