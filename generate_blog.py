#!/usr/bin/env python3
"""generate_blog.py — synthesize an ORIGINAL blog post from saved Reddit evidence.

Pipeline (per task spec, adapted to the user's provider choice):
  1. Read reddit_raw_data.json (produced by the Hit MCP scan — recent threads + top comments).
  2. Send the thread bodies + comments to an LLM through OpenRouter's OpenAI-compatible
     Chat Completions API (the user opted for OpenRouter instead of the Anthropic SDK).
  3. Force the model (with the strict system prompt below) to SYNTHESIZE — never quote/copy —
     a clean-Markdown blog post that speaks to the ICP's pain points.
  4. Save the result as a timestamped .md file in ./drafts.

No third-party packages required (uses only the standard library), and it never calls
Reddit or publishes anything — fully local.

Auth (in priority order):
  - env var OPENROUTER_API_KEY, else
  - "OPENROUTER_API_KEY" in the gitignored ./_keys.json
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# --- Configuration -----------------------------------------------------------
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# DeepSeek V3 via OpenRouter — strong, cheap writer. Swap for any OpenRouter model id,
# e.g. "anthropic/claude-sonnet-4" or "openai/gpt-4o", without touching anything else.
MODEL = "deepseek/deepseek-chat"
MAX_TOKENS = 4000
TEMPERATURE = 0.7

HERE = Path(__file__).resolve().parent
INPUT_PATH = HERE / "reddit_raw_data.json"
KEYS_PATH = HERE / "_keys.json"
DRAFTS_DIR = HERE / "drafts"   # task says "/drafts"; kept inside cwd per the no-escape rule

# The strict system prompt, verbatim from the task. It forces synthesis, not quotation.
SYSTEM_PROMPT = """You are an expert copywriter. Read the provided Reddit thread and comments. \
These represent the pain points and interests of our Ideal Customer Profile (ICP).
Your task is to write an engaging, original blog post that addresses these pain points.
STRICT RULES:
- DO NOT copy-paste or quote the Reddit text directly.
- Synthesize the core problems into a cohesive narrative.
- Provide actionable solutions or insights related to our product/service.
- Format the output in clean Markdown."""


# --- Helpers -----------------------------------------------------------------
def load_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key.strip()
    if KEYS_PATH.exists():
        try:
            key = (json.loads(KEYS_PATH.read_text(encoding="utf-8"))
                   .get("OPENROUTER_API_KEY"))
        except (json.JSONDecodeError, AttributeError):
            key = None
        if key:
            return key.strip()
    sys.exit("ERROR: no OpenRouter key. Set OPENROUTER_API_KEY in the env "
             "or add it to _keys.json.")


def load_evidence(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"ERROR: {path.name} not found. Run the Hit MCP scan first to produce it.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"ERROR: {path.name} is not valid JSON: {exc}")
    if not (data.get("posts") or data.get("threads")):
        sys.exit(f"ERROR: {path.name} contains no posts/threads to synthesize from.")
    return data


def render_thread(post: dict, idx: int) -> str:
    """Flatten one thread + its comments into plain text for the model."""
    title = post.get("title", "(untitled)")
    sub = post.get("subreddit", "?")
    body = post.get("body") or post.get("body_excerpt") or post.get("selftext") or ""
    lines = [f"### THREAD {idx}: r/{sub} — {title}", "", f"POST:\n{body.strip()}", ""]

    comments = post.get("comments") or []
    if comments:
        lines.append("TOP COMMENTS:")
        for c in comments:
            text = (c.get("body") or c.get("text") or c.get("quote") or "").strip()
            if not text:
                continue
            score = c.get("score", c.get("ups", ""))
            tag = f" (+{score})" if score != "" else ""
            lines.append(f"- {text}{tag}")
    else:
        lines.append("TOP COMMENTS: (none captured for this thread)")
    lines.append("")
    return "\n".join(lines)


def build_user_message(data: dict) -> str:
    posts = data.get("posts") or data.get("threads") or []
    parts = [
        "Below are recent Reddit threads (with top comments where available) from UK "
        "property/housing communities. They surface the real frustrations of our ICP: "
        "homeowners, sellers and buyers trying to understand what a property is actually "
        "worth. Synthesize them into one original blog post per the system instructions.\n",
    ]
    for i, post in enumerate(posts, start=1):
        parts.append(render_thread(post, i))
    return "\n".join(parts)


def call_openrouter(api_key: str, user_message: str) -> str:
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # OpenRouter attribution headers (optional but recommended)
            "HTTP-Referer": "https://usehonestly.co.uk",
            "X-Title": "Honestly blog synthesis",
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
        sys.exit(f"ERROR: unexpected OpenRouter response shape: {json.dumps(body)[:500]}")


def main() -> None:
    api_key = load_api_key()
    data = load_evidence(INPUT_PATH)
    n = len(data.get("posts") or data.get("threads") or [])
    user_message = build_user_message(data)

    print(f"Sending {n} thread(s) to {MODEL} via OpenRouter ...", file=sys.stderr)
    markdown = call_openrouter(api_key, user_message)
    if not markdown:
        sys.exit("ERROR: the model returned no text content.")

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = DRAFTS_DIR / f"blog-draft-{stamp}.md"
    out_path.write_text(markdown, encoding="utf-8")

    print(f"OK: wrote {out_path.relative_to(HERE)} ({len(markdown)} chars)")


if __name__ == "__main__":
    main()
