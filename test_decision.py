# -*- coding: utf-8 -*-
"""Evidence Purity + the personalised 'If this were our money' decision block.

These guard the two spec artifacts that close the report: the Evidence Purity Score
(replaces a vibe confidence number with a composition fact) and the per-profile decision
frame (grounded in the Hit voice-of-customer scans). Both are single-sourced in the engine
so the PDF and the interactive HTML can never disagree.
"""
import copy
import unittest

import engine


def _comp(p, sqm, addr, official=True):
    return {"address": addr, "price": p, "sqm": sqm, "date": "2025-08-01", "dist": 0.2,
            "score": 0.82, "match": "good", "floor_area_official": official,
            "strict_comparable": True, "justification": "same type, 0.3mi, 4mo",
            "floor_area_status": "official EPC"}


def _result(**over):
    r = {
        "subject": {"address": "58 Cronin Street, London SE15 6JH", "sqm": 92, "beds": 4,
                    "epc": "C", "tax": "D", "type": "terraced house", "last_sold": 430000,
                    "last_sold_date": "2019-06", "investment": False,
                    "floor_area_status": "official EPC", "finish": "high"},
        "valuation": {"low": 590000, "high": 650000, "central": 620000, "guide": 600000,
                      "psmA": 6700, "raw_comparable_median": 570000, "condition_tier": "high",
                      "basis": "hmlr_sold_evidence", "market": {"pct": 0, "label": "Sold-evidence only"},
                      "avm": {}, "sold_anchor": 570000,
                      "formula": {"name": "AVM", "evidence": {"selected_count": 9, "raw_median": 570000},
                                  "condition": {"tier": "high"}, "filter": {"recency_window_months": 12}}},
        "positioning": None,
        "compsA": [_comp(560000, 90, "12 Cronin St"), _comp(580000, 95, "40 Cronin St"),
                   _comp(570000, 88, "7 Whorlton Rd"), _comp(595000, 98, "21 Lugard Rd"),
                   _comp(545000, 86, "3 Cronin St")],
        "n_candidates": 41, "n_screened": 36, "finish": "high",
    }
    for k, v in over.items():
        r[k] = v
    return r


class TestEvidencePurity(unittest.TestCase):
    def test_composition_is_the_gap_between_raw_median_and_central(self):
        d = engine.summary(_result(), audience="vendor", tier="lite")
        ep = d["evidence_purity"]
        # 570k raw median -> 620k central = ~8% adjustment -> ~92% evidence
        self.assertEqual(ep["pct"], 92)
        self.assertEqual(ep["adjustment_pct"], 8)
        self.assertEqual(ep["pct"] + ep["adjustment_pct"], 100)
        self.assertTrue(ep["bar"].startswith("█"))

    def test_average_tier_on_median_is_fully_evidence_based(self):
        r = _result()
        r["valuation"]["central"] = 570000
        r["valuation"]["condition_tier"] = "average"
        d = engine.summary(r, audience="vendor", tier="lite")
        self.assertEqual(d["evidence_purity"]["pct"], 100)

    def test_modelled_areas_capped_below_100(self):
        r = _result()
        r["valuation"]["central"] = 570000
        r["valuation"]["condition_tier"] = "average"
        for c in r["compsA"]:
            c["floor_area_official"] = False
        d = engine.summary(r, audience="vendor", tier="lite")
        self.assertLessEqual(d["evidence_purity"]["pct"], 96)

    def test_history_basis_discloses_hpi_as_adjustment(self):
        r = {"subject": {"address": "1 X Rd N1", "sqm": 70, "last_sold": 300000, "investment": False},
             "valuation": {"low": 400000, "high": 440000, "central": 420000, "guide": 405000,
                           "psmA": 6000, "raw_comparable_median": 0, "condition_tier": "average",
                           "basis": "hmlr_subject_history_hpi", "history_model": {"price": 300000},
                           "market": {"pct": 0}, "avm": {}},
             "positioning": None, "compsA": [], "n_candidates": 12, "n_screened": 12}
        ep = engine.summary(r, audience="buyer", tier="lite")["evidence_purity"]
        self.assertLess(ep["pct"], 80)
        self.assertTrue(any("HPI" in x for x in ep["drivers"]))


class TestDecisionPersonalisation(unittest.TestCase):
    def test_each_profile_gets_its_own_question_and_need(self):
        qs = {}
        for aud in ("buyer", "vendor", "agent"):
            d = engine.summary(_result(), audience=aud, tier="lite")
            blk = engine.decision_block(d, aud)
            qs[aud] = blk["question"]
            self.assertTrue(blk["need"] and blk["next"])
        # the three profiles must not collapse to one generic question
        self.assertEqual(len(set(qs.values())), 3)
        self.assertIn("pay", qs["buyer"].lower())
        self.assertIn("list", qs["vendor"].lower())

    def test_investment_flag_switches_to_investor_frame(self):
        r = _result()
        r["subject"]["investment"] = True
        d = engine.summary(r, audience="buyer", tier="lite")
        blk = engine.decision_block(d, "buyer")
        self.assertIn("stack", blk["question"].lower())
        self.assertTrue(any("net" in x.lower() for x in blk["risks"] + [blk["next"]]))

    def test_strong_evidence_yields_a_yes(self):
        d = engine.summary(_result(), audience="vendor", tier="lite")
        blk = engine.decision_block(d, "vendor")
        self.assertTrue(blk["word"].startswith("YES"))
        self.assertFalse(blk["warn"])
        self.assertTrue(1 <= len(blk["why"]) <= 3)
        self.assertTrue(1 <= len(blk["risks"]) <= 2)

    def test_thin_evidence_is_not_a_blind_yes(self):
        r = _result()
        r["compsA"] = r["compsA"][:2]            # < 5 strict comps
        r["valuation"]["basis"] = "hmlr_subject_history_hpi"
        r["valuation"]["history_model"] = {"price": 300000}
        d = engine.summary(r, audience="buyer", tier="lite")
        blk = engine.decision_block(d, "buyer")
        self.assertEqual(blk["word"], "NOT BLIND")
        self.assertTrue(blk["warn"])

    def test_pdf_and_html_share_the_same_block(self):
        import report
        d = engine.summary(_result(), audience="agent", tier="lite")
        self.assertEqual(report._decision_block(d, "agent"), engine.decision_block(d, "agent"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
