# Transparent AVM

Sources:

- `research/HONESTLY_TAVM_strategy.md`
- `research/HONESTLY_monopoly_launch_PRD.md`

## Category

Honestly should be understood as a Transparent AVM, not a generic AVM.

Definition:

> A valuation engine that gives a defended number, shows the evidence, explains the adjustment, and grades its own confidence.

Public positioning:

> The UK's most transparent property valuation engine.

## Why this wins

Most incumbents can reach similar public facts. The moat is not raw data ownership. The moat is:

- inference quality
- visible sold evidence
- proof rows
- confidence scoring
- plain-English explanation
- backtesting and model accountability over time
- decision consequences after the price

## Minimum valuation output

Every valuation should include:

- estimated value
- range
- confidence score or label
- comparable sales count
- comparable sales table
- proof row for each comparable: address, date, price, source, open HMLR URI where available
- date decay / recency logic
- plain-English explanation
- what would improve confidence

## Proof standard

P0 proof is HM Land Registry.

The product must be able to say:

> This comparable home sold for £X. Here is the proof.

The HMLR row shown inside Honestly is the proof. A link is secondary. If an open HMLR linked-data URI is available, include it. Otherwise use GOV.UK sold-price search fallback.

Never use a paywalled aggregator page as proof.

## Confidence standard

Confidence should move based on evidence quality:

- number of same-type comps
- recency
- distance
- property type match
- EPC/floor area availability
- condition signal quality
- whether evidence was expanded geographically

Missing public data should explain lower confidence. It should not block the first value.

Related: [[valuation-comparable-rules]], [[data-source-spine]], [[decision-intelligence-layers]].
