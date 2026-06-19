#!/usr/bin/env python3
"""Offline tests for press_review.py + blog.render_commentary - the blog's "headlines vs the
sold record" fact-check (build #75).

No network: claims are frozen artifacts on disk; the city snapshot is built from stored
district models via market_study._row_from_model. The honesty contract under test:
  * shape_articles drops any claim we cannot link to (no quote, url, publisher or title) -
    we never cite what we cannot show the reader;
  * freeze merges one city's block without clobbering another city's;
  * the snapshot needs >= 3 districts with a sold basis or it degrades to {ok: False} -
    we do not publish a thin or one-sided page;
  * every figure in clarify() comes from the snapshot, never from the quoted claim, and the
    verdict vocabulary stays conservative (we add ground truth, we do not rate journalism);
  * render_commentary refuses to render without both a claims block and an ok snapshot, and
    when it does render it quotes the article, links it rel=nofollow, and prints OUR figure.
"""
import json
import os
import tempfile
import unittest

import press_review as PR
import blog
import cities


# --------------------------------------------------------------------------- a fake store
def _model(slug, district, *, sold_median, psm=None, asking=None, dom=None,
           avail=None, stuck=None, sales_12m=None, country="", sold_ok=True,
           name="Testville", series="Testville property", city_slug="testville"):
    """A stored district model shaped exactly as market_study._row_from_model expects."""
    return {
        "city": {"name": name, "series": series, "slug": city_slug, "country": country},
        "district": district, "slug": slug, "generated_at": "2026-06-01",
        "sold": {"ok": sold_ok, "median_price": sold_median, "psm_median": psm,
                 "recency": {"last_12m": sales_12m}},
        "listings": {"ok": True, "asking_median": asking, "available_n": avail,
                     "stuck_n": stuck, "n": avail, "mean_dom": dom, "under_offer_n": None},
    }


class FakeStore:
    """Minimal store_mod stand-in: only the two accessors city_snapshot uses."""
    def __init__(self, models):
        # models: {city_slug: [model, ...]}
        self._by_city = models
        self._by_slug = {m["slug"]: m for ms in models.values() for m in ms}

    def list_blog_posts(self, city_slug=None):
        if city_slug is None:
            return [{"slug": m["slug"]} for ms in self._by_city.values() for m in ms]
        return [{"slug": m["slug"]} for m in self._by_city.get(city_slug, [])]

    def get_blog_post(self, slug, with_model=False):
        m = self._by_slug.get(slug)
        return {"model": m} if m else None


def _three_district_store(city_slug="testville", country=""):
    return FakeStore({city_slug: [
        _model(f"{city_slug}-a", "A1", sold_median=400000, psm=6000, asking=390000,
               dom=40, avail=100, stuck=10, sales_12m=120, country=country, city_slug=city_slug),
        _model(f"{city_slug}-b", "B2", sold_median=500000, psm=6500, asking=520000,
               dom=55, avail=80, stuck=20, sales_12m=90, country=country, city_slug=city_slug),
        _model(f"{city_slug}-c", "C3", sold_median=450000, psm=6200, asking=445000,
               dom=48, avail=60, stuck=9, sales_12m=70, country=country, city_slug=city_slug),
    ]})


# --------------------------------------------------------------------------- shaping
class TestShape(unittest.TestCase):
    def test_keeps_a_full_claim_and_normalises_fields(self):
        out = PR.shape_articles([{
            "publisher": "The Guardian", "title": "London asking prices dip",
            "url": "https://example.com/a", "date": "May 2026",
            "quote": "Asking prices in London fell 2% over the quarter.",
            "topic": "Asking prices", "metric": "sold_median", "claim_dir": "down",
            "claim_value": "410000", "claim_value_str": "£410,000"}])
        self.assertEqual(len(out), 1)
        c = out[0]
        self.assertEqual(c["publisher"], "The Guardian")
        self.assertEqual(c["metric"], "sold_median")
        self.assertEqual(c["claim_dir"], "down")
        self.assertEqual(c["claim_value"], 410000.0)

    def test_drops_claim_we_cannot_link_to(self):
        items = [
            {"publisher": "X", "title": "T", "quote": "no url here"},          # no url
            {"publisher": "Y", "title": "T", "url": "https://e.com/2"},         # no quote
            {"title": "T", "url": "https://e.com/3", "quote": "no publisher"},  # no publisher
            {"publisher": "Z", "url": "https://e.com/4", "quote": "no title"},  # no title
        ]
        self.assertEqual(PR.shape_articles(items), [])

    def test_unknown_metric_or_dir_blanked_not_kept(self):
        out = PR.shape_articles([{
            "publisher": "P", "title": "T", "url": "https://e.com/x",
            "quote": "q", "metric": "interest_rate", "claim_dir": "sideways"}])
        self.assertEqual(out[0]["metric"], "")
        self.assertEqual(out[0]["claim_dir"], "")

    def test_max_claims_caps(self):
        items = [{"publisher": f"P{i}", "title": "T", "url": f"https://e.com/{i}",
                  "quote": "q"} for i in range(10)]
        self.assertEqual(len(PR.shape_articles(items, max_claims=3)), 3)

    def test_never_raises_on_junk(self):
        self.assertEqual(PR.shape_articles(None), [])
        self.assertEqual(PR.shape_articles(["not a dict", 5, None]), [])


# --------------------------------------------------------------------------- build + freeze
class TestBlockAndFreeze(unittest.TestCase):
    def test_build_block_carries_honesty_posture_by_default(self):
        blk = PR.build_block(claims=[{"quote": "q", "url": "u", "publisher": "p", "title": "t"}],
                             captured_at="2026-06-10")
        self.assertEqual(blk["captured_at"], "2026-06-10")
        self.assertIn("recognise the source", blk["method"])
        self.assertIn("every number in the clarification is the city's own sold record", blk["disclaimer"])
        self.assertEqual(len(blk["claims"]), 1)

    def test_build_block_drops_claim_without_quote(self):
        blk = PR.build_block(claims=[{"url": "u"}, {"quote": "ok"}], captured_at="2026-06-10")
        self.assertEqual(len(blk["claims"]), 1)

    def test_freeze_and_load_round_trip_without_clobber(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "press_review.json")
            blk_a = PR.build_block(claims=[{"quote": "a", "url": "u", "publisher": "p",
                                            "title": "t"}], captured_at="2026-06-10")
            blk_b = PR.build_block(claims=[{"quote": "b", "url": "u", "publisher": "p",
                                            "title": "t"}], captured_at="2026-06-10")
            self.assertTrue(PR.freeze(city_slug="london", block=blk_a, path=path))
            self.assertTrue(PR.freeze(city_slug="leeds", block=blk_b, path=path))
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # both cities present - freezing leeds did not clobber london
            self.assertIn("london", data["by_city"])
            self.assertIn("leeds", data["by_city"])

    def test_load_returns_empty_when_no_claims(self):
        orig = PR._PATH
        try:
            with tempfile.TemporaryDirectory() as d:
                PR._PATH = os.path.join(d, "press_review.json")
                self.assertEqual(PR.load("nowhere"), {})
                self.assertEqual(PR.cities_with_claims(), [])
        finally:
            PR._PATH = orig


# --------------------------------------------------------------------------- snapshot
class TestSnapshot(unittest.TestCase):
    def test_degrades_below_three_districts(self):
        store = FakeStore({"testville": [
            _model("testville-a", "A1", sold_median=400000),
            _model("testville-b", "B2", sold_median=500000)]})
        snap = PR.city_snapshot("testville", store_mod=store)
        self.assertFalse(snap["ok"])

    def test_aggregates_three_districts(self):
        snap = PR.city_snapshot("testville", store_mod=_three_district_store())
        self.assertTrue(snap["ok"])
        self.assertEqual(snap["n_districts"], 3)
        self.assertEqual(snap["metrics"]["sold_median"], 450000)   # median of 400/500/450k
        self.assertEqual(snap["metrics"]["sold_low"], 400000)
        self.assertEqual(snap["metrics"]["sold_high"], 500000)
        self.assertEqual(snap["metrics"]["sales_12m"], 280)        # summed
        self.assertEqual(snap["country"], "")

    def test_skips_districts_with_no_sold_basis(self):
        store = FakeStore({"testville": [
            _model("testville-a", "A1", sold_median=400000),
            _model("testville-b", "B2", sold_median=500000),
            _model("testville-c", "C3", sold_median=None, sold_ok=False),
            _model("testville-d", "D4", sold_median=450000)]})
        snap = PR.city_snapshot("testville", store_mod=store)
        self.assertTrue(snap["ok"])
        self.assertEqual(snap["n_districts"], 3)

    def test_never_raises_without_store(self):
        # store_mod given as a broken object -> {ok: False}, no exception
        class Boom:
            def list_blog_posts(self, *a, **k):
                raise RuntimeError("db down")
        self.assertFalse(PR.city_snapshot("x", store_mod=Boom())["ok"])


# --------------------------------------------------------------------------- clarify
class TestClarify(unittest.TestCase):
    def setUp(self):
        self.snap = PR.city_snapshot("testville", store_mod=_three_district_store())

    def test_no_metric_is_beyond_sold_data(self):
        cl = PR.clarify({"metric": "", "quote": "prices will boom next year"}, self.snap)
        self.assertEqual(cl["verdict"], "Beyond what sold data can confirm")
        self.assertIsNone(cl["our_value"])

    def test_metric_without_value_is_grounded(self):
        cl = PR.clarify({"metric": "sold_median"}, self.snap)
        self.assertEqual(cl["verdict"], "Grounded by the local record")
        self.assertEqual(cl["our_value"], 450000)
        self.assertEqual(cl["our_kind"], "gbp")

    def test_close_value_is_broadly_in_line(self):
        # 460k vs our 450k median -> within 10%
        cl = PR.clarify({"metric": "sold_median", "claim_value": 460000}, self.snap)
        self.assertEqual(cl["verdict"], "Broadly in line with the local record")

    def test_far_value_differs(self):
        cl = PR.clarify({"metric": "sold_median", "claim_value": 650000}, self.snap)
        self.assertEqual(cl["verdict"], "The local record differs")
        self.assertIn("above", cl["sentence"])

    def test_never_prints_the_quoted_figure_as_ours(self):
        cl = PR.clarify({"metric": "sold_median", "claim_value": 650000}, self.snap)
        self.assertEqual(cl["our_value"], 450000)   # our snapshot figure, not 650000


# --------------------------------------------------------------------------- render gating
class TestRender(unittest.TestCase):
    def setUp(self):
        self.city = {"slug": "testville", "name": "Testville",
                     "series": "Testville property", "country": ""}
        self.snap = PR.city_snapshot("testville", store_mod=_three_district_store())
        self.claims = PR.shape_articles([{
            "publisher": "The Example Times", "title": "Testville prices climb",
            "url": "https://example.com/testville", "date": "June 2026",
            "quote": "Average prices in Testville hit a record high this spring.",
            "topic": "House prices", "metric": "sold_median", "claim_dir": "up"}])
        self.block = PR.build_block(claims=self.claims, captured_at="2026-06-10")

    def test_renders_nothing_without_claims(self):
        empty = PR.build_block(claims=[], captured_at="2026-06-10")
        self.assertEqual(blog.render_commentary(self.city, self.snap, empty), "")

    def test_renders_nothing_without_ok_snapshot(self):
        bad = {"ok": False, "reason": "thin"}
        self.assertEqual(blog.render_commentary(self.city, bad, self.block), "")

    def test_renders_full_page_with_honest_marks(self):
        html = blog.render_commentary(self.city, self.snap, self.block)
        self.assertTrue(html.startswith("<!doctype html>"))
        # the article is quoted and linked, rel=nofollow (someone else's page)
        self.assertIn("Average prices in Testville hit a record high", html)
        self.assertIn('rel="nofollow noopener"', html)
        # our own figure appears (450k median); we issue no valuation
        self.assertIn("£450,000", html)
        self.assertIn("No valuation", html)
        # JSON-LD is an Article, never a ClaimReview (we do not rate the journalism)
        self.assertIn('"@type": "Article"', html)
        self.assertNotIn("ClaimReview", html)
        # canonical + breadcrumb to the commentary URL
        self.assertIn("testville-market-commentary", html)

    def test_no_em_or_en_dash_in_output(self):
        html = blog.render_commentary(self.city, self.snap, self.block)
        self.assertNotIn("—", html)   # em dash
        self.assertNotIn("–", html)   # en dash


if __name__ == "__main__":
    unittest.main(verbosity=2)
