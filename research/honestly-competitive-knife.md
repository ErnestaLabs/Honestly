# Honestly - The Competitive Knife

> The third of the three planned deliverables (api-inventory, bot-architecture,
> competitive-knife). Positioning: what Honestly has that nobody else does, what to build
> next to extend the gap, and the exact messaging that turns each competitor's weakness
> into our line. Primary evidence is `HONESTLY_reddit_voc_intel.md` (verbatim Reddit VOC
> via the Hit MCP scans, thread IDs preserved). Every CAPABILITY claim below is traced to
> a line of our own code - nothing here is asserted from how the system "should" work.
> Zoopla/Rightmove are deliberately out of scope (portals everyone already benchmarks).

---

## 0. The one-sentence knife

**Every rival gives you a number with no working, or a pile of data with no number.
Honestly gives you one figure and the arithmetic that produced it - anchored on sold
evidence, never moved by HPI, and steered by the live market only within a disclosed
+6% / -5% cap.**

That sentence is defensible line by line in the code:

- "anchored on sold evidence" - `appraise.apply_market` sets `val['sold_anchor'] =
  val['central']` before any live-market move; sold + AVM is the floor of fact.
  (`appraise.py:486`)
- "never moved by HPI" - HPI is reported beside the figure as context; it is not a term
  in `valuation()`. The HMLR cross-check note says it in plain text: the register read "is
  never blended into the figure." (`engine.py:145`)
- "steered ... within a disclosed +6% / -5% cap" - `factor = 1.0 + (0.06 * t if t >= 0
  else 0.05 * t)`, with the market temperature `t` clamped to `[-1, +1]`, and the working
  recorded under `val['market']`. (`appraise.py:505-510`)

This is the whole thesis: a glass box where the competition ships black boxes or raw
tables.

---

## 1. The competitive field (six lanes, all real)

| # | Competitor | What they sell | Their fatal complaint (VOC) | Honestly's knife |
|---|---|---|---|---|
| 1 | **Estate agents** (the human valuation) | a free valuation set to win the instruction | "Some agents give high valuations because it helps them seal the deal" (HousingUK 1b6ctuo); industry itself: "stop over-valuing to gain instructions" (yino8f) | a figure with **no instruction to chase and no commission riding on it** |
| 2 | **Surveyors / lender AVMs** (the down-valuation) | a desktop figure that can sink a deal | "the lender ... down valued the property to £640k based on a **desktop valuation**" (1kpoegt); a £60k swing between lenders on one house (12bg0zv) | the **evidence pack you bring INTO the down-valuation fight** - the working the lender refuses to show |
| 2b | **Calculator soup** (free black boxes) | one estimate each, no working | one £265k house: Nationwide HPI £242,142 vs Mouseprice £264,000, a ~£22k spread (UKPF bjgr0e) | **one figure, plus the arithmetic** - replaces the scatter with a defended number |
| 3 | **Sprift** | agent-facing data-on-one-page | thin consumer VOC; built B2B, never for buyers/sellers | a **glass-box figure anyone can verify**, not a pro data dump |
| 4 | **Data incumbents** (PropertyData, Mouseprice, NetHousePrices) | sold rows + an estimate | "the biggest friction ... is always getting structured property data **in**" reasoned to an answer (MCP thread 1s81yoc) | the **layer above** - same data, reasoned into a defended figure |
| 5 | **Indie/free tools** (propertylookup, truely.uk, mypropertyanalyst, propertypiper, postcode scorers, the £/sqft extension) | each does ONE thing well | "the property app this sub has been asking for" - 561 upvotes, 567 comments (1c19hmr) | the **integration none of them are**: sold + EPC + per-sqft + finish tier + area/safety + capped market steer, in one figure |
| 6 | **DIY spreadsheet** | the manual fallback distrust forces | "I put it together in a spreadsheet myself" (1hixnwe) | **the spreadsheet you were going to build anyway - in 30 seconds, working shown** |

Note the structural point: lanes 1, 2 and 2b complain about **numbers with no working**;
lanes 4 and 5 complain about **data with no number**. Honestly is the only thing in the
field that closes both gaps at once.

---

## 2. The proof the knife is real (this build cycle's spine work)

A positioning claim is only a knife if the product behind it actually does the thing. This
cycle hardened exactly the parts the VOC says the market craves, and each is grounded in
shipped, tested code (the offline suite is green at 300 tests).

### 2.1 An independent official-sold check - directly answers lane 2 and lane 2b
The black-box down-valuation (lane 2) and the calculator soup (lane 2b) both lose to a
figure you can independently verify. `engine.summary()` now carries a `crosscheck` block
that pulls the **raw HM Land Registry Price Paid register for the exact postcode** (SPARQL,
OGL) and shows it beside our tier-matched comparable set, naming both medians and their
divergence. (`engine.py:146-159`) Critically, the note states the register read "is never
blended into the figure" - it is a check on the evidence, not an input. That is the literal
"is it worth renegotiating?" evidence pack the down-valuation threads beg for.

The HMLR read is also a quiet engineering moat: a bare prefix scan times out, so the client
binds the sector's exact postcodes via a `VALUES` block to stay on the postcode index (a
whole sector resolves in about a tenth of a second). Competitors hitting the same endpoint
naively cannot do area-level official checks at interactive speed.

### 2.2 Sector-level demand - answers lane 5's postcode-scorer competitors
The investor-lane rivals are postcode scoring tools (crime/yield/demand/flood). `demand.py`
now counts transactions at **postcode-sector** level (enumerating the sector's members via
Postcodes.io, then one indexed HMLR count), so confidence is driven by real sector volume
rather than the sparse single-unit-postcode counts that read "quiet" everywhere. A live run
over SE15 6 returned 47 sales, lifting confidence to "good" where a unit-postcode count
would have shown "low". This is the same beside-the-figure context the scorers sell, but
paired with a defended valuation they do not have.

### 2.3 An independent EPC / floor-area cross-check - answers lane 5's data aggregators
truely.uk and propertylookup market "Land Registry + EPC + crime + flood in one report".
`epc.py` pulls floor area and EPC rating **straight from the DLUHC register** as an
independent firm-up of `sqm` and the NTSELAT material-information block, degrading honestly
to `{ok: False, reason}` with no credentials and never raising. We match their data spine
and then do the thing they cannot: reason it into a figure.

### 2.4 Photos -> finish tier, conservatively - extends the one honest lever
Condition is the **one** input that legitimately moves the figure, via the engine's existing
finish tiers on `v['avm']`. `vision.py` proposes the condition sub-survey signals from
listing photos and derives the tier through the **same confirmed `bot.derive_finish` path**
(`vision.py:114-128`) - it never invents a new figure input, leaves overall condition for
the human (photos cannot judge dilapidation), credits a room only on clear premium-material
evidence, and caps its own confidence at "medium". It pre-fills the lever; a human still
confirms before it moves anything. This is the glass box applied to its own most sensitive
knob.

**The through-line:** every spine addition this cycle sits BESIDE the figure as sourced
context. The only thing that moves the number is the disclosed, capped market steer and the
human-confirmed condition tier. That discipline IS the product - it is what lets us say
"defensible" and mean it.

---

## 3. Exact messaging per competitor weakness

Lead the landing copy with lane 2b - it is the single cleanest statement of the thesis and
it comes pre-quantified by the market (a real ~£22k spread between three free black boxes on
one £265k house).

1. **vs estate agents:** "A valuation with no instruction to win and no commission riding on
   it." (backed by the industry's own admission, not just aggrieved sellers)
2. **vs surveyor / lender AVM:** "The evidence pack you bring to a down-valuation - the
   working the lender's desktop model refuses to show."
3. **vs calculator soup:** "Three free calculators, three different numbers, a £22k spread,
   none of them showing their working. One figure. The arithmetic. Done."
4. **vs the indie field:** "Every free tool gives you one piece. This gives you the answer."
5. **vs the 561-upvote unmet demand:** "The property tool this sub has been asking for -
   built."
6. **vs DIY:** "The spreadsheet you were going to build anyway, in 30 seconds, with the
   working shown."

---

## 4. What to build next to widen the gap

Ranked by how directly each closes a VOC-proven want without violating the honesty contract
(nothing below becomes a new input to `valuation()`):

1. **Confidence score on the face of the figure** ("High confidence - N tier-matched
   comparables + official register agreement"). The cross-check divergence already exists in
   `engine.summary()`; surface it as a headline trust signal. Cheapest, highest-trust win.
2. **Area/safety context paired with the figure** - an 856-upvote post ("a 'perfect' house
   that turned out to be in a flood zone", 1j7sivz) proves the appetite. Police.uk, flood,
   and Overpass clients exist; the knife is that **no competitor pairs a defended figure WITH
   this context in one place**. Render the panels we already wired.
3. **Watchlist / monthly auto-refresh** - turns a one-off £5 figure into a standing
   relationship; the HMLR cross-check makes "what changed and why" honest.
4. **Side-by-side two-address comparison** - "Tools to help compare houses?" (1galtxp) is
   repeated unprompted demand nobody owns cleanly; our per-sqft glass box is the natural fit.
5. **Inline down-valuation pack export** - a one-tap PDF framed explicitly as "take this to
   your lender", productising messaging line #2.

---

## 5. The honesty caveat (it applies to our own positioning too)

- The VOC samples are strong but partial (consumer 40/233, agent 19, competitor-by-name
  70/160). Quote thread IDs, not "the data is exhaustive".
- Sprift's thin Reddit footprint is real (B2B), so its lane is a positioning read, not quoted
  market voice.
- Every capability claim in Section 2 is traced to current code and the green test suite. If
  a future change moves any of those lines, this doc is wrong until re-grounded - the same
  read-the-source rule we hold the copy to.
