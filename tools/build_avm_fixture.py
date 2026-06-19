#!/usr/bin/env python3
"""Build AVM backtest fixtures from historical transaction rows.

Input can be CSV or JSON. Minimum fields:
  case_id,address,target_price
Optional fields:
  finish,time_on_market_days,low,central,high,confidence_score,sold_date

Use --with-engine-baseline to snapshot current AVM v1 outputs for each address. For true
promotion-grade research, run this against a leakage-safe historical cut where the target
sale is masked from evidence available to the valuation engine.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_rows(path):
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with p.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("cases") or data.get("rows") or []
    return data if isinstance(data, list) else []


def _num(v):
    if v in (None, ""):
        return None
    try:
        return int(float(str(v).replace(",", "")))
    except Exception:
        return None


def _engine_baseline(address, finish):
    import engine
    r = engine.value(address, finish=finish or "average")
    d = engine.summary(r, "vendor", tier="pro")
    return {
        "low": d["low"],
        "central": d["central"],
        "high": d["high"],
        "confidence_score": (d.get("confidence") or {}).get("score"),
    }


def build(rows, *, with_engine_baseline=False):
    cases = []
    for i, row in enumerate(rows, 1):
        address = (row.get("address") or row.get("Address") or "").strip()
        target = _num(row.get("target_price") or row.get("sold_price") or row.get("price"))
        if not address or not target:
            continue
        finish = (row.get("finish") or "average").strip() or "average"
        case = {
            "case_id": (row.get("case_id") or row.get("id") or f"case_{i:04d}").strip(),
            "address": address,
            "finish": finish,
            "target_price": target,
            "sentiment": {"posts": []},
        }
        tom = _num(row.get("time_on_market_days") or row.get("tom_days"))
        if tom is not None:
            case["time_on_market_days"] = tom
        if row.get("sold_date"):
            case["sold_date"] = row.get("sold_date")
        if with_engine_baseline:
            try:
                case["baseline"] = _engine_baseline(address, finish)
            except BaseException as e:
                case["baseline_error"] = repr(e)
        else:
            low, central, high = _num(row.get("low")), _num(row.get("central")), _num(row.get("high"))
            if low and central and high:
                case["baseline"] = {"low": low, "central": central, "high": high}
                conf = _num(row.get("confidence_score"))
                if conf is not None:
                    case["baseline"]["confidence_score"] = conf
        cases.append(case)
    return {
        "schema": "honestly_avm_v2_fixture_v1",
        "leakage_warning": "Promotion-grade research must mask each target sale from valuation evidence and preserve train/calibration/test splits.",
        "cases": cases,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--with-engine-baseline", action="store_true")
    args = ap.parse_args(argv)
    fixture = build(_load_rows(args.input), with_engine_baseline=args.with_engine_baseline)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(fixture, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ok": True, "out": args.out, "cases": len(fixture["cases"])}, indent=2))


if __name__ == "__main__":
    main()
