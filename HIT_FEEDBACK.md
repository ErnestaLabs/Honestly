# Hit MCP — Field Feedback for Codex

**Context:** Voice-of-customer research for usehonestly.co.uk (UK property valuation). ~1 research
scan across r/HousingUK, r/UKPersonalFinance, r/FirstTimeBuyerUK, r/HousePricesUK with
`hit_scan(workflow=research, return_posts=true, include_comments=true)`. This doc merges the
operator's field notes with engineering recommendations so it can be actioned directly.

---

## What works (keep / protect)

- **Real threads, real human quotes** — not AI summaries. The verifiable Reddit links are the
  core value. Comment extraction surfaced the *actual* pain ("zoopla estimate is a load of
  bullshit, check sold prices on the street") that the OP title never showed. This is the moat.
- **SSR triage** is a useful gut check *as a concept*.
- **Cross-subreddit search** works when keywords land.
- `search_queries` + `time_filter` + `include_comments` is the right surface for VOC work.

---

## Issues, ranked by (impact ÷ effort)

### P0 — Structured JSON output  *(high impact, low effort)*
**Problem:** Output is a text firehose. The consumer (me, an agent) has to regex-parse titles,
scores, quotes, links back out of prose. That blocks dashboards, dedup, alerts, and the Honestly
Reddit-intel page.
**Fix:** Add `response_format: "json"` (keep text as default for humans). Per-post shape:
```json
{
  "scan_id": "scan_...",
  "posts": [{
    "id": "t3_1i3lsca", "subreddit": "HousingUK",
    "title": "...", "url": "https://...", "permalink": "...",
    "score": 0, "upvotes": 142, "num_comments": 38,
    "created_utc": 1737000000, "age_hours": 73.2,
    "ssr": 0, "ssr_band": "COLD", "matched_query": "zoopla estimate accurate or wrong",
    "matched_keywords": ["zoopla estimate"],
    "body_excerpt": "...",
    "comments": [{ "id":"...", "permalink":"...", "score": 21, "quote":"...", "matched_keywords":["sold prices"] }]
  }]
}
```
Everything below gets easier once this exists. **Ship first.**

### P0 — Dedup across scans  *(high impact, low effort — falls out of P0 JSON)*
**Problem:** Same thread reappears in every scan with overlapping keywords (operator saw one
thread hit in 3 scans).
**Fix:** Canonical post id (Reddit `t3_*`). Add `dedup_against_scan_ids: [...]` param and/or a
server-side seen-set per session. Return `first_seen_scan_id` so repeats are visible but not noisy.

### P1 — Query expansion layer  *(high impact, medium effort — the 80/20 of "semantic")*
**Problem:** Keyword matching is brittle. "down valuation" hits; "offering on a house" misses
because the post is titled "Offer accepted… now what?". Operator is "playing keyword roulette."
**Fix (cheap):** Before hitting Reddit search, expand each keyword/query with an LLM into a
synonym/intent set, e.g. `"offering on a house"` → `["offer accepted","made an offer","sealed
bids","gazumped","how much to offer","asking vs offer"]`, then OR-search them. Return
`expanded_from` per match so it's auditable. This gets ~80% of semantic value without a vector DB.
**Fix (full):** embed posts + vector search (see P2).

### P1 — SSR calibration  *(high impact, medium effort)*
**Problem:** Scoring feels arbitrary and capped. A 2,100-upvote / 420-comment thread and a sleepy
council-tax thread both land SSR=20 COLD. It isn't tracking what matters.
**Fix:** Make SSR an explicit, documented function with weighted, normalized components:
- engagement velocity: `comments / age_hours` (z-scored within subreddit, not absolute)
- intent/emotion: classifier over title+body+top comments for buying/selling-intent and pain
  language ("overpaid", "down valued", "can't trust", "is this worth") — regex seed now, LLM later
- recency decay: `exp(-age/τ)`
- subreddit base-rate normalization (r/HousingUK volume ≠ niche sub)
Return the **sub-scores**, not just the total, so the operator can see *why* something is WARM.
Expose `min_ssr` filter so low-signal noise can be dropped server-side.

### P2 — "Find more like this"  *(high impact, medium-high effort)*
**Problem:** Find a gold thread, can't pivot to neighbors without re-guessing keywords.
**Fix:** `hit_similar(post_id, limit)` — embed the seed thread (title+body+top comments),
nearest-neighbor over an embedded post index. Natural pairing with the full-semantic version of P1
(same embedding infra). This is the feature that turns blind scans into exploration.

### P2 — Trend / discovery mode  *(high value, medium effort)*
**Problem:** Can only find what you already know to search for. "What's hot in r/HousingUK this
week?" is impossible — and the best intel is what you didn't know to ask.
**Fix:** `hit_trends(subreddits, window)` — pull /hot + /top(window), compute delta vs a rolling
baseline, cluster by topic (embeddings or cheap TF-IDF), return rising topics with exemplar threads.
Distinct mode from targeted scan (discovery vs retrieval).

### P3 — Scan speed  *(medium impact, low-medium effort)*
**Problem:** 30–60s/scan. Fine for research, too slow to monitor 10 subs × 50 keywords.
**Fix:** Fan out subreddit/query fetches concurrently (looks sequential today); cache Reddit
responses ~5–15 min; return partial results streaming if the protocol allows. Async fetch alone
likely 3–5× the throughput.

---

## Operator pricing read (validated, with my note)

| Tier | Operator's number | Eng note |
|---|---|---|
| One research session (saveable + structured export) | £5–£10 | Trivial once P0 lands |
| Monthly: saved searches, dedup, trend alerts, exports | £29–£49/mo | Needs P0+P1; fair for power users |
| API: unlimited calls, embed in product (Honestly intel page) | £99–£199/mo | The real business. "Replaces a junior researcher." |
| One-off "everything Reddit says about [area/market]" report | £49–£99 | trend mode (P2) + structured export |

---

## Bottom line

Hit is a **powerful engine with a text-based UX**. The pricing lives in the gap between what it is
(keyword-text-search + good-instinct SSR) and what it could be (structured API + semantic/expansion
+ calibrated scoring + trend discovery). **Build order: P0 JSON+dedup → P1 query-expansion +
SSR calibration → P2 similar + trends → P3 speed.** P0 is a weekend and unblocks the whole ladder.

**The actual moat** is not the search — generic Reddit search tools exist. It's (a) comment-level
quote extraction, (b) a *calibrated* intent/SSR score, and (c) the scan→queue→approve outreach loop
in lead_generation mode. Double down there; that's what nobody else has.

---

## Session log — 2026-06-09 (research scan, usehonestly.co.uk copy)

**Scan:** `hit_scan(workflow=research)` across r/HousingUK, r/FirstTimeBuyerUK, r/HousePricesUK,
r/UKPersonalFinance. Keywords/queries around Zoopla-estimate trust, overpaying, down valuations,
agent over-valuation. `return_posts=true, include_comments=true`.

**Reinforces (already filed above):**
- **SSR all-COLD again.** Every returned post scored COLD, including threads with high engagement.
  Confirms the **P1 SSR-calibration** gap — the score is not separating signal from noise, so the
  operator ignores it and reads quotes manually. This is now observed across multiple sessions, not
  a one-off. Bump P1 priority.
- **Comment-level extraction is the value, again.** The strongest copy-usable quotes came from
  comments, not OP titles (the DIY "check what similar homes on your street actually sold for"
  advice never appears in a title). Protect this.

**New observation — VOC quality is high enough to drive product copy directly.** This scan produced
verbatim lines that went straight into the landing page (Zoopla distrust → hero/objection copy;
"overpaid and ruminating" → buyer pain clause; "highest number wins the instruction" → seller
clause). That is the concrete £-value case for the **structured JSON export (P0)**: an operator
should be able to tag a quote → export → drop into a brief without re-reading the firehose.

**Net:** no new feature classes — this session is corroborating evidence for the existing P0 (JSON
export) and P1 (SSR calibration) build order. The ranking holds.
