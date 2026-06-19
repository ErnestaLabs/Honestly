# -*- coding: utf-8 -*-
"""reddit_blog.py - original, voice-matched blog answer pages.

The job: people on r/HousingUK (and elsewhere) describe property problems in their OWN voice -
"why isn't my house selling", "am I being delusional", "agent talked me into overvaluing it".
We use those threads as RESEARCH ONLY: they tell us what to write about and HOW REAL PEOPLE TALK
about it. Then we write an ORIGINAL blog post about that situation, in that same register and
tone, so it resonates with people living the same problem - and answer it with our sold-evidence
method, with the matching paid product as the CTA.

HARD RULE - this module NEVER reposts. There is no field for, and no code path that emits, the
source post's text, quote, body, URL, author, or a link to the thread. Reposting someone's
content on a commercial blog is off the table. The input here is an ARTICLE we authored; the
Reddit research that inspired it lives nowhere in the output.

An `article` is original copy (ours):
  {product, title, lead, sections:[{h, body}], faqs:[{q, a}], slug?, area?, stats?}
`product` is a catalogue.py id - it sets the CTA (the deep link into the matching product).
"""
import os
import re
import sys
import json
import blog
import catalogue

_HERE = os.path.dirname(os.path.abspath(__file__))
_SITE_DIR = os.environ.get("BLOG_SITE_DIR", os.path.join(_HERE, "site"))


def _slugify(s, maxlen=70):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return (s[:maxlen].strip("-")) or "property-answer"


def spec_from_article(article):
    """Build a blog.render_topic_page spec from an ORIGINAL article we authored. No source text,
    no source link - only our own copy + the product CTA. Raises ValueError if the article looks
    like it carries a reposted source (defence in depth: a quote/url field is a bug, not data)."""
    for banned in ("quote", "body", "body_excerpt", "permalink", "url", "source_url", "reddit"):
        if article.get(banned):
            raise ValueError(f"article carries a reposted-source field '{banned}' - refused. "
                             "This module publishes ORIGINAL copy only; it never reposts.")
    pid = article.get("product") or "buyer_is_overpriced"
    prod = catalogue.get(pid) or {}
    title = (article.get("title") or prod.get("name") or "Is this priced right?").strip()
    area = (article.get("area") or "").strip()
    title_full = f"{title} ({area})" if area else title
    slug = article.get("slug") or _slugify(f"{title}-{area}")
    sections = article.get("sections") or []
    bullets = [{"title": s.get("h", ""), "body": s.get("body", "")} for s in sections]
    return {
        "slug": slug,
        "title": title_full,
        "h1": title_full,
        "kicker": article.get("kicker") or "Honestly answers",
        "series": "Honestly answers",
        "summary": article.get("lead") or "",
        "stats": article.get("stats") or [],
        "bullets": bullets,
        "steps": article.get("steps") or [],
        "faqs": article.get("faqs") or [],
        "links": [],                       # never a source link
        "cta_lead": (f"{prod.get('name','Get the answer')} runs on YOUR address from the Land "
                     "Registry sold record - the real figure, in a couple of minutes."),
        "cta": [
            {"class": "cta-tg", "url": f"{blog.BOT}?start=p_{pid}", "rel": True,
             "label": f"{prod.get('name','Get the answer')} - for your address"},
            {"class": "cta-ghost", "url": blog.BOT, "rel": True,
             "label": "Or run a free instant valuation"},
        ],
        "_product_id": pid,
    }


def render_article(article, *, cities_nav=None):
    spec = spec_from_article(article)
    html = blog.render_topic_page(spec, cities_nav=cities_nav)
    return html, spec["slug"], blog._topic_url(spec["slug"]), spec["title"]


def _write(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


def _patch_sitemap(site_dir, new_urls):
    sm = os.path.join(site_dir, "sitemap.xml")
    try:
        existing = open(sm, encoding="utf-8").read() if os.path.exists(sm) else (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n</urlset>\n')
        adds = ""
        for u in new_urls:
            loc = blog.SITE + u
            if loc not in existing:
                adds += f"  <url><loc>{loc}</loc><changefreq>weekly</changefreq></url>\n"
        if adds and "</urlset>" in existing:
            _write(sm, existing.replace("</urlset>", adds + "</urlset>"))
        return True
    except Exception as e:
        print("sitemap patch failed:", str(e)[:160], file=sys.stderr)
        return False


def publish_articles(articles, *, site_dir=None, cities_nav=None):
    """Render + write each ORIGINAL article to <site_dir>/blog/<slug>/index.html, patch sitemap.
    Returns [{slug,url,title,product}]. Refuses any article carrying a reposted-source field."""
    site_dir = site_dir or _SITE_DIR
    blog_dir = os.path.join(site_dir, "blog")
    out, urls = [], []
    for a in articles or []:
        html, slug, url, title = render_article(a, cities_nav=cities_nav)
        _write(os.path.join(blog_dir, slug, "index.html"), html)
        urls.append(url)
        out.append({"slug": slug, "url": url, "title": title, "product": a.get("product")})
    _patch_sitemap(site_dir, urls)
    return out


def _cli():
    if len(sys.argv) >= 3 and sys.argv[1] == "publish":
        with open(sys.argv[2], encoding="utf-8") as f:
            data = json.load(f)
        articles = data.get("articles", data) if isinstance(data, dict) else data
        results = publish_articles(articles)
        print(f"published {len(results)} original page(s):")
        for r in results:
            print(f"  {r['url']}  [{r['product']}]  {r['title']}")
        return
    print(selftest())


def selftest():
    # an authored article renders; a reposting attempt is refused.
    art = {"product": "seller_why_not_selling",
           "title": "Why isn't my house selling?",
           "lead": "Six weeks, barely a viewing, and the silence is starting to get to you.",
           "sections": [{"h": "It's almost always the price", "body": "If you're sat there "
                         "refreshing Rightmove wondering what's wrong with your photos, start "
                         "with the number."}],
           "faqs": [("Why is my house not selling?", "Usually the asking price is above what the "
                     "street has actually sold for.")]}
    html, slug, url, title = render_article(art)
    assert "<title>" in html and "start=p_seller_why_not_selling" in html
    assert "reddit" not in html.lower(), "no reddit reference may ever appear"
    refused = False
    try:
        spec_from_article({"product": "buyer_is_overpriced", "title": "x", "quote": "someone's words"})
    except ValueError:
        refused = True
    assert refused, "must refuse a reposted-source field"
    return "ok"


if __name__ == "__main__":
    _cli()
