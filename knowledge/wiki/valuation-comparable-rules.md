# Valuation Comparable Rules

Sources:

- current project decisions from session history
- `research/HONESTLY_TAVM_strategy.md`
- `research/HONESTLY_data_source_replacement_plan.md`
- 2026-06-15 operational directive on UK comparable selection

## Role

A comparable is not merely a recent HMLR sale. It is a property a reasonable buyer would consider a direct substitute for the subject in the open market.

Rows that do not pass the comparable gate are still useful, but they must be labelled as **HMLR sold proof rows / market context**, never as comparables and never as a comparable anchor.

## Hard comparable gate

A row may be called a comparable only if all hard checks pass:

1. **Subject sale exclusion**: the subject's own previous sale is never a comparable.
2. **Micro-market**: exact distance must be known. 0.5 miles is the ideal/default radius. If there are no usable same-type HMLR sales within 0.5 miles in the last 12 months, expand cautiously up to 1 mile with explicit disclosure and lower confidence; still do not cross known barriers/catchment/micro-market boundaries.
3. **Locality/barriers**: same immediate neighbourhood/estate/road-market where known; do not cross major roads, railways, industrial edges, catchment breaks, or obvious psychological barriers.
4. **Property class**: same property type/spec class. Flats/maisonettes only compare to flats/maisonettes; detached to detached; semi to semi; terrace to terrace.
5. **Size**: official/public EPC floor area must be verified for both subject and row; row must sit within the allowed physical band (current engine: ±15%). Modelled area can display but cannot make a row a strict comparable.
6. **Bedrooms/spec**: bedroom count must be verified and within 1 bedroom/reception where applicable. If unverified, row is proof/context only.
7. **Tenure**: tenure must be verified compatible. Unknown tenure is not a comparable.
8. **Temporal**: target minimum is 5 comparables. Strict comparables should ideally complete within 6 months; if fewer than 5 pass, extend to 12 months with disclosure before expanding radius.
9. **Price sanity**: sold price must sit within the similar-price band around the anchor (current engine: ±30%). Price band alone never qualifies a row.
10. **Condition/externalities**: known major condition disparity, main-road/railway/commercial-premises exposure, short lease, auction/distress/probate, or other non-open-market context disqualifies the row unless the subject is materially similar.

## Current engine behaviour

- Minimum strict comparables: `5`.
- Comparable ideal/default radius: `0.5 miles`.
- Comparable ideal recency: `6 months`.
- Recency rescue: extend to `12 months` only to reach 5.
- Fallback radius: up to `1 mile` only when the 0.5-mile gate still cannot reach 5.
- Comparable recency hard cap: `6 months`.
- Floor area is mandatory as a field:
  - exact public/official EPC where matched;
  - modelled/provenanced otherwise.
- Modelled floor area is **display data**, not a strict comparable qualifier.
- If strict comparable count is thin, valuation falls back to subject HMLR history indexed by HMLR UK HPI and condition factor.
- HMLR rows remain visible as proof/context with reject reasons, but output must not call them comparables.

## Forbidden anti-patterns

- Postcode fallacy: broad postcode/outcode match is not enough.
- Price-band fallacy: similar price alone is not enough.
- Tenure blindness: unknown/wrong tenure is not comparable.
- Size blindness: no 40-70 sqm flat as comp for a 103 sqm maisonette.
- Fake score fallacy: no `avg match 100%` unless strict physical/spec data supports it.
- Geography expansion fallacy: do not expand just to improve the story. Expansion is only allowed when the 0.5-mile/12-month same-type pool is empty, and must still respect micro-market/barrier/catchment constraints.

## Required output behaviour

If rows pass the hard gate:

- heading: `Comparable evidence (sold)`
- label rows as `Comparable`
- include a one-sentence justification for every comparable

If rows fail the hard gate:

- heading: `HMLR sold proof rows`
- label rows as `Proof row`
- disclose why the row is proof/context, not comparable
- do not show comparable-match confidence as if the row is a substitute

## Tests / launch gate

Required checks:

- Cronin has subject area `103 sqm` from public EPC cache/register.
- Cronin has at least 5 strict comparables after public EPC floor-area enrichment and 12-month rescue.
- Cronin PDF must contain `Comparable evidence (sold)` and `Comparable justifications`.
- Every strict comparable must have `sqm`, `floor_area_source`, `floor_area_status`, `dist`, and `justification`.

Related: [[transparent-avm]], [[data-source-spine]], [[telegram-conversion-flow]].
