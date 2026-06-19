#!/usr/bin/env python3
"""Fresh Reddit VOC collector for Honestly enrichment fields.

Uses public old.reddit.com HTML search only. No commercial property-data APIs.
Writes a markdown brief with links, quotes and product implications.
"""
import html, re, time, urllib.parse, urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (compatible; honestly-voc/1.0; +https://usehonestly.co.uk)"
SUBS = ["HousingUK", "PropertyUK", "UKPersonalFinance"]
SEARCH_TERMS = [
    "Zoopla estimate accurate valuation",
    "estate agent valuation too high",
    "down valuation mortgage valuation",
    "survey after offer damp roof",
    "sold prices comparable offer asking",
    "overpaying house asking price valuation",
    "EPC leasehold property buying",
    "price reduced house not selling agent",
    "mortgage valuation lower than offer",
    "how much to offer sold prices",
]
KEYWORDS = [
    "valuation", "zoopla", "rightmove", "estate agent", "agent", "survey",
    "down valuation", "mortgage valuation", "overpay", "sold price", "comparable",
    "offer", "asking price", "epc", "leasehold", "damp", "roof", "price reduced",
]


def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def search_sub(sub, q, limit=10):
    url = f"https://old.reddit.com/r/{sub}/search?" + urllib.parse.urlencode({
        "q": q, "restrict_sr": "on", "sort": "relevance", "t": "all",
    })
    try:
        page = fetch_text(url)
    except Exception as e:
        return []
    rows = []
    things = re.findall(r'<div[^>]+class="[^"]*search-result[^"]*"[\s\S]*?(?=<div[^>]+class="[^"]*search-result|<footer|</body>)', page)
    for block in things:
        title_m = re.search(r'<a(?=[^>]*class="[^"]*search-title[^"]*")(?=[^>]*href="([^"]+)")[^>]*>([\s\S]*?)</a>', block)
        if not title_m:
            continue
        href = html.unescape(title_m.group(1))
        title = clean(title_m.group(2))
        if not href.startswith("http"):
            href = "https://old.reddit.com" + href
        text_m = re.search(r'<div[^>]+class="[^"]*usertext-body[^"]*"[^>]*>([\s\S]*?)</div>\s*</div>', block)
        text = clean(text_m.group(1))[:900] if text_m else ""
        comments_m = re.search(r'>(\d+) comments?</a>', block)
        comments = int(comments_m.group(1)) if comments_m else 0
        score_m = re.search(r'<span[^>]+class="[^"]*search-score[^"]*"[^>]*>(\d+) points?</span>', block)
        score = int(score_m.group(1)) if score_m else 0
        hay = (title + " " + text).lower()
        if any(k in hay for k in KEYWORDS):
            rows.append({"subreddit": sub, "title": title, "url": href.replace("old.reddit.com", "www.reddit.com"),
                         "comments": comments, "score": score, "text": text})
        if len(rows) >= limit:
            break
    return rows


def collect():
    seen, rows = set(), []
    for sub in SUBS:
        for term in SEARCH_TERMS:
            for row in search_sub(sub, term, limit=8):
                if row["url"] in seen:
                    continue
                seen.add(row["url"]); rows.append(row)
            time.sleep(0.35)
    rows.sort(key=lambda r: ((r.get("comments") or 0) * 2 + (r.get("score") or 0)), reverse=True)
    return rows[:45]


def classify(rows):
    themes = {
        "trust_black_box": [],
        "agent_incentives": [],
        "down_valuation": [],
        "survey_risk": [],
        "negotiation_evidence": [],
        "material_facts": [],
        "monitoring_timing": [],
    }
    rules = {
        "trust_black_box": ["zoopla", "estimate", "valuation", "worth"],
        "agent_incentives": ["estate agent", "agent", "overvalu", "price reduced", "not selling"],
        "down_valuation": ["down valuation", "mortgage valuation", "lender", "mortgage"],
        "survey_risk": ["survey", "damp", "roof", "structural", "electrics", "boiler"],
        "negotiation_evidence": ["offer", "asking", "sold price", "comparable", "overpay"],
        "material_facts": ["epc", "leasehold", "lease", "service charge", "ground rent"],
        "monitoring_timing": ["price reduced", "not selling", "days", "market", "reduced"],
    }
    for r in rows:
        hay = (r["title"] + " " + r["text"]).lower()
        for theme, words in rules.items():
            if any(w in hay for w in words):
                themes[theme].append(r)
    return themes


def quote(row):
    body = row["text"] or row["title"]
    body = body.replace("|", " ").strip()
    if len(body) > 260:
        body = body[:260].rsplit(" ", 1)[0] + "..."
    return body


def main():
    rows = collect()
    themes = classify(rows)
    out = ["# Fresh Reddit VOC: Honestly enrichment fields", "", "Source: public old.reddit.com search across r/HousingUK, r/PropertyUK, r/UKPersonalFinance. No commercial property-data APIs.", ""]
    out += ["## What users are really asking for", ""]
    implications = [
        ("Trust black-box valuations", "Show proof rows, confidence, range width, and why the model trusts or distrusts the result."),
        ("Agent incentive defence", "Compare agent quote/asking price against evidence; give the exact question to ask back."),
        ("Down-valuation fear", "Paid field: lender-risk gap, cash-gap if central/lower value lands, LTV pressure."),
        ("Survey anxiety", "Paid field: pre-survey red flags from EPC/age/condition/floor-area gaps; questions before spending money."),
        ("Negotiation evidence", "Turn comps into offer/guide scripts, not just a table."),
        ("Material facts", "Surface EPC/floor area/tenure/council-tax/planning/flood as status fields with source and missing-state."),
        ("Timing/monitoring", "Watch evidence changes: new sold rows, price reductions, stale listings, HPI/rate movement."),
    ]
    for theme, implication in implications:
        out.append(f"- **{theme}**: {implication}")
    out.append("")
    out.append("## Evidence snippets")
    for name, items in themes.items():
        if not items:
            continue
        out += ["", f"### {name.replace('_', ' ').title()}", ""]
        for r in items[:6]:
            out.append(f"- [{r['title']}]({r['url']}) — r/{r['subreddit']}, {r.get('comments')} comments. “{quote(r)}”")
    out += ["", "## Product response: Honestly enrichment fields", "", "Free card/evidence pack:", "", "- valuation range / central / guide", "- confidence score + reason", "- HMLR proof rows with source links", "- subject history HPI model when used", "- EPC/floor-area status, including missing-state", "- plain-English decision read", "", "Paid decision pack:", "", "- down-valuation exposure", "- affordability pressure when user provides deposit/income after first value", "- pre-survey risk questions", "- agent quote / asking-price challenge", "- evidence map from proof rows", "- monitoring/watchlist triggers", ""]
    path = Path("research/REDDIT_enrichment_fields_voc.md")
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8")
    print(path)
    print(f"rows={len(rows)} themes=" + ",".join(f"{k}:{len(v)}" for k,v in themes.items()))


if __name__ == "__main__":
    main()
