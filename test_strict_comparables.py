import unittest

import engine


class StrictComparableContractTests(unittest.TestCase):
    def test_cronin_rescues_strict_comparables_with_public_epc_area(self):
        r = engine.value("58 Cronin Street, London SE15 6JH", finish="high")
        d = engine.summary(r, "vendor", tier="pro")
        formula = d["valuation_formula"]

        self.assertGreaterEqual(formula["evidence"]["strict_comparable_count"], 5)
        self.assertEqual(formula["evidence"]["evidence_role"], "strict_comparables")
        self.assertEqual(r["valuation"]["basis"], "hmlr_sold_evidence")
        self.assertEqual(d["sqm"], 103)
        self.assertEqual(d["floor_area_source"], "public EPC register")

        strict_rows = [row for row in d["evidence"] if row.get("strict_comparable")]
        self.assertGreaterEqual(len(strict_rows), 5)
        for row in strict_rows[:5]:
            self.assertTrue(row.get("sqm"), row)
            self.assertTrue(row.get("floor_area_source"), row)
            self.assertTrue(row.get("justification"), row)
            self.assertIsNone(row.get("strict_reject_reason"), row)
            self.assertLessEqual(row.get("dist") or 9, 0.5, row)

    def test_formula_contains_hard_comparable_gate_and_rescue_radius(self):
        r = engine.value("58 Cronin Street, London SE15 6JH", finish="high")
        rule = r["valuation"]["formula"]["filter"]["strict_comparable_rule"]
        self.assertIn("<=0.5 miles by default", rule)
        self.assertIn("up to 1 mile only when the 0.5-mile gate returns fewer than 5", rule)
        self.assertIn("minimum 5 comparables", rule)
        self.assertIn("sold within 6 months ideally", rule)
        self.assertIn("extended to 12 months only to reach 5", rule)
        self.assertIn("verified/inferred bedrooms", rule)
        self.assertIn("tenure caveated", rule)
        self.assertIn("otherwise proof/context only", rule)


if __name__ == "__main__":
    unittest.main()
