# -*- coding: utf-8 -*-
"""product_html.py - Render catalogue.build() output as a standalone branded HTML document.

Every product purchased from the Honestly workspace becomes a hosted page at /p/<share_token>.
The user can open it in the Telegram browser, bookmark it, print it, and come back to it from
the Library tab. Not a Telegram message - a real document.

`render(title, blurb, content, address, profile)` -> HTML string.
"""
import html as _html
import datetime
import re as _re

_CSS = """
:root{--green:#15807f;--navy:#0e2747;--teal:#2aa39a;--gold:#d89a32;
      --ink:#1c1a16;--mut:#6b6557;--line:#e7e1d4;--bg:#f6f3ec;--paper:#fbf9f4;
      --disp:"Fraunces",Georgia,"Times New Roman",serif}
*{box-sizing:border-box;margin:0;padding:0}
html{font:16px/1.65 -apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg);
     -webkit-font-smoothing:antialiased}
body{max-width:740px;margin:0 auto;padding:28px 18px 60px}
.hdr{display:flex;align-items:center;gap:10px;margin-bottom:24px;padding-bottom:16px;
     border-bottom:2px solid var(--line)}
.logo{height:26px;width:auto}
.mark{height:19px;width:auto}
.badge{display:inline-block;background:var(--navy);color:#fff;font-size:11px;font-weight:800;
       text-transform:uppercase;letter-spacing:.06em;padding:3px 10px;border-radius:20px;margin:0 0 12px}
h1.doc-title{font:700 26px/1.2 var(--disp);color:var(--navy);margin:0 0 6px;letter-spacing:-.5px}
.doc-addr{font-size:15px;color:var(--mut);margin:0 0 4px}
.doc-blurb{font-size:14px;color:var(--mut);margin:0 0 24px;font-style:italic}
hr.div{border:0;border-top:2px solid var(--line);margin:22px 0}
h2{font:700 18px/1.3 var(--disp);color:var(--navy);margin:24px 0 10px;padding-bottom:6px;
   border-bottom:1px solid var(--line)}
h3{font:600 15px/1.3 var(--disp);color:var(--teal);margin:16px 0 8px}
p{margin:0 0 10px;font-size:15px;line-height:1.65}
ul{margin:0 0 14px;padding:0;list-style:none}
ul li{padding:7px 0 7px 24px;position:relative;font-size:15px;
      border-bottom:1px solid var(--line);line-height:1.55}
ul li:last-child{border:0}
ul li::before{content:"▪";position:absolute;left:0;top:8px;color:var(--green);font-weight:800}
.flag{background:#fef6ed;border-left:3px solid var(--gold);padding:11px 14px;margin:10px 0;
      border-radius:0 8px 8px 0;font-size:14px;line-height:1.55}
.risk{background:#fbeee7;border-left:3px solid #c0392b;padding:11px 14px;margin:10px 0;
      border-radius:0 8px 8px 0;font-size:14px;line-height:1.55}
.ok{background:#e8f1ee;border-left:3px solid var(--green);padding:11px 14px;margin:10px 0;
    border-radius:0 8px 8px 0;font-size:14px;line-height:1.55}
.question{background:#f0f4ff;border-left:3px solid #4466cc;padding:11px 14px;margin:10px 0;
          border-radius:0 8px 8px 0;font-size:14px;line-height:1.55}
.cite{font-size:12px;color:var(--mut);font-style:italic;margin:16px 0 0;padding-top:12px;
      border-top:1px dashed var(--line);line-height:1.6}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:14px 0}
.stat{background:#fff;border:1px solid var(--line);border-radius:11px;padding:13px 14px}
.stat .sv{font:700 22px/1 var(--disp);color:var(--green);margin:0 0 4px}
.stat .sk{font-size:12px;color:var(--mut)}
.ftr{margin-top:44px;padding-top:16px;border-top:2px solid var(--line);font-size:12px;
     color:var(--mut);text-align:center;line-height:1.7}
.ftr a{color:var(--mut)}
@media print{body{padding:10px}.hdr{margin-bottom:12px}}
"""

_PROFILE_LABEL = {
    "buyer": "Buyer", "seller": "Seller / Vendor", "vendor": "Seller / Vendor",
    "agent": "Estate Agent", "investor": "Investor",
}


def _esc(s):
    return _html.escape(str(s))


def _md_clean(line):
    """Strip raw markdown and template artifacts from a line before HTML rendering.
    Converts **bold** -> <b>bold</b>, *italic* -> <i>italic</i>, ## Heading -> <b>Heading</b>,
    and drops {{...}} / {%...%} / stray }} {{ template artifacts."""
    s = str(line)
    # Drop Jinja/template artifacts: {{...}}, {%...%}, stray }} or {{
    s = _re.sub(r'\{\{.*?\}\}', '', s)
    s = _re.sub(r'\{%.*?%\}', '', s)
    s = s.replace('}}', '').replace('{{', '')
    # Markdown headings: ### / ## / # at line start -> <b>...</b>
    m = _re.match(r'^#{1,3}\s+(.+)$', s.strip())
    if m:
        return f"<b>{m.group(1).strip()}</b>"
    # Bold: **text** -> <b>text</b>  (before italic so ***x*** works)
    s = _re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', s)
    s = _re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    # Italic: *text* or _text_ -> <i>text</i>
    s = _re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', s)
    s = _re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'<i>\1</i>', s)
    # Inline code backticks -> strip the backticks, keep content plain
    s = _re.sub(r'`(.+?)`', r'\1', s)
    return s


def _is_section_header(line):
    """True if the whole line is a bold heading: <b>text</b> with no other content."""
    s = line.strip()
    return (s.startswith("<b>") and s.endswith("</b>")
            and s.count("<b>") == 1 and s.count("</b>") == 1
            and not s[3:-4].strip() == "")


def _classify(line):
    """Return (tag, content) for one content line."""
    s = line.strip()
    if not s:
        return ("blank", "")
    # Section separator
    if s in ("---", "***", "___"):
        return ("hr", "")
    # Bold-only line = section header
    if _is_section_header(s):
        inner = s[3:-4]
        # First bold line tends to be the product title - render as h2; subsequent = h3
        return ("h2", inner)
    # List item: starts with  "- " / "• " / "▪ "
    if len(s) >= 2 and s[0] in "-•▪" and s[1] == " ":
        return ("li", s[2:])
    # Citation / source
    low = s.lower()
    if s.startswith("<i>") or low.startswith("source:") or "hm land registry" in low[:40]:
        return ("cite", s)
    # Force/must-ask question
    if any(x in low[:60] for x in ("force these", "ask:", "question:", "must ask", "demand ")):
        return ("question", s)
    # Risk/warning flag
    if any(x in s[:4] for x in ("⚠", "🚨", "🔴", "❌")):
        return ("risk", s)
    # Positive / all-clear
    if any(x in s[:4] for x in ("✓", "✅", "🟢", "🟩")):
        return ("ok", s)
    # Regular paragraph
    return ("p", s)


def _lines_to_html(lines):
    """Convert a list (or str) of content lines to an HTML fragment."""
    if not lines:
        return ""
    if isinstance(lines, str):
        lines = lines.split("\n")

    parts = []
    in_ul = False
    h2_count = 0

    for raw in lines:
        tag, content = _classify(_md_clean(raw if isinstance(raw, str) else str(raw)))

        if tag != "li" and in_ul:
            parts.append("</ul>")
            in_ul = False

        if tag == "blank":
            continue
        elif tag == "hr":
            parts.append('<hr class="div">')
        elif tag == "h2":
            h2_count += 1
            # first h2 is the product title which we render separately; skip it
            if h2_count == 1:
                continue
            parts.append(f"<h2>{content}</h2>")
        elif tag == "li":
            if not in_ul:
                parts.append("<ul>")
                in_ul = True
            parts.append(f"  <li>{content}</li>")
        elif tag == "cite":
            parts.append(f'<p class="cite">{content}</p>')
        elif tag == "question":
            parts.append(f'<div class="question">{content}</div>')
        elif tag == "risk":
            parts.append(f'<div class="risk">{content}</div>')
        elif tag == "ok":
            parts.append(f'<div class="ok">{content}</div>')
        else:
            parts.append(f"<p>{content}</p>")

    if in_ul:
        parts.append("</ul>")

    return "\n".join(parts)


def render(title, blurb, content, address, profile, generated_at=None):
    """Return a complete standalone HTML document for a catalogue product.

    title:        product name e.g. 'Red-Flag Interpretation Report'
    blurb:        one-line product description
    content:      list of strings from catalogue.build() — may contain <b>/<i> HTML
    address:      subject property address
    profile:      buyer | seller | agent | investor | vendor
    generated_at: optional datetime string; defaults to today UTC
    """
    if generated_at is None:
        dt = datetime.datetime.utcnow()
        generated_at = f"{dt.day} {dt.strftime('%B %Y')}"
    profile_label = _PROFILE_LABEL.get((profile or "").lower(), "Buyer")
    content_html = _lines_to_html(content)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)} – Honestly</title>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head>
<body>

<div class="hdr">
  <img class="logo" src="/img/logo-icon.png" alt="">
  <img class="mark" src="/img/logo-wordmark-clean.png" alt="Honestly">
</div>

<div class="badge">{_esc(profile_label)} · {_esc(generated_at)}</div>
<h1 class="doc-title">{_esc(title)}</h1>
<p class="doc-addr">📍 {_esc(address)}</p>
<p class="doc-blurb">{_esc(blurb)}</p>

{content_html}

<div class="ftr">
  HM Land Registry Price Paid · planning.data.gov.uk · Environment Agency · Honestly<br>
  A comparative evidence read, not a RICS Red Book valuation or legal advice.<br>
  Generated {_esc(generated_at)} ·
  <a href="https://usehonestly.co.uk">usehonestly.co.uk</a>
</div>
</body>
</html>"""
