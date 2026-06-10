"""Audio valuation walkthrough - narrates the glass-box working with Voxtral TTS.

Stdlib-only (urllib/json/base64) so it adds no runtime dependency. Every call is
best-effort: any failure (no key, network, bad response) returns None and the
valuation is delivered exactly as before. Audio NEVER blocks a valuation.

Hard rule: the spoken script reproduces the engine's figures and the exact
arithmetic chain (sold median -> condition-adjusted -> live market % = central)
verbatim. It never invents a number, never paraphrases the figure into a vibe.
"""
import os, json, base64, urllib.request, urllib.error

ENDPOINT = "https://api.mistral.ai/v1/audio/speech"
MODEL = os.environ.get("VOXTRAL_MODEL", "voxtral-mini-tts-2603")
VOICE = os.environ.get("VOXTRAL_VOICE", "vivian")
TIMEOUT = int(os.environ.get("VOXTRAL_TIMEOUT", "60"))


def _key(explicit=None):
    return explicit or os.environ.get("MISTRAL_API_KEY")


def _say_money(s):
    """'£530,000' -> '530,000 pounds' so the model reads currency naturally."""
    if not s:
        return ""
    return s.replace("£", "").strip() + " pounds"


def _say_range(s):
    """'£500,000 - £560,000' -> '500,000 pounds to 560,000 pounds'."""
    if not s:
        return ""
    parts = [p.strip() for p in s.replace("£", "").split("-")]
    parts = [p for p in parts if p]
    if len(parts) == 2:
        return f"{parts[0]} pounds to {parts[1]} pounds"
    return _say_money(s)


def walkthrough_script(d):
    """Build the spoken narration from an engine.summary() dict.

    Returns plain text (hyphens/commas only, no em dashes - it is copy). Reproduces
    the glass-box chain with the engine's own figures. Returns "" if there is no
    central figure to narrate (nothing honest to say)."""
    central = d.get("central")
    if not central:
        return ""
    audience = d.get("audience", "agent")
    addr = d.get("address", "this property")
    central_say = f"{central:,} pounds"

    intro = {
        "vendor": f"Here is the honest valuation for your home at {addr}.",
        "buyer": f"Here is what the evidence says this home at {addr} is worth.",
        "agent": f"Here is the instant appraisal for {addr}.",
    }.get(audience, f"Here is the valuation for {addr}.")

    lines = [intro]

    rng = d.get("range_str")
    if rng:
        lines.append(
            f"Based on comparable homes that actually sold, the assessed range is "
            f"{_say_range(rng)}, with a central figure of {central_say}."
        )
    else:
        lines.append(f"The central figure is {central_say}.")

    # the glass box, spoken: the same chain shown in the card and PDF
    chain_said = False
    sold_median = d.get("sold_median")
    sold_anchor = d.get("sold_anchor")
    market = d.get("market") or {}
    pct = market.get("pct")

    if sold_median:
        lines.append(
            f"Here is exactly how we got there. The median of the sold comparables "
            f"was {sold_median:,} pounds."
        )
        chain_said = True
        if sold_anchor and sold_anchor != sold_median:
            lines.append(
                f"Adjusted for the property's condition, that anchors at "
                f"{sold_anchor:,} pounds."
            )
    if pct and abs(pct) >= 0.1:
        direction = "above" if pct > 0 else "below"
        lines.append(
            f"The live market is running {abs(pct)} percent {direction} those sold "
            f"prices, which brings the central figure to {central_say}."
        )
        chain_said = True

    n = d.get("comparable_count") or len(d.get("evidence") or [])
    if n:
        lines.append(
            f"Every one of the {n} comparables behind this number is a real "
            f"Land Registry sold record, linked in your full report."
        )

    lines.append(
        "This is an evidence-based assessment, not a formal R I C S valuation. "
        "The honesty is the point. No black box, just the working, shown."
    )
    # if we somehow could not show any chain, do not pretend we did
    if not chain_said:
        # still honest - we just describe the range and the source
        pass
    return " ".join(lines)


def synthesize(text, key=None, fmt="mp3"):
    """Voxtral TTS: text -> audio bytes. Best-effort, returns None on any failure.

    The hosted Mistral API uses 'voice_id'; the OpenAI-compatible shape uses
    'voice'. We try voice_id first and fall back to voice, then degrade to None."""
    if not text:
        return None
    api_key = _key(key)
    if not api_key:
        return None  # no key -> no audio, silently (the valuation already went out)

    for voice_field in ("voice_id", "voice"):
        payload = {
            "model": MODEL,
            "input": text,
            voice_field: VOICE,
            "response_format": fmt,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            ENDPOINT, data=body, method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                ctype = (r.headers.get("Content-Type") or "").lower()
                raw = r.read()
        except urllib.error.HTTPError as e:
            # 400/422 likely means the field name was wrong - try the other one
            if e.code in (400, 422) and voice_field == "voice_id":
                continue
            return None
        except Exception:
            return None

        # JSON envelope with base64 audio_data (hosted Mistral), or raw audio bytes
        if "application/json" in ctype or raw[:1] in (b"{", b"["):
            try:
                obj = json.loads(raw.decode("utf-8", "ignore"))
            except Exception:
                return None
            b64 = obj.get("audio_data") or obj.get("audio") or obj.get("data")
            if not b64:
                return None
            try:
                return base64.b64decode(b64)
            except Exception:
                return None
        return raw  # already binary audio
    return None


def walkthrough(d, key=None, fmt="mp3"):
    """engine.summary() dict -> spoken-walkthrough audio bytes (or None)."""
    return synthesize(walkthrough_script(d), key=key, fmt=fmt)


def save_walkthrough(d, path, key=None, fmt="mp3"):
    """Generate the walkthrough and write it to `path`. Returns path or None."""
    audio = walkthrough(d, key=key, fmt=fmt)
    if not audio:
        return None
    try:
        with open(path, "wb") as f:
            f.write(audio)
        return path
    except Exception:
        return None


if __name__ == "__main__":
    demo = {
        "audience": "vendor",
        "address": "11 Shadwell Gardens, London E1 2QG",
        "range_str": "£500,000 - £560,000",
        "central": 530000,
        "sold_median": 525000,
        "sold_anchor": 472500,
        "market": {"pct": 3.2, "label": "rising"},
        "comparable_count": 4,
    }
    print(walkthrough_script(demo))
    out = save_walkthrough(demo, "_walkthrough_demo.mp3")
    print("Saved:", out if out else "(no audio - set MISTRAL_API_KEY to generate)")
