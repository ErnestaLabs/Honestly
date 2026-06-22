#!/usr/bin/env python3
"""generate_seo_article.py — generate a hyper-local, data-backed SEO blog post.

Queries graph_db.py for real HMLR sold prices (last 12 months, median £ for
flats vs houses, yearly trend, market momentum), then calls OpenRouter (via
generate_blog.py's API pattern) to produce a fact-anchored SEO article.
Saves as Markdown to content/<slug>.md.

Usage:
  python scripts/generate_seo_article.py --postcode SW16
  python scripts/generate_seo_article.py --postcode SE15 --output my_blog.md
  python scripts/generate_seo_article.py --postcode SW16 --months 24 --no-llm
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Path setup ──────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent.parent  # project root
CONTENT_DIR = HERE / "content"
KEYS_PATH = HERE / "_keys.json"

# Add project root to sys.path so we can import graph_db
sys.path.insert(0, str(HERE))

from graph_db import GraphQuery

# ── OpenRouter config ──────────────────────────────────────────────────────
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "deepseek/deepseek-chat"
MAX_TOKENS = 4000
TEMPERATURE = 0.5  # lower temp for factual accuracy


# ── Postcode matching ───────────────────────────────────────────────────────
def _outcode_sql(outcode: str) -> tuple:
    """Build SQL WHERE clause to match all postcodes for a given outcode.

    Handles both formats in the DB:
      - With space:  'SW16 2JY'   (London format)
      - Without:     'M111AH'     (rest of UK, outcode + inward starting with digit)
    """
    oc = outcode.upper().strip()
    oc_len = len(oc)
    pattern_space = f"{oc} %"
    pattern_nospace = f"{oc}%"
    next_pos = oc_len + 1  # 1-indexed for SQLite substr()
    clause = (
        "(postcode LIKE ? "
        "OR (postcode LIKE ? AND postcode NOT LIKE '% %' "
        f"AND substr(postcode, {next_pos}, 1) BETWEEN '0' AND '9'))"
    )
    return clause, [pattern_space, pattern_nospace]


# ── Data extraction ─────────────────────────────────────────────────────────
def get_outcode_data(gq: GraphQuery, outcode: str, months: int = 12) -> dict:
    """Fetch and summarise HMLR data for a postcode outcode (e.g. SW16)."""
    now = datetime.now()
    window_ago = (now - timedelta(days=months * 30)).strftime("%Y-%m-%d")
    prev_window_ago = (now - timedelta(days=months * 60)).strftime("%Y-%m-%d")

    where_clause, params = _outcode_sql(outcode)

    def exec_query(sql, extra_params):
        return gq.db.execute(
            sql.replace("__OUTCOND__", where_clause),
            params + extra_params
        ).fetchall()

    def exec_count(sql, extra_params):
        return gq.db.execute(
            sql.replace("__OUTCOND__", where_clause),
            params + extra_params
        ).fetchone()[0]

    # ── Last N months: flats (F) vs houses (S, D, T) ──
    flats = exec_query(
        "SELECT price, date FROM hmlr_sales WHERE __OUTCOND__"
        " AND ptype=? AND date>=? ORDER BY date DESC",
        ["F", window_ago]
    )

    houses = exec_query(
        "SELECT price, date FROM hmlr_sales WHERE __OUTCOND__"
        " AND ptype IN (?,?,?) AND date>=? ORDER BY date DESC",
        ["S", "D", "T", window_ago]
    )

    def summarise(rows, label):
        if not rows:
            return {"label": label, "count": 0, "median": 0, "avg": 0, "min": 0, "max": 0}
        prices = sorted([r[0] for r in rows])
        n = len(prices)
        return {
            "label": label,
            "count": n,
            "median": prices[n // 2],
            "avg": round(sum(prices) / n),
            "min": prices[0],
            "max": prices[-1],
        }

    flat_stats = summarise(flats, "Flats (F)")
    house_stats = summarise(houses, "Houses (S/D/T)")

    # ── Yearly trend (last 6 full years) ──
    current_year = now.year
    yearly_data = exec_query(
        """SELECT substr(date,1,4) as yr, ptype,
                  ROUND(AVG(price)) as avg_price, COUNT(*) as n
           FROM hmlr_sales
           WHERE __OUTCOND__ AND date>=?
           GROUP BY yr, ptype
           ORDER BY yr DESC""",
        [f"{current_year - 6}-01-01"]
    )

    # ── All sales within window (for overall market pulse) ──
    all_window = exec_query(
        "SELECT price, date FROM hmlr_sales WHERE __OUTCOND__ AND date>=? ORDER BY date",
        [window_ago]
    )
    all_prices = sorted([r[0] for r in all_window])
    total_sales_window = len(all_prices)
    overall_median = all_prices[total_sales_window // 2] if all_prices else 0
    overall_avg = round(sum(all_prices) / total_sales_window) if all_prices else 0

    # ── Total known data ──
    total_all = exec_count(
        "SELECT COUNT(*) FROM hmlr_sales WHERE __OUTCOND__", []
    )

    # ── Momentum: last 3 months vs previous 3 months ──
    last_3m = exec_count(
        "SELECT COUNT(*) FROM hmlr_sales WHERE __OUTCOND__ AND date>=?",
        [(now - timedelta(days=90)).strftime("%Y-%m-%d")]
    )
    prev_3m = exec_count(
        "SELECT COUNT(*) FROM hmlr_sales WHERE __OUTCOND__"
        " AND date>=? AND date<?",
        [(now - timedelta(days=180)).strftime("%Y-%m-%d"),
         (now - timedelta(days=90)).strftime("%Y-%m-%d")]
    )

    # ── Price change vs previous period ──
    prev_window = exec_query(
        "SELECT price FROM hmlr_sales WHERE __OUTCOND__"
        " AND date>=? AND date<?",
        [prev_window_ago, window_ago]
    )
    prev_prices = sorted([r[0] for r in prev_window])
    prev_median = prev_prices[len(prev_prices) // 2] if prev_prices else 0
    hpi_change = round(
        ((overall_median - prev_median) / prev_median * 100) if prev_median else 0, 1
    )

    # ── Most recent date ──
    where_replaced = "SELECT MAX(date) FROM hmlr_sales WHERE " + where_clause
    max_date_row = gq.db.execute(where_replaced, params + []).fetchone()

    return {
        "outcode": outcode.upper(),
        "last_updated": now.strftime("%B %Y"),
        "analysis_window": f"{months} months",
        "total_records": total_all,
        "total_sales_window": total_sales_window,
        "overall_median": overall_median,
        "overall_avg": overall_avg,
        "flats": flat_stats,
        "houses": house_stats,
        "yearly": [
            {"year": r[0], "ptype": r[1], "avg_price": r[2], "count": r[3]}
            for r in yearly_data
        ],
        "momentum": {
            "last_3m": last_3m,
            "prev_3m": prev_3m,
            "hpi_change_pct": hpi_change,
        },
        "max_date": max_date_row[0] if max_date_row else None,
    }


# ── LLM prompt construction ────────────────────────────────────────────────
def build_prompt(data: dict) -> tuple:
    """Return (system_prompt, user_prompt, title) for the OpenRouter call."""
    oc = data["outcode"]
    month = data["last_updated"]
    window = data["analysis_window"]
    flats = data["flats"]
    houses = data["houses"]
    momentum = data["momentum"]
    title = f"{oc} Property Market Update {month}"

    # Build the data injection block
    data_lines = [
        "Total {0} sales in HMLR database: {1:,}".format(oc, data['total_records']),
        "Sold properties last {0}: {1}".format(window, data['total_sales_window']),
        "Overall median sold price ({0}): £{1:,}".format(window, data['overall_median']),
        "Overall average sold price ({0}): £{1:,}".format(window, data['overall_avg']),
    ]
    if flats["count"] > 0:
        data_lines.append(
            "Flats sold ({0}): {1}, median: £{2:,}, range: £{3:,} – £{4:,}".format(
                window, flats['count'], flats['median'], flats['min'], flats['max']
            )
        )
    if houses["count"] > 0:
        data_lines.append(
            "Houses sold ({0}): {1}, median: £{2:,}, range: £{3:,} – £{4:,}".format(
                window, houses['count'], houses['median'], houses['min'], houses['max']
            )
        )
    if flats["count"] > 0 and houses["count"] > 0:
        ratio = round(houses["median"] / flats["median"], 1) if flats["median"] else 0
        data_lines.append("House-to-flat price ratio: {0}x".format(ratio))
    if momentum["hpi_change_pct"] != 0:
        sign = "+" if momentum["hpi_change_pct"] > 0 else ""
        data_lines.append(
            "Year-over-year median price change: {0}{1}%".format(sign, momentum['hpi_change_pct'])
        )
    data_lines.append(
        "Sales last 3 months: {0} (previous 3 months: {1})".format(
            momentum['last_3m'], momentum['prev_3m']
        )
    )
    data_lines.append("Most recent sale date: {0}".format(data['max_date']))
    data_block = "\n".join(data_lines)

    system_prompt = (
        "You are an expert UK property analyst and SEO content writer. "
        "Your specialty is hyper-local market reports backed by official HM Land "
        "Registry data. You write clearly, authoritatively, and accessibly for "
        "homeowners, buyers, and sellers."
    )

    user_prompt = (
        'Write an 800-word SEO-optimised blog post titled "{0}". '
        'Do not change the title.\n\n'
        'Use ONLY this real HMLR data \u2014 do not hallucinate any prices '
        'or statistics not provided here:\n\n'
        '{1}\n\n'
        'STRUCTURE:\n'
        '- H2: "{2}: Market Snapshot" \u2014 summarise the overall market '
        'in 2-3 sentences using the data.\n'
        '- H2: "Flats vs Houses: How Prices Compare" \u2014 analyse the flat vs '
        'house price gap. Use bullet points for the raw numbers.\n'
        '- H2: "Market Momentum & Trends" \u2014 discuss sales volume trends '
        '(last 3 months vs previous 3 months) and year-over-year price change.\n'
        '- H2: "What This Means for Buyers in {2}" \u2014 2-3 paragraphs '
        'of actionable advice for buyers.\n'
        '- H2: "What This Means for Sellers in {2}" \u2014 2-3 paragraphs '
        'of actionable advice for sellers.\n'
        '- H2: "Get Your Free Honestly Appraisal" \u2014 a CTA paragraph. '
        'Include: "Ready to know what your {2} property is worth right now? '
        'Get your free data-backed Honestly appraisal at usehonestly.co.uk."\n\n'
        'BLOG RULES:\n'
        '1. Use UK English spelling throughout.\n'
        '2. Include the exact data figures in natural sentences \u2014 '
        'do not just list them.\n'
        '3. Keep a neutral, professional tone \u2014 no hype, '
        'no estate-agent fluff.\n'
        '4. End every H2 section with a smooth transition to the next.\n'
        '5. The CTA section must be the final H2.\n\n'
        'Output only the final blog post in clean Markdown. '
        'No introductory or closing remarks.'
    ).format(title, data_block, oc)

    return system_prompt, user_prompt, title


# ── OpenRouter call ─────────────────────────────────────────────────────────
def load_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key.strip()
    if KEYS_PATH.exists():
        try:
            data = json.loads(KEYS_PATH.read_text(encoding="utf-8"))
            key = data.get("OPENROUTER_API_KEY")
        except (json.JSONDecodeError, AttributeError):
            key = None
        if key:
            return key.strip()
    sys.exit("ERROR: no OpenRouter key. Set OPENROUTER_API_KEY in the env or _keys.json.")


def call_openrouter(api_key: str, system_prompt: str, user_prompt: str) -> str:
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://usehonestly.co.uk",
            "X-Title": "Honestly SEO blog engine",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        sys.exit(f"ERROR: OpenRouter HTTP {exc.code}: {detail}")
    except urllib.error.URLError as exc:
        sys.exit(f"ERROR: could not reach OpenRouter: {exc.reason}")

    try:
        return body["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        sys.exit(f"ERROR: unexpected OpenRouter response: {json.dumps(body)[:500]}")


# ── Slug generation ─────────────────────────────────────────────────────────
def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


# ── Front matter ────────────────────────────────────────────────────────────
def build_front_matter(title: str, data: dict) -> str:
    f = data["flats"]
    h = data["houses"]
    return (
        "---\n"
        'title: "{0}"\n'
        "date: {1}\n"
        "postcode: {2}\n"
        "type: market-report\n"
        "last_updated: {3}\n"
        "analysis_window: {4}\n"
        "total_records: {5}\n"
        "total_sales_window: {6}\n"
        'median_price: "\u00a3{7:,}"\n'
        'flats_median: "\u00a3{8:,}"\n'
        'houses_median: "\u00a3{9:,}"\n'
        'source: "HM Land Registry Price Paid Data"\n'
        "generated_by: seo-blog-engine\n"
        "---\n\n"
    ).format(
        title,
        datetime.now().strftime("%Y-%m-%d"),
        data["outcode"],
        data["last_updated"],
        data["analysis_window"],
        data["total_records"],
        data["total_sales_window"],
        data["overall_median"],
        f["median"],
        h["median"],
    )


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="Generate a hyper-local SEO blog post from HMLR data"
    )
    ap.add_argument("--postcode", required=True,
                    help="Postcode outcode (e.g. SW16, M1, B1)")
    ap.add_argument("--output",
                    help="Output file path (default: content/<slug>.md)")
    ap.add_argument("--months", type=int, default=12,
                    help="Analysis window in months (default: 12, min 6)")
    ap.add_argument("--no-llm", action="store_true",
                    help="Print data summary and prompt without calling LLM")
    args = ap.parse_args()

    months = max(args.months, 6)
    outcode = args.postcode.upper().strip()

    print("Data query for {0} (window: {1} months)...".format(outcode, months),
          file=sys.stderr)
    gq = GraphQuery()
    try:
        data = get_outcode_data(gq, outcode, months=months)
    finally:
        gq.close()

    if data["total_sales_window"] == 0:
        sys.exit(
            "ERROR: No sales data found for {0} "
            "in the last {1} months. Try a different postcode or increase --months.".format(
                outcode, months
            )
        )

    # Print data summary
    dat = data
    m = dat["momentum"]
    print("\nData Summary for {0}:".format(outcode), file=sys.stderr)
    print("   Total records:    {0:,}".format(dat['total_records']), file=sys.stderr)
    print("   Window:           {0}".format(dat['analysis_window']), file=sys.stderr)
    print("   Sales in window:  {0}".format(dat['total_sales_window']), file=sys.stderr)
    print("   Median price:     \u00a3{0:,}".format(dat['overall_median']), file=sys.stderr)
    print("   Flats sold:       {0} (median \u00a3{1:,})".format(
        dat['flats']['count'], dat['flats']['median']), file=sys.stderr)
    print("   Houses sold:      {0} (median \u00a3{1:,})".format(
        dat['houses']['count'], dat['houses']['median']), file=sys.stderr)
    if m["hpi_change_pct"] != 0:
        sign = "+" if m["hpi_change_pct"] > 0 else ""
        print("   YoY change:       {0}{1}%".format(sign, m['hpi_change_pct']),
              file=sys.stderr)
    print("   Last 3 months:    {0} sales (prev: {1})".format(
        m['last_3m'], m['prev_3m']), file=sys.stderr)
    print("   Most recent:      {0}".format(dat['max_date']), file=sys.stderr)

    system_prompt, user_prompt, title = build_prompt(data)

    if args.no_llm:
        print("\nPrompt (no-llm mode):", file=sys.stderr)
        print("=== SYSTEM ===")
        print(system_prompt)
        print("=== USER ===")
        print(user_prompt)
        return

    print("\nCalling {0} via OpenRouter...".format(MODEL), file=sys.stderr)
    api_key = load_api_key()
    markdown = call_openrouter(api_key, system_prompt, user_prompt)

    # Build output path
    if args.output:
        out_path = Path(args.output)
    else:
        slug = slugify(title)
        out_path = CONTENT_DIR / "{0}.md".format(slug)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    full_content = build_front_matter(title, data) + markdown
    out_path.write_text(full_content, encoding="utf-8")

    print("\nSaved: {0}".format(out_path.resolve()), file=sys.stderr)
    print("   Title: {0}".format(title), file=sys.stderr)
    print("   Length: {0:,} chars / ~{1:,} words".format(
        len(markdown), len(markdown.split())), file=sys.stderr)


if __name__ == "__main__":
    main()
