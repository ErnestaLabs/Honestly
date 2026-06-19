# Honestly Project Instructions

## Product constitution

Every change must improve conversion, retention, or decision trust. If a feature does not help a user reach a defended property decision or come back for monitoring, do not add it.

Core promise:

> One address. A defended price. Sold evidence shown.

Honestly is a Transparent AVM, not a generic property blog or a PropertyData wrapper. The moat is visible evidence, confidence, explanation, decision intelligence, and retention.

## Non-negotiables

- Preserve existing district reports unless explicitly asked to redesign them.
- Do not edit `HERMES_PROMPT.md` for coding-agent rules.
- Do not make PropertyData, Street Data, Chimnie, PaTMa, or any commercial same-data aggregator a valuation dependency.
- Do not route proof to paywalled PropertyData transaction pages.
- HMLR row shown inside Honestly is proof. Use open HMLR URI where available, or GOV.UK sold-price search fallback.
- Never use the subject property's own previous sale as a comparable.
- Prefer valuation comps within 12 months.
- Hard cap valuation comps at 24 months.
- Search 0.5 miles first. If fewer than 5 comps, expand geography, not time.
- Do not blend unrelated property types into the valuation anchor.
- Missing floor area lowers confidence only. It must never block first value.
- Do not ask for floor area, EPC, income, deposit, term, tenure, or mortgage details before the first value.
- Allowed before first value: address, purpose, situation, condition, known asking/offer/agent valuation.
- Free must prove trust fast: valuation, range, confidence, proof rows, plain English, lightweight PDF evidence pack, next action.
- Paid sells decision intelligence: affordability pressure, down-valuation exposure, pre-survey risk, seller liquidity, compare homes, watchlist/monitoring, full decision pack.
- Paid does not mean paying aggregators for the same public data.

## Public copy bans

Do not use these on public pages:

- reader / readers
- authority engine
- the product
- blog page
- How we did this
- How we built this
- Why compare on a blog page
- Because the blog
- internal/meta copy about our content strategy
- the word "working" in public copy

Run `python seo_audit.py` after public-page changes.

## Source spine

P0 direct sources:

- HM Land Registry Price Paid Data and HPI
- EPC register for floor area and rating where available
- Postcodes.io / ONS geography
- Bank of England rates
- GOV.UK fallback pages for proof/search

P1 context sources:

- Police.uk
- Environment Agency
- Ofcom
- VOA/local authorities
- OS OpenData

Context must not silently move the valuation. It can explain confidence, risk, and next action.

## Telegram-first conversion flow

The bot flow should be:

1. Address.
2. Purpose/situation/condition/known price if useful.
3. Immediate free valuation with confidence and proof rows.
4. Lightweight evidence PDF.
5. Paid decision modules only after trust is created.

Avoid pre-value forms. The user should see value before friction.

## Persistent LLM wiki protocol

This repo now uses the Karpathy LLM Wiki pattern in `knowledge/`.

- Raw immutable sources live in `knowledge/raw/`.
- LLM-maintained markdown pages live in `knowledge/wiki/`.
- `knowledge/wiki/index.md` is the content map.
- `knowledge/wiki/log.md` is the chronological operation log.

Before strategy, product, valuation, funnel, or data-source work:

1. Read `knowledge/wiki/index.md`.
2. Read the pages linked from the relevant section.
3. Update affected wiki pages when a durable decision changes.
4. Append an entry to `knowledge/wiki/log.md`.

When ingesting a new source:

1. Save the source in `knowledge/raw/` if it is not already present.
2. Create or update one summary page in `knowledge/wiki/`.
3. Update related pages and backlinks.
4. Update `index.md`.
5. Append to `log.md` with date, source, and changed pages.

The wiki is internal memory, not public copy. It can mention strategy and implementation constraints that should never appear on public pages.

## Testing and deploy discipline

Before deploy after valuation/bot changes, run at minimum:

```bash
python -m py_compile engine.py bot.py land_registry.py appraise.py report.py decision_models.py
python -m pytest test_bot.py test_land_registry.py test_decision_models.py test_engine_own_figure.py
```

Deploy only after local compile/tests pass and production module list includes any new Python files.
