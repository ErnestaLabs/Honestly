# HONESTLY BOT — FULL ARCHITECTURE & API SPECIFICATION
## Research / Build Prompt

---

### THE GOAL

Build a Telegram bot that is architecturally, mechanically, structurally, effectively, and actually superior to every UK property valuation tool that actually charges money.

**The paid competitors (not free tools like Zoopla/Rightmove — those compete for attention, not revenue):**

1. **Sprift** — £125/month for estate agents. 300+ data points per property. Interactive reports. NOT consumer-facing, NOT a bot, NOT pay-per-use. Reddit says: "It's not an official search pack, more of a marketing tool for agents." Honestly can undercut on price (£30/mo Pro vs £125/mo) and beat them on delivery channel (Telegram vs emailed PDF).

2. **RICS Surveyors** — £500-£1,500 per professional valuation. The high-end alternative. Slow (7-14 day wait), expensive, but carries legal weight. Honestly's target: the "I want to know before I pay a surveyor" segment.

3. **Estate agent "free" valuations** — Free upfront, but cost 1-2% commission (£4k-£8k on a £400k house). The most expensive option disguised as free. Honestly attacks this directly: "Pay £5 for the truth, not £8k for a sales pitch."

4. **Homedata** — New UK property data API. 29M properties. Free tier (100 calls/month). API-based, could build their own bot. Directly in Honestly's space. They're a data provider that could become a competitor.

5. **PropertyData** — API pricing for developers/agents. NOT consumer-facing. Honestly uses their API — they're a supplier, not a competitor. But if they build a consumer bot, they become one.

6. **Chimnie / PriceHubble / BatchData** — Data APIs and comparison tools. Developer/agent-facing. Not consumer bots.

**The competitive landscape:**
- Sprift is the closest paid competitor (same data, different delivery, 4x the price)
- RICS surveyors are the premium alternative (10x the price, 100x the wait)
- Estate agents are the hidden-cost alternative (free now, £thousands later)
- Homedata is the emerging threat (could build a bot tomorrow)
- Zoopla/Rightmove are irrelevant for revenue — they're free and users don't trust them anyway

**Honestly's position:**
- Cheaper than Sprift (£30/mo vs £125/mo)
- Faster than surveyors (30 seconds vs 7-14 days)
- Honest than estate agents (glass box vs sales pitch)
- Consumer-native (Telegram bot vs PDF report vs phone call)
- Pay-per-use available (nobody else offers £5 single valuations)

Currently Honestly has:
- A working valuation engine (`engine.py`) hitting PropertyData API
- A raw Telegram bot (`bot.py`) over urllib
- Audio walkthroughs (Mistral TTS)
- Street View images (Google Static API)
- Reddit intel module (`reddit_intel.py`)
- PDF/HTML reports (`report.py`)
- Card image generation (`cardimg.py`)
- Hosted on VPS 187.77.100.209

It needs to be transformed into a bot that users cannot leave because no competitor offers the complete package.

---

### SECTION 1: ALL CURRENT APIS

Map every API currently used by Honestly. For each one document:

**PropertyData API** (`api.propertydata.co.uk`)
- Endpoints used: `address-match-uprn`, `uprns`, `uprn`, `sold-prices`, `sold-prices-per-sqf`, `prices`, `valuation-sale`, `demand`
- What each returns
- How the engine chains them together (address → UPRN → sold comparables → valuation → market adjustment)
- Rate limits
- Cost per call
- Coverage gaps (areas with thin data)

**Mistral TTS API** (`api.mistral.ai/v1/audio/speech`)
- What it generates: spoken walkthrough of valuation
- Cost per generation
- Quality compared to alternatives (OpenAI TTS, ElevenLabs)

**Google Maps Platform (GOOGLE_MAPS_API_KEY) — 38 APIS ENABLED, ONLY 2 IN USE**

Currently wired in `maps_tools.py`:
- Geocoding API — address → lat/lng (used in engine, no direct user-facing output)
- Street View Static API — frontage photo for the valuation card (8 requests total, 157ms median)
- Maps Static API — map images for PDF reports (used but low volume)
- Routes API — optimised door-knock route for agents (1 request total, 196ms median)
- Places API (New) — address lookup / nearby search (wired but zero usage)

**APIs enabled with ZERO usage — free firepower sitting on the table:**

| API | What it would add | Priority |
|-----|------------------|----------|
| **Gemini API** | Generate report narrative from valuation data. Answer follow-up questions conversationally. Analyse property descriptions for condition/clues. Replace string formatting with intelligent prose. | **CRITICAL** |
| **Address Validation API** | Validate user address BEFORE hitting PropertyData. Saves money on bad lookups. Catches typos. Suggests corrections. Address-level, not postcode. | **HIGH** |
| **Places API** (original) | Nearby amenities: schools, stations, shops, parks, cafes. Map these on the valuation card. Sprift doesn't do this. | **HIGH** |
| **Distance Matrix API** | Commute times, school run duration, transport links from the property. "17 min to Canary Wharf by tube." | **HIGH** |
| **Google Sheets API** | Export valuation data to Google Sheets for agents/investors. Portfolio tracking. Automated weekly market reports. | **MEDIUM** |
| **Google Drive API** | Store reports, share as Drive links instead of file attachments. Version history. | **MEDIUM** |
| **Gmail API** | Alternative delivery: email the report. Send follow-ups. Re-engagement for free users. | **MEDIUM** |
| **Solar API** | Solar panel potential for the property. Unique data point no competitor offers. Green angle. | **MEDIUM** |
| **Air Quality API** | Air quality data in the report. Another unique differentiator. | **LOW** |
| **Directions API** | Route planning for agents (alternative to Routes API). Commute time display. | **LOW** |
| **Google Calendar API** | Schedule viewings, reminders, subscription renewal. | **LOW** |
| **Maps JavaScript API** | Interactive map on a web frontend (if built). | **FUTURE** |
| **Google Ads API** | Marketing Honestly. Not for product features. | **FUTURE** |
| **Weather API / Pollen API / Time Zone API** | Niche additions to reports. Differentiators for specific user segments. | **NICHE** |
| **Navigation SDK / Maps SDK / 3D SDK** | Mobile app future. Not relevant for MVP. | **FUTURE** |

**Key insight:** 38 APIs are already enabled and PAID FOR. The only cost is usage. Honestly could add Gemini-generated narratives, Places-powered amenity maps, Address Validation pre-checks, and Distance Matrix commute times for pennies. Sprift doesn't do any of this. Zoopla doesn't either.

**Telegram Bot API** (direct, no library)
- Methods used: sendMessage, sendPhoto, sendDocument, sendAudio, answerCallbackQuery, createInvoiceLink, getUpdates
- Payment flow: Telegram Stars → createInvoiceLink → pre_checkout_query → successful_payment
- How the raw implementation differs from using python-telegram-bot
- Bot rate limits

---

### SECTION 2: ADDITIONAL PROPERTY DATA APIS TO INTEGRATE

For each API below, research: cost, coverage, endpoint list, what it adds that PropertyData doesn't have, integration complexity:

**HM Land Registry direct API** (free but slower)
- Does it offer anything PropertyData doesn't?
- Is there a direct API or only bulk downloads?

**EPC Register API** (epc.opendatacommunities.org)
- What does it return that PropertyData's EPC data doesn't?
- Can Honestly pull EPC certificates directly for the report?

**Council Tax bands API** (gov.uk)
- Free. What does it add to a valuation report?
- Is it address-level or postcode-level?

**Crime data API** (data.police.uk)
- Free. Does it add differentiation (safety scores per area)?
- How granular?

**School catchment / Ofsted API**
- What APIs exist for school performance data?
- Cost?
- Does Zoopla or Rightmove already offer this?

**Flood risk API** (gov.uk)
- Free. Does it add valuation context?
- Is it address-level?

**Broadband availability API**
- Does it matter for property buyers?
- What APIs exist?

**Planning permission API**
- What's available? Cost?
- Does it add competitive differentiation?

**Transport / walkability / PTAL scores**
- TfL API for London
- What exists outside London?

**Property auction data**
- Does an API exist?
- Does it add value for investors?

---

### SECTION 3: AI / MACHINE LEARNING APIS

**Valuation improvement APIs**
- Are there ML models that improve on PropertyData's AVM?
- What would it take to train a custom model on Honestly's accumulated data?

**Image analysis APIs**
- Can Honestly accept a property photo and extract condition, style, features?
- Google Vision API? Custom model?
- What would this add to valuation accuracy?

**Natural language APIs**
- Is there a way to generate the report narrative automatically?
- Is current approach (string formatting) sufficient or should it switch to LLM-generated narrative?

**Conversational AI APIs**
- Could the bot handle follow-up questions conversationally?
- What would that architecture look like?

---

### SECTION 4: PAYMENT & MONETISATION

**Payment stack (3 channels):**

**1. Telegram Stars** — already built into `bot.py`
- Pricing: Valuation pack ⭐300 (~£5), Full pack ⭐600 (~£10), Pro ⭐1800/mo (~£30)
- Intro discount toggle (`bot.INTRO`) at 50%
- Flow: createInvoiceLink → user pays Stars → bot receives → tracked via `_subscriber_set` / `_subscriber_check` / `_subscriber_scan`
- Star/GBP: ~60 Stars per £1 via `STARS_PER_GBP`
- First valuation free per user
- Daily renewal heartbeat already coded
- No card processor needed, Telegram handles it

**2. PayRequest.me** — needs integration
- Handles fiat (card, Apple Pay, Google Pay) and crypto
- What's the integration path? API docs? Webhooks?
- How does pricing map to the same packs (⭐300/600/1800)?
- Does PayRequest handle subscription management or just one-time?
- How does the bot detect payment completion from PayRequest?
- What's the cut/fee compared to Stars?

**3. Combined flow:**
- User chooses payment method (Stars / PayRequest fiat / PayRequest crypto)
- Same product packs across all channels
- Subscription state unified regardless of payment method
- Payment history tracking per user across all channels

**What needs improvement:**
- Subscription database: currently in-memory, needs persistent storage (SQLite/Supabase)
- Pro tier enforcement: needs DB-backed expiry
- Usage tracking: valuations per user, free limit enforcement
- Abandoned cart handling

---

### SECTION 5: MESSAGING CHANNEL APIS

**Current: Telegram Bot API only**

**WhatsApp Business API** (should add)
- Cost per message (marketing: $0.025-$0.1365, utility: $0.004-$0.0456)
- Message template approval process
- Session window (24-hour free customer support window)
- Integration path: Composio WhatsApp toolkit or direct API
- How WhatsApp valuations would differ from Telegram (format, length, interactivity)

**Web frontend** (should add)
- Single-page app for valuation reports (deeper than Telegram can display)
- Interactive chart (plotly/d3) vs static chart (matplotlib)
- PDF download
- Report sharing (link-based)

**Mobile app** (future)
- React Native vs Flutter
- What justifies a native app over Telegram + Web?

---

### SECTION 6: DATABASE & PERSISTENCE

**Current: no database** — everything runs in-memory per valuation

**Database architecture needed:**
- User profiles: user_id, audience preference, valuation history, subscription tier, star balance
- Valuation cache: address → result (avoid re-running engine for repeated queries)
- Subscription tracking: user_id, plan, start_date, renewal_date, status
- Payment history: user_id, amount, product, timestamp
- Saved properties: user_id, address, valuation_snapshot, saved_at, alert_price

**Database options compared:**
- SQLite: simple, file-based, no server, single-writer, good for single-process
- Supabase: hosted PostgreSQL, row-level security, real-time subscriptions, free tier available
- PostgreSQL direct: more control, more operations overhead
- Which is right for Honestly given VPS hosting?

---

### SECTION 7: QUEUE & SCALING ARCHITECTURE

**Current bottleneck:** One valuation = one blocking API chain. No concurrency. No queue.

**Architecture needed:**
- Valuation queue: user submits address → queued → processed → notified
- Why: PropertyData API calls take 3-10 seconds. Multiple concurrent users would block.
- Queue options: Redis (in-memory, fast), PostgreSQL (persistent, simpler)
- Async delivery: process valuation → notify user via bot (don't make them wait in the HTTP request)
- Webhook pattern: user sends address → bot acknowledges → bot processes → bot sends result

**Redis integration**
- What does Redis add beyond a queue? (session cache, API response cache, rate limiting)
- Redis setup on VPS

---

### SECTION 8: REPORT & DELIVERABLE FORMATS

**Current:**
- Telegram card (text + photo): `cardimg.py` generates matplotlib chart → uploaded as photo
- PDF report: `report.py` generates via matplotlib + html → pdf
- Audio walkthrough: Mistral TTS → .mp3 file
- Interactive HTML: `report.py`

**Should add / improve:**
- Interactive chart (plotly) embedded in HTML report — zoom, hover, filter comparable sales
- Map view of comparables — show sold properties on a map around the subject property
- Side-by-side comparison — two addresses valued and compared
- Portfolio report — value multiple properties in one report (for agents/investors)
- Market report — valuation + area trends + Reddit sentiment + macro data in one PDF

---

### SECTION 9: OBSERVABILITY & MONITORING

**Current: none.** If the bot goes down or an API fails, nobody knows.

**What's needed:**
- Uptime monitoring: is the bot process running?
- API health checks: PropertyData responding? Mistral responding? Google Maps responding?
- Valuation latency tracking: how long per valuation, per API call
- Error logging: structured logs per valuation (what failed, why)
- Alerting: if error rate > X% in Y minutes, notify handler
- Usage analytics: how many valuations/day, conversion rate (free → paid), most popular audience

**Tooling options:**
- Self-hosted: Prometheus + Grafana
- Simple: Python logging + log rotation + periodic health check script
- Lightweight: healthcheck.io + structured logging

---

### SECTION 10: COMPETITIVE DIFFERENTIATORS — THE KNIFE

**What Honestly has that NO competitor offers:**

1. **Glass-box methodology** — Zoopla shows a number. Honestly shows 159 comparable sales, £/sqm calculation, market adjustment, and the working. This is the single biggest competitive advantage. Document it explicitly.

2. **Multi-audience output** — Same engine, three different views (vendor/buyer/agent). No competitor does this.

3. **Reddit market pulse** — Real-time sentiment from actual buyers/sellers. Zoopla doesn't know what people are saying in the market today. Honestly does.

4. **Audio walkthrough** — Nobody else reads the valuation to you while you're driving.

5. **Telegram-native** — No app install. No account creation. Send an address, get a valuation. The friction is zero.

6. **First valuation free, then pay-as-you-go** — No subscription lock-in for casual users. No competitor offers single-valuation purchase.

**What would make it unbeatable:**

- **Price alerts** — "Tell me when properties in this postcode drop below £X"
- **Watchlist** — Save addresses, auto-refresh valuations monthly
- **Market report subscription** — Weekly area update: what sold, what listed, sentiment shift
- **Comparable map** — See the sold evidence on a map, not just a list
- **Confidence score** — "This valuation has high/medium/low confidence based on 159 comparables vs 3 comparables"
- **Lender comparison** — "Based on this valuation, here's what each lender might offer"
- **Stamp duty calculator embedded** — Inline, not a separate tool
- **Chain health check** — "Your chain has 3 links. The weakest link is [X]. Here's the risk."

---

### OUTPUT REQUIREMENTS

Return three deliverables:

1. **`honestly-api-inventory.md`** — Complete, exhaustive list of every API currently used + every API that should be added, with cost, coverage, integration complexity, and priority ranking

2. **`honestly-bot-architecture.md`** — Full system architecture diagram (text-based), data flow, component diagram, queue architecture, database schema, deployment topology

3. **`honestly-competitive-knife.md`** — The positioning document: what Honestly has that nobody else does, what to build next to extend the gap, exact messaging for each competitor weakness

---

### SECTION 11: FREE API HUNT — BEAT THE GIANTS FOR PENNIES

This is a dedicated research track. The goal: find every free, official UK government and public data API that can be layered into Honestly's valuations to create differentiation that competitors can't match without spending millions.

**The strategy:** Zoopla, Rightmove, and Sprift all use the same commercial data sources. They can't afford to integrate 50 free government APIs because they're bloated enterprises. Honestly, running lean on a VPS, can integrate ANYTHING that has a free tier.

**Hunt criteria:**
- Must be free or have a generous free tier
- Must have a documented REST API (not just bulk downloads)
- Must be UK-specific (or adaptable to UK)
- Must add real value to a property valuation report (not just noise)
- Priority: APIs that produce a number, a date, or a map point (easy to display)

**Categories to search (each with specific APIs to find):**

**Environment & Climate (free, gov.uk):**
- Flood risk by postcode — gov.uk API exists, is it address-level?
- Air quality — is there a free UK AQ API beyond Google's?
- Solar potential — is there a free UK-specific solar API beyond Google's?
- Energy performance — EPC Register API, but is there a richer one?
- Green belt / conservation area boundaries — API?
- Noise pollution maps — API?
- Tree preservation orders — API?

**Transport (free):**
- TfL API — Tube/rail/bus stops near an address (free, no key)
- National Rail API — station proximity and commute times
- Bus stops / routes — what API exists outside London?
- Cycle routes / bike share — API?
- Road traffic data — average speeds near the property?
- Parking zones / permit costs — API?

**Crime & Safety (free):**
- Police UK API (data.police.uk) — street-level crime, outcomes, neighbourhood policing
- Fire station locations — API?
- Hospital A&E waiting times — proximity to the property?
- Flood warning areas — API?

**Education (free):**
- Ofsted reports API — does one exist?
- School catchment area boundaries — API or shapefile?
- School performance data — possible via gov.uk data?
- University proximity — free but easy to hardcode

**Local Amenities (free):**
- NHS services — GP, dentist, pharmacy near the address
- Libraries, leisure centres, parks — OpenStreetMap?
- Supermarket proximity — free via OSM or Google Places
- Postcode to council tax band — gov.uk
- Council tax rates by area — free data

**Planning & Development (free):**
- Planning application search by postcode — exists (gov.uk)
- Permitted development rights checker — free
- Local plan allocations — free data
- Building control applications — free data

**Demographics (free):**
- ONS / Nomis API — census data, population stats by postcode
- Index of Multiple Deprivation — free data by postcode
- House price index by region — gov.uk free
- Rental market data — private rental index

**Maps & Location (free):**
- OpenStreetMap Overpass API — completely free, no key, unlimited. Can extract ANYTHING near a property (parks, schools, train stations, bus stops, pubs, restaurants, GPs, dentists, supermarkets, police stations, post offices, places of worship). This is the single most powerful free API for what Honestly needs.
- OS Maps API — Ordnance Survey has free tiers
- Postcodes.io — free postcode lookup, geolocation, area data (completely free, unlimited, no key)
- MapTiler — free tier for map tiles

**Property-Specific (free):**
- HM Land Registry Price Paid Data — free bulk download (updated monthly). The raw data PropertyData resells.
- HM Land Registry Transaction Data API — does a direct API exist or only CSV download?
- EPC Register — free per-property lookup, rate limited but free
- Council Tax bands — free via various sources
- Planning portal — free planning application search

**Weather (free):**
- Met Office API — free tier for UK weather data
- OpenWeatherMap — free tier, 60 calls/minute

**Required output for each API found:**
- API name + URL
- Free tier limits (calls/month, rate limits)
- Authentication required? (key, OAuth, or none)
- What data it returns per property/address
- How it would display in a Telegram valuation card
- Implementation effort (easy: 1-2 hrs / medium: 4-8 hrs / hard: 2+ days)
- Single greatest value: "This one API alone would let Honestly show ________ that no competitor shows"

**The killer insight to find:**
Is there a single free API that, if integrated, would let Honestly claim "the most comprehensive property report in the UK" for free? Postcodes.io + OSM Overpass + Land Registry + EPC + Police UK already covers location, amenities, sold prices, energy efficiency, and crime — all free. That might already be the answer.
