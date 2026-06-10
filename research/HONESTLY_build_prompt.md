# PROJECT HONESTLY BOT — FULL ARCHITECTURE & API SPECIFICATION (Research / Build Prompt)

> Source: user-supplied build/research prompt, stored 2026-06-10. This is the canonical spec
> that the system is being built against, and the prompt fed to the hit MCP strategist.

## THE GOAL
Build a Telegram bot that is architecturally, mechanically, structurally, effectively, and
actually superior to every UK property valuation tool that exists — free or paid.

### Competitive landscape
**Free (compete for attention + trust):**
- **Zoopla** — free automated valuations. Black box. Distrusted ("sudden £20k drop, no
  explanation"). Honestly beats it by showing the working.
- **Rightmove** — free instant valuation. Same black-box problem. No methodology disclosure.
- **Nationwide HPI / Halifax HPI** — free index-based. Postcode-level only, not property-specific.

**Paid (compete for revenue):**
- **Sprift** — £125/mo for agents. 300+ data points, interactive reports. Not a bot, not
  pay-per-use, not consumer-facing. "Marketing tool for agents, not a search pack."
- **RICS Surveyors** — £500-£1,500 per valuation. Slow (7-14 days). Premium alternative.
- **Estate agent "free" valuations** — actually 1-2% commission (£4k-£8k on a £400k house).
  Most expensive option disguised as free.
- **Homedata** — UK property data API. 29M properties, free tier (100 calls/mo).
- **PropertyData** — developer API. Supplier, not competitor (unless they build a consumer layer).
- **Chimnie / PriceHubble / BatchData** — data APIs / comparison tools, developer/agent-facing.

### Honestly's position
- Vs free: shows the working (glass box beats black box).
- Vs Sprift: £30/mo vs £125/mo, Telegram vs PDF, consumer + agent vs agent-only.
- Vs surveyors: 30 seconds vs 14 days, £5 vs £500+.
- Vs estate agents: pay £5 for truth vs pay £8k for a sales pitch disguised as free.

## SECTION 1: ALL CURRENT APIs
Map every API currently used. For each: endpoint, what it returns, how it's called, cost,
coverage gaps, rate limits.
- **PropertyData** (api.propertydata.co.uk) — endpoints: address-match-uprn, uprns, uprn,
  sold-prices, sold-prices-per-sqf, prices, valuation-sale, demand. Chain: address → UPRN →
  comparables → valuation → market adjustment. Cost/call, rate limits, coverage gaps
  (rural/flats/new builds). Better/cheaper alternatives (Homedata?).
- **Mistral TTS** (api.mistral.ai/v1/audio/speech) — generation cost; quality vs OpenAI TTS /
  ElevenLabs / Amazon Polly.
- **Google Maps Platform** — 38 APIs enabled, only ~4 in use. Wired: Geocoding, Street View
  Static (8 reqs, 157ms median), Maps Static, Routes (1 req, 196ms median), Places (New)
  (wired, zero usage).
  - **Zero-usage free firepower:** Gemini (CRITICAL — narrative + follow-up + condition
    analysis, replace string formatting), Address Validation (HIGH — validate before
    PropertyData), Places original (HIGH — amenities map), Distance Matrix (HIGH — commute
    times), Google Sheets/Drive/Gmail (MEDIUM), Solar (MEDIUM — unique), Air Quality (LOW),
    Directions (LOW), Calendar (LOW), Maps JavaScript (FUTURE), Ads (FUTURE), Weather/Pollen/
    Time Zone (NICHE), Navigation/Maps/3D SDK (FUTURE).
  - **Key insight:** 38 APIs already enabled and PAID FOR; only cost is usage. Gemini
    narratives, Places amenity maps, Address Validation pre-checks, Distance Matrix commute
    times for pennies. Sprift/Zoopla do none of this.
- **Telegram Bot API** (direct urllib, no library) — methods: sendMessage, sendPhoto,
  sendDocument, sendAudio, answerCallbackQuery, createInvoiceLink, getUpdates. Payment:
  Stars → createInvoiceLink → pre_checkout_query → successful_payment. Raw vs
  python-telegram-bot; rate limits; polling vs webhook.

## SECTION 2: ADDITIONAL PROPERTY DATA APIs
For each: cost, coverage, endpoints, what it adds over PropertyData, integration complexity,
priority. HM Land Registry direct; EPC Register (epc.opendatacommunities.org); Council Tax
bands (gov.uk); Crime (data.police.uk); School catchment/Ofsted; Flood risk (gov.uk);
Broadband availability; Planning permission; Transport/walkability/PTAL (TfL for London);
Property auction data.

## SECTION 3: AI / MACHINE LEARNING APIs
Valuation improvement (ML beyond PropertyData AVM; custom model on accumulated data); Image
analysis (property photo → condition/style/features; Google Vision / custom); Narrative
generation (LLM via Gemini — cost vs quality vs hallucination control); Conversational
follow-up (multi-turn architecture).

## SECTION 4: PAYMENT & MONETISATION
Three channels: (1) **Telegram Stars** — built in bot.py; Valuation ⭐300/£5, Full ⭐600/£10,
Pro ⭐1800/mo (~£30); intro 50% toggle; createInvoiceLink → tracked via
_subscriber_set/_check/_scan; ~60 Stars/£1 (STARS_PER_GBP); first valuation free; daily
renewal heartbeat; no card processor. (2) **PayRequest.me** — fiat + crypto; integration path,
docs, webhooks; map to same packs; subscription vs one-time; payment-completion detection;
fee vs Stars. (3) **Combined** — user picks method; same packs; unified subscription state;
per-user cross-channel history. **Improve:** persistent subscription DB (SQLite/Supabase);
DB-backed Pro expiry; usage tracking + free-limit enforcement; abandoned cart.

## SECTION 5: MESSAGING CHANNEL APIs
Current: Telegram only. **WhatsApp Business API** — per-message cost, template approval,
24h session window, Composio toolkit or direct API, format constraints. **Web frontend** —
SPA for deeper reports; interactive chart (plotly) vs static matplotlib; PDF download; link
sharing. **Mobile app (future)** — RN vs Flutter vs nothing.

## SECTION 6: DATABASE & PERSISTENCE
Current: none, all in-memory, no history. Needed: Users (id, audience_preference,
valuation_history, subscription_tier, created_at); Valuation cache (address_hash → result
JSON → created_at); Subscriptions (user_id, plan, start, renewal, status); Payments (user_id,
amount, product, provider, timestamp); Saved properties (user_id, address, snapshot, saved_at,
alert_price). Options: SQLite / Supabase (hosted Postgres, free tier) / PostgreSQL.

## SECTION 7: QUEUE & SCALING ARCHITECTURE
Bottleneck: one valuation = one blocking PropertyData chain (6-8 calls), no concurrency,
10-30s wait. Needed: valuation queue (submit → queued → async → notify); Redis (fast) or
Postgres (persistent); async delivery; webhook vs polling. Redis roles: queue, 24h
PropertyData cache, session store, rate limiter.

## SECTION 8: REPORT & DELIVERABLE FORMATS
Current: Telegram card (text + matplotlib chart photo); PDF report; audio walkthrough (Mistral
TTS mp3); interactive HTML. Should exist: interactive chart (plotly, zoomable/filterable
comparables); comparable map (sold properties plotted around subject); side-by-side comparison
of two addresses; portfolio/batch report; combined market report (valuation + area trends +
Reddit sentiment + macro).

## SECTION 9: OBSERVABILITY & MONITORING
Current: zero. Needed: process monitoring (is bot.py running?); API health checks
(PropertyData/Mistral/Maps); latency tracking; structured error logging per valuation;
alerting (error rate > X% in Y min); usage analytics (valuations/day, free→paid, popular
audiences). Options: simple (Python logging + healthcheck) / medium (healthchecks.io + JSON
logs) / heavy (Prometheus + Grafana — overkill for single VPS).

## SECTION 10: THE COMPETITIVE KNIFE
**Has that no competitor offers:** glass-box methodology (159 comparables, £/sqm, market
adjustment, the working); multi-audience output (vendor/buyer/agent from one engine); Reddit
market pulse; audio walkthrough; Telegram-native (zero friction, no install/account/email);
pay-per-use (£5 single vs Sprift £125/mo vs surveyor £500+ vs agent £8k commission).
**Would make it unbeatable:** price alerts; watchlist (monthly auto-refresh); market report
subscription; comparable map; confidence score ("High confidence — 159 comparables");
chain health check; inline stamp-duty calculator; affordability check.

## SECTION 11: FREE API HUNT — BEAT THE GIANTS FOR PENNIES
Strategy: Zoopla/Rightmove/Sprift share commercial sources and are too bloated to integrate
50 free gov APIs. Honestly on a lean VPS can integrate anything with a free tier. Criteria:
free/generous tier; documented REST API; UK-specific; adds real value; priority to APIs that
produce a number, a date, or a map point.
- **Environment/Climate:** Flood risk (gov.uk); air quality; solar potential; EPC Register;
  green belt/conservation boundaries; noise pollution; tree preservation orders.
- **Transport:** TfL (free, no key); National Rail; bus stops/routes; cycle routes; road
  traffic; parking zones.
- **Crime/Safety:** Police UK (data.police.uk); fire station locations; hospital A&E waits;
  flood warning areas.
- **Education:** Ofsted reports; catchment boundaries; school performance (gov.uk); university
  proximity.
- **Amenities:** NHS (GP/dentist/pharmacy); libraries/leisure/parks (OSM); supermarkets;
  council tax band (gov.uk); council tax rates.
- **Planning/Development:** planning application search; permitted development checker; local
  plan allocations; building control.
- **Demographics:** ONS/Nomis (census); Index of Multiple Deprivation; regional HPI; rental
  index.
- **Maps/Location:** **OSM Overpass** (free, no key, unlimited — any POI); OS Maps (free
  tiers); **Postcodes.io** (free, unlimited, no key); MapTiler.
- **Property-specific:** HM Land Registry Price Paid (free monthly bulk — the raw data
  PropertyData resells); HM Land Registry Transaction Data API; EPC Register (rate-limited
  per-property); council tax bands; planning portal.
- **Weather:** Met Office (free tier); OpenWeatherMap (free, 60/min).
- For each: name + URL; free-tier limits; auth (key/OAuth/none); data returned per
  property/address; how it displays in a Telegram card; effort (easy 1-2h / medium 4-8h /
  hard 2+ days); single greatest value.
- **Killer insight to find:** is there one free API that lets Honestly claim "the most
  comprehensive property report in the UK" for free? Postcodes.io + OSM Overpass + Land
  Registry + EPC + Police UK already covers location, amenities, sold prices, energy
  efficiency, and crime — all free.

## OUTPUT REQUIREMENTS — three deliverables
1. **honestly-api-inventory.md** — exhaustive list of every API used + every API to add, with
   cost, coverage, integration complexity, priority ranking.
2. **honestly-bot-architecture.md** — full text-based system architecture, data flow,
   component diagram, queue architecture, database schema, deployment topology.
3. **honestly-competitive-knife.md** — positioning: what Honestly has that nobody else does,
   what to build next to extend the gap, exact messaging for each competitor weakness.
