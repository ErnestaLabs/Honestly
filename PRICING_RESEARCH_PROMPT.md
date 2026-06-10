# Deep-Research Prompt — Pricing for "Honestly" (UK property valuation on Telegram)

> Paste the block below into Gemini Deep Research / ChatGPT Deep Research / Claude Research.
> It is written to return a defensible, numbers-first pricing recommendation, not a generic essay.

---

## ROLE
You are a pricing strategist for UK consumer + B2B SaaS and proptech. You combine
competitive teardown, willingness-to-pay (WTP) analysis, and behavioural/psychological
pricing. You cite sources with dates and you show your working. You output concrete
numbers, not ranges of opinion.

## THE PRODUCT YOU ARE PRICING
**Honestly** is an automated, evidence-led UK residential property valuation service that
runs entirely inside a Telegram bot (@usehonestly_bot). A persona ("Hermes") takes one
address, asks who the user is (vendor / buyer / estate agent), runs a real valuation
engine, and returns a defensible figure with the full working shown ("glass box"). It is
NOT a vague online estimate (Zoopla/Rightmove-style AVM); the differentiator is *evidence
and the shown method*.

**How the number is built (the glass box, shown to the user verbatim):**
sold median (HM Land Registry comparables) → condition-adjusted (AVM anchor) →
live-market % steer → central value, plus an assessed range.

**Data + tech actually used (live, not mocked):**
- PropertyData API: sold comparables, asking/listing data, PSF, schools (Ofsted links).
- Google Maps Platform (server-side key): Geocoding, Street View frontage photo, Static
  Maps, Routes API (optimised multi-stop), keyless shareable Google Maps directions URLs.
  Available to upgrade with: Maps JavaScript API, Places API (New), Solar API, Air Quality.
- Macro context (rates/momentum), and a social-sentiment scanner (labelled as context only,
  never a valuation input).
- Voxtral TTS: a spoken audio walkthrough of the valuation (voice note).

**Deliverables (the same number for all; framing + tools differ by audience):**
1. Telegram valuation card (free first one) — range, central value, glass-box chain,
   comparables each linking to its HM Land Registry record.
2. **PDF report** — branded, evidence-backed appraisal document.
3. **Interactive HTML report** (add-on) — richer, explorable version.
4. **Spoken audio walkthrough** (voice note).
5. **Plan of action** — numbered, audience-specific (win the instruction / sell for most /
   offer from evidence).
6. **Ready-to-send email/script** (agent prospecting / vendor agent-vetting / buyer offer).
7. **Door-knock hit list + map** — up to 20 ranked nearby live listings, an optimised
   route, and (target state) an *interactive* map whose markers link to the actual portal
   listings — not just static pins.
8. Nearby schools with official Ofsted links.

**Audiences and their economics:**
- **Vendor** (consumer, one-off, high emotional + financial stakes: selling a home).
- **Buyer** (consumer, one-off, wants negotiation ammunition).
- **Agent** (B2B, repeat usage, uses it to win instructions and prospect a street — highest
  WTP and frequency; the door-knock list + email templates are revenue tools for them).

## CURRENT MONETISATION (to be validated/replaced)
- Payment rail: **Telegram Stars (XTR)** only — Telegram's mandated in-app digital-goods
  currency (Apple/Google policy). Prices must be whole numbers of Stars. The codebase
  currently assumes ~**60 Stars ≈ £1** (i.e. ~£0.0167/Star). **Verify the true current
  Star→GBP economics** (what Telegram charges users to buy Stars, the ~30% store cut, and
  what a developer actually nets per Star in GBP) and flag if 60×GBP is wrong.
- First valuation per user: **free** (the taste).
- Today's model (likely mispriced — that's why we're researching):
  - Membership £9.99/mo (⭐650) = base access to use the service (does NOT make reports free).
  - Per-valuation ladder charged on top: £2.50 PDF, £3.50 +HTML, £5.00 +plan+route, £7.50 +email.

## THE PRICING WE WANT TO PRESSURE-TEST (founder's instinct — likely too cheap)
- PDF report: **£2.99**
- HTML add-on: **+£0.99**
- Door-knock hit list: **£0.99**
- Interactive map linked to live listings: **£2.99**
- Subscription: **£9.99/mo = 2 full results/month including everything**
- All prices to be displayed as **50% off for the first month** (founder suspects base
  prices are too low and wants the discount to be real headroom, not a giveaway).

## RESEARCH OBJECTIVES (answer each, with sources + dates)
1. **Competitive price teardown.** For every realistic UK substitute, find the actual
   current price (with source + date) and what you get:
   - Free AVMs: Zoopla, Rightmove, OnTheMarket estimates.
   - Paid consumer reports: Hometrack/property reports, Mouseprice Pro, PropertyData
     subscriptions, Sprift, the Land Registry/HMLR data cost, RICS "Red Book" valuations,
     RICS condition/homebuyer survey price bands, estate-agent "free" appraisals (and what
     the agent's hidden cost/commission is).
   - Agent/B2B tools: Sprift, Nimbus, LandInsight/LandTech, GetAgent, Rightmove/Zoopla
     agent products, prospecting/letter-box tools — monthly cost and per-report cost.
   Produce a table: product | who it's for | price | unit (one-off/sub) | what's included.
2. **WTP by segment.** Estimate willingness to pay for vendor, buyer, and agent separately,
   grounded in the substitutes above and the stakes (a vendor decision concerns ~£300k–£1m;
   an agent winning one instruction is worth thousands in commission). Where is the price
   ceiling for each? Where does "too cheap to be credible" begin (price as a trust signal
   for a *valuation* product)?
3. **Is the founder's pricing too cheap?** Specifically assess £2.99 PDF / £0.99 add-ons /
   £9.99 sub against the teardown and WTP. If too cheap, give the recommended numbers and
   the reasoning. Pay special attention to: does a £0.99 / £2.99 price *undermine the
   premium, defensible, evidence-backed positioning* (anchoring/quality-cue effects)?
4. **Recommended price architecture.** Propose the full price list:
   - Per-component à la carte prices (PDF, HTML add-on, door-knock list, interactive map,
     email template, audio — or recommend bundling some).
   - The subscription: right monthly price, what's included, how many results, and whether
     to split consumer vs agent tiers (e.g. a higher "Pro/Agent" tier). Recommend annual
     pricing too.
   - Bundle vs à la carte: what should be one-off-purchasable vs subscription-only.
   Express every price in **GBP and in whole Telegram Stars** at the verified conversion.
5. **The 50%-first-month discount.** Is a 50% first-month/launch discount the right
   mechanic, or does it cheapen a trust product? Compare to alternatives (free first report
   only [already in place], time-limited founder pricing, "introductory" vs permanent,
   credits/packs). Recommend the exact discount framing and guardrails (how to show
   anchored "was/now" prices honestly and legally under UK ASA/CAP pricing-claim rules).
6. **Packaging psychology.** Recommend anchoring, decoy/good-better-best, charm pricing
   (.99 vs .00 for a premium product), and how to display Stars-priced goods so the GBP
   value is legible. Note any Telegram Stars UX constraints (minimum invoice, refunds,
   subscriptions support).
7. **Unit economics sanity check.** Given per-valuation variable costs (PropertyData API
   call, Google Maps calls — Geocoding/Street View/Static/Routes, Voxtral TTS ~£0.008,
   compute), estimate gross margin at the recommended prices and the Stars store cut. Flag
   any price that doesn't clear cost + the ~30% cut comfortably.
8. **Go-to-market price test.** Suggest 2–3 priced packages to A/B test at launch and the
   metric that decides the winner (conversion × ARPU, not conversion alone).

## OUTPUT FORMAT (required)
- **Section A — Executive recommendation:** the final price list (GBP + Stars), one-paragraph
  rationale. Lead with this.
- **Section B — Competitive teardown table** (with sourced, dated prices).
- **Section C — WTP by segment** (vendor / buyer / agent) with the reasoning.
- **Section D — Verdict on founder pricing** ("too cheap?" yes/no + by how much).
- **Section E — Discount + packaging mechanics** (incl. the 50% question and UK ASA rules).
- **Section F — Unit economics + Stars conversion** (verified £/Star, margin per product).
- **Section G — Launch price-test plan.**
- Cite every external price with a source and an access date. State assumptions explicitly.
  Prefer 2025–2026 data; flag anything older.

## CONSTRAINTS / NON-NEGOTIABLES
- Payment is Telegram Stars only; prices must round to whole Stars. Use the verified
  Star→GBP rate, not an assumed one.
- The product's brand promise is *honesty and defensibility* — pricing must not contradict
  that (no fake scarcity; the discount must be a genuine, ASA-compliant claim).
- Agents are B2B and the highest-value segment; do not price the whole product to the
  lowest-WTP consumer.
- The free first valuation stays.
