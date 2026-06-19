#!/usr/bin/env python3
"""store.py - Honestly's persistence layer.

A real, ACID database (single-file SQLite, zero infra) behind one module with a
small, typed accessor surface. Everything the app produces is written here,
categorised with provenance and timestamps, for two reasons the user named:
training (an accumulating, labelled corpus) and legal (a durable audit trail of
exactly what we told whom, and on what evidence).

Five tables, each documented:

  appraisals       one row per valuation run: the address, the resolved postcode
                   and district, the audience, the condition tier and CGT flag,
                   the four headline figures, AND the full engine.summary() JSON
                   so the figure can always be reconstructed and explained.
  deliverables     every artifact built off an appraisal (pdf|html|audio|plan|
                   map|email): its on-disk path and, for the hosted link, the
                   HTML body itself so /r/<token> can serve it with zero drift.
  tokens           the /r/<token> registry: a public share token -> an appraisal,
                   with an expiry (nullable = permanent; default 90 days) and a
                   revoked flag, so a private link can be timed out or killed.
  market_analysis  cached, categorised market reads keyed by postcode district +
                   date, with full provenance (which tool, the query, the raw
                   payload, the synthesised lines, a sentiment, a TTL).
  events           a categorised audit log of everything the app does
                   (valuation_requested, deliverable_built, link_served,
                   payment, market_scan, ...) for training + legal.
  leads            the blog-PDF lead-capture gate: one row per reader who handed
                   over their details to download a free area report. Holds the
                   email, the slug they wanted, and a download token for /dl/<token>.

Contract: this module is BEST-EFFORT. No public function ever raises into the
request path - on any failure it logs to stderr and returns a safe default
(None / False / []). Persistence failing must never cost a user their valuation.

The accessor surface is deliberately storage-agnostic (no SQL leaks out), so the
Phase-5 move to Postgres/PostGIS is a swap of this file's internals, not its
callers. SQLite runs in WAL mode with a busy timeout and a fresh connection per
call, which is safe under server.py's ThreadingHTTPServer.

  python store.py selftest      # round-trip every table in a temp DB, no infra
"""
import os, json, time, sqlite3, secrets, re, sys, threading

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("HONESTLY_DB", os.path.join(HERE, "honestly.db"))

_DDL = """
CREATE TABLE IF NOT EXISTS appraisals (
    token             TEXT PRIMARY KEY,
    address           TEXT,
    postcode          TEXT,
    postcode_district TEXT,
    audience          TEXT,
    finish            TEXT,
    investment        INTEGER DEFAULT 0,
    low               INTEGER,
    high              INTEGER,
    central           INTEGER,
    guide             INTEGER,
    summary_json      TEXT,
    source            TEXT,
    tier              TEXT,
    chat_id           TEXT,
    created_at        REAL
);
CREATE INDEX IF NOT EXISTS ix_appraisals_district ON appraisals(postcode_district);
CREATE INDEX IF NOT EXISTS ix_appraisals_created  ON appraisals(created_at);

CREATE TABLE IF NOT EXISTS deliverables (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    appraisal_token  TEXT,
    kind             TEXT,
    path             TEXT,
    body             TEXT,
    created_at       REAL
);
CREATE INDEX IF NOT EXISTS ix_deliverables_appraisal ON deliverables(appraisal_token);
CREATE INDEX IF NOT EXISTS ix_deliverables_kind      ON deliverables(appraisal_token, kind);

CREATE TABLE IF NOT EXISTS tokens (
    token            TEXT PRIMARY KEY,
    appraisal_token  TEXT,
    created_at       REAL,
    expires_at       REAL,
    revoked          INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_tokens_appraisal ON tokens(appraisal_token);

CREATE TABLE IF NOT EXISTS market_analysis (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    postcode_district TEXT,
    category          TEXT,
    source            TEXT,
    query             TEXT,
    payload_json      TEXT,
    lines_json        TEXT,
    sentiment         TEXT,
    fetched_at        REAL,
    ttl               REAL
);
CREATE INDEX IF NOT EXISTS ix_market_lookup ON market_analysis(postcode_district, category, fetched_at);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT,
    token       TEXT,
    detail_json TEXT,
    created_at  REAL
);
CREATE INDEX IF NOT EXISTS ix_events_kind    ON events(kind, created_at);
CREATE INDEX IF NOT EXISTS ix_events_token   ON events(token);

CREATE TABLE IF NOT EXISTS leads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    token       TEXT UNIQUE,
    email       TEXT,
    name        TEXT,
    slug        TEXT,
    persona     TEXT,    -- who the reader told us they are: vendor|buyer|agent|other
    source      TEXT,
    created_at  REAL
);
CREATE INDEX IF NOT EXISTS ix_leads_email   ON leads(email);
CREATE INDEX IF NOT EXISTS ix_leads_slug    ON leads(slug, created_at);

CREATE TABLE IF NOT EXISTS email_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_token  TEXT,
    email       TEXT,
    slug        TEXT,
    step        INTEGER,
    kind        TEXT,
    send_after  REAL,
    sent_at     REAL,
    status      TEXT DEFAULT 'pending',
    created_at  REAL
);
CREATE INDEX IF NOT EXISTS ix_emailq_due   ON email_queue(status, send_after);
CREATE INDEX IF NOT EXISTS ix_emailq_email ON email_queue(email);
CREATE INDEX IF NOT EXISTS ix_emailq_lead  ON email_queue(lead_token);

-- Telegram re-engagement / micro-sell queue. The bot user is a persistent channel (we hold
-- their chat_id), so a delivered Lite report can be followed by honest, value-led, audience-
-- aware nudges and small Pro unlocks - the in-chat analog of email_queue. opt-outs are tracked
-- per chat so a /stop is permanent.
CREATE TABLE IF NOT EXISTS tg_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     TEXT,
    token       TEXT,           -- appraisal token this nudge is about
    audience    TEXT,
    step        INTEGER,
    kind        TEXT,
    send_after  REAL,
    sent_at     REAL,
    status      TEXT DEFAULT 'pending',
    created_at  REAL
);
CREATE INDEX IF NOT EXISTS ix_tgq_due  ON tg_queue(status, send_after);
CREATE INDEX IF NOT EXISTS ix_tgq_chat ON tg_queue(chat_id);

CREATE TABLE IF NOT EXISTS tg_optout (
    chat_id     TEXT PRIMARY KEY,
    created_at  REAL
);

-- Bot user directory. Telegram gives no list of your users, so we log each one the first time
-- they interact (id is always present; username/first_name only when they have/share them) and
-- bump last_seen + a message counter on every interaction. Lets us see and export who our
-- users actually are (privacy-respecting: only what Telegram already hands the bot).
CREATE TABLE IF NOT EXISTS users (
    uid         TEXT PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    last_name   TEXT,
    first_seen  REAL,
    last_seen   REAL,
    msg_count   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_users_seen ON users(last_seen);

CREATE TABLE IF NOT EXISTS blog_posts (
    slug              TEXT PRIMARY KEY,
    city_slug         TEXT,
    district          TEXT,
    series            TEXT,
    title             TEXT,
    description       TEXT,
    headline_price    INTEGER,
    model_json        TEXT,
    html              TEXT,
    generated_at      TEXT,
    created_at        REAL,
    updated_at        REAL
);
CREATE INDEX IF NOT EXISTS ix_blog_city    ON blog_posts(city_slug, updated_at);
CREATE INDEX IF NOT EXISTS ix_blog_updated ON blog_posts(updated_at);

-- Purchased catalogue products: one row per delivery. The html_body is the full standalone
-- HTML page (product_html.render output) served at /p/<share_token>. Permanent; the user
-- can return to it from the Library tab any time. uid = Telegram user id (str).
CREATE TABLE IF NOT EXISTS purchases (
    share_token     TEXT PRIMARY KEY,
    uid             TEXT,
    pid             TEXT,
    address         TEXT,
    title           TEXT,
    blurb           TEXT,
    profile         TEXT,
    html_body       TEXT,
    created_at      REAL
);
CREATE INDEX IF NOT EXISTS ix_purchases_uid ON purchases(uid, created_at);

-- Research notebooks: maps each saved appraisal to its Open Notebook notebook_id and the
-- current chat session_id (so conversations persist across property opens).
CREATE TABLE IF NOT EXISTS property_notebooks (
    appraisal_token  TEXT PRIMARY KEY,
    notebook_id      TEXT,
    chat_session_id  TEXT,
    created_at       REAL
);
"""

_INIT_LOCK = threading.Lock()
_INITED = False


def _log(*a):
    print("[store]", *a, file=sys.stderr)


def _conn():
    """A fresh connection per call - simplest correct posture under threads. WAL +
    busy timeout let the bot poller and the web server write concurrently without
    'database is locked'. The schema is ensured once, lazily, behind a lock."""
    global _INITED
    c = sqlite3.connect(DB_PATH, timeout=10.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=10000")
    if not _INITED:
        with _INIT_LOCK:
            if not _INITED:
                c.executescript(_DDL)
                _ensure_columns(c)
                c.commit()
                _INITED = True
    return c


# Columns added to existing tables after their first ship. CREATE TABLE IF NOT EXISTS never
# alters a live table, so each new column is applied here, idempotently, on first connect.
_COLUMN_MIGRATIONS = [
    ("leads", "persona", "TEXT"),
    # the bot/web user who owns this valuation - powers the Pro workspace "my properties"
    # list. Lives here (not just the free-text source) so list_appraisals(chat_id) is indexed.
    ("appraisals", "chat_id", "TEXT"),
]

# Indexes that depend on a migrated column (so they can't live in _DDL, which runs before the
# column is added on an existing DB). Applied after the column migrations, idempotently.
_POST_MIGRATION_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_appraisals_chat ON appraisals(chat_id, created_at)",
]


def _ensure_columns(c):
    """Best-effort: add any missing column in _COLUMN_MIGRATIONS to an existing DB, then create
    any index that depends on those columns. Idempotent (checks PRAGMA table_info first) and never
    raises - a migration failure must not block a request; the feature using the column simply
    reads NULL."""
    for table, col, decl in _COLUMN_MIGRATIONS:
        try:
            have = {r["name"] for r in c.execute("PRAGMA table_info(%s)" % table)}
            if col not in have:
                c.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, decl))
        except Exception as e:
            _log("migrate", table, col, str(e)[:120])
    for ddl in _POST_MIGRATION_INDEXES:
        try:
            c.execute(ddl)
        except Exception as e:
            _log("migrate-index", str(e)[:120])


# ------------------------------------------------------------------ helpers
_PC_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.I)


def _postcode(text):
    """Pull a UK postcode out of an address string, normalised 'OUT IN'. None if absent."""
    if not text:
        return None
    m = _PC_RE.search(text.upper())
    return f"{m.group(1)} {m.group(2)}" if m else None


def district_of(postcode_or_addr):
    """The outward code (e.g. 'EC1V' from 'EC1V 1AE') - the public key for area-level
    records like market_analysis. Accepts a bare postcode or a full address."""
    pc = postcode_or_addr if (postcode_or_addr and _PC_RE.fullmatch(
        (postcode_or_addr or "").strip().upper())) else _postcode(postcode_or_addr)
    if not pc:
        return None
    return pc.split()[0]


def _new_token(nbytes=9):
    return secrets.token_urlsafe(nbytes)


def _json(obj):
    try:
        return json.dumps(obj, default=str, ensure_ascii=False)
    except Exception:
        return None


# ------------------------------------------------------------------ appraisals
def record_appraisal(summary, *, address=None, postcode=None, audience=None,
                     finish=None, investment=None, source=None, tier=None,
                     token=None, chat_id=None):
    """Persist one valuation run and return its appraisal token (or None on failure).

    `summary` is the engine.summary() dict - the single source of truth. The
    headline figures, address and audience are read from it; anything passed
    explicitly overrides. The whole dict is stored as JSON so the figure can be
    reconstructed and re-explained later (training + legal).

    `chat_id` is the owning bot/web user (when known) - it indexes the Pro workspace's
    "my properties" list. Falls back to parsing a 'bot:<chat_id>' source so existing
    callers that only set `source` still tag the owner."""
    try:
        d = summary or {}
        token = token or _new_token()
        address = address or d.get("address")
        postcode = postcode or _postcode(address)
        audience = audience or d.get("audience")
        investment = d.get("investment") if investment is None else investment
        chat_id = _chat_id_str(chat_id) or _chat_id_from_source(source)
        with _conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO appraisals (token, address, postcode, "
                "postcode_district, audience, finish, investment, low, high, "
                "central, guide, summary_json, source, tier, chat_id, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (token, address, postcode, district_of(postcode or address or ""),
                 audience, finish, 1 if investment else 0,
                 d.get("low"), d.get("high"), d.get("central"), d.get("guide"),
                 _json(d), source, tier, chat_id, time.time()))
        log_event("valuation_requested", token=token,
                  detail={"address": address, "audience": audience,
                          "central": d.get("central"), "source": source, "tier": tier})
        return token
    except Exception as e:
        _log("record_appraisal:", str(e)[:200])
        return None


def _chat_id_str(chat_id):
    """Normalise a chat_id to a non-empty string, or None."""
    if chat_id is None:
        return None
    s = str(chat_id).strip()
    return s or None


_SOURCE_CHAT_RE = re.compile(r"^bot:(\d+)")


def _chat_id_from_source(source):
    """Pull the chat_id out of a 'bot:<chat_id>' source tag (the bot path's convention), or None."""
    if not source:
        return None
    m = _SOURCE_CHAT_RE.match(str(source).strip())
    return m.group(1) if m else None


def get_appraisal(token):
    """The stored appraisal row as a dict (summary re-parsed under 'summary'), or None."""
    try:
        with _conn() as c:
            row = c.execute("SELECT * FROM appraisals WHERE token=?", (token,)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["summary"] = json.loads(out["summary_json"]) if out.get("summary_json") else None
        return out
    except Exception as e:
        _log("get_appraisal:", str(e)[:200])
        return None


def list_appraisals(chat_id, limit=50):
    """The Pro workspace's 'my properties' list: this user's valuations, newest first, as light
    dicts (no full summary JSON - just what a portfolio card needs). The purity % is read back out
    of the stored summary so the card can show it without re-running the engine. Returns [] on
    failure or for an unknown user."""
    chat_id = _chat_id_str(chat_id)
    if not chat_id:
        return []
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT a.token, a.address, a.postcode, a.postcode_district, a.audience, "
                "a.investment, a.low, a.high, a.central, a.guide, a.tier, a.created_at, "
                "a.summary_json, "
                "(SELECT t.token FROM tokens t WHERE t.appraisal_token=a.token AND t.revoked=0 "
                "  ORDER BY t.created_at DESC LIMIT 1) AS share_token, "
                "EXISTS(SELECT 1 FROM deliverables d WHERE d.appraisal_token=a.token "
                "  AND d.kind='html') AS has_html "
                "FROM appraisals a WHERE a.chat_id=? ORDER BY a.created_at DESC LIMIT ?",
                (chat_id, int(limit))).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            sj = d.pop("summary_json", None)
            purity = None
            if sj:
                try:
                    purity = (json.loads(sj).get("evidence_purity") or {}).get("pct")
                except Exception:
                    purity = None
            d["purity"] = purity
            d["has_html"] = bool(d.get("has_html"))
            out.append(d)
        return out
    except Exception as e:
        _log("list_appraisals:", str(e)[:200])
        return []


def tag_appraisal(token, chat_id):
    """Claim an appraisal for a user (the web path, where the owner is only known once the Mini
    App POSTs its initData). Idempotent. Returns True iff a row was updated."""
    chat_id = _chat_id_str(chat_id)
    if not (token and chat_id):
        return False
    try:
        with _conn() as c:
            cur = c.execute("UPDATE appraisals SET chat_id=? WHERE token=?", (chat_id, token))
        return cur.rowcount > 0
    except Exception as e:
        _log("tag_appraisal:", str(e)[:200])
        return False


def backfill_chat_id_from_source(limit=100000):
    """One-off: populate chat_id on old rows that predate the column, from their 'bot:<chat_id>'
    source tag. Safe to run repeatedly (only touches rows where chat_id IS NULL). Returns the
    number of rows updated."""
    try:
        n = 0
        with _conn() as c:
            rows = c.execute(
                "SELECT token, source FROM appraisals WHERE chat_id IS NULL AND source LIKE 'bot:%' "
                "LIMIT ?", (int(limit),)).fetchall()
            for r in rows:
                cid = _chat_id_from_source(r["source"])
                if cid:
                    c.execute("UPDATE appraisals SET chat_id=? WHERE token=?", (cid, r["token"]))
                    n += 1
        _log("backfill_chat_id_from_source:", n, "rows")
        return n
    except Exception as e:
        _log("backfill_chat_id_from_source:", str(e)[:200])
        return 0


# ------------------------------------------------------------------ deliverables
def record_deliverable(appraisal_token, kind, *, path=None, body=None):
    """Record an artifact built off an appraisal. `kind` in pdf|html|audio|plan|map|
    email. For the hosted HTML link, pass the HTML `body` so /r/<token> serves it
    directly. Returns the deliverable id, or None."""
    try:
        with _conn() as c:
            cur = c.execute(
                "INSERT INTO deliverables (appraisal_token, kind, path, body, created_at) "
                "VALUES (?,?,?,?,?)", (appraisal_token, kind, path, body, time.time()))
            did = cur.lastrowid
        log_event("deliverable_built", token=appraisal_token,
                  detail={"kind": kind, "path": path, "has_body": bool(body)})
        return did
    except Exception as e:
        _log("record_deliverable:", str(e)[:200])
        return None


def get_deliverable(appraisal_token, kind):
    """The most recent deliverable of a kind for an appraisal, as a dict, or None."""
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT * FROM deliverables WHERE appraisal_token=? AND kind=? "
                "ORDER BY created_at DESC LIMIT 1", (appraisal_token, kind)).fetchone()
        return dict(row) if row else None
    except Exception as e:
        _log("get_deliverable:", str(e)[:200])
        return None


# ------------------------------------------------------------------ tokens (/r/)
DEFAULT_TTL_DAYS = 90


def mint_token(appraisal_token, *, ttl_days=DEFAULT_TTL_DAYS):
    """Mint a public /r/<token> share token for an appraisal. ttl_days=None makes it
    permanent. Returns the token string, or None on failure."""
    try:
        now = time.time()
        expires = None if ttl_days is None else now + ttl_days * 86400
        tok = _new_token()
        with _conn() as c:
            c.execute(
                "INSERT INTO tokens (token, appraisal_token, created_at, expires_at, revoked) "
                "VALUES (?,?,?,?,0)", (tok, appraisal_token, now, expires))
        return tok
    except Exception as e:
        _log("mint_token:", str(e)[:200])
        return None


def share_token_for(appraisal_token):
    """The most recent live (non-revoked, unexpired) /r/<token> share token for an appraisal, or
    None. Lets the Pro workspace surface the existing public link instead of minting duplicates."""
    if not appraisal_token:
        return None
    try:
        now = time.time()
        with _conn() as c:
            row = c.execute(
                "SELECT token FROM tokens WHERE appraisal_token=? AND revoked=0 "
                "AND (expires_at IS NULL OR expires_at > ?) ORDER BY created_at DESC LIMIT 1",
                (appraisal_token, now)).fetchone()
        return row["token"] if row else None
    except Exception as e:
        _log("share_token_for:", str(e)[:200])
        return None


def resolve_token(token):
    """Resolve a /r/<token> link for serving. Returns a dict:
        {ok, reason, appraisal_token, address, html}
    ok is False with a reason ('unknown'|'revoked'|'expired') when the link must
    not serve. The stored HTML body travels in 'html' so the route serves it with
    zero drift from the file the user was sent."""
    try:
        with _conn() as c:
            row = c.execute("SELECT * FROM tokens WHERE token=?", (token,)).fetchone()
            if not row:
                return {"ok": False, "reason": "unknown"}
            if row["revoked"]:
                return {"ok": False, "reason": "revoked"}
            if row["expires_at"] is not None and time.time() > row["expires_at"]:
                return {"ok": False, "reason": "expired"}
            appraisal_token = row["appraisal_token"]
            dv = c.execute(
                "SELECT body, path FROM deliverables WHERE appraisal_token=? AND kind='html' "
                "ORDER BY created_at DESC LIMIT 1", (appraisal_token,)).fetchone()
            ap = c.execute("SELECT address FROM appraisals WHERE token=?",
                           (appraisal_token,)).fetchone()
        html_body = dv["body"] if dv else None
        # fall back to reading the stored path if the body was not inlined
        if not html_body and dv and dv["path"] and os.path.exists(dv["path"]):
            try:
                with open(dv["path"], encoding="utf-8") as f:
                    html_body = f.read()
            except Exception:
                html_body = None
        log_event("link_served", token=token,
                  detail={"appraisal_token": appraisal_token, "served": bool(html_body)})
        return {"ok": True, "appraisal_token": appraisal_token,
                "address": ap["address"] if ap else None, "html": html_body}
    except Exception as e:
        _log("resolve_token:", str(e)[:200])
        return {"ok": False, "reason": "error"}


def revoke_token(token):
    """Kill a share link. Returns True iff a row was updated."""
    try:
        with _conn() as c:
            cur = c.execute("UPDATE tokens SET revoked=1 WHERE token=?", (token,))
        log_event("link_revoked", token=token, detail={})
        return cur.rowcount > 0
    except Exception as e:
        _log("revoke_token:", str(e)[:200])
        return False


# ------------------------------------------------------------------ market analysis
def record_market_analysis(postcode_district, category, *, source=None, query=None,
                           payload=None, lines=None, sentiment=None, ttl_hours=24):
    """Cache a categorised market read for an area, with full provenance. Returns the
    row id, or None. Keyed (for lookup) by district + category + freshness."""
    try:
        with _conn() as c:
            cur = c.execute(
                "INSERT INTO market_analysis (postcode_district, category, source, query, "
                "payload_json, lines_json, sentiment, fetched_at, ttl) VALUES (?,?,?,?,?,?,?,?,?)",
                (postcode_district, category, source, _json(query) if query is not None else None,
                 _json(payload), _json(lines), sentiment, time.time(),
                 None if ttl_hours is None else ttl_hours * 3600.0))
            mid = cur.lastrowid
        log_event("market_scan", token=postcode_district,
                  detail={"category": category, "source": source, "sentiment": sentiment})
        return mid
    except Exception as e:
        _log("record_market_analysis:", str(e)[:200])
        return None


def get_market_analysis(postcode_district, category=None, *, fresh_only=True):
    """The most recent market read for a district (optionally a category), as a dict with
    'payload' and 'lines' re-parsed. fresh_only drops records past their TTL. None if none."""
    try:
        sql = "SELECT * FROM market_analysis WHERE postcode_district=?"
        args = [postcode_district]
        if category:
            sql += " AND category=?"
            args.append(category)
        sql += " ORDER BY fetched_at DESC LIMIT 1"
        with _conn() as c:
            row = c.execute(sql, args).fetchone()
        if not row:
            return None
        if (fresh_only and row["ttl"] is not None
                and (time.time() - row["fetched_at"]) > row["ttl"]):
            return None
        out = dict(row)
        out["payload"] = json.loads(out["payload_json"]) if out.get("payload_json") else None
        out["lines"] = json.loads(out["lines_json"]) if out.get("lines_json") else None
        out["query"] = json.loads(out["query"]) if out.get("query") else None
        return out
    except Exception as e:
        _log("get_market_analysis:", str(e)[:200])
        return None


# ------------------------------------------------------------------ events (audit)
def log_event(kind, *, token=None, detail=None):
    """Append a categorised audit row. Best-effort and SILENT on failure - the audit log
    must never itself break the thing it is auditing. Returns the event id or None."""
    try:
        with _conn() as c:
            cur = c.execute(
                "INSERT INTO events (kind, token, detail_json, created_at) VALUES (?,?,?,?)",
                (kind, token, _json(detail or {}), time.time()))
            return cur.lastrowid
    except Exception:
        return None


def recent_events(limit=50, kind=None):
    """The latest audit rows (newest first), as dicts. For the ops view + tests."""
    try:
        sql = "SELECT * FROM events"
        args = []
        if kind:
            sql += " WHERE kind=?"
            args.append(kind)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(int(limit))
        with _conn() as c:
            rows = c.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        _log("recent_events:", str(e)[:200])
        return []


# ------------------------------------------------------------------ blog posts
def record_blog_post(slug, *, city_slug, district, series=None, title=None,
                     description=None, headline_price=None, model=None, html=None,
                     generated_at=None):
    """Upsert one published district report. The slug is the stable primary key, so
    republishing the same district (the rotation refresh) updates the row in place and
    keeps created_at while bumping updated_at. Stores the full model JSON (for rebuilds
    and training) and the rendered HTML (so the server can serve it). Returns the slug
    or None. Best-effort, never raises into the pipeline."""
    try:
        now = time.time()
        with _conn() as c:
            existing = c.execute(
                "SELECT created_at FROM blog_posts WHERE slug=?", (slug,)).fetchone()
            created = existing["created_at"] if existing else now
            c.execute(
                """INSERT INTO blog_posts
                   (slug, city_slug, district, series, title, description, headline_price,
                    model_json, html, generated_at, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(slug) DO UPDATE SET
                     city_slug=excluded.city_slug, district=excluded.district,
                     series=excluded.series, title=excluded.title,
                     description=excluded.description, headline_price=excluded.headline_price,
                     model_json=excluded.model_json, html=excluded.html,
                     generated_at=excluded.generated_at, updated_at=excluded.updated_at""",
                (slug, city_slug, district, series, title, description, headline_price,
                 _json(model) if model is not None else None, html, generated_at,
                 created, now))
            c.commit()
        log_event("blog_published", token=slug,
                  detail={"city": city_slug, "district": district})
        return slug
    except Exception as e:
        _log("record_blog_post:", str(e)[:200])
        return None


def get_blog_post(slug, *, with_html=True, with_model=False):
    """One published post by slug, as a dict, or None. HTML/model are heavy, so they are
    opt-in for callers that only need metadata (the hub/index builders)."""
    try:
        with _conn() as c:
            r = c.execute("SELECT * FROM blog_posts WHERE slug=?", (slug,)).fetchone()
        if not r:
            return None
        d = dict(r)
        if not with_html:
            d.pop("html", None)
        if with_model:
            d["model"] = json.loads(d["model_json"]) if d.get("model_json") else None
        d.pop("model_json", None)
        return d
    except Exception as e:
        _log("get_blog_post:", str(e)[:200])
        return None


def published_districts(city_slug):
    """The set of district outcodes already published for a city - what the rotation reads
    to pick the next unpublished district. Returns a list (possibly empty)."""
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT district FROM blog_posts WHERE city_slug=?", (city_slug,)).fetchall()
        return [r["district"] for r in rows]
    except Exception as e:
        _log("published_districts:", str(e)[:200])
        return []


def stalest_post(city_slug):
    """The oldest-updated post for a city (for the refresh phase once a city is fully
    covered). Returns a metadata dict or None."""
    try:
        with _conn() as c:
            r = c.execute(
                "SELECT slug, district, updated_at FROM blog_posts WHERE city_slug=? "
                "ORDER BY updated_at ASC LIMIT 1", (city_slug,)).fetchone()
        return dict(r) if r else None
    except Exception as e:
        _log("stalest_post:", str(e)[:200])
        return None


def list_blog_posts(city_slug=None, limit=500):
    """Post metadata (no HTML body), newest-updated first, optionally one city. Feeds the
    hub pages, the index, the sitemap and the RSS feed."""
    try:
        sql = ("SELECT slug, city_slug, district, series, title, description, "
               "headline_price, generated_at, created_at, updated_at FROM blog_posts")
        args = []
        if city_slug:
            sql += " WHERE city_slug=?"
            args.append(city_slug)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        args.append(int(limit))
        with _conn() as c:
            rows = c.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        _log("list_blog_posts:", str(e)[:200])
        return []


def delete_blog_post(slug):
    """Unpublish one district report by slug (e.g. a page that no longer meets the publish
    gate because its district has no transaction data). Removes the row so it drops out of
    the hubs, index, sitemap and RSS on the next rebuild. Returns True if a row was deleted.
    Best-effort, never raises into the pipeline. The on-disk static file is removed by the
    caller (the DB does not own the filesystem)."""
    try:
        with _conn() as c:
            cur = c.execute("DELETE FROM blog_posts WHERE slug=?", (slug,))
            c.commit()
            deleted = cur.rowcount > 0
        if deleted:
            log_event("blog_unpublished", token=slug)
        return deleted
    except Exception as e:
        _log("delete_blog_post:", str(e)[:200])
        return False


# ------------------------------------------------------------------ leads (blog PDF gate)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(email):
    """True iff `email` looks like a deliverable address. Deliberately permissive - we
    gate the free PDF, we do not police the inbox."""
    return bool(email and _EMAIL_RE.match(email.strip()))


_PERSONAS = ("vendor", "buyer", "agent", "other")


def clean_persona(persona):
    """Normalise a self-declared persona to one of vendor|buyer|agent|other, or None. This is
    the reader telling us why they want the report - it steers the follow-up emails and the
    Telegram offer, never the figures (the report carries no valuation)."""
    p = (persona or "").strip().lower()
    return p if p in _PERSONAS else None


def record_lead(email, slug, *, name=None, persona=None, source="blog_pdf"):
    """Capture a lead in exchange for a free blog-report PDF and mint a download token.

    This is the lead-capture gate: the reader hands over their details to download a
    report we already publish for free. `persona` is who they say they are (vendor|buyer|
    agent|other), captured at PDF request so the follow-up and the Telegram offer can speak
    to them. Returns the download token (used by /dl/<token>), or None on failure / invalid
    email. Best-effort, never raises into the request path."""
    try:
        email = (email or "").strip()
        if not valid_email(email):
            return None
        persona = clean_persona(persona)
        tok = _new_token()
        with _conn() as c:
            c.execute(
                "INSERT INTO leads (token, email, name, slug, persona, source, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (tok, email, (name or "").strip() or None, slug, persona, source, time.time()))
        log_event("lead_captured", token=tok,
                  detail={"email": email, "slug": slug, "persona": persona, "source": source})
        return tok
    except Exception as e:
        _log("record_lead:", str(e)[:200])
        return None


def resolve_download(token):
    """Resolve a /dl/<token> download for serving. Returns a dict:
        {ok, reason, slug, email, persona}
    ok is False with reason 'unknown' when the token is not a captured lead. The token
    does not expire: the reader already gave their details, so re-downloading is allowed."""
    try:
        with _conn() as c:
            row = c.execute("SELECT slug, email, persona FROM leads WHERE token=?",
                            (token,)).fetchone()
        if not row:
            return {"ok": False, "reason": "unknown"}
        log_event("lead_download", token=token,
                  detail={"slug": row["slug"], "email": row["email"]})
        return {"ok": True, "slug": row["slug"], "email": row["email"],
                "persona": row["persona"]}
    except Exception as e:
        _log("resolve_download:", str(e)[:200])
        return {"ok": False, "reason": "error"}


def lead_persona(token):
    """The persona a lead declared at PDF request (vendor|buyer|agent|other), or None. Read by
    the bot when a reader arrives from a follow-up email, so the Pro offer can speak to them."""
    try:
        with _conn() as c:
            row = c.execute("SELECT persona FROM leads WHERE token=?", (token,)).fetchone()
        return (row["persona"] if row else None)
    except Exception as e:
        _log("lead_persona:", str(e)[:200])
        return None


def recent_leads(limit=200, slug=None):
    """The latest captured leads (newest first), as dicts. For the ops view + export."""
    try:
        sql = "SELECT * FROM leads"
        args = []
        if slug:
            sql += " WHERE slug=?"
            args.append(slug)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(int(limit))
        with _conn() as c:
            rows = c.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        _log("recent_leads:", str(e)[:200])
        return []


# ------------------------------------------------------------ email sequence
# The follow-up drip behind the blog-PDF lead gate. One row per scheduled email:
# WHICH step, for WHICH lead, due WHEN. Bodies are NOT stored - they render from
# templates + the live blog model at send time, so a follow-up can never go stale
# or drift from the report it points at. The runner (email_funnel.run_due) pulls
# due rows, sends, and marks them. Unsubscribing cancels every pending row for an
# address. Best-effort throughout: never raises into the request path.
def has_queue(lead_token):
    """True iff we have already queued a sequence for this lead (idempotency guard, so a
    re-submitted gate form does not double-send)."""
    try:
        with _conn() as c:
            row = c.execute("SELECT 1 FROM email_queue WHERE lead_token=? LIMIT 1",
                            (lead_token,)).fetchone()
        return bool(row)
    except Exception as e:
        _log("has_queue:", str(e)[:200])
        return False


def enqueue_email(lead_token, email, slug, step, kind, send_after):
    """Schedule one follow-up. Returns the row id, or None. send_after is a unix ts."""
    try:
        with _conn() as c:
            cur = c.execute(
                "INSERT INTO email_queue (lead_token, email, slug, step, kind, send_after, "
                "status, created_at) VALUES (?,?,?,?,?,?,'pending',?)",
                (lead_token, (email or "").strip(), slug, int(step), kind,
                 float(send_after), time.time()))
            return cur.lastrowid
    except Exception as e:
        _log("enqueue_email:", str(e)[:200])
        return None


def due_emails(now=None, limit=200):
    """Pending rows whose send_after has passed, oldest first. The runner's work list."""
    try:
        now = time.time() if now is None else now
        with _conn() as c:
            rows = c.execute(
                "SELECT * FROM email_queue WHERE status='pending' AND send_after<=? "
                "ORDER BY send_after ASC LIMIT ?", (float(now), int(limit))).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        _log("due_emails:", str(e)[:200])
        return []


def mark_email(row_id, status, *, sent_at=None):
    """Move a queued email to 'sent' / 'failed' / 'cancelled'. Stamps sent_at on success."""
    try:
        with _conn() as c:
            c.execute("UPDATE email_queue SET status=?, sent_at=? WHERE id=?",
                      (status, (time.time() if (sent_at is None and status == "sent")
                                else sent_at), int(row_id)))
        return True
    except Exception as e:
        _log("mark_email:", str(e)[:200])
        return False


def cancel_sequence(lead_token):
    """Unsubscribe: cancel every PENDING email to the address behind this lead token (not
    just this lead's rows - the person, however they reached us). Returns {ok,email,n}."""
    try:
        with _conn() as c:
            row = c.execute("SELECT email FROM leads WHERE token=?", (lead_token,)).fetchone()
            if not row:
                return {"ok": False, "reason": "unknown", "n": 0}
            email = row["email"]
            cur = c.execute("UPDATE email_queue SET status='cancelled' "
                            "WHERE email=? AND status='pending'", (email,))
            n = cur.rowcount
        log_event("email_unsubscribe", token=lead_token, detail={"email": email, "cancelled": n})
        return {"ok": True, "email": email, "n": n}
    except Exception as e:
        _log("cancel_sequence:", str(e)[:200])
        return {"ok": False, "reason": "error", "n": 0}


# ----------------------------------------------- Telegram re-engagement queue
def has_tg_queue(chat_id, token):
    """True iff a nudge sequence is already queued for this chat + appraisal (idempotency)."""
    try:
        with _conn() as c:
            row = c.execute("SELECT 1 FROM tg_queue WHERE chat_id=? AND token=? LIMIT 1",
                            (str(chat_id), token)).fetchone()
        return bool(row)
    except Exception as e:
        _log("has_tg_queue:", str(e)[:200]); return False


def has_pending_tg(chat_id, token):
    """True iff a PENDING nudge is already queued for this chat+token. Unlike has_tg_queue (which
    matches any status), this lets a recurring nudge (e.g. an area refresh) re-enqueue once a prior
    one has actually sent - it only blocks stacking duplicates while one still waits."""
    try:
        with _conn() as c:
            row = c.execute("SELECT 1 FROM tg_queue WHERE chat_id=? AND token=? AND status='pending' "
                            "LIMIT 1", (str(chat_id), token)).fetchone()
        return bool(row)
    except Exception as e:
        _log("has_pending_tg:", str(e)[:200]); return False


def last_area_nudge_at(chat_id, token):
    """sent_at of the most recent area-refresh nudge SENT to this chat for this area, or None - so
    the pinger only re-nudges when the area's evidence is newer than the last nudge."""
    try:
        with _conn() as c:
            row = c.execute("SELECT sent_at FROM tg_queue WHERE chat_id=? AND token=? "
                            "AND kind='nudge_area_refresh' AND status='sent' "
                            "ORDER BY sent_at DESC LIMIT 1", (str(chat_id), token)).fetchone()
        return row["sent_at"] if (row and row["sent_at"] is not None) else None
    except Exception as e:
        _log("last_area_nudge_at:", str(e)[:200]); return None


def enqueue_tg(chat_id, token, audience, step, kind, send_after):
    """Schedule one Telegram nudge. Returns the row id, or None. send_after is a unix ts."""
    try:
        with _conn() as c:
            cur = c.execute(
                "INSERT INTO tg_queue (chat_id, token, audience, step, kind, send_after, "
                "status, created_at) VALUES (?,?,?,?,?,?,'pending',?)",
                (str(chat_id), token, audience, int(step), kind, float(send_after), time.time()))
            return cur.lastrowid
    except Exception as e:
        _log("enqueue_tg:", str(e)[:200]); return None


def due_tg(now=None, limit=200):
    """Pending nudges whose send_after has passed, oldest first - the runner's work list."""
    try:
        now = time.time() if now is None else now
        with _conn() as c:
            rows = c.execute(
                "SELECT * FROM tg_queue WHERE status='pending' AND send_after<=? "
                "ORDER BY send_after ASC LIMIT ?", (float(now), int(limit))).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        _log("due_tg:", str(e)[:200]); return []


def mark_tg(row_id, status, *, sent_at=None):
    """Move a queued nudge to 'sent' / 'failed' / 'cancelled'. Stamps sent_at on success."""
    try:
        with _conn() as c:
            c.execute("UPDATE tg_queue SET status=?, sent_at=? WHERE id=?",
                      (status, (time.time() if (sent_at is None and status == "sent")
                                else sent_at), int(row_id)))
        return True
    except Exception as e:
        _log("mark_tg:", str(e)[:200]); return False


def last_tg_sent_at(chat_id):
    """Unix ts of the most recent nudge actually sent to this chat (for frequency capping),
    or None if we have never pinged them."""
    try:
        with _conn() as c:
            row = c.execute("SELECT MAX(sent_at) AS t FROM tg_queue WHERE chat_id=? "
                            "AND status='sent'", (str(chat_id),)).fetchone()
        return row["t"] if row and row["t"] else None
    except Exception as e:
        _log("last_tg_sent_at:", str(e)[:200]); return None


def tg_optout(chat_id):
    """Permanently stop nudging this chat (a /stop): record the opt-out and cancel every
    pending nudge to them. Returns {ok, cancelled}."""
    try:
        with _conn() as c:
            c.execute("INSERT OR IGNORE INTO tg_optout (chat_id, created_at) VALUES (?,?)",
                      (str(chat_id), time.time()))
            cur = c.execute("UPDATE tg_queue SET status='cancelled' WHERE chat_id=? "
                            "AND status='pending'", (str(chat_id),))
            n = cur.rowcount
        log_event("tg_optout", token=str(chat_id), detail={"cancelled": n})
        return {"ok": True, "cancelled": n}
    except Exception as e:
        _log("tg_optout:", str(e)[:200]); return {"ok": False, "cancelled": 0}


def is_tg_optout(chat_id):
    """True iff this chat has opted out of nudges. Checked before every send."""
    try:
        with _conn() as c:
            row = c.execute("SELECT 1 FROM tg_optout WHERE chat_id=? LIMIT 1",
                            (str(chat_id),)).fetchone()
        return bool(row)
    except Exception as e:
        _log("is_tg_optout:", str(e)[:200]); return False


# ------------------------------------------------------------------ user directory
def record_user(uid, username=None, first_name=None, last_name=None):
    """Upsert a bot user on interaction: insert on first sight, else refresh name/handle and
    bump last_seen + msg_count. Best-effort, never raises into the request path."""
    if uid in (None, ""):
        return False
    try:
        now = time.time()
        with _conn() as c:
            exists = c.execute("SELECT 1 FROM users WHERE uid=?", (str(uid),)).fetchone()
            if exists:
                c.execute("UPDATE users SET username=COALESCE(?,username), "
                          "first_name=COALESCE(?,first_name), last_name=COALESCE(?,last_name), "
                          "last_seen=?, msg_count=msg_count+1 WHERE uid=?",
                          (username, first_name, last_name, now, str(uid)))
            else:
                c.execute("INSERT INTO users (uid, username, first_name, last_name, first_seen, "
                          "last_seen, msg_count) VALUES (?,?,?,?,?,?,1)",
                          (str(uid), username, first_name, last_name, now, now))
        return True
    except Exception as e:
        _log("record_user:", str(e)[:200]); return False


def list_users(limit=10000):
    """All known bot users, most-recently-seen first. The export/work list."""
    try:
        with _conn() as c:
            rows = c.execute("SELECT uid, username, first_name, last_name, first_seen, last_seen, "
                             "msg_count FROM users ORDER BY last_seen DESC LIMIT ?",
                             (int(limit),)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        _log("list_users:", str(e)[:200]); return []


def users_count():
    """Total distinct bot users we have on record."""
    try:
        with _conn() as c:
            return c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    except Exception as e:
        _log("users_count:", str(e)[:200]); return 0


# ------------------------------------------------------------------ purchases (catalogue products)
def record_purchase(uid, pid, address, title, blurb, profile, html_body):
    """Store a delivered catalogue product document and return its share_token.
    The html_body is served permanently at /p/<share_token>. Returns the token or None."""
    try:
        uid = _chat_id_str(uid) or ""
        tok = _new_token()
        with _conn() as c:
            c.execute(
                "INSERT INTO purchases (share_token, uid, pid, address, title, blurb, profile, "
                "html_body, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (tok, uid, pid, address, title, blurb, profile, html_body, time.time()))
        log_event("purchase_delivered", token=tok,
                  detail={"uid": uid, "pid": pid, "address": address})
        return tok
    except Exception as e:
        _log("record_purchase:", str(e)[:200])
        return None


def list_purchases(uid, limit=50):
    """This user's purchased documents, newest first, without the html_body (the Library card
    just needs title/address/date/url). Returns [] on failure or unknown user."""
    uid = _chat_id_str(uid)
    if not uid:
        return []
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT share_token, pid, address, title, blurb, profile, created_at "
                "FROM purchases WHERE uid=? ORDER BY created_at DESC LIMIT ?",
                (uid, int(limit))).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        _log("list_purchases:", str(e)[:200])
        return []


def get_purchase(share_token):
    """Fetch a purchase document by its share_token for serving at /p/<token>.
    Returns a dict with html_body, or None."""
    if not share_token:
        return None
    try:
        with _conn() as c:
            row = c.execute("SELECT * FROM purchases WHERE share_token=?",
                            (share_token,)).fetchone()
        return dict(row) if row else None
    except Exception as e:
        _log("get_purchase:", str(e)[:200])
        return None


# ----------------------------------------------------------- research notebooks
def get_notebook_id(appraisal_token):
    """The Open Notebook notebook_id for a saved property, or None."""
    try:
        with _conn() as c:
            row = c.execute("SELECT notebook_id FROM property_notebooks WHERE appraisal_token=?",
                            (appraisal_token,)).fetchone()
        return row["notebook_id"] if row else None
    except Exception as e:
        _log("get_notebook_id:", str(e)[:200])
        return None


def set_notebook_id(appraisal_token, notebook_id):
    """Store the Open Notebook notebook_id for a property (upsert). Returns True iff stored."""
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO property_notebooks (appraisal_token, notebook_id, created_at) "
                "VALUES (?,?,?) ON CONFLICT(appraisal_token) DO UPDATE SET notebook_id=excluded.notebook_id",
                (appraisal_token, notebook_id, time.time()))
        return True
    except Exception as e:
        _log("set_notebook_id:", str(e)[:200])
        return False


def get_notebook_session(appraisal_token):
    """The persisted chat session_id for a property's research notebook, or None."""
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT chat_session_id FROM property_notebooks WHERE appraisal_token=?",
                (appraisal_token,)).fetchone()
        return row["chat_session_id"] if row else None
    except Exception as e:
        _log("get_notebook_session:", str(e)[:200])
        return None


def set_notebook_session(appraisal_token, session_id):
    """Persist the current chat session_id for a property notebook."""
    try:
        with _conn() as c:
            c.execute("UPDATE property_notebooks SET chat_session_id=? WHERE appraisal_token=?",
                      (session_id, appraisal_token))
        return True
    except Exception as e:
        _log("set_notebook_session:", str(e)[:200])
        return False


# ------------------------------------------------------------------ selftest
def _selftest():
    """Round-trip every table in a throwaway DB. No network, no infra."""
    global DB_PATH, _INITED
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    DB_PATH, _INITED = path, False
    try:
        summary = {"address": "1 Test Street, London EC1V 1AE", "audience": "agent",
                   "low": 900000, "high": 1080000, "central": 915000, "guide": 800000,
                   "investment": False}
        tok = record_appraisal(summary, finish="average", source="selftest", tier="prophet")
        assert tok, "appraisal not stored"
        got = get_appraisal(tok)
        assert got and got["central"] == 915000, "appraisal readback failed"
        assert got["postcode_district"] == "EC1V", f"district wrong: {got['postcode_district']}"
        assert got["summary"]["guide"] == 800000, "summary json not round-tripped"

        did = record_deliverable(tok, "html", path="/tmp/x.html", body="<html>hi</html>")
        assert did, "deliverable not stored"
        assert get_deliverable(tok, "html")["body"] == "<html>hi</html>"

        link = mint_token(tok, ttl_days=90)
        res = resolve_token(link)
        assert res["ok"] and res["html"] == "<html>hi</html>", "link did not resolve to html"
        assert res["address"] == summary["address"]
        assert share_token_for(tok) == link, "share_token_for did not return the live link"

        # owner tagging + the Pro workspace "my properties" list
        assert tag_appraisal(tok, "777"), "tag_appraisal failed"
        mine = list_appraisals("777")
        assert mine and mine[0]["token"] == tok, "list_appraisals did not return the tagged row"
        assert mine[0]["central"] == 915000 and mine[0]["share_token"] == link
        assert mine[0]["has_html"] is True, "has_html flag wrong"
        assert list_appraisals("nobody") == [], "list_appraisals leaked another user's rows"
        # record_appraisal pulls chat_id straight out of a 'bot:<id>' source tag
        bt = record_appraisal({"address": "2 Owner Road, London EC1V 1AE", "central": 500000},
                              source="bot:424242")
        assert get_appraisal(bt)["chat_id"] == "424242", "chat_id not parsed from source"
        # backfill claims old rows that predate the column (NULL chat_id + bot: source)
        with _conn() as c:
            c.execute("UPDATE appraisals SET chat_id=NULL WHERE token=?", (bt,))
        assert backfill_chat_id_from_source() >= 1
        assert get_appraisal(bt)["chat_id"] == "424242", "backfill did not populate chat_id"

        assert resolve_token("nope")["reason"] == "unknown"
        expired = mint_token(tok, ttl_days=None)
        with _conn() as c:  # force-expire it
            c.execute("UPDATE tokens SET expires_at=? WHERE token=?", (1.0, expired))
        assert resolve_token(expired)["reason"] == "expired"
        assert revoke_token(link) and resolve_token(link)["reason"] == "revoked"

        mid = record_market_analysis("EC1V", "sentiment", source="hit_scan",
                                     query={"q": "ec1"}, payload={"raw": 1},
                                     lines=["demand firm"], sentiment="warm", ttl_hours=24)
        assert mid, "market row not stored"
        ma = get_market_analysis("EC1V", "sentiment")
        assert ma and ma["lines"] == ["demand firm"] and ma["sentiment"] == "warm"
        assert get_market_analysis("EC1V", "sentiment", fresh_only=True) is not None
        record_market_analysis("EC1V", "stale", source="x", ttl_hours=0.0)
        # ttl 0 means never-fresh; fresh_only should drop it
        # (0 ttl stored as 0 seconds -> elapsed>0 always, so dropped)
        # blog posts: upsert keeps created_at, bumps updated_at; rotation reads districts
        s1 = record_blog_post("london-se15", city_slug="london", district="SE15",
                              series="The London Daily", title="SE15 report",
                              description="median 480k", headline_price=480000,
                              model={"district": "SE15"}, html="<html>se15</html>",
                              generated_at="2026-06-11")
        assert s1 == "london-se15", "blog post not stored"
        bp = get_blog_post("london-se15", with_model=True)
        assert bp and bp["html"] == "<html>se15</html>" and bp["model"]["district"] == "SE15"
        c0 = get_blog_post("london-se15")["created_at"]
        record_blog_post("london-se15", city_slug="london", district="SE15",
                         html="<html>se15 v2</html>", generated_at="2026-06-12")
        bp2 = get_blog_post("london-se15")
        assert bp2["html"] == "<html>se15 v2</html>" and bp2["created_at"] == c0, \
            "upsert should refresh in place and keep created_at"
        record_blog_post("london-ec1", city_slug="london", district="EC1",
                         html="<html>ec1</html>", generated_at="2026-06-11")
        assert set(published_districts("london")) == {"SE15", "EC1"}, "rotation districts wrong"
        assert stalest_post("london")["district"] == "SE15", "stalest should be SE15 (older)"
        assert len(list_blog_posts("london")) == 2
        assert "html" not in list_blog_posts("london")[0], "list must omit heavy html"

        # leads: the blog-PDF gate. valid email -> token -> resolves back to the slug.
        assert valid_email("a@b.co") and not valid_email("nope")
        ltok = record_lead("buyer@example.com", "london-se15", name="Sam", persona="buyer")
        assert ltok, "lead not stored"
        assert record_lead("not-an-email", "london-se15") is None, "bad email must be rejected"
        dl = resolve_download(ltok)
        assert dl["ok"] and dl["slug"] == "london-se15" and dl["email"] == "buyer@example.com"
        assert dl["persona"] == "buyer" and lead_persona(ltok) == "buyer", "persona must round-trip"
        assert clean_persona("VENDOR ") == "vendor" and clean_persona("junk") is None, "persona clean"
        assert record_lead("v@example.com", "london-se15", persona="junk") and \
            lead_persona(record_lead("v2@example.com", "london-se15", persona="agent")) == "agent"
        assert resolve_download("nope")["reason"] == "unknown"
        assert len(recent_leads(slug="london-se15")) >= 1

        # email sequence: enqueue due + future, the runner sees only the due one, then
        # unsubscribing this lead's address cancels the still-pending future row.
        assert not has_queue(ltok), "no queue yet"
        e0 = enqueue_email(ltok, "buyer@example.com", "london-se15", 0, "deliver", time.time() - 1)
        e1 = enqueue_email(ltok, "buyer@example.com", "london-se15", 1, "nurture1", time.time() + 9e9)
        assert e0 and e1 and has_queue(ltok), "enqueue / has_queue failed"
        due = due_emails()
        assert len(due) == 1 and due[0]["step"] == 0, f"only step 0 is due: {due}"
        assert mark_email(e0, "sent"), "mark_email failed"
        assert len(due_emails()) == 0, "sent row should not be due"
        canc = cancel_sequence(ltok)
        assert canc["ok"] and canc["email"] == "buyer@example.com" and canc["n"] == 1, canc
        with _conn() as c:
            st = c.execute("SELECT status FROM email_queue WHERE id=?", (e1,)).fetchone()["status"]
        assert st == "cancelled", "future row should be cancelled after unsubscribe"

        evs = recent_events(limit=100)
        kinds = {e["kind"] for e in evs}
        assert {"valuation_requested", "deliverable_built", "link_served",
                "link_revoked", "market_scan", "blog_published",
                "lead_captured", "lead_download"} <= kinds, \
            f"missing audit kinds: {kinds}"
        print("store selftest OK -", path)
        print("  appraisal token:", tok)
        print("  audit kinds    :", sorted(kinds))
    finally:
        try:
            os.remove(path)
            for ext in ("-wal", "-shm"):
                if os.path.exists(path + ext):
                    os.remove(path + ext)
        except Exception:
            pass


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        _selftest()
    else:
        print(__doc__)
