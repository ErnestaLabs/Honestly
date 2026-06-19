# Honestly Launch PRD - TAVM Decision Pack

**Status:** Active build PRD  
**Launch target:** Telegram bot usable within 30 minutes  
**Category:** Transparent AVM, not generic AVM

## 1. Product thesis

Same public data. Different method.

PropertyData, portals, agents and lenders can all point at property facts. Honestly wins by turning the facts into a transparent decision model:

> One address. A defended price. Sold evidence shown. Then: can it be financed, what may a survey flag, and what should happen next?

## 2. Launch wedge

Primary wedge:

> UK buyers and sellers who need to defend one price decision with sold evidence.

Launch must work even if PropertyData credits are unavailable.

P0 data spine:

- HM Land Registry Price Paid Data
- open HMLR linked-data URI where available
- GOV.UK sold-price search fallback
- EPC/register context where available, fetched by us and never required upfront
- user-entered asking/quoted price where the user already has one
- post-valuation income/deposit inputs for buyer affordability decision modules

## 3. P0 Telegram product

A user must be able to use the Telegram bot and complete a valuation in under 30 minutes.

### Flow

1. User sends address.
2. Bot asks audience: buyer / vendor / agent.
3. Bot asks only conversion-safe context before value:
   - condition signals
   - buyer asking/offer price if known, optional
   - vendor agent quote if known, optional
   - investment/main-home situation where relevant
4. Bot returns before any paywall or finance form:
   - value range
   - guide / anchor
   - confidence
   - plain-English explanation
   - HMLR proof rows
   - lightweight PDF evidence pack
   - next action
5. Bot offers paid decision modules after trust:
   - buyer finance/down-valuation pressure
   - pre-survey risk screen
   - compare homes
   - monitoring/watchlist

Do not ask for floor area, EPC, tenure, income, deposit, debts, dependants, or mortgage term before first value. Floor area and EPC are fetched/inferred by Honestly where public records allow; missing data lowers confidence only.

## 4. P0 models

### Comparable Sales Model

Purpose: defend the value range.

Outputs:
- range
- central estimate
- confidence
- proof rows

Rules:
- no paywalled evidence links
- no portal scraping
- HMLR row is the proof

### Mortgage Affordability Model

Purpose: tell a buyer whether the property is financeable at their inputs.

Inputs, requested only after the first value/evidence pack:
- asking/offer price
- deposit
- household income
- model range

Outputs:
- estimated mortgage
- LTV
- income multiple
- monthly payment estimate
- finance pressure: low / medium / high

### Down-Valuation Exposure Model

Purpose: show what happens if the lender/surveyor lands lower.

Outputs:
- low / medium / high exposure
- offer above/below evidence range
- estimated cash gap if lender uses central evidence value

### Pre-Survey Risk Model

Purpose: estimate what a survey may question before the buyer spends more.

Inputs:
- EPC where available
- condition tier
- property type confidence
- evidence confidence
- flood/planning/etc later

Outputs:
- low / medium / high risk
- likely questions to ask

This is not a survey and must never be described as one.

## 5. Copy rules

Allowed:

- evidence suggests
- risk
- pressure
- likely questions
- ask before you commit
- comparative market appraisal

Forbidden:

- guaranteed
- lender will
- survey will
- certified
- RICS valuation
- proof link to PropertyData

## 6. Acceptance criteria for this build

- Bot runs without PropertyData credits for lite valuation.
- Evidence links are not PropertyData transaction pages.
- Buyer path accepts optional deposit and income.
- Buyer card shows finance pressure when deposit/income provided.
- Buyer card shows down-valuation exposure when asking price provided.
- All cards show pre-survey risk screen.
- Tests pass.
- Production bot is restarted and verified with a real address.

## 7. Build next after P0

- Model card in every report
- persistent prediction store with model version
- rerun/change explanation
- backtesting against future HMLR sold prices
- planning/supply model
- listing behaviour model only with legal/robust source
