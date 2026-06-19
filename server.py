#!/usr/bin/env python3
"""server.py - Honestly. The web surface for the valuation engine.

Serves one self-contained page that runs as a Telegram Mini App AND as a public
browser link (usehonestly.co.uk), both fed by the same engine.summary(). No
framework, no build step - Python stdlib only, same as the rest of the engine.

  GET /                      the Honestly app (webapp/index.html)
  GET /api/value?address=..  run the engine -> JSON summary + image URLs
        &as=vendor|buyer|agent  &beds=N  &asking=N  &quoted=N
  GET /img/<file>            cached frontage / route-map image

Run:
  python server.py            (PROPERTYDATA_KEY + GOOGLE_MAPS_API_KEY from .env)
  python server.py --port 8080
For Telegram, expose it over https (a tunnel for dev, a host for prod) and set
HONESTLY_WEBAPP_URL so the bot's "Open Honestly" button launches it.
"""
import os, sys, json, html, hmac, time, hashlib, secrets, argparse, urllib.parse, urllib.request, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import engine, maps_tools
import bot  # reuse the single source of truth for pricing + Stars invoicing
import store  # persistence: hosted /r/<token> reports + audit trail
import area_report  # on-demand free area-report PDF for the blog lead-capture gate
import email_funnel  # the blog-PDF email funnel: emails the PDF + runs the follow-up drip

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
# Static blog tree written by publish_daily.py: site/blog/<slug>/index.html, the city hubs,
# the index, site/sitemap.xml and site/blog/feed.xml. Served read-only from here.
SITE_DIR = os.environ.get("BLOG_SITE_DIR", os.path.join(HERE, "site"))
os.makedirs(CACHE, exist_ok=True)
maps_tools._load_env()
KEY = os.environ.get("PROPERTYDATA_KEY")
# Handoff store: the Mini App writes a purchase "intent" here keyed by a short id; the
# bot reads it on successful_payment so the paid valuation delivers even though the Mini
# App (this process) and the bot poller are separate processes. See bot.load_intent().
INTENTS = os.path.join(HERE, "miniapp_intents.json")

# In-process job registry: job_id -> {status, url, title, error}. Products are built in daemon
# threads; the frontend polls /api/product_poll until status=='done'. Entries pruned after 10 min.
_JOBS = {}
_JOBS_LOCK = threading.Lock()


def _jobs_gc():
    """Remove entries older than 10 minutes (they carry a 'ts' key set at creation)."""
    cutoff = time.time() - 600
    with _JOBS_LOCK:
        stale = [k for k, v in _JOBS.items() if v.get("ts", 0) < cutoff]
        for k in stale:
            del _JOBS[k]

def _hash(s): return hashlib.md5(s.encode("utf-8")).hexdigest()[:10]

def _link_gone_page(reason):
    """A small branded page for an unknown/expired/revoked /r/<token> link. Brand palette
    from site/tailwind.config.js (navy/cream/gold) - no figure, no data, just an honest
    'this link is no longer live' with a route back."""
    msg = {"expired": ("This report link has expired",
                       "Hosted links lapse after 90 days for privacy. The valuation still "
                       "exists - ask for a fresh link and we'll re-issue it."),
           "revoked": ("This report link has been turned off",
                       "The owner of this report has disabled the link. Request a new one "
                       "if you still need access."),
           "unknown": ("We couldn't find that report",
                       "This link doesn't match any report we hold. Check it was copied in "
                       "full, or request a new one.")}.get(reason, (
                       "This link isn't available",
                       "Please request a fresh link."))
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(msg[0])} - Honestly</title>"
        "<style>:root{color-scheme:light}"
        "body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;"
        "background:#f6f3ec;color:#1c1a16;font:16px/1.6 -apple-system,Segoe UI,Roboto,sans-serif}"
        ".card{max-width:30rem;margin:1.5rem;padding:2.25rem;background:#fbf9f4;border:1px solid #e7e1d4;"
        "border-radius:18px;box-shadow:0 10px 40px rgba(14,39,71,.08);text-align:center}"
        "h1{font-family:Georgia,serif;color:#0e2747;font-size:1.5rem;margin:.25rem 0 1rem}"
        "p{color:#6b6557;margin:0 0 1.5rem}"
        "a{display:inline-block;background:#0e2747;color:#fff;text-decoration:none;"
        "padding:.7rem 1.4rem;border-radius:999px;font-weight:600}"
        ".g{height:4px;width:54px;margin:0 auto 1.25rem;border-radius:4px;background:#d89a32}"
        "</style></head><body><div class=card><div class=g></div>"
        f"<h1>{html.escape(msg[0])}</h1><p>{html.escape(msg[1])}</p>"
        "<a href='https://usehonestly.co.uk'>Go to Honestly</a></div></body></html>")

def _safe_site_path(rel):
    """Resolve a URL path to a file inside SITE_DIR, refusing any traversal outside it.
    Returns the absolute path if it is safely under SITE_DIR, else None."""
    rel = rel.lstrip("/")
    base = os.path.realpath(SITE_DIR)
    full = os.path.realpath(os.path.join(base, *[p for p in rel.split("/") if p not in ("", ".", "..")]))
    if full == base or full.startswith(base + os.sep):
        return full
    return None

def _blog_missing_page():
    """Branded 'not published yet' page for a blog URL that has no static file. Same palette
    as the link-gone page; honest, no fabricated data, a route back to the blog index."""
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Report not published yet - Honestly</title>"
        "<style>:root{color-scheme:light}"
        "body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;"
        "background:#f6f3ec;color:#1c1a16;font:16px/1.6 -apple-system,Segoe UI,Roboto,sans-serif}"
        ".card{max-width:30rem;margin:1.5rem;padding:2.25rem;background:#fbf9f4;border:1px solid #e7e1d4;"
        "border-radius:18px;box-shadow:0 10px 40px rgba(14,39,71,.08);text-align:center}"
        "h1{font-family:Georgia,serif;color:#0e2747;font-size:1.5rem;margin:.25rem 0 1rem}"
        "p{color:#6b6557;margin:0 0 1.5rem}"
        "a{display:inline-block;background:#0e2747;color:#fff;text-decoration:none;"
        "padding:.7rem 1.4rem;border-radius:999px;font-weight:600}"
        ".g{height:4px;width:54px;margin:0 auto 1.25rem;border-radius:4px;background:#d89a32}"
        "</style></head><body><div class=card><div class=g></div>"
        "<h1>This report isn't published yet</h1>"
        "<p>We post a fresh postcode-district report for each major UK city every day. "
        "This one is still in the rotation - browse the ones that are live.</p>"
        "<a href='/blog/'>Browse the blog</a></div></body></html>")

def _unsub_page(ok):
    """Branded confirmation page for /u/<token>. Same palette as the other system pages.
    Honest either way: 'you're unsubscribed' when we cancelled a live sequence, and a calm
    'nothing to do' when the token is unknown or already drained - we never reveal whether an
    email is on file, and we never error a reader who clicks an old link twice."""
    if ok:
        head, body = ("You're unsubscribed",
                      "We've stopped the follow-up emails for this address. The free area "
                      "report you downloaded is still yours, and you can value any address "
                      "free on Telegram whenever you like - no emails required.")
    else:
        head, body = ("Nothing more to unsubscribe",
                      "There are no active emails for this link. You won't hear from this "
                      "sequence again.")
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(head)} - Honestly</title>"
        "<style>:root{color-scheme:light}"
        "body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;"
        "background:#f6f3ec;color:#1c1a16;font:16px/1.6 -apple-system,Segoe UI,Roboto,sans-serif}"
        ".card{max-width:30rem;margin:1.5rem;padding:2.25rem;background:#fbf9f4;border:1px solid #e7e1d4;"
        "border-radius:18px;box-shadow:0 10px 40px rgba(14,39,71,.08);text-align:center}"
        "h1{font-family:Georgia,serif;color:#0e2747;font-size:1.5rem;margin:.25rem 0 1rem}"
        "p{color:#6b6557;margin:0 0 1.5rem}"
        "a{display:inline-block;background:#0e2747;color:#fff;text-decoration:none;"
        "padding:.7rem 1.4rem;border-radius:999px;font-weight:600}"
        ".g{height:4px;width:54px;margin:0 auto 1.25rem;border-radius:4px;background:#d89a32}"
        "</style></head><body><div class=card><div class=g></div>"
        f"<h1>{html.escape(head)}</h1><p>{html.escape(body)}</p>"
        "<a href='https://usehonestly.co.uk'>Go to Honestly</a></div></body></html>")

def _to_int(v):
    """Best-effort int (web body values arrive as ints or strings); None if not a number."""
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None

def _bot_token():
    """The bot token lives ONLY in .env (loaded above). Never hardcoded, never sent to a
    client - it is used here purely to sign invoice links and verify Telegram initData."""
    t = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not t:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set (env or .env)")
    return t

def validate_init_data(init_data):
    """Verify Telegram WebApp initData and return the parsed user dict, or None if the
    signature doesn't check out. This is how we trust 'who is buying' without a password:
    Telegram signs the data with our bot token (HMAC), so only genuine launches verify."""
    if not init_data:
        return None
    try:
        pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
        data = dict(pairs)
        their_hash = data.pop("hash", None)
        if not their_hash:
            return None
        check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret = hmac.new(b"WebAppData", _bot_token().encode(), hashlib.sha256).digest()
        ours = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(ours, their_hash):
            return None
        # reject stale launches (replay window) - auth_date is unix seconds
        if data.get("auth_date") and abs(time.time() - int(data["auth_date"])) > 86400:
            return None
        return json.loads(data.get("user", "{}")) or None
    except Exception:
        return None

def _load_intents():
    try:
        with open(INTENTS, encoding="utf-8") as f: return json.load(f)
    except Exception: return {}

def save_intent(uid, address, audience, pack, beds=None, finish="average", investment=False,
                asking=None, quoted=None, micro=None, product=None):
    """Persist a purchase intent and return its short id. Pruned of anything older than a day.
    `micro` (a legacy micro-upsell id) or `product` (a catalogue.py product id) marks an
    a-la-carte purchase instead of a pack; the bot's deliver_intent dispatches on whichever is set."""
    store = _load_intents()
    cutoff = time.time() - 86400
    store = {k: v for k, v in store.items() if v.get("ts", 0) > cutoff}
    sid = secrets.token_urlsafe(9)
    store[sid] = {"uid": int(uid), "address": address, "audience": audience, "pack": pack,
                  "micro": micro, "product": product, "beds": beds, "finish": finish,
                  "investment": bool(investment),
                  "asking": asking, "quoted": quoted, "ts": time.time()}
    with open(INTENTS, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)
    return sid

def _derive_web_finish(get_int, fallback):
    """Pull the condition sub-survey signals (c_state/c_kitchen/c_bath/c_premium) the web
    form may send and derive the finish tier with the SAME bot.derive_finish the chat
    wizard uses - so the web intake and the bot can never disagree on how condition maps
    to a tier (one derivation, server-side, no JS/Python drift). Falls back to the plain
    single-select `fallback` when no signals are present. Returns (tier, disclosure)."""
    sig = {}
    for f in ("c_state", "c_kitchen", "c_bath", "c_premium"):
        v = get_int(f)
        if v is not None:
            sig[f] = v
    if not sig:
        return fallback, None
    return bot.derive_finish(sig)

def create_invoice_link(title, description, payload, stars, subscription_period=None):
    """Ask Telegram for a Stars (XTR) invoice link the Mini App can open with
    WebApp.openInvoice. Digital goods: empty provider_token, integer Star amount."""
    params = {"title": title[:32], "description": description[:255], "payload": payload,
              "provider_token": "", "currency": "XTR",
              "prices": [{"label": title[:32], "amount": int(stars)}]}
    if subscription_period:
        params["subscription_period"] = subscription_period
    url = f"https://api.telegram.org/bot{_bot_token()}/createInvoiceLink"
    req = urllib.request.Request(url, data=json.dumps(params).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.load(r)
    if not out.get("ok"):
        raise RuntimeError(out.get("description", "createInvoiceLink failed"))
    return out["result"]

def build(address, audience, beds=None, asking=None, quoted=None,
          finish="average", investment=False):
    """One engine run -> shared summary + the two images, cached by address.
    Condition (finish) and investment/CGT are user-set, not assumed."""
    r = engine.value(address, KEY, beds=beds, finish=finish, investment=investment)
    d = engine.summary(r, audience, asking=asking, quoted=quoted, n=6)
    h = _hash(r["subject"]["address"])
    imgs = {"frontage": None, "map": None}
    # frontage (honesty rule: only if real imagery exists)
    fpath = os.path.join(CACHE, f"{h}_frontage.jpg")
    sv = maps_tools.street_view(r["subject"]["address"], fpath)
    if sv.get("ok") and sv.get("available"):
        imgs["frontage"] = f"/img/{h}_frontage.jpg"; d["frontage_date"] = sv.get("date")
    # route / locality map
    stops = [r["subject"]["address"]] + [c["full_address"] for c in d["evidence"][:5]]
    rt = maps_tools.route(stops, optimize=True)
    if rt.get("ok"):
        mpath = os.path.join(CACHE, f"{h}_map.png")
        mp = maps_tools.static_map(mpath, markers=rt["ordered_stops"][:10],
                                   path=("enc:" + rt["polyline"]) if rt.get("polyline") else None)
        if mp.get("ok"):
            imgs["map"] = f"/img/{h}_map.png"
            d["route"] = {"km": rt["km"], "doors": len(rt["ordered_stops"]),
                          "mins": int(rt["duration"].rstrip("s") or 0) // 60}
    d["images"] = imgs
    return d

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass  # quiet

    def _send(self, code, body, ctype="application/json", no_store=False):
        if isinstance(body, str): body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        # The Mini App is a single HTML file that changes on every deploy. Without this,
        # Telegram's webview serves a STALE cached copy, so a fix can be live on the server
        # yet invisible to users (exactly the 'you fixed nothing' symptom). no-store forces a
        # fresh fetch on every open.
        if no_store:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path, q = u.path, urllib.parse.parse_qs(u.query)
        if path in ("/", "/index.html", "/app", "/app/", "/webapp", "/webapp/"):
            # The Telegram Mini App (the valuation form). In production nginx owns "/" with the
            # static marketing landing page, so the Mini App is reached at the dedicated /app
            # path (HONESTLY_WEBAPP_URL=https://usehonestly.co.uk/app) which nginx proxies here.
            # Serving it at "/" too keeps direct :8080 access and local dev working.
            try:
                with open(os.path.join(HERE, "webapp", "index.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8", no_store=True)
            except FileNotFoundError:
                return self._send(500, "webapp/index.html missing", "text/plain")
        if path.startswith("/img/"):
            name = os.path.basename(path)
            # Cached per-property imagery (frontage / route map) lives in CACHE; the brand
            # assets (logo-icon.png, logo-wordmark-clean.png) live in site/img and are served
            # here too so the Mini App can use the EXACT logo files, identical to the landing.
            fp = os.path.join(CACHE, name)
            if not os.path.exists(fp):
                cand = os.path.join(HERE, "site", "img", name)
                if os.path.exists(cand):
                    fp = cand
            if os.path.exists(fp):
                ct = "image/png" if name.endswith(".png") else "image/jpeg"
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), ct)
            return self._send(404, "not found", "text/plain")
        if path.startswith("/r/"):
            # hosted interactive report: /r/<token> serves the byte-identical HTML the
            # buyer was sent, looked up in store.py. Expired/revoked/unknown -> branded page.
            tok = path[3:].strip("/")
            res = store.resolve_token(tok) if tok else {"ok": False, "reason": "unknown"}
            if res.get("ok") and res.get("html"):
                return self._send(200, res["html"], "text/html; charset=utf-8")
            reason = res.get("reason", "unknown")
            code = 410 if reason in ("expired", "revoked") else 404
            return self._send(code, _link_gone_page(reason), "text/html; charset=utf-8")
        if path.startswith("/p/"):
            # Purchased product document: /p/<share_token> serves the HTML page built by
            # product_html.render and stored in the purchases table. Permanent - the user
            # can open it from the Library tab any time. 404 if unknown.
            tok = path[3:].strip("/")
            row = store.get_purchase(tok) if tok else None
            if row and row.get("html_body"):
                return self._send(200, row["html_body"], "text/html; charset=utf-8")
            return self._send(404, _link_gone_page("unknown"), "text/html; charset=utf-8")
        if path.startswith("/u/"):
            # Unsubscribe from the blog-PDF email drip: /u/<lead_token> cancels every pending
            # follow-up for that lead's address. The List-Unsubscribe header points here too;
            # the one-click POST variant is handled in do_POST. GET is the human click from the
            # email's visible link. Idempotent and quiet - an old/unknown token just confirms.
            tok = path[3:].strip("/")
            res = store.cancel_sequence(tok) if tok else {"ok": False}
            return self._send(200, _unsub_page(bool(res.get("ok"))),
                              "text/html; charset=utf-8")
        if path.startswith("/dl/"):
            # The blog-PDF lead-capture gate, serving side: /dl/<token> resolves a captured
            # lead -> the slug they asked for -> the stored blog model -> a freshly built
            # PDF of a report we already publish for free. Pure (no API): the PDF is rendered
            # from the model in store, so it can never be stale or drift from the web page.
            tok = path[4:].strip("/")
            res = store.resolve_download(tok) if tok else {"ok": False, "reason": "unknown"}
            if not res.get("ok"):
                return self._send(404, _link_gone_page(res.get("reason", "unknown")),
                                  "text/html; charset=utf-8")
            post = store.get_blog_post(res["slug"], with_html=False, with_model=True)
            model = post.get("model") if post else None
            if not model:
                return self._send(404, _blog_missing_page(), "text/html; charset=utf-8")
            try:
                pdf = area_report.build(model)
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)[:200]}))
            fname = area_report.filename(model)
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(pdf)))
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return self.wfile.write(pdf)
        if path == "/sitemap.xml" or path == "/robots.txt":
            # SEO: the sitemap (written by publish_daily.rebuild_indices) and a minimal
            # robots that points crawlers at it. Both live at the site root.
            if path == "/robots.txt":
                body = ("User-agent: *\nAllow: /\n"
                        "Sitemap: https://usehonestly.co.uk/sitemap.xml\n")
                return self._send(200, body, "text/plain; charset=utf-8")
            fp = _safe_site_path("sitemap.xml")
            if fp and os.path.exists(fp):
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), "application/xml; charset=utf-8")
            return self._send(404, "not found", "text/plain")
        if path == "/blog/feed.xml":
            fp = _safe_site_path("blog/feed.xml")
            if fp and os.path.exists(fp):
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), "application/xml; charset=utf-8")
            return self._send(404, "not found", "text/plain")
        if path.endswith(".csv"):
            # Public raw-data downloads (e.g. the UK City-Centre Index CSV the data study
            # links). Served from the site root via the same traversal-safe resolver, so the
            # "Download the raw data" CTA is a real file, not a 404 - that download is the
            # whole point of an original-data study a journalist can cite.
            fp = _safe_site_path(path.strip("/"))
            if fp and os.path.exists(fp):
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), "text/csv; charset=utf-8")
            return self._send(404, "not found", "text/plain")
        if path == "/blog" or path.startswith("/blog/"):
            # The auto-published blog network. /blog/ is the index, /blog/city/<slug>/ a
            # city hub, /blog/<city>-<district>/ a district report - each a static
            # index.html under SITE_DIR/blog, written by publish_daily.py. A path with no
            # file yet (a district still in the rotation) gets the branded "not yet" page.
            rel = path.strip("/")                     # "blog" | "blog/..." (no leading slash)
            rel = rel + "/index.html" if not rel.endswith(".html") else rel
            fp = _safe_site_path(rel)
            if fp and os.path.exists(fp):
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            return self._send(404, _blog_missing_page(), "text/html; charset=utf-8")
        if path == "/api/packs":
            aud = (q.get("as", ["agent"])[0])
            return self._send(200, json.dumps(packs_payload(aud)))
        if path == "/api/value":
            addr = (q.get("address", [""])[0]).strip()
            if not addr:
                return self._send(400, json.dumps({"error": "address required"}))
            aud = (q.get("as", ["agent"])[0])
            beds = int(q["beds"][0]) if q.get("beds") else None
            asking = int(q["asking"][0]) if q.get("asking") else None
            quoted = int(q["quoted"][0]) if q.get("quoted") else None
            finish = (q.get("finish", ["average"])[0])
            if finish not in ("average", "high", "very_high"): finish = "average"
            # richer condition: derive the tier from the sub-survey signals if sent
            finish, finish_note = _derive_web_finish(
                lambda f: int(q[f][0]) if q.get(f) else None, finish)
            investment = (q.get("investment", ["0"])[0]) in ("1", "true", "yes", "on")
            try:
                d = build(addr, aud, beds=beds, asking=asking, quoted=quoted,
                          finish=finish, investment=investment)
                if finish_note:
                    d["finish_note"] = finish_note
                return self._send(200, json.dumps(d, default=str))
            except SystemExit as e:
                return self._send(404, json.dumps({"error": str(e)}))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)[:200]}))
        return self._send(404, "not found", "text/plain")

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path.startswith("/u/"):
            # RFC 8058 one-click unsubscribe: mail clients POST here (List-Unsubscribe-Post)
            # with no JSON body. Drain and ignore the body, cancel the sequence, return 200.
            try:
                self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
            except Exception:
                pass
            tok = u.path[3:].strip("/")
            if tok:
                store.cancel_sequence(tok)
            return self._send(200, json.dumps({"ok": True}))
        if u.path not in ("/api/invoice", "/api/handoff", "/api/lead", "/api/me",
                          "/api/save", "/api/portfolio", "/api/property",
                          "/api/catalogue", "/api/product",
                          "/api/product_poll", "/api/library",
                          "/api/research/notebook", "/api/research/source",
                          "/api/research/sources", "/api/research/chat", "/api/v1/payments/create_invoice"):
            return self._send(404, "not found", "text/plain")
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, json.dumps({"error": "bad request"}))
        if u.path == "/api/lead":
            # PUBLIC lead-capture gate (NOT a signed Telegram launch): the reader hands
            # over their details on a blog report page to download the free PDF. We capture
            # the lead and mint a /dl/<token> the page then fetches. No Telegram, no payment.
            return self._lead(body)
        # only a genuine, signed Telegram launch can act on behalf of a user
        user = validate_init_data(body.get("initData", ""))
        if not user or not user.get("id"):
            return self._send(403, json.dumps({"error": "Open this inside Telegram first."}))
        uid = user["id"]
        if u.path == "/api/me":
            # The Mini App is a Pro-gated workspace. The bot owns the free valuation; entry to
            # the app requires an active Pro subscription (comp owners always pass).
            pro = bool(bot.subscribed(uid)) or bool(bot.is_comp(uid))
            return self._send(200, json.dumps({"pro": pro,
                                                "name": (user.get("first_name") or "").strip()}))
        if u.path == "/api/handoff":
            return self._handoff(uid, body)
        if u.path == "/api/save":
            return self._save(uid, body)
        if u.path == "/api/portfolio":
            # The Pro workspace "my properties" list - this user's saved valuations, newest first.
            return self._send(200, json.dumps(
                {"properties": store.list_appraisals(str(uid), limit=60)}, default=str))
        if u.path == "/api/property":
            return self._property(uid, body)
        if u.path == "/api/catalogue":
            import catalogue
            aud = body.get("as", "buyer")
            return self._send(200, json.dumps(catalogue.catalog_payload(aud, uid), default=str))
        if u.path == "/api/product":
            return self._product(uid, body)
        if u.path == "/api/product_poll":
            return self._product_poll(uid, body)
        if u.path == "/api/library":
            return self._library(uid, body)
        if u.path == "/api/research/notebook":
            return self._research_notebook(uid, body)
        if u.path == "/api/research/source":
            return self._research_source(uid, body)
        if u.path == "/api/research/sources":
            return self._research_sources(uid, body)
        if u.path == "/api/research/chat":
            return self._research_chat(uid, body)
        if u.path == "/api/v1/payments/create_invoice":
            return self._create_invoice(uid, body)
        pack_id = body.get("pack", "")
        aud = body.get("as", "agent")
        if aud not in ("vendor", "buyer", "agent"):
            aud = "agent"
        try:
            if pack_id == "pro":
                stars = bot.STARS_SUB   # flat £14.99/mo - the sub is intro-independent
                link = create_invoice_link(
                    "Honestly Pro", "Your property workspace: saved properties, the full report "
                    "on each, and the decision tools. Cancel anytime.",
                    "sub", stars, subscription_period=bot.SUB_PERIOD)
                return self._send(200, json.dumps({"link": link}))
            micro_id = (body.get("micro") or "").strip()
            address = (body.get("address") or "").strip()
            if len(address) < 6:
                return self._send(400, json.dumps({"error": "address required"}))
            beds = body.get("beds") or None
            finish = body.get("finish", "average")
            if finish not in ("average", "high", "very_high"):
                finish = "average"
            finish, _ = _derive_web_finish(lambda f: _to_int(body.get(f)), finish)
            investment = bool(body.get("investment"))
            asking = body.get("asking") or None
            quoted = body.get("quoted") or None
            if micro_id:                              # a-la-carte micro-upsell add-on
                m = bot.MICRO_BY.get(micro_id)
                if not m:
                    return self._send(400, json.dumps({"error": "unknown add-on"}))
                sid = save_intent(uid, address, aud, None, beds=beds, finish=finish,
                                  investment=investment, asking=asking, quoted=quoted, micro=micro_id)
                stars, _, gbp = bot.micro_price(m)
                link = create_invoice_link(f"{m['name']} ({gbp})", m["blurb"], f"mbuy:{sid}", stars)
                return self._send(200, json.dumps({"link": link}))
            p = bot.PACK.get(pack_id)
            if not p:
                return self._send(400, json.dumps({"error": "unknown pack"}))
            sid = save_intent(uid, address, aud, pack_id, beds=beds, finish=finish,
                              investment=investment, asking=asking, quoted=quoted)
            stars, _, gbp = bot.pack_price(p)
            link = create_invoice_link(f"{p['name']} ({gbp})",
                                       ", ".join(bot._SHORT[c] for c in p["components"]),
                                       f"mbuy:{sid}", stars)
            return self._send(200, json.dumps({"link": link}))
        except Exception as e:
            return self._send(500, json.dumps({"error": str(e)[:200]}))

    def _lead(self, body):
        """Capture a blog-PDF lead and return the download URL. The reader gave us their
        email (and optionally a name) to download a report we already publish for free;
        we store the lead and hand back /dl/<token>. No payment, no Telegram - this is the
        'simply give us their details as usual' path. Honest 400s on a bad email / unknown
        slug; never reveals whether an email is already on file."""
        email = (body.get("email") or "").strip()
        slug = (body.get("slug") or "").strip()
        name = (body.get("name") or "").strip() or None
        # who the reader says they are (vendor|buyer|agent|other) - captured at PDF request so
        # the follow-up emails and the Telegram offer fit them. Normalised; never blocks the
        # download on its own (the form requires it, but a bad value just stores NULL).
        persona = store.clean_persona(body.get("persona"))
        if not store.valid_email(email):
            return self._send(400, json.dumps({"error": "Please enter a valid email address."}))
        if not slug or not store.get_blog_post(slug, with_html=False):
            return self._send(404, json.dumps({"error": "We couldn't find that report."}))
        tok = store.record_lead(email, slug, name=name, persona=persona, source="blog_pdf")
        if not tok:
            return self._send(500, json.dumps({"error": "Could not prepare your download."}))
        # Email the PDF and enqueue the follow-up drip. Best-effort and OUT of the reader's
        # way: the instant /dl/<token> download is the contract we owe them, so a slow or
        # unconfigured mailer must never delay or fail this response. start() is idempotent and
        # never raises; when SMTP is unconfigured it dry-runs to _outbox and still queues.
        try:
            email_funnel.start(tok, email, slug, name=name)
        except Exception as e:
            print("[lead] funnel.start failed:", str(e)[:160], file=sys.stderr)
        return self._send(200, json.dumps({"ok": True, "url": f"/dl/{tok}"}))

    def _handoff(self, uid, body):
        """Carry the full intake the user entered in the widget across to the bot chat.
        Saves a self-contained intent and returns a t.me deep link; opening it sends
        /start run_<sid> to the bot, which delivers with everything pre-filled - the user
        never re-answers a single question in chat."""
        address = (body.get("address") or "").strip()
        if len(address) < 6:
            return self._send(400, json.dumps({"error": "address required"}))
        aud = body.get("as", "vendor")
        if aud not in ("vendor", "buyer", "agent"):
            aud = "vendor"
        finish = body.get("finish", "average")
        if finish not in ("average", "high", "very_high"):
            finish = "average"
        sid = save_intent(uid, address, aud, None, beds=body.get("beds") or None,
                          finish=finish, investment=bool(body.get("investment")),
                          asking=body.get("asking") or None, quoted=body.get("quoted") or None)
        link = f"https://t.me/{bot.BOT_USERNAME}?start=run_{sid}"
        return self._send(200, json.dumps({"link": link}))

    def _save(self, uid, body):
        """Pro workspace: save the valuation the user just ran in the Mini App into THEIR
        portfolio. We re-run the engine server-side and build the report ourselves, so the stored
        appraisal and the public /r/<token> link are bytes WE generated - never client-supplied
        HTML on a public URL. Tagged to this user (chat_id=uid) and keyed on a deterministic token
        (address+tier), so re-saving the same property updates the row in place. Best-effort
        persistence, real 4xx on bad input."""
        address = (body.get("address") or "").strip()
        if len(address) < 6:
            return self._send(400, json.dumps({"error": "address required"}))
        aud = body.get("as", "vendor")
        if aud not in ("vendor", "buyer", "agent"):
            aud = "vendor"
        finish = body.get("finish", "average")
        if finish not in ("average", "high", "very_high"):
            finish = "average"
        finish, _ = _derive_web_finish(lambda f: _to_int(body.get(f)), finish)
        investment = bool(body.get("investment"))
        beds = _to_int(body.get("beds"))
        asking = _to_int(body.get("asking"))
        quoted = _to_int(body.get("quoted"))
        try:
            r = engine.value(address, KEY, beds=beds, finish=finish, investment=investment)
            d = engine.summary(r, aud, asking=asking, quoted=quoted, n=6)
        except SystemExit as e:
            return self._send(404, json.dumps({"error": str(e)}))
        except Exception as e:
            return self._send(500, json.dumps({"error": str(e)[:200]}))
        resolved = r["subject"]["address"]
        token = "v_" + hashlib.sha1(f"{resolved}|lite".encode("utf-8")).hexdigest()[:22]
        # persist, tagged to this user. INSERT OR REPLACE on the deterministic token -> idempotent.
        store.record_appraisal(d, token=token, address=resolved, audience=aud,
                               finish=r.get("finish"), investment=investment,
                               source=f"app:{uid}", tier="lite", chat_id=str(uid))
        # build the interactive Lite report server-side and host it at /r/<share>, exactly as the
        # bot does (report.build -> (pdf, html); store the html body so the link serves it verbatim).
        url = None
        try:
            import report
            context = None
            try:
                import area_context
                subject = dict(r["subject"])
                subject.setdefault("postcode", engine.postcode_of(subject.get("address", "")))
                context = area_context.gather(subject, summary=d)
            except Exception as e:
                print("[save] area context:", str(e)[:160], file=sys.stderr)
            _, html_path = report.build(r, aud, slug=f"app{uid}", interactive=True,
                                        key=KEY, context=context, tier="lite")
            if html_path and os.path.exists(html_path):
                with open(html_path, encoding="utf-8") as f:
                    html_body = f.read()
                store.record_deliverable(token, "html", path=html_path, body=html_body)
                share = store.mint_token(token)
                if share:
                    url = f"/r/{share}"
        except Exception as e:
            print("[save] report build:", str(e)[:200], file=sys.stderr)
        return self._send(200, json.dumps({"ok": True, "token": token, "url": url,
                                           "central": d.get("central")}, default=str))

    def _property(self, uid, body):
        """The Pro workspace's per-property view: the saved appraisal (verified to belong to THIS
        user) plus its hosted /r/<token> report link. 404 for an unknown token; 403 if it isn't
        theirs (no cross-user reads)."""
        token = (body.get("token") or "").strip()
        ap = store.get_appraisal(token) if token else None
        if not ap:
            return self._send(404, json.dumps({"error": "not found"}))
        if str(ap.get("chat_id") or "") != str(uid):
            return self._send(403, json.dumps({"error": "not your property"}))
        share = store.share_token_for(token)
        out = {"token": token, "address": ap.get("address"), "postcode": ap.get("postcode"),
               "audience": ap.get("audience"), "investment": bool(ap.get("investment")),
               "low": ap.get("low"), "high": ap.get("high"), "central": ap.get("central"),
               "guide": ap.get("guide"), "summary": ap.get("summary"),
               "report_url": f"/r/{share}" if share else None}
        return self._send(200, json.dumps(out, default=str))

    def _product(self, uid, body):
        """Buy/obtain a catalogue.py product.

        - mode='stars': return a Telegram invoice link (non-subscriber or credit-dry path).
        - mode='included'/'credits': build the product document in a daemon thread, return
          {job_id} immediately. The frontend polls /api/product_poll every 3s until done,
          then opens /p/<share_token> via TG.openLink — a real hosted HTML page stored in
          the purchases table and listed in the Library tab. Nobody gets a Telegram message.

        Credits are debited before the thread starts and refunded on failure."""
        import catalogue, product_html
        pid = (body.get("product") or "").strip()
        p = catalogue.get(pid)
        if not p:
            return self._send(400, json.dumps({"error": "unknown product"}))
        address = (body.get("address") or "").strip()
        if len(address) < 6:
            return self._send(400, json.dumps({"error": "address required"}))
        aud = body.get("as", p["profile"])
        if aud not in ("vendor", "buyer", "agent", "investor"):
            aud = "buyer"
        finish = body.get("finish", "average")
        if finish not in ("average", "high", "very_high"):
            finish = "average"
        finish, _ = _derive_web_finish(lambda f: _to_int(body.get(f)), finish)
        investment = bool(body.get("investment"))
        beds = _to_int(body.get("beds"))
        asking = _to_int(body.get("asking"))
        quoted = _to_int(body.get("quoted"))

        mode = catalogue.purchase_mode(uid, p)

        def _stars_link():
            sid = save_intent(uid, address, aud, None, beds=beds, finish=finish,
                              investment=investment, asking=asking, quoted=quoted, product=pid)
            try:
                link = create_invoice_link(f"{p['name']} ({catalogue.gbp(p)})",
                                           p["blurb"], f"mbuy:{sid}", catalogue.price_stars(p))
                return self._send(200, json.dumps({"mode": "stars", "link": link}))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)[:200]}))

        if mode == "stars":
            return _stars_link()
        if mode == "credits" and not bot.spend_credits(uid, p["credits"]):
            return _stars_link()   # ran out between resolve and spend

        # included / credits - build the document in a daemon thread
        _jobs_gc()
        job_id = secrets.token_urlsafe(9)
        with _JOBS_LOCK:
            _JOBS[job_id] = {"status": "building", "uid": str(uid), "ts": time.time()}

        _mode = mode
        _pid = pid
        _address = address
        _aud = aud
        _finish = finish
        _investment = investment
        _beds = beds
        _asking = asking
        _quoted = quoted

        def _do_build():
            try:
                import area_context
                r_raw = engine.value(_address, KEY, beds=_beds, finish=_finish, investment=_investment)
                d = engine.summary(r_raw, _aud, asking=_asking, quoted=_quoted, n=6)
                # Expose the buyer-supplied figures so price-aware products (the need-named
                # diagnostics) can measure the exact gap — engine.summary uses them for the
                # verdict but doesn't surface the raw numbers on the dict.
                if _asking:
                    d["asking"] = _asking
                if _quoted:
                    d["quoted"] = _quoted
                subject = dict(r_raw["subject"])
                try:
                    subject.setdefault("postcode", engine.postcode_of(subject.get("address", "")))
                except Exception:
                    pass
                ctx = None
                try:
                    ctx = area_context.gather(subject, summary=d)
                except Exception as ce:
                    print("[product] context:", str(ce)[:160], file=sys.stderr)
                content = catalogue.build(_pid, ctx, d, d, _aud)
                if not content:
                    content = [f"<b>{p['name']}</b>", p["blurb"],
                               "This product is built from a property valuation. Run a valuation "
                               "on this address first, then try again."]
                html_body = product_html.render(p["name"], p["blurb"], content, _address, _aud)
                share_tok = store.record_purchase(
                    uid=str(uid), pid=_pid, address=_address,
                    title=p["name"], blurb=p["blurb"], profile=_aud,
                    html_body=html_body)
                if share_tok:
                    with _JOBS_LOCK:
                        _JOBS[job_id].update({"status": "done",
                                              "url": f"/p/{share_tok}",
                                              "title": p["name"]})
                else:
                    with _JOBS_LOCK:
                        _JOBS[job_id].update({"status": "error", "error": "storage failed"})
                    if _mode == "credits":
                        bot.refund_credits(uid, p["credits"])
            except Exception as e:
                print("[product] build:", str(e)[:200], file=sys.stderr)
                with _JOBS_LOCK:
                    _JOBS[job_id].update({"status": "error", "error": str(e)[:120]})
                if _mode == "credits":
                    bot.refund_credits(uid, p["credits"])

        threading.Thread(target=_do_build, daemon=True).start()
        return self._send(200, json.dumps({"mode": mode, "job_id": job_id}))

    def _product_poll(self, uid, body):
        """Poll for a background product build. Returns {status, url, title} when done."""
        job_id = (body.get("job_id") or "").strip()
        if not job_id:
            return self._send(400, json.dumps({"error": "job_id required"}))
        with _JOBS_LOCK:
            job = dict(_JOBS.get(job_id) or {})
        if not job:
            return self._send(404, json.dumps({"status": "unknown"}))
        if str(job.get("uid", "")) != str(uid):
            return self._send(403, json.dumps({"error": "not your job"}))
        return self._send(200, json.dumps({
            "status": job.get("status", "building"),
            "url": job.get("url"),
            "title": job.get("title"),
            "error": job.get("error"),
        }))

    def _library(self, uid, body):
        """The Pro Library tab: both valuation reports (appraisals with html) and purchased
        product documents (purchases table). Returns two lists so the frontend can render
        distinct card types."""
        reports = []
        for ap in store.list_appraisals(str(uid), limit=60):
            if ap.get("share_token") or ap.get("has_html"):
                url = (f"/r/{ap['share_token']}" if ap.get("share_token") else None)
                reports.append({"kind": "report", "title": ap.get("address") or "Property",
                                 "subtitle": "Valuation report",
                                 "address": ap.get("address"), "url": url,
                                 "created_at": ap.get("created_at")})
        products = []
        for pu in store.list_purchases(str(uid), limit=60):
            products.append({"kind": "product", "title": pu.get("title") or "Document",
                              "subtitle": pu.get("address") or "",
                              "address": pu.get("address"),
                              "url": f"/p/{pu['share_token']}",
                              "created_at": pu.get("created_at")})
        # newest first across both lists
        items = sorted(reports + products, key=lambda x: -(x.get("created_at") or 0))
        return self._send(200, json.dumps({"items": items}, default=str))

    # ---------------------------------------------------------------- research (Open Notebook)
    def _research_notebook(self, uid, body):
        """Ensure an Open Notebook notebook exists for this property and return its id.
        Creates it on first call and persists the id in store.property_notebooks so
        subsequent opens are instant (no duplicate notebooks). 503 when the service
        is offline - the frontend degrades gracefully."""
        import notebook_client
        if not notebook_client.ping():
            return self._send(503, json.dumps({"error": "Research service offline"}))
        token = (body.get("token") or "").strip()
        ap = store.get_appraisal(token) if token else None
        if not ap:
            return self._send(404, json.dumps({"error": "not found"}))
        if str(ap.get("chat_id") or "") != str(uid):
            return self._send(403, json.dumps({"error": "not your property"}))
        nb_id = store.get_notebook_id(token)
        if not nb_id:
            name = f"Honestly: {(ap.get('address') or token)[:60]}"
            desc = f"Research for {ap.get('address', '')}"
            nb_id = notebook_client.ensure_notebook(name, desc)
            if nb_id:
                store.set_notebook_id(token, nb_id)
        if not nb_id:
            return self._send(503, json.dumps({"error": "Could not create research notebook"}))
        return self._send(200, json.dumps({"ok": True, "notebook_id": nb_id}))

    def _research_source(self, uid, body):
        """Add a URL or text passage to this property's research notebook."""
        import notebook_client
        token = (body.get("token") or "").strip()
        ap = store.get_appraisal(token) if token else None
        if not ap:
            return self._send(404, json.dumps({"error": "not found"}))
        if str(ap.get("chat_id") or "") != str(uid):
            return self._send(403, json.dumps({"error": "not your property"}))
        nb_id = store.get_notebook_id(token)
        if not nb_id:
            return self._send(400, json.dumps({"error": "Open the research notebook first"}))
        url     = (body.get("url") or "").strip()
        content = (body.get("content") or "").strip()
        title   = (body.get("title") or "").strip()
        if url:
            src_id = notebook_client.add_source_url(nb_id, url, title or url[:60])
        elif content:
            src_id = notebook_client.add_source_text(nb_id, content, title or "Research note")
        else:
            return self._send(400, json.dumps({"error": "url or content required"}))
        if not src_id:
            return self._send(503, json.dumps({"error": "Could not add that source"}))
        return self._send(200, json.dumps({"ok": True, "source_id": src_id}))

    def _research_sources(self, uid, body):
        """List the sources in this property's research notebook."""
        import notebook_client
        token = (body.get("token") or "").strip()
        ap = store.get_appraisal(token) if token else None
        if not ap:
            return self._send(404, json.dumps({"error": "not found"}))
        if str(ap.get("chat_id") or "") != str(uid):
            return self._send(403, json.dumps({"error": "not your property"}))
        nb_id = store.get_notebook_id(token)
        if not nb_id:
            return self._send(200, json.dumps({"ok": True, "sources": []}))
        sources = notebook_client.list_sources(nb_id)
        return self._send(200, json.dumps({"ok": True, "sources": sources}, default=str))

    def _research_chat(self, uid, body):
        """Send a message to the AI research assistant for this property.

        The assistant's context includes the property address, valuation range, and
        audience (buyer / seller / agent). A chat session is opened on first call and
        the session_id is persisted so follow-up questions retain context."""
        import notebook_client
        token = (body.get("token") or "").strip()
        ap = store.get_appraisal(token) if token else None
        if not ap:
            return self._send(404, json.dumps({"error": "not found"}))
        if str(ap.get("chat_id") or "") != str(uid):
            return self._send(403, json.dumps({"error": "not your property"}))
        nb_id = store.get_notebook_id(token)
        if not nb_id:
            return self._send(400, json.dumps({"error": "Open the research notebook first"}))
        message = (body.get("message") or "").strip()
        if not message:
            return self._send(400, json.dumps({"error": "message required"}))
        session_id = store.get_notebook_session(token)
        if not session_id:
            session_id = notebook_client.start_chat(nb_id)
            if session_id:
                store.set_notebook_session(token, session_id)
        if not session_id:
            return self._send(503, json.dumps({"error": "Could not start research session"}))
        context = {
            "property": ap.get("address", ""),
            "postcode": ap.get("postcode", ""),
            "audience": ap.get("audience", ""),
            "valuation_central": ap.get("central"),
            "valuation_low": ap.get("low"),
            "valuation_high": ap.get("high"),
        }
        reply = notebook_client.send_message(session_id, message, context=context)
        if reply is None:
            return self._send(503, json.dumps({"error": "No response from research assistant"}))
        return self._send(200, json.dumps({"ok": True, "session_id": session_id, "reply": reply}))

    def _create_invoice(self, uid, body):
        """Create a Telegram invoice link for native in-app payment.

        The frontend calls this instead of constructing deep-links.
        Uses the existing create_invoice_link() to talk to Telegram.
        Supports product purchases, subscriptions, and credit top-ups.
        """
        import json

        product_id = body.get("product_id") or None
        sub_tier = body.get("sub_tier") or None
        credit_pack_gbp = body.get("credit_pack_gbp") or None

        title = ""
        description = ""
        gbp_price = 0.0
        payload_data = {}

        if product_id:
            # Product upsell - use existing bot.MICRO_BY lookup
            m = bot.MICRO_BY.get(product_id)
            if m:
                title = m.get("name", product_id)
                description = m.get("blurb", "")
                stars, _, gbp = bot.micro_price(m)
                gbp_price = gbp
                payload_data = {"type": "upsell", "product_id": product_id, "gbp_price": gbp_price}
            else:
                return self._send(400, json.dumps({"error": "unknown product"}))
        elif sub_tier:
            if sub_tier not in ("plus", "pro"):
                return self._send(400, json.dumps({"error": "sub_tier must be 'plus' or 'pro'"}))
            # Use existing bot subscription pricing
            stars = bot.STARS_SUB if sub_tier == "pro" else getattr(bot, "STARS_PLUS", 75)
            gbp_price = round(stars / 50, 2)
            tier_names = {"plus": "Honestly Plus", "pro": "Honestly Pro"}
            tier_descs = {
                "plus": "3 AVMs/day, Room posting, ad-free, £5 monthly credit",
                "pro": "Unlimited AVMs, custom branding, advanced maps, £10 monthly credit",
            }
            title = tier_names.get(sub_tier, sub_tier)
            description = tier_descs.get(sub_tier, "")
            payload_data = {"type": "subscription", "tier": sub_tier, "gbp_price": gbp_price}
        elif credit_pack_gbp and credit_pack_gbp > 0:
            credits = int(credit_pack_gbp * 100)
            title = f"{credits} Credits"
            description = f"Top up your Honestly credit balance with {credits} credits"
            gbp_price = credit_pack_gbp
            stars = int(gbp_price * 50)
            payload_data = {"type": "credit_topup", "gbp_price": gbp_price, "credits": credits}
        else:
            return self._send(400, json.dumps({"error": "One of product_id, sub_tier, or credit_pack_gbp is required"}))

        try:
            invoice_url = create_invoice_link(title, description, json.dumps(payload_data), stars)
        except Exception as e:
            return self._send(502, json.dumps({"error": str(e)[:200]}))

        return self._send(200, json.dumps({
            "ok": True,
            "invoice_url": invoice_url,
            "xtr_amount": stars,
            "gbp_price": gbp_price,
            "title": title,
            "payload": payload_data,
        }))

def packs_payload(audience):
    """Pricing for the Mini App, rendered in this reader's language - one source of truth
    (bot.PACKS) so the web surface and the chat never quote different numbers."""
    labels = bot._component_labels(audience)
    out = {"intro": bool(bot.INTRO), "packs": []}
    prev = []
    for p in bot.PACKS:
        added = [c for c in p["components"] if c not in prev]
        stars, stars_str, gbp = bot.pack_price(p)
        out["packs"].append({"id": p["id"], "name": p["name"], "stars": stars, "gbp": gbp,
                             "includes": [labels[c] for c in added],
                             # the FULL deliverable list, so the Mini App can present the hero
                             # Decision pack with every line a ✓ - exactly like the bot does
                             "all_includes": [labels[c] for c in p["components"]],
                             "plus_above": bool(prev)})
        prev = p["components"]
    psub = bot.STARS_SUB          # flat £14.99/mo - the sub is intro-independent
    sub_gbp = bot._gbp(psub)
    # anchor + Pro copy come straight from bot.py so the chat and the web funnel never
    # diverge in either the numbers OR the way the offer is framed.
    out["anchor"] = bot._anchor_line(audience)
    out["pro"] = {"id": "pro", "name": "Pro", "stars": psub, "gbp": sub_gbp,
                  "packs_per_month": bot.SUB_PACKS_PER_MONTH,
                  "line": bot._pro_line(audience, sub_gbp),   # full line (name + price + pitch)
                  "pitch": bot._pro_pitch(audience)}          # bare pitch for the web block header
    # à-la-carte micro-upsells (beside Pro): the full catalogue, audience-filtered, one source
    # of truth (bot.MICRO) so the Mini App and the bot never quote a different add-on or price.
    micros = []
    for m in bot.MICRO:
        if m["id"] in bot.LITE_INCLUDED:        # never sell what the free Lite report already gave
            continue
        if not bot._micro_fits(m, audience):
            continue
        s, _str, gbp = bot.micro_price(m)
        micros.append({"id": m["id"], "name": m["name"], "stars": s, "gbp": gbp, "blurb": m["blurb"]})
    out["micros"] = micros
    return out

def main():
    # Persist every valuation this server runs (store + update in place). Set in the live
    # entrypoint, not at import, so importing this module under test never writes to the DB.
    os.environ.setdefault("HONESTLY_AUTOSTORE", "1")
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    if not KEY:
        sys.exit("PROPERTYDATA_KEY not set (env or .env)")
    print(f"Honestly server on http://localhost:{args.port}  (Ctrl-C to stop)")
    ThreadingHTTPServer(("0.0.0.0", args.port), H).serve_forever()

if __name__ == "__main__":
    main()
