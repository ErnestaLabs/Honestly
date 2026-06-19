#!/usr/bin/env python3
"""test_webhook_payments.py - Tests for Telegram payment webhook handlers.

Verifies:
  - pre_checkout_query always returns ok=True
  - successful_payment handles subscriptions (tier + credits)
  - successful_payment handles credit top-ups (balance increment)
  - successful_payment handles direct upsell purchases (entitlement)
"""
import unittest
from unittest.mock import patch, MagicMock


class TestPreCheckout(unittest.TestCase):

    def test_pre_checkout_always_ok(self):
        """pre_checkout_query always answers ok=True within 10 seconds."""
        from bot.webhook import handle_pre_checkout
        import asyncio

        update = {
            "pre_checkout_query": {
                "id": "query_123",
                "currency": "XTR",
                "total_amount": 75,
            }
        }
        result = asyncio.get_event_loop().run_until_complete(
            handle_pre_checkout(update)
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["method"], "answerPreCheckoutQuery")
        self.assertEqual(result["pre_checkout_query_id"], "query_123")


class TestSubscriptionPayment(unittest.TestCase):

    @patch("bot.webhook._get_redis")
    @patch("payments.stars_handler.grant_monthly_credits")
    def test_plus_subscription_sets_tier(self, mock_grant, mock_redis_fn):
        """Plus subscription sets the user's tier and grants credits."""
        mock_redis = MagicMock()
        mock_redis_fn.return_value = mock_redis
        mock_grant.return_value = 5.0

        from bot.webhook import handle_successful_payment
        import asyncio

        update = {
            "message": {
                "from": {"id": 12345},
                "successful_payment": {
                    "invoice_payload": '{"type":"subscription","tier":"plus","gbp_price":5.0}',
                    "total_amount": 250,  # £5 * 50
                    "currency": "XTR",
                },
            }
        }
        result = asyncio.get_event_loop().run_until_complete(
            handle_successful_payment(update)
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["tier"], "plus")
        self.assertEqual(result["credits_granted_gbp"], 5.0)
        # Redis SET should have been called for tier and expiry
        mock_redis.set.assert_called()

    @patch("bot.webhook._get_redis")
    @patch("payments.stars_handler.grant_monthly_credits")
    def test_pro_subscription_sets_tier(self, mock_grant, mock_redis_fn):
        """Pro subscription sets tier=pro and grants £10 credits."""
        mock_redis = MagicMock()
        mock_redis_fn.return_value = mock_redis
        mock_grant.return_value = 10.0

        from bot.webhook import handle_successful_payment
        import asyncio

        update = {
            "message": {
                "from": {"id": 67890},
                "successful_payment": {
                    "invoice_payload": '{"type":"subscription","tier":"pro","gbp_price":15.0}',
                    "total_amount": 750,  # £15 * 50
                    "currency": "XTR",
                },
            }
        }
        result = asyncio.get_event_loop().run_until_complete(
            handle_successful_payment(update)
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["tier"], "pro")
        self.assertEqual(result["credits_granted_gbp"], 10.0)


class TestCreditTopUp(unittest.TestCase):

    @patch("bot.webhook._get_redis")
    def test_credit_topup_adds_to_balance(self, mock_redis_fn):
        """Credit top-up adds the purchased amount to the Redis balance."""
        mock_redis = MagicMock()
        mock_redis.incrby.return_value = 5000  # new balance in pence
        mock_redis_fn.return_value = mock_redis

        from bot.webhook import handle_successful_payment
        import asyncio

        update = {
            "message": {
                "from": {"id": 12345},
                "successful_payment": {
                    "invoice_payload": '{"type":"credit_topup","gbp_price":10.0}',
                    "total_amount": 500,  # £10 * 50
                    "currency": "XTR",
                },
            }
        }
        result = asyncio.get_event_loop().run_until_complete(
            handle_successful_payment(update)
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["type"], "credit_topup")
        self.assertEqual(result["added_gbp"], 10.0)
        self.assertEqual(result["paid_xtr"], 500)
        # Redis INCRBY should have been called to add credits
        mock_redis.incrby.assert_called_once()


class TestUpsellPurchase(unittest.TestCase):

    @patch("bot.webhook._get_redis")
    def test_upsell_purchase_sets_entitlement(self, mock_redis_fn):
        """Direct upsell purchase adds an entitlement to the user's profile."""
        mock_redis = MagicMock()
        mock_redis_fn.return_value = mock_redis

        from bot.webhook import handle_successful_payment
        import asyncio

        update = {
            "message": {
                "from": {"id": 12345},
                "successful_payment": {
                    "invoice_payload": '{"type":"upsell_lowball","product_id":"lowball_counter_email","gbp_price":1.49}',
                    "total_amount": 75,  # ~£1.49 * 50
                    "currency": "XTR",
                },
            }
        }
        result = asyncio.get_event_loop().run_until_complete(
            handle_successful_payment(update)
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["product_id"], "lowball_counter_email")
        self.assertEqual(result["type"], "upsell_purchase")
        # Redis SET should have been called for the entitlement
        mock_redis.set.assert_called_once()
        # The entitlement key should contain the product_id
        call_args = mock_redis.set.call_args[0]
        self.assertIn("lowball_counter_email", call_args[1])

    @patch("bot.webhook._get_redis")
    def test_non_xtr_payment_rejected(self, mock_redis_fn):
        """Non-XTR currency payments are rejected."""
        from bot.webhook import handle_successful_payment
        import asyncio

        update = {
            "message": {
                "from": {"id": 12345},
                "successful_payment": {
                    "invoice_payload": '{"type":"subscription","tier":"plus"}',
                    "total_amount": 500,
                    "currency": "USD",  # wrong currency
                },
            }
        }
        result = asyncio.get_event_loop().run_until_complete(
            handle_successful_payment(update)
        )

        self.assertFalse(result["ok"])
        self.assertIn("non_xtr_payment", result["error"])


if __name__ == "__main__":
    unittest.main()
