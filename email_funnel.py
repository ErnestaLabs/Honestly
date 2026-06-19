#!/usr/bin/env python3
"""email_funnel.py - the blog-PDF lead funnel, by email.

The front door of the unchanged funnel:

    blog report  ->  reader gives email for the FREE area-report PDF
                 ->  WE EMAIL THEM THE PDF  (this module, step 0)
                 ->  a short follow-up drip, every email's one CTA is the SAME:
                     "claim your FREE valuation of your own address on Telegram"
                 ->  (on Telegram) the free lite valuation, then the Pro offer.

This module owns only the email leg. It does two things:

    start(lead_token, email, slug, name)   enqueue the sequence + deliver step 0 now
    run_due()                              send every email that is now due

Bodies are rendered at SEND TIME from the live blog model in store, so a follow-up can
never drift from the report it points at. Copy is written here, by hand, district-aware -
not generated per-lead. Every email carries an unsubscribe (header + visible link) that
cancels the whole sequence. Sending goes through email_send, which is DRY-RUN by default:
nothing leaves the machine until SMTP_* are set AND EMAIL_DRY_RUN=0.

Honesty contract held throughout: the area PDF is genuinely free, the Telegram lite
valuation is genuinely free, and Pro is the only thing that costs - the free/paid line is
kept bright in every email, and we never promise a mechanic the bot does not have.

    python email_funnel.py selftest        # dry-run a full sequence into _outbox, assert
    python email_funnel.py run             # send everything currently due (cron this)
"""
import os, sys, html as _h

import brand
import store
import email_send
import area_report

PUBLIC_BASE = (os.environ.get("BLOG_PUBLIC_BASE") or "https://usehonestly.co.uk").rstrip("/")
BOT = os.environ.get("BLOG_BOT_URL", "https://t.me/usehonestly_bot")
FROM_NAME = os.environ.get("SMTP_FROM_NAME", "Honestly")

DAY = 86400.0
# step -> (kind, delay-seconds-after-capture). Tunable via env for testing; defaults in days.
def _delay(name, default_days):
    try:
        return float(os.environ.get(name, "")) * DAY if os.environ.get(name) else default_days * DAY
    except Exception:
        return default_days * DAY

SEQUENCE = [
    (0, "deliver",  0.0),
    (1, "nurture1", None),   # filled below from env-tunable delays
    (2, "nurture2", None),
    (3, "nurture3", None),
]


def _schedule(now):
    """Return [(step, kind, send_after), ...] for a capture at `now`."""
    d1 = _delay("FUNNEL_D1_DAYS", 2)
    d2 = _delay("FUNNEL_D2_DAYS", 5)
    d3 = _delay("FUNNEL_D3_DAYS", 9)
    offs = {0: -1.0, 1: d1, 2: d2, 3: d3}   # step 0 is due immediately (now-1s)
    return [(s, k, now + offs[s]) for (s, k, _) in SEQUENCE]


# ----------------------------------------------------------------- templates
H = brand.HEX


def _logo_bytes():
    """The EXACT compact lockup PNG bytes, embedded inline (cid) so the real asset shows in
    email where data: URIs are blocked. Returns (cid, bytes, mime) or None if missing."""
    try:
        p = brand.logo_path("lockup-compact")
        with open(p, "rb") as f:
            return ("honestlylogo", f.read(), "image/png")
    except Exception:
        return None


def _btn(href, label):
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" '
            f'style="margin:22px 0"><tr><td bgcolor="{H["navy"]}" '
            f'style="border-radius:9px">'
            f'<a href="{_h.escape(href)}" '
            f'style="display:inline-block;padding:14px 26px;font-family:Arial,Helvetica,sans-serif;'
            f'font-size:16px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:9px">'
            f'{_h.escape(label)}</a></td></tr></table>')


def _shell(inner, *, unsub_url, preheader, logo_cid):
    """Branded, email-client-safe wrapper: a 600px centred card, cream page, navy footer rule.
    Logo via cid (real asset) with a styled-text fallback in alt. Inline styles only - no
    <style> block, because Gmail and Outlook strip or mangle those."""
    logo = (f'<img src="cid:{logo_cid}" width="160" alt="Honestly" '
            f'style="display:block;border:0;height:auto;max-width:160px">'
            if logo_cid else
            f'<span style="font:bold 24px Georgia,serif;color:{H["navy"]}">honest'
            f'<span style="color:{H["teal"]}">ly</span></span>')
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{H['paper']}">
<span style="display:none;max-height:0;overflow:hidden;opacity:0">{_h.escape(preheader)}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{H['paper']}">
<tr><td align="center" style="padding:26px 14px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0"
 style="width:600px;max-width:600px;background:#ffffff;border:1px solid {H['line']};border-radius:14px;overflow:hidden">
<tr><td style="height:4px;background:{H['gold']};line-height:4px;font-size:0">&nbsp;</td></tr>
<tr><td style="padding:22px 30px 6px 30px;background:{H['cream']}">{logo}</td></tr>
<tr><td style="padding:8px 30px 28px 30px;font-family:Arial,Helvetica,sans-serif;
 font-size:16px;line-height:1.65;color:{H['ink']}">
{inner}
</td></tr>
<tr><td style="padding:18px 30px 24px 30px;background:{H['cream']};border-top:1px solid {H['line']};
 font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.6;color:{H['muted']}">
Honestly reports every UK postcode district from official data - sold prices, asking prices and
rents from HM Land Registry and live listings. The area report is free. A valuation of one
specific address is the paid product.<br><br>
A product by Ernesta Labs.<br>
<a href="{_h.escape(unsub_url)}" style="color:{H['muted']};text-decoration:underline">
Unsubscribe from these emails</a>
</td></tr>
</table></td></tr></table></body></html>"""


def _district(model):
    return model.get("district") or "your area"


def _city(model):
    return ((model.get("city") or {}).get("name")) or ""


def _report_url(slug):
    return f"{PUBLIC_BASE}/blog/{slug}/"


def _render(row):
    """Build (subject, html, attachments, inline_images) for one queued email, or None to
    skip (the slug no longer resolves to a published report)."""
    slug = row["slug"]
    post = store.get_blog_post(slug, with_html=False, with_model=True)
    model = post.get("model") if post else None
    if not model:
        return None
    d = _district(model)
    city = _city(model)
    where = f"{d}" + (f", {city}" if city and city not in d else "")
    rep = _report_url(slug)
    unsub = f"{PUBLIC_BASE}/u/{row['lead_token']}"
    logo = _logo_bytes()
    logo_cid = logo[0] if logo else None
    inline = [logo] if logo else None
    kind = row["kind"]

    if kind == "deliver":
        subject = f"Your {d} market report (free PDF inside)"
        pre = f"The {where} report you asked for, plus how to value your own address free."
        inner = (
            f"<p>Here is your <strong>{_h.escape(where)} market report</strong>, attached as a "
            f"PDF. It is the same report we publish free at "
            f'<a href="{_h.escape(rep)}" style="color:{H["green"]}">{_h.escape(rep)}</a> - sold '
            f"prices, asking prices, days on market and rents for the district, straight from "
            f"official data.</p>"
            f"<p>One thing it does <em>not</em> do: value <strong>your</strong> specific address. "
            f"The report describes the area; it never names a figure for one home.</p>"
            f"<p>If you want that number, it is also free. Send your address to our Telegram bot "
            f"and you get a lite valuation back - sold-evidence based, in a couple of minutes, no "
            f"card, no call.</p>"
            f"{_btn(BOT, 'Get your free valuation on Telegram')}"
            f"<p style=\"font-size:13px;color:{H['muted']}\">Only a full Pro valuation costs "
            f"anything, and only when you decide you want it. The area report and the lite "
            f"valuation are free.</p>")
        atts = [(area_report.filename(model), _safe_pdf(model), "application/pdf")]
        atts = [a for a in atts if a[1]]
        return subject, _shell(inner, unsub_url=unsub, preheader=pre, logo_cid=logo_cid), atts, inline

    if kind == "nurture1":
        subject = f"What is your {d} place actually worth?"
        pre = f"The {where} report shows the area. Here is the number for your own address."
        inner = (
            f"<p>A couple of days ago you downloaded the <strong>{_h.escape(where)}</strong> "
            f"market report. It shows what the district is doing - but not what your own home "
            f"would sell for.</p>"
            f"<p>That part is free too. Send your address to our Telegram bot and it values it "
            f"against the actual sold comparables nearby, then shows you the working - not a "
            f"single mystery number.</p>"
            f"{_btn(BOT, f'Value your {d} address free')}"
            f"<p>Two minutes, no card, no estate agent calling you back.</p>")
        return subject, _shell(inner, unsub_url=unsub, preheader=pre, logo_cid=logo_cid), [], inline

    if kind == "nurture2":
        subject = "The number an agent will not put in writing"
        pre = "Sold evidence, not an opinion. Free for your address on Telegram."
        inner = (
            f"<p>Two agents will give you two prices for the same home, often tens of thousands "
            f"apart - one to win the instruction, one to win the offer. Neither is evidence.</p>"
            f"<p>Honestly does the opposite: it starts from what nearby homes <em>actually sold "
            f"for</em>, on the Land Registry record, and shows every comparable it used. Your "
            f"{_h.escape(_district(model))} address, valued free on Telegram:</p>"
            f"{_btn(BOT, 'Get the sold-evidence valuation')}"
            f"<p style=\"font-size:13px;color:{H['muted']}\">The lite valuation is free. When a "
            f"sale or an offer is real money on the line, a defensible Pro valuation is there - "
            f"but you never need it to get started.</p>")
        return subject, _shell(inner, unsub_url=unsub, preheader=pre, logo_cid=logo_cid), [], inline

    if kind == "nurture3":
        subject = f"Last one from me - your free {d} valuation"
        pre = "A final nudge, then I will stop emailing."
        inner = (
            f"<p>This is the last email I will send about it. If the {_h.escape(where)} report "
            f"was useful, the natural next step is the number for your own address - and it is "
            f"free:</p>"
            f"{_btn(BOT, 'Claim your free valuation')}"
            f"<p>If now is not the time, no problem at all. You can come back to the bot whenever "
            f"a specific address matters - yours, or one you are about to offer on.</p>"
            f"<p style=\"font-size:13px;color:{H['muted']}\">Thanks for reading - the Honestly "
            f"team.</p>")
        return subject, _shell(inner, unsub_url=unsub, preheader=pre, logo_cid=logo_cid), [], inline

    return None


def _safe_pdf(model):
    """Build the area-report PDF bytes, best-effort. Returns b'' on failure so a PDF build
    problem degrades to a still-useful email (link to the online report) instead of no email."""
    try:
        return area_report.build(model)
    except Exception as e:
        email_send and None
        print("[funnel] pdf build failed:", str(e)[:160], file=sys.stderr)
        return b""


# ------------------------------------------------------------------- actions
def start(lead_token, email, slug, name=None, *, now=None):
    """Enqueue the full sequence for a fresh lead and deliver step 0 immediately.
    Idempotent: a second call for the same lead_token is a no-op. Best-effort: a failure
    to email never costs the reader their /dl download (the caller already minted it)."""
    import time
    now = time.time() if now is None else now
    if not email or not slug:
        return {"ok": False, "reason": "missing email/slug"}
    if store.has_queue(lead_token):
        return {"ok": True, "skipped": "already queued"}
    for step, kind, send_after in _schedule(now):
        store.enqueue_email(lead_token, email, slug, step, kind, send_after)
    # flush anything due right now (step 0) so the PDF lands immediately
    flushed = run_due(now=now)
    return {"ok": True, "queued": len(SEQUENCE), "delivered_now": flushed}


def run_due(now=None, limit=200):
    """Send every queued email that is now due. Renders each from the live model, sends via
    email_send (dry-run-safe), marks the row sent/failed/cancelled. Returns a summary dict."""
    rows = store.due_emails(now=now, limit=limit)
    sent = failed = skipped = 0
    for row in rows:
        built = _render(row)
        if not built:
            store.mark_email(row["id"], "cancelled")   # report gone -> drop quietly
            skipped += 1
            continue
        subject, html, atts, inline = built
        unsub = f"{PUBLIC_BASE}/u/{row['lead_token']}"
        headers = {
            "List-Unsubscribe": f"<{unsub}>, <mailto:unsubscribe@usehonestly.co.uk?subject=unsubscribe>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }
        res = email_send.send(row["email"], subject, html, attachments=atts,
                              inline_images=inline, headers=headers, from_name=FROM_NAME)
        if res.get("ok"):
            store.mark_email(row["id"], "sent")
            store.log_event("email_sent", token=row["lead_token"],
                            detail={"step": row["step"], "kind": row["kind"],
                                    "email": row["email"], "dry_run": res.get("dry_run", False)})
            sent += 1
        else:
            store.mark_email(row["id"], "failed")
            store.log_event("email_failed", token=row["lead_token"],
                            detail={"kind": row["kind"], "reason": res.get("reason", "")})
            failed += 1
    return {"sent": sent, "failed": failed, "skipped": skipped, "due": len(rows)}


def _selftest():
    """End-to-end dry-run in a throwaway DB: seed a blog post, capture a lead, start the
    sequence, assert step 0 emailed a PDF, fast-forward and flush the nurture steps, then
    unsubscribe and confirm the rest are cancelled. No network, nothing actually sent."""
    import tempfile, time, glob
    os.environ["EMAIL_DRY_RUN"] = "1"
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd); os.remove(path)
    store.DB_PATH, store._INITED = path, False
    outbox = tempfile.mkdtemp()
    os.environ["EMAIL_OUTBOX"] = outbox

    model = {"district": "SE15", "slug": "london-se15",
             "city": {"name": "London", "slug": "london", "series": "The London Daily"},
             "present": {"pd_sold": 1},
             "sold": {"ok": True, "median_price": 480000, "psm_median": 7200, "total": 300,
                      "recency": {"window_months": 24, "last_12m": 120}, "by_type": [], "sample": []},
             "listings": {"ok": True, "n": 90, "asking_median": 500000, "mean_dom": 60,
                          "available_n": 80, "stuck_n": 20, "under_offer_n": 12},
             "area": {}}
    store.record_blog_post("london-se15", city_slug="london", district="SE15",
                           series="The London Daily", title="SE15", description="x",
                           headline_price=480000, model=model, html="<html>se15</html>",
                           generated_at=brand.DATESTR)
    tok = store.record_lead("buyer@example.com", "london-se15", name="Sam")
    assert tok, "lead not captured"

    t0 = time.time()
    r = start(tok, "buyer@example.com", "london-se15", "Sam", now=t0)
    assert r["ok"] and r["queued"] == 4, r
    assert r["delivered_now"]["sent"] == 1, f"step 0 should send immediately: {r}"
    emls = sorted(glob.glob(os.path.join(outbox, "*.eml")))
    assert len(emls) == 1, f"one email so far, got {len(emls)}"
    raw = open(emls[0], "rb").read()
    assert b"market report (free PDF inside)" in raw, "deliver subject missing"
    assert b"application/pdf" in raw and b"honestly-SE15-market-report.pdf" in raw, "PDF not attached"
    assert b"cid:honestlylogo" in raw or b"honest" in raw, "logo/brand missing"
    assert b"/u/" + tok.encode() in raw, "unsubscribe link missing"

    # idempotency: starting again does nothing
    assert start(tok, "buyer@example.com", "london-se15", now=t0).get("skipped"), "should be idempotent"

    # fast-forward past every delay and flush the nurture steps
    future = t0 + 100 * DAY
    summ = run_due(now=future)
    assert summ["sent"] == 3, f"three nurture emails due later: {summ}"
    emls = glob.glob(os.path.join(outbox, "*.eml"))
    assert len(emls) == 4, f"four emails total, got {len(emls)}"

    # nothing left due; unsubscribe is a no-op on an empty pending set but must not error
    assert run_due(now=future)["due"] == 0, "queue should be drained"
    canc = store.cancel_sequence(tok)
    assert canc["ok"], canc

    # a fresh lead, then unsubscribe BEFORE the nurtures fire -> they are cancelled, not sent
    tok2 = store.record_lead("seller@example.com", "london-se15")
    start(tok2, "seller@example.com", "london-se15", now=t0)
    store.cancel_sequence(tok2)
    summ2 = run_due(now=t0 + 100 * DAY)
    assert summ2["sent"] == 0, f"unsubscribed lead must get nothing more: {summ2}"
    print("email_funnel selftest OK ->", outbox, "| 4 emails dry-run, unsubscribe honoured")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        _selftest()
    elif len(sys.argv) > 1 and sys.argv[1] == "run":
        print(run_due())
    else:
        print(__doc__)
