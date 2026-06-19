# Hit research - lite comparables + funnel

## What the Cronin appraisal already proves

Source artifacts:
- `appraisal_cronin_street_SE15.md`
- `C:\Users\Hello\Downloads\Cronin_Appraisal (1).pdf`
- `cronin_uprn.json`
- `cronin_match.json`

### Subject profile
- 58 Cronin Street is not a generic flat.
- The richer appraisal describes it as a **4-bed, 2-bath maisonette** of about **103 sqm**.
- EPC: C.
- Council tax band: B.
- Last sale: **£320,000** in 2015.

### Comparable structure that actually works
The paid appraisal does **not** value it against loose postcode history.
It splits evidence into tiers:

- **Tier A**: same-size, same-character comparables
- **Tier B**: premium / distinct-market-tier comps, kept as ceiling context only

For Cronin:
- Tier A comps: **£445,000 - £612,500**
- Tier A median: **£505,000**
- Final assessed range: **£530,000 - £590,000**
- Central: **~£560,000**
- Guide: **Offers Over £500,000**

That is the right shape.

## Quant logic worth preserving

### 1) Same-size, same-character first
A 400k home is only comparable to 375k / 425k if size, type, condition and location are genuinely similar.
Bedroom count alone is not enough.

### 2) Weighted evidence beats raw averaging
The strong pattern is:
- use a similarity score per comp
- weight recent / close / same-type comps harder
- let weak comps exist, but demote them

### 3) Separate tiers
Do not blend a premium conversion / larger unit into the core range.
Keep it as context only.

### 4) Range from dispersion, not vibes
A good band comes from the spread of the actual comparable set, not a fixed multiplier.
Useful shape:
- central = weighted median / blended sold anchor
- low/high = weighted IQR or weighted percentile band
- guide = deliberately below assessed range to create competition

### 5) Condition is a separate lever
The current product already treats condition as a legit mover.
That is correct.
The free surface should keep that logic, but only after the subject is properly shaped.

## Why the current lite result is weak

The lite path currently leans too hard on broad HMLR postcode history.
That is how it ends up with stale low sales pulling the band down.
It is mathematically honest, but commercially weak.

The product should instead:
- resolve the subject profile as richly as possible
- use same-size / same-character evidence
- show a premium free result that makes the paid layer look obviously richer

## Funnel research

The current funnel is already strong enough.
Do **not** redesign it.
It already does the important things:
- captures audience + address
- hands off to Telegram with `?start=` payload
- skips retyping
- routes quickly into the bot
- keeps the brand shell clean

What the funnel needs is not more decoration.
It needs the result surface to feel premium.
That means the free valuation card must look like a serious first appraisal, then show a clear upgrade path:
- floor area firm-up
- stronger cross-checks
- full PDF / interactive report
- richer subject / comp analysis

## Bottom line

The free version should feel like:
> "Damn, if this is free, what does paid do?"

Not:
> "This is a thin postcode average."

The paid Cronin appraisal is the reference.
The lite product should borrow its structure, not its exact spend.
