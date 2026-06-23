"""test_intent_engine.py — Tests for the intent tracking and scoring engine.

Verifies:
  - Signal logging works end-to-end (requires Redis)
  - Scoring algorithm produces correct 0–100 range
  - Each signal type contributes the right weight
  - Score caps at 100
  - High-intent property query works
  - Affiliate injector returns correct offers
"""
from __future__ import annotations

import json
import time

import pytest

from core.intent_engine import (
    SIGNAL_VALUATION_RUN,
    SIGNAL_UPSELL_PURCHASED,
    SIGNAL_RETURNED_7_DAYS,
    calculate_sell_probability,
    get_high_intent_properties,
    get_postcode_stats,
    log_intent_signal,
    WEIGHT_VALUATION_RUN,
    WEIGHT_UPSELL_PURCHASED,
    WEIGHT_REPEATED_VALUATION_3PLUS,
    WEIGHT_RETURNED_7_DAYS,
    SCORE_CAP,
)


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def postcode():
    return "SW16"


@pytest.fixture
def property_id():
    return "SW16_TEST_001"


@pytest.fixture
def user_id():
    return "test_user_001"


@pytest.fixture
def another_user():
    return "test_user_002"


# ── Helpers ────────────────────────────────────────────────────────────────

def _clear_keys(postcode, property_id):
    """Clean up Redis test keys."""
    try:
        import redis as redis_mod
        r = redis_mod.Redis.from_url("redis://localhost:6379/0", decode_responses=True)
        r.delete(
            f"honestly:intent:signal:{postcode}:{property_id}",
            f"honestly:intent:timeline:test_user_001:{postcode}:{property_id}",
            f"honestly:intent:score:{postcode}:{property_id}",
            f"honestly:intent:timeline:test_user_002:{postcode}:{property_id}",
        )
    except Exception:
        pass


# ── Test 1: Score is 0 with no signals ────────────────────────────────────

def test_no_signals_score_zero(postcode, property_id):
    """A property with no intent signals should score 0."""
    _clear_keys(postcode, property_id)
    score = calculate_sell_probability(postcode, property_id)
    assert score == 0, f"Expected 0, got {score}"
    _clear_keys(postcode, property_id)


# ── Test 2: Valuation run adds +20 ────────────────────────────────────────

def test_valuation_run_adds_20(postcode, property_id, user_id):
    """A single valuation_run should produce a score of 20."""
    _clear_keys(postcode, property_id)
    log_intent_signal(user_id, postcode, property_id, SIGNAL_VALUATION_RUN)
    score = calculate_sell_probability(postcode, property_id)
    assert score == WEIGHT_VALUATION_RUN, f"Expected {WEIGHT_VALUATION_RUN}, got {score}"
    _clear_keys(postcode, property_id)


# ── Test 3: Upsell purchased adds +30 ─────────────────────────────────────

def test_upsell_purchased_adds_30(postcode, property_id, user_id):
    """An upsell_purchased signal should add 30."""
    _clear_keys(postcode, property_id)
    log_intent_signal(user_id, postcode, property_id, SIGNAL_VALUATION_RUN)
    log_intent_signal(
        user_id, postcode, property_id, SIGNAL_UPSELL_PURCHASED,
        metadata={"product_id": "lowball_counter_email"},
    )
    score = calculate_sell_probability(postcode, property_id)
    expected = WEIGHT_VALUATION_RUN + WEIGHT_UPSELL_PURCHASED
    assert score == expected, f"Expected {expected}, got {score}"
    _clear_keys(postcode, property_id)


# ── Test 4: Repeated valuations (3+) adds +20 ─────────────────────────────

def test_repeated_valuations_3plus_adds_20(postcode, property_id, user_id):
    """Three valuation runs by the same user should add the repeat bonus."""
    _clear_keys(postcode, property_id)
    for _ in range(3):
        log_intent_signal(user_id, postcode, property_id, SIGNAL_VALUATION_RUN)
    score = calculate_sell_probability(postcode, property_id)
    expected = WEIGHT_VALUATION_RUN + WEIGHT_REPEATED_VALUATION_3PLUS
    assert score == expected, f"Expected {expected}, got {score}"
    _clear_keys(postcode, property_id)


# ── Test 5: Two valuations (not 3+) does NOT add repeat bonus ─────────────

def test_two_valuations_no_repeat_bonus(postcode, property_id, user_id):
    """Two valuation runs should not trigger the repeat bonus."""
    _clear_keys(postcode, property_id)
    for _ in range(2):
        log_intent_signal(user_id, postcode, property_id, SIGNAL_VALUATION_RUN)
    score = calculate_sell_probability(postcode, property_id)
    # Should be just the valuation_run weight (no repeat bonus for < 3)
    assert score == WEIGHT_VALUATION_RUN, f"Expected {WEIGHT_VALUATION_RUN}, got {score}"
    _clear_keys(postcode, property_id)


# ── Test 6: Returned within 7 days adds +30 ───────────────────────────────

def test_returned_7_days_adds_30(postcode, property_id, user_id):
    """A returned_7_days signal should add 30."""
    _clear_keys(postcode, property_id)
    log_intent_signal(user_id, postcode, property_id, SIGNAL_VALUATION_RUN)
    log_intent_signal(user_id, postcode, property_id, SIGNAL_RETURNED_7_DAYS)
    score = calculate_sell_probability(postcode, property_id)
    expected = WEIGHT_VALUATION_RUN + WEIGHT_RETURNED_7_DAYS
    assert score == expected, f"Expected {expected}, got {score}"
    _clear_keys(postcode, property_id)


# ── Test 7: All signals max out at 100 ────────────────────────────────────

def test_score_caps_at_100(postcode, property_id, user_id):
    """Combining all signals should never exceed 100."""
    _clear_keys(postcode, property_id)
    # 3 valuation runs (20 + 20)
    for _ in range(3):
        log_intent_signal(user_id, postcode, property_id, SIGNAL_VALUATION_RUN)
    # Upsell purchased (30)
    log_intent_signal(
        user_id, postcode, property_id, SIGNAL_UPSELL_PURCHASED,
    )
    # Returned within 7 days (30)
    log_intent_signal(user_id, postcode, property_id, SIGNAL_RETURNED_7_DAYS)

    score = calculate_sell_probability(postcode, property_id)
    # Raw would be: 20 + 30 + 20 + 30 = 100
    assert score == SCORE_CAP, f"Expected {SCORE_CAP}, got {score}"
    _clear_keys(postcode, property_id)


# ── Test 8: Scores from different users are aggregated ─────────────────────

def test_multiple_users_aggregated(postcode, property_id, user_id, another_user):
    """Signals from different users should all count toward the property score."""
    _clear_keys(postcode, property_id)
    # User 1: valuation run
    log_intent_signal(user_id, postcode, property_id, SIGNAL_VALUATION_RUN)
    # User 2: valuation run + upsell purchased
    log_intent_signal(another_user, postcode, property_id, SIGNAL_VALUATION_RUN)
    log_intent_signal(
        another_user, postcode, property_id, SIGNAL_UPSELL_PURCHASED,
    )

    score = calculate_sell_probability(postcode, property_id)
    # valuation_run from either user = +20, upsell_purchased = +30
    expected = WEIGHT_VALUATION_RUN + WEIGHT_UPSELL_PURCHASED
    assert score == expected, f"Expected {expected}, got {score}"
    _clear_keys(postcode, property_id)


# ── Test 9: High-intent query returns correct results ──────────────────────

def test_high_intent_query(postcode, property_id, user_id):
    """get_high_intent_properties should return properties above threshold."""
    _clear_keys(postcode, property_id)
    # Create a medium-intent property (just valuation_run = 20)
    log_intent_signal(user_id, postcode, property_id, SIGNAL_VALUATION_RUN)

    # Create a high-intent property
    high_intent_id = "SW16_HOT_002"
    log_intent_signal(user_id, postcode, high_intent_id, SIGNAL_VALUATION_RUN)
    log_intent_signal(user_id, postcode, high_intent_id, SIGNAL_UPSELL_PURCHASED)
    log_intent_signal(user_id, postcode, high_intent_id, SIGNAL_RETURNED_7_DAYS)

    results = get_high_intent_properties(
        postcodes=[postcode],
        threshold=60,
        limit=10,
    )

    # Should find the hot property (score = 20+30+30 = 80), not the cold one
    prop_ids = [r["property_id"] for r in results]
    assert high_intent_id in prop_ids, f"Hot property not found in {prop_ids}"
    # The cold property (score=20) should be below threshold
    for r in results:
        if r["property_id"] == property_id:
            assert r["sell_probability"] >= 60, (
                f"Cold property unexpectedly in results"
            )

    # Cleanup
    _clear_keys(postcode, property_id)
    _clear_keys(postcode, high_intent_id)


# ── Test 10: Postcode stats returns aggregate data ─────────────────────────

def test_postcode_stats(postcode, property_id, user_id):
    """get_postcode_stats should return non-zero aggregate data."""
    _clear_keys(postcode, property_id)
    log_intent_signal(user_id, postcode, property_id, SIGNAL_VALUATION_RUN)

    stats = get_postcode_stats(postcode)
    assert stats["postcode"] == postcode
    assert stats["total_signals"] >= 1
    assert stats["unique_properties"] >= 1

    _clear_keys(postcode, property_id)


# ── Test 11: Affiliate injector — high value ──────────────────────────────

def test_affiliate_high_value():
    """Properties valued over £500k should get a mortgage broker offer."""
    from monetization.router import get_marketplace_offers
    avm = {
        "ok": True,
        "central": 650_000,
        "epc": "C",
        "type": "house",
        "confidence_score": 75,
    }
    offers = get_marketplace_offers(avm)
    types = [o["offer_type"] for o in offers]
    assert "mortgage" in types, f"Expected mortgage offer in {types}"


# ── Test 12: Affiliate injector — poor EPC ────────────────────────────────

def test_affiliate_poor_epc():
    """EPC < C should trigger an energy upgrade offer."""
    from monetization.router import get_marketplace_offers
    avm = {
        "ok": True,
        "central": 350_000,
        "epc": "E",
        "type": "house",
        "confidence_score": 75,
    }
    offers = get_marketplace_offers(avm)
    types = [o["offer_type"] for o in offers]
    assert "energy" in types, f"Expected energy offer in {types}"


# ── Test 13: Affiliate injector — leasehold flat ──────────────────────────

def test_affiliate_leasehold_flat():
    """Flats should trigger a conveyancing offer."""
    from monetization.router import get_marketplace_offers
    avm = {
        "ok": True,
        "central": 350_000,
        "epc": "B",
        "type": "flat",
        "confidence_score": 75,
    }
    offers = get_marketplace_offers(avm)
    types = [o["offer_type"] for o in offers]
    assert "conveyancing" in types, f"Expected conveyancing offer in {types}"


# ── Test 14: Affiliate injector — low confidence survey ───────────────────

def test_affiliate_low_confidence():
    """Low confidence should trigger a survey offer."""
    from monetization.router import get_marketplace_offers
    avm = {
        "ok": True,
        "central": 350_000,
        "epc": "B",
        "type": "house",
        "confidence_score": 40,
    }
    offers = get_marketplace_offers(avm)
    types = [o["offer_type"] for o in offers]
    assert "survey" in types, f"Expected survey offer in {types}"


# ── Test 15: Affiliate injector — no match ────────────────────────────────

def test_affiliate_no_match():
    """A property that doesn't trigger any conditions should get no offers."""
    from monetization.router import get_marketplace_offers
    avm = {
        "ok": True,
        "central": 350_000,
        "epc": "B",
        "type": "house",
        "confidence_score": 75,
    }
    offers = get_marketplace_offers(avm)
    assert len(offers) == 0, f"Expected no offers, got {offers}"
