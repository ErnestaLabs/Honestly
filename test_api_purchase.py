#!/usr/bin/env python3
"""test_api_purchase.py - Tests for POST /v1/products/purchase.

Verifies the atomic credit deduction and refund logic:
  - Successful purchase deducts credits
  - Insufficient funds returns 402
  - Engine failure triggers credit refund (INCRBY rollback)
  - Tier access denied returns 403
"""
import unittest
from unittest.mock import patch, MagicMock


class TestPurchaseEndpoint(unittest.TestCase):

    def _mock_redis_with_balance(self, balance_pence: int):
        """Create a mock Redis client with a specific balance."""
        mock_redis = MagicMock()
        balance_key = f"honestly:credits:pence:user_123"

        # Simulate DECRBY: subtract and return new balance
        def decrby_side_effect(key, amount):
            nonlocal balance_pence
            balance_pence -= amount
            return balance_pence

        def incrby_side_effect(key, amount):
            nonlocal balance_pence
            balance_pence += amount
            return balance_pence

        def get_side_effect(key):
            return str(balance_pence)

        mock_redis.decrby.side_effect = decrby_side_effect
        mock_redis.incrby.side_effect = incrby_side_effect
        mock_redis.get.side_effect = get_side_effect
        mock_redis.ping.return_value = True
        return mock_redis

    @patch("api.v1.products._execute_product")
    @patch("api.v1.products._get_redis")
    def test_successful_purchase_deducts_credits(self, mock_redis_fn, mock_execute):
        """Successful purchase deducts the correct amount from the balance."""
        mock_redis = self._mock_redis_with_balance(1000)  # £10.00 in pence
        mock_redis_fn.return_value = mock_redis
        mock_execute.return_value = {"ok": True, "email_text": "Dear Agent..."}

        from api.v1.products import purchase_product, PurchaseRequest
        req = PurchaseRequest(
            user_id="user_123",
            product_id="lowball_counter_email",  # £1.49
            valuation_context={"address": "1 Test St", "central": 500000},
        )
        result = purchase_product(req, authorization="Bearer user_123:free")

        self.assertTrue(result["ok"])
        self.assertEqual(result["product_id"], "lowball_counter_email")
        self.assertEqual(result["charged_gbp"], 1.49)
        # DECRBY should have been called
        mock_redis.decrby.assert_called_once()
        # INCRBY (refund) should NOT have been called
        mock_redis.incrby.assert_not_called()

    @patch("api.v1.products._execute_product")
    @patch("api.v1.products._get_redis")
    def test_insufficient_funds_returns_402(self, mock_redis_fn, mock_execute):
        """Insufficient credits returns 402 Payment Required."""
        mock_redis = self._mock_redis_with_balance(50)  # £0.50 in pence
        mock_redis_fn.return_value = mock_redis

        from api.v1.products import purchase_product, PurchaseRequest
        from fastapi import HTTPException
        req = PurchaseRequest(
            user_id="user_123",
            product_id="lowball_counter_email",  # £1.49 = 149 pence
            valuation_context={"address": "1 Test St"},
        )

        with self.assertRaises(HTTPException) as ctx:
            purchase_product(req, authorization="Bearer user_123:free")

        self.assertEqual(ctx.exception.status_code, 402)
        detail = ctx.exception.detail
        self.assertIn("insufficient_credits", str(detail))
        # INCRBY should have been called to roll back the negative deduction
        mock_redis.incrby.assert_called_once()

    @patch("api.v1.products._execute_product")
    @patch("api.v1.products._get_redis")
    def test_engine_failure_refunds_credits(self, mock_redis_fn, mock_execute):
        """Product engine failure triggers credit refund via INCRBY."""
        mock_redis = self._mock_redis_with_balance(1000)  # £10.00
        mock_redis_fn.return_value = mock_redis
        mock_execute.return_value = {"ok": False, "error": "LLM unavailable"}

        from api.v1.products import purchase_product, PurchaseRequest
        from fastapi import HTTPException
        req = PurchaseRequest(
            user_id="user_123",
            product_id="lowball_counter_email",  # £1.49
            valuation_context={"address": "1 Test St"},
        )

        with self.assertRaises(HTTPException) as ctx:
            purchase_product(req, authorization="Bearer user_123:free")

        self.assertEqual(ctx.exception.status_code, 500)
        detail = ctx.exception.detail
        self.assertIn("product_execution_failed", str(detail))
        self.assertIn("refunded_gbp", str(detail))
        # INCRBY should have been called for the refund
        mock_redis.incrby.assert_called_once()
        # The refund amount should match the deduction amount
        decrby_amount = mock_redis.decrby.call_args[0][1]
        incrby_amount = mock_redis.incrby.call_args[0][1]
        self.assertEqual(decrby_amount, incrby_amount, "Refund must match deduction")

    def test_tier_access_denied_returns_403(self):
        """Free user buying a Plus-tier product gets 403."""
        from api.v1.products import purchase_product, PurchaseRequest
        from fastapi import HTTPException
        req = PurchaseRequest(
            user_id="user_123",
            product_id="stealth_listing_sniper",  # tier_access="plus"
            valuation_context={"address": "1 Test St"},
        )

        with self.assertRaises(HTTPException) as ctx:
            purchase_product(req, authorization="Bearer user_123:free")

        self.assertEqual(ctx.exception.status_code, 403)

    @patch("api.v1.products._execute_product")
    @patch("api.v1.products._get_redis")
    def test_pro_discount_reduces_cost(self, mock_redis_fn, mock_execute):
        """Pro users get 20% discount on the credit cost."""
        mock_redis = self._mock_redis_with_balance(5000)  # £50.00
        mock_redis_fn.return_value = mock_redis
        mock_execute.return_value = {"ok": True, "email_text": "test"}

        from api.v1.products import purchase_product, PurchaseRequest
        req = PurchaseRequest(
            user_id="pro_user",
            product_id="lowball_counter_email",  # £1.49 base
            valuation_context={"address": "1 Test St"},
        )
        result = purchase_product(req, authorization="Bearer pro_user:pro")

        self.assertTrue(result["ok"])
        # Pro discount: £1.49 * 0.8 = £1.19 (rounded)
        self.assertAlmostEqual(result["charged_gbp"], 1.19, places=2)
        self.assertEqual(result["discount_pct"], 20.0)

    def test_unknown_product_returns_404(self):
        """Unknown product_id returns 404."""
        from api.v1.products import purchase_product, PurchaseRequest
        from fastapi import HTTPException
        req = PurchaseRequest(
            user_id="user_123",
            product_id="nonexistent_product",
            valuation_context={},
        )

        with self.assertRaises(HTTPException) as ctx:
            purchase_product(req, authorization="Bearer user_123:free")

        self.assertEqual(ctx.exception.status_code, 404)


class TestCatalogEndpoint(unittest.TestCase):

    def test_catalog_includes_discount(self):
        """Catalog returns tier-adjusted prices."""
        from api.v1.products import get_catalog
        result = get_catalog(authorization="Bearer user_1:pro")

        self.assertTrue(result["ok"])
        self.assertEqual(result["tier"], "pro")
        self.assertEqual(result["discount_pct"], 20.0)
        # Each product should have effective_gbp_price < gbp_price for Pro
        for p in result["products"]:
            self.assertLessEqual(p["effective_gbp_price"], p["gbp_price"])

    def test_catalog_free_no_discount(self):
        """Free tier gets no discount."""
        from api.v1.products import get_catalog
        result = get_catalog(authorization="Bearer user_1:free")

        self.assertTrue(result["ok"])
        self.assertEqual(result["discount_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
