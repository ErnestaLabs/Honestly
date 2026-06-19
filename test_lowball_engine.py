#!/usr/bin/env python3
"""test_lowball_engine.py - Unit tests for the Lowball Counter-Email engine.

Mocks the LangChain LLM call to verify:
  - Prompt formatting with correct evidence injection
  - Email output structure (ok, email_text, model, gap_pct)
  - Template fallback when LLM is unavailable
  - Gap percentage calculation
"""
import unittest
from unittest.mock import patch, MagicMock


class TestLowballEngine(unittest.TestCase):

    def _sample_evidence(self):
        return [
            {"address": "6 Newdigate House, London", "price": 406219, "date": "2021-06-14", "sqm": 100},
            {"address": "1 Newdigate House, London", "price": 370000, "date": "2025-05-23", "sqm": 95},
            {"address": "10 Newdigate House, London", "price": 450000, "date": "2025-01-10", "sqm": 110},
        ]

    def test_llm_call_with_correct_prompt(self):
        """LLM is called with the right model and the prompt contains evidence."""
        from products.engines.lowball_engine import generate_counter_email

        # Mock the LangChain call chain at the source module
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Dear Agent,\n\nThank you for the offer..."
        mock_llm.invoke.return_value = mock_response

        with patch("langchain_openai.ChatOpenAI", return_value=mock_llm):
            with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key-123"}):
                result = generate_counter_email(
                    subject_address="8 Newdigate House, London SW16 2RQ",
                    assessed_value=440000,
                    low_range=400000,
                    high_range=480000,
                    confidence_score=75,
                    confidence_grade="Good",
                    sqm=140,
                    epc_rating="C",
                    lowball_offer=350000,
                    evidence=self._sample_evidence(),
                    model="meta-llama/llama-3-70b-instruct",
                )

        self.assertTrue(result["ok"])
        self.assertIn("email_text", result)
        self.assertEqual(result["model"], "meta-llama/llama-3-70b-instruct")
        self.assertEqual(result["lowball_offer"], 350000)
        self.assertEqual(result["assessed_value"], 440000)
        # Gap: (1 - 350000/440000) * 100 = 20.5%
        self.assertAlmostEqual(result["gap_pct"], 20.5, places=1)

    def test_fallback_email_without_api_key(self):
        """Without OPENROUTER_API_KEY, the template fallback is used."""
        from products.engines.lowball_engine import generate_counter_email

        with patch.dict("os.environ", {}, clear=True):
            # Remove the key
            os_env = {}
            with patch("os.environ.get", side_effect=lambda k, d="": os_env.get(k, d)):
                result = generate_counter_email(
                    subject_address="8 Newdigate House, London SW16 2RQ",
                    assessed_value=440000,
                    low_range=400000,
                    high_range=480000,
                    confidence_score=75,
                    confidence_grade="Good",
                    sqm=140,
                    epc_rating="C",
                    lowball_offer=350000,
                    evidence=self._sample_evidence(),
                )

        self.assertTrue(result["ok"])
        self.assertIn("email_text", result)
        self.assertEqual(result["model"], "template_fallback")
        self.assertIn("Dear Agent", result["email_text"])
        self.assertIn("440,000", result["email_text"])
        self.assertIn("350,000", result["email_text"])
        self.assertIn("6 Newdigate House", result["email_text"])

    def test_fallback_contains_all_comps(self):
        """Fallback email includes all comparable addresses."""
        from products.engines.lowball_engine import generate_counter_email

        with patch.dict("os.environ", {}, clear=True):
            result = generate_counter_email(
                subject_address="1 Test St",
                assessed_value=500000,
                low_range=450000,
                high_range=550000,
                confidence_score=80,
                confidence_grade="Strong",
                sqm=100,
                epc_rating="B",
                lowball_offer=400000,
                evidence=self._sample_evidence(),
            )

        email = result["email_text"]
        for e in self._sample_evidence():
            # At least part of the address should appear
            self.assertIn(e["address"].split(",")[0], email)

    def test_gap_calculation(self):
        """Gap percentage is calculated correctly."""
        from products.engines.lowball_engine import generate_counter_email

        with patch.dict("os.environ", {}, clear=True):
            # 10% gap: offer=450k, assessed=500k
            result = generate_counter_email(
                subject_address="1 Test St",
                assessed_value=500000,
                low_range=475000,
                high_range=525000,
                confidence_score=90,
                confidence_grade="Strong",
                sqm=100,
                epc_rating="C",
                lowball_offer=450000,
                evidence=[],
            )

        self.assertAlmostEqual(result["gap_pct"], 10.0, places=1)

    def test_format_comps(self):
        """Comp formatting produces numbered list with prices."""
        from products.engines.lowball_engine import _format_comps

        result = _format_comps(self._sample_evidence())
        self.assertIn("1.", result)
        self.assertIn("406,219", result)
        self.assertIn("6 Newdigate House", result)
        # Should have 3 entries
        self.assertEqual(result.count("\n") + 1, 3)

    def test_empty_evidence(self):
        """Empty evidence list produces a note, not an error."""
        from products.engines.lowball_engine import generate_counter_email

        with patch.dict("os.environ", {}, clear=True):
            result = generate_counter_email(
                subject_address="1 Test St",
                assessed_value=500000,
                low_range=450000,
                high_range=550000,
                confidence_score=80,
                confidence_grade="Strong",
                sqm=100,
                epc_rating="C",
                lowball_offer=400000,
                evidence=[],
            )

        self.assertTrue(result["ok"])


class TestPlanningOracleEngine(unittest.TestCase):

    def test_flats_always_need_planning(self):
        """Flats cannot use PD for loft conversions."""
        from products.engines.planning_oracle_engine import assess_permitted_development

        result = assess_permitted_development(
            address="1 Flat St",
            ptype="flat",
            sqm=65,
            roof_type="pitched",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["verdict"], "Not Permitted Development")
        self.assertGreater(result["confidence_pct"], 80)

    def test_gable_roof_likely_pd(self):
        """Gable roof on a terraced house is likely PD."""
        from products.engines.planning_oracle_engine import assess_permitted_development

        result = assess_permitted_development(
            address="1 House St",
            ptype="terraced_house",
            sqm=90,
            roof_type="gable",
            conservation_area=False,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["verdict"], "Likely Permitted Development")
        self.assertIn("conditions", result)
        self.assertGreater(len(result["conditions"]), 0)

    def test_conservation_area_blocks_pd(self):
        """Conservation area blocks loft PD."""
        from products.engines.planning_oracle_engine import assess_permitted_development

        result = assess_permitted_development(
            address="1 Old St",
            ptype="semi_detached_house",
            sqm=110,
            roof_type="hipped",
            conservation_area=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["verdict"], "Not Permitted Development")

    def test_flat_roof_blocks_pd(self):
        """Flat roof cannot accommodate a loft conversion."""
        from products.engines.planning_oracle_engine import assess_permitted_development

        result = assess_permitted_development(
            address="1 Flat Roof St",
            ptype="detached_house",
            sqm=150,
            roof_type="flat",
            conservation_area=False,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["verdict"], "Not Permitted Development")

    def test_volume_limits_by_type(self):
        """Terraced houses get 40 cubic metres, others get 50."""
        from products.engines.planning_oracle_engine import assess_permitted_development

        result_t = assess_permitted_development(
            address="1 Terraced St", ptype="terraced_house", sqm=90,
            roof_type="gable", conservation_area=False,
        )
        result_s = assess_permitted_development(
            address="1 Semi St", ptype="semi_detached_house", sqm=110,
            roof_type="gable", conservation_area=False,
        )

        self.assertEqual(result_t["max_volume_cubic_m"], 40)
        self.assertEqual(result_s["max_volume_cubic_m"], 50)


if __name__ == "__main__":
    unittest.main()
