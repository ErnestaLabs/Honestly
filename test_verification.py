#!/usr/bin/env python3
import unittest
import verification as V


def _summary(**over):
    d = {
        "tier": "pro",
        "evidence": [{"full_address": "1 Cronin Street", "price_str": "£530,000", "date": "2025-01", "verify": "https://landregistry.data.gov.uk/"}],
        "lite_basis": {"source": "HM Land Registry Price Paid Data + EPC credentials not set",
                       "type_basis": "flats", "window_months": 12, "n_evidence": 8,
                       "note": "Built from HMLR proof rows."},
        "epc_register": {"matched": True, "source": "EPC register", "floor_area_sqm": 103},
        "epc": "C",
        "sqm": 103,
        "crosscheck": {"source": "HM Land Registry Price Paid Data (SPARQL, OGL)",
                       "postcode": "SE15 6JH", "official_count": 4,
                       "official_median_str": "£540,000",
                       "note": "Exact-postcode register check."},
        "confidence": {"grade": "Good", "score": 70, "note": "evidence depth good"},
    }
    d.update(over)
    return d


class TestPublicVerification(unittest.TestCase):
    def test_builds_direct_public_rows(self):
        r = V.build(_summary())
        self.assertTrue(r["ok"])
        facts = [x["fact"] for x in r["rows"]]
        self.assertIn("Sold evidence", facts)
        self.assertIn("Valuation basis", facts)
        self.assertIn("EPC / floor area", facts)
        self.assertIn("Exact-postcode register cross-check", facts)
        joined = str(r)
        self.assertIn("HM Land Registry", joined)
        self.assertIn("EPC register", joined)
        self.assertNotIn("Street Data", joined)
        self.assertNotIn("Chimnie", joined)
        self.assertNotIn("PaTMa", joined)

    def test_epc_gap_becomes_decision_check_not_banned_missing_copy(self):
        r = V.build(_summary(epc=None, epc_register=None, sqm=None))
        epc = next(x for x in r["rows"] if x["fact"] == "EPC / floor area")
        self.assertEqual(epc["status"], "Included")
        self.assertIn("decision-check", str(epc))
        self.assertNotIn("missing", str(epc).lower())

    def test_lines_empty_on_junk(self):
        self.assertFalse(V.build(None)["ok"])
        self.assertEqual(V.lines(None), [])

    def test_lines_render(self):
        out = V.lines(_summary())
        self.assertTrue(out)
        self.assertTrue(any("Sold evidence" in x for x in out))


if __name__ == "__main__":
    unittest.main()
