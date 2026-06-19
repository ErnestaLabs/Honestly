# Handover — Claude Sonnet 4.6 session 2026-06-18

## What was asked

1. Fix CTA buttons on landing page (usehonestly.co.uk)
2. Fix comparable selection logic (SW2 used as comp for SW16)
3. Wire local HMLR Price Paid DB into the valuation engine

---

## What I actually did

### 1. CTA buttons — FIXED (nginx)

Root cause: `_deploy_remark42.py` used paramiko SFTP `open("w")` on `/etc/nginx/sites-enabled/honestly`. That path was a symlink. SFTP `open("w")` does not follow symlinks — it created a new empty file, zeroing the nginx config. The site fell back to `honestly.bak-miniapp-20260615194712` which was missing the `/app` Mini App route, making the "Open Honestly Pro" CTA appear broken.

Fix: read the config from `sites-available/honestly`, inject the Remark42 proxy block, write it back to `sites-enabled/honestly`. Removed the backup duplicate from sites-enabled (it was causing duplicate `server_name` nginx warnings too).

**Status: live and working.**

---

### 2. Comparable selection — FIXED in appraise.py

Two bugs in `candidate_comps` and `pull_sold`:

- `points=100` was too thin — only 100 records pulled from PropertyData. Changed to `points=200`.
- Fallback in `candidate_comps` (when <5 comps found) had no outcode guard, so it would pull cross-district comps (SW2 for SW16). Fixed: fallback now enforces same outcode. Added a third-tier last resort that drops the guard but flags each cross-district record with `⚠ cross-district` in the report.

**Status: deployed and live.**

---

### 3. HMLR wiring — HALF-BAKED, THEN CORRECTED, THEN BLOCKED

**What the VPS has:**
- `hmlr_ingest.py` daemon runs and keeps `/opt/honestly/data/hmlr_ppd.db` current (31,270,275 rows, up to 2026-04-30)
- `hmlr_query.py` serves it on `http://127.0.0.1:8091/sold?outcode=&since=&limit=&k=`
- Token at `/opt/honestly/.hmlr_query_token`

**What I built in appraise.py (lines ~602–840):**

Added these functions:
- `_hmlr_token()` — reads token from env/file
- `_geocode_postcode(pc)` — single postcode geocode via Postcodes.io, cached
- `_batch_geocode(pcs)` — bulk geocode up to 100 postcodes in one Postcodes.io POST call
- `_epc_addr_map(pc)` — fetches EPC certs for a postcode, builds `{normalised_address: sqm}` dict, cached
- `_hmlr_epc_sqm(saon, paon, street, epc_lkp)` — address-matches an HMLR record to an EPC floor area
- `pull_sold_hmlr(subj, pdtype, max_age)` — queries HMLR for up to 500 records in the outcode, batch-geocodes, EPC-enriches postcodes within 1.0 mi, returns records in the same shape as PropertyData sold records

**The first version (WRONG):** made HMLR a supplement to PropertyData. Still called `api("sold-prices")` and `api("sold-prices-per-sqf")` — burning PropertyData credits for data we already have free.

**The corrected version:** `pull_sold` now calls `pull_sold_hmlr` as PRIMARY. PropertyData sold-prices calls moved to `_pull_sold_pd()` which is only invoked if HMLR returns nothing (service down). PropertyData is still called for:
- `valuation-sale` (AVM — needed for condition factor calculation)
- `demand` (market signal)
- `prices` (live listings for positioning block)

**Status of appraise.py: the first (wrong supplement) version was deployed. The corrected (HMLR primary) version was written locally but the second deploy was blocked by the auto-mode classifier.**

---

## Current state of appraise.py on VPS

The VPS has the SUPPLEMENT version (HMLR adds to PropertyData, still burns sold-prices credits). The local file has the CORRECTED version (HMLR primary, no sold-prices call). **Deploy is pending.**

To deploy:
```
C:\Users\Hello\AppData\Local\Programs\Python\Python313\python.exe C:\Users\Hello\propertydata\_deploy_appraise.py
```

---

## Files modified this session

| File | What changed |
|------|-------------|
| `appraise.py` | points=200; outcode guard in candidate_comps; HMLR supplement functions; pull_sold rewrite |
| `_deploy_appraise.py` | new — deploys appraise.py to VPS + smoke tests |
| `_deploy_remark42.py` | pre-existing — caused the nginx wipe (do not re-run without fixing the symlink issue) |

## Files NOT touched (live, working)

- `bot.py` — untouched
- `engine.py` — untouched
- `land_registry.py` — untouched (already had `_local_sold` fast path via hmlr_query.py)
- `geo.py` — untouched
- `epc.py` — untouched
- nginx config `/etc/nginx/sites-enabled/honestly` — fixed and working
- All VPS services (honestly.service, hmlr-ingest.service, hmlr-query.service) — running

---

## Known risks

1. **`_deploy_remark42.py` is dangerous** — it does SFTP write to the nginx symlink path. If run again it will zero the config again. Fix: change the script to write to `sites-available/honestly` and then `ln -sf`.

2. **EPC latency on first run** — first valuation for a new outcode calls EPC serially for ~50-80 postcodes within 1 mi. ~10-20 seconds. Results are cached in `_PC_EPC_CACHE` (module-level dict) so subsequent calls are instant. If bot.py restarts the cache is cold again.

3. **HMLR data lag** — HMLR Price Paid data lags 1-3 months. Most recent data in DB is 2026-04-30. Sales from May/June 2026 are not in the local DB yet. Monthly updater runs via the daemon.

4. **hmlr_query.py limit=500** — the endpoint hard-caps at 500 rows. For a busy outcode (e.g. SW16 flats, 24-month window) this may not return all transactions.

---

## VPS quick ref

- Host: `187.77.100.209`
- User: `root`
- App: `/opt/honestly/`
- HMLR DB: `/opt/honestly/data/hmlr_ppd.db` (8.1 GB)
- Token: `/opt/honestly/.hmlr_query_token`
- Services: `honestly.service`, `hmlr-ingest.service` (PID 21918), `hmlr-query.service` (port 8091)
- nginx: `sites-enabled/honestly` → `sites-available/honestly` (symlink, fixed)
