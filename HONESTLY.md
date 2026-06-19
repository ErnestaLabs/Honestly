# HONESTLY — system source of truth (LLM-wiki)

> The compiled map of the system. Read this first; update it after any structural change.
> Sources are the code (immutable truth); this file is the synthesis. If this disagrees with
> the code, the code wins and this file is wrong — fix it.

## What it is
A UK property-valuation system, Telegram-native. Every figure traces to a verifiable official
source (primarily HM Land Registry sold data). The engine is deterministic; the LLM only
explains and frames — it never computes or moves a figure.

## Surfaces
- **Bot** (`bot.py`, long-poll): the FREE valuation lives here. Address → Lite report (PDF +
  interactive HTML) in chat. The trust hook. After the value moment: ONE clean offer.
- **Mini App** (`webapp/index.html`, served by `server.py` at `/app`): → becoming a **Pro-gated
  property workspace** (see Strategy). Today: valuation form + storefront catalogue.
- **Landing** (`site/index.html`): marketing + the hermes widget that hands an address to the bot.
- **Blog** (`site/blog/**`, built by `publish_daily.py`/`blog.py`): pSEO area/city reports.

## Engine (deterministic, source-backed)
- `engine.value()` → sold-evidence anchor + condition tier (+ capped/disclosed market steer on
  paid path; none in free Lite). `engine.summary(r, audience, tier)` is the ONE dict every
  surface renders — numbers never drift.
- `tier`: `lite` (free) vs `pro` (paid). Single source of truth (#68).
- Honesty contract: only condition tier + capped market steer move the figure. Crime/flood/
  planning/EPC/etc. are CONTEXT beside the figure, never inputs. No fabricated per-factor £.
- `engine.evidence_purity(r)` — % of the figure that is hard sold evidence vs disclosed
  adjustment. Replaces a vibe "confidence" on the homeowner surface.
- `engine.decision_block(d, audience)` — the "If this were our money" verdict (deterministic
  readout of the signals), personalised per profile via `engine.decision_frame`.
- `engine.factor_qa(context)` — crime/planning/flood Q→A→Evidence→So-what, each with a `flag`
  that is True only when genuinely flagged (planning apps exist, real flood). Upsell links fire
  ONLY on flagged factors.

## Profiles (audience)
buyer / vendor(seller) / agent / **investor** (inferred from the bot's "is this an investment
property?" question → `subject.investment` → investor decision frame + investor upsells).

## Catalogue + hybrid economics (the Tribute product layer)
- `catalogue.py` — ONE declarative registry of all **30 products** (buyer/seller/agent + investor
  reuses buyer), mirroring `guides.py`. Each row: `{id, profile, name, kind, included, credits,
  price_gbp, data_sources, producer}`. `kind` ∈ flagship | read | pack | bundle.
- **Pro = £14.99/mo, HYBRID** (`bot.STARS_SUB=900`, intro-independent): flagship + reads
  **included** free; packs/bundles cost **credits** (monthly pool, `bot.MONTHLY_CREDITS`, granted
  by `grant_sub`, spent via `credit_balance`/`spend_credits`/`refund_credits`); a non-subscriber
  buys any product standalone at its charm Stars price. Resolver: `catalogue.purchase_mode(uid,p)`
  → included | credits | stars.
- **Flagship = `due_diligence.py`** — the Pre-Offer Due-Diligence Dossier, profile-framed: every
  public red flag (what it means / what to ask / what to renegotiate / deal-breaker?) + the
  no-free-data questions to FORCE (knotweed, cladding, subsidence, lease). Data-gated + honest.
- Delivery: `catalogue.build(pid, ctx, d, s, profile)` dispatches by producer (dossier →
  due_diligence; decision/negotiation/timeline → engine decision modules; market → area read;
  watchlist → follow; bundle → composed). `bot.deliver_catalogue_product` sends + fires triggers.
- Buy path: Mini App → `POST /api/product` resolves the mode (included/credits → deliver now;
  stars → invoice via the existing `mbuy` intent flow → `deliver_intent` (now product-aware)).
- **Automations** (`bot.TRIGGERS`, declarative, existing-infra-first): purchase → action, fired
  after delivery. Watchlist → `follow_area`. External legs (email/Slack/SMS/Sheets) are declared
  in `EXTERNAL_TRIGGERS` and no-op + log until a Composio adapter lands (user chose Composio-later).

## Conversion (the funnel)
- Free Lite report = the hook. Deliberately excellent.
- **Never re-sell what Lite already gave.** `bot.LITE_INCLUDED` filtered out of every sellable surface.
- Legacy packs (`bot.PACKS`) + guides (`guides.py`) still exist; the **catalogue.py** registry is
  the product spine the Mini App now renders (`/api/catalogue`).
- Micro-upsells / guides: `guides.py` registry (planning_guide, flood_guide, lease_guide, …).
  Declarative — a new guide is ONE entry; catalogue + delivery + deep-link + in-report link
  all auto-wire. Delivered generically in `deliver_micro` (`guides.build_by_micro`).
- Deep-link buy triggers: `?start=buy_<id>` → `bot.begin_buy` fires the relevant offer
  (invoice if a valuation exists in chat, else primes). `buy_pro` → Pro.
- Pricing: charm everywhere via `bot._gbp`→`_charm` (£4.99 / £14.99 / £0.99). Stars (XTR),
  `provider_token=""`. Invoices go through `bot._invoice` (titles capped ≤32 — Telegram limit;
  surfaces + logs failures, never silent).
- Post-Lite: `bot.offer_next` = ONE combined offer (packs + top add-ons), not two walls.

## Persistence (`store.py`, SQLite)
appraisals (token,address,postcode,summary JSON, **chat_id** = owner), deliverables (pdf|html|…),
tokens (/r/<token>), market_analysis, events, leads, email_queue, tg_queue/tg_optout, users,
blog_posts. Owner accessors: `list_appraisals(chat_id)`, `tag_appraisal`, `share_token_for`,
`backfill_chat_id_from_source` — power the Pro workspace "my properties" list.
Retention: `tg_funnel.py` (re-engagement + `nudge_followed_areas` area-refresh pinger),
`email_funnel.py`, `follow_area`.

## Deploy
`_deploy_vps.py push` → uploads .py + webapp + site assets to the VPS, restarts `honestly`
(bot) + `honestly-web` (server). `.env`/`.vps_secret` NEVER uploaded. Mini App served at
`/app` with `Cache-Control: no-store` (so deploys aren't masked by Telegram's webview cache).

## STRATEGY (Tribute model — BUILT)
The Mini App is a **Pro-gated property workspace** (`webapp/index.html`, tabs:
Portfolio · +Value · Library · Store + a Property drill-down):
1. **Free valuation stays in the bot chat** (the hook). Unlimited for everyone.
2. **Mini App access = Pro subscription** (`gateApp` + `POST /api/me`; paywall vs workspace).
3. **Inside = one persistent property object** (auto-saved on every Pro valuation via `/api/save`)
   + the **catalogue.py** marketplace selling on action-by-action, with the hybrid credit economics.
Endpoints: `/api/me`, `/api/save`, `/api/portfolio`, `/api/property`, `/api/catalogue`,
`/api/product`. Retention: `tg_funnel.nudge_followed_areas` (area-refresh) + the nudge sequence.
Free-data enrichment: `planning_data.py` (planning.data.gov.uk constraints) is wired into
`area_context.gather` + the dossier + `brand.DELIVERABLE_MAP`. REMAINING (no free per-address JSON
API — need bulk ingestion or keys; the dossier forces these as questions today): HMLR CCOD/OCOD +
INSPIRE (bulk CSV), Companies House (free key + a company name), UKradon (HTML). `bgs.py`/
`broadband.py` are stubs (`{ok:False}`) until their real source is wired.

## Standing rules
- Read source before describing a mechanism. No invented mechanisms.
- Brand assets: use the exact files, never re-draw a logo.
- Don't sell free facts. Sell interpretation/decisions/next actions.
- Keep the suite green (`pytest -q`) before deploy.
