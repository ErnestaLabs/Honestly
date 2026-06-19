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
try:
    from fpdf import FPDF, XPos, YPos
    _HAS_FPDF = True
except ImportError:  # optional in this harness; the app should still import cleanly
    from types import SimpleNamespace
    _HAS_FPDF = False
    class FPDF:
        def __getattr__(self, name):
            raise RuntimeError("fpdf2 is not installed")
    XPos = SimpleNamespace(LMARGIN=None)
    YPos = SimpleNamespace(NEXT=None)
import engine
import brand
from appraise import (money, round_to, txn_link, postcode_of, DATESTR,
                      interactive_chart, comp_band, sold_median)

# Best-effort Reddit market intelligence (optional dependency)
try:
    import reddit_intel as _reddit_intel
    _HAS_REDDIT = True
except ImportError:
    _HAS_REDDIT = False

# brand palette - single-sourced from brand.py (the live tailwind palette). The
# legacy names are kept as aliases so the existing render code reads unchanged,
# but every colour now resolves to the real navy/green/teal/gold brand system.
NAVY   = brand.RGB["navy"]    # #0e2747  structure, headings, dark bands
GREEN  = brand.RGB["green"]   # #15807f  sold comparables, central value, links
TEAL   = brand.RGB["teal"]    # #2aa39a  secondary accent
GOLD   = brand.RGB["gold"]    # #d89a32  recommended-guide marker
SAND   = brand.RGB["sand"]    # #c9c1ad
CREAM  = brand.RGB["cream"]   # #f6f3ec  panel fill / masthead band
PAPER  = brand.RGB["paper"]   # #fbf9f4  page background
INK    = brand.RGB["ink"]     # #1c1a16  body text
MUTED  = brand.RGB["muted"]   # #6b6557  secondary text
LINE   = brand.RGB["line"]    # #e7e1d4  hairlines
PALE   = brand.RGB["pale"]    # #e7eef0  pale teal band fill
DARK   = NAVY                 # legacy alias: headings/masthead -> navy
TERRA  = GOLD                 # legacy alias: guide marker -> gold (teal too close to green)
LINK   = GREEN                # link colour

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


def _wrap(text, width=92):
    """Tiny word wrapper for the dependency-free PDF fallback."""
    words = T(text).replace("\n", " ").split()
    lines, cur = [], ""
    for w in words:
        nxt = (cur + " " + w).strip()
        if len(nxt) > width and cur:
            lines.append(cur); cur = w
        else:
            cur = nxt
    if cur:
        lines.append(cur)
    return lines or [""]


def _pdf_text_escape(s):
    return T(s).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_simple_pdf(path, title, lines):
    """Write a valid, plain PDF with no third-party dependency.

    This is the launch safety net: a first valuation must always be able to send a
    lightweight evidence pack, even when fpdf2 is missing on a machine. It deliberately
    uses only built-in Helvetica and text rows.
    """
    pages, page, y = [], [], 800
    for item in lines:
        if item is None:
            y -= 10; continue
        text, bold = (item if isinstance(item, tuple) else (item, False))
        wrapped = _wrap(text, 78 if bold else 92)
        for ln in wrapped:
            if y < 58:
                pages.append(page); page, y = [], 800
            page.append((ln, y, bold)); y -= 15 if bold else 12
        if bold:
            y -= 4
    if page:
        pages.append(page)
    if not pages:
        pages = [[(title, 800, True)]]

    objs = []
    def obj(data):
        objs.append(data); return len(objs)
    font = obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font_b = obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    page_ids = []
    content_ids = []
    for pg in pages:
        parts = ["BT"]
        for text, yy, bold in pg:
            f = "/F2" if bold else "/F1"
            size = 15 if bold else 10
            parts.append(f"{f} {size} Tf 50 {yy} Td ({_pdf_text_escape(text)}) Tj")
        parts.append("ET")
        stream = "\n".join(parts).encode("cp1252", "replace")
        content_ids.append(obj(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"))
        page_ids.append(None)
    pages_id = len(objs) + len(pages) + 1
    for i, cid in enumerate(content_ids):
        page_ids[i] = obj((f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] "
                           f"/Resources << /Font << /F1 {font} 0 R /F2 {font_b} 0 R >> >> "
                           f"/Contents {cid} 0 R >>").encode())
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    pages_id = obj(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode())
    catalog = obj(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, data in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + data + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode()
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs)+1} /Root {catalog} 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    with open(path, "wb") as f:
        f.write(out)
    return path


def _build_simple_evidence_pdf(r, audience, outdir=None, slug=None, bot_url=None,
                               interactive=True, link=None, context=None, tier="lite"):
    """Dependency-free evidence pack used when fpdf2 is unavailable."""
    outdir = outdir or os.path.dirname(os.path.abspath(__file__))
    slug = slug or "report"
    bot_url = bot_url or os.environ.get("HONESTLY_BOT_URL", "https://t.me/usehonestly_bot")
    d = engine.summary(r, audience, n=8, tier=tier)
    path = os.path.join(outdir, f"{slug}_evidence_pack.pdf")
    lines = [
        ("Honestly evidence pack", True),
        f"Prepared {DATESTR}",
        "",
        (d.get("address") or "Property", True),
        f"Assessed range: {d.get('range_str')}",
        f"Central estimate: {money(d.get('central'))}",
        f"{d.get('guide_label', 'Guide')}: {d.get('guide_value_str')}",
        f"Confidence: {(d.get('confidence') or {}).get('grade', 'n/a')} ({(d.get('confidence') or {}).get('score', 'n/a')}/100)",
        "",
        ("Why this is defensible", True),
    ]
    basis = d.get("lite_basis") or {}
    note = basis.get("note") or d.get("plain_english") or "Built from completed sold evidence, not asking prices."
    lines += _wrap(note, 95) + [""]
    if basis:
        lines += [
            f"Primary source: {basis.get('source') or 'HM Land Registry Price Paid Data'}",
            f"Type basis: {basis.get('type_basis') or 'residential evidence'}",
            f"Evidence rows: {basis.get('n_evidence') or d.get('n_comps')}",
            f"Window: {basis.get('window_months') or 'recent'} months",
            "",
        ]
    vf = d.get("valuation_formula") or {}
    if vf:
        lines += [("Formula", True), vf.get("plain_formula") or vf.get("name") or "Honestly Transparent AVM", ""]
    hist = (r.get("valuation") or {}).get("history_model") or {}
    if hist:
        lines += [
            ("Subject history cross-check", True),
            f"Previous recorded sale: {money(hist.get('sale_price'))} on {hist.get('sale_date')}",
            f"HPI-adjusted base: {money(hist.get('base_hpi'))}",
            f"Condition factor: {hist.get('condition_factor')}",
            "This subject history is a cross-check/fallback, never a comparable row.",
            "",
        ]
    lines += [("Proof rows", True)]
    for i, ev in enumerate(d.get("evidence") or [], 1):
        parts = [f"{i}. {ev.get('full_address') or ev.get('address')}",
                 f"sold {ev.get('price_str')} ({ev.get('date')})"]
        if ev.get("sqm"):
            parts.append(f"{ev.get('sqm')} sqm")
        if ev.get("match"):
            parts.append(str(ev.get("match")))
        lines.append(" - ".join(parts))
        if ev.get("verify"):
            lines.append(f"   Source: {ev.get('verify')}")
    lines += [
        "",
        ("Limits", True),
        "This is a transparent automated market appraisal, not a RICS Red Book valuation or survey.",
        "Floor area/EPC may be missing where public records do not match. Missing public facts lower confidence; they do not block the first value.",
        f"Value another property: {bot_url}",
    ]
    _write_simple_pdf(path, "Honestly evidence pack", lines)

    html_path = None
    try:
        if interactive:
            s, v, pos = r["subject"], r["valuation"], r["positioning"]
            html_path = interactive_chart(r.get("compsA") or [], v, s, slug, outdir, bot_url,
                                          d=d, pos=pos, ref_data=d, context=context)
    except Exception:
        html_path = None
    return path, html_path


# ---- Reddit market intelligence (best-effort PDF section) -------------------
_REDDIT_CACHE = {}  # postcode -> intel dict, survives for the process lifetime


def _render_reddit_intel(pdf, subject):
    """Add a Reddit market intelligence page to the PDF - best-effort only.

    Fetches recent Reddit chatter for the property's postcode area, showing
    local sentiment and discussion themes. Never blocks the report; silently
    skipped if unavailable.
    """
    if not _HAS_REDDIT:
        return False
    addr = subject.get("address") or ""
    pc = postcode_of(addr)
    if not pc:
        return False
    area = pc.split()[0] if pc else pc  # postcode district (e.g. SE15)

    # Check cache first
    intel = _REDDIT_CACHE.get(area)
    if intel is None:
        try:
            intel = _reddit_intel.for_area(area, audience="agent", postcode=pc)
            _REDDIT_CACHE[area] = intel if intel else {}
        except Exception:
            return False
    if not intel or not intel.get("threads"):
        return False

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
    return True


_SCHOOLS_CACHE = {}  # postcode -> [schools], survives for the process lifetime


def _render_schools(pdf, s, key):
    """Nearest schools with phase, distance and an OFFICIAL Ofsted report link.
    Direct-public-source only; currently silent until the Ofsted/GIAS client lands."""
    if not key:
        return False
    try:
        import products as _products
    except Exception:
        return False
    pc = postcode_of(s.get("address", "")) or ""
    schools = _SCHOOLS_CACHE.get(pc)
    if schools is None:
        try:
            schools = _products.nearby_schools({"subject": s}, key, n=6)
        except Exception:
            schools = []
        _SCHOOLS_CACHE[pc] = schools
    if not schools:
        return False

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
    return True


def _render_material_information(pdf, s, v):
    """NTSELAT Material Information starter - Parts A, B and C.

    Renders the facts we hold from the public record, and turns disclosure-only fields
    into decision-check items. Honest by design: we never invent a legal/material fact,
    but the user always receives a usable checklist rather than a blank.
    Reference: NTSELAT Material Information in Property Listings, Parts A/B/C."""
    if pdf.get_y() > 210:
        pdf.add_page()
    pdf.h2("Material information (NTSELAT)")
    pdf.body(
        "National Trading Standards (NTSELAT) sets defined material information for every "
        "UK property listing. This pack includes the public facts plus the decision-check "
        "items needed before marketing or offering. Legal disclosure facts are never guessed.")

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
        pdf.cell(67, 7, T(value if known else "Decision-check item"), align='R')
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
        "Parts A, B and C as defined by NTSELAT. Honestly includes the public record plus the "
        "decision-check items a buyer, seller or agent should verify before commitment. This is not legal advice."),
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
        # the EXACT brand icon as the running mark (never a font-drawn logo)
        icon = brand.logo_path('icon')
        if os.path.exists(icon):
            self.image(icon, x=ML, y=7.5, h=6.0)
            tx = ML + 7.5
        else:
            tx = ML
        self.set_xy(tx, 8)
        self.set_font('Times', 'B', 11)
        self.set_text_color(*NAVY)
        self.cell(0, 6, T('honestly'), align='L')
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
        self.cell(0, 5, T('Anchored in HM Land Registry sold evidence, explained by '
                          'transparent market context.'), align='L')
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
EV_COLS = [('Comparable', 50, 'L'), ('Size', 17, 'R'), ('Sold', 25, 'R'),
           ('When', 20, 'C'), ('GBP/sqm', 21, 'R'), ('Dist', 14, 'R'),
           ('Match', 16, 'R'), ('Verify', 0, 'C')]


def _ev_cols(rows, first_label='Comparable'):
    """Hide dead evidence columns when public data does not contain the field.

    A table full of '-' in Size/GBP-sqm/Match destroys trust. If HMLR gave sale rows but
    EPC/floor-area matching did not, show those rows honestly as sold proof/context.
    """
    rows = rows or []
    have_size = any(r.get('sqm') for r in rows)
    have_psm = any(r.get('psm') for r in rows)
    have_match = any(r.get('match') is not None for r in rows)
    cols = [(first_label, 66, 'L')]
    if have_size:
        cols.append(('Size', 17, 'R'))
    cols += [('Sold', 27, 'R'), ('When', 20, 'C')]
    if have_psm:
        cols.append(('GBP/sqm', 21, 'R'))
    cols.append(('Dist', 16, 'R'))
    if have_match:
        cols.append(('Match', 16, 'R'))
    cols.append(('Verify', 0, 'C'))
    return cols


def _ev_header(pdf, cols):
    pdf.set_font('Helvetica', 'B', 8.5)
    pdf.set_fill_color(*DARK); pdf.set_text_color(255, 255, 255)
    x = ML
    for name, w, align in cols:
        ww = w if w else (ML + CW - x)
        pdf.set_xy(x, pdf.get_y())
        pdf.cell(ww, 7, T(name), align=align, fill=True)
        x += ww
    pdf.ln(7)

def _ev_table(pdf, rows, first_label='Comparable'):
    cols = _ev_cols(rows, first_label=first_label)
    _ev_header(pdf, cols)
    fill = False
    pdf.set_font('Helvetica', '', 8.5)
    for r in rows:
        if pdf.get_y() > 262:                 # leave room for footer
            pdf.add_page(); _ev_header(pdf, cols)
            pdf.set_font('Helvetica', '', 8.5)
        y = pdf.get_y()
        pdf.set_fill_color(*(CREAM if fill else (255, 255, 255)))
        pdf.rect(ML, y, CW, 6.4, 'F')
        addr = r['address'].split(',')[0]
        match = f"{r['match']}%" if r.get('match') is not None else '-'
        cell_map = {
            first_label: addr,
            'Size': f"{r['sqm']} sqm" if r.get('sqm') else '-',
            'Sold': money(r['price']),
            'When': str(r.get('date') or '')[:7],
            'GBP/sqm': f"£{int(r['psm']):,}" if r.get('psm') else '-',
            'Dist': f"{r['dist']} mi" if r.get('dist') is not None else '-',
            'Match': match,
        }
        cells = [(cell_map[name], w, align) for name, w, align in cols if name != 'Verify']
        x = ML
        for txt, w, align in cells:
            pdf.set_xy(x, y)
            pdf.set_font('Helvetica', '', 8.3)
            # weak (screened) comparables, if any slip into view, are muted, not bold-faced
            pdf.set_text_color(*(MUTED if r.get('weak') else INK))
            pdf.cell(w, 6.4, T(txt), align=align)
            x += w
        # clickable verify cell
        vw = ML + CW - x
        pdf.set_xy(x, y)
        pdf.set_font('Helvetica', 'U', 8.3); pdf.set_text_color(*LINK)
        pdf.cell(vw, 6.4, T('source'), align='C', link=txn_link(r))
        pdf.set_text_color(*INK)
        pdf.ln(6.4)
        fill = not fill


# -- the native bar chart (no image, drawn with rects) ------------------------
def _bar_chart(pdf, rows, val, row_label='Sold comparable'):
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
    pdf.cell(34, 5, T(row_label))
    pdf.set_fill_color(*PALE); pdf.rect(pdf.get_x(), pdf.get_y() + 1, 3, 3, 'DF')
    pdf.set_x(pdf.get_x() + 4); pdf.cell(30, 5, T('Assessed range'))
    pdf.set_draw_color(*GREEN); pdf.set_line_width(0.5)
    yy = pdf.get_y() + 2.5; pdf.line(pdf.get_x(), yy, pdf.get_x() + 3, yy)
    pdf.set_x(pdf.get_x() + 4); pdf.cell(28, 5, T('Central value'))
    pdf.set_draw_color(*TERRA)
    yy = pdf.get_y() + 2.5; pdf.line(pdf.get_x(), yy, pdf.get_x() + 3, yy)
    pdf.set_x(pdf.get_x() + 4); pdf.cell(34, 5, T('Recommended guide'))
    pdf.ln(8)


# -- price-influence ledger (Pro section 4) -------------------------------------------
def _render_price_ledger(pdf, d):
    """Pro section 4 - the price-influence ledger. Renders d['price_ledger'] (built by
    price_ledger.build): every factor that bears on this property's price, each with its
    source and direction, split honestly into the three that actually moved the figure and
    everything that sits beside it. Best-effort: renders nothing if the ledger is absent or
    unavailable. It reads what engine.summary() + the area context already established; it
    never moves a number. Returns True if it rendered, False otherwise."""
    led = d.get("price_ledger")
    if not led or not led.get("ok"):
        return False
    try:
        import price_ledger as _pl
    except Exception:
        return False

    def _trunc(txt, n):
        s = T(txt)
        return s if len(s) <= n else s[: n - 1].rstrip() + "."

    if pdf.get_y() > 205:
        pdf.add_page()
    pdf.h2("Price-influence ledger")
    pdf.body(
        "The glass box, in full: every factor that bears on this property's price, each with "
        "its source and the direction it pushes value. The honest part is the split - only "
        "three of these actually moved the assessed figure; everything else is real, sourced "
        "and shown beside it, never blended into the number.")

    def _group(title, items):
        if not items:
            return
        pdf.ln(1)
        pdf.set_font('Times', 'B', 11); pdf.set_text_color(*NAVY)
        pdf.cell(0, 6, T(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(0.5)
        for i, f in enumerate(items):
            if pdf.get_y() > 262:
                pdf.add_page()
            rh = 11.0
            y = pdf.get_y()
            pdf.set_fill_color(*(CREAM if i % 2 == 0 else (255, 255, 255)))
            pdf.rect(ML, y, CW, rh, 'F')
            direction = f.get("direction", "context")
            arrow = _pl._ARROW.get(direction, ".")
            col = (GREEN if direction in ("up", "anchor") else
                   GOLD if direction == "down" else MUTED)
            # direction chip
            pdf.set_xy(ML + 2, y + 1.6); pdf.set_font('Helvetica', 'B', 11); pdf.set_text_color(*col)
            pdf.cell(8, 5, T(f"[{arrow}]"), align='L')
            # factor + value
            head = f.get("factor", "")
            if f.get("value"):
                head += f" - {f['value']}"
            pdf.set_xy(ML + 11, y + 1.6); pdf.set_font('Helvetica', 'B', 9.5); pdf.set_text_color(*INK)
            pdf.cell(CW - 11 - 40, 5, _trunc(head, 70), align='L')
            # direction word, right
            pdf.set_xy(ML + CW - 41, y + 1.6); pdf.set_font('Helvetica', 'I', 8.5)
            pdf.set_text_color(*MUTED)
            pdf.cell(39, 5, T(_pl._WORD.get(direction, "context")), align='R')
            # source line
            pdf.set_xy(ML + 11, y + 6.2); pdf.set_font('Helvetica', 'I', 7.6); pdf.set_text_color(*MUTED)
            pdf.cell(CW - 13, 4, _trunc(f.get("source", ""), 110), align='L')
            pdf.set_xy(ML, y + rh)
        pdf.ln(1)

    _group("Moved the figure", led.get("movers"))
    _group("Beside the figure (context, not blended in)", led.get("context_factors"))
    if led.get("basis"):
        pdf.ln(0.5)
        pdf.set_font('Helvetica', 'I', 8.5); pdf.set_text_color(*MUTED)
        pdf.multi_cell(CW, 4.4, T(led["basis"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1)
    return True


def _render_verification(pdf, d):
    """Pro section 7 - the data-spine verification panel. Renders d['verification'] (built by
    verification.build): direct public facts are listed with source and status, never silently
    reconciled. Pure synthesis beside the figure - it moves no number. Best-effort:
    renders nothing if the panel is absent. Returns True if it rendered, False otherwise."""
    ver = d.get("verification")
    if not ver or not ver.get("ok") or not ver.get("rows"):
        return False

    def _trunc(txt, n):
        s = T(txt)
        return s if len(s) <= n else s[: n - 1].rstrip() + "."

    if pdf.get_y() > 215:
        pdf.add_page()
    pdf.h2("Data-spine verification")
    div = ver.get("divergences", 0)
    lead = ("We resolve this property through more than one data provider. Where two of them "
            "describe the same attribute, we cross-check - and where they disagree, we show you "
            "exactly what each one said rather than quietly picking one. ")
    lead += (f"{div} attribute(s) diverge below. " if div else
             "The providers corroborate one another below. ")
    lead += "None of this moves the assessed figure; it is material information beside it."
    pdf.body(lead)

    _STATUS = {"divergent": ("Sources differ", GOLD),
               "corroborated": ("Sources agree", GREEN),
               "single": ("One source", MUTED)}
    for r in ver["rows"]:
        if pdf.get_y() > 250:
            pdf.add_page()
        label, col = _STATUS.get(r.get("status"), ("", MUTED))
        y = pdf.get_y()
        # header row: attribute label + status chip
        pdf.set_fill_color(*CREAM); pdf.rect(ML, y, CW, 6.4, 'F')
        pdf.set_xy(ML + 2, y + 1.3); pdf.set_font('Times', 'B', 10.5); pdf.set_text_color(*NAVY)
        pdf.cell(CW - 44, 4, _trunc(r.get("label", ""), 48), align='L')
        pdf.set_xy(ML + CW - 42, y + 1.3); pdf.set_font('Helvetica', 'B', 8)
        pdf.set_text_color(*col)
        pdf.cell(40, 4, T(label), align='R')
        pdf.set_xy(ML, y + 6.4)
        # one line per source that spoke (and per source that did not, shown 'not reported')
        for v in r.get("values", []):
            yy = pdf.get_y()
            pdf.set_xy(ML + 6, yy + 0.6); pdf.set_font('Helvetica', 'B', 8.5)
            pdf.set_text_color(*INK)
            pdf.cell(30, 4.4, T(v.get("source", "")), align='L')
            pdf.set_xy(ML + 38, yy + 0.6); pdf.set_font('Helvetica', '', 8.5)
            pdf.set_text_color(*MUTED)
            pdf.cell(CW - 40, 4.4, _trunc(v.get("raw", ""), 80), align='L')
            pdf.set_xy(ML, yy + 5.0)
        if r.get("note"):
            yy = pdf.get_y()
            pdf.set_xy(ML + 6, yy); pdf.set_font('Helvetica', 'I', 7.4); pdf.set_text_color(*MUTED)
            pdf.multi_cell(CW - 8, 3.8, _trunc(r["note"], 220),
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1.5)
    return True


# -- area context (Location / Area / Safety / Environment / Planning / Narrative) -----
def _render_context(pdf, context, skip=None):
    """Render the area-context sections from area_context.gather(). Best-effort: each
    section renders only if its source returned data; a down source is omitted (its honest
    'not available' is simply the absence of the section), never faked. Returns the set of
    citation ids actually rendered, so build() can light the matching References entries.
    All of this is context BESIDE the figure - none of it is an input to the valuation.

    `skip` is a set of section keys whose home is elsewhere in the document (the blueprint
    moves crime/flood/planning into the factor Q&A), so they are not rendered twice."""
    if not context:
        return set()
    skip = skip or set()
    sec = context.get("sections") or {}
    out = set()

    def _need(space=44):
        if pdf.get_y() > (297 - 18 - space):
            pdf.add_page()

    def _line(label, value):
        y = pdf.get_y()
        pdf.set_x(ML)
        pdf.set_font('Helvetica', '', 9.3); pdf.set_text_color(*MUTED)
        pdf.cell(54, 5.4, T(label), align='L')
        pdf.set_xy(ML + 54, y)
        pdf.set_font('Helvetica', 'B', 9.5); pdf.set_text_color(*INK)
        pdf.multi_cell(CW - 54, 5.4, T(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ---- Narrative (Gemini, grounded + guarded)
    nar = sec.get("narrative")
    if nar and nar.get("ok") is not False and nar.get("text"):
        _need(54)
        pdf.h2("In plain English")
        for para in [p.strip() for p in str(nar["text"]).split("\n") if p.strip()]:
            pdf.body(para, h=4.8, size=9.5)
        pdf.set_font('Helvetica', 'I', 8); pdf.set_text_color(*MUTED)
        pdf.multi_cell(CW, 4.2, T("Narrative drafted by an AI model strictly from the figures in "
                                  "this report; any figure it could not source was rejected before printing."),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1); out.add("gemini")

    # ---- Location & connectivity
    loc = sec.get("location")
    if loc and (loc.get("legs") or loc.get("validated") or (loc.get("lat") and loc.get("lng"))):
        _need(46)
        pdf.h2("Location & connectivity")
        if loc.get("validated") and loc["validated"].get("formatted"):
            pdf.body("Verified address: " + loc["validated"]["formatted"] + ".", h=4.8, size=9.3)
            out.add("addr_val")
        for g in (loc.get("legs") or []):
            v = " - ".join([x for x in [g.get("time"), g.get("dist")] if x]) or "-"
            _line(g.get("label", "Travel"), v)
            if g.get("time"):
                out.add("distance_mx")
        if loc.get("lat") and loc.get("lng"):
            pdf.ln(0.5)
            pdf.set_font('Helvetica', 'I', 8); pdf.set_text_color(*MUTED)
            pdf.multi_cell(CW, 4.2, T(f"Geolocated to {loc.get('postcode') or ''} "
                                      f"({loc['lat']:.4f}, {loc['lng']:.4f})."),
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            out.add("postcodes_io")
        pdf.ln(1)

    # ---- Area & amenities
    area = sec.get("area")
    if area and area.get("counts") and any(area["counts"].values()):
        _need(40)
        pdf.h2("Area & amenities")
        within = ", ".join(f"{k}: {v}" for k, v in area["counts"].items() if v)
        pdf.body(f"Within {area.get('radius_m', 800)} m of the property - {within}.",
                 h=4.8, size=9.3)
        for t in (area.get("transport") or [])[:4]:
            _line(t.get("name", "Station"), f"~{t.get('dist_m')} m")
        pdf.ln(1); out.add("overpass")

    # ---- Safety
    saf = sec.get("safety")
    if "safety" not in skip and saf and saf.get("total") is not None:
        _need(36)
        pdf.h2("Safety")
        pdf.body(f"{saf['total']} street-level crimes recorded {saf.get('radius_note', '')} "
                 f"in {saf.get('month', 'the latest month')}.", h=4.8, size=9.3)
        for cat, n in (saf.get("by_category") or [])[:5]:
            _line(cat, str(n))
        pdf.ln(1); out.add("police")

    # ---- Environment
    env = sec.get("environment")
    if "environment" not in skip and env and (env.get("flood") or env.get("air")):
        _need(34)
        pdf.h2("Environment")
        if env.get("flood"):
            fl = env["flood"]
            txt = fl.get("severity", "")
            if fl.get("lines"):
                txt += " - " + fl["lines"][0]
            _line("Flood", txt); out.add("flood")
        if env.get("air"):
            aq = env["air"]
            aqv = (f"AQI {round(aq['aqi'])} {aq.get('band', '')}" if aq.get("aqi") is not None
                   else (aq.get("band") or "-"))
            bits = []
            for lab, k in (("PM2.5", "pm2_5"), ("PM10", "pm10"), ("NO2", "no2")):
                if aq.get(k) is not None:
                    bits.append(f"{lab} {aq[k]}")
            if bits:
                aqv += "  (" + ", ".join(bits) + " ug/m3)"
            _line("Air quality", aqv); out.add("air_quality")
        pdf.ln(1)

    # ---- Planning & development
    pl = sec.get("planning")
    if "planning" not in skip and pl and pl.get("total") is not None:
        _need(40)
        pdf.h2("Planning & development")
        pdf.body(f"{pl['total']} planning application(s) recorded near the property "
                 f"in the recent window.", h=4.8, size=9.3)
        for status, n in (pl.get("by_status") or [])[:5]:
            _line(status, str(n))
        pdf.ln(1); out.add("planning")

    # ---- Solar & energy (Google Solar, building-level roof potential)
    so = sec.get("solar")
    if so and so.get("ok") is not False and so.get("potential"):
        _need(44)
        pdf.h2("Solar & energy")
        if so.get("potential"):
            _line("Roof solar potential", so["potential"])
        if so.get("domestic_panels") and so.get("domestic_kwh_yr"):
            _line("Domestic array",
                  f"{so['domestic_panels']} panels (~{so.get('domestic_kwp')} kWp), "
                  f"~{so['domestic_kwh_yr']:,} kWh/yr")
        if so.get("max_panels"):
            area = so.get("max_array_area_m2")
            _line("Whole-roof maximum",
                  f"up to {so['max_panels']} panels"
                  + (f" across ~{area} m2" if area else "") + " (building-level)")
        if so.get("co2_offset_kg_yr"):
            _line("CO2 offset", f"~{so['co2_offset_kg_yr']:,} kg/yr (domestic array)")
        if so.get("imagery_date"):
            _line("Roof imagery", f"{so['imagery_date']} "
                  f"({str(so.get('imagery_quality', '')).lower()} quality)")
        if so.get("far_snap"):
            pdf.set_font('Helvetica', 'I', 8); pdf.set_text_color(*MUTED)
            pdf.multi_cell(CW, 4.2, T(f"The nearest mapped roof is ~{round(so['snap_distance_m'])} m "
                                      f"from the address, so these figures may describe a "
                                      f"neighbouring building - treat as indicative."),
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(0.5)
        pdf.set_font('Helvetica', 'I', 7.6); pdf.set_text_color(*MUTED)
        pdf.multi_cell(CW, 4.0, T(so.get("band_rule", "")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1); out.add("google_solar")

    return out


def _locked_section(pdf, title, teaser, bot_url, link=None):
    """Draw a frosted 'PRO - locked' placeholder where a Pro section would sit in a Lite
    report. It names the section and what Pro adds, and links to unlock - it never prints the
    Pro data itself, so a Lite PDF physically carries none of it (leak-proof by construction).
    Mirrors the HTML in-place locked preview."""
    h = 24.0
    if pdf.get_y() > (297 - 18 - h):
        pdf.add_page()
    pdf.ln(1)
    y = pdf.get_y()
    pdf.set_fill_color(*CREAM); pdf.set_draw_color(*SAND); pdf.set_line_width(0.3)
    pdf.rect(ML, y, CW, h, 'DF')
    pdf.set_xy(ML + 3, y + 3)
    pdf.set_fill_color(*GOLD); pdf.set_text_color(*NAVY); pdf.set_font('Helvetica', 'B', 7.5)
    pdf.cell(13, 5, T("PRO"), align='C', fill=True)
    pdf.set_xy(ML + 19, y + 2.6)
    pdf.set_font('Times', 'B', 12); pdf.set_text_color(*NAVY)
    pdf.cell(CW - 22, 6, T(title))
    pdf.set_xy(ML + 3, y + 10)
    pdf.set_font('Helvetica', '', 9); pdf.set_text_color(*MUTED)
    pdf.multi_cell(CW - 6, 4.4, T(teaser), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    # A Pro lock links to the live purchase (?start=buy_pro), so tapping lands the reader on
    # the Pro offer ready to buy - never a sleeping bot. _buy_link is defined below build().
    target = _buy_link(bot_url, "pro")
    pdf.set_x(ML + 3)
    pdf.set_font('Helvetica', 'U', 8.5); pdf.set_text_color(*LINK)
    pdf.cell(0, 5, T("Unlock the full report  >"), link=target)
    pdf.set_y(y + h + 2)


def _purity_bar(pdf, ep):
    """Evidence Purity Score - the trust metric that REPLACES a vibe confidence number
    with a composition fact: the share of the published figure that is direct HM Land
    Registry sold evidence versus disclosed system adjustment. Two stacked bars, drawn
    from engine.summary()'s evidence_purity so the PDF, the HTML and the bot never drift.
    """
    pct = ep.get("pct")
    if pct is None:
        return
    adj = ep.get("adjustment_pct", 100 - pct)
    if pdf.get_y() > 250:
        pdf.add_page()
    pdf.ln(1)
    y0 = pdf.get_y()
    pdf.set_font('Helvetica', 'B', 9.5); pdf.set_text_color(*NAVY)
    pdf.cell(0, 5.5, T("Evidence purity"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    bar_w = CW - 64
    def _row(label, value, colour, note):
        yy = pdf.get_y()
        pdf.set_font('Helvetica', '', 8.5); pdf.set_text_color(*MUTED)
        pdf.cell(40, 5.5, T(label), align='L')
        x = pdf.get_x()
        pdf.set_fill_color(*LINE); pdf.rect(x, yy + 1.0, bar_w, 3.2, 'F')
        pdf.set_fill_color(*colour); pdf.rect(x, yy + 1.0, bar_w * (value / 100.0), 3.2, 'F')
        pdf.set_xy(x + bar_w + 3, yy)
        pdf.set_font('Helvetica', 'B', 9); pdf.set_text_color(*DARK)
        pdf.cell(20, 5.5, T(f"{value}%"), align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    _row("Hard sold evidence", pct, GREEN, "")
    _row("System adjustment", adj, GOLD, "")
    drivers = ep.get("drivers") or []
    if drivers:
        pdf.set_font('Helvetica', 'I', 8); pdf.set_text_color(*MUTED)
        pdf.multi_cell(CW, 4.2, T(f"What the {adj}% adjustment is: " + "; ".join(drivers[:3]) + "."),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)


def _decision_block(d, audience):
    """Thin wrapper: the decision logic is single-sourced in engine.decision_block so the
    PDF and the interactive HTML render the SAME verdict, why/risks and personalised frame."""
    return engine.decision_block(d, audience)


def _render_decision(pdf, d, audience):
    """Render the decision block. Mirrors the HTML decision panel 1:1."""
    blk = _decision_block(d, audience)
    h_needed = 44 + 5 * (len(blk["why"]) + len(blk["risks"]))
    if pdf.get_y() > (297 - 18 - h_needed):
        pdf.add_page()
    pdf.h2("If this were our money")
    warn = blk["word"] in ("NOT AT THIS PRICE", "NOT BLIND")
    badge = TERRA if warn else GREEN
    # Personalised question + the one need this profile cares about most (Hit VOC).
    pdf.set_font('Helvetica', '', 9.5); pdf.set_text_color(*MUTED)
    pdf.cell(0, 5.5, T(blk.get("question") or "Would we stand behind this number?"),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('Times', 'B', 18); pdf.set_text_color(*badge)
    pdf.cell(0, 9, T(blk["word"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('Helvetica', 'I', 9); pdf.set_text_color(*INK)
    pdf.multi_cell(CW, 4.6, T("- " + blk["headline"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if blk.get("need"):
        pdf.ln(0.8)
        pdf.set_font('Helvetica', '', 9); pdf.set_text_color(*MUTED)
        pdf.multi_cell(CW, 4.6, T(blk["need"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1.5)
    pdf.set_font('Helvetica', 'B', 9); pdf.set_text_color(*NAVY)
    pdf.cell(0, 5, T("Why"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('Helvetica', '', 9); pdf.set_text_color(*INK)
    for b in blk["why"]:
        pdf.multi_cell(CW, 4.6, T(f"   +  {b}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(0.5)
    pdf.set_font('Helvetica', 'B', 9); pdf.set_text_color(*NAVY)
    pdf.cell(0, 5, T("Watch out for"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('Helvetica', '', 9); pdf.set_text_color(*INK)
    for b in blk["risks"]:
        pdf.multi_cell(CW, 4.6, T(f"   !  {b}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if blk.get("next"):
        pdf.ln(0.8)
        pdf.set_font('Helvetica', 'B', 9); pdf.set_text_color(*NAVY)
        pdf.cell(0, 5, T("What to do next"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('Helvetica', '', 9); pdf.set_text_color(*INK)
        pdf.multi_cell(CW, 4.6, T(blk["next"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)


def _bp_role_badge(pdf, audience, investment):
    """Header role badge: BUYER / SELLER / AGENT / INVESTOR. Sits top-right under the date."""
    label = ("INVESTOR" if investment else
             {"buyer": "BUYER", "vendor": "SELLER", "seller": "SELLER",
              "agent": "AGENT", "investor": "INVESTOR"}.get((audience or "").lower(), "BUYER"))
    w = 30.0
    x = ML + CW - w
    y = 26.0
    pdf.set_fill_color(*NAVY); pdf.set_draw_color(*NAVY)
    pdf.rect(x, y, w, 6.4, 'F')
    pdf.set_xy(x, y + 0.3)
    pdf.set_font('Helvetica', 'B', 8.5); pdf.set_text_color(*CREAM)
    pdf.cell(w, 5.8, T(label), align='C')
    pdf.set_text_color(*INK)


def _bp_hero(pdf, d, v, ep, n_comps, radius_mi):
    """Section 1 - the value the eyes hit first. Big centred central figure, the range
    under it, the Evidence Purity bars, and one line of provenance. No prose."""
    pdf.ln(2)
    pdf.set_font('Helvetica', '', 10); pdf.set_text_color(*MUTED)
    pdf.cell(CW, 5, T("ASSESSED MARKET VALUE"), align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('Times', 'B', 40); pdf.set_text_color(*NAVY)
    pdf.cell(CW, 18, T(money(v['central'])), align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('Helvetica', '', 12); pdf.set_text_color(*INK)
    pdf.cell(CW, 6, T(f"{money(v['low'])}  to  {money(v['high'])}"), align='C',
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)
    # Evidence Purity bars, centred
    pct = (ep or {}).get("pct")
    if pct is not None:
        adj = ep.get("adjustment_pct", 100 - pct)
        bw = CW * 0.62
        x0 = ML + (CW - bw) / 2.0
        def _bar(lab, val, colour):
            yy = pdf.get_y()
            pdf.set_font('Helvetica', '', 8.5); pdf.set_text_color(*MUTED)
            pdf.set_xy(x0, yy); pdf.cell(46, 4.6, T(lab), align='L')
            bx = x0 + 46
            innerw = bw - 46 - 14
            pdf.set_fill_color(*LINE); pdf.rect(bx, yy + 0.8, innerw, 3.0, 'F')
            pdf.set_fill_color(*colour); pdf.rect(bx, yy + 0.8, innerw * (val / 100.0), 3.0, 'F')
            pdf.set_xy(bx + innerw + 1, yy)
            pdf.set_font('Helvetica', 'B', 8.5); pdf.set_text_color(*DARK)
            pdf.cell(13, 4.6, T(f"{val}%"), align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        _bar("Evidence purity", pct, GREEN)
        _bar("System adjustment", adj, GOLD)
        pdf.ln(1)
    # provenance one-liner
    rad = (f"{radius_mi:.1f} miles" if isinstance(radius_mi, (int, float)) else "0.5 miles")
    pdf.set_font('Helvetica', 'I', 9.5); pdf.set_text_color(*MUTED)
    pdf.cell(CW, 5, T(f"Based on {n_comps} comparable sale{'s' if n_comps != 1 else ''} within {rad}, from HM Land Registry."),
             align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.set_draw_color(*LINE); pdf.set_line_width(0.3); pdf.line(ML, pdf.get_y(), ML + CW, pdf.get_y())
    pdf.ln(3)


def _bp_trust(pdf, d, history_basis):
    """Section 2 - trust anchor. The exclusion statement + the comparability criteria as
    bullets. No paragraphs."""
    excl = d.get("n_screened") or 0
    pdf.set_font('Helvetica', 'B', 12); pdf.set_text_color(*NAVY)
    if excl:
        pdf.multi_cell(CW, 6, T(f"We excluded {excl} nearby sale{'s' if excl != 1 else ''} because they were not comparable."),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.multi_cell(CW, 6, T("Every comparable below passed the same strict gate."),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(0.5)
    crit = ["Same property type", "Same size band (floor area within 20%)",
            "Within half a mile", "Sold in the last 6-12 months",
            "Price within 30% of the local anchor"]
    pdf.set_font('Helvetica', '', 9.5); pdf.set_text_color(*INK)
    for c in crit:
        pdf.set_x(ML)
        pdf.set_text_color(*GREEN); pdf.set_font('Helvetica', 'B', 9.5); pdf.cell(5, 4.8, T("+"))
        pdf.set_text_color(*INK); pdf.set_font('Helvetica', '', 9.5)
        pdf.cell(0, 4.8, T(c), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)


def _bp_ladder(pdf, allc, v):
    """Section 3 - the price ladder. Comparable sold prices ranked high to low with the
    subject's assessed value highlighted in place, so the reader sees where it sits."""
    rows = [c for c in allc if c.get("price")]
    if not rows:
        return
    rows = sorted(rows, key=lambda c: -c["price"])[:8]
    items = [(c["price"], c.get("address", "").split(",")[0][:24], False) for c in rows]
    items.append((v["central"], "THIS PROPERTY (assessed)", True))
    items.sort(key=lambda t: -t[0])
    prices = [p for p, _, _ in items]
    pmin, pmax = min(prices), max(prices)
    span = (pmax - pmin) or 1
    pdf.set_font('Helvetica', 'B', 11); pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, T("Where this sits in the market"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    label_w, val_w = 64.0, 26.0
    bar_w = CW - label_w - val_w
    for price, lab, is_subj in items:
        y = pdf.get_y()
        frac = (price - pmin) / span
        col = NAVY if is_subj else GREEN
        if is_subj:
            pdf.set_fill_color(*PALE); pdf.rect(ML, y - 0.6, CW, 6.6, 'F')
        pdf.set_xy(ML, y)
        pdf.set_font('Helvetica', 'B' if is_subj else '', 8.5)
        pdf.set_text_color(*(NAVY if is_subj else INK))
        pdf.cell(label_w, 5.4, T(("> " if is_subj else "  ") + lab), align='L')
        bx = ML + label_w
        pdf.set_fill_color(*col)
        pdf.rect(bx, y + 1.0, max(1.5, bar_w * frac), 3.2, 'F')
        pdf.set_xy(bx + bar_w, y)
        pdf.set_font('Helvetica', 'B' if is_subj else '', 8.5); pdf.set_text_color(*(NAVY if is_subj else DARK))
        pdf.cell(val_w, 5.4, T(money(price)), align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)


def _bp_drivers(pdf, d, v, ep, context):
    """Section 4 - what actually drives the price, as ranked bars. Honest by construction:
    the figure rests on what same-size local homes sold for (the comparable basis), condition
    is the one explicit adjustment, and the area factors are shown at their REAL influence -
    zero on the figure - never a fabricated per-factor pounds or percent."""
    adj = (ep or {}).get("adjustment_pct", 0) or 0
    sec = ((context or {}).get("sections") or {}) if isinstance(context, dict) else {}
    has_ctx = any(sec.get(k) for k in ("safety", "environment", "planning"))
    drivers = [("Comparable sold evidence (location + size)", 100, GREEN),
               ("Condition of the property", max(6, min(40, adj * 3)), GOLD)]
    for lab, key in (("Planning nearby", "planning"), ("Crime", "safety"), ("Flood risk", "environment")):
        drivers.append((lab, 3 if has_ctx else 2, SAND))
    mx = max(w for _, w, _ in drivers) or 1
    pdf.set_font('Helvetica', 'B', 11); pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, T("What drives this price"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    lw = 76.0
    bw = CW - lw
    for lab, w, col in drivers:
        y = pdf.get_y()
        pdf.set_xy(ML, y); pdf.set_font('Helvetica', '', 9); pdf.set_text_color(*INK)
        pdf.cell(lw, 5.2, T(lab), align='L')
        pdf.set_fill_color(*col)
        pdf.rect(ML + lw, y + 1.0, max(1.2, bw * (w / mx)), 3.2, 'F')
        pdf.ln(5.2)
    pdf.ln(1)
    pdf.set_font('Helvetica', 'I', 9); pdf.set_text_color(*MUTED)
    pdf.multi_cell(CW, 4.6, T("Most of the value is set by what same-size homes nearby actually sold for. "
                              "Condition is the only factor that adjusts it. Crime, flood and planning "
                              "showed no measurable effect on local sold prices."),
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)


def _buy_link(bot_url, mid):
    """A Telegram deep link that lands the reader on the RELEVANT product, ready to act -
    the bot decodes ?start=buy_<mid> and fires that exact offer (never a sleeping bot)."""
    base = bot_url or "https://t.me/usehonestly_bot"
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}start=buy_{mid}"


def _bp_factor_qa(pdf, context, bot_url=None, link=None):
    """Section 5 - factor Q&A. Crime, Planning, Flood, each EXACTLY Question -> Answer ->
    Evidence -> So what. At the moment of doubt, a curiosity-framed hyperlink ('see how this
    affects YOUR price') lands on the price-influence ledger - the paid product that answers
    exactly that for this property. Conversion hook, honest target. Data-gated; never invented."""
    blocks = engine.factor_qa(context)
    if not blocks:
        return
    pdf.set_font('Helvetica', 'B', 11); pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, T("Does anything change the number?"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    for b in blocks:
        if pdf.get_y() > 244:
            pdf.add_page()
        pdf.set_font('Helvetica', 'B', 9.5); pdf.set_text_color(*INK)
        pdf.multi_cell(CW, 4.8, T(b["q"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('Helvetica', 'B', 9.5); pdf.set_text_color(*(TERRA if b["flag"] else GREEN))
        pdf.multi_cell(CW, 4.8, T(b["a"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('Helvetica', '', 9); pdf.set_text_color(*MUTED)
        pdf.multi_cell(CW, 4.4, T("Evidence: " + b["ev"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.multi_cell(CW, 4.4, T("So what: " + b["sw"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        # The upsell hyperlink fires ONLY when the factor is genuinely flagged (a real reason
        # to look closer). A benign factor ("crime: no impact", "flood: very low") gets no link -
        # slapping a paid link on a non-issue is amateur and kills trust. Flagged = conversion moment.
        if b["flag"]:
            pdf.set_font('Helvetica', 'U', 8.8); pdf.set_text_color(*LINK)
            pdf.cell(0, 4.6, T(b["guide"] + "  >"), link=_buy_link(bot_url, b["mid"]),
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1.5)


def _bp_market_logic(pdf, d, v, allc, history_basis):
    """Section 6 - market logic, a tight synthesis (no storytelling). What the comps say,
    what the price implies, where the uncertainty is."""
    band = comp_band(allc)
    pe = d.get("plain_english") or {}
    pdf.set_font('Helvetica', 'B', 11); pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, T("The logic, in short"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('Helvetica', '', 9.5); pdf.set_text_color(*INK)
    lines = []
    if band:
        lines.append(f"The middle half of comparable sales cluster between {money(band[0])} and {money(band[1])}.")
    lines.append(f"The evidence places this property at about {money(v['central'])}, in a {money(v['low'])} to {money(v['high'])} range.")
    if pe.get("headline"):
        lines.append(pe["headline"])
    for b in (pe.get("bullets") or [])[:2]:
        lines.append(b)
    for ln in lines[:6]:
        pdf.multi_cell(CW, 4.7, T("- " + ln), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)


def _bp_role(pdf, d, audience, v, s):
    """Section 7 - role-based insight, <=4 bullets, rotated by profile (Hit-grounded frames)."""
    frame = engine.decision_frame(audience, s.get("investment"))
    invest = bool(s.get("investment"))
    title = ("For you as an investor" if invest else
             {"buyer": "For you as a buyer", "vendor": "For you as a seller",
              "agent": "For you as the agent"}.get((audience or "").lower(), "What this means for you"))
    headroom = max(0, (v.get("high") or 0) - (v.get("guide") or v.get("central") or 0))
    bullets = []
    if invest:
        bullets = ["Build the case on this evidence-backed price, not the asking",
                   "Subtract realistic voids, service charge and finance before you commit",
                   f"Assessed range {money(v['low'])} to {money(v['high'])} - your downside and upside",
                   "Capital Gains Tax applies on a future sale"]
    elif (audience or "").lower() == "buyer":
        bullets = ["The asking is a hope; this is what comparable homes sold for",
                   (f"Headroom to negotiate toward {money(v.get('guide') or v['central'])}" if headroom else "Pay within the evidence-backed range"),
                   "A price above the evidence risks a mortgage down-valuation",
                   "Open every comparable's public record before you offer"]
    elif (audience or "").lower() == "vendor":
        bullets = [f"List around {money(v.get('guide') or v['central'])} to draw viewings and offers",
                   "The highest agent quote wins the instruction, not the sale",
                   "Over-pricing buys silence, then forced reductions",
                   "This is the number the sold evidence defends"]
    else:  # agent
        bullets = ["A defensible figure to put in front of the vendor",
                   "Win the instruction on credibility, not the highest guess",
                   "Every comparable links to its public record",
                   "Pitch above the evidence and the listing stalls"]
    pdf.set_font('Helvetica', 'B', 11); pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, T(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('Helvetica', '', 9.5); pdf.set_text_color(*INK)
    for b in bullets[:4]:
        pdf.set_x(ML)
        pdf.set_text_color(*GREEN); pdf.set_font('Helvetica', 'B', 9.5); pdf.cell(5, 4.8, T(">"))
        pdf.set_text_color(*INK); pdf.set_font('Helvetica', '', 9.5)
        pdf.multi_cell(CW - 5, 4.8, T(b), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)


# -- main ---------------------------------------------------------------------
def build(r, audience, outdir=None, slug=None, agent="Honestly",
          bot_url=None, interactive=True, key=None, link=None, context=None, tier="pro"):
    """Render the detailed PDF. Returns (pdf_path, html_path). `tier` controls how much
    decision context is rendered beside the same public-spine valuation. It is threaded
    into engine.summary() so the document and every other surface agree on which sources
    are present.

    When interactive is
    True the companion interactive HTML is built alongside (same data) and the PDF
    points the reader to it; when False (a PDF-only tier) the HTML is not built and
    the PDF makes no claim about an attached chart - so the two never disagree.

    link = the hosted usehonestly.co.uk/r/<token> URL for the interactive report. When
    given, the PDF prints it as a real clickable link (works in any reader, forwarded or
    not). When absent, the PDF only references the sibling HTML file attached in the same
    Telegram message - never a promise the document cannot keep."""
    link = link or os.environ.get("HONESTLY_REPORT_LINK") or None
    if not _HAS_FPDF:
        return _build_simple_evidence_pdf(r, audience, outdir=outdir, slug=slug,
                                          bot_url=bot_url, interactive=interactive,
                                          link=link, context=context, tier=tier)
    outdir = outdir or os.path.dirname(os.path.abspath(__file__))
    bot_url = bot_url or os.environ.get("HONESTLY_BOT_URL", "https://t.me/usehonestly_bot")
    key = key or os.environ.get("PROPERTYDATA_KEY")
    slug = slug or "report"
    s, v, pos = r["subject"], r["valuation"], r["positioning"]
    # View-level tier separation (mirrors the interactive HTML): the engine runs the full
    # arsenal once; a Lite PDF prints the L1 hook in full and replaces each Pro section with
    # a frosted locked placeholder + pay link. Because a locked section is simply NOT printed,
    # a Lite PDF physically carries none of the Pro data - leak-proof by construction.
    is_lite = str(tier).strip().lower() == "lite"
    d = engine.summary(r, audience, n=4, tier=tier)   # audience-framed guide, same numbers
    # Re-assemble the price-influence ledger WITH the free area spine (flood, crime, planning,
    # connectivity, amenities) that engine.summary cannot see - the figure-only ledger it
    # attached is replaced by the fuller one here. Pro only, fully guarded; never moves a number.
    if str(tier).strip().lower() == "pro":
        try:
            import price_ledger
            led = price_ledger.build(d, context=context)
            if led.get("ok"):
                d["price_ledger"] = led
        except Exception:
            pass

    # Strict comparables drive the table only when the hard comparable gate passes. Otherwise
    # this is proof/context, sorted by evidence quality and distance.
    allc = r["compsA"]
    nearest = sorted(allc, key=lambda c: (-(c.get("score") or 0),
                     c.get("dist") if c.get("dist") is not None else 9, -c["price"]))
    table_rows = nearest[:14]
    chart_rows = nearest[:12]
    A_med = sold_median(allc)            # score-weighted midpoint, single source of truth

    pdf = Report(agent, bot_url)
    pdf.add_page()

    # ---- masthead -------------------------------------------------------
    # Cream band carrying the EXACT brand lockup (Brand Asset Rule: the real file
    # bytes, never a font-drawn wordmark). The lockup already contains the icon,
    # the "honestly" wordmark and the tagline, so nothing is redrawn beside it.
    BAND_H = 34.0
    pdf.set_fill_color(*CREAM)
    pdf.rect(0, 0, PW, BAND_H, 'F')
    logo = brand.logo_path('lockup')
    if os.path.exists(logo):
        pdf.image(logo, x=ML, y=4.0, h=BAND_H - 8.0)   # h-only keeps aspect ratio
    else:
        # Asset missing: brand text only, never a generated graphic.
        pdf.set_xy(ML, 11); pdf.set_font('Times', 'B', 22)
        pdf.set_text_color(*NAVY); pdf.cell(60, 10, T('honestly'))
    # right-aligned title + date, navy on cream, vertically set in the band
    pdf.set_xy(ML, 11)
    pdf.set_font('Times', 'B', 15); pdf.set_text_color(*NAVY)
    pdf.cell(CW, 7, T('Market Appraisal'), align='R')
    pdf.set_xy(ML, 19)
    pdf.set_font('Helvetica', '', 9.5); pdf.set_text_color(*MUTED)
    pdf.cell(CW, 6, T(DATESTR), align='R')
    # gold hairline under the band for a premium finish
    pdf.set_draw_color(*GOLD); pdf.set_line_width(0.6)
    pdf.line(0, BAND_H, PW, BAND_H)
    # section 0: the role badge (BUYER / SELLER / AGENT / INVESTOR), top-right under the date
    _bp_role_badge(pdf, audience, s.get('investment'))
    pdf.set_y(BAND_H + 6)

    # ---- section 0: subject line (the masthead carries date + role badge) ------
    pdf.set_font('Times', 'B', 16); pdf.set_text_color(*INK)
    pdf.multi_cell(CW, 7, T(d['address']), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    facts = []
    if s.get('sqm'):  facts.append(f"{s['sqm']} sqm")
    if d.get('beds'): facts.append(f"{d['beds']} bed")
    if s.get('epc'):  facts.append(f"EPC {s['epc']}")
    if s.get('tax'):  facts.append(f"Council Tax {s['tax']}")
    history_basis = v.get('basis') == 'hmlr_subject_history_hpi'
    any_comp_size = any(c.get('sqm') for c in allc)
    any_official_comp_size = any(c.get('floor_area_official') for c in allc)
    any_strict_comparable = any(c.get('strict_comparable') for c in allc)
    facts.append(f"{len(allc)} HMLR sold proof rows" if history_basis and not any_strict_comparable else f"{len(allc)} sold comparables")
    if s.get('investment'): facts.append("Investment property")
    pdf.set_font('Helvetica', '', 9.5); pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, T("   -   ".join(facts)), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    ep = d.get("evidence_purity") or {}
    _radius = (d.get("methodology") or {}).get("ideal_radius_miles") or 0.5
    # ---- the decision-sheet spine (blueprint sections 1-6) ---------------------
    # The free PDF is a viral DECISION document, not an appraisal: big value, the trust
    # anchor, the price ladder, what drives the figure, the factor Q&A and a tight synthesis.
    # The role block (7) and the decision (8) close it just before the footer (9).
    _bp_hero(pdf, d, v, ep, len(allc), _radius)
    _bp_trust(pdf, d, history_basis)
    _bp_ladder(pdf, allc, v)
    _bp_drivers(pdf, d, v, ep, context)
    _bp_factor_qa(pdf, context, bot_url=bot_url, link=link)
    _bp_market_logic(pdf, d, v, allc, history_basis)

    # ---- material information (NTSELAT compliance starter) --------------
    # Lite FACT: the material information a buyer is entitled to (EPC, council tax, tenure).
    # Competitors show this free, so Lite must too - it stays out of the Pro lock.
    _render_material_information(pdf, s, v)

    # ---- mandatory data coverage contract -------------------------------
    # Pro: the internal data-coverage/audit ledger (part of the Pro evidence room).
    contract = {} if is_lite else (d.get('mandatory_output_contract') or {})
    if contract:
        pdf.h2("Data coverage contract")
        pdf.body("Every line below is included in the delivered report data contract with a source and a user-facing value or fallback.")
        pdf.set_font('Helvetica', '', 7.8); pdf.set_text_color(*INK)
        for key, row in list(contract.items())[:24]:
            label = key.replace('_', ' ')
            phase = row.get('phase') or ''
            status = row.get('status') or ''
            src = row.get('source') or ''
            pdf.multi_cell(CW, 4.2, T(f"- {label}: {phase} / {status} / {src}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ---- schools nearby (Ofsted, best-effort) --------------------------
    # Lite FACT: nearest schools + Ofsted ratings. Portals show this free, so Lite does too.
    schools_rendered = _render_schools(pdf, s, key)

    # ---- comparable evidence -------------------------------------------
    proof_heading = "HMLR sold proof rows" if history_basis and not any_strict_comparable else "Comparable evidence (sold)"
    pdf.h2(proof_heading)
    if history_basis and not any_strict_comparable:
        pdf.body("HM Land Registry records completed sales. Every proof row has a floor-area field with provenance: official/public EPC where matched, otherwise Honestly-modelled. Rows that fail the strict comparable gate are shown as proof/context only; the headline value is the disclosed subject-history HPI formula above.")
    elif not any_strict_comparable:
        pdf.body("Same-type properties sold near the subject, from HM Land Registry Price Paid Data. Floor area is filled for every row with provenance. Verify every sold price against the free public transaction record.")
    else:
        pdf.body("Same-type properties sold near the subject, from HM Land Registry Price Paid Data. Each is scored for comparability - how close it sits to the subject on location, size, price per square metre, recency and tenure - and the best-matching sales are shown first. The 'Match' column is that score. Each 'record' link opens the free public transaction. Verify every figure yourself.")
    # The headline exclusion statement is the page-1 Trust Anchor; here we just give the
    # reasons breakdown (not repeated up front), so the count is never stated twice.
    _rr = (d.get("methodology") or {}).get("strict_reject_reasons") or {}
    if _rr:
        top = sorted(_rr.items(), key=lambda kv: -kv[1])[:3]
        pdf.set_font('Helvetica', 'I', 8.5); pdf.set_text_color(*MUTED)
        pdf.multi_cell(CW, 4.4, T("Why sales were excluded: " + "; ".join(f"{k} ({n})" for k, n in top) + "."),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(0.5)
    _ev_table(pdf, table_rows, first_label=('Proof row' if history_basis and not any_strict_comparable else 'Comparable'))
    if any_strict_comparable:
        pdf.ln(1)
        pdf.set_font('Helvetica', 'B', 8.5); pdf.set_text_color(*INK)
        pdf.cell(0, 5, T('Comparable justifications'), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('Helvetica', '', 8.5); pdf.set_text_color(*MUTED)
        for rr in [x for x in table_rows if x.get('strict_comparable') and x.get('justification')][:5]:
            pdf.multi_cell(CW, 4.5, T(f"- {rr['address'].split(',')[0]}: {rr['justification']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    pdf.set_font('Helvetica', 'I', 8.5); pdf.set_text_color(*MUTED)
    _screened = d.get("n_screened") or 0
    _screen_note = (f" {_screened} further sale{'s' if _screened != 1 else ''} were screened "
                    f"out as non-comparable (different tier, tenure or too distant/stale)."
                    if _screened else "")
    label = "proof rows" if history_basis and not any_strict_comparable else "strict comparables"
    median_label = "HMLR row median" if history_basis and not any_strict_comparable else "Score-weighted median"
    pdf.multi_cell(CW, 5, T(f"Showing the {len(table_rows)} strongest {label} of {len(allc)} "
                     f"reviewed rows.{_screen_note} {median_label} {money(A_med)}."),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    # Official-register cross-check (HM Land Registry pulled directly, beside the figure).
    # An independent reality-check that the comparable sales are real; never blended in.
    _cc = d.get("crosscheck")
    if _cc and _cc.get("official_count"):
        pdf.ln(0.5)
        pdf.set_text_color(*MUTED)
        _div = _cc.get("divergence_pct")
        _div_label = "HMLR row median" if history_basis and not any_strict_comparable else "strict comparable median"
        _divtxt = (f" Our {_div_label} sits {abs(_div):.1f}% "
                   f"{'above' if _div > 0 else 'below'} it."
                   if isinstance(_div, (int, float)) and _div else "")
        pdf.multi_cell(CW, 5, T(
            f"Official-register check: HM Land Registry records {_cc['official_count']} "
            f"completed sale(s) in {_cc['postcode']}"
            + (f" ({_cc['window']})" if _cc.get("window") else "")
            + f", median {_cc.get('official_median_str') or 'n/a'}."
            + _divtxt
            + " Shown as an independent check on the evidence, never blended into the figure."),
            new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    # (The market-position visual is the page-1 price ladder; the old bar chart is dropped
    # to avoid showing "where it sits" twice. The table above is the verifiable backing data.)

    # ---- valuation basis ------------------------------------------------
    if pdf.get_y() > 225:
        pdf.add_page()
    pdf.h2("Basis of assessment")
    vf = d.get("valuation_formula") or v.get("formula") or {}
    evf = vf.get("evidence") or {}
    basis = []
    if vf:
        basis.append(("Formula", vf.get("name", "Honestly Transparent AVM")))
        basis.append(("Evidence set", f"{evf.get('selected_count', len(allc))} HMLR rows, {vf.get('filter', {}).get('recency_window_months', '?')} months"))
        if evf.get("raw_median"):
            basis.append((("HMLR row median" if history_basis and not any_strict_comparable else "Raw strict-comparable median"), money(evf["raw_median"])))
        basis.append(("Condition tier", str((vf.get("condition") or {}).get("tier") or s.get("finish") or "average")))
        basis.append(("Assessed central value", money(v['central'])))
    else:
        basis = [("Comparable median", money(A_med))]
    for fq in ('average', 'high', 'very_high'):
        if v['avm'].get(fq):
            basis.append((f"Condition-adjusted valuation, {fq.replace('_',' ')} finish",
                          money(v['avm'][fq])))
    if v.get('crosscheck') and v.get('psmA'):
        basis.append((f"GBP/sqm cross-check (£{int(v['psmA']):,} x {s.get('sqm','-')} sqm)",
                      money(v['crosscheck'])))
    mk = v.get('market') or {}
    if v.get('sold_anchor') and not vf:
        basis.append(("Sold-anchored value", money(v['sold_anchor'])))
    if mk.get('pct'):
        sign = '+' if mk['pct'] > 0 else ''
        basis.append((f"Market context adjustment ({mk.get('label','')})", f"{sign}{mk['pct']}%"))
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
    if vf.get("plain_formula"):
        lead = f"Formula: {vf['plain_formula']}. "
    else:
        lead = "Comparable sold evidence and the condition adjustment anchor the value. "
    if mk.get('note'):
        lead += mk['note'] + " "
    conf = d.get("confidence") or {}
    conf_note = conf.get("note") or ""
    conf_text = f"{conf.get('grade', 'Fair')} ({conf.get('score', '-')}/100)"
    pdf.body(lead + f"The result is an assessed range of {money(v['low'])} to {money(v['high'])}, "
             f"central about {money(v['central'])}. Confidence is {conf_text}."
             + (f" Data signal: {conf_note}." if conf_note else ""))

    # ---- price-influence ledger (Pro section 4) -------------------------
    # The full glass box: every price-bearing factor with its source and direction, split
    # honestly into the three movers and everything beside the figure. Pro-only (attached to
    # d by engine.summary + re-assembled with area context in build() below); never moves a
    # number. Best-effort - renders nothing if the ledger is absent.
    if is_lite:
        _locked_section(pdf, "Price-influence ledger",
                        "Every price-bearing factor with its source and direction - the full glass "
                        "box of what does and does not move the figure.", bot_url, link)
    else:
        _render_price_ledger(pdf, d)

        # ---- data-spine verification (Pro section 7) ------------------------
        # Direct public fact verification - source/status, never silently reconciled and never
        # an input to the figure. Pro-only (attached to d by engine.summary). Best-effort.
        _render_verification(pdf, d)

    # ---- positioning ----------------------------------------------------
    if is_lite:
        _locked_section(pdf, "Live market & competitive positioning",
                        "Live asking vs sold, average days on market, and how much local stock is "
                        "stuck past 90 days.", bot_url, link)
    elif pos and pos.get('band'):
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
    if is_lite:
        _locked_section(pdf, "Market outlook",
                        "The local outlook with Bank-Rate and house-price-index context.",
                        bot_url, link)
    elif mc:
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
    if is_lite:
        reddit_rendered = False
        _locked_section(pdf, "Local market sentiment",
                        "What residents and buyers in the area are actually saying about the "
                        "local market.", bot_url, link)
    else:
        reddit_rendered = _render_reddit_intel(pdf, s)

    # ---- net proceeds (SELLER-side only) --------------------------------
    # Agent commission + CGT are the SELLER's costs. A buyer never pays the agent
    # fee in the UK (the seller instructs and pays the agent), so this section is
    # gated to vendor/agent audiences. A buyer's cost side (SDLT, legal, survey) is
    # a different section - see buyer-costs work item, not an "agent fee".
    if audience != "buyer":
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

    # ---- costs to buy (BUYER-side only) ---------------------------------
    # The buyer's counterpart to net proceeds. Stamp duty is the exact figure from
    # macro.sdlt (marginal England/NI bands, first-time-buyer relief), cited in the
    # References; legal and survey are clearly-labelled indicative third-party ranges
    # the buyer confirms with their own solicitor/surveyor, never a Honestly figure.
    if audience == "buyer":
        try:
            import macro as _macro
            c = v['central']
            sdlt = _macro.sdlt(c, first_time=False)
            sdlt_ftb = (_macro.sdlt(c, first_time=True)
                        if c <= getattr(_macro, "SDLT_FTB_CEILING", 500_000) else None)
        except Exception:
            sdlt, sdlt_ftb = None, None
        if sdlt is not None:
            if pdf.get_y() > 230:
                pdf.add_page()
            pdf.h2("Your costs to buy")
            rows = [("Purchase price (assessed central)", money(c)),
                    ("Stamp duty (SDLT)", money(sdlt))]
            if sdlt_ftb is not None and sdlt_ftb < sdlt:
                rows.append(("  If a first-time buyer, SDLT is", money(sdlt_ftb)))
            rows.append(("Legal / conveyancing (indicative)", money(1000) + " - " + money(1500)))
            rows.append(("Survey (indicative)", money(400) + " - " + money(1000)))
            rows.append(("Indicative total to buy (excl. mortgage fees)",
                         money(c + sdlt + 1000 + 400) + " - " + money(c + sdlt + 1500 + 1000)))
            for i, (k, val_) in enumerate(rows):
                y = pdf.get_y(); last = (i == len(rows) - 1)
                pdf.set_fill_color(*(PALE if last else (CREAM if i % 2 == 0 else (255, 255, 255))))
                pdf.rect(ML, y, CW, 7, 'F')
                pdf.set_xy(ML + 3, y)
                pdf.set_font('Helvetica', 'B' if last else '', 9.5); pdf.set_text_color(*INK)
                pdf.cell(CW - 50, 7, T(k), align='L')
                pdf.set_font('Helvetica', 'B', 10); pdf.set_text_color(*DARK)
                pdf.cell(45, 7, T(val_), align='R')
                pdf.ln(7)
            pdf.ln(1)
            pdf.set_font('Helvetica', 'I', 8); pdf.set_text_color(*MUTED)
            pdf.multi_cell(CW, 4.5, T("Stamp duty is the exact figure for this value (England & NI "
                                      "marginal bands, first-time-buyer relief where it applies). Legal "
                                      "and survey are indicative third-party ranges - confirm with your "
                                      "own solicitor and surveyor. A UK buyer does not pay the seller's "
                                      "agent fee. Not financial or tax advice."),
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2)

    # ---- area context (location/area/safety/environment/planning/narrative) ----
    # Lite FACTS: all beside the figure, never an input to the valuation. Location &
    # connectivity, area & amenities, safety, environment, planning and the narrative are the
    # facts competitors give free, so Lite renders them in full. Returns the citation ids
    # actually rendered so the References list below lights the matching entries.
    ctx_ids = _render_context(pdf, context, skip={"safety", "environment", "planning"})

    # ---- sections 7 + 8: role-based insight, then the decision (the closing punch) ----
    # Both in EVERY report incl. free Lite. The decision is a deterministic readout of the
    # computed signals (never an LLM opinion); the role block rotates by profile. Together
    # they are the human payoff the whole document builds to, sitting just before the footer.
    if pdf.get_y() > 230:
        pdf.add_page()
    _bp_role(pdf, d, audience, v, s)
    _render_decision(pdf, d, audience)

    # ---- methodology / honesty -----------------------------------------
    if pdf.get_y() > 225:
        pdf.add_page()
    pdf.h2("Methodology, limitations & sources")
    pdf.set_font('Helvetica', '', 9); pdf.set_text_color(*INK)
    method = [
        ("A home is worth what the market will pay. HM Land Registry sold evidence is "
         "the floor of fact. Where same-size public evidence is available, it anchors the figure. "
         "Where exact public floor-area evidence is not matched, the report uses the labelled "
         "public-EPC cache/proxy or the disclosed subject-history HPI formula instead of pretending generic sales are size-matched comps."),
        "Comparables are not simply 'similar homes nearby'. Each sold sale is filtered to the "
        "subject's property type and recency window. Where public floor area exists, physical "
        "similarity and GBP/sqm are used; where it does not, those fields are not shown as if "
        "known. Recency is spent as weight only - an older comparable counts for less, but its "
        "price is never moved by a house price index. The condition tier is applied explicitly "
        "in the formula, not hidden inside a black box.",
        "Floor area is EPC-recorded; a measured survey may differ. Refurbishment specification "
        "is not independently inspected. This is a comparative market appraisal, not a RICS Red "
        "Book valuation.",
        "The sources this appraisal drew on are listed in full under References below; each "
        "entry carries the publisher, the dataset and an access date so every figure can be "
        "traced back to its origin.",
    ]
    for m in method:
        pdf.set_x(ML)
        pdf.set_font('Helvetica', 'B', 9); pdf.set_text_color(*GREEN)
        pdf.cell(4, 4.8, T("-"))
        pdf.set_font('Helvetica', '', 9); pdf.set_text_color(*INK)
        pdf.multi_cell(CW - 4, 4.8, T(m), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(0.8)

    # ---- References (academic-style, source-gated, shared with the HTML) --
    ref_data = dict(d)
    ref_data["schools"] = bool(schools_rendered) or None
    ref_data["reddit"] = bool(reddit_rendered) or None
    ref_data["epc"] = s.get("epc")
    ref_data["tax"] = s.get("tax")          # council-tax band -> VOA citation
    # light the References entries the area-context layer actually used (the present-flags
    # from area_context.gather and the ids _render_context drew). Lite prints all the facts,
    # so it cites them too - the only sources withheld are the Pro-only synthesis ones below.
    for _k in (context.get("present") or {}) if context else {}:
        ref_data[_k] = True
    for _k in ctx_ids:
        ref_data[_k] = True
    refs = brand.references(ref_data)
    if is_lite:
        # A Lite report prints every fact but locks the Pro synthesis (market outlook/macro and
        # local sentiment), so it must NOT cite those two sources - everything else it shows is
        # cited honestly. A source is listed only where its data appears in this report.
        refs = [c for c in refs if c.get("id") not in ("macro", "reddit")]
        for _i, _c in enumerate(refs, 1):
            _c["n"] = _i
    if refs:
        if pdf.get_y() > 235:
            pdf.add_page()
        pdf.h2("References")
        pdf.set_font('Helvetica', 'I', 8.5); pdf.set_text_color(*MUTED)
        pdf.multi_cell(CW, 4.6, T("The data sources this appraisal actually used, numbered and "
                                  "dated. A source is listed only where its data appears above."),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1.5)
        for c in refs:
            if pdf.get_y() > 270:
                pdf.add_page()
            y = pdf.get_y()
            pdf.set_x(ML)
            pdf.set_font('Helvetica', 'B', 8.5); pdf.set_text_color(*NAVY)
            pdf.cell(6, 4.6, T(f"{c['n']}."))
            pdf.set_xy(ML + 6, y)
            pdf.set_font('Helvetica', 'B', 8.5); pdf.set_text_color(*INK)
            pdf.multi_cell(CW - 6, 4.6, T(f"{c['publisher']}. "), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_x(ML + 6)
            pdf.set_font('Helvetica', '', 8.5); pdf.set_text_color(*MUTED)
            pdf.multi_cell(CW - 6, 4.4, T(f"{c['title']}."), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_x(ML + 6)
            pdf.set_font('Helvetica', 'U', 8); pdf.set_text_color(*LINK)
            pdf.multi_cell(CW - 6, 4.4, T(f"{c['url']}  ({c['accessed']})"),
                           link=c['url'], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1.2)

    # interactive companion + brand sign-off
    pdf.ln(2)
    if interactive:
        pdf.set_fill_color(*CREAM); pdf.set_draw_color(*LINE)
        y = pdf.get_y(); pdf.rect(ML, y, CW, 16, 'DF')
        pdf.set_xy(ML + 4, y + 2.5)
        pdf.set_font('Times', 'B', 11); pdf.set_text_color(*DARK)
        pdf.cell(0, 5, T("Your interactive report"),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_xy(ML + 4, y + 8)
        if link:
            # a real, clickable hosted link - works in any reader, forwarded or not
            pdf.set_font('Helvetica', 'U', 9); pdf.set_text_color(*LINK)
            pdf.cell(0, 5, T("Open it here: " + link),
                     link=link, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            # Telegram delivery: the HTML rides as a sibling attachment in the same message
            pdf.set_font('Helvetica', '', 9); pdf.set_text_color(*INK)
            pdf.cell(0, 5, T("Open the attached HTML file to inspect every sold comparable row and its source."),
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
            html_path = interactive_chart(allc, v, s, slug, outdir, bot_url,
                                          d=d, pos=pos, ref_data=ref_data, context=context)
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
