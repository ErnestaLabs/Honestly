#!/usr/bin/env python3
"""bot.py - the valuation engine as a Telegram bot. No UI to build, payments built in.

Delivery surface for the engine: a user sends an address, picks who they are
(vendor / buyer / agent), and gets a mobile-native, evidence-backed valuation - 
plus the Street View frontage and, for agents, an optimised door-knock map.

Monetisation (Telegram Stars, in-app, no card processor):
  • First valuation per user - the FULL kit, free: a taste of everything we do.
  • After that, single valuations are bought outright - no membership needed
    (Stars ~= £ x 60 at what the buyer pays; clean rounded figures, no 99p add-ons):
      Valuation pack  ⭐300 (~£5)   PDF + interactive HTML report (+ audio walkthrough)
      Full pack       ⭐600 (~£10)  the above + action plan + door-knock map + email/script
  • Pro subscription ⭐1800/mo (~£30) - 10 full packs a month, for repeat (agent) use.
  • A 50% introductory launch price applies to every figure, shown honestly as an
    "Introductory price" (no fabricated was/now); flip bot.INTRO to False for standard.
The products differ by audience (agent / vendor / buyer); see products.py. We keep
the door open with one free first valuation, then buy-as-you-go packs or Pro.

Star amounts are integers and the Star/GBP rate is not fixed - the table below is
set to today's approximate mapping (~$0.02/Star) and should be tuned to the live rate.

Run:
  add TELEGRAM_BOT_TOKEN=... to .env   (from @BotFather)
  python bot.py
Raw Bot API over urllib - no third-party dependencies, same as the rest of the engine.
"""
import os, sys, json, time, html, datetime, base64, urllib.parse, urllib.request, urllib.error
import engine, maps_tools, cardimg, products
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

# ---- pricing (Telegram Stars; ~60 Stars per £ at what the buyer pays) -------
# Two one-off packs - a single valuation is bought outright, no membership needed -
# plus a Pro subscription for repeat (agent) use. Clean rounded Star figures: a
# defensible valuation is not sold like a 99p app, and there are no sub-£1 add-ons.
# The components mean different products by audience - see products.py.
STARS_PER_GBP = 60

PACKS = [
    {"id": "consumer", "stars": 300, "name": "Valuation pack",
     "components": ["report", "html"]},
    {"id": "full",     "stars": 600, "name": "Full pack",
     "components": ["report", "html", "plan", "map", "email"]},
]
PACK = {p["id"]: p for p in PACKS}
ALL_COMPONENTS = ["report", "html", "plan", "map", "email"]

STARS_SUB  = 1800       # Pro: ~£30/mo, 10 full packs a month (repeat/agent use)
SUB_PERIOD = 2592000    # 30 days, for recurring Star subscriptions
SUB_PACKS_PER_MONTH = 10

# 50% introductory launch price on every figure. A genuine launch discount, shown as
# an "Introductory price" (ASA-compliant - never a fabricated was/now). Flip to False
# to charge the standard prices above.
INTRO = True
INTRO_PCT = 50

def _stars(base):
    """Apply the introductory discount, rounded to a whole Star (Stars are integers)."""
    return max(1, round(base * (100 - INTRO_PCT) / 100)) if INTRO else base

def _gbp(stars):
    """Clean GBP display for a Star price at the buyer-facing rate (£5, £2.50, £15)."""
    v = stars / STARS_PER_GBP
    s = f"£{v:.2f}"
    return s[:-3] if s.endswith(".00") else s

def pack_price(p):
    """(stars_charged, '⭐150', '£2.50') - the live price for a pack, intro applied."""
    s = _stars(p["stars"])
    return s, f"⭐{s}", _gbp(s)

INTRO_NOTE = "✨ <b>Introductory price</b> - 50% off while we launch."

# short label per component, for invoice descriptions
_SHORT = {"report": "Valuation PDF", "html": "interactive HTML",
          "plan": "action plan", "map": "20 targets + map", "email": "email template"}

def _component_labels(audience):
    """What each component is called for this reader, so the ladder reads in their language."""
    L = {"report": "Valuation PDF (sold evidence, every comparable a Land Registry link)",
         "html":   "Interactive HTML report (tap any comparable to open its sold record)"}
    if audience == "agent":
        L["plan"]  = "Listing-win action plan"
        L["map"]   = "Door-knock route + 20 nearby targets, mapped"
        L["email"] = "Ready-to-send prospecting email"
    elif audience == "vendor":
        L["plan"]  = "Sell-for-the-most action plan"
        L["map"]   = "Your 20 live rivals, mapped"
        L["email"] = "Agent-vetting email template"
    else:  # buyer
        L["plan"]  = "Offer + negotiation plan"
        L["map"]   = "20 live alternatives, mapped"
        L["email"] = "Offer email to the agent"
    return L

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
    rec["sub_period_start"] = now.isoformat()   # resets the monthly pack allowance each cycle
    rec["sub_used"] = 0
    save_ent(e)
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
    """Has this user already had their one free, full-kit taste valuation?"""
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
def invoice_sub(chat_id):
    s = _stars(STARS_SUB)
    return tg("sendInvoice", chat_id=chat_id, title="Honestly Pro - monthly",
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
    return tg("sendInvoice", chat_id=chat_id, title=f"Honestly {p['name']} ({gbp})",
              description=what[:255], payload=f"buy:{audience}:{pack_id}",
              provider_token="", currency="XTR",
              prices=[{"label": f"{p['name']} ({gbp})", "amount": s}])

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
    """Short, mobile-native HTML, rendered from the shared engine.summary() - so the
    bot, the Mini App and the public link never quote different numbers. No table
    markdown (Telegram can't render it)."""
    d = engine.summary(r, audience, asking=asking, quoted=quoted, n=3)
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
    if chain:
        L.append("🔎 <b>How we got here</b> · " + " → ".join(chain)
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
    ev = "\n".join(f"• {html.escape(c['address'])} · {c['sqm']}sqm · {c['price_str']} "
                   f"({c['date']}), {_link(c['verify'], 'verify')}" for c in d["evidence"])
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
    L.append("\n<i>Anchored in HM Land Registry sold evidence (via PropertyData), steered for live "
             "market conditions. A home is worth what the market will pay.</i>")
    return "\n".join(L)

# ---------------------------------------------------------------- intake wizard
# We refuse to guess the inputs that move the number. After the user picks who they
# are, we ask a SHORT interactive form - a tap each for beds, baths and condition,
# plus the one figure that matters to their side of the deal (an agent's quote for a
# vendor, the asking price for a buyer). Only then do we value. That is the whole
# point of "Honestly": the figure rests on the real property, not our assumptions.
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

# --- condition sub-survey -------------------------------------------------------
# Two same-size homes are NOT worth the same: one with marble bathrooms and a stone
# kitchen sits above a plain neighbour. We refuse to flatten that into a single tap.
# Instead we ask a few quick condition signals and DERIVE the finish tier from them.
# The derived tier is the ONLY condition input that moves the figure, and it moves it
# exactly through the engine's existing finish_quality path (appraise.valuation queries
# the AVM at average/high/very_high, and discounts below that for needs_modernising /
# needs_renovation). No new multiplier, fully traceable, and disclosed back to the user.
FINISH_TIERS = ("needs_renovation", "needs_modernising", "average", "high", "very_high")

def _condition_steps():
    """The condition sub-survey: overall state (the floor) plus three quality signals
    that lift a liveable home up the finish ladder. Values are small integers we score."""
    return [
        {"field": "c_state", "q": "Overall, what <b>condition</b> is it in?",
         "opts": [("Needs full renovation", "0"), ("Dated, needs work", "1"),
                  ("Average, liveable", "2"), ("Well presented", "3"),
                  ("Refurbished throughout", "4")]},
        {"field": "c_kitchen", "q": "The <b>kitchen</b>?",
         "opts": [("Original / basic", "0"), ("Modern, mid-range", "1"),
                  ("High-end (stone tops, integrated)", "2")]},
        {"field": "c_bath", "q": "The <b>bathrooms</b>?",
         "opts": [("Dated", "0"), ("Modern, mid-range", "1"),
                  ("Luxury (marble / stone, underfloor)", "2")]},
        {"field": "c_premium",
         "q": "Any <b>premium materials</b> - marble, hardwood, bespoke joinery?",
         "opts": [("Standard throughout", "0"), ("Some premium", "1"),
                  ("Premium throughout", "2")]},
    ]

_FINISH_LABEL = {"needs_renovation": "FULL-RENOVATION", "needs_modernising": "NEEDS-MODERNISING",
                 "average": "AVERAGE", "high": "HIGH-SPEC", "very_high": "PREMIUM"}

def derive_finish(ans):
    """Map the condition signals to one of the engine's five finish tiers, deterministically.

    state 0/1 floor the home at needs_renovation / needs_modernising regardless of fittings
    (you do not get high-spec credit for a gut job). From 'liveable' up, what lifts the tier
    is GENUINELY high-end elements (a kitchen/bathroom/materials answer of 'high-end' or
    'luxury' = 2), not merely modern ones: two or more high-end elements -> very_high, one ->
    high, none -> average (mid-range fittings are what an average home already has). A full
    refurbishment is at least high spec. Returns (tier, disclosure_or_None). An explicit
    finish already on the answers (landing handoff, direct pick) is respected untouched -
    this only derives when the sub-survey was actually used."""
    if ans.get("finish") in FINISH_TIERS:
        return ans["finish"], None
    sig = {k: ans.get(k) for k in ("c_state", "c_kitchen", "c_bath", "c_premium")}
    if all(v is None for v in sig.values()):
        return "average", None                       # no signals -> safe, unmoved default
    state = sig["c_state"] if sig["c_state"] is not None else 2
    if state <= 1:
        tier = "needs_renovation" if state == 0 else "needs_modernising"
    else:
        high_end = sum(1 for f in ("c_kitchen", "c_bath", "c_premium") if sig.get(f) == 2)
        tier = "very_high" if high_end >= 2 else ("high" if high_end == 1 else "average")
        if state == 4 and tier == "average":         # a full refurbishment is at least high
            tier = "high"
    return tier, _finish_disclosure(sig, tier)

def _finish_disclosure(sig, tier):
    """Plain-English line naming the signals that set the tier, and stating - truthfully -
    that this is the one condition input that moves the figure."""
    bits = []
    if sig.get("c_kitchen") == 2: bits.append("a high-end kitchen")
    if sig.get("c_bath") == 2:    bits.append("luxury bathrooms")
    if sig.get("c_premium") == 2: bits.append("premium materials throughout")
    elif sig.get("c_premium") == 1: bits.append("some premium materials")
    if sig.get("c_state") == 4:   bits.append("a full refurbishment")
    elif sig.get("c_state") == 0: bits.append("a full renovation needed")
    elif sig.get("c_state") == 1: bits.append("dated finishes")
    detail = f" ({', '.join(bits)})" if bits else ""
    return (f"📐 Condition read{detail}: valuing this at the <b>{_FINISH_LABEL[tier]}</b> "
            f"finish tier. That is the one condition input that moves your figure - it "
            f"prices the model at that finish level. Everything else sits beside the "
            f"number, with its source, never inside it.")

def _wizard_steps(aud):
    """The questions, in order. 'opts' = tap choices; 'num' = type a figure (skippable).
    The single old 'condition' question is now the condition sub-survey (see above)."""
    beds  = {"field": "beds",  "q": "How many <b>bedrooms</b>?",
             "opts": [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5+", "5")]}
    baths = {"field": "baths", "q": "How many <b>bathrooms</b>?",
             "opts": [("1", "1"), ("2", "2"), ("3+", "3")]}
    cond  = _condition_steps()
    inv   = {"field": "investment",
             "q": "Is this an <b>investment</b> property (not your main home)?",
             "opts": [("Yes", "1"), ("No", "0")]}
    if aud == "vendor":
        return [beds, baths, *cond, inv,
                {"field": "quoted", "num": True,
                 "q": "Has an agent <b>quoted you a figure</b>? Type it "
                      "(e.g. <code>525000</code>) and I'll check it against the sold "
                      "evidence, or tap Skip."}]
    if aud == "buyer":
        return [beds, baths, *cond,
                {"field": "asking", "num": True,
                 "q": "What's the <b>asking price</b>? Type it (e.g. <code>525000</code>) "
                      "and I'll show your headroom over the evidence, or tap Skip."}]
    return [beds, baths, *cond, inv]          # agent

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
        kb = [[{"text": "Skip", "callback_data": f"q:{step['field']}:skip"}]]
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
    elif field in ("c_state", "c_kitchen", "c_bath", "c_premium"):
        try: ans[field] = int(raw)
        except ValueError: pass
    elif field == "finish":                          # direct pick / landing handoff
        if raw in FINISH_TIERS: ans[field] = raw
    elif field == "investment":
        ans[field] = (raw == "1")
    elif field in ("asking", "quoted"):
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
    tier, disclosure = derive_finish(ans)            # condition signals -> one finish tier
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
    if not had_first(uid):                           # the one free taste of everything
        ok = deliver_full(chat, r, aud, asking=asking, quoted=quoted)
        if ok:
            mark_first(uid)                          # only on success - a failed taste isn't spent
            explain_packs(chat, aud)
            ask_testimonial(chat, uid)
        return ok
    if subscribed(uid):                              # Pro: full kit, drawn from the monthly allowance
        return deliver_sub(chat, uid, r, aud, asking=asking, quoted=quoted)
    return present_packs(chat, r, aud, uid)          # buy a single valuation outright (no membership)

# ---------------------------------------------------------------- produce the work
def run_value(chat_id, address, answers=None):
    """Produce the work: run the engine on the inputs the user actually gave us in the
    intake (beds, baths, condition, investment) - never guessed. Returns the result, or
    None on failure (having messaged the user). Cached in PENDING so the paid result is
    identical to the teaser."""
    say(chat_id, "⏳ Pulling sold comparables and crunching the evidence.")
    key = os.environ.get("PROPERTYDATA_KEY")
    a = answers or {}
    try:
        return engine.value(address, key,
                            beds=a.get("beds"), baths=a.get("baths") or 1,
                            finish=a.get("finish") or "average",
                            investment=bool(a.get("investment")))
    except SystemExit as e:
        say(chat_id, f"❌ {html.escape(str(e))}"); return None
    except Exception as e:
        say(chat_id, f"❌ Couldn't value that address: {html.escape(str(e)[:160])}"); return None

def _pack_lines(audience):
    """The two packs, written in this reader's language. Returns (text_lines, keyboard)."""
    labels = _component_labels(audience)
    lines, prev = [], []
    for p in PACKS:
        added = [c for c in p["components"] if c not in prev]
        desc = "; ".join(labels[c] for c in added)
        _, stars_str, gbp = pack_price(p)
        tail = "" if not prev else " <i>(plus everything above)</i>"
        lines.append(f"• <b>{p['name']} - {gbp}</b> ({stars_str}): {desc}{tail}")
        prev = p["components"]
    kb = [[{"text": f"{p['name']} · {pack_price(p)[1]}", "callback_data": f"buy:{audience}:{p['id']}"}]
          for p in PACKS]
    return lines, kb

def present_packs(chat_id, r, audience, uid=None):
    """No teaser image - the figure is real and the products are real. Show the honest
    summary, then the two packs: buy a single valuation outright, no membership. A user
    with a free unlock (promo credit) gets a button for the full kit at no charge."""
    d = engine.summary(r, audience, n=4)
    n = len(r["compsA"])
    lines = [f"Your valuation for <b>{html.escape(d['address'])}</b> is ready - built from "
             f"<b>{n}</b> verified sold comparables and the live local market.", "",
             "Take it further:"]
    pack_text, kb = _pack_lines(audience)
    lines += pack_text
    if INTRO:
        lines += ["", INTRO_NOTE]
    has_free = uid is not None and free_credits(uid) > 0
    if has_free:
        lines.append("\nYou have a <b>free unlock</b> - tap below for the full kit, no charge.")
        kb.append([{"text": "🔓 Use my free unlock (full kit)", "callback_data": f"pay:{audience}"}])
    else:
        lines.append(f"\nRun lots? <b>Pro</b> is {_gbp(_stars(STARS_SUB))}/mo for "
                     f"{SUB_PACKS_PER_MONTH} full packs - send /subscribe. "
                     "Have a code? <code>/code YOURCODE</code>.")
    return say(chat_id, "\n".join(lines), keyboard=kb)

def explain_packs(chat, audience):
    """Shown once, right after the free first-time taste: how it works from here - buy a
    single valuation outright whenever you need one, or go Pro if you run lots."""
    lines = ["", "🎁 <b>That one was on us</b> - the full kit, so you can see exactly what "
             "Honestly does for you.", "",
             "From here, buy a single valuation whenever you need one - no membership:"]
    pack_text, kb = _pack_lines(audience)
    lines += pack_text
    if INTRO:
        lines += ["", INTRO_NOTE]
    lines += ["", f"Run lots? <b>Pro</b> is {_gbp(_stars(STARS_SUB))}/mo for "
              f"{SUB_PACKS_PER_MONTH} full packs."]
    kb.append([{"text": f"⭐ Go Pro, {_gbp(_stars(STARS_SUB))}/mo", "callback_data": "sub"}])
    say(chat, "\n".join(lines), keyboard=kb)

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
    """The 20 nearby listings as a tappable in-chat list (each row links to its portal)."""
    head = {"agent": "🚪 <b>Doors to knock</b>", "vendor": "📊 <b>Your live rivals</b>",
            "buyer": "🔍 <b>Live alternatives</b>"}.get(audience, "<b>Nearby</b>")
    L = [head]
    for i, t in enumerate(targets, 1):
        addr = html.escape(t.get("loc") or t["address"])
        if t.get("link"):
            addr = f'<a href="{html.escape(t["link"])}">{addr}</a>'
        beds = f"{t['beds']} bed · " if t.get("beds") else ""
        dom  = f" · {t['dom']}d on mkt" if t.get("dom") else ""
        L.append(f"{i}. {addr} · {beds}{html.escape(t['price_str'])}{dom}")
    return "\n".join(L)

def deliver_components(chat_id, r, audience, components, asking=None, quoted=None):
    """Deliver exactly the components bought (or all of them, for the free taste / a
    subscriber). The text card is ALWAYS sent - it IS the answer and the safety net.
    Everything else is layered on per the tier. Returns True iff something reached the
    user, so callers can refund on total failure. Each extra is fully guarded - a slow
    or missing piece never blocks the rest."""
    comp = set(components)
    d = engine.summary(r, audience, asking=asking, quoted=quoted, n=4)
    res = say(chat_id, card(r, audience, asking=asking, quoted=quoted))
    delivered = bool(res.get("ok"))
    key = os.environ.get("PROPERTYDATA_KEY")
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
            pdf_path, html_path = report.build(r, audience, slug=str(chat_id),
                                               interactive=("html" in comp), key=key)
            res = tg_document(chat_id, pdf_path,
                              caption="📄 <b>Full report</b> - every comparable links to its HM Land Registry record.")
            delivered = delivered or bool(res.get("ok"))
            if html_path and "html" in comp:
                try:
                    tg_document(chat_id, html_path, mime="text/html",
                                caption="🔗 Interactive version - tap any comparable to open its sold record.")
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
    # the action plan, written for this reader
    if "plan" in comp:
        try:
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
                    head = "your live rivals" if audience == "vendor" else "the live alternatives"
                    stops = [subj_addr] + [t["address"] for t in targets[:9]]
                    url = maps_tools.directions_url(stops, mode="driving")
                    cap = f"🗺️ <b>{head.capitalize()} on the map</b> - {len(targets)} nearby, pinned and live."
                    btn = "🗺️ Open the map in Google Maps"
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
    """The whole kit, every component. Used for subscribers, comp (PROPHET) and the one
    free first-time taste. Returns True iff something reached the user."""
    return deliver_components(chat_id, r, audience, ALL_COMPONENTS, asking=asking, quoted=quoted)

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

def begin_from_intent(chat, uid, intent):
    """A widget hand-off (NOT a purchase): the Mini App already collected the address and the
    full intake, so we pick up with everything pre-filled and never re-ask in chat. We rebuild
    PENDING from the intent and run the SAME finisher the chat wizard uses, so the entitlement
    logic (free first taste / Pro / buy a pack) stays identical no matter where the user started."""
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

def deliver_intent(chat, uid, intent):
    """Deliver a Mini App purchase. The intent is self-contained (address + inputs the user
    gave the web form), so it doesn't depend on the bot's in-memory PENDING - the two run as
    separate processes. Re-runs the engine on those inputs and delivers the pack's components."""
    if not intent or int(intent.get("uid", -1)) != int(uid):
        return False
    p = PACK.get(intent.get("pack"))
    if not p:
        return False
    aud = intent.get("audience", "agent")
    answers = {"beds": intent.get("beds"), "finish": intent.get("finish") or "average",
               "investment": intent.get("investment")}
    r = run_value(chat, intent["address"], answers)
    if not r:
        return False
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
def handle(u):
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
        if cq["data"].startswith("buy:"):              # buy a single pack outright (no membership)
            _, aud, pack_id = cq["data"].split(":", 2)
            return invoice_pack(chat, aud, pack_id)    # the Stars invoice for that pack
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
        # landing-site widget: /start <base64url v1|audience|address> - pick up mid-flow with
        # the address and audience the visitor already chose, so we never start from nothing
        elif arg:
            decoded = decode_start_payload(arg)
            if decoded and begin_from_landing(chat, uid, decoded[0], decoded[1]):
                return
        kb = None
        wa = webapp_url()
        if wa:
            kb = [[{"text": "📊 Open the valuation app", "web_app": {"url": wa}}]]
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
            "type": "web_app", "text": "Valuation app", "web_app": {"url": wa}})
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
