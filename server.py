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
import os, sys, json, html, hmac, time, hashlib, secrets, argparse, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import engine, maps_tools
import bot  # reuse the single source of truth for pricing + Stars invoicing

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)
maps_tools._load_env()
KEY = os.environ.get("PROPERTYDATA_KEY")
# Handoff store: the Mini App writes a purchase "intent" here keyed by a short id; the
# bot reads it on successful_payment so the paid valuation delivers even though the Mini
# App (this process) and the bot poller are separate processes. See bot.load_intent().
INTENTS = os.path.join(HERE, "miniapp_intents.json")

def _hash(s): return hashlib.md5(s.encode("utf-8")).hexdigest()[:10]

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
                asking=None, quoted=None):
    """Persist a purchase intent and return its short id. Pruned of anything older than a day."""
    store = _load_intents()
    cutoff = time.time() - 86400
    store = {k: v for k, v in store.items() if v.get("ts", 0) > cutoff}
    sid = secrets.token_urlsafe(9)
    store[sid] = {"uid": int(uid), "address": address, "audience": audience, "pack": pack,
                  "beds": beds, "finish": finish, "investment": bool(investment),
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

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str): body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path, q = u.path, urllib.parse.parse_qs(u.query)
        if path in ("/", "/index.html"):
            try:
                with open(os.path.join(HERE, "webapp", "index.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            except FileNotFoundError:
                return self._send(500, "webapp/index.html missing", "text/plain")
        if path.startswith("/img/"):
            name = os.path.basename(path)
            fp = os.path.join(CACHE, name)
            if os.path.exists(fp):
                ct = "image/png" if name.endswith(".png") else "image/jpeg"
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), ct)
            return self._send(404, "not found", "text/plain")
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
        if u.path not in ("/api/invoice", "/api/handoff"):
            return self._send(404, "not found", "text/plain")
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, json.dumps({"error": "bad request"}))
        # only a genuine, signed Telegram launch can act on behalf of a user
        user = validate_init_data(body.get("initData", ""))
        if not user or not user.get("id"):
            return self._send(403, json.dumps({"error": "Open this inside Telegram first."}))
        uid = user["id"]
        if u.path == "/api/handoff":
            return self._handoff(uid, body)
        pack_id = body.get("pack", "")
        aud = body.get("as", "agent")
        if aud not in ("vendor", "buyer", "agent"):
            aud = "agent"
        try:
            if pack_id == "pro":
                stars = bot._stars(bot.STARS_SUB)
                link = create_invoice_link(
                    "Honestly Pro", f"{bot.SUB_PACKS_PER_MONTH} full valuation packs a month.",
                    "sub", stars, subscription_period=bot.SUB_PERIOD)
                return self._send(200, json.dumps({"link": link}))
            p = bot.PACK.get(pack_id)
            if not p:
                return self._send(400, json.dumps({"error": "unknown pack"}))
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
            sid = save_intent(uid, address, aud, pack_id, beds=beds, finish=finish,
                              investment=investment, asking=asking, quoted=quoted)
            stars, _, gbp = bot.pack_price(p)
            link = create_invoice_link(f"{p['name']} ({gbp})",
                                       ", ".join(bot._SHORT[c] for c in p["components"]),
                                       f"mbuy:{sid}", stars)
            return self._send(200, json.dumps({"link": link}))
        except Exception as e:
            return self._send(500, json.dumps({"error": str(e)[:200]}))

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
                             "plus_above": bool(prev)})
        prev = p["components"]
    psub = bot._stars(bot.STARS_SUB)
    out["pro"] = {"id": "pro", "name": "Pro", "stars": psub, "gbp": bot._gbp(psub),
                  "packs_per_month": bot.SUB_PACKS_PER_MONTH}
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    if not KEY:
        sys.exit("PROPERTYDATA_KEY not set (env or .env)")
    print(f"Honestly server on http://localhost:{args.port}  (Ctrl-C to stop)")
    ThreadingHTTPServer(("0.0.0.0", args.port), H).serve_forever()

if __name__ == "__main__":
    main()
