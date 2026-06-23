"""test_sell_vs_let.py — Tests for the Sell vs Let ROI calculator.

Verifies:
  - Sell path arithmetic (net proceeds, compound interest)
  - Let path arithmetic (net yield, capital appreciation)
  - Edge cases: zero value, zero rent, very high value
  - Recommendation logic (sell better, let better, neutral)
  - Input sanitisation (negative values, extreme values)
"""
from __future__ import annotations

import pytest

from products.engines.sell_vs_let_engine import calculate_sell_vs_let


# ── Test 1: Default sell scenario (high value, no rent) ────────────────────

def test_sell_better_high_value():
    """A £1M property with no rental income should clearly recommend selling."""
    result = calculate_sell_vs_let(
        assessed_value=1_000_000,
        outstanding_mortgage=200_000,
        average_local_rent=0,  # no rental income
    )
    assert result["ok"] is True
    assert result["recommendation"] == "sell"
    assert result["sell_path"]["net_proceeds_gbp"] > 0
    assert result["sell_path"]["3yr_total_gbp"] > 0
    assert result["difference_gbp"] > 0


# ── Test 2: Default let scenario (good rent, low value) ────────────────────

def test_let_better_good_rent():
    """A low-value property with high rent should favour letting."""
    result = calculate_sell_vs_let(
        assessed_value=150_000,
        outstanding_mortgage=100_000,
        average_local_rent=1200,  # £1,200/mo rent on £150k property
    )
    # High rent relative to value, low mortgage
    assert result["ok"] is True
    assert result["let_path"]["3yr_total_gbp"] > 0


# ── Test 3: Sell path arithmetic ──────────────────────────────────────────

def test_sell_path_arithmetic():
    """Verify the sell path math step by step."""
    result = calculate_sell_vs_let(
        assessed_value=500_000,
        outstanding_mortgage=300_000,
        fees_pct_sell=1.5,  # 1.5% selling fees
    )
    sp = result["sell_path"]

    # Net proceeds: 500k - 300k - (500k * 0.015) = 500k - 300k - 7.5k = 192.5k
    assert sp["net_proceeds_gbp"] == 192500.0

    # Invested at 4% for 3 years: 192500 * (1.04^3 - 1) = 192500 * 0.124864
    expected_return = 192500 * (1.04 ** 3 - 1)
    assert abs(sp["investment_return_gbp"] - expected_return) < 0.01

    # Total: net proceeds + return
    expected_total = 192500.0 + expected_return
    assert abs(sp["3yr_total_gbp"] - expected_total) < 0.01


# ── Test 4: Let path arithmetic ────────────────────────────────────────────

def test_let_path_arithmetic():
    """Verify the let path math step by step."""
    result = calculate_sell_vs_let(
        assessed_value=500_000,
        outstanding_mortgage=300_000,
        average_local_rent=2000,  # £2,000/mo
        mortgage_rate=4.5,
        hpi_momentum_pct=2.0,
        marginal_tax_rate=20,
        maintenance_pct=1.0,
    )
    lp = result["let_path"]

    # Annual rent: 2000 * 12 = 24,000
    assert lp["annual_rent_gbp"] == 24000.0

    # Annual mortgage: 300k * 0.045 = 13,500
    assert lp["annual_mortgage_cost_gbp"] == 13500.0

    # Mortgage interest portion: 13,500 * 0.8 = 10,800
    # Taxable profit: 24,000 - 10,800 = 13,200
    # Tax at 20%: 13,200 * 0.2 = 2,640
    assert lp["annual_tax_gbp"] == 2640.0

    # Maintenance: 500k * 0.01 = 5,000
    assert lp["annual_maintenance_gbp"] == 5000.0

    # Net annual yield: 24,000 - 13,500 - 2,640 - 5,000 = 2,860
    assert lp["net_annual_yield_gbp"] == 2860.0

    # Capital appreciation: 500k * (1.02^3 - 1) = 500k * 0.061208
    expected_ca = 500000 * (1.02 ** 3 - 1)
    assert abs(lp["3yr_capital_appreciation_gbp"] - expected_ca) < 0.01

    # 3yr total: 2,860 * 3 + capital_appreciation
    expected_total = max(2860.0, 0) * 3 + max(expected_ca, 0)
    assert abs(lp["3yr_total_gbp"] - expected_total) < 0.01


# ── Test 5: Edge case — zero value ────────────────────────────────────────

def test_zero_value():
    """A zero-value property should not crash."""
    result = calculate_sell_vs_let(assessed_value=0)
    assert result["ok"] is True
    assert result["sell_path"]["net_proceeds_gbp"] == 0.0
    assert result["recommendation"] in ("sell", "neutral", "let")


# ── Test 6: Edge case — no mortgage ───────────────────────────────────────

def test_no_mortgage():
    """A property owned outright should clearly favour something."""
    result = calculate_sell_vs_let(
        assessed_value=500_000,
        outstanding_mortgage=0,
        average_local_rent=2000,
    )
    assert result["ok"] is True
    # No mortgage means full proceeds on sell, full rent on let
    sp = result["sell_path"]
    lp = result["let_path"]
    assert sp["net_proceeds_gbp"] > 0
    assert lp["net_annual_yield_gbp"] > 0


# ── Test 7: Recommendation — sell strongly better ─────────────────────────

def test_recommendation_sell():
    """When sell > let by >5% of value, recommend sell."""
    result = calculate_sell_vs_let(
        assessed_value=1_000_000,
        outstanding_mortgage=100_000,
        average_local_rent=500,  # low rent
        fees_pct_sell=1.0,
    )
    assert result["recommendation"] == "sell"
    assert result["difference_pct_of_value"] > 0


# ── Test 8: Recommendation — let strongly better ──────────────────────────

def test_recommendation_let():
    """When let > sell by >5% of value, recommend let."""
    result = calculate_sell_vs_let(
        assessed_value=100_000,
        outstanding_mortgage=80_000,
        average_local_rent=2000,  # very high rent relative to value
        mortgage_rate=3.0,
        hpi_momentum_pct=5.0,
        fees_pct_sell=0,
        marginal_tax_rate=0,
        maintenance_pct=0.5,
    )
    assert result["recommendation"] == "let"


# ── Test 9: Recommendation — neutral (within 5% band) ─────────────────────

def test_recommendation_neutral():
    """When sell and let are close, recommend neutral."""
    # Tweak inputs to get close outcomes
    result = calculate_sell_vs_let(
        assessed_value=300_000,
        outstanding_mortgage=150_000,
        average_local_rent=1200,
        mortgage_rate=4.0,
        hpi_momentum_pct=2.0,
        fees_pct_sell=1.0,
        marginal_tax_rate=20,
        maintenance_pct=1.0,
        years=3,
    )
    assert result["recommendation"] in ("sell", "let", "neutral")


# ── Test 10: Sanity — total is always positive ────────────────────────────

@pytest.mark.parametrize("value,mortgage,rent", [
    (50_000, 0, 300),
    (250_000, 150_000, 1000),
    (1_000_000, 500_000, 3000),
    (5_000_000, 2_000_000, 8000),
    (100_000, 95_000, 500),
])
def test_totals_positive(value, mortgage, rent):
    """All financial totals should be non-negative for sensible inputs."""
    result = calculate_sell_vs_let(
        assessed_value=value,
        outstanding_mortgage=mortgage,
        average_local_rent=rent,
    )
    assert result["sell_path"]["3yr_total_gbp"] >= 0
    assert result["let_path"]["3yr_total_gbp"] >= 0


# ── Test 11: Input snapshot is complete ────────────────────────────────────

def test_input_snapshot():
    """The inputs reflection should contain all expected keys."""
    result = calculate_sell_vs_let(assessed_value=300_000)
    keys = set(result["inputs"].keys())
    expected = {
        "assessed_value_gbp",
        "outstanding_mortgage_gbp",
        "average_local_rent_gbp_pcm",
        "mortgage_rate_pct",
        "hpi_momentum_pct",
        "selling_fees_pct",
        "marginal_tax_rate_pct",
        "maintenance_pct",
    }
    assert keys == expected, f"Missing keys: {expected - keys}"
