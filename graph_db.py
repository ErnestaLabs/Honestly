#!/usr/bin/env python3
"""graph_db.py - Honestly local data spine. SQLite + graph-style queries.

Pre-ingested, indexed local data replacing live API calls per valuation:
  - HM Land Registry Price Paid Data (all of England & Wales)
  - EPC records (cached from public register)
  - Postcodes.io geography (postcodes, lat/lng, neighbours, distances)
  - HPI monthly indices

The engine queries this DB in single-digit ms instead of hitting
rate-limited APIs that take seconds and timeout.

Usage:
  python graph_db.py init          # create schema
  python graph_db.py ingest-hmlr   # download + load HMLR bulk CSV
  python graph_db.py ingest-epc    # load EPC cache into DB
  python graph_db.py ingest-geo    # bulk-load postcode geography
  python graph_db.py serve         # run the local query service on port 8091
  python graph_db.py status        # row counts and freshness
"""
import argparse, csv, gzip, io, json, os, sqlite3, sys, time, urllib.request, urllib.parse
from pathlib import Path

DB_PATH = os.environ.get("HONESTLY_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "honestly.db"))
# HM Land Registry bulk CSV - updated monthly, ~28M rows, ~1.2GB gzipped
HMLR_BULK_URL = "http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-2025.csv"
# Postcodes.io list - all UK postcodes with lat/lng
POSTCODES_LIST_URL = "https://api.postcodes.io/data/postcodes/export"


def _conn() -> sqlite3.Connection:
    """Get a connection with WAL mode and foreign keys."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA cache_size=-64000")  # 64MB cache
    return db


# ────────────────────────────────────────────────────────────────── schema
SCHEMA_SQL = """
-- HM Land Registry Price Paid Data
CREATE TABLE IF NOT EXISTS hmlr_sales (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tuid        TEXT NOT NULL,            -- HM Land Registry transaction ID
    price       INTEGER NOT NULL,
    date        TEXT NOT NULL,            -- YYYY-MM-DD
    postcode    TEXT NOT NULL,
    ptype       TEXT NOT NULL,            -- D/S/T/F/O
    paon        TEXT,
    saon        TEXT,
    street      TEXT,
    town        TEXT,
    district    TEXT,
    county      TEXT,
    address     TEXT GENERATED ALWAYS AS (
        TRIM(COALESCE(saon || ', ', '') || COALESCE(paon || ', ', '') ||
             COALESCE(street || ', ', '') || COALESCE(town, ''))
    ) VIRTUAL,
    created_at  REAL NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_hmlr_postcode ON hmlr_sales(postcode);
CREATE INDEX IF NOT EXISTS idx_hmlr_ptype    ON hmlr_sales(postcode, ptype);
CREATE INDEX IF NOT EXISTS idx_hmlr_date     ON hmlr_sales(date);
CREATE INDEX IF NOT EXISTS idx_hmlr_tuid     ON hmlr_sales(tuid);

-- EPC records (cached from public register)
CREATE TABLE IF NOT EXISTS epc_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    address_key     TEXT NOT NULL,         -- normalised UPPER address for matching
    postcode        TEXT NOT NULL,
    address_raw     TEXT,                  -- original address string
    floor_area_sqm  INTEGER,
    rating          TEXT,                  -- A-G
    property_type   TEXT,
    built_form      TEXT,
    inspection_date TEXT,
    source          TEXT DEFAULT 'public EPC register',
    created_at      REAL NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_epc_address ON epc_records(address_key, postcode);
CREATE INDEX IF NOT EXISTS idx_epc_postcode ON epc_records(postcode);

-- Postcode geography (from Postcodes.io)
CREATE TABLE IF NOT EXISTS postcodes (
    postcode    TEXT PRIMARY KEY,
    outcode     TEXT NOT NULL,
    lat         REAL,
    lng         REAL,
    district    TEXT,
    region      TEXT,
    country     TEXT,
    created_at  REAL NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_pc_outcode ON postcodes(outcode);
CREATE INDEX IF NOT EXISTS idx_pc_latlng ON postcodes(lat, lng);

-- Pre-computed postcode neighbours within ~1 mile (from Postcodes.io nearest)
CREATE TABLE IF NOT EXISTS postcode_neighbours (
    postcode_a  TEXT NOT NULL,
    postcode_b  TEXT NOT NULL,
    dist_m      INTEGER NOT NULL,
    PRIMARY KEY (postcode_a, postcode_b)
);
CREATE INDEX IF NOT EXISTS idx_pn_a ON postcode_neighbours(postcode_a);
CREATE INDEX IF NOT EXISTS idx_pn_dist ON postcode_neighbours(postcode_a, dist_m);

-- HPI monthly indices (from HM Land Registry UK HPI)
CREATE TABLE IF NOT EXISTS hpi_monthly (
    region  TEXT NOT NULL,
    month   TEXT NOT NULL,     -- YYYY-MM
    idx     REAL NOT NULL,
    PRIMARY KEY (region, month)
);

-- Ingest metadata
CREATE TABLE IF NOT EXISTS ingest_log (
    source    TEXT PRIMARY KEY,
    row_count INTEGER,
    etag      TEXT,
    ingested_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);
"""


def init():
    """Create all tables and indexes."""
    db = _conn()
    db.executescript(SCHEMA_SQL)
    db.commit()
    db.close()
    print(f"Schema created at {DB_PATH}")


# ─────────────────────────────────────────────────────────────── HMLR ingest
_PTYPE_MAP = {"D": "D", "S": "S", "T": "T", "F": "F", "O": "O"}


def ingest_hmlr(since=None, limit=None):
    """Download and load HM Land Registry Price Paid Data.

    The bulk CSV is ~1.2GB gzipped, ~28M rows. We load everything
    (or rows since a given date) into SQLite with proper indexes.

    Columns in the CSV (no header row):
      0: tuid, 1: price, 2: date, 3: postcode, 4: ptype,
      5: new_build, 6: duration, 7: paon, 8: saon, 9: street,
      10: locality, 11: town, 12: district, 13: county,
      14: ppd_cat, 15: record_status
    """
    db = _conn()
    # Check what we already have
    existing = db.execute("SELECT row_count, etag FROM ingest_log WHERE source='hmlr'").fetchone()
    print(f"Downloading HMLR bulk CSV from {HMLR_BULK_URL}...")
    t0 = time.time()
    try:
        resp = urllib.request.urlopen(HMLR_BULK_URL, timeout=300)
    except Exception as e:
        print(f"Download failed: {e}")
        db.close()
        return
    # The file is served as CSV (not gzipped despite the URL)
    total = 0
    loaded = 0
    batch = []
    BATCH_SIZE = 50000
    cursor = db.cursor()
    for line in resp:
        total += 1
        if limit and total > limit:
            break
        # Parse CSV line
        parts = line.decode("utf-8", errors="replace").strip().split(",")
        if len(parts) < 14:
            continue
        # Skip header if present
        if parts[0].startswith("{"):
            continue
        tuid = parts[0].strip('"{}')
        try:
            price = int(parts[1].strip('"'))
        except ValueError:
            continue
        date = parts[2].strip('"')[:10]
        postcode = parts[3].strip('"').upper().replace(" ", "")
        # Re-add space for standard format
        if len(postcode) >= 5 and postcode[-4:].isdigit() is False and postcode[-3:].isalpha():
            postcode = postcode[:-3] + " " + postcode[-3:]
        ptype = parts[4].strip('"')
        paon = parts[7].strip('"')
        saon = parts[8].strip('"')
        street = parts[9].strip('"')
        town = parts[11].strip('"')
        district_str = parts[12].strip('"')
        county = parts[13].strip('"')
        if since and date < since:
            continue
        batch.append((tuid, price, date, postcode, ptype, paon, saon, street, town, district_str, county))
        loaded += 1
        if len(batch) >= BATCH_SIZE:
            cursor.executemany(
                "INSERT OR IGNORE INTO hmlr_sales (tuid, price, date, postcode, ptype, paon, saon, street, town, district, county) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                batch
            )
            batch = []
            if loaded % 500000 == 0:
                elapsed = time.time() - t0
                rate = loaded / elapsed if elapsed > 0 else 0
                print(f"  {loaded:,} rows loaded ({rate:,.0f}/s)...")
    # Flush remaining
    if batch:
        cursor.executemany(
            "INSERT OR IGNORE INTO hmlr_sales (tuid, price, date, postcode, ptype, paon, saon, street, town, district, county) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            batch
        )
    db.execute("INSERT OR REPLACE INTO ingest_log (source, row_count) VALUES ('hmlr', ?)", (loaded,))
    db.commit()
    elapsed = time.time() - t0
    print(f"Loaded {loaded:,} rows in {elapsed:.1f}s ({loaded/elapsed:,.0f}/s)" if elapsed > 0 else f"Loaded {loaded:,} rows")
    db.close()


# ─────────────────────────────────────────────────────────────── EPC ingest
def ingest_epc():
    """Load the EPC JSON cache into SQLite for fast lookups."""
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "epc_public_cache.json")
    if not os.path.exists(cache_path):
        print(f"No EPC cache at {cache_path}")
        return
    with open(cache_path, encoding="utf-8") as f:
        cache = json.load(f)
    db = _conn()
    loaded = 0
    for key, val in cache.items():
        if not isinstance(val, dict) or not val.get("ok") or not val.get("matched"):
            continue
        # key is typically "ADDRESS|POSTCODE"
        parts = key.rsplit("|", 1)
        addr_raw = parts[0] if len(parts) >= 1 else key
        pc = parts[1] if len(parts) >= 2 else ""
        addr_key = addr_raw.upper().strip()
        db.execute(
            "INSERT OR REPLACE INTO epc_records (address_key, postcode, address_raw, floor_area_sqm, rating, property_type, built_form, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (addr_key, pc.upper().strip(), addr_raw,
             val.get("floor_area_sqm"), val.get("rating"),
             val.get("property_type"), val.get("built_form"),
             val.get("source", "public EPC register"))
        )
        loaded += 1
    db.execute("INSERT OR REPLACE INTO ingest_log (source, row_count) VALUES ('epc', ?)", (loaded,))
    db.commit()
    print(f"Loaded {loaded} EPC records")
    db.close()


# ──────────────────────────────────────────────────────── Postcodes.io ingest
def ingest_geo(postcodes_csv=None):
    """Load postcode geography from Postcodes.io export or a local CSV.

    The CSV has columns: postcode, latitude, longitude, etc.
    """
    db = _conn()
    if postcodes_csv and os.path.exists(postcodes_csv):
        print(f"Loading from local CSV: {postcodes_csv}")
        with open(postcodes_csv, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            loaded = 0
            batch = []
            for row in reader:
                pc = (row.get("postcode") or "").upper().strip()
                if not pc:
                    continue
                outcode = pc.split()[0] if " " in pc else pc[:-3].strip()
                try:
                    lat = float(row.get("latitude") or row.get("lat") or 0)
                    lng = float(row.get("longitude") or row.get("lng") or 0)
                except ValueError:
                    continue
                if lat == 0 and lng == 0:
                    continue
                batch.append((pc, outcode, lat, lng,
                              row.get("admin_district", ""), row.get("region", ""),
                              row.get("country", "")))
                loaded += 1
                if len(batch) >= 50000:
                    db.executemany(
                        "INSERT OR REPLACE INTO postcodes (postcode, outcode, lat, lng, district, region, country) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
                    batch = []
                    if loaded % 500000 == 0:
                        print(f"  {loaded:,} postcodes loaded...")
            if batch:
                db.executemany(
                    "INSERT OR REPLACE INTO postcodes (postcode, outcode, lat, lng, district, region, country) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
            db.execute("INSERT OR REPLACE INTO ingest_log (source, row_count) VALUES ('geo', ?)", (loaded,))
            db.commit()
            print(f"Loaded {loaded:,} postcodes")
    else:
        # Use Postcodes.io API for a smaller set - just the outcodes we need
        print("No local CSV. Use: python graph_db.py ingest-geo --csv <path>")
        print("Download from: https://api.postcodes.io/data/postcodes/export")
    db.close()


def compute_neighbours(radius_m=1609):
    """Pre-compute postcode neighbours within radius_m using lat/lng.

    This replaces the live geo.nearest() API call per valuation.
    Uses the haversine formula on the cached lat/lng.
    """
    import math
    db = _conn()
    postcodes = db.execute("SELECT postcode, lat, lng FROM postcodes WHERE lat IS NOT NULL").fetchall()
    print(f"Computing neighbours for {len(postcodes):,} postcodes within {radius_m}m...")
    by_outcode = {}
    for pc, lat, lng in postcodes:
        oc = pc.split()[0]
        by_outcode.setdefault(oc, []).append((pc, lat, lng))
    batch = []
    loaded = 0
    t0 = time.time()
    for oc, pcs in by_outcode.items():
        # Check this outcode + adjacent outcodes
        nearby = list(pcs)
        for adj_oc in _adjacent_outcodes(oc):
            nearby.extend(by_outcode.get(adj_oc, []))
        for i, (pc_a, lat_a, lng_a) in enumerate(pcs):
            for pc_b, lat_b, lng_b in nearby:
                if pc_a >= pc_b:
                    continue  # avoid duplicates
                d = _haversine(lat_a, lng_a, lat_b, lng_b)
                if d <= radius_m:
                    batch.append((pc_a, pc_b, int(d)))
                    batch.append((pc_b, pc_a, int(d)))
                    loaded += 1
        if len(batch) >= 100000:
            db.executemany(
                "INSERT OR IGNORE INTO postcode_neighbours (postcode_a, postcode_b, dist_m) "
                "VALUES (?, ?, ?)", batch)
            batch = []
            if loaded % 500000 == 0:
                elapsed = time.time() - t0
                print(f"  {loaded:,} neighbour pairs ({elapsed:.0f}s)...")
    if batch:
        db.executemany(
            "INSERT OR IGNORE INTO postcode_neighbours (postcode_a, postcode_b, dist_m) "
            "VALUES (?, ?, ?)", batch)
    db.execute("INSERT OR REPLACE INTO ingest_log (source, row_count) VALUES ('neighbours', ?)", (loaded,))
    db.commit()
    elapsed = time.time() - t0
    print(f"Computed {loaded:,} neighbour pairs in {elapsed:.0f}s")
    db.close()


def _adjacent_outcodes(outcode):
    """Generate likely adjacent outcodes (same area, +/-1 digit)."""
    # Simple heuristic: same first letter/digits
    parts = []
    for i in range(len(outcode)):
        prefix = outcode[:i+1]
        parts.append(prefix)
    return parts


def _haversine(lat1, lng1, lat2, lng2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


# ──────────────────────────────────────────────────────────── query API
class GraphQuery:
    """Fast local queries replacing live API calls.

    Usage:
        gq = GraphQuery()
        sales = gq.sales_for_postcode('SW16 2RQ')
        nearby = gq.nearby_postcodes('SW16 2RQ', radius_m=805)
        epc = gq.epc_for_address('8 Newdigate House', 'SW16 2RQ')
    """
    def __init__(self, db_path=None):
        self.db = sqlite3.connect(db_path or DB_PATH, timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.row_factory = sqlite3.Row

    def sales_for_postcode(self, postcode, ptype=None, since=None, limit=200):
        """All HMLR sales for a postcode, optionally filtered by type and date."""
        pc = postcode.upper().strip()
        if ptype:
            if since:
                rows = self.db.execute(
                    "SELECT * FROM hmlr_sales WHERE postcode=? AND ptype=? AND date>=? ORDER BY date DESC LIMIT ?",
                    (pc, ptype, since, limit)).fetchall()
            else:
                rows = self.db.execute(
                    "SELECT * FROM hmlr_sales WHERE postcode=? AND ptype=? ORDER BY date DESC LIMIT ?",
                    (pc, ptype, limit)).fetchall()
        else:
            if since:
                rows = self.db.execute(
                    "SELECT * FROM hmlr_sales WHERE postcode=? AND date>=? ORDER BY date DESC LIMIT ?",
                    (pc, since, limit)).fetchall()
            else:
                rows = self.db.execute(
                    "SELECT * FROM hmlr_sales WHERE postcode=? ORDER BY date DESC LIMIT ?",
                    (pc, limit)).fetchall()
        return [dict(r) for r in rows]

    def sales_for_postcodes(self, postcodes, ptype=None, since=None, limit=1500):
        """Sales across multiple postcodes (for area queries)."""
        if not postcodes:
            return []
        pcs = [p.upper().strip() for p in postcodes if p]
        placeholders = ",".join("?" * len(pcs))
        sql = f"SELECT * FROM hmlr_sales WHERE postcode IN ({placeholders})"
        params = list(pcs)
        if ptype:
            sql += " AND ptype=?"
            params.append(ptype)
        if since:
            sql += " AND date>=?"
            params.append(since)
        sql += f" ORDER BY date DESC LIMIT {int(limit)}"
        rows = self.db.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def nearby_postcodes(self, postcode, radius_m=1609):
        """Postcodes within radius_m, with distances."""
        pc = postcode.upper().strip()
        rows = self.db.execute(
            "SELECT postcode_b, dist_m FROM postcode_neighbours WHERE postcode_a=? AND dist_m<=? ORDER BY dist_m",
            (pc, radius_m)).fetchall()
        result = [{"postcode": r["postcode_b"], "dist_m": r["dist_m"]} for r in rows]
        # Always include the subject postcode itself
        if not any(r["postcode"] == pc for r in result):
            result.insert(0, {"postcode": pc, "dist_m": 0})
        return result

    def epc_for_address(self, address, postcode):
        """EPC record for an address."""
        pc = postcode.upper().strip()
        addr_key = address.upper().strip()
        row = self.db.execute(
            "SELECT * FROM epc_records WHERE postcode=? AND address_key LIKE ? LIMIT 1",
            (pc, f"%{addr_key[:30]}%")).fetchone()
        if row:
            return dict(row)
        # Try broader match
        row = self.db.execute(
            "SELECT * FROM epc_records WHERE postcode=? LIMIT 5",
            (pc,)).fetchone()
        return dict(row) if row else None

    def epc_for_postcode(self, postcode):
        """All EPC records for a postcode."""
        pc = postcode.upper().strip()
        rows = self.db.execute("SELECT * FROM epc_records WHERE postcode=?", (pc,)).fetchall()
        return [dict(r) for r in rows]

    def postcode_geo(self, postcode):
        """Lat/lng and admin areas for a postcode."""
        pc = postcode.upper().strip()
        row = self.db.execute("SELECT * FROM postcodes WHERE postcode=?", (pc,)).fetchone()
        return dict(row) if row else None

    def hpi_index(self, region, month=None):
        """HPI index for a region and month."""
        if month:
            row = self.db.execute("SELECT * FROM hpi_monthly WHERE region=? AND month<=? ORDER BY month DESC LIMIT 1", (region, month)).fetchone()
        else:
            row = self.db.execute("SELECT * FROM hpi_monthly WHERE region=? ORDER BY month DESC LIMIT 1", (region,)).fetchone()
        return dict(row) if row else None

    def close(self):
        self.db.close()


# ──────────────────────────────────────────────────────── query service
def serve(port=8091):
    """Run a local HTTP query service so land_registry.py can use it.

    Endpoints:
      GET /sold?postcode=SW16+2RQ&limit=100&k=TOKEN
      GET /health
    """
    from http.server import HTTPServer, BaseHTTPRequestHandler
    gq = GraphQuery()
    token = os.environ.get("HMLR_QUERY_TOKEN", "local")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if parsed.path == "/health":
                self._json(200, {"ok": True, "status": "running"})
                return
            if parsed.path == "/sold":
                k = params.get("k", [""])[0]
                if k != token:
                    self._json(403, {"ok": False, "reason": "bad token"})
                    return
                pc = params.get("postcode", [""])[0]
                limit = int(params.get("limit", ["100"])[0])
                sales = gq.sales_for_postcode(pc, limit=limit)
                self._json(200, {"ok": True, "postcode": pc, "count": len(sales), "rows": sales})
                return
            self._json(404, {"ok": False, "reason": "not found"})

        def _json(self, code, data):
            body = json.dumps(data, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass  # suppress access logs

    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Honestly data spine serving on http://127.0.0.1:{port}")
    print(f"DB: {DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")
        gq.close()


# ──────────────────────────────────────────────────────────── status
def status():
    db = _conn()
    tables = ["hmlr_sales", "epc_records", "postcodes", "postcode_neighbours", "hpi_monthly"]
    for t in tables:
        try:
            count = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception:
            count = "NOT CREATED"
        print(f"  {t:30s} {count:>12,}")
    logs = db.execute("SELECT source, row_count, ingested_at FROM ingest_log").fetchall()
    for src, cnt, ts in logs:
        tstr = time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts)) if ts else "?"
        print(f"  ingest: {src:20s} {cnt:>12,} rows  {tstr}")
    db.close()


# ──────────────────────────────────────────────────────────── CLI
def main():
    ap = argparse.ArgumentParser(description="Honestly data spine - local graph DB")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("init", help="Create schema")
    p = sub.add_parser("ingest-hmlr", help="Download and load HMLR bulk CSV")
    p.add_argument("--since", help="Only load rows with date >= YYYY-MM-DD")
    p.add_argument("--limit", type=int, help="Max rows to load (for testing)")
    sub.add_parser("ingest-epc", help="Load EPC cache into DB")
    p2 = sub.add_parser("ingest-geo", help="Load postcode geography")
    p2.add_argument("--csv", help="Path to Postcodes.io export CSV")
    sub.add_parser("compute-neighbours", help="Pre-compute postcode neighbour distances")
    p3 = sub.add_parser("serve", help="Run local query service")
    p3.add_argument("--port", type=int, default=8091)
    sub.add_parser("status", help="Row counts and freshness")
    args = ap.parse_args()
    if args.cmd == "init":
        init()
    elif args.cmd == "ingest-hmlr":
        ingest_hmlr(since=args.since, limit=args.limit)
    elif args.cmd == "ingest-epc":
        ingest_epc()
    elif args.cmd == "ingest-geo":
        ingest_geo(postcodes_csv=args.csv)
    elif args.cmd == "compute-neighbours":
        compute_neighbours()
    elif args.cmd == "serve":
        serve(port=args.port)
    elif args.cmd == "status":
        status()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
