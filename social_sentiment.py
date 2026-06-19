"""social_sentiment.py - frozen-artifact loader/shaper for the blog's "What people say".

Real voices from public UK property forums are captured OUT OF BAND through the Hit MCP
(hitman.red, an Ernesta Labs preview) when that tooling is connected, shaped here, and
frozen to social_sentiment.json on disk. The headless daily build (publish_daily.py
--rebuild) has no MCP: it only reads/renders the frozen file. This mirrors the established
pattern in market_study._load_sentiment(), which reads study_sentiment.json.

Honesty contract (same as the study): these are individual posts on public forums, quoted
as social sentiment only. They are anecdote, not evidence of value, and not one of them
feeds any figure on the page. They are colour beside the numbers, never an input to them.

Nothing here ever raises into the build: a missing or malformed file yields {} and the
section simply omits.
"""

import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "social_sentiment.json")


def _read():
    """Whole frozen file as {by_slug:{}, by_city:{}}; {} on any error. Never raises."""
    try:
        with open(_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load(slug, city_slug=None):
    """Best-effort load of one district's frozen sentiment block.

    Looks up the district slug first (most specific), then falls back to the city block so a
    district with no captured voices of its own can still borrow its city's. Returns {} when
    nothing applies, so the caller renders no section. Never raises.
    """
    data = _read()
    by_slug = data.get("by_slug") or {}
    block = by_slug.get(slug)
    if isinstance(block, dict) and block.get("voices"):
        return block
    if city_slug:
        by_city = data.get("by_city") or {}
        cblock = by_city.get(city_slug)
        if isinstance(cblock, dict) and cblock.get("voices"):
            return cblock
    return {}


def shape_scan(scan, *, area_terms=None, max_voices=4):
    """Turn a raw Hit-MCP scan payload into a list of clean voice dicts.

    A Hit scan returns posts with assorted shapes; this normalises each to the canonical
    voice schema the renderer expects (quote/reply/where/subreddit/url/ties_to) and keeps
    only the strongest, on-theme few. Pure/defensive: unknown keys are ignored, missing
    fields default to empty, and it never raises. area_terms (e.g. ["SE15","Peckham"]) is a
    soft relevance filter; when given, a post must mention one of them in title or body.
    """
    posts = []
    if isinstance(scan, dict):
        posts = scan.get("posts") or scan.get("voices") or scan.get("results") or []
    elif isinstance(scan, list):
        posts = scan
    terms = [t.lower() for t in (area_terms or []) if t]
    out = []
    for p in posts:
        if not isinstance(p, dict):
            continue
        quote = (p.get("quote") or p.get("body") or p.get("selftext") or "").strip()
        title = (p.get("where") or p.get("title") or "").strip()
        if not quote:
            continue
        if terms:
            hay = (quote + " " + title).lower()
            if not any(t in hay for t in terms):
                continue
        out.append({
            "quote": quote,
            "reply": (p.get("reply") or "").strip(),
            "where": title or p.get("author_flair") or "A seller on a public forum",
            "subreddit": (p.get("subreddit") or "r/HousingUK").strip(),
            "url": (p.get("url") or p.get("permalink") or "").strip(),
            "ties_to": (p.get("ties_to") or "").strip(),
        })
        if len(out) >= max_voices:
            break
    return out


def build_block(*, voices, scan_id="", captured_at,
                source_label=("Public UK property forums, captured via hitman.red "
                              "(Ernesta Labs Exclusive Preview)"),
                method="", disclaimer=""):
    """Assemble one renderable sentiment block from shaped voices + provenance.

    captured_at is required (passed in - this module never calls Date.now-style clocks). The
    default disclaimer carries the honesty contract verbatim; callers can override per-area.
    """
    if not disclaimer:
        disclaimer = (
            "These are individual posts on public property forums, quoted as social "
            "sentiment only. They are anecdote, not evidence of value, and not one of them "
            "fed any figure on this page. We include them because they put a human voice to "
            "what the sold and listing data already shows.")
    if not method:
        method = ("Captured by listening across public UK property forums for live "
                  "discussion of buying and selling in this area. Quoted verbatim, lightly "
                  "trimmed; each links to its public thread.")
    return {
        "captured_at": captured_at,
        "source_label": source_label,
        "method": method,
        "disclaimer": disclaimer,
        "scan_id": scan_id,
        "voices": [v for v in (voices or []) if isinstance(v, dict) and v.get("quote")],
    }


def freeze(*, slug=None, city_slug=None, block, path=None):
    """Write/merge one block into social_sentiment.json under by_slug[slug] and/or
    by_city[city_slug]. Reads the existing file first so freezing one area never clobbers
    another. Best-effort: returns True on success, False on any failure; never raises.
    """
    target = path or _PATH
    try:
        try:
            with open(target, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        data.setdefault("by_slug", {})
        data.setdefault("by_city", {})
        if slug:
            data["by_slug"][slug] = block
        if city_slug:
            data["by_city"][city_slug] = block
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False
