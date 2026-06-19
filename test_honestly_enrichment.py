#!/usr/bin/env python3
import unittest
import engine


class TestHonestlyEnrichment(unittest.TestCase):
    def test_public_enrichment_fields_render_without_vendor_feeds(self):
        r = engine.value("58 Cronin Street, London SE15 6JH", finish="high")
        d = engine.summary(r, "buyer", asking=610000, tier="pro")
        en = d["honestly_enrichment"]
        self.assertEqual(en["source"], "Honestly public-data enrichment")
        self.assertFalse(en["commercial_data"])
        self.assertEqual(en["proof"]["source"], "HM Land Registry Price Paid Data")
        self.assertTrue(en["proof"]["subject_sale_excluded_from_comps"])
        self.assertGreaterEqual(en["proof"]["rows_shown"], 1)
        self.assertIn("floor_area", en["material"])
        self.assertIn("epc", en["material"])
        self.assertIn("downvaluation_exposure", {x["key"] for x in en["decision_signals"]})
        self.assertIn("pre_survey_questions", {x["key"] for x in en["decision_signals"]})
        self.assertTrue(en["monitoring_triggers"])
        self.assertEqual(en["formula"]["name"], "Honestly Transparent AVM v1")
        self.assertIn("plain_formula", en["formula"])
        self.assertIn("google_context", en)
        self.assertIn("address_validation", en["google_context"])
        self.assertIn("solar", en["google_context"])
        self.assertIn("free_api_context", en)
        self.assertIn("postcodes_io", en["free_api_context"])
        blob = str(en)
        for banned in ("Street Data", "StreetData", "Chimnie", "PaTMa", "PropertyData"):
            self.assertNotIn(banned, blob)

    def test_vendor_quote_gap_signal(self):
        r = engine.value("58 Cronin Street, London SE15 6JH", finish="high")
        d = engine.summary(r, "vendor", quoted=650000, tier="pro")
        signals = {x["key"]: x for x in d["honestly_enrichment"]["decision_signals"]}
        self.assertIn("agent_quote_gap", signals)
        self.assertEqual(signals["agent_quote_gap"]["status"], "high")

    def test_summary_exposes_definite_formula(self):
        r = engine.value("58 Cronin Street, London SE15 6JH", finish="high")
        d = engine.summary(r, "vendor", tier="lite")
        vf = d["valuation_formula"]
        self.assertEqual(vf["name"], "Honestly Transparent AVM v1")
        self.assertEqual(vf["filter"]["comparable_ideal_months"], 6)
        self.assertEqual(vf["filter"]["comparable_rescue_cap_months"], 12)
        self.assertEqual(vf["filter"]["proof_context_hard_cap_months"], 24)
        self.assertTrue(vf["filter"]["subject_sale_excluded"])
        self.assertIn("commercial same-data aggregators", vf["non_sources"])
        self.assertEqual(vf["result"]["central"], d["central"])
        self.assertIn("HMLR", vf["plain_formula"])


if __name__ == "__main__":
    unittest.main()
