#!/usr/bin/env python3
"""ads.py - the blog's paid-placement inventory layer.

The blog is an SEO/AEO asset, so selling space on it has two hard rules that this module
exists to enforce, not merely allow:

  1. Every paid unit is VISIBLY labelled as advertising (UK ASA / CAP Code: marketing must
     be obviously identifiable). The renderer in blog.py stamps the label - config cannot
     suppress it.
  2. Every paid OUTBOUND link carries rel="sponsored nofollow noopener" (Google's paid-link
     policy). A paid dofollow link would risk a manual action against the whole network, so
     the renderer hardcodes the rel - config cannot loosen it.

This module is pure data + targeting: it reads a best-effort inventory file and tells the
renderer which creatives belong on a given surface. It never renders HTML (blog.py does, so
the mandatory label + rel are applied in exactly one place) and never raises into a build.

Inventory file (JSON, path from $BLOG_ADS_FILE or ads.json beside this module):

  {
    "slots": [
      {"id": "acme-q3", "advertiser": "Acme Mortgages", "active": true,
       "surfaces": ["district:default", "study"], "positions": ["leaderboard"],
       "headline": "Fee-free remortgage advice", "body": "Whole-of-market brokers.",
       "url": "https://acme.example/uk", "image": ""},
      ...
    ],
    "featured_listings": {
      "SE15": {"id": "agentx-se15", "advertiser": "Agent X", "active": true,
               "headline": "Featured: 2-bed warehouse conversion",
               "price": 525000, "beds": 2, "type": "flat",
               "address": "Bussey Building, SE15", "portal": "Agent X",
               "url": "https://agentx.example/listing/123"}
    }
  }

Surfaces a slot can target:
  "index"            the /blog landing page
  "study"            the UK city-centre index data study
  "hub:<city_slug>"  a city series hub (e.g. hub:london)
  "district:default" every district report
  "district:<OUT>"  one district report (e.g. district:SE15) - overrides default

Positions (where on the surface): "leaderboard" (top), "mid", "footer".

A featured_listing books the sponsored card in that district's "listings to watch" block.
It renders ALONGSIDE the organic random picks, clearly marked Sponsored, and it flips the
block's disclosure to state that a paid placement is present - so the page never claims to
be unpaid while carrying a paid card."""
import os
import json

ADS_FILE = os.environ.get(
    "BLOG_ADS_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ads.json"))

_CACHE = {"path": None, "data": None}


def _load():
    """Best-effort load of the inventory, cached per (path) for the process. Returns a dict
    with 'slots' and 'featured_listings' always present (empty when the file is absent or
    unreadable). Never raises."""
    if _CACHE["path"] == ADS_FILE and _CACHE["data"] is not None:
        return _CACHE["data"]
    data = {"slots": [], "featured_listings": {}}
    try:
        with open(ADS_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            slots = raw.get("slots")
            fl = raw.get("featured_listings")
            data["slots"] = slots if isinstance(slots, list) else []
            data["featured_listings"] = fl if isinstance(fl, dict) else {}
    except Exception:
        pass
    _CACHE["path"] = ADS_FILE
    _CACHE["data"] = data
    return data


def reset_cache():
    """Drop the cache (tests / hot-reload)."""
    _CACHE["path"] = None
    _CACHE["data"] = None


def _surfaces_for(surface, slug=None):
    """The set of surface tokens a slot may target to appear on this concrete page."""
    keys = {surface}
    if surface == "district":
        keys = {"district:default"}
        if slug:
            keys.add(f"district:{slug.upper()}")
    elif surface == "hub" and slug:
        keys = {f"hub:{slug}"}
    return keys


def slots(surface, position, *, slug=None):
    """Active creatives booked for this surface + position. surface is one of
    'index'|'study'|'district'|'hub'; for district/hub pass slug (outcode / city slug).
    Returns a list of creative dicts (may be empty). Order: file order (booking order)."""
    want = _surfaces_for(surface, slug)
    out = []
    for s in _load()["slots"]:
        if not isinstance(s, dict) or not s.get("active"):
            continue
        if not s.get("url") or not (s.get("headline") or s.get("image")):
            continue
        s_surfaces = set(s.get("surfaces") or [])
        s_positions = set(s.get("positions") or ["leaderboard"])
        if (s_surfaces & want) and position in s_positions:
            out.append(s)
    return out


def featured_listing(outcode):
    """The sponsored 'listings to watch' card booked for this district, or None."""
    if not outcode:
        return None
    fl = _load()["featured_listings"].get(outcode.upper())
    if isinstance(fl, dict) and fl.get("active") and fl.get("url"):
        return fl
    return None


def has_any():
    """True if any active inventory exists at all (used to decide disclosure wording)."""
    d = _load()
    if any(isinstance(s, dict) and s.get("active") for s in d["slots"]):
        return True
    return any(isinstance(v, dict) and v.get("active")
               for v in d["featured_listings"].values())


if __name__ == "__main__":
    d = _load()
    print(f"inventory: {ADS_FILE}")
    print(f"slots: {len(d['slots'])} | featured_listings: {len(d['featured_listings'])}")
    print("study leaderboard:", [s.get('id') for s in slots('study', 'leaderboard')])
