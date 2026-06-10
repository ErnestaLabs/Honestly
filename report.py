#!/usr/bin/env python3
"""report.py - the paid deliverable as a real, detailed PDF (not a picture of one).

Pure-Python via fpdf2: no browser, no matplotlib, no system libraries - so it runs
on the memory-constrained Linux VPS exactly as it does on a dev box. Renders a
branded, multi-section market appraisal straight from the engine result:

  * branded header + assessed-range hero
  * the property on record
  * comparable evidence table - every row a CLICKABLE HM Land Registry record
  * a natively-drawn comps-vs-assessed-range bar chart (no image dependency)
  * valuation basis (Tier A median, condition-adjusted AVM, GBP/sqm cross-check,
    then a bounded live-market adjustment)
  * live competitive positioning
  * net proceeds
  * methodology, limitations, sources, and the honesty footer

Companion to appraise.interactive_chart() (the self-contained HTML the PDF points to).
Numbers come from engine.summary()/valuation so the PDF can never drift from the
bot card or the Mini App. Sold evidence anchors the value; the live market steers it.

  build(r, audience, outdir, slug, agent, bot_url) -> pdf_path
"""
import os, statistics
from fpdf import FPDF, XPos, YPos
import engine
from appraise import (money, round_to, txn_link, postcode_of, DATESTR,
                      interactive_chart)

# Best-effort Reddit market intelligence (optional dependency)
try:
    import reddit_intel as _reddit_intel
    _HAS_REDDIT = True
except ImportError:
    _HAS_REDDIT = False

# brand palette (mirrors appraise.py / the interactive chart) -----------------
GREEN  = (31, 111, 92)    # #1f6f5c
DARK   = (20, 63, 51)     # #143f33  headings
TERRA  = (185, 98, 58)    # #b9623a  recommended guide marker
SAND   = (201, 193, 173)  # #c9c1ad
CREAM  = (246, 243, 236)  # panel fill
INK    = (28, 26, 22)
MUTED  = (107, 101, 87)
LINE   = (231, 225, 212)
LINK   = (31, 111, 92)
PALE   = (236, 242, 239)  # very light green band fill

PW = 210.0   # A4 width mm
ML = 16.0    # left/right margin
CW = PW - 2 * ML  # content width

_SUBST = {'–': '-', '—': '-', '‒': '-', '−': '-',
          '→': 'to', '←': '<-', '•': '-', '·': '-',
          '≈': '~', '‘': "'", '’': "'", '“': '"',
          '”': '"', '…': '...', ' ': ' ', ' ': ' ',
          '✕': 'x', '✓': 'ok'}

def T(s):
    """Core PDF fonts speak cp1252. Map the few typographic glyphs we emit to plain
    equivalents (and never an em dash - house style), then drop anything else safely.
    The pound sign survives; only exotic glyphs are touched."""
    s = str(s)
    for k, v in _SUBST.items():
        s = s.replace(k, v)
    return s.encode('cp1252', 'replace').decode('cp1252')


# ---- Reddit market intelligence (best-effort PDF section) -------------------
_REDDIT_CACHE = {}  # postcode -> intel dict, survives for the process lifetime


def _render_reddit_intel(pdf, subject):
    """Add a Reddit market intelligence page to the PDF - best-effort only.

    Fetches recent Reddit chatter for the property's postcode area, showing
    local sentiment and discussion themes. Never blocks the report; silently
    skipped if unavailable.
    """
    if not _HAS_REDDIT:
        return
    addr = subject.get("address") or ""
    pc = postcode_of(addr)
    if not pc:
        return
    area = pc.split()[0] if pc else pc  # postcode district (e.g. SE15)

    # Check cache first
    intel = _REDDIT_CACHE.get(area)
    if intel is None:
        try:
            intel = _reddit_intel.for_area(area, audience="agent", postcode=pc)
            _REDDIT_CACHE[area] = intel if intel else {}
        except Exception:
            return
    if not intel or not intel.get("threads"):
        return

    if pdf.get_y() > 225:
        pdf.add_page()
    pdf.h2("Market intelligence from Reddit")
    pdf.body(
        "What people are saying about the local market online. These are real discussions "
        "from UK property subreddits - buyer experiences, seller frustrations, agent "
        "complaints, and market sentiment. Sits beside the hard sold-evidence numbers "
        "as context, not a valuation input.")

    # Sentiment indicator
    sent = intel.get("sentiment", "neutral")
    sent_map = {"supportive": "Positive / hopeful", "cautious": "Cautious / concerned",
                "mixed": "Mixed"}
    sent_label = sent_map.get(sent, "Neutral")
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(*DARK)
    pdf.cell(0, 6, T(f"Local sentiment: {sent_label}"),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Key themes
    themes = intel.get("themes", [])
    if themes:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 5, T("Key themes: " + " | ".join(themes)),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(2)

    # Thread cards
    for t in intel.get("threads", [])[:4]:
        title = t.get("title", "")
        sub = t.get("subreddit", "")
        quote = t.get("quote", "")
        url = t.get("url", "")

        if pdf.get_y() > 255:
            pdf.add_page()

        # Subreddit badge
        pdf.set_fill_color(*GREEN)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 7.5)
        pdf.cell(28, 5.5, T(f"  r/{sub}"), fill=True)
        pdf.ln(6.5)

        # Title (clickable link)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*DARK)
        if url:
            pdf.cell(CW, 5, T(title), link=url,
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(CW, 5, T(title),
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Quote excerpt
        if quote:
            excerpt = quote[:250].rsplit(" ", 1)[0] + ("..." if len(quote) > 250 else "")
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(*MUTED)
            pdf.multi_cell(CW, 4, T(f'"{excerpt}"'),
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.ln(2.5)

    pdf.ln(1)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 4, T("Reddit sentiment for additional context only - not a valuation input. "
                     "Sourced from UK property subreddits (r/HousingUK, r/PropertyUK)."),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)


_SCHOOLS_CACHE = {}  # postcode -> [schools], survives for the process lifetime


def _render_schools(pdf, s, key):
    """Nearest schools with phase, distance and an OFFICIAL Ofsted report link.
    Best-effort: from PropertyData's schools endpoint (same key). We never assert a
    rating - we link the reader to the public Ofsted page to verify at source. Silent
    if unavailable; never blocks the report."""
    if not key:
        return
    try:
        import products as _products
    except Exception:
        return
    pc = postcode_of(s.get("address", "")) or ""
    schools = _SCHOOLS_CACHE.get(pc)
    if schools is None:
        try:
            schools = _products.nearby_schools({"subject": s}, key, n=6)
        except Exception:
            schools = []
        _SCHOOLS_CACHE[pc] = schools
    if not schools:
        return

    if pdf.get_y() > 225:
        pdf.add_page()
    pdf.h2("Schools nearby")
    pdf.body(
        "The nearest schools to the property, by distance. We show what the public record "
        "states and link each school to its official Ofsted report - we do not assert a "
        "rating ourselves; verify it at source. School proximity is area context, not a "
        "valuation input.")
    for sc in schools[:6]:
        y = pdf.get_y()
        if y > 258:
            pdf.add_page(); y = pdf.get_y()
        pdf.set_fill_color(*CREAM)
        pdf.rect(ML, y, CW, 7, 'F')
        pdf.set_xy(ML + 3, y)
        pdf.set_font('Helvetica', 'B', 9.5); pdf.set_text_color(*DARK)
        meta = []
        if sc.get("phase"):    meta.append(sc["phase"])
        if sc.get("distance") is not None: meta.append(f"{sc['distance']:.1f} mi")
        if sc.get("pupils"):   meta.append(f"{sc['pupils']} pupils")
        pdf.cell(CW - 34, 7, T(sc["name"]), align='L')
        pdf.set_xy(ML + 3, y)
        pdf.set_font('Helvetica', '', 8.3); pdf.set_text_color(*MUTED)
        pdf.cell(CW - 34, 11.5, T("  -  ".join(meta)), align='L')
        if sc.get("ofsted_url"):
            pdf.set_xy(ML + CW - 34, y)
            pdf.set_font('Helvetica', 'U', 8.3); pdf.set_text_color(*LINK)
            pdf.cell(31, 7, T("Ofsted report"), align='R', link=sc["ofsted_url"])
        pdf.ln(8)
    pdf.ln(2)


def _render_material_information(pdf, s, v):
    """NTSELAT Material Information starter - Parts A, B and C.

    Renders the facts we hold from the public record, and flags every remaining
    required field as 'Confirm with seller'. Honest by design: we never invent a
    field we do not have. An agent can lift Part A straight into a listing; the
    blanks are the seller's disclosure homework, surfaced before they go to market.
    Reference: NTSELAT Material Information in Property Listings, Parts A/B/C."""
    if pdf.get_y() > 210:
        pdf.add_page()
    pdf.h2("Material information (NTSELAT)")
    pdf.body(
        "National Trading Standards (NTSELAT) requires defined material information on every "
        "UK property listing. This is a starting checklist: the facts we can evidence from the "
        "public record, and the items a seller or agent must confirm before marketing. Blanks "
        "are to verify - never guessed.")

    def _row(label, value, i):
        y = pdf.get_y()
        if y > 260:
            pdf.add_page(); y = pdf.get_y()
        pdf.set_fill_color(*(CREAM if i % 2 == 0 else (255, 255, 255)))
        pdf.rect(ML, y, CW, 7, 'F')
        known = value not in (None, '', '-')
        pdf.set_xy(ML + 3, y)
        pdf.set_font('Helvetica', '', 9.5); pdf.set_text_color(*INK)
        pdf.cell(CW - 70, 7, T(label), align='L')
        pdf.set_font('Helvetica', 'B' if known else 'I', 9.5)
        pdf.set_text_color(*(DARK if known else MUTED))
        pdf.cell(67, 7, T(value if known else "Confirm with seller"), align='R')
        pdf.ln(7)

    lease = (s['leases'][0].get('term') if s.get('leases') else None)
    area = (f"{s['sqft']} sqft" if s.get('sqft')
            else (f"{s.get('sqm')} sqm" if s.get('sqm') else None))
    rows = [
        ("Part A - Tenure", lease),
        ("Part A - Council tax band", s.get('tax')),
        ("Part A - Price (assessed central value)", money(v['central'])),
        ("Part B - Property type", (s.get('type') or '').strip() or None),
        ("Part B - Internal floor area", area),
        ("Part B - EPC", (f"score {s['epc']}" if s.get('epc') else None)),
        ("Part B - Construction", s.get('construction')),
        ("Part B - Utilities (gas / electric / water / sewerage)", None),
        ("Part B - Broadband & mobile coverage", None),
        ("Part B - Parking", None),
        ("Part C - Flood risk", None),
        ("Part C - Building safety / cladding", None),
        ("Part C - Rights, restrictions & easements", None),
    ]
    for i, (k, val_) in enumerate(rows):
        _row(k, val_, i)
    pdf.ln(2)
    pdf.set_font('Helvetica', 'I', 8.5); pdf.set_text_color(*MUTED)
    pdf.multi_cell(CW, 4.5, T(
        "Parts A, B and C as defined by NTSELAT. Honestly populates what the public record "
        "supports; the remaining fields require seller disclosure. This is not legal advice."),
        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)


class Report(FPDF):
    def __init__(self, agent, bot_url):
        super().__init__('P', 'mm', 'A4')
        self.agent = agent
        self.bot_url = bot_url
        self.set_auto_page_break(True, margin=18)
        self.set_margins(ML, 14, ML)

    def header(self):
        if self.page_no() == 1:
            return
        self.set_y(8)
        self.set_font('Times', 'B', 11)
        self.set_text_color(*DARK)
        self.cell(0, 6, T('Honestly'), align='L')
        self.set_font('Helvetica', '', 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, T('Market appraisal  -  ' + DATESTR), align='R',
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*LINE); self.set_line_width(0.3)
        self.line(ML, 16, PW - ML, 16)
        self.set_y(22)

    def footer(self):
        self.set_y(-13)
        self.set_draw_color(*LINE); self.set_line_width(0.3)
        self.line(ML, self.get_y(), PW - ML, self.get_y())
        self.set_y(-11)
        self.set_font('Helvetica', '', 7.5)
        self.set_text_color(*MUTED)
        self.cell(0, 5, T('Anchored in HM Land Registry sold evidence (via PropertyData), '
                          'steered for live market conditions.'), align='L')
        self.cell(0, 5, T(f'Page {self.page_no()}'), align='R')

    # -- helpers ------------------------------------------------------------
    def h2(self, txt):
        self.ln(2)
        self.set_font('Times', 'B', 14)
        self.set_text_color(*DARK)
        self.cell(0, 8, T(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*GREEN); self.set_line_width(0.5)
        y = self.get_y() + 0.5
        self.line(ML, y, ML + 26, y)
        self.ln(3)

    def body(self, txt, h=5.0, size=10):
        self.set_font('Helvetica', '', size)
        self.set_text_color(*INK)
        self.multi_cell(CW, h, T(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def kv_panel(self, rows):
        """A soft-filled panel of label / value pairs (the hero facts)."""
        self.set_draw_color(*LINE); self.set_fill_color(*CREAM)
        top = self.get_y()
        rh = 8.0
        self.rect(ML, top, CW, rh * len(rows), 'DF')
        for i, (k, v, big) in enumerate(rows):
            y = top + i * rh
            self.set_xy(ML + 4, y)
            self.set_font('Helvetica', '', 9.5)
            self.set_text_color(*MUTED)
            self.cell(58, rh, T(k), align='L')
            self.set_xy(ML + 62, y)
            if big:
                self.set_font('Times', 'B', 13); self.set_text_color(*DARK)
            else:
                self.set_font('Helvetica', 'B', 10.5); self.set_text_color(*INK)
            self.cell(CW - 66, rh, T(v), align='L')
            if i:
                self.set_draw_color(*LINE)
                self.line(ML + 2, y, ML + CW - 2, y)
        self.set_xy(ML, top + rh * len(rows))
        self.ln(4)


# -- the comparable-evidence table -------------------------------------------
EV_COLS = [('Comparable', 60, 'L'), ('Size', 18, 'R'), ('Sold', 26, 'R'),
           ('When', 22, 'C'), ('GBP/sqm', 22, 'R'), ('Dist', 16, 'R'),
           ('Verify', 0, 'C')]

def _ev_header(pdf):
    pdf.set_font('Helvetica', 'B', 8.5)
    pdf.set_fill_color(*DARK); pdf.set_text_color(255, 255, 255)
    x = ML
    for name, w, align in EV_COLS:
        ww = w if w else (ML + CW - x)
        pdf.set_xy(x, pdf.get_y())
        pdf.cell(ww, 7, T(name), align=align, fill=True)
        x += ww
    pdf.ln(7)

def _ev_table(pdf, rows):
    _ev_header(pdf)
    fill = False
    pdf.set_font('Helvetica', '', 8.5)
    for r in rows:
        if pdf.get_y() > 262:                 # leave room for footer
            pdf.add_page(); _ev_header(pdf)
            pdf.set_font('Helvetica', '', 8.5)
        y = pdf.get_y()
        pdf.set_fill_color(*(CREAM if fill else (255, 255, 255)))
        pdf.rect(ML, y, CW, 6.4, 'F')
        addr = r['address'].split(',')[0]
        cells = [(addr, 60, 'L'), (f"{r['sqm']} sqm", 18, 'R'),
                 (money(r['price']), 26, 'R'), (r['date'][:7], 22, 'C'),
                 (f"£{r['psm']:,}", 22, 'R'),
                 (f"{r['dist']} mi" if r.get('dist') is not None else '-', 16, 'R')]
        x = ML
        pdf.set_text_color(*INK)
        for txt, w, align in cells:
            pdf.set_xy(x, y)
            pdf.set_font('Helvetica', '', 8.3)
            pdf.cell(w, 6.4, T(txt), align=align)
            x += w
        # clickable verify cell
        vw = ML + CW - x
        pdf.set_xy(x, y)
        pdf.set_font('Helvetica', 'U', 8.3); pdf.set_text_color(*LINK)
        pdf.cell(vw, 6.4, T('record'), align='C', link=txn_link(r))
        pdf.set_text_color(*INK)
        pdf.ln(6.4)
        fill = not fill


# -- the native bar chart (no image, drawn with rects) ------------------------
def _bar_chart(pdf, rows, val):
    """Horizontal bars: one per comparable, with the assessed range as a shaded
    band and the central value as a line - so a reader sees at a glance which sold
    comparables sit inside, above or below the assessed range."""
    if not rows:
        return
    label_w = 52.0
    x0 = ML + label_w
    plot_w = CW - label_w - 24      # room for the value label on the right
    rowh = 6.2
    top = pdf.get_y() + 2
    prices = [r['price'] for r in rows]
    pmin = min(prices + [val['low']]) * 0.96
    pmax = max(prices + [val['high']]) * 1.02
    span = (pmax - pmin) or 1.0
    def X(v): return x0 + plot_w * ((v - pmin) / span)
    chart_h = rowh * len(rows)
    # assessed-range band
    pdf.set_fill_color(*PALE)
    pdf.rect(X(val['low']), top, X(val['high']) - X(val['low']), chart_h, 'F')
    # bars
    for i, r in enumerate(rows):
        y = top + i * rowh
        pdf.set_font('Helvetica', '', 7.6); pdf.set_text_color(*INK)
        pdf.set_xy(ML, y - 0.3)
        lab = r['address'].split(',')[0]
        while pdf.get_string_width(lab) > label_w - 3 and len(lab) > 6:
            lab = lab[:-2]
        pdf.cell(label_w - 2, rowh, T(lab), align='L')
        pdf.set_fill_color(*GREEN)
        bw = max(0.6, X(r['price']) - x0)
        pdf.rect(x0, y + 1.0, bw, rowh - 2.0, 'F')
        pdf.set_font('Helvetica', '', 7.4); pdf.set_text_color(*MUTED)
        pdf.set_xy(X(r['price']) + 1.5, y - 0.3)
        pdf.cell(22, rowh, T(money(r['price'])), align='L')
    # central line + guide line
    pdf.set_draw_color(*GREEN); pdf.set_line_width(0.5)
    pdf.line(X(val['central']), top - 1.5, X(val['central']), top + chart_h + 1.5)
    pdf.set_draw_color(*TERRA); pdf.set_line_width(0.5)
    gx = X(val['guide']) if pmin <= val['guide'] <= pmax else x0
    pdf.set_dash_pattern(dash=1.2, gap=1.2)
    pdf.line(gx, top, gx, top + chart_h)
    pdf.set_dash_pattern()                       # back to solid
    pdf.set_xy(ML, top + chart_h + 1)
    pdf.ln(rowh)
    # legend
    pdf.set_font('Helvetica', '', 7.6); pdf.set_text_color(*MUTED)
    pdf.set_x(ML)
    pdf.set_fill_color(*GREEN); pdf.rect(ML, pdf.get_y() + 1, 3, 3, 'F')
    pdf.set_xy(ML + 4, pdf.get_y())
    pdf.cell(34, 5, T('Sold comparable'))
    pdf.set_fill_color(*PALE); pdf.rect(pdf.get_x(), pdf.get_y() + 1, 3, 3, 'DF')
    pdf.set_x(pdf.get_x() + 4); pdf.cell(30, 5, T('Assessed range'))
    pdf.set_draw_color(*GREEN); pdf.set_line_width(0.5)
    yy = pdf.get_y() + 2.5; pdf.line(pdf.get_x(), yy, pdf.get_x() + 3, yy)
    pdf.set_x(pdf.get_x() + 4); pdf.cell(28, 5, T('Central value'))
    pdf.set_draw_color(*TERRA)
    yy = pdf.get_y() + 2.5; pdf.line(pdf.get_x(), yy, pdf.get_x() + 3, yy)
    pdf.set_x(pdf.get_x() + 4); pdf.cell(34, 5, T('Recommended guide'))
    pdf.ln(8)


# -- main ---------------------------------------------------------------------
def build(r, audience, outdir=None, slug=None, agent="Honestly",
          bot_url=None, interactive=True, key=None):
    """Render the detailed PDF. Returns (pdf_path, html_path). When interactive is
    True the companion interactive HTML is built alongside (same data) and the PDF
    points the reader to it; when False (a PDF-only tier) the HTML is not built and
    the PDF makes no claim about an attached chart - so the two never disagree."""
    outdir = outdir or os.path.dirname(os.path.abspath(__file__))
    bot_url = bot_url or os.environ.get("HONESTLY_BOT_URL", "https://t.me/usehonestly_bot")
    key = key or os.environ.get("PROPERTYDATA_KEY")
    slug = slug or "report"
    s, v, pos = r["subject"], r["valuation"], r["positioning"]
    d = engine.summary(r, audience, n=4)        # audience-framed guide, same numbers

    # nearest comparables drive the table + chart (closest = firmest evidence)
    allc = r["compsA"]
    nearest = sorted(allc, key=lambda c: (c.get("dist") if c.get("dist") is not None else 9,
                                          -c["price"]))
    table_rows = nearest[:14]
    chart_rows = nearest[:12]
    A_med = round_to(statistics.median([c["price"] for c in allc]), 1000)

    pdf = Report(agent, bot_url)
    pdf.add_page()

    # ---- masthead -------------------------------------------------------
    pdf.set_fill_color(*DARK)
    pdf.rect(0, 0, PW, 30, 'F')
    pdf.set_xy(ML, 8)
    pdf.set_font('Times', 'B', 22); pdf.set_text_color(255, 255, 255)
    pdf.cell(60, 9, T('Honestly'))
    pdf.set_font('Helvetica', '', 9.5); pdf.set_text_color(*SAND)
    pdf.set_xy(ML, 18)
    pdf.cell(0, 5, T("a defensible value: sold evidence, steered by the live market"))
    pdf.set_xy(ML, 8)
    pdf.set_font('Helvetica', '', 9); pdf.set_text_color(*SAND)
    pdf.cell(CW, 6, T(DATESTR), align='R')
    pdf.set_xy(ML, 14)
    pdf.set_font('Helvetica', 'B', 9); pdf.set_text_color(255, 255, 255)
    pdf.cell(CW, 6, T('Market Appraisal'), align='R')
    pdf.set_y(36)

    # ---- subject + hero -------------------------------------------------
    pdf.set_font('Times', 'B', 16); pdf.set_text_color(*INK)
    pdf.multi_cell(CW, 7, T(d['address']), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    facts = []
    if s.get('sqm'):  facts.append(f"{s['sqm']} sqm")
    if d.get('beds'): facts.append(f"{d['beds']} bed")
    if s.get('epc'):  facts.append(f"EPC {s['epc']}")
    if s.get('tax'):  facts.append(f"Council Tax {s['tax']}")
    facts.append(f"{len(allc)} sold comparables analysed")
    pdf.set_font('Helvetica', '', 9.5); pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, T("  -  ".join(facts)), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    inv = "Investment property (CGT applies)" if s.get('investment') else "Primary residence"
    hero = [("Assessed value range", f"{money(v['low'])} - {money(v['high'])}", True),
            ("Central value", f"~ {money(v['central'])}", False),
            (d['guide_label'], d['guide_value_str'], True)]
    if s.get('last_sold'):
        hero.append(("Last recorded sale",
                     f"{money(s['last_sold'])}  ({s.get('last_sold_date','')})", False))
    hero.append(("Held as", inv, False))
    pdf.kv_panel(hero)

    # ---- executive summary ---------------------------------------------
    pdf.h2("Executive summary")
    lo_c, hi_c = min(c['price'] for c in allc), max(c['price'] for c in allc)
    rtype = (s.get('type') or 'property').strip() or 'property'
    pdf.body(
        f"This appraisal values {d['address']} at {money(v['low'])} to {money(v['high'])}, "
        f"with a central figure of about {money(v['central'])}. The {d.get('beds') or '-'}-bedroom "
        f"{rtype} of approximately {s.get('sqm','-')} sqm sits within a comparable price tier of "
        f"{money(lo_c)} to {money(hi_c)}, set by {len(allc)} same-size, same-character properties "
        f"that actually sold near it. The recommended position is {d['guide_value_str']}.")
    if audience == "buyer":
        pdf.body("This figure is grounded in what comparable homes actually sold for and steered by "
                 "what the live market is doing now - not what a seller hopes to achieve. Every "
                 "comparable below links to its free public record so you can check it before you offer.")
    elif audience == "vendor":
        pdf.body("No one can name an exact figure - a home is worth what a buyer will pay. This is "
                 "the value the sold evidence defends: the number a buyer's signature supports, not "
                 "the highest figure an agent can quote to win your instruction.")
    if d.get("verdict"):
        pdf.set_font('Helvetica', 'B', 9.5)
        pdf.set_text_color(*(TERRA if d['verdict']['tone'] == 'warn' else GREEN))
        pdf.multi_cell(CW, 5, T(("! " if d['verdict']['tone'] == 'warn' else "ok  ")
                                + d['verdict']['text']),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1)

    # ---- the property ---------------------------------------------------
    pdf.h2("The property on record")
    lease = (s['leases'][0].get('term') if s.get('leases') else None) or 'see register'
    parts = []
    if s.get('sqft'): parts.append(f"Recorded internal area {s['sqft']} sqft ({s.get('sqm','-')} sqm)")
    elif s.get('sqm'): parts.append(f"Estimated internal area {s['sqm']} sqm")
    if s.get('epc'):   parts.append(f"EPC score {s['epc']}")
    if s.get('tax'):   parts.append(f"Council Tax Band {s['tax']}")
    if s.get('construction'): parts.append(f"construction {s['construction']}")
    parts.append(f"tenure {lease}")
    line = ".  ".join(parts) + "."
    if s.get('last_sold'):
        line += f"  Last sold {money(s['last_sold'])} on {s.get('last_sold_date','')}."
    pdf.body(line)

    # ---- material information (NTSELAT compliance starter) --------------
    _render_material_information(pdf, s, v)

    # ---- schools nearby (Ofsted, best-effort) --------------------------
    _render_schools(pdf, s, key)

    # ---- comparable evidence -------------------------------------------
    pdf.h2("Comparable evidence (sold)")
    pdf.body("Same-size, same-character properties sold near the subject, from HM Land Registry "
             "Price Paid Data via PropertyData. The closest comparables are shown; each 'record' "
             "link opens the free public transaction - the exact sale, the property and its "
             "photographs. Verify every figure yourself.")
    _ev_table(pdf, table_rows)
    pdf.ln(1)
    pdf.set_font('Helvetica', 'I', 8.5); pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, T(f"Showing the {len(table_rows)} closest of {len(allc)} comparables analysed. "
                     f"Tier A median {money(A_med)}."),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    # ---- chart ----------------------------------------------------------
    if pdf.get_y() > 215:
        pdf.add_page()
    pdf.h2("Where the comparables sit")
    _bar_chart(pdf, chart_rows, v)

    # ---- valuation basis ------------------------------------------------
    if pdf.get_y() > 225:
        pdf.add_page()
    pdf.h2("Basis of assessment")
    basis = [("Tier A comparable median", money(A_med))]
    for fq in ('average', 'high', 'very_high'):
        if v['avm'].get(fq):
            basis.append((f"Condition-adjusted valuation, {fq.replace('_',' ')} finish",
                          money(v['avm'][fq])))
    if v.get('crosscheck') and v.get('psmA'):
        basis.append((f"GBP/sqm cross-check (£{int(v['psmA']):,} x {s.get('sqm','-')} sqm)",
                      money(v['crosscheck'])))
    mk = v.get('market') or {}
    if v.get('sold_anchor'):
        basis.append(("Sold-anchored value (evidence + AVM)", money(v['sold_anchor'])))
    if mk.get('pct'):
        sign = '+' if mk['pct'] > 0 else ''
        basis.append((f"Live-market adjustment ({mk.get('label','')})", f"{sign}{mk['pct']}%"))
        basis.append(("Assessed central value", money(v['central'])))
    # render as a light two-column table
    pdf.set_draw_color(*LINE)
    for i, (k, val_) in enumerate(basis):
        y = pdf.get_y()
        pdf.set_fill_color(*(CREAM if i % 2 == 0 else (255, 255, 255)))
        pdf.rect(ML, y, CW, 7, 'F')
        pdf.set_xy(ML + 3, y); pdf.set_font('Helvetica', '', 9.5); pdf.set_text_color(*INK)
        pdf.cell(CW - 45, 7, T(k), align='L')
        pdf.set_font('Helvetica', 'B', 10); pdf.set_text_color(*DARK)
        pdf.cell(40, 7, T(val_), align='R')
        pdf.ln(7)
    pdf.ln(2)
    lead = (f"Comparable sold evidence and the condition-adjusted valuation anchor the value; "
            f"the live market then steers it. ")
    if mk.get('note'):
        lead += mk['note'] + " "
    pdf.body(lead + f"The result is an assessed range of {money(v['low'])} to {money(v['high'])}, "
             f"central about {money(v['central'])}. Confidence is moderate; see Limitations.")

    # ---- positioning ----------------------------------------------------
    if pos and pos.get('band'):
        if pdf.get_y() > 210:
            pdf.add_page()
        pdf.h2("Live market & competitive positioning")
        pdf.body(
            f"Sold prices anchor the value; this live band is how we steer it for current "
            f"conditions. Across the district {len(pos['band'])} comparable homes are "
            f"currently listed at {money(pos['lo_p'])} to {money(pos['hi_p'])}, median asking "
            f"{money(pos['median'])}, average {pos['mean_dom']} days on the market. Asking prices "
            f"signal vendor hope, not achieved value, so they inform the market steer and the "
            f"positioning here - they never set the figure on their own.")
        if pos.get('stuck'):
            pdf.body(
                f"{len(pos['stuck'])} of those listings have sat unsold for 90 days or more. In "
                f"this district an over-ambitious asking price does not win a higher sale - it "
                f"produces a longer, costlier one. The recommended {d['guide_value_str']} is set "
                f"toward the lower end of the live band, anchored to sold evidence, to draw "
                f"viewings and competing offers rather than join the stalled listings above.")

    # ---- forward market outlook ----------------------------------------
    mc = d.get('macro')
    if mc:
        if pdf.get_y() > 225:
            pdf.add_page()
        pdf.h2("Market outlook")
        pdf.body(
            "These are the scheduled, factual influences on what a buyer can actually pay - the "
            "cost of borrowing and the tax on the purchase. They shape demand, so they sit beside "
            "the figure; they do not move it. Forecasting them into the number would be a guess, "
            "and a guess is exactly what this report exists to replace.")
        for line in mc.get('lines', []):
            pdf.body(line)
        # live macro momentum (BoE + ONS), fed from official statistics at run time
        mom = mc.get('momentum')
        if mom:
            pdf.body("Live momentum, read from official statistics rather than kept by hand:")
            for line in mom.get('lines', []):
                pdf.body(line)
            src = ", ".join(sorted(set(mom.get('sources', {}).values())))
            if src:
                pdf.body(f"(Momentum sources: {src}. Measured against each series' trailing window; "
                         f"a description of conditions, not a forecast.)")
        if mc.get('stale'):
            pdf.body(f"(Macro figures last reviewed {mc['as_of']}; verify current rates before relying on them.)")

    # ---- Reddit market intelligence (best-effort) ---------------------
    _render_reddit_intel(pdf, s)

    # ---- net proceeds ---------------------------------------------------
    if pdf.get_y() > 235:
        pdf.add_page()
    pdf.h2("Net proceeds")
    fee = round(v['central'] * 0.024)
    net = v['central'] - fee
    cols = [("Achieved price", money(v['central'])),
            ("Estimated agent fee (2% + VAT)", money(fee))]
    if s.get('investment'):
        gain = max(0, v['central'] - (s.get('last_sold') or 0) - fee - 3000)
        cgt = round(gain * 0.24)
        cols.append(("Indicative CGT (24% after £3,000 allowance)", money(cgt)))
        cols.append(("Net in pocket", money(net - cgt)))
    else:
        cols.append(("Net in pocket", money(net)))
    for i, (k, val_) in enumerate(cols):
        y = pdf.get_y(); last = (i == len(cols) - 1)
        pdf.set_fill_color(*(PALE if last else (CREAM if i % 2 == 0 else (255, 255, 255))))
        pdf.rect(ML, y, CW, 7, 'F')
        pdf.set_xy(ML + 3, y)
        pdf.set_font('Helvetica', 'B' if last else '', 9.5); pdf.set_text_color(*INK)
        pdf.cell(CW - 45, 7, T(k), align='L')
        pdf.set_font('Helvetica', 'B', 10); pdf.set_text_color(*DARK)
        pdf.cell(40, 7, T(val_), align='R')
        pdf.ln(7)
    if s.get('investment'):
        pdf.ln(1)
        pdf.set_font('Helvetica', 'I', 8); pdf.set_text_color(*MUTED)
        pdf.multi_cell(CW, 4.5, T("Indicative CGT at 24% higher-rate residential after the "
                                  "£3,000 annual exempt amount (2025/26); acquisition and "
                                  "refurbishment costs are allowable and excluded here. Not tax advice."),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    # ---- methodology / honesty -----------------------------------------
    if pdf.get_y() > 225:
        pdf.add_page()
    pdf.h2("Methodology, limitations & sources")
    pdf.set_font('Helvetica', '', 9); pdf.set_text_color(*INK)
    method = [
        "A home is worth what the market will pay. HM Land Registry sold evidence (via "
        "PropertyData) is the anchor - the floor of fact - but it lags the market by months, "
        "so we do not value on sold data alone. A bounded, fully-disclosed adjustment (capped "
        "at +6% / -5%) steers the figure for live market conditions: how fast comparable stock "
        "is going under offer, how long it sits, where it is priced. Asking prices inform that "
        "steer and the positioning above; they never set the figure on their own.",
        "Comparables are filtered to same property type and a focused size band around the "
        "subject, then weighted by proximity. The condition-adjusted valuation models finish "
        "quality against the same area and bedroom profile.",
        "Floor area is EPC-recorded; a measured survey may differ. Refurbishment specification "
        "is not independently inspected. This is a comparative market appraisal, not a RICS Red "
        "Book valuation.",
        "Sources: HM Land Registry Price Paid Data (OGL v3.0), gov.uk/search-house-prices, via "
        "the PropertyData API; EPC Register; HMRC CGT rates.",
    ]
    for m in method:
        pdf.set_x(ML)
        pdf.set_font('Helvetica', 'B', 9); pdf.set_text_color(*GREEN)
        pdf.cell(4, 4.8, T("-"))
        pdf.set_font('Helvetica', '', 9); pdf.set_text_color(*INK)
        pdf.multi_cell(CW - 4, 4.8, T(m), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(0.8)

    # interactive companion + brand sign-off
    pdf.ln(2)
    if interactive:
        pdf.set_fill_color(*CREAM); pdf.set_draw_color(*LINE)
        y = pdf.get_y(); pdf.rect(ML, y, CW, 16, 'DF')
        pdf.set_xy(ML + 4, y + 2.5)
        pdf.set_font('Times', 'B', 11); pdf.set_text_color(*DARK)
        pdf.cell(0, 5, T("Your interactive chart is attached in this chat"),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_xy(ML + 4, y + 8)
        pdf.set_font('Helvetica', '', 9); pdf.set_text_color(*INK)
        pdf.cell(0, 5, T("Open the HTML file above and tap any sold comparable to verify it on HM Land Registry."),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_y(y + 18)
    pdf.set_font('Helvetica', 'U', 9); pdf.set_text_color(*LINK)
    pdf.cell(0, 5, T("Value another property yourself on Telegram - " + bot_url),
             link=bot_url, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    pdf.set_font('Helvetica', '', 8); pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, T(f"Prepared by {agent} - made with Honestly - {DATESTR}"),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf_path = os.path.join(outdir, f"{slug}_appraisal.pdf")
    pdf.output(pdf_path)

    # companion interactive HTML (same data, self-contained, no CDN) - only when this
    # tier includes it, so the PDF's "attached chart" promise is always truthful
    html_path = None
    try:
        if interactive:
            html_path = interactive_chart(allc, v, s, slug, outdir, bot_url)
    except Exception:
        html_path = None
    return pdf_path, html_path


if __name__ == "__main__":
    import sys
    import maps_tools
    maps_tools._load_env()
    key = os.environ.get("PROPERTYDATA_KEY")
    addr = sys.argv[1] if len(sys.argv) > 1 else "11 Shadwell Gardens E1 2QG"
    aud = sys.argv[2] if len(sys.argv) > 2 else "agent"
    r = engine.value(addr, key, finish="average", investment=False)
    p, h = build(r, aud, slug="_sample")
    print("PDF :", p)
    print("HTML:", h)
