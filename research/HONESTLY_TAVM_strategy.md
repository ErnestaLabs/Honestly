# Honestly - Transparent AVM strategy

## Core shift
Do not compete on owning secret data.

Most serious players can reach roughly the same public facts:

- sold prices
- EPC
- planning
- schools
- crime
- flood
- rates
- geography
- local context

The moat is not the raw data.

The moat is the model, the explanation, the confidence scoring, and the proof trail.

## Product category
Honestly should not be framed as a generic AVM.

Build a **Transparent AVM**:

> A valuation engine that gives a defended number, shows the evidence, explains the adjustment, and grades its own confidence.

Public positioning:

> The UK's most transparent property valuation engine.

Not:

> The UK's most accurate valuation model.

Accuracy is hard for a user to judge immediately. Transparency can be judged immediately.

## P0 launch truth
For launch, we do not need to scrape portals or recreate every commercial signal.

We need to reliably say:

> This comparable home sold for £X. Here is the proof.

That proof is HM Land Registry.

The first wedge is sold-evidence proof, not portal intelligence.

## Minimum TAVM output
Every valuation should show:

- estimated value
- range
- confidence score
- comparable sales count
- comparable sales table
- proof row for each comparable: address, date, price, source and open HMLR URI where available
- date decay / recency logic
- plain-English explanation
- what would improve confidence

Example:

```text
Estimated value: £432,000
Range: £423,000 - £440,000
Confidence: 91%

Based on:
- 38 comparable sales
- same property type evidence
- recent transaction dates
- EPC/floor area where available
- local market context

Proof:
12 Example Road sold for £425,000 on 12 March 2025 - HM Land Registry Price Paid Data. The address/date/price row is shown in the report. Where the open HMLR linked-data URI is available, it is included. Never use a paywalled aggregator page as proof.
```

## Multi-model architecture
The long-term model should be an ensemble, not a single average.

### 1. Comparable Sales Model
Core launch model.

Inputs:
- HMLR sold prices
- date
- property type
- distance / postcode proximity
- floor area where available
- condition where known

Output:
- sold-evidence central value
- range
- comp strength

### 2. Rental Yield Model
Investor context.

Inputs:
- VOA/ONS rents
- rental listings later if licensed or user-provided
- estimated gross yield

Output:
- investor support / pressure
- not a primary residential value input unless explicit investor mode

### 3. Replacement / Improvement Model
Later.

Inputs:
- floor area
- build type
- EPC
- renovation/condition signals
- user-uploaded photos/floorplans

Output:
- condition uplift/downlift
- improvement explainability

### 4. Market Momentum Model
Context around the sold anchor.

Inputs:
- HPI
- rates
- local transaction velocity
- time since sale
- supply trend when available

Output:
- bounded market steer
- confidence impact

### 5. Listing Behaviour Model
Later and only with clean data.

Inputs:
- asking price changes
- stale listings
- withdrawn listings
- failed sales
- listing-to-sale discount where licensed/observed

Output:
- liquidity and discounting context

### 6. Final Ensemble
Combines model outputs with transparent weights.

Rule:
- always show what moved the number
- always show what was only context
- never hide a black-box adjustment

## Time decay
Sold evidence must be weighted by recency.

A sale yesterday is stronger than a sale 14 months ago.

Date weighting should be explicit:

- 0-3 months: highest weight
- 3-6 months: strong
- 6-12 months: moderate
- 12-24 months: weak unless local evidence is thin
- older: context only unless needed for sparse markets

Every report should show if confidence is lower because evidence is old.

## Confidence model
Confidence is more useful than the exact midpoint.

A valuation with 112 recent same-type comparable sales is different from one with 4 old mixed-type sales.

Confidence should score:

- number of usable comparables
- recency of comps
- same-type match
- distance / locality match
- floor-area match
- EPC/property-detail confidence
- range width
- HMLR/HPI consistency
- market volatility
- missing-data penalties

Public copy:

```text
Confidence: High
Reason: 24 recent same-type sales nearby and a tight evidence range.
```

or:

```text
Confidence: Low
Reason: only 4 recent comparable sales and the range is wide.
```

## Explainability
Every valuation should answer: why?

Example adjustment language:

```text
+£18k - stronger condition than local average
+£12k - closer to station than most comps
-£7k - flood-risk context
+£9k - school catchment context
-£14k - local oversupply / stale listings
```

Important: only show numeric adjustments where we can defend the source and method.

If we cannot defend the amount, say it as context, not as a quantified value movement.

## Consensus model
Valuation consensus is valuable, but only if legal/source-safe.

Do not scrape competitors.

Allowed paths:

1. User manually enters another estimate.
2. User uploads or pastes their own estimate.
3. Publicly permitted source/API.
4. Our own previous prediction vs actual sale after completion.

Consensus output:

```text
Your model: £430k
Other estimate supplied by user: £450k
Disagreement: £20k

Why we differ:
- local sold comparables are lower
- flood risk context
- recent nearby oversupply
```

This creates an evidence-backed opinion without illegal scraping.

## Continuous learning moat
Every completed sale becomes a backtest.

Store:

- prediction date
- predicted range
- central value
- confidence
- model version
- comps used
- actual sold price when HMLR publishes it
- error percentage

Then report:

```text
Predicted: £422k
Actual: £418k
Error: 0.95%
```

This becomes the long-term moat:

- model calibration
- area-level error tracking
- confidence calibration
- public proof of accuracy over time

## Launch implementation rule
Do not wait for every model.

P0 TAVM is:

- direct HMLR comparable sales
- proof row for every comparable
- recency weighting
- confidence score
- plain-English explanation
- range, not false precision
- no portal scraping
- no hidden valuation input

That is enough to launch the transparent valuation category.

## Outsmarting incumbents
Same public data. Different method.

Incumbents show numbers that move without explanation, or rows of data that leave the judgement to the user. Honestly wins by making the model accountable:

1. proof rows, not paywalled proof links
2. confidence with reasons
3. model cards showing inputs used and not used
4. explainable value movements over time
5. user-supplied disagreement analysis
6. prediction-vs-actual backtesting

The complete playbook lives in:

`research/HONESTLY_outsmart_incumbents_playbook.md`

## One-line doctrine
We do not win because we know a house sold.

We win because we prove what sold, explain why it matters, grade confidence, and learn when the market proves us wrong.
