#!/usr/bin/env python3
"""test_email_funnel.py - offline, end-to-end proof of the blog-PDF email funnel as the
server actually drives it. No socket, no network, nothing sent: EMAIL_DRY_RUN forces every
message to a .eml in a throwaway outbox, and the DB is a throwaway file.

Covers the seam the unit selftests do not:
  - POST /api/lead through the REAL server handler -> lead persisted (with persona),
    the PDF emailed (step 0 .eml with the attachment), the drip queued.
  - GET  /u/<token> and one-click POST /u/<token> cancel the whole sequence.
  - persona (vendor|buyer|agent|other) is captured at PDF request and round-trips.

    python test_email_funnel.py
"""
import io, os, sys, json, glob, tempfile

# force dry-run + throwaway sinks BEFORE importing the app
os.environ["EMAIL_DRY_RUN"] = "1"
_OUTBOX = tempfile.mkdtemp(prefix="outbox-")
os.environ["EMAIL_OUTBOX"] = _OUTBOX
# fast schedule so we do not depend on real day-delays in any later flush
os.environ.setdefault("FUNNEL_D1_DAYS", "2")

import store
fd, _DB = tempfile.mkstemp(suffix=".db"); os.close(fd); os.remove(_DB)
store.DB_PATH, store._INITED = _DB, False

import brand
import server
import email_funnel


class FakeH(server.H):
    """A server.H with no socket: we set the request fields by hand and capture _send()."""
    def __init__(self, method, path, body=b""):
        self.command = method
        self.path = path
        self.headers = {"Content-Length": str(len(body))}
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.sent = []  # list of (code, body, ctype)

    def _send(self, code, body, ctype="application/json"):
        self.sent.append((code, body, ctype))
        return None


def _seed_post():
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


def _post_lead(persona):
    body = json.dumps({"email": "buyer@example.com", "name": "Sam",
                       "persona": persona, "slug": "london-se15"}).encode()
    h = FakeH("POST", "/api/lead", body)
    h.do_POST()
    assert h.sent, "no response"
    code, payload, _ = h.sent[-1]
    return code, json.loads(payload)


def main():
    _seed_post()

    # 1) lead capture through the real POST handler: 200 + /dl url, PDF emailed, drip queued
    n_before = len(glob.glob(os.path.join(_OUTBOX, "*.eml")))
    code, j = _post_lead("buyer")
    assert code == 200 and j.get("ok") and j.get("url", "").startswith("/dl/"), (code, j)
    tok = j["url"].split("/dl/")[1]

    # persona persisted on the lead
    assert store.lead_persona(tok) == "buyer", "persona not captured"
    assert store.resolve_download(tok)["persona"] == "buyer"

    # the whole sequence is queued, and step 0 emailed the PDF right now
    assert store.has_queue(tok), "sequence not queued"
    emls = sorted(glob.glob(os.path.join(_OUTBOX, "*.eml")))
    assert len(emls) == n_before + 1, f"expected one new .eml, got {len(emls) - n_before}"
    raw = open(emls[-1], "rb").read()
    assert b"market report (free PDF inside)" in raw, "deliver subject missing"
    assert b"honestly-SE15-market-report.pdf" in raw and b"application/pdf" in raw, "PDF not attached"
    assert b"/u/" + tok.encode() in raw, "unsubscribe link missing"

    # 2) GET /u/<token> shows the branded page AND cancels the rest of the drip
    g = FakeH("GET", "/u/" + tok)
    g.do_GET()
    gc, gbody, gctype = g.sent[-1]
    assert gc == 200 and "text/html" in gctype, (gc, gctype)
    assert "unsubscribed" in gbody.lower(), "unsub page wording"

    # flushing far in the future now sends NOTHING (sequence cancelled)
    summ = email_funnel.run_due(now=9_999_999_999.0)
    assert summ["sent"] == 0, f"cancelled drip must send nothing: {summ}"

    # 3) one-click POST /u/<token> is a quiet 200 even with no live sequence
    p = FakeH("POST", "/u/" + tok, b"List-Unsubscribe=One-Click")
    p.do_POST()
    pc, pbody, _ = p.sent[-1]
    assert pc == 200 and json.loads(pbody).get("ok"), (pc, pbody)

    # 4) an unknown-persona lead still downloads, but stores NULL persona (tolerant, not blocked)
    code2, j2 = _post_lead("junk")
    assert code2 == 200 and j2.get("url"), (code2, j2)
    tok2 = j2["url"].split("/dl/")[1]
    assert store.lead_persona(tok2) is None, "invalid persona should store NULL, not block"

    # 5) each persona value is accepted and distinct
    for who in ("vendor", "agent", "other"):
        c, jj = _post_lead(who)
        assert c == 200, (who, c)
        assert store.lead_persona(jj["url"].split("/dl/")[1]) == who, who

    print("test_email_funnel OK ->", _OUTBOX,
          "| lead+PDF emailed, persona captured, unsubscribe (GET+1-click) honoured")


if __name__ == "__main__":
    main()
