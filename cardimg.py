#!/usr/bin/env python3
"""cardimg.py - render a valuation result as a branded card image, and a blurred
'locked' version of it. The blurred card is the paywall: the customer sees a real,
detailed report for their address but cannot read the figures until they pay.

render(d, audience) -> (clear_png_path, blurred_png_path)
  d = engine.summary(r, audience)
No network, no state. PIL only (Pillow is installed)."""
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
W = 1080
BG = (246, 243, 236)        # cream
INK = (28, 26, 22)
MUT = (107, 101, 87)
GREEN = (31, 111, 92)
GREEND = (20, 63, 51)
LINE = (231, 225, 212)
CARD = (255, 255, 255)

def _font(names, size):
    for n in names:
        p = os.path.join(r"C:\Windows\Fonts", n)
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()

def _f(size, bold=False):      # body (Arial)
    return _font(["arialbd.ttf"] if bold else ["arial.ttf"], size)
def _serif(size):              # headline (Georgia)
    return _font(["georgiab.ttf", "timesbd.ttf"], size)

def _text(d, xy, s, font, fill, anchor="la"):
    d.text(xy, s, font=font, fill=fill, anchor=anchor)

def render(summary, audience, slug="card"):
    d = summary
    pad = 56
    rng = d["range_str"]
    ev = d.get("evidence", [])[:4]
    # ---- measure height
    H = 1180 + max(0, (len(ev) - 4)) * 64
    img = Image.new("RGB", (W, H), BG)
    dr = ImageDraw.Draw(img)

    # ---- header band (kept SHARP in the blurred version)
    band_h = 286
    dr.rectangle([0, 0, W, band_h], fill=BG)
    _text(dr, (pad, 50), "Honestly", _serif(52), GREEND)
    _text(dr, (pad + 246, 64), "what it's really worth", _f(26), GREEN)
    _text(dr, (pad, 150), d["address"], _f(34, bold=True), INK)
    meta = []
    if d.get("sqm"): meta.append(f"{d['sqm']} sqm")
    if d.get("beds"): meta.append(f"{d['beds']} bed")
    if d.get("epc"): meta.append(f"EPC {d['epc']}")
    _text(dr, (pad, 200), "  ·  ".join(meta), _f(28), MUT)
    n = len(d.get("evidence", []))
    _text(dr, (pad, 240), f"Valued from {n} verified sold comparables · HM Land Registry",
          _f(24), GREEN)
    dr.line([pad, band_h, W - pad, band_h], fill=LINE, width=2)

    # ---- the figures (these get blurred)
    y = band_h + 44
    _text(dr, (pad, y), "Assessed value", _f(26), MUT); y += 44
    _text(dr, (pad, y), rng, _serif(74), GREEND); y += 96
    _text(dr, (pad, y), f"most likely ~£{d['central']:,}", _f(30), MUT); y += 66
    gl = d.get("guide_label", "Guide"); gv = d.get("guide_value_str", "")
    _text(dr, (pad, y), f"{gl}:  ", _f(32), INK)
    glw = dr.textlength(f"{gl}:  ", font=_f(32))
    _text(dr, (pad + glw, y), gv, _f(34, bold=True), GREEN); y += 80

    dr.line([pad, y, W - pad, y], fill=LINE, width=2); y += 36
    _text(dr, (pad, y), "Evidence - homes like it, sold", _f(28, bold=True), INK); y += 56
    for c in ev:
        _text(dr, (pad, y), f"• {c['address']}", _f(28), INK)
        _text(dr, (pad, y + 34), f"   {c['sqm']} sqm · {c['date']}", _f(23), MUT)
        _text(dr, (W - pad, y + 6), c["price_str"], _f(30, bold=True), GREEND, anchor="ra")
        y += 78
    _text(dr, (pad, H - 60), "HM Land Registry via PropertyData · asking prices never used to value",
          _f(22), MUT)

    clear_path = os.path.join(HERE, f"_{slug}_clear.png")
    img.save(clear_path)

    # ---- blurred 'locked' version
    blur = img.filter(ImageFilter.GaussianBlur(16))
    blur.paste(img.crop((0, 0, W, band_h)), (0, 0))           # keep header sharp
    bd = ImageDraw.Draw(blur, "RGBA")
    bd.line([pad, band_h, W - pad, band_h], fill=LINE, width=2)
    # central lock pill
    pill_w, pill_h = 640, 132
    px = (W - pill_w) // 2; py = band_h + (H - band_h) // 2 - pill_h // 2
    bd.rounded_rectangle([px, py, px + pill_w, py + pill_h], radius=20,
                         fill=(20, 63, 51, 235))
    _text(bd, (W // 2, py + 40), "VALUATION READY", _f(34, bold=True), (255, 255, 255), anchor="ma")
    _text(bd, (W // 2, py + 84), "Tap Reveal to unlock - first one £2.50", _f(26), (210, 226, 220), anchor="ma")
    blur_path = os.path.join(HERE, f"_{slug}_locked.png")
    blur.save(blur_path)
    return clear_path, blur_path

if __name__ == "__main__":
    # quick self-test with dummy data
    demo = {"address": "58, Cronin Street, London SE15 6JH", "sqm": 103, "beds": 4,
            "epc": "C", "range_str": "£550,000 - £600,000", "central": 550000,
            "guide_label": "Recommended guide", "guide_value_str": "Offers Over £500,000",
            "evidence": [{"address": "Flat 8", "sqm": 97, "date": "2026-01", "price_str": "£445,000"},
                         {"address": "95", "sqm": 104, "date": "2026-04", "price_str": "£590,000"},
                         {"address": "Flat 8", "sqm": 92, "date": "2026-03", "price_str": "£500,000"}]}
    c, b = render(demo, "agent", "demo")
    print("clear:", c); print("locked:", b)
