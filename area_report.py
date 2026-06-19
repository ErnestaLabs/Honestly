#!/usr/bin/env python3
"""area_report.py - the FREE downloadable PDF for a blog district report.

The lead magnet. Every published district page on the blog can be downloaded as a
branded PDF, in exchange for the reader's details (the gate lives in server.py). The
PDF is built PURELY from the stored blog `model` dict - no API calls, no network - so
it is fast, reproducible and can be generated on demand from store.get_blog_post().

This is the BLOG deliverable, not the paid appraisal (report.py). The difference is the
honesty posture: this report issues NO valuation. It reports what the market actually
did - HM Land Registry sold prices, live listings and the UK House Price Index, side by
side and never blended - exactly like the web page it mirrors. It reuses blog.py's own
figure helpers (money/pct/_answer_paragraph/_references) so the PDF and the page can
never quote different numbers, and it borrows report.py's fpdf2 styling vocabulary
(cp1252-safe text, cream panels, Times headings, navy/green/gold palette).

  build(model) -> bytes        # the PDF, ready to stream or persist
"""
import os
try:
    from fpdf import FPDF, XPos, YPos
    _HAS_FPDF = True
except ImportError:  # optional in this harness; keep the module importable
    from types import SimpleNamespace
    _HAS_FPDF = False
    class FPDF:
        def __getattr__(self, name):
            raise RuntimeError("fpdf2 is not installed")
    XPos = SimpleNamespace(LMARGIN=None)
    YPos = SimpleNamespace(NEXT=None)
import brand
import blog
from blog import money, money_short, pct, _district_name, _answer_paragraph

# brand palette - single-sourced from brand.py (same as report.py)
NAVY  = brand.RGB["navy"]
GREEN = brand.RGB["green"]
TEAL  = brand.RGB["teal"]
GOLD  = brand.RGB["gold"]
SAND  = brand.RGB["sand"]
CREAM = brand.RGB["cream"]
PAPER = brand.RGB["paper"]
INK   = brand.RGB["ink"]
MUTED = brand.RGB["muted"]
LINE  = brand.RGB["line"]
PALE  = brand.RGB["pale"]
WHITE = (255, 255, 255)

PW = 210.0
ML = 16.0
CW = PW - 2 * ML

# cp1252 glyph sanitiser - core PDF fonts speak cp1252, and house style bans em dashes.
_SUBST = {'–': '-', '—': '-', '‒': '-', '−': '-', '→': 'to', '←': '<-', '•': '-',
          '·': '-', '≈': '~', '‘': "'", '’': "'", '“': '"', '”': '"', '…': '...',
          ' ': ' ', ' ': ' ', '✕': 'x', '✓': 'ok', '²': '2', '£': '£', '&': '&'}


def T(s):
    """Map the few typographic glyphs we emit to plain cp1252 equivalents (never an em
    dash), then drop anything else safely. The pound sign survives."""
    import html as _html
    s = _html.unescape(str(s))          # model prose is plain, but be safe with entities
    for k, v in _SUBST.items():
        s = s.replace(k, v)
    return s.encode('cp1252', 'replace').decode('cp1252')


class AreaReport(FPDF):
    def __init__(self, model):
        super().__init__('P', 'mm', 'A4')
        self.model = model
        self.city = model.get("city") or {}
        self.district = model.get("district") or ""
        self.series = self.city.get("series") or "Property market report"
        self.set_auto_page_break(True, margin=18)
        self.set_margins(ML, 14, ML)
        self.set_title(T(f"{self.district} House Prices and Property Market Report"))
        self.set_author("Honestly")

    # running header on continuation pages (page 1 carries the full masthead instead)
    def header(self):
        if self.page_no() == 1:
            return
        self.set_y(8)
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
        self.cell(0, 6, T(f'{self.district} market report  -  {brand.DATESTR}'),
                  align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*LINE); self.set_line_width(0.3)
        self.line(ML, 16, PW - ML, 16)
        self.set_y(22)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(*LINE); self.set_line_width(0.3)
        self.line(ML, self.get_y(), PW - ML, self.get_y())
        self.set_y(-11.5)
        self.set_font('Helvetica', '', 7.3)
        self.set_text_color(*MUTED)
        self.cell(0, 5, T('HM Land Registry sold prices, live listings and the UK House Price '
                          'Index, side by side and never blended. We issue no valuation.'),
                  align='L')
        self.cell(0, 5, T(f'Page {self.page_no()}'), align='R')

    # -- building blocks -----------------------------------------------------
    def h2(self, txt):
        if self.get_y() > 250:
            self.add_page()
        self.ln(2)
        self.set_font('Times', 'B', 14)
        self.set_text_color(*NAVY)
        self.cell(0, 8, T(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*GREEN); self.set_line_width(0.5)
        y = self.get_y() + 0.5
        self.line(ML, y, ML + 26, y)
        self.ln(3)

    def body(self, txt, h=5.0, size=10, color=None):
        self.set_font('Helvetica', '', size)
        self.set_text_color(*(color or INK))
        self.multi_cell(CW, h, T(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def kv_panel(self, rows):
        """A soft cream panel of label / value pairs (the headline facts)."""
        rows = [r for r in rows if r[1] not in (None, "", "n/a")]
        if not rows:
            return
        self.set_draw_color(*LINE); self.set_fill_color(*CREAM)
        top = self.get_y()
        rh = 8.0
        self.rect(ML, top, CW, rh * len(rows), 'DF')
        for i, row in enumerate(rows):
            k, v = row[0], row[1]
            big = row[2] if len(row) > 2 else False
            y = top + i * rh
            self.set_xy(ML + 4, y)
            self.set_font('Helvetica', '', 9.5)
            self.set_text_color(*MUTED)
            self.cell(70, rh, T(k), align='L')
            self.set_xy(ML + 74, y)
            if big:
                self.set_font('Times', 'B', 13); self.set_text_color(*NAVY)
            else:
                self.set_font('Helvetica', 'B', 10.5); self.set_text_color(*INK)
            self.cell(CW - 78, rh, T(v), align='L')
            if i:
                self.set_draw_color(*LINE)
                self.line(ML + 2, y, ML + CW - 2, y)
        self.set_xy(ML, top + rh * len(rows))
        self.ln(5)

    def table(self, caption, cols, rows, links=None, link_first=False):
        """Generic striped table. cols = [(header, width_mm_or_0, align)]; a width of 0
        flexes to fill. rows = list of tuples of pre-formatted strings (same length as
        cols). links (optional) = list mapping row index -> a URL for the LAST column;
        set link_first=True to also make that row's FIRST column the same link."""
        rows = [r for r in rows if r]
        if not rows:
            return
        self._table_caption(caption)
        self._table_head(cols)
        fill = False
        for ri, r in enumerate(rows):
            if self.get_y() > 262:
                self.add_page()
                self._table_head(cols)
                fill = False
            y = self.get_y()
            self.set_fill_color(*(CREAM if fill else WHITE))
            self.rect(ML, y, CW, 6.4, 'F')
            x = ML
            last = len(cols) - 1
            url = (links or {}).get(ri) if links else None
            for ci, (name, w, align) in enumerate(cols):
                ww = w if w else (ML + CW - x)
                self.set_xy(x, y)
                if url and (ci == last or (ci == 0 and link_first)):
                    self.set_font('Helvetica', 'U', 8.3); self.set_text_color(*GREEN)
                    self.cell(ww, 6.4, T(r[ci]), align=align, link=url)
                    self.set_text_color(*INK)
                else:
                    self.set_font('Helvetica', '', 8.5)
                    self.set_text_color(*INK)
                    self.cell(ww, 6.4, T(r[ci]), align=align)
                x += ww
            self.ln(6.4)
            fill = not fill
        self.ln(2)

    def _table_caption(self, caption):
        if not caption:
            return
        self.set_font('Helvetica', 'B', 9)
        self.set_text_color(*MUTED)
        self.cell(0, 5.5, T(caption.upper()), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(0.5)

    def _table_head(self, cols):
        self.set_font('Helvetica', 'B', 8.5)
        self.set_fill_color(*NAVY); self.set_text_color(*WHITE)
        x = ML
        y = self.get_y()
        for name, w, align in cols:
            ww = w if w else (ML + CW - x)
            self.set_xy(x, y)
            self.cell(ww, 7, T(name), align=align, fill=True)
            x += ww
        self.ln(7)

    def bullets(self, title, items):
        items = [i for i in items if i]
        if not items:
            return
        self.set_font('Helvetica', 'B', 10.5)
        self.set_text_color(*NAVY)
        self.cell(0, 6, T(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font('Helvetica', '', 9.5)
        self.set_text_color(*INK)
        for it in items:
            x = ML
            self.set_xy(x, self.get_y())
            self.set_text_color(*GREEN)
            self.cell(4, 5, T('-'), align='L')
            self.set_text_color(*INK)
            self.multi_cell(CW - 4, 5, T(it), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def leg_line(self, prefix, name, tail, place_url, dir_url=None):
        """One connectivity line where only the place name (and an optional Directions
        affordance) are links - the rest stays plain text on the same row."""
        self.set_xy(ML, self.get_y())
        self.set_font('Helvetica', '', 9.5)
        self.set_text_color(*GREEN)
        self.cell(4, 5, T('-'), align='L')
        self.set_text_color(*INK)
        if prefix:
            seg = T(prefix + ": ")
            self.cell(self.get_string_width(seg) + 0.5, 5, seg, align='L')
        self.set_font('Helvetica', 'U', 9.5); self.set_text_color(*GREEN)
        nm = T(name)
        self.cell(self.get_string_width(nm) + 0.5, 5, nm, align='L', link=place_url)
        self.set_font('Helvetica', '', 9.5); self.set_text_color(*INK)
        if tail:
            tl = T(tail)
            self.cell(self.get_string_width(tl) + 0.5, 5, tl, align='L')
        if dir_url:
            self.cell(2, 5, '', align='L')
            self.set_font('Helvetica', 'U', 9.5); self.set_text_color(*TEAL)
            dd = T("Directions >")
            self.cell(self.get_string_width(dd) + 0.5, 5, dd, align='L', link=dir_url)
            self.set_font('Helvetica', '', 9.5); self.set_text_color(*INK)
        self.ln(5)


# ---- the masthead (page 1) -------------------------------------------------
def _masthead(pdf):
    """A cream band carrying the EXACT brand lockup (never recreated) + the date."""
    band_h = 30.0
    pdf.set_fill_color(*CREAM)
    pdf.rect(0, 0, PW, band_h, 'F')
    pdf.set_draw_color(*GOLD); pdf.set_line_width(1.0)
    pdf.line(0, band_h, PW, band_h)
    lockup = brand.logo_path('lockup')
    placed = False
    if os.path.exists(lockup):
        try:
            pdf.image(lockup, x=ML, y=7.5, h=15.0)
            placed = True
        except Exception:
            placed = False
    if not placed:
        # Brand Asset Rule: never recreate the logo - fall back to the NAME in text only.
        pdf.set_xy(ML, 10)
        pdf.set_font('Times', 'B', 20); pdf.set_text_color(*NAVY)
        pdf.cell(0, 10, T('honestly'))
    pdf.set_xy(PW - ML - 70, 11.5)
    pdf.set_font('Helvetica', '', 8.5); pdf.set_text_color(*MUTED)
    pdf.cell(70, 5, T(brand.DATESTR), align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_xy(PW - ML - 70, 16.5)
    pdf.set_font('Helvetica', '', 8.5); pdf.set_text_color(*MUTED)
    pdf.cell(70, 5, T('A defensible value from sold evidence'), align='R')
    pdf.set_y(band_h + 7)


def _hero(pdf, model):
    """The headline: the scope-honest median, big, with the quotable answer beneath it."""
    s = model.get("sold") or {}
    title = f"{model['district']} House Prices and Property Market"
    pdf.set_font('Helvetica', 'B', 8.5); pdf.set_text_color(*GREEN)
    pdf.cell(0, 5, T(model.get("city", {}).get("series", "Property market report").upper()),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(0.5)
    pdf.set_font('Times', 'B', 22); pdf.set_text_color(*NAVY)
    pdf.multi_cell(CW, 9, T(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('Helvetica', '', 9.5); pdf.set_text_color(*MUTED)
    pdf.cell(0, 5.5, T(f"{_district_name(model)}  -  Updated {model.get('generated_at', brand.DATESTR)}"),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)
    if s.get("ok") and s.get("median_price"):
        pdf.set_font('Times', 'B', 30); pdf.set_text_color(*GREEN)
        pdf.cell(0, 13, T(money(s["median_price"])), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        sub = "median recorded sale price, across all property types"
        if s.get("psm_median"):
            sub += f"  -  about {money(s['psm_median'])} per square metre"
        pdf.set_font('Helvetica', '', 9.5); pdf.set_text_color(*MUTED)
        pdf.cell(0, 5.5, T(sub), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
    # the quotable answer paragraph - identical text to the web page's answer box. Rendered
    # as an indented blockquote with a green left rule (no fragile box-height arithmetic).
    answer = _answer_paragraph(model)
    pdf.set_font('Helvetica', '', 10); pdf.set_text_color(*INK)
    top = pdf.get_y()
    pdf.set_xy(ML + 5, top)
    pdf.multi_cell(CW - 5, 5.0, T(answer), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    bottom = pdf.get_y()
    pdf.set_draw_color(*GREEN); pdf.set_line_width(1.3)
    pdf.line(ML + 1.5, top + 0.8, ML + 1.5, bottom - 1.0)
    pdf.ln(3)


def _kpis(pdf, model):
    s = model.get("sold") or {}
    l = model.get("listings") or {}
    h = model.get("hpi") or {}
    rt = model.get("rent") or {}
    rows = []
    if s.get("ok"):
        rows.append(("Median sale price (all types)", money(s.get("median_price")), True))
        if s.get("psm_median"):
            rows.append(("Median price per square metre", money(s["psm_median"]), False))
        rec = s.get("recency", {})
        rows.append(("Sales on record", f"{s.get('total','-')} over {rec.get('window_months',24)} months "
                                        f"({rec.get('last_12m','-')} in the last year)", False))
        if s.get("price_low") and s.get("price_high"):
            rows.append(("Recorded price range", f"{money(s['price_low'])} to {money(s['price_high'])}", False))
    if l.get("ok"):
        rows.append(("Live asking median", f"{money(l.get('asking_median'))} ({l.get('n','-')} on the market)", False))
        if l.get("mean_dom") is not None:
            rows.append(("Average days on market", f"{l.get('mean_dom','-')} days "
                         f"({l.get('stuck_n','-')} stuck 90+ days, {l.get('under_offer_n','-')} under offer)", False))
    if rt.get("ok") and rt.get("headline_yield") is not None:
        wk = rt.get("headline_weekly")
        v = f"{rt['headline_yield']}% gross"
        if wk:
            v = f"{money(wk)}/week  -  {v}"
        rows.append(("Typical rent and gross yield", v, False))
    if h.get("ok") and h.get("annual_change_pct") is not None:
        rows.append((f"{model['city']['name']} index (UK HPI)",
                     f"{pct(h['annual_change_pct'])} year on year, {money(h.get('average_price'))} avg "
                     f"({h.get('month','')})", False))
    pdf.kv_panel(rows)


def _sold(pdf, model):
    s = model.get("sold") or {}
    if not s.get("ok"):
        return
    pdf.h2(f"Sold prices in {model['district']}")
    rec = s.get("recency", {})
    pdf.body(
        f"Across the last {rec.get('window_months',24)} months, {s.get('total','-')} sales are "
        f"on record in {model['district']} - a median of {money(s.get('median_price'))}, ranging "
        f"{money(s.get('price_low'))} to {money(s.get('price_high'))}. "
        f"{rec.get('last_12m','-')} sales completed in the last 12 months. These are HM Land "
        f"Registry Price Paid Data, the official record of what actually changed hands.")
    cols = [("Property type", 0, 'L'), ("Sales", 22, 'R'),
            ("Median price", 38, 'R'), ("Median /m2", 34, 'R')]
    rows = []
    for bt in s.get("by_type", []):
        if not bt.get("n"):
            continue
        rows.append((bt.get("label", bt.get("type", "")), str(bt["n"]),
                     money(bt.get("median")),
                     money(bt.get("psm_median")) if bt.get("psm_median") else "-"))
    pdf.table("Sold price by property type", cols, rows)
    beds = s.get("beds_mix") or {}
    if beds:
        brows = [(f"{k}-bed", str(v)) for k, v in beds.items()]
        pdf.table("Bedroom mix of recorded sales",
                  [("Size", 0, 'L'), ("Sales", 30, 'R')], brows)


def _evidence(pdf, model):
    s = model.get("sold") or {}
    sample = s.get("sample") or []
    if not sample:
        return
    pdf.h2("Recent transaction evidence")
    pdf.body(f"The most recent recorded sales in {model['district']}. Every row is a real "
             f"registered transaction; the record link opens the underlying entry.")
    cols = [("Date", 24, 'L'), ("Price", 30, 'R'), ("Type", 0, 'L'),
            ("m2", 18, 'R'), ("/m2", 26, 'R'), ("Verify", 22, 'C')]
    rows, links = [], {}
    for i, r in enumerate(sample):
        rows.append((r.get("date") or "", money(r.get("price")),
                     (r.get("type") or "").replace("_", " "),
                     str(r.get("sqm") or ""),
                     money(r.get("psm")) if r.get("psm") else "",
                     "record" if r.get("url") else ""))
        if r.get("url"):
            links[i] = r["url"]
    pdf.table("Most recent recorded sales", cols, rows, links=links)


def _live(pdf, model):
    l = model.get("listings") or {}
    if not l.get("ok"):
        return
    pdf.h2("The live market right now")
    pdf.body(
        f"There are {l.get('n','-')} properties currently on the market in {model['district']}, "
        f"at a median asking price of {money(l.get('asking_median'))} "
        f"({money(l.get('asking_low'))} to {money(l.get('asking_high'))}). They have been listed "
        f"for an average of {l.get('mean_dom','-')} days. Asking prices signal vendor "
        f"expectation - they are context, not evidence of value, and are never blended with "
        f"the sold record above.")
    cols = [("Measure", 0, 'L'), ("Count", 36, 'R')]
    rows = [("On the market", str(l.get("n", "-"))),
            ("Available (not under offer)", str(l.get("available_n", "-"))),
            ("Fresh (20 days or less)", str(l.get("fresh_n", "-"))),
            ("Stuck (90+ days)", str(l.get("stuck_n", "-"))),
            ("Under offer", str(l.get("under_offer_n", "-")))]
    pdf.table("Live on-market dynamics", cols, rows)


def _rent(pdf, model):
    rt = model.get("rent") or {}
    if not rt.get("ok") or not rt.get("rows"):
        return
    pdf.h2("What it rents for, and the yield")
    hw, hy = rt.get("headline_weekly"), rt.get("headline_yield")
    lead = []
    if hw:
        lead.append(f"Typical long-let asking rent in {model['district']} runs around "
                    f"{money(hw)} a week ({money(round(hw * 52 / 12))} a month)")
    if hy is not None:
        lead.append(f"a gross rental yield of about {hy}%")
    intro = (", ".join(lead) + ". ") if lead else ""
    pdf.body(intro + "Rent here is live long-let asking data, and the gross yield is "
             "PropertyData's own estimate - a year's rent as a share of price, before letting "
             "costs, voids and tax. It is market context, not a valuation of any property.")
    cols = [("Type", 0, 'L'), ("Per week", 28, 'R'), ("Per month", 30, 'R'),
            ("Gross yield", 28, 'R'), ("Listings", 22, 'R')]
    rows = []
    for r in rt["rows"]:
        rows.append((f"{r.get('beds','')}-bed {str(r.get('label','')).lower()}",
                     money(r["weekly"]) if r.get("weekly") else "n/a",
                     money(r["monthly"]) if r.get("monthly") else "n/a",
                     f"{r['gross_yield']}%" if r.get("gross_yield") is not None else "n/a",
                     str(r.get("rent_n") or r.get("yield_n") or 0)))
    pdf.table("Typical rent and gross yield by property type", cols, rows)


def _audiences(pdf, model):
    """Three reads of the SAME numbers - buyers, sellers, investors. No new figures."""
    s = model.get("sold") or {}
    l = model.get("listings") or {}
    h = model.get("hpi") or {}
    rt = model.get("rent") or {}
    buyer, seller, invest = [], [], []
    if l.get("ok") and s.get("ok") and l.get("asking_median") and s.get("median_price"):
        gap = l["asking_median"] - s["median_price"]
        if gap > 0:
            buyer.append(f"Asking prices sit {money(gap)} above the median sale - there is room "
                         f"between what sellers want and what completes.")
            seller.append(f"The median sale is {money(s['median_price'])}; price to the evidence, "
                          f"not to the {money(l['asking_median'])} asking median, or you risk "
                          f"joining the {l.get('stuck_n','-')} stuck listings.")
        else:
            buyer.append("Asking prices are at or below the median sale - competition is real; "
                         "offers near asking are the norm.")
    if l.get("ok") and l.get("mean_dom") is not None:
        fast = l["mean_dom"] < 45
        buyer.append(f"Average time on market is {l['mean_dom']} days - "
                     + ("a fast market, move decisively." if fast
                        else "a measured pace, there is time to do diligence."))
        seller.append(f"Expect roughly {l['mean_dom']} days to a sale at the right price.")
    if s.get("ok") and s.get("psm_median"):
        invest.append(f"The blended sold rate is {money(s['psm_median'])} per square metre - your "
                      f"per-m2 entry price is the cleanest cross-district comparison.")
    if s.get("ok") and s.get("recency"):
        invest.append(f"{s['recency'].get('last_12m','-')} sales in the last year signals "
                      f"liquidity - how easily you could exit.")
    if rt.get("ok") and rt.get("headline_yield") is not None:
        invest.append(f"Gross rental yield is running near {rt['headline_yield']}% - before "
                      f"letting costs and voids, not a guaranteed return.")
    if h.get("ok") and h.get("annual_change_pct") is not None:
        invest.append(f"The wider {model['city']['name']} index is {pct(h['annual_change_pct'])} "
                      f"year on year (context, not a forecast).")
    if not (buyer or seller or invest):
        return
    pdf.h2("What the numbers mean for you")
    pdf.bullets("If you are buying", buyer)
    pdf.bullets("If you are selling", seller)
    pdf.bullets("If you are investing", invest)


def _area(pdf, model):
    a = model.get("area") or {}
    ll = blog._latlng(model)
    cityname = (model.get("city") or {}).get("name") or ""
    loc = a.get("location") or {}
    legs = loc.get("rows") or loc.get("legs") or []
    am = a.get("area") or {}
    sf = a.get("safety") or {}
    env = a.get("environment") or {}
    pl = a.get("planning") or {}
    has = (legs or (am.get("ok") and am.get("counts")) or sf.get("ok")
           or env or pl.get("ok"))
    if not has:
        return
    pdf.h2("Area intelligence")

    # Connectivity - the station name links to the map; Directions routes from the centroid.
    if legs:
        pdf.set_font('Helvetica', 'B', 10.5); pdf.set_text_color(*NAVY)
        pdf.cell(0, 6, T("Connectivity"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        for x in legs:
            label = x.get("label", "")
            prefix, name = (label.rsplit(": ", 1) if ": " in label else ("", label))
            is_station = "station" in label.lower()
            dest = name + (" station" if is_station and "station" not in name.lower() else "")
            dest_q = dest + (", " + cityname if cityname else "")
            tail = ""
            if x.get("dist"):
                tail += f" - {x['dist']}"
            if x.get("time"):
                tail += f", {x['time']}"
            pdf.leg_line(prefix, name, tail, blog._gmap_place(dest_q),
                         (blog._gmap_dir(ll, dest_q) if ll else None))
        pdf.ln(2)

    # Amenities - each category links to a map of that category centred on the postcode.
    if am.get("ok") and am.get("counts"):
        rows, links = [], {}
        for i, (k, v) in enumerate(am["counts"].items()):
            rows.append((str(k), str(v)))
            if ll:
                q = blog._AMENITY_QUERY.get(k) or k.replace(" &", "").lower()
                links[i] = blog._gmap_browse(ll, q)
        pdf.table("Amenities within 800m", [("", 0, 'L'), ("", 30, 'R')], rows,
                  links=(links or None), link_first=True)
        if ll:
            pdf.set_font('Helvetica', '', 8); pdf.set_text_color(*MUTED)
            pdf.cell(0, 5, T("Each category links to the map."),
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)

    if sf.get("ok"):
        rows = [(str(c), str(n)) for c, n in (sf.get("by_category") or [])[:6]]
        note = (f"{sf.get('total','-')} crimes recorded {sf.get('month','')} "
                f"{sf.get('radius_note','')}.")
        pdf.bullets("Safety", [note])
        pdf.table("", [("", 0, 'L'), ("", 30, 'R')], rows)

    if env:
        lines = []
        if env.get("flood", {}).get("ok"):
            lines += env["flood"].get("lines", [])
        if env.get("air", {}).get("ok"):
            lines += env["air"].get("lines", [])
        if lines:
            pdf.bullets("Environment", lines)

    if pl.get("ok"):
        st = "; ".join(f"{s} {n}" for s, n in (pl.get("by_status") or [])[:4])
        pdf.bullets("Planning and development",
                    [f"{pl.get('total','-')} recent applications within ~0.5km. {st}."])


def _context(pdf, model):
    h = model.get("hpi") or {}
    if not h.get("ok"):
        return
    pdf.h2("Wider market context")
    pdf.body(
        f"The UK House Price Index for {model['city']['name']} stands at an average of "
        f"{money(h.get('average_price'))} in {h.get('month','')}, {pct(h.get('annual_change_pct'))} "
        f"over the year and {pct(h.get('monthly_change_pct'))} over the month. This is the "
        f"regional index - it sits beside the {model['district']} figures as background and "
        f"never moves a local price. The transaction figures above are what actually happened "
        f"in this postcode.")


def _references(pdf, model):
    refs = _ref_list(model)
    if not refs:
        return
    pdf.h2("References")
    pdf.set_font('Helvetica', '', 8.8)
    for c in refs:
        n = c["n"]
        self_x = ML
        pdf.set_text_color(*NAVY); pdf.set_font('Helvetica', 'B', 8.8)
        pdf.set_xy(self_x, pdf.get_y())
        pdf.cell(7, 4.6, T(f"{n}."), align='L')
        pdf.set_font('Helvetica', '', 8.8); pdf.set_text_color(*INK)
        txt = f"{c['publisher']}. {c['title']}. {c['url']} ({c['accessed']})."
        pdf.set_xy(self_x + 7, pdf.get_y())
        pdf.multi_cell(CW - 7, 4.6, T(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(0.6)


# blog._references is shadowed by the method above at module import via the `from blog
# import _references` line; keep an explicit handle to the blog builder to avoid confusion.
_ref_list = blog._references


def _closing(pdf, model):
    pdf.ln(3)
    pdf.set_draw_color(*GOLD); pdf.set_line_width(0.6)
    pdf.line(ML, pdf.get_y(), ML + 26, pdf.get_y())
    pdf.ln(3)
    pdf.set_font('Times', 'B', 12); pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, T("This report is free, and so is every report in this series."),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('Helvetica', '', 9.5); pdf.set_text_color(*INK)
    pdf.multi_cell(CW, 5, T(
        "We rebuild a fresh postcode-district report for each major UK city every day, from "
        "official data, and issue no valuation on any of them. When you want this same "
        "sold-evidence treatment for one specific address - your own home, or one you are "
        "buying - that runs on Telegram."), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    pdf.set_font('Helvetica', 'B', 10); pdf.set_text_color(*GREEN)
    bot = getattr(blog, "BOT", "https://t.me/")
    pdf.cell(0, 6, T("Value your own address on Telegram"), link=bot,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def build(model):
    """Render the free area-report PDF for a stored blog model. Returns PDF bytes.

    Pure: reads only the model dict (no network, no API). Numbers come from blog.py's
    own helpers so this PDF and the web page can never disagree."""
    pdf = AreaReport(model)
    pdf.add_page()
    _masthead(pdf)
    _hero(pdf, model)
    _kpis(pdf, model)
    _sold(pdf, model)
    _evidence(pdf, model)
    _live(pdf, model)
    _rent(pdf, model)
    _audiences(pdf, model)
    _area(pdf, model)
    _context(pdf, model)
    _references(pdf, model)
    _closing(pdf, model)
    out = pdf.output()
    return bytes(out)


def filename(model):
    """A clean download filename for the report, e.g. 'honestly-B1-market-report.pdf'."""
    d = (model.get("district") or "area").replace(" ", "")
    return f"honestly-{d}-market-report.pdf"


if __name__ == "__main__":
    # selftest: build a PDF from a synthetic-but-realistic model, write it next to here.
    demo = {
        "district": "B1", "slug": "birmingham-b1", "generated_at": brand.DATESTR,
        "city": {"name": "Birmingham", "slug": "birmingham", "series": "The Birmingham Daily"},
        "present": {"pd_sold": 1, "pd_listings": 1, "pd_rent": 1, "hmlr_direct": 1},
        "sold": {"ok": True, "median_price": 232500, "psm_median": 3650, "total": 477,
                 "price_low": 92000, "price_high": 695000,
                 "recency": {"window_months": 24, "last_12m": 188},
                 "by_type": [{"type": "flat", "label": "Flat", "n": 410, "median": 215000, "psm_median": 3720},
                             {"type": "terraced_house", "label": "Terraced house", "n": 41, "median": 305000, "psm_median": 3100}],
                 "beds_mix": {"1": 120, "2": 240, "3": 90},
                 "sample": [{"date": "2026-03-14", "price": 245000, "type": "flat", "sqm": 64, "psm": 3828,
                             "url": "https://landregistry.data.gov.uk/"},
                            {"date": "2026-02-28", "price": 198000, "type": "flat", "sqm": 52, "psm": 3808, "url": None}]},
        "listings": {"ok": True, "n": 156, "asking_median": 250000, "asking_low": 110000,
                     "asking_high": 800000, "mean_dom": 71, "available_n": 132, "fresh_n": 24,
                     "stuck_n": 38, "under_offer_n": 24},
        "rent": {"ok": True, "headline_weekly": 320, "headline_yield": 6.4,
                 "rows": [{"beds": 1, "label": "Flat", "weekly": 280, "monthly": 1213, "gross_yield": 6.8, "rent_n": 60},
                          {"beds": 2, "label": "Flat", "weekly": 360, "monthly": 1560, "gross_yield": 6.1, "rent_n": 80}]},
        "hpi": {"ok": True, "average_price": 245000, "month": "April 2026",
                "annual_change_pct": 2.4, "monthly_change_pct": 0.3},
        "area": {}}
    data = build(demo)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "area_report_selftest.pdf")
    with open(out, "wb") as f:
        f.write(data)
    print(f"area_report selftest OK - {len(data):,} bytes -> {out}")
