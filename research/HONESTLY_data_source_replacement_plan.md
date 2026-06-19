# Honestly - PropertyData replacement plan

## Core conclusion
PropertyData is not the source. It is an aggregator over mostly public datasets plus portal/listing access and modelling.

Honestly should not be blocked by PropertyData credits.

More importantly: Honestly should not compete on raw data ownership. Everyone can reach roughly the same public facts. The moat is the model, confidence scoring, explainability, proof trail, and continuous learning.

The product is a **Transparent AVM (TAVM)**:

> a defended number, visible evidence, explicit confidence, and proof for every comparable.

The product spine can be rebuilt from direct sources:

- HM Land Registry for sold prices and HPI
- EPC register for EPC and floor area
- Postcodes.io / ONS for geography
- Police.uk for crime
- Environment Agency for flood
- Bank of England for rates
- Ofcom for broadband
- OS OpenData for maps/context
- local authorities / VOA where practical for council tax and rents

PropertyData becomes optional enrichment, not a hard dependency.

---

## Source map

| Data | Source | Replacement status |
|---|---|---|
| Sold prices | HM Land Registry Price Paid Data | P0 - direct, already partly wired in `land_registry.py` |
| House Price Index | HM Land Registry UK HPI | P0 - direct, already partly wired |
| EPC | MHCLG / EPC register | P0 - direct, `epc.py` exists |
| Floor area | EPC register + floorplan extraction later | P0 via EPC, P2 via floorplan extraction |
| Census | ONS | P1 |
| Crime | UK Police | P1, `police.py` exists |
| Flood risk | Environment Agency | P1, `flood.py` exists |
| Mortgage stats | Bank of England | P0/P1, `macro_live.py` exists |
| Broadband | Ofcom | P1 |
| Maps | Ordnance Survey / Postcodes.io / Google fallback | P1 |
| Council Tax | Local authorities / VOA where available | P1, `council_tax.py` exists |
| Planning | Planning API provider / local authority portals | P2 - likely paid or fragmented |
| Listings | Rightmove, Zoopla, OnTheMarket | P2 - licensing risk; do not rely on scraping for launch |
| Rental listings | Rightmove, Zoopla, OTM, SpareRoom | P2 - licensing risk; launch with VOA/ONS + user-provided asking rent where needed |
| Commercial quoting rents | VOA + MHCLG + modelling | P2 |

---

## P0: make valuation independent of PropertyData

### Goal
A user can get a defensible sold-evidence valuation even when PropertyData has zero credits.

P0 does not need portal scraping. It needs to say, reliably:

> this comparable home sold for £X; here is the HM Land Registry proof.

### Inputs
- Address with postcode
- Optional beds
- Optional property type
- Optional condition
- Optional asking/quoted price

### Direct-source pipeline
1. Extract postcode from address.
2. Resolve postcode via Postcodes.io.
3. Pull exact-postcode sold transactions from HM Land Registry.
4. If thin, widen to outcode/nearby postcodes through Postcodes.io enumeration.
5. Infer property type from:
   - HMLR transaction type if the address has sold
   - EPC property type if matched
   - address string fallback
   - postcode dominant type fallback
6. Build comps from direct HMLR rows.
7. Use recent same-type evidence first.
8. Compute range and central from weighted sold comps.
9. Show confidence and the exact evidence.
10. Keep asking price separate as context.

### Acceptance criteria
- No PropertyData call required for the free/lite valuation.
- If HMLR has no usable evidence, say so. Do not invent a number.
- Every comp links or traces to HM Land Registry.
- User-facing copy says sold-evidence estimate / comparative market appraisal, not RICS valuation.

---

## P1: rebuild the context layer from open sources

Add beside-the-figure context without moving the value:

- EPC rating and floor area from EPC register
- flood from Environment Agency
- crime from Police.uk
- broadband from Ofcom
- mortgage/rates from BoE
- schools from government datasets
- council tax from VOA/local authority source where available
- ONS census/area stats

Rule: context never silently moves the figure.

---

## P2: live listings and rental data

This is the only hard part.

Rightmove, Zoopla, OnTheMarket and SpareRoom are not clean free data sources. Scraping them blindly is a legal/product risk and can break anytime.

Launch-safe alternatives:

1. Ask the user for the asking price manually.
2. Let the user paste a listing URL and extract only what they provide/authorise.
3. Use user-uploaded floorplans/photos for floor area and condition enrichment.
4. Add a licensed listings provider later.
5. Treat portal listings as optional context, never the valuation anchor.

For rental/yield:

- P1: use VOA/ONS rental statistics for area-level rent context.
- P2: add live rental listings only through a licensed or user-provided path.

---

## Why this is better than PropertyData for the wedge

For the monopoly wedge, the key data is sold evidence, not portal breadth.

Direct HMLR gives:

- official source
- no credit cap
- no aggregator dependency
- cheaper operation
- better trust story
- reproducible evidence

PropertyData can still be useful for:

- fast paid enrichment
- live listings
- schools endpoint
- convenience while replacing pieces

But it must not be the thing that decides whether the bot works.

---

## Launch stance

Tonight’s launch should not promise live portal intelligence if we do not have licensed/robust access.

Launch promise:

> One address. A defended price. Sold evidence shown.

That can run on HMLR + EPC + Postcodes.io.

The first product category is not “another AVM.” It is:

> the UK's most transparent property valuation engine.

Transparency is visible immediately. Accuracy compounds through backtesting once predicted values can be compared to later HMLR sold prices.

Future promise after listings/rent licensing:

> Sold evidence plus live market pressure.

Do not sell the future promise until the data route is real.

---

## Engineering next steps

1. Make `tier="lite"` the default free path everywhere user-facing.
2. Ensure `geo.py`, `land_registry.py`, and `epc.py` are in deploy forever.
3. Add tests that simulate missing `PROPERTYDATA_KEY` and prove the bot still returns a lite valuation.
4. Gate all PropertyData-only enrichments behind Pro/paid and graceful fallback.
5. Add a clear data-source block to reports: HMLR direct, EPC direct, asking price user-provided if present.
6. Add a nightly HMLR cache/SQLite ingest so queries are local and fast.
7. Add EPC cache keyed by UPRN/address/postcode.
8. Keep portal/listing work out of P0 unless licensed or user-provided.
