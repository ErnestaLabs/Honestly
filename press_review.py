"""press_review.py - frozen-artifact loader/shaper for the blog's "Headlines vs the data".

The brief, in the user's words: find other people's newsletters, blog posts and articles
about a city's property market, recognise them, cite them, and clarify - from a pure
analytical perspective.

This is a fact-check, not a take-down. Each external publication is the INPUT we are
checking: we quote its claim verbatim, attribute it to its publisher with an outbound
link, and then set it beside the one thing we can speak to with authority - the official
sold record for that city's postcode districts, which we already publish daily. We never
call a journalist wrong; we add the ground-level transaction figure they did not have, and
we are explicit about the limits of what sold data can and cannot confirm.

Honesty contract (ABSOLUTE, carried from social_sentiment.py / market_study.py):
  * The external claims are captured OUT OF BAND (via WebSearch when that tooling is
    connected), shaped here, and frozen to press_review.json. The headless daily build
    (publish_daily.py --rebuild) has no web access: it only reads/renders the frozen file.
  * Not one external claim ever becomes a figure on the page. Every number we print in the
    clarification comes from THIS city's own stored district models (the same HM Land
    Registry / live-listing figures the district pages and the study already report, via
    the shared market_study._row_from_model derivation - so the commentary can never drift
    from the rest of the network).
  * Where a claim is about something sold data cannot measure (a forecast, sentiment, a
    policy effect), we say so plainly and decline to dress it up as confirmed or refuted.

Nothing here ever raises into the build: a missing or malformed file yields {} and the
section simply omits.

Public surface:
  load(city_slug)                       -> one city's frozen claims block, or {}
  shape_articles(items, ...)            -> normalise captured search hits into claim dicts
  build_block(claims=, captured_at=, ...) -> a renderable block with provenance + disclaimer
  freeze(city_slug=, block=)            -> merge one block into press_review.json
  city_snapshot(city_slug, store_mod=)  -> this city's aggregated sold/listing figures
  clarify(claim, snapshot)              -> the honest reconciliation for one claim
"""

import json
import os
import statistics

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "press_review.json")

# The metrics a claim may be checked against. Each maps to a figure we genuinely hold for
# the city, derived from market_study._row_from_model so it matches the study and the
# district pages exactly. Anything outside this set is treated as "beyond sold data".
_METRICS = ("sold_median", "psm", "mean_dom", "asking_gap", "stuck_share", "sales_12m")

# Soft band: a claimed figure within this fraction of our recorded figure is "broadly in
# line with the local record"; beyond it, we note the divergence with its direction.
_MATCH_BAND = 0.10


# --------------------------------------------------------------------------- frozen file
def _read():
    """Whole frozen file as {by_city:{...}}; {} on any error. Never raises."""
    try:
        with open(_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load(city_slug):
    """Best-effort load of one city's frozen claims block. Returns {} when nothing applies
    (so the caller renders no commentary page). Never raises."""
    data = _read()
    by_city = data.get("by_city") or {}
    block = by_city.get(city_slug)
    if isinstance(block, dict) and block.get("claims"):
        return block
    return {}


def cities_with_claims():
    """City slugs that currently carry a frozen claims block. Pure read, never raises."""
    data = _read()
    by_city = data.get("by_city") or {}
    return [s for s, b in by_city.items()
            if isinstance(b, dict) and b.get("claims")]


# --------------------------------------------------------------------------- shaping
def _clean_metric(m):
    m = (m or "").strip().lower()
    return m if m in _METRICS else ""


def _clean_dir(d):
    d = (d or "").strip().lower()
    return d if d in ("up", "down", "high", "low", "flat") else ""


def shape_articles(items, *, max_claims=6):
    """Turn raw captured search hits into clean claim dicts.

    Each input item is a dict from a web search / fetch; this normalises it to the canonical
    claim schema the renderer expects and keeps only the strongest few. Pure/defensive:
    unknown keys are ignored, missing fields default to empty, and it never raises. A claim
    with no quote or no source URL is dropped - we never cite what we cannot link to.

    Canonical claim schema:
      publisher       who said it (masthead/outlet)             - required
      title           the article headline                       - required
      url             the public article URL                     - required
      date            publication date string (as printed)       - optional
      quote           the specific assertion, verbatim/trimmed    - required
      topic           short human label ("Asking prices", ...)    - optional
      metric          which of our figures bears on it            - optional, in _METRICS
      claim_dir       direction the article asserts (up/down/...) - optional
      claim_value     a numeric figure the article states         - optional (for comparison)
      claim_value_str how that figure was printed                 - optional
      dek             one-line analytical subhead for the claim    - optional
      analysis        authored prose paragraphs (full-article body)- optional, list[str]

    dek/analysis carry the written analysis: a human reads the verbatim claim, then several
    grounded paragraphs setting it against this city's OWN sold record. Every figure in that
    prose must be a snapshot figure (never the quoted article's number) - the author's
    responsibility at freeze time; the renderer prints them as written.
    """
    out = []
    for p in (items or []):
        if not isinstance(p, dict):
            continue
        quote = (p.get("quote") or p.get("claim") or "").strip()
        url = (p.get("url") or p.get("link") or "").strip()
        publisher = (p.get("publisher") or p.get("source") or p.get("outlet") or "").strip()
        title = (p.get("title") or p.get("headline") or "").strip()
        if not (quote and url and publisher and title):
            continue
        cv = p.get("claim_value")
        try:
            cv = float(cv) if cv is not None and cv != "" else None
        except (TypeError, ValueError):
            cv = None
        out.append({
            "publisher": publisher,
            "title": title,
            "url": url,
            "date": (p.get("date") or "").strip(),
            "quote": quote,
            "topic": (p.get("topic") or "").strip(),
            "metric": _clean_metric(p.get("metric")),
            "claim_dir": _clean_dir(p.get("claim_dir")),
            "claim_value": cv,
            "claim_value_str": (p.get("claim_value_str") or "").strip(),
            "dek": (p.get("dek") or "").strip(),
            "analysis": [str(x).strip() for x in (p.get("analysis") or []) if str(x).strip()],
        })
        if len(out) >= max_claims:
            break
    return out


def build_block(*, claims, captured_at,
                source_label="Public reporting on the UK property market",
                method="", disclaimer="", intro=None, synthesis=None):
    """Assemble one renderable city block from shaped claims + provenance.

    captured_at is required (passed in - this module never calls a clock). The default
    disclaimer and method carry the honesty posture verbatim; callers can override.

    intro/synthesis (each a list of authored paragraph strings, optional) are the article's
    opening and closing prose. Like a claim's analysis they are written at freeze time and
    must reference only this city's own snapshot figures; the renderer prints them verbatim.
    """
    if not method:
        method = ("We collect recent, publicly published newsletters, blog posts and articles "
                  "about this city's property market, quote each verbatim with a link to the "
                  "original, and set it beside the official sold record for the city's postcode "
                  "districts that we already publish. We recognise the source, cite it, and "
                  "clarify - we do not rewrite anyone's reporting.")
    if not disclaimer:
        disclaimer = ("These are other people's published claims, cited as such. They are checked "
                      "against the recorded sold prices for this city's postcodes. National or "
                      "regional commentary can be right about its own scope while the local figure "
                      "looks different - both can be shown without declaring a winner. Not one "
                      "quoted claim is a figure on this page; every number in the clarification is "
                      "the city's own sold record.")
    def _paras(x):
        return [str(p).strip() for p in (x or []) if str(p).strip()]
    return {
        "captured_at": captured_at,
        "source_label": source_label,
        "method": method,
        "disclaimer": disclaimer,
        "intro": _paras(intro),
        "synthesis": _paras(synthesis),
        "claims": [c for c in (claims or []) if isinstance(c, dict) and c.get("quote")],
    }


def freeze(*, city_slug, block, path=None):
    """Write/merge one block into press_review.json under by_city[city_slug]. Reads the
    existing file first so freezing one city never clobbers another. Best-effort: returns
    True on success, False on any failure; never raises."""
    target = path or _PATH
    try:
        try:
            with open(target, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        data.setdefault("by_city", {})
        if city_slug:
            data["by_city"][city_slug] = block
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- the data side
def _med(vals):
    xs = [v for v in vals if v is not None]
    return round(statistics.median(xs)) if xs else None


def city_snapshot(city_slug, *, store_mod=None):
    """This city's aggregated sold/listing figures, from its OWN stored district models.

    Reuses market_study._row_from_model so every figure matches the district pages and the
    cross-city study exactly (numbers never drift). Returns {ok: False, reason} when there is
    too little data to be worth a fact-check page, else {ok, name, country, n_districts,
    metrics:{...}, rows:[...]}. Best-effort: never raises.
    """
    if store_mod is None:
        try:
            import store as store_mod
        except Exception:
            return {"ok": False, "reason": "no database"}
    try:
        import market_study
        metas = store_mod.list_blog_posts(city_slug)
    except Exception as exc:                                # pragma: no cover
        return {"ok": False, "reason": f"db read failed: {exc}"}

    rows, name, country = [], "", ""
    for meta in metas:
        post = store_mod.get_blog_post(meta["slug"], with_model=True)
        m = (post or {}).get("model") or {}
        if not m:
            continue
        r = market_study._row_from_model(m)
        if r:
            rows.append(r)
            name = name or r.get("city") or ""
            country = country or r.get("country") or ""
    if len(rows) < 3:
        return {"ok": False, "reason": f"only {len(rows)} {city_slug} districts with a sold basis"}

    sold = [r["sold_median"] for r in rows if r.get("sold_median")]
    metrics = {
        "sold_median": _med([r.get("sold_median") for r in rows]),
        "sold_low": min(sold) if sold else None,
        "sold_high": max(sold) if sold else None,
        "psm": _med([r.get("psm_median") for r in rows]),
        "mean_dom": _med([r.get("mean_dom") for r in rows]),
        "asking_gap": _med([r.get("asking_gap_pct") for r in rows]),
        "stuck_share": _med([r.get("stuck_share_pct") for r in rows]),
        "sales_12m": sum(r.get("sales_12m") or 0 for r in rows) or None,
    }
    as_of = max((r.get("generated_at") for r in rows if r.get("generated_at")), default="")
    return {"ok": True, "name": name, "country": country, "city_slug": city_slug,
            "n_districts": len(rows), "as_of": as_of, "metrics": metrics, "rows": rows}


# How each metric is read for the clarification: the snapshot key, a formatter, and a
# human noun. money/pct formatting is done by the renderer; here we keep it source-pure.
_METRIC_LABEL = {
    "sold_median": "recorded median sale price",
    "psm": "recorded price per square metre",
    "mean_dom": "average time to sell",
    "asking_gap": "asking price against the sold median",
    "stuck_share": "share of stock stuck 90+ days",
    "sales_12m": "recorded sales in the last 12 months",
}


def clarify(claim, snapshot):
    """The honest reconciliation for one claim, computed live from the snapshot (never frozen).

    Returns a dict the renderer turns into the "what the sold record shows" half of a card:
      metric        the metric checked (or "" when beyond sold data)
      label         human noun for the metric
      our_value     the city's figure for that metric (raw number, or None)
      our_kind      "gbp" | "gbp_psm" | "days" | "pct" | "count" - tells the renderer the unit
      verdict       a short, conservative tag (see below)
      sentence      a plain-English clarification, no figure that is not in the snapshot

    Verdict vocabulary (deliberately not a truth score - we add ground truth, we do not rate
    the journalism): "Grounded by the local record", "Broadly in line with the local record",
    "The local record differs", "Beyond what sold data can confirm".
    """
    metric = _clean_metric(claim.get("metric"))
    metrics = (snapshot or {}).get("metrics") or {}
    name = (snapshot or {}).get("name") or "this city"
    n = (snapshot or {}).get("n_districts") or 0

    if not metric or metrics.get(metric) is None:
        return {
            "metric": "", "label": "", "our_value": None, "our_kind": "",
            "verdict": "Beyond what sold data can confirm",
            "sentence": (f"This is commentary the recorded sold prices for {name} cannot "
                         f"directly measure - a forecast, a sentiment read or a policy effect. "
                         f"It is left as commentary, not dressed up as confirmed or refuted: "
                         f"the sold record shows what happened, not what might happen."),
        }

    val = metrics[metric]
    kind = {"sold_median": "gbp", "psm": "gbp_psm", "mean_dom": "days",
            "asking_gap": "pct", "stuck_share": "pct", "sales_12m": "count"}[metric]
    label = _METRIC_LABEL[metric]
    cv = claim.get("claim_value")

    if cv is not None and metric in ("sold_median", "psm", "mean_dom", "sales_12m") and val:
        delta = cv / val - 1.0
        if abs(delta) <= _MATCH_BAND:
            verdict = "Broadly in line with the local record"
            sent = (f"The figure quoted is close to the local record: across the {n} {name} "
                    f"postcode districts reported here, the {label} is the anchor, and the "
                    f"claim sits within {int(_MATCH_BAND * 100)}% of it.")
        else:
            hi = "above" if delta > 0 else "below"
            verdict = "The local record differs"
            sent = (f"The quoted figure is materially {hi} the recorded {label} across the "
                    f"{n} {name} districts reported here. The source may be right about its "
                    f"own scope; the local sold record shows the gap between the two questions.")
    else:
        verdict = "Grounded by the local record"
        sent = (f"Here is the figure the headline is reaching for, measured directly: the "
                f"{label} across the {n} {name} postcode districts reported here, straight "
                f"from the sold record rather than a national average or an asking price.")

    return {"metric": metric, "label": label, "our_value": val, "our_kind": kind,
            "verdict": verdict, "sentence": sent}


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    import sys
    slug = sys.argv[1] if len(sys.argv) > 1 else None
    if slug:
        snap = city_snapshot(slug)
        blk = load(slug)
        print(f"snapshot {slug}: {snap.get('ok')} "
              f"({snap.get('n_districts', 0)} districts) {snap.get('reason', '')}")
        if snap.get("ok"):
            print("  metrics:", snap["metrics"])
        print(f"frozen claims: {len(blk.get('claims', []))}")
        for c in blk.get("claims", []):
            cl = clarify(c, snap) if snap.get("ok") else {}
            print(f"  - [{c.get('publisher')}] {c.get('quote')[:70]}...")
            print(f"      verdict: {cl.get('verdict')}")
    else:
        print("cities with frozen claims:", cities_with_claims())
