# -*- coding: utf-8 -*-
"""property_graph.py - the Honestly property knowledge graph (production, SQLite-backed).

A real, persistent property graph fed by ONE rule and one rule only: **only our own data-source
clients and free public datasets write nodes into it.** No code, no scraped third-party content,
no fabricated entities. Every node traces to a free official source:

    HM Land Registry Price Paid (land_registry.ppd_area, live SPARQL, OGL)  -> Property, Transaction, Area
    Environment Agency flood          (flood.floods, by lat/lng)            -> FloodZone
    planning.data.gov.uk constraints  (planning_data.constraints, by point) -> PlanningConstraint
    Companies House                   (companies_house, by company number)  -> CorporateLandlord

It lives in the SAME SQLite database as the rest of the app (store.DB_PATH) - one store, zero new
infrastructure - in two tables built for graphs: `graph_nodes` and `graph_edges`. Upserts are
idempotent (MERGE-style), so re-ingesting an area UPDATES in place instead of duplicating. This is
the free graph now; a push to Neo4j later is a straight export of these two tables.

HONEST SCALE NOTE: HMLR is queried area-by-area over the network. "Bulk ingest" means ingesting a
real, explicit set of postcodes/districts - it is minutes-to-hours of live SPARQL for a large
network, never an instant load of all of England. The graph holds the transactions and the derived
entities for the areas we have actually ingested; it never pretends to hold more.

  python property_graph.py ingest "EC1V 1AE" "EC1V 8TT"     # ingest explicit postcodes (live)
  python property_graph.py stats                            # node/edge counts by kind
  python property_graph.py selftest                         # offline round-trip, no network
"""
import json
import os
import sqlite3
import sys
import time

import store   # reuse the one database + its connection conventions

_DDL = """
CREATE TABLE IF NOT EXISTS graph_nodes (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,        -- Property | Transaction | Area | FloodZone | PlanningConstraint | CorporateLandlord
    label       TEXT,
    postcode    TEXT,
    district    TEXT,
    lat         REAL,
    lng         REAL,
    source      TEXT,                 -- the free source that produced this node (provenance)
    props_json  TEXT,
    created_at  REAL,
    updated_at  REAL
);
CREATE INDEX IF NOT EXISTS ix_gnodes_kind     ON graph_nodes(kind);
CREATE INDEX IF NOT EXISTS ix_gnodes_postcode ON graph_nodes(postcode);
CREATE INDEX IF NOT EXISTS ix_gnodes_district ON graph_nodes(district, kind);

CREATE TABLE IF NOT EXISTS graph_edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    src         TEXT NOT NULL,
    dst         TEXT NOT NULL,
    rel         TEXT NOT NULL,        -- SOLD | IN_AREA | COMPARABLE_TO | IN_FLOOD_ZONE | AFFECTED_BY_PLANNING | OWNED_BY
    source      TEXT,
    props_json  TEXT,
    created_at  REAL,
    UNIQUE(src, rel, dst)
);
CREATE INDEX IF NOT EXISTS ix_gedges_src ON graph_edges(src, rel);
CREATE INDEX IF NOT EXISTS ix_gedges_dst ON graph_edges(dst, rel);
"""

_INITED = False


def _log(*a):
    print("[graph]", *a, file=sys.stderr)


def _conn():
    """A fresh connection to the SAME database the app uses (store.DB_PATH), with the graph tables
    ensured once. WAL + busy timeout so it coexists with the bot poller and the web server."""
    global _INITED
    c = sqlite3.connect(store.DB_PATH, timeout=10.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=10000")
    if not _INITED:
        c.executescript(_DDL)
        c.commit()
        _INITED = True
    return c


def _json(obj):
    try:
        return json.dumps(obj, default=str, ensure_ascii=False)
    except Exception:
        return None


def _district(postcode):
    return store.district_of(postcode or "") or None


# ------------------------------------------------------------------ upserts (idempotent)
def upsert_node(c, node_id, kind, *, label=None, postcode=None, district=None, lat=None, lng=None,
                source=None, props=None):
    """MERGE a node: insert if new, else refresh its mutable fields. Returns the id. The graph is
    fed ONLY through here, and every node carries the free source that produced it (provenance)."""
    now = time.time()
    district = district or _district(postcode)
    c.execute(
        "INSERT INTO graph_nodes (id, kind, label, postcode, district, lat, lng, source, "
        "props_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET label=COALESCE(excluded.label, graph_nodes.label), "
        "postcode=COALESCE(excluded.postcode, graph_nodes.postcode), "
        "district=COALESCE(excluded.district, graph_nodes.district), "
        "lat=COALESCE(excluded.lat, graph_nodes.lat), lng=COALESCE(excluded.lng, graph_nodes.lng), "
        "source=COALESCE(excluded.source, graph_nodes.source), "
        "props_json=COALESCE(excluded.props_json, graph_nodes.props_json), updated_at=excluded.updated_at",
        (node_id, kind, label, postcode, district, lat, lng, source, _json(props) if props else None,
         now, now))
    return node_id


def upsert_edge(c, src, dst, rel, *, source=None, props=None):
    """MERGE an edge (src)-[rel]->(dst). Idempotent on (src, rel, dst)."""
    c.execute(
        "INSERT INTO graph_edges (src, dst, rel, source, props_json, created_at) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(src, rel, dst) DO UPDATE SET props_json=COALESCE(excluded.props_json, graph_edges.props_json)",
        (src, dst, rel, source, _json(props) if props else None, time.time()))


def _prop_id(address, postcode):
    key = (str(address or "").strip().lower() + "|" + str(postcode or "").strip().lower())
    return "prop:" + key


# ------------------------------------------------------------------ ingestion (free sources only)
_HMLR_SRC = "HM Land Registry Price Paid (OGL)"


def ingest_area(postcodes, since=None, comparable_band=0.20, max_comparable_edges=4000):
    """Ingest the REAL HMLR sold transactions for an explicit postcode set into the graph:
    Property + Transaction + Area nodes, SOLD + IN_AREA edges, and COMPARABLE_TO edges between
    same-district properties within +/- `comparable_band`. Live SPARQL via land_registry.ppd_area;
    idempotent (re-running updates in place). Returns a counts dict, or {ok:False} if the source
    call failed - never raises, never fabricates a sale."""
    try:
        import land_registry
        res = land_registry.ppd_area(postcodes, since=since, use_cache=False)
    except Exception as e:
        return {"ok": False, "reason": str(e)[:160]}
    if not res.get("ok"):
        return {"ok": False, "reason": res.get("reason", "ppd_area failed")}
    sales = res.get("sales") or []
    return _ingest_sales(sales, comparable_band=comparable_band,
                         max_comparable_edges=max_comparable_edges)


def _ingest_sales(sales, comparable_band=0.20, max_comparable_edges=4000):
    """The deterministic graph-building half of ingest_area, split out so the selftest can drive it
    with canned sales (no network). Builds Property/Transaction/Area nodes + edges from real rows."""
    n_prop = n_tx = n_area = n_edge = 0
    # latest price per property in each district, for the comparable pass
    by_district = {}
    with _conn() as c:
        for s in sales:
            addr, pc = s.get("address"), s.get("postcode")
            price, date = s.get("price"), (s.get("date") or "")[:10]
            if not (addr and price):
                continue
            pid = _prop_id(addr, pc)
            upsert_node(c, pid, "Property", label=addr, postcode=pc, source=_HMLR_SRC,
                        props={"property_type": s.get("type"), "category": s.get("category")})
            n_prop += 1
            tx_uri = s.get("hmlr_uri") or f"{pid}@{date}:{price}"
            tid = "tx:" + tx_uri
            upsert_node(c, tid, "Transaction", label=f"{addr} - £{price:,} ({date})",
                        postcode=pc, source=_HMLR_SRC,
                        props={"price": price, "date": date, "hmlr_uri": s.get("hmlr_uri")})
            n_tx += 1
            upsert_edge(c, pid, tid, "SOLD", source=_HMLR_SRC, props={"price": price, "date": date})
            d = _district(pc)
            if d:
                aid = "area:" + d
                upsert_node(c, aid, "Area", label=d, district=d, source=_HMLR_SRC)
                n_area += 1
                upsert_edge(c, pid, aid, "IN_AREA", source=_HMLR_SRC)
                cur = by_district.setdefault(d, {})
                # keep the most recent price per property for comparability
                if pid not in cur or date > cur[pid][1]:
                    cur[pid] = (price, date)
        # COMPARABLE_TO: within a district, link properties whose latest price is within the band.
        edges_made = 0
        for d, props in by_district.items():
            items = list(props.items())            # [(pid, (price, date)), ...]
            for i in range(len(items)):
                if edges_made >= max_comparable_edges:
                    break
                pid_a, (price_a, _) = items[i]
                if not price_a:
                    continue
                for j in range(i + 1, len(items)):
                    pid_b, (price_b, _) = items[j]
                    if not price_b:
                        continue
                    diff = abs(price_a - price_b) / max(price_a, price_b)
                    if diff <= comparable_band:
                        upsert_edge(c, pid_a, pid_b, "COMPARABLE_TO", source=_HMLR_SRC,
                                    props={"price_diff_pct": round(diff * 100, 1)})
                        n_edge += 1
                        edges_made += 1
                        if edges_made >= max_comparable_edges:
                            break
    return {"ok": True, "properties": n_prop, "transactions": n_tx, "areas": n_area,
            "comparable_edges": n_edge, "sales_seen": len(sales)}


def enrich_point(node_id, lat, lng):
    """Attach the point-based free designations to an existing Property node: EA flood zone and
    planning.data.gov.uk constraints (conservation area / Article 4 / flood zone / green belt).
    Only writes what the live free clients actually return. Returns a counts dict; never raises."""
    if lat is None or lng is None:
        return {"ok": False, "reason": "no coordinates"}
    made = {"flood": 0, "planning": 0}
    with _conn() as c:
        # record the coordinates on the property
        c.execute("UPDATE graph_nodes SET lat=?, lng=?, updated_at=? WHERE id=?",
                  (float(lat), float(lng), time.time(), node_id))
        try:
            import flood
            fl = flood.floods(lat, lng)
            sev = (fl.get("severity") or fl.get("risk")) if isinstance(fl, dict) and fl.get("ok") else None
            if sev:
                fid = "flood:" + str(sev).strip().lower().replace(" ", "_")
                upsert_node(c, fid, "FloodZone", label=str(sev), lat=lat, lng=lng,
                            source="Environment Agency flood (OGL)", props={"severity": sev})
                upsert_edge(c, node_id, fid, "IN_FLOOD_ZONE", source="Environment Agency flood (OGL)")
                made["flood"] += 1
        except Exception as e:
            _log("enrich flood:", str(e)[:120])
        try:
            import planning_data
            pc = planning_data.constraints(lat, lng)
            for it in (pc.get("items") or []) if pc.get("ok") else []:
                ref = it.get("reference") or it.get("name") or it.get("dataset")
                cid = "plan:" + str(ref).strip().lower().replace(" ", "_")
                upsert_node(c, cid, "PlanningConstraint", label=it.get("name") or it.get("label"),
                            lat=lat, lng=lng, source="planning.data.gov.uk (OGL)",
                            props={"dataset": it.get("dataset"), "label": it.get("label")})
                upsert_edge(c, node_id, cid, "AFFECTED_BY_PLANNING", source="planning.data.gov.uk (OGL)")
                made["planning"] += 1
        except Exception as e:
            _log("enrich planning:", str(e)[:120])
    return {"ok": True, **made}


# ------------------------------------------------------------------ queries
def comparables(property_id, limit=10):
    """Comparable properties for a property node, with their latest sold price. Pure graph read."""
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT n.id, n.label, n.postcode, e.props_json AS edge "
                "FROM graph_edges e JOIN graph_nodes n "
                "  ON n.id = CASE WHEN e.src=? THEN e.dst ELSE e.src END "
                "WHERE e.rel='COMPARABLE_TO' AND (e.src=? OR e.dst=?) LIMIT ?",
                (property_id, property_id, property_id, int(limit))).fetchall()
        out = []
        for r in rows:
            d = {"id": r["id"], "address": r["label"], "postcode": r["postcode"]}
            try:
                d["price_diff_pct"] = (json.loads(r["edge"]) or {}).get("price_diff_pct")
            except Exception:
                pass
            out.append(d)
        return out
    except Exception as e:
        _log("comparables:", str(e)[:160]); return []


def area_summary(district):
    """Live-from-the-graph summary for a district: property + transaction counts and a median of
    the most recent sold prices held in the graph. Honest: only what we've ingested."""
    try:
        with _conn() as c:
            props = c.execute("SELECT COUNT(*) n FROM graph_nodes WHERE kind='Property' AND district=?",
                              (district,)).fetchone()["n"]
            txs = c.execute(
                "SELECT props_json FROM graph_nodes WHERE kind='Transaction' AND district=?",
                (district,)).fetchall()
        prices = []
        for t in txs:
            try:
                p = (json.loads(t["props_json"]) or {}).get("price")
                if p:
                    prices.append(int(p))
            except Exception:
                pass
        prices.sort()
        median = prices[len(prices) // 2] if prices else None
        return {"district": district, "properties": props, "transactions": len(prices),
                "median_price": median}
    except Exception as e:
        _log("area_summary:", str(e)[:160]); return {"district": district}


def stats():
    """Node + edge counts by kind/relation - the honest size of the graph."""
    try:
        with _conn() as c:
            nodes = {r["kind"]: r["n"] for r in
                     c.execute("SELECT kind, COUNT(*) n FROM graph_nodes GROUP BY kind")}
            edges = {r["rel"]: r["n"] for r in
                     c.execute("SELECT rel, COUNT(*) n FROM graph_edges GROUP BY rel")}
        return {"nodes": nodes, "edges": edges,
                "total_nodes": sum(nodes.values()), "total_edges": sum(edges.values())}
    except Exception as e:
        _log("stats:", str(e)[:160]); return {"nodes": {}, "edges": {}}


# ------------------------------------------------------------------ CLI + selftest
def selftest():
    """Offline round-trip: drive the deterministic graph builder with canned HMLR-shaped sales (no
    network), then prove upsert idempotency, comparables, area summary and stats."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd); os.remove(path)
    prev_path, prev_inited = store.DB_PATH, store._INITED
    global _INITED
    store.DB_PATH, store._INITED, _INITED = path, False, False
    try:
        sales = [
            {"address": "1 Test St, London EC1V 1AE", "price": 500000, "date": "2025-01-10",
             "type": "T", "postcode": "EC1V 1AE", "hmlr_uri": "uri-1"},
            {"address": "2 Test St, London EC1V 1AE", "price": 520000, "date": "2025-02-10",
             "type": "T", "postcode": "EC1V 1AE", "hmlr_uri": "uri-2"},
            {"address": "3 Test St, London EC1V 1AE", "price": 900000, "date": "2025-03-10",
             "type": "D", "postcode": "EC1V 1AE", "hmlr_uri": "uri-3"},
        ]
        r1 = _ingest_sales(sales)
        assert r1["ok"] and r1["properties"] == 3 and r1["transactions"] == 3, r1
        # #1 and #2 are within 20% -> one COMPARABLE_TO; #3 (900k) is not comparable to 500k
        assert r1["comparable_edges"] == 1, r1
        # idempotent: re-ingest creates no duplicate nodes
        s = stats()
        _ingest_sales(sales)
        s2 = stats()
        assert s2["total_nodes"] == s["total_nodes"], (s, s2)
        assert s2["nodes"].get("Property") == 3 and s2["nodes"].get("Area") == 1
        # comparables query
        comps = comparables(_prop_id("1 Test St, London EC1V 1AE", "EC1V 1AE"))
        assert any("2 Test St" in (c["address"] or "") for c in comps), comps
        # area summary median of [500000,520000,900000] = 520000
        summ = area_summary("EC1V")
        assert summ["properties"] == 3 and summ["median_price"] == 520000, summ
        print("property_graph selftest OK:", json.dumps(s2))
    finally:
        store.DB_PATH, store._INITED, _INITED = prev_path, prev_inited, False
        for p in (path, path + "-wal", path + "-shm"):
            try:
                if os.path.exists(p): os.remove(p)
            except OSError:
                pass


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "selftest":
        return selftest()
    if cmd == "stats":
        print(json.dumps(stats(), indent=2)); return
    if cmd == "ingest":
        pcs = sys.argv[2:]
        if not pcs:
            print("usage: property_graph.py ingest <postcode> [<postcode> ...]"); return
        os.environ.setdefault("HONESTLY_AUTOSTORE", "0")
        print("ingesting", len(pcs), "postcode(s) from HM Land Registry (live)...")
        r = ingest_area(pcs)
        print(json.dumps(r, indent=2))
        print(json.dumps(stats(), indent=2))
        return
    print(__doc__)


if __name__ == "__main__":
    main()
