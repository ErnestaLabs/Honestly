#!/usr/bin/env python3
"""HM Land Registry Price Paid Data - full-dataset ingestion daemon.

FREE, Open Government Licence v3.0. England & Wales ONLY (Scotland = Registers of
Scotland; NI = Land & Property Services - neither is in this register).

What it does, forever, on the VPS (never the laptop):
  1. First run: download the complete snapshot (pp-complete.csv, ~5.47 GB, ~30M rows
     since 1995) once, stream-parse it into a local SQLite mirror, build indexes.
  2. Then loop: poll the monthly-update file; when its Last-Modified advances, download
     it and apply adds/changes (record status A/C) and deletes (status D) by TUID.

Stdlib only (urllib, csv, sqlite3) - no pip deps. Tuned for a 1-core / ~3.8 GB box:
streaming parse, batched executemany, journal/synchronous off during bulk load,
indexes built after the load, modest page cache, sort-temp on the big data disk.

Source base (S3 static site, 301-redirects to prod1):
  http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/

CSV layout (no header, 16 columns):
  TUID, Price, Date of Transfer, Postcode, Property Type (D/S/T/F/O), Old/New,
  Duration (F/L), PAON, SAON, Street, Locality, Town/City, District, County,
  PPD Category (A/B), Record Status (A/C/D)
"""
import csv, json, os, sqlite3, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

BASE = "http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com"
COMPLETE_URL = f"{BASE}/pp-complete.csv"
MONTHLY_URL  = f"{BASE}/pp-monthly-update-new-version.csv"

DATA_DIR   = os.environ.get("HMLR_DATA_DIR", "/opt/honestly/data")
DB_PATH    = os.path.join(DATA_DIR, "hmlr_ppd.db")
STATE_PATH = os.path.join(DATA_DIR, "hmlr_state.json")
CSV_TMP    = os.path.join(DATA_DIR, "_pp.csv.part")

POLL_SECONDS = int(os.environ.get("HMLR_POLL_SECONDS", "21600"))   # 6h between monthly polls
BATCH        = int(os.environ.get("HMLR_BATCH", "20000"))
UA           = "honestly-hmlr-ingest/1.0 (+usehonestly.co.uk; OGL v3.0 open data)"

# 16 source columns mapped to our schema; outcode is derived (postcode before the space).
COLS = ("tuid", "price", "deed_date", "postcode", "ptype", "old_new", "duration",
        "paon", "saon", "street", "locality", "town", "district", "county",
        "ppd_cat", "record_status")
_INSERT = (f"INSERT OR REPLACE INTO ppd ({','.join(COLS)},outcode) "
           f"VALUES ({','.join('?' * len(COLS))},?)")


def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}  {msg}"
    print(line, flush=True)


def _state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(d):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, STATE_PATH)


def _outcode(postcode):
    p = (postcode or "").strip().upper()
    return p.split(" ")[0] if " " in p else (p or None)


def _row_values(rec):
    """Map a 16-field CSV record to the bound parameter tuple (+ derived outcode)."""
    rec = (rec + [""] * 16)[:16]
    tuid = rec[0].strip("{}")
    try:
        price = int(rec[1]) if rec[1] else None
    except ValueError:
        price = None
    deed_date = rec[2][:10] if rec[2] else None        # 'YYYY-MM-DD HH:MM' -> 'YYYY-MM-DD'
    postcode = rec[3].strip() or None
    vals = [tuid, price, deed_date, postcode, rec[4], rec[5], rec[6], rec[7], rec[8],
            rec[9], rec[10], rec[11], rec[12], rec[13], rec[14], rec[15]]
    return tuple(vals) + (_outcode(postcode),)


# ---------------------------------------------------------------------------- schema

def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    cx = sqlite3.connect(DB_PATH, timeout=60)
    cx.execute("PRAGMA cache_size=-65536")     # ~64 MB page cache (small box)
    cx.execute("PRAGMA temp_store=FILE")        # sort temp -> on-disk (big data disk)
    cx.execute(f"PRAGMA temp_store_directory='{DATA_DIR}'")
    cx.execute("""
        CREATE TABLE IF NOT EXISTS ppd (
            tuid          TEXT PRIMARY KEY,
            price         INTEGER,
            deed_date     TEXT,
            postcode      TEXT,
            ptype         TEXT,
            old_new       TEXT,
            duration      TEXT,
            paon          TEXT,
            saon          TEXT,
            street        TEXT,
            locality      TEXT,
            town          TEXT,
            district      TEXT,
            county        TEXT,
            ppd_cat       TEXT,
            record_status TEXT,
            outcode       TEXT
        )""")
    cx.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    return cx


def _build_indexes(cx):
    log("building indexes (outcode, postcode, date, ptype) ...")
    cx.execute("CREATE INDEX IF NOT EXISTS ix_ppd_outcode ON ppd(outcode)")
    cx.execute("CREATE INDEX IF NOT EXISTS ix_ppd_postcode ON ppd(postcode)")
    cx.execute("CREATE INDEX IF NOT EXISTS ix_ppd_date ON ppd(deed_date)")
    cx.execute("CREATE INDEX IF NOT EXISTS ix_ppd_outcode_type_date "
               "ON ppd(outcode, ptype, deed_date)")
    cx.commit()
    log("indexes built")


# ------------------------------------------------------------------------- download

def _head(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.headers.get("Last-Modified"), int(r.headers.get("Content-Length") or 0)


def _download(url, dest):
    """Resumable download to dest (HTTP Range). Returns Last-Modified of the resource."""
    last_mod, total = _head(url)
    have = os.path.getsize(dest) if os.path.exists(dest) else 0
    if have and have == total:
        log(f"already have {dest} ({have:,} B) - skipping download")
        return last_mod
    if have > total:
        have = 0
    mode = "ab" if have else "wb"
    headers = {"User-Agent": UA}
    if have:
        headers["Range"] = f"bytes={have}-"
        log(f"resuming download at {have:,} / {total:,} B")
    else:
        log(f"downloading {url} -> {dest} ({total:,} B)")
    req = urllib.request.Request(url, headers=headers)
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, mode) as f:
        got = have
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if got % (256 << 20) < (1 << 20):
                rate = (got - have) / max(1e-3, time.time() - t0) / 1e6
                log(f"  {got/1e9:.2f} / {total/1e9:.2f} GB ({rate:.0f} MB/s)")
    log(f"downloaded {got:,} B in {time.time()-t0:.0f}s")
    return last_mod


def _stream_apply(cx, path, *, deletes=True):
    """Stream-parse a PPD CSV from disk into the table. Returns (upserts, deletes)."""
    up = dl = 0
    batch = []
    cur = cx.cursor()
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        for rec in csv.reader(f):
            if not rec or not rec[0]:
                continue
            status = rec[15].strip().upper() if len(rec) >= 16 else "A"
            if deletes and status == "D":
                cur.execute("DELETE FROM ppd WHERE tuid=?", (rec[0].strip("{}"),))
                dl += 1
                continue
            batch.append(_row_values(rec))
            if len(batch) >= BATCH:
                cur.executemany(_INSERT, batch)
                up += len(batch)
                batch.clear()
                if up % (BATCH * 50) == 0:
                    cx.commit()
                    log(f"  {up:,} rows ...")
    if batch:
        cur.executemany(_INSERT, batch)
        up += len(batch)
    cx.commit()
    return up, dl


# --------------------------------------------------------------------------- phases

def initial_load(cx):
    st = _state()
    if st.get("complete_loaded"):
        log("complete snapshot already loaded - skipping initial load")
        return
    log("=== INITIAL LOAD: complete Price Paid snapshot ===")
    last_mod = _download(COMPLETE_URL, CSV_TMP)
    # bulk-load fast: no journal, no fsync. Safe because we re-run from scratch on crash.
    cx.execute("PRAGMA journal_mode=OFF")
    cx.execute("PRAGMA synchronous=OFF")
    t0 = time.time()
    up, _ = _stream_apply(cx, CSV_TMP, deletes=False)
    log(f"loaded {up:,} rows in {time.time()-t0:.0f}s")
    _build_indexes(cx)
    cx.execute("PRAGMA journal_mode=WAL")     # serving mode: durable + concurrent reads
    cx.execute("PRAGMA synchronous=NORMAL")
    cx.execute("INSERT OR REPLACE INTO meta VALUES ('rows', ?)", (str(up),))
    cx.commit()
    try:
        os.remove(CSV_TMP)                      # reclaim 5.47 GB; monthly updates keep us current
    except OSError:
        pass
    st.update(complete_loaded=True, complete_last_modified=last_mod,
              complete_rows=up, complete_at=datetime.now(timezone.utc).isoformat())
    _save_state(st)
    log("=== initial load complete ===")


def apply_monthly(cx):
    st = _state()
    last_mod, total = _head(MONTHLY_URL)
    if last_mod and last_mod == st.get("monthly_last_modified"):
        return False
    log(f"=== MONTHLY UPDATE: {last_mod} ({total:,} B) ===")
    dest = os.path.join(DATA_DIR, "_pp-monthly.csv")
    _download(MONTHLY_URL, dest)
    up, dl = _stream_apply(cx, dest, deletes=True)
    log(f"monthly applied: {up:,} upserts, {dl:,} deletes")
    try:
        os.remove(dest)
    except OSError:
        pass
    st.update(monthly_last_modified=last_mod,
              monthly_at=datetime.now(timezone.utc).isoformat())
    _save_state(st)
    (n,) = cx.execute("SELECT COUNT(*) FROM ppd").fetchone()
    cx.execute("INSERT OR REPLACE INTO meta VALUES ('rows', ?)", (str(n),))
    cx.commit()
    return True


def status(cx):
    (n,) = cx.execute("SELECT COUNT(*) FROM ppd").fetchone()
    (mn,) = cx.execute("SELECT MIN(deed_date) FROM ppd").fetchone()
    (mx,) = cx.execute("SELECT MAX(deed_date) FROM ppd").fetchone()
    st = _state()
    log(f"rows={n:,} dates={mn}..{mx} state={json.dumps(st)}")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "daemon"
    cx = connect()
    if arg == "status":
        status(cx); return
    if arg == "once":
        initial_load(cx); apply_monthly(cx); status(cx); return
    if arg == "monthly":
        apply_monthly(cx); status(cx); return
    # daemon: load once, then poll the monthly file forever.
    initial_load(cx)
    status(cx)
    log(f"entering poll loop (every {POLL_SECONDS}s)")
    while True:
        try:
            if apply_monthly(cx):
                status(cx)
        except (urllib.error.URLError, OSError, sqlite3.Error) as e:
            log(f"poll error (will retry): {e!r}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
