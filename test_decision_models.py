#!/usr/bin/env python3
import unittest
import decision_models as dm


class TestDecisionModels(unittest.TestCase):
    def test_affordability_returns_pressure(self):
        r = dm.affordability(380000, deposit=60000, income=85000)
        self.assertEqual(r["loan"], 320000)
        self.assertAlmostEqual(r["ltv_pct"], 84.2, places=1)
        self.assertGreater(r["monthly_payment"], 0)
        self.assertIn(r["pressure"], ("Low", "Medium", "High"))

    def test_downvaluation_exposure(self):
        r = dm.downvaluation_exposure(380000, 310000, 365000, 340000, deposit=60000)
        self.assertEqual(r["grade"], "Medium")
        self.assertEqual(r["cash_gap"], 40000)

    def test_pre_survey_risk_is_not_empty(self):
        r = dm.pre_survey_risk({"confidence": {"grade": "Fair"}, "epc": None, "sqm": None}, {"finish": "needs_modernising"})
        self.assertIn(r["grade"], ("Low", "Medium", "High"))
        self.assertTrue(r["asks"])


if __name__ == "__main__":
    unittest.main()
