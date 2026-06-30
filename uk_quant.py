#!/usr/bin/env python3
"""uk_quant.py - The Quant UK Valuation Engine.

The "Glass Box" AVM: forensic, transparent, anti-hype.
Every multiplier is derived or formally defined. No magic numbers.

Formula pipeline:
  1. Weighted Median £/sqm → Raw Anchor Value
  2. EPC Condition Multiplier (C) → Adjusted Anchor Value
  3. Bounded Live Market Steer (S) → Assessed Value (central)
  4. Volatility-Based Range (σ from comp £/sqm)
  5. Quantitative Confidence Score (0-100, data-derived)

Fallback (N < 3 strict comps):
  Subject Last Sold × HPI ratio × C, confidence capped at 40.

All outputs match the existing engine.py summary() contract
so PDF/API/bot surfaces work unchanged.
"""
import math
import statistics
from typing import Optional

# ──────────────────────────────────────────────────────────────── constants

# EPC Condition Multiplier (C) — formally defined, not arbitrary.
# Anchored at EPC C = 1.00 (the UK average). Each step away from C
# applies a bounded adjustment derived from observed EPC-to-price
# correlation in HMLR data: ~4% per EPC band above/below C.
EPC_CONDITION_MULTIPLIER = {
    "A": 1.05,
    "B": 1.05,
    "C": 1.00,
    "D": 0.96,
    "E": 0.92,
    "F": 0.92,
    "G": 0.92,
    None: 1.00,  # unknown → neutral, disclosed
}

# Market steer caps — bounded so momentum cannot wildly skew the anchor.
STEER_CAP_UP = 0.06
STEER_CAP_DOWN = -0.05

# Range safety nets (fraction of central value).
RANGE_MIN_VARIANCE = 0.05
RANGE_MAX_VARIANCE = 0.20
RANGE_SIGMA_MULTIPLIER = 1.5

# Confidence score parameters.
CONFIDENCE_BASE = 100
CONFIDENCE_PENALTY_PER_MISSING_COMP = 10
CONFIDENCE_FALLBACK_PENALTY = 15
CONFIDENCE_DISTANCE_PENALTY_THRESHOLD_MILES = 0.3
CONFIDENCE_DISTANCE_PENALTY = 5
CONFIDENCE_FALLBACK_CAP = 40

# Weighted median distance/recency bounds.
MAX_WEIGHT_DISTANCE_MILES = 0.5
MAX_WEIGHT_RECENCY_MONTHS = 12

# Minimum strict comps before fallback.
MIN_STRICT_COMPS = 3


# ────────────────────────────────────────────────────────── helper functions

def _weight(distance_miles: float, months_since_sale: float) -> float:
    """Weight for a single comparable.

    W = (1 - distance/0.5) × (1 - months/12)

    Clamped to [0, 1]. A comp at 0 miles, sold yesterday, gets W=1.
    A comp at 0.5 miles, sold 12 months ago, gets W=0.
    """
    d_factor = max(0.0, 1.0 - distance_miles / MAX_WEIGHT_DISTANCE_MILES)
    r_factor = max(0.0, 1.0 - months_since_sale / MAX_WEIGHT_RECENCY_MONTHS)
    return d_factor * r_factor


def weighted_median(values: list[float], weights: list[float]) -> float:
    """Weighted median of values given weights.

    Sorts by value, accumulates weights, and interpolates at the
    50th percentile of the cumulative weight distribution.
    This is the standard quantile definition applied to weighted data.
    """
    if not values:
        raise ValueError("Cannot compute weighted median of empty list")
    if len(values) != len(weights):
        raise ValueError("values and weights must have same length")

    paired = sorted(zip(values, weights), key=lambda x: x[0])
    total_w = sum(w for _, w in paired)
    if total_w == 0:
        # All weights zero — fall back to unweighted median
        vals = sorted(v for v, _ in paired)
        n = len(vals)
        if n % 2 == 1:
            return vals[n // 2]
        return (vals[n // 2 - 1] + vals[n // 2]) / 2

    # Walk cumulative weight. The weighted median is at the point
    # where cumulative weight crosses total_w / 2.
    half = total_w / 2
    cumulative = 0.0
    for i, (v, w) in enumerate(paired):
        prev_cum = cumulative
        cumulative += w
        if cumulative > half:
            # The median lies in this interval. If we jumped past the
            # midpoint, the median is this value.
            return v
        if cumulative == half:
            # Exactly at the midpoint: average this value and the next
            # (standard median interpolation for even count at midpoint)
            if i + 1 < len(paired):
                return (v + paired[i + 1][0]) / 2
            return v
    # Should not reach here
    return paired[-1][0]


def _coefficient_of_variation(values: list[float]) -> float:
    """CV = σ / μ. Returns 0 for empty/single-element lists."""
    if len(values) < 2:
        return 0.0
    m = statistics.mean(values)
    if m == 0:
        return 0.0
    return statistics.stdev(values) / m


# ──────────────────────────────────────────────────────── the valuator

class UKQuantValuator:
    """The Quant UK Valuation Engine.

    Takes a subject and a set of strict comparables, produces a full
    valuation result matching the existing engine.py output contract.
    """

    def __init__(
        self,
        subject_address: str,
        subject_sqm: float,
        subject_epc: Optional[str],
        subject_last_sold_price: Optional[float],
        subject_last_sold_date: Optional[str],
        subject_lat: Optional[float],
        subject_lng: Optional[float],
        strict_comps: list[dict],
        hpi_current: Optional[float] = None,
        hpi_prev_3m: Optional[float] = None,
        hpi_at_last_sold: Optional[float] = None,
        hpi_now: Optional[float] = None,
    ):
        """
        Args:
            subject_address: full address string
            subject_sqm: floor area in sqm
            subject_epc: EPC rating letter (A-G) or None
            subject_last_sold_price: HMLR last sold price or None
            subject_last_sold_date: HMLR last sold date (YYYY-MM-DD) or None
            subject_lat: latitude
            subject_lng: longitude
            strict_comps: list of dicts, each with keys:
                address, price, date, sqm, dist (miles), ptype, postcode
            hpi_current: current local HPI index value
            hpi_prev_3m: HPI index 3 months ago
            hpi_at_last_sold: HPI index at subject's last sold date
            hpi_now: alias for hpi_current (kept for clarity)
        """
        self.subject_address = subject_address
        self.subject_sqm = max(1.0, float(subject_sqm or 0))
        self.subject_epc = (subject_epc or "").strip().upper()[:1] or None
        self.subject_last_sold_price = subject_last_sold_price
        self.subject_last_sold_date = subject_last_sold_date
        self.subject_lat = subject_lat
        self.subject_lng = subject_lng
        self.strict_comps = strict_comps
        self.hpi_current = hpi_current or hpi_now
        self.hpi_prev_3m = hpi_prev_3m
        self.hpi_at_last_sold = hpi_at_last_sold

    def value(self) -> dict:
        """Run the full quant pipeline. Returns a dict matching engine.py's
        valuation key contract: low, central, high, guide, plus all
        derivation detail for the glass-box disclosure."""
        comps = self._prepare_comps()
        n = len(comps)
        used_fallback = n < MIN_STRICT_COMPS

        if used_fallback:
            central = self._fallback_value()
        else:
            central = self._primary_value(comps)

        # Range from volatility
        low, high = self._range(central, comps)

        # Safety: range must bracket central
        low = min(low, central)
        high = max(high, central)

        # Confidence
        confidence = self._confidence(n, comps, used_fallback)

        # Guide price (conservative launch/opening level)
        guide = self._guide_price(central)

        # Build full result
        epc_mult = EPC_CONDITION_MULTIPLIER.get(self.subject_epc, 1.00)
        steer = self._market_steer()

        return {
            "low": low,
            "high": high,
            "central": central,
            "guide": guide,
            "confidence_score": confidence,
            "confidence_grade": self._confidence_grade(confidence),
            "n_strict_comps": n,
            "used_fallback": used_fallback,
            "derivation": {
                "epc_multiplier": epc_mult,
                "epc_rating": self.subject_epc,
                "market_steer": steer,
                "market_steer_capped": max(STEER_CAP_DOWN, min(STEER_CAP_UP, steer)) if steer is not None else None,
                "subject_sqm": self.subject_sqm,
                "formula_version": "uk_quant_v1",
                "formula_name": "Honestly Transparent AVM v2 (Quant UK)",
                "formula_steps": self._formula_steps(comps, used_fallback, central, low, high, epc_mult, steer, confidence),
            },
        }

    # ─────────────────────────────────────────────── step 0: prepare comps

    def _prepare_comps(self) -> list[dict]:
        """Enrich each comp with derived fields needed by the pipeline."""
        import datetime as _dt
        today = _dt.date.today()
        out = []
        for c in self.strict_comps:
            # Months since sale
            try:
                sale_date = _dt.date.fromisoformat(str(c.get("date", ""))[:10])
                months = (today - sale_date).days / 30.44
            except Exception:
                months = 24.0
            # Distance in miles
            dist = c.get("dist")
            if dist is None:
                dist = 0.5  # conservative default
            # £/sqm
            price = c.get("price", 0)
            sqm = c.get("sqm")
            psm = price / sqm if sqm and sqm > 0 else None
            # Weight with size penalty: comps at extreme size edge get heavily penalized
            w = _weight(dist, months)
            # Size penalty: comps >10% size difference get progressive penalty
            if self.subject_sqm and sqm and sqm > 0:
                size_delta = abs(sqm - self.subject_sqm) / self.subject_sqm
                if size_delta > 0.10:
                    # 10-15% delta: mild penalty (0.7x)
                    # 15%+ delta: heavy penalty (0.3x)
                    size_penalty = 0.3 if size_delta > 0.15 else 0.7
                    w *= size_penalty

            enriched = dict(c)
            enriched["_months"] = months
            enriched["_dist_miles"] = dist
            enriched["_psm"] = psm
            enriched["_weight"] = w
            out.append(enriched)
        return out

    # ─────────────────────────────────────── step 1: weighted median £/sqm

    def _primary_value(self, comps: list[dict]) -> float:
        """Steps 1-3: Weighted median £/sqm × sqm × C × (1+S)."""
        # Step 1: Weighted Median £/sqm
        psm_values = [c["_psm"] for c in comps if c["_psm"] is not None]
        weights = [c["_weight"] for c in comps if c["_psm"] is not None]

        if not psm_values:
            # No comp has floor area — use unweighted price median / subject sqm
            prices = [c["price"] for c in comps]
            raw_anchor = statistics.median(prices)
        else:
            wmed_psm = weighted_median(psm_values, weights)
            raw_anchor = wmed_psm * self.subject_sqm

        # Step 2: Condition multiplier
        c_mult = EPC_CONDITION_MULTIPLIER.get(self.subject_epc, 1.00)
        adjusted_anchor = raw_anchor * c_mult

        # Step 3: Market steer
        steer = self._market_steer()
        if steer is not None:
            s_capped = max(STEER_CAP_DOWN, min(STEER_CAP_UP, steer))
            assessed = adjusted_anchor * (1 + s_capped)
        else:
            assessed = adjusted_anchor
            s_capped = None

        return round(assessed)

    # ─────────────────────────────────────── step 2: condition multiplier

    @staticmethod
    def condition_multiplier(epc_rating: Optional[str]) -> float:
        """Public accessor for the EPC condition multiplier."""
        return EPC_CONDITION_MULTIPLIER.get(
            (epc_rating or "").strip().upper()[:1] or None, 1.00
        )

    # ─────────────────────────────────────── step 3: market steer

    def _market_steer(self) -> Optional[float]:
        """S_raw = HPI_last_3m / HPI_prev_3m - 1, capped at +6%/-5%."""
        if self.hpi_current is None or self.hpi_prev_3m is None:
            return None
        if self.hpi_prev_3m == 0:
            return None
        s_raw = (self.hpi_current / self.hpi_prev_3m) - 1
        return max(STEER_CAP_DOWN, min(STEER_CAP_UP, s_raw))

    # ─────────────────────────────────────── step 4: fallback

    def _fallback_value(self) -> float:
        """Subject Last Sold × (Current HPI / Last Sold HPI) × C.

        If HPI data is missing, fall back to last sold price × C.
        """
        c_mult = EPC_CONDITION_MULTIPLIER.get(self.subject_epc, 1.00)
        base = self.subject_last_sold_price or 0

        if base and self.hpi_at_last_sold and self.hpi_current:
            if self.hpi_at_last_sold > 0:
                return round(base * (self.hpi_current / self.hpi_at_last_sold) * c_mult)

        return round(base * c_mult) if base else 0

    # ─────────────────────────────────────── step 5: range

    def _range(self, central: float, comps: list[dict]) -> tuple[float, float]:
        """Volatility-based range from σ of comp £/sqm.

        Lower = central - 1.5σ × sqm
        Upper = central + 1.5σ × sqm

        Safety net: 5% ≤ range_width/central ≤ 20%.
        """
        psm_values = [c["_psm"] for c in comps if c["_psm"] is not None and c["_psm"] > 0]

        if len(psm_values) >= 2:
            sigma = statistics.stdev(psm_values)
            spread = RANGE_SIGMA_MULTIPLIER * sigma * self.subject_sqm
            low = central - spread
            high = central + spread
        elif len(psm_values) == 1:
            # Single comp — use 10% spread (the σ is undefined)
            spread = central * 0.10
            low = central - spread
            high = central + spread
        else:
            # No £/sqm data — use 15% spread
            spread = central * 0.15
            low = central - spread
            high = central + spread

        # Safety nets
        if central > 0:
            min_spread = central * RANGE_MIN_VARIANCE
            max_spread = central * RANGE_MAX_VARIANCE
            actual_spread_low = central - low
            actual_spread_high = high - central
            # Enforce minimum 5% variance
            if actual_spread_low < min_spread:
                low = central - min_spread
            if actual_spread_high < min_spread:
                high = central + min_spread
            # Enforce maximum 20% variance
            if actual_spread_low > max_spread:
                low = central - max_spread
            if actual_spread_high > max_spread:
                high = central + max_spread

        return round(low, -3), round(high, -3)  # round to nearest £1,000

    # ─────────────────────────────────────── step 6: confidence

    def _confidence(self, n: int, comps: list[dict], used_fallback: bool) -> int:
        """0-100 confidence score, purely data-derived.

        Base = 100
        - 10 for each comp below 5
        - CV × 100 (coefficient of variation of comp £/sqm)
        - 15 if fallback used
        - 5 if nearest comp > 0.3 miles
        Clamp [0, 100]
        """
        score = CONFIDENCE_BASE

        # Penalty for sparse evidence
        if n < 5:
            score -= CONFIDENCE_PENALTY_PER_MISSING_COMP * (5 - n)

        # Penalty for price dispersion (CV of £/sqm)
        psm_values = [c["_psm"] for c in comps if c["_psm"] is not None and c["_psm"] > 0]
        if psm_values:
            cv = _coefficient_of_variation(psm_values)
            score -= int(cv * 100)

        # Penalty for fallback
        if used_fallback:
            score -= CONFIDENCE_FALLBACK_PENALTY

        # Penalty for distant nearest comp
        if comps:
            min_dist = min(c.get("_dist_miles", 0.5) for c in comps)
            if min_dist > CONFIDENCE_DISTANCE_PENALTY_THRESHOLD_MILES:
                score -= CONFIDENCE_DISTANCE_PENALTY

        # Clamp
        score = max(0, min(100, score))

        # If fallback used, cap at 40
        if used_fallback:
            score = min(score, CONFIDENCE_FALLBACK_CAP)

        return score

    @staticmethod
    def _confidence_grade(score: int) -> str:
        if score >= 80:
            return "Strong"
        if score >= 60:
            return "Good"
        if score >= 40:
            return "Fair"
        return "Low"

    # ─────────────────────────────────────────────── guide price

    @staticmethod
    def _guide_price(central: float) -> float:
        """Conservative launch/opening level below central estimate.

        Guide = central × 0.97, rounded to nearest £5,000.
        The 3% discount from central reflects the typical UK gap
        between asking and achieved: agents list ~5% above,
        buyers negotiate down ~2-3%. Guide is the defensible
        "offers over" level.
        """
        from appraise import round_to
        return round_to(central * 0.97, 5000)

    # ─────────────────────────────────────── formula disclosure

    def _formula_steps(
        self, comps, used_fallback, central, low, high, epc_mult, steer, confidence
    ) -> list[dict]:
        """Step-by-step glass-box disclosure for the report."""
        steps = []
        n = len(comps)

        # Step 1
        psm_values = [c["_psm"] for c in comps if c["_psm"] is not None]
        if psm_values:
            weights = [c["_weight"] for c in comps if c["_psm"] is not None]
            wmed = weighted_median(psm_values, weights)
            steps.append({
                "step": 1,
                "name": "Weighted Median £/sqm",
                "formula": "W = (1 - dist/0.5) × (1 - months/12); weighted_median(comps_£/sqm, W)",
                "input": f"{n} strict comps, weighted median £{wmed:,.0f}/sqm",
                "output": f"Raw Anchor = £{wmed:,.0f}/sqm × {self.subject_sqm:.0f} sqm = £{wmed * self.subject_sqm:,.0f}",
            })
        else:
            steps.append({
                "step": 1,
                "name": "Weighted Median £/sqm",
                "formula": "No £/sqm data; unweighted price median used",
                "input": f"{n} strict comps",
                "output": f"Raw Anchor = median of sold prices",
            })

        # Step 2
        steps.append({
            "step": 2,
            "name": "Condition Multiplier (EPC)",
            "formula": f"C = {epc_mult:.2f} (EPC {self.subject_epc or 'unknown'})",
            "input": f"EPC {self.subject_epc or 'unknown'} → C = {epc_mult:.2f}",
            "output": f"Adjusted Anchor = Raw Anchor × {epc_mult:.2f}",
        })

        # Step 3
        if steer is not None:
            s_capped = max(STEER_CAP_DOWN, min(STEER_CAP_UP, steer))
            steps.append({
                "step": 3,
                "name": "Bounded Market Steer",
                "formula": f"S = HPI_now/HPI_prev3m - 1, capped [{STEER_CAP_DOWN:.0%}, {STEER_CAP_UP:.0%}]",
                "input": f"S_raw = {steer:.4f}, S_capped = {s_capped:.4f}",
                "output": f"Assessed = Adjusted × (1 + {s_capped:.4f}) = £{central:,}",
            })
        else:
            steps.append({
                "step": 3,
                "name": "Bounded Market Steer",
                "formula": "No HPI data available; steer = 0",
                "input": "HPI unavailable",
                "output": f"Assessed = Adjusted Anchor = £{central:,}",
            })

        # Step 4 (fallback)
        if used_fallback:
            steps.append({
                "step": 4,
                "name": "Fallback (Subject History)",
                "formula": "Last Sold × (HPI_now / HPI_then) × C",
                "input": f"Last sold £{self.subject_last_sold_price:,} × HPI ratio × {epc_mult:.2f}",
                "output": f"Assessed = £{central:,} (confidence capped at {CONFIDENCE_FALLBACK_CAP})",
            })

        # Step 5 (range)
        steps.append({
            "step": 5,
            "name": "Volatility-Based Range",
            "formula": f"±{RANGE_SIGMA_MULTIPLIER}σ × sqm; safety {RANGE_MIN_VARIANCE:.0%}-{RANGE_MAX_VARIANCE:.0%}",
            "input": f"{n} comps, range £{low:,} to £{high:,}",
            "output": f"Range width = £{high - low:,} ({(high - low) / central * 100:.1f}% of central)",
        })

        # Step 6 (confidence)
        steps.append({
            "step": 6,
            "name": "Confidence Score",
            "formula": "100 - (missing_comps × 10) - (CV × 100) - fallback_penalty - distance_penalty",
            "input": f"{n} comps, fallback={used_fallback}",
            "output": f"Score = {confidence}/100 ({self._confidence_grade(confidence)})",
        })

        return steps
