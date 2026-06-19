#!/usr/bin/env python3
"""email_send.py - Honestly's SMTP transport. The thin, safe layer every email goes through.

One job: hand a message to an SMTP server (Gmail App Password, or any host) and never raise
into the caller. This is stdlib `smtplib` + `email.message.EmailMessage` - exactly what the
reference repo (urvish12345/python-smtp-email-automation) wraps, but without the dead weight:
no "less secure app access" (Google removed it; App Passwords are the supported path), no
third-party dependency, and a transactional provider (SES/Postmark/Resend SMTP) drops straight
in by changing four env vars - same seam, no code change.

Configuration is ENV ONLY (keys never hardcoded, never sent to a client):
    SMTP_HOST        e.g. smtp.gmail.com
    SMTP_PORT        587 (STARTTLS, default) or 465 (implicit SSL, set SMTP_SSL=1)
    SMTP_USER        the mailbox / API user
    SMTP_PASS        an App Password / API secret  (NEVER a real account password in git)
    SMTP_FROM        From address (defaults to SMTP_USER)
    SMTP_FROM_NAME   display name (default "Honestly")
    SMTP_SSL         "1" to use implicit SSL on connect (port 465)
    EMAIL_DRY_RUN    "1" (DEFAULT) writes the .eml to EMAIL_OUTBOX and sends NOTHING.
                     Set to "0" only when you intend to actually send.
    EMAIL_OUTBOX     dir for dry-run .eml files (default ./_outbox)

SAFETY: dry-run is the default. Nothing leaves this machine until SMTP_* are set AND
EMAIL_DRY_RUN=0. That is deliberate - outbound email is hard to recall.

    python email_send.py selftest          # build + dry-run one message, prove the .eml
    python email_send.py test you@x.com     # send a real test IF live (else dry-run)
"""
import os, sys, ssl, smtplib, mimetypes, re
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, formatdate

HERE = os.path.dirname(os.path.abspath(__file__))


def _env(k, default=""):
    return (os.environ.get(k) or default).strip()


def configured():
    """True iff we have enough to actually connect (host + user + pass)."""
    return bool(_env("SMTP_HOST") and _env("SMTP_USER") and _env("SMTP_PASS"))


def dry_run():
    """Dry-run unless EMAIL_DRY_RUN is explicitly falsey. Default-safe: missing -> dry."""
    return _env("EMAIL_DRY_RUN", "1").lower() not in ("0", "false", "no", "off")


def live():
    """Will this actually send? Only when configured AND dry-run is off."""
    return configured() and not dry_run()


def from_pair():
    addr = _env("SMTP_FROM") or _env("SMTP_USER")
    name = _env("SMTP_FROM_NAME", "Honestly")
    return name, addr


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]*\n[ \t]*")


def _plaintext(html):
    """A readable plain-text fallback from HTML, so the message is never HTML-only (which
    trips spam filters and breaks text clients). Crude but honest: strip tags, keep links."""
    if not html:
        return ""
    t = re.sub(r"(?is)<br\s*/?>", "\n", html)
    t = re.sub(r"(?is)</p>", "\n\n", t)
    t = re.sub(r'(?is)<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"\2 (\1)", t)
    t = _TAG_RE.sub("", t)
    t = (t.replace("&amp;", "&").replace("&pound;", "£").replace("&middot;", "-")
          .replace("&rarr;", "->").replace("&nbsp;", " ").replace("&mdash;", "-")
          .replace("&#39;", "'").replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">"))
    t = _WS_RE.sub("\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def build_message(to, subject, html, *, text=None, attachments=None, inline_images=None,
                  reply_to=None, headers=None, from_name=None):
    """Build a multipart/alternative EmailMessage (text + html) with optional attachments.
    attachments:   list of (filename, bytes, mimetype|None) - shown as downloads.
    inline_images: list of (cid, bytes, mimetype|None) - embedded in the HTML via
                   src="cid:<cid>" (the email-safe way to carry the REAL logo asset; data:
                   URIs are blocked by Gmail). Returns the EmailMessage."""
    name, addr = from_pair()
    msg = EmailMessage()
    msg["From"] = formataddr((from_name or name, addr))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=(addr.split("@")[-1] if "@" in addr else "usehonestly.co.uk"))
    if reply_to:
        msg["Reply-To"] = reply_to
    for k, v in (headers or {}).items():
        if v:
            msg[k] = v
    msg.set_content(text if text is not None else _plaintext(html))
    if html:
        msg.add_alternative(html, subtype="html")
        # embed inline images INTO the html alternative (multipart/related) before any
        # download attachments turn the message into multipart/mixed.
        if inline_images:
            html_part = msg.get_payload()[-1]
            for cid, data, mime in inline_images:
                if not data:
                    continue
                mt, _, st = (mime or "image/png").partition("/")
                html_part.add_related(data, maintype=mt or "image", subtype=st or "png",
                                      cid="<%s>" % cid.strip("<>"))
    for fn, data, mime in (attachments or []):
        if not data:
            continue
        ctype = mime or mimetypes.guess_type(fn)[0] or "application/octet-stream"
        maintype, _, subtype = ctype.partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream",
                           filename=fn)
    return msg


def _outbox_dir():
    d = _env("EMAIL_OUTBOX") or os.path.join(HERE, "_outbox")
    os.makedirs(d, exist_ok=True)
    return d


def _drop_eml(msg):
    """Dry-run sink: write the exact .eml we WOULD have sent, so it can be inspected /
    opened in any mail client. Returns the path."""
    safe = re.sub(r"[^a-z0-9]+", "-", (msg["To"] or "noone").lower()).strip("-")
    import time as _t
    stamp = "%.0f" % (_t.time() * 1000)
    path = os.path.join(_outbox_dir(), f"{stamp}-{safe[:40]}.eml")
    with open(path, "wb") as f:
        f.write(bytes(msg))
    return path


def send(to, subject, html, *, text=None, attachments=None, inline_images=None,
         reply_to=None, headers=None, from_name=None):
    """Send one email. BEST-EFFORT: never raises. Returns a dict:
        {ok, dry_run, reason, path?}
    - If not live (unconfigured OR EMAIL_DRY_RUN on): writes the .eml to the outbox and
      returns {ok:True, dry_run:True, path:...}. Nothing is sent.
    - If live: connects (STARTTLS or implicit SSL), authenticates, sends; {ok:True,...}.
    A bad single recipient never takes down a sequence run."""
    try:
        if not to or "@" not in to:
            return {"ok": False, "dry_run": dry_run(), "reason": "bad recipient"}
        msg = build_message(to, subject, html, text=text, attachments=attachments,
                            inline_images=inline_images, reply_to=reply_to,
                            headers=headers, from_name=from_name)
    except Exception as e:
        return {"ok": False, "dry_run": dry_run(), "reason": "build: " + str(e)[:160]}

    if not live():
        try:
            p = _drop_eml(msg)
            reason = "unconfigured" if not configured() else "dry_run"
            return {"ok": True, "dry_run": True, "reason": reason, "path": p}
        except Exception as e:
            return {"ok": False, "dry_run": True, "reason": "outbox: " + str(e)[:160]}

    host = _env("SMTP_HOST")
    port = int(_env("SMTP_PORT", "587") or "587")
    user, pw = _env("SMTP_USER"), _env("SMTP_PASS")
    use_ssl = _env("SMTP_SSL", "1" if port == 465 else "0").lower() in ("1", "true", "yes")
    try:
        ctx = ssl.create_default_context()
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=30, context=ctx) as s:
                s.login(user, pw)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.ehlo()
                s.login(user, pw)
                s.send_message(msg)
        return {"ok": True, "dry_run": False, "reason": "sent"}
    except Exception as e:
        return {"ok": False, "dry_run": False, "reason": str(e)[:200]}


def _selftest():
    """Force dry-run, build + drop one .eml with an attachment, assert it round-trips."""
    os.environ["EMAIL_DRY_RUN"] = "1"
    res = send("buyer@example.com", "Your SE15 area report",
               "<p>Hello - your report is attached. "
               '<a href="https://t.me/usehonestly_bot">Claim your free valuation</a>.</p>',
               attachments=[("report.pdf", b"%PDF-1.4 fake", "application/pdf")],
               headers={"List-Unsubscribe": "<mailto:unsub@usehonestly.co.uk>"})
    assert res["ok"] and res["dry_run"], res
    assert os.path.exists(res["path"]), "no .eml written"
    raw = open(res["path"], "rb").read()
    assert b"Your SE15 area report" in raw and b"report.pdf" in raw, "eml missing parts"
    assert b"Claim your free valuation" in raw, "html part missing"
    assert _plaintext("<p>Hi <a href='http://x'>link</a></p>").startswith("Hi link"), "text fallback"
    print("email_send selftest OK ->", res["path"], "| live=", live(), "configured=", configured())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        _selftest()
    elif len(sys.argv) > 2 and sys.argv[1] == "test":
        r = send(sys.argv[2], "Honestly SMTP test",
                 "<p>This is a live SMTP test from Honestly.</p>")
        print(r)
    else:
        print(__doc__)
