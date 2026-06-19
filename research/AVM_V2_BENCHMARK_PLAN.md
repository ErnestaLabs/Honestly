# AVM v2 Benchmark Plan: From Transparent AVM Baseline to Benchmark Engine

## Objective

Build the last UK valuation engine users need by treating Transparent AVM v1 as the baseline to beat, not the final architecture.

## Non-negotiable rule

No candidate signal enters production until it beats AVM v1 on leakage-safe backtesting and keeps the glass-box delivery contract intact.

## Baseline

Transparent AVM v1 currently uses:

- HMLR Price Paid proof rows
- HMLR UK HPI subject-history fallback
- public EPC floor area/rating/type, including public-EPC cache/proxy
- Postcodes.io geography
- strict comparable pack: minimum 5, 0.5 mile ideal, 6 month ideal, 12 month rescue, 1 mile fallback only when needed
- condition-tier rules
- fixed formula/range logic

## Phase 0 - Evaluation harness

Implemented files:

- `avm_v2.py`
- `tools/avm_backtest.py`
- `tools/build_avm_fixture.py`
- `research/avm_v2_fixture_cases.json`
- `test_avm_v2.py`

Metrics:

- MAPE
- MAE
- RMSE
- range coverage
- average interval width percentage
- confidence calibration proxy / ECE
- sentiment vs time-on-market correlation

Outputs:

- `out/avm_v2_backtest_latest.json`
- `out/avm_v2_backtest_latest.md`

## Phase 1 - Exact-local sentiment experiments

Candidate sentiment features:

```text
S_avg = sum(S_i * W_entity_i * exp(-lambda * age_days_i)) / sum(W_entity_i * exp(-lambda * age_days_i))
S_m = clamp(1 + S_avg * k, 0.90, 1.10)
```

Current experimental candidates:

1. `baseline`
2. `sentiment_multiplier`
3. `sentiment_uncertainty`
4. `sentiment_hybrid`

Promotion is blocked until a larger leakage-safe dataset proves lift.

## Phase 2 - Dynamic condition inference

Research candidates:

- subject photos
- listing text
- EPC score/age
- planning/works records
- prior sale delta
- public-EPC evidence
- exact-local language patterns

Target output:

```json
{
  "condition_tier": "high",
  "confidence": 0.82,
  "evidence": ["photo kitchen quality", "EPC C", "recent works language"]
}
```

## Phase 3 - Native uncertainty

Research target architecture:

```text
features -> predictive model -> central value
features + calibration residuals -> conformal prediction interval -> low/high
SHAP/explanation layer -> user-facing glass box
```

Candidate models:

- XGBoost / Gradient Boosted Trees
- Random Forest
- Quantile Regression Forest
- conformal wrapper over best model

## Promotion criteria

A candidate can be considered for production only when it:

1. reduces MAPE versus AVM v1;
2. improves or preserves range coverage;
3. improves confidence calibration;
4. does not degrade sparse-data homes;
5. preserves locality discipline;
6. keeps user-facing output contract complete;
7. remains explainable in PDF/HTML/bot surfaces.

## Current status

Phase 0 is implemented as a deterministic harness. The included fixture is for harness validation, not production promotion. `tools/build_avm_fixture.py` can convert CSV/JSON historical rows into backtest fixtures and optionally snapshot current AVM v1 baselines. Next step is building a leakage-safe historical dataset from HMLR/EPC snapshots and rerunning the same harness at scale.
