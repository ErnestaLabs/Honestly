# LLM Wiki Schema

Source: `knowledge/raw/karpathy-llm-wiki.md`.

## Purpose

This wiki is the persistent memory layer between raw documents and day-to-day coding. The agent should not re-derive product strategy from scattered chat summaries every time. It should read the compiled pages, update them when decisions change, and keep contradictions visible.

## Directory layout

```text
knowledge/
  raw/      immutable source documents
  wiki/     LLM-maintained synthesis pages
```

## Page conventions

Each wiki page should include:

- a clear title
- source references by file path
- durable decisions
- implementation implications
- contradictions or open questions when present
- backlinks to related pages using `[[page-name]]`

## Required files

- `index.md` - content-oriented map of the wiki.
- `log.md` - append-only chronological operation log.

## Ingest workflow

1. Save source material in `knowledge/raw/` when external or not already in repo.
2. Read existing `index.md` and related pages.
3. Create or update a wiki synthesis page.
4. Update cross-links and `index.md`.
5. Append to `log.md`.

## Query workflow

1. Read `index.md`.
2. Read pages relevant to the question.
3. Answer from the wiki first, then inspect code/docs only where needed.
4. If the answer creates durable synthesis, file it back into the wiki.

## Lint workflow

Periodically check for:

- contradictions between pages
- stale claims superseded by newer decisions
- orphan pages not linked from the index
- missing pages for important concepts
- decisions present in code but absent here

Related: [[honestly-product-constitution]], [[log]].
