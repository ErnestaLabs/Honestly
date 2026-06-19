# Telegram Conversion Flow

Sources:

- `research/HONESTLY_monopoly_launch_PRD.md`
- current product correction from session history

## Goal

Telegram is the first launch surface. It must prove value before friction.

## Correct first-run flow

1. User sends one address.
2. Bot may ask only high-leverage decision-shaping questions:
   - purpose: buyer / vendor / agent / curious owner
   - situation: buying, selling, checking agent quote, negotiating, monitoring
   - condition if known
   - known asking price, offer, or agent valuation if the user has one
3. Bot returns immediately:
   - defended price
   - range
   - confidence
   - proof rows
   - plain-English reasoning
   - what would improve confidence
4. Bot sends lightweight evidence PDF.
5. Bot offers next actions and paid decision modules.

## Do not ask before first value

Never ask upfront for:

- floor area
- EPC
- tenure
- income
- deposit
- mortgage term
- debts
- dependants
- full finance profile

These create friction and/or give away paid decision value before trust exists.

## First value contract

The first output must feel complete enough to trust:

```text
Estimated value: £X
Range: £Y - £Z
Confidence: Fair / Good / Strong
Evidence: N sold homes, with proof rows shown
Plain English: why the range is where it is
Next action: what to check or compare next
```

## Paid transition

After the evidence pack, upsell with consequence-based language:

- "Check down-valuation exposure"
- "See whether this price is financeable for your numbers"
- "Compare this home against another option"
- "Monitor this address and nearby sold evidence"

Do not upsell floor area or basic public facts. Those are table stakes.

Related: [[honestly-product-constitution]], [[decision-intelligence-layers]], [[valuation-comparable-rules]].
