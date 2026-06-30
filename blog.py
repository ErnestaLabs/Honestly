#!/usr/bin/env python3
"""blog.py - the SEO/AEO sealed template for the daily postcode-district report.

One canonical render model (market_district.gather) feeds one sealed HTML template, so
two districts never share numbers - only the data varies. Same shape, different postcode,
packed with that district's own real transaction intelligence. This is the report-as-
acquisition-node: every page is built to be cited by answer engines AND to convert a
reader into a Telegram activation.

What makes a page rank and get cited (AEO/GEO + classic SEO), all implemented here:
  * Semantic HTML5 (article / section / table) with one H1 and a clean heading tree.
  * An above-the-fold ANSWER BOX: a 40-60 word, fact-dense, directly-quotable paragraph
    that answers "what is the SE15 property market like?" in the first screen - the shape
    answer engines lift verbatim.
  * Structured data: JSON-LD Article, Dataset, Place, FAQPage and BreadcrumbList, so the
    page is machine-readable as a dataset about a named place, not just prose.
  * Fact tables (sold by type, bedroom mix, live market, area) - scannable, entity-rich.
  * A real FAQ answered from the district's own numbers (buyers, sellers, investors).
  * A numbered, academic References list (honest by construction - only sources used).
  * An internal-link mesh: sibling districts in the same city + every city series + the
    index, so authority flows across the network (the distributed-growth-network idea).
  * CTAs at every decision point, Telegram primary (the primary success metric).

Honesty posture (ABSOLUTE): the page issues no valuation. It reports transactions, listings,
the regional HPI (beside the figures, never blended in) and free area context. Every
block self-labels "not available" when its source is down; nothing is invented.

Public surface:
  render_post(model, siblings=, cities_nav=)  -> full district HTML page
  render_city_hub(city, posts, cities_nav=)   -> a city series hub page
  render_index(by_city, cities_nav=)          -> the /blog landing page
  build_sitemap(urls)                         -> sitemap.xml
  build_rss(items)                            -> RSS 2.0 feed for the network
"""
import os, html, json, datetime, urllib.parse

import brand
import ads
import social_sentiment

SITE = os.environ.get("BLOG_SITE_URL", "https://usehonestly.co.uk").rstrip("/")
BOT = os.environ.get("BLOG_BOT_URL", "https://t.me/usehonestly_bot")
AFFILIATE = os.environ.get("BLOG_AFFILIATE_URL", "")   # only rendered if set (no fake link)
BLOG_BASE = "/blog"

# Remark42 comments (self-hosted, open-source, MIT). The reader comments with NO account -
# anonymous login is enabled on our own Remark42 server (AUTH_ANON=true) - and it's OUR server,
# not a SaaS or third party, so the discussion (and the ad slot beside it) stays 100% ours.
# Rendered ONLY when REMARK_URL is set (same "no fake link" rule as AFFILIATE above), so the
# live static site is unchanged until the Remark42 backend is actually up. The widget loads
# from our REMARK_URL host, never a third-party CDN. See deploy/remark42/ for standing it up.
REMARK_URL = os.environ.get("REMARK_URL", "").rstrip("/")   # e.g. https://usehonestly.co.uk/remark42
REMARK_SITE = os.environ.get("REMARK_SITE", "honestly")     # Remark42 SITE id (groups our pages)


# ----------------------------------------------------------------- small helpers
def e(s):
    return html.escape(str(s if s is not None else ""), quote=True)


# A missing figure renders as a muted dash, never the literal string "n/a". On a property-
# intel page the word "n/a" reads as self-sabotage; a dash is the conventional "no figure
# recorded" mark in a financial table. Headline surfaces are structurally guarded upstream
# (the publish gate + _answer_paragraph + _kpi_grid only emit a figure we actually hold), so
# this dash can only ever surface in a detailed breakdown sub-cell, where it reads cleanly.
NA = "-"


def money(v):
    try:
        return "£{:,.0f}".format(round(float(v)))
    except (TypeError, ValueError):
        return NA


def money_short(v):
    """Hero-scale money: £480k, £1.8m."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return NA
    if v >= 1_000_000:
        return f"£{v/1_000_000:.2f}m".replace(".00m", "m")
    if v >= 1_000:
        return f"£{v/1000:.0f}k"
    return f"£{v:.0f}"


def pct(v, signed=True):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return NA
    return (f"{v:+.1f}%" if signed else f"{v:.1f}%")


# The official register that records sold prices depends on the country. HM Land Registry's
# Price Paid Data covers England & Wales ONLY; Scotland's transactions are recorded by
# Registers of Scotland, and Northern Ireland's by Land & Property Services. They all reach
# us through PropertyData, so the figures are real either way - but citing "HM Land Registry"
# on an Edinburgh or Glasgow page is a factual error (the EH2 self-sabotage's quieter cousin).
# These helpers make the citation follow the city's country so it is never wrong.
def _sold_authority(country):
    """Full dataset citation, e.g. 'HM Land Registry Price Paid Data' / 'Registers of Scotland'."""
    c = (country or "").strip().lower()
    if c == "scotland":
        return "Registers of Scotland"
    if c in ("northern ireland", "n. ireland", "ni"):
        return "Land & Property Services (Northern Ireland)"
    return "HM Land Registry Price Paid Data"


def _sold_authority_name(country):
    """Short body name, e.g. 'HM Land Registry' / 'Registers of Scotland'."""
    c = (country or "").strip().lower()
    if c == "scotland":
        return "Registers of Scotland"
    if c in ("northern ireland", "n. ireland", "ni"):
        return "Land & Property Services (Northern Ireland)"
    return "HM Land Registry"


def _country_of(model):
    return ((model or {}).get("city") or {}).get("country", "")


def _study_authorities(study):
    """Correct sold-data citation for the multi-city study, derived from the countries
    actually present in the data. The study spans English and Scottish city centres, and
    each country's sold prices are recorded by a different official register, so a single
    'HM Land Registry' label would be wrong. Returns the precise list, never over-claiming
    a register for a country that is not in the data."""
    countries = ((study or {}).get("agg") or {}).get("countries") or []
    names, seen = [], set()
    for c in countries:
        a = _sold_authority_name(c)
        if a not in seen:
            seen.add(a)
            names.append(a)
    if not names:                                   # nothing tagged: fall back to the E&W register
        names = ["HM Land Registry"]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def post_url(slug):
    return f"{BLOG_BASE}/{slug}/"


def hub_url(city_slug):
    return f"{BLOG_BASE}/city/{city_slug}/"


def meta_clip(text, n=157):
    """Trim prose to a meta-description-safe length on a word boundary, adding an ellipsis
    only when it actually cut. One source of truth so every surface (post, hub, index) keeps
    its <meta name=description> inside the ~160-char window the SEO audit enforces."""
    text = (text or "").strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0].rstrip(",;:- ")
    return cut + "..."


def brand_name():
    """The brand name rendered to echo the wordmark - lowercase 'honestly', navy with a
    teal final 'y' - so every human-visible mention cements the logo in the reader's head.
    Machine-readable contexts (title, meta, JSON-LD, og, alt) keep the plain 'Honestly'
    string; only on-page prose uses this. Not a recreation of the logo GRAPHIC (the
    masthead still serves the real PNG): a typographic echo of the NAME in the body sans,
    which is the only safe move without loading a guessed webfont for the wordmark face."""
    return '<span class="brandname">honestl<span class="brand-y">y</span></span>'


def _district_name(model):
    """A human label for the district: 'SE15, Peckham (Southwark)' style when geo gives
    a borough/ward, else just the outcode."""
    d = model["district"]
    g = model.get("geo") or {}
    bits = []
    if g.get("ward"):
        bits.append(g["ward"])
    boroughs = g.get("districts") or ([g["district"]] if g.get("district") else [])
    if boroughs:
        bits.append("/".join(boroughs[:2]))
    return f"{d}" + (f", {bits[0]}" if bits else "") + (f" ({bits[1]})" if len(bits) > 1 else "")


# ----------------------------------------------------------------- the answer box
def _answer_paragraph(model):
    """The 40-60 word, fact-dense, quotable answer. Built ONLY from figures we actually
    hold: every clause is dropped when its figure is absent, so the answer never states a
    number we do not have and never prints "n/a" (a property-intel page that headlines
    "n/a" is self-sabotage). The lead clause is whichever real figure we hold, in priority
    order sold median -> live asking median -> regional index, so a genuinely thin district
    (no recorded sales yet) opens on something true rather than a blank. Asking prices are
    always labelled as asking, never implied to be a sold figure."""
    d, city = model["district"], model["city"]
    s = model.get("sold") or {}
    l = model.get("listings") or {}
    h = model.get("hpi") or {}
    sold_med = s.get("median_price") if s.get("ok") else None
    ask_med = l.get("asking_median") if l.get("ok") else None
    parts = []
    if sold_med:
        lead = (f"in {d}, the median recorded sale price across all property types is "
                f"{money(sold_med)}")
        if s.get("psm_median"):
            lead += f" (about {money(s['psm_median'])} per square metre)"
        parts.append(lead)
        if s.get("total"):
            parts.append(f"across {s['total']} sales in the last "
                         f"{s.get('recency',{}).get('window_months',24)} months, "
                         f"{s.get('recency',{}).get('last_12m','-')} of them in the last year")
        if ask_med:
            parts.append(f"homes currently list at a median {money(ask_med)} and sit "
                         f"about {l.get('mean_dom','-')} days on the market")
    elif ask_med:
        # No settled-sale median for this district yet - lead honestly on live asking prices,
        # clearly labelled as asking, so we never imply a sold figure we do not have.
        parts.append(f"in {d}, homes currently list at a median asking price of "
                     f"{money(ask_med)} across {l.get('n','-')} live listings, sitting about "
                     f"{l.get('mean_dom','-')} days on the market")
        parts.append("there are too few recorded sales to publish a reliable sold median for "
                     "the district yet")
    elif h.get("ok") and h.get("average_price"):
        parts.append(f"recorded sales are too thin in {d} to publish a reliable district sold "
                     f"median yet; the wider {city['name']} index sits at a "
                     f"{money(h['average_price'])} average")
    else:
        parts.append(f"transaction data for {d} is not currently available")
    # Year-on-year HPI tail, but only when we did not already lead on the index.
    if h.get("ok") and h.get("annual_change_pct") is not None and (sold_med or ask_med):
        parts.append(f"the wider {city['name']} index is {pct(h['annual_change_pct'])} year on year")
    # Each clause is its own sentence, so capitalise the first letter of each before joining
    # (the trailing clauses are written lower-case to read as a comma list, but we present
    # them as sentences in the answer box).
    txt = ". ".join(p[:1].upper() + p[1:] for p in parts).rstrip(".") + "."
    return txt


# ----------------------------------------------------------------- sections
def _kpi_grid(model):
    s = model.get("sold") or {}
    l = model.get("listings") or {}
    h = model.get("hpi") or {}
    cells = []

    def cell(label, value, sub=""):
        cells.append(
            f'<div class="kpi"><div class="kpi-v">{e(value)}</div>'
            f'<div class="kpi-l">{e(label)}</div>'
            + (f'<div class="kpi-s">{e(sub)}</div>' if sub else "") + "</div>")

    # Every KPI cell is gated on the figure actually being present, so the grid never shows a
    # "n/a" tile - a missing figure means no tile, never a blank-looking core number.
    if s.get("ok"):
        if s.get("median_price"):
            cell("Median sale price", money_short(s.get("median_price")),
                 f"{s.get('total','-')} sales / {s.get('recency',{}).get('window_months',24)}m")
        if s.get("psm_median"):
            cell("Price per m²", money(s["psm_median"]), "sold, all types")
        cell("Sales last 12 months", s.get("recency", {}).get("last_12m", "-"),
             "transaction activity")
    if l.get("ok"):
        if l.get("asking_median"):
            cell("Asking median", money_short(l.get("asking_median")), f"{l.get('n','-')} live")
        cell("Days on market", l.get("mean_dom", "-"), "average, live stock")
        if l.get("stuck_n") is not None:
            cell("Stuck 90+ days", l["stuck_n"], f"of {l.get('available_n','-')} available")
    if h.get("ok"):
        cell(f"{model['city']['name']} index YoY", pct(h.get("annual_change_pct")),
             f"HPI {h.get('month','')}")
    if not cells:
        return ""
    return '<div class="kpis">' + "".join(cells) + "</div>"


# ----------------------------------------------------------------- charts
# Pure-CSS horizontal bar charts. No SVG text-measurement pain, no JS, no network, no CDN -
# they render offline from a Telegram-saved file and theme themselves from brand.HEX. Every
# value is also live text in the DOM (the bar-val), so screen readers and the SEO/AEO audit
# read the real figures, not a picture of them. We only ever chart CATEGORICAL data we hold
# (sold by type, bedroom mix, asking-vs-sold, live-stock counts, district medians) - never a
# trend line, because the HPI block is a single-month snapshot and a line would be invented.
def _pctw(v, vmax):
    """Bar width as a percentage of the chart max, floored at 3% so a real-but-tiny value is
    still visibly a bar (and never a misleading zero)."""
    if not vmax or not v:
        return 0
    return max(3, round(v / vmax * 100))


def _bar_chart(caption, rows, *, fmt=money, note="", vmax=None):
    """A horizontal bar chart from rows of (label, value, sub, colour_key). value is numeric;
    sub is an optional small line under the label; colour_key is a brand.HEX key. Rows with a
    falsy value are dropped. vmax fixes the scale (use it when bars are shares of a known
    total, e.g. live-stock counts out of N); otherwise the largest value sets full width."""
    rows = [r for r in rows if r[1]]
    if not rows:
        return ""
    H = brand.HEX
    mx = vmax or max(r[1] for r in rows)
    bars = ""
    for r in rows:
        lab, val = r[0], r[1]
        sub = r[2] if len(r) > 2 else ""
        fill = H.get(r[3] if len(r) > 3 else "green", H["green"])
        sub_html = f'<span class="bar-sub">{e(sub)}</span>' if sub else ""
        bars += (f'<div class="bar-row"><span class="bar-label">{e(lab)}{sub_html}</span>'
                 f'<span class="bar-track"><span class="bar-fill" '
                 f'style="width:{_pctw(val, mx)}%;background:{fill}"></span></span>'
                 f'<span class="bar-val">{e(fmt(val))}</span></div>')
    note_html = f'<p class="chart-note">{e(note)}</p>' if note else ""
    return (f'<figure class="chart"><figcaption class="chart-cap">{e(caption)}</figcaption>'
            f'<div class="bars">{bars}</div>{note_html}</figure>')


def _chart_asking_vs_sold(model):
    """The brand's signature visual: sold and asking medians as two bars in DISTINCT colours,
    side by side and explicitly never blended. Sold (green) is what completed; asking (gold)
    is vendor expectation only."""
    s = model.get("sold") or {}
    l = model.get("listings") or {}
    if not (s.get("ok") and l.get("ok")):
        return ""
    sm, am = s.get("median_price"), l.get("asking_median")
    if not (sm and am):
        return ""
    rows = [("Sold median", sm, "what buyers actually paid", "green"),
            ("Asking median", am, "what sellers are asking", "gold")]
    return _bar_chart(
        f"Asking vs sold in {model['district']}", rows, fmt=money,
        note=f"Shown side by side and never blended. Sold prices are the "
             f"{_sold_authority_name(_country_of(model))} record of completed sales; asking "
             f"prices are live vendor expectation, context only. This page is not a valuation.")


def _chart_sold_by_type(model):
    s = model.get("sold") or {}
    if not s.get("ok"):
        return ""
    rows = [(bt["label"], bt.get("median"), f"{bt['n']} sales", "green")
            for bt in s.get("by_type", []) if bt.get("n") and bt.get("median")]
    if len(rows) < 2:
        return ""
    return _bar_chart(
        f"Median sold price by property type in {model['district']}", rows, fmt=money,
        note=f"{_sold_authority(_country_of(model))} - the median of what actually completed, by type.")


def _chart_beds_mix(model):
    s = model.get("sold") or {}
    beds = s.get("beds_mix") or {}
    rows = [(f"{k}-bed", v, "", "teal") for k, v in beds.items()]
    if len(rows) < 2:
        return ""
    return _bar_chart(
        "Recorded sales by number of bedrooms", rows,
        fmt=lambda v: f"{v} sale" + ("" if v == 1 else "s"),
        note="Count of recorded sales by bedroom count, where the registered record carries it.")


def _chart_market_pace(model):
    l = model.get("listings") or {}
    if not l.get("ok") or not l.get("n"):
        return ""
    n = l["n"]
    rows = [("Fresh (<=20 days)", l.get("fresh_n"), "", "green"),
            ("Available", l.get("available_n"), "", "teal"),
            ("Under offer", l.get("under_offer_n"), "", "navy"),
            ("Stuck (90+ days)", l.get("stuck_n"), "", "gold")]
    rows = [r for r in rows if r[1]]
    if len(rows) < 2:
        return ""
    return _bar_chart(
        f"Live stock in {model['district']}", rows, fmt=lambda v: f"{v}", vmax=n,
        note=f"Each measure as a count out of {n} live listings. The measures can overlap (a "
             f"fresh listing may also be under offer), so they are separate bars, not a single "
             f"divided total.")


def _chart_gross_yield(model):
    """Gross rental yield by property type - PropertyData's published estimate, charted as
    categorical bars (never a trend line). Each bar is labelled with its bed count so it never
    implies a figure speaks for a whole type."""
    rt = model.get("rent") or {}
    if not rt.get("ok"):
        return ""
    rows = [(f"{r['beds']}-bed {r['label'].lower()}", r.get("gross_yield"),
             f"from {r['yield_n']} listings" if r.get("yield_n") else "", "teal")
            for r in rt.get("rows", []) if r.get("gross_yield") is not None]
    if len(rows) < 2:
        return ""
    return _bar_chart(
        f"Gross rental yield by property type in {model['district']}", rows,
        fmt=lambda v: f"{v}%",
        note="Gross yield is PropertyData's estimate of a year's rent as a share of price, "
             "before letting costs, voids and tax. It is a market ratio shown beside its "
             "inputs, not a valuation or a return you are guaranteed.")


def _chart_district_medians(name, posts, country=""):
    """City-hub overview: each district's own median sale price as a bar. Honest by
    construction - it only reuses the headline_price each district report already publishes."""
    rows = [(p["district"], p["headline_price"], "", "green")
            for p in posts if p.get("headline_price")]
    if len(rows) < 2:
        return ""
    rows.sort(key=lambda r: r[1], reverse=True)
    return _bar_chart(
        f"Median sale price by {name} postcode district", rows, fmt=money_short,
        note=f"Each bar is that district's own median recorded sale price "
             f"({_sold_authority(country)}). Open any district below for its full evidence.")


# ----------------------------------------------------------------- cover (section front)
def _cover(kicker_html, h1_html, brief_text, stats=None, meta_html=""):
    """The report head, in the printed-appraisal idiom that the PDF and the interactive HTML
    already use: a green eyebrow kicker, a serif navy headline on the paper ground, an optional
    edition/dateline under a hairline, the AEO brief as the page's standfirst, and an optional
    facts panel rendered in the report's own cream kv-panel language. No dark hero, no gradient
    text, no animated glows - this matches report.py and appraise.interactive_chart, not a SaaS
    landing. kicker_html/h1_html/meta_html are already HTML (caller controls markup); brief_text
    is plain and escaped here. The brief stays a verbatim standfirst paragraph so the answer-box
    contract the SEO/AEO audit checks holds."""
    facts_html = ""
    if stats:
        cells = "".join(
            f'<div class="hf"><span class="hf-v">{e(v)}</span>'
            f'<span class="hf-l">{e(lab)}</span></div>'
            for (v, lab) in stats if v not in (None, ""))
        if cells:
            facts_html = f'<div class="herofacts">{cells}</div>'
    meta = f'<p class="dateline">{meta_html}</p>' if meta_html else ""
    return (f'<header class="report-head">'
            f'<div class="rh-body">'
            f'<p class="kicker">{kicker_html}</p>'
            f'<h1>{h1_html}</h1>{meta}'
            f'<p class="standfirst">{e(brief_text)}</p>'
            f'{facts_html}</div></header>')


def _sold_section(model):
    s = model.get("sold") or {}
    if not s.get("ok"):
        return ('<section id="sold"><h2>Sold prices</h2>'
                f'<p class="na">Sold-price data is not currently available for '
                f'{e(model["district"])}.</p></section>')
    rows = ""
    for bt in s.get("by_type", []):
        if not bt.get("n"):
            continue
        rows += (f"<tr><td>{e(bt['label'])}</td><td>{bt['n']}</td>"
                 f"<td>{money(bt.get('median'))}</td>"
                 f"<td>{money(bt.get('psm_median'))}</td></tr>")
    beds = s.get("beds_mix") or {}
    bedrows = "".join(
        f"<tr><td>{e(k)}-bed</td><td>{v}</td></tr>" for k, v in beds.items())
    rec = s.get("recency", {})
    return f"""<section id="sold">
  <h2>Sold prices in {e(model['district'])}</h2>
  <p>Across the last {rec.get('window_months',24)} months, {s['total']} sales are on
  record in {e(model['district'])} - a median of {money(s.get('median_price'))}, ranging
  {money(s.get('price_low'))} to {money(s.get('price_high'))}. {rec.get('last_12m','-')}
  sales completed in the last 12 months. Figures are {_sold_authority(_country_of(model))},
  the official record of what actually changed hands.</p>
  <table class="data"><caption>Sold price by property type</caption>
  <thead><tr><th>Type</th><th>Sales</th><th>Median price</th><th>Median £/m²</th></tr></thead>
  <tbody>{rows}</tbody></table>
  {("<table class='data'><caption>Bedroom mix of recorded sales</caption>"
    "<thead><tr><th>Size</th><th>Sales</th></tr></thead><tbody>"
    + bedrows + "</tbody></table>") if bedrows else ""}
  {_chart_sold_by_type(model)}
  {_chart_beds_mix(model)}
</section>"""


def _evidence_section(model):
    s = model.get("sold") or {}
    sample = s.get("sample") or []
    # Honesty contract: a sold price is only shown as evidence when the reader can open
    # the official HM Land Registry record for that exact transaction. Rows without a
    # verification link are dropped, never displayed as an unprovable claim.
    sample = [r for r in sample if r.get("url")]
    if not sample:
        return ""
    rows = ""
    for r in sample:
        link = (f'<a href="{e(r["url"])}" rel="nofollow noopener" target="_blank">'
                f'View on HM Land Registry</a>')
        rows += (f"<tr><td>{e(r.get('date') or '')}</td>"
                 f"<td>{e(r.get('postcode') or '')}</td>"
                 f"<td>{money(r.get('price'))}</td>"
                 f"<td>{e((r.get('type') or '').replace('_',' '))}</td>"
                 f"<td>{link}</td></tr>")
    n_drop = len((s.get('sample') or [])) - len(sample)
    note = ("" if not n_drop else
            f" Sales we cannot yet link to a register entry are not shown here.")
    return f"""<section id="evidence">
  <h2>Recent transaction evidence</h2>
  <p>The most recent recorded sales in {e(model['district'])}. Every row is a real
  registered transaction - follow "View on HM Land Registry" to open the registry's own
  record of that exact sale and confirm the price, address and date for yourself.{note}</p>
  <table class="data"><caption>Most recent recorded sales (each links to its HM Land Registry record)</caption>
  <thead><tr><th>Date</th><th>Postcode</th><th>Price</th><th>Type</th><th>Verify</th></tr></thead>
  <tbody>{rows}</tbody></table>
</section>"""


def _live_section(model):
    l = model.get("listings") or {}
    if not l.get("ok"):
        return ""
    return f"""<section id="live">
  <h2><span class="pulse-dot" aria-hidden="true"><i></i></span>The live market right now</h2>
  <p>There are {l['n']} properties currently on the market in {e(model['district'])}, at a
  median asking price of {money(l.get('asking_median'))} ({money(l.get('asking_low'))} to
  {money(l.get('asking_high'))}). They have been listed for an average of
  {l.get('mean_dom','-')} days. Asking prices signal vendor expectation - they are context,
  not evidence of value.</p>
  {_chart_asking_vs_sold(model)}
  <table class="data"><caption>Live on-market dynamics</caption>
  <thead><tr><th>Measure</th><th>Count</th></tr></thead><tbody>
    <tr><td>On the market</td><td>{l['n']}</td></tr>
    <tr><td>Available (not under offer)</td><td>{l.get('available_n','-')}</td></tr>
    <tr><td>Fresh (≤20 days)</td><td>{l.get('fresh_n','-')}</td></tr>
    <tr><td>Stuck (90+ days)</td><td>{l.get('stuck_n','-')}</td></tr>
    <tr><td>Under offer</td><td>{l.get('under_offer_n','-')}</td></tr>
  </tbody></table>
  {_chart_market_pace(model)}
</section>"""


def _rent_section(model):
    """The district's rental picture: typical long-let rent and PropertyData's gross yield,
    per type at a representative bed count. Rent and yield sit beside the sold and asking
    figures as their own reported facts - the page still issues no valuation. Degrades to
    nothing when no rental data came back."""
    rt = model.get("rent") or {}
    if not rt.get("ok"):
        return ""
    rows = rt.get("rows", [])
    hy = rt.get("headline_yield")
    hw = rt.get("headline_weekly")
    # an honest intro line that names what the figures are and what they are not
    lead = []
    if hw:
        lead.append(f"Typical long-let asking rent in {e(model['district'])} runs around "
                    f"{money(hw)} a week ({money(round(hw * 52 / 12))} a month)")
    if hy is not None:
        lead.append(f"a gross rental yield of about {hy}%")
    intro = (", ".join(lead) + ".") if lead else ""
    trs = ""
    for r in rows:
        wk = money(r["weekly"]) if r.get("weekly") else f'<span class="na">{NA}</span>'
        mo = money(r["monthly"]) if r.get("monthly") else f'<span class="na">{NA}</span>'
        gy = f"{r['gross_yield']}%" if r.get("gross_yield") is not None else f'<span class="na">{NA}</span>'
        n = r.get("rent_n") or r.get("yield_n") or 0
        trs += (f"<tr><td>{r['beds']}-bed {e(r['label'].lower())}</td>"
                f"<td>{wk}</td><td>{mo}</td><td>{gy}</td><td>{n}</td></tr>")
    return f"""<section id="rent">
  <h2>What it rents for, and the yield</h2>
  <p>{intro} Rent here is live long-let asking data, and the gross yield is PropertyData's own
  estimate - a year's rent as a share of price, <strong>before letting costs, voids and tax</strong>.
  It sits beside the sold and asking figures; like them, it is market context, not a
  valuation of any property.</p>
  <table class="data"><caption>Typical rent and gross yield by property type</caption>
  <thead><tr><th>Type</th><th>Per week</th><th>Per month</th><th>Gross yield</th><th>Listings</th></tr></thead>
  <tbody>{trs}</tbody></table>
  {_chart_gross_yield(model)}
</section>"""


def _audience_section(model):
    """Buyers, sellers and investors - three reads of the SAME numbers, no new figures."""
    s = model.get("sold") or {}
    l = model.get("listings") or {}
    h = model.get("hpi") or {}
    buyer, seller, invest = [], [], []

    if l.get("ok") and s.get("ok") and l.get("asking_median") and s.get("median_price"):
        gap = l["asking_median"] - s["median_price"]
        if gap > 0:
            buyer.append(f"Asking prices sit {money(gap)} above the median sale - there is "
                         f"room between what sellers want and what completes.")
            seller.append(f"The median sale is {money(s['median_price'])}; price to the "
                          f"evidence, not to the {money(l['asking_median'])} asking median, "
                          f"or you risk joining the {l.get('stuck_n','-')} stuck listings.")
        else:
            buyer.append("Asking prices are at or below the median sale - competition is "
                         "real; offers near asking are the norm.")
    if l.get("ok") and l.get("mean_dom") is not None:
        buyer.append(f"Average time on market is {l['mean_dom']} days - "
                     + ("a fast market, move decisively." if l['mean_dom'] < 45
                        else "a measured pace, there is time to do diligence."))
        seller.append(f"Expect roughly {l['mean_dom']} days to a sale at the right price.")
    if s.get("ok") and s.get("psm_median"):
        invest.append(f"The blended sold rate is {money(s['psm_median'])} per m² - your "
                      f"per-m² entry price is the cleanest cross-district comparison.")
    if s.get("ok") and s.get("recency"):
        invest.append(f"{s['recency'].get('last_12m','-')} sales in the last year signals "
                      f"liquidity - how easily you could exit.")
    rt = model.get("rent") or {}
    if rt.get("ok") and rt.get("headline_yield") is not None:
        invest.append(f"Gross rental yield is running near {rt['headline_yield']}% - a year's "
                      f"rent as a share of price, before letting costs and voids, not a "
                      f"guaranteed return.")
    if h.get("ok") and h.get("annual_change_pct") is not None:
        invest.append(f"The wider {model['city']['name']} index is "
                      f"{pct(h['annual_change_pct'])} year on year (context, not a forecast).")

    def col(title, items):
        if not items:
            return ""
        lis = "".join(f"<li>{x}</li>" for x in items)
        return f'<div class="aud"><h3>{e(title)}</h3><ul>{lis}</ul></div>'

    cols = col("If you are buying", buyer) + col("If you are selling", seller) \
        + col("If you are investing", invest)
    if not cols:
        return ""
    return (f'<section id="audiences"><h2>What the numbers mean for you</h2>'
            f'<div class="aud-grid">{cols}</div></section>')


def _days(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "-"
    return f"{n} day" + ("" if n == 1 else "s")


def _ad_unit(creative, position):
    """Render ONE paid ad. The mandatory 'Advertisement' label (UK ASA / CAP Code) and the
    rel="sponsored nofollow noopener" on the outbound link (Google's paid-link policy) are
    stamped HERE, in the renderer - config in ads.json can book a slot but it can never
    suppress the label or loosen the rel. That is the whole point of doing this in one place."""
    url = e(creative.get("url") or "#")
    headline = e(creative.get("headline") or "")
    body = creative.get("body")
    adv = creative.get("advertiser")
    img = creative.get("image")
    txt = [f'<span class="ad-headline">{headline}</span>']
    if body:
        txt.append(f'<span class="ad-copy">{e(body)}</span>')
    if adv:
        txt.append(f'<span class="ad-adv">Paid promotion by {e(adv)}</span>')
    media = (f'<img class="ad-img" src="{e(img)}" alt="" loading="lazy">' if img else "")
    return (f'<aside class="ad-unit ad-{e(position)}" aria-label="Advertisement">'
            f'<span class="ad-label">Advertisement</span>'
            f'<a class="ad-body" href="{url}" target="_blank" rel="sponsored nofollow noopener">'
            f'{media}<span class="ad-text">{"".join(txt)}</span></a></aside>')


def _ad_slot(surface, position, *, slug=None):
    """Every creative booked for this surface+position, each rendered as a labelled ad unit.
    Returns '' when nothing is booked, so the slot is simply invisible until it is sold - the
    page never shows an empty ad frame."""
    booked = ads.slots(surface, position, slug=slug)
    if not booked:
        return ""
    return "".join(_ad_unit(c, position) for c in booked)


def _watch_sponsored_card(fl):
    """A paid 'listings to watch' card. Marked Sponsored (ASA/CAP) and its outbound link forced
    to rel="sponsored nofollow noopener" (Google paid-link policy) - both stamped here, never in
    config. It sits ALONGSIDE the organic picks and flips the block's disclosure (see below)."""
    meta_bits = []
    if fl.get("beds"):
        meta_bits.append(f"{fl['beds']} bed")
    if fl.get("type"):
        meta_bits.append(e(str(fl["type"]).replace("_", " ")))
    meta = " &middot; ".join(meta_bits)
    addr = e(fl.get("address") or "")
    portal = e(fl.get("portal") or fl.get("advertiser") or "the advertiser")
    link = e(fl.get("url") or "#")
    return (f'<div class="watch-card watch-sponsored">'
            f'<div class="watch-badge watch-sponsored-badge">Sponsored</div>'
            f'<div class="watch-headline">{e(fl.get("headline",""))}</div>'
            f'<div class="watch-price">{money(fl.get("price"))}</div>'
            f'<div class="watch-meta">{meta}</div>'
            f'<div class="watch-addr">{addr}</div>'
            f'<p class="watch-reason">A paid placement by {e(fl.get("advertiser") or portal)}. '
            f'Not an editorial pick; no claim is made about its price - it is an advertisement.</p>'
            f'<a class="watch-link" href="{link}" target="_blank" rel="sponsored nofollow noopener">'
            f'View on {portal} &rarr;</a></div>')


def _watch_reason(p):
    """One honest sentence per pick, grounded only in this listing's own asking price against
    the relevant sold median. Asking is context, never evidence of value - the copy says so."""
    vs = p.get("vs_median_pct")
    ref = p.get("ref_median")
    basis = p.get("ref_basis") or "the local"
    dom = p.get("dom") or 0
    key = p.get("reason_key")
    if key == "bargain":
        if vs is not None and vs < 0 and ref:
            return (f"Asking {money(p.get('price'))} - about {abs(vs)}% below the "
                    f"{e(basis)} sold median of {money(ref)}. A keen asking price is not proof "
                    f"of a bargain, but it is where a buyer starts looking.")
        return (f"Asking {money(p.get('price'))} - one of the lower-priced listings in the "
                f"district right now. Worth a buyer's closer look against the sold evidence.")
    if key == "overpriced":
        if vs is not None and vs > 0 and ref:
            return (f"Asking {money(p.get('price'))} - about {vs}% above the {e(basis)} sold "
                    f"median of {money(ref)}, after {_days(dom)} on the market. Priced above "
                    f"what the evidence has been completing at, which is how listings end up sitting.")
        return (f"Asking {money(p.get('price'))} after {_days(dom)} on the market - a reminder "
                f"that price beyond the sold evidence is what keeps a listing waiting.")
    # stalled (agents)
    return (f"On the market {_days(dom)}. A stalled instruction - the sold evidence is the "
            f"pricing conversation an agent can have to get it moving again.")


def _watch_section(model):
    """Three live listings to watch - one each for buyers, sellers and agents - drawn at random
    from every listing that genuinely qualifies on its measure. Each links out to the public
    portal listing so the reader can verify it. This is the paid-placement surface in waiting:
    a listing can be featured by default, but it is never guaranteed and never paid for here."""
    w = model.get("watch") or {}
    if not w.get("ok") or not w.get("picks"):
        return ""
    aud_label = {"buyers": "For buyers", "sellers": "For sellers", "agents": "For agents"}
    cards = []
    sponsored = ads.featured_listing(model.get("district"))
    if sponsored:
        cards.append(_watch_sponsored_card(sponsored))
    for p in w["picks"]:
        aud = p.get("audience")
        meta_bits = []
        if p.get("beds"):
            meta_bits.append(f"{p['beds']} bed")
        if p.get("type"):
            meta_bits.append(e(str(p["type"]).replace("_", " ")))
        meta_bits.append("under offer" if p.get("sstc") else "available")
        if p.get("dom") is not None:
            meta_bits.append(f"listed {_days(p['dom'])}")
        meta = " &middot; ".join(meta_bits)
        addr = e(p.get("address") or "Address withheld until enquiry")
        portal = e(p.get("portal") or "the portal")
        link = e(p.get("link") or "#")
        cards.append(f"""<div class="watch-card watch-{e(aud)}">
    <div class="watch-badge">{e(aud_label.get(aud, aud))}</div>
    <div class="watch-headline">{e(p.get('headline',''))}</div>
    <div class="watch-price">{money(p.get('price'))}</div>
    <div class="watch-meta">{meta}</div>
    <div class="watch-addr">{addr}</div>
    <p class="watch-reason">{_watch_reason(p)}</p>
    <a class="watch-link" href="{link}" target="_blank" rel="nofollow noopener noreferrer">
      View on {portal} &rarr;</a>
  </div>""")
    if sponsored:
        note = ("<strong>How these are chosen.</strong> The card marked <em>Sponsored</em> is a "
                "paid advertisement - not an editorial pick and not a price claim. The other cards "
                "are editorial picks: one live listing for buyers, one for sellers and one for "
                "agents, drawn at random from every listing in this district that genuinely "
                "qualifies on that measure - a keen asking price, a price sitting above the sold "
                "evidence, or a long-stalled instruction - and those are never paid for. Asking "
                "prices are context, not evidence of value; this page is not a valuation.")
    else:
        note = ("<strong>How these are chosen.</strong> One live listing is selected for buyers, "
                "one for sellers and one for agents, drawn at random from every listing in this "
                "district that genuinely qualifies on that measure - a keen asking price, a price "
                "sitting above the sold evidence, or a long-stalled instruction. Selection is "
                "possible by default but never guaranteed, and no placement here is paid for. "
                "Asking prices are context, not evidence of value; this page is not a valuation.")
    return (f'<section id="watch"><h2>Listings to watch in {e(model["district"])}</h2>'
            f'<div class="watch-grid">{"".join(cards)}</div>'
            f'<p class="watch-note">{note}</p></section>')


# Map a displayed amenity category to a clean Google Maps search term, so tapping the row
# opens that category on a live map centred on the postcode (the count itself stays the
# OSM-sourced figure - the link is a "see them on a map" affordance, not a second source).
_AMENITY_QUERY = {
    "Stations": "train station", "Bus stops": "bus stop", "Schools": "school",
    "Supermarkets": "supermarket", "Cafes & restaurants": "restaurants and cafes",
    "Green space": "park", "GP & pharmacy": "pharmacy",
}


def _latlng(model):
    """The postcode-district centroid as 'lat,lng' (5dp), or None. Used to centre every map
    link on the actual place rather than a name guess."""
    g = model.get("geo") or {}
    loc = (model.get("area") or {}).get("location") or {}
    lat, lng = g.get("lat") or loc.get("lat"), g.get("lng") or loc.get("lng")
    if lat is None or lng is None:
        return None
    try:
        return f"{float(lat):.5f},{float(lng):.5f}"
    except (TypeError, ValueError):
        return None


def _gmap_browse(latlng, query):
    """A Google Maps link that drops the reader into <query> centred on the postcode centroid -
    e.g. every supermarket near SE15. Path form so the @lat,lng,zoom actually centres the map."""
    return (f"https://www.google.com/maps/search/{urllib.parse.quote(query)}/@{latlng},15z")


def _gmap_place(query):
    """A Google Maps link to a named place (the nearest station)."""
    return ("https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(query))


def _gmap_dir(origin_latlng, dest_query):
    """A Google Maps directions link from the postcode centroid to a named destination."""
    return ("https://www.google.com/maps/dir/?api=1&origin=" + urllib.parse.quote(origin_latlng)
            + "&destination=" + urllib.parse.quote(dest_query))


def _maplink(url, text, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f'<a{c} href="{e(url)}" target="_blank" rel="noopener">{text}</a>'


def _area_section(model):
    a = model.get("area") or {}
    blocks = []
    ll = _latlng(model)
    cityname = (model.get("city") or {}).get("name") or ""
    loc = a.get("location") or {}
    legs = loc.get("rows") or loc.get("legs") or []
    if legs:
        items = []
        for x in legs:
            label = x.get("label", "")
            prefix, name = (label.rsplit(": ", 1) if ": " in label else ("", label))
            tail = ((f" ({e(x.get('dist'))})" if x.get("dist") else "")
                    + (f", {e(x.get('time'))}" if x.get("time") else ""))
            is_station = "station" in (prefix + " " + label).lower()
            dest = name + (" station" if is_station and "station" not in name.lower() else "")
            dest_q = dest + (", " + cityname if cityname else "")
            sep = (e(prefix) + ": ") if prefix else ""
            line = sep + _maplink(_gmap_place(dest_q), e(name)) + tail
            if ll:
                line += " " + _maplink(_gmap_dir(ll, dest_q),
                                       "Directions &rsaquo;", cls="area-dir")
            items.append(f"<li>{line}</li>")
        blocks.append(f"<div class='area-card'><h3>Connectivity</h3><ul>{''.join(items)}</ul></div>")
    am = a.get("area") or {}
    if am.get("ok") and am.get("counts"):
        rows = []
        for k, v in am["counts"].items():
            cell = e(k)
            if ll:
                q = _AMENITY_QUERY.get(k) or k.replace(" &", "").lower()
                cell = _maplink(_gmap_browse(ll, q), e(k))
            rows.append(f"<tr><td>{cell}</td><td>{v}</td></tr>")
        note = ("<p class='area-note'>Tap a category to see it on the map.</p>" if ll else "")
        blocks.append(f"<div class='area-card'><h3>Amenities within 800m</h3>"
                      f"<table class='mini'><tbody>{''.join(rows)}</tbody></table>{note}</div>")
    sf = a.get("safety") or {}
    if sf.get("ok"):
        top = "".join(f"<tr><td>{e(c)}</td><td>{n}</td></tr>"
                      for c, n in (sf.get("by_category") or [])[:6])
        blocks.append(f"<div class='area-card'><h3>Safety</h3>"
                      f"<p>{sf.get('total','-')} crimes recorded {e(sf.get('month',''))} "
                      f"{e(sf.get('radius_note',''))}.</p>"
                      f"<table class='mini'><tbody>{top}</tbody></table></div>")
    env = a.get("environment") or {}
    if env:
        lines = []
        if env.get("flood", {}).get("ok"):
            lines += env["flood"].get("lines", [])
        if env.get("air", {}).get("ok"):
            lines += env["air"].get("lines", [])
        if lines:
            blocks.append("<div class='area-card'><h3>Environment</h3><ul>"
                          + "".join(f"<li>{e(x)}</li>" for x in lines) + "</ul></div>")
    pl = a.get("planning") or {}
    if pl.get("ok"):
        st = "; ".join(f"{e(s)} {n}" for s, n in (pl.get("by_status") or [])[:4])
        blocks.append(f"<div class='area-card'><h3>Planning &amp; development</h3>"
                      f"<p>{pl.get('total','-')} recent applications within ~0.5km. {st}.</p>"
                      f"</div>")
    photo = _area_photo_block(model)
    if not blocks and not photo:
        return ""
    return (f'<section id="area"><h2>Area intelligence</h2>{photo}'
            f'<div class="area-grid">{"".join(blocks)}</div></section>')


def _hpi_section(model):
    h = model.get("hpi") or {}
    if not h.get("ok"):
        return ""
    return f"""<section id="context">
  <h2>Wider market context</h2>
  <p>The UK House Price Index for {e(model['city']['name'])} stands at an average of
  {money(h.get('average_price'))} in {e(h.get('month',''))}, {pct(h.get('annual_change_pct'))}
  over the year and {pct(h.get('monthly_change_pct'))} over the month. This is the regional
  index - it sits beside the {e(model['district'])} figures as background and never moves a
  local price. The transaction figures above are what actually happened in this postcode.</p>
</section>"""


# ----------------------------------------------------------------- FAQ (+ schema)
def _faqs(model):
    """Return [(question, answer_html, answer_text)] built from the real numbers. The text
    form feeds the FAQPage JSON-LD; the html form renders on the page."""
    d = model["district"]
    s = model.get("sold") or {}
    l = model.get("listings") or {}
    h = model.get("hpi") or {}
    faqs = []
    if s.get("ok"):
        faqs.append((
            f"What is the average house price in {d}?",
            f"The median recorded sale price in {d} is {money(s.get('median_price'))}, "
            f"based on {s.get('total','-')} sales over the last "
            f"{s.get('recency',{}).get('window_months',24)} months "
            f"({_sold_authority(_country_of(model))})."))
        flat = next((b for b in s.get("by_type", []) if b["type"] == "flat" and b["n"]), None)
        ter = next((b for b in s.get("by_type", []) if b["type"] == "terraced_house" and b["n"]), None)
        if flat or ter:
            bits = []
            if flat:
                bits.append(f"flats at a median {money(flat['median'])}")
            if ter:
                bits.append(f"terraced houses at {money(ter['median'])}")
            faqs.append((
                f"How much do flats and houses cost in {d}?",
                f"In {d}, recorded sales show " + " and ".join(bits) + "."))
    if s.get("psm_median"):
        faqs.append((
            f"What is the price per square metre in {d}?",
            f"The median sold price per square metre in {d} is {money(s['psm_median'])}, "
            f"across all property types on record."))
    if l.get("ok"):
        faqs.append((
            f"Is {d} a buyer's or seller's market?",
            f"There are {l['n']} homes on the market in {d} at a median asking price of "
            f"{money(l.get('asking_median'))}, averaging {l.get('mean_dom','-')} days listed, "
            f"with {l.get('stuck_n','-')} stuck beyond 90 days and {l.get('under_offer_n','-')} "
            f"under offer. " + ("Stock is moving quickly." if (l.get('mean_dom') or 99) < 45
                                else "The pace is measured, giving buyers room to negotiate.")))
    if h.get("ok"):
        faqs.append((
            f"Are house prices in {model['city']['name']} rising or falling?",
            f"The UK House Price Index for {model['city']['name']} is "
            f"{pct(h.get('annual_change_pct'))} year on year as of {h.get('month','')}, "
            f"with an average price of {money(h.get('average_price'))}. This regional index "
            f"is context only; it does not set the local {d} figure."))
    return faqs


def _faq_section(faqs):
    if not faqs:
        return ""
    items = "".join(
        f'<div class="faq"><h3>{e(q)}</h3><p>{a}</p></div>' for q, a in faqs)
    return f'<section id="faq"><h2>Frequently asked questions</h2>{items}</section>'


# ----------------------------------------------------------------- references
def _references(model):
    """Honest, blog-scoped citations: only the sources this page actually used, rendered in
    brand's canonical order from brand's citation templates. The blog runs no valuation, so
    it never cites an AVM or tax tables - unlike the appraisal report."""
    present = set(model.get("present", {}).keys())
    cites = getattr(brand, "_CITATIONS", {})
    order = ["pd_sold", "pd_listings", "pd_rent", "hmlr_direct", "postcodes_io", "overpass",
             "police", "flood", "air_quality", "planning", "hitman_red"]
    out, n = [], 0
    for cid in order:
        if cid in present and cid in cites:
            pub, title, url = cites[cid]
            n += 1
            out.append({"n": n, "publisher": pub, "title": title, "url": url,
                        "accessed": f"Accessed {brand.DATESTR}"})
    return out


def _references_section(refs):
    if not refs:
        return ""
    # Editorial citations to official records are FOLLOW links on purpose: vouching for the
    # primary source is the trust/authority signal we want to send, and nofollow here would
    # only throw it away. nofollow stays where it belongs - paid/affiliate/sponsored links.
    lis = "".join(
        f'<li>{e(c["publisher"])}. {e(c["title"])}. '
        f'<a href="{e(c["url"])}" rel="noopener" target="_blank">{e(c["url"])}</a> '
        f'({e(c["accessed"])}).</li>'
        for c in refs)
    return (f'<section id="references"><h2>References</h2>'
            f'<ol class="refs">{lis}</ol></section>')


def _official_sources_section():
    """A curated 'Official statistics and further reading' block linking out to the primary
    UK house-price datasets and statutory guidance (ONS, HM Land Registry, Bank of England,
    GOV.UK, NTSELAT). Follow links - citing the official record is a legitimate authority
    signal and gives the reader the canonical source to verify and go deeper."""
    srcs = brand.official_sources()
    if not srcs:
        return ""
    lis = "".join(
        f'<li><a href="{e(c["url"])}" rel="noopener" target="_blank">'
        f'{e(c["publisher"])} - {e(c["title"])}</a></li>'
        for c in srcs)
    return (f'<section id="official-sources"><h2>Official statistics and further reading</h2>'
            f'<p class="src-intro">Every figure on this page traces to official data. These are '
            f'the primary public datasets and statutory guidance behind UK house-price reporting '
            f'- go here to verify the record and dig deeper.</p>'
            f'<ul class="links src-links">{lis}</ul></section>')


def _comments_section(model):
    """Reader discussion via Remark42 (self-hosted, open-source, MIT). NO account is required -
    anonymous commenting is enabled on our own Remark42 server (AUTH_ANON=true) - but a reader
    who WANTS to can sign in (Google/GitHub/email, see deploy/remark42/), which gives them a
    persistent identity. It's OUR server, not a SaaS or third party, so the discussion and the
    ad slot beside it stay 100% ours. Rendered ONLY when REMARK_URL is configured (same "no fake
    link" rule as AFFILIATE), otherwise "" so the static site is unchanged until the backend is
    up. Each report is its own thread, keyed by its canonical URL (stable across rebuilds). An
    _ad_slot sits beside the thread - our own inventory (ads.py), rendered only when sold, 100%
    ours. The widget loads from our REMARK_URL host, never a third-party CDN. The loader script
    is Remark42's official embed snippet, kept verbatim."""
    if not REMARK_URL:
        return ""
    slug = model.get("slug") or ""
    if not slug:
        return ""
    ad = _ad_slot("blog", "comments", slug=slug)
    ad_html = f'<div class="comments-ad">{ad}</div>' if ad else ""
    cfg = json.dumps({
        "host": REMARK_URL,
        "site_id": REMARK_SITE,
        "url": SITE + post_url(slug),   # stable thread key, independent of query strings
        "components": ["embed"],
        "theme": "light",
        "locale": "en",
    })
    return (
        '<section id="comments"><h2>Join the discussion</h2>'
        '<p class="src-intro">Bought or sold near here, or think a figure looks off? '
        'Share what you saw - no account needed (sign in only if you want to).</p>'
        f'{ad_html}'
        '<div id="remark42">Comments loading&hellip;</div>'
        f'<script>var remark_config = {cfg};</script>'
        # Remark42's official loader, verbatim: picks ESM (.mjs) when supported, else a deferred
        # classic script, and pulls each component from OUR REMARK_URL host (never a third party).
        '<script>!function(e,n){for(var o=0;o<e.length;o++){var r=n.createElement("script"),'
        'c=".js",d=n.head||n.body;"noModule"in r?(r.type="module",c=".mjs"):r.async=!0,r.defer=!0,'
        'r.src=remark_config.host+"/web/"+e[o]+c,d.appendChild(r)}}'
        '(remark_config.components||["embed"],document);</script>'
        '<noscript>Comments need JavaScript. '
        f'<a href="{e(BOT)}" rel="noopener">Talk to us on Telegram</a> instead.</noscript>'
        '</section>')


def _share_bar(model):
    """A first-party 'share this report' bar - real platform share/intent links keyed to the
    page's canonical URL, plus a copy-link button. Entirely ours (no third-party widget, no
    tracking script), so it works on the static page with no backend and never leaks the reader
    to an external SDK. This is what delivers 'share easily to social media' concretely; the
    Remark42 sign-in gives a persistent identity, but the social distribution lives here."""
    slug = model.get("slug") or ""
    if not slug:
        return ""
    url = SITE + post_url(slug)
    d = model.get("district") or ""
    city = model.get("city") or ""
    where = (f"{d}, {city}" if d and city else (d or city or "this area"))
    title = f"{where} property market report - Honestly"
    u = urllib.parse.quote(url, safe="")
    t = urllib.parse.quote(title, safe="")
    # Public share endpoints (no API key, no SDK): X/Twitter & WhatsApp take text+url, Facebook
    # & LinkedIn take the url (they scrape our OG tags for the title/image).
    links = [
        ("X", f"https://twitter.com/intent/tweet?text={t}&url={u}"),
        ("Facebook", f"https://www.facebook.com/sharer/sharer.php?u={u}"),
        ("WhatsApp", f"https://api.whatsapp.com/send?text={t}%20{u}"),
        ("LinkedIn", f"https://www.linkedin.com/sharing/share-offsite/?url={u}"),
    ]
    btns = "".join(
        f'<a class="share-btn share-{name.lower()}" href="{e(href)}" '
        f'target="_blank" rel="noopener nofollow" '
        f'aria-label="Share on {e(name)}">{e(name)}</a>'
        for name, href in links)
    cu = json.dumps(url)
    return (
        '<div class="share-bar" aria-label="Share this report">'
        '<span class="share-label">Share</span>'
        f'{btns}'
        f'<button type="button" class="share-btn share-copy" data-url={cu}>Copy link</button>'
        '<span class="share-copied" role="status" hidden>Link copied</span>'
        '<script>(function(){var b=document.currentScript.parentNode;'
        'var btn=b.querySelector(".share-copy"),ok=b.querySelector(".share-copied");'
        'if(!btn)return;btn.addEventListener("click",function(){'
        'var u=btn.getAttribute("data-url")||location.href;'
        'function done(){if(ok){ok.hidden=false;setTimeout(function(){ok.hidden=true;},2000);}}'
        'if(navigator.clipboard&&navigator.clipboard.writeText){'
        'navigator.clipboard.writeText(u).then(done).catch(done);}else{done();}});})();</script>'
        '</div>')


def _cite_this_section(canonical, csv_url, label, as_of):
    """The 'Cite this' block - the backlink magnet. Gives journalists and researchers a ready
    attribution line, the raw open-data download, and an explicit licence to republish with a
    link back. This is how an original dataset earns inbound citations."""
    citation = (f"Honestly. {label} ({as_of}). Retrieved from {canonical}")
    dl = (f'<a class="cite-dl" href="{e(csv_url)}" download>Download the full dataset (CSV)</a>'
          if csv_url else "")
    return (f'<section id="cite"><h2>Cite this / use the data</h2>'
            f'<p>This is original analysis built from official records. You are free to '
            f'republish the figures and chart in news and research with attribution and a link '
            f'back to this page.</p>'
            f'<p class="cite-line"><strong>Suggested citation</strong><br>'
            f'<span class="cite-text">{e(citation)}</span></p>'
            f'<p>{dl}</p>'
            f'<p class="cite-press">Journalists and analysts: for the methodology, an interview '
            f'or a custom city-centre cut, get in touch via <a href="{e(BOT)}" rel="noopener">'
            f'{brand_name()} on Telegram</a>.</p></section>')


# ----------------------------------------------------------------- CTAs + nav
def _download_block(model):
    """The free-PDF lead-capture gate. Every figure on this page is already free; this offers
    the SAME report as a clean, brand-built PDF in exchange for an email - the reader logs in
    or 'simply gives us their details as usual'. Honest by construction: same free data, no
    valuation, and it never promises paid-bot mechanics. The form POSTs to /api/lead, which
    captures the lead and returns a one-off /dl/<token> the page then downloads (a PDF rendered
    on demand from the stored model, so it can never drift from this page)."""
    d = model["district"]
    cname = (model.get("city") or {}).get("name") or "this area"
    slug = e(model["slug"])
    doc_svg = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16'
               'a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm0 2l4 4h-4V4zM8 13h8v1.5H8V13zm0 3h8'
               'v1.5H8V16zm0-6h3v1.5H8V10z"/></svg>')
    lead = (f"This {e(d)} report is free - every figure on this page is. Want the whole thing "
            f"as a clean PDF to keep, print or forward? Enter an email address and the PDF "
            f"downloads, no charge.")
    who = (
        ("vendor", "I'm selling"), ("buyer", "I'm buying"),
        ("agent", "I'm an agent"), ("other", "Just researching"))
    persona = (
        '<fieldset class="dl-who">'
        '<legend class="dl-who-q">Which sounds like you?</legend>'
        '<div class="dl-who-opts" role="radiogroup">'
        + "".join(
            f'<label class="dl-who-opt"><input type="radio" name="persona" value="{val}" '
            f'required><span>{lbl}</span></label>' for val, lbl in who)
        + '</div></fieldset>')
    form = (
        f'<form class="dl-form" data-slug="{slug}" novalidate>'
        f'{persona}'
        f'<div class="dl-fields">'
        f'<input class="dl-in" type="email" name="email" required autocomplete="email" '
        f'placeholder="you@email.com" aria-label="Your email address">'
        f'<input class="dl-in" type="text" name="name" autocomplete="given-name" '
        f'placeholder="First name (optional)" aria-label="Your first name">'
        f'<button class="cta cta-primary dl-go" type="submit">{doc_svg}Email me the free PDF</button>'
        f'</div>'
        f'<p class="dl-note">No payment, ever. Get this PDF and, now and then, the next '
        f'free {e(cname)} report. Unsubscribe anytime.</p>'
        f'<p class="dl-msg" role="status" aria-live="polite" hidden></p>'
        f'</form>')
    return (f'<aside class="dlpdf"><span class="dl-kick">Free download</span>'
            f'<p class="dl-lead">{lead}</p>{form}</aside>')


# One shared handler for every .dl-form on the page: validate the email client-side, POST it to
# /api/lead, then send the browser to the returned /dl/<token> to fetch the PDF. Plain string
# (NOT an f-string) so the JS braces are not doubled. Uses f.elements[...] because a form's own
# .name property shadows an input named "name".
_DL_SCRIPT = """<script>
(function(){
  var re=/^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$/;
  document.querySelectorAll('form.dl-form').forEach(function(f){
    var msg=f.querySelector('.dl-msg'), btn=f.querySelector('.dl-go');
    function show(t,err){ msg.hidden=false; msg.textContent=t; msg.classList.toggle('is-err',!!err); }
    f.addEventListener('submit',function(ev){
      ev.preventDefault();
      var email=(f.elements['email'].value||'').trim();
      var name=(f.elements['name'].value||'').trim();
      var persona=(f.elements['persona']?f.elements['persona'].value:'')||'';
      var slug=f.getAttribute('data-slug');
      if(!persona){ show('Choose the option that fits so the right thing gets sent.',true); return; }
      if(!re.test(email)){ show('Please enter a valid email address.',true); return; }
      btn.disabled=true; show('Preparing your PDF...',false);
      fetch('/api/lead',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({email:email,name:name,persona:persona,slug:slug})})
        .then(function(r){ return r.json().then(function(j){ return {ok:r.ok,j:j}; }); })
        .then(function(res){
          btn.disabled=false;
          if(res.ok && res.j && res.j.url){
            show('Done - your PDF is downloading. Check your downloads folder.',false);
            window.location.href=res.j.url;
          } else { show((res.j && res.j.error) || 'Something went wrong. Please try again.',true); }
        })
        .catch(function(){ btn.disabled=false; show('Network error. Please try again.',true); });
    });
  });
})();
</script>"""


# The city/postcode navigator is built from native <details> so it works with zero JS. This
# tiny controller upgrades it to a proper menu when JS is on: opening one city closes the
# others (accordion - no stacked, overlapping popovers), clicking anywhere outside the nav
# dismisses the open one, and Escape closes it and returns focus to the city button. Without
# this, native <details> never auto-close: tap London and it stays stuck open, tap Manchester
# and its popover just stacks on top. Plain string (no f-string) so the JS braces are literal.
_CITYNAV_SCRIPT = """<script>
(function(){
  var nav=document.querySelector('.citynav');
  var drawer=document.getElementById('cn-drawer');
  var scrim=document.querySelector('.cn-scrim');
  if(!nav||!drawer||!scrim) return;
  var trigger=nav.querySelector('.cn-trigger');
  var closeBtn=drawer.querySelector('.cn-close');
  var lastFocus=null, hideT=null;
  function openDrawer(){
    lastFocus=document.activeElement;
    if(hideT){ clearTimeout(hideT); hideT=null; }
    scrim.hidden=false;
    requestAnimationFrame(function(){ scrim.classList.add('show'); drawer.classList.add('open'); });
    drawer.setAttribute('aria-hidden','false');
    if(trigger) trigger.setAttribute('aria-expanded','true');
    document.documentElement.style.overflow='hidden';
    var f=drawer.querySelector('summary, a, button'); if(f){ f.focus(); }
  }
  function closeDrawer(){
    scrim.classList.remove('show'); drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden','true');
    if(trigger) trigger.setAttribute('aria-expanded','false');
    document.documentElement.style.overflow='';
    // hide the scrim after it fades so it cannot intercept taps (fallback timer if no transitionend)
    hideT=setTimeout(function(){ scrim.hidden=true; }, 320);
    if(lastFocus&&lastFocus.focus){ lastFocus.focus(); }
  }
  scrim.addEventListener('transitionend',function(){ if(!scrim.classList.contains('show')){ scrim.hidden=true; } });
  if(trigger) trigger.addEventListener('click',openDrawer);
  if(closeBtn) closeBtn.addEventListener('click',closeDrawer);
  scrim.addEventListener('click',closeDrawer);
  document.addEventListener('keydown',function(ev){
    if((ev.key==='Escape'||ev.keyCode===27) && drawer.classList.contains('open')){ closeDrawer(); }
  });
  // The cities inside are native <details>: independent, so several can stay open at once -
  // opening Manchester never closes London. No accordion-close logic, by design.
})();
</script>"""


def _cta_block(model, where="mid"):
    """Honestly-separated calls to action. The blog is ALWAYS free. The free CTAs are: more
    city reports (inside the blog), and a FREE 'follow this report on Telegram' deep link that
    pings the reader when this district refreshes - no email, no phone, just their chat. The
    paid product is a defensible valuation of the reader's OWN address, the solid paper-plane
    button, and only that costs anything. Two Telegram links now, kept visually distinct (the
    follow is a ghost button, no icon; the paid valuation is the solid branded button) so the
    free/paid line stays bright. Conflating the two would be the bug to avoid."""
    d = model["district"]
    city = model.get("city") or {}
    cslug = city.get("slug") or ""
    cname = city.get("name") or ""
    # Free, forever: more of these reports - inside the blog, no Telegram.
    if cslug:
        more = (f'<a class="cta cta-ghost" href="{e(hub_url(cslug))}">'
                f'More free {e(cname)} reports</a>')
    else:
        more = (f'<a class="cta cta-ghost" href="{e(BLOG_BASE)}/">'
                f'Browse every free report</a>')
    # FREE follow: opens the Telegram bot with a deep link that registers a follow on this
    # district (bot.py /start sub_<slug> -> follow_area), so we can ping the reader here when
    # the report refreshes. No email, no phone captured - just their Telegram chat. Still free,
    # so it stays a ghost (free) CTA, never the solid paid button. Only rendered when this is a
    # real district report (it carries a slug); the city hub has no single slug to follow, so it
    # falls back to just 'more' + the paid button - we never promise a follow we cannot fulfil.
    dslug = model.get("slug") or ""
    follow = (f'<a class="cta cta-ghost" href="{e(BOT)}?start=sub_{e(dslug)}" '
              f'rel="noopener">Follow {e(d)} updates on Telegram</a>') if dslug else ""
    # Paid product: a valuation of YOUR address, clearly distinct, on Telegram - the button
    # carries the official Telegram blue + paper-plane mark so the channel is unmistakable.
    tg_svg = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.78 18.65l.28-4.23 '
              '7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3'
              'l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71'
              'L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"/></svg>')
    bot = (f'<a class="cta cta-tg" href="{e(BOT)}" rel="noopener">'
           f'{tg_svg}Value your own address on Telegram</a>')
    aff = (f'<a class="cta cta-ghost" href="{e(AFFILIATE)}" rel="nofollow noopener">'
           f'Run the data yourself</a>') if AFFILIATE else ""
    if where == "mid":
        lead = (f"Every report in this series is free, {e(d)} included - read as many "
                f"districts as you like, no sign-up. And when you want the same "
                f"sold-evidence treatment for one specific address, that runs on Telegram "
                f"in a couple of minutes.")
        return (f'<aside class="ctaband"><p>{lead}</p>'
                f'<div class="cta-row">{more}{bot}{aff}</div></aside>')
    lead = (f'{brand_name()} reports every postcode district from official data - free, and '
            f'refreshed daily. Read the whole network at no cost. When one specific address '
            f'matters - yours, or one you are about to offer on - the same method values it '
            f'on Telegram.')
    return (f'<aside class="ctaband"><p>{lead}</p>'
            f'<div class="cta-row">{more}{follow}{bot}{aff}</div></aside>')


def _internal_links(model, siblings, cities_nav):
    blocks = []
    if siblings:
        lis = "".join(f'<li><a href="{e(post_url(sl))}">{e(model["city"]["name"])} '
                      f'{e(dist)}</a></li>' for dist, sl in siblings)
        blocks.append(f'<div><h3>More {e(model["city"]["series"])}</h3>'
                      f'<ul class="links">{lis}</ul></div>')
    if cities_nav:
        lis = "".join(f'<li><a href="{e(hub_url(c["slug"]))}">{e(c["series"])}</a></li>'
                      for c in cities_nav)
        blocks.append(f'<div><h3>Every city series</h3><ul class="links">{lis}</ul></div>')
    if not blocks:
        return ""
    return (f'<section id="more"><h2>Across the network</h2>'
            f'<div class="link-grid">{"".join(blocks)}</div></section>')


# ----------------------------------------------------------------- JSON-LD
def _jsonld(model, faqs, refs):
    import json as _json
    d = model["district"]
    city = model["city"]
    g = model.get("geo") or {}
    s = model.get("sold") or {}
    url = SITE + post_url(model["slug"])
    title = f"{d} Property Market Report - {city['series']}"
    desc = _answer_paragraph(model)[:300]

    graph = []
    graph.append({
        "@type": "Article", "headline": title[:110],
        "description": desc, "datePublished": model["generated_at"],
        "dateModified": model["generated_at"], "url": url, "isPartOf": city["series"],
        "author": {"@type": "Organization", "name": "Honestly", "url": SITE},
        "publisher": {"@type": "Organization", "name": "Honestly",
                      "logo": {"@type": "ImageObject",
                               "url": SITE + "/img/logo-icon.png"}},
        "mainEntityOfPage": url,
    })
    place = {"@type": "Place", "name": f"{d}, {city['name']}",
             "address": {"@type": "PostalAddress", "postalCode": d,
                         "addressLocality": g.get("district") or city["name"],
                         "addressRegion": city["name"], "addressCountry": "GB"}}
    if g.get("lat") and g.get("lng"):
        place["geo"] = {"@type": "GeoCoordinates",
                        "latitude": g["lat"], "longitude": g["lng"]}
    graph.append(place)
    if s.get("ok"):
        measured = [{"@type": "PropertyValue", "name": "Median sale price",
                     "value": s.get("median_price"), "unitText": "GBP"}]
        if s.get("psm_median"):
            measured.append({"@type": "PropertyValue", "name": "Median price per square metre",
                             "value": s.get("psm_median"), "unitText": "GBP/m2"})
        measured.append({"@type": "PropertyValue", "name": "Recorded sales",
                         "value": s.get("total")})
        graph.append({
            "@type": "Dataset",
            "name": f"{d} residential transaction statistics",
            "description": f"Sold prices, price per square metre and transaction volume "
                           f"for postcode district {d} in {city['name']}, from "
                           f"{_sold_authority(city.get('country',''))}.",
            "url": url, "spatialCoverage": place, "creator": {"@type": "Organization",
            "name": "Honestly"}, "variableMeasured": measured,
            "license": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
            "isAccessibleForFree": True,
        })
    if faqs:
        graph.append({
            "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q,
                            "acceptedAnswer": {"@type": "Answer", "text": a_text}}
                           for q, a_text in faqs]})
    graph.append({
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE},
            {"@type": "ListItem", "position": 2, "name": "Blog", "item": SITE + BLOG_BASE + "/"},
            {"@type": "ListItem", "position": 3, "name": city["series"],
             "item": SITE + hub_url(city["slug"])},
            {"@type": "ListItem", "position": 4, "name": d, "item": url},
        ]})
    return _json.dumps({"@context": "https://schema.org", "@graph": graph},
                       ensure_ascii=False)


# ----------------------------------------------------------------- page shell
def _fonts():
    """The report type system: Fraunces for headings (brand serif, matching the landing page)
    and Inter for body text, the clean sans proxy for the PDF's Helvetica."""
    return ('<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
            'family=Inter:wght@400;500;600;700&'
            'family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,700;1,9..144,400;1,9..144,500;1,9..144,600&'
            'display=swap">')


_CN_PIN = ('<svg class="cn-pin" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">'
           '<path fill="currentColor" d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0'
           '-7-7Zm0 9.6A2.6 2.6 0 1 1 12 6.4a2.6 2.6 0 0 1 0 5.2Z"/></svg>')


def _citynav(cities_nav, active_city=None, active_district=None):
    """A left slide-in 'Your area' sidebar: one sticky trigger opens a drawer listing every
    city, each expanding inline to its published postcode districts.

    A sidebar, not a floating popover - which is the whole point. Several cities can stay open
    at once, so reaching for Manchester never collapses London; and the panel sits in its own
    column over a scrim, so it never overlays the article. Dismissed by the close button, a
    scrim tap, or Escape. Only PUBLISHED districts are linked (every chip is a real report, so
    the nav never 404s); a city with nothing yet still opens, to its hub with an honest 'soon'
    note. The reader's current city opens by default and is badged 'You are here'; their current
    district chip is aria-current. Zero-JS fallback: with no controller the drawer markup is a
    plain stacked <details> list that still expands inline - it simply is not collapsed off-canvas."""
    if not cities_nav:
        return ""
    cur = ""
    for c in cities_nav:
        if c["slug"] == active_city:
            cur = c["name"] + ((" " + active_district) if active_district else "")
            break
    cur_html = (f'<span class="cn-cur">{e(cur)}</span>' if cur
                else '<span class="cn-cur cn-cur-none">Browse by area</span>')

    cells = []
    for c in cities_nav:
        nd = c.get("nav_districts") or []
        is_active = (c["slug"] == active_city)
        cls = "cn-city is-active" if is_active else "cn-city"
        open_attr = " open" if is_active else ""  # land already expanded on your own patch
        all_link = (f'<a class="cn-all" href="{e(hub_url(c["slug"]))}">'
                    f'All {e(c["name"])} reports &rarr;</a>')
        if nd:
            chips = []
            for dn in nd:
                here = is_active and dn["code"] == active_district
                klass = "cn-code is-here" if here else "cn-code"
                aria = ' aria-current="page"' if here else ""
                chips.append(f'<a class="{klass}" href="{e(dn["url"])}"{aria}>'
                             f'{e(dn["code"])}</a>')
            body = all_link + f'<div class="cn-codes">{"".join(chips)}</div>'
        else:
            body = all_link + (f'<p class="cn-empty">First {e(c["name"])} postcode '
                               f'publishes soon.</p>')
        cells.append(f'<details class="{cls}"{open_attr}>'
                     f'<summary><span class="cn-cname">{e(c["name"])}</span>'
                     f'<span class="cn-chev" aria-hidden="true"></span></summary>'
                     f'<div class="cn-pop">{body}</div></details>')
    return (
        '<nav class="citynav" aria-label="Browse reports by city and postcode">'
        '<div class="cn-row">'
        '<button type="button" class="cn-trigger" aria-haspopup="dialog" '
        'aria-expanded="false" aria-controls="cn-drawer">'
        f'{_CN_PIN}<span class="cn-trigger-label">Your area</span>{cur_html}'
        '<span class="cn-trigger-chev" aria-hidden="true"></span></button>'
        '</div></nav>'
        '<div class="cn-scrim" hidden></div>'
        '<aside class="cn-drawer" id="cn-drawer" role="dialog" aria-modal="true" '
        'aria-label="Browse reports by city and postcode" aria-hidden="true">'
        f'<div class="cn-drawer-head">{_CN_PIN}'
        '<span class="cn-drawer-title">Your area</span>'
        '<button type="button" class="cn-close" aria-label="Close area menu">&times;</button>'
        '</div>'
        f'<div class="cn-drawer-body">{"".join(cells)}</div>'
        '<p class="cn-drawer-foot">Every chip is a published report.</p>'
        '</aside>')


def _masthead(series, citynav=""):
    """A research-house broadsheet masthead: a gold hairline, a cream band carrying the
    EXACT icon + horizontal wordmark (Brand Asset Rule - never recreated), and an edition
    line, optionally followed by the sticky city/postcode navigator. The wordmark is dark
    ink, so it lives on the light band, not a navy bar - which is why it now reads at full
    size instead of being shrunk onto a dark strip."""
    icon = brand.logo_url("icon") or ""
    word = brand.logo_url("wordmark") or ""
    if word:
        ic = (f'<img class="mast-icon" src="{icon}" alt="" width="40" height="40">'
              if icon else "")
        # The wordmark is the EXACT asset (Brand Asset Rule). The .mast-shine span sits OVER
        # it and uses the same wordmark PNG as a mask, so the hero's glass glint sweeps through
        # the letterforms of 'honestly' on a loop - the asset is never redrawn or recoloured,
        # a light highlight just travels across it (mix-blend screen). Cements the brand.
        brand_html = (f'{ic}<span class="mast-word-wrap">'
                      f'<img class="mast-word" src="{word}" alt="Honestly">'
                      f'<span class="mast-shine" aria-hidden="true"></span></span>')
    else:
        brand_html = '<span class="mast-fallback">Honestly</span>'
    return (f'<div class="topline"></div>'
            f'<header class="masthead"><div class="wrap mast-row">'
            f'<a class="mast-brand" href="{e(BLOG_BASE)}/">{brand_html}</a>'
            f'<div class="mast-edition"><span class="ed-series">{e(series)}</span>'
            f'<span class="ed-meta">Postcode market reports &middot; {e(brand.DATESTR)}</span>'
            f'</div></div></header>{citynav}'
            + (_CITYNAV_SCRIPT if citynav else ""))


def _foot_brand():
    """The EXACT compact lockup closing every page on the light colophon, the same asset and
    ground the landing footer uses (Brand Asset Rule - never recreated, never recoloured).
    Falls back to the full lockup, then to nothing - never a drawn substitute."""
    lock = (brand.logo_url("lockup-compact") or brand.logo_url("lockup") or "")
    ernesta = '<p class="ernesta">A product by Ernesta Labs.</p>'
    if not lock:
        return ernesta
    return (f'<div class="foot-brand">'
            f'<img src="{lock}" alt="Honestly - a defensible value" width="180"></div>'
            f'{ernesta}')


def _css():
    H = brand.HEX
    word_uri = brand.logo_url("wordmark") or ""
    return f""":root{{--navy:{H['navy']};--green:{H['green']};--teal:{H['teal']};
--gold:{H['gold']};--cream:{H['cream']};--paper:{H['paper']};--ink:{H['ink']};
--muted:{H['muted']};--line:{H['line']};--pale:{H['pale']};--sand:{H['sand']};
--tg:#229ED9;--tgdark:#1b88bd;
--serif:"Fraunces",Georgia,"Times New Roman","Iowan Old Style",serif;
--sans:"Inter",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
--glass:rgba(255,255,255,.72);--glassln:rgba(255,255,255,.9)}}
*{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%}}
body{{margin:0;font-family:var(--sans);font-size:17px;line-height:1.7;color:var(--ink);
background:var(--paper);font-feature-settings:"ss01","cv01";position:relative;overflow-x:clip;
-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}}
/* the document content rides ABOVE the page-ground aurora (z-index:0): the masthead is opaque
   at the very top, the article/footer are transparent so the aura glows through behind them. */
.topline,.masthead{{position:relative;z-index:3}}
article.wrap,main.wrap{{position:relative;z-index:1}}
footer.site{{position:relative;z-index:1}}
.wrap{{max-width:880px;margin:0 auto;padding:0 24px}}
p{{margin:0 0 1.05em}}
::selection{{background:var(--green);color:var(--cream)}}
*:focus-visible{{outline:2px solid var(--green);outline-offset:3px;border-radius:2px}}
/* paper grain - the appraisal-document texture lifted verbatim from the landing */
.grain{{position:fixed;inset:0;z-index:9;pointer-events:none;opacity:.05;mix-blend-mode:multiply;
background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.82' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>")}}

/* masthead */
.topline{{height:3px;background:linear-gradient(90deg,var(--gold) 0%,#e7b659 60%,var(--gold) 100%)}}
.masthead{{background:var(--cream);border-bottom:1px solid var(--line)}}
.mast-row{{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:18px 24px}}
.mast-brand{{display:flex;align-items:center;gap:13px;text-decoration:none}}
.mast-icon{{height:40px;width:40px;display:block}}
.mast-word-wrap{{position:relative;display:inline-flex;line-height:0}}
.mast-word{{height:25px;width:auto;display:block}}
/* the hero glass-glint, ported onto the wordmark: a diagonal light band sweeps across, masked
   to the EXACT wordmark PNG so it glints only through the letterforms of 'honestly', then holds.
   The asset underneath is untouched; screen blend means the band only lightens, never recolours. */
.mast-shine{{position:absolute;inset:0;pointer-events:none;
-webkit-mask-image:url("{word_uri}");mask-image:url("{word_uri}");
-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;
-webkit-mask-size:contain;mask-size:contain;
-webkit-mask-position:left center;mask-position:left center;
background:linear-gradient(115deg,transparent 42%,rgba(255,255,255,.9) 50%,transparent 58%);
background-size:280% 100%;background-repeat:no-repeat;background-position:-80% 0;
mix-blend-mode:screen;animation:word-sheen 7.5s ease-in-out infinite}}
@keyframes word-sheen{{0%{{background-position:-80% 0}}24%{{background-position:170% 0}}100%{{background-position:170% 0}}}}
@media (prefers-reduced-motion:reduce){{.mast-shine{{animation:none;opacity:0}}}}
.mast-fallback{{font:700 1.5rem/1 var(--serif);color:var(--navy)}}

/* brand name in prose - echoes the wordmark: lowercase, navy, teal final 'y'.
   Renders the same in links so the name reads as the logo everywhere it appears. */
.brandname{{font-weight:700;color:var(--navy);letter-spacing:-.012em;font-style:normal}}
.brand-y{{color:var(--teal)}}
.mast-edition{{text-align:right;line-height:1.25}}
.ed-series{{display:block;font-family:var(--serif);font-weight:600;font-size:.98rem;color:var(--navy)}}
.ed-meta{{display:block;font-size:.68rem;font-weight:600;letter-spacing:.7px;
text-transform:uppercase;color:var(--muted);margin-top:2px}}

/* CITY + POSTCODE NAVIGATOR - a left slide-in 'Your area' sidebar. A sticky trigger opens a
   drawer listing every city; each expands inline to its postcodes. A sidebar, not a floating
   popover: several cities can stay open at once and it never overlays the article. The drawer
   degrades to a plain stacked list if the controller never runs (it just is not off-canvas). */
.citynav{{position:sticky;top:0;z-index:6;background:rgba(251,249,244,.9);
-webkit-backdrop-filter:blur(11px) saturate(1.05);backdrop-filter:blur(11px) saturate(1.05);
border-bottom:1px solid var(--line);box-shadow:0 1px 0 rgba(255,255,255,.6) inset,0 10px 22px -18px rgba(14,39,71,.5)}}
.cn-row{{display:flex;align-items:center;gap:14px;padding:8px 24px}}
.cn-trigger{{display:inline-flex;align-items:center;gap:9px;cursor:pointer;font-family:var(--sans);
background:#fff;border:1px solid var(--line);border-radius:999px;padding:6px 15px 6px 12px;
color:var(--navy);transition:border-color .18s,box-shadow .18s}}
.cn-trigger:hover{{border-color:var(--teal);box-shadow:0 0 0 2px rgba(42,163,154,.16)}}
.cn-pin{{flex:none;color:var(--teal)}}
.cn-trigger-label{{font-size:.62rem;font-weight:700;letter-spacing:.9px;
text-transform:uppercase;color:var(--muted)}}
.cn-cur{{font-size:.86rem;font-weight:700;color:var(--navy);white-space:nowrap}}
.cn-cur-none{{font-weight:600}}
.cn-trigger-chev{{width:7px;height:7px;border-right:2px solid var(--muted);
border-bottom:2px solid var(--muted);transform:rotate(45deg);margin:-3px 0 0 1px}}

/* scrim + the drawer itself */
.cn-scrim{{position:fixed;inset:0;z-index:40;background:rgba(14,39,71,.42);
opacity:0;transition:opacity .25s ease}}
.cn-scrim.show{{opacity:1}}
.cn-drawer{{position:fixed;top:0;left:0;bottom:0;z-index:41;width:328px;max-width:86vw;
display:flex;flex-direction:column;background:var(--paper);border-right:1px solid var(--line);
box-shadow:0 0 60px -8px rgba(14,39,71,.5);transform:translateX(-100%);
transition:transform .28s cubic-bezier(.16,1,.3,1)}}
.cn-drawer.open{{transform:translateX(0)}}
.cn-drawer-head{{flex:none;display:flex;align-items:center;gap:9px;padding:15px 16px;
border-bottom:1px solid var(--line);background:#fff}}
.cn-drawer-head .cn-pin{{color:var(--teal)}}
.cn-drawer-title{{flex:1;font-family:var(--serif);font-weight:600;font-size:1.05rem;color:var(--navy)}}
.cn-close{{flex:none;width:32px;height:32px;border:1px solid var(--line);border-radius:8px;
background:var(--paper);cursor:pointer;font-size:1.3rem;line-height:1;color:var(--muted);
display:flex;align-items:center;justify-content:center;transition:border-color .15s,color .15s}}
.cn-close:hover{{border-color:var(--teal);color:var(--navy)}}
.cn-drawer-body{{flex:1;overflow-y:auto;padding:4px 0}}
.cn-drawer-foot{{flex:none;margin:0;padding:11px 16px;border-top:1px solid var(--line);
font-size:.7rem;color:var(--muted)}}

/* city accordion rows inside the drawer - independent, multiple may stay open */
.cn-city{{border-bottom:1px solid var(--line)}}
.cn-city>summary{{list-style:none;cursor:pointer;display:flex;align-items:center;
font-family:var(--sans);font-size:.96rem;font-weight:600;color:var(--navy);
padding:12px 16px;transition:background .15s}}
.cn-city>summary::-webkit-details-marker{{display:none}}
.cn-city>summary::marker{{content:""}}
.cn-city>summary:hover{{background:rgba(42,163,154,.07)}}
.cn-cname{{flex:1}}
.cn-city.is-active>summary .cn-cname::after{{content:"You are here";margin-left:8px;
font-size:.58rem;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--teal)}}
.cn-chev{{flex:none;width:7px;height:7px;border-right:2px solid var(--muted);
border-bottom:2px solid var(--muted);transform:rotate(45deg);transition:transform .2s;
margin-top:-2px}}
.cn-city[open]>summary .cn-chev{{transform:rotate(225deg);margin-top:2px}}
.cn-pop{{padding:0 16px 14px}}
.cn-all{{display:block;font-family:var(--sans);font-size:.8rem;font-weight:700;color:var(--navy);
text-decoration:none;padding-bottom:9px;margin-bottom:10px;border-bottom:1px solid var(--line)}}
.cn-all:hover{{color:var(--teal)}}
.cn-codes{{display:flex;flex-wrap:wrap;gap:6px}}
.cn-code{{font-family:var(--sans);font-size:.78rem;font-weight:600;color:var(--navy);
text-decoration:none;padding:5px 11px;border:1px solid var(--line);border-radius:7px;
background:#fff;transition:border-color .15s,background .15s,color .15s}}
.cn-code:hover{{border-color:var(--teal)}}
.cn-code.is-here{{background:var(--teal);color:#fff;border-color:var(--teal)}}
.cn-empty{{margin:0;font-size:.78rem;color:var(--muted)}}

/* hero illustration band - the landing's sample-report glass: a layered translucent shadow
   stack with an inset top highlight (the lit glass bevel) and a light band that sweeps the
   surface every few seconds (.hero-shine, ported from the certificate's .cert-shine). */
.hero{{margin:2.1em 0 0;border-radius:13px;overflow:hidden;border:1px solid var(--line);
box-shadow:inset 0 1px 1px rgba(255,255,255,.55),0 2px 5px rgba(14,39,71,.06),
0 22px 48px -14px rgba(14,39,71,.20),0 60px 110px -44px rgba(14,39,71,.26);
position:relative;background:var(--navy);
transition:transform .55s cubic-bezier(.16,1,.3,1),box-shadow .55s ease}}
.hero:hover{{transform:translateY(-4px);
box-shadow:inset 0 1px 1px rgba(255,255,255,.6),0 2px 5px rgba(14,39,71,.07),
0 28px 56px -14px rgba(14,39,71,.24),0 72px 130px -44px rgba(14,39,71,.30)}}
.hero img{{display:block;width:100%;aspect-ratio:16/9;height:auto;object-fit:cover}}
/* glass glint - a diagonal light band travels across the hero, same timing as the landing */
.hero-shine{{position:absolute;inset:0;overflow:hidden;border-radius:inherit;
pointer-events:none;z-index:5}}
.hero-shine::before{{content:"";position:absolute;top:-60%;left:-40%;width:36%;height:220%;
background:linear-gradient(115deg,transparent,rgba(255,255,255,.55),transparent);
transform:rotate(8deg);animation:cert-sweep 8s ease-in-out infinite;opacity:0}}
@keyframes cert-sweep{{0%{{left:-40%;opacity:0}}10%{{opacity:.9}}26%{{left:130%;opacity:0}}100%{{left:130%;opacity:0}}}}
.hero figcaption{{position:absolute;right:12px;bottom:10px;z-index:6;font-family:var(--sans);
font-size:.66rem;font-weight:600;letter-spacing:.4px;text-transform:uppercase;
color:#fff;background:rgba(14,39,71,.72);padding:4px 9px;border-radius:5px}}
/* area street-view photo */
.area-photo{{margin:0 0 1.4em;border-radius:11px;overflow:hidden;border:1px solid var(--line)}}
.area-photo img{{display:block;width:100%;aspect-ratio:16/9;height:auto;object-fit:cover}}
.area-photo figcaption{{font-family:var(--sans);font-size:.78rem;color:var(--muted);
padding:9px 14px;background:#fff;border-top:1px solid var(--line)}}

/* PAGE-GROUND AURORA - the landing's hero effect, painted on the PAGE ITSELF, never a box.
   One full-bleed layer pinned to the top of the document (left:0;right:0 = full viewport width),
   sitting behind all content (z-index:0). It is the same drifting blue/teal wash as the landing
   hero-aurora at inset:0 - a soft repeating-linear colour sweep plus three drifting glows, with
   NO blend mode so the hue reads on the light paper. A vertical mask dissolves it downward into
   the document. The opaque cream masthead caps the very top; the transparent article lets the
   aura glow through behind the headline and in the page margins. There is no rectangle, no
   border, no card - just a lit page. */
.page-aura{{position:absolute;top:0;left:0;right:0;height:660px;z-index:0;pointer-events:none;
overflow:hidden;-webkit-mask-image:linear-gradient(180deg,#000 46%,transparent 100%);
mask-image:linear-gradient(180deg,#000 46%,transparent 100%)}}
.page-aura::before,.page-aura::after{{content:"";position:absolute;inset:-30%;
background-image:repeating-linear-gradient(100deg,var(--tg) 4%,var(--green) 11%,var(--teal) 17%,var(--navy) 24%,var(--tg) 30%);
background-size:200% 200%;filter:blur(72px) saturate(1.1)}}
.page-aura::before{{opacity:.16;animation:aurora-drift 26s linear infinite}}
.page-aura::after{{opacity:.10;animation:aurora-drift 44s linear infinite reverse}}
/* drifting blue/teal glows - the landing .dark-glow exactly: NO blend mode -> visible on light */
.page-aura .ab{{position:absolute;border-radius:9999px;filter:blur(82px);opacity:.42}}
.page-aura .ab.b1{{top:-6%;right:13%;width:30rem;height:30rem;
background:radial-gradient(circle,rgba(34,158,217,.42),transparent 62%);
animation:glow-drift 22s ease-in-out infinite}}
.page-aura .ab.b2{{top:-12%;right:34%;width:24rem;height:24rem;
background:radial-gradient(circle,rgba(42,163,154,.34),transparent 62%);
animation:glow-drift 30s ease-in-out infinite reverse}}
.page-aura .ab.b3{{top:6%;left:9%;width:22rem;height:22rem;
background:radial-gradient(circle,rgba(34,158,217,.28),transparent 64%);
animation:glow-drift 38s ease-in-out infinite}}
/* report head - a PRINTED-REPORT masthead, NOT a box: no background, no border, no card. The
   headline sits directly on the paper page, lit by the page-ground aurora behind it. */
.report-head{{position:relative;margin:2.4em 0 2.6em;padding:0;background:none;border:0}}
@keyframes aurora-drift{{0%{{background-position:0% 50%}}50%{{background-position:100% 50%}}100%{{background-position:0% 50%}}}}
@keyframes glow-drift{{0%,100%{{transform:translate(0,0) scale(1)}}50%{{transform:translate(8%,-10%) scale(1.18)}}}}
.rh-body{{position:relative;z-index:2}}
.kicker{{font-size:.74rem;font-weight:700;letter-spacing:1.7px;text-transform:uppercase;
color:var(--green);margin:0 0 .6em}}
h1{{font-family:var(--serif);font-optical-sizing:auto;font-weight:700;font-size:2.7rem;
line-height:1.07;letter-spacing:-.012em;color:var(--navy);margin:0 0 .3em}}
.dateline{{font-size:.84rem;font-weight:500;color:var(--muted);margin:0 0 1.2em;
border-bottom:1px solid var(--line);padding-bottom:1.1em;letter-spacing:.2px}}
/* AEO answer lead - the single most-cited paragraph: clean scannable Inter, ink on the page,
   never a display serif. Reads as a crisp answer for AI engines + featured snippets. */
.standfirst{{font-family:var(--sans);font-size:1.18rem;line-height:1.62;
color:#2b2925;font-weight:400;margin:0 0 1.5em;padding-left:18px;
border-left:3px solid var(--gold);max-width:64ch}}
.standfirst strong{{font-weight:600;color:var(--navy)}}
.answer strong{{font-weight:600;color:var(--navy)}}
/* ruled stats strip - the research-report summary band: navy top rule, hairline dividers,
   navy serif figures, muted labels, transparent so the page reads through. NOT a card. */
.herofacts{{display:flex;flex-wrap:wrap;
margin:1.5em 0 0;background:none;border-top:2px solid var(--navy);border-bottom:1px solid var(--line)}}
.hf{{flex:1 1 145px;min-width:130px;padding:14px 18px 13px;border-right:1px solid var(--line)}}
.hf:last-child{{border-right:none}}
.hf-v{{display:block;font-family:var(--serif);font-optical-sizing:auto;font-weight:600;
font-size:1.5rem;line-height:1.05;color:var(--navy);font-variant-numeric:tabular-nums lining-nums}}
.hf-l{{display:block;font-size:.72rem;font-weight:700;letter-spacing:.4px;text-transform:uppercase;
color:var(--muted);margin-top:6px}}
.hub-range{{font-size:1.04rem;color:#2b2925;margin:.2em 0 1.6em}}
.hub-range strong{{color:var(--navy);font-weight:600}}

h2{{font-family:var(--serif);font-optical-sizing:auto;font-weight:700;
font-size:1.62rem;line-height:1.2;letter-spacing:-.015em;color:var(--navy);
margin:2.7em 0 .7em;padding-top:1.4em;border-top:1px solid var(--line);position:relative}}
/* report.py idiom: a short green accent rule sitting on the section hairline */
h2::before{{content:"";position:absolute;top:-1px;left:0;width:48px;height:3px;
background:var(--green);border-radius:2px}}
h2 .pulse-dot{{vertical-align:middle;margin-right:.5em}}
h3{{font-family:var(--serif);font-optical-sizing:auto;font-weight:700;font-size:1.2rem;
color:var(--navy);margin:1.5em 0 .4em}}
.meta{{color:var(--muted);font-size:.88rem;margin:.2em 0 1.2em}}
.answer{{font-family:var(--sans);font-size:1.16rem;line-height:1.62;
color:#2b2925;margin:0 0 1.5em;padding-left:18px;border-left:3px solid var(--gold);max-width:64ch}}

/* data plinths - flexbox with flex-grow so the final row STRETCHES to fill the strip
   completely. Never an orphan empty cell, whatever the count (auto-fit grid left a hole when
   the count was not a multiple of the column count - e.g. 7 KPIs in a 4-wide grid). */
.kpis{{display:flex;flex-wrap:wrap;
background:var(--glass);-webkit-backdrop-filter:blur(12px) saturate(1.06);
backdrop-filter:blur(12px) saturate(1.06);border:1px solid var(--glassln);
border-radius:12px;overflow:hidden;margin:1.9em 0}}
.kpi{{flex:1 1 175px;min-width:155px;background:transparent;padding:19px 18px 17px;position:relative;
box-shadow:inset -1px 0 0 var(--line),inset 0 -1px 0 var(--line)}}
.kpi::before{{content:"";position:absolute;top:0;left:0;right:0;height:2px;background:var(--green)}}
.kpi-v{{font-family:var(--serif);font-optical-sizing:auto;font-weight:600;font-size:1.9rem;
line-height:1.02;color:var(--navy);font-variant-numeric:tabular-nums lining-nums}}
.kpi-l{{font-size:.76rem;font-weight:700;letter-spacing:.4px;text-transform:uppercase;
color:var(--ink);margin-top:9px}}
.kpi-s{{font-size:.76rem;color:var(--muted);margin-top:3px}}

/* tables - research-note style, tabular figures, numerics right-aligned */
table.data{{width:100%;border-collapse:collapse;margin:1.3em 0;font-size:.95rem;
font-variant-numeric:tabular-nums lining-nums}}
table.data caption{{text-align:left;font-family:var(--serif);font-weight:600;font-size:1.05rem;
color:var(--navy);padding:0 0 .55em;caption-side:top}}
table.data thead th{{background:var(--navy);color:#fff;font-size:.72rem;letter-spacing:.5px;
text-transform:uppercase;font-weight:600;text-align:left;padding:11px 13px}}
table.data tbody td{{padding:10px 13px;border-bottom:1px solid var(--line)}}
table.data tbody tr:nth-child(even){{background:#fbf8f1}}
table.data tbody tr:hover{{background:var(--pale)}}
table.data th:not(:first-child),table.data td:not(:first-child){{text-align:right}}
table.mini{{width:100%;border-collapse:collapse;font-size:.9rem;
font-variant-numeric:tabular-nums lining-nums}}
table.mini td{{padding:6px 8px;border-bottom:1px solid var(--line)}}
table.mini td:last-child{{text-align:right}}
/* area links - every amenity row + the nearest station open a live map; the directions link
   is the small green pill at the end of a connectivity line. Intentional, tappable, on-source. */
.area-card a{{color:var(--green);text-decoration:none;font-weight:600}}
.area-card a:hover{{text-decoration:underline}}
.area-card ul{{margin:.2em 0 0;padding-left:1.1em}}
.area-card li{{margin:.3em 0}}
.area-dir{{font-size:.82rem;white-space:nowrap;color:var(--teal) !important}}
.area-note{{margin:.7em 0 0;font-size:.76rem;color:var(--muted)}}

/* cards */
.aud-grid,.area-grid,.link-grid{{display:grid;gap:16px;
grid-template-columns:repeat(auto-fit,minmax(240px,1fr));margin:1.4em 0}}
.aud,.area-card{{background:var(--glass);-webkit-backdrop-filter:blur(10px) saturate(1.05);
backdrop-filter:blur(10px) saturate(1.05);border:1px solid var(--glassln);
border-radius:11px;padding:18px 20px;overflow:hidden}}
.aud h3{{margin-top:0}}
/* publication cover - a real city photograph (Pexels) bleeding to the card edges, clipped to
   the card's top radius. Falls back to the editorial hero illustration; absent if neither. */
.aud-cover{{display:block;margin:-18px -20px 15px;line-height:0}}
.aud-cover img{{display:block;width:100%;aspect-ratio:16/9;height:auto;object-fit:cover;
border-bottom:1px solid var(--line);transition:transform .5s cubic-bezier(.16,1,.3,1)}}
.aud:hover .aud-cover img{{transform:scale(1.035)}}
.aud ul{{margin:.3em 0 0;padding-left:1.1em}}.aud li{{margin:.45em 0}}
.watch-grid{{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));margin:1.4em 0}}
.watch-card{{background:var(--glass);-webkit-backdrop-filter:blur(10px) saturate(1.05);
backdrop-filter:blur(10px) saturate(1.05);border:1px solid var(--glassln);
border-top:3px solid var(--green);border-radius:11px;padding:18px 18px 16px;
display:flex;flex-direction:column;box-shadow:0 1px 2px rgba(14,39,71,.04)}}
.watch-buyers{{border-top-color:var(--green)}}
.watch-sellers{{border-top-color:var(--gold)}}
.watch-agents{{border-top-color:var(--navy)}}
.watch-badge{{font-size:.7rem;font-weight:700;letter-spacing:.7px;text-transform:uppercase;color:var(--muted)}}
.watch-headline{{font-family:var(--serif);font-weight:600;font-size:1.14rem;line-height:1.25;
color:var(--navy);margin:.3em 0 .1em}}
.watch-price{{font-family:var(--serif);font-optical-sizing:auto;font-weight:600;font-size:1.6rem;
line-height:1;color:var(--green);margin:.2em 0;font-variant-numeric:tabular-nums lining-nums}}
.watch-meta{{font-size:.82rem;color:var(--muted);margin:.1em 0 .4em}}
.watch-addr{{font-size:.9rem;font-weight:600;color:var(--ink);margin:.1em 0 .5em}}
.watch-reason{{font-size:.9rem;color:var(--ink);margin:.2em 0 .9em;flex:1}}
.watch-link{{align-self:flex-start;background:var(--navy);color:#fff;text-decoration:none;
font-weight:600;font-size:.86rem;padding:9px 15px;border-radius:7px;transition:background .15s}}
.watch-link:hover{{background:#143458}}
.watch-note{{font-size:.86rem;color:var(--muted);background:var(--cream);border-left:3px solid var(--gold);
padding:13px 17px;border-radius:8px;margin:1.3em 0}}.watch-note strong{{color:var(--navy)}}
.voice-grid{{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));margin:1.4em 0}}
.voice{{margin:0;background:#fff;border:1px solid var(--line);border-left:3px solid var(--green);
border-radius:11px;padding:16px 18px}}
.voice blockquote{{margin:0 0 .4em;font:italic 400 1.08rem/1.45 var(--serif);color:var(--ink)}}
.voice-reply{{margin:.4em 0;font-size:.92rem;color:var(--muted)}}
.voice-tag{{font-style:normal;font-size:.78rem}}
.voice figcaption{{font-size:.82rem;color:var(--muted);margin-top:.4em}}
.voice figcaption a{{color:var(--green)}}
.voice-tie{{font-size:.8rem;color:var(--green);margin:.5em 0 0;font-weight:600}}
.voice-src{{font-size:.78rem;color:var(--muted);margin:.6em 0 0}}
.voice-pro{{font-size:.88rem;color:var(--ink);background:var(--pale);border:1px solid var(--line);
border-left:3px solid var(--gold);border-radius:9px;padding:13px 17px;margin:1.1em 0 0}}
.voice-pro strong{{color:var(--navy)}}
.faq{{margin:1em 0}}.faq h3{{margin-bottom:.2em}}
.refs{{font-size:.86rem;color:var(--muted)}}.refs li{{margin:.45em 0}}
.refs a{{color:var(--green);word-break:break-all}}
.src-intro{{font-size:.95rem;color:var(--muted);margin:.2em 0 1em;max-width:64ch}}
.src-links li{{margin:.5em 0}}
#cite{{background:var(--pale);border:1px solid var(--line);border-left:4px solid var(--gold);
border-radius:12px;padding:22px 26px;margin:2.1em 0}}
#cite h2{{margin-top:0}}
#cite p{{font-size:.95rem;margin:.6em 0}}
.cite-text{{font-family:var(--sans);background:#fff;border:1px solid var(--line);border-radius:7px;
display:inline-block;padding:8px 12px;font-size:.9rem;color:var(--ink);margin-top:4px;word-break:break-word}}
.cite-dl{{display:inline-block;background:var(--navy);color:#fff;text-decoration:none;font-weight:600;
font-size:.9rem;padding:10px 18px;border-radius:8px}}
.cite-dl:hover{{filter:brightness(1.08)}}
.cite-press{{color:var(--muted);font-size:.9rem}}
.cite-press a{{color:var(--green);font-weight:600}}
.na{{color:var(--muted);font-style:italic}}
/* CTA - a light document panel (gold rule), NOT a blue box, so the navy brand reads and the
   text has full contrast. The Telegram action carries the official Telegram blue + paper-plane. */
.ctaband{{color:var(--ink);border:1px solid var(--line);border-left:4px solid var(--gold);
border-radius:12px;padding:24px 26px;margin:2.1em 0;background:var(--cream)}}
.ctaband p{{margin:0 0 16px;font-size:1.06rem;color:var(--ink);max-width:66ch}}
.cta-row{{display:flex;flex-wrap:wrap;gap:11px;align-items:center}}
.cta{{display:inline-flex;align-items:center;gap:8px;padding:12px 18px;border-radius:8px;
text-decoration:none;font-weight:600;font-size:.95rem;transition:transform .12s,filter .15s,
background .15s,border-color .15s}}
.cta:hover{{transform:translateY(-1px)}}
/* Telegram action - official Telegram blue (#229ED9) + the paper-plane mark */
.cta-tg{{background:var(--tg);color:#fff}}.cta-tg:hover{{background:var(--tgdark)}}
.cta-tg svg{{width:17px;height:17px;flex:none;fill:#fff}}
/* gold primary (non-Telegram primary actions e.g. CSV download) */
.cta-primary{{background:var(--gold);color:var(--navy)}}.cta-primary:hover{{filter:brightness(1.05)}}
/* secondary, on the light panel */
.cta-ghost{{background:#fff;color:var(--navy);border:1px solid var(--line)}}
.cta-ghost:hover{{border-color:var(--navy)}}
/* FREE-PDF LEAD GATE - the page is already free; this offers the same report as a clean PDF for
   an email. A light panel with a GREEN rule (distinct from the gold CTA) so it reads as a gift,
   not a paywall. The form posts to /api/lead and the browser downloads /dl/<token>. */
.dlpdf{{border:1px solid var(--line);border-left:4px solid var(--green);border-radius:12px;
padding:22px 24px;margin:2.1em 0;background:linear-gradient(180deg,#fff,var(--cream))}}
.dl-kick{{display:inline-block;font-size:.64rem;font-weight:700;letter-spacing:.9px;
text-transform:uppercase;color:var(--green);margin-bottom:7px}}
.dl-lead{{margin:0 0 16px;font-size:1.06rem;color:var(--ink);max-width:66ch}}
/* persona self-select: we ask who they are so the follow-up and the Telegram offer fit them.
   Pills, not a dropdown - one tap, the checked one fills navy. The whole label is the target. */
.dl-who{{border:0;margin:0 0 15px;padding:0;min-width:0}}
.dl-who-q{{padding:0;font-size:.82rem;font-weight:700;letter-spacing:.3px;color:var(--navy);
margin-bottom:9px}}
.dl-who-opts{{display:flex;flex-wrap:wrap;gap:8px}}
.dl-who-opt{{position:relative}}
.dl-who-opt input{{position:absolute;opacity:0;width:0;height:0}}
.dl-who-opt span{{display:inline-block;cursor:pointer;font-family:var(--sans);font-size:.88rem;
color:var(--ink);padding:8px 15px;border:1px solid var(--sand);border-radius:999px;background:#fff;
transition:border-color .15s,background .15s,color .15s}}
.dl-who-opt span:hover{{border-color:var(--green)}}
.dl-who-opt input:checked+span{{background:var(--navy);border-color:var(--navy);color:#fff}}
.dl-who-opt input:focus-visible+span{{outline:none;box-shadow:0 0 0 3px rgba(21,128,127,.22)}}
.dl-fields{{display:flex;flex-wrap:wrap;gap:10px;align-items:center}}
.dl-in{{flex:1 1 190px;min-width:0;font-family:var(--sans);font-size:.95rem;color:var(--ink);
padding:12px 14px;border:1px solid var(--sand);border-radius:8px;background:#fff;
transition:border-color .15s,box-shadow .15s}}
.dl-in::placeholder{{color:var(--muted)}}
.dl-in:focus{{outline:none;border-color:var(--green);box-shadow:0 0 0 3px rgba(21,128,127,.14)}}
.dl-go{{flex:none;border:0;cursor:pointer;font-family:var(--sans)}}
.dl-go svg{{width:16px;height:16px;flex:none;fill:var(--navy)}}
.dl-go:disabled{{opacity:.6;cursor:default;transform:none}}
.dl-note{{margin:11px 0 0;font-size:.82rem;color:var(--muted);max-width:60ch}}
.dl-msg{{margin:11px 0 0;font-size:.9rem;font-weight:600;color:var(--green)}}
.dl-msg.is-err{{color:#b4452f}}
@media(max-width:540px){{.dl-go{{width:100%;justify-content:center}}}}
ul.links{{list-style:none;padding:0;margin:0}}ul.links li{{margin:.4em 0}}
ul.links a{{color:var(--green);text-decoration:none;font-weight:500}}
ul.links a:hover{{text-decoration:underline}}
.study-banner{{display:block;color:#fff;border-radius:14px;padding:24px 28px;text-decoration:none;
border-left:5px solid var(--gold);margin:.6em 0 1.6em;
background:radial-gradient(135% 150% at 100% 0%,#163a63 0%,var(--navy) 60%)}}
.study-kicker{{display:block;font-size:.72rem;font-weight:700;letter-spacing:1.2px;
text-transform:uppercase;color:var(--gold)}}
.study-title{{display:block;font-family:var(--serif);font-weight:600;font-size:1.5rem;
line-height:1.15;margin:.25em 0}}
.study-sub{{display:block;font-size:.94rem;color:#c7d2df}}
.ad-unit{{background:#fff;border:1px solid var(--line);border-radius:11px;margin:1.8em 0;overflow:hidden}}
.ad-label{{display:block;font-size:.64rem;font-weight:700;letter-spacing:1.3px;text-transform:uppercase;
color:var(--muted);background:var(--cream);padding:6px 14px;border-bottom:1px solid var(--line)}}
.ad-body{{display:flex;gap:15px;align-items:center;padding:15px 17px;text-decoration:none;color:var(--ink)}}
.ad-img{{width:108px;height:80px;object-fit:cover;border-radius:7px;flex:none}}
.ad-text{{display:flex;flex-direction:column;gap:3px}}
.ad-headline{{font-family:var(--serif);font-weight:600;font-size:1.1rem;color:var(--navy)}}
.ad-copy{{font-size:.9rem;color:var(--ink)}}
.ad-adv{{font-size:.74rem;color:var(--muted)}}
.watch-sponsored{{border-top-color:var(--gold)}}
.watch-sponsored-badge{{display:inline-block;align-self:flex-start;color:var(--navy);background:var(--gold);
padding:2px 9px;border-radius:5px;letter-spacing:.6px}}
a{{color:var(--green)}}

/* live-market pulse - the landing's .pulse-dot, a real "data is live" signal */
.pulse-dot{{display:inline-flex;width:11px;height:11px;position:relative}}
.pulse-dot i{{position:absolute;inset:0;border-radius:50%;background:var(--teal)}}
.pulse-dot::after{{content:"";position:absolute;inset:0;border-radius:50%;background:var(--teal);
animation:pulse-ring 1.9s cubic-bezier(.4,0,.2,1) infinite}}
@keyframes pulse-ring{{0%{{transform:scale(1);opacity:.7}}80%,100%{{transform:scale(2.6);opacity:0}}}}

/* pure-CSS bar charts - every value is real DOM text (.bar-val), never a picture of a number */
.chart{{margin:1.7em 0;background:var(--glass);-webkit-backdrop-filter:blur(12px) saturate(1.06);
backdrop-filter:blur(12px) saturate(1.06);border:1px solid var(--glassln);border-radius:12px;
padding:20px 22px 18px}}
.chart-cap{{font-family:var(--serif);font-weight:600;font-size:1.05rem;color:var(--navy);margin:0 0 1em}}
.bars{{display:flex;flex-direction:column;gap:13px}}
.bar-row{{display:grid;grid-template-columns:minmax(120px,200px) 1fr auto;align-items:center;gap:14px}}
.bar-label{{font-size:.86rem;font-weight:600;color:var(--ink);display:flex;
flex-direction:column;line-height:1.25}}
.bar-sub{{font-size:.72rem;font-weight:400;color:var(--muted)}}
.bar-track{{background:var(--pale);border-radius:6px;height:22px;overflow:hidden}}
.bar-fill{{display:block;height:100%;border-radius:6px;min-width:3px;
transition:width .6s cubic-bezier(.4,0,.2,1)}}
.bar-val{{font-family:var(--serif);font-optical-sizing:auto;font-weight:600;font-size:1.02rem;
color:var(--navy);font-variant-numeric:tabular-nums lining-nums;text-align:right;white-space:nowrap}}
.chart-note{{font-size:.8rem;color:var(--muted);margin:1.1em 0 0;max-width:68ch;line-height:1.5}}

/* shadow-doc: a layered resting shadow on every data surface, lifted from the landing's
   .certificate so the report reads as paper laid on paper, not flat boxes */
.kpis,.chart,.aud,.area-card{{box-shadow:0 1px 2px rgba(14,39,71,.05),0 16px 38px -24px rgba(14,39,71,.30)}}
/* card lift - a little life on hover, killed under reduced-motion */
.aud,.area-card{{transition:transform .15s ease,box-shadow .15s ease}}
.aud:hover,.area-card:hover{{transform:translateY(-2px);box-shadow:0 16px 34px -18px rgba(14,39,71,.55)}}
/* link-u: the landing's underline-grow on every in-content link - a hairline that fills on hover */
ul.links a,.aud a,.refs a,.src-links a{{position:relative;text-decoration:none;
background-image:linear-gradient(var(--green),var(--green));background-repeat:no-repeat;
background-position:0 100%;background-size:0% 1.5px;transition:background-size .25s ease}}
ul.links a:hover,.aud a:hover,.refs a:hover,.src-links a:hover{{background-size:100% 1.5px}}
@media(prefers-reduced-motion:reduce){{
.bar-fill,.aud,.area-card,.cta,ul.links a,.aud a,.refs a,.src-links a,.aud-cover img{{transition:none}}
.aud:hover,.area-card:hover,.cta:hover,.hero:hover{{transform:none}}
.aud:hover .aud-cover img{{transform:none}}
.hero{{transition:none}}
.page-aura .ab,.page-aura::before,.page-aura::after,.pulse-dot::after,.hero-shine::before{{animation:none}}
ul.links a:hover,.aud a:hover,.refs a:hover,.src-links a:hover{{background-size:100% 1.5px}}
}}

/* footer colophon - the landing's idiom: a quiet document colophon on the paper ground (NOT a
   navy bar), so the navy-inked compact lockup reads in full instead of vanishing into blue.
   A gold hairline marks the top; text is muted, links green, the brand name navy. */
footer.site{{background:var(--paper);color:var(--muted);margin-top:3.5em;padding:0 0 42px;
font-size:.9rem}}
footer.site .wrap{{display:block;border-top:1px solid var(--line);padding-top:28px}}
footer.site strong{{color:var(--navy);font-family:var(--serif);font-weight:600}}
footer.site p{{max-width:74ch}}
footer.site a{{color:var(--green);font-weight:600}}
/* the EXACT compact lockup (navy-inked mark) on the light colophon, exactly as the landing
   footer shows it - shown as-is, never recoloured or recreated (Brand Asset Rule) */
.foot-brand{{display:inline-block;margin:0 0 16px}}
.foot-brand img{{display:block;height:auto;width:180px}}
.ernesta{{font-size:.8rem;color:var(--muted);letter-spacing:.02em;margin:1.4em 0 0;opacity:.85}}
/* --- share bar: first-party social sharing, keyed to the canonical URL (no third-party SDK) --- */
.share-bar{{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:2.4em 0 .6em;
padding:14px 16px;border:1px solid var(--line);border-radius:14px;background:var(--glass)}}
.share-label{{font-weight:650;color:var(--navy);margin-right:4px;font-size:.95rem}}
.share-btn{{display:inline-flex;align-items:center;padding:7px 14px;border-radius:999px;
border:1px solid var(--line);background:#fff;color:var(--navy);font-size:.86rem;font-weight:600;
text-decoration:none;cursor:pointer;line-height:1;
transition:transform .08s ease,box-shadow .12s ease,background .12s ease,color .12s ease}}
.share-btn:hover{{transform:translateY(-1px);box-shadow:0 4px 14px rgba(20,40,80,.12)}}
.share-x:hover{{background:#000;color:#fff;border-color:#000}}
.share-facebook:hover{{background:#1877f2;color:#fff;border-color:#1877f2}}
.share-whatsapp:hover{{background:#25d366;color:#fff;border-color:#25d366}}
.share-linkedin:hover{{background:#0a66c2;color:#fff;border-color:#0a66c2}}
.share-copy:hover{{background:var(--navy);color:var(--cream);border-color:var(--navy)}}
.share-copied{{font-size:.82rem;color:var(--green);font-weight:650}}
/* --- comments: the Remark42 widget styles itself; we just give it room + spacing for the ad --- */
#comments{{margin-top:2.4em}}
#remark42{{margin-top:1.1em;min-height:120px}}
.comments-ad{{margin:1.1em 0}}
@media(max-width:600px){{
h1{{font-size:1.95rem}}
.standfirst,.answer{{font-size:1.16rem}}
.mast-row{{flex-direction:column;align-items:flex-start;gap:12px}}
.mast-edition{{text-align:left}}
.kpi{{flex-basis:46%}}
.hf{{flex-basis:46%}}
.bar-row{{grid-template-columns:1fr;gap:5px}}
.bar-val{{text-align:left}}
/* the area navigator on mobile: a slim trigger row; the drawer is already responsive (86vw) */
.cn-row{{padding:7px 16px;gap:9px}}
.cn-trigger{{padding:6px 13px 6px 11px}}
}}"""


def _hero_figure(hero):
    """Render a hero illustration figure from a {url, caption} dict. Pure data, no network.
    Returns '' when no image was supplied, so every surface degrades cleanly."""
    h = hero or {}
    url = h.get("url")
    if not url:
        return ""
    cap = h.get("caption") or "Editorial illustration"
    return (f'<figure class="hero"><img src="{e(url)}" alt="{e(cap)}" loading="eager">'
            f'<span class="hero-shine" aria-hidden="true"></span>'
            f'<figcaption>{e(cap)}</figcaption></figure>')


def _hero_block(model):
    """The masthead hero illustration for a district report, from model['hero']."""
    return _hero_figure(model.get("hero"))


def _area_photo_block(model):
    """A real, attributed city-centre photograph from model['area_photo'] (sourced from
    Pexels). Pure data. The figcaption carries an honest caption plus the Pexels licence
    attribution - the photographer's name and a link to the photo on Pexels - when those
    fields are present, falling back to a plain credit string otherwise. Omitted when no
    image is available (honest absence beats a mislabelled photo)."""
    p = model.get("area_photo") or {}
    url = p.get("url")
    if not url:
        return ""
    cap = p.get("caption") or "City centre"
    grapher = p.get("photographer")
    if grapher:
        by = (f'<a href="{e(p["photographer_url"])}" rel="noopener nofollow" target="_blank">'
              f'{e(grapher)}</a>') if p.get("photographer_url") else e(grapher)
        on = (f'<a href="{e(p["photo_url"])}" rel="noopener nofollow" target="_blank">Pexels</a>'
              ) if p.get("photo_url") else "Pexels"
        credit = f"Photo by {by} on {on}"
    else:
        credit = e(p.get("credit") or "")
    return (f'<figure class="area-photo"><img src="{e(url)}" alt="{e(cap)}" loading="lazy">'
            f'<figcaption>{e(cap)} &middot; {credit}</figcaption></figure>')


def _report_voices_section(model):
    """The 'What people say' section: real, captured public-forum voices for this district,
    rendered beside the numbers as colour, never as evidence. Voices are frozen out of band
    via the Hit MCP (hitman.red, an Ernesta Labs preview) and loaded by social_sentiment;
    when none are present the section omits. Mirrors the study's voice markup so the two
    surfaces look identical, but it is report-scoped and carries the free/Pro honesty line:
    on the free report these are context; the price-impact synthesis is a Pro feature.

    The honesty contract holds absolutely: nothing here moves a figure on the page, and the
    free report never claims a mechanism (how sentiment affects price) it does not compute -
    that synthesis is named as Pro-only and is not performed here."""
    s = model.get("sentiment") or {}
    voices = s.get("voices") or []
    if not voices:
        return ""
    d = model["district"]
    cards = []
    for v in voices:
        reply = (f'<p class="voice-reply">&ldquo;{e(v["reply"])}&rdquo; '
                 f'<span class="voice-tag">- a reply</span></p>') if v.get("reply") else ""
        tie = (f'<p class="voice-tie">{e(v["ties_to"])}</p>') if v.get("ties_to") else ""
        url = e(v.get("url", "#"))
        cards.append(
            f'<figure class="voice"><blockquote>&ldquo;{e(v.get("quote",""))}&rdquo;</blockquote>'
            f'{reply}'
            f'<figcaption>{e(v.get("where",""))} &middot; '
            f'<a href="{url}" rel="nofollow noopener noreferrer" target="_blank">'
            f'{e(v.get("subreddit","source"))}</a></figcaption>{tie}</figure>')
    note = e(s.get("disclaimer", ""))
    src = e(s.get("source_label", ""))
    method = e(s.get("method", ""))
    captured = e(s.get("captured_at", ""))
    src_line = (f'<p class="voice-src">Source: {src}'
                f'{(" &middot; captured " + captured) if captured else ""}.</p>') if src else ""
    # The free/Pro line: honest about what this section is and is NOT. No invented mechanism.
    pro_line = (f'<p class="voice-pro">On this free report these voices are context - the human '
                f'noise around the same sold and listing data shown above. <strong>How local '
                f'sentiment, schools and flood risk actually move a price</strong> is the '
                f'synthesis in the paid {brand_name()} report; it is never blended into the '
                f'figures here.</p>')
    return (f'<section id="voices"><h2>What people in {e(d)} are saying</h2>'
            f'<p>The numbers above describe what the market did; these posts are what people '
            f'in it say while they are doing it. {method}</p>'
            f'<div class="voice-grid">{"".join(cards)}</div>'
            f'<p class="watch-note"><strong>Read these as colour, not evidence.</strong> {note}</p>'
            f'{src_line}'
            f'{pro_line}'
            f'</section>')


def render_post(model, *, siblings=None, cities_nav=None):
    """Render one district report to a complete, self-contained HTML page."""
    d, city = model["district"], model["city"]
    # Load any frozen social-sentiment voices for this district (Hit MCP -> social_sentiment).
    # Render-time load so freshly-frozen voices appear without re-running market_district.gather.
    # Best-effort: {} when none, and we flag 'reddit' present only when voices actually exist,
    # so the hitman.red citation is honest by construction.
    if not model.get("sentiment"):
        model["sentiment"] = social_sentiment.load(model["slug"], (city or {}).get("slug"))
    if (model.get("sentiment") or {}).get("voices"):
        model.setdefault("present", {})["hitman_red"] = True
    faqs = _faqs(model)
    refs = _references(model)
    title = f"{d} House Prices &amp; Property Market Report | {city['series']}"
    desc = _answer_paragraph(model)
    desc_meta = e(desc[:157] + ("..." if len(desc) > 157 else ""))
    canonical = SITE + post_url(model["slug"])
    jsonld = _jsonld(model, faqs, refs)

    body = f"""<article class="wrap">
  {_hero_block(model)}
  {_cover(e(city['series']), f"{e(d)} House Prices &amp; Property Market", desc,
          meta_html=f"{e(_district_name(model))} &middot; Updated {e(model['generated_at'])}")}
  {_ad_slot("district", "leaderboard", slug=d)}
  {_kpi_grid(model)}
  {_download_block(model)}
  {_cta_block(model, "mid")}
  {_sold_section(model)}
  {_evidence_section(model)}
  {_live_section(model)}
  {_rent_section(model)}
  {_ad_slot("district", "mid", slug=d)}
  {_watch_section(model)}
  {_audience_section(model)}
  {_area_section(model)}
  {_report_voices_section(model)}
  {_hpi_section(model)}
  {_faq_section(faqs)}
  {_cta_block(model, "foot")}
  {_ad_slot("district", "footer", slug=d)}
  {_internal_links(model, siblings, cities_nav)}
  {_official_sources_section()}
  {_share_bar(model)}
  {_comments_section(model)}
  {_references_section(refs)}
</article>"""

    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc_meta}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc_meta}">
<meta property="og:url" content="{e(canonical)}">
<meta property="og:site_name" content="Honestly">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">{jsonld}</script>
{_fonts()}
<style>{_css()}</style>
</head>
<body>
<div class="grain" aria-hidden="true"></div>
<div class="page-aura" aria-hidden="true"><span class="ab b1"></span><span class="ab b2"></span><span class="ab b3"></span></div>
{_masthead(city['series'], _citynav(cities_nav, active_city=city['slug'], active_district=d))}
{body}
<footer class="site"><div class="wrap">
{_foot_brand()}
<p>{brand_name()} - a defensible value from sold evidence. The figures above are
{_sold_authority(city.get('country',''))}, live listings and the UK House Price Index, reported beside
each other, never blended. This page is market evidence, not a valuation.</p>
<p><a href="{e(BOT)}">Get a valuation on Telegram</a> &middot;
<a href="{e(BLOG_BASE)}/">All reports</a> &middot;
<a href="{e(hub_url(city['slug']))}">{e(city['series'])}</a></p>
</div></footer>
{_DL_SCRIPT}
</body></html>"""


# ----------------------------------------------------------------- hub + index
def _shell(title, desc, canonical, inner, logo_link=None, series="Property market reports",
           jsonld=None, citynav=""):
    jsonld_tag = (f'<script type="application/ld+json">{jsonld}</script>' if jsonld else "")
    return f"""<!doctype html>
<html lang="en-GB"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:title" content="{e(title)}"><meta property="og:type" content="website">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canonical)}">
<meta property="og:site_name" content="Honestly">
<meta name="twitter:card" content="summary_large_image">
{jsonld_tag}
{_fonts()}
<style>{_css()}</style></head><body>
<div class="grain" aria-hidden="true"></div>
<div class="page-aura" aria-hidden="true"><span class="ab b1"></span><span class="ab b2"></span><span class="ab b3"></span></div>
{_masthead(series, citynav)}
<main class="wrap">{inner}</main>
<footer class="site"><div class="wrap">
{_foot_brand()}
<p>{brand_name()} - daily postcode property intelligence from official data.
<a href="{e(BOT)}">Get a valuation on Telegram</a>.</p></div></footer>
</body></html>"""


def _median(vals):
    """Plain median of a list of numbers, or None if empty."""
    xs = sorted(v for v in vals if v is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def _city_aggregate(posts):
    """An honest city-level roll-up of the district reports' OWN headline medians - never a
    blended valuation, just the range and typical of figures each page already publishes.
    Returns None when no priced reports exist yet (so the head-term copy never invents a
    number)."""
    prices = [p.get("headline_price") for p in posts if p.get("headline_price")]
    if not prices:
        return None
    return {"n_priced": len(prices), "low": min(prices), "high": max(prices),
            "typical": _median(prices)}


def _city_answer(city, posts, agg):
    """The 40-60 word quotable city answer, built only from real reported figures. Doubles as
    the meta description, so it is PLAIN text (no brand HTML)."""
    name = city["name"]
    n = len(posts)
    if agg:
        return (f"Across the {n} {name} postcode districts reported here, recorded median sale "
                f"prices currently range from {money(agg['low'])} to {money(agg['high'])}, "
                f"with a typical district median around {money(agg['typical'])} "
                f"({_sold_authority_name(city.get('country',''))} data). A fresh {name} postcode is rebuilt every day from sold "
                f"prices, live listings and the UK House Price Index, shown side by side and "
                f"never blended. This is market evidence, not a valuation.")
    return (f"A fresh {name} postcode property report every day, each built from that "
            f"district's {_sold_authority_name(city.get('country',''))} sold prices, live listings and the UK House Price "
            f"Index, reported side by side and never blended. This is market evidence, "
            f"not a valuation.")


def _city_faqs(city, posts, agg):
    """City-level FAQ aimed at the broad head-terms people search ('average house price in
    X', 'is X a good place to buy', 'X property market'), every answer grounded in the data
    these pages already report. Non-advisory by construction - we never tell anyone to buy
    or sell, we point at the evidence."""
    name = city["name"]
    n = len(posts)
    faqs = []
    if agg:
        faqs.append((
            f"What is the average house price in {name}?",
            f"Across the {n} {name} postcode districts reported here, recorded median sale "
            f"prices range from {money(agg['low'])} to {money(agg['high'])}, with a typical "
            f"district median around {money(agg['typical'])} "
            f"({_sold_authority(city.get('country',''))}). Prices vary widely by postcode - open a district report below for its "
            f"own sold evidence."))
    faqs.append((
        f"What is the {name} property market like right now?",
        f"A fresh {name} postcode report is published every day. Each is built from that "
        f"district's {_sold_authority_name(city.get('country',''))} sold prices, current asking prices, days on market "
        f"and stuck-stock counts, plus the UK House Price Index - the figures sit beside "
        f"each other, never blended."))
    faqs.append((
        f"Is {name} a good place to buy property?",
        f"No buy-or-sell advice and no valuation. The useful part is the evidence: "
        f"recorded sold prices, current asking prices and "
        f"how long homes are taking to sell, district by district across {name}."))
    faqs.append((
        f"How often is the {name} house price data updated?",
        f"Daily. One {name} postcode district is rebuilt from the latest official data each "
        f"day; once the list is covered, the oldest report is refreshed - so the series "
        f"stays current rather than going stale."))
    faqs.append((
        f"Where does the {name} property data come from?",
        f"{_sold_authority(city.get('country',''))} for sold prices and price per square metre, live "
        f"property listings for asking prices and market pace, and the UK House Price Index "
        f"for the regional trend. All official sources, cited at the foot of every report."))
    return faqs


def _hub_jsonld(city, canonical, title, desc, faqs, agg):
    import json as _json
    name = city["name"]
    org = {"@type": "Organization", "name": "Honestly", "url": SITE,
           "logo": {"@type": "ImageObject", "url": SITE + "/img/logo-icon.png"}}
    place = {"@type": "Place", "name": name,
             "address": {"@type": "PostalAddress", "addressLocality": name,
                         "addressRegion": name, "addressCountry": "GB"}}
    graph = [place, {
        "@type": "CollectionPage", "name": title, "headline": title[:110],
        "description": desc, "url": canonical, "isPartOf": city["series"],
        "about": place, "publisher": org, "inLanguage": "en-GB"}]
    if agg:
        graph.append({
            "@type": "Dataset",
            "name": f"{name} residential sold-price statistics",
            "description": f"Recorded median sale prices across {name} postcode districts, "
                           f"from {_sold_authority(city.get('country',''))}.",
            "url": canonical, "spatialCoverage": place, "creator": org,
            "variableMeasured": [
                {"@type": "PropertyValue", "name": "Lowest district median sale price",
                 "value": agg["low"], "unitText": "GBP"},
                {"@type": "PropertyValue", "name": "Highest district median sale price",
                 "value": agg["high"], "unitText": "GBP"},
                {"@type": "PropertyValue", "name": "Typical district median sale price",
                 "value": agg["typical"], "unitText": "GBP"}],
            "license": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
            "isAccessibleForFree": True})
    if faqs:
        graph.append({"@type": "FAQPage",
                      "mainEntity": [{"@type": "Question", "name": q,
                                      "acceptedAnswer": {"@type": "Answer", "text": a}}
                                     for q, a in faqs]})
    graph.append({"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE},
        {"@type": "ListItem", "position": 2, "name": "Blog", "item": SITE + BLOG_BASE + "/"},
        {"@type": "ListItem", "position": 3, "name": city["series"], "item": canonical}]})
    return _json.dumps({"@context": "https://schema.org", "@graph": graph},
                       ensure_ascii=False)


def render_city_hub(city, posts, *, cities_nav=None, hero=None, commentary_url=None):
    """posts: list of dicts {district, slug, generated_at, headline_price}. Newest first.

    Built to surface for the BROAD city head-terms ('Manchester house prices', 'Manchester
    property market', 'average house price Manchester', 'is Manchester a good place to buy')
    - not just the narrow district-report query. The title, H1, answer box, city FAQ and
    JSON-LD all target those head-terms, every claim grounded in the districts' own reported
    figures (honest by construction - no blended valuation, no invented number)."""
    name = city["name"]
    canonical = SITE + hub_url(city["slug"])
    agg = _city_aggregate(posts)
    answer = _city_answer(city, posts, agg)
    faqs = _city_faqs(city, posts, agg)
    title = f"{name} House Prices & Property Market | {city['series']}"
    jsonld = _hub_jsonld(city, canonical, title.replace("&", "&amp;"), answer, faqs, agg)
    rows = ""
    for p in posts:
        sub = (f" - median {money_short(p['headline_price'])}"
               if p.get("headline_price") else "")
        rows += (f'<li><a href="{e(post_url(p["slug"]))}">{e(city["name"])} '
                 f'{e(p["district"])} house prices</a>{sub} '
                 f'<span class="meta">{e(p.get("generated_at",""))}</span></li>')
    cover_stats = [(str(len(posts)), "Districts reported")]
    if agg:
        cover_stats = [
            (money_short(agg["low"]), "Lowest district median"),
            (money_short(agg["typical"]), "Typical district median"),
            (money_short(agg["high"]), "Highest district median"),
            (str(len(posts)), "Districts reported")]
    nav = ""
    if cities_nav:
        nav = "".join(f'<li><a href="{e(hub_url(c["slug"]))}">{e(c["series"])}</a></li>'
                      for c in cities_nav if c["slug"] != city["slug"])
        nav = f'<section><h2>Other city series</h2><ul class="links">{nav}</ul></section>'
    commentary_banner = ""
    if commentary_url:
        commentary_banner = (
            f'<section><a class="study-banner" href="{e(commentary_url)}">'
            f'<span class="study-kicker">Publication analysis</span>'
            f'<span class="study-title">{e(name)} newsletters, blogs and headlines - checked '
            f'against the sold record</span>'
            f'<span class="study-sub">Read the original claim, then check it beside {e(name)}\'s '
            f'own recorded sold prices &middot; no takedown, no valuation &rarr;</span></a></section>')
    inner = f"""{_hero_figure(hero)}
{_cover(f"{e(city['series'])} &middot; {e(name)} property market",
        f"{e(name)} House Prices &amp; Property Market", answer, stats=cover_stats)}
{commentary_banner}
{_ad_slot("hub", "leaderboard", slug=city["slug"])}
<section><h2>{e(name)} house prices by postcode district</h2>
<p>Open any {e(name)} postcode below for its own sold-price evidence, price per square
metre, live asking prices and market pace - rebuilt daily from official data.</p>
{_chart_district_medians(name, posts, country=city.get('country',''))}
<ul class="links">{rows or '<li>Coming soon.</li>'}</ul></section>
{_faq_section(faqs)}
{_ad_slot("hub", "footer", slug=city["slug"])}
{_cta_block({'district': city['name'], 'city': city}, 'foot')}
{nav}"""
    return _shell(title, meta_clip(answer), canonical, inner, series=city['series'],
                  jsonld=jsonld,
                  citynav=_citynav(cities_nav, active_city=city['slug']))


def render_index(by_city, *, cities_nav=None, featured_study=None, hero=None,
                 commentary_pages=None, content_pages=None):
    """by_city: list of (city, posts) tuples in display order. featured_study, when given,
    is the study model dict - it renders a banner linking the cross-city data study.
    commentary_pages, when given, lists publication-analysis pages to surface on the index.
    content_pages, when given, lists the broader topical blog pages."""
    canonical = SITE + BLOG_BASE + "/"
    study_banner = ""
    if featured_study and featured_study.get("ok"):
        a = featured_study["agg"]
        study_banner = (
            f'<section><a class="study-banner" href="{e(_study_url(featured_study))}">'
            f'<span class="study-kicker">Original data study</span>'
            f'<span class="study-title">The UK City-Centre Property Index</span>'
            f'<span class="study-sub">Days on market, asking vs sold, stuck stock and price per '
            f'm² across {a["n_districts"]} city centres in {a["n_cities"]} cities '
            f'&middot; updated {e(featured_study["generated_at"])} &rarr;</span></a></section>')
    content_banner = ""
    if content_pages:
        cards = ""
        for page in content_pages:
            if not isinstance(page, dict):
                continue
            url = page.get("url") or ""
            title = page.get("title") or ""
            summary = page.get("summary") or ""
            if not url:
                continue
            cov = page.get("cover") or {}
            cover_html = ""
            if cov.get("url"):
                alt = cov.get("alt") or title
                cover_html = (f'<a class="aud-cover" href="{e(url)}" tabindex="-1" aria-hidden="true">'
                              f'<img src="{e(cov["url"])}" alt="{e(alt)}" loading="lazy" '
                              f'width="600" height="338"></a>')
            cards += (f'<div class="aud">{cover_html}<h3><a href="{e(url)}">{e(title)}</a></h3>'
                      f'<p>{e(summary)}</p>'
                      f'<p><a href="{e(url)}">Read the page &rarr;</a></p></div>')
        if cards:
            content_banner = (
                f'<section><h2>Make the next property decision clearer</h2>'
                f'<p>Compare homes, check headlines against sold prices, track alerts and understand '
                f'why a listing may be stuck.</p>'
                f'<div class="aud-grid">{cards}</div></section>')
    commentary_banner = ""
    if commentary_pages:
        links = ""
        for page in commentary_pages:
            city = page.get("city") or {}
            url = page.get("url") or ""
            if not (city and url):
                continue
            links += (f'<li><a href="{e(url)}">{e(city.get("name") or city.get("series") or "City")} '
                      f'headlines vs the record</a></li>')
        if links:
            commentary_banner = (
                f'<section><h2>Headlines, blogs and newsletters - checked against the record</h2>'
                f'<p>Read the original first, then compare it with the local sold record and live '
                f'listings.</p>'
                f'<ul class="links">{links}</ul></section>')
    cards = ""
    for city, posts in by_city:
        latest = posts[0] if posts else None
        link = post_url(latest["slug"]) if latest else hub_url(city["slug"])
        sub = (f"Latest: {e(city['name'])} {e(latest['district'])}" if latest
               else "Coming soon")
        cov = city.get("cover") or {}
        cover_html = ""
        if cov.get("url"):
            alt = cov.get("alt") or f'{city["name"]} city centre'
            cover_html = (f'<a class="aud-cover" href="{e(link)}" tabindex="-1" aria-hidden="true">'
                          f'<img src="{e(cov["url"])}" alt="{e(alt)}" loading="lazy" '
                          f'width="600" height="338"></a>')
        cards += (f'<div class="aud">{cover_html}<h3><a href="{e(hub_url(city["slug"]))}">'
                  f'{e(city["series"])}</a></h3>'
                  f'<p class="meta">{e(city["name"])} &middot; {len(posts)} reports</p>'
                  f'<p>{sub}</p>'
                  f'<p><a href="{e(link)}">Read the latest &rarr;</a></p></div>')
    cities_line = ", ".join(c["name"] for c, _ in by_city)
    desc = ("Daily property market reports for UK postcode districts - sold prices, price "
            "per square metre, live market and area data from official sources. Covering "
            + cities_line + ".")
    idx_jsonld = _index_jsonld(by_city, canonical, desc)
    idx_answer = ("Every day brings a fresh property market report for a postcode district "
                  "in each of the UK's most active cities - sold prices, price per square metre, "
                  "live-market dynamics and area intelligence, straight from official data. Same "
                  "format, different postcode, packed with that district's own numbers.")
    total_reports = sum(len(posts) for _, posts in by_city)
    idx_stats = [(str(len(by_city)), "Cities covered"),
                 (str(total_reports), "Reports published")]
    inner = f"""{_hero_figure(hero)}
{_cover(f"{brand_name()} &middot; official-data market reports",
        "UK House Prices &amp; Property Market Reports by Postcode", idx_answer, stats=idx_stats)}
{study_banner}
{content_banner}
{commentary_banner}
{_ad_slot("index", "leaderboard")}
<section><h2>Choose your city</h2>
<p>Pick a city for its house prices and property-market reports, postcode by postcode.</p>
<div class="aud-grid">{cards}</div></section>
{_ad_slot("index", "footer")}
{_cta_block({'district': 'any UK address', 'city': {'name': 'the UK', 'slug': ''}}, 'foot')}"""
    return _shell("UK House Prices & Property Market Reports by Postcode | Honestly",
                  meta_clip(desc), canonical, inner, jsonld=idx_jsonld,
                  citynav=_citynav(cities_nav))


def _index_jsonld(by_city, canonical, desc):
    """JSON-LD for the blog index: a CollectionPage that lists every city series as an
    ItemList, plus the breadcrumb. Machine-readable 'this site reports property data for
    these named UK cities' - the entity signal behind the city head-terms."""
    import json as _json
    org = {"@type": "Organization", "name": "Honestly", "url": SITE,
           "logo": {"@type": "ImageObject", "url": SITE + "/img/logo-icon.png"}}
    items = [{"@type": "ListItem", "position": i,
              "name": f"{c['name']} house prices & property market",
              "url": SITE + hub_url(c["slug"])}
             for i, (c, _) in enumerate(by_city, 1)]
    graph = [
        {"@type": "CollectionPage",
         "name": "UK House Prices & Property Market Reports by Postcode",
         "description": desc, "url": canonical, "publisher": org, "inLanguage": "en-GB",
         "mainEntity": {"@type": "ItemList", "itemListElement": items}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE},
            {"@type": "ListItem", "position": 2, "name": "Blog", "item": canonical}]}]
    return _json.dumps({"@context": "https://schema.org", "@graph": graph},
                       ensure_ascii=False)


# ----------------------------------------------------------------- the data study
def _study_url(study):
    return f"{BLOG_BASE}/{study['slug']}/"


def _gap_word(pct_val):
    """'X% below' / 'X% above' / 'level with', from a signed integer percentage."""
    if pct_val is None:
        return "level with"
    if pct_val < 0:
        return f"{abs(pct_val)}% below"
    if pct_val > 0:
        return f"{pct_val}% above"
    return "level with"


def _study_table(rows, cols, caption):
    """Render a league table. cols is a list of (header, fn(row)->str)."""
    head = "".join(f"<th>{e(h)}</th>" for h, _ in cols)
    body = ""
    for i, r in enumerate(rows, 1):
        tds = f"<td>{i}</td>" + "".join(f"<td>{fn(r)}</td>" for _, fn in cols)
        body += f"<tr>{tds}</tr>"
    return (f'<table class="data"><caption>{e(caption)}</caption>'
            f'<thead><tr><th>#</th>{head}</tr></thead><tbody>{body}</tbody></table>')


def _study_place_cell(r):
    return (f'<a href="{e(post_url(r["slug"]))}">{e(r["city"])} {e(r["district"])}</a>')


def _study_findings(study):
    """The 5-7 key-findings bullets, each bound to a real figure in the study model so the
    prose can never drift from the data."""
    a = study["agg"]
    out = []
    ds, df = a.get("dom_slowest"), a.get("dom_fastest")
    if ds and df and a.get("dom_spread_x"):
        out.append(
            f"The gap between the slowest and fastest city centre is roughly "
            f"<strong>{a['dom_spread_x']}x</strong>: {e(ds['city'])} {e(ds['district'])} "
            f"averages {ds['mean_dom']} days on the market, against {df['mean_dom']} days in "
            f"{e(df['city'])} {e(df['district'])}.")
    out.append(
        f"In <strong>{a['neg_gap_count']} of {a['n_districts']}</strong> districts the median "
        f"asking price sits <em>below</em> the median sold price. This is a composition signal, "
        f"not a discount: the flats on sale today skew smaller and cheaper than the trailing "
        f"two years of completed sales, so the two medians describe different stock.")
    st = a.get("stuck_top")
    if st and st.get("stuck_share_pct") is not None:
        out.append(
            f"Stuck stock concentrates in the largest Midlands and North-West cores: "
            f"{e(st['city'])} {e(st['district'])} has <strong>{st['stuck_share_pct']}%</strong> "
            f"of its available listings sitting 90+ days, against a {a['median_stuck_share_pct']}% "
            f"median across all {a['n_districts']} districts.")
    pt, pb = a.get("psm_top"), a.get("psm_bottom")
    if pt and pb and a.get("psm_spread_x"):
        out.append(
            f"Price per square metre spans <strong>{a['psm_spread_x']}x</strong>, from "
            f"{money(pt['psm_median'])}/m² in {e(pt['city'])} {e(pt['district'])} to "
            f"{money(pb['psm_median'])}/m² in {e(pb['city'])} {e(pb['district'])} - the cleanest "
            f"like-for-like comparison across cities.")
    out.append(
        f"The typical city centre shows a median sold price of "
        f"{money(a['median_sold_median'])} and a median {money(a['median_psm'])}/m², across "
        f"{a['total_on_market']:,} live listings and {a['total_sales_12m']:,} sales in the last "
        f"twelve months.")
    return out


def _study_sentiment_section(study):
    s = study.get("sentiment") or {}
    voices = s.get("voices") or []
    if not voices:
        return ""
    cards = []
    for v in voices:
        reply = (f'<p class="voice-reply">&ldquo;{e(v["reply"])}&rdquo; '
                 f'<span class="voice-tag">- a reply</span></p>') if v.get("reply") else ""
        tie = (f'<p class="voice-tie">{e(v["ties_to"])}</p>') if v.get("ties_to") else ""
        cards.append(
            f'<figure class="voice"><blockquote>&ldquo;{e(v.get("quote",""))}&rdquo;</blockquote>'
            f'{reply}'
            f'<figcaption>{e(v.get("where",""))} &middot; '
            f'<a href="{e(v.get("url","#"))}" rel="nofollow noopener noreferrer" target="_blank">'
            f'{e(v.get("subreddit","source"))}</a></figcaption>{tie}</figure>')
    note = e(s.get("disclaimer", ""))
    return (f'<section id="voices"><h2>What sellers and buyers are saying</h2>'
            f'<p>The numbers above describe what the market did; these posts are what people '
            f'in it say while they are doing it. {e(s.get("method",""))}</p>'
            f'<div class="voice-grid">{"".join(cards)}</div>'
            f'<p class="watch-note"><strong>Read these as colour, not evidence.</strong> {note}</p>'
            f'</section>')


def _study_jsonld(study, faqs):
    import json as _json
    a = study["agg"]
    url = SITE + _study_url(study)
    title = "UK City-Centre Property Index"
    desc = (f"Days on market, asking-vs-sold gap, stuck stock and price per square metre across "
            f"{a['n_districts']} city-centre postcode districts in {a['n_cities']} UK cities.")
    place = {"@type": "Place", "name": "United Kingdom city centres",
             "address": {"@type": "PostalAddress", "addressCountry": "GB"}}
    measured = [
        {"@type": "PropertyValue", "name": "Median sold price", "value": a["median_sold_median"],
         "unitText": "GBP"},
        {"@type": "PropertyValue", "name": "Median price per square metre",
         "value": a["median_psm"], "unitText": "GBP/m2"},
        {"@type": "PropertyValue", "name": "Median days on market", "value": a["median_mean_dom"]},
        {"@type": "PropertyValue", "name": "Median asking-vs-sold gap",
         "value": a["median_asking_gap_pct"], "unitText": "PERCENT"},
        {"@type": "PropertyValue", "name": "Median stuck-stock share",
         "value": a["median_stuck_share_pct"], "unitText": "PERCENT"},
    ]
    graph = [
        {"@type": "Article", "headline": title, "description": desc,
         "datePublished": study["generated_at"], "dateModified": study["generated_at"],
         "url": url, "author": {"@type": "Organization", "name": "Honestly", "url": SITE},
         "publisher": {"@type": "Organization", "name": "Honestly",
                       "logo": {"@type": "ImageObject", "url": SITE + "/img/logo-icon.png"}},
         "mainEntityOfPage": url},
        {"@type": "Dataset", "name": "UK City-Centre Property Index",
         "description": desc + f" Sold figures are {_study_authorities(study)} records of "
         "completed transactions; asking figures are live listings. Updated as each district "
         "refreshes.",
         "url": url, "spatialCoverage": place,
         "creator": {"@type": "Organization", "name": "Honestly"},
         "variableMeasured": measured,
         "distribution": {"@type": "DataDownload", "encodingFormat": "text/csv",
                          "contentUrl": SITE + "/" + study["csv"]},
         "license": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
         "isAccessibleForFree": True},
    ]
    if faqs:
        graph.append({"@type": "FAQPage",
                      "mainEntity": [{"@type": "Question", "name": q,
                                      "acceptedAnswer": {"@type": "Answer", "text": at}}
                                     for q, at in faqs]})
    graph.append({"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE},
        {"@type": "ListItem", "position": 2, "name": "Blog", "item": SITE + BLOG_BASE + "/"},
        {"@type": "ListItem", "position": 3, "name": "UK City-Centre Index", "item": url}]})
    return _json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)


def _study_faqs(study):
    a = study["agg"]
    faqs = []
    faqs.append((
        "Which UK city centre is slowest to sell a flat?",
        f"Of the {a['n_districts']} city-centre districts tracked, "
        f"{a['dom_slowest']['city']} {a['dom_slowest']['district']} is slowest at "
        f"{a['dom_slowest']['mean_dom']} days on the market on average, while "
        f"{a['dom_fastest']['city']} {a['dom_fastest']['district']} is fastest at "
        f"{a['dom_fastest']['mean_dom']} days."))
    faqs.append((
        "Why do asking prices sit below sold prices in some city centres?",
        f"In {a['neg_gap_count']} of {a['n_districts']} districts the median asking price is "
        f"below the median sold price. That is a mix effect, not a discount: the stock on the "
        f"market today is smaller and cheaper than the trailing two years of completed sales, "
        f"so the two medians measure different homes. Asking prices are vendor expectation, not "
        f"evidence of value."))
    faqs.append((
        "What is the most expensive UK city centre per square metre?",
        f"{a['psm_top']['city']} {a['psm_top']['district']} is the most expensive at "
        f"{money(a['psm_top']['psm_median'])} per square metre of recorded sales; "
        f"{a['psm_bottom']['city']} {a['psm_bottom']['district']} is the most affordable at "
        f"{money(a['psm_bottom']['psm_median'])} per square metre."))
    faqs.append((
        "Where does this data come from?",
        f"Sold prices and price per square metre are {_study_authorities(study)} data, the "
        "official record of completed transactions in each country. Live asking prices, days on "
        "market and stuck-stock counts are current listings. The two are reported side by side "
        "and never blended into a single figure. The full per-district table is downloadable as "
        "CSV."))
    return faqs


def render_study(study, *, cities_nav=None, hero=None):
    """Render the cross-district data study to a complete HTML page. Mirrors the district
    page's shell, palette and JSON-LD, but the body is the league-table report. The study
    issues no valuation: it reports official-register sold figures (HM Land Registry for
    England and Wales, Registers of Scotland for Scotland) beside live asking figures."""
    if not study.get("ok"):
        return ""
    a = study["agg"]
    canonical = SITE + _study_url(study)
    title = "UK City-Centre Property Index | Honestly"
    gap_word = _gap_word(a["median_asking_gap_pct"])
    slowest_info = a.get('dom_slowest') or {}
    fastest_info = a.get('dom_fastest') or {}
    tldr = (
        f"As of {brand.DATESTR}, across {a['n_districts']} city-centre postcode districts in "
        f"{a['n_cities']} UK cities, the typical city-centre flat takes about "
        f"{a['median_mean_dom']} days to sell and is listed {gap_word} the local sold median of "
        f"{money(a['median_sold_median'])}. The slowest centre, {slowest_info.get('city','N/A')} "
        f"{slowest_info.get('district','')}, averages {slowest_info.get('mean_dom','N/A')} days - about "
        f"{a['dom_spread_x']} times the fastest, {fastest_info.get('city','N/A')} "
        f"{fastest_info.get('district','')} at {fastest_info.get('mean_dom','N/A')} days. Sold prices are "
        f"{_study_authorities(study)} records; asking prices are live listings, reported side by "
        f"side.")
    desc_meta = e(tldr[:157] + ("..." if len(tldr) > 157 else ""))

    findings = "".join(f"<li>{x}</li>" for x in _study_findings(study))

    # the four league tables
    dom_tbl = _study_table(
        study["by_dom_slowest"],
        [("City centre", _study_place_cell),
         ("Avg days on market", lambda r: str(r["mean_dom"])),
         ("Sold median", lambda r: money(r["sold_median"])),
         ("Stuck 90+ days", lambda r: f'{r["stuck_share_pct"]}%' if r.get("stuck_share_pct") is not None else "-")],
        "Days on the market, slowest to fastest")
    gap_tbl = _study_table(
        study["by_asking_gap"],
        [("City centre", _study_place_cell),
         ("Asking median", lambda r: money(r["asking_median"])),
         ("Sold median", lambda r: money(r["sold_median"])),
         ("Asking vs sold", lambda r: pct(r["asking_gap_pct"]) if r.get("asking_gap_pct") is not None else "-")],
        "Asking median against sold median (context, not a discount)")
    stuck_tbl = _study_table(
        study["by_stuck_share"],
        [("City centre", _study_place_cell),
         ("Stuck 90+ days", lambda r: f'{r["stuck_share_pct"]}%'),
         ("Stuck / available", lambda r: f'{r["stuck_n"]} / {r["available_n"]}'),
         ("Avg days on market", lambda r: str(r["mean_dom"]) if r.get("mean_dom") is not None else "-")],
        "Share of available stock listed 90+ days")
    psm_tbl = _study_table(
        study["by_psm"],
        [("City centre", _study_place_cell),
         ("Price per m²", lambda r: money(r["psm_median"])),
         ("Sold median", lambda r: money(r["sold_median"])),
         ("Sales last 12m", lambda r: str(r["sales_12m"]) if r.get("sales_12m") is not None else "-")],
        "Median sold price per square metre, highest first")

    faqs = _study_faqs(study)
    refs = study.get("references") or []
    jsonld = _study_jsonld(study, faqs)

    ds, st = a["dom_slowest"], a.get("stuck_top")
    body = f"""<article class="wrap">
  {_hero_figure(hero)}
  <header class="report-head">
    <div class="rh-body">
    <p class="kicker">An original-data study by {brand_name()}</p>
    <h1>The UK City-Centre Property Index</h1>
    <p class="dateline">{a['n_districts']} districts &middot; {a['n_cities']} cities &middot;
    Updated {e(study['generated_at'])}</p>
    <p class="standfirst">{e(tldr)}</p>
    </div>
  </header>
  {_ad_slot("study", "leaderboard")}

  <div class="kpis">
    <div class="kpi"><div class="kpi-v">{a['median_mean_dom']}</div>
      <div class="kpi-l">Median days on market</div><div class="kpi-s">across {a['n_districts']} centres</div></div>
    <div class="kpi"><div class="kpi-v">{pct(a['median_asking_gap_pct'])}</div>
      <div class="kpi-l">Median asking vs sold</div><div class="kpi-s">context, not a discount</div></div>
    <div class="kpi"><div class="kpi-v">{a['median_stuck_share_pct']}%</div>
      <div class="kpi-l">Median stuck 90+ days</div><div class="kpi-s">of available stock</div></div>
    <div class="kpi"><div class="kpi-v">{money_short(a['median_psm'])}</div>
      <div class="kpi-l">Median price per m²</div><div class="kpi-s">recorded sales</div></div>
  </div>

  <section id="findings"><h2>Key findings</h2><ul class="findings">{findings}</ul></section>

  <section id="method"><h2>Method</h2>
  <p>This index lays daily city-centre district reports side by side. Every figure is that
  district's own data: sold prices and price per square metre are {_study_authorities(study)}
  data; asking prices, days on market and stuck-stock counts are live listings on the day the
  district was last refreshed. Nothing is blended into a valuation: the official transaction
  record and the live market sit next to each other.</p>
  <p>This snapshot covers <strong>{a['n_districts']} city-centre districts across
  {a['n_cities']} cities</strong> ({", ".join(e(c) for c in a['cities'])}), as of
  {e(a['as_of'])}. It is a sample of the most active city centres, not the whole of any city
  or the whole UK, and it grows as the daily rotation adds districts. You can download every
  number below.</p>
  <p><a class="cta cta-primary" href="/{e(study['csv'])}" download>Download the raw data (CSV)</a></p>
  </section>

  <section id="dom"><h2>1. How long a city-centre flat takes to sell</h2>
  <p>As of {brand.DATESTR}, the spread is stark. {e(ds['city'])} {e(ds['district'])} averages
  {ds['mean_dom']} days on the market; {e(a['dom_fastest']['city'])}
  {e(a['dom_fastest']['district'])} turns over in {a['dom_fastest']['mean_dom']}. Time on
  market is the cleanest read on liquidity - how quickly a realistic asking price finds a
  buyer.</p>
  {dom_tbl}</section>

  <section id="gap"><h2>2. Why asking prices sit below sold prices</h2>
  <p>This is the finding most likely to be misread. In {a['neg_gap_count']} of
  {a['n_districts']} districts the median asking price is <em>below</em> the median sold price.
  That is not sellers discounting - it is a composition effect. The flats listed today are
  smaller and cheaper stock than the trailing two years of completed sales the sold median is
  built from, so the two medians are measuring different homes. Asking prices are vendor
  expectation; they are context beside the sold record, never evidence of value.</p>
  {gap_tbl}</section>

  <section id="stuck"><h2>3. Where stock gets stuck</h2>
  <p>A listing past 90 days is usually a pricing problem, not a market problem.
  {(e(st['city']) + ' ' + e(st['district']) + f" carries the most: {st['stuck_share_pct']}% of its available stock has sat 90+ days.") if st else ''}
  The fastest centres barely register it. The same homes sell quickly when priced to the sold
  evidence and sit when priced to hope.</p>
  {stuck_tbl}</section>

  <section id="psm"><h2>4. Price per square metre, city by city</h2>
  <p>Headline prices mislead because they mix flat sizes. Price per square metre is the honest
  cross-city comparison. It runs from {money(a['psm_top']['psm_median'])}/m² in
  {e(a['psm_top']['city'])} {e(a['psm_top']['district'])} to
  {money(a['psm_bottom']['psm_median'])}/m² in {e(a['psm_bottom']['city'])}
  {e(a['psm_bottom']['district'])} - roughly {a['psm_spread_x']} times.</p>
  {psm_tbl}</section>

  {_ad_slot("study", "mid")}

  {_study_sentiment_section(study)}

  <section id="implications"><h2>What it means</h2>
  <div class="aud-grid">
    <div class="aud"><h3>If you are buying</h3><ul>
      <li>The slow, high-stuck centres are where offers below asking are most likely to land -
      a 90+ day listing has a motivated seller behind it.</li>
      <li>Compare on price per square metre, not headline price, to see which city centre
      actually gives you more home for the money.</li></ul></div>
    <div class="aud"><h3>If you are selling</h3><ul>
      <li>Price to the sold record, not the asking median - in {a['neg_gap_count']} of
      {a['n_districts']} centres the asking median is already below what is completing, and the
      stuck pile is full of homes priced above the evidence.</li>
      <li>Expect roughly the days-on-market figure for your centre at a realistic price; well
      beyond it means the price, not the market, is the problem.</li></ul></div>
    <div class="aud"><h3>If you are an agent</h3><ul>
      <li>The stuck-stock share is your instruction-health gauge - the higher it is, the more
      of your board is a pricing conversation waiting to happen.</li>
      <li>The sold-evidence number is the lever to get a stalled listing moving without a
      guessing game.</li></ul></div>
  </div></section>

  <section id="limits"><h2>Limitations</h2>
  <p>This is a sample of {a['n_districts']} active city-centre districts, not a census. Medians
  are robust but hide the spread within each district. The asking-vs-sold gap reflects the
  current listing mix and should never be read as a discount on value. Sold data lags
  completion and registration by weeks. Days on market and stuck counts are a snapshot on each
  district's refresh date, not a continuous series. The figures describe city-centre flats and
  do not generalise to a whole city or to houses.</p></section>

  {_cite_this_section(canonical, ("/" + study["csv"]) if study.get("csv") else "",
                      "The UK City-Centre Property Index", study.get("generated_at", ""))}
  {_cta_block({'district': 'any UK address', 'city': {'name': 'the UK', 'slug': ''}}, 'foot')}
  {_ad_slot("study", "footer")}
  {_faq_section(faqs)}
  {_official_sources_section()}
  {_references_section(refs)}
</article>"""

    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc_meta}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc_meta}">
<meta property="og:url" content="{e(canonical)}">
<meta property="og:site_name" content="Honestly">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">{jsonld}</script>
{_fonts()}
<style>{_css()}
.findings li{{margin:.6em 0}}
.voice-grid{{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));margin:1.4em 0}}
.voice{{margin:0;background:#fff;border:1px solid var(--line);border-left:3px solid var(--green);
border-radius:11px;padding:16px 18px}}
.voice blockquote{{margin:0 0 .4em;font:italic 400 1.08rem/1.45 var(--serif);color:var(--ink)}}
.voice-reply{{margin:.4em 0;font-size:.92rem;color:var(--muted)}}
.voice-tag{{font-style:normal;font-size:.78rem}}
.voice figcaption{{font-size:.82rem;color:var(--muted);margin-top:.4em}}
.voice-tie{{font-size:.8rem;color:var(--green);margin:.5em 0 0;font-weight:600}}</style>
</head>
<body>
<div class="page-aura" aria-hidden="true"><span class="ab b1"></span><span class="ab b2"></span><span class="ab b3"></span></div>
{_masthead("UK City-Centre Index", _citynav(cities_nav))}
{body}
<footer class="site"><div class="wrap">
<p><strong>Honestly</strong> - a defensible value from sold evidence. The figures above are
{_study_authorities(study)} data and live listings, reported beside each other, never blended.
We issue no valuation on this page; we report what the market actually did.</p>
<p><a href="{e(BOT)}">Get a valuation on Telegram</a> &middot;
<a href="{e(BLOG_BASE)}/">All reports</a></p>
<p class="ernesta">A product by Ernesta Labs.</p>
</div></footer>
</body></html>"""


# ----------------------------------------------------------------- press fact-check (commentary)
def _commentary_url(city_slug):
    return f"{BLOG_BASE}/{city_slug}-market-commentary/"


def _topic_url(slug):
    return f"{BLOG_BASE}/{slug}/"


# Each verdict from press_review.clarify maps to a tone class. Deliberately NOT a red
# "false" - we add ground truth, we do not rate the journalism. Green = our record backs the
# claim's territory; gold = a divergence to weigh (caution, never an accusation); navy =
# honestly out of sold data's reach.
def _topic_jsonld(spec, canonical, desc, faqs):
    import json as _json
    org = {"@type": "Organization", "name": "Honestly", "url": SITE,
           "logo": {"@type": "ImageObject", "url": SITE + "/img/logo-icon.png"}}
    graph = [{"@type": "Article", "headline": spec.get("title") or spec.get("h1") or "",
              "description": desc, "url": canonical, "mainEntityOfPage": canonical,
              "author": org, "publisher": org, "inLanguage": "en-GB"}]
    if faqs:
        graph.append({"@type": "FAQPage",
                      "mainEntity": [{"@type": "Question", "name": q,
                                      "acceptedAnswer": {"@type": "Answer", "text": a}}
                                     for q, a in faqs]})
    graph.append({"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE},
        {"@type": "ListItem", "position": 2, "name": "Blog", "item": SITE + BLOG_BASE + "/"},
        {"@type": "ListItem", "position": 3, "name": spec.get("title") or spec.get("h1") or "Page",
         "item": canonical}]})
    return _json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)


def render_topic_page(spec, *, cities_nav=None, hero=None):
    """Render a topical analysis page (compare, alerts, friction, publication analysis).

    These are the blog's second-order pages: not district reports, but the editorial pages
    that explain how readers should think about the market and where to click next."""
    slug = spec.get("slug") or "topic"
    canonical = SITE + _topic_url(slug)
    title = spec.get("title") or spec.get("h1") or slug.replace("-", " ").title()
    h1 = spec.get("h1") or title
    kicker = spec.get("kicker") or "Market analysis"
    summary = spec.get("summary") or ""
    desc = meta_clip(summary)
    bullets = spec.get("bullets") or []
    steps = spec.get("steps") or []
    links = spec.get("links") or []
    faqs = spec.get("faqs") or []
    stats = spec.get("stats") or []
    if isinstance(hero, dict):
        hero = {**hero, "caption": title, "alt": title}
    jsonld = _topic_jsonld(spec, canonical, desc, faqs)

    def _cards(items):
        out = ""
        for item in items:
            if isinstance(item, dict):
                head = item.get("title") or item.get("label") or ""
                body = item.get("body") or item.get("text") or ""
            else:
                head, body = item if isinstance(item, tuple) and len(item) >= 2 else (str(item), "")
            out += f'<div class="aud"><h3>{e(head)}</h3><p>{e(body)}</p></div>'
        return out

    link_html = ""
    if links:
        lis = "".join(
            f'<li><a href="{e(it.get("url") if isinstance(it, dict) else it[1] if isinstance(it, tuple) and len(it) > 1 else it)}">'
            f'{e(it.get("label") if isinstance(it, dict) else it[0] if isinstance(it, tuple) and len(it) > 0 else it)}</a></li>'
            for it in links)
        link_html = f'<section><h2>Next steps</h2><ul class="links">{lis}</ul></section>'

    step_html = ""
    if steps:
        ol = "".join(f'<li>{e(s)}</li>' for s in steps)
        step_html = f'<section><h2>What to check first</h2><ol>{ol}</ol></section>'

    bullet_html = ""
    if bullets:
        bullet_html = f'<section><h2>What to check</h2><div class="aud-grid">{_cards(bullets)}</div></section>'

    cta = spec.get("cta") or []
    cta_html = ""
    if cta:
        buttons = []
        for btn in cta:
            if not isinstance(btn, dict):
                continue
            cls = btn.get("class") or "cta-ghost"
            rel_attr = ' rel="noopener"' if btn.get("rel") else ""
            buttons.append(f'<a class="cta {e(cls)}" href="{e(btn.get("url") or "#")}"'
                          f'{rel_attr}>{e(btn.get("label") or "Read more")}</a>')
        if buttons:
            lead = spec.get("cta_lead") or "Choose the next step that fits what you are trying to do."
            cta_html = f'<aside class="ctaband"><p>{e(lead)}</p><div class="cta-row">{"".join(buttons)}</div></aside>'

    body = f"""<article class="wrap">
  {_hero_figure(hero)}
  {_cover(f"{e(kicker)} &middot; {e(spec.get('series') or 'Market analysis')}",
          h1, summary, stats=stats)}
  {bullet_html}
  {step_html}
  {link_html}
  {_faq_section(faqs)}
  {cta_html}
  {_official_sources_section()}
</article>"""

    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} | Honestly</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:type" content="article">
<meta property="og:title" content="{e(title)} | Honestly">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canonical)}">
<meta property="og:site_name" content="Honestly">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">{jsonld}</script>
{_fonts()}
<style>{_css()}</style>
</head>
<body>
<div class="grain" aria-hidden="true"></div>
<div class="page-aura" aria-hidden="true"><span class="ab b1"></span><span class="ab b2"></span><span class="ab b3"></span></div>
{_masthead(spec.get('series') or 'Market analysis', _citynav(cities_nav))}
{body}
<footer class="site"><div class="wrap">
{_foot_brand()}
<p>{brand_name()} - compare homes and get a fast address value check on Telegram. <a href="{e(BOT)}">Get a valuation on Telegram</a>.</p>
</div></footer>
</body></html>"""


_VERDICT_CLASS = {
    "Grounded by the local record": "v-ground",
    "Broadly in line with the local record": "v-inline",
    "The local record differs": "v-differ",
    "Beyond what sold data can confirm": "v-beyond",
}


def _commentary_value(kind, val):
    """Format the snapshot figure for a clarification, by its unit. Never prints a number we
    do not hold (None -> the muted dash, as everywhere else on the network)."""
    if val is None:
        return NA
    if kind == "gbp":
        return money(val)
    if kind == "gbp_psm":
        return money(val) + "/m&sup2;"
    if kind == "days":
        return f"{int(round(val))} days"
    if kind == "pct":
        return pct(val)
    if kind == "count":
        try:
            return f"{int(round(float(val))):,}"
        except (TypeError, ValueError):
            return NA
    return NA


def _commentary_card(claim, cl):
    """One fact-check card: the source's claim recognised and cited (left), our local sold
    record set beside it (right). The outbound link to the article is rel='nofollow noopener'
    (it is someone else's page we are quoting, not an authority we are vouching for); the
    figure shown is always our own record, never the quoted number."""
    pub = e(claim.get("publisher") or "")
    title = e(claim.get("title") or "")
    url = e(claim.get("url") or "")
    date = e(claim.get("date") or "")
    quote = e(claim.get("quote") or "")
    topic = e(claim.get("topic") or "")
    cite_meta = pub + (f" &middot; {date}" if date else "")
    link = (f'<a class="pc-src" href="{url}" rel="nofollow noopener" target="_blank">'
            f'Read the original on {pub} &rarr;</a>') if url else ""
    topic_tag = f'<span class="pc-topic">{topic}</span>' if topic else ""
    vclass = _VERDICT_CLASS.get(cl.get("verdict"), "v-beyond")
    val_html = ""
    if cl.get("metric"):
        val_html = (f'<p class="pc-figure"><span class="pc-fval">'
                    f'{_commentary_value(cl.get("our_kind"), cl.get("our_value"))}</span>'
                    f'<span class="pc-flabel">{e(cl.get("label") or "")}</span></p>')
    return (
        f'<div class="pc-card">'
        f'<div class="pc-claim">{topic_tag}'
        f'<blockquote>{quote}</blockquote>'
        f'<figcaption>{cite_meta}</figcaption>{link}</div>'
        f'<div class="pc-check">'
        f'<span class="pc-verdict {vclass}">{e(cl.get("verdict") or "")}</span>'
        f'{val_html}'
        f'<p class="pc-sentence">{e(cl.get("sentence") or "")}</p></div>'
        f'</div>')


def _commentary_references(claims, authority):
    """References for the fact-check: every external article we quoted (rel='nofollow noopener'
    - a cited source, not an endorsed authority), then the official records our figures came
    from (follow links - vouching for the primary source is the authority signal we want).
    Built only from what is actually present, honest by construction."""
    art_lis, seen = "", set()
    for c in (claims or []):
        url = (c.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        pub = c.get("publisher") or ""
        title = c.get("title") or ""
        when = c.get("date") or f"Accessed {brand.DATESTR}"
        art_lis += (f'<li>{e(pub)}. {e(title)}. '
                    f'<a href="{e(url)}" rel="nofollow noopener" target="_blank">{e(url)}</a> '
                    f'({e(when)}).</li>')
    cites = getattr(brand, "_CITATIONS", {})
    off_lis = ""
    for cid in ("pd_sold", "pd_listings"):
        if cid in cites:
            pub, title, url = cites[cid]
            off_lis += (f'<li>{e(pub)}. {e(title)}. '
                        f'<a href="{e(url)}" rel="noopener" target="_blank">{e(url)}</a> '
                        f'(Accessed {brand.DATESTR}).</li>')
    if not (art_lis or off_lis):
        return ""
    parts = '<section id="references"><h2>References</h2>'
    if art_lis:
        parts += ('<p class="src-intro">The published claims on this page, cited in full. '
                  'Read the originals in context.</p>'
                  f'<ol class="refs">{art_lis}</ol>')
    if off_lis:
        parts += (f'<p class="src-intro">The local sold record and live listings used in the '
                  f'clarifications ({e(authority)}):</p>'
                  f'<ol class="refs">{off_lis}</ol>')
    return parts + '</section>'


def _commentary_jsonld(city_slug, name, title, desc, captured_at, claims, faqs):
    import json as _json
    url = SITE + _commentary_url(city_slug)
    org = {"@type": "Organization", "name": "Honestly", "url": SITE,
           "logo": {"@type": "ImageObject", "url": SITE + "/img/logo-icon.png"}}
    citation = [{"@type": "CreativeWork", "name": c.get("title") or c.get("publisher"),
                 "url": c.get("url"),
                 "publisher": {"@type": "Organization", "name": c.get("publisher")}}
                for c in (claims or []) if c.get("url")]
    article = {"@type": "Article", "headline": title, "description": desc,
               "url": url, "mainEntityOfPage": url,
               "author": org, "publisher": org, "inLanguage": "en-GB"}
    if captured_at:
        article["datePublished"] = captured_at
        article["dateModified"] = captured_at
    if citation:
        article["citation"] = citation
    graph = [article]
    if faqs:
        graph.append({"@type": "FAQPage",
                      "mainEntity": [{"@type": "Question", "name": q,
                                      "acceptedAnswer": {"@type": "Answer", "text": at}}
                                     for q, at in faqs]})
    graph.append({"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE},
        {"@type": "ListItem", "position": 2, "name": "Blog", "item": SITE + BLOG_BASE + "/"},
        {"@type": "ListItem", "position": 3, "name": f"{name} market commentary", "item": url}]})
    return _json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)


def _commentary_faqs(name, authority, n_districts):
    return [
        ("How are the claims checked?",
         f"Each published claim is set beside the local sold record and live listings for {name}. "
         f"The figures come from {authority} and live listings across the {n_districts} {name} "
         f"districts reported here - never from the quoted article."),
        (f"Is the source being called wrong?",
         "No. A claim can be right about a wider market while the local figure looks different. "
         "Both are shown so the gap is clear."),
        ("Where do the figures come from?",
         f"From {name}'s sold prices and current listings across the postcode districts reported "
         f"on this site. Not one quoted claim becomes a figure on this page."),
    ]


def _commentary_article(claims, snapshot, name, block):
    """Render the publication analysis as a written article, not a card grid.

    Each claim becomes a titled passage: the verbatim quote (cited and linked), the verdict
    chip with our own figure beside it, then the authored analysis paragraphs that set the
    claim against this city's recorded sold record. An opening lede and a closing synthesis
    (block-level authored prose) bracket the passages. Renders only the prose that was
    actually authored - every number in it was written at freeze time from the snapshot, so
    nothing here computes a figure. Returns "" if no authored prose exists (caller falls back
    to the card grid)."""
    import press_review
    intro = [p for p in (block.get("intro") or []) if p]
    synthesis = [p for p in (block.get("synthesis") or []) if p]
    has_analysis = any((c.get("analysis") or c.get("dek")) for c in (claims or []))
    if not (has_analysis or intro or synthesis):
        return ""

    lede = "".join(f'<p class="pca-lede-p">{e(p)}</p>' for p in intro)
    lede_html = f'<div class="pca-lede">{lede}</div>' if lede else ""

    items = ""
    for i, claim in enumerate(claims or [], 1):
        cl = press_review.clarify(claim, snapshot)
        pub = e(claim.get("publisher") or "")
        ctitle = e(claim.get("title") or "")
        url = e(claim.get("url") or "")
        date = e(claim.get("date") or "")
        quote = e(claim.get("quote") or "")
        topic = e(claim.get("topic") or "")
        dek = e(claim.get("dek") or (f"{claim.get('publisher','')}: {claim.get('topic','')}".strip(": ")))
        analysis = claim.get("analysis") or []
        cite_meta = pub + (f" &middot; {date}" if date else "")
        link = (f'<a class="pc-src" href="{url}" rel="nofollow noopener" target="_blank">'
                f'Read the original on {pub} &rarr;</a>') if url else ""
        vclass = _VERDICT_CLASS.get(cl.get("verdict"), "v-beyond")
        fig = ""
        if cl.get("metric"):
            fig = (f'<span class="pca-fig"><span class="pca-fig-v">'
                   f'{_commentary_value(cl.get("our_kind"), cl.get("our_value"))}</span> '
                   f'<span class="pca-fig-l">{e(cl.get("label") or "")}</span></span>')
        verdict_row = (f'<p class="pca-verdict"><span class="pc-verdict {vclass}">'
                       f'{e(cl.get("verdict") or "")}</span>{fig}</p>')
        # If the author wrote analysis, print it; otherwise fall back to the clarify sentence
        # so a not-yet-written claim still reads as a paragraph, not an empty section.
        paras = analysis if analysis else [cl.get("sentence") or ""]
        body = "".join(f'<p>{e(p)}</p>' for p in paras if p)
        topic_tag = f'<span class="pc-topic">{topic}</span>' if topic else ""
        items += (
            f'<section class="pca-item">'
            f'<h3 class="pca-h">{topic_tag}{dek}</h3>'
            f'<figure class="pca-quote"><blockquote>{quote}</blockquote>'
            f'<figcaption>{cite_meta}</figcaption>{link}</figure>'
            f'{verdict_row}'
            f'<div class="pca-analysis">{body}</div>'
            f'</section>')

    syn = "".join(f'<p>{e(p)}</p>' for p in synthesis)
    syn_html = (f'<section class="pca-synthesis"><h2>What the sold record says, in the round</h2>'
                f'{syn}</section>') if syn else ""

    return f'{lede_html}<div class="pca-stream">{items}</div>{syn_html}'


def render_commentary(city, snapshot, block, *, cities_nav=None, hero=None):
    """Render a city's "Headlines vs the data" fact-check: recent published newsletters,
    blog posts and articles about the city's property market, each recognised, cited and
    clarified against the city's OWN sold record. Mirrors the study's shell, palette and
    JSON-LD. Issues no valuation; quotes no figure - every number is the city's recorded
    sold/listing data via city_snapshot.

    Returns "" (renders nothing) unless we hold both a frozen claims block and a real snapshot
    (>=3 districts with a sold basis) - honest absence beats a thin or one-sided page."""
    import press_review
    if not (block and block.get("claims") and snapshot and snapshot.get("ok")):
        return ""
    city_slug = city["slug"]
    name = city["name"]
    country = snapshot.get("country") or city.get("country") or ""
    authority = _sold_authority_name(country)
    m = snapshot.get("metrics") or {}
    n = snapshot.get("n_districts") or 0
    as_of = snapshot.get("as_of") or block.get("captured_at") or brand.DATESTR
    canonical = SITE + _commentary_url(city_slug)
    title = f"{name} Property Market: the Headlines, Checked Against the Sold Record | Honestly"

    claims = block.get("claims") or []
    article = _commentary_article(claims, snapshot, name, block)
    cards = "" if article else "".join(
        _commentary_card(c, press_review.clarify(c, snapshot)) for c in claims)

    bits = []
    if m.get("sold_median") is not None:
        bits.append(f"a typical recorded sold median of {money(m['sold_median'])}")
    if m.get("psm") is not None:
        bits.append(f"about {money(m['psm'])} per square metre")
    if m.get("mean_dom") is not None:
        bits.append(f"homes taking around {int(round(m['mean_dom']))} days to sell")
    record_line = "; ".join(bits) if bits else "its recorded sold prices"
    tldr = (f"Recent headlines, newsletters and blog posts about {name}, checked against the "
            f"local sold record: across the {n} postcode districts reported here, {record_line} "
            f"({authority} data and live listings). No valuation, and no quoted figure appears on "
            f"this page as a local number.")
    desc_meta = meta_clip(tldr)

    faqs = _commentary_faqs(name, authority, n)
    jsonld = _commentary_jsonld(city_slug, name, title.replace("&", "&amp;"),
                                desc_meta, block.get("captured_at"), claims, faqs)

    kpis = []
    if m.get("sold_median") is not None:
        kpis.append((money_short(m["sold_median"]), "Typical sold median", f"across {n} districts"))
    if m.get("psm") is not None:
        kpis.append((money_short(m["psm"]), "Median price per m&sup2;", "recorded sales"))
    if m.get("mean_dom") is not None:
        kpis.append((str(int(round(m["mean_dom"]))), "Median days on market", "live listings"))
    kpis.append((str(len(claims)), "Claims checked", f"in {name}"))
    kpi_html = "".join(
        f'<div class="kpi"><div class="kpi-v">{v}</div>'
        f'<div class="kpi-l">{l}</div><div class="kpi-s">{s}</div></div>'
        for v, l, s in kpis)

    refs = _commentary_references(claims, authority)
    method = e(block.get("method") or "")
    disclaimer = e("These are other people's published claims, cited as such. They are checked against the recorded sold prices for this city's postcodes. National or regional commentary can be right about its own scope while the local figure looks different - both can be shown without declaring a winner. Not one quoted claim is a figure on this page; every number in the clarification is the city's own sold record.")
    src_label = e(block.get("source_label") or "Public reporting on the UK property market")

    body = f"""<article class="wrap">
  {_hero_figure(hero)}
  <header class="report-head">
    <div class="rh-body">
    <p class="kicker">A data fact-check by {brand_name()}</p>
    <h1>{e(name)} property market: the headlines, checked against the sold record</h1>
    <p class="dateline">{n} districts &middot; {len(claims)} claims checked &middot;
    Updated {e(as_of)}</p>
    <p class="standfirst">{e(tldr)}</p>
    </div>
  </header>
  {_ad_slot("commentary", "leaderboard")}

  <div class="kpis">{kpi_html}</div>

  <section id="checks"><h2>The headlines, beside the local record</h2>
  <p class="src-intro">{src_label}.</p>
  {article if article else (
    "<p>Each card recognises a published claim and links to the original, then sets it beside "
    + e(name) + "'s own recorded sold figure for the metric in question. The verdict tags add "
    "ground truth; they are not a score of the journalism.</p>"
    '<div class="pc-grid">' + cards + '</div>')}
  </section>

  {_ad_slot("commentary", "mid")}

  <section id="limits"><h2>What the sold record can and cannot settle</h2>
  <p>{disclaimer}</p>
  <p>These figures are medians across {n} {e(name)} postcode districts, so they are robust but
  not a full spread. Sold data lags completion and registration by weeks; days-on-market and
  stuck-stock counts are a snapshot on each district's refresh date. A forecast, sentiment read
  or policy effect is left as a reading, not a verdict.</p></section>

  {_cta_block({'district': name, 'city': city}, 'foot')}
  {_ad_slot("commentary", "footer")}
  {_faq_section(faqs)}
  {_official_sources_section()}
  {refs}
</article>"""

    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc_meta}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc_meta}">
<meta property="og:url" content="{e(canonical)}">
<meta property="og:site_name" content="Honestly">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">{jsonld}</script>
{_fonts()}
<style>{_css()}
.pc-grid{{display:grid;gap:18px;margin:1.4em 0}}
.pc-card{{display:grid;gap:0;grid-template-columns:1fr 1fr;background:#fff;border:1px solid var(--line);
border-radius:13px;overflow:hidden}}
@media(max-width:680px){{.pc-card{{grid-template-columns:1fr}}}}
.pc-claim{{padding:18px 20px;border-right:1px solid var(--line)}}
@media(max-width:680px){{.pc-claim{{border-right:none;border-bottom:1px solid var(--line)}}}}
.pc-claim blockquote{{margin:.2em 0 .5em;font:italic 400 1.08rem/1.45 var(--serif);color:var(--ink)}}
.pc-claim figcaption{{font-size:.82rem;color:var(--muted);font-weight:600}}
.pc-topic{{display:inline-block;font-size:.72rem;letter-spacing:.04em;text-transform:uppercase;
color:var(--green);font-weight:700;margin-bottom:.4em}}
.pc-src{{display:inline-block;margin-top:.6em;font-size:.85rem;color:var(--green);font-weight:600}}
.pc-check{{padding:18px 20px;background:var(--paper)}}
.pc-verdict{{display:inline-block;font-size:.74rem;letter-spacing:.03em;font-weight:700;
padding:.28em .7em;border-radius:999px;margin-bottom:.6em}}
.v-ground,.v-inline{{background:rgba(21,128,127,.12);color:var(--green)}}
.v-differ{{background:rgba(216,154,50,.16);color:#9a6a12}}
.v-beyond{{background:rgba(14,39,71,.08);color:var(--navy)}}
.pc-figure{{margin:.3em 0 .5em;display:flex;flex-direction:column}}
.pc-fval{{font:700 1.7rem/1 var(--serif);color:var(--navy)}}
.pc-flabel{{font-size:.8rem;color:var(--muted);margin-top:.2em}}
.pc-sentence{{margin:.4em 0 0;font-size:.94rem;color:var(--ink)}}
/* publication analysis - written article */
.pca-lede{{margin:1.2em 0 1.6em;max-width:42rem}}
.pca-lede-p{{font:400 1.18rem/1.62 var(--serif);color:var(--ink)}}
.pca-lede-p:first-child::first-letter{{float:left;font:700 3.1rem/.8 var(--serif);
color:var(--green);padding:.04em .12em 0 0}}
.pca-stream{{display:flex;flex-direction:column;gap:34px;margin:1.2em 0;max-width:42rem}}
.pca-item{{padding-top:26px;border-top:2px solid var(--line)}}
.pca-item:first-child{{border-top:none;padding-top:0}}
.pca-h{{font:700 1.32rem/1.3 var(--serif);color:var(--navy);margin:.1em 0 .55em}}
.pca-h .pc-topic{{display:block;margin-bottom:.3em}}
.pca-quote{{margin:0 0 .9em;padding:.2em 0 .2em 1.1em;border-left:3px solid var(--gold)}}
.pca-quote blockquote{{margin:0 0 .35em;font:italic 400 1.16rem/1.5 var(--serif);color:var(--ink)}}
.pca-quote figcaption{{font-size:.82rem;color:var(--muted);font-weight:600}}
.pca-verdict{{display:flex;align-items:baseline;flex-wrap:wrap;gap:.6em;margin:.2em 0 .8em}}
.pca-fig{{font-size:.92rem;color:var(--muted)}}
.pca-fig-v{{font:700 1.05rem/1 var(--serif);color:var(--navy)}}
.pca-analysis p{{margin:0 0 .85em;font:400 1.04rem/1.66 var(--sans);color:var(--ink)}}
.pca-synthesis{{margin:2em 0 1em;padding:24px 26px;background:var(--paper);
border:1px solid var(--line);border-radius:14px;max-width:42rem}}
.pca-synthesis h2{{margin:.1em 0 .5em}}
.pca-synthesis p{{margin:0 0 .8em;font:400 1.05rem/1.64 var(--sans);color:var(--ink)}}</style>
</head>
<body>
<div class="grain" aria-hidden="true"></div>
<div class="page-aura" aria-hidden="true"><span class="ab b1"></span><span class="ab b2"></span><span class="ab b3"></span></div>
{_masthead(city.get('series', name + ' property market'), _citynav(cities_nav, active_city=city_slug))}
{body}
<footer class="site"><div class="wrap">
<p><strong>Honestly</strong> - a defensible value from sold evidence. The claims above are public
reporting, cited as such; every figure in the clarification is {e(name)}'s own {e(authority)} sold
record and live listings, never blended and never a valuation.</p>
<p><a href="{e(BOT)}">Get a valuation on Telegram</a> &middot;
<a href="{e(hub_url(city_slug))}">All {e(name)} reports</a> &middot;
<a href="{e(BLOG_BASE)}/">All reports</a></p>
<p class="ernesta">A product by Ernesta Labs.</p>
</div></footer>
</body></html>"""


# ----------------------------------------------------------------- sitemap + rss
def build_sitemap(urls):
    """urls: list of (loc_path, lastmod) - loc_path is site-relative or absolute."""
    items = ""
    for loc, lastmod in urls:
        full = loc if loc.startswith("http") else SITE + loc
        items += (f"<url><loc>{e(full)}</loc>"
                  + (f"<lastmod>{e(lastmod)}</lastmod>" if lastmod else "")
                  + "<changefreq>daily</changefreq></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + items + "</urlset>")


def build_rss(items):
    """items: list of dicts {title, slug, description, date}. Newest first."""
    entries = ""
    for it in items:
        link = SITE + post_url(it["slug"])
        entries += (f"<item><title>{e(it['title'])}</title>"
                    f"<link>{e(link)}</link><guid>{e(link)}</guid>"
                    f"<description>{e(it.get('description',''))}</description>"
                    f"<pubDate>{e(it.get('date',''))}</pubDate></item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<rss version="2.0"><channel>'
            '<title>Honestly - UK postcode property market reports</title>'
            f'<link>{SITE}{BLOG_BASE}/</link>'
            '<description>Daily property market intelligence for UK postcode districts.</description>'
            + entries + "</channel></rss>")


# ----------------------------------------------------------------- CLI
def main():
    import sys, json as _json
    if len(sys.argv) >= 3 and sys.argv[1] == "render":
        # render a cached model JSON to an HTML file: blog.py render _se15_model.json out.html
        model = _json.load(open(sys.argv[2], encoding="utf-8"))
        import cities
        city = cities.CITY_BY_SLUG.get(model["city"]["slug"])
        sibs = [(dist, cities.slug_for(city["slug"], dist))
                for dist in (city["districts"] if city else []) if dist != model["district"]][:8]
        html_out = render_post(model, siblings=sibs, cities_nav=cities.CITIES)
        outp = sys.argv[3] if len(sys.argv) > 3 else "blog_preview.html"
        open(outp, "w", encoding="utf-8").write(html_out)
        print(f"wrote {outp} ({len(html_out):,} bytes)")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
