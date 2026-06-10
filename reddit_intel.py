#!/usr/bin/env python3
"""reddit_intel.py - market sentiment from Reddit for Honestly valuation reports.

Best-effort integration with the Hit MCP server. Never blocks a valuation:
all failures degrade to empty data. The PDF and bot check if intel exists
before rendering anything.

Reddit threads about an area provide qualitative context: buyer anxieties,
seller experiences, agent complaints, and local market chatter. This sits
beside the hard sold-evidence numbers - a flavour layer, not a valuation input.

Uses the _hit_sdk.py CLI wrapper (which uses the MCP SDK) to communicate
with the Hit MCP server. Pure stdlib in this module.

Usage:
    import reddit_intel
    intel = reddit_intel.for_area("SE15", audience="buyer")
    # -> {"sentiment": "mixed", "themes": [...], "threads": [...]}
"""
import json, os, subprocess, re, sys
from pathlib import Path

# UK property subreddits for market intelligence
_SUBREDDITS = {
    "general": ["HousingUK", "PropertyUK", "UKProperty"],
    "landlords": ["uklandlord", "UKLandlords"],
    "investors": ["UKPropertyInvesting", "PropertyInvestingUK"],
    "tenants": ["Tenant", "uklandlordtenant"],
}

# Keywords grouped by what they reveal about the market
_KEYWORD_GROUPS = {
    "buyer_sentiment": [
        "overpaying", "gazumped", "offers over", "asking price",
        "sold for", "reduction", "negotiation", "chain",
        "mortgage offer", "valuation down", "down valuation",
    ],
    "seller_sentiment": [
        "estate agent", "valuation quote", "overpriced", "stuck",
        "reduced", "no viewings", "sell quickly", "cash buyer",
    ],
    "market_conditions": [
        "interest rate", "house prices", "crash", "slow market",
        "buyers market", "sellers market", "stamp duty",
    ],
    "area_market": [
        "London property", "commuter belt", "prices rising",
        "prices falling", "hotspot", "gentrification",
    ],
}

HERE = Path(__file__).parent
HIT_SDK = HERE / "_hit_sdk.py"
HIT_PYTHON = os.getenv("HIT_SDK_PYTHON") or sys.executable
MCP_TIMEOUT = 60  # seconds for a scan


def _call_mcp(tool_name: str, arguments: dict) -> dict | None:
    """Call a Hit MCP tool via the SDK CLI wrapper.

    Uses the _hit_sdk.py CLI which handles MCP protocol correctly.
    Pure stdlib subprocess call - no direct MCP dependency.
    Returns the parsed result or None on failure.
    """
    try:
        args_json = json.dumps(arguments)
        result = subprocess.run(
            [HIT_PYTHON, str(HIT_SDK), tool_name, args_json],
            capture_output=True, text=True, timeout=MCP_TIMEOUT,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        if data.get("success"):
            raw = data.get("raw", "")
            return {"raw": raw, "parsed": _parse_scan_output(raw)}
        return None
    except Exception:
        return None


def _parse_scan_output(text: str) -> dict:
    """Parse hit_scan output into structured data.

    The scan output is free text, not JSON. We extract the signal count,
    evidence posts, and classify them into themes.
    """
    lines = text.split("\n")
    result = {
        "signal_count": 0,
        "threads": [],
        "themes": [],
        "sentiment": "neutral",
    }

    # Extract signal count
    for line in lines:
        m = re.search(r"Monitored\s*:\s*(\d+)", line)
        if m:
            result["signal_count"] = int(m.group(1))

    # Extract evidence posts
    current = {}
    for line in lines:
        m = re.match(r"\d+\.\s+r/(\w+)\s+(?:—|--)\s+(.+)", line)
        if m:
            if current:
                result["threads"].append(current)
            current = {"subreddit": m.group(1), "title": m.group(2).strip()}
        elif current and line.strip().startswith("SSR="):
            current["ssr"] = line.strip()
        elif current and line.strip().startswith("Quote:"):
            current["quote"] = line.replace("Quote:", "", 1).strip()
        elif current and line.strip().startswith("Link:"):
            current["url"] = line.replace("Link:", "", 1).strip()
    if current:
        result["threads"].append(current)

    # Classify sentiment from threads
    warn_words = ["overpay", "crash", "stuck", "reduced", "gazump", "scam",
                  "down valuation", "can't sell", "no offers", "overpriced"]
    pos_words = ["good price", "sold quickly", "offers over", "bidding war",
                 "competitive", "high demand", "fair value"]
    warn_count = sum(1 for t in result["threads"] if any(
        w in (t.get("title", "") + t.get("quote", "")).lower() for w in warn_words))
    pos_count = sum(1 for t in result["threads"] if any(
        w in (t.get("title", "") + t.get("quote", "")).lower() for w in pos_words))

    if warn_count > pos_count * 2:
        result["sentiment"] = "cautious"
    elif pos_count > warn_count * 2:
        result["sentiment"] = "supportive"
    else:
        result["sentiment"] = "mixed"

    # Extract themes from combined text
    combined = " ".join(t.get("title", "") + " " + t.get("quote", "") for t in result["threads"]).lower()
    theme_map = {
        "overpaying / valuation concerns": ["overpay", "overpriced", "down value", "high price"],
        "negotiation / offers": ["offer", "negotiat", "gazump", "best and final"],
        "market conditions": ["interest rate", "crash", "slow market", "stamp duty"],
        "sold prices / evidence": ["sold for", "comparable", "sq ft", "per sq"],
        "chain / transaction stress": ["chain", "fall through", "exchange delay"],
        "rental / landlord": ["landlord", "tenant", "rent", "void", "section 21"],
    }
    for theme, keywords in theme_map.items():
        if any(k in combined for k in keywords):
            result["themes"].append(theme)

    return result


def for_area(area: str, audience: str = "buyer", postcode: str = "") -> dict:
    """Get Reddit market intelligence for a UK area.

    Args:
        area: Area name (e.g. "SE15", "Peckham", "Manchester")
        audience: Context for keyword selection (buyer/vendor/agent)
        postcode: Full postcode for more targeted search

    Returns:
        dict with keys: sentiment, themes, threads, signal_count
        Empty dict on failure (never raises).
    """
    keywords = []

    # Area-specific keywords
    if postcode:
        area_parts = postcode.split()
        if area_parts:
            keywords.append(area_parts[0])  # postcode district
    keywords.append(area)

    # Audience-specific keywords
    if audience == "buyer":
        keywords.extend(_KEYWORD_GROUPS["buyer_sentiment"][:4])
    elif audience == "vendor":
        keywords.extend(_KEYWORD_GROUPS["seller_sentiment"][:4])
    else:  # agent
        keywords.extend(_KEYWORD_GROUPS["buyer_sentiment"][:3])
        keywords.extend(_KEYWORD_GROUPS["seller_sentiment"][:3])

    # Always include market conditions
    keywords.extend(_KEYWORD_GROUPS["market_conditions"][:3])

    result = _call_mcp("hit_scan", {
        "subreddits": _SUBREDDITS["general"],
        "keywords": keywords,
        "limit": 5,
        "return_posts": True,
        "evidence_limit": 5,
        "workflow": "research",
        "time_filter": "year",
    })

    if result and result.get("parsed"):
        parsed = result["parsed"]
        return {
            "sentiment": parsed.get("sentiment", "neutral"),
            "themes": parsed.get("themes", []),
            "threads": parsed.get("threads", []),
            "signal_count": parsed.get("signal_count", 0),
            "area": area,
        }
    return {}


def format_brief(intel: dict) -> str:
    """Format Reddit intel as a brief text block for bot or report."""
    if not intel or not intel.get("threads"):
        return ""
    lines = ["📊 <b>Market intelligence from Reddit</b>"]
    sent = intel.get("sentiment", "neutral")
    emoji = {"supportive": "📈", "cautious": "📉", "mixed": "🔄"}.get(sent, "➖")
    lines.append(f"{emoji} Local sentiment: <b>{sent.capitalize()}</b>")
    themes = intel.get("themes", [])
    if themes:
        lines.append(f"Key themes: {' · '.join(themes)}")
    lines.append("")
    for t in intel.get("threads", [])[:3]:
        title = t.get("title", "")
        url = t.get("url", "")
        sub = t.get("subreddit", "")
        if url:
            lines.append(f'• <a href="{url}">{title}</a> <i>(r/{sub})</i>')
        else:
            lines.append(f"• {title} <i>(r/{sub})</i>")
    lines.append("\n<i>Reddit sentiment for context only - never a valuation input.</i>")
    return "\n".join(lines)


def format_report_text(intel: dict) -> str:
    """Format Reddit intel as a plain-text block for the PDF report."""
    if not intel or not intel.get("threads"):
        return ""
    lines = ["Market intelligence from Reddit", "=" * 35, ""]
    sent = intel.get("sentiment", "neutral")
    lines.append(f"Local sentiment on Reddit: {sent.capitalize()}")
    themes = intel.get("themes", [])
    if themes:
        lines.append(f"Key discussion themes: {' | '.join(themes)}")
    lines.append("")
    for t in intel.get("threads", [])[:3]:
        lines.append(f"- {t.get('title', '')}")
        lines.append(f"  r/{t.get('subreddit', '')} - {t.get('url', '')}")
    lines.append("")
    lines.append("(Reddit market chatter for additional context - not a valuation input)")
    return "\n".join(lines)
