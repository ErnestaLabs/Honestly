#!/usr/bin/env python3
"""Offline tests for market_study.py + blog.render_study - no DB, no network.

A fake store feeds three hand-built district models so the league-table maths and the
rendered study page are checked against known inputs. The honesty contract is asserted in
code: asking is never blended into sold, the gap is labelled context, and the page values
nothing."""
import json
import unittest

import market_study
import blog


def _model(city, slug, district, *, sold_med, psm, last12, n, ask, dom, avail, stuck, uo):
    return {
        "city": {"name": city, "series": f"{city} property", "slug": city.lower()},
        "district": district, "slug": slug, "generated_at": "2026-06-11",
        "sold": {"ok": True, "median_price": sold_med, "psm_median": psm,
                 "recency": {"last_12m": last12, "window_months": 24}},
        "listings": {"ok": True, "n": n, "asking_median": ask, "mean_dom": dom,
                     "available_n": avail, "stuck_n": stuck, "under_offer_n": uo},
    }


class FakeStore:
    def __init__(self, models):
        self._m = {m["slug"]: m for m in models}

    def list_blog_posts(self, *a, **k):
        return [{"slug": s} for s in self._m]

    def get_blog_post(self, slug, *a, **k):
        return {"model": self._m[slug]}


MODELS = [
    # city, slug, district, sold_med, psm, last12, n, ask, dom, avail, stuck, uo
    _model("Birmingham", "birmingham-b1", "B1", sold_med=225000, psm=3222, last12=100,
           n=242, ask=180000, dom=148, avail=236, stuck=72, uo=6),    # gap -20, stuck 31
    _model("Leeds", "leeds-ls1", "LS1", sold_med=217262, psm=3400, last12=47,
           n=94, ask=219975, dom=18, avail=91, stuck=2, uo=3),        # gap +1, stuck 2
    _model("London", "london-ec1", "EC1", sold_med=700000, psm=10479, last12=171,
           n=302, ask=700000, dom=79, avail=280, stuck=46, uo=22),    # gap 0, stuck 16
]


class TestAggregation(unittest.TestCase):
    def setUp(self):
        self.study = market_study.gather_study(store_mod=FakeStore(MODELS))

    def test_ok_and_counts(self):
        self.assertTrue(self.study["ok"])
        a = self.study["agg"]
        self.assertEqual(a["n_districts"], 3)
        self.assertEqual(a["n_cities"], 3)
        self.assertEqual(a["total_on_market"], 242 + 94 + 302)
        self.assertEqual(a["total_sales_12m"], 100 + 47 + 171)

    def test_dom_league_order_and_spread(self):
        a = self.study["agg"]
        self.assertEqual(a["dom_slowest"]["district"], "B1")
        self.assertEqual(a["dom_fastest"]["district"], "LS1")
        self.assertEqual(a["dom_spread_x"], round(148 / 18, 1))
        # slowest-first ordering
        order = [r["district"] for r in self.study["by_dom_slowest"]]
        self.assertEqual(order, ["B1", "EC1", "LS1"])

    def test_gap_is_asking_over_sold_not_blended(self):
        # B1 asking 180k vs sold 225k -> -20; never the mean of the two
        b1 = next(r for r in self.study["rows"] if r["district"] == "B1")
        self.assertEqual(b1["asking_gap_pct"], -20)
        self.assertEqual(b1["sold_median"], 225000)
        self.assertEqual(b1["asking_median"], 180000)

    def test_stuck_share_is_of_available(self):
        b1 = next(r for r in self.study["rows"] if r["district"] == "B1")
        self.assertEqual(b1["stuck_share_pct"], round(72 / 236 * 100))

    def test_neg_gap_count(self):
        # only B1 is negative here
        self.assertEqual(self.study["agg"]["neg_gap_count"], 1)

    def test_psm_top_bottom(self):
        a = self.study["agg"]
        self.assertEqual(a["psm_top"]["district"], "EC1")
        self.assertEqual(a["psm_bottom"]["district"], "B1")

    def test_too_few_districts_degrades(self):
        s = market_study.gather_study(store_mod=FakeStore(MODELS[:1]))
        self.assertFalse(s["ok"])
        self.assertIn("districts", s["reason"])

    def test_no_db_degrades_not_raises(self):
        class Dead:
            def list_blog_posts(self, *a, **k):
                raise RuntimeError("db down")
        s = market_study.gather_study(store_mod=Dead())
        self.assertFalse(s["ok"])


class TestRender(unittest.TestCase):
    def setUp(self):
        self.study = market_study.gather_study(store_mod=FakeStore(MODELS))
        self.html = blog.render_study(self.study)

    def test_renders_and_no_template_leak(self):
        self.assertGreater(len(self.html), 5000)
        for bad in ("{a[", "{e(", "{money", "{pct", "lambda", "None days"):
            self.assertNotIn(bad, self.html)

    def test_values_nothing_disclosure_present(self):
        # the page must state plainly that it issues no valuation (no ambiguous "value nothing")
        self.assertIn("issue no valuation", self.html.lower())
        self.assertNotIn("value nothing", self.html.lower())
        self.assertIn("never blended", self.html)

    def test_real_numbers_on_page(self):
        # the slowest centre and spread must appear
        self.assertIn("148 days", self.html)
        self.assertIn("Birmingham", self.html)

    def test_jsonld_valid_and_dataset(self):
        import re
        m = re.search(r'application/ld\+json">(.*?)</script>', self.html, re.S)
        graph = json.loads(m.group(1))["@graph"]
        types = [g.get("@type") for g in graph]
        self.assertIn("Dataset", types)
        self.assertIn("Article", types)

    def test_csv_roundtrip(self):
        import tempfile, os, csv
        d = tempfile.mkdtemp()
        path = os.path.join(d, "x.csv")
        market_study.write_csv(self.study, path)
        with open(path, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        self.assertEqual(len(rows), 1 + 3)            # header + 3 districts
        self.assertEqual(rows[0][0], "city")

    def test_disabled_study_renders_empty(self):
        self.assertEqual(blog.render_study({"ok": False}), "")


if __name__ == "__main__":
    unittest.main()
