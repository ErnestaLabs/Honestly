#!/usr/bin/env python3
"""Offline tests for epc.py - the network layer (_get_json) and auth are stubbed, so
these run anywhere and never depend on the DLUHC register being up or credentialled.

The honesty point under test: EPC is area context that firms up sqm/rating beside the
figure; the client degrades to {ok: False} with no credentials or a down register and
NEVER raises, and address matching is honest (it reports unmatched rather than guessing).
"""
import unittest
from unittest import mock
import epc


_ROWS = {"rows": [
    {"address": "58, CRONIN STREET", "postcode": "SE15 6JH",
     "current-energy-rating": "C", "potential-energy-rating": "B",
     "current-energy-efficiency": "72", "total-floor-area": "79.0",
     "property-type": "Flat", "built-form": "Mid-Terrace",
     "lodgement-date": "2021-05-04"},
    {"address": "60, CRONIN STREET", "postcode": "SE15 6JH",
     "current-energy-rating": "D", "current-energy-efficiency": "63",
     "total-floor-area": "84.5 m2", "property-type": "Flat"},
    {"address": "12, OTHER ROAD", "postcode": "SE15 6JH",
     "current-energy-rating": "E", "current-energy-efficiency": "49",
     "total-floor-area": "55"},
]}

_AUTH = "Basic dGVzdDp0ZXN0"   # base64("test:test"), any non-None value unlocks the path


class TestAuth(unittest.TestCase):
    def test_prebuilt_auth_used_verbatim(self):
        with mock.patch.dict(epc.os.environ, {"EPC_AUTH": "Basic abc"}, clear=False):
            self.assertEqual(epc._auth(), "Basic abc")

    def test_auth_built_from_email_and_key(self):
        with mock.patch.dict(epc.os.environ,
                             {"EPC_EMAIL": "a@b.com", "EPC_KEY": "k"}, clear=False):
            with mock.patch.dict(epc.os.environ, {}, clear=False):
                epc.os.environ.pop("EPC_AUTH", None)
                a = epc._auth()
        self.assertTrue(a.startswith("Basic "))

    def test_no_credentials_returns_none(self):
        with mock.patch.object(epc, "_load_env", lambda: None), \
             mock.patch.dict(epc.os.environ, {}, clear=True):
            self.assertIsNone(epc._auth())


class TestNum(unittest.TestCase):
    def test_extracts_numbers(self):
        self.assertEqual(epc._num("79"), 79.0)
        self.assertEqual(epc._num("84.5 m2"), 84.5)
        self.assertIsNone(epc._num(None))
        self.assertIsNone(epc._num("n/a"))


class TestForPostcode(unittest.TestCase):
    def test_parses_certificates(self):
        with mock.patch.object(epc, "_auth", return_value=_AUTH), \
             mock.patch.object(epc, "_get_json", return_value=_ROWS):
            r = epc.for_postcode("SE15 6JH")
        self.assertTrue(r["ok"])
        self.assertEqual(r["count"], 3)
        c0 = r["certificates"][0]
        self.assertEqual(c0["rating"], "C")
        self.assertEqual(c0["score"], 72)
        self.assertEqual(c0["floor_area_sqm"], 79)
        self.assertEqual(r["certificates"][1]["floor_area_sqm"], 84)  # '84.5 m2' parsed

    def test_no_credentials_degrades(self):
        with mock.patch.object(epc, "_auth", return_value=None):
            r = epc.for_postcode("SE15 6JH")
        self.assertFalse(r["ok"])
        self.assertIn("credentials", r["reason"])

    def test_no_postcode_degrades(self):
        self.assertFalse(epc.for_postcode("")["ok"])

    def test_auth_rejected_degrades(self):
        import urllib.error
        err = urllib.error.HTTPError("u", 401, "no", {}, None)
        with mock.patch.object(epc, "_auth", return_value=_AUTH), \
             mock.patch.object(epc, "_get_json", side_effect=err):
            r = epc.for_postcode("SE15 6JH")
        self.assertFalse(r["ok"])
        self.assertIn("auth rejected", r["reason"])

    def test_404_is_ok_empty(self):
        import urllib.error
        err = urllib.error.HTTPError("u", 404, "none", {}, None)
        with mock.patch.object(epc, "_auth", return_value=_AUTH), \
             mock.patch.object(epc, "_get_json", side_effect=err):
            r = epc.for_postcode("ZZ99 9ZZ")
        self.assertTrue(r["ok"])
        self.assertEqual(r["count"], 0)

    def test_network_error_degrades_never_raises(self):
        with mock.patch.object(epc, "_auth", return_value=_AUTH), \
             mock.patch.object(epc, "_get_json", side_effect=Exception("boom")):
            r = epc.for_postcode("SE15 6JH")
        self.assertFalse(r["ok"])
        self.assertIn("boom", r["reason"])


_NEW_API_ROWS = {   # new Bearer-API search shape: camelCase, band letter, no floor area
    "data": [
        {"addressLine1": "58 Cronin Street", "postTown": "LONDON", "postcode": "SE15 6JH",
         "currentEnergyEfficiencyBand": "C", "uprn": "100021",
         "registrationDate": "2021-05-04", "propertyType": "Flat"},
    ],
    "pagination": {"totalRecords": 1, "currentPage": 1, "totalPages": 1, "pageSize": 100},
}


class TestCredScheme(unittest.TestCase):
    def test_bearer_token_preferred_and_new_host(self):
        with mock.patch.object(epc, "_load_env", lambda: None), \
             mock.patch.dict(epc.os.environ, {"EPC_TOKEN": "tok"}, clear=True):
            scheme, auth, base = epc._creds()
            self.assertTrue(epc.credentials_present())
        self.assertEqual(scheme, "bearer")
        self.assertEqual(auth, "Bearer tok")
        self.assertEqual(base, epc.API_NEW)

    def test_epc_key_alone_is_a_bearer_token(self):
        with mock.patch.object(epc, "_load_env", lambda: None), \
             mock.patch.dict(epc.os.environ, {"EPC_KEY": "k"}, clear=True):
            scheme, auth, base = epc._creds()
        self.assertEqual(scheme, "bearer")
        self.assertEqual(auth, "Bearer k")

    def test_email_plus_key_is_legacy_basic(self):
        with mock.patch.object(epc, "_load_env", lambda: None), \
             mock.patch.dict(epc.os.environ,
                             {"EPC_EMAIL": "a@b.com", "EPC_KEY": "k"}, clear=True):
            scheme, auth, base = epc._creds()
        self.assertEqual(scheme, "basic")
        self.assertTrue(auth.startswith("Basic "))
        self.assertEqual(base, epc.API_LEGACY)

    def test_no_credentials_present_is_false(self):
        with mock.patch.object(epc, "_load_env", lambda: None), \
             mock.patch.dict(epc.os.environ, {}, clear=True):
            self.assertFalse(epc.credentials_present())


class TestNewApiShape(unittest.TestCase):
    def test_camelcase_band_and_assembled_address(self):
        with mock.patch.object(epc, "_creds",
                               return_value=("bearer", "Bearer t", epc.API_NEW)), \
             mock.patch.object(epc, "_get_json", return_value=_NEW_API_ROWS):
            r = epc.for_postcode("SE15 6JH")
        self.assertTrue(r["ok"])
        self.assertEqual(r["count"], 1)
        c = r["certificates"][0]
        self.assertEqual(c["rating"], "C")            # currentEnergyEfficiencyBand
        self.assertIsNone(c["score"])                 # new search carries no numeric score
        self.assertIsNone(c["floor_area_sqm"])        # nor floor area - never invented
        self.assertIn("58 Cronin Street", c["address"])
        self.assertEqual(c["uprn"], "100021")

    def test_address_match_on_new_api_rows(self):
        with mock.patch.object(epc, "_creds",
                               return_value=("bearer", "Bearer t", epc.API_NEW)), \
             mock.patch.object(epc, "_get_json", return_value=_NEW_API_ROWS):
            a = epc.for_address("58 Cronin Street", "SE15 6JH")
        self.assertTrue(a["matched"])
        self.assertEqual(a["rating"], "C")

    def test_rate_limited_degrades(self):
        import urllib.error
        err = urllib.error.HTTPError("u", 429, "slow down", {}, None)
        with mock.patch.object(epc, "_creds",
                               return_value=("bearer", "Bearer t", epc.API_NEW)), \
             mock.patch.object(epc, "_get_json", side_effect=err):
            r = epc.for_postcode("SE15 6JH")
        self.assertFalse(r["ok"])
        self.assertIn("rate-limited", r["reason"])


class TestForAddress(unittest.TestCase):
    def test_matches_on_building_number(self):
        with mock.patch.object(epc, "_auth", return_value=_AUTH), \
             mock.patch.object(epc, "_get_json", return_value=_ROWS):
            a = epc.for_address("58 Cronin Street", "SE15 6JH")
        self.assertTrue(a["matched"])
        self.assertEqual(a["rating"], "C")
        self.assertEqual(a["floor_area_sqm"], 79)

    def test_wrong_number_is_not_matched(self):
        with mock.patch.object(epc, "_auth", return_value=_AUTH), \
             mock.patch.object(epc, "_get_json", return_value=_ROWS):
            a = epc.for_address("999 Cronin Street", "SE15 6JH")
        self.assertFalse(a["matched"])
        self.assertIn("no confident", a["reason"])

    def test_empty_postcode_certificates(self):
        with mock.patch.object(epc, "_auth", return_value=_AUTH), \
             mock.patch.object(epc, "_get_json", return_value={"rows": []}), \
             mock.patch.object(epc, "public_for_address", return_value={"ok": True, "matched": False, "postcode": "SE15 6JH"}):
            a = epc.for_address("58 Cronin Street", "SE15 6JH")
        self.assertTrue(a["ok"])
        self.assertFalse(a["matched"])

    def test_no_credentials_uses_public_fallback(self):
        public = {"ok": True, "matched": True, "floor_area_sqm": 103, "rating": "C", "source": "public EPC register"}
        with mock.patch.object(epc, "_auth", return_value=None), \
             mock.patch.object(epc, "_bearer", return_value=None), \
             mock.patch.object(epc, "public_for_address", return_value=public):
            a = epc.for_address("58 Cronin Street", "SE15 6JH")
        self.assertTrue(a["ok"])
        self.assertTrue(a["matched"])
        self.assertEqual(a["floor_area_sqm"], 103)


if __name__ == "__main__":
    unittest.main(verbosity=2)
