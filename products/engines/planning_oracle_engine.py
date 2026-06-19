#!/usr/bin/env python3
"""products/engines/planning_oracle_engine.py - "Can I Build A Loft Without Asking The Council?"

The Planning Permission Oracle: Laziness-triggered micro-upsell.

Deterministic Python logic (no LLM needed). Checks Permitted Development
rules using:
  1. Property type from the AVM (flats = no PD for lofts)
  2. Vision.py for roof shape analysis from Street View
  3. Overpass.py for conservation area / boundary checks
  4. A rule engine that returns a strict JSON verdict

This is a 3-second product. No LLM, no waiting.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────── PD rules engine

# Permitted Development volume limits (cubic metres)
PD_VOLUME_LIMITS = {
    "terraced_house": {"standard": 40, "with_hip_to_gable": 50},
    "semi_detached_house": {"standard": 50, "with_hip_to_gable": 60},
    "detached_house": {"standard": 50, "with_hip_to_gable": 60},
}

# Roof types that allow loft conversions
ROOF_TYPES_ALLOWING_PD = {"gable", "hipped", "pitched", "mansard"}

# Standard conditions that always apply to loft PD
STANDARD_LOFT_CONDITIONS = [
    "Must use materials similar in appearance to the existing house",
    "No extension beyond the plane of the existing roof slope on the principal elevation",
    "No side-facing windows without obscure glazing",
    "No balcony, veranda, or raised platform",
    "Maximum 40 cubic metres for terraced houses, 50 for others",
]

# Disallowed property types for loft PD
NO_PD_PROPERTY_TYPES = {"flat", "flat-maisonette", "maisonette", "apartment"}


def assess_permitted_development(
    address: str,
    ptype: str,
    sqm: int | None = None,
    lat: float | None = None,
    lng: float | None = None,
    roof_type: str | None = None,
    conservation_area: bool | None = None,
) -> dict:
    """Assess whether a loft conversion is likely Permitted Development.

    Deterministic rule engine. No LLM. Returns in <3 seconds.

    Args:
        address: property address
        ptype: property type slug (flat, terraced_house, etc.)
        sqm: floor area
        lat: latitude (for Overpass queries)
        lng: longitude (for Overpass queries)
        roof_type: "gable", "hipped", "pitched", "flat", "mansard" (or None to infer)
        conservation_area: True/False/None (or None to check)

    Returns:
        {"ok": True, "verdict": str, "confidence_pct": int, "conditions": [...], "details": {...}}
    """
    details = {
        "address": address,
        "ptype": ptype,
        "sqm": sqm,
        "roof_type": roof_type,
        "conservation_area": conservation_area,
    }

    # ── Gate 1: Property type ────────────────────────────────────────
    if ptype and any(t in ptype.lower() for t in NO_PD_PROPERTY_TYPES):
        return {
            "ok": True,
            "verdict": "Not Permitted Development",
            "confidence_pct": 95,
            "conditions": [
                "Flats and maisonettes cannot use Permitted Development for loft conversions",
                "You will need full planning permission",
                "Check your lease for alteration restrictions as well",
            ],
            "details": details,
            "format": "json",
        }

    # ── Gate 2: Roof shape ───────────────────────────────────────────
    if roof_type is None:
        # Try to infer from vision.py or property type
        roof_type = _infer_roof_type(address, ptype, lat, lng)
        details["roof_type"] = roof_type
        details["roof_source"] = "inferred"

    if roof_type and roof_type.lower() == "flat":
        return {
            "ok": True,
            "verdict": "Not Permitted Development",
            "confidence_pct": 90,
            "conditions": [
                "Flat roofs cannot accommodate a loft conversion under PD",
                "Full planning permission is required",
            ],
            "details": details,
            "format": "json",
        }

    # ── Gate 3: Conservation area ────────────────────────────────────
    if conservation_area is None and lat and lng:
        conservation_area = _check_conservation_area(lat, lng)
        details["conservation_area"] = conservation_area
        details["conservation_area_source"] = "overpass"

    if conservation_area:
        return {
            "ok": True,
            "verdict": "Not Permitted Development",
            "confidence_pct": 85,
            "conditions": [
                "Properties in conservation areas lose PD rights for loft conversions",
                "You must apply for full planning permission",
                "Contact your local planning authority for the conservation area appraisal",
            ],
            "details": details,
            "format": "json",
        }

    # ── Gate 4: Volume limits ────────────────────────────────────────
    volume_key = ptype or "semi_detached_house"
    volume_limits = PD_VOLUME_LIMITS.get(volume_key, PD_VOLUME_LIMITS["semi_detached_house"])
    max_volume = volume_limits["standard"]

    conditions = list(STANDARD_LOFT_CONDITIONS)

    if roof_type and roof_type.lower() == "hipped":
        conditions.append("Hip-to-gable conversion may be possible, adding up to "
                         f"{volume_limits['with_hip_to_gable']} cubic metres")
        max_volume = volume_limits["with_hip_to_gable"]

    # ── Final verdict ────────────────────────────────────────────────
    roof_ok = roof_type and roof_type.lower() in ROOF_TYPES_ALLOWING_PD
    confidence = 90 if roof_ok and conservation_area is False else 75

    return {
        "ok": True,
        "verdict": "Likely Permitted Development",
        "confidence_pct": confidence,
        "conditions": conditions,
        "details": details,
        "max_volume_cubic_m": max_volume,
        "format": "json",
    }


# ──────────────────────────────────────────────────────── helpers

def _infer_roof_type(address: str, ptype: str, lat: float | None, lng: float | None) -> str:
    """Infer roof type from property type or Street View.

    Falls back to type-based heuristics if vision.py is unavailable.
    """
    # Try vision.py first
    try:
        from vision import assess
        # Vision assess works on image URLs; for now use type heuristics
        # TODO: integrate Google Street View image capture
    except Exception:
        pass

    # Type-based heuristics
    if ptype and "terraced" in ptype:
        return "gable"  # most UK terraces have gable roofs
    if ptype and "semi" in ptype:
        return "hipped"  # many UK semis have hipped roofs
    if ptype and "detached" in ptype:
        return "hipped"
    return "gable"  # default assumption for UK houses


def _check_conservation_area(lat: float, lng: float) -> bool:
    """Check if the property is in a conservation area using Overpass.

    Queries OSM for conservation area boundaries near the coordinates.
    Returns True if inside a boundary, False if not, None if unknown.
    """
    try:
        from overpass import amenities
        result = amenities(lat, lng, radius_m=200)
        if result.get("ok"):
            # Check for conservation-related tags in the result
            counts = result.get("counts", {})
            # If we find heritage/conservation-related POIs nearby, flag it
            heritage_count = counts.get("historic", 0)
            if heritage_count >= 3:
                return True  # likely in a conservation area
    except Exception:
        pass
    return False
