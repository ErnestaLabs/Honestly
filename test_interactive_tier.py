# -*- coding: utf-8 -*-
"""Tier is a VIEW over one full-arsenal computation, and a Lite deliverable must be
leak-proof: the Pro payload is physically stripped from the embedded data, so a Lite
file cannot be un-locked from its own source. These tests are the paywall's regression
guard - if a future change lets Pro data ride along in a Lite file, they fail.
"""
import copy
import os
import tempfile
import unittest

import appraise

VAL = {
    "low": 480000, "high": 540000, "central": 510000, "guide": 515000,
    "psmA": 5400, "crosscheck": 505000, "sold_anchor": 508000,
    "avm": {"average": 510000, "high": 540000, "very_high": 570000},
    "market": {"pct": 3.0, "label": "Rising", "note": "Stock is tight and homes are selling quickly."},
    "formula": {"name": "Honestly Transparent AVM v1",
                "plain_formula": "sold median, condition-adjusted, steered for the live market",
                "evidence": {"selected_count": 6},
                "filter": {"property_type": "flats", "distance": "0.5 miles",
                           "recency_window_months": 12, "subject_sale_excluded": True,
                           "strict_reject_reasons": {"floor area >20% from subject": 3}}},
}
SUBJ = {"address": "58 Cronin Street, London SE15 6JH", "sqm": 103, "beds": 2,
        "epc": "D", "tax": "D", "type": "flat", "postcode": "SE15 6JH", "investment": False}
COMPS = [
    {"address": "60 Cronin Street, SE15 6JH", "sqm": 100, "price": 505000,
     "date": "2025-02-01", "dist": 0.1, "match": 0.92, "score": 0.92},
    {"address": "3 Bird Road, SE15 6AB", "sqm": 108, "price": 520000,
     "date": "2024-11-01", "dist": 0.3, "match": 0.85, "score": 0.85},
]
BASE_D = {"address": SUBJ["address"], "audience": "vendor", "sold_median": 508000,
          "guide_label": "Offers Over", "guide_value_str": "Offers Over GBP515,000",
          "macro": {"momentum": {"lines": ["Bank Rate held at 4.25% (MPC, May 2025)."]}},
          "confidence": {"score": 72, "grade": "Good", "note": "6 strict sold comps."},
          "postcode": "SE15 6JH", "valuation_formula": VAL["formula"],
          "crosscheck": {"official_median_str": "GBP512,000"}}
POS = {"band": [1, 2, 3, 4], "lo_p": 480000, "hi_p": 560000, "median": 525000,
       "mean_dom": 34, "stuck": [1]}
CONTEXT = {"sections": {
    "location": {"legs": [{"label": "Nearest station: Peckham Rye", "time": "8 min", "dist": "~600 m"}]},
    "safety": {"ok": True, "total": 48, "month": "2025-04",
               "by_category": [["violent-crime", 12], ["burglary", 4]]},
    "environment": {"flood": {"ok": True, "severity": "Monitored, no active warning", "active": [],
                              "lines": ["Inside 2 monitored flood area(s); no warning is currently active."]},
                    "air": {"ok": True, "aqi": 31, "band": "Fair", "pm2_5": 8}},
    "planning": {"ok": True, "total": 5, "by_status": [["Approved", 3]]},
    "material": {"ok": True, "band": "D", "bracket_1991": "GBP68,001 to GBP88,000", "note": "England band."},
    "narrative": "A two-bed flat in central Peckham, valued from six strict sold comparables.",
}, "lat": 51.4663, "lng": -0.0666, "postcode": "SE15 6JH"}

# Lite = the full FACTS product (beats every competitor's free estimate). Only the Pro
# SYNTHESIS is withheld, so only these may NEVER appear in a Lite file's source.
PRO_ONLY = [
    "Bank Rate held at 4.25%",            # market outlook / macro (Pro synthesis)
    '"impact_cards": [{',                 # L2 dashboard translation payload (Pro)
    '"positioning": {',                   # live positioning strategy payload (Pro)
]

# The facts that MUST be in a Lite file - the reason Lite beats portals. If any of these
# regress out of Lite, the free product got worse, which is the opposite of the goal.
LITE_FACTS = [
    "GBP68,001 to GBP88,000",            # council-tax bracket (material info)
    "Inside 2 monitored flood area",      # flood line (environment)
    "violent-crime",                      # crime category (safety)
    "Peckham Rye",                        # station (location & connectivity)
]


def _render(tier):
    d = copy.deepcopy(BASE_D)
    d["tier"] = tier
    with tempfile.TemporaryDirectory() as td:
        p = appraise.interactive_chart(
            COMPS, VAL, SUBJ, "t_" + tier, td, "https://t.me/usehonestly_bot",
            d=d, pos=POS, context=copy.deepcopy(CONTEXT))
        return open(p, encoding="utf-8").read()


class TestInteractiveTierView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pro = _render("pro")
        cls.lite = _render("lite")

    def test_pro_contains_the_real_pro_data(self):
        for needle in PRO_ONLY:
            self.assertIn(needle, self.pro, f"Pro file should contain {needle!r}")

    def test_lite_leaks_no_pro_synthesis_in_source(self):
        leaks = [n for n in PRO_ONLY if n in self.lite]
        self.assertEqual(leaks, [], f"Lite file leaked Pro synthesis in source: {leaks}")

    def test_lite_keeps_all_the_facts(self):
        # Lite must remain superior to portals: every verifiable fact stays in the free file.
        missing = [n for n in LITE_FACTS if n not in self.lite]
        self.assertEqual(missing, [], f"Lite lost facts it must keep: {missing}")

    def test_lite_blob_only_synthesis_fields_stripped(self):
        # the Pro synthesis is stripped; the facts (epc/tax) are NOT
        for marker in ('"impact_cards": []', '"positioning": null', '"macro": null'):
            self.assertIn(marker, self.lite, f"Lite blob should carry {marker}")
        self.assertNotIn('"epc": null', self.lite)   # EPC is a Lite fact, kept
        self.assertNotIn('"tax": null', self.lite)    # council tax is a Lite fact, kept

    def test_lite_renders_locked_previews_and_unlock_banner(self):
        for marker in ("lock-preview", "lock-card", "lock-badge", "p_unlock"):
            self.assertIn(marker, self.lite)

    def test_lite_keeps_the_l1_hook_and_lite_narrative(self):
        # the free hook stays whole: range/central + the condition lever's real AVM tiers
        self.assertIn('"central": 510000', self.lite)
        self.assertIn("central Peckham", self.lite)  # narrative is Lite, not stripped


if __name__ == "__main__":
    unittest.main()
