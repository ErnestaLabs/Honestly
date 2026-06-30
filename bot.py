#!/usr/bin/env python3
"""bot.py - the valuation engine as a Telegram bot. No UI to build, payments built in.

Delivery surface for the engine: a user sends an address, picks who they are
(vendor / buyer / agent), and gets a mobile-native, evidence-backed valuation - 
plus the Street View frontage and, for agents, an optimised door-knock map.

Monetisation (Telegram Stars, in-app, no card processor):
  • EVERY valuation is free at Lite tier - the figure, the strict sold comparables with
    HM Land Registry links, and the full local facts, with the Pro decision-layer locked.
    Lite is the hook, the trust-builder AND a permanent public asset (each is persisted and
    served at /r/<token>); we never give the full Decision pack away.
  • Pro is the paid UPGRADE on top of any Lite valuation - the decision layer no portal has:
    the impact dashboard, pricing/negotiation strategy, scenarios and the evidence room
    (Stars ~= £ x 60 at what the buyer pays; clean rounded figures, no 99p add-ons):
      Evidence pack   ⭐300 (~£5)   PDF + interactive HTML report (+ audio walkthrough)
      Decision pack   ⭐600 (~£10)  the above + action plan + door-knock map + email/script
  • Pro subscription ⭐1800/mo (~£30) - 10 full packs a month, for repeat (agent) use.
  • A 50% introductory launch price applies to every figure, shown honestly as an
    "Introductory price" (no fabricated was/now); flip bot.INTRO to False for standard.
The products differ by audience (agent / vendor / buyer); see products.py. The free Lite
valuation is unlimited; Pro is the buy-as-you-go (or subscription) upgrade.

Star amounts are integers and the Star/GBP rate is not fixed - the table below is
set to today's approximate mapping (~$0.02/Star) and should be tuned to the live rate.

Run:
  add TELEGRAM_BOT_TOKEN=... to .env   (from @BotFather)
  python bot.py
Raw Bot API over urllib - no third-party dependencies, same as the rest of the engine.
"""
import os, sys, json, time, html, datetime, base64, urllib.parse, urllib.request, urllib.error
import threading, tempfile
import engine, maps_tools, cardimg, products, decision_models
# Best-effort Reddit market pulse
try:
    import reddit_intel as _ri_mod
    _HAS_PULSE = True
except ImportError:
    _HAS_PULSE = False

# Some hosts advertise an IPv6 (AAAA) route that does not actually work, so
# urllib tries IPv6 first and stalls on every Telegram call (curl falls back to
# IPv4 and is fine). Force IPv4-only resolution so the bot can't hang on that.
import socket as _socket
_orig_getaddrinfo = _socket.getaddrinfo
def _ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, _socket.AF_INET, type, proto, flags)
_socket.getaddrinfo = _ipv4_only

# systemd captures stdout to a file, which Python block-buffers - logs would never
# appear. Line-buffer so journald/log files show activity in real time.
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(line_buffering=True)
    except Exception: pass

def _utcnow():
    """Naive UTC now (no tz suffix) - utcnow() is deprecated but we keep the same
    string shape so existing ISO comparisons stay consistent."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

def log(*a):
    print(_utcnow().strftime("%H:%M:%S"), *a)

def _fmt_ts(ts):
    """Unix ts -> 'YYYY-MM-DD HH:MM' (UTC), or '' when missing - for the user-export CSV."""
    try:
        return datetime.datetime.utcfromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""

# ---- pricing (Telegram Stars; ~60 Stars per £ at what the buyer pays) -------
# Two one-off packs - a single valuation is bought outright, no membership needed -
# plus a Pro subscription for repeat (agent) use. Clean rounded Star figures: a
# defensible valuation is not sold like a 99p app, and there are no sub-£1 add-ons.
# The components mean different products by audience - see products.py.
STARS_PER_GBP = 60

PACKS = [
    {"id": "consumer", "stars": 300, "name": "Evidence pack",
     "components": ["report", "html"]},
    {"id": "full",     "stars": 600, "name": "Decision pack",
     "components": ["report", "html", "plan", "map", "email"]},
]
PACK = {p["id"]: p for p in PACKS}
ALL_COMPONENTS = ["report", "html", "plan", "map", "email"]

STARS_SUB  = 900        # Pro: a flat £14.99/mo (900⭐ / 60⭐-per-£ -> charm £14.99). The
                        # subscription is NOT subject to the launch INTRO discount - it is a
                        # stable recurring price (a recurring sub that later "un-discounts" is
                        # a bad contract). One-off packs/products still take INTRO.
SUB_PERIOD = 2592000    # 30 days, for recurring Star subscriptions
SUB_PACKS_PER_MONTH = 10
# Hybrid Pro economics: each cycle a subscriber gets a pool of CREDITS. The flagship report + the
# area/market reads are INCLUDED free; the premium packs/toolkits cost credits (1-2 each, bundles
# 8-12); a non-subscriber buys any product standalone at its charm Stars price. The pool resets
# on each renewal (grant_sub). 10 credits comfortably covers a few packs a month.
MONTHLY_CREDITS = 10

# 50% introductory launch price on every figure. A genuine launch discount, shown as
# an "Introductory price" (ASA-compliant - never a fabricated was/now). Flip to False
# to charge the standard prices above.
INTRO = True
INTRO_PCT = 50

def _stars(base):
    """Apply the introductory discount, rounded to a whole Star (Stars are integers)."""
    return max(1, round(base * (100 - INTRO_PCT) / 100)) if INTRO else base

def _charm(v):
    """Charm pricing (price psychology): every price ends in .99 - £15 -> £14.99, £5 -> £4.99,
    £30 -> £29.99. Snaps the true GBP to the nearest whole pound, then drops a penny, with a
    £0.99 floor. One place, so the bot, Mini App, landing and PDF all show charm prices."""
    return max(0.99, round(v) - 0.01)

def _gbp(stars):
    """Charm GBP display for a Star price at the buyer-facing rate (£14.99, £4.99, £29.99)."""
    return f"£{_charm(stars / STARS_PER_GBP):.2f}"

def pack_price(p):
    """(stars_charged, '⭐150', '£2.50') - the live price for a pack, intro applied."""
    s = _stars(p["stars"])
    return s, f"⭐{s}", _gbp(s)

INTRO_NOTE = "✨ <b>Introductory price</b> - 50% off while we launch."

# short label per component, for invoice descriptions
_SHORT = {"report": "full report unlocked", "html": "interactive report unlocked",
          "plan": "action plan", "map": "20 targets + map", "email": "email template"}

def _component_labels(audience):
    """What each component is called for this reader, so the ladder reads in their language.
    CRITICAL: the free Lite report already gives the PDF + interactive report with the Pro
    sections LOCKED. So a pack does NOT sell 'a PDF' (you have one) - it sells the UNLOCK: the
    same report with the decision layer switched on. The labels must say that, or it reads as
    re-selling what was already given."""
    L = {"report": "Your report, fully UNLOCKED - the Pro decision layer switched on inside it: "
                   "the price-influence ledger, scenario pricing, data-spine verification, live "
                   "positioning and the market outlook (all frosted/locked in the free report)",
         "html":   "The interactive report with every Pro panel LIVE - the locked panels in your "
                   "free version, unfrosted and tappable"}
    if audience == "agent":
        L["plan"]  = "Listing-win action plan"
        L["map"]   = "Nearby proof-row route, mapped"
        L["email"] = "Ready-to-send prospecting email"
    elif audience == "vendor":
        L["plan"]  = "Sell-for-the-most action plan"
        L["map"]   = "Nearby proof rows, mapped"
        L["email"] = "Agent-vetting email template"
    else:  # buyer
        L["plan"]  = "Offer + negotiation plan"
        L["map"]   = "Nearby proof rows, mapped"
        L["email"] = "Offer email to the agent"
    return L

# ---- micro-upsells (à-la-carte, beside Pro) ---------------------------------
# Every item is a REAL artifact the code already produces (no invented SKUs): each maps to a
# producer module that builds it from this property's own data. Priced as small Stars (£1-£3),
# bought one-off, listed in the Mini App, and surfaced intelligently after the free Lite report
# (see suggest_micros). 'aud' = audiences it fits ('all' or a set); 'sig' = the live signal that
# makes it relevant (used to order suggestions). Delivery is dispatched in deliver_micro().
MICRO = [
    {"id": "interactive", "stars": 120, "name": "Interactive report",
     "blurb": "Tap any comparable to open its HM Land Registry sold record.", "aud": "all"},
    {"id": "scenario", "stars": 150, "name": "Scenario pricing matrix",
     "blurb": "The same sold evidence re-run at any asking price - what each likely costs in time on market.",
     "aud": {"vendor", "agent", "investor"}, "sig": "stuck"},
    {"id": "plan", "stars": 180, "name": "Action plan",
     "blurb": "Your costed, step-by-step plan to act on the number.", "aud": "all"},
    {"id": "ledger", "stars": 120, "name": "Price-influence ledger",
     "blurb": "Every price-bearing factor, its source and direction - the full glass box.", "aud": "all"},
    {"id": "verify", "stars": 90, "name": "Data-spine verification",
     "blurb": "Direct public-fact checks of the subject's attributes, source by source.", "aud": "all"},
    {"id": "map", "stars": 120, "name": "Nearby proof rows + route",
     "blurb": "The nearest comparable sales pinned, with an opt-route map.", "aud": {"agent", "vendor"}},
    {"id": "email", "stars": 90, "name": "Ready-to-send email / script",
     "blurb": "The message to send your agent, vendor or buyer - written for you.", "aud": "all"},
    {"id": "area", "stars": 90, "name": "Area & amenities report",
     "blurb": "What is within a short walk - transport, shops, schools, green space.", "aud": "all"},
    {"id": "safety", "stars": 90, "name": "Safety report",
     "blurb": "Street-level recorded crime near the property, latest published month.", "aud": "all", "sig": "crime"},
    {"id": "environment", "stars": 90, "name": "Flood & air-quality report",
     "blurb": "Environment Agency flood monitoring and local air quality at this point.", "aud": "all", "sig": "flood"},
    {"id": "planning", "stars": 90, "name": "Planning & development nearby",
     "blurb": "Recent planning applications and what is changing around the property.", "aud": "all", "sig": "planning"},
    {"id": "schools", "stars": 90, "name": "Schools & Ofsted",
     "blurb": "Nearest schools with their official Ofsted ratings.", "aud": "all"},
    {"id": "solar", "stars": 90, "name": "Solar & energy potential",
     "blurb": "Roof solar potential and the energy picture for this property.", "aud": {"vendor", "buyer", "investor"}, "sig": "epc"},
    {"id": "material", "stars": 60, "name": "Full material information",
     "blurb": "The material facts a buyer is entitled to: EPC and council-tax detail.", "aud": "all"},
    {"id": "netproceeds", "stars": 90, "name": "Net proceeds / costs to buy",
     "blurb": "What actually lands in your pocket (or what the purchase really costs), SDLT included.",
     "aud": {"vendor", "buyer", "investor"}, "sig": "money"},
    {"id": "market", "stars": 120, "name": "Market analysis & sentiment",
     "blurb": "The local market read - momentum, demand and what people in the area are saying.", "aud": "all"},
]
# The guide upsells are DECLARED in guides.py and folded in here automatically - a new guide
# needs no edit to this file (catalogue, delivery, deep-link buy and the in-report hyperlink
# all derive from the guides registry). Each is a distinct product: a topic guide, never the
# valuation again.
try:
    import guides as _guides
    MICRO += [dict(g) for g in _guides.MICROS]
except Exception:
    _guides = None
MICRO_BY = {m["id"]: m for m in MICRO}

# Already delivered FREE inside the Lite report - never sell these back to someone who just
# received them in chat ("don't sell the PDF/facts you just gave"). They stay in MICRO_BY so a
# legacy id still resolves, but they are filtered out of every SELLABLE surface (the in-chat
# offer and the Mini App). What we DO sell at these moments is the INTERPRETATION: the topic
# guides (planning_guide, flood_guide...) and the Pro decision modules - things Lite does not include.
LITE_INCLUDED = {"interactive", "material", "area", "safety", "environment", "planning", "schools"}

def sellable_micros():
    """The micro-upsells we may actually offer - excludes anything already free in Lite."""
    return [m for m in MICRO if m["id"] not in LITE_INCLUDED]

def micro_price(m):
    """(stars_charged, '⭐60', '£1') for a micro-upsell, intro discount applied."""
    s = _stars(m["stars"])
    return s, f"⭐{s}", _gbp(s)

def _micro_fits(m, audience):
    a = m.get("aud", "all")
    return a == "all" or audience in a

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "entitlements.json")
INTENTS = os.path.join(HERE, "miniapp_intents.json")     # Mini App purchase intents (written by server.py)
TESTI = os.path.join(HERE, "testimonials.json")          # collected testimonials (metadata)
TDIR  = os.path.join(HERE, "testimonials")               # downloaded testimonial videos/photos
PENDING = {}        # uid -> {"address":..., "audience":..., "r":...}  (in-memory)
AWAIT_TESTI = set() # uids we're currently waiting on a testimonial from
BOT_USERNAME = "usehonestly_bot"   # used for /invite deep links; refreshed from getMe at startup

# ---------------------------------------------------------------- Bot API
def token():
    maps_tools._load_env()
    t = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not t:
        sys.exit("Set TELEGRAM_BOT_TOKEN in .env (get one from @BotFather)")
    return t

def webapp_url():
    """HTTPS URL of the Mini App (server.py /webapp). Set HONESTLY_WEBAPP_URL in .env
    to the public https address; empty when unset so the bot degrades to chat-only."""
    maps_tools._load_env()
    return (os.environ.get("HONESTLY_WEBAPP_URL") or "").strip()

def public_base():
    """The public site origin that serves /r/<token> hosted reports - ONLY a server we know
    is actually deployed and reachable. Prefers the explicit HONESTLY_PUBLIC_URL, else the
    origin of the Mini App URL (Telegram forces HONESTLY_WEBAPP_URL to be a live HTTPS server,
    and it is the same server.py that serves /r/, so that origin is genuinely reachable).

    Returns "" when neither is configured. We deliberately do NOT fall back to a hardcoded
    'https://usehonestly.co.uk': emitting a link to a domain that may have no DNS / no running
    server would hand the recipient a dead URL, which breaks the honesty contract. No
    configured server -> no link -> callers fall back to the offline-file-only message."""
    maps_tools._load_env()
    explicit = (os.environ.get("HONESTLY_PUBLIC_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    wa = webapp_url()
    if wa:
        p = urllib.parse.urlsplit(wa)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}"
    return ""

def tg(method, **params):
    url = f"https://api.telegram.org/bot{token()}/{method}"
    data = json.dumps(params).encode()
    for attempt in range(3):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try: body = json.loads(e.read().decode("utf-8", "ignore"))
            except Exception: body = {"ok": False, "error": e.code}
            # 429 rate-limit / 5xx server blips: back off and retry, honouring retry_after
            if e.code in (429, 500, 502, 503) and attempt < 2:
                wait = (body.get("parameters", {}) or {}).get("retry_after", attempt + 1)
                time.sleep(min(wait, 5)); continue
            return body
        except Exception as e:
            if attempt < 2:
                time.sleep(1); continue
            return {"ok": False, "error": str(e)[:120]}

def tg_photo(chat_id, path, caption="", keyboard=None):
    """multipart upload - the one call that isn't plain JSON."""
    boundary = "----pd" + str(int(time.time() * 1000))
    parts = []
    def field(name, val):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{val}\r\n".encode())
    field("chat_id", str(chat_id))
    if caption: field("caption", caption); field("parse_mode", "HTML")
    if keyboard: field("reply_markup", json.dumps({"inline_keyboard": keyboard}))
    with open(path, "rb") as f: blob = f.read()
    parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; "
                  f"filename=\"{os.path.basename(path)}\"\r\nContent-Type: image/jpeg\r\n\r\n").encode())
    parts.append(blob); parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(f"https://api.telegram.org/bot{token()}/sendPhoto", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return json.load(r)
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}

def tg_document(chat_id, path, caption="", keyboard=None, mime="application/pdf"):
    """multipart sendDocument - delivers the real file (PDF report, interactive HTML)
    so the user gets a document they can open, save and forward, not a picture of one."""
    boundary = "----pd" + str(int(time.time() * 1000))
    parts = []
    def field(name, val):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{val}\r\n".encode())
    field("chat_id", str(chat_id))
    if caption: field("caption", caption); field("parse_mode", "HTML")
    if keyboard: field("reply_markup", json.dumps({"inline_keyboard": keyboard}))
    with open(path, "rb") as f: blob = f.read()
    parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; "
                  f"filename=\"{os.path.basename(path)}\"\r\nContent-Type: {mime}\r\n\r\n").encode())
    parts.append(blob); parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(f"https://api.telegram.org/bot{token()}/sendDocument", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r: return json.load(r)
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}

def tg_audio(chat_id, path, caption="", title="Valuation walkthrough", performer="Honestly"):
    """multipart sendAudio - the spoken glass-box walkthrough (mp3). Best-effort:
    a failed upload never blocks the rest of the delivery, the text card already landed."""
    boundary = "----pd" + str(int(time.time() * 1000))
    parts = []
    def field(name, val):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{val}\r\n".encode())
    field("chat_id", str(chat_id))
    if caption: field("caption", caption); field("parse_mode", "HTML")
    if title: field("title", title)
    if performer: field("performer", performer)
    with open(path, "rb") as f: blob = f.read()
    parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"audio\"; "
                  f"filename=\"{os.path.basename(path)}\"\r\nContent-Type: audio/mpeg\r\n\r\n").encode())
    parts.append(blob); parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(f"https://api.telegram.org/bot{token()}/sendAudio", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r: return json.load(r)
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}

def say(chat_id, text, keyboard=None):
    p = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if keyboard: p["reply_markup"] = {"inline_keyboard": keyboard}
    return tg("sendMessage", **p)

TG_MAX = 4000  # headroom below Telegram's 4096 hard limit

def say_long(chat_id, text, keyboard=None):
    """Send text to Telegram, splitting into ≤TG_MAX chunks at paragraph breaks when needed."""
    if len(text) <= TG_MAX:
        return say(chat_id, text, keyboard=keyboard)
    paras = text.split("\n\n")
    chunks, cur, cur_len = [], [], 0
    for para in paras:
        seg = len(para) + (2 if cur else 0)
        if cur_len + seg > TG_MAX and cur:
            chunks.append("\n\n".join(cur))
            cur, cur_len = [para], len(para)
        else:
            cur.append(para); cur_len += seg
    if cur:
        chunks.append("\n\n".join(cur))
    result = None
    for i, chunk in enumerate(chunks):
        result = say(chat_id, chunk, keyboard=(keyboard if i == len(chunks) - 1 else None))
        if not (result or {}).get("ok"):
            log(f"say_long chunk {i+1}/{len(chunks)} failed:", (result or {}).get("description", "?")[:80])
            break
    return result

# ---------------------------------------------------------------- entitlements
def load_ent():
    try:
        with open(STATE, encoding="utf-8") as f: return json.load(f)
    except Exception: return {}
def save_ent(e):
    with open(STATE, "w", encoding="utf-8") as f: json.dump(e, f, indent=2)
def subscribed(uid):
    e = load_ent().get(str(uid), {})
    if e.get("comp"):                      # permanent comp (e.g. the PROPHET owner code) - always unlocked
        return True
    until = e.get("sub_until")
    return bool(until and until > _utcnow().isoformat())
def grant_sub(uid):
    e = load_ent()
    now = _utcnow()
    rec = e.setdefault(str(uid), {})
    rec["sub_until"] = (now + datetime.timedelta(seconds=SUB_PERIOD)).isoformat()
    rec["sub_period_start"] = now.isoformat()   # resets the monthly allowances each cycle
    rec["sub_used"] = 0
    rec["credits"] = MONTHLY_CREDITS            # hybrid pool: packs/bundles draw on this each cycle
    save_ent(e)
def follow_area(uid, chat_id, slug):
    """Record that this user wants updates for a postcode-district report (the blog's
    'follow on Telegram' deep link, /start sub_<slug>). Stored in the same entitlements file,
    under the user's record, alongside their chat_id - so the area-update sender (the rooms
    project, built later) can read who follows what and message them right here. Capture now,
    ping later: the record is real, so the promise on the button is real, never a fake
    mechanic. Returns the normalised slug followed (or '')."""
    slug = (slug or "").strip().lower()
    e = load_ent()
    rec = e.setdefault(str(uid), {})
    rec["chat_id"] = chat_id
    follows = rec.setdefault("follows", [])
    if slug and slug not in follows:
        follows.append(slug)
    save_ent(e)
    return slug
def sub_usage(uid):
    """(used_this_period, cap). cap is None for comp (PROPHET) - unlimited."""
    rec = load_ent().get(str(uid), {})
    if rec.get("comp"):
        return (0, None)
    return (rec.get("sub_used", 0), SUB_PACKS_PER_MONTH)
def bump_sub_usage(uid):
    """Count one full-kit valuation against the Pro monthly allowance."""
    e = load_ent(); rec = e.setdefault(str(uid), {})
    rec["sub_used"] = rec.get("sub_used", 0) + 1
    save_ent(e)
    return rec["sub_used"]
def bump_paid(uid):
    """Record a paid one-off valuation; return the user's running paid count."""
    e = load_ent()
    rec = e.setdefault(str(uid), {})
    rec["paid_count"] = rec.get("paid_count", 0) + 1
    save_ent(e)
    return rec["paid_count"]
def is_comp(uid):
    """The owner's permanent comp (PROPHET): free, unlimited, every component - the only
    path that delivers the full kit at no charge on every valuation (Pro draws an allowance)."""
    return bool(load_ent().get(str(uid), {}).get("comp"))
def had_first(uid):
    """Has this user had a (free, forever) valuation before? Lite is always free; this flag
    only varies first-touch copy and testimonial timing - it is NOT a paywall after one use."""
    return bool(load_ent().get(str(uid), {}).get("first_done"))
def mark_first(uid):
    e = load_ent(); e.setdefault(str(uid), {})["first_done"] = True; save_ent(e)

def consume_intent(sid):
    """Pop a Mini App purchase intent (written by server.py) so it can only deliver once.
    Returns the intent dict, or None if it's unknown/already spent."""
    try:
        with open(INTENTS, encoding="utf-8") as f: store = json.load(f)
    except Exception:
        return None
    intent = store.pop(sid, None)
    if intent is not None:
        try:
            with open(INTENTS, "w", encoding="utf-8") as f: json.dump(store, f, indent=2)
        except Exception: pass
    return intent

# ---- promo codes -------------------------------------------------------------
# value is either an int (that many free valuations) or "comp" (permanent, unlimited
# access - the owner's master code). "comp" flips the same gate as an active sub.
CODES = {"TAUK": 1, "PROPHET": "comp"}
def free_credits(uid):
    return load_ent().get(str(uid), {}).get("free_credits", 0)

# ---- hybrid Pro credit pool (separate from the promo 'free_credits' unlock) -------------------
def credit_balance(uid):
    """This Pro subscriber's remaining monthly credits. Comp (PROPHET) is unlimited -> a large
    sentinel so every product resolves to 'included/credits', never a charge."""
    rec = load_ent().get(str(uid), {})
    if rec.get("comp"):
        return 10 ** 9
    return int(rec.get("credits", 0) or 0)

def spend_credits(uid, n):
    """Debit n credits for a pack/bundle. Comp is unlimited (always True, no decrement). Returns
    True iff the balance covered it (and was decremented). Never goes negative."""
    n = max(1, int(n or 1))
    e = load_ent(); rec = e.setdefault(str(uid), {})
    if rec.get("comp"):
        return True
    have = int(rec.get("credits", 0) or 0)
    if have < n:
        return False
    rec["credits"] = have - n
    save_ent(e)
    return True

def refund_credits(uid, n):
    """Hand n credits back - used when a credit-paid delivery fails, so nobody loses credits for a
    product they didn't receive. No-op for comp."""
    n = max(1, int(n or 1))
    e = load_ent(); rec = e.setdefault(str(uid), {})
    if rec.get("comp"):
        return
    rec["credits"] = int(rec.get("credits", 0) or 0) + n
    save_ent(e)
def redeem_code(uid, code):
    """Apply a promo code once. Returns 'comp' | 'ok' | 'invalid' | 'used'."""
    code = code.upper()
    if code not in CODES: return "invalid"
    e = load_ent(); rec = e.setdefault(str(uid), {})
    if code in rec.get("redeemed", []): return "used"
    grant = CODES[code]
    rec.setdefault("redeemed", []).append(code)
    if grant == "comp":
        rec["comp"] = True               # permanent, unlimited access
        save_ent(e); return "comp"
    rec["free_credits"] = rec.get("free_credits", 0) + grant
    save_ent(e); return "ok"
def use_credit(uid):
    """Spend one free valuation credit if available. Returns True if spent."""
    e = load_ent(); rec = e.setdefault(str(uid), {})
    if rec.get("free_credits", 0) > 0:
        rec["free_credits"] -= 1; save_ent(e); return True
    return False
def refund_credit(uid):
    """Hand a free valuation (back) to the user - used when a paid/credited delivery
    fails, so nobody is ever charged for a valuation they didn't receive."""
    e = load_ent(); rec = e.setdefault(str(uid), {})
    rec["free_credits"] = rec.get("free_credits", 0) + 1
    save_ent(e); return rec["free_credits"]

# ---- referrals ---------------------------------------------------------------
# /invite gives every user a stable code and a deep link. When someone they invited
# buys their FIRST pack, the referrer earns a free valuation (paid out once). This is
# on-brand growth - it costs us one marginal valuation to win a paying user, and it
# never touches the report's content the way ad/affiliate injection would.
import hashlib as _hashlib
REF_BONUS = 1   # free valuations the referrer earns per converted referral

def _gen_ref_code(uid):
    """A short, stable, address-bar-safe code derived from the user id."""
    return _hashlib.sha1(f"honestly:{uid}".encode()).hexdigest()[:6].upper()

def referral_code(uid):
    """Get-or-create this user's stable referral code."""
    e = load_ent(); rec = e.setdefault(str(uid), {})
    if not rec.get("ref_code"):
        rec["ref_code"] = _gen_ref_code(uid); save_ent(e)
    return rec["ref_code"]

def _uid_for_ref(code):
    code = (code or "").upper()
    for k, v in load_ent().items():
        if v.get("ref_code") == code:
            return int(k)
    return None

def attach_referral(new_uid, code):
    """Record who referred a new user - once, before they've converted. No self-referral,
    no overwrite, and never for a user who has already paid out a referral."""
    ref_uid = _uid_for_ref(code)
    if not ref_uid or ref_uid == int(new_uid):
        return False
    e = load_ent(); rec = e.setdefault(str(new_uid), {})
    if rec.get("referred_by") or rec.get("ref_converted"):
        return False
    rec["referred_by"] = ref_uid; save_ent(e)
    return True

def convert_referral(uid):
    """Call when `uid` completes their first paid pack. If they were referred and it
    hasn't paid out, credit the referrer with a free valuation. Pays out exactly once.
    Returns the referrer's uid (so we can notify them) or None."""
    e = load_ent(); rec = e.setdefault(str(uid), {})
    ref_uid = rec.get("referred_by")
    if not ref_uid or rec.get("ref_converted"):
        return None
    rec["ref_converted"] = True
    ref_rec = e.setdefault(str(ref_uid), {})
    ref_rec["free_credits"] = ref_rec.get("free_credits", 0) + REF_BONUS
    ref_rec["ref_earned"] = ref_rec.get("ref_earned", 0) + 1
    save_ent(e)
    return ref_uid

def ref_earned(uid):
    return load_ent().get(str(uid), {}).get("ref_earned", 0)

def _reward_referrer(uid):
    """On a referee's first paid pack, credit and notify whoever invited them.
    Best-effort: a failed DM to the referrer must never break the buyer's delivery."""
    ref_uid = convert_referral(uid)
    if not ref_uid:
        return
    try:
        say(ref_uid, "🎁 <b>Someone you invited just bought their first valuation.</b> "
                     "You've earned a <b>free full valuation</b> - send an address to use it.")
    except Exception as e:
        log("referrer notify failed:", str(e)[:120])

# ---------------------------------------------------------------- invoices
# Digital goods inside Telegram MUST be sold in Telegram Stars (currency "XTR") -
# per Telegram policy (Apple 3.1.1/3.1.3, Google Payments). For Stars invoices the
# provider_token MUST be an empty string ("the invoice is for digital goods and
# services"); omitting it entirely is what makes a Stars invoice fail to open.
def _invoice(chat_id, **params):
    """Send a Stars invoice and NEVER fail silently. Telegram returns {ok:false,...} when an
    invoice cannot open (Stars not enabled, bad amount, etc.) - if we ignored it, the buyer
    would tap and see absolutely nothing. We check it, surface a human fallback, and log the
    exact Telegram error so a payment outage is diagnosable, not invisible. Returns the resp."""
    # Telegram hard limits: invoice title <=32 chars, description <=255. A title over 32 is
    # rejected outright (the buyer sees nothing), so cap it - the price lives in the price label
    # and the Stars amount anyway. This alone breaks any long-named micro/guide invoice.
    if params.get("title") and len(params["title"]) > 32:
        params["title"] = params["title"][:32]
    if params.get("description") and len(params["description"]) > 255:
        params["description"] = params["description"][:255]
    resp = tg("sendInvoice", chat_id=chat_id, **params)
    if not (isinstance(resp, dict) and resp.get("ok")):
        log("sendInvoice FAILED:", str(resp)[:240], "| params:", str({k: params.get(k) for k in ("title", "currency", "payload")})[:160])
        say(chat_id, "Hmm - I couldn't open the payment just then. Tap the button once more, "
                     "or reply here and I'll sort it for you straight away.")
    return resp

def invoice_sub(chat_id):
    s = STARS_SUB          # flat £14.99/mo - the sub is intro-independent (see STARS_SUB)
    return _invoice(chat_id, title="Honestly Pro - monthly",
                    description=f"{SUB_PACKS_PER_MONTH} full valuation packs a month "
                                "(every report, map, plan and script). Cancel anytime.",
                    payload="sub", provider_token="", currency="XTR",
                    prices=[{"label": f"Pro ({_gbp(s)}/mo)", "amount": s}],
                    subscription_period=SUB_PERIOD)

def invoice_pack(chat_id, audience, pack_id):
    """One-off Stars invoice for a pack. Payload carries audience + pack so the
    successful-payment handler knows exactly which components to deliver."""
    p = PACK.get(pack_id)
    if not p:
        return say(chat_id, "That option isn't available - send the address again.")
    s, _, gbp = pack_price(p)
    what = ", ".join(_SHORT[c] for c in p["components"])
    return _invoice(chat_id, title=f"Honestly {p['name']} ({gbp})",
                    description=what[:255], payload=f"buy:{audience}:{pack_id}",
                    provider_token="", currency="XTR",
                    prices=[{"label": f"{p['name']} ({gbp})", "amount": s}])

def invoice_micro(chat_id, audience, mid):
    """One-off Stars invoice for a single micro-upsell. Payload buym:<aud>:<id> tells the
    successful-payment handler exactly which artifact to build and deliver."""
    m = MICRO_BY.get(mid)
    if not m:
        return say(chat_id, "That add-on isn't available - send the address again.")
    s, _, gbp = micro_price(m)
    return _invoice(chat_id, title=f"Honestly: {m['name']} ({gbp})",
                    description=m["blurb"][:255], payload=f"buym:{audience}:{mid}",
                    provider_token="", currency="XTR",
                    prices=[{"label": f"{m['name']} ({gbp})", "amount": s}])

# ---------------------------------------------------------------- mobile cards
import re as _re
def _link(u, t): return f'<a href="{html.escape(u)}">{html.escape(t)}</a>'
def _m(v): return engine.money(v)
def _nice(addr):  # title-case the street but keep the postcode uppercase
    t = addr.title() if addr.isupper() else addr
    pc = engine.postcode_of(addr)
    if pc: t = _re.sub(_re.escape(pc.title()), pc, t)
    return t

HEAD = {"vendor": ("🏠", "What the data says your home is worth"),
        "buyer":  ("🔍", "What the data says this home is worth"),
        "agent":  ("📋", "Instant appraisal")}

def card(r, audience, asking=None, quoted=None):
    """A clean, scannable HEADLINE for the chat - the number, the range, the guide and the
    trust signal, then a pointer to the full report below. The detail (the formula, every
    comparable with its link, the market backdrop) lives in the attached PDF and interactive
    report, NOT dumped into the chat. One tidy message, never a wall. Same engine.summary()
    as every surface, so the figures never drift."""
    d = engine.summary(r, audience, asking=asking, quoted=quoted, n=3, tier="lite")
    icon, _title = HEAD[audience]
    ep = d.get("evidence_purity") or {}
    conf = d.get("confidence") or {}
    n = d.get("n_comps") or 0
    L = [f"{icon} <b>{html.escape(d['address'])}</b>", ""]
    if audience == "agent":
        bits = [b for b in [(f"{d['sqm']}sqm" if d.get('sqm') else None),
                            (f"{d['beds']} bed" if d.get('beds') else None),
                            (f"EPC {d['epc']}" if d.get('epc') else None)] if b]
        if bits:
            L.append("<i>" + " · ".join(bits) + "</i>")
    L.append(f"<b>{html.escape(d['range_str'])}</b>")
    gl = "" if audience == "agent" else (d["guide_label"] + " ")
    L.append(f"Central ~<b>{_m(d['central'])}</b>   ·   {gl}<b>{html.escape(d['guide_value_str'])}</b>")
    if ep.get("pct") is not None:
        L.append(f"✅ <b>{ep['pct']}% evidence-based</b>   ·   {n} sold comparable{'s' if n != 1 else ''}")
    elif conf:
        L.append(f"✅ Confidence <b>{html.escape(conf.get('grade', '-'))}</b>   ·   {n} sold comparable{'s' if n != 1 else ''}")
    pe = d.get("plain_english") or {}
    if pe.get("headline"):
        L += ["", f"🗣️ {html.escape(pe['headline'])}"]
    if d.get("verdict"):
        mark = "⚠️" if d["verdict"]["tone"] == "warn" else "✓"
        L.append(f"{mark} {html.escape(d['verdict']['text'])}")
    L += ["", "📄 <b>Your full report is just below</b> - every comparable with its HM Land "
          "Registry link, the full breakdown, and what it means for your decision."]
    return "\n".join(L)


def _card_legacy(r, audience, asking=None, quoted=None):
    """Retained for reference: the previous all-in-one card (kept out of the flow)."""
    d = engine.summary(r, audience, asking=asking, quoted=quoted, n=3, tier="lite")
    icon, title = HEAD[audience]
    L = [f"{icon} <b>{title}</b>\n{html.escape(d['address'])}\n"]
    if audience == "agent":
        bits = []
        if d.get("sqm"):  bits.append(f"{d['sqm']}sqm")
        if d.get("beds"): bits.append(f"{d['beds']} bed")
        if d.get("epc"):  bits.append(f"EPC {d['epc']}")
        if bits: L.append(" · ".join(bits) + "\n")
    L.append(f"<b>{html.escape(d['range_str'])}</b>  (likely ~{_m(d['central'])})")
    gl = "" if audience == "agent" else d["guide_label"] + ": "
    L.append(f"{gl}<b>{html.escape(d['guide_value_str'])}</b>"
             + (f" · £{d['psm']:,}/sqm" if audience == "agent" and d["psm"] else "") + "\n")
    conf = d.get("confidence") or {}
    if conf:
        L.append(f"Confidence: <b>{html.escape(conf.get('grade', '-'))}</b> ({conf.get('score', '-')}/100)\n")
    pe = d.get("plain_english") or {}
    if pe:
        L.append(f"🗣️ <b>Plain English</b> · {html.escape(pe.get('headline', ''))}\n")
        for b in (pe.get('bullets') or [])[:2]:
            L.append(f"• {html.escape(b)}\n")
    up = d.get("upgrade") or {}
    if up:
        L.append(f"✨ <b>{html.escape(up.get('headline', ''))}</b>\n")
        for b in (up.get('bullets') or [])[:3]:
            L.append(f"• {html.escape(b)}\n")
    # the glass box: the exact chain from sold evidence to the assessed figure, in one line
    chain = []
    if d.get("sold_median"):
        chain.append(f"sold median {_m(d['sold_median'])}")
    if d.get("sold_anchor") and d.get("sold_anchor") != d.get("sold_median"):
        chain.append(f"condition-adjusted {_m(d['sold_anchor'])}")
    mkw = d.get("market")
    if mkw and abs(mkw.get("pct") or 0) >= 0.1:
        sgn = "+" if mkw["pct"] > 0 else ""
        chain.append(f"live market {sgn}{mkw['pct']}%")
    vf = d.get("valuation_formula") or {}
    if vf.get("plain_formula"):
        L.append("🔎 <b>Formula</b> · " + html.escape(vf["plain_formula"]) + "\n")
    elif chain:
        L.append("🔎 <b>Formula</b> · " + " → ".join(chain)
                 + f" = <b>{_m(d['central'])}</b> central\n")
    mk = d.get("market")
    if mk and abs(mk.get("pct") or 0) >= 0.1:
        arrow = "📈" if mk["pct"] > 0 else "📉"
        sign = "+" if mk["pct"] > 0 else ""
        L.append(f"{arrow} <b>{html.escape(mk['label'])}</b> · sold evidence "
                 f"{'steered ' + sign}{mk['pct']}% for live conditions "
                 f"(from {_m(d['sold_anchor'])})\n")
    if d["verdict"]:
        mark = "⚠️" if d["verdict"]["tone"] == "warn" else "✓"
        L.append(f"{mark} {html.escape(d['verdict']['text'])}\n")
    ev = "\n".join(f"• {html.escape(c['address'])} · "
                   f"{(str(c.get('sqm')) + 'sqm · ') if c.get('sqm') else ''}{c['price_str']} "
                   f"({c['date']}), {_link(c['verify'], 'source')}" for c in d["evidence"])
    L.append(f"<b>Evidence: homes like it, sold</b>\n{ev}\n")
    if d["positioning"]:
        L.append(f"📉 {html.escape(d['positioning']['note'])}")
    mc = d.get("macro")
    if mc:
        rate = f"Bank Rate {mc['base_rate']:.2f}%"
        if mc.get("next_mpc_str"):
            rate += f" (next call {mc['next_mpc_str']})"
        std = mc.get("sdlt_standard")
        sdlt = ""
        if std is not None:
            sdlt = f". Stamp duty here ~{_m(std)}"
            if mc.get("sdlt_ftb") is not None and mc["sdlt_ftb"] < std:
                sdlt += f" ({_m(mc['sdlt_ftb'])} first-time)"
        L.append(f"\n🏦 <b>Market backdrop</b> · {html.escape(rate)}{html.escape(sdlt)}.")
        mom = mc.get("momentum")
        if mom:
            arrow = {"supportive": "📈", "soft": "📉"}.get(mom.get("lean"), "➖")
            L.append(f"{arrow} <b>Momentum</b> · {html.escape(mom['headline'])} "
                     f"<i>Beside the figure, not in it.</i>")
    L.append("\n<i>Anchored in HM Land Registry sold evidence. Asking prices sit beside the figure, never inside it.</i>")
    return "\n".join(L)


def decision_brief(r, audience, answers=None):
    """Decision models around the valuation. They do not move the figure."""
    answers = answers or {}
    d = engine.summary(r, audience, asking=answers.get("asking"), quoted=answers.get("quoted"), n=4, tier="lite")
    L = ["🧭 <b>Decision read</b> <i>(beside the valuation, not inside it)</i>"]
    v = (r or {}).get("valuation") or {}
    low = d.get("low") if d.get("low") is not None else v.get("low")
    high = d.get("high") if d.get("high") is not None else v.get("high")
    central = d.get("central") if d.get("central") is not None else v.get("central")
    if audience == "buyer":
        asking = answers.get("asking")
        if asking and low and high and central:
            down = decision_models.downvaluation_exposure(asking, low, high, central, answers.get("deposit"))
            if down:
                L.append(f"• Down-valuation exposure: <b>{html.escape(down['grade'])}</b>. {html.escape(down['text'])} {html.escape(down['cash_text'])}")
        aff = decision_models.affordability(asking or d["central"], deposit=answers.get("deposit"), income=answers.get("income"))
        if aff:
            bits = [f"finance pressure <b>{html.escape(aff['pressure'])}</b>"]
            if aff.get("ltv_pct") is not None: bits.append(f"{aff['ltv_pct']:.0f}% LTV")
            if aff.get("income_multiple") is not None: bits.append(f"{aff['income_multiple']:.1f}x income")
            if aff.get("monthly_payment") is not None: bits.append(f"~{decision_models.money(aff['monthly_payment'])}/mo at {aff['rate_pct']}% over {aff['term_years']}y")
            L.append("• Mortgage affordability: " + ", ".join(bits) + ".")
            for reason in aff.get("reasons") or []:
                L.append(f"  - {html.escape(reason)}")
        elif asking:
            L.append("• Add deposit and income next time and I will estimate LTV, income pressure and down-valuation cash gap.")
    elif audience == "vendor" and answers.get("quoted"):
        q = answers["quoted"]
        if q > d["high"]:
            L.append(f"• Agent quote check: <b>{decision_models.money(q - d['high'])}</b> above the top of the evidence range. Ask the agent which completed sales defend that gap.")
        elif q < d["low"]:
            L.append("• Agent quote check: below the evidence range. Ask whether they are pricing for speed or missing comparable evidence.")
        else:
            L.append("• Agent quote check: inside the evidence-supported range.")
    risk = decision_models.pre_survey_risk(d, answers)
    L.append(f"• Pre-survey risk screen: <b>{html.escape(risk['grade'])}</b>.")
    for reason in risk.get("reasons") or []:
        L.append(f"  - {html.escape(reason)}")
    if risk.get("asks"):
        L.append("Ask before you commit:")
        for ask in risk["asks"][:3]:
            L.append(f"  - {html.escape(ask)}")
    L.append("<i>Not a lender decision. Not a survey. A transparent risk screen from the data and answers available.</i>")
    return "\n".join(L)

# ---------------------------------------------------------------- intake wizard
# Conversion rule: prove value before friction. After the user picks who they are,
# ask only high-leverage decision context: condition and the one price they already
# know (asking price / agent quote). Public facts like floor area, EPC, tenure and
# finance details are our job later, not a gate before the first value.
def _parse_money(s):
    """A typed figure -> int. Accepts '£525,000', '525000', '525k', '0.5m'. None if junk."""
    t = (s or "").strip().lower().replace("£", "").replace(",", "").replace(" ", "")
    if not t:
        return None
    mult = 1
    if t.endswith("k"): mult, t = 1_000, t[:-1]
    elif t.endswith("m"): mult, t = 1_000_000, t[:-1]
    try:
        v = int(round(float(t) * mult))
    except ValueError:
        return None
    return v if 1000 <= v <= 100_000_000 else (v if v == 0 else None)

# --- condition input (realistic, single-question) --------------------------------
# The market sets the ceiling. Condition discounts tired properties; it never
# pushes a refurbished home above the comp median. Over-renovation does not print money.
CONDITION_TIERS = {
    1: {"label": "Tired / Unmodernised", "finish": "needs_modernising", "adjustment": -0.05},
    2: {"label": "Standard / Lived-in",    "finish": "average",           "adjustment": 0.0},
    3: {"label": "Newly Refurbished",      "finish": "high",              "adjustment": 0.0},
}

def _condition_step():
    """Single condition question: 1 = Tired, 2 = Standard, 3 = Refurbished."""
    return {"field": "condition_tier",
            "q": "How would you rate the <b>condition</b>?",
            "opts": [(CONDITION_TIERS[1]["label"], "1"),
                     (CONDITION_TIERS[2]["label"], "2"),
                     (CONDITION_TIERS[3]["label"], "3")]}
    'luxury' = 2), not merely modern ones: two or more high-end elements -> very_high, one ->
def _condition_result(ans):
    """Map the single condition_tier answer to finish and disclosure.
    Tier 1 (Tired): -5% adjustment, finish=needs_modernising
    Tier 2 (Standard): no adjustment, finish=average
    Tier 3 (Refurbished): no adjustment, finish=high, tighter upper bound"""
    tier = int(ans.get("condition_tier") or 2)
    if tier not in CONDITION_TIERS:
        tier = 2
    info = CONDITION_TIERS[tier]
    adj = info["adjustment"]
    label = info["label"]
    if adj < 0:
        disc = f"Tired condition: applying {int(abs(adj)*100)}% discount to valuation. Unmodernised homes sell below the comp median."
    elif tier == 3:
        disc = "Refurbished condition: central value anchored at the comp median (renovation does not push above market evidence). Upper range tightened."
    else:
        disc = "Standard condition: central value is the comp median. No adjustment."
    return info["finish"], disc

def _wizard_steps(aud):
    """The questions, in order. Beds/baths first, then condition, then audience-specific."""
    cond  = _condition_step()
    inv   = {"field": "investment",
             "q": "Is this an <b>investment</b> property (not your main home)?",
             "opts": [("Yes", "1"), ("No", "0")]}
    beds  = {"field": "beds", "num": True,
             "q": "How many <b>bedrooms</b> does the property have? Type a number (e.g. <code>2</code>) or tap Skip."}
    baths = {"field": "baths", "num": True,
             "q": "How many <b>bathrooms</b>? Type a number (e.g. <code>1</code>) or tap Skip."}
    if aud == "vendor":
        return [beds, baths, cond, inv,
                {"field": "quoted", "num": True,
                 "q": "Has an agent <b>quoted you a figure</b>? Type it "
                      "(e.g. <code>525000</code>) and I'll check it against the sold "
                      "evidence, or tap Skip."}]
    if aud == "buyer":
        return [beds, baths, cond,
                {"field": "asking", "num": True,
                 "q": "What's the <b>asking price</b>? Type it (e.g. <code>525000</code>) "
                      "and I'll show your headroom over the evidence, or tap Skip."}]
    return [beds, baths, cond, inv]          # agent

def wizard_start(chat, uid):
    pend = PENDING.get(uid)
    if not pend:
        return say(chat, "Send me an address first.")
    pend["answers"] = {}
    pend["step_idx"] = 0
    pend.pop("await", None)
    return _ask_step(chat, uid)

def _ask_step(chat, uid):
    pend = PENDING[uid]
    steps = _wizard_steps(pend["audience"])
    i = pend.get("step_idx", 0)
    if i >= len(steps):
        return _wizard_finish(chat, uid)
    step = steps[i]
    head = f"<i>Question {i+1} of {len(steps)}</i>\n"
    if step.get("num"):
        pend["await"] = step["field"]
        # Number buttons for tap-friendly input (beds 1-5, baths 1-3, else keyboard)
        if step["field"] == "beds":
            btns = [{"text": str(n), "callback_data": f"q:beds:{n}"} for n in range(1, 6)]
        elif step["field"] == "baths":
            btns = [{"text": str(n), "callback_data": f"q:baths:{n}"} for n in range(1, 4)]
        else:
            btns = []
        btns.append({"text": "Skip", "callback_data": f"q:{step['field']}:skip"})
        kb = [btns[i:i+3] for i in range(0, len(btns), 3)]
        return say(chat, head + step["q"], keyboard=kb)
    pend.pop("await", None)
    btns = [{"text": lab, "callback_data": f"q:{step['field']}:{val}"} for lab, val in step["opts"]]
    width = 3 if any(len(lab) > 6 for lab, _ in step["opts"]) else 5   # narrower rows for wordy labels
    kb = [btns[j:j + width] for j in range(0, len(btns), width)]
    return say(chat, head + step["q"], keyboard=kb)

def _store_answer(uid, field, raw):
    pend = PENDING[uid]
    ans = pend.setdefault("answers", {})
    if raw == "skip":
        pass
    elif field in ("beds", "baths"):
        try: ans[field] = int(raw)
        except ValueError: pass
    elif field == "condition_tier":
        try: ans[field] = int(raw)
        except ValueError: pass
    elif field == "investment":
        ans[field] = (raw == "1")
    elif field in ("asking", "quoted", "deposit", "income"):
        v = _parse_money(raw)
        if v: ans[field] = v
    pend["step_idx"] = pend.get("step_idx", 0) + 1
    pend.pop("await", None)

def _wizard_answer(chat, uid, field, raw):
    pend = PENDING.get(uid)
    if not pend:
        return say(chat, "Send me an address first.")
    _store_answer(uid, field, raw)
    return _ask_step(chat, uid)

def _wizard_finish(chat, uid):
    pend = PENDING[uid]
    pend.pop("await", None)
    aud = pend["audience"]
    ans = pend.get("answers", {})
    tier, disclosure = _condition_result(ans)       # single condition tier -> finish + disclosure
    ans["finish"] = tier
    if disclosure:
        say(chat, disclosure)                        # glass box: show why, before we value
    r = run_value(chat, pend["address"], ans)        # the work, on the user's real inputs
    if not r:
        return
    pend["r"] = r
    asking, quoted = ans.get("asking"), ans.get("quoted")
    if is_comp(uid):                                 # the owner's permanent comp: full kit, free
        return deliver_full(chat, r, aud, asking=asking, quoted=quoted)
    if subscribed(uid):                              # Pro: full kit, drawn from the monthly allowance
        return deliver_sub(chat, uid, r, aud, asking=asking, quoted=quoted)
    # Everyone else (first-time AND returning): the FREE LITE valuation - the figure, the
    # evidence, the full facts, with the Pro decision-layer locked. We never give the full
    # Decision pack away; Lite is the hook and the permanent public asset, Pro is the upgrade.
    first = not had_first(uid)
    # Clean 3-beat handoff: (1) headline card + (2) the full report, both inside deliver_lite,
    # then (3) ONE tidy 'what's next' offer. No double offer wall, no testimonial interrupt
    # stacked on the value the moment it lands.
    ok = deliver_lite(chat, r, aud, asking=asking, quoted=quoted)
    if ok and first:
        mark_first(uid)
        ask_testimonial(chat, uid)
    try:
        offer_next(chat, r, aud, uid)                # ONE combined offer (was two walls)
    except Exception as e:
        log("offer_next error:", str(e)[:140])
    return ok

# ---------------------------------------------------------------- produce the work
def run_value(chat_id, address, answers=None):
    """Produce the work: run the engine on the inputs the user actually gave us in the
    intake (beds, baths, condition, investment) - never guessed. Returns the result, or
    None on failure (having messaged the user). Cached in PENDING so the paid result is
    identical to the teaser."""
    say(chat_id, "⏳ Pulling sold comparables from HM Land Registry and crunching the evidence.")
    key = os.environ.get("PROPERTYDATA_KEY")
    a = answers or {}
    try:
        # The bot's valuation is the FREE Lite figure: sold evidence straight from the
        # official HM Land Registry Price Paid register (OGL, no paid credits). It never
        # uses the direct public spine, so the free lead-gen valuation costs nothing and can
        # never be stopped by a paid credit cap. Paid value is decision intelligence, not a
        # commercial aggregator wrapper.
        return engine.value(address, key, tier="lite",
                            beds=a.get("beds"), baths=a.get("baths") or 1,
                            finish=a.get("finish") or "average",
                            investment=bool(a.get("investment")))
    except SystemExit as e:
        say(chat_id, f"❌ {html.escape(str(e))}"); return None
    except Exception as e:
        say(chat_id, f"❌ Couldn't value that address: {html.escape(str(e)[:160])}"); return None

# The value anchor is real and defensible (NOT a fabricated per-item price, which the
# honesty contract + the ASA both forbid): the sold-evidence appraisal tools agents use to
# win and defend instructions - Hometrack, Sprift, Acaboom - sit behind pro accounts at
# hundreds of pounds a month. That true external cost is what the stack anchors against, so
# the offer is presented with conviction without inventing a single number.
def _anchor_line(audience):
    if audience == "agent":
        return ("The tools that win instructions - Hometrack, Sprift, Acaboom - cost agents "
                "<b>hundreds of pounds a month</b>. This is the same doorstep-ready, defensible "
                "sold-evidence appraisal, branded and in your hands in 60 seconds.")
    if audience == "vendor":
        return ("An agent's free valuation is a pitch to win your instruction. The pro evidence "
                "tools that actually defend a price cost <b>hundreds a month</b>. You get that "
                "evidence here - so you walk in knowing your number, not hoping.")
    return ("The data desks that price a home properly cost <b>hundreds a month</b>. You get the "
            "same sold evidence here - so you offer on proof, not on the asking price someone "
            "invented to start the bidding.")

def _pro_pitch(audience):
    """The Pro pitch sentence(s) WITHOUT the '🔑 Honestly Pro - £x/mo.' prefix - so a surface
    that already shows the name+price as a header (the Mini App block) can render just the
    argument, while the bot prepends the prefix via _pro_line. One source of conviction."""
    if audience == "agent":
        return (f"{SUB_PACKS_PER_MONTH} full Decision packs every month - {SUB_PACKS_PER_MONTH} "
                "doorstep-ready appraisals for a fraction of one pro-tool seat. If you value more "
                "than one home a fortnight, Pro pays for itself on the first instruction it helps "
                "you win.")
    return (f"Weighing up several places? Pro gives you {SUB_PACKS_PER_MONTH} full Decision packs "
            "a month - the whole shortlist, fully evidenced, for less than the cost of getting one "
            "wrong.")

def _pro_line(audience, sub_gbp):
    return f"🔑 <b>Honestly Pro - {sub_gbp}/mo.</b> {_pro_pitch(audience)}"

def _offer_lines(audience):
    """The offer, stacked and presented like we mean it: the hero Decision pack with every
    deliverable laid out as a ✓ line, anchored against what the pro tools genuinely cost,
    then the lighter Evidence pack, then Pro with its own button. Returns (lines, keyboard)."""
    labels = _component_labels(audience)
    ev, full = PACK["consumer"], PACK["full"]
    _, ev_stars, ev_gbp = pack_price(ev)
    _, full_stars, full_gbp = pack_price(full)
    sub_gbp = _gbp(STARS_SUB)   # flat £14.99/mo - intro-independent (see STARS_SUB)

    L = [f"🎯 <b>The Decision pack - {full_gbp}</b>  <i>everything you need to act:</i>"]
    L += [f"   ✓ {labels[c]}" for c in full["components"]]
    L += ["", _anchor_line(audience), ""]
    if INTRO:
        L.append(f"Yours for <b>{full_gbp}</b> ({full_stars}) - that is <b>50% off while we "
                 "launch</b>. The price goes up when the launch window closes.")
    else:
        L.append(f"Yours for <b>{full_gbp}</b> ({full_stars}).")
    L += ["", f"Just the proof for now? <b>Evidence pack - {ev_gbp}</b> ({ev_stars}): "
          + "; ".join(labels[c] for c in ev["components"]) + ".",
          "", _pro_line(audience, sub_gbp)]
    kb = [
        [{"text": f"🎯 Get the Decision pack · {full_gbp}", "callback_data": f"buy:{audience}:full"}],
        [{"text": f"Evidence pack · {ev_gbp}", "callback_data": f"buy:{audience}:consumer"}],
        [{"text": f"🔑 Go Pro · {sub_gbp}/mo ({SUB_PACKS_PER_MONTH} packs)", "callback_data": "sub"}],
    ]
    return L, kb

def offer_next(chat_id, r, audience, uid=None):
    """ONE clean 'what's next' message after the free report - never two competing walls.
    The full stacked offer (Decision pack, Evidence pack, Pro) PLUS the 1-2 most relevant
    add-ons for THIS property, in a SINGLE tidy message. Replaces firing present_packs AND
    offer_micros back to back (that was the wall). Honest: only real products, never what
    Lite already gave - suggest_micros excludes the LITE_INCLUDED facts."""
    try:
        d = engine.summary(r, audience, n=4, tier="pro")
    except Exception:
        d = {}
    lines, kb = _offer_lines(audience)
    L = ["<b>Ready to act on your report?</b>", ""] + lines
    if uid is not None and free_credits(uid) > 0:
        L.append("\nYou have a <b>free unlock</b> - take the full Decision pack, no charge.")
        kb = [[{"text": "🔓 Use my free unlock (full kit)", "callback_data": f"pay:{audience}"}]] + kb
    try:
        picks = suggest_micros(d, r, audience, _ctx_for(r, d), n=2)
    except Exception as e:
        log("offer_next suggest error:", str(e)[:140]); picks = []
    if picks:
        L += ["", "<b>Or add just the piece you need:</b>"]
        for m in picks:
            _, _s, gbp = micro_price(m)
            L.append(f"• <b>{m['name']}</b> ({gbp}) - {m['blurb']}")
            kb.append([{"text": f"{m['name']} · {gbp}", "callback_data": f"buym:{audience}:{m['id']}"}])
    wa = webapp_url()
    if wa:
        kb.append([{"text": "See everything", "web_app": {"url": wa}}])
    return say(chat_id, "\n".join(L), keyboard=kb)


def present_packs(chat_id, r, audience, uid=None):
    """No teaser image - the figure is real and the products are real. Show the honest
    summary, then the STACKED offer (hero Decision pack, lighter Evidence pack, Pro). A user
    with a free unlock (promo credit) gets a button for the full kit at no charge."""
    d = engine.summary(r, audience, n=4)
    n = len(r["compsA"])
    lines = [f"Your valuation for <b>{html.escape(d['address'])}</b> is ready - built from "
             f"<b>{n}</b> verified sold comparables and the live local market.",
             "You have the number. Here is how you turn it into a result:", ""]
    offer, kb = _offer_lines(audience)
    lines += offer
    has_free = uid is not None and free_credits(uid) > 0
    if has_free:
        lines.append("\nYou have a <b>free unlock</b> - tap below for the full Decision pack, no charge.")
        kb.insert(0, [{"text": "🔓 Use my free unlock (full kit)", "callback_data": f"pay:{audience}"}])
    else:
        lines.append("\nHave a code? <code>/code YOURCODE</code>.")
    return say(chat_id, "\n".join(lines), keyboard=kb)

def deliver_sub(chat, uid, r, audience, asking=None, quoted=None):
    """A Pro subscriber's valuation: the full kit, drawn from the monthly pack allowance.
    Comp (PROPHET) is unlimited. When the allowance is spent, offer single packs instead."""
    used, cap = sub_usage(uid)
    if cap is not None and used >= cap:
        say(chat, f"You've used all <b>{cap}</b> Pro valuations this cycle. Buy a single "
                  "pack to keep going - your allowance resets next month.")
        return present_packs(chat, r, audience, uid)
    ok = deliver_full(chat, r, audience, asking=asking, quoted=quoted)
    if ok and cap is not None:
        left = cap - bump_sub_usage(uid)
        say(chat, f"✅ Delivered on Pro - <b>{left}</b> of {cap} valuations left this cycle.")
    return ok

def _targets_text(targets, audience):
    """Nearby sold-evidence rows as a tappable in-chat list."""
    head = "📍 <b>Nearby proof rows</b>"
    L = [head]
    for i, t in enumerate(targets, 1):
        addr = html.escape(t.get("loc") or t["address"])
        if t.get("link"):
            addr = f'<a href="{html.escape(t["link"])}">{addr}</a>'
        beds = f"{t['beds']} bed · " if t.get("beds") else ""
        dom  = f" · {t['dom']}d on mkt" if t.get("dom") else ""
        L.append(f"{i}. {addr} · {beds}{html.escape(t['price_str'])}{dom}")
    return "\n".join(L)

def deliver_components(chat_id, r, audience, components, asking=None, quoted=None, tier="pro"):
    """Deliver exactly the components requested. The text card is ALWAYS sent - it IS the
    answer and the safety net. `tier` decides how much travels with the figure: 'pro' renders
    the full decision layer; 'lite' (the free valuation) builds the Pro-stripped Lite PDF +
    interactive page (locked previews where Pro would be) - leak-proof by construction, since
    the Pro payload is never computed into the Lite deliverables. The figure is identical
    across tiers; only the surrounding context differs. Returns True iff something reached the
    user, so callers can refund on total failure. Each extra is fully guarded."""
    comp = set(components)
    is_lite = str(tier).strip().lower() == "lite"
    # the single-source summary, at the delivered tier. The figure is the same either way.
    d = engine.summary(r, audience, asking=asking, quoted=quoted, n=4, tier=tier)
    res = say(chat_id, card(r, audience, asking=asking, quoted=quoted))
    delivered = bool(res.get("ok"))
    key = os.environ.get("PROPERTYDATA_KEY")
    # persist the appraisal (single source of truth + audit trail, training + legal).
    # Best-effort: store.py never raises, so a DB hiccup can't cost a paid valuation.
    appraisal_token = None
    try:
        import store
        appraisal_token = store.record_appraisal(
            d, address=r["subject"]["address"], audience=audience,
            finish=(r["subject"].get("finish") or "average"),
            investment=r["subject"].get("investment", False),
            source=f"bot:{chat_id}", tier=",".join(sorted(comp)) or None,
            chat_id=chat_id)   # owner tag -> the Pro workspace "my properties" list
    except Exception as e:
        log("store appraisal error:", str(e)[:160])
    # Lite-only delivery -> open the honest re-engagement / micro-sell sequence over the
    # persistent Telegram channel. Skipped if they bought the full report (they converted) or
    # if persistence failed. Nudges are DRY-RUN until HONESTLY_TG_LIVE=1, so this never messages
    # anyone by accident; run_due (a cron/loop) actually sends, honouring opt-out + quiet hours.
    try:
        if appraisal_token and is_lite:
            import tg_funnel
            tg_funnel.start(chat_id, appraisal_token, audience)
    except Exception as e:
        log("tg_funnel start error:", str(e)[:160])
    # schools nearby - honest area context for every audience, best-effort. Links each
    # school to its official Ofsted report; we never assert a rating, never value on it.
    try:
        brief = products.schools_brief(products.nearby_schools(r, key, n=6))
        if brief:
            say(chat_id, brief)
    except Exception as e:
        log("schools error:", str(e)[:160])
    # spoken walkthrough of the glass-box working (Voxtral TTS), best-effort. Only
    # fires if a MISTRAL_API_KEY is present; otherwise it silently no-ops. The script
    # reproduces the engine's figures and arithmetic verbatim - never invents a number.
    try:
        import audio
        d["comparable_count"] = len(r.get("compsA") or [])
        clip = audio.save_walkthrough(d, f"_walk_{chat_id}.mp3")
        if clip:
            tg_audio(chat_id, clip,
                     caption="🔊 <b>Listen to the working</b> - the same figures, narrated.")
            try: os.remove(clip)
            except Exception: pass
    except Exception as e:
        log("audio walkthrough error:", str(e)[:160])
    # the branded PDF (and the interactive HTML, if that rung was bought)
    if "report" in comp:
        try:
            import report
            want_html = "html" in comp
            # Mint the hosted /r/<token> link BEFORE building, so the PDF can print it as a
            # real clickable link (works in any reader, even forwarded off Telegram). The
            # token references the appraisal, not the file, so it's valid before the HTML
            # body is stored below - resolve_token finds the latest HTML at serve time.
            link = None
            if want_html and appraisal_token:
                try:
                    import store
                    tok = store.mint_token(appraisal_token)
                    base = public_base()
                    if tok and base:
                        link = f"{base}/r/{tok}"
                except Exception as e:
                    log("mint link error:", str(e)[:160])
            # area context: the free-spine + Google + Gemini sources around the property
            # (location/connectivity, amenities, safety, environment, planning, narrative).
            # Best-effort and never raises into the request path; with it, the PDF and the
            # HTML render the Area/Safety/Environment/Planning sections identically, so the
            # two surfaces stay 1:1. None of it is an input to the figure - context only.
            context = None
            try:
                import area_context
                subject = dict(r["subject"])
                subject.setdefault("postcode", engine.postcode_of(subject.get("address", "")))
                context = area_context.gather(subject, summary=d)
            except Exception as e:
                log("area context error:", str(e)[:160])
            pdf_path, html_path = report.build(r, audience, slug=str(chat_id),
                                               interactive=want_html, key=key, link=link,
                                               context=context, tier=tier)
            pdf_name = os.path.basename(pdf_path).lower()
            pdf_label = ("Your free Lite report" if is_lite
                         else "Evidence pack" if "evidence" in pdf_name else "Full report")
            cap_tail = ("- every comparable links to its HM Land Registry record. The Pro "
                        "decision layer is unlocked below." if is_lite
                        else "- every comparable links to its HM Land Registry record.")
            res = tg_document(chat_id, pdf_path, caption=f"📄 <b>{pdf_label}</b> {cap_tail}")
            delivered = delivered or bool(res.get("ok"))
            # record the PDF artifact for the audit trail (path only - it is not hosted)
            if appraisal_token:
                try:
                    import store
                    store.record_deliverable(appraisal_token, "pdf", path=pdf_path)
                except Exception as e:
                    log("store pdf error:", str(e)[:160])
            if html_path and want_html:
                # send BOTH the self-contained file (durable, opens offline) AND the hosted
                # tap-to-open link on our own domain (best mobile UX). The link serves the
                # byte-identical stored HTML, so the two can never drift. Store the body now
                # so the link minted above resolves the moment the user opens it.
                try:
                    import store
                    with open(html_path, encoding="utf-8") as _f:
                        html_body = _f.read()
                    if appraisal_token and html_body:
                        store.record_deliverable(appraisal_token, "html",
                                                 path=html_path, body=html_body)
                except Exception as e:
                    log("store html error:", str(e)[:160])
                try:
                    cap = "🔗 Interactive version - tap any comparable to open its sold record."
                    if link:
                        cap += f"\n\n🌐 Or open it on any device: {link}"
                    tg_document(chat_id, html_path, mime="text/html", caption=cap)
                except Exception as e:
                    log("interactive html error:", str(e)[:160])
        except Exception as e:
            log("pdf report error:", str(e)[:200])
        # frontage photo travels with the report - part of the valuation picture
        try:
            sv = maps_tools.street_view(r["subject"]["address"], "_frontage.jpg")
            if sv.get("ok") and sv.get("available"):
                tg_photo(chat_id, "_frontage.jpg", caption=f"Street View frontage - captured {sv.get('date','?')}")
        except Exception as e:
            log("frontage error:", str(e)[:160])
    # the action plan, written for this reader. Pro carries the full costed, scenario-anchored
    # plan (action_plan.py) on the summary; render it when present, else the short fallback.
    if "plan" in comp:
        try:
            pl = None
            ap = d.get("action_plan")
            if ap and ap.get("ok"):
                import action_plan as _ap
                pl = _ap.lines(ap)
            if not pl:
                pl = products.plan_of_action(d, r, audience)
            if pl:
                say(chat_id, "\n".join(pl))
        except Exception as e:
            log("plan error:", str(e)[:160])
    # 20 nearby targets + a REAL interactive Google Maps route (opens live in Maps)
    if "map" in comp:
        try:
            targets = products.target_listings(r, key, audience, n=20)
            if targets:
                say(chat_id, _targets_text(targets, audience))
                subj_addr = r["subject"]["address"]
                if audience == "agent":
                    # optimise the door-knock order over the subject + nearest 9 doors
                    stops = [subj_addr] + [t["address"] for t in targets[:9]]
                    rt = maps_tools.route(stops, optimize=True, mode="WALK")
                    ordered = rt["ordered_stops"] if rt.get("ok") else stops
                    url = maps_tools.directions_url(ordered, mode="walking")
                    if rt.get("ok"):
                        mins = int(str(rt["duration"]).rstrip("s") or 0) // 60
                        cap = (f"🗺️ <b>Door-knock route</b> - {len(ordered)} doors, "
                               f"{rt['km']}km on foot, ~{mins}min, walked in the optimal order.")
                    else:
                        cap = f"🗺️ <b>Door-knock route</b> - {len(ordered)} doors, opened in order."
                    btn = "🚪 Open walking route in Google Maps"
                else:
                    stops = [subj_addr] + [t["address"] for t in targets[:9]]
                    url = maps_tools.directions_url(stops, mode="driving")
                    cap = f"🗺️ <b>Nearby proof rows on the map</b> - {len(targets)} completed sales, pinned."
                    btn = "🗺️ Open the evidence map in Google Maps"
                if url:
                    say(chat_id, cap,
                        keyboard=[[{"text": btn, "url": url}]])
        except Exception as e:
            log("targets error:", str(e)[:160])
    # the ready-to-send email / script
    if "email" in comp:
        try:
            em = products.email_template(d, r, audience)
            say(chat_id, f"✉️ <b>{html.escape(em['subject'])}</b>\n\n<code>{html.escape(em['body'])}</code>")
        except Exception as e:
            log("email error:", str(e)[:160])
    return delivered

def deliver_full(chat_id, r, audience, asking=None, quoted=None):
    """The whole kit, every component, at Pro tier. Used for subscribers and the owner comp.
    Returns True iff something reached the user."""
    return deliver_components(chat_id, r, audience, ALL_COMPONENTS, asking=asking,
                              quoted=quoted, tier="pro")

def deliver_lite(chat_id, r, audience, asking=None, quoted=None):
    """The FREE Lite valuation - the figure, the evidence, the full facts, with the Pro
    decision-layer locked. Delivers the branded Lite PDF + the interactive page (both Pro-
    stripped, leak-proof) and opens the re-engagement funnel; never the full Decision pack.
    The interactive page is persisted (and a /r/<token> link minted), so each free valuation
    is also a permanent, shareable asset. Returns True iff something reached the user."""
    return deliver_components(chat_id, r, audience, ["report", "html"], asking=asking,
                              quoted=quoted, tier="lite")

# ------------------------------------------------ micro-upsell delivery + suggestion
def _ctx_for(r, d):
    """Gather the free area-context spine once (location/area/safety/environment/planning/
    solar/material) for the micro-upsells that render from it. Best-effort, never raises."""
    try:
        import area_context
        subj = dict(r["subject"])
        subj.setdefault("postcode", engine.postcode_of(subj.get("address", "")))
        return area_context.gather(subj, summary=d)
    except Exception as e:
        log("micro ctx error:", str(e)[:140]); return None

def deliver_micro(chat_id, r, audience, mid, *, d=None, context=None):
    """Deliver ONE micro-upsell: a real artifact built from this property's own data by its
    producer module. Returns True iff something reached the user. Each branch is guarded so a
    producer hiccup degrades to an honest message - we never charge and silently send nothing
    (callers refund on False)."""
    m = MICRO_BY.get(mid)
    if not m:
        say(chat_id, "That option isn't available - send the address again."); return False
    if d is None:
        d = engine.summary(r, audience, n=4, tier="pro")
    key = os.environ.get("PROPERTYDATA_KEY")
    s, v, pos = r["subject"], r["valuation"], r.get("positioning")
    # Automated guide delivery: any '<topic>_guide' micro is produced generically from the
    # guides registry - a distinct topic guide built from this property's own data, never the
    # valuation. A new guide added to guides.py needs no branch here.
    if _guides is not None and mid in getattr(_guides, "GUIDE_TOPIC_BY_MICRO", {}):
        try:
            ctx = context or _ctx_for(r, d)
            sec = (ctx or {}).get("sections") if isinstance(ctx, dict) else None
            body = _guides.build_by_micro(mid, sec or {}, d, s)
            return _say_block(chat_id, f"📘 <b>{MICRO_BY[mid]['name']}</b>", body)
        except Exception as e:
            log(f"guide {mid} error:", str(e)[:160])
            say(chat_id, f"Sorry - couldn't build the {MICRO_BY[mid]['name']} just now. Reply and I'll sort it.")
            return False
    try:
        if mid == "interactive":
            import appraise as _ap
            htmlp = _ap.interactive_chart(r["compsA"], v, s, str(chat_id), HERE, BOT_URL_DEFAULT,
                                          d=d, pos=pos, context=(context or _ctx_for(r, d)))
            if htmlp:
                tg_document(chat_id, htmlp, mime="text/html",
                            caption="🔗 Interactive report - tap any comparable to open its sold record.")
                return True
        elif mid == "scenario":
            import scenario
            txt = scenario.lines(scenario.matrix(d, pos), audience)
            return _say_block(chat_id, "📊 <b>Scenario pricing matrix</b>", txt)
        elif mid == "plan":
            import action_plan
            txt = action_plan.lines(action_plan.build(d, r, audience)) or products.plan_of_action(d, r, audience)
            return _say_block(chat_id, "🧭 <b>Action plan</b>", txt)
        elif mid == "ledger":
            import price_ledger
            txt = price_ledger.lines(price_ledger.build(d, context=(context or _ctx_for(r, d))), audience)
            return _say_block(chat_id, "🔎 <b>Price-influence ledger</b>", txt)
        elif mid == "verify":
            import verification
            txt = verification.lines(d)
            return _say_block(chat_id, "✅ <b>Data-spine verification</b>", txt)
        elif mid == "map":
            targets = products.target_listings(r, key, audience, n=20)
            if targets:
                say(chat_id, _targets_text(targets, audience))
                return True
        elif mid == "email":
            em = products.email_template(d, r, audience)
            if em:
                say(chat_id, f"✉️ <b>{html.escape(em['subject'])}</b>\n\n<code>{html.escape(em['body'])}</code>")
                return True
        elif mid == "schools":
            txt = products.schools_brief(products.nearby_schools(r, key, n=6))
            return _say_block(chat_id, "🏫 <b>Schools & Ofsted</b>", txt)
        elif mid in ("area", "safety", "environment", "planning", "solar", "material"):
            return _deliver_ctx_micro(chat_id, mid, context or _ctx_for(r, d), d, s)
        elif mid == "netproceeds":
            return _deliver_netproceeds(chat_id, d, s, audience)
        elif mid == "market":
            import market_analysis
            rec = market_analysis.gather(store_district(s), postcode=s.get("postcode"),
                                         price=v.get("central"), positioning=pos)
            txt = market_analysis.brief(rec) if rec else None
            return _say_block(chat_id, "📈 <b>Market analysis & sentiment</b>", txt)
    except Exception as e:
        log(f"micro {mid} error:", str(e)[:160])
    say(chat_id, f"Sorry - couldn't build the {m['name']} just now. Reply and I'll sort it.")
    return False

def _say_block(chat_id, header, body):
    """Send a header + a producer's lines (list or str). Returns True iff Telegram confirmed delivery."""
    if not body:
        return False
    txt = body if isinstance(body, str) else "\n".join(str(x) for x in body)
    if not txt.strip():
        return False
    result = say_long(chat_id, header + "\n\n" + txt)
    return bool(result and result.get("ok"))

def store_district(s):
    try:
        import store
        return store.district_of(s.get("postcode") or s.get("address") or "")
    except Exception:
        return (s.get("postcode") or "").split(" ")[0]

BOT_URL_DEFAULT = "https://t.me/usehonestly_bot"

def suggest_micros(d, r, audience, context=None, n=3):
    """Pick the most relevant micro-upsells to surface NOW, ordered by live signal then audience
    fit. Intelligent timing: a flood reading promotes the environment report, stuck stock promotes
    the scenario matrix, an investor gets rent, a low EPC gets solar, etc. Honest - it only
    promotes a real artifact, never invents a reason. Returns a list of MICRO dicts."""
    s, v, pos = r["subject"], r["valuation"], r.get("positioning")
    sec = ((context or {}).get("sections") or {}) if isinstance(context, dict) else {}
    # If the bot's intake confirmed this is an investment property, we infer an INVESTOR and
    # sell to them as one: the micro-upsell fit and the audience-core priorities rotate to the
    # investor set, regardless of the buyer/vendor base role they entered with.
    aud_eff = "investor" if s.get("investment") else audience
    sig = set()
    if pos and (pos.get("stuck") or (pos.get("mean_dom") or 0) >= 60): sig.add("stuck")
    if s.get("investment"): sig.add("invest")
    fl = (sec.get("environment") or {}).get("flood") or {}
    if fl.get("active") or "monitored" in str(fl.get("severity", "")).lower(): sig.add("flood")
    if (sec.get("safety") or {}).get("total"): sig.add("crime")
    if (sec.get("planning") or {}).get("total"): sig.add("planning")
    epc = s.get("epc")
    if epc and str(epc)[:1] in ("D", "E", "F", "G"): sig.add("epc")
    if aud_eff in ("vendor", "buyer", "investor"): sig.add("money")
    scored = []
    for m in MICRO:
        if m["id"] in LITE_INCLUDED:        # already given free in Lite - never re-sell it
            continue
        if not _micro_fits(m, aud_eff):
            continue
        score = 2 if m.get("sig") in sig else 0
        # audience-core picks always rank decently even without a live signal
        if m["id"] in {"vendor": ("scenario", "plan", "netproceeds"),
                       "buyer": ("plan", "netproceeds", "scenario"),
                       "agent": ("map", "plan", "email"),
                       "investor": ("netproceeds", "scenario", "market")}.get(aud_eff, ()):
            score += 1
        scored.append((score, m))
    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored[:n]]

def _solar_lines(so):
    L = []
    for k, label in (("annual_kwh", "Estimated annual generation"), ("max_panels", "Roof capacity"),
                     ("annual_savings_gbp", "Estimated annual saving"), ("payback_years", "Indicative payback")):
        if isinstance(so, dict) and so.get(k) is not None:
            L.append(f"{label}: {so[k]}")
    if not L and isinstance(so, dict):
        L = [f"{k}: {v}" for k, v in list(so.items())[:6] if not isinstance(v, (dict, list))]
    L.append("Source: Google Solar API. Energy context beside the figure, not a price input.")
    return L

def _deliver_ctx_micro(chat_id, mid, context, d, s):
    sec = ((context or {}).get("sections") or {}) if isinstance(context, dict) else {}
    if mid == "area":
        a = sec.get("area") or {}; counts = a.get("counts") or {}
        if not any(counts.values()): return False
        within = "; ".join(f"{k}: {v}" for k, v in counts.items() if v)
        L = [f"Within {a.get('radius_m', 800)} m of the property - {within}."]
        L += [f"- {t.get('name', 'Station')} ~{t.get('dist_m')} m" for t in (a.get("transport") or [])[:5]]
        return _say_block(chat_id, "📍 <b>Area & amenities</b>", L + ["Source: OpenStreetMap (ODbL)."])
    if mid == "safety":
        sf = sec.get("safety") or {}
        if not sf.get("total"): return False
        cats = "; ".join(f"{c}: {n}" for c, n in (sf.get("by_category") or [])[:6])
        return _say_block(chat_id, "🛡️ <b>Safety</b>",
            [f"{sf['total']} street-level crimes recorded within ~1 mile in {sf.get('month', 'the latest month')}.",
             cats, "Recorded crime is area context, never a price input. Source: Police.uk (OGL v3.0)."])
    if mid == "environment":
        env = sec.get("environment") or {}; fl = env.get("flood") or {}; air = env.get("air") or {}
        L = list(fl.get("lines") or ([fl.get("severity")] if fl.get("severity") else []))
        if air.get("aqi") is not None:
            L.append(f"Air quality index ~{air['aqi']} ({air.get('band', '')}).")
        if not L: return False
        return _say_block(chat_id, "🌊 <b>Flood & air quality</b>",
                          L + ["Source: Environment Agency flood data + open air-quality."])
    if mid == "planning":
        pl = sec.get("planning") or {}
        if not pl.get("total"): return False
        byst = "; ".join(f"{st}: {n}" for st, n in (pl.get("by_status") or [])[:6])
        return _say_block(chat_id, "🏗️ <b>Planning & development nearby</b>",
                          [f"{pl['total']} recent planning applications near the property.", byst,
                           "Source: PlanIt / local planning data."])
    if mid == "solar":
        so = sec.get("solar")
        if not so:
            try:
                import solar
                lat, lng = s.get("lat"), s.get("lng")
                so = solar.roof(lat, lng) if (lat and lng) else None
            except Exception:
                so = None
        if not so or (isinstance(so, dict) and so.get("ok") is False): return False
        return _say_block(chat_id, "☀️ <b>Solar & energy potential</b>", _solar_lines(so))
    if mid == "material":
        L = []
        if s.get("epc"): L.append(f"EPC: {s['epc']}")
        if s.get("tax"): L.append(f"Council Tax band: {s['tax']}")
        mat = sec.get("material") or {}
        if mat.get("bracket_1991"): L.append(f"Council-tax 1991 value bracket: {mat['bracket_1991']}")
        if mat.get("note"): L.append(str(mat["note"]))
        if not L: return False
        return _say_block(chat_id, "📋 <b>Material information</b>",
                          L + ["Source: EPC register (DLUHC) + VOA council tax."])
    return False

def _deliver_netproceeds(chat_id, d, s, audience):
    central = d.get("central") or (d.get("valuation") or {}).get("central")
    if not central:
        return False
    try:
        import macro as _macro
    except Exception:
        _macro = None
    if audience == "buyer":
        sdlt = _macro.sdlt(central, first_time=False) if _macro else None
        L = [f"Purchase price (assessed central): {_m(central)}"]
        if sdlt is not None:
            L.append(f"Stamp duty (SDLT): {_m(sdlt)}")
            ftb = _macro.sdlt(central, first_time=True) if _macro else None
            if ftb is not None and ftb < sdlt:
                L.append(f"  If a first-time buyer, SDLT is {_m(ftb)}")
        L += ["Legal / conveyancing (indicative): " + _m(1000) + " - " + _m(1500),
              "Survey (indicative): " + _m(400) + " - " + _m(1000)]
        if sdlt is not None:
            L.append(f"Indicative total to buy (excl. mortgage fees): {_m(central + sdlt + 1400)} - {_m(central + sdlt + 2500)}")
        L.append("SDLT is exact (England/NI marginal bands); legal/survey are indicative third-party ranges, not a Honestly figure.")
        return _say_block(chat_id, "💷 <b>Your costs to buy</b>", L)
    # seller / vendor / agent / investor: net proceeds
    fee = round(central * 0.024)
    L = [f"Achieved price (assessed central): {_m(central)}",
         f"Estimated agent fee (2% + VAT): {_m(fee)}"]
    net = central - fee
    if s.get("investment"):
        gain = max(0, central - (s.get("last_sold") or 0) - fee - 3000)
        cgt = round(gain * 0.24)
        L.append(f"Indicative CGT (24% after £3,000 allowance): {_m(cgt)}")
        net -= cgt
    L.append(f"Net in pocket: {_m(net)}")
    L.append("Indicative only; agent fees vary and this is not tax advice.")
    return _say_block(chat_id, "💷 <b>Net proceeds</b>", L)


def _deliver_from_pending(chat, uid, audience, components):
    """Resolve the cached (or re-run) result for this user and deliver the given
    components. Returns True iff delivered. Shared by the paid-tier and free-credit
    paths, so neither can charge for a valuation that never arrived."""
    pend = PENDING.get(uid)
    ans = (pend.get("answers", {}) if pend else {})
    asking, quoted = ans.get("asking"), ans.get("quoted")
    if pend and pend.get("r"):
        r = pend["r"]
    elif pend:
        r = run_value(chat, pend["address"], ans)
        if not r:
            return False
        pend["r"] = r
    else:
        say(chat, "Send the address again and I'll run it - your unlock is still valid.")
        return False
    return deliver_components(chat, r, audience, components, asking=asking, quoted=quoted)


def _deliver_micro_from_pending(chat, uid, audience, mid):
    """Resolve the cached (or re-run) result and deliver one purchased micro-upsell.
    Returns True iff the artifact actually reached the user (caller refunds on False)."""
    pend = PENDING.get(uid) or {}
    ans = pend.get("answers", {})
    r = pend.get("r")
    if not r and pend.get("address"):
        r = run_value(chat, pend["address"], ans)
        if r:
            pend["r"] = r
    if not r:
        say(chat, "Send the address again and I'll deliver your add-on automatically.")
        return False
    d = engine.summary(r, audience, n=4, tier="pro")
    return deliver_micro(chat, r, audience, mid, d=d)


def offer_micros(chat_id, r, audience):
    """Right after the free Lite report, surface the most relevant micro-upsells for THIS
    property as tappable buy buttons (intelligent timing via suggest_micros). The full
    catalogue lives in the Mini App; here we show the best 3 so it never reads as a wall."""
    try:
        d = engine.summary(r, audience, n=4, tier="pro")
    except Exception:
        return
    ctx = _ctx_for(r, d)
    picks = suggest_micros(d, r, audience, ctx, n=3)
    if not picks:
        return
    lines = ["", "🧩 <b>Add to this report</b> - the pieces that matter most for this property:"]
    kb = []
    for m in picks:
        _, _star, gbp = micro_price(m)
        lines.append(f"• <b>{m['name']}</b> ({gbp}) - {m['blurb']}")
        kb.append([{"text": f"{m['name']} · {gbp}", "callback_data": f"buym:{audience}:{m['id']}"}])
    wa = webapp_url()
    if wa:
        kb.append([{"text": "See all add-ons", "web_app": {"url": wa}}])
    say(chat_id, "\n".join(lines), keyboard=kb)

def finish_pack(chat, uid, audience, pack_id):
    """Deliver exactly the pack the user bought. Returns True iff delivered - the caller
    refunds a free unlock on False, so nobody ever pays for nothing."""
    p = PACK.get(pack_id)
    if not p:
        say(chat, "That option isn't available - send the address again."); return False
    return _deliver_from_pending(chat, uid, audience, p["components"])

def decode_start_payload(arg):
    """Decode the landing-site widget's deep link. The site packs a single Telegram start
    param as base64url of 'v1|audience|address' (capped at Telegram's 64 chars; if the address
    pushes it over, the site sends 'v1|audience|' with an empty address). Returns
    (audience, address) on a valid v1 payload, else None - any garbage falls through to the
    normal greeting, so an unrecognised link never errors."""
    if not arg:
        return None
    s = arg.strip()
    s = s.replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)                      # restore stripped base64 padding
    try:
        raw = base64.b64decode(s, validate=True).decode("utf-8")
    except Exception:
        return None
    parts = raw.split("|")
    if len(parts) < 2 or parts[0] != "v1":
        return None
    aud = parts[1].strip().lower()
    if aud not in ("vendor", "buyer", "agent"):
        aud = "vendor"
    addr = parts[2].strip() if len(parts) > 2 else ""
    return aud, addr

def begin_from_landing(chat, uid, aud, addr):
    """Pick up a landing-site hand-off. Unlike the Mini App run_<sid> path there's no signed
    initData here (the link is opened outside Telegram), so we can't trust extra intake - just
    the address and audience the visitor chose on the site. We seed PENDING with both and jump
    straight into the intake wizard, skipping 'Who are you?' - the bot already knows. Returns
    True iff we took over the flow; False (empty/short address) falls through to the greeting."""
    if len(addr) < 6:
        return False
    PENDING[uid] = {"address": addr, "audience": aud}
    say(chat, f"📍 <b>{html.escape(addr)}</b>\nValuing as a <b>{aud}</b> - a couple of quick "
              "questions and I'll run the evidence.")
    wizard_start(chat, uid)
    return True

def begin_buy(chat, uid, code):
    """Deep-link purchase trigger. A guide/Pro hyperlink in any deliverable lands here via
    /start buy_<code>. If the reader has a valuation in THIS chat (PENDING), we fire the exact
    offer ready to pay; cold (forwarded report, new chat) we name the product and prime them to
    run an address - never a sleeping bot. Returns True if handled."""
    code = (code or "").strip().lower()
    pend = PENDING.get(uid) or {}
    aud = pend.get("audience") or "buyer"
    have = bool(pend.get("r") or pend.get("address"))
    wa = webapp_url()
    appkb = [[{"text": "📊 Open Honestly Pro", "web_app": {"url": wa}}]] if wa else None
    if code in ("pro", "full", "report", ""):
        if pend.get("r"):
            present_packs(chat, pend["r"], aud, uid=uid)
            return True
        say(chat, "🔓 <b>The full decision report</b> turns your free valuation into a decision: "
                  "what actually moves your price, the scenarios, the action plan and the full "
                  "evidence room.\n\nSend me your property address and I'll build it.", keyboard=appkb)
        return True
    m = MICRO_BY.get(code)
    if m:
        if have:
            _, _star, gbp = micro_price(m)
            say(chat, f"🧩 <b>{m['name']}</b> ({gbp})\n{m['blurb']}\n\nThis answers it for "
                      f"<b>your</b> property - tap to add it.")
            invoice_micro(chat, aud, code)
            return True
        say(chat, f"🧩 <b>{m['name']}</b> - {m['blurb']}\n\nSend me your property address and "
                  f"I'll run the free valuation first, then you can add this in a tap.", keyboard=appkb)
        return True
    return False  # unknown code -> caller falls through to the normal greeting


def begin_from_intent(chat, uid, intent):
    """A widget hand-off (NOT a purchase): the Mini App already collected the address and the
    full intake, so we pick up with everything pre-filled and never re-ask in chat. We rebuild
    PENDING from the intent and run the SAME finisher the chat wizard uses, so the entitlement
    logic (free-forever Lite / Pro / buy a pack) stays identical no matter where the user started."""
    if not intent or int(intent.get("uid", -1)) != int(uid):
        return False
    addr = (intent.get("address") or "").strip()
    if len(addr) < 6:
        return False
    answers = {}
    for f in ("beds", "baths"):
        if intent.get(f) is not None:
            try: answers[f] = int(intent[f])
            except (TypeError, ValueError): pass
    if intent.get("finish"):
        answers["finish"] = intent["finish"]
    if intent.get("investment") is not None:
        answers["investment"] = bool(intent["investment"])
    for f in ("asking", "quoted"):
        if intent.get(f) is not None:
            answers[f] = intent[f]
    aud = intent.get("audience", "vendor")
    if aud not in ("vendor", "buyer", "agent"):
        aud = "vendor"
    PENDING[uid] = {"address": addr, "audience": aud, "answers": answers}
    _wizard_finish(chat, uid)        # runs the value on the supplied inputs, then delivers per entitlement
    return True

# ---- purchase -> action automations (declarative; existing-infra-first) ----------------------
# Each automation fires AFTER a catalogue product is delivered, built on infra we already own
# (Telegram follows/queues via follow_area + tg_funnel; report.py PDFs; email_send). A new
# automation is one entry, keyed by the product's producer (or its exact id). The legs that need
# an external app (Slack / SMS / Google Sheets / third-party email) are listed in EXTERNAL_TRIGGERS
# and stay a no-op + log until a Composio adapter is connected - nothing here blocks delivery.
def _trig_watchlist(uid, chat, p, r):
    """A Comparable Watchlist purchase sets up the real area follow; the area-refresh pinger
    (tg_funnel.nudge_followed_areas) does the recurring nudge from there."""
    follow_area(uid, chat, engine.postcode_of(r["subject"].get("address", "")) or "")
    return "followed"

TRIGGERS = {
    "watchlist": _trig_watchlist,            # keyed by producer
}
# Composio-deferred automations (the user opted: existing-infra-first, Composio later). Declared so
# the wiring is one line when the adapter lands; until then they no-op (logged), never faked.
EXTERNAL_TRIGGERS = {
    "survey_email":    "email the survey brief to the buyer's surveyor",
    "solicitor_email": "email the conveyancing red flags to the solicitor",
    "sheets_sync":     "sync the offer calculator to Google Sheets",
    "slack_alert":     "post the market alert to Slack",
}

def _fire_triggers(uid, chat, p, r):
    """Run any purchase->action automation for a delivered product. Declarative: keyed by the
    product's producer, then its id. Best-effort - an automation failure never affects the
    delivery the user paid for."""
    try:
        fn = TRIGGERS.get(p.get("producer")) or TRIGGERS.get(p.get("id"))
        if fn:
            fn(uid, chat, p, r)
    except Exception as e:
        log("trigger error:", str(e)[:140])

def _deliver_podcast_async(chat_id, job_id, addr, prod_name):
    """Background thread: polls Open Notebook podcast job → downloads audio → sends via Telegram.
    Runs as a daemon thread so it doesn't block the main polling loop."""
    try:
        import notebook_client as nc
        max_wait = 360   # 6 minutes
        interval = 20   # poll every 20s
        waited = 0
        while waited < max_wait:
            time.sleep(interval)
            waited += interval
            status, episode_id = nc.podcast_job_status(job_id)
            if status == "done" and episode_id:
                audio_url = nc.episode_audio_url(episode_id)
                if not audio_url:
                    audio_url = f"{nc._BASE}/api/podcasts/episodes/{episode_id}/audio"
                try:
                    req = urllib.request.Request(audio_url, headers={"Accept": "audio/*"})
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        tmp = tempfile.mktemp(suffix=".mp3")
                        with open(tmp, "wb") as f:
                            f.write(resp.read())
                    tg_audio(chat_id, tmp,
                             caption=f"🎙️ <b>{prod_name}</b>\n{html.escape(addr)}",
                             title=f"Briefing: {addr[:40]}", performer="Honestly")
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass
                    return
                except Exception as e:
                    log("podcast audio download error:", str(e)[:160])
                    break
            if status == "error":
                say(chat_id, "⚠️ Your audio briefing could not be generated. Please try again.")
                return
        else:
            say(chat_id, "⚠️ Audio briefing is taking longer than expected — we'll send it as soon as it's ready.")
    except Exception as e:
        log("_deliver_podcast_async error:", str(e)[:160])


def deliver_catalogue_product(chat, uid, pid, r, aud):
    """Deliver one catalogue.py product to the chat: build its free-data synthesis from this
    property's run and send it, then fire any purchase->action automation. The producer (dossier /
    decision / market / watchlist / bundle) is chosen declaratively in catalogue.build. Returns
    True iff something reached the user, so callers can refund credits / Stars on a total failure.
    Best-effort, never raises."""
    try:
        import catalogue
        p = catalogue.get(pid)
        if not p:
            return False
        d = engine.summary(r, aud, n=4, tier="pro")
        ctx = _ctx_for(r, d)
        # Podcast: start the async job HERE, before catalogue.build() is ever called.
        # catalogue.build() would return a rendered "generating" page which is fine for
        # the HTML product page, but the actual audio delivery is handled by this thread.
        if p.get("producer") == "podcast":
            job_id, addr = catalogue.start_podcast_job(ctx, d, r.get("subject"))
            if job_id:
                say(chat, f"🎙️ <b>{p['name']}</b> — your audio briefing is generating.\n"
                          "We'll send the audio file here within a few minutes.")
                t = threading.Thread(
                    target=_deliver_podcast_async,
                    args=(chat, job_id, addr, p["name"]),
                    daemon=True,
                )
                t.start()
            else:
                say(chat, f"🎙️ <b>{p['name']}</b>\n"
                          "Open Notebook is not available right now — please try again shortly.")
            _fire_triggers(uid, chat, p, r)
            return bool(job_id)
        body = catalogue.build(pid, ctx, d, r.get("subject"), profile=aud)
        if not body:
            return False
        ok = bool(_say_block(chat, f"📘 <b>{p['name']}</b>", body))
        if ok:
            _fire_triggers(uid, chat, p, r)      # purchase -> action (watchlist follow, etc.)
        return ok
    except Exception as e:
        log(f"deliver_catalogue_product {pid} error:", str(e)[:160])
        return False

def deliver_intent(chat, uid, intent):
    """Deliver a Mini App purchase. The intent is self-contained (address + inputs the user
    gave the web form), so it doesn't depend on the bot's in-memory PENDING - the two run as
    separate processes. Re-runs the engine on those inputs and delivers the product / pack."""
    if not intent or int(intent.get("uid", -1)) != int(uid):
        return False
    pid = intent.get("product")                      # a catalogue.py product (the new spec)
    mid = intent.get("micro")                         # a legacy guide/micro add-on
    p = None if (pid or mid) else PACK.get(intent.get("pack"))
    if not (pid or mid or p):
        return False
    aud = intent.get("audience", "buyer")
    answers = {"beds": intent.get("beds"), "finish": intent.get("finish") or "average",
               "investment": intent.get("investment")}
    r = run_value(chat, intent["address"], answers)
    if not r:
        return False
    # Carry the asking / agent-quoted price onto the subject so price-aware products (e.g. the
    # need-named "Why isn't my house selling?" diagnostic) can measure the exact gap in pounds.
    for _k in ("asking", "quoted"):
        if intent.get(_k) is not None and isinstance(r.get("subject"), dict):
            try: r["subject"][_k] = int(float(intent[_k]))
            except (TypeError, ValueError): pass
    if pid:                                          # catalogue product (dossier / pack / read / bundle)
        return deliver_catalogue_product(chat, uid, pid, r, aud)
    if mid:                                          # a-la-carte micro-upsell add-on
        d = engine.summary(r, aud, n=4, tier="pro")
        return deliver_micro(chat, r, aud, mid, d=d)
    return deliver_components(chat, r, aud, p["components"],
                              asking=intent.get("asking"), quoted=intent.get("quoted"))

# ---------------------------------------------------------------- testimonials
def _tg_download(file_id, dest):
    """Resolve a Telegram file_id and download the bytes to dest. Returns True on success."""
    info = tg("getFile", file_id=file_id)
    if not info.get("ok"):
        return False
    fp = info["result"].get("file_path")
    if not fp:
        return False
    url = f"https://api.telegram.org/file/bot{token()}/{fp}"
    try:
        with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:
            f.write(r.read())
        return True
    except Exception:
        return False

def _load_testi():
    try:
        with open(TESTI, encoding="utf-8") as f: return json.load(f)
    except Exception: return []
def _save_testi(rows):
    with open(TESTI, "w", encoding="utf-8") as f: json.dump(rows, f, indent=2)

def save_testimonial(uid, msg, kind, text="", file_name=""):
    """Append one testimonial record to testimonials.json."""
    rows = _load_testi()
    frm = msg.get("from", {})
    rows.append({
        "uid": uid,
        "name": (frm.get("first_name", "") + " " + frm.get("last_name", "")).strip(),
        "username": frm.get("username", ""),
        "kind": kind,                 # text | video | video_note | photo
        "text": text,
        "file": file_name,            # relative path under testimonials/ when media
        "ts": _utcnow().isoformat() + "Z",
    })
    _save_testi(rows)

def ask_testimonial(chat, uid):
    """Invite the user to leave a testimonial. They can reply with text, a video, or a video note."""
    AWAIT_TESTI.add(uid)
    say(chat, "🙏 If this was useful, drop a line (or a quick video) to help others "
              "trust the figures. /skip to pass.")

def capture_testimonial(chat, uid, msg, text):
    """Store whatever the user sent as their testimonial: text, video, video note or photo."""
    if text.lower() in ("/skip", "skip", "no", "no thanks"):
        AWAIT_TESTI.discard(uid)
        return say(chat, "No problem. Thanks for using Honestly.")
    os.makedirs(TDIR, exist_ok=True)
    stamp = _utcnow().strftime("%Y%m%d%H%M%S")
    kind = "text"; file_name = ""
    media = None
    if msg.get("video"):
        media = (msg["video"]["file_id"], "video", f"{uid}_{stamp}.mp4")
    elif msg.get("video_note"):
        media = (msg["video_note"]["file_id"], "video_note", f"{uid}_{stamp}_note.mp4")
    elif msg.get("photo"):
        media = (msg["photo"][-1]["file_id"], "photo", f"{uid}_{stamp}.jpg")
    elif msg.get("voice"):
        media = (msg["voice"]["file_id"], "voice", f"{uid}_{stamp}.ogg")
    if media:
        fid, kind, fname = media
        ok = _tg_download(fid, os.path.join(TDIR, fname))
        if not ok:
            return say(chat, "Couldn't save that, sorry. Try sending it again, or a line of text instead.")
        file_name = fname
        caption = (msg.get("caption") or "").strip()
        save_testimonial(uid, msg, kind, text=caption, file_name=file_name)
    elif text:
        save_testimonial(uid, msg, "text", text=text)
    else:
        return say(chat, "Send a line of text, a video, or a voice note, or /skip to pass.")
    AWAIT_TESTI.discard(uid)
    return say(chat, "🙏 Thank you. That genuinely helps.")

# ---------------------------------------------------------------- update loop
def _owner_ids():
    """Telegram uids allowed to run owner-only commands (/users). From HONESTLY_OWNER_IDS
    (comma-separated) so it is never hardcoded; comp accounts also count as owner."""
    maps_tools._load_env()
    raw = os.environ.get("HONESTLY_OWNER_IDS", "")
    return {x.strip() for x in raw.split(",") if x.strip()}

def _is_owner(uid):
    return str(uid) in _owner_ids() or is_comp(uid)

def _capture_user(u):
    """Log the interacting user (id always; username/first_name when present) on EVERY update,
    so the bot keeps a real, exportable user directory. Best-effort; never blocks handling."""
    for key in ("message", "edited_message", "callback_query", "pre_checkout_query"):
        node = u.get(key)
        if isinstance(node, dict) and isinstance(node.get("from"), dict):
            frm = node["from"]
            try:
                import store
                store.record_user(frm.get("id"), username=frm.get("username"),
                                  first_name=frm.get("first_name"), last_name=frm.get("last_name"))
            except Exception as e:
                log("capture_user error:", str(e)[:120])
            return

def handle(u):
    try:
        _capture_user(u)
    except Exception:
        pass
    if "message" in u and "successful_payment" in u["message"]:
        sp = u["message"]["successful_payment"]; chat = u["message"]["chat"]["id"]; uid = u["message"]["from"]["id"]
        payload = sp.get("invoice_payload", "")
        if payload == "sub":
            grant_sub(uid)
            say(chat, f"✅ <b>Pro active</b> - {SUB_PACKS_PER_MONTH} full valuation packs this "
                      "cycle, the whole kit each time. Send an address to run one.")
        elif payload.startswith("mbuy:"):           # a purchase made inside the Mini App
            say(chat, "✅ Payment received.")
            intent = consume_intent(payload.split(":", 1)[1])
            if deliver_intent(chat, uid, intent):
                _reward_referrer(uid)
            else:
                refund_credit(uid)
                say(chat, "I hit a snag generating that one. I've added a <b>free unlock</b> to your "
                          "account - send the address here and it'll deliver automatically.")
        elif payload.startswith("buym:"):           # a single micro-upsell add-on
            _, aud, mid = payload.split(":", 2)
            say(chat, "✅ Payment received.")
            if _deliver_micro_from_pending(chat, uid, aud, mid):
                _reward_referrer(uid)
            else:
                cid = sp.get("telegram_payment_charge_id")
                if cid:
                    try: tg("refundStarPayment", user_id=uid, telegram_payment_charge_id=cid)
                    except Exception as e: log("refund micro error:", str(e)[:120])
                say(chat, "Couldn't build that add-on, so I've refunded your Stars. Send the "
                          "address again and I'll deliver it.")
        elif payload.startswith("buy:"):
            _, aud, pack_id = payload.split(":", 2)
            say(chat, "✅ Payment received.")
            if finish_pack(chat, uid, aud, pack_id):
                _reward_referrer(uid)
            else:
                refund_credit(uid)   # they paid; hand a free unlock to retry, never charge for nothing
                say(chat, "I hit a snag generating that one. I've added a <b>free unlock</b> to your "
                          "account - send the address again and it'll deliver automatically.")
        return
    if "pre_checkout_query" in u:
        return tg("answerPreCheckoutQuery", pre_checkout_query_id=u["pre_checkout_query"]["id"], ok=True)
    if "callback_query" in u:
        cq = u["callback_query"]; uid = cq["from"]["id"]; chat = cq["message"]["chat"]["id"]
        tg("answerCallbackQuery", callback_query_id=cq["id"])
        if cq["data"].startswith("aud:"):
            aud = cq["data"].split(":", 1)[1]
            pend = PENDING.get(uid)
            if not pend: return say(chat, "Send me an address first.")
            pend["audience"] = aud
            return wizard_start(chat, uid)             # ask the intake, THEN value
        if cq["data"].startswith("q:"):
            _, field, raw = cq["data"].split(":", 2)
            return _wizard_answer(chat, uid, field, raw)
        if cq["data"].startswith("buym:"):             # buy a single micro-upsell add-on
            _, aud, mid = cq["data"].split(":", 2)
            return invoice_micro(chat, aud, mid)
        if cq["data"].startswith("buy:"):              # buy a single pack outright (no membership)
            _, aud, pack_id = cq["data"].split(":", 2)
            return invoice_pack(chat, aud, pack_id)    # the Stars invoice for that pack
        if cq["data"] == "tg_stop":                    # mute the re-engagement nudges (opt-out)
            try:
                import tg_funnel; tg_funnel.stop(chat)
            except Exception as e:
                log("tg_stop error:", str(e)[:160])
            return say(chat, "Muted - I won't nudge you about past valuations again. Your free "
                             "reports are still yours, and you can value a new address any time.")
        if cq["data"].startswith("pay:"):              # free unlock (promo credit) -> full kit
            aud = cq["data"].split(":", 1)[1]
            if use_credit(uid):
                say(chat, "✅ Free unlock - the full kit is on its way.")
                if not _deliver_from_pending(chat, uid, aud, ALL_COMPONENTS):
                    refund_credit(uid)                 # delivery failed - put the unlock back
                    say(chat, "Something went wrong delivering it - I've put your free unlock "
                              "back. Send the address again.")
                return
            pend = PENDING.get(uid)                     # no credit: show the packs
            if pend and pend.get("r"):
                return present_packs(chat, pend["r"], aud, uid)
            return say(chat, "Send the address again to see the options.")
        if cq["data"] == "sub":
            return invoice_sub(chat) if not subscribed(uid) else say(chat, "✅ You're already subscribed.")
        return
    if "message" not in u: return
    msg = u["message"]; chat = msg["chat"]["id"]; uid = msg["from"]["id"]
    text = (msg.get("text") or "").strip()
    if uid in AWAIT_TESTI and not text.startswith("/"):
        return capture_testimonial(chat, uid, msg, text)
    # mid-intake: we're waiting on a typed figure (agent quote / asking price)
    pend = PENDING.get(uid)
    if pend and pend.get("await") and not text.startswith("/"):
        field = pend["await"]
        if field in ("beds", "baths"):
            try: v = int(text)
            except ValueError: v = None
            if v is None or v < 1:
                return say(chat, "Type a number like <code>2</code>, or tap a button.")
        else:
            v = _parse_money(text)
            if v is None:
                return say(chat, "Send a figure like <code>525000</code>, or tap <b>Skip</b>.")
        _store_answer(uid, field, str(v))
        return _ask_step(chat, uid)
    if text.startswith("/start") or text.startswith("/app"):
        parts = text.split()
        arg = parts[1] if len(parts) > 1 else ""
        # widget hand-off: /start run_<sid> carries the full intake the user entered in the
        # Mini App, so we deliver straight away with everything pre-filled - no cold wizard.
        if arg.lower().startswith("run_"):
            intent = consume_intent(arg[4:])
            if begin_from_intent(chat, uid, intent):
                return
            say(chat, "That link has expired - send me the address here and I'll run it.")
        # deep-link referral: /start ref_<CODE> attaches the inviter before any purchase
        elif arg.lower().startswith("ref_"):
            if attach_referral(uid, arg[4:]):
                say(chat, "🎁 You came in on an invite - your first valuation's already free, "
                          "and your friend earns one when you upgrade.")
        # blog 'follow on Telegram': /start sub_<district-slug> registers a report follow on
        # this chat_id (no email, no phone) so we can ping the reader here when that report
        # refreshes - then nudges them toward valuing their own address.
        elif arg.lower().startswith("sub_"):
            slug = follow_area(uid, chat, arg[4:])
            label = slug.upper() if slug else "this area"
            return say(chat, f"🔔 You're following <b>{label}</b>. I'll message you right here "
                             f"when that report refreshes with new sold prices and listings - "
                             f"no email, nothing to manage.\n\nAnd when you want the same "
                             f"sold-evidence treatment for one specific address - yours, or one "
                             f"you're about to offer on - just send it to me and I'll run it.")
        # deliverable upsell deep link: /start buy_<product> - a guide/Pro hyperlink in the
        # PDF or interactive report lands here and fires the RELEVANT offer ready to buy
        # (never a sleeping bot). buy_pro -> Pro packs; buy_<micro-id> -> that single add-on.
        elif arg.lower().startswith("buy_"):
            if begin_buy(chat, uid, arg[4:]):
                return
        # landing-site widget: /start <base64url v1|audience|address> - pick up mid-flow with
        # the address and audience the visitor already chose, so we never start from nothing
        elif arg:
            decoded = decode_start_payload(arg)
            if decoded and begin_from_landing(chat, uid, decoded[0], decoded[1]):
                return
        kb = None
        wa = webapp_url()
        if wa:
            kb = [[{"text": "📊 Open Honestly Pro", "web_app": {"url": wa}}]]
        return say(chat, "👋 <b>Honestly</b>. A home is worth what the market will pay - "
                         "so no one can hand you an exact figure. What we can do is ground a "
                         "defensible estimate in the data, with every comparable open to check.\n\n"
                         "Send me a UK address to start"
                         + (", or open the app below." if wa else "."),
                         keyboard=kb)
    if text.startswith("/subscribe"):
        return invoice_sub(chat) if not subscribed(uid) else say(chat, "✅ You're already subscribed.")
    if text.startswith("/invite"):
        code = referral_code(uid)
        link = f"https://t.me/{BOT_USERNAME}?start=ref_{code}"
        earned = ref_earned(uid)
        tally = (f"\n\nSo far you've earned <b>{earned}</b> free "
                 f"valuation{'s' if earned != 1 else ''} from invites.") if earned else ""
        return say(chat, "🎁 <b>Invite a friend, earn a valuation.</b>\n"
                         "Share your link. When someone you invite buys their first pack, "
                         "you get a <b>free full valuation</b> - no limit on how many you can earn.\n\n"
                         f"<code>{link}</code>" + tally)
    if text.startswith("/testimonial"):
        return ask_testimonial(chat, uid)
    if text.startswith("/code"):
        parts = text.split()
        if len(parts) < 2:
            return say(chat, "Send the code after the command, e.g. <code>/code TAUK</code>.")
        res = redeem_code(uid, parts[1])
        if res == "comp":
            return say(chat, "✅ Unlimited access unlocked - full reports deliver instantly, no charge. "
                             "Send an address.")
        if res == "ok":
            return say(chat, f"✅ Code applied. You have <b>{free_credits(uid)}</b> free valuation. "
                             "Send an address to use it.")
        if res == "used":
            return say(chat, "You've already used that code.")
        return say(chat, "That code isn't valid.")
    if text.startswith("/help"):
        return say(chat, "Send an address, pick vendor/buyer/agent, answer a few quick questions about the "
                         "property (beds, baths, condition), see that the valuation is real, then unlock the "
                         "full appraisal.\n"
                         "/invite to earn free valuations · /code to redeem a promo · /subscribe for Pro · "
                         "/pulse for market chatter · /testimonial · /help")
    if text.startswith("/users"):                      # owner-only: who are our users + CSV export
        if not _is_owner(uid):
            return say(chat, "That command is for the bot owner.")
        try:
            import store, csv as _csv, io as _io
            rows = store.list_users()
            n = store.users_count()
            if not rows:
                return say(chat, "No users on record yet - the directory fills as people interact.")
            buf = _io.StringIO()
            w = _csv.writer(buf)
            w.writerow(["uid", "username", "first_name", "last_name", "first_seen", "last_seen", "msg_count"])
            for r in rows:
                w.writerow([r.get("uid"), r.get("username") or "", r.get("first_name") or "",
                            r.get("last_name") or "", _fmt_ts(r.get("first_seen")),
                            _fmt_ts(r.get("last_seen")), r.get("msg_count") or 0])
            path = os.path.join(HERE, "_users_export.csv")
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(buf.getvalue())
            preview = ", ".join(("@" + r["username"]) if r.get("username")
                                else (r.get("first_name") or str(r.get("uid"))) for r in rows[:8])
            tg_document(chat, path, caption=f"👥 <b>{n} users</b> on record. CSV attached "
                                            f"(uid, username, name, first/last seen, messages).")
            try: os.remove(path)
            except Exception: pass
            return say(chat, f"Most recent: {html.escape(preview)}")
        except Exception as e:
            log("/users error:", str(e)[:160])
            return say(chat, "Couldn't build the user export just now.")
    if text.startswith("/stop"):                       # opt out of re-engagement nudges
        try:
            import tg_funnel; tg_funnel.stop(chat)
        except Exception as e:
            log("/stop error:", str(e)[:160])
        return say(chat, "Done - no more nudges about past valuations. Your free reports stay "
                         "yours, and you can value a new address any time.")
    if text.startswith("/pulse"):
        return _cmd_pulse(chat, text)
    # a bare promo code typed on its own, e.g. "TAUK"
    if text.upper() in CODES:
        res = redeem_code(uid, text)
        if res == "comp":
            return say(chat, "✅ Unlimited access unlocked - full reports deliver instantly, no charge. "
                             "Send an address.")
        if res == "ok":
            return say(chat, f"✅ Code applied. You have <b>{free_credits(uid)}</b> free valuation. "
                             "Send an address to use it.")
        if res == "used":
            return say(chat, "You've already used that code. Send an address to get a valuation.")
    if len(text) < 6 or text.startswith("/"):
        return say(chat, "Send me a full UK address, e.g. <i>58 Cronin Street, London SE15 6JH</i>")
    # treat as an address (strip a leading conversational filler like "okay do" / "value")
    addr = _re.sub(r"^(ok(ay)?\s+)?(do|value|price|check|appraise)\s+", "", text, flags=_re.I).strip() or text
    PENDING[uid] = {"address": addr}
    say(chat, f"📍 <b>{html.escape(addr)}</b>\nWho are you?", keyboard=[[
        {"text": "🏠 Vendor", "callback_data": "aud:vendor"},
        {"text": "🔍 Buyer", "callback_data": "aud:buyer"},
        {"text": "📋 Agent", "callback_data": "aud:agent"}]])

def _cmd_pulse(chat, text):
    """ /pulse [area] - Reddit market sentiment for a UK area. Best-effort; never blocks."""
    if not _HAS_PULSE:
        return say(chat, "Market pulse isn't available right now (Reddit integration not loaded).")
    parts = text.split(maxsplit=1)
    area = parts[1].strip() if len(parts) > 1 else ""
    if not area:
        return say(chat, "Tell me an area or postcode, e.g. <code>/pulse SE15</code> or <code>/pulse Manchester</code>.")
    say(chat, "Looking for Reddit market chatter on <b>" + html.escape(area[:60]) + "</b>...")
    try:
        intel = _ri_mod.for_area(area, audience="general")
        if not intel or not intel.get("threads"):
            return say(chat, "Not enough Reddit chatter for <b>" + html.escape(area[:60]) + "</b> right now. Try a bigger area or a postcode district.")
        brief = _ri_mod.format_brief(intel)
        if brief:
            return say(chat, brief)
        return say(chat, "Couldn't build a market pulse for <b>" + html.escape(area[:60]) + "</b> right now.")
    except Exception as e:
        log("pulse error:", str(e)[:200])
        return say(chat, "Market pulse hit a glitch - try again in a moment.")



def _single_instance_lock(port=58982):
    """Bind a localhost port as a mutex. A second bot.py on this machine will fail
    to bind and exit, so we can never again have two pollers fighting over updates.
    The OS releases the port the instant this process dies."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.listen(1)
    except OSError:
        s.close()
        sys.exit("Another Honestly bot instance is already running on this machine. Exiting.")
    return s  # caller must keep this alive for the lock to hold

def _chat_of(u):
    """Best-effort chat id from any update shape, so we can apologise on a crash."""
    for k in ("message", "edited_message"):
        if k in u: return u[k].get("chat", {}).get("id")
    if "callback_query" in u:
        return u["callback_query"].get("message", {}).get("chat", {}).get("id")
    return None

def main():
    # Persist every valuation this process runs (store + update in place). Set here, in the
    # live entrypoint, rather than at import time, so the offline test suite (which imports
    # this module but never calls main) is never made to write to the database.
    os.environ.setdefault("HONESTLY_AUTOSTORE", "1")
    lock = _single_instance_lock()           # noqa: F841 (held for the process lifetime)
    log("Bot polling. Ctrl-C to stop.")
    me = tg("getMe")
    if not me.get("ok"): sys.exit(f"Bad token: {me}")
    global BOT_USERNAME
    BOT_USERNAME = me["result"]["username"]      # keep /invite links correct even if renamed
    log("Bot:", BOT_USERNAME)
    tg("deleteWebhook", drop_pending_updates=False)   # ensure long-polling is the only consumer
    wa = webapp_url()
    if wa:
        # Pin the Mini App to the chat's menu button so it's one tap from any chat.
        r = tg("setChatMenuButton", menu_button={
            "type": "web_app", "text": "Honestly Pro", "web_app": {"url": wa}})
        log("Menu button -> Mini App:", "ok" if r.get("ok") else r)
    else:
        log("HONESTLY_WEBAPP_URL not set - Mini App launch button disabled (chat-only mode).")
    offset = None
    while True:
        resp = tg("getUpdates", offset=offset, timeout=50)
        if not resp.get("ok"): time.sleep(3); continue
        for u in resp["result"]:
            offset = u["update_id"] + 1
            try:
                handle(u)
            except Exception as e:
                log("handler error:", str(e)[:200])
                chat = _chat_of(u)
                if chat:
                    try: say(chat, "Something went wrong on my end. Try again in a moment.")
                    except Exception: pass

if __name__ == "__main__":
    main()
