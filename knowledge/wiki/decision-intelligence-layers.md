# Decision Intelligence Layers

Sources:

- `research/HONESTLY_TAVM_model_layers.md`
- `research/HONESTLY_monopoly_launch_PRD.md`

## Principle

Portals show a price. Honestly should show the decision consequence.

Paid value is not public facts. Paid value is what the price means for this buyer, seller, or agent.

## Layer 1: Comparable Sales Model

Purpose: defend the value range.

Outputs:

- central estimate
- range
- confidence
- proof rows
- why confidence is high/low

This is free-trust infrastructure and the anchor for everything else.

## Layer 2: Mortgage Affordability Model

Purpose: show whether the property is realistically financeable for this buyer.

Inputs should be requested only after first value:

- income
- deposit
- debts / monthly commitments
- dependants
- purchase price / asking price / offer price
- term
- expected rate or default market rate

Outputs:

- estimated LTV
- deposit gap
- monthly payment estimate
- affordability pressure
- lender-risk band

## Layer 3: Down-Valuation Exposure Model

Purpose: show what happens if the lender/surveyor lands lower than the offer.

Outputs:

- low / medium / high exposure
- offer above/below evidence range
- likely cash gap if lender uses central evidence value
- negotiation consequence

## Layer 4: Pre-Survey Risk Model

Purpose: estimate what a survey may question before the buyer spends more.

Do not call this a survey. It is a pre-survey screen.

Risk areas:

- EPC upgrade risk
- damp / ventilation risk
- flood risk
- leasehold/service-charge risk
- unregularised works risk
- listed/conservation constraints
- old heating/electrics signals where sourced

## Layer 5: Seller Liquidity Diagnosis

Purpose: help users understand sale pressure and market friction.

Signals may include:

- time since listing if user provides it
- price cuts if known
- local transaction velocity
- local evidence gap
- mismatch between ask and sold evidence

## Layer 6: Compare Homes

Purpose: help users choose between two or more options.

Compare should answer:

- which price is better defended?
- which has more finance risk?
- which has more survey/context risk?
- which one is easier to justify if challenged?

## Layer 7: Monitoring / Watchlist

Purpose: retention.

Monitor:

- nearby sold evidence
- rate changes
- comparable new data
- price/decision pack expiry
- changed confidence

Related: [[telegram-conversion-flow]], [[transparent-avm]], [[data-source-spine]].
