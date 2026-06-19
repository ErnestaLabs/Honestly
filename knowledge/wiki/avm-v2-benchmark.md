# AVM v2 Benchmark Engine

## Status

Research-only. Transparent AVM v1 remains production until a candidate beats it in leakage-safe backtesting.

## Core principle

The current formula is a benchmark to beat, not a belief system to preserve.

## Implemented harness

Code:

- `avm_v2.py`
- `tools/avm_backtest.py`
- `tools/build_avm_fixture.py`
- `research/avm_v2_fixture_cases.json`
- `test_avm_v2.py`
- `research/AVM_V2_BENCHMARK_PLAN.md`

Reports:

- `out/avm_v2_backtest_latest.json`
- `out/avm_v2_backtest_latest.md`
- `out/avm_v2_backtest_engine.json`
- `out/avm_v2_backtest_engine.md`

## Candidate signals

### Exact-local sentiment

Formula:

```text
S_avg = sum(S_i * W_entity_i * exp(-lambda * age_days_i)) / sum(W_entity_i * exp(-lambda * age_days_i))
S_m = clamp(1 + S_avg * k, 0.90, 1.10)
```

Research uses:

- entity weights;
- exponential decay;
- minimum sample count;
- bounded multiplier;
- volatility as uncertainty driver.

### Candidate modes

- `baseline`
- `sentiment_multiplier`
- `sentiment_uncertainty`
- `sentiment_hybrid`

No mode is production-approved.

## Metrics

- MAPE
- MAE
- RMSE
- range coverage
- average interval width percentage
- confidence calibration proxy / ECE
- sentiment vs time-on-market correlation

## Promotion criteria

A candidate can be promoted only when it:

1. lowers MAPE versus Transparent AVM v1;
2. preserves or improves range coverage;
3. improves confidence calibration;
4. does not degrade sparse-data homes;
5. respects strict locality rules;
6. remains explainable in user-facing surfaces;
7. passes `python launch_gate.py`.

## Next research step

Build a leakage-safe historical dataset:

- train set;
- calibration set;
- untouched test set;
- HMLR target sale masked from evidence at prediction time;
- EPC and context facts as they would have been known pre-sale.

Only then can sentiment, multimodal condition inference, or conformal uncertainty be considered for production.
