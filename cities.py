#!/usr/bin/env python3
"""cities.py - the rotation universe for the daily postcode blog.

Ten top UK cities by residential transaction volume (the user's ranked list). Each
city is a content CATEGORY with a branded series name ("The London Daily", "The
Edinburgh Breakdown", ...) and a ranked list of its real postcode DISTRICTS (outcodes).

The publishing pipeline advances ONE district per city per day, so ten fresh,
city-categorised reports publish daily. When a city's district list is exhausted the
rotation wraps to the start and the oldest report is refreshed with new data - so the
corpus stays live, never stale, and every report is grounded in THAT district's own
transactions (never one city's numbers reused for another - the cardinal data rule).

Nothing here is a market claim. The districts are postcode geography (Royal Mail
outcodes); the regions are the HM Land Registry HPI area names used to pull the real
local index. Every number on a published page comes from a live API for that exact
district, never from this file.
"""

# Each city: the display name, the HM Land Registry HPI region (for the local index),
# the branded series title for its category, a one-line category strapline, and the
# ranked outcodes. Outcodes are ordered by prominence/centrality so the rotation leads
# with the districts people actually search for.
CITIES = [
    {
        "slug": "edinburgh", "name": "Edinburgh", "country": "Scotland",
        "hpi_region": "City of Edinburgh",
        "series": "The Edinburgh Breakdown",
        "strapline": "Daily postcode-by-postcode read on Edinburgh's housing market.",
        "districts": ["EH1", "EH2", "EH3", "EH4", "EH6", "EH7", "EH8", "EH9",
                       "EH10", "EH11", "EH12", "EH16"],
    },
    {
        "slug": "glasgow", "name": "Glasgow", "country": "Scotland",
        "hpi_region": "Glasgow City",
        "series": "The Glasgow Market Brief",
        "strapline": "Daily postcode intelligence across Glasgow's neighbourhoods.",
        "districts": ["G1", "G2", "G3", "G4", "G5", "G11", "G12", "G13",
                       "G20", "G31", "G41", "G42"],
    },
    {
        "slug": "leeds", "name": "Leeds", "country": "England",
        "hpi_region": "Leeds",
        "series": "The Leeds Ledger",
        "strapline": "Daily transaction and price read across Leeds postcodes.",
        "districts": ["LS1", "LS2", "LS4", "LS6", "LS7", "LS8", "LS9",
                       "LS11", "LS12", "LS17", "LS18", "LS27"],
    },
    {
        "slug": "birmingham", "name": "Birmingham", "country": "England",
        "hpi_region": "Birmingham",
        "series": "The Birmingham Bulletin",
        "strapline": "Daily postcode market breakdown for Birmingham.",
        "districts": ["B1", "B2", "B3", "B5", "B12", "B13", "B14", "B15",
                       "B16", "B17", "B23", "B29"],
    },
    {
        "slug": "london", "name": "London", "country": "England",
        "hpi_region": "London",
        "series": "The London Daily",
        "strapline": "A different London postcode, every day, in numbers.",
        # Central London bare outcodes (EC1, EC2, SW1, W1, WC1) were split into sub-districts
        # decades ago and are no longer valid Royal Mail outcodes - Postcodes.io and the free HM
        # Land Registry enumeration both reject them. We publish the real, searchable residential
        # sub-districts instead: EC1V (Clerkenwell), EC2A (Shoreditch edge), SW1P (Westminster),
        # W1H (Marylebone), WC1N (Bloomsbury).
        "districts": ["EC1V", "EC2A", "E1", "E2", "E8", "E14", "N1", "N4", "N7",
                       "SE1", "SE15", "SW1P", "SW4", "SW9", "SW11", "W1H", "W2",
                       "NW1", "NW3", "NW5", "WC1N"],
    },
    {
        "slug": "manchester", "name": "Manchester", "country": "England",
        "hpi_region": "Manchester",
        "series": "The Manchester Monitor",
        "strapline": "Daily postcode-level read on Manchester's housing market.",
        "districts": ["M1", "M2", "M3", "M4", "M8", "M11", "M14", "M15",
                       "M16", "M19", "M20", "M21"],
    },
    {
        "slug": "bristol", "name": "Bristol", "country": "England",
        "hpi_region": "Bristol",
        "series": "The Bristol Brief",
        "strapline": "Daily postcode market intelligence for Bristol.",
        "districts": ["BS1", "BS2", "BS3", "BS4", "BS5", "BS6", "BS7", "BS8",
                       "BS9", "BS16"],
    },
    {
        "slug": "liverpool", "name": "Liverpool", "country": "England",
        "hpi_region": "Liverpool",
        "series": "The Liverpool Ledger",
        "strapline": "Daily postcode breakdown of Liverpool's property market.",
        "districts": ["L1", "L2", "L3", "L4", "L7", "L8", "L15", "L17",
                       "L18", "L19"],
    },
    {
        "slug": "nottingham", "name": "Nottingham", "country": "England",
        "hpi_region": "Nottingham",
        "series": "The Nottingham Note",
        "strapline": "Daily postcode-by-postcode read on Nottingham.",
        "districts": ["NG1", "NG2", "NG3", "NG5", "NG7", "NG8", "NG9", "NG11"],
    },
    {
        "slug": "sheffield", "name": "Sheffield", "country": "England",
        "hpi_region": "Sheffield",
        "series": "The Sheffield Signal",
        "strapline": "Daily postcode market read across Sheffield.",
        "districts": ["S1", "S2", "S3", "S6", "S7", "S8", "S10", "S11", "S17"],
    },
]

CITY_BY_SLUG = {c["slug"]: c for c in CITIES}


def all_targets():
    """Every (city, district) pair in the universe, in rotation order. Used by the
    pipeline to enumerate what can be published."""
    return [(c, dist) for c in CITIES for dist in c["districts"]]


def city_of_district(district):
    """Return the city dict that owns a postcode district (outcode), or None."""
    d = (district or "").upper()
    for c in CITIES:
        if d in c["districts"]:
            return c
    return None


def next_district(city, published):
    """Pick the next district to publish for a city.

    `published` is the set/dict of district outcodes already published for this city
    (any city-scoped lookup the caller has). Returns the first district in the city's
    ranked list that has NOT been published yet; if the city is fully covered, returns
    None so the caller can instead refresh the stalest existing report. Deterministic:
    no randomness, so a resumed/replayed run picks the same next district."""
    have = set(published or [])
    for dist in city["districts"]:
        if dist not in have:
            return dist
    return None


def slug_for(city_slug, district):
    """Canonical URL slug for a district report: '<city>-<district-lower>'.
    e.g. ('london','SE15') -> 'london-se15'. Stable, so the URL never changes."""
    return f"{city_slug}-{(district or '').lower()}"


if __name__ == "__main__":
    tot = sum(len(c["districts"]) for c in CITIES)
    print(f"{len(CITIES)} cities, {tot} districts in the rotation universe")
    for c in CITIES:
        print(f"  {c['series']:28s} {c['name']:11s} {len(c['districts']):2d} districts: "
              f"{', '.join(c['districts'])}")
