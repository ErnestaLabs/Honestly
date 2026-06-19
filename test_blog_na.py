#!/usr/bin/env python3
"""Offline regression tests for the "n/a on the blog" defect - no DB, no network.

The bug: EH2 (and the central-business outcodes M2, B2) published a report whose answer box
read "the median recorded sale price across all property types is n/a". Two faults:
  1. The publish gate let a district through on regional HPI alone (a city-wide average, not a
     figure for that outcode), so a district with no recorded sales AND no live listings still
     produced a page with nothing real to headline.
  2. _answer_paragraph led with the sold median unconditionally, so an absent median rendered
     the literal string "n/a".

These tests lock the fix: the gate requires district-level transaction data (sold OR
listings), the answer paragraph is built only from figures we hold and never emits "n/a", and
the money/percent helpers fall back to a muted dash, never the word.
"""
import unittest

import blog
import publish_daily


def _city():
    return {"slug": "edinburgh", "name": "Edinburgh", "series": "The Edinburgh Breakdown",
            "country": "Scotland", "hpi_region": "City of Edinburgh", "strapline": "",
            "districts": ["EH1", "EH2"]}


def _model(district, *, sold=None, listings=None, hpi=None):
    return {
        "city": {"slug": "edinburgh", "name": "Edinburgh", "series": "The Edinburgh Breakdown"},
        "district": district, "slug": f"edinburgh-{district.lower()}",
        "generated_at": "2026-06-11",
        "sold": sold or {"ok": False, "reason": "no sold records for this district"},
        "listings": listings or {"ok": False, "reason": "no live listings for this district"},
        "hpi": hpi or {"ok": False},
    }


class AnswerParagraphNeverNA(unittest.TestCase):
    def test_no_data_at_all_is_honest_not_na(self):
        m = _model("EH2")  # the exact EH2 shape: sold off, listings off, no hpi
        ans = blog._answer_paragraph(m)
        self.assertNotIn("n/a", ans.lower())
        self.assertIn("not currently available", ans)

    def test_hpi_only_leads_on_index_not_na(self):
        # EH2 as actually stored: only the regional HPI was present.
        m = _model("EH2", hpi={"ok": True, "average_price": 289857.0,
                               "annual_change_pct": 2.1, "region": "city-of-edinburgh"})
        ans = blog._answer_paragraph(m)
        self.assertNotIn("n/a", ans.lower())
        self.assertIn("289,857", ans)            # the real figure we hold
        self.assertIn("Edinburgh index", ans)
        self.assertNotIn("recorded sale price across all property types is", ans)

    def test_listings_only_leads_on_asking_clearly_labelled(self):
        m = _model("EH2", listings={"ok": True, "n": 23, "asking_median": 410000,
                                    "mean_dom": 48})
        ans = blog._answer_paragraph(m)
        self.assertNotIn("n/a", ans.lower())
        self.assertIn("asking", ans.lower())      # never imply it is a sold figure
        self.assertIn("410,000", ans)

    def test_sold_present_still_reads_normally(self):
        m = _model("EH1", sold={"ok": True, "median_price": 345000, "psm_median": 5200,
                                "total": 249, "recency": {"last_12m": 120, "window_months": 24}})
        ans = blog._answer_paragraph(m)
        self.assertNotIn("n/a", ans.lower())
        self.assertIn("345,000", ans)
        self.assertIn("median recorded sale price", ans)


class MoneyHelpersFallBackToDash(unittest.TestCase):
    def test_money_none_is_dash_not_na(self):
        self.assertEqual(blog.money(None), "-")
        self.assertEqual(blog.money_short(None), "-")
        self.assertEqual(blog.pct(None), "-")
        for f in (blog.money, blog.money_short, blog.pct):
            self.assertNotIn("n/a", f(None).lower())


class PublishGateRequiresTransactionData(unittest.TestCase):
    def _patch_gather(self, model):
        self._orig = publish_daily.market_district.gather
        publish_daily.market_district.gather = lambda *a, **k: model

    def tearDown(self):
        if hasattr(self, "_orig"):
            publish_daily.market_district.gather = self._orig

    def test_no_sold_no_listings_is_skipped_even_with_hpi(self):
        m = _model("EH2", hpi={"ok": True, "average_price": 289857.0, "region": "x"})
        self._patch_gather(m)
        res = publish_daily.publish_one(_city(), "EH2", key=None)
        self.assertFalse(res.get("ok"))
        self.assertIn("transaction data", res.get("reason", ""))

    def test_confirmed_absent_sold_skips_honestly_not_retry(self):
        # B2: the free HM Land Registry register was queried across every member postcode and
        # holds no residential sale (sold confirmed_absent), while listings provider-errored.
        # The gate must SKIP it honestly as a non-residential district, NOT defer it forever as
        # 'feed down' on the strength of the listings error.
        m = _model("B2",
                   sold={"ok": False, "errored": False, "confirmed_absent": True,
                         "reason": "no residential sales on the HMLR register"},
                   listings={"ok": False, "errored": True, "reason": "PropertyData HTTP 404"})
        self._patch_gather(m)
        res = publish_daily.publish_one(_city(), "B2", key=None)
        self.assertFalse(res.get("ok"))
        self.assertFalse(res.get("retryable"))                 # definitive, not deferred
        self.assertIn("HM Land Registry register", res.get("reason", ""))
        self.assertIn("not a residential market", res.get("reason", ""))

    def test_scotland_uncovered_skips_honestly_not_provider_down(self):
        # A Scotland district (EH3). The free HM Land Registry Price Paid register is the only
        # sold source we use (the paid vendors that once carried Registers of Scotland sales are
        # retired), and it does not cover Scotland - so sold comes back uncovered. The gate must
        # skip it honestly on the coverage boundary, never the lie 'provider down' and never
        # 'no data', and never claim the district has no market.
        m = _model("EH3",
                   sold={"ok": False, "errored": False, "uncovered": True,
                         "reason": "HM Land Registry Price Paid does not cover Scotland"})
        self._patch_gather(m)
        res = publish_daily.publish_one(_city(), "EH3", key=None)
        self.assertFalse(res.get("ok"))
        self.assertTrue(res.get("uncovered"))
        self.assertIn("England & Wales", res.get("reason", ""))
        self.assertIn("Price Paid register", res.get("reason", ""))
        self.assertNotIn("provider down", res.get("reason", ""))
        self.assertNotIn("no-data", res.get("reason", "").replace("NOT recorded as no-data", ""))

    def test_listings_only_is_allowed_through(self):
        m = _model("EH2", listings={"ok": True, "n": 9, "asking_median": 410000,
                                    "mean_dom": 40, "available_n": 9, "stuck_n": 1,
                                    "under_offer_n": 0})
        self._patch_gather(m)
        # store is best-effort; publish_one should pass the gate and return ok. It may write a
        # static file via _write, so just assert it cleared the gate (no skip reason).
        res = publish_daily.publish_one(_city(), "EH2", key=None)
        self.assertTrue(res.get("ok"), res)


if __name__ == "__main__":
    unittest.main()
