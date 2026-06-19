import unittest

import reddit_intel


class RedditIntelLocalityTests(unittest.TestCase):
    def test_se15_filters_waltham_forest_thread(self):
        terms = reddit_intel._local_terms("SE15", "SE15 6JH")
        threads = [
            {"title": "Property hunt in East London - Waltham Forest is insane", "quote": "Leyton to Walthamstow and Highams Park prices are insane"},
            {"title": "Local advice needed - Peckham SE15", "quote": "Cronin Street and Nunhead nearby"},
        ]
        kept = reddit_intel._filter_local_threads(threads, terms)
        self.assertEqual([t["title"] for t in kept], ["Local advice needed - Peckham SE15"])

    def test_whitechapel_filters_stratford_thread(self):
        terms = reddit_intel._local_terms("Whitechapel", "E1 1AA")
        threads = [
            {"title": "Stratford property market is wild", "quote": "E15 viewings and Olympic Park flats"},
            {"title": "Whitechapel E1 buying advice", "quote": "Aldgate and Stepney sold prices"},
        ]
        kept = reddit_intel._filter_local_threads(threads, terms)
        self.assertEqual([t["title"] for t in kept], ["Whitechapel E1 buying advice"])

    def test_broad_london_is_not_a_local_match(self):
        terms = reddit_intel._local_terms("SE15", "SE15 6JH")
        self.assertNotIn("london", terms)
        threads = [{"title": "London property market", "quote": "Prices and viewings across London"}]
        self.assertEqual(reddit_intel._filter_local_threads(threads, terms), [])


if __name__ == "__main__":
    unittest.main()
