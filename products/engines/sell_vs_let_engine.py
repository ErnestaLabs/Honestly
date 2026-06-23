"""products/engines/sell_vs_let_engine.py — Sell vs Let ROI calculator.

Plus-tier consumer tool. Deterministic financial comparison of selling a
property vs renting it out over a 3-year horizon. No LLM, no hallucination —
pure arithmetic from real inputs.

Inputs (from AVM context):
  - assessed_value: Current AVM central value in GBP
  - outstanding_mortgage: Remaining mortgage balance (default 50% of value)
  - average_local_rent: Monthly rent for similar property (mock/ONS)
  - mortgage_rate: Current BoE-influenced mortgage rate (from boe.py or default 4.5%)
  - hpi_momentum_pct: Annual local HPI change (from graph_db or default 2%)
  - fees_pct_sell: Selling fees as % of value (estate agent + legal, default 1.5%)
  - marginal_tax_rate: Seller's marginal income tax rate (default 20%)
  - maintenance_pct: Annual maintenance as % of value (default 1%)

Sell Path (3-year net position):
  1. Net proceeds = assessed_value - outstanding_mortgage - fees_pct_sell*value
  2. If invested at 4% annual return (post-tax cash):
     3yr_compound = net_proceeds * (1.04^3 - 1)
  3. Total = net_proceeds + 3yr_compound

Let Path (3-year net position):
  1. Annual rent = monthly_rent * 12
  2. Annual mortgage cost = outstanding_mortgage * mortgage_rate
  3. Annual tax = (annual_rent - mortgage_interest_portion) * marginal_tax_rate
     where mortgage_interest_portion = outstanding_mortgage * mortgage_rate * 0.8
  4. Annual maintenance = assessed_value * maintenance_pct
  5. Net annual yield = annual_rent - annual_mortgage - annual_tax - annual_maintenance
  6. 3yr_capital_appreciation = assessed_value * ((1 + hpi_momentum_pct)^3 - 1)
  7. Total = net_annual_yield * 3 + 3yr_capital_appreciation

Output:
  Clean JSON with both paths, the difference, and a recommendation.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)

# ── Defaults (sourced from BoE/ONS where live data unavailable) ────────────
DEFAULT_MORTGAGE_RATE = 4.5   # %
DEFAULT_HPI_MOMENTUM = 2.0     # % annual
DEFAULT_SELLING_FEES_PCT = 1.5 # %
DEFAULT_MARGINAL_TAX_RATE = 20 # %
DEFAULT_MAINTENANCE_PCT = 1.0  # %
DEFAULT_INVESTMENT_RETURN = 4.0  # % annual (post-tax, e.g. ISA / index fund)


def calculate_sell_vs_let(
    assessed_value: float,
    outstanding_mortgage: Optional[float] = None,
    average_local_rent: Optional[float] = None,
    mortgage_rate: Optional[float] = None,
    hpi_momentum_pct: Optional[float] = None,
    fees_pct_sell: Optional[float] = None,
    marginal_tax_rate: Optional[float] = None,
    maintenance_pct: Optional[float] = None,
    years: int = 3,
) -> dict:
    """Compare the 3-year net financial position of Selling vs Letting.

    All monetary values in GBP. All percentages as whole numbers
    (e.g. 4.5 for 4.5%).

    Args:
        assessed_value: Current AVM central value.
        outstanding_mortgage: Remaining mortgage balance. Default 50% of value.
        average_local_rent: Monthly rent. Default 0.4% of value (rough UK avg).
        mortgage_rate: Annual mortgage interest rate %. Default 4.5%.
        hpi_momentum_pct: Annual house price inflation %. Default 2%.
        fees_pct_sell: Selling costs as % of value. Default 1.5%.
        marginal_tax_rate: Income tax rate for rental income. Default 20%.
        maintenance_pct: Annual maintenance as % of value. Default 1%.
        years: Projection horizon in years. Default 3.

    Returns:
        Dict with:
          - sell_path: dict with net proceeds, invested return, total
          - let_path: dict with annual yield, capital appreciation, total
          - difference: sell_total - let_total (positive = sell better)
          - recommendation: "sell" | "let" | "neutral"
          - inputs: sanitised input snapshot
    """
    # ── Sanitise inputs ──────────────────────────────────────────────
    assessed_value = max(assessed_value, 0.0)
    outstanding_mortgage = outstanding_mortgage or assessed_value * 0.5
    average_local_rent = average_local_rent or assessed_value * 0.004
    mortgage_rate = mortgage_rate or DEFAULT_MORTGAGE_RATE
    hpi_momentum_pct = hpi_momentum_pct or DEFAULT_HPI_MOMENTUM
    fees_pct_sell = fees_pct_sell or DEFAULT_SELLING_FEES_PCT
    marginal_tax_rate = marginal_tax_rate or DEFAULT_MARGINAL_TAX_RATE
    maintenance_pct = maintenance_pct or DEFAULT_MAINTENANCE_PCT
    years = max(1, min(years, 30))

    # Convert percentages to decimals
    mr = mortgage_rate / 100.0
    hpi = hpi_momentum_pct / 100.0
    fees = fees_pct_sell / 100.0
    tax = marginal_tax_rate / 100.0
    maint = maintenance_pct / 100.0

    # ── Sell Path ────────────────────────────────────────────────────
    selling_costs = assessed_value * fees
    net_proceeds = assessed_value - outstanding_mortgage - selling_costs
    net_proceeds = max(net_proceeds, 0.0)  # can't go below zero

    # 3-year compound at 4% (post-tax, e.g. ISA)
    investment_return = DEFAULT_INVESTMENT_RETURN / 100.0
    compound_factor = (1 + investment_return) ** years - 1
    invested_return = net_proceeds * compound_factor

    sell_total = net_proceeds + invested_return

    # ── Let Path ─────────────────────────────────────────────────────
    annual_rent = average_local_rent * 12

    # Annual mortgage interest cost
    annual_mortgage = outstanding_mortgage * mr

    # Mortgage interest portion (roughly 80% of payment in early years)
    mortgage_interest_portion = annual_mortgage * 0.8

    # Tax on rental profit (rent minus mortgage interest)
    taxable_profit = max(annual_rent - mortgage_interest_portion, 0.0)
    annual_tax = taxable_profit * tax

    # Maintenance
    annual_maintenance = assessed_value * maint

    # Net annual yield
    net_annual_yield = annual_rent - annual_mortgage - annual_tax - annual_maintenance

    # Capital appreciation over N years
    capital_appreciation = assessed_value * ((1 + hpi) ** years - 1)

    let_total = max(net_annual_yield, 0.0) * years + max(capital_appreciation, 0.0)

    # ── Comparison ───────────────────────────────────────────────────
    difference = sell_total - let_total

    if difference > assessed_value * 0.05:  # > 5% of value
        recommendation = "sell"
    elif difference < -assessed_value * 0.05:
        recommendation = "let"
    else:
        recommendation = "neutral"

    return {
        "ok": True,
        "sell_path": {
            "net_proceeds_gbp": round(net_proceeds, 2),
            "investment_return_pct": DEFAULT_INVESTMENT_RETURN,
            "investment_return_gbp": round(invested_return, 2),
            f"{years}yr_total_gbp": round(sell_total, 2),
        },
        "let_path": {
            "annual_rent_gbp": round(annual_rent, 2),
            "annual_mortgage_cost_gbp": round(annual_mortgage, 2),
            "annual_tax_gbp": round(annual_tax, 2),
            "annual_maintenance_gbp": round(annual_maintenance, 2),
            "net_annual_yield_gbp": round(net_annual_yield, 2),
            "capital_appreciation_pct_yr": hpi_momentum_pct,
            f"{years}yr_capital_appreciation_gbp": round(capital_appreciation, 2),
            f"{years}yr_total_gbp": round(let_total, 2),
        },
        "difference_gbp": round(difference, 2),
        "difference_pct_of_value": round(difference / assessed_value * 100, 1) if assessed_value else 0,
        "recommendation": recommendation,
        "years": years,
        "inputs": {
            "assessed_value_gbp": round(assessed_value, 2),
            "outstanding_mortgage_gbp": round(outstanding_mortgage, 2),
            "average_local_rent_gbp_pcm": round(average_local_rent, 2),
            "mortgage_rate_pct": mortgage_rate,
            "hpi_momentum_pct": hpi_momentum_pct,
            "selling_fees_pct": fees_pct_sell,
            "marginal_tax_rate_pct": marginal_tax_rate,
            "maintenance_pct": maintenance_pct,
        },
    }
