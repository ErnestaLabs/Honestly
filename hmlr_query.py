#!/usr/bin/env python3
"""hmlr_query.py - tiny read-only HTTP query service over the locally-mirrored HM Land
Registry Price Paid register (built + kept current by hmlr_ingest.py).

Runs on the VPS, bound to localhost only; nginx proxies /hmlr/ to it over TLS. The blog
pipeline on the laptop reaches it via HMLR_QUERY_URL so the laptop NEVER downloads the
5.47 GB dataset - it just asks the VPS for an outcode's rows. Data is open (OGL v3.0); a
shared token (HMLR_QUERY_TOKEN, read from /opt/honestly/.hmlr_query_token, never .env)
gates it only to keep casual scrapers off the small box.

Endpoints:
  GET /sold?outcode=LS2&since=2016-06-12&k=<token>
      -> {"ok": true, "outcode": "LS2",
          "rows": [{"tuid","price","date","postcode","ptype"}...], "n": N}
  GET /health?k=<token>   -> {"ok": true, "rows": <count>, "max_date": "..."}
"""
import json, os, re, sqlite3, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

DB_PATH    = os.environ.get("HMLR_DB_PATH", "/opt/honestly/data/hmlr_ppd.db")
TOKEN_FILE = os.environ.get("HMLR_QUERY_TOKEN_FILE", "/opt/honestly/.hmlr_query_token")
BIND       = os.environ.get("HMLR_QUERY_BIND", "127.0.0.1")
PORT       = int(os.environ.get("HMLR_QUERY_PORT", "8091"))

_OUTCODE = re.compile(r"^[A-Z]{1,2}[0-9][A-Z0-9]?$")     # AA9A-style outcode, validated
_DATE    = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _token():
    try:
        return open(TOKEN_FILE, encoding="utf-8").read().strip()
    except OSError:
        return os.environ.get("HMLR_QUERY_TOKEN", "")


def _ro_conn():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)


class Handler(BaseHTTPRequestHandler):
    server_version = "hmlr-query/1.0"

    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):                # quiet; systemd captures what we choose to print
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        tok = _token()
        if not tok or (q.get("k", [""])[0] != tok):
            return self._send(403, {"ok": False, "reason": "forbidden"})

        if u.path.rstrip("/") == "/hmlr/health" or u.path.rstrip("/") == "/health":
            try:
                cx = _ro_conn()
                (n,) = cx.execute("SELECT COUNT(*) FROM ppd").fetchone()
                (mx,) = cx.execute("SELECT MAX(deed_date) FROM ppd").fetchone()
                cx.close()
                return self._send(200, {"ok": True, "rows": n, "max_date": mx})
            except sqlite3.Error as e:
                return self._send(503, {"ok": False, "reason": str(e)[:120]})

        if u.path.rstrip("/").endswith("/sold") or u.path.rstrip("/") == "/sold":
            outcode = (q.get("outcode", [""])[0] or "").strip().upper()
            # Exact full postcode filter (the valuation hot path) takes precedence over the
            # outcode scan (the blog's area sweep). Normalise to the stored form: upper-case,
            # single internal space before the 3-char inward code.
            postcode = re.sub(r"\s+", "", (q.get("postcode", [""])[0] or "").upper())
            if len(postcode) > 3:
                postcode = postcode[:-3] + " " + postcode[-3:]
            since = (q.get("since", [""])[0] or "").strip()
            try:
                limit = max(1, min(500, int(q.get("limit", ["100"])[0])))
            except (TypeError, ValueError):
                limit = 100
            if not postcode and not _OUTCODE.match(outcode):
                return self._send(400, {"ok": False, "reason": "bad outcode/postcode"})
            if since and not _DATE.match(since):
                return self._send(400, {"ok": False, "reason": "bad since"})
            # tuid + postcode travel with every row so the blog can build the official
            # HMLR per-transaction verification link (.../ppi/transaction/<tuid>/current)
            # and name the postcode; the address parts (paon/saon/street/town) let the
            # valuation show a real comp address, identical to the SPARQL path.
            sql = ("SELECT tuid, price, deed_date, postcode, ptype, paon, saon, street, town "
                   "FROM ppd WHERE ptype IN ('F','T','S','D') AND ")
            if postcode:
                sql += "postcode=?"; args = [postcode]
            else:
                sql += "outcode=?"; args = [outcode]
            if since:
                sql += " AND deed_date>=?"
                args.append(since)
            sql += " ORDER BY deed_date DESC LIMIT ?"
            args.append(limit)
            try:
                cx = _ro_conn()
                recs = cx.execute(sql, args).fetchall()
                cx.close()
            except sqlite3.Error as e:
                return self._send(503, {"ok": False, "reason": str(e)[:120]})
            rows = [{"tuid": u, "price": p, "date": d, "postcode": pc, "ptype": t,
                     "paon": pa, "saon": sa, "street": st, "town": tn}
                    for (u, p, d, pc, t, pa, sa, st, tn) in recs]
            return self._send(200, {"ok": True, "outcode": outcode, "postcode": postcode,
                                    "n": len(rows), "rows": rows})

        return self._send(404, {"ok": False, "reason": "not found"})


def main():
    srv = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"hmlr_query serving {DB_PATH} on {BIND}:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
