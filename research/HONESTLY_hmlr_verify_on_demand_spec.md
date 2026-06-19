# HMLR "Verify on Demand" — hybrid data + court-evidence provenance spec

> Captured 2026-06-11 from an external blueprint, reconciled against the existing codebase.
> Status: **specification, not yet built.** This sits beside `land_registry.py` (which already
> exists) and extends task #15 (HMLR cross-check) with a litigation/court-evidence layer.

## The idea in one line

Use **PropertyData** (api.propertydata.co.uk) as the fast, rich **discovery/analytics layer**
for everyday work, and the **official HM Land Registry APIs** as a **verification layer** that
is hit only when a property moves from "browsing" to "legal preparation" — so the product can
offer court-admissible provenance without trying to host or sync the whole HMLR estate.

This is a **provenance and title-verification** concern. It is **NOT** a valuation input. The
honesty contract is unchanged: the figure is still anchored on sold evidence via
`engine.summary()`; nothing here moves `valuation()`. HMLR live data overrides *ownership /
title / boundary* fields for an evidence bundle, never the price.

## What already exists vs what this adds

| Concern | Module | Status |
|---|---|---|
| HMLR **Price Paid Data** (sold comps, official) + **HPI** series | `land_registry.py` (`ppd_postcode`, `hpi_region`) | **built** — SPARQL + REST, OGL, no key, best-effort `{ok,...}` |
| HMLR **title / ownership / boundary** live verification | (new) `hmlr_verify.py` | **spec only** — this document |
| On-demand **Official Copy (OC1, £7)** ordering | (new) Business Gateway client | **spec only** |
| Provenance + audit of which source proved what | `store.py` (`events`, `deliverables`) | partial — schema exists, verify-events not yet emitted |

`land_registry.py` is the *sold-market* truth source. This spec is the *title* truth source.
They are different HMLR products and should stay in separate modules.

## 1. Architecture — the two-phase gateway

```
                 [ Honestly app / bot / appraisal pipeline ]
                                     |
        ----------------------------------------------------------
        |                                                        |
  Phase 1: Research & Discovery                  Phase 2: Legal / Court Evidence
        |                                                        |
  [ PropertyData API ]                            [ HMLR official REST APIs ]
   - fast JSON, sub-market analytics               - live title verification
   - listings, demand, comps, boundaries           - proprietorship register (owners)
   - powers the UI + the valuation                 - boundary coordinates
                                                   - OGL v3, legally citable
```

- **Discovery layer (PropertyData):** unchanged. Every daily operation — search, comps,
  listings, demand, the valuation itself — runs on PropertyData as today.
- **Verification layer (HMLR "Use Land and Property Data" REST API):** triggered only when a
  user requests an *Official Court Evidence Bundle* or flags a property for litigation. A live,
  direct call confirms the current title number, registered proprietor(s) and boundary.
  Endpoint family: `use-land-property-data.service.gov.uk/api-information`.

Rationale for not bulk-syncing HMLR: hosting/keeping the full register current is costly and
complex, and the official copy is what a court ultimately wants anyway. Verify-on-demand keeps
cost and rate-limit exposure to the moment a case actually needs it.

## 2. Discrepancy handling — single source of truth

PropertyData caches and reformats; HMLR is authoritative and may be fresher. When a case is
marked for court, **HMLR overrides the critical title fields**, and the override is recorded
with provenance — never silently reconciled (mirrors how the engine surfaces divergence rather
than hiding it).

```python
# pseudocode — verification override, court path only
data = propertydata_client.get_attributes(property_id)   # rich analytics (Phase 1)
if case_status == "LITIGATION_PREP":
    live = hmlr_client.get_live_title(property_id)        # Phase 2, live
    data["owner_name"]      = live["proprietorship_register"]["owners"]
    data["title_number"]    = live["title_number"]
    data["data_provenance"] = "OFFICIAL HM LAND REGISTRY LIVE API"
    # record BOTH values + the divergence as an event in store.py, do not discard the cached one
```

Honesty posture: when the cached and live values disagree, the bundle shows both and names the
source of each, exactly as the data-spine divergence note does. The live HMLR value wins for
the *evidence claim*; the discrepancy itself is part of the evidence.

## 3. Declaring sources in court (the citation phrasing)

The References builder (`report.references()`, Workstream F) should be able to emit, when the
verification layer ran:

> "The preliminary real-estate analytics and market metrics were compiled using PropertyData.
> The ownership records, title statuses and boundary coordinates were verified live and direct
> against the authoritative real-time endpoints of the HM Land Registry REST API under the Open
> Government Licence v3."

This phrasing is only valid **when the live HMLR call actually succeeded for that report** —
honest by construction, like every other citation. If verification did not run, the bundle must
not claim it did.

## 4. Constraints to honour in the build

- **Official document caveat (OC1).** A live API stream is not itself a stamped legal document.
  A judge may still demand an **Official Copy**. Use the API to resolve the exact **Title
  Number** instantly, then order the **£7 Official Copy PDF on demand** via the **HMLR Business
  Gateway** (`gov.uk/guidance/hm-land-registry-business-gateway`). The ordered PDF is a
  `deliverables` row in `store.py` (type `official_copy`), with its own provenance + cost.
- **Rate limits.** The official REST APIs are query-limited. **Only activate the live HMLR call
  when a property moves from browsing → legal-prep** — never on the discovery path, never in the
  daily blog pipeline. This is a per-case, user-triggered action.
- **Keys / auth.** Any HMLR API credential lives in `.env` only (`HMLR_*`), read via
  `os.environ.get`, never hardcoded, never sent to a client — same rule as every other key.
- **Best-effort.** `hmlr_verify.py` returns `{ok: False, reason}` and never raises into a
  request, same posture as `land_registry.py` / `maps_tools.py`. If verification is down, the
  bundle degrades to "title not verified" rather than fabricating a result.

## 5. Where it wires in

- New module `hmlr_verify.py`: `get_live_title(...)`, `order_official_copy(title_number)` —
  both best-effort `{ok,...}`.
- `store.py`: emit a `verification_requested` / `title_verified` event with both cached and live
  values; add `deliverables` type `official_copy`.
- `report.references()`: add the HMLR live-verification citation, gated on a successful call.
- Trigger point: a bot/web action ("Official Court Evidence Bundle"), **off the request path**
  (Celery in Phase 5), never the valuation or the daily publish pipeline.

## Boundary with the blog (important)

This is an **appraisal / litigation product** feature. The **blog values nothing and verifies
nothing in court** — it reports transactions, listings and HPI side by side. None of this layer
touches `blog.py`, `market_district.py`, `market_study.py` or the daily publish pipeline.
