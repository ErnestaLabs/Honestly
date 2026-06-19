# Honestly TAVM - model layers that outsmart incumbents

## Principle
Same public data is not the game.

The game is inference around the property decision:

- Can this buyer actually afford it?
- Will the lender support it?
- What will a survey likely flag?
- What evidence supports renegotiation?
- What risks explain why the market is discounting it?

Portals show a price. Honestly should show the decision consequence.

---

## Layer 1 - Comparable Sales Model

Purpose: defend the value range.

Inputs:
- HM Land Registry sold prices
- property type
- recency
- locality
- EPC/floor area where available
- condition/user inputs

Output:
- central estimate
- range
- confidence
- proof rows
- reasons confidence is high/low

This remains the core valuation anchor.

---

## Layer 2 - Mortgage Affordability Model

Purpose: show whether the property is realistically financeable for this buyer.

This is not just a mortgage calculator. It connects the valuation to the buyer's actual constraint.

### Inputs
User-provided after the first valuation/evidence pack, never as an upfront gate:
- income
- deposit
- debts / monthly commitments
- dependants
- purchase price / asking price / offer price
- term
- product type where known
- expected rate or default market rate

Public / maintained data:
- Bank of England base rate
- mortgage-rate assumptions / manually maintained rate bands
- stamp duty rules
- LTV bands
- stress-rate assumptions

### Outputs
- estimated LTV
- deposit gap
- monthly payment estimate
- affordability pressure
- likely lender-risk band
- down-valuation exposure
- cash needed if lender values below offer

### Decision language

```text
At a £430,000 offer with a £60,000 deposit, you are at 86% LTV.
If the lender values it at £410,000, your effective LTV rises and you may need about £20,000 extra cash or a lower offer.
```

### Why this beats incumbents
Portals show price. Lenders show affordability separately. Honestly connects them:

> Is this price defendable and financeable for this buyer?

That is a higher-value decision than a standalone valuation.

---

## Layer 3 - Pre-Survey Risk Model

Purpose: estimate what a survey is likely to flag before the buyer spends money or negotiates blind.

Do not call this a survey. It is a risk estimate / pre-survey screen. It is offered after the first value, once the user has seen the defended price and sold evidence.

### Inputs
Public / inferred:
- EPC age, rating, heating type, floor area
- property age / construction clues
- flood risk
- conservation area / Article 4 area
- planning history
- listed building status where available
- transaction age and property type
- nearby environmental/context risks
- leasehold/freehold where available
- floorplan/photo/user-uploaded signals later
- user-entered listing text / known defects

### Risk flags
- damp / ventilation risk
- roof age / maintenance risk
- old electrics / rewire risk
- EPC upgrade risk
- flood risk
- leasehold/service-charge risk
- unregularised extension / loft conversion risk
- subsidence/context risk where sourced
- conservation/listed constraints
- boiler/heating age risk where EPC indicates
- poor resale/liquidity risk

### Outputs
- survey-risk score
- likely survey flags
- renegotiation evidence checklist
- what to ask the agent/seller
- what evidence would change the risk grade

### Decision language

```text
Pre-survey risk: Medium-high.
Reasons: low EPC rating, older property type, flood context nearby, and no evidence of recent electrical/heating upgrade.
Before survey, ask for boiler age, electrical certificate, building regulation sign-off for the extension, and recent damp/roof works.
```

### Why this beats incumbents
Surveyors see the house later. Portals do not tell you what may go wrong.

Honestly can say:

> Here is what the survey is likely to question, and what to ask before you commit more money.

---

## Layer 4 - Down-Valuation Exposure Model

Purpose: estimate whether the offer is vulnerable to a lender/surveyor coming in lower.

### Inputs
- offer/asking price
- Honestly sold-evidence range
- confidence score
- comp recency
- range width
- condition risk
- affordability/LTV position

### Outputs
- down-valuation risk: low / medium / high
- expected cash shortfall if lender value lands at low/mid evidence range
- renegotiation anchor

### Decision language

```text
Down-valuation exposure: High.
Your offer is £28,000 above the top of the sold-evidence range. If the lender lands near our central estimate, you either renegotiate or find roughly £28,000 more cash.
```

---

## Layer 5 - Seller Liquidity Diagnosis

Purpose: answer “why is this not selling?”

### Inputs
- asking price or quoted price
- sold-evidence range
- price reductions supplied by user or observed later
- days on market if available/user-provided
- local sale volume
- stale listing context when licensed/available
- confidence/range width

### Outputs
- price support grade
- liquidity risk
- agent-quote gap
- next action: hold / adjust / relaunch / improve presentation

### Decision language

```text
The current asking price is £22,000 above the evidence-supported range. If viewings are low after three weeks, the issue is probably price or presentation, not exposure.
```

---

## Layer 6 - Final Decision Pack

The paid product should not be “a valuation PDF.”

It should be a decision pack:

Buyer:
- value range
- affordability pressure
- down-valuation exposure
- pre-survey risk
- negotiation anchor

Seller:
- evidence-supported asking range
- liquidity diagnosis
- agent quote challenge
- pre-listing risk issues

Agent:
- defended price
- proof rows
- vendor objection handling
- likely survey/finance objections

---

## Product positioning

Portals answer:

> What might it be worth?

Honestly answers:

> What does the evidence support, can the buyer finance it, what will a survey likely question, and what should happen next?

That is the moat.

---

## Build order

P0:
1. Comparable Sales Model
2. Confidence Model
3. Proof Rows
4. Down-Valuation Exposure from user-entered offer/asking price

P1:
5. Mortgage Affordability Model
6. Pre-Survey Risk Model using public/context data and user-entered defects

P2:
7. Listing Behaviour Model
8. Rental Yield Model
9. Planning/Supply Model
10. Backtesting and model calibration

---

## Rule
Never pretend these models are formal lender decisions or formal surveys.

Use language like:

- estimated
- likely
- risk
- pressure
- evidence suggests
- ask before you commit

Do not use language like:

- guaranteed
- lender will
- survey will
- certified
- RICS valuation
