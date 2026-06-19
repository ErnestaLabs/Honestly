#!/usr/bin/env python3
"""vision.py - propose a finish tier from listing photos (Google Cloud Vision).

Direction #2 of the condition work. Task #16 shipped a condition sub-survey the user
taps through; this proposes the SAME signals automatically by reading the listing
photos, so the sub-survey arrives pre-filled. CRITICAL: vision proposes, it never
decides. The output is a set of condition SIGNALS (c_state / c_kitchen / c_bath /
c_premium) in exactly the shape bot.derive_finish already consumes, plus the tier that
function would derive from them. Nothing here is a new input to valuation(): the figure
still moves only through the engine's existing finish path, and only once a human has
confirmed the tier. Photos can over- or under-sell a home, so the read is conservative
(it does not invent premium credit) and always disclosed as a from-photos proposal.

Auth: Google Cloud Vision via an API key (VISION_API_KEY, then GOOGLE_CLOUD_VISION_KEY,
then GOOGLE_MAPS_API_KEY if the same project has the Vision API enabled). With no key it
degrades to {'ok': False, 'reason': 'Vision API key not set'} - never raises, never
blocks a valuation, same posture as geo.py / epc.py / police.py.

Surfaces:
  assess(image_urls, max_images=8) -> {ok, proposed_tier, signals, labels, confidence,
                                       photo_count, note} or {ok: False, reason}

CLI:
  python vision.py assess "https://.../photo1.jpg" "https://.../photo2.jpg"
  python vision.py selftest
"""
import os, sys, json, urllib.request, urllib.error

API = "https://vision.googleapis.com/v1/images:annotate"
_SRC = "Google Cloud Vision (LABEL_DETECTION) on listing photos"
_SCORE_MIN = 0.70          # ignore weak label guesses
_MAX = 8                   # cap photos per assessment (cost + latency)

# label tokens (lower-case substring match against Vision descriptions), grouped by what
# they signal. Kept deliberately tight: only GENUINELY premium materials lift a tier.
_PREMIUM = ("marble", "granite", "quartz", "travertine", "terrazzo", "hardwood",
            "parquet", "bespoke", "joinery", "brass", "natural stone")
_KITCHEN = ("kitchen", "countertop", "cabinetry", "kitchen appliance", "kitchen stove",
            "kitchen & dining")
_BATH = ("bathroom", "bathtub", "shower", "bathroom sink", "plumbing fixture", "bidet")


def _load_env():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(here):
        with open(here, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def _key():
    _load_env()
    return (os.environ.get("VISION_API_KEY")
            or os.environ.get("GOOGLE_CLOUD_VISION_KEY")
            or os.environ.get("GOOGLE_MAPS_API_KEY"))


def _annotate(image_urls, key, timeout=40):
    """One annotate POST covering all images. Returns the parsed JSON (raises on error)."""
    reqs = [{"image": {"source": {"imageUri": u}},
             "features": [{"type": "LABEL_DETECTION", "maxResults": 30}]}
            for u in image_urls]
    body = json.dumps({"requests": reqs}).encode()
    req = urllib.request.Request(f"{API}?key={key}", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _labels(resp):
    """Flatten labelAnnotations across all image responses to [(desc_lower, score), ...]
    keeping the best score seen for each distinct label."""
    best = {}
    for img in (resp.get("responses") or []):
        for la in (img.get("labelAnnotations") or []):
            desc = (la.get("description") or "").strip().lower()
            sc = la.get("score")
            if not desc or sc is None:
                continue
            if sc >= _SCORE_MIN and sc > best.get(desc, 0):
                best[desc] = round(float(sc), 3)
    return sorted(best.items(), key=lambda kv: -kv[1])


def _hit(labels, tokens):
    """True if any label contains any of the tokens at/above the score threshold."""
    return any(any(t in desc for t in tokens) for desc, _ in labels)


def _signals_from_labels(labels):
    """Map detected labels to the condition sub-survey's lift signals, conservatively.
    c_state is left None on purpose: a photo set cannot reliably judge overall dilapidation
    (staging, lighting and crops mislead), so the human's overall-condition answer keeps
    governing the floor. We only ever propose the high-end LIFTS, and only on clear
    premium-material evidence. Returns the signals dict the sub-survey understands."""
    has_premium = _hit(labels, _PREMIUM)
    premium_kinds = sum(1 for t in _PREMIUM
                        if any(t in desc for desc, _ in labels))
    sig = {"c_state": None}                          # never inferred from photos
    # a premium material seen alongside the room only credits that room's fitting
    sig["c_kitchen"] = 2 if (has_premium and _hit(labels, _KITCHEN)) else None
    sig["c_bath"] = 2 if (has_premium and _hit(labels, _BATH)) else None
    if premium_kinds >= 2:
        sig["c_premium"] = 2
    elif premium_kinds == 1:
        sig["c_premium"] = 1
    else:
        sig["c_premium"] = None
    return sig


def _derive(signals):
    """Derive the tier exactly as the bot would, via the existing engine path. Lazy,
    guarded import so vision.py never hard-depends on bot.py. Falls back to a faithful
    local mirror of the lift rule if the import is unavailable."""
    ans = {k: v for k, v in signals.items() if v is not None}
    try:
        import bot
        tier, _ = bot.derive_finish(ans)
        return tier
    except Exception:
        # mirror of bot.derive_finish's lift rule for the photo signals (c_state absent)
        if not ans:
            return "average"
        high_end = sum(1 for f in ("c_kitchen", "c_bath", "c_premium") if ans.get(f) == 2)
        return "very_high" if high_end >= 2 else ("high" if high_end == 1 else "average")


def assess(image_urls, max_images=_MAX):
    """Propose condition signals + a finish tier from listing photos. Returns
    {ok, proposed_tier, signals, labels, confidence, photo_count, note} or
    {ok: False, reason}. Never raises. The tier is a PROPOSAL to pre-fill the condition
    sub-survey - only a human-confirmed tier moves the figure."""
    urls = [u for u in (image_urls or []) if u][:int(max_images)]
    if not urls:
        return {"ok": False, "reason": "no images given"}
    key = _key()
    if not key:
        return {"ok": False, "reason": "Vision API key not set"}
    try:
        resp = _annotate(urls, key)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"ok": False, "reason": "Vision auth rejected"}
        return {"ok": False, "reason": f"Vision HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}
    # a per-image error object surfaces inside responses; treat a wholly empty read honestly
    if not isinstance(resp, dict) or "responses" not in resp:
        return {"ok": False, "reason": "unexpected Vision response"}

    labels = _labels(resp)
    signals = _signals_from_labels(labels)
    tier = _derive(signals)
    lifts = sum(1 for f in ("c_kitchen", "c_bath", "c_premium") if signals.get(f))
    if tier in ("high", "very_high") and lifts >= 2 and len(urls) >= 3:
        confidence = "medium"          # photos never give better than medium on their own
    elif tier == "average":
        confidence = "low" if len(urls) < 3 else "medium"
    else:
        confidence = "low"

    note = ("Proposed from listing photos to pre-fill the condition sub-survey - a human "
            "confirms it before it is used. Photos cannot judge overall condition reliably, "
            "so the overall-condition answer is left for you to set; only genuinely premium "
            "materials lift the tier. This is the one condition input that moves the figure, "
            "and only once confirmed.")
    return {
        "ok": True, "proposed_tier": tier, "signals": signals,
        "labels": labels[:15], "confidence": confidence,
        "photo_count": len(urls), "note": note, "source": _SRC,
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    if sys.argv[1] == "assess":
        print(json.dumps(assess(sys.argv[2:]), indent=2, ensure_ascii=False))
    elif sys.argv[1] == "selftest":
        if not _key():
            print("vision selftest: no API key set - degraded path is the live behaviour here.")
            print("  assess ->", assess(["https://example.com/x.jpg"]).get("reason"))
            return
        r = assess(["https://example.com/kitchen.jpg"])
        print("vision assess:", "ok" if r.get("ok") else r.get("reason"),
              ("| tier " + r.get("proposed_tier", "")) if r.get("ok") else "")
    else:
        print("unknown command:", sys.argv[1])


if __name__ == "__main__":
    main()
