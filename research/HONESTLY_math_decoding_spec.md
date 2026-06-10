# Mathematical Decoding of UK Property Prices - canonical math spec

Status: REFERENCE SPEC. Handed over by the user 2026-06. This is the intellectual
spine of the data-spine plan (ticklish-painting-kite.md). It does NOT replace the
engine. It formalizes the *beside-the-figure* macro/hedonic layer and a residual
anomaly engine, and names the live official-API pipeline that feeds them.

------------------------------------------------------------------------------
## 0. The honesty-contract guardrail (READ FIRST - non-negotiable)

The system below is a HEDONIC + MACRO OVERLAY. Under Honestly's honesty contract:

- The **sold-evidence anchor** sets the valuation figure (engine.value() ->
  PropertyData AVM at finish tiers + sold median / per-sqft cross-check, then the
  capped/disclosed apply_market temperature steer). That does not change.
- Everything in this spec sits **BESIDE** the figure with its source, exactly like
  macro.py and macro_live.py already do. It is context, cross-check, and anomaly
  detection - never a silent new input to valuation().
- The hedonic regression here is a **cross-check and residual engine**, not a price
  setter. propertylookup markets "HPI-adjusted to today" AS its valuation; that is
  precisely what we refuse. We show the hedonic "fair value" and the residual
  beside our sold-anchored figure, and name both sources.
- Any number that influences the headline figure must be **bounded and disclosed**
  or it does not ship. The only thing allowed to move the figure is the existing
  apply_market steer, clamped to +6% / -5% and printed line-by-line. A future
  Vertex/learned steer obeys the same clamp (plan Phase 7).

------------------------------------------------------------------------------
## 1. Already implemented in this codebase (do not rebuild)

`macro_live.py` ALREADY realizes the spec's z-score macro overlay:

| Spec element | Where it already lives |
|---|---|
| BoE IADB 2yr fixed mortgage, series **IUMBV34** | `macro_live._boe_mortgage()` |
| ONS **D7G7** (CPI), **KAC3** (AWE total pay), **MGSX** (unemployment) | `macro_live.ONS`, `_ons()` |
| z-score normalization `z(x_t) = (x_t - mu)/sigma` over trailing window | `macro_live._z()`, WINDOW=36, SMOOTH=3 |
| Real pay = AWE - CPI | `macro_live._align_real()` |
| Unified score `Score_t = sum w_i z(bucket_i)` (equal weights, signed) | `macro_live._compute()` -> `score` |
| Linear map `dP = a + b*Score` -> lean | `_compute()` lean bands (LEAN_BAND=0.40) |
| Bounded score, offline-safe cache, best-effort fetch | `signal()`, `_read_cache()` |
| "NEVER moves the figure, sits beside it" honesty contract | module docstring lines 19-22 |

`macro.py` carries the dated FACT layer: Bank Rate value + next MPC date, and the
SDLT / LBTT / LTT tax-friction bucket (`sdlt()`, banded). Tax bucket = spec bucket 6.

So three of the six spec buckets (financing-partial, income, policy/tax) and the
entire z-score machinery already exist and already obey the contract.

------------------------------------------------------------------------------
## 2. The six core drivers (proxy buckets)

1. **Financing** - cost of capital. Proxies: BoE Bank Rate (IUMA), quoted 2yr fix
   (IUMBV34, HAVE), effective rate on outstanding stock (IUMTLMV). Sign: negative.
2. **Incomes / borrowing capacity** - AWE (KAC3/K54I) deflated by CPI (D7G7) or
   CPIH (L522); claimant/unemployment (MGSX). Sign: positive. OBR long-run income
   elasticity of housing services ~2.51 vs price elasticity ~-0.92 (income wins).
3. **Supply constraints** - per-capita stock, planning approvals, completions vs
   household formation. ~1% supply increase -> ~2% relative price fall (theory,
   often swamped by demand). Sign: negative on prices.
4. **Demand / liquidity / sentiment** - HMRC monthly residential transactions
   >= GBP 40,000 (seasonally adjusted). Volume leads price momentum. Sign: positive.
5. **Local desirability / spatial premium** - distance to green/blue space,
   transport, schools; Acorn area class (CACI). Handled PER-PROPERTY in the hedonic
   L_i term, not in the national macro score.
6. **Taxes / transaction frictions / policy** - SDLT (Eng/NI), LBTT (Scot), LTT
   (Wales); Help to Buy etc. HAVE via macro.py. Sign: distortionary.

------------------------------------------------------------------------------
## 3. The hedonic base model (semi-log, mix-adjusted)

Resolves compositional heterogeneity (a month heavy in big detached homes must not
read as a price crash). Mirrors the official UK HPI: double-imputation,
semi-logarithmic hedonic regression.

Core equation:

    log(P_{i,t}) = alpha + beta * X_{i,t} + gamma * M_t + delta * L_i + eps_{i,t}

- `log(P)` - natural log of transaction price. Log because prices are log-normal /
  right-skewed; log normalizes variance and makes coefficients = % effects.
- `alpha` - baseline constant.
- `beta * X_{i,t}` - property traits (shadow prices): property type (detached /
  semi / terraced / flat as dummies), floor area m^2 (continuous), habitable rooms,
  new-build indicator, EPC rating.
- `gamma * M_t` - macro environment: Bank Rate, effective mortgage rate, CPI, wage
  growth, transaction volume. gamma = systemic elasticity.
- `delta * L_i` - location: Local Authority District code, Acorn class, geospatial
  distance to rail / green space / labour markets.
- `eps_{i,t}` - residual: variance unexplained by size/type/location/macro. Tracking
  this is the anomaly engine (Section 6).

Resilience adjustments (ONS 2025 methodology):
- **Reduced regression model** for provisional current month: OMIT the new/existing
  indicator for month t (tiny new-build samples cause over-estimation + downward
  revision), compare reduced-model t vs t-1; restore the full equation once data
  matures.
- **K-nearest-neighbour imputation** for missing continuous traits (floor area,
  rooms): impute from K=10 closest properties sharing postcode/type/Acorn. Never
  set missing to zero - it distorts beta.
- **Missing Acorn**: keep the row, down-weight it in OLS (UK HPI 2023), do not drop.

------------------------------------------------------------------------------
## 4. The macro overlay (z-score scoring -> ECM)

Z-score normalize each live driver:  `z(x_t) = (x_t - mu_x) / sigma_x`
(mu, sigma = rolling mean / sd over the window). Combine:

    Score_t = w1*z(rates) + w2*z(income) + w3*z(supply) + w4*z(demand)
              + w5*z(location) + w6*z(policy)

Weights calibrated by regressing on the quality-adjusted UK HPI target (w1 rates
strongly negative; w2 income strongly positive). First-pass linear map:

    dP_{t+1} = a + b * Score_t       (momentum indicator)

Institutional upgrade - **Error Correction Model** (BoE/ECB VECM; real house price,
real income, rates are I(1) but cointegrated):

    d log(P_t) = alpha + sum_i theta_i d log(P_{t-i})
                 + sum_j phi_j d M_{t-j}
                 + gamma ( log(P_{t-1}) - beta Y_{t-1} ) + u_t

- `( log(P_{t-1}) - beta Y_{t-1} )` = error-correction term: divergence of actual
  price from long-run equilibrium (driven by real price / real income ratio +
  equilibrium rates).
- `gamma` = speed of adjustment (gamma < 0 => mispriced market reverts to
  fundamentals). Anchors short-term projection; flags unsustainable deviation
  instead of forecasting runaway bubbles.

------------------------------------------------------------------------------
## 5. The live-data pipeline (all official, mostly keyless)

| Stage | Endpoint | Series / params | Retrieved |
|---|---|---|---|
| Sales / target | **HM Land Registry SPARQL** `http://landregistry.data.gov.uk/landregistry/query` | `ukhpi:refPeriodStart`, PPD by postcode | transaction prices, HPI, volumes |
| Features | **MHCLG EPC API** `https://epc.opendatacommunities.org/api/v1/domestic/search` | postcode / lmk-key, Basic auth (EPC_KEY) | floor area m^2, rooms, EPC rating |
| Rates | **BoE IADB** `_iadb-fromshowcolumns.asp?csv.x=yes` | **IUMA** (Bank Rate), **IUMBV34** (2yr fix), **IUMTLMV** (effective stock) | rate series, CSV |
| Income / labour | **ONS** website-JSON timeseries | **KAC3/K54I** (AWE), **D7G7** (CPI) / **L522** (CPIH), **MGSX/LF24** (unemp) | wage growth, CPI, unemployment |
| Liquidity | **HMRC** monthly property transactions | residential txns >= GBP 40,000, SA | volume indicator (z(demand)) |

Pipeline steps:
1. Pull PPD + HPI target via LR SPARQL (delta updates by refPeriodStart).
2. Join EPC features (floor area, rooms, rating) by postcode/identifier.
3. Add macro (BoE IADB CSV; ONS JSON; HMRC volumes).
4. Recompute derived features (affordability = median price / real AWE; supply
   tightness), z-score them, **fit on a rolling 3-5yr (36-60 month) window** so
   structural breaks phase out old regimes automatically. Log prices => stable
   elasticity coefficients. Optional: replace linear map with gradient boosting.
5. **Track residuals** (Section 6).

------------------------------------------------------------------------------
## 6. Residual tracking - the actionable anomaly engine (beside the figure)

Because the hedonic model controls size/type/age/location/macro, the residual
`eps_{i,t}` = (actual transacted price) - (model "fair" hedonic value). Aggregate
residuals by postcode sector / LAD over consecutive quarters:

- **Positive residual cluster** = persistent premium to predicted value =>
  gentrification, infrastructure investment, regeneration, speculative clustering.
- **Negative residual cluster** = persistent discount => capital flight, falling
  desirability (crime up, schools down), or mean-reversion opportunity.

A multivariate GARCH / VARX layer on the residual variances measures local
volatility / risk. For Honestly this powers an honest area-context line beside the
figure ("homes here have been transacting ~X% above/below their modelled fair value
over the last N quarters, source: LR PPD + hedonic residual"), and a quality flag on
our own figure - never a silent adjustment to it.

------------------------------------------------------------------------------
## 7. Build order for Honestly (honest, lean, testable; each ships beside the figure)

1. **land_registry.py** - HMLR SPARQL PPD-by-postcode (independent official sold
   evidence = the down-valuation evidence pack) + UK HPI series. Keyless, testable
   now. [Phase-1 spine client.]
2. **Extend macro_live.py** to a fuller six-bucket Score_t: add Bank Rate (IUMA) to
   financing and an HMRC liquidity driver to demand. Still bounded, still beside the
   figure, still disclosed. Keyless, testable now.
3. **epc.py** - MHCLG EPC client (firms floor area / rooms / rating). Needs EPC_KEY;
   degrades cleanly without it.
4. **Hedonic cross-check + residual** - fit semi-log hedonic on LR PPD + EPC over a
   rolling window; surface fair-value + residual BESIDE the sold-anchored figure
   with both sources. KNN-impute missing area; reduced model for provisional month.
5. **ECM / weight calibration** - calibrate w1..w6 and the error-correction term
   against the LR HPI target. Gated; context only.

Verification invariant (every phase): run engine.value() for one address and assert
summary()'s central/low/high are byte-identical before and after these layers are
added. They add `sources` / context only. If the headline figure moves, the contract
is broken and it does not ship.

------------------------------------------------------------------------------
## 8. Event-conditioned sequence forecaster (the transformer upgrade) - GATED

Idea (user, 2026-06): ingest the full historical property-market record and train a
transformer-style sequence model to predict market moves, cross-checked against the
dated events that actually moved the market through time.

Why it fits cleanly:
- It is the principled successor to Section 4's linear map `dP = a + b*Score` and the
  ECM. Instead of fixed weights w1..w6, a sequence model learns time-varying,
  non-linear interactions across the six buckets - and self-attention is the natural
  way to let a 2026 month "attend" to the 2008 crash or the 2020 stamp-duty holiday
  when the present rhymes with them. This is exactly the "structural breaks" problem
  the rolling-window technique handles bluntly; attention handles it with memory.
- The "events" stream is a first-class second input, not decoration. A dated event
  table (MPC decisions, fiscal events, stamp-duty holidays, Help to Buy start/end,
  Brexit vote, COVID, the 2022 mini-budget, Bank Rate regime turns) is encoded as
  tokens aligned to the macro/price time axis. The model is trained to predict the
  next-period quality-adjusted HPI move CONDITIONED on both the macro state sequence
  and the event sequence. Cross-checking against events is what stops it from
  hallucinating momentum that was really a one-off policy shock.

Architecture sketch (when built):
- Inputs per month t: the z-scored six-bucket vector (Section 4) + property/hedonic
  aggregates (Section 3) + an event embedding for events dated in [t-k, t].
- Backbone: a small temporal transformer / TFT-style model (decoder over the monthly
  sequence). Target: next-period UK HPI move (the LR HPI series, Section 5 Step 1).
- Trained on the rolling window so it keeps adapting; evaluated by walk-forward
  backtest against held-out future months, never in-sample fit.
- Lives where Phase 7's Vertex steer lives: `vertex.py`, consumed inside
  `appraise.apply_market` BEHIND A FLAG.

Honesty guardrail (same as everything else - non-negotiable):
- Its raw output is FORWARD CONTEXT that sits beside the figure, like macro_live's
  Score_t. By default it does not touch the headline number.
- The ONLY way it may nudge the figure is through the existing apply_market steer,
  clamped to +6% / -5% and printed as a disclosed line in "Basis of assessment". If
  the model's signal cannot be bounded and disclosed line-by-line, it ships as
  context only. A black-box transformer silently setting prices is the exact
  thing this product exists to replace.
- Every prediction is shown with the events it leaned on ("model reads conditions
  like late-2024; nearest analogues: ... ; source: LR HPI + dated event table"), so
  it stays a glass box, not an oracle.

Prerequisite before any of this: Section 5 pipeline persisting {summary, macro
state, later-observed outcome} rows to PostGIS (plan Phase 5), plus the dated event
table. No training set, no model - so this is strictly last, after the spine and the
honest beside-the-figure overlay are shipping and accumulating data.

## Section 9 - Richer condition capture, vision, and area demand (user direction, 2026-06)

Three additions handed down in session. The honest framing for all three: they
attach to mechanics that ALREADY exist in the engine, so none of them invents a
new figure-mover. Read before building.

### 9.1 The finish/condition tier is the one legitimate condition lever (verified in source)

`appraise.valuation(subj, compsA, key, finish, pdtype)` already drives the figure
off `finish_quality`:
- For `average` / `high` / `very_high` it queries the PropertyData `valuation-sale`
  AVM at each tier (`finish_quality=fq`, lines ~296-304) and picks `avm[finish]`.
- For below-average it applies a DISCLOSED, conservative cut to the average AVM:
  `CONDITION_DISCOUNT = {'needs_modernising': 0.90, 'needs_renovation': 0.80}`
  (lines ~291, 311-320).

So "marble all over vs the neighbour's same-size house" is NOT a missing feature -
it is precisely the `high` / `very_high` tier the AVM already prices. Two same-size
homes legitimately diverge here. What is missing is a precise, evidence-backed way
to SET that tier instead of a coarse one-word self-report.

### 9.2 More questions -> a precise finish tier (condition detail capture)  [IMPLEMENTED]

Extend the bot/Mini-App wizard with a short condition sub-survey (kitchen age, bath
count/quality, flooring, glazing, recent refurb, extensions, premium materials like
marble/stone). These map to one of the five finish levels the engine already
accepts (`needs_renovation .. very_high`). The mapping is deterministic and
disclosed ("you told us: new kitchen + marble bathrooms + hardwood -> we priced this
at HIGH finish; that is the AVM tier driving the figure"). It changes the figure
ONLY through the existing `finish_quality` path - no new multiplier, fully traceable.

Built in `bot.py` (2026-06): the single condition tap is now a four-question
sub-survey - overall state (the floor), kitchen, bathrooms, premium materials -
collected as integer signals (`c_state`, `c_kitchen`, `c_bath`, `c_premium`).
`bot.derive_finish(ans)` maps them deterministically to the five tiers: state 0/1
floor at `needs_renovation`/`needs_modernising` regardless of fittings (a gut job
earns no high-spec credit); from "liveable" up, `kitchen+bath+premium` (0..6) lifts
the tier (>=5 very_high, >=2 high, else average; a full refurb is at least high).
`bot._finish_disclosure` prints the named signals and states - truthfully - that this
is the one condition input that moves the figure. An explicit `finish` already on the
answers (landing handoff / direct pick) is respected untouched. Covered by
`test_bot.py::TestConditionSurvey` (renovation floor dominates fittings; marble home
out-tiers a same-size plain neighbour; derived tier threads into the engine and is
disclosed in chat). Suite green at 167 offline tests.

Web parity (same date): the Mini App intake (`webapp/index.html`) now posts the same
four condition signals; `server.py` derives the tier server-side via the SAME
`bot.derive_finish` (one derivation, no JS/Python drift), surfaces the disclosure as
`finish_note`, and the GET `/api/value`, POST `/api/handoff` and `/api/invoice` paths
all route condition through it. `bot.derive_finish` counts GENUINELY high-end elements
(a kitchen/bath/materials answer of "high-end/luxury/premium" = 2): two or more ->
very_high, one -> high, none -> average - so a modern mid-range home stays average and
only real premium finish (the marble case) lifts the tier. The public marketing page
(`site/App.jsx`) has no intake form (it is a worked example), so no change needed there.

### 9.3 Photos -> vision-assessed finish (best tool: Gemini, per plan ai.py)

User uploads photos in the bot; a vision model reads them and PROPOSES a finish
tier with evidence ("marble bathroom, integrated appliances, new flooring ->
high"). Honesty rules:
- Vision output is a PROPOSAL the user confirms or overrides; it never silently
  sets the figure.
- It resolves to the SAME five-level `finish_quality` the engine already uses - the
  only thing it can move is that disclosed tier, within the AVM the engine already
  queries. It cannot introduce a number outside the tier ladder.
- The chosen tier and the photo evidence behind it are printed in "Basis of
  assessment", so a reader sees why the home was priced at that finish.
- Use the real vision API (Gemini, the plan's `ai.py`), not a hand-rolled
  approximation. The user is not in the loop per-photo in the bot pipeline.

### 9.4 Area demand from official transaction velocity x sentiment (`demand.py`)

The math spec's demand/liquidity bucket (Section 2), built from sources already in
hand and beside the figure:
- COUNT of actual recorded transactions for the subject postcode and its nearest
  neighbours over a fixed window, pulled from `land_registry.ppd_postcode` (official
  HMLR PPD, already built and live-proven). Subject area vs nearby areas gives a
  RELATIVE liquidity read ("this postcode + nearest N recorded X sales in 24 months,
  busier/in-line/quieter than the surrounding cluster").
- CROSS-CHECKED against `reddit_intel.for_area` (the `hit` MCP wrapper, already
  wired) - qualitative chatter agreeing or diverging with the hard count. Assembly
  of one official quantitative signal with one qualitative signal is exactly the
  "beat the field on assembly" goal.
- Needs nearest-postcode resolution: `geo.py` over Postcodes.io (keyless public
  endpoint, localhost self-host fallback per plan) - the Phase-1 geo client.
- Placement: BESIDE the figure, disclosed, like macro momentum and the HMLR
  cross-check. It is a demand read, not a price input. It may only ever influence
  the headline through the EXISTING capped+disclosed `apply_market` steer, and only
  if disclosed line-by-line - default is context-only.

Verification invariant (unchanged, applies to all of 9.x): run `engine.value()` for
one address and assert `summary()`'s `central`/`low`/`high` are byte-identical
before and after these layers, EXCEPT where the user deliberately changes the finish
tier (9.2/9.3) - which is the one disclosed, already-existing lever, and whose effect
is shown as the tier it set.
