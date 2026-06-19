#!/usr/bin/env python3
"""test_api_valuate.py - Tests for POST /v1/properties/valuate.

Mocks the orchestrator and entitlements to verify:
  - Successful valuation returns AVM + triggers
  - Daily AVM limit blocks further requests (429)
  - Missing address/postcode returns 400
"""
import unittest
from unittest.mock import patch, MagicMock


class TestValuateEndpoint(unittest.TestCase):

    @patch("auth.entitlements.check_avm_limit")
    @patch("core.orchestrator.run_valuation")
    def test_successful_valuation(self, mock_run, mock_limit):
        """Successful valuation returns AVM data + triggers."""
        mock_limit.return_value = {"allowed": True, "count_today": 0, "daily_limit": 1, "remaining": 0}
        mock_run.return_value = {
            "ok": True,
            "avm": {
                "ok": True,
                "address": "1 Test St",
                "central": 500000,
                "low": 450000,
                "high": 550000,
                "confidence_score": 85,
                "confidence_grade": "Strong",
                "sqm": 100,
                "epc": "C",
                "postcode": "SW16 2RQ",
                "evidence": [],
                "n_comps": 10,
                "type": "terraced_house",
            },
            "product_triggers": [
                {"product_id": "planning_permission_oracle", "relevance_score": 70},
            ],
            "elapsed_s": 1.2,
        }

        from api.v1.properties import valuate_property, ValuateRequest
        req = ValuateRequest(address="1 Test St", user_id="user_123")
        result = valuate_property(req, authorization="Bearer user_123:free")

        self.assertTrue(result["ok"])
        self.assertEqual(result["avm"]["central"], 500000)
        self.assertEqual(len(result["product_triggers"]), 1)

    @patch("auth.entitlements.check_avm_limit")
    @patch("core.orchestrator.run_valuation")
    def test_avm_limit_blocks_request(self, mock_run, mock_limit):
        """Daily AVM limit exceeded raises 429."""
        from fastapi import HTTPException
        mock_limit.return_value = {"allowed": False, "count_today": 1, "daily_limit": 1, "remaining": 0}

        from api.v1.properties import valuate_property, ValuateRequest
        req = ValuateRequest(address="1 Test St", user_id="user_123")

        with self.assertRaises(HTTPException) as ctx:
            valuate_property(req, authorization="Bearer user_123:free")

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("avm_limit_reached", str(ctx.exception.detail))

    @patch("auth.entitlements.check_avm_limit")
    @patch("core.orchestrator.run_valuation")
    def test_missing_address_raises_400(self, mock_run, mock_limit):
        """Missing both address and postcode raises 400."""
        from fastapi import HTTPException
        mock_limit.return_value = {"allowed": True, "count_today": 0, "daily_limit": 1, "remaining": 1}

        from api.v1.properties import valuate_property, ValuateRequest
        req = ValuateRequest(user_id="user_123")

        with self.assertRaises(HTTPException) as ctx:
            valuate_property(req, authorization="Bearer user_123:free")

        self.assertEqual(ctx.exception.status_code, 400)

    @patch("auth.entitlements.check_avm_limit")
    @patch("core.orchestrator.run_valuation")
    def test_pro_user_no_limit(self, mock_run, mock_limit):
        """Pro users have unlimited AVMs (daily_limit=0)."""
        mock_limit.return_value = {"allowed": True, "count_today": 100, "daily_limit": "unlimited", "remaining": "unlimited"}
        mock_run.return_value = {
            "ok": True,
            "avm": {"ok": True, "address": "1 Pro St", "central": 800000, "low": 720000, "high": 880000,
                     "confidence_score": 90, "confidence_grade": "Strong", "sqm": 120, "epc": "C",
                     "postcode": "N22 5JB", "evidence": [], "n_comps": 15, "type": "semi_detached_house"},
            "product_triggers": [],
            "elapsed_s": 0.8,
        }

        from api.v1.properties import valuate_property, ValuateRequest
        req = ValuateRequest(address="1 Pro St", user_id="pro_user")
        result = valuate_property(req, authorization="Bearer pro_user:pro")

        self.assertTrue(result["ok"])
        self.assertEqual(result["tier"], "pro")


if __name__ == "__main__":
    unittest.main()
