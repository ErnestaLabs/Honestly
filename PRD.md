# Honestly - Product Requirements Document

**Product:** Honestly - an honest, automated UK property-valuation service
**Surface:** Telegram bot [@usehonestly_bot](https://t.me/usehonestly_bot) (Mini App next)
**Owner:** Riccardo Minniti
**Status:** Live and healthy. This PRD transforms the strategic analysis into build-ready requirements.
**Last updated:** 2026-06-08

---

## 1. Vision

One address in, one evidence-backed valuation out. No black-box number. The comparable
sales, the condition adjustment, the live-market steer, and the exact arithmetic are all
shown. **The honesty is the product** - the moat is a glass box, not a guarded oracle.

Every figure traces to a free, verifiable public source (HM Land Registry sold prices via
PropertyData). Asking prices are treated as positioning, never as evidence.

## 2. Problem & positioning

UK valuations are either (a) free but worthless (portal "estimates", agent flattery to win
instructions) or (b) accurate but gated behind paid pro tools (Hometrack, Sprift, Acaboom)
that consumers cannot reach. Honestly delivers a defensible, audit-trail valuation to the
person who needs it, in the channel they already live in, at a price that undercuts the pro
tools while out-trusting the free ones.

| Competitor | Audience | Weakness Honestly exploits |
|---|---|---|
| Hometrack / Sprift | B2B pro | Inaccessible & opaque to consumers; expensive |
| Acaboom | Agent CRM | Sales-enablement gloss, not buyer-trustable evidence |
| Portal estimates | Consumer | Free but non-defensible, no working shown |
| PropertyData (raw) | Pro/devs | Raw data, no audience framing, no deliverable |

**Our wedge:** the exposed valuation formula + audience framing + a real deliverable, on
Telegram, for pounds not hundreds.

## 3. Audiences

The valuation is identical for everyone; the framing and the call-to-action differ.

- **Vendor** - "the value the sold evidence defends," not the highest figure to win an instruction.
- **Buyer** - "what comparable homes actually sold for," ammunition against overpaying.
- **Agent** - listing-ready material: comps table, door-knock route, material-information starter.

## 4. The deliverable (current state + requirements)

### 4.1 Shipped
- [x] Assessed range + central value, audience-framed (`engine.summary`).
- [x] Branded multi-section PDF (`report.build`): hero, exec summary, property on record,
      comparable evidence (each row a clickable HM Land Registry record), native bar chart,
      **Basis of assessment (the glass-box working)**, live positioning, net proceeds,
      methodology/limitations/sources.
- [x] Tap-interactive HTML companion chart (mobile-native, each bar opens the Land Registry record).
- [x] Keyless interactive Google Maps route link (door-knock route / mapped rivals).
- [x] Condition-adjusted AVM (needs_modernising 0.90, needs_renovation 0.80).
- [x] Reddit market-intelligence page (best-effort, context only - never a valuation input).
- [x] **NTSELAT Material Information starter (Parts A/B/C)** - facts we hold, blanks flagged
      "Confirm with seller." *(shipped this iteration)*

### 4.2 Requirements (prioritised - see Section 8 for the roadmap)
- [x] Glass-box one-liner in the bot message: the literal arithmetic
      (`sold median -> condition-adjusted -> live market % = central`). *(shipped + live)*
- [x] Schools nearby + official Ofsted report links (PropertyData schools endpoint, no new
      dependency). Bot brief + PDF section. We never assert a rating - link to source. *(shipped + live)*
- [x] **Audio walkthrough of the valuation (Voxtral TTS, Mistral)** - spoken narration of the
      glass-box working, figures reproduced verbatim. Stdlib-only client, best-effort, key-gated.
      *(shipped this iteration - Hermes-side + auto-enables in-bot when `MISTRAL_API_KEY` is set)*
- [ ] Telegram Mini App over the same `engine.summary()` - needs a hosted web surface (`server.py` seed).
- [ ] RICS surveyor sign-off bridge - needs a surveyor network + commercial/legal arrangement.

## 5. Monetisation (Telegram Stars only - XTR, `provider_token=""`)

Non-negotiable: in-app digital goods MUST use Telegram Stars. No card/provider-token processor.

- **First valuation per user = the full kit, free** (the taste).
- **Membership £9.99/mo (⭐650) = the BASE cost to USE the service.** It does NOT make valuations free.
- **Per-valuation ladder, charged on top** (Stars = £ x 60):
  - £2.50 (⭐150) - valuation PDF only
  - £3.50 (⭐210) - + interactive HTML report
  - £5.00 (⭐300) - + action plan + door-knock route / 20 mapped targets
  - £7.50 (⭐450) - + ready-to-send email template
- Only the **PROPHET** comp code (the owner) is free, every time.

### Strategic pricing tiers (from the analysis - future, multi-surface)
These are the eventual market-facing tiers the doc proposes; the Stars ladder above is the
in-Telegram implementation. Web/Mini-App surfaces unlock these:
- **Consumer D2C** - £29-49 per report (one-off, premium single valuation).
- **Pro Investor SaaS** - £59-99/mo (unlimited valuations, portfolio, alerts).
- **White-Label B2B** - £149-199 per branch/mo (agent-branded reports).
- **RICS-signed report** - £99-149 consumer-facing; surveyor takes £45-60, we keep the spread.

## 6. Hermes - role in the architecture

**Hermes is the autonomous front-of-house agent.** Honestly's Python is the engine and the
deliverable factory; Hermes is the intelligence layer that drives it and composes the human-
facing response. Hermes is NOT a second valuation logic - it never invents numbers.

| Layer | Owner | Responsibility |
|---|---|---|
| Conversation / orchestration | **Hermes** | Reads the user, decides audience, calls the valuation tool, composes a "stunning" reply, handles follow-ups. |
| Valuation engine | `engine.py` / `appraise.py` | The single source of truth for the number. Deterministic, auditable. |
| Deliverable factory | `report.py` / `products.py` / `maps_tools.py` | PDF, HTML, route, plan, email. |
| Market intelligence (Reddit) | `reddit_intel.py` -> Hit MCP (`hitman-red`) | Sentiment/themes for context. Best-effort, never blocks, never values. |

**Hermes integration points (already built):**
- `_valuation_tool.py` - Hermes-callable: runs `engine.value` + `report.build` + `reddit_intel`
  on the live VPS over SSH, returns a structured result for Hermes to narrate.
- `_hit_sdk.py` - the MCP client wrapper Hermes/the bot use to reach the Hit (Reddit) server.
- `reddit_intel.for_area()` / `format_brief()` - the bridge; surfaced in-bot via `/pulse`.
- `_valuation_tool.walkthrough_audio()` -> `audio.py` - Hermes turns the structured result into a
  spoken walkthrough via Voxtral TTS (its own `MISTRAL_API_KEY`). The script is built from the
  engine's figures only; Hermes never narrates a number the engine did not produce.

**Hard rule for Hermes:** Hermes may frame, narrate, and route, but the valuation number,
the comparables, and the working come verbatim from the engine. Hermes must reproduce the
glass-box (never paraphrase the figure into a vibe). Reddit sentiment is labelled context,
never an input. Hermes obeys every constraint in Section 9.

## 7. Non-functional requirements

- **Stdlib-first.** Pure Python over the raw Telegram Bot API. Only runtime deps: `fpdf2`
  (PDF), `paramiko` (deploy), `mcp` (Hit bridge). Runs on a memory-constrained Linux VPS.
- **Never block a valuation.** Every enrichment (Reddit, maps, audio) is best-effort and
  degrades to empty silently.
- **Determinism.** Same address + inputs -> same number, every time, on dev and VPS.
- **Test gate.** `test_bot.py` must stay green before any deploy (currently 85+).
- **Single source of numbers.** Bot card, PDF, HTML and Mini App all read `engine.summary()`.

## 8. Roadmap (prioritised)

**P0 - moat & compliance (do now, low risk, contained):** ALL SHIPPED + LIVE
1. [x] NTSELAT Material Information starter in the PDF. *(shipped + live)*
2. [x] Glass-box arithmetic one-liner in the bot delivery message. *(shipped + live)*
3. [x] Em-dash + copy compliance sweep across the entire codebase. *(complete - only the
       report.py sanitiser, the purge-tool regex and the ban test retain the glyph, all by design)*

**P1 - enrichment (medium effort, real data sources):** ALL SHIPPED
4. [x] Schools + Ofsted section, via the PropertyData schools endpoint (no new dependency).
       Bot brief + PDF, links to the official Ofsted report. *(shipped + live)*
5. [x] Hermes narration: the glass-box chain reproduced verbatim in `_valuation_tool.compose_card`,
       with `sold_median` passed through to Hermes. *(shipped - Hermes-side tool)*

**P2 - new surfaces & premium:**
6. [x] Audio walkthrough via **Voxtral TTS (Mistral)** - `audio.py` (stdlib `urllib`, no new dep)
       narrates the glass-box chain with the engine's figures verbatim. Best-effort and key-gated:
       Hermes generates it locally with its `MISTRAL_API_KEY`; the live bot auto-enables it the
       moment that key is present in the VPS env, and silently no-ops otherwise. *(shipped)*
7. [ ] Telegram Mini App over `engine.summary()` (`server.py` is the seed). NEEDS: a hosted
       web surface (TLS domain) + Mini App registration with BotFather.
8. [ ] RICS surveyor sign-off bridge + the £99-149 signed tier. NEEDS: a surveyor partner/network
       and the commercial + PI-insurance/legal arrangement (cannot be built blind).
9. [ ] Multi-surface pricing tiers (Consumer D2C / Pro / White-Label). NEEDS: payment surfaces
       beyond Telegram Stars (web checkout) + the pricing/packaging business call.

## 9. Hard constraints (do not violate)

1. **Secrets stay in `.env`** - never in code, never echoed, never deployed. The deploy tool
   hard-blocks `.env`, `.vps_pw`, `.vps_secret` from upload.
2. **Google Maps key is unrestricted & server-side ONLY.** User-facing maps use the keyless
   `maps_tools.directions_url()`. The key must never appear in any deliverable.
3. **Digital goods = Telegram Stars (XTR), empty `provider_token`.** No card processors.
4. **No em dashes** in any copy or output. Hyphens only. (Sole exception: `report.py`'s
   `_SUBST` sanitiser, which strips them.)
5. **Membership is the base, not free valuations.** Ladder charged on top. Only PROPHET is free.
6. **Keep `test_bot.py` green** before any deploy.
7. **Reddit sentiment is context, never a valuation input.** Always labelled as such.
8. **Do not read or transmit** `_PRIVATE_notes_DO_NOT_SEND.md` or anything `_PRIVATE*`.

## 10. Success metrics

- Free-taste -> paid conversion rate (first valuation to first ladder purchase).
- Membership retention (monthly ⭐650 renewals).
- Valuations per active user / month.
- Deliverable open rate (PDF + interactive HTML taps, map link opens).
- Trust proxy: testimonials captured after the free taste.
