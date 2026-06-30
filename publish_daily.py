#!/usr/bin/env python3
"""publish_daily.py - the daily blog pipeline. One district per city, every day.

For each of the ten city series it picks the next district in the rotation (the first one
not yet published; once a city is fully covered it refreshes the stalest report with new
data), gathers that district's OWN live data, renders the sealed SEO/AEO page, persists the
model + HTML to the database, and writes the static file. After all cities it rebuilds the
city hubs, the blog index, the sitemap and the RSS feed from the database.

Solo-operable: one command, fully automated, template-driven. Run it from cron once a day.

  python publish_daily.py                 # publish today's district for every city
  python publish_daily.py --city london   # just one city
  python publish_daily.py --district SE15  # one specific district (manual / sample)
  python publish_daily.py --rebuild        # rebuild hubs/index/sitemap/rss only (no fetch)

Output tree (served by server.py):
  site/blog/index.html                     the network landing page
  site/blog/city/<city>/index.html         each city series hub
  site/blog/<city>-<district>/index.html   each district report
  site/sitemap.xml                         all URLs
  site/blog/feed.xml                       RSS 2.0
"""
import os, sys, json, datetime

import cities
import market_district
import market_study
import blog
import press_review

try:
    import store
except Exception:                                   # pragma: no cover
    store = None

try:
    import blog_images                               # editorial hero + Street View (best-effort)
except Exception:                                   # pragma: no cover
    blog_images = None

HERE = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.environ.get("BLOG_SITE_DIR", os.path.join(HERE, "site"))
BLOG_DIR = os.path.join(SITE_DIR, "blog")
CACHE_DIR = os.path.join(HERE, "cache")

# the composite hero that fronts the index + the cross-city study (one UK skyline, not a
# single city). Generated once in a network-ok phase; reused everywhere else by filesystem.
UK_HERO_SLUG = "uk-city-centre"
UK_HERO_NAME = "the United Kingdom"
_UK_HERO_PROMPT = (
    "A refined editorial illustration combining the iconic skylines of several major UK "
    "cities - London, Manchester, Birmingham, Leeds - into one continuous panoramic city "
    "centre at dusk, for the masthead of a serious UK property research index. Flat vector "
    "poster style with clean architectural line work and subtle texture. Strict colour "
    "palette: deep navy (#0e2747) sky and buildings, warm gold (#d89a32) window and accent "
    "lights, muted teal-green (#15807f) highlights, cream (#f6f3ec) negative space. Calm, "
    "authoritative, premium, understated. Wide letterbox composition. Absolutely no text, no "
    "words, no logos, no watermarks, no people. It must read as a tasteful illustration, not "
    "a photograph.")

_HERO_SOURCE = getattr(blog_images, "HERO_SRC", "Editorial illustration") if blog_images else "Editorial illustration"


def _hero_dict(slug, caption):
    """Pure, no-network hero descriptor for a _shell page. Returns {url, caption, source} when
    cache/blog_hero_<slug>.jpg already exists on disk, else None. Used inside rebuild_indices,
    which is 'no fetch' by contract - the image is generated elsewhere (run/backfill); here we
    only point the render at a file that is already there."""
    name = f"blog_hero_{slug}.jpg"
    path = os.path.join(CACHE_DIR, name)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return {"url": "/img/" + name, "caption": caption, "source": _HERO_SOURCE}
    return None


def _cover_dict(city_slug):
    """Pure, no-network COVER descriptor for a publication card on the index/hub. Prefers the
    real cached Pexels city photograph (cache/blog_area_<slug>.jpg, with its attribution sidecar
    blog_area_<slug>.json), and falls back to the cached editorial hero illustration; None if
    neither is on disk. Reads only the filesystem - rebuild_indices is 'no fetch' by contract,
    so the photo is fetched at publish/backfill time (blog_images.attach) and here we only point
    the card at a file already present. Returns {url, alt, photographer, photographer_url,
    photo_url, ...} so the licence attribution rides with the image."""
    area = f"blog_area_{city_slug}.jpg"
    apath = os.path.join(CACHE_DIR, area)
    if os.path.exists(apath) and os.path.getsize(apath) > 0:
        cover = {"url": "/img/" + area}
        try:
            with open(os.path.join(CACHE_DIR, f"blog_area_{city_slug}.json"),
                      "r", encoding="utf-8") as fh:
                cover.update(json.load(fh))
        except Exception:
            pass
        return cover
    h = _hero_dict(city_slug, "")
    return {"url": h["url"], "alt": h.get("caption") or ""} if h else None


def _topic_cover(topic_slug):
    """Pure, no-network COVER descriptor for a topical blog page."""
    name = f"blog_topic_{topic_slug}.jpg"
    apath = os.path.join(CACHE_DIR, name)
    if os.path.exists(apath) and os.path.getsize(apath) > 0:
        cover = {"url": "/img/" + name}
        try:
            with open(os.path.join(CACHE_DIR, f"blog_topic_{topic_slug}.json"),
                      "r", encoding="utf-8") as fh:
                cover.update(json.load(fh))
        except Exception:
            pass
        return cover
    return None


def _nav():
    """Enriched city-navigator data for blog._citynav: each city dict plus `nav_districts`,
    the list of its PUBLISHED districts as {code, slug, url} in the city's own ranked order.
    Only published districts are listed, so every navigator chip is a real report and never
    404s. Pure DB read, no network. Falls back to plain cities.CITIES (no nav_districts, the
    navigator then shows each city's 'publishes soon' note) when there is no store."""
    if not store:
        return cities.CITIES
    published = {}
    for r in store.list_blog_posts():
        published.setdefault(r["city_slug"], {})[r["district"]] = r["slug"]
    nav = []
    for c in cities.CITIES:
        pub = published.get(c["slug"], {})
        nd = [{"code": d, "slug": pub[d], "url": blog.post_url(pub[d])}
              for d in c["districts"] if d in pub]
        nav.append({**c, "nav_districts": nd})
    return nav


def _topic_specs(commentary_pages):
    """Editorial page catalog for the blog's topical content types."""
    comm_links = []
    for page in (commentary_pages or []):
        city = page.get("city") or {}
        url = page.get("url") or ""
        if city and url:
            comm_links.append({"label": f"{city.get('name') or city.get('series') or 'City'} headlines vs the record",
                               "url": url})
    if not comm_links:
        comm_links = [{"label": "Blog index", "url": blog.SITE + blog.BLOG_BASE + "/"}]

    return [
        {
            "slug": "publication-analysis",
            "url": blog.SITE + blog._topic_url("publication-analysis"),
            "title": "Headlines vs the record",
            "h1": "Headlines vs the record",
            "series": "Market headlines",
            "kicker": "Headline check",
            "summary": "Check newsletters, blogs and market headlines against the local sold record before trusting the market story.",
            "stats": [("Source", "Original claim"), ("Record", "Sold prices"), ("Context", "Live listings")],
            "bullets": [
                {"title": "Read the source", "body": "Open the original article or newsletter first."},
                {"title": "Check the local sold record", "body": "See how the claim lines up with the numbers already on this site."},
                {"title": "Stay neutral", "body": "No takedown, no value judgement, no hidden valuation."},
            ],
            "steps": [
                "Open the city page for the market you are reading about.",
                "Check the original claim against the local sold record and live listings.",
                "Use the district reports when you want the raw numbers.",
            ],
            "links": comm_links,
            "cta_lead": "Read the claim, then open the local record.",
            "cta": [
                {"label": "See all reports", "url": blog.SITE + blog.BLOG_BASE + "/", "class": "cta-ghost"},
                {"label": "Get your address value on Telegram", "url": blog.BOT, "class": "cta-tg", "rel": True},
            ],
            "faqs": [
                ("Is this a takedown?", "No. It is a local record check: the claim on one side, the numbers on the other."),
                ("Where do the figures come from?", "From the city's stored district models and the same sold and listing data already shown elsewhere on the site."),
            ],
            "queries": ["newspaper desk", "laptop report", "editorial workspace"],
            "cover": _topic_cover("publication-analysis"),
        },
        {
            "slug": "compare-houses",
            "url": blog.SITE + blog._topic_url("compare-houses"),
            "title": "Compare homes side by side",
            "h1": "Compare homes",
            "series": "Home comparison",
            "kicker": "Compare homes",
            "summary": "Side-by-side comparison for homes, with sold prices, asking prices, pace and yield in one place.",
            "stats": [("Sold", "Evidence"), ("Asking", "Context"), ("Pace", "Market speed")],
            "bullets": [
                {"title": "On the sold record", "body": "Compare homes on real completed sales, price per square metre, pace and yield - not asking prices."},
                {"title": "Area by area", "body": "Open the report for each district on your shortlist and read them side by side."},
                {"title": "Buyer chooses the winner", "body": "The evidence lays the options out; the buyer picks the winner."},
            ],
            "steps": [
                "Open the city or district report for the areas on your shortlist.",
                "Read each home against the local sold record - price, size and price per square metre.",
                "Get a fast address value check on Telegram for the home you are weighing up.",
            ],
            "links": [
                {"label": "UK city-centre index", "url": blog.SITE + blog.BLOG_BASE + "/uk-city-centre-index/"},
                {"label": "All reports", "url": blog.SITE + blog.BLOG_BASE + "/"},
                {"label": "Get an address value on Telegram", "url": blog.BOT},
            ],
            "cta_lead": "When a buyer is choosing between options, start with the sold record for each area, then check the specific address.",
            "cta": [
                {"label": "Get your address value on Telegram", "url": blog.BOT, "class": "cta-tg", "rel": True},
                {"label": "See all reports", "url": blog.SITE + blog.BLOG_BASE + "/", "class": "cta-ghost"},
            ],
            "faqs": [
                ("How do I compare homes here?", "Open the district report for each area on your shortlist and read them against the same sold record, then check the specific address on Telegram."),
                ("What should I compare?", "Anything that changes the decision: sold price, size, price per square metre, market pace and yield."),
            ],
            "queries": ["calculator desk house", "property comparison", "blueprint notebook"],
            "cover": _topic_cover("compare-houses"),
        },
        {
            "slug": "alerts-watchlists",
            "url": blog.SITE + blog._topic_url("alerts-watchlists"),
            "title": "Alerts and watchlists",
            "h1": "Alerts and watchlists",
            "series": "Market alerts",
            "kicker": "Watchlist",
            "summary": "Price-drop alerts, watchlists and market pulses for keeping track of a place after the first answer.",
            "stats": [("Drops", "Price changes"), ("Stock", "New listings"), ("Rates", "Mortgage moves")],
            "bullets": [
                {"title": "Price-drop alerts", "body": "Useful when a buyer is waiting for the right entry point."},
                {"title": "Market pulse", "body": "A recurring check keeps the picture fresh without another search."},
                {"title": "Mortgage-rate-change alerts", "body": "Track rate changes beside the property search."},
            ],
            "steps": [
                "Start with the free answer.",
                "Save the area or property to watch.",
                "Return when the market changes instead of starting the search again.",
            ],
            "links": [
                {"label": "All reports", "url": blog.SITE + blog.BLOG_BASE + "/"},
                {"label": "London house prices", "url": blog.SITE + blog.hub_url("london")} ,
                {"label": "Manchester house prices", "url": blog.SITE + blog.hub_url("manchester")},
            ],
            "cta_lead": "Use alerts and watchlists when a buyer is not ready to stop tracking the market.",
            "cta": [
                {"label": "Get your address value on Telegram", "url": blog.BOT, "class": "cta-tg", "rel": True},
                {"label": "See all reports", "url": blog.SITE + blog.BLOG_BASE + "/", "class": "cta-ghost"},
            ],
            "faqs": [
                ("Why set alerts?", "Because prices and availability change."),
                ("What gets alerted?", "Price changes, watchlist hits and the next reason to come back."),
            ],
            "queries": ["phone notification", "mobile dashboard", "property app"],
            "cover": _topic_cover("alerts-watchlists"),
        },
        {
            "slug": "market-friction",
            "url": blog.SITE + blog._topic_url("market-friction"),
            "title": "Why a home is not selling",
            "h1": "Why a home is not selling",
            "series": "Stuck listings",
            "kicker": "Stuck listing help",
            "summary": "Down-valued properties, stalled listings and broker or lender friction - the next step should be clear.",
            "stats": [("Sold", "Evidence"), ("Asking", "Context"), ("Pace", "Days on market")],
            "bullets": [
                {"title": "Why is this home not selling?", "body": "Use the sold record against the asking story and the market pace."},
                {"title": "Down-valued property", "body": "A lender or valuation gap needs comparison, not spin."},
                {"title": "Broker / solicitor / surveyor friction", "body": "Turn the problem into a compare-options route."},
            ],
            "steps": [
                "Start with the fast valuation or comparison path.",
                "Check the sold evidence, asking price and days on market.",
                "Use the partner-intro path only when the decision is ready.",
            ],
            "links": [
                {"label": "UK city-centre index", "url": blog.SITE + blog.BLOG_BASE + "/uk-city-centre-index/"},
                {"label": "All reports", "url": blog.SITE + blog.BLOG_BASE + "/"},
                {"label": "Get an address value on Telegram", "url": blog.BOT},
            ],
            "cta_lead": "For a stuck listing, down valuation or broker/lender issue, start with the area's sold record, then check the specific address.",
            "cta": [
                {"label": "Get your address value on Telegram", "url": blog.BOT, "class": "cta-tg", "rel": True},
                {"label": "See all reports", "url": blog.SITE + blog.BLOG_BASE + "/", "class": "cta-ghost"},
            ],
            "faqs": [
                ("Is this advice?", "No. It is the evidence and the next step. The decision stays with the buyer or seller."),
                ("What matters first?", "Start with the sold evidence, the asking price and the time on market."),
            ],
            "queries": ["for sale sign", "estate agent office", "house keys"],
            "cover": _topic_cover("market-friction"),
        },
    ]


def ensure_uk_hero():
    """Generate (once) the composite UK index/study hero. Network-ok phases only. Best-effort."""
    if blog_images is None:
        return None
    try:
        return blog_images.ensure_city_hero(UK_HERO_SLUG, UK_HERO_NAME, prompt=_UK_HERO_PROMPT)
    except Exception:
        return None


def _write(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


def _pick_district(city):
    """Next district for a city: first unpublished in ranked order, else the stalest
    existing report (refresh). Deterministic given the database state."""
    published = store.published_districts(city["slug"]) if store else []
    nxt = cities.next_district(city, published)
    if nxt:
        return nxt, "new"
    # fully covered - refresh the stalest
    if store:
        s = store.stalest_post(city["slug"])
        if s and s.get("district"):
            return s["district"], "refresh"
    # no DB / nothing published yet -> start at the top
    return city["districts"][0], "new"


def _siblings(city, current):
    """PUBLISHED sibling districts in the same city, as (district, slug) pairs. Only ever
    links to pages that exist, so the internal mesh never 404s. The ranked list is NOT a
    fallback here - an unpublished district has no page to link to. As the rotation
    publishes more districts, rebuild_indices re-renders earlier pages so their sibling
    lists catch up (the models are cached, so that costs no API calls)."""
    if store:
        rows = store.list_blog_posts(city["slug"])
        return [(r["district"], r["slug"]) for r in rows if r["district"] != current][:8]
    return []


def publish_one(city, district, *, key=None):
    """Gather, render and persist one district report. Returns a result dict."""
    district = district.upper()
    model = market_district.gather(city, district, key=key)
    if blog_images is not None:
        try:
            blog_images.attach(model)               # adds model['hero'] / ['area_photo'] in place
            blog_images.attach_charts(model)         # generates chart PNGs -> model['charts']
        except Exception:
            pass                                     # imagery/charts are decorative; never block a publish
    sold = model.get("sold") or {}
    listings = model.get("listings") or {}
    sold_ok = sold.get("ok")
    listings_ok = listings.get("ok")
    # District-level transaction data is the product. The HPI is a CITY-REGIONAL average
    # (e.g. "City of Edinburgh"), not a figure for this outcode, so it cannot carry a page
    # on its own: a district with no recorded sales AND no live listings has nothing real to
    # headline and would print "n/a" for the core figure (the EH2 self-sabotage). Skip it
    # honestly rather than publish an empty "property intel" report.
    if not (sold_ok or listings_ok):
        # Authoritative confirmed-absence beats a provider error. When the FREE HM Land Registry
        # register has been queried across every member postcode of an England/Wales district and
        # holds no residential sale (e.g. B2, an all-commercial city core), that is definitive:
        # asking-price listings alone cannot headline a sold-evidence page, so a listings
        # provider-error does NOT earn a perpetual retry. Skip it honestly as a non-residential
        # district rather than deferring forever as 'feed down'. (Scotland/NI never set this flag,
        # so they fall through to the defer path and keep retrying PropertyData, their only source.)
        if sold.get("confirmed_absent"):
            return {"ok": False, "district": district,
                    "reason": "no residential sales in the official HM Land Registry register for "
                              "this district, confirmed across all member postcodes via the free "
                              "register - not a residential market, skipped honestly"}
        # Scotland / Northern Ireland are not in the HM Land Registry Price Paid register, which
        # is the only sold source we use (the paid vendors that once carried Registers of
        # Scotland sales are retired). This is not an outage and not absence - it is a coverage
        # boundary of the free data - so say that exactly and skip honestly; there is nothing to
        # retry until a free RoS/NI register is wired in.
        if sold.get("uncovered"):
            return {"ok": False, "district": district, "uncovered": True,
                    "reason": "this district is outside England & Wales, so it is not in the free "
                              "HM Land Registry Price Paid register; no free sold source covers it "
                              "yet - skipped honestly, NOT recorded as a market without sales"}
        # A query ERROR is never logged as "this district has no data". market_district tries the
        # local/VPS register mirror and then the direct SPARQL enumeration before giving up, so
        # reaching here on an error means the free register query itself failed transiently
        # (SPARQL endpoint or Postcodes.io unreachable) - defer and retry on the next run, do NOT
        # record the district as confirmed-empty.
        errored = bool(sold.get("errored") or listings.get("errored"))
        if errored:
            return {"ok": False, "district": district, "retryable": True,
                    "reason": "free HM Land Registry register query failed (transient) - deferred, "
                              "will retry; NOT recorded as no-data"}
        return {"ok": False, "district": district,
                "reason": "no district-level transaction data after widening to 120 months "
                          "(confirmed absence, sold genuinely empty on the free register)"}

    sibs = _siblings(city, district)
    html_out = blog.render_post(model, siblings=sibs, cities_nav=_nav())
    slug = model["slug"]
    desc = blog._answer_paragraph(model)
    headline = (model.get("sold") or {}).get("median_price")

    if store:
        store.record_blog_post(
            slug, city_slug=city["slug"], district=district,
            series=city["series"], title=f"{district} property market report",
            description=desc[:300], headline_price=headline,
            model=model, html=html_out, generated_at=model["generated_at"])

    path = _write(os.path.join(BLOG_DIR, slug, "index.html"), html_out)
    return {"ok": True, "district": district, "slug": slug, "path": path,
            "median": headline, "sold": sold_ok, "bytes": len(html_out)}


def _posts_for_hub(city):
    """Hub rows from the DB (newest first), or [] if no DB."""
    if not store:
        return []
    rows = store.list_blog_posts(city["slug"])
    return [{"district": r["district"], "slug": r["slug"],
             "generated_at": r.get("generated_at", ""),
             "headline_price": r.get("headline_price")} for r in rows]


def refresh_post_pages():
    """Re-render every published district page from its STORED model, so each page's
    internal-link mesh reflects all siblings published so far. Costs no API calls (the
    model is cached in the DB); keeps the network fully connected as it grows. Updates
    both the stored HTML (zero drift with the served page) and the static file."""
    if not store:
        return []
    nav = _nav()
    written = []
    for meta in store.list_blog_posts():
        post = store.get_blog_post(meta["slug"], with_model=True)
        model = post.get("model") if post else None
        if not model:
            continue
        city = cities.CITY_BY_SLUG.get(model["city"]["slug"])
        if not city:
            continue
        sibs = _siblings(city, model["district"])
        html_out = blog.render_post(model, siblings=sibs, cities_nav=nav)
        store.record_blog_post(
            meta["slug"], city_slug=city["slug"], district=model["district"],
            series=city["series"], title=meta.get("title"),
            description=meta.get("description"), headline_price=meta.get("headline_price"),
            model=model, html=html_out, generated_at=meta.get("generated_at"))
        written.append(_write(os.path.join(BLOG_DIR, meta["slug"], "index.html"), html_out))
    return written


def backfill_images():
    """Attach the editorial hero + Street View photo to every already-published district by
    loading its STORED model, fetching/caching its images (the only network here), then
    re-storing the model and re-rendering. One-off catch-up for pages published before the
    image feature existed; future publishes attach images at publish time. Best-effort per
    page - a page whose images fail simply re-renders unchanged."""
    if not store or blog_images is None:
        return []
    if ensure_uk_hero():
        print(f"  [img ] {UK_HERO_SLUG:<22} hero (index + study)")
    nav = _nav()
    written = []
    for meta in store.list_blog_posts():
        post = store.get_blog_post(meta["slug"], with_model=True)
        model = post.get("model") if post else None
        if not model:
            continue
        city = cities.CITY_BY_SLUG.get(model["city"]["slug"])
        if not city:
            continue
        try:
            blog_images.attach(model)
        except Exception:
            pass
        sibs = _siblings(city, model["district"])
        html_out = blog.render_post(model, siblings=sibs, cities_nav=nav)
        store.record_blog_post(
            meta["slug"], city_slug=city["slug"], district=model["district"],
            series=city["series"], title=meta.get("title"),
            description=meta.get("description"), headline_price=meta.get("headline_price"),
            model=model, html=html_out, generated_at=meta.get("generated_at"))
        written.append(_write(os.path.join(BLOG_DIR, meta["slug"], "index.html"), html_out))
        has_hero = "hero" if model.get("hero") else "----"
        has_photo = "photo" if model.get("area_photo") else "-----"
        print(f"  [img ] {meta['slug']:<22} {has_hero} {has_photo}")
    for spec in _topic_specs([]):
        if blog_images is None:
            break
        try:
            photo = blog_images.ensure_topic_photo(spec["slug"], spec["title"], spec.get("queries") or [])
        except Exception:
            photo = None
        if photo:
            print(f"  [img ] topic:{spec['slug']:<14} photo")
    return written


def build_study(study=None, *, hero=None):
    """Build the cross-district data study page + its public CSV from the stored models.
    Best-effort: returns [] when there is not enough data, never blocks the rebuild."""
    if not store:
        return []
    if study is None:
        study = market_study.gather_study(store_mod=store)
    if not study.get("ok"):
        print(f"  [skip] study: {study.get('reason')}")
        return []
    written = []
    written.append(_write(os.path.join(BLOG_DIR, study["slug"], "index.html"),
                          blog.render_study(study, cities_nav=_nav(), hero=hero)))
    written.append(market_study.write_csv(study, os.path.join(SITE_DIR, study["csv"])))
    a = study["agg"]
    print(f"  [ok ] study: {a['n_districts']} districts / {a['n_cities']} cities, "
          f"{len(study['rows'])} rows -> CSV")
    return written


def _build_commentary(city, nav, hero=None):
    """Render a city's press fact-check page from the FROZEN claims block + the city's own
    stored district models. No fetch: claims are captured out of band into press_review.json;
    the snapshot reuses market_study._row_from_model so its figures match the rest of the
    network exactly. Returns the HTML, or "" when there is nothing honest to publish (no
    frozen claims, or fewer than three districts with a sold basis)."""
    if not store:
        return ""
    block = press_review.load(city["slug"])
    if not block.get("claims"):
        return ""
    snap = press_review.city_snapshot(city["slug"], store_mod=store)
    if not snap.get("ok"):
        print(f"  [skip] commentary {city['slug']}: {snap.get('reason')}")
        return ""
    html_out = blog.render_commentary(city, snap, block, cities_nav=nav, hero=hero)
    if html_out:
        print(f"  [ok ] commentary {city['slug']}: {len(block['claims'])} claims / "
              f"{snap['n_districts']} districts")
    return html_out


def rebuild_indices():
    """Re-render the post pages (so their mesh is current), then rebuild every hub, the
    index, the sitemap and the RSS feed from the database."""
    written = list(refresh_post_pages())
    study = market_study.gather_study(store_mod=store) if store else {"ok": False}
    # hero descriptors are pure filesystem checks (no fetch) - the images themselves are
    # generated in run()/backfill_images(). Index + study share the composite UK hero; each
    # city hub reuses its own city hero already cached by the district publishes.
    uk_hero = _hero_dict(UK_HERO_SLUG, "UK city centres - editorial illustration")
    study_written = build_study(study, hero=uk_hero)
    written += study_written
    nav = _nav()
    by_city = []
    commentary_pages = []
    for city in cities.CITIES:
        posts = _posts_for_hub(city)
        # Attach the cached cover photo (Pexels city photo, hero illustration fallback) so
        # the index cards carry a real image. Pure filesystem read, no fetch (#42).
        city = {**city, "cover": _cover_dict(city["slug"])}
        by_city.append((city, posts))
        hub_hero = _hero_dict(city["slug"], f"{city['name']} - editorial illustration")

        # Press fact-check page ("headlines vs the sold record"): rendered only when we hold
        # both a frozen claims block (captured out of band - no fetch here) AND a real
        # snapshot of this city's own stored district models. Honest absence otherwise. Built
        # before the hub so the hub can link it with a banner when it exists.
        commentary_html = _build_commentary(city, nav, hub_hero)
        commentary_url = None
        if commentary_html:
            slug = f"{city['slug']}-market-commentary"
            written.append(_write(os.path.join(BLOG_DIR, slug, "index.html"), commentary_html))
            commentary_url = blog._commentary_url(city["slug"])
            commentary_pages.append({"city": city, "url": commentary_url})

        hub = blog.render_city_hub(city, posts, cities_nav=nav, hero=hub_hero,
                                   commentary_url=commentary_url)
        written.append(_write(os.path.join(BLOG_DIR, "city", city["slug"], "index.html"), hub))

    topic_pages = _topic_specs(commentary_pages)
    for spec in topic_pages:
        topic_html = blog.render_topic_page(spec, cities_nav=nav, hero=spec.get("cover"))
        written.append(_write(os.path.join(BLOG_DIR, spec["slug"], "index.html"), topic_html))

    idx = blog.render_index(by_city, cities_nav=nav,
                            featured_study=study if study.get("ok") else None,
                            hero=uk_hero,
                            commentary_pages=commentary_pages,
                            content_pages=topic_pages)
    written.append(_write(os.path.join(BLOG_DIR, "index.html"), idx))

    # sitemap: index + hubs + every district post + the data study + topic pages
    urls = [(blog.BLOG_BASE + "/", datetime.date.today().isoformat())]
    if study_written:
        urls.append((blog.BLOG_BASE + "/" + market_study.STUDY_SLUG + "/",
                     datetime.date.today().isoformat()))
    for city, posts in by_city:
        urls.append((blog.hub_url(city["slug"]), datetime.date.today().isoformat()))
        for p in posts:
            urls.append((blog.post_url(p["slug"]), p.get("generated_at")))
    for cp in commentary_pages:
        urls.append((cp["url"], datetime.date.today().isoformat()))
    for spec in topic_pages:
        urls.append((blog.SITE + blog._topic_url(spec["slug"]), datetime.date.today().isoformat()))
    written.append(_write(os.path.join(SITE_DIR, "sitemap.xml"), blog.build_sitemap(urls)))

    # rss: newest posts across the whole network
    all_posts = store.list_blog_posts(limit=60) if store else []
    items = [{"title": p.get("title") or f"{p['district']} report",
              "slug": p["slug"], "description": p.get("description", ""),
              "date": p.get("generated_at", "")} for p in all_posts]
    written.append(_write(os.path.join(BLOG_DIR, "feed.xml"), blog.build_rss(items)))

    # Always-on SEO/AEO gate: audit the exact network we just rebuilt. Loud but non-fatal
    # here (a transient soft issue must not nuke the daily publish); the standalone
    # `python seo_audit.py --strict` exits non-zero for a hard pre-publish gate.
    try:
        import seo_audit
        findings = audit_network()
        errs, warns = seo_audit.summarize(findings)
        print(f"SEO/AEO audit: {errs} error(s), {warns} warning(s)")
        for x in findings:
            if x.level == "ERROR":
                print(f"  {x}")
    except Exception as ex:  # pragma: no cover - audit must never break a publish
        print(f"SEO/AEO audit skipped: {ex}")
    return written


def audit_network():
    """Render every blog surface from the STORED models (no network, no writes) and run the
    SEO/AEO audit over the exact HTML the templates produce, plus the on-disk sitemap and
    feed. Returns a flat list of seo_audit.Finding. This is the single entry point the CLI
    and the rebuild tail share, so 'the checks' are the blog's own machinery, every time."""
    import seo_audit
    findings = []
    if not store:
        return findings
    nav = _nav()
    for meta in store.list_blog_posts():
        post = store.get_blog_post(meta["slug"], with_model=True)
        model = post.get("model") if post else None
        if not model:
            continue
        city = cities.CITY_BY_SLUG.get(model["city"]["slug"])
        if not city:
            continue
        sibs = _siblings(city, model["district"])
        html_out = blog.render_post(model, siblings=sibs, cities_nav=nav)
        findings.extend(seo_audit.audit_post(model, html_out))
    by_city = []
    for city in cities.CITIES:
        posts = _posts_for_hub(city)
        city = {**city, "cover": _cover_dict(city["slug"])}
        by_city.append((city, posts))
        hub = blog.render_city_hub(city, posts, cities_nav=nav)
        findings.extend(seo_audit.audit_hub(city, posts, hub))
    commentary_pages = []
    for city in cities.CITIES:
        commentary_html = _build_commentary(city, nav, None)
        if commentary_html:
            commentary_pages.append({"city": city, "url": blog._commentary_url(city["slug"])})
    topic_pages = _topic_specs(commentary_pages)
    for spec in topic_pages:
        topic_html = blog.render_topic_page(spec, cities_nav=nav, hero=spec.get("cover"))
        findings.extend(seo_audit.audit_html(topic_html, f"topic:{spec['slug']}",
                                             required_types=["Article", "BreadcrumbList"],
                                             answer_words=(15, 110)))
    idx = blog.render_index(by_city, cities_nav=nav, content_pages=topic_pages,
                            commentary_pages=commentary_pages)
    findings.extend(seo_audit.audit_index(by_city, idx))
    study = market_study.gather_study(store_mod=store)
    if study.get("ok"):
        study_html = blog.render_study(study, cities_nav=nav)
        findings.extend(seo_audit.audit_study(study_html))
    sm_path = os.path.join(SITE_DIR, "sitemap.xml")
    if os.path.exists(sm_path):
        with open(sm_path, encoding="utf-8") as fh:
            findings.extend(seo_audit.audit_sitemap(fh.read()))
    feed_path = os.path.join(BLOG_DIR, "feed.xml")
    if os.path.exists(feed_path):
        with open(feed_path, encoding="utf-8") as fh:
            findings.extend(seo_audit.audit_rss(fh.read()))
    return findings


def run(city_slugs=None, *, key=None):
    """Publish one district for each named city (default: all), then rebuild indices."""
    targets = ([cities.CITY_BY_SLUG[s] for s in city_slugs if s in cities.CITY_BY_SLUG]
               if city_slugs else cities.CITIES)
    results = []
    for city in targets:
        district, mode = _pick_district(city)
        res = publish_one(city, district, key=key)
        res["mode"] = mode
        res["city"] = city["name"]
        results.append(res)
        tag = "ok " if res.get("ok") else "SKIP"
        extra = (f"median {res.get('median')}, {res.get('bytes',0):,}B"
                 if res.get("ok") else res.get("reason"))
        print(f"  [{tag}] {city['series']:<26} {district:<5} ({mode}) -> {extra}")
    if ensure_uk_hero():
        print(f"  [img ] {UK_HERO_SLUG:<22} hero (index + study)")
    written = rebuild_indices()
    print(f"rebuilt {len(written)} index/hub/sitemap/feed files")
    return results


def main():
    args = sys.argv[1:]
    if "--rebuild" in args:
        w = rebuild_indices()
        print(f"rebuilt {len(w)} files (no fetch)")
        return
    if "--images" in args:
        w = backfill_images()
        print(f"backfilled images on {len(w)} district pages")
        rebuild_indices()
        return
    if "--district" in args:
        d = args[args.index("--district") + 1].upper()
        city = cities.city_of_district(d)
        if not city:
            sys.exit(f"unknown district {d}")
        res = publish_one(city, d)
        print(json.dumps({k: v for k, v in res.items() if k != "html"}, indent=2))
        rebuild_indices()
        return
    city_slugs = None
    if "--city" in args:
        city_slugs = [args[args.index("--city") + 1].lower()]
    print(f"publish_daily {datetime.date.today().isoformat()} "
          f"-> {len(city_slugs) if city_slugs else len(cities.CITIES)} city/cities")
    run(city_slugs)


if __name__ == "__main__":
    main()
