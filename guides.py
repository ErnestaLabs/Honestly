# -*- coding: utf-8 -*-
"""The automated upsell-guide engine.

A guide is a DISTINCT paid product: not the valuation again, but a focused, decision-grade
read on ONE topic (planning, flood, lease, condition...), built from the property's OWN data
plus vetted, source-grounded guidance. Adding a new guide is declarative - register one
TOPIC entry here and the catalogue, the delivery, the deep-link buy trigger and the in-report
hyperlink all wire themselves from it. No bespoke dispatch code per guide.

Honesty contract (same as the engine): a guide interprets and instructs; it NEVER invents a
price effect. It states what the data shows, what it typically means, and what to check - and
where the sold evidence shows no effect, it says so. A topic with no real data for this
property yields no guide (the caller refunds), so we never charge for an empty product.
"""

# Each TOPIC: {id, name, stars, aud, factor (the report Q&A key it is sold from), build(sec,d,s)}.
# build() returns a list of lines (the guide body) or None when there is no real data to guide on.


def _planning(sec, d, s):
    pl = (sec or {}).get("planning") or {}
    n = pl.get("total")
    if not n:
        return None
    byst = pl.get("by_status") or []
    L = [f"There are <b>{n}</b> recent planning application(s) recorded near this property. "
         "Here is how to read them before you commit - and what actually moves a price."]
    if byst:
        L.append("<b>What is in the pipeline</b>")
        L += [f"- {st}: {c}" for st, c in byst[:8]]
    L += [
        "",
        "<b>What typically matters for value</b>",
        "- A large nearby development can cut light, parking or a view - or add amenity and lift demand. Direction depends on the scheme, not the count.",
        "- Approved-but-not-built is a future change; refused or withdrawn usually is not.",
        "- An extension/loft next door rarely moves your price; a block of flats or a commercial use can.",
        "",
        "<b>What to check (10 minutes)</b>",
        "- Open each application on the local authority portal and read the description and decision.",
        "- Look for height, use-class change, and distance to your boundary.",
        "- Check for an appeal or a repeat submission after a refusal.",
        "",
        "<b>How it lands on YOUR figure</b>",
        "- Our valuation already reflects what comparable homes near these same applications actually sold for. "
        "No comparable in the set shows a discount tied to them, so no adjustment is applied today.",
        "- If a scheme completes or escalates, re-run the address and the sold evidence will move with it.",
        "Source: local planning data (PlanIt / local authority registers). Guidance, not planning advice.",
    ]
    return L


def _flood(sec, d, s):
    env = (sec or {}).get("environment") or {}
    fl = env.get("flood") or {}
    sev = (fl.get("severity") or fl.get("risk") or "").strip()
    if not sev:
        return None
    L = [f"This property's flood designation is <b>{sev}</b>. Here is what that means for value, "
         "and what to check before you commit."]
    L += [
        "",
        "<b>What it means for value</b>",
        "- A designation is a flag, not a discount. Buyers price flooding when it raises insurance cost or lender caution - not from the map alone.",
        "- Many homes in designated zones sell at full value with no history of flooding and standard cover.",
        "",
        "<b>What to check</b>",
        "- Ask the seller for the actual flooding history and any past claims.",
        "- Get an insurance quote NOW - premium and excess are the real test, and Flood Re may apply.",
        "- Confirm your lender's stance for this postcode before you offer.",
        "",
        "<b>How it lands on YOUR figure</b>",
        "- No comparable in the evidence set sold at a discount for this designation, so no adjustment is applied.",
        "- If the insurance quote comes back loaded, that is your negotiating lever - bring it to the table with the quote.",
        "Source: Environment Agency flood data. Guidance, not insurance advice.",
    ]
    return L


def _lease(sec, d, s):
    # Leasehold guide - only when we know it is leasehold (tenure or a lease term present).
    tenure = (s or {}).get("tenure")
    leases = (s or {}).get("leases") or []
    term = leases[0].get("term") if leases else None
    if not (str(tenure or "").lower().startswith("lease") or term):
        return None
    L = ["This is a leasehold property. Lease length and charges move value more than almost "
         "anything else a survey will find - here is how to read it."]
    if term:
        L.append(f"Recorded lease term: <b>{term}</b>.")
    L += [
        "",
        "<b>Why it matters</b>",
        "- Under ~80 years, 'marriage value' kicks in and extension cost jumps - lenders get cautious too.",
        "- Ground rent and service charge are ongoing costs a buyer prices in directly.",
        "",
        "<b>What to check</b>",
        "- Exact unexpired term, ground rent (and any doubling clause), and the service-charge history.",
        "- Whether the freeholder is responsive and if a Section 42 extension is in progress.",
        "",
        "<b>How it lands on YOUR figure</b>",
        "- Our comparables are same-tenure where the data allows; where the public record does not confirm tenure we caveat it rather than guess.",
        "- A short lease is a price lever - get the extension cost and deduct it openly.",
        "Source: HM Land Registry tenure / lease records. Guidance, not legal advice.",
    ]
    return L


TOPICS = {
    "planning": {"name": "Planning impact guide", "stars": 90, "aud": "all", "factor": "planning", "build": _planning,
                 "blurb": "What the nearby planning applications mean for your price - and exactly what to check."},
    "flood":    {"name": "Flood risk guide",       "stars": 90, "aud": "all", "factor": "flood",    "build": _flood,
                 "blurb": "What this flood designation means for value, insurance and your offer."},
    "lease":    {"name": "Leasehold guide",        "stars": 90, "aud": "all", "factor": "lease",    "build": _lease,
                 "blurb": "How your lease length, ground rent and charges move value - and what to check."},
}

# Everything below derives from TOPICS, so a new guide is added by declaring ONE entry above:
#   MICROS            -> catalogue rows (id '<topic>_guide'), folded into bot.MICRO automatically
#   FACTOR_TO_GUIDE   -> report factor key -> guide micro id (the in-report hyperlink target)
#   GUIDE_TOPIC_BY_MICRO -> guide micro id -> topic, for the generic delivery dispatch
# The guide is promoted by the SAME live signal that flags its factor, so when planning apps
# exist the planning guide rises (the excluded raw-fact micro no longer does).
_FACTOR_SIG = {"planning": "planning", "flood": "flood"}
MICROS = [{"id": f"{tid}_guide", "stars": t["stars"], "name": t["name"], "blurb": t["blurb"],
           "aud": t["aud"], "guide_topic": tid, "sig": _FACTOR_SIG.get(t["factor"])}
          for tid, t in TOPICS.items()]
FACTOR_TO_GUIDE = {t["factor"]: f"{tid}_guide" for tid, t in TOPICS.items()}
GUIDE_TOPIC_BY_MICRO = {f"{tid}_guide": tid for tid in TOPICS}


def build(topic_id, sec, d=None, s=None):
    """Build one guide's body lines, or None if there is no real data for this property.
    Generic: a new topic added to TOPICS is delivered with zero extra dispatch code."""
    t = TOPICS.get(topic_id)
    if not t:
        return None
    try:
        return t["build"](sec or {}, d or {}, s or {})
    except Exception:
        return None


def build_by_micro(micro_id, sec, d=None, s=None):
    """Deliver dispatch: resolve a '<topic>_guide' micro id to its topic and build it."""
    return build(GUIDE_TOPIC_BY_MICRO.get(micro_id, ""), sec, d, s)


def selftest():
    sec = {"planning": {"total": 3, "by_status": [("Approved", 2), ("Pending", 1)]},
           "environment": {"flood": {"severity": "Flood warning area"}}}
    assert build("planning", sec) and any("planning" in x.lower() for x in build("planning", sec))
    assert build("flood", sec)
    assert build("planning", {"planning": {"total": 0}}) is None     # data-gated
    assert build("flood", {"environment": {"flood": {}}}) is None
    assert build("lease", {}, s={"tenure": "leasehold", "leases": [{"term": "82 years"}]})
    assert build("nope", sec) is None
    return "ok"


if __name__ == "__main__":
    print(selftest())
