#!/usr/bin/env python3
"""Offline tests for the company thesis in code: OUR figure is built from sold evidence,
PropertyData's AVM is a DISTRUSTED cross-reference that never sets the number.

Two surfaces under test, both fully offline (no network, no paid credits):
  * appraise.valuation()  - the headline figure is the sold-evidence blend; the AVM is
    pulled (via a stubbed api) only as a divergence note and, for an above-average finish,
    a clamped relative tier premium. At an AVERAGE finish a wildly divergent AVM moves the
    figure by exactly nothing.
  * engine.lite_value()   - the free figure resolves the subject's TYPE (address -> EPC
    register -> postcode-dominant prior) so a house is never valued against an area's flats.
"""
import unittest
from unittest import mock

import appraise
import engine


# ----------------------------------------------------------------- valuation(): own figure
def _comps():
    """Consistent ~62 sqm flats at ~£8,400/sqm -> ~£520k, all strong matches."""
    out = []
    for i, (p, sq, sc) in enumerate([(520000, 62, 0.95), (515000, 61, 0.92),
                                     (530000, 63, 0.90), (505000, 60, 0.88),
                                     (540000, 64, 0.85), (498000, 59, 0.80)]):
        out.append({"price": p, "sqm": sq, "psm": round(p / sq), "score": sc,
                    "weak": sc < appraise.COMP_WEAK, "dist": 0.04 + i * 0.01,
                    "date": "2024-06-01", "tenure": "leasehold", "class": "flat"})
    return out


def _subj():
    return {"address": "58 Cronin Street, London, SE15 6JH", "construction": "pre_1914",
            "type": "flat", "sqft": None, "sqm": 62, "beds": 2, "baths": 1,
            "tenure": "leasehold", "class": "flat"}


def _stub_avm(average=700000, high=770000, very_high=840000):
    """A deliberately CRAP, divergent AVM - the thing we exist to beat."""
    def fake_api(endpoint, key, **kw):
        return {"result": {"estimate": {"average": average, "high": high,
                                        "very_high": very_high}[kw.get("finish_quality")]}}
    return fake_api


class TestValuationOwnFigure(unittest.TestCase):
    def test_average_finish_ignores_a_divergent_avm(self):
        with mock.patch.object(appraise, "api", _stub_avm()):
            v = appraise.valuation(_subj(), _comps(), "k", "average", "flat")
        # the headline is OUR evidence (~£520k), NOT the £700k AVM
        self.assertEqual(v["evidence_basis"], "sold")
        self.assertEqual(v["cond_factor"], 1.0)            # AVM does not touch the figure
        self.assertLess(v["central"], 560000)
        self.assertGreater(v["central"], 490000)
        # central is the own evidence at avg finish (cond_factor 1.0); they agree up to
        # their rounding grain (central snaps to 5k, own_value to 1k).
        self.assertAlmostEqual(v["central"], v["own_value"], delta=5000)
        # the AVM is kept only as a distrusted cross-reference, divergence named
        self.assertEqual(v["avm_ref"], 700000)
        self.assertGreater(v["avm_divergence"], 25)        # ~+34%, shown beside, never used

    def test_high_finish_applies_clamped_tier_premium_not_avm_level(self):
        with mock.patch.object(appraise, "api", _stub_avm()):
            avg = appraise.valuation(_subj(), _comps(), "k", "average", "flat")
            hi = appraise.valuation(_subj(), _comps(), "k", "high", "flat")
        # high uses the RELATIVE tier ratio (770/700 = 1.10), applied to OUR figure
        self.assertGreater(hi["central"], avg["central"])
        self.assertAlmostEqual(hi["cond_factor"], 770000 / 700000, places=3)
        self.assertLess(hi["central"], 620000)             # nowhere near the £770k AVM level

    def test_tier_premium_is_clamped(self):
        # an absurd very_high AVM tier (3x average) must be clamped to the 1.25 ceiling
        with mock.patch.object(appraise, "api",
                               _stub_avm(average=500000, high=560000, very_high=1500000)):
            v = appraise.valuation(_subj(), _comps(), "k", "very_high", "flat")
        self.assertLessEqual(v["cond_factor"], 1.25 + 1e-9)

    def test_renovation_discounts_off_our_evidence(self):
        with mock.patch.object(appraise, "api", _stub_avm()):
            avg = appraise.valuation(_subj(), _comps(), "k", "average", "flat")
            ren = appraise.valuation(_subj(), _comps(), "k", "needs_renovation", "flat")
        # 0.80 cut applied to OUR evidence figure, not the AVM
        self.assertEqual(ren["cond_factor"], 0.80)
        self.assertLess(ren["central"], avg["central"])
        self.assertAlmostEqual(ren["central"] / avg["central"], 0.80, delta=0.03)

    def test_no_sold_evidence_falls_back_to_avm_and_says_so(self):
        with mock.patch.object(appraise, "api", _stub_avm()):
            v = appraise.valuation(_subj(), [], "k", "average", "flat")
        self.assertEqual(v["evidence_basis"], "avm_fallback")   # honest about the degradation
        self.assertEqual(v["central"], 700000)

    def test_range_brackets_central_and_tracks_dispersion(self):
        with mock.patch.object(appraise, "api", _stub_avm()):
            v = appraise.valuation(_subj(), _comps(), "k", "average", "flat")
        self.assertLess(v["low"], v["central"])
        self.assertGreater(v["high"], v["central"])
        # tight, consistent cohort -> a narrow band (well under +-18%)
        self.assertLess((v["high"] - v["low"]) / v["central"], 0.30)


# ----------------------------------------------------------- summary(): disclosure surfaces
class TestSummaryDisclosure(unittest.TestCase):
    def _pro_result(self):
        comps = [{"address": f"{n} Road, SE15 6JH", "sqm": 62, "price": p,
                  "date": "2024-06-01", "score": s, "dist": 0.1, "match": int(s * 100),
                  "psm": round(p / 62)}
                 for n, p, s in [(1, 520000, 0.95), (3, 515000, 0.9), (5, 530000, 0.85)]]
        v = {"low": 505000, "high": 535000, "central": 520000, "guide": 475000,
             "psmA": 8400, "crosscheck": 521000, "sold_anchor": 520000, "market": None,
             "own_value": 521000, "sw_price": 520000, "sw_area": 521000,
             "cond_factor": 1.0, "evidence_basis": "sold",
             "avm_ref": 700000, "avm_divergence": 34.6, "avm": {"average": 700000}}
        return {"subject": {"address": "58 Cronin Street, London SE15 6JH", "sqm": 62,
                            "beds": 2}, "valuation": v, "positioning": None,
                "compsA": comps, "n_candidates": 6, "n_screened": 3}

    def setUp(self):
        for name in ("outlook", "txn_link"):
            p = mock.patch.object(engine, name, return_value=(None if name == "outlook" else ""))
            p.start(); self.addCleanup(p.stop)
        # keep the HMLR direct cross-check out of the way - separate concern, separate test
        import land_registry
        p = mock.patch.object(land_registry, "ppd_postcode",
                              side_effect=Exception("offline"))
        p.start(); self.addCleanup(p.stop)

    def test_methodology_states_the_figure_is_ours(self):
        out = engine.summary(self._pro_result(), audience="agent", tier="pro")
        m = out["methodology"]
        self.assertEqual(m["basis"], "sold")
        self.assertEqual(m["n_comps"], 3)
        self.assertIn("built from", m["note"])
        self.assertIn("not an automated estimate", m["note"])

    def test_commercial_avm_crosscheck_is_not_rendered(self):
        out = engine.summary(self._pro_result(), audience="agent", tier="pro")
        self.assertNotIn("avm_crosscheck", out)
        self.assertNotIn("street_enrichment", out)
        self.assertNotIn("chimnie_enrichment", out)
        self.assertNotIn("patma_crosscheck", out)


# --------------------------------------------------------- lite_value(): type resolution
class TestLiteTypeResolution(unittest.TestCase):
    ADDR = "58 Cronin Street, London, SE15 6JH"
    PC = "SE15 6JH"

    def setUp(self):
        import geo, land_registry, epc
        self.geo, self.lr, self.epc = geo, land_registry, epc

        def _row(addr, price, date, typ):
            return {"address": addr, "price": price, "date": date, "type": typ}
        import datetime as _dt
        recent = (_dt.date.today() - _dt.timedelta(days=120)).isoformat()
        # district: many cheap flats (~£400k) + several pricier terraced houses (~£700k)
        district = [_row(f"Flat {i}, Block, SE15 6JL", 395000 + i * 1000, recent,
                         "flat-maisonette") for i in range(8)]
        district += [_row(f"{n} Cronin Street, SE15 6JH", 690000 + i * 4000, recent,
                          "terraced") for i, n in enumerate((62, 64, 66, 68, 70, 72))]
        # exact postcode kept MIXED so the dominant-prior does not fire - isolates EPC
        exact = [_row("Flat 1, Court, SE15 6JH", 405000, recent, "flat-maisonette"),
                 _row("60 Cronin Street, SE15 6JH", 705000, recent, "terraced")]

        self._patches = [
            mock.patch.object(geo, "lookup", lambda pc, **k: {
                "ok": True, "country": "England", "lat": 51.4, "lng": -0.06,
                "outcode": "SE15", "postcode": self.PC}),
            mock.patch.object(geo, "outcode_postcodes",
                              lambda oc: {"ok": True, "postcodes": ["SE15 6JH", "SE15 6JL"]}),
            mock.patch.object(land_registry, "ppd_postcode",
                              lambda pc, **k: {"ok": True, "sales": exact}),
            mock.patch.object(land_registry, "ppd_area",
                              lambda pcs, **k: {"ok": True, "sales": district}),
        ]
        for p in self._patches:
            p.start(); self.addCleanup(p.stop)

    def test_epc_confirms_house_so_it_is_not_valued_as_a_flat(self):
        with mock.patch.object(self.epc, "credentials_present", lambda: True), \
             mock.patch.object(self.epc, "for_address", lambda a, pc, **k: {
                 "ok": True, "matched": True, "property_type": "House",
                 "built_form": "Mid-Terrace"}):
            r = engine.lite_value(self.ADDR)
        v = r["valuation"]
        self.assertEqual(v["type_source"], "epc_register")
        self.assertTrue(v["type_confident"])
        self.assertEqual(v["type_basis"], "terraced houses")
        self.assertGreater(v["central"], 600000)           # valued as a house, ~£700k

    def test_subjects_own_hmlr_record_sets_the_type(self):
        # 58 Cronin Street has its OWN sold record in HM Land Registry as a terraced house.
        # EPC is OFF. The register's own entry is authoritative -> valued as a house, ~£700k,
        # WITHOUT needing EPC or a postcode guess.
        import datetime as _dt
        recent = (_dt.date.today() - _dt.timedelta(days=120)).isoformat()
        own = [{"address": "58, Cronin Street, London", "price": 698000,
                "date": recent, "type": "terraced"},
               {"address": "60, Cronin Street, London", "price": 705000,
                "date": recent, "type": "terraced"},
               {"address": "Flat 1, Court, London", "price": 405000,
                "date": recent, "type": "flat-maisonette"}]
        with mock.patch.object(self.lr, "ppd_postcode",
                               lambda pc, **k: {"ok": True, "sales": own}), \
             mock.patch.object(self.epc, "credentials_present", lambda: False):
            r = engine.lite_value(self.ADDR)
        v = r["valuation"]
        self.assertEqual(v["type_source"], "hmlr_register")
        self.assertTrue(v["type_confident"])
        self.assertEqual(v["type_basis"], "terraced houses")
        self.assertGreater(v["central"], 600000)            # valued as a house from the register
        self.assertIn("HM Land Registry's own record",
                      r["subject"]["lite_basis"]["note"])

    def test_epc_confirms_flat(self):
        with mock.patch.object(self.epc, "credentials_present", lambda: True), \
             mock.patch.object(self.epc, "for_address", lambda a, pc, **k: {
                 "ok": True, "matched": True, "property_type": "Flat",
                 "built_form": "Enclosed Mid-Floor"}):
            r = engine.lite_value(self.ADDR)
        v = r["valuation"]
        self.assertEqual(v["type_source"], "epc_register")
        self.assertEqual(v["type_basis"], "flats")
        self.assertLess(v["central"], 460000)              # valued as a flat, ~£400k

    def test_unconfirmed_type_is_disclosed_not_silent(self):
        # EPC and optional subject enrichment off, exact postcode mixed -> cannot confirm.
        # The figure must SAY so.
        with mock.patch.object(engine, "_epc_subject", lambda address, pc: None):
            r = engine.lite_value(self.ADDR)
        v = r["valuation"]
        self.assertFalse(v["type_confident"])
        self.assertTrue(r["subject"]["sqm"])                # floor area is now always filled/provenanced
        self.assertEqual(r["subject"]["floor_area_status"], "modelled")
        note = r["subject"]["lite_basis"]["note"]
        self.assertTrue("could not confirm" in note or "predominant property type" in note)
        self.assertIn("Floor area is filled", note)

    def test_subjects_own_sale_is_excluded_from_lite_comps(self):
        import datetime as _dt
        recent = (_dt.date.today() - _dt.timedelta(days=90)).isoformat()
        sales = [{"address": "58, Cronin Street, London", "price": 999000,
                  "date": recent, "type": "terraced"}]
        sales += [{"address": f"{n}, Cronin Street, London", "price": 700000 + i * 1000,
                   "date": recent, "type": "terraced"}
                  for i, n in enumerate((60, 62, 64, 66, 68, 70))]
        with mock.patch.object(self.lr, "ppd_postcode",
                               lambda pc, **k: {"ok": True, "sales": sales}), \
             mock.patch.object(self.lr, "ppd_area",
                               lambda pcs, **k: {"ok": True, "sales": sales}), \
             mock.patch.object(self.epc, "credentials_present", lambda: False):
            r = engine.lite_value(self.ADDR, ptype="terraced_house")
        self.assertTrue(all("58" not in c["address"] for c in r["compsA"]))

    def test_lite_comps_respect_24_month_hard_cap(self):
        import datetime as _dt
        recent = (_dt.date.today() - _dt.timedelta(days=90)).isoformat()
        old = (_dt.date.today() - _dt.timedelta(days=800)).isoformat()
        sales = [{"address": "60, Cronin Street, London", "price": 1500000,
                  "date": old, "type": "terraced"}]
        sales += [{"address": f"{n}, Cronin Street, London", "price": 700000 + i * 1000,
                   "date": recent, "type": "terraced"}
                  for i, n in enumerate((62, 64, 66, 68, 70, 72))]
        with mock.patch.object(self.lr, "ppd_area",
                               lambda pcs, **k: {"ok": True, "sales": sales}), \
             mock.patch.object(self.epc, "credentials_present", lambda: False):
            r = engine.lite_value(self.ADDR, ptype="terraced_house")
        self.assertTrue(all(c["date"] != old for c in r["compsA"]))
        self.assertLess(r["valuation"]["central"], 800000)

    def test_cronin_high_finish_regression_uses_size_not_generic_flats(self):
        import datetime as _dt
        recent = (_dt.date.today() - _dt.timedelta(days=90)).isoformat()
        older = (_dt.date.today() - _dt.timedelta(days=500)).isoformat()
        exact = [{"address": "58, Cronin Street, London", "price": 320000,
                  "date": "2015-02-06", "type": "flat-maisonette"}]
        sales = [
            {"address": "Flat 8, 86, Chandler Way, London", "price": 445000, "date": recent, "type": "flat-maisonette"},
            {"address": "Flat 8, 105, Peckham Road, London", "price": 500000, "date": recent, "type": "flat-maisonette"},
            {"address": "Flat 6, 73, Blakes Road, London", "price": 505000, "date": older, "type": "flat-maisonette"},
            {"address": "Apartment 7, 95, Peckham Road, London", "price": 590000, "date": recent, "type": "flat-maisonette"},
            {"address": "Flat 9, Hamley Lodge, 29, Peckham High Street, London", "price": 612500, "date": older, "type": "flat-maisonette"},
            {"address": "102, Leontine Close, London", "price": 706700, "date": older, "type": "flat-maisonette"},
            {"address": "Flat 3, Tiny Court, London", "price": 170000, "date": recent, "type": "flat-maisonette"},
        ]
        sizes = {"86": 97, "105": 92, "73": 95, "95": 104, "Hamley": 118, "Leontine": 114, "Tiny": 40}
        def attach(rows):
            for s in rows:
                for k, sqm in sizes.items():
                    if k.lower() in s["address"].lower():
                        s["sqm"] = sqm
            return rows, "test size cache"
        with mock.patch.object(self.lr, "ppd_postcode", lambda pc, **k: {"ok": True, "sales": exact}), \
             mock.patch.object(self.lr, "ppd_area", lambda pcs, **k: {"ok": True, "sales": sales}), \
             mock.patch.object(engine, "_epc_subject", lambda address, pc: {"floor_area_sqm": 103, "property_type": "Flat", "built_form": ""}), \
             mock.patch.object(engine, "_attach_epc_floor_areas", lambda rows, pcs: attach(rows)):
            r = engine.lite_value(self.ADDR, finish="high")
        self.assertEqual(r["subject"]["sqm"], 103)
        # The figure is the subject's own 2015 sale brought forward by LIVE HPI to today, so the
        # exact pounds drift with each HPI release (and with today's date). Assert a tolerance band
        # + ordering, not an exact tuple. The real regression guards are the basis (subject history,
        # NOT generic flats) and strict_comparable_count==0, below.
        v = r["valuation"]
        self.assertLess(v["low"], v["central"])
        self.assertLess(v["central"], v["high"])
        self.assertTrue(510000 <= v["central"] <= 570000,
                        f"central {v['central']} outside HPI-tolerance band: {v}")
        self.assertEqual(v["basis"], "hmlr_subject_history_hpi")
        self.assertEqual(v["formula"]["evidence"]["strict_comparable_count"], 0)
        self.assertNotIn(706700, [c["price"] for c in r["compsA"]])
        self.assertNotIn(170000, [c["price"] for c in r["compsA"]])


class TestHmlrSubjectType(unittest.TestCase):
    """The subject's OWN HM Land Registry record sets its type - the register is the
    definitive answer to 'what IS this property'. Matches on PAON (+ SAON for flats)."""
    SALES = [{"address": "58, Cronin Street, London", "type": "terraced"},
             {"address": "Flat 3, 12, High Road, London", "type": "flat-maisonette"},
             {"address": "Flat 5, 12, High Road, London", "type": "flat-maisonette"}]

    def test_house_self_match(self):
        self.assertEqual(
            engine._hmlr_subject_type("58 Cronin Street, London, SE15 6JH", self.SALES),
            "terraced_house")

    def test_flat_unit_match(self):
        # subject names its unit; match the exact flat in the building
        self.assertEqual(
            engine._hmlr_subject_type("Flat 3, 12 High Road, London", self.SALES), "flat")

    def test_building_unanimous_is_that_stock(self):
        # subject "12 High Road" with no unit named; both sold units are flats -> flat
        self.assertEqual(
            engine._hmlr_subject_type("12 High Road, London", self.SALES), "flat")

    def test_no_record_returns_none(self):
        self.assertIsNone(
            engine._hmlr_subject_type("99 Cronin Street, London", self.SALES))

    def test_mixed_building_stays_unresolved(self):
        mixed = [{"address": "Flat 1, 5, Mill Lane, London", "type": "flat-maisonette"},
                 {"address": "5, Mill Lane, London", "type": "terraced"}]
        # a house AND a flat at number 5 -> genuinely mixed -> we do not guess
        self.assertIsNone(engine._hmlr_subject_type("5 Mill Lane, London", mixed))

    def test_empty_inputs_are_safe(self):
        self.assertIsNone(engine._hmlr_subject_type("", self.SALES))
        self.assertIsNone(engine._hmlr_subject_type("58 Cronin Street", None))


class TestEpcTypeMap(unittest.TestCase):
    def test_built_form_maps_to_slug_semi_before_detached(self):
        self.assertEqual(engine._epc_type_to_slug("House", "Semi-Detached"),
                         "semi_detached_house")
        self.assertEqual(engine._epc_type_to_slug("House", "Detached"), "detached_house")
        self.assertEqual(engine._epc_type_to_slug("House", "Mid-Terrace"), "terraced_house")
        self.assertEqual(engine._epc_type_to_slug("Bungalow", "End-Terrace"), "terraced_house")
        self.assertEqual(engine._epc_type_to_slug("Flat", "Mid-Floor"), "flat")
        self.assertEqual(engine._epc_type_to_slug("Maisonette", ""), "flat")
        self.assertIsNone(engine._epc_type_to_slug("Park home", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
