# Honestly - how we outsmart incumbents

## Thesis
Same public data. Different method.

Competitors compete on access, breadth, and opaque estimates. Honestly competes on inference, proof, confidence, and model accountability.

The category is not “another AVM.”

The category is:

> Transparent AVM: a defended number, proof rows, confidence, and an explanation of why the model believes it.

## Hit signal from fresh scan

Raw scan saved at:

`research/hit_outsmart_incumbents_raw.json`

### 1. Black-box estimates create anxiety
Fresh threads show users reacting to unexplained Zoopla estimate moves:

- “Sudden £20K Drop on Zoopla Estimate - Any Ideas Why?”
- “Zoopla estimate updated to my offer price - Coincidence or was it reported?”
- “Zoopla house price estimate just wiped out 30,000??”
- “Big difference in asking price vs Zoopla estimate”

Read: people do not just want the figure. They want to understand why the figure changed and whether to trust it.

### 2. Spreadsheet behaviour is the fallback
Fresh threads show people building and sharing spreadsheets:

- house buying planner spreadsheet
- mortgage spreadsheet
- affordability spreadsheet
- running-cost spreadsheet
- compare-house tooling requests

Read: the trusted alternative to black boxes is DIY arithmetic. Honestly should become the spreadsheet they were going to build, but faster and cleaner.

### 3. Sellers need diagnosis, not another valuation pitch
Fresh threads show sellers asking why a property is not moving after agent pricing:

- “Why is my home not selling?”
- “Update on house not selling”
- “Why is my flat not selling?”
- “London flat is not selling”

Read: sellers need a pricing and liquidity diagnosis anchored to completed sales and market behaviour. They do not need another agent-flattery number.

## The incumbent weakness

### Portal estimates
They show a number but not enough reasoning.

User question:

> Why did this move £20k?

Portal answer:

> Estimate updated.

Our answer:

> The number moved because these comps entered/aged out, the evidence range widened/tightened, and confidence changed from X to Y.

### Estate agents
They have a conflict: win the instruction.

User question:

> Is the agent’s number real or optimistic?

Our answer:

> Here is what completed sales support. Here is the range. Here is what would need to be true to justify the higher number.

### Data tools
They show rows and charts but leave judgement to the user.

User question:

> What does this mean for my offer/listing?

Our answer:

> This evidence supports £X to £Y. Confidence is Z because of A/B/C. Here is the next move.

### Lenders/surveyors
They can down-value without showing the working.

User question:

> Should I renegotiate or proceed?

Our answer:

> Here is the sold evidence pack. If the lender is below this range, these are the comps to question. If the lender is inside this range, renegotiate carefully.

## Our method

### 1. Proof rows, not proof links
Never rely on a paywalled clickout as proof.

Each comparable row must show:

- address
- sold price
- sale date
- property type where known
- postcode / locality
- source: HM Land Registry Price Paid Data
- open HMLR URI where available

The proof is the row shown inside Honestly. The link is secondary.

### 2. Transparent comparable sales model
The first model is not magic.

It should disclose:

- how many comps were considered
- how many comps were used
- why comps were included/excluded
- same-type match
- recency weight
- distance/locality weight
- floor-area match where known
- range width

User-facing principle:

> We show the evidence before asking you to trust the number.

### 3. Confidence is first-class
Confidence matters more than the midpoint.

Do not just show:

> £430k

Show:

> £430k, confidence 91%, because 38 recent same-type sales support a tight range.

Or:

> £430k, confidence 42%, because only 4 usable sales exist and the evidence range is wide.

Confidence should move based on:

- comp count
- comp recency
- same-type quality
- range width
- evidence freshness
- floor-area availability
- locality spread
- model agreement/disagreement

### 4. Explain changes over time
This is how we beat black boxes.

Every re-run should be able to say:

- value changed by X
- confidence changed by Y
- reason: new sale entered, old sale aged out, evidence set widened, HPI moved, user condition changed, or model version changed

If we cannot explain a movement, the model is not transparent enough.

### 5. Multi-model, but staged
Do not pretend we have every model on day one.

Build the ensemble in layers:

1. Comparable Sales Model - P0
2. Confidence Model - P0
3. EPC/Floor Area Adjustment - P1
4. Market Momentum Model - P1
5. Rental Yield Model - P1/P2
6. Listing Behaviour Model - P2, only with clean listing data
7. Planning/Supply Model - P2
8. Final Ensemble - after the component models are observable

The ensemble should not hide behind “AI.” Each component has a model card.

### 6. Model cards
Every valuation should carry a small model card:

```text
Model version: comps-lite-0.3
Primary model: comparable sales
Inputs used: HMLR sold prices, EPC type/floor area where available
Inputs not used: portal estimates, asking price, sentiment
Confidence: Fair
Reason: 7 same-type sales, but older than 12 months and no floor-area match
```

This turns the honesty contract into a product surface.

### 7. Disagreement is a feature
If another number is supplied by the user, do not average blindly.

Show disagreement:

```text
Agent quote: £500k
Honestly range: £430k - £455k
Gap: £45k above the evidence range

To defend the agent quote, we would need to see:
- larger floor area
- premium condition evidence
- newer nearby sales at that level
```

This is stronger than a consensus average.

### 8. Backtesting is the long-term moat
Every valuation should be stored with:

- model version
- predicted range
- central estimate
- confidence
- comps used
- data timestamp
- later HMLR actual sold price
- error percentage

Then we can say:

> In SE15 flats, model v0.4 has a median absolute error of X% on completed sales after Y months.

This is the moat competitors cannot fake quickly.

## What we should not do

- Do not scrape portals and call that proof.
- Do not send users to paywalled aggregator pages as evidence.
- Do not claim “most accurate” before backtesting proves it.
- Do not hide adjustments behind AI language.
- Do not average in a portal estimate just because it exists.
- Do not quantify an adjustment unless the method is defensible.
- Do not promise live listing intelligence until the data route is legal and robust.

## Product pillars

### Pillar 1 - Evidence ledger
Every comp shown as a proof row.

### Pillar 2 - Confidence engine
The score explains evidence quality, not just model swagger.

### Pillar 3 - Explainable movement
Every value movement over time has a reason.

### Pillar 4 - Decision framing
Buyer: offer/renegotiate/proceed.
Seller: price/change/hold.
Agent: defend/win/work the street.

### Pillar 5 - Backtest ledger
Prediction vs actual sale becomes the compounding moat.

## P0 build order

1. **No paywalled evidence links** - already fixed. HMLR URI or GOV.UK search only.
2. **Evidence ledger UI** - every comparable row shows address, date, price, source.
3. **Confidence reason block** - not just score; why the score is what it is.
4. **Model card** - model version, inputs used, inputs not used.
5. **Change explanation** - when a rerun differs, show what changed.
6. **Prediction store** - persist every valuation with model version and comps used.
7. **Backtest job** - later match predictions to new HMLR sold prices.

## Launch positioning

Public line:

> One address. A defended price. Sold evidence shown.

Strategic line:

> The UK's most transparent property valuation engine.

## One-line answer

We outsmart them by making the model accountable: proof rows, confidence, explainability, and backtesting over the same public data everyone else treats like a black box.
