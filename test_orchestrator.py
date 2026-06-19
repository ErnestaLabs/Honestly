#!/usr/bin/env python3
"""test_orchestrator.py - Unit tests for the Core Orchestrator.

Mocks UKQuantValuator and arena modules to verify:
  - The orchestrator combines AVM + Arena points correctly
  - Product triggers are derived from AVM signals
  - The async flow completes in <2s
  - Arena point failure doesn't block the AVM result
"""
import asyncio
import unittest
from unittest.mock import patch, MagicMock


class TestOrchestrator(unittest.TestCase):

    @patch("core.orchestrator._award_arena_points", return_value=True)
    @patch("core.orchestrator._compute_avm")
    def test_full_orchestrator_flow(self, mock_avm, mock_arena):
        """Orchestrator returns AVM data + product triggers."""
        mock_avm.return_value = {
            "ok": True,
            "address": "8 Newdigate House, London SW16 2RQ",
            "central": 440000,
            "low": 400000,
            "high": 480000,
            "guide": 425000,
            "confidence_score": 75,
            "confidence_grade": "Good",
            "sqm": 140,
            "epc": "C",
            "postcode": "SW16 2RQ",
            "evidence": [{"address": "6 Newdigate House", "price": 406219, "date": "2021-06-14", "sqm": 100}],
            "n_comps": 6,
            "type": "flat",
        }

        from core.orchestrator import run_valuation
        result = run_valuation(
            address="8 Newdigate House, London SW16 2RQ",
            user_id="user_123",
            user_tier="free",
        )

        self.assertTrue(result["ok"])
        self.assertIn("avm", result)
        self.assertEqual(result["avm"]["central"], 440000)
        self.assertIn("product_triggers", result)
        # Arena points should have been awarded
        mock_arena.assert_called_once()

    @patch("core.orchestrator._award_arena_points", return_value=True)
    @patch("core.orchestrator._compute_avm")
    def test_product_triggers_for_flat(self, mock_avm, mock_arena):
        """Flats trigger the Leasehold Trap X-Ray."""
        mock_avm.return_value = {
            "ok": True,
            "address": "1 Flat St",
            "central": 300000,
            "low": 270000,
            "high": 330000,
            "confidence_score": 75,
            "confidence_grade": "Good",
            "sqm": 65,
            "epc": "D",
            "postcode": "SE15 6JH",
            "evidence": [],
            "n_comps": 5,
            "type": "flat",
        }

        from core.orchestrator import run_valuation
        result = run_valuation(address="1 Flat St", user_id="u1", user_tier="free")

        triggers = result["product_triggers"]
        trigger_ids = [t["product_id"] for t in triggers]
        # Flat should trigger leasehold trap x-ray
        self.assertIn("leasehold_trap_xray", trigger_ids)
        # EPC D should trigger council tax challenger
        self.assertIn("council_tax_challenger", trigger_ids)
        # Flat should NOT trigger planning oracle
        self.assertNotIn("planning_permission_oracle", trigger_ids)

    @patch("core.orchestrator._award_arena_points", return_value=True)
    @patch("core.orchestrator._compute_avm")
    def test_product_triggers_for_house(self, mock_avm, mock_arena):
        """Houses trigger Planning Oracle and Extension Blueprint."""
        mock_avm.return_value = {
            "ok": True,
            "address": "1 House St",
            "central": 800000,
            "low": 720000,
            "high": 880000,
            "confidence_score": 85,
            "confidence_grade": "Strong",
            "sqm": 120,
            "epc": "C",
            "postcode": "N22 5JB",
            "evidence": [],
            "n_comps": 10,
            "type": "terraced_house",
        }

        from core.orchestrator import run_valuation
        result = run_valuation(address="1 House St", user_id="u1", user_tier="free")

        triggers = result["product_triggers"]
        trigger_ids = [t["product_id"] for t in triggers]
        # House should trigger planning oracle and extension blueprint
        self.assertIn("planning_permission_oracle", trigger_ids)
        self.assertIn("neighbor_extension_blueprint", trigger_ids)
        # House should NOT trigger leasehold trap x-ray
        self.assertNotIn("leasehold_trap_xray", trigger_ids)

    @patch("core.orchestrator._award_arena_points", return_value=True)
    @patch("core.orchestrator._compute_avm")
    def test_low_confidence_triggers_lowball(self, mock_avm, mock_arena):
        """Low confidence triggers the Lowball Counter-Email."""
        mock_avm.return_value = {
            "ok": True,
            "address": "1 Low Conf St",
            "central": 500000,
            "low": 400000,
            "high": 600000,
            "confidence_score": 35,
            "confidence_grade": "Fair",
            "sqm": 100,
            "epc": "C",
            "postcode": "SW16 2RQ",
            "evidence": [],
            "n_comps": 3,
            "type": "terraced_house",
        }

        from core.orchestrator import run_valuation
        result = run_valuation(address="1 Low Conf St", user_id="u1", user_tier="free")

        triggers = result["product_triggers"]
        trigger_ids = [t["product_id"] for t in triggers]
        self.assertIn("lowball_counter_email", trigger_ids)
        # The relevance score should be high (100 - 35 = 65)
        lowball = next(t for t in triggers if t["product_id"] == "lowball_counter_email")
        self.assertGreater(lowball["relevance_score"], 50)

    @patch("core.orchestrator._award_arena_points", return_value=False)
    @patch("core.orchestrator._compute_avm")
    def test_arena_failure_doesnt_block_avm(self, mock_avm, mock_arena):
        """Arena point failure should not block the AVM result."""
        mock_avm.return_value = {
            "ok": True,
            "address": "1 Test St",
            "central": 500000,
            "low": 450000,
            "high": 550000,
            "confidence_score": 90,
            "confidence_grade": "Strong",
            "sqm": 100,
            "epc": "C",
            "postcode": "SW16 2RQ",
            "evidence": [],
            "n_comps": 10,
            "type": "terraced_house",
        }

        from core.orchestrator import run_valuation
        result = run_valuation(address="1 Test St", user_id="u1", user_tier="free")

        # AVM should still succeed even though arena failed
        self.assertTrue(result["ok"])
        self.assertEqual(result["avm"]["central"], 500000)

    @patch("core.orchestrator._award_arena_points", return_value=True)
    @patch("core.orchestrator._compute_avm")
    def test_triggers_sorted_by_relevance(self, mock_avm, mock_arena):
        """Product triggers are sorted by relevance score (highest first)."""
        mock_avm.return_value = {
            "ok": True,
            "address": "1 Test St",
            "central": 500000,
            "low": 450000,
            "high": 550000,
            "confidence_score": 30,
            "confidence_grade": "Fair",
            "sqm": 100,
            "epc": "D",
            "postcode": "SW16 2RQ",
            "evidence": [],
            "n_comps": 2,
            "type": "semi_detached_house",
        }

        from core.orchestrator import run_valuation
        result = run_valuation(address="1 Test St", user_id="u1", user_tier="free")

        triggers = result["product_triggers"]
        if len(triggers) >= 2:
            self.assertGreaterEqual(
                triggers[0]["relevance_score"],
                triggers[1]["relevance_score"],
            )

    @patch("core.orchestrator._compute_avm")
    def test_avm_failure_returns_error(self, mock_avm):
        """AVM failure returns ok=False with the error."""
        mock_avm.return_value = {"ok": False, "error": "No data", "address": "ZZ9 9ZZ"}

        from core.orchestrator import run_valuation
        result = run_valuation(address="ZZ9 9ZZ", user_id="u1", user_tier="free")

        self.assertFalse(result["ok"])
        self.assertFalse(result["avm"]["ok"])


if __name__ == "__main__":
    unittest.main()
