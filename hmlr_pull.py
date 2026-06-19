"""hmlr_pull.py - pull every blog outcode's residential sold rows from the VPS-hosted HM Land
Registry Price Paid register in ONE read-only query over the existing SSH channel, and write a
local JSON cache the blog pipeline reads (HMLR_CACHE_PATH).

Why this shape:
  - The 5.47 GB register lives on the VPS (built + kept current by hmlr_ingest.py). The laptop
    must NEVER download it ("dont kill my laptop with a bulk import"). This tool only pulls the
    rows for the ~100 outcodes we actually publish - a few MB, not gigabytes.
  - It adds NO persistent service and NO open port on the shared VPS: it reads the open-data DB
    read-only through the authenticated SSH session and prints JSON to stdout. One round trip.
  - England & Wales only - HMLR Price Paid does not cover Scotland (Registers of Scotland) or
    Northern Ireland (Land & Property Services), so those cities are skipped here.

Usage (PowerShell, so POSIX paths are not mangled):
  python hmlr_pull.py                 # pull all E&W outcodes -> hmlr_cache.json
  python hmlr_pull.py LS1 LS2 EC1     # pull just these outcodes
"""
import datetime, json, os, sys

import cities
import _vps_run

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "hmlr_cache.json")
WINDOW_MONTHS = 120
DB = "/opt/honestly/data/hmlr_ppd.db"

# E&W only - HMLR Price Paid excludes Scotland and NI.
_EW = ("england", "wales", "england and wales")

# Read-only remote query: one SELECT over the whole register for every requested outcode in the
# window. OC/SINCE come in as env vars so we never interpolate user-ish strings into the SQL or
# the shell. Single-quoted to the shell, so double quotes inside are literal Python.
_REMOTE = (
    'import os,sqlite3,json\n'
    'ocs=[x for x in os.environ.get("OC","").split(",") if x]\n'
    'since=os.environ.get("SINCE","")\n'
    'cx=sqlite3.connect("file:%s?mode=ro",uri=True,timeout=120)\n'
    'ph=",".join("?"*len(ocs))\n'
    'q="SELECT outcode,tuid,price,deed_date,postcode,ptype FROM ppd WHERE outcode IN ("+ph+") '
    'AND deed_date>=? AND ptype IN (\\"F\\",\\"T\\",\\"S\\",\\"D\\")"\n'
    'rows=cx.execute(q,ocs+[since]).fetchall()\n'
    'cx.close()\n'
    'out={}\n'
    'for o,u,p,d,pc,t in rows:\n'
    '    out.setdefault(o,[]).append({"tuid":u,"price":p,"date":d,"postcode":pc,"ptype":t})\n'
    'print(json.dumps({"ok":True,"n":len(rows),"outcodes":out}))\n'
) % DB


def _ew_outcodes():
    seen, out = set(), []
    for c in cities.CITIES:
        if (c.get("country") or "").strip().lower() not in _EW:
            continue
        for d in c["districts"]:
            u = d.upper()
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


def main():
    args = [a.upper() for a in sys.argv[1:] if not a.startswith("-")]
    ocs = args or _ew_outcodes()
    since = (datetime.date.today()
             - datetime.timedelta(days=int(WINDOW_MONTHS * 30.44))).isoformat()
    print(f"pulling {len(ocs)} outcodes since {since} from {DB} ...")

    cli = _vps_run.connect()
    try:
        # Inline env vars + python3 -c. The remote script is single-quoted so its double quotes
        # stay literal; OC/SINCE are passed as the environment, never spliced into the SQL.
        oc_env = ",".join(ocs)
        cmd = (f"OC='{oc_env}' SINCE='{since}' python3 -c '{_REMOTE}'")
        rc, out, err = _vps_run.run(cli, cmd, timeout=300)
    finally:
        cli.close()

    if rc != 0:
        print(f"[remote exit {rc}] {err.strip()[:400]}")
        sys.exit(1)
    try:
        d = json.loads(out.strip().splitlines()[-1])
    except Exception as e:
        print(f"could not parse remote output: {e}\n--- raw ---\n{out[:600]}")
        sys.exit(1)
    if not d.get("ok"):
        print(f"remote query not ok: {d}")
        sys.exit(1)

    by_oc = d["outcodes"]
    payload = {
        "ok": True,
        "source": "HM Land Registry Price Paid Data (free official register, VPS mirror, OGL v3.0)",
        "db": DB,
        "since": since,
        "window_months": WINDOW_MONTHS,
        "n_rows": d["n"],
        "outcodes": by_oc,
    }
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    nonempty = sum(1 for o in ocs if by_oc.get(o))
    print(f"wrote {CACHE}: {d['n']:,} rows across {nonempty}/{len(ocs)} outcodes with sales")
    # quick visibility on the central districts the launch hinges on
    for o in ocs[:12]:
        print(f"  {o:5s} {len(by_oc.get(o, [])):>6} rows")


if __name__ == "__main__":
    main()
