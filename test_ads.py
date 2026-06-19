#!/usr/bin/env python3
"""Offline tests for ads.py + the blog ad renderers - no network, no DB.

Two things are proven here. First, the targeting in ads.py: an inventory file books creatives
onto named surfaces/positions, inactive or malformed entries are dropped, and nothing shows
when the file is absent. Second, and more important, the COMPLIANCE the renderer enforces:
every paid unit carries the 'Advertisement'/'Sponsored' label (UK ASA / CAP) and every paid
outbound link is forced to rel='sponsored nofollow noopener' (Google paid-link policy) - and
the 'listings to watch' disclosure flips to admit a paid card the moment one is present. Those
are stamped in blog.py, so config can book a slot but can never suppress the label or the rel."""
import json
import os
import tempfile
import unittest

import ads
import blog


def _write_inventory(data):
    """Point ads at a temp inventory file and clear its cache. Returns the path."""
    d = tempfile.mkdtemp()
    path = os.path.join(d, "ads.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    ads.ADS_FILE = path
    ads.reset_cache()
    return path


def _empty_inventory():
    ads.ADS_FILE = os.path.join(tempfile.mkdtemp(), "missing.json")
    ads.reset_cache()


BOOKED = {
    "slots": [
        {"id": "acme", "advertiser": "Acme", "active": True,
         "surfaces": ["district:default", "study"], "positions": ["leaderboard"],
         "headline": "Fee-free remortgage", "body": "Whole of market.",
         "url": "https://acme.example/uk", "image": ""},
        {"id": "m1-only", "advertiser": "Northside", "active": True,
         "surfaces": ["district:M1"], "positions": ["mid"],
         "headline": "Manchester conveyancing", "url": "https://northside.example"},
        {"id": "paused", "advertiser": "X", "active": False,
         "surfaces": ["study"], "positions": ["footer"],
         "headline": "no", "url": "https://x.example"},
        {"id": "no-url", "advertiser": "Y", "active": True,
         "surfaces": ["index"], "positions": ["leaderboard"],
         "headline": "broken booking"},
    ],
    "featured_listings": {
        "SE15": {"id": "agentx", "advertiser": "Agent X", "active": True,
                 "headline": "Featured: 2-bed conversion", "price": 525000, "beds": 2,
                 "type": "flat", "address": "Bussey Building, SE15", "portal": "Agent X",
                 "url": "https://agentx.example/listing/123"},
        "N1": {"id": "paused-fl", "advertiser": "Z", "active": False,
               "headline": "paused", "url": "https://z.example"},
    },
}


class TestTargeting(unittest.TestCase):
    def tearDown(self):
        _empty_inventory()

    def test_empty_inventory_shows_nothing(self):
        _empty_inventory()
        self.assertEqual(ads.slots("district", "leaderboard", slug="SE15"), [])
        self.assertIsNone(ads.featured_listing("SE15"))
        self.assertFalse(ads.has_any())

    def test_default_surface_applies_to_every_district(self):
        _write_inventory(BOOKED)
        got = ads.slots("district", "leaderboard", slug="LS1")
        self.assertEqual([s["id"] for s in got], ["acme"])

    def test_district_specific_overrides_position(self):
        _write_inventory(BOOKED)
        # m1-only books district:M1 at 'mid'
        self.assertEqual([s["id"] for s in ads.slots("district", "mid", slug="M1")], ["m1-only"])
        self.assertEqual(ads.slots("district", "mid", slug="LS1"), [])

    def test_inactive_and_urlless_dropped(self):
        _write_inventory(BOOKED)
        self.assertEqual(ads.slots("study", "footer"), [])        # 'paused' is inactive
        self.assertEqual(ads.slots("index", "leaderboard"), [])   # 'no-url' has no url

    def test_featured_listing_active_only(self):
        _write_inventory(BOOKED)
        fl = ads.featured_listing("se15")                         # case-insensitive
        self.assertEqual(fl["id"], "agentx")
        self.assertIsNone(ads.featured_listing("N1"))             # inactive
        self.assertIsNone(ads.featured_listing("XX"))

    def test_has_any_true_when_booked(self):
        _write_inventory(BOOKED)
        self.assertTrue(ads.has_any())

    def test_corrupt_file_degrades_not_raises(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "ads.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{ not json")
        ads.ADS_FILE = path
        ads.reset_cache()
        self.assertEqual(ads.slots("study", "leaderboard"), [])
        self.assertFalse(ads.has_any())


class TestRendererCompliance(unittest.TestCase):
    def tearDown(self):
        _empty_inventory()

    def test_ad_unit_stamps_label_and_rel(self):
        unit = blog._ad_unit(
            {"headline": "Buy now", "body": "x", "advertiser": "Acme",
             "url": "https://acme.example"}, "leaderboard")
        self.assertIn("Advertisement", unit)
        self.assertIn('rel="sponsored nofollow noopener"', unit)
        self.assertIn("https://acme.example", unit)

    def test_ad_slot_empty_when_unbooked(self):
        _empty_inventory()
        self.assertEqual(blog._ad_slot("study", "leaderboard"), "")

    def test_ad_slot_renders_booked(self):
        _write_inventory(BOOKED)
        html = blog._ad_slot("study", "leaderboard")
        self.assertIn("Fee-free remortgage", html)
        self.assertIn("Advertisement", html)
        self.assertIn('rel="sponsored nofollow noopener"', html)


def _watch_model(district, picks):
    return {"district": district, "watch": {"ok": True, "picks": picks}}


PICKS = [
    {"audience": "buyers", "reason_key": "bargain", "price": 300000, "headline": "Keen flat",
     "vs_median_pct": -8, "ref_median": 325000, "dom": 20, "beds": 2, "type": "flat",
     "address": "1 Test St", "portal": "Portal", "link": "https://portal.example/1"},
    {"audience": "sellers", "reason_key": "overpriced", "price": 500000, "headline": "Sitting",
     "vs_median_pct": 12, "ref_median": 445000, "dom": 140, "address": "2 Test St",
     "portal": "Portal", "link": "https://portal.example/2"},
    {"audience": "agents", "reason_key": "stalled", "price": 400000, "headline": "Stalled",
     "dom": 200, "address": "3 Test St", "portal": "Portal", "link": "https://portal.example/3"},
]


class TestWatchDisclosure(unittest.TestCase):
    def tearDown(self):
        _empty_inventory()

    def test_unpaid_disclosure_when_no_sponsor(self):
        _empty_inventory()
        html = blog._watch_section(_watch_model("LS1", PICKS))
        self.assertIn("no placement here is paid for", html)
        self.assertNotIn("Sponsored", html)

    def test_sponsored_card_and_flipped_disclosure(self):
        _write_inventory(BOOKED)
        html = blog._watch_section(_watch_model("SE15", PICKS))
        self.assertIn("Sponsored", html)
        self.assertIn("Bussey Building", html)
        self.assertIn('rel="sponsored nofollow noopener"', html)
        # the disclosure now admits the paid card and no longer claims nothing is paid
        self.assertIn("paid advertisement", html)
        self.assertNotIn("no placement here is paid for", html)


class TestStudyPageCarriesAds(unittest.TestCase):
    """The ad wiring is live on a real rendered page, and absent when unbooked."""

    def setUp(self):
        import market_study

        def _m(city, slug, district, sold, psm, last12, n, ask, dom, avail, stuck, uo):
            return {"city": {"name": city, "series": f"{city} property", "slug": city.lower()},
                    "district": district, "slug": slug, "generated_at": "2026-06-11",
                    "sold": {"ok": True, "median_price": sold, "psm_median": psm,
                             "recency": {"last_12m": last12, "window_months": 24}},
                    "listings": {"ok": True, "n": n, "asking_median": ask, "mean_dom": dom,
                                 "available_n": avail, "stuck_n": stuck, "under_offer_n": uo}}

        class FakeStore:
            def __init__(self, models):
                self._m = {m["slug"]: m for m in models}

            def list_blog_posts(self, *a, **k):
                return [{"slug": s} for s in self._m]

            def get_blog_post(self, slug, *a, **k):
                return {"model": self._m[slug]}

        models = [
            _m("Birmingham", "birmingham-b1", "B1", 225000, 3222, 100, 242, 180000, 148, 236, 72, 6),
            _m("Leeds", "leeds-ls1", "LS1", 217262, 3400, 47, 94, 219975, 18, 91, 2, 3),
            _m("London", "london-ec1", "EC1", 700000, 10479, 171, 302, 700000, 79, 280, 46, 22),
        ]
        self.study = market_study.gather_study(store_mod=FakeStore(models))

    def tearDown(self):
        _empty_inventory()

    def test_no_ads_when_unbooked(self):
        _empty_inventory()
        html = blog.render_study(self.study)
        self.assertNotIn("Advertisement", html)

    def test_ad_present_when_booked(self):
        _write_inventory(BOOKED)
        html = blog.render_study(self.study)
        self.assertIn("Advertisement", html)
        self.assertIn("Fee-free remortgage", html)
        self.assertIn('rel="sponsored nofollow noopener"', html)


if __name__ == "__main__":
    unittest.main()
