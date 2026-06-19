# Data Source Spine

Sources:

- `research/HONESTLY_data_source_replacement_plan.md`
- `research/HONESTLY_TAVM_strategy.md`

## Core decision

PropertyData, Street Data, Chimnie, PaTMa and other commercial same-data aggregators are not the source and are not valuation dependencies.

Honestly must launch and keep functioning from direct public sources. Paid sells decision intelligence over this spine, not paid re-packaging of public data.

## P0 sources

| Need | Source | Notes |
|---|---|---|
| Sold prices | HM Land Registry Price Paid Data | Core proof source |
| HPI | HM Land Registry UK HPI | Market movement context |
| EPC / floor area | EPC register | Fetch/infer, never ask upfront |
| Geography | Postcodes.io / ONS | Postcode resolution and area context |
| Rates | Bank of England | Affordability assumptions |
| Proof fallback | GOV.UK sold-price search | When open HMLR URI unavailable |

## P1 context

| Need | Source |
|---|---|
| Crime | Police.uk |
| Flood | Environment Agency |
| Broadband | Ofcom |
| Council tax | VOA / local authorities |
| Maps/context | OS OpenData / Postcodes.io |
| Census | ONS |

## Launch-safe rule

No portal scraping dependency for P0. No commercial property aggregator dependency for Lite or paid valuation. User can manually provide asking price, offer price, or listing context if needed.

## Product implication

Public data is table stakes. Do not sell public facts as the premium. Sell interpretation and consequence:

- is this price defendable?
- is it financeable?
- what could a survey question?
- what evidence supports negotiation?
- what should be monitored next?

Related: [[transparent-avm]], [[valuation-comparable-rules]], [[decision-intelligence-layers]].
