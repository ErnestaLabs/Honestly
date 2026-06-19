#!/usr/bin/env python3
"""ai.py - plain-English narrative via the Gemini API, with a hard honesty guard.

Gemini writes the prose; it never invents the numbers. The narrative is grounded ONLY in
the figures already present in engine.summary(): the prompt hands Gemini the allowed values
and forbids any new ones, and then a deterministic post-check (guard_figures) scans the
generated text for monetary figures that are NOT derivable from the summary dict. If it
finds one, the narrative is REJECTED (ok: False) rather than shown - a fabricated figure can
never reach a deliverable. This mirrors the standing rule: describe only what the source
data actually says.

Best-effort: no key, a down endpoint, an empty completion, or a guard failure all return
{'ok': False, 'reason': ...} and never raise, so the report falls back to its own prose.

Surfaces:
  narrative(summary, audience="owner") -> {ok, text, source} | {ok: False, reason}
  guard_figures(text, summary)         -> (clean: bool, offending: [str])

CLI:
  python ai.py selftest          # runs the guard offline (no network/key needed)
"""
import os, re, sys, json, urllib.parse, urllib.request, urllib.error

MODEL = "gemini-2.5-flash"
ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
            + MODEL + ":generateContent")
_SRC = "Google Gemini API (" + MODEL + "), grounded in engine.summary() figures"

# numbers this big are treated as "money/area figures" that MUST trace to the summary;
# smaller integers (bedroom counts, years, single-digit percentages) are allowed through.
_FIGURE_MIN = 1000


def _digits(s):
    """All integer-like tokens in a string, comma-stripped, as plain digit strings."""
    return [re.sub(r"[,\s]", "", m) for m in re.findall(r"\d[\d,]*", str(s))]


def _allowed_set(summary):
    """Every numeric token derivable from the summary dict, as digit strings. Includes
    the raw integers and their thousands-rounded forms so '550,000' and '550000' match."""
    allowed = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif isinstance(v, bool):
            return
        elif isinstance(v, (int, float)):
            n = int(round(v))
            allowed.add(str(n))
            allowed.add(str(abs(n)))
        elif isinstance(v, str):
            for d in _digits(v):
                allowed.add(d)
    walk(summary)
    return allowed


def guard_figures(text, summary):
    """Return (clean, offending). A figure >= _FIGURE_MIN in the text that is not in the
    summary's allowed set is an offence. Small numbers (beds, years, low percentages) pass."""
    allowed = _allowed_set(summary)
    offending = []
    for tok in _digits(text):
        try:
            n = int(tok)
        except ValueError:
            continue
        if n < _FIGURE_MIN:
            continue
        if tok in allowed:
            continue
        # tolerate thousands-rounding either way (e.g. 547600 -> 548000)
        if any(abs(n - int(a)) <= 1000 for a in allowed if a.isdigit() and len(a) >= 4):
            continue
        offending.append(tok)
    return (not offending, offending)


def _prompt(summary, audience):
    facts = json.dumps(summary, ensure_ascii=False, default=str)
    return (
        "You are writing two short paragraphs of plain-English narrative for a UK property "
        "valuation report. Audience: " + str(audience) + ".\n\n"
        "STRICT RULES:\n"
        "1. Use ONLY the figures in the JSON below. Do NOT introduce any number, price, "
        "percentage or area that is not present there. If you need a figure you do not have, "
        "describe it in words instead of inventing one.\n"
        "2. The sold comparable evidence anchors the figure. The live-market move is small, "
        "capped and disclosed - never present it as the main driver.\n"
        "3. No hype, no superlatives, no investment advice. Calm, precise, defensible.\n"
        "4. British spelling. No em dashes - use hyphens.\n\n"
        "JSON (the only figures you may cite):\n" + facts + "\n\n"
        "Write the narrative now."
    )


def narrative(summary, audience="owner", timeout=30):
    """Generate a grounded narrative for the summary dict. Returns {ok, text, source} or
    {ok: False, reason}. Never raises. The text is guard-checked before it is returned."""
    if not isinstance(summary, dict) or not summary:
        return {"ok": False, "reason": "no summary data"}
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return {"ok": False, "reason": "GEMINI_API_KEY not set"}
    body = json.dumps({
        "contents": [{"parts": [{"text": _prompt(summary, audience)}]}],
        # thinkingBudget 0 keeps the whole output budget for the narrative itself -
        # 2.5 models otherwise spend it on internal reasoning and return empty text.
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 800,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }).encode()
    url = ENDPOINT + "?key=" + urllib.parse.quote(key)
    try:
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        return {"ok": False, "reason": f"Gemini HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    try:
        text = d["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return {"ok": False, "reason": "empty completion"}
    if not text:
        return {"ok": False, "reason": "empty completion"}
    clean, offending = guard_figures(text, summary)
    if not clean:
        return {"ok": False, "reason": f"honesty guard rejected figures: {offending[:5]}"}
    return {"ok": True, "text": text, "source": _SRC}


def _selftest():
    summary = {"central": 550000, "low": 525000, "high": 575000, "guide": 540000,
               "sold_median": 547000, "beds": 2, "market": {"pct": 1.5}}
    ok_text = ("Our central assessment is 550,000, within an assessed range of 525,000 to "
               "575,000. We recommend a guide of 540,000. The sold median nearby is 547,000.")
    bad_text = ("Our central assessment is 550,000, but the property could fetch 720,000 "
                "at auction.")
    c1, o1 = guard_figures(ok_text, summary)
    c2, o2 = guard_figures(bad_text, summary)
    print("guard clean text :", "PASS" if c1 else f"FAIL {o1}")
    print("guard dirty text :", "PASS" if (not c2 and "720000" in o2) else f"FAIL {o2}")
    key = "set" if (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")) else "not set"
    print("GEMINI_API_KEY   :", key)


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "selftest":
        _selftest(); return
    print("unknown command:", sys.argv[1])


if __name__ == "__main__":
    main()
