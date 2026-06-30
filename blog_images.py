#!/usr/bin/env python3
"""blog_images.py - real imagery for the daily district reports, generated once and cached.

Two images per report, both honest about what they are:

  * a city HERO - an editorial illustration generated with Gemini (gemini-2.5-flash-image),
    cached per city. It is a stylised cityscape in the brand palette, NEVER a photoreal image
    of a property, and it is captioned as an illustration. It carries no figure and never
    stands in for evidence - it sets the masthead tone, nothing more.
  * an area PHOTO - a real city-centre photograph from Pexels, cached per city (districts
    of a city share it). It is only used when the photo's Pexels alt text genuinely names
    the city, so it can never caption the wrong place as this city (Pexels keyword search
    is loose - a "Nottingham" query surfaces Manchester and Leeds frames). Honest or absent.
    Carries the Pexels licence attribution: photographer name + a link to the photo.

Design rules that keep the blog pure:
  * This module is the ONLY place that touches the network for images. It writes files into
    the server's image cache (served flat at /img/<name>) and returns plain URLs.
  * attach(model) mutates the model to carry model["hero"] / model["area_photo"] as small
    dicts of strings. blog.py render hooks read those keys and emit no network calls, so
    refresh_post_pages() re-renders from the stored model with zero API cost and zero drift.
  * Best-effort throughout: a missing key, a down endpoint or no Street View imagery returns
    None and the report simply renders without that image. Never raises into the pipeline.

CLI:
  python blog_images.py hero london "London"            # generate + cache one city hero
  python blog_images.py cityphoto manchester "Manchester"  # cache one Pexels city photo
  python blog_images.py area london-ec2 51.515 -0.09     # (legacy) cache one Street View
  python blog_images.py selftest                         # report key presence, no network
"""
import os, sys, json, io, base64, urllib.parse, urllib.request, urllib.error

import maps_tools  # _load_env + street_view

try:
    from PIL import Image                            # optional: downscale + JPEG the hero
except Exception:                                   # pragma: no cover
    Image = None

_HERO_MAX_W = 1600        # cap the hero width; a masthead band never needs more
_HERO_QUALITY = 85        # JPEG quality for the dusk-gradient illustration
_AREA_MAX_W = 3840        # area PHOTO: keep it 4K-wide and crisp (city photographs)
_AREA_QUALITY = 88        # area photos carry detail (skylines), so encode a touch higher
_AREA_MIN_W = 1920        # reject sub-HD Pexels sources: only HD/4K originals qualify

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

_GEMINI_MODEL = "gemini-2.5-flash-image"
_GEMINI_ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
                    + _GEMINI_MODEL + ":generateContent")
HERO_SRC = "Editorial illustration generated with Google Gemini (" + _GEMINI_MODEL + ")"
AREA_SRC = "Google Street View"
PEXELS_SRC = "Photograph via Pexels"

# A browser-like UA: the Pexels API sits behind Cloudflare and 403s (error 1010) the
# default urllib agent. The Authorization header is still the real auth.
_PEXELS_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_PEXELS_SEARCH = "https://api.pexels.com/v1/search"
# Words that mark a result as a genuine wide city view (quality preference, applied
# only AFTER the honesty filter that the alt text actually names the city).
_PEXELS_PREFER = ("skyline", "cityscape", "city cent", "aerial", "panoram", "architecture")
# Words that mark a result as the WRONG kind of shot (a close-up, a wall, an interior)
# even when it honestly names the city - demote these so a wide view wins.
_PEXELS_AVOID = ("graffiti", "mural", "wall", "street art", "interior", "indoor",
                 "close-up", "closeup", "close up", "portrait", "statue", "sign",
                 "museum", "fort", "gate", "vintage")
# Monochrome cues: a black-and-white frame reads as the odd one out among colour covers.
# Demote hard so any honest COLOUR candidate wins, but a lone B&W still beats no photo.
_PEXELS_MONO = ("black and white", "black-and-white", "monochrome", "grayscale",
                "greyscale", "b&w", "b & w")
# Two complementary queries: "skyline" biases to recognisable wide views, "city centre"
# catches cities whose skyline term is thin. Pooled, deduped and scored together.
_PEXELS_QUERIES = ("{name} skyline", "{name} city centre skyline UK",
                   "{name} city centre aerial")
_PEXELS_PHOTO = "https://api.pexels.com/v1/photos/"

# Curated per-city overrides: a hand-verified Pexels photo ID for a city whose loose
# search cannot do better. Some cities have so few honestly-named photos that the only
# matches are off-brand (Nottingham: the just two alt-named frames are both black-and-
# white aerials). Each entry below was checked BY HAND on Pexels - the photo genuinely
# shows the named city and is in colour - so it bypasses the loose search + honesty filter
# safely. The caption names the REAL subject (a landmark), never a false "city centre".
_CURATED_CITY_PHOTO = {
    # Wollaton Hall, the Elizabethan mansion in Nottingham - colour, recognisable, alt-named.
    "nottingham": {"id": 5579376, "caption": "Wollaton Hall, Nottingham"},
}


def _gemini_key():
    maps_tools._load_env()
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _pexels_key():
    maps_tools._load_env()
    return os.environ.get("PEXELS_API_KEY")


def _hero_name(city_slug):
    return f"blog_hero_{city_slug}.jpg"


def _write_hero(raw_png, out, *, max_w=_HERO_MAX_W, quality=_HERO_QUALITY):
    """Save image bytes as a web-light JPEG. Downscales only when wider than max_w (never
    upscales) and re-encodes to JPEG when Pillow is present; otherwise writes the raw bytes
    unchanged. Reused for both the masthead hero (1600w) and the 4K-wide area photo (3840w).
    Returns True on success."""
    if Image is not None:
        try:
            im = Image.open(io.BytesIO(raw_png)).convert("RGB")
            if im.width > max_w:
                h = round(im.height * max_w / im.width)
                im = im.resize((max_w, h), Image.LANCZOS)
            im.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
            return True
        except Exception:
            pass
    try:
        with open(out, "wb") as f:
            f.write(raw_png)
        return True
    except Exception:
        return False


def _area_name(slug):
    return f"blog_area_{slug}.jpg"


def _hero_prompt(city_name):
    return (
        "A refined editorial illustration of the " + str(city_name) + " city-centre skyline "
        "at dusk for the masthead of a serious UK property research report. Flat vector poster "
        "style with clean architectural line work and subtle texture. Strict colour palette: "
        "deep navy (#0e2747) sky and buildings, warm gold (#d89a32) window and accent lights, "
        "muted teal-green (#15807f) highlights, cream (#f6f3ec) negative space. Calm, "
        "authoritative, premium, understated. Wide letterbox composition. Absolutely no text, "
        "no words, no logos, no watermarks, no people. It must read as a tasteful illustration, "
        "not a photograph."
    )


def ensure_city_hero(city_slug, city_name, *, cache_dir=None, timeout=90, force=False,
                     prompt=None, aspect_ratio="16:9"):
    """Generate (once) and cache an editorial city hero illustration via Gemini. Returns a
    relative URL string ('/img/<name>') or None. Idempotent: a cached file is reused unless
    force=True. Pass prompt=... to override the default city-skyline prompt (e.g. a UK
    composite for the index/study). aspect_ratio is requested via the image config so the
    masthead band crops cleanly (a square source would be chopped top-and-bottom by the wide
    band). Best-effort - never raises."""
    cache_dir = cache_dir or CACHE
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except Exception:
        return None
    name = _hero_name(city_slug)
    out = os.path.join(cache_dir, name)
    if os.path.exists(out) and os.path.getsize(out) > 0 and not force:
        return "/img/" + name
    key = _gemini_key()
    if not key:
        return None
    text = prompt or _hero_prompt(city_name)
    payload = {"contents": [{"parts": [{"text": text}]}]}
    if aspect_ratio:
        # gemini-2.5-flash-image honours a requested aspect ratio via generationConfig;
        # harmless if the field is ignored by an older endpoint (we still get an image).
        payload["generationConfig"] = {"imageConfig": {"aspectRatio": aspect_ratio}}
    body = json.dumps(payload).encode()
    url = _GEMINI_ENDPOINT + "?key=" + urllib.parse.quote(key)
    try:
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
    except Exception:
        return None
    try:
        parts = d["candidates"][0]["content"]["parts"]
    except Exception:
        return None
    for p in parts:
        inline = p.get("inlineData") or p.get("inline_data")
        if inline and inline.get("data"):
            try:
                raw = base64.b64decode(inline["data"])
            except Exception:
                return None
            if _write_hero(raw, out):
                return "/img/" + name
            return None
    return None


def _pexels_pick(photos, city_name):
    """From a pool of Pexels results, return the photo that GENUINELY shows the named
    city, or None. Honesty filter first: keep only photos whose alt text names the city
    (Pexels keyword search is loose - a 'Nottingham' query returns Manchester and Leeds
    frames, so the top hit is NOT trustworthy). Quality score second: among the honest
    candidates, favour a wide recognisable city view (+1 per skyline/cityscape/aerial
    cue) and demote close-ups/walls/interiors (-2 per cue), keeping Pexels' own relevance
    order as the tie-break. Returns None rather than mislabel a photo of the wrong place."""
    needle = (city_name or "").lower().strip()
    if not needle:
        return None
    candidates = [p for p in photos if needle in (p.get("alt") or "").lower()]
    if not candidates:
        return None
    # HD/4K only: drop sub-HD originals so the rendered photo is never soft. Fall back to
    # the full honest set only if none reach HD (so an honest match still beats nothing).
    hd = [p for p in candidates if (p.get("width") or 0) >= _AREA_MIN_W]
    pool = hd or candidates
    def score(idx_p):
        idx, p = idx_p
        alt = (p.get("alt") or "").lower()
        s = sum(1 for w in _PEXELS_PREFER if w in alt)
        s -= 2 * sum(1 for w in _PEXELS_AVOID if w in alt)
        s -= 5 * sum(1 for w in _PEXELS_MONO if w in alt)
        if (p.get("width") or 0) >= 3840:      # bonus for genuine 4K source width
            s += 1
        # higher alt-score wins; then highest resolution; then Pexels' own relevance order
        return (s, p.get("width") or 0, -idx)
    best = max(enumerate(pool), key=score)
    return best[1]


def _pexels_photo_by_id(photo_id, key, *, timeout=45):
    """GET a single Pexels photo by its numeric ID. Used only for the hand-verified
    _CURATED_CITY_PHOTO overrides, so it skips the search + honesty filter (the photo was
    checked by hand). Returns the raw Pexels photo dict or None. Best-effort - never raises."""
    try:
        req = urllib.request.Request(_PEXELS_PHOTO + str(photo_id),
                                     headers={"Authorization": key, "User-Agent": _PEXELS_UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def ensure_city_photo(city_slug, city_name, *, cache_dir=None, force=False, timeout=45):
    """Fetch (once) and cache a real, attributed city-centre PHOTOGRAPH from Pexels for
    a city. Returns a small dict {url, caption, credit, photographer, photographer_url,
    photo_url, source, alt} or None. Honest by construction: only a photo whose Pexels
    alt text actually names the city is used (see _pexels_pick); if none of the search
    hits genuinely show the city, returns None and the report renders without an area
    photo rather than captioning the wrong place as this city. Best-effort - never
    raises. Cached per city as blog_area_<city_slug>.jpg (districts of a city share it)."""
    cache_dir = cache_dir or CACHE
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except Exception:
        return None
    if not city_slug or not city_name:
        return None
    name = _area_name(city_slug)
    out = os.path.join(cache_dir, name)
    meta_path = os.path.join(cache_dir, f"blog_area_{city_slug}.json")
    if os.path.exists(out) and os.path.getsize(out) > 0 and not force:
        # Reuse the cached image AND its stored attribution (Pexels licence requires the
        # photographer credit + a Pexels link to ride with every use).
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"url": "/img/" + name, "caption": f"{city_name} city centre",
                    "credit": PEXELS_SRC, "source": PEXELS_SRC}
    key = _pexels_key()
    if not key:
        return None
    # Hand-verified override first: when a city's loose search cannot surface an honest
    # colour photo, use the curated landmark ID (checked by hand) with its real caption.
    curated = _CURATED_CITY_PHOTO.get(city_slug)
    caption = f"{city_name} city centre"
    pick = None
    if curated:
        pick = _pexels_photo_by_id(curated["id"], key, timeout=timeout)
        if pick:
            caption = curated.get("caption") or caption
    if not pick:
        pool, seen = [], set()
        for tmpl in _PEXELS_QUERIES:
            q = urllib.parse.urlencode({"query": tmpl.format(name=city_name),
                                        "orientation": "landscape", "per_page": 30})
            try:
                req = urllib.request.Request(_PEXELS_SEARCH + "?" + q,
                                             headers={"Authorization": key,
                                                      "User-Agent": _PEXELS_UA})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = json.load(r)
            except Exception:
                continue
            for p in data.get("photos") or []:
                if p.get("id") not in seen:
                    seen.add(p.get("id")); pool.append(p)
        pick = _pexels_pick(pool, city_name)
    if not pick:
        return None
    src = pick.get("src") or {}
    # Fetch the full-resolution ORIGINAL (Pexels originals are typically 3000-6000px wide),
    # not the 1200px 'landscape' crop - then _write_hero caps it at 4K. This is what makes
    # the rendered photo HD/4K-crisp rather than soft.
    img_url = src.get("original") or src.get("large2x") or src.get("large")
    if not img_url:
        return None
    try:
        ireq = urllib.request.Request(img_url, headers={"User-Agent": _PEXELS_UA})
        with urllib.request.urlopen(ireq, timeout=timeout) as r:
            raw = r.read()
    except Exception:
        return None
    if not _write_hero(raw, out, max_w=_AREA_MAX_W, quality=_AREA_QUALITY):
        return None
    photo = {"url": "/img/" + name,
             "caption": caption,
             "photographer": pick.get("photographer"),
             "photographer_url": pick.get("photographer_url"),
             "photo_url": pick.get("url"),
             "alt": pick.get("alt"),
             "credit": PEXELS_SRC,
             "source": PEXELS_SRC}
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(photo, f, ensure_ascii=False)
    except Exception:
        pass
    return photo


def ensure_topic_photo(topic_slug, caption, queries, *, cache_dir=None, force=False,
                       timeout=45):
    """Fetch (once) and cache a generic Pexels photograph for a topical blog page.

    This is decorative only: a report workflow can still render fine without it. The image is
    chosen from a small set of search queries and stored on disk so the daily rebuild can
    reuse it with no network."""
    cache_dir = cache_dir or CACHE
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except Exception:
        return None
    if not topic_slug or not caption:
        return None
    name = f"blog_topic_{topic_slug}.jpg"
    out = os.path.join(cache_dir, name)
    meta_path = os.path.join(cache_dir, f"blog_topic_{topic_slug}.json")
    if os.path.exists(out) and os.path.getsize(out) > 0 and not force:
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"url": "/img/" + name, "caption": caption,
                    "credit": PEXELS_SRC, "source": PEXELS_SRC}
    key = _pexels_key()
    if not key:
        return None
    if isinstance(queries, str):
        queries = [queries]
    pool, seen = [], set()
    for qtxt in (queries or []):
        if not qtxt:
            continue
        q = urllib.parse.urlencode({"query": qtxt, "orientation": "landscape", "per_page": 30})
        try:
            req = urllib.request.Request(_PEXELS_SEARCH + "?" + q,
                                         headers={"Authorization": key,
                                                  "User-Agent": _PEXELS_UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
        except Exception:
            continue
        for p in data.get("photos") or []:
            pid = p.get("id")
            if pid not in seen:
                seen.add(pid)
                pool.append(p)
    if not pool:
        return None
    # Prefer wide, colourful, relevant images; never pick a monochrome or close-up if a
    # broader frame exists.
    def score(idx_p):
        idx, p = idx_p
        alt = (p.get("alt") or "").lower()
        s = 0
        s += 2 * sum(1 for w in ("skyline", "city", "house", "home", "apartment",
                                 "desk", "laptop", "phone", "notification", "paper",
                                 "report", "calculator", "keys", "sign") if w in alt)
        s -= 2 * sum(1 for w in _PEXELS_AVOID if w in alt)
        s -= 5 * sum(1 for w in _PEXELS_MONO if w in alt)
        if (p.get("width") or 0) >= _AREA_MIN_W:
            s += 1
        if (p.get("width") or 0) >= 3840:
            s += 1
        return (s, p.get("width") or 0, -idx)
    pick = max(enumerate(pool), key=score)[1]
    src = pick.get("src") or {}
    img_url = src.get("original") or src.get("large2x") or src.get("large")
    if not img_url:
        return None
    try:
        ireq = urllib.request.Request(img_url, headers={"User-Agent": _PEXELS_UA})
        with urllib.request.urlopen(ireq, timeout=timeout) as r:
            raw = r.read()
    except Exception:
        return None
    if not _write_hero(raw, out, max_w=_AREA_MAX_W, quality=_AREA_QUALITY):
        return None
    photo = {"url": "/img/" + name,
             "caption": caption,
             "photographer": pick.get("photographer"),
             "photographer_url": pick.get("photographer_url"),
             "photo_url": pick.get("url"),
             "alt": pick.get("alt"),
             "credit": PEXELS_SRC,
             "source": PEXELS_SRC,
             "query": queries}
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(photo, f, ensure_ascii=False)
    except Exception:
        pass
    return photo


def ensure_area_photo(slug, lat, lng, *, cache_dir=None, force=False):
    """Cache (once) a Google Street View frame at the district centroid. Returns a small dict
    {url, credit, caption_hint} or None when no imagery / no key. Best-effort - never raises."""
    cache_dir = cache_dir or CACHE
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except Exception:
        return None
    if lat is None or lng is None:
        return None
    name = _area_name(slug)
    out = os.path.join(cache_dir, name)
    if os.path.exists(out) and os.path.getsize(out) > 0 and not force:
        return {"url": "/img/" + name, "credit": "(c) Google", "source": AREA_SRC}
    try:
        res = maps_tools.street_view(f"{lat},{lng}", out, size="640x360", fov=90, pitch=4)
    except Exception:
        return None
    if not res.get("ok") or not res.get("available") or not os.path.exists(out):
        return None
    return {"url": "/img/" + name, "credit": "(c) Google", "source": AREA_SRC,
            "date": res.get("date")}


def attach(model, *, cache_dir=None, force=False):
    """Mutate a district model in place, adding model['hero'] and model['area_photo'] when an
    image is available. Pure data (strings) so blog.py renders them with no network. Returns
    the model. Best-effort - a failure to fetch simply leaves the key absent."""
    if not isinstance(model, dict):
        return model
    city = model.get("city") or {}
    geo = model.get("geo") or {}
    city_slug = city.get("slug")
    city_name = city.get("name") or city_slug
    if city_slug:
        hero_url = ensure_city_hero(city_slug, city_name, cache_dir=cache_dir, force=force)
        if hero_url:
            model["hero"] = {"url": hero_url,
                             "caption": f"{city_name} - editorial illustration",
                             "source": HERO_SRC}
    # Area photo: a real, attributed city-centre photograph from Pexels, keyed per city
    # (districts of a city share it). This replaces the Street View frame, which returned
    # the NEAREST panorama and at commercial centroids could be a business-contributed
    # indoor photo sphere (a furniture showroom mislabelled as "a street"). The Pexels
    # photo is only used when its alt text genuinely names the city - honest or absent.
    if city_slug:
        photo = ensure_city_photo(city_slug, city_name, cache_dir=cache_dir, force=force)
        if photo:
            model["area_photo"] = photo
    return model


def _selftest():
    g = "set" if _gemini_key() else "not set"
    print("GEMINI key       :", g)
    maps_tools._load_env()
    m = "set" if os.environ.get("GOOGLE_MAPS_API_KEY") else "not set"
    print("GOOGLE_MAPS key  :", m)
    print("cache dir        :", CACHE, "(exists)" if os.path.isdir(CACHE) else "(missing)")
    print("hero name e.g.   :", _hero_name("london"))
    print("area name e.g.   :", _area_name("london-ec2"))


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "selftest":
        _selftest(); return
    cmd = sys.argv[1]
    if cmd == "hero":
        slug = sys.argv[2]; name = sys.argv[3] if len(sys.argv) > 3 else slug
        print(json.dumps({"url": ensure_city_hero(slug, name, force="--force" in sys.argv)}, indent=2))
    elif cmd == "area":
        slug = sys.argv[2]; lat = float(sys.argv[3]); lng = float(sys.argv[4])
        print(json.dumps(ensure_area_photo(slug, lat, lng, force="--force" in sys.argv), indent=2))
    elif cmd == "cityphoto":
        slug = sys.argv[2]; name = sys.argv[3] if len(sys.argv) > 3 else slug
        print(json.dumps(ensure_city_photo(slug, name, force="--force" in sys.argv),
                         indent=2, ensure_ascii=False))
    else:
        print("unknown command:", cmd); print(__doc__)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Chart generation (matplotlib) -- real PNG graphs for blog articles
# ---------------------------------------------------------------------------
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path

# Brand colours
BRAND = {
    'navy': '#0e2747', 'green': '#15807f', 'gold': '#d89a32',
    'cream': '#f6f3ec', 'ink': '#1c1a16', 'muted': '#6b6557',
    'terra': '#2aa39a', 'tg': '#229ED9'
}

CHART_DIR = Path(__file__).resolve().parent / 'site' / 'img' / 'charts'
CHART_WEB_PREFIX = '/img/charts/'
CHART_DIR.mkdir(parents=True, exist_ok=True)


def money_fmt(x, pos=None):
    """Format axis values as money: 350000 -> 350k."""
    if x >= 1_000_000:
        return f'{x/1_000_000:.1f}M'
    if x >= 1_000:
        return f'{x/1_000:.0f}k'
    return str(int(x))


def chart_asking_vs_sold(slug, district, sold_median, asking_median):
    """Generate a branded bar chart comparing sold vs asking median prices."""
    path = CHART_DIR / f'{slug}-asking-vs-sold.png'
    if path.exists():
        return str(path)

    fig, ax = plt.subplots(figsize=(7, 3.5))
    fig.patch.set_facecolor(BRAND['cream'])
    ax.set_facecolor(BRAND['cream'])

    labels = ['Sold median', 'Asking median']
    values = [sold_median, asking_median]
    colors = [BRAND['green'], BRAND['gold']]

    bars = ax.bar(labels, values, color=colors, width=0.5, edgecolor='none')
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values)*0.02,
                f'£{val:,.0f}', ha='center', va='bottom', fontsize=10, fontweight='bold',
                color=BRAND['ink'], fontfamily='sans-serif')

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(money_fmt))
    ax.set_ylabel('Price', fontsize=9, color=BRAND['muted'])
    ax.set_title(f'Asking vs Sold in {district}', fontsize=13, fontweight='bold',
                 color=BRAND['navy'], pad=10, fontfamily='serif')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color(BRAND['muted'])
    ax.spines['bottom'].set_color(BRAND['muted'])
    ax.tick_params(colors=BRAND['muted'], labelsize=9)
    fig.text(0.5, -0.02, 'Source: HM Land Registry Price Paid Data | Asking: live listings',
             ha='center', fontsize=7, color=BRAND['muted'], fontstyle='italic')
    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=BRAND['cream'])
    plt.close(fig)
    return str(path)


def chart_sold_by_type(slug, district, by_type):
    """Generate a horizontal bar chart of sold prices by property type."""
    if not by_type or len(by_type) < 2:
        return None
    path = CHART_DIR / f'{slug}-sold-by-type.png'
    if path.exists():
        return str(path)

    labels = [bt['label'] for bt in by_type if bt.get('median')]
    values = [bt['median'] for bt in by_type if bt.get('median')]
    if len(labels) < 2:
        return None

    fig, ax = plt.subplots(figsize=(7, len(labels)*0.6 + 1.5))
    fig.patch.set_facecolor(BRAND['cream'])
    ax.set_facecolor(BRAND['cream'])

    colors = [BRAND['green']] + [BRAND['terra']] + [BRAND['tg']] * (len(labels) - 2)
    bars = ax.barh(labels, values, color=colors[:len(labels)], height=0.5, edgecolor='none')
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + max(values)*0.02, bar.get_y() + bar.get_height()/2,
                f'£{val:,.0f}', va='center', fontsize=9, fontweight='bold',
                color=BRAND['ink'], fontfamily='sans-serif')

    ax.xaxis.set_major_formatter(mticker.FuncFormatter(money_fmt))
    ax.set_title(f'Sold Price by Property Type in {district}', fontsize=13, fontweight='bold',
                 color=BRAND['navy'], pad=10, fontfamily='serif')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color(BRAND['muted'])
    ax.spines['bottom'].set_color(BRAND['muted'])
    ax.tick_params(colors=BRAND['muted'], labelsize=9)
    fig.text(0.5, -0.02, 'Source: HM Land Registry Price Paid Data',
             ha='center', fontsize=7, color=BRAND['muted'], fontstyle='italic')
    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=BRAND['cream'])
    plt.close(fig)
    return str(path)


def attach_charts(model):
    """Generate chart images for a district model and attach URLs.
    Called from publish_daily.py before rendering."""
    slug = model.get('slug', '')
    district = model.get('district', '')
    s = model.get('sold') or {}
    l = model.get('listings') or {}

    charts = {}
    if s.get('ok') and s.get('median_price') and l.get('ok') and l.get('asking_median'):
        p = chart_asking_vs_sold(slug, district, s['median_price'], l['asking_median'])
        if p:
            charts['asking_vs_sold'] = CHART_WEB_PREFIX + Path(p).name

    if s.get('ok') and s.get('by_type'):
        p = chart_sold_by_type(slug, district, s['by_type'])
        if p:
            charts['sold_by_type'] = CHART_WEB_PREFIX + Path(p).name

    if charts:
        model['charts'] = charts
    return model
