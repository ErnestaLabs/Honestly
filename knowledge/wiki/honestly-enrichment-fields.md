# Honestly Enrichment Fields

Sources:

- `research/REDDIT_enrichment_fields_voc.md`
- [[data-source-spine]]
- [[decision-intelligence-layers]]
- [[transparent-avm]]

## Core decision

Honestly needs enrichment fields, but they must be ours: public/direct source status plus our own calculations. No Street Data, Chimnie, PaTMa, PropertyData, or commercial same-data vendor block should appear as product enrichment.

## Field groups

`engine.summary(...)["honestly_enrichment"]` contains:

- `proof`: HMLR proof-row count, source links, explicit subject-sale exclusion.
- `basis`: property-type basis, source, window, evidence count, confidence grade/score.
- `subject_history`: HMLR subject sale + HMLR UK HPI history model when used. This is history/cross-check/fallback, never comparable evidence.
- `material`: floor area, EPC, tenure and council-tax status fields with source, missing-state and effect.
- `decision_signals`: buyer/vendor signals such as down-valuation exposure, agent quote gap and pre-survey questions.
- `monitoring_triggers`: what should cause a watchlist update.

## Reddit VOC signal

Fresh Reddit search showed recurring user anxieties:

- black-box valuation distrust (especially Zoopla-style estimates),
- agent valuation incentives and inflated quotes,
- lender down-valuations after offer,
- survey risk and unknown repair exposure,
- need for sold-price evidence in negotiation,
- material facts like EPC/leasehold/service charge,
- timing/monitoring when prices reduce or evidence changes.

## Product response

Free:

- defended range,
- confidence,
- HMLR proof rows,
- plain English,
- lightweight evidence PDF.

Paid:

- affordability pressure,
- down-valuation exposure,
- pre-survey risk questions,
- agent/asking challenge,
- compare/evidence map,
- monitoring triggers.

Related: [[data-source-spine]], [[telegram-conversion-flow]], [[decision-intelligence-layers]].
