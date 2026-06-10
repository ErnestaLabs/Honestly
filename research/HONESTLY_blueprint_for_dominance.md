# Blueprint for Dominance — Technical Roadmap for Upgrading PROJECT HONESTLY BOT

> Source: user-supplied deep-research deliverable ("Blueprint for Dominance: A Technical
> Roadmap for Upgrading PROJECT HONESTLY BOT with Untapped APIs and Asynchronous
> Architecture"). Stored verbatim-in-substance on 2026-06-10. Directive from user: "store
> it, read it, learn it, understand it and dont take it as gospel take what works. but dont
> ignore what works." Inline `(src: ...)` markers are the research's own citations.
>
> NOTE ON STANDING: this is an external research document, not the codebase. Where it
> describes the engine, the SOURCE CODE in this repo is the single source of truth — claims
> here are cross-checked against `engine.py` / `appraise.py` before being acted on.

---

## 1. Current API Infrastructure — Asset Inventory and Gap Analysis

The system's core rests on a chain of calls to **PropertyData**, augmented by select
**Google Maps Platform** services and **Mistral** for audio. A significant portion of
paid-for capability remains untapped. The primary architectural constraint is the
**synchronous, blocking** valuation process: one request triggers a linear sequence of 6-8
API calls — a bottleneck in response time and scalability.

### PropertyData (api.propertydata.co.uk) — the central engine
The "glass box" workflow:
1. `address-match` — validate/locate a user address string against PropertyData's DB.
2. Retrieve **UPRN** (Unique Property Reference Number) for cross-referencing records (src: cambridge.org).
3. `sold-prices` — list of sold prices; `sold-prices-per-sqf` — granular per-sqft breakdown.
4. `valuation-sale` — base valuation.
5. `demand` — market adjustment to contextualize within current conditions (src: propertymarketintel.com).

This transparent step-by-step process counters the opaque "black box" valuations of Zoopla
and Rightmove — a trust-based advantage.

- **Cost model:** credit-based (PropertyData, now rebranded Homedata). A full workflow ≈ **13
  credits**. Free tier only 100 credits/month; production needs a paid tier (src: propertymarketintel.com).
- **Coverage gap:** rural areas, flats, and new builds — lower transaction frequency → less
  reliable comparable sales (a common AVM challenge globally) (src: oecd.org).

### Google Maps Platform — 38 APIs enabled, only ~4 integrated
Wired in `maps_tools.py`:
- **Geocoding API** — address → lat/lng for spatial queries/chaining (internal).
- **Street View Static API** — frontage photo on the valuation card (≈8 requests recorded).
- **Maps Static API** — map images for PDF reports (low volume).
- **Routes API** — optimised door-knock routes for agents (≈1 request).

**Highest finding: substantial underutilization of paid resources.** Enabled, zero usage:
- **Places API** — nearby amenities (schools, shops, parks) overlaid on the card. Sprift
  does not prominently do this.
- **Address Validation API** — pre-check before paid PropertyData calls; saves cost on
  invalid lookups, fixes typos.
- **Distance Matrix API** — commute times, e.g. "17 min to Canary Wharf by tube" — context
  competitors lack.

### Mistral TTS (api.mistral.ai/v1/audio/speech)
Generates an MP3 audio walkthrough of the report — a multi-modal differentiator. Needs
evaluation vs OpenAI TTS / ElevenLabs / Amazon Polly on quality, latency, cost-per-generation.

### Telegram Bot API (direct urllib, no library)
Methods: sendMessage, sendPhoto, sendDocument, sendAudio. Pro subscription ⭐600 (£10) via
`createInvoiceLink`; subscriber state via `_subscriber_set` / `_subscriber_check` /
`_subscriber_scan`. Raw implementation gives fine control but lacks the resilience/features
of an established library; **polling** is a limitation vs a **webhook** architecture for high
concurrency.

### Inventory table
| Provider | Service | Status | Function | Cost | Consideration |
|---|---|---|---|---|---|
| PropertyData (Homedata) | All endpoints | Active | Core valuation (match, UPRN, sold, valuation, demand) | Credit-based | Gaps: rural, flats, new builds |
| Google Maps | Geocoding | Active | Address → lat/lng | In 38 enabled | Low volume |
| Google Maps | Street View Static | Active | Frontage photo | In 38 enabled | Very low (8 reqs) |
| Google Maps | Maps Static | Active | Map images for PDF | In 38 enabled | Low volume |
| Google Maps | Routes | Active | Door-knock routes | In 38 enabled | Extremely low (1 req) |
| Google Maps | Places | **Inactive** | Nearby amenities on card | In 38 enabled | HIGH-priority differentiation |
| Google Maps | Address Validation | **Inactive** | Validate before lookup | In 38 enabled | HIGH-priority, cost-saving |
| Google Maps | Distance Matrix | **Inactive** | Commute times | In 38 enabled | HIGH-priority, practical context |
| Mistral | TTS | Active | Audio walkthrough | Usage-based | Compare vs OpenAI/ElevenLabs |

---

## 2. The Free API Advantage — Layering Public Data

Competitors (Zoopla, Rightmove, Sprift) are locked into expensive commercial data
partnerships. Honestly, lean on a VPS, can layer a vast array of **free official UK gov/public
datasets** to differentiate on comprehensiveness, not just price — extending the "glass box".

- **HM Land Registry Price Paid Data (PPD)** — authoritative UK residential sales, free
  monthly bulk download (src: cambridge.org). PropertyData resells this; accessing it natively
  enables custom time-series and bespoke filtering. **Hurdle:** PPD lacks UPRN → needs fuzzy
  matching (Levenshtein on concatenated address strings, ~95% confidence) to link sales.
- **EPC Register** — open APIs for property-level energy data: ratings, construction
  characteristics, floor area → running-cost and green-mortgage context (src: cambridge.org).
- **Police API (data.police.uk)** — street-level crime, outcomes, neighbourhood policing.
  **No authentication required** now (src: stackoverflow.com). Enables qualitative/quantitative
  safety scores.
- **Flood risk + Air quality** — free gov portals; environmental risk factors affecting
  long-term value/desirability.
- **Ordnance Survey OpenMap Local** — aggregated building data; free tiers for detail.
- **OpenStreetMap Overpass API** — the most powerful free tool: completely free, **no API
  key**, unlimited; extract virtually any POI near a property (GP surgeries, supermarkets,
  post offices, places of worship, leisure centres) — rivals paid Google Places at zero
  marginal cost (src: rpubs.com).

### Free-API table
| API | Source | Data | Effort | Strategic value |
|---|---|---|---|---|
| HM Land Registry PPD | gov.uk | Historical sale prices/dates | Hard (fuzzy match, no UPRN) | Authoritative, unfiltered sales history |
| EPC Register API | opendatacommunities.org | EPC ratings, construction, floor area | Easy-Medium (rate-limited) | Running-cost + green-mortgage context |
| Police UK API | data.police.uk | Street crime, outcomes, policing | Easy (no auth) | Qualitative/quantitative safety scores |
| Flood Risk API | gov.uk | Flood warning areas, risk | Easy (postcode/address) | Major environmental risk → insurance/value |
| Air Quality API | multiple | AQI real-time/forecast | Easy (free tiers) | Environmental health/livability |
| OSM Overpass API | overpass-api.de | Any POI | Medium (spatial query parsing) | Replaces paid Places at zero cost |
| Planning Portal API | planningportal.service.gov.uk | Planning applications/permissions | Easy-Medium | Development risk/opportunity |
| Council Tax Bands API | gov.uk | Current band by property/postcode | Easy | Direct financial/taxation context |

---

## 3. Architectural Overhaul — Asynchronous Processing

**Bottleneck:** monolithic synchronous model — one request → sequential 6-8 blocking
PropertyData calls; user waits 10-30s. Problems: limited concurrency (main process blocked on
I/O); poor UX (long unresponsive wait); brittle failure (one failed call → whole valuation
times out, no feedback).

**Proposed:** decouple request-handling from processing via an **async queue**.
- **Redis** as message queue (speed, in-memory, optional persistence). On submit, the bot
  immediately acknowledges ("Your valuation is being processed and will be sent shortly") and
  enqueues a job (user ID, address, unique id).
- **Background worker(s)** poll the queue, run the PropertyData chain async, handle failures
  gracefully (log, mark failed, retry) instead of propagating a fatal error. On completion,
  store result in a persistent cache keyed by `address_hash`, then send via Telegram Bot API.

**Benefits:** scalability (lightweight concurrent front, heavy work offloaded to a scalable
worker pool); reliability/observability (auto-retry, explicit per-job state); advanced
features (ready-notifications, periodic "watchlist" refresh). **Redis also serves as:** 24h
PropertyData response cache (cuts cost), session store, rate limiter.

---

## 4. Monetisation & Payment — Unified Multi-Channel

Three channels, identical packs, **unified subscription state regardless of payment method**:
Valuation pack (⭐300/£5), Full pack (⭐600/£10), Pro (⭐1800/£30). Current in-memory dicts are
insufficient (state lost on restart) → move to a managed DB (**Supabase / Postgres**).

- **Telegram Stars** — already built. `createInvoiceLink` → `successful_payment`;
  `_subscriber_set`/`_subscriber_check` track status; 50% intro toggle (`bot.INTRO`); no
  external card processor.
- **PayRequest.me** — fiat (card, Apple Pay, Google Pay) + crypto. Open questions: recurring
  vs one-time? webhook payload to confirm a transaction → parse user + plan → update the
  central subscription DB. Unified DB is the linchpin: master record of each user's status,
  start/renewal date, active plan; payment method becomes an implementation detail while
  **entitlement is the single source of truth**. Enables abandoned-cart + payment history.

### Components table
| Component | Description | Tech | Priority |
|---|---|---|---|
| Product Packs | Standard packages, all channels | Bot code | Critical |
| Subscription State | Persistent tier/expiry store | Supabase (Postgres) | Critical |
| Payment History | All transactions per user | Supabase (payments) | High |
| DB Schema | Users, Subscriptions, Payments, SavedProperties | Supabase | Critical |
| PayRequest.me | Fiat/crypto integration | PayRequest API + webhooks | High |
| Subscription Mgmt | Renewals + access enforcement | DB-backed expiry | Critical |
| Unified Access Control | Enforce by status, any method | Central DB query | Critical |

---

## 5. Advanced Capabilities — AI/ML

Evolve from data aggregator to **intelligent advisor**.

- **Gemini API (enabled, paid, unused) — highest-value, lowest-hanging fruit.** Replace
  string-formatted narrative with LLM-generated, natural-language explanation grounded in the
  structured valuation JSON. Synthesizes data points into a coherent story; powers
  **conversational follow-up** ("What was the condition of the top comparable?", "Why is
  demand high?") with multi-turn memory tied to a Redis session / DB profile. Key concerns:
  cost-per-token, latency, **hallucination control to keep text grounded in the factual data**
  (src: patsnap.com).
- **Image analysis (future)** — user uploads a property photo; **Google Vision** identifies
  features (pool, modern kitchen), assesses condition (roof, walls), suggests renovations.
  Fuse this unstructured data with PropertyData's structured data for richer valuation.
- **Custom ML model (future)** — train a proprietary model on accumulated valuations + free
  gov contextual data. Patent landscape trends toward hybrid models + explainable AI (XAI,
  e.g. SHAP) for accurate, interpretable results (src: patsnap.com). Turns data collection
  into a defensible asset.

---

## How this maps onto the EXISTING codebase (cross-check, not gospel)

The repo already implements the "glass box" engine (`engine.py` / `appraise.py`), Maps
helpers (`maps_tools.py`), Voxtral audio (`audio.py`), fpdf2 report (`report.py`), the
Telegram Stars bot (`bot.py`), live macro (`macro_live.py`), and Reddit intel
(`reddit_intel.py`). The blueprint is therefore an **expansion**, not a rebuild. Take-what-works
priorities, reconciled with what is already built:

1. **Free data spine (build first, zero/low cost):** Postcodes.io (geo), OSM Overpass
   (amenities), Police.uk (safety), EPC Register (floor area/rating), HM Land Registry PPD
   (independent sold cross-check). Each sits BESIDE the figure with its source — never silently
   moves the valuation.
2. **Activate the paid-but-unused Google APIs:** Places (amenity map), Address Validation
   (pre-check before paid PropertyData), Distance Matrix (commute context).
3. **Gemini narrative + `/ask`** with a hard honesty guard: answers ONLY from the
   `engine.summary()` dict; any figure not present in the dict is rejected.
4. **Persistence + async:** Supabase/Postgres for users/subs/payments/cache; Redis queue +
   workers so PDF/audio/fan-out run off the request path; webhook over polling at scale.
5. **PayRequest.me** for off-Telegram fiat/crypto; Stars stays in-bot; one unified entitlement.
6. **Vision + custom ML** last, and gated/disclosed — any model-derived steer stays clamped by
   the existing `apply_market` cap and is printed as a disclosed line, or it does not ship.
