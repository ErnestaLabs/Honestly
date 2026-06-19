#!/usr/bin/env python3
"""Experimental AVM v2 research utilities.

Production pricing remains in engine.py. This module is for research/backtesting only:
- transform exact-local sentiment posts into numeric features;
- apply candidate AVM v2 adjustments to a baseline valuation;
- score candidates against holdout targets.

Nothing in here is used by Telegram/PDF production unless a future backtest proves lift and
we explicitly promote a candidate.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import statistics
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

ENTITY_WEIGHTS = {
    "crime": 3.0,
    "safety": 3.0,
    "transport": 3.0,
    "station": 3.0,
    "school": 3.0,
    "catchment": 3.0,
    "regeneration": 3.0,
    "planning": 2.0,
    "noise": 2.0,
    "flood": 2.0,
    "gentrification": 1.5,
    "development": 1.5,
    "amenity": 0.5,
    "cafe": 0.5,
    "park": 0.5,
    "vibe": 0.5,
}
DEFAULT_ENTITY_WEIGHT = 1.0
POSITIVE_WORDS = {
    "good", "great", "excellent", "safe", "quiet", "fast", "improving", "popular",
    "desirable", "outstanding", "green", "walkable", "regeneration", "upgraded",
    "renovated", "premium", "demand", "competitive", "convenient", "beautiful",
}
NEGATIVE_WORDS = {
    "bad", "unsafe", "crime", "noisy", "rough", "overpriced", "slow", "stuck",
    "flood", "pollution", "dirty", "anti-social", "dangerous", "traffic", "railway",
    "industrial", "problem", "avoid", "down", "falling", "weak", "risky",
}


@dataclass
class SentimentConfig:
    min_posts: int = 10
    decay_lambda: float = 0.05
    multiplier_k: float = 0.10
    multiplier_low: float = 0.90
    multiplier_high: float = 1.10
    max_promoted_adjustment: float = 0.10


def _parse_date(value: Any, today: Optional[_dt.date] = None) -> Optional[_dt.date]:
    if value in (None, ""):
        return None
    if isinstance(value, _dt.date):
        return value
    s = str(value)[:10]
    try:
        return _dt.date.fromisoformat(s)
    except Exception:
        return None


def _post_age_days(post: Dict[str, Any], today: Optional[_dt.date] = None) -> int:
    today = today or _dt.date.today()
    d = _parse_date(post.get("created_at") or post.get("date"), today=today)
    if not d:
        return 30
    return max(0, (today - d).days)


def _lexicon_sentiment(text: str) -> float:
    """Tiny deterministic polarity scorer for benchmark reproducibility.

    Real research can swap this for a model scorer; keeping this dependency-free lets the
    harness run in CI and compare candidate math.
    """
    import re
    toks = re.findall(r"[a-z][a-z\-']+", (text or "").lower())
    if not toks:
        return 0.0
    pos = sum(1 for t in toks if t in POSITIVE_WORDS)
    neg = sum(1 for t in toks if t in NEGATIVE_WORDS)
    if pos == neg == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / max(1, pos + neg)))


def _entity_weight(post: Dict[str, Any]) -> float:
    ents = post.get("entities") or post.get("topics") or []
    if isinstance(ents, str):
        ents = [ents]
    weights = [ENTITY_WEIGHTS.get(str(e).strip().lower(), DEFAULT_ENTITY_WEIGHT) for e in ents if str(e).strip()]
    return max(weights) if weights else DEFAULT_ENTITY_WEIGHT


def sentiment_features(posts: Iterable[Dict[str, Any]], *, config: SentimentConfig | None = None,
                       today: Optional[_dt.date] = None) -> Dict[str, Any]:
    """Return weighted exact-local sentiment features.

    Output is stable and bounded. If there are too few relevant posts, multiplier is neutral
    and status says insufficient_sample.
    """
    cfg = config or SentimentConfig()
    today = today or _dt.date.today()
    rows = []
    for p in posts or []:
        if not isinstance(p, dict):
            continue
        text = " ".join(str(p.get(k) or "") for k in ("title", "quote", "body", "text", "selftext"))
        polarity = p.get("sentiment")
        try:
            polarity = float(polarity)
        except Exception:
            polarity = _lexicon_sentiment(text)
        polarity = max(-1.0, min(1.0, polarity))
        w = _entity_weight(p)
        age = _post_age_days(p, today=today)
        decay = math.exp(-cfg.decay_lambda * age)
        rows.append({"sentiment": polarity, "entity_weight": w, "age_days": age, "decay": decay,
                     "weighted": polarity * w * decay, "denom": w * decay})
    n = len(rows)
    denom = sum(r["denom"] for r in rows)
    avg = (sum(r["weighted"] for r in rows) / denom) if denom else 0.0
    if n < cfg.min_posts:
        avg_for_multiplier = 0.0
        status = "insufficient_sample_neutral"
    else:
        avg_for_multiplier = avg
        status = "usable"
    mult = 1.0 + (avg_for_multiplier * cfg.multiplier_k)
    mult = max(cfg.multiplier_low, min(cfg.multiplier_high, mult))
    vals = [r["sentiment"] for r in rows]
    volatility = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    return {
        "status": status,
        "post_count": n,
        "min_posts": cfg.min_posts,
        "s_avg": round(avg, 6),
        "s_avg_for_multiplier": round(avg_for_multiplier, 6),
        "sentiment_multiplier": round(mult, 6),
        "sentiment_volatility": round(volatility, 6),
        "weighted_denominator": round(denom, 6),
        "rows": rows,
    }


def _round_to(n: float, step: int = 5000) -> int:
    return int(round(float(n) / step) * step)


def candidate_from_baseline(baseline: Dict[str, Any], sentiment: Dict[str, Any], *, mode: str) -> Dict[str, Any]:
    """Apply an experimental AVM v2 candidate transform.

    Modes:
    - sentiment_multiplier: central/range multiplied by bounded sentiment multiplier.
    - sentiment_uncertainty: central unchanged; range widens with sentiment volatility.
    - sentiment_hybrid: small central move plus volatility range adjustment.
    """
    low = float(baseline["low"]); central = float(baseline["central"]); high = float(baseline["high"])
    sm = float(sentiment.get("sentiment_multiplier") or 1.0)
    vol = float(sentiment.get("sentiment_volatility") or 0.0)
    if mode == "baseline":
        return {"model": "baseline", "low": int(low), "central": int(central), "high": int(high), "sentiment_used": False}
    if mode == "sentiment_multiplier":
        return {"model": mode, "low": _round_to(low * sm), "central": _round_to(central * sm),
                "high": _round_to(high * sm), "sentiment_used": sentiment.get("status") == "usable"}
    if mode == "sentiment_uncertainty":
        width = max(high - central, central - low)
        widen = 1.0 + min(0.35, vol * 0.35)
        return {"model": mode, "low": _round_to(central - width * widen), "central": int(central),
                "high": _round_to(central + width * widen), "sentiment_used": sentiment.get("status") == "usable"}
    if mode == "sentiment_hybrid":
        central2 = central * (1.0 + ((sm - 1.0) * 0.5))
        width = max(high - central, central - low)
        widen = 1.0 + min(0.30, vol * 0.30)
        return {"model": mode, "low": _round_to(central2 - width * widen), "central": _round_to(central2),
                "high": _round_to(central2 + width * widen), "sentiment_used": sentiment.get("status") == "usable"}
    raise ValueError(f"unknown candidate mode: {mode}")


def _safe_pct_err(pred: float, actual: float) -> Optional[float]:
    try:
        actual = float(actual); pred = float(pred)
        if actual <= 0:
            return None
        return abs(pred - actual) / actual * 100.0
    except Exception:
        return None


def _corr(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy)


def score_predictions(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    errs = []
    abs_errs = []
    sq_errs = []
    covered = []
    widths = []
    confs = []
    accurate = []
    sent = []
    tom = []
    for r in rows:
        target = r.get("target_price")
        pred = (r.get("prediction") or {}).get("central")
        pe = _safe_pct_err(pred, target)
        if pe is not None:
            errs.append(pe)
            abs_errs.append(abs(float(pred) - float(target)))
            sq_errs.append((float(pred) - float(target)) ** 2)
            p = r.get("prediction") or {}
            low, high = p.get("low"), p.get("high")
            if low is not None and high is not None:
                covered.append(1 if float(low) <= float(target) <= float(high) else 0)
                widths.append((float(high) - float(low)) / float(target) * 100.0)
            c = r.get("confidence_score")
            if c is not None:
                confs.append(float(c) / 100.0)
                accurate.append(1.0 if pe <= 10.0 else 0.0)
        sf = r.get("sentiment") or {}
        if r.get("time_on_market_days") is not None and sf.get("s_avg") is not None:
            sent.append(float(sf.get("s_avg") or 0.0))
            tom.append(float(r["time_on_market_days"]))
    ece = None
    if confs:
        ece = sum(abs(c - a) for c, a in zip(confs, accurate)) / len(confs)
    return {
        "n": len(rows),
        "scored_n": len(errs),
        "mape": round(statistics.mean(errs), 4) if errs else None,
        "mae": round(statistics.mean(abs_errs), 2) if abs_errs else None,
        "rmse": round(math.sqrt(statistics.mean(sq_errs)), 2) if sq_errs else None,
        "coverage": round(sum(covered) / len(covered), 4) if covered else None,
        "avg_interval_width_pct": round(statistics.mean(widths), 4) if widths else None,
        "ece_10pct_accuracy": round(ece, 4) if ece is not None else None,
        "sentiment_time_on_market_corr": round(_corr(sent, tom), 4) if _corr(sent, tom) is not None else None,
    }


def comparison_verdict(metrics: Dict[str, Dict[str, Any]], baseline_name: str = "baseline") -> Dict[str, Any]:
    base = metrics.get(baseline_name) or {}
    verdicts = {}
    for name, m in metrics.items():
        if name == baseline_name:
            continue
        delta = None
        if base.get("mape") is not None and m.get("mape") is not None:
            delta = round(float(m["mape"]) - float(base["mape"]), 4)
        verdicts[name] = {
            "mape_delta_vs_baseline": delta,
            "beats_baseline_on_mape": (delta is not None and delta < 0),
            "promotion_candidate": False,
            "reason": "Research-only: promotion requires larger leakage-safe backtest and calibration split.",
        }
    return verdicts


def load_cases(path: str) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("cases") or []
    return data if isinstance(data, list) else []
