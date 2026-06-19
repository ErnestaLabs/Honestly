# The 10 Big Ideas / pSEO Engine - Honest Assessment

> Deliverable for task #34. The user supplied 10 programmatic content templates plus a
> pSEO engine concept ("Steal Their Traffic"), ending "obviously no need to build we have
> our tool and intelligence sources." This is the honest read: which ideas we can build
> WITHOUT fabricating data, which break a standing rule, and the build order.
>
> The single test applied to every idea: **do we actually hold the data, or would we be
> inventing it?** A pSEO page with no real data behind it is a thin doorway page Google
> penalises AND a dishonesty - both fatal to this brand. Grounded in shipped code, not
> opinion: where an idea is already built, the file/function is named.

---

## Verdict at a glance

| # | Idea | Verdict | Status / data basis |
|---|------|---------|---------------------|
| 1 | Portal Delusion Index | RULE BREACH -> reframed & shipped | Names Zoopla/Rightmove + implies a counter-valuation. Honest version already live: the **Asking vs Sold gap** chart (`blog._chart_asking_vs_sold`). |
| 6 | Livability Score | BUILD FIRST | Every input is data we pull: Police.uk, Overpass, Ofsted, Distance Matrix, DEFRA air, EA flood (`area_context.py`). Show components, never one black-box score. |
| 3 | Time Machine (historical sold) | BUILD, hard-constrained | Legitimate ONLY from dated HMLR PPD transaction rows. NOT from the HPI snapshot (one month - a trend line would be invented). |
| 7 | Yield Illusion | SHIPPED | rent data IS on PropertyData. Built: `blog._rent_section` + `_chart_gross_yield`, disclosed as PropertyData's asking-rent-based gross-yield estimate, beside the figure, never blended (#37). |
| 8a | Flood risk | BUILD | Environment Agency flood risk - we hold it (`area_context.py`). |
| 2 | True cost of ownership | REFRAME (amber) | EPC running-cost band (`epc.py`) + VOA council-tax band we hold. We do NOT hold retrofit quotes - state what EPC says, never invent a "£12k to fix it" figure. |
| 4 | FTB Reality Map | PARTIAL (amber) | Entry price + a clearly-labelled *illustrative* mortgage cost at the live BoE Bank Rate is honest. True affordability-vs-income needs ONS local income data we'd have to source first. |
| 5 | Haggling Index | REFRAME (amber) | We hold asking-median and sold-median, NOT matched asking->achieved pairs per home. "Haggle 8%" conflates two populations. Frame as the asking-vs-completion gap only. |
| 9 | Distressed Deal Radar | REFRAME (amber) | "Distressed/repossession" is a legal seller status we cannot verify - claiming it is a factual assertion about a person we don't hold. We DO hold stale stock (90+ days). Ship that; drop the "distressed" label. |
| 8b | Subsidence | HOLD | Needs BGS subsidence data we don't hold. |
| 10 | Chain Breaker Stress | HOLD | Needs fall-through / chain-break rates we don't measure. Under-offer share is a weak proxy, not chain stress. |

Three buckets: **5 buildable or built honestly now** (1-reframed, 3, 6, 7, 8a), **4 need a
reframe to stay honest** (2, 4, 5, 9), **2 are blocked on data we don't hold** (8b, 10).

---

## The two rule breaches (not building as written)

**Idea #1 "Portal Delusion Index" - two violations.** (a) It names Zoopla/Rightmove as
sources; portals are banned as data sources. (b) It implies a counter-valuation ("the
portal says X, the truth is Y") - but the blog issues no valuation. The honest version is
already shipped: the **Asking vs Sold gap** chart states the distance between vendor asking
expectation and HMLR completed prices, names no portal, and issues no figure of our own.
Same SEO pull, zero breach.

**The "Run a free Glass-Box Audit in the Honestly Telegram Bot" CTA** re-creates the
free/paid conflation killed in #30. Blog reports are free; the bot's address valuation is
the paid product. Honest CTA: "This report is free and always will be. When you need a
defensible figure for one specific address, that's what the bot does." The free/paid line
stays bright.

---

## The pSEO / Content Engine assessment (DB -> template -> Gemini -> human polish)

The architecture described is essentially **what we already run**: sealed templates
(`blog.render_post/render_study/render_city_hub/render_index`) rendering daily from
`market_district.gather()`, with the SEO/AEO audit (`seo_audit.py`) reusing the blog's own
builders in the publish pipeline. So the engine is real and shipping, not a concept.

Two non-negotiables if Gemini joins the loop:
1. **Generation happens at the gather/copy stage, never in a render hook.** Render stays
   pure - no network calls (the PURITY rule; `rebuild_indices()` is "no fetch").
2. **The honesty guard holds: every figure traces to source.** Gemini polishes prose; it
   never originates a number. Same guard the blueprint's `/ask` path specifies.

**On "Steal Their Traffic" / engineered backlinks (embeddable widgets, proprietary indices
like an "Overvaluation Index", DMCA enforcement):** the embeddable per-sqft / asking-vs-sold
widget is a clean, honest backlink engine - it ships real data others will cite. A named
proprietary index is fine ONLY if it is a transparent computation over data we hold (the
Asking vs Sold gap qualifies; an "Overvaluation Index" that implies we know true value does
not - same trap as Idea #1).

**On "1.8M postcodes": do not.** At unit-postcode granularity most pages would have roughly
zero recorded sales - thin doorway pages Google penalises, and dishonest (a "report" with no
data). Scale to **district / sector** where HMLR volume is real - exactly where `demand.py`
now operates (sector-level counts, #18) and where the city hubs already sit. Coverage that is
honest by construction beats coverage that is broad and empty.

---

## Recommended build order (honest, data-backed first)

1. **Livability Score (#6)** - all inputs already aggregated in `area_context.py`; render the
   components transparently, no single black-box number. Highest SEO value, zero new data.
2. **Time Machine historical (#3)** - dated HMLR PPD rows only; hard-block the HPI snapshot.
3. **True cost of ownership (#2, reframed)** - EPC band + VOA council tax, no invented retrofit £.
4. **Haggling / Distressed reframes (#5, #9)** - relabel to asking-vs-completion gap and
   stale-stock; both are honest restatements of data already in the model.
5. **FTB Reality Map (#4)** - ship the illustrative-mortgage version now; gate the income-ratio
   half behind sourcing ONS local income.

Held until a real source exists: Subsidence (#8b, needs BGS), Chain Breaker (#10, needs
fall-through rates). Shipped: Yield (#7), Asking-vs-Sold reframe of #1, Flood (#8a is wired in
`area_context.py`, surface it in a blog panel next).
