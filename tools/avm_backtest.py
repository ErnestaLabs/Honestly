#!/usr/bin/env python3
"""Run AVM v2 candidate backtests.

Examples:
  python tools/avm_backtest.py --fixture research/avm_v2_fixture_cases.json --no-engine
  python tools/avm_backtest.py --fixture research/avm_v2_fixture_cases.json --out out/avm_v2_backtest.json --markdown out/avm_v2_backtest.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import avm_v2


def _baseline_from_engine(case):
    import engine
    r = engine.value(case["address"], finish=case.get("finish") or "average")
    d = engine.summary(r, case.get("audience") or "vendor", tier="pro")
    return {
        "low": d["low"], "central": d["central"], "high": d["high"],
        "confidence_score": (d.get("confidence") or {}).get("score"),
        "confidence_grade": (d.get("confidence") or {}).get("grade"),
        "strict_comparable_count": (d.get("valuation_formula") or {}).get("evidence", {}).get("strict_comparable_count"),
        "floor_area_source": d.get("floor_area_source"),
        "sqm": d.get("sqm"),
    }


def _baseline(case, use_engine=True):
    if use_engine:
        try:
            return _baseline_from_engine(case)
        except BaseException as e:
            b = dict(case.get("baseline") or {})
            b["engine_error"] = repr(e)
            return b
    return dict(case.get("baseline") or {})


def run(fixture, *, use_engine=True):
    cases = avm_v2.load_cases(fixture)
    modes = ["baseline", "sentiment_multiplier", "sentiment_uncertainty", "sentiment_hybrid"]
    rows_by_mode = {m: [] for m in modes}
    detailed = []
    for case in cases:
        base = _baseline(case, use_engine=use_engine)
        if not all(k in base for k in ("low", "central", "high")):
            detailed.append({"case_id": case.get("case_id"), "address": case.get("address"), "ok": False, "error": "no baseline"})
            continue
        sent = avm_v2.sentiment_features((case.get("sentiment") or {}).get("posts") or [], today=None)
        case_detail = {
            "case_id": case.get("case_id"),
            "address": case.get("address"),
            "target_price": case.get("target_price"),
            "time_on_market_days": case.get("time_on_market_days"),
            "baseline": base,
            "sentiment": {k: v for k, v in sent.items() if k != "rows"},
            "predictions": {},
        }
        for mode in modes:
            pred = avm_v2.candidate_from_baseline(base, sent, mode=mode)
            row = {
                "case_id": case.get("case_id"),
                "address": case.get("address"),
                "target_price": case.get("target_price"),
                "time_on_market_days": case.get("time_on_market_days"),
                "confidence_score": base.get("confidence_score"),
                "sentiment": sent,
                "prediction": pred,
            }
            rows_by_mode[mode].append(row)
            case_detail["predictions"][mode] = pred
        detailed.append(case_detail)
    metrics = {m: avm_v2.score_predictions(rows) for m, rows in rows_by_mode.items()}
    return {
        "schema": "honestly_avm_v2_backtest_v1",
        "fixture": str(fixture),
        "engine_used": bool(use_engine),
        "case_count": len(cases),
        "metrics": metrics,
        "verdicts": avm_v2.comparison_verdict(metrics),
        "promotion_rule": "No candidate promotes without leakage-safe train/calibration/test backtest beating AVM v1 on MAPE, coverage and calibration.",
        "cases": detailed,
    }


def write_markdown(result, path):
    lines = [
        "# AVM v2 Backtest Report",
        "",
        f"Fixture: `{result['fixture']}`",
        f"Engine used: `{result['engine_used']}`",
        f"Cases: `{result['case_count']}`",
        "",
        "## Metrics",
        "",
        "| model | n | MAPE | MAE | RMSE | coverage | avg interval width % | ECE | TOM corr |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, m in result.get("metrics", {}).items():
        lines.append("| {name} | {n} | {mape} | {mae} | {rmse} | {coverage} | {width} | {ece} | {corr} |".format(
            name=name, n=m.get("scored_n"), mape=m.get("mape"), mae=m.get("mae"), rmse=m.get("rmse"),
            coverage=m.get("coverage"), width=m.get("avg_interval_width_pct"),
            ece=m.get("ece_10pct_accuracy"), corr=m.get("sentiment_time_on_market_corr")))
    lines += ["", "## Verdicts", ""]
    for name, v in result.get("verdicts", {}).items():
        lines.append(f"- **{name}**: MAPE delta vs baseline `{v.get('mape_delta_vs_baseline')}`; promotion `{v.get('promotion_candidate')}`. {v.get('reason')}")
    lines += ["", "## Case details", ""]
    for c in result.get("cases", []):
        if not c.get("predictions"):
            lines.append(f"- `{c.get('case_id')}` {c.get('address')}: skipped ({c.get('error')})")
            continue
        sent = c.get("sentiment") or {}
        lines.append(f"- `{c.get('case_id')}` {c.get('address')}: target £{c.get('target_price'):,}; sentiment `{sent.get('status')}` S_avg `{sent.get('s_avg')}` multiplier `{sent.get('sentiment_multiplier')}`")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", default=str(ROOT / "research" / "avm_v2_fixture_cases.json"))
    ap.add_argument("--out", default=str(ROOT / "out" / "avm_v2_backtest_latest.json"))
    ap.add_argument("--markdown", default=str(ROOT / "out" / "avm_v2_backtest_latest.md"))
    ap.add_argument("--no-engine", action="store_true", help="Use fixture baseline predictions instead of calling engine.value")
    args = ap.parse_args(argv)
    result = run(args.fixture, use_engine=not args.no_engine)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(result, args.markdown)
    print(json.dumps({"ok": True, "out": args.out, "markdown": args.markdown, "metrics": result["metrics"], "verdicts": result["verdicts"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
