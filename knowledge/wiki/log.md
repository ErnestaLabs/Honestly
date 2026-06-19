# Honestly LLM Wiki Log

## [2026-06-14] ingest | Karpathy LLM Wiki pattern

Source: `knowledge/raw/karpathy-llm-wiki.md`.

Created internal wiki structure using the persistent compiled-knowledge pattern: immutable raw sources, LLM-maintained synthesis pages, content index, and chronological log.

Changed pages:

- `knowledge/wiki/index.md`
- `knowledge/wiki/llm-wiki-schema.md`

## [2026-06-14] synthesize | Product constitution and TAVM memory

Sources:

- `research/HONESTLY_TAVM_strategy.md`
- `research/HONESTLY_monopoly_launch_PRD.md`
- `research/HONESTLY_data_source_replacement_plan.md`
- `research/HONESTLY_TAVM_model_layers.md`
- current session decisions

Created synthesis pages for the core product memory so future sessions do not re-derive or lose the conversion rules.

Changed pages:

- `knowledge/wiki/honestly-product-constitution.md`
- `knowledge/wiki/telegram-conversion-flow.md`
- `knowledge/wiki/transparent-avm.md`
- `knowledge/wiki/valuation-comparable-rules.md`
- `knowledge/wiki/data-source-spine.md`
- `knowledge/wiki/decision-intelligence-layers.md`
- `knowledge/wiki/index.md`

Key durable decision: floor area and public facts are our job to fetch or infer. They can affect confidence, but they must never become a first-value gate.

## [2026-06-14] repair | Removed pre-value gates from bot and Lite valuation

Changed pages/code:

- `bot.py`
- `engine.py`
- `test_bot.py`
- `test_engine_own_figure.py`
- `research/HONESTLY_monopoly_launch_PRD.md`
- `research/HONESTLY_TAVM_model_layers.md`

What changed:

- Removed bedrooms/bathrooms from the Telegram pre-value wizard.
- Removed deposit and household income prompts from the Telegram pre-value wizard.
- Stopped sending decision-module text before the valuation/evidence pack.
- Removed the Lite engine floor-area hard gate.
- EPC/floor area is now a confidence signal, not a blocker.
- Added regression coverage for no public-data/finance gates, no subject-sale comps, 24-month hard cap, and missing floor area not blocking first value.

Verification:

- `python -m py_compile engine.py bot.py land_registry.py appraise.py report.py decision_models.py`
- `python -m unittest test_bot.py test_land_registry.py test_decision_models.py test_engine_own_figure.py`

Note: `python -m pytest ...` could not run in this environment because `pytest` is not installed for the active Python.

## [2026-06-14] investigation | Cronin Lite valuation wrong by ~£150k

Symptom:

- `engine.value("58 Cronin Street, London SE15 6JH", tier="lite")` produced a generic-flat range around `£285k-£440k`, later `£380k-£425k`, while the preserved Cronin appraisal says `£530k-£590k`, central ~`£560k`.

Root causes:

1. Removing the floor-area hard gate fixed conversion but left no replacement subject-size inference.
2. EPC credentials are absent locally, so Lite knew only `flat`, not `103 sqm maisonette`.
3. Lite treated small/partial/noisy nearby flats as equal comps to a 103 sqm maisonette.
4. Lite ignored the user-captured condition tier, so `high`/refurbished did not move the figure.
5. Dense London postcode lookup was capped too tightly, so valid 0.25-0.5 mile comps were missing from HMLR pulls.

Fix:

- Added local subject-fact cache fallback from preserved `*_uprn.json` files.
- Removed the old-appraisal comp-area cache from the production path. It was a crutch and not the product.
- Removed Street Data from Lite and paid valuation paths. It is a commercial aggregator over the same public spine and should not be part of the product dependency chain.
- Disabled Street Data, Chimnie and PaTMa as subject fallbacks/enrichment in `appraise.find_subject`.
- Added free-data history model: HMLR subject sale history + HMLR UK HPI + condition tier. The subject's own sale remains history, never a comparable.
- Expanded postcode collection without per-postcode lookup stalls.
- Raised HMLR area query cap so valid nearby postcodes reach the SPARQL query.
- Applied condition tier in Lite valuation.
- Updated tests to assert commercial aggregators are not called as fallbacks.

Verification:

- Free-spine Cronin high-finish Lite now returns `£530,000 - £590,000`, central `£540,000`, guide `Offers Over £475,000` from HMLR subject sale + HMLR UK HPI + condition tier, with HMLR sold rows still shown as evidence context.
- Live check confirms no `street` subject block and no `street_enrichment` summary block.
- `python -m py_compile engine.py appraise.py bot.py report.py verification.py price_ledger.py decision_models.py`
- `python -m unittest test_engine_own_figure.py test_bot.py test_land_registry.py test_decision_models.py` → 204 tests OK.

## 2026-06-14 - Product spine locked to direct/public data for Lite and paid

Change:

- `engine.value()` now defaults to the public-data valuation spine and no longer routes paid/pro through the legacy commercial feed path.
- Removed the legacy PropertyData `_pro_value()` path from `engine.py`.
- `engine.summary(..., tier="pro")` now adds decision context only; it does not render Street Data, Chimnie, PaTMa or commercial AVM cross-check blocks.
- `bot.py` no longer catches/mentions commercial provider quota failures in the valuation path.
- `products.nearby_schools()` no longer calls a commercial school endpoint; it returns empty until a direct Ofsted/GIAS client exists.
- `products.target_listings()` no longer calls commercial live listings; paid map/list rows use nearby HMLR proof rows until a direct listing spine exists.
- Added a dependency-free PDF fallback in `report.py`, so the first valuation can always send a lightweight evidence pack even when `fpdf2` is unavailable.
- Rewrote `verification.py` as a direct-public-source verification panel: HMLR proof rows, Lite basis, EPC/floor-area status, HMLR postcode cross-check, confidence.
- Updated tests to assert no commercial same-data aggregator fields render in paid/pro output.

Verification:

- Default keyless Cronin valuation returns `£530,000 - £590,000`, central `£540,000`, guide `Offers Over £475,000`, confidence `Good 70`.
- Smoke evidence pack generated: `_product_smoke_evidence_pack.pdf`.
- `python -m py_compile engine.py bot.py report.py products.py price_ledger.py verification.py appraise.py land_registry.py decision_models.py`
- `python -m unittest discover -p 'test_*.py'` → 463 tests OK.

## 2026-06-15 - Finish gate before VPS deploy

Change:

- Added `launch_gate.py` as the local finish gate: compile, full unittest discovery, deploy-manifest validation, keyless Cronin product smoke, PDF smoke, and commercial-source leak check.
- Updated `_deploy_vps.py` so deploy includes runtime dependencies (`store.py`, `ai.py`, scenario/action/verification/ledger/context modules) and exact logo image assets.
- Updated `brand.py` references so reports cite direct/public sources only; no PropertyData/Street Data/Chimnie/PaTMa references are emitted.
- Rule: local launch gate must pass before VPS deploy.

Verification:

- `python launch_gate.py` → LAUNCH GATE: PASS.
- Deployed once after gate pass.
- VPS smoke: Cronin high finish returns `£530,000 - £590,000`, central `£540,000`, guide `Offers Over £475,000`, confidence `Good 70`, no commercial enrichment fields, PDF generated successfully.
- `honestly.service` active after deploy.

## 2026-06-15 - Honestly-owned enrichment fields + fresh Reddit VOC

Change:

- Added fresh Reddit VOC collector: `tools/reddit_voc_enrichment.py`.
- Wrote `research/REDDIT_enrichment_fields_voc.md` from public old.reddit.com search across r/HousingUK, r/PropertyUK and r/UKPersonalFinance. No commercial property-data APIs.
- Reddit themes: black-box valuation distrust, agent quote incentives, down-valuation fear, survey anxiety, sold-price negotiation evidence, material facts, timing/monitoring.
- Added `engine.summary()["honestly_enrichment"]` with public/direct and Honestly-owned fields:
  - `proof`: HMLR row count/links and subject-sale exclusion.
  - `basis`: type/window/evidence/confidence basis.
  - `subject_history`: HMLR subject sale + HPI model when used.
  - `material`: floor area, EPC, tenure, council tax status and missing-state.
  - `decision_signals`: down-valuation exposure, agent quote gap, pre-survey questions.
  - `monitoring_triggers`: HMLR rows, HPI shifts, EPC/floor-area changes, confidence changes, price-gap movement.
- Added `test_honestly_enrichment.py` and tightened `launch_gate.py` so enrichment is required before deploy.
- Added [[honestly-enrichment-fields]] wiki page and linked it from the index.

Verification:

- `python launch_gate.py` → LAUNCH GATE: PASS, 465 tests OK.
- Deployed after gate pass.
- VPS smoke confirms `Honestly public-data enrichment`, `commercial_data=False`, proof rows present, decision signals present, no commercial enrichment fields, PDF generated.

## 2026-06-15 - Definite valuation formula + Google/free API enrichment context

Change:

- Added explicit `valuation_formula` to `engine.summary()` and `honestly_enrichment`.
- Formula now exposes:
  - `name`: `Honestly Transparent AVM v1`.
  - sources and non-sources.
  - property-type, distance, recency and subject-sale exclusion filters.
  - selected evidence count, pool count, raw Q1/median/Q3 prices.
  - finish-tier rule constants.
  - subject-history HPI fallback when used.
  - rounding and guide rule.
  - final low/central/high/guide.
- Bot card now renders the formula line instead of hidden prose.
- PDF Basis of assessment and fallback PDF include the same formula.
- Interactive HTML data blob and Build-up panel include the formula.
- `honestly_enrichment` now includes Google context status fields: Address Validation, Maps Routes, Street View, Solar. These are context/deliverable enrichments only, never valuation inputs.
- `honestly_enrichment` also includes free API context fields: Postcodes.io, HMLR, EPC register, BoE/ONS, Police.uk, Environment Agency, VOA council tax.
- Updated PRD to reflect the direct public spine, definite formula, Honestly enrichment fields, and that direct Ofsted/GIAS is still pending.

Verification:

- `python launch_gate.py` → LAUNCH GATE: PASS, 466 tests OK.
- Deployed after gate pass.
- VPS smoke confirms formula present, Google/free API context present, no commercial enrichment fields, PDF and interactive HTML generated.

## 2026-06-15 - PDF proof-row presentation fixed after user read-through

Problem:

- Fresh generated PDF showed `--bedroom`, `None sqm`, and comparable table columns `Size`, `GBP/sqm`, `Match` full of dashes.
- It implied generic HMLR flat rows were size-matched comparables even when public floor area was missing.
- Confidence note said `avg match 100%`, which was misleading without floor-area evidence.

Fix:

- PDF now hides Size/GBP-sqm/Match columns when those fields are unavailable.
- When subject-history HPI fallback is used, PDF labels rows as `HMLR sold proof rows`, not size-matched comparables.
- Executive summary explicitly says public floor area is not confirmed and the headline value uses subject HMLR sale history + HMLR UK HPI + condition.
- Plain-English and confidence notes now say `HMLR proof rows`, `subject-history HPI formula used`, and `public floor area missing for proof rows`.
- Methodology now states that missing floor-area evidence is disclosed rather than faked.
- Regenerated local PDF: `out/honestly_cronin_user_read_fixed2_appraisal.pdf`.

Verification:

- Read generated PDF text via `pypdf`; first three pages no longer show `None sqm` or dead Size/GBP-sqm/Match columns.
- `python launch_gate.py` → LAUNCH GATE: PASS, 466 tests OK.
- Deployed after gate pass.

## 2026-06-15 - strict comparable contract enforced

User directive:

- Stop calling loose nearby HMLR rows comparables.
- A true comparable must be a direct buyer substitute: same micro-market, same property class/spec, similar official size, similar price band, recent completion, verified tenure/spec/condition, and no obvious barrier/catchment/externality mismatch.

Implemented:

- Comparable radius hard cap is now 0.5 miles. No 1-mile expansion for rows called comparables.
- Strict comparable recency hard cap is 6 months.
- Strict comparable rule now requires verified official/public EPC floor area within 15%, verified bedrooms, verified compatible tenure, same property type, exact distance, similar price band and micro-market constraints.
- Unknown bedrooms/tenure/spec means proof/context only, not comparable.
- HMLR rows that fail the gate carry `strict_reject_reason` and remain visible as proof rows.
- Rows marked `strict_comparable=True` must carry a one-sentence `justification`.
- Cronin now has strict comparable count 0 and uses subject-history/HPI valuation basis; HMLR rows are labelled proof/context.
- Public EPC website fallback now has persistent cache at `data/epc_public_cache.json`; Cronin exact public EPC certificate cached as 103 sqm, EPC C to avoid GOV.UK throttling degrading to modelled area.
- PDF now switches on `strict_comparable`, not just presence of area. If no strict comps, it says `HMLR sold proof rows`, `not comparables`, and does not show `Comparable evidence (sold)`.
- Reddit/local chatter locality filter generalised: exact locality/postcode-district/micro-area only; no broad London bleed.

Verification:

- `python -m unittest test_epc.py test_engine_own_figure.py test_honestly_enrichment.py test_strict_comparables.py` passed.
- `python launch_gate.py` passed: 471 tests OK, product smoke OK.
- Deployed to VPS; smoke confirms Cronin: area 103, public EPC register, EPC C, valuation basis `hmlr_subject_history_hpi`, strict comparable count 0, evidence role `proof_context`.

## 2026-06-15 - comparable minimum corrected to 5

Correction from user:

- Three comparables is not enough. Minimum comparable pack is 5.

Implemented:

- `_LITE_MIN_STRICT_COMPS = 5`.
- Comparable rescue sequence is now: 0.5mi + 6 months, then extend recency to 12 months to reach 5, then expand up to 1 mile only if still below 5.
- Cronin now finds 6 strict comparables using public EPC floor-area enrichment and 12-month recency rescue, without radius expansion.
- Output discloses `strict_recency_extended=True` and `strict_recency_months=12`.
- Launch gate now requires at least 5 strict comparables, 103 sqm public EPC area, comparable justifications in PDF, and no irrelevant locality bleed.

Verification:

- Targeted tests passed.
- `python launch_gate.py` passed: 471 tests OK, product smoke OK.
- Deployed to VPS. VPS smoke confirms range £500k-£565k, central £530k, confidence Good 70, area 103 sqm public EPC, strict comparable count 6, evidence role `strict_comparables`.

## 2026-06-15 - project-wide delivery contract and banned-language gate

User directive:

- No user-facing `wired`, `missing`, `requires`, `pending`, `n/a`, `not available`, `Confirm with seller`, or similar implementation/failure language.
- Every inch of output must convert: every requested data item appears every time with a value, source-backed fallback, or decision-check item.

Implemented:

- Added `mandatory_output_contract` to `engine.summary()` with all 23 required product lines: HMLR/HPI, EPC/floor area, geo/admin/nearest postcodes, travel/amenities, address validation, amenities/transport/boundaries, crime, flood, air quality, planning, council tax, solar, macro, sentiment, map, frontage, route map, finish proposal, narrative, spoken walkthrough, market steer, payment, and delivery/link.
- Reframed contract phases/statuses as customer-facing `Data`, `Context`, `Delivery` and `Included`; no `Wired` status.
- Rewrote PDF data coverage section to render the contract as included report data, not internal plumbing.
- Replaced Material Information `Confirm with seller` with `Decision-check item`.
- Rewrote `verification.py` statuses to `Included` / `Included as decision-check item`; no `missing` status.
- Reframed `honestly_enrichment` public/free API statuses away from `missing`/`best_effort`.
- Interactive HTML source map now says `Included`, `Included in pack`, `Delivered`; no `Wired`/`pending` copy.
- Added `USER_FACING_BANNED` launch-gate scan over summary JSON and generated PDF text.

Verification:

- Generated PDF text has no banned terms: wired, missing, requires, lookup_required, best_effort, pending, not available, n/a, Confirm with seller, no public floor-area, None sqm, --bedroom.
- `python launch_gate.py` passed: 471 tests OK, product smoke OK.
- Deployed to VPS. VPS smoke confirms 23 contract keys, 6 strict comps, 103 sqm public EPC, and no banned terms in contract/enrichment JSON.

## 2026-06-15 - AVM v2 benchmark harness implemented

User directive:

- Execute the research blueprint for moving from Transparent AVM v1 baseline to an evidence-based benchmark engine.
- Do not promote sentiment or uncertainty logic into production pricing until it beats AVM v1 on backtesting.

Implemented:

- Added `research/AVM_V2_BENCHMARK_PLAN.md` as the phased research execution plan.
- Added `knowledge/wiki/avm-v2-benchmark.md` and linked it from `knowledge/wiki/index.md`.
- Added `avm_v2.py` with dependency-free experimental research utilities:
  - exact-local sentiment feature extraction;
  - entity weighting;
  - exponential time decay;
  - bounded sentiment multiplier;
  - sentiment volatility;
  - AVM v2 candidate transforms;
  - MAPE/MAE/RMSE/range coverage/interval width/ECE/TOM-correlation scoring.
- Added `tools/avm_backtest.py` CLI to compare candidates:
  - `baseline`;
  - `sentiment_multiplier`;
  - `sentiment_uncertainty`;
  - `sentiment_hybrid`.
- Added `tools/build_avm_fixture.py` to convert CSV/JSON historical transaction rows into AVM v2 fixtures and optionally snapshot current AVM v1 baselines.
- Added deterministic fixture file `research/avm_v2_fixture_cases.json` covering the current 10-address validation set.
- Added `test_avm_v2.py` regression tests for sentiment math, candidate transforms, scoring, and CLI runner.
- Wired a fast no-engine AVM v2 harness check into `launch_gate.py` so the benchmark layer cannot silently break.
- Generated reports:
  - `out/avm_v2_backtest_latest.json` / `.md` using fixture baselines;
  - `out/avm_v2_backtest_engine.json` / `.md` using live `engine.value()` outputs.

Important decision:

- Current AVM v2 candidates remain research-only. Even where the small fixture shows a candidate beating baseline on MAPE, promotion remains blocked until a larger leakage-safe train/calibration/test backtest proves lift, coverage, calibration, and sparse-home safety.

Verification:

- `python -m py_compile avm_v2.py tools/avm_backtest.py tools/build_avm_fixture.py launch_gate.py` passed.
- `python -m unittest test_avm_v2.py` passed: 6 tests OK.
- `python tools/avm_backtest.py --fixture research/avm_v2_fixture_cases.json --out out/avm_v2_backtest_latest.json --markdown out/avm_v2_backtest_latest.md --no-engine` passed.
- `python tools/avm_backtest.py --fixture research/avm_v2_fixture_cases.json --out out/avm_v2_backtest_engine.json --markdown out/avm_v2_backtest_engine.md` passed.
- `python launch_gate.py` passed: 476 tests OK, product smoke OK.

## 2026-06-15 - production web service brought online

User correction:

- Priority is the whole product working, not speculative research.

Implemented:

- Added `deploy/honestly-web.service` to run `server.py --port 8080` as a systemd service.
- Updated `_deploy_vps.py` so deploy pushes the web app/server dependencies and restarts both `honestly` and `honestly-web`.
- Updated `deploy/setup_vps.sh` to install/enable/restart both bot and web services.
- Added web/server files to `launch_gate.py` compile and deploy-manifest validation.
- Added missing web/blog dependencies to deploy: `webapp/index.html`, `server.py`, `area_report.py`, `email_funnel.py`, `email_send.py`, `blog.py`, `blog_images.py`, `ads.py`, `press_review.py/json`, `social_sentiment.py/json`, `seo_audit.py`, `cities.py`, `demand.py`, `market_analysis.py`, `market_district.py`, `market_study.py`, `publish_daily.py`.
- Initially configured VPS `.env` with `HONESTLY_PUBLIC_URL=http://187.77.100.209:8080` so hosted report links could resolve through the live web service.
- Then added nginx reverse proxy + Let's Encrypt certificate for temporary HTTPS origin `https://honestly.187.77.100.209.sslip.io` using sslip.io.
- After GoDaddy DNS was updated (`A @ -> 187.77.100.209`, `CNAME www -> usehonestly.co.uk.`), added nginx/certbot production config for `usehonestly.co.uk` and `www.usehonestly.co.uk`.
- Updated VPS `.env` so both `HONESTLY_PUBLIC_URL` and `HONESTLY_WEBAPP_URL` use `https://usehonestly.co.uk`. Telegram Mini App menu button is enabled on the real domain.

Verification:

- `python launch_gate.py` passed: 477 tests OK, product smoke OK.
- Deployed to VPS after gate pass.
- `honestly.service` active.
- `honestly-web.service` active, `ActiveState=active`, `SubState=running`, `NRestarts=0` after fix.
- External HTTP checks passed:
  - `http://187.77.100.209:8080/` returns 200.
  - `https://honestly.187.77.100.209.sslip.io/` returns 200 during temporary setup.
  - `https://usehonestly.co.uk/` returns 200.
  - `https://www.usehonestly.co.uk/` returns 200.
  - `/api/packs?as=vendor` returns 200.
  - `/api/value` for `58 Cronin Street, London SE15 6JH` returns central `£530,000`, range `£500,000 - £565,000`, 103 sqm, EPC C, 6 strict comparables, 23 contract keys over production HTTPS.
- Telegram API `getMe` passed for `usehonestly_bot`.
- Bot log shows `Menu button -> Mini App: ok`.

