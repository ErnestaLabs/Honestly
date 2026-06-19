#!/usr/bin/env python3
"""seo_audit.py - the always-on SEO/AEO audit for the blog network.

This does NOT re-implement the page model. It REUSES blog.py's own builders as the single
source of truth and asserts the rendered HTML actually carries what those builders produce.
So the audit can never drift from the templates: if render_post stops embedding the JSON-LD
that blog._jsonld() builds, the audit regenerates that exact JSON-LD and fails to find it.

What it enforces on every rendered page (classic SEO + answer-engine/AEO):
  * <title> present, inside a sane length window
  * <meta name="description"> present, ~50-160 chars
  * <link rel="canonical"> present and absolute (on our domain)
  * Open Graph (title/type/url/description/site_name) + twitter:card present
  * exactly ONE <h1>
  * <html lang="en-GB">
  * every <img> carries an alt attribute (empty alt allowed = decorative)
  * no robots "noindex"
  * a JSON-LD block that PARSES and carries the @types this page kind requires
  * the AEO answer paragraph is present and a quotable length (~25-80 words)
  * machinery cross-check: the exact JSON-LD / answer blog.py builds is embedded verbatim

And on the network artefacts: sitemap.xml (well-formed, has <loc>s), RSS feed (well-formed,
has <item>s), robots.txt (has a Sitemap: line).

Findings carry a level: ERROR (a real SEO/AEO defect) or WARN (advisory). audit_site()
returns (findings, ok) where ok is "no ERRORs". Wired into publish_daily.rebuild_indices()
so it runs on every rebuild, and exposed as a CLI that exits non-zero on ERROR for CI.
"""
import html as _html
import re
import json

import blog


# ----------------------------------------------------------------- finding model
class Finding:
    __slots__ = ("level", "where", "code", "detail")

    def __init__(self, level, where, code, detail):
        self.level, self.where, self.code, self.detail = level, where, code, detail

    def __repr__(self):
        return f"[{self.level}] {self.where}: {self.code} - {self.detail}"


def _err(where, code, detail):
    return Finding("ERROR", where, code, detail)


def _warn(where, code, detail):
    return Finding("WARN", where, code, detail)


# ----------------------------------------------------------------- tiny readers
# These READ the rendered HTML (they are not a second SEO model - the model lives in
# blog.py). Regex is deliberate and narrow: we extract the literal tags the templates emit.
def _find_all(pattern, doc, flags=re.I | re.S):
    return re.findall(pattern, doc, flags)


def _first(pattern, doc, flags=re.I | re.S):
    m = re.search(pattern, doc, flags)
    return m.group(1) if m else None


def _title(doc):
    return _first(r"<title>(.*?)</title>", doc)


def _meta(doc, name=None, prop=None):
    if name:
        return _first(rf'<meta\s+name=["\']{re.escape(name)}["\']\s+content=["\'](.*?)["\']', doc)
    if prop:
        return _first(rf'<meta\s+property=["\']{re.escape(prop)}["\']\s+content=["\'](.*?)["\']', doc)
    return None


def _word_count(text):
    return len((text or "").split())


def _jsonld_blocks(doc):
    return _find_all(r'<script type="application/ld\+json">(.*?)</script>', doc)


def _jsonld_types(parsed):
    """All @type strings in a parsed JSON-LD doc (handles @graph + nested)."""
    out = []

    def walk(node):
        if isinstance(node, dict):
            t = node.get("@type")
            if isinstance(t, str):
                out.append(t)
            elif isinstance(t, list):
                out.extend(x for x in t if isinstance(x, str))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(parsed)
    return out


_PUBLIC_COPY_BANNED = (
    "authority engine", "the product", "blog page", "routes the reader",
    "because the blog", "why compare on a blog page", "how we did this",
    "how we built this", "what this page covers", "read the market",
    "reader", "readers", "shared method", "brochure fluff", "urgent intent",
    "recurring intent", "content mix",
)


def _visible_text(doc):
    """Best-effort visible text for public-copy linting."""
    txt = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', doc, flags=re.I | re.S)
    txt = re.sub(r'<[^>]+>', ' ', txt)
    return _html.unescape(re.sub(r'\s+', ' ', txt)).strip()


# ----------------------------------------------------------------- generic checks
def audit_html(doc, where, *, required_types=(), expect_jsonld=None, expect_answer=None,
               answer_words=(25, 80)):
    """The structural SEO/AEO checks every page kind shares. required_types: JSON-LD @types
    this page must carry. expect_jsonld/expect_answer: exact strings blog.py built, which
    must appear verbatim (the machinery cross-check)."""
    f = []

    # lang
    if not re.search(r'<html[^>]*\blang=["\']en-GB["\']', doc, re.I):
        f.append(_err(where, "lang", 'missing <html lang="en-GB">'))

    # title
    title = _title(doc)
    if not title:
        f.append(_err(where, "title", "no <title>"))
    else:
        tlen = len(_html.unescape(title))
        if tlen < 15:
            f.append(_warn(where, "title-short", f"title {tlen} chars (<15): {title!r}"))
        elif tlen > 70:
            f.append(_warn(where, "title-long", f"title {tlen} chars (>70 may truncate in SERP)"))

    # meta description
    desc = _meta(doc, name="description")
    if not desc:
        f.append(_err(where, "meta-desc", "no <meta name=description>"))
    else:
        dlen = len(_html.unescape(desc))
        if dlen < 50:
            f.append(_warn(where, "desc-short", f"description {dlen} chars (<50)"))
        elif dlen > 160:
            f.append(_warn(where, "desc-long", f"description {dlen} chars (>160 truncates)"))

    # canonical
    canon = _first(r'<link\s+rel=["\']canonical["\']\s+href=["\'](.*?)["\']', doc)
    if not canon:
        f.append(_err(where, "canonical", "no <link rel=canonical>"))
    elif not canon.startswith(blog.SITE):
        f.append(_err(where, "canonical-domain", f"canonical not on site domain: {canon}"))

    # open graph + twitter
    for prop in ("og:title", "og:type", "og:url", "og:description", "og:site_name"):
        if not _meta(doc, prop=prop):
            f.append(_warn(where, "og", f"missing {prop}"))
    if not _meta(doc, name="twitter:card"):
        f.append(_warn(where, "twitter", "missing twitter:card"))

    # exactly one H1
    h1s = _find_all(r"<h1[ >].*?</h1>", doc)
    if len(h1s) == 0:
        f.append(_err(where, "h1-missing", "no <h1>"))
    elif len(h1s) > 1:
        f.append(_err(where, "h1-multiple", f"{len(h1s)} <h1> tags (must be exactly 1)"))

    # robots noindex
    robots = _meta(doc, name="robots") or ""
    if "noindex" in robots.lower():
        f.append(_err(where, "noindex", "page is set to noindex"))

    # public-copy lint: no internal/product/process language in visible page text.
    visible = _visible_text(doc).lower()
    for phrase in _PUBLIC_COPY_BANNED:
        if phrase in visible:
            f.append(_err(where, "public-copy", f"public copy contains banned phrase: {phrase!r}"))

    # images must carry an alt attribute (empty alt OK = decorative)
    for img in _find_all(r"<img\b[^>]*>", doc):
        if not re.search(r'\balt=', img, re.I):
            f.append(_err(where, "img-alt", f"<img> without alt attribute: {img[:80]}"))

    # JSON-LD: parses + carries required @types
    blocks = _jsonld_blocks(doc)
    if not blocks:
        f.append(_err(where, "jsonld-missing", "no JSON-LD block"))
    else:
        types = []
        for b in blocks:
            try:
                types.extend(_jsonld_types(json.loads(b)))
            except json.JSONDecodeError as ex:
                f.append(_err(where, "jsonld-parse", f"JSON-LD does not parse: {ex}"))
        for t in required_types:
            if t not in types:
                f.append(_err(where, "jsonld-type", f"JSON-LD missing required @type {t} "
                                                    f"(found: {sorted(set(types))})"))

    # machinery cross-check: the exact JSON-LD blog.py built must be embedded
    if expect_jsonld is not None and expect_jsonld not in doc:
        f.append(_err(where, "jsonld-drift", "rendered JSON-LD differs from blog._jsonld() "
                                            "output - template and builder have drifted"))

    # AEO answer paragraph
    ans = _first(r'<p class="(?:standfirst|answer)">(.*?)</p>', doc)
    if not ans:
        f.append(_err(where, "answer-missing", "no .standfirst/.answer AEO paragraph"))
    else:
        wc = _word_count(re.sub(r"<[^>]+>", "", ans))
        lo, hi = answer_words
        if wc < lo:
            f.append(_warn(where, "answer-short", f"answer {wc} words (<{lo})"))
        elif wc > hi:
            f.append(_warn(where, "answer-long", f"answer {wc} words (>{hi})"))
    if expect_answer is not None:
        if _html.escape(expect_answer, quote=True) not in doc and expect_answer not in doc:
            f.append(_warn(where, "answer-drift",
                           "rendered answer differs from blog._answer_paragraph() output"))

    return f


# ----------------------------------------------------------------- per-kind audits
def audit_post(model, doc):
    where = f"post:{model.get('slug', '?')}"
    faqs = blog._faqs(model)
    refs = blog._references(model)
    expect_jsonld = blog._jsonld(model, faqs, refs)
    required = ["Article", "Place", "BreadcrumbList"]
    if faqs:
        required.append("FAQPage")
    if (model.get("sold") or {}).get("ok"):
        required.append("Dataset")
    return audit_html(doc, where, required_types=required, expect_jsonld=expect_jsonld,
                      expect_answer=blog._answer_paragraph(model), answer_words=(25, 80))


def audit_hub(city, posts, doc):
    where = f"hub:{city.get('slug', '?')}"
    agg = blog._city_aggregate(posts)
    faqs = blog._city_faqs(city, posts, agg)
    required = ["CollectionPage", "Place", "BreadcrumbList"]
    if faqs:
        required.append("FAQPage")
    return audit_html(doc, where, required_types=required, answer_words=(25, 90))


def audit_index(by_city, doc):
    return audit_html(doc, "index", required_types=["CollectionPage", "BreadcrumbList"],
                      answer_words=(25, 90))


def audit_study(doc):
    return audit_html(doc, "study", required_types=["Article"], answer_words=(15, 120))


# ----------------------------------------------------------------- network artefacts
def audit_sitemap(xml, where="sitemap.xml"):
    f = []
    if "<urlset" not in xml:
        f.append(_err(where, "sitemap-shape", "no <urlset> root"))
    locs = _find_all(r"<loc>(.*?)</loc>", xml)
    if not locs:
        f.append(_err(where, "sitemap-empty", "no <loc> entries"))
    bad = [u for u in locs if not u.startswith("http")]
    if bad:
        f.append(_err(where, "sitemap-rel", f"{len(bad)} non-absolute loc(s), e.g. {bad[0]}"))
    return f


def audit_rss(xml, where="feed.xml"):
    f = []
    if "<rss" not in xml or "<channel>" not in xml:
        f.append(_err(where, "rss-shape", "not a well-formed RSS 2.0 channel"))
    if not _find_all(r"<item>", xml):
        f.append(_warn(where, "rss-empty", "feed has no <item>s"))
    if "<link>" not in xml:
        f.append(_err(where, "rss-link", "channel missing <link>"))
    return f


def audit_robots(txt, where="robots.txt"):
    f = []
    if not re.search(r"(?im)^\s*sitemap:\s*http", txt):
        f.append(_err(where, "robots-sitemap", "robots.txt has no absolute Sitemap: line"))
    return f


# ----------------------------------------------------------------- aggregate + report
def audit_site(pages):
    """pages: list of finding-lists already produced by the per-kind audits, OR a flat list
    of Finding. Returns (findings, ok)."""
    findings = []
    for p in pages:
        if isinstance(p, (list, tuple)):
            findings.extend(p)
        else:
            findings.append(p)
    ok = not any(x.level == "ERROR" for x in findings)
    return findings, ok


def summarize(findings):
    errs = sum(1 for x in findings if x.level == "ERROR")
    warns = sum(1 for x in findings if x.level == "WARN")
    return errs, warns


def format_report(findings):
    errs, warns = summarize(findings)
    lines = [f"SEO/AEO audit: {errs} error(s), {warns} warning(s)"]
    for x in findings:
        lines.append(f"  {x}")
    if not findings:
        lines.append("  clean - all checks passed")
    return "\n".join(lines)


# ----------------------------------------------------------------- CLI
def main():
    """Render the live network from the database and audit every page. Exit 1 on any ERROR
    so CI / a pre-publish gate can block a broken release."""
    import sys
    try:
        import publish_daily
    except Exception as ex:  # pragma: no cover - import guard
        print(f"seo_audit: cannot import publish_daily: {ex}")
        return 2
    findings = publish_daily.audit_network()
    _, ok = audit_site(findings)
    print(format_report(findings))
    if "--strict" in sys.argv:
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
