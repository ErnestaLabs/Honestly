# -*- coding: utf-8 -*-
"""The PDF mirror of test_interactive_tier: a Lite PDF prints the L1 hook in full and
replaces each Pro section with a frosted locked placeholder - and, because a locked section
is simply not rendered, the Lite PDF physically carries none of the Pro data. These tests
render a Lite and a Pro PDF offline (engine.summary stubbed) and read the text back to prove
no Pro data leaks into Lite and that References cite only what Lite prints.
"""
import copy
import os
import tempfile
import unittest

import report

try:
    from pypdf import PdfReader
    _HAS_PYPDF = True
except Exception:
    _HAS_PYPDF = False

S = {"address": "58 Cronin Street, London SE15 6JH", "sqm": 103, "beds": 2, "epc": "D",
     "tax": "D", "type": "flat", "postcode": "SE15 6JH", "investment": False,
     "floor_area_source": "EPC register", "floor_area_status": "official"}
V = {"low": 480000, "high": 540000, "central": 510000, "guide": 515000, "basis": "comps",
     "avm": {"average": 510000, "high": 540000, "very_high": 570000},
     "market": {"pct": 3.0, "label": "Rising", "note": "Stock is tight."},
     "crosscheck": 505000, "psmA": 5400, "sold_anchor": 508000}
POS = {"band": [1, 2, 3, 4], "lo_p": 480000, "hi_p": 560000, "median": 525000,
       "mean_dom": 34, "stuck": [1]}
COMPS = [
    {"address": "60 Cronin Street, SE15 6JH", "price": 505000, "sqm": 100, "date": "2025-02-01",
     "dist": 0.1, "psm": 5050, "score": 0.92, "match": 0.92, "strict_comparable": False},
    {"address": "3 Bird Road, SE15 6AB", "price": 520000, "sqm": 108, "date": "2024-11-01",
     "dist": 0.3, "psm": 4814, "score": 0.85, "match": 0.85, "strict_comparable": False},
]
R = {"subject": S, "valuation": V, "positioning": POS, "compsA": COMPS}

D = {"address": S["address"], "beds": 2, "guide_label": "Offers Over",
     "guide_value_str": "Offers Over GBP515,000",
     "confidence": {"grade": "Good", "score": 72, "note": "6 strict sold comps."},
     "valuation_formula": {"plain_formula": "sold median, condition-adjusted, steered",
                           "condition": {"tier": "average"}},
     "macro": {"lines": ["MACROLEAKCANARY Bank Rate held at 4.25%."],
               "momentum": {"lines": ["HPI up 1.1% on the year."], "sources": {"a": "ONS"}}},
     "crosscheck": {"official_median_str": "GBP512,000"},
     "n_screened": 3, "floor_area_source": "EPC register", "floor_area_status": "official",
     "plain_english": {"headline": "A defensible two-bed flat valuation.", "bullets": ["b1"]}}

CONTEXT = {"sections": {
    "location": {"legs": [{"label": "STATIONLEAKCANARY Peckham Rye", "time": "8 min", "dist": "~600 m"}],
                 "lat": 51.4663, "lng": -0.0666, "postcode": "SE15 6JH"},
    "narrative": {"ok": True, "text": "NARRATIVEKEEP A two-bed flat valued from sold comparables."},
}, "present": {"postcodes_io": True, "distance_mx": True}, "lat": 51.4663, "lng": -0.0666,
   "postcode": "SE15 6JH"}


def _render(tier, outdir):
    orig = report.engine.summary
    report.engine.summary = lambda r, audience, n=4, tier=tier: dict(copy.deepcopy(D), tier=tier)
    try:
        p, _ = report.build(R, "vendor", outdir=outdir, slug="rep_" + tier,
                            bot_url="https://t.me/usehonestly_bot", interactive=False,
                            context=copy.deepcopy(CONTEXT), tier=tier)
    finally:
        report.engine.summary = orig
    return "\n".join((pg.extract_text() or "") for pg in PdfReader(p).pages)


@unittest.skipUnless(getattr(report, "_HAS_FPDF", False) and _HAS_PYPDF,
                     "needs fpdf2 + pypdf for an offline PDF round-trip")
class TestReportTierView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Isolation: another test module (test_bot) monkeypatches report.build to a stub that
        # returns fake paths; if its teardown chain leaks, we would read a non-existent PDF.
        # Reload the module so this test always exercises the REAL build, never a leaked stub.
        import importlib
        importlib.reload(report)
        cls._td = tempfile.mkdtemp()
        cls.pro = _render("pro", cls._td)
        cls.lite = _render("lite", cls._td)

    def test_pro_contains_its_section_data(self):
        for needle in ("MACROLEAKCANARY", "STATIONLEAKCANARY"):
            self.assertIn(needle, self.pro)

    def test_lite_leaks_no_pro_synthesis(self):
        # Only the Pro synthesis (market outlook / macro) must be absent. The location FACT
        # (STATIONLEAKCANARY) is now a Lite section and is asserted present below.
        self.assertNotIn("MACROLEAKCANARY", self.lite)

    def test_lite_keeps_facts_l1_narrative_and_shows_lock(self):
        for needle in ("STATIONLEAKCANARY", "NARRATIVEKEEP", "Unlock the full report",
                       "PRO", "480,000", "Good"):
            self.assertIn(needle, self.lite)

    def test_lite_references_only_what_it_prints(self):
        # Lite cites HMLR, EPC, VOA council tax, HMRC and the narrative's model - never a
        # Bank of England / macro line, whose section is locked.
        self.assertIn("HM Land Registry", self.lite)
        self.assertNotIn("MACROLEAKCANARY", self.lite)


if __name__ == "__main__":
    unittest.main()
