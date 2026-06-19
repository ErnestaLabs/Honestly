# Honestly — API Inventory + Locked Lite/Pro Product Spec

Status: LOCKED direction. Date stamped on write. Everything below is grounded in a live
probe of the actual keys (not memory) and a file-by-file check of which clients exist.
Honesty contract unchanged: sold evidence anchors the figure; every API below the anchor
sits BESIDE the number as sourced context, never an input to `engine.value()`.

---

## 1. API inventory — what we ACTUALLY have (probe-verified 2026-06)

### 1a. Keyed / billing providers

| Provider | Key | Cost (real) | Client | Gives us | Tier |
|---|---|---|---|---|---|
| PropertyData | SET (quota-out) | subscription, per-call quota | `appraise.api` | AVM (`valuation-sale`), sold comps, listings, demand, schools, rent/yield | PRO |
| Street Group (StreetData) | SET (~£47 bal) | £0.10 / property (verified `request_cost_gbp`) | `appraise.street_subject` (gated) | 2nd-source attrs, council-tax annual £, full lease, flood, plot, per-property £/sqm sold history | PRO |
| Chimnie | UNSET (free credits pending) | Core £0.05 / Plus £0.10 / Premium £0.15 | `chimnie.py` (built, gated, schema-unverified) | **AVM w/ calibrated CI**, 500+ attrs, **Scotland/NI**, solar/rebuild/roof | PRO |
| Gemini | SET | per-token | `ai.py` | plain-English narrative grounded in `summary()` | PRO |
| Mistral Voxtral | UNSET | per-char TTS | `audio.py` (needs key) | spoken glass-box walkthrough | PRO |

### 1b. Google Maps key — the fleet (one key, probe-verified LIVE)

All returned HTTP 200 with real payloads unless noted. These bill beyond Google's monthly
free credit, so they are **PRO / on-demand only — never in bulk blog backfill**.

| Google API | Status | Client | Use |
|---|---|---|---|
| **Solar** | 200 ✓ | **NONE (build `solar.py`)** | roof solar potential, kWh/yr, panel config, payback financials |
| **Weather** | 200 ✓ | NONE (minor) | current/seasonal context for Outlook |
| **Pollen** | 200 ✓ | NONE (minor) | tree/grass/weed forecast → Environment |
| Air Quality | 200 ✓ | — (we use free CAMS instead) | redundant; keep CAMS (`air_quality.py`) |
| Distance Matrix | 200 ✓ | `maps_tools.distance_matrix` | travel times → Location & connectivity |
| Address Validation | 200 ✓ | `maps_tools.validate_address` | verified/normalised subject + provenance badge |
| Geocoding | 200 ✓ | `maps_tools.geocode` | lat/lng |
| Routes / Roads | 200 ✓ | `maps_tools.route` (Directions) | door-knock route (agent) |
| Elevation | 200 ✓ | NONE (trivial) | flood-context elevation |
| Time Zone / Geolocation | 200 ✓ | — | minor |
| Street View (meta+img) | 200 ✓ | `maps_tools.street_view` | frontage photo |
| Static Maps | 200 ✓ | `maps_tools.static_map` | location map image |
| Places (New) | enabled (needs FieldMask) | `maps_tools.places_search` | amenities/schools |
| Aerial View | 403 not enabled | — | (could enable: cinematic flyover video) |
| Map Tiles (2D/3D) | 403 not enabled | — | (could enable: photorealistic tiles) |

Net new client to build with access already live: **`solar.py`** (high value), then optional
`weather`/`pollen`/`elevation` helpers (low value).

### 1c. Free / keyless spine (clients ALREADY built)

| Source | Client | Gives us | Licence |
|---|---|---|---|
| HM Land Registry Price Paid + HPI | `land_registry.py` | official sold comps + HPI series (E&W) | OGL v3.0 |
| Postcodes.io | `geo.py` | postcode→lat/lng, admin areas, nearest postcodes | OGL/MIT |
| Police.uk | `police.py` | street-level crime by category | OGL v3.0 |
| Environment Agency Flood Monitoring | `flood.py` | active flood warnings/alerts near subject | OGL v3.0 |
| Open-Meteo / CAMS | `air_quality.py` | European AQI + PM2.5/PM10/NO2 | CAMS |
| PlanIt | `planning.py` | nearby planning applications by status | open |
| OSM Overpass | `overpass.py` | amenities + transport nodes (self-host on VPS) | ODbL |
| VOA (band→bracket) | `council_tax.py` | council-tax band → 1991 value bracket | OGL |
| BoE / ONS | `macro.py`, `macro_live.py` | Bank Rate, MPC date, HPI momentum, SDLT | OGL |
| Reddit (via Hit MCP) | `social_sentiment.py`, `market_analysis.py` | local social sentiment (NOT value evidence) | MCP boundary |

Aggregated by `area_context.py` → Location, Area, Safety, Environment, Planning, Material,
Narrative panels (already render in both PDF and HTML).

---

## 2. Possible GREAT additions (ranked by value × effort)

| Add | Why it's great | Cost | Effort | Verdict |
|---|---|---|---|---|
| **Google Solar client** | closes the only real capability gap; roof kWh + payback is a standout Pro panel | free tier / cheap | ~1 file | **BUILD NOW** |
| **Chimnie (on key)** | restores an AVM anchor (PD quota-out), adds Scotland/NI, solar/rebuild/roof | £0.05–0.15 | wired, gated | **ON KEY** |
| **EPC Register direct** (`EPC_KEY`) | official floor area + EPC straight from register; firms up `sqm` that today rides on the provider | free (register) | small | HIGH — register the key |
| **OS Open UPRN / OS Places** | free UPRN resolution → cut PropertyData dependence for subject resolve | free (OS OpenData) | medium | HIGH for cost-down |
| **Companies House** | freeholder/landlord corporate lookup for leasehold intel | free | small | MED (Pro leasehold) |
| **English Indices of Deprivation (IMD) + Census** | neighbourhood quality / demographics, sourced | free | small | MED (Lite + Pro) |
| **DfE school performance tables** | beyond Ofsted rating: Progress 8, results | free | small | MED |
| **HMLR title summary** (Find-a-Property) | official tenure/title confirmation | £3/title | small | LOW (Pro premium add-on) |
| Google Weather / Pollen / Elevation | minor Environment/Outlook polish | cheap | trivial | LOW |
| Google Aerial View / Map Tiles | cinematic flyover / 3D tiles (enable in console) | cheap | medium | LATER (wow-factor) |

---

## 3. LOCKED direction — the Lite/Pro philosophy

**THE THESIS (this is the whole product in one line):**
**Lite is an excellent valuation. Pro takes it to a DEFENSIBLE VALUE in the real sense** — every
factor that can move the price accounted for and shown with its source, the number adjusted for
your scenario, and a plan of action that follows from the evidence, so you can *defend* the
figure to an agent, a buyer, a mortgage valuer, a court, or yourself. That is the brand tagline
("A DEFENSIBLE VALUE") made literal: defensible because nothing is hidden and every lever is on
the table. Lite is the free lead-gen weapon at the top of the funnel; Pro is the defensible
dossier at the point.

**The distinction is REAL, not cosmetic. It is a SOURCE distinction, which is why it is honest:**

- **Lite = excellent, free, and carries an ACCURATE figure plus the key details.** Lite is the
  honest sold-anchored valuation from the free spine (the existing `engine.value()` figure:
  sold comps + £/sqm + condition-adjusted build-up) — a real, accurate, range-bounded number,
  not a watered-down "estimate" — plus the core property and area detail: comps, HPI, macro
  outlook, crime, flood, air quality, planning, amenities, transport, council-tax, sentiment,
  references. Free and bulk-safe (it is the £0 producer for the blog backfill — the standing
  HMLR-bulk rule). Lite alone is better than every "free valuation" online, which give one
  black-box number; Lite gives an accurate figure WITH the evidence and the sources.

- **Pro = the FULL ARSENAL. "Too good to be true."** Pro fires EVERY API we have, paid and free,
  all of them, and turns the report from a valuation into a DECISION DOSSIER. Specifically Pro:
  1. **Factors in everything that can influence the price** — the AVM anchor (PropertyData +
     Chimnie, cross-checked vs sold build-up), 2nd/3rd-source attribute verification
     (StreetData + Chimnie), condition/finish, EPC + energy + **solar** financials, lease/tenure,
     rebuild cost, flood/subsidence/air-quality/crime/planning, connectivity (travel times),
     amenities, schools, demand, live positioning, and macro (Bank Rate, HPI momentum). Each is
     shown with its source and its direction of effect — the glass box, comprehensive.
  2. **Adjusts the price for each SCENARIO** — not one number but a scenario matrix: quick-sale
     floor vs realistic guide vs aspirational ceiling, each with expected days-on-market and net
     proceeds; buyer's sensible opening offer vs walk-away ceiling vs negotiating headroom against
     asking; lister's instruction-winning-but-defensible guide. Grounded in the real
     `low/high/central/guide` + positioning, never invented.
  3. **Tells you what people say** — live Reddit/social sentiment via the Hit MCP, beside the
     figure as sentiment (never value evidence).
  4. **Gives a PLAN OF ACTION for YOUR role — buying, selling, or listing.** A written, numbered
     strategy keyed to the persona: the offer/price to put forward, the timing, the leverage,
     the negotiation levers, the costs to expect (SDLT/CGT/fees), and the next steps. This is the
     deliverable's spine, not an afterthought — built on the existing `audience` (buyer / vendor /
     agent) framing in `engine.summary()`, extended into a full action plan.

  Plus UK-wide coverage incl. Scotland/NI (Chimnie), Gemini narrative, audio walkthrough, the
  genuinely interactive HTML app, and a persisted/audited hosted link.

This maps onto the existing gates: `STREETDATA_ENRICH`, `CHIMNIE_ENRICH`, `CHIMNIE_AVM_ANCHOR`
default OFF (Lite/bulk) and switch ON only on the Pro path; the persona action plan reuses the
`audience` parameter already threaded through `engine.summary()`.

### Lite is the lead-gen + distribution WEAPON (its strategic job)

Lite is not merely the free tier — it is the top-of-funnel growth engine, and its design serves
that job:

- **Free + accurate + every-line-sourced + £0-to-mint = it scales.** Because Lite uses only the
  free spine it costs nothing per report, so it blankets all 118 districts (and every address on
  demand) without burning budget — the standing HMLR-bulk economics.
- **It is built to be FOUND.** Sourced, referenced, structured copy is exactly what ranks in
  Google and what ChatGPT / Claude / Perplexity cite (the AEO/GEO play, #33). A black-box number
  cannot earn a citation; an evidenced, referenced figure can. Lite's honesty IS its SEO moat.
- **It captures and converts.** Each Lite report drops a free branded PDF lead magnet (#45),
  captures the lead, and the email funnel (#51-55) + the free → Telegram lite → Pro funnel (#46)
  walk the lead up to the paid dossier. Lite is the wide end; Pro is the monetised point.
- **Implication for the build:** anything that makes Lite more accurate, more sourced, or more
  shareable compounds across the whole funnel. Lite quality is growth, not just product.

---

## 4. LITE template (free — locked section list)

Bulk blog backfill renders the same template at £0. On-demand Lite may add a single static map.

| # | Section | Source(s) | Notes |
|---|---|---|---|
| 1 | Hero + accurate figure | `engine.value()` sold-anchored figure (free spine) | a real accurate range, sourced — not a black box |
| 2 | How we got here (glass-box, static) | the arithmetic chain | sold median → £/sqm cross-check → condition-adj → range |
| 3 | Comparable evidence | HMLR PPD, comparability-scored | sortable in HTML, table in PDF |
| 4 | Price trend | HMLR/ONS HPI | CSS bar chart |
| 5 | Market outlook | `macro.py` + `macro_live.py` | Bank Rate, MPC, HPI momentum |
| 6 | Location & connectivity | Postcodes.io + Overpass transport | free transport proximity (no Google billing in bulk) |
| 7 | Area & amenities | Overpass | counts + nearest named |
| 8 | Safety | Police.uk | crime by category |
| 9 | Environment | EA Flood + CAMS air quality | active warnings + AQI |
| 10 | Planning & development | PlanIt | nearby apps by status |
| 11 | Material information | VOA council-tax bracket | band → 1991 bracket (no invented bill) |
| 12 | Neighbourhood (proposed add) | IMD / Census | deprivation decile, demographics |
| 13 | Local voices | frozen Reddit sentiment | social, NOT value evidence |
| 14 | References | shared `references()` builder | numbered, academic, accessed-date |
| — | Delivery | free PDF + hosted `/r/<token>` link | lead magnet → Telegram lite → Pro |

---

## 5. PRO template (full arsenal — locked section list)

Pro contains everything in Lite, then the full arsenal: every price-influencing signal, the
scenario-adjusted pricing matrix, what people say, and a role-specific plan of action. The
three Pro-defining blocks (Price-influence ledger, Scenario matrix, Action plan) are the spine.

| # | Section | Source(s) | What Pro adds |
|---|---|---|---|
| 1 | Hero + figure | AVM anchor (PropertyData + Chimnie) x-checked vs sold build-up | divergence disclosed; UK-wide incl. Scotland/NI |
| 2 | Glass-box build-up (interactive) | the arithmetic chain | tap-through: median → condition-adj AVM → £/sqm → sold anchor → disclosed capped steer → central |
| 3 | Condition lever | real `v['avm']` tiers | toggle finish tier; figure moves only on real tiers |
| **4** | **PRICE-INFLUENCE LEDGER** | **the whole arsenal** | **every factor that moves price, each with source + direction of effect: AVM, 2nd/3rd-source attr verification (StreetData+Chimnie), EPC/energy, solar financials, lease/tenure, rebuild, flood/subsidence/AQI/crime/planning, connectivity, schools, demand, positioning, macro** |
| **5** | **SCENARIO PRICING MATRIX** | `low/high/central/guide` + positioning + macro | **quick-sale floor / realistic guide / aspirational ceiling — each with expected days-on-market + net proceeds; buyer offer/ceiling/headroom; lister defensible guide. All grounded, none invented** |
| 6 | Data-spine verification | StreetData + Chimnie | sqm/type/beds cross-check; divergences shown (glass box over the spine) |
| 7 | Solar & energy | Google Solar (+ Chimnie rebuild/roof) | roof potential, kWh/yr, panel config, payback financials |
| 8 | Comparable evidence | HMLR + PropertyData + StreetData neighbour £/sqm | sortable; click → HMLR record |
| 9 | Full material information | StreetData + Chimnie | council-tax annual £, lease term/details, EPC current+potential, subsidence |
| 10 | Location & connectivity | Distance Matrix + Street View + Static Map | travel times to user anchors (work/school/station) + frontage + branded map |
| 11 | Live positioning | PropertyData listings | asking-vs-sold band, days on market, stuck stock |
| 12 | What people say | live Reddit via Hit MCP | sentiment beside the figure (never value evidence) |
| **13** | **PLAN OF ACTION (per role)** | persona × all of the above | **written, numbered strategy for BUYING / SELLING / LISTING: the price to put forward, timing, leverage, negotiation levers, costs (SDLT/CGT/fees), next steps. Built on `engine.summary()` audience framing** |
| 14 | Narrative | Gemini | plain-English summary grounded in `summary()`, honesty-guarded |
| 15 | Audio walkthrough | Voxtral (on key) | spoken glass-box |
| 16 | Market analysis | macro + demand + Reddit + positioning | `market_analysis.py` synthesis |
| 17 | References | shared `references()` | every source cited |
| — | Deliverables | — | interactive single-file HTML app + PDF + audio + hosted link + persisted/audited |

---

## 6. Honesty rules carried through BOTH tiers

1. The figure anchors on sold evidence in BOTH tiers — Lite carries the accurate sold-anchored
   `engine.value()` figure; Pro adds a disclosed AVM cross-check. Area context never moves
   low/high/central/guide in either tier.
2. The scenario matrix and the action plan are DERIVED from the real figure + positioning +
   macro — they reframe and strategise around the number, they never invent a new number.
3. Chimnie's AVM stays behind `CHIMNIE_AVM_ANCHOR` until one live call verifies the schema.
4. Every divergence between sources is shown and attributed, never silently reconciled.
5. Every section that has no data renders an honest "not available" state — never faked.
6. References cite only sources actually present in that report.
7. Bulk blog = Lite = free spine only, £0. Enrichment providers (StreetData, Chimnie, billing
   Google incl. Solar) fire on the Pro/on-demand path only.

---

## 7. Build order (locked)

Pro-spine first (the three things that make Pro "too good to be true"), then the arsenal
clients, then the tier plumbing. Lite stays the £0 lead-gen weapon throughout.

1. **`tier` flag, single source of truth** — one `tier='lite'|'pro'` threaded through
   `engine.summary` / `report.build` / `interactive_chart` / blog, driving which sections +
   sources render and which enrichment gates flip. Everything below slots into it.
2. **`scenario.py` — scenario pricing matrix** — quick-sale floor / realistic guide /
   aspirational ceiling, each with expected days-on-market + net proceeds; buyer offer / ceiling
   / headroom; lister defensible guide. Pure derivation from `low/high/central/guide` +
   positioning + macro. Pro section 5.
3. **`action_plan.py` — per-role plan of action** — numbered BUYING / SELLING / LISTING
   strategy built on the `audience` framing + the scenario matrix + costs (SDLT/CGT/fees).
   Pro section 13, the dossier's spine.
4. **Price-influence ledger** — Pro section 4: assemble every price-moving factor already in
   `summary()` + enrichment, each with source + direction of effect.
5. **`solar.py`** — Google Solar client (access live), best-effort `{ok,...}`, into
   `area_context` + Pro "Solar & energy" panel. Closes the gap caught today.
6. **Data-spine verification panel** — surface StreetData/Chimnie attribute divergences in Pro.
7. **EPC_KEY** register + `epc.py` direct floor-area/EPC firm-up (Lite + Pro).
8. On Chimnie key: verify schema → `CHIMNIE_ENRICH=1` → (after figure checks out)
   `CHIMNIE_AVM_ANCHOR=1`.
9. Optional wow-factor later: enable Aerial View / Map Tiles in the console.
