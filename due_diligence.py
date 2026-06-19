# -*- coding: utf-8 -*-
"""due_diligence.py - the Pre-Offer Due-Diligence Dossier (the per-profile flagship).

The product people actually pay for, drawn from VOC: one upfront, plain-English read on EVERY
public red flag against an address - BEFORE anyone spends £400-1,500 on a survey or ~£300 on
searches. Each flag answers four questions in the buyer's own words:

    WHAT IT MEANS  ·  WHAT TO ASK  ·  WHAT TO RENEGOTIATE  ·  DEAL-BREAKER?

Honesty contract (identical to the engine + guides):
  * We only RAISE a flag where there is real, free public data for it (flood designation,
    nearby planning, recorded crime, air quality, council-tax band, ...). No data -> no flag.
  * For the defects that have NO free per-address feed (Japanese knotweed, cladding/EWS1,
    subsidence history, the exact lease terms) we do NOT invent a finding - we FLAG THE QUESTION
    and tell the reader exactly what to demand of the seller/solicitor/surveyor. That is the
    product: knowing what to force, before you pay for the survey that would otherwise find it.
  * Nothing here moves the valuation figure. This is decision context beside the number.

Profile-framed: the same evidence, pointed at what THIS reader is deciding -
    buyer    -> should I commit, and what do I renegotiate?
    vendor   -> what will a buyer's surveyor raise, so I pre-empt it and protect my price?
    agent    -> the material-information disclosures I must make (CPRs / Material Information).
    investor -> what threatens yield, void, insurability and exit?

Built to mirror guides.py: a flag is one entry in CHECKS; the dossier, its delivery and any
deep-link all derive from it. A new public-data check is one function + one CHECKS row.
"""

# Each check: (key, build(sec, d, s)) -> a flag dict, or None when there is no real data.
# A flag dict: {key, title, finding, means, ask, renegotiate, breaker(bool|str), severity}.
# severity: "info" | "watch" | "serious" - drives ordering and the headline count of real flags.


def _flood(sec, d, s):
    env = (sec.get("environment") or {})
    fl = env.get("flood") or {}
    sev = (fl.get("severity") or fl.get("risk") or "").strip()
    if not sev:
        return None
    serious = any(w in sev.lower() for w in ("warning", "high", "significant"))
    return {
        "key": "flood", "severity": "serious" if serious else "watch",
        "title": "Flood risk", "finding": f"Environment Agency designation: {sev}.",
        "means": "A designation is a flag, not a discount - buyers price flooding only when it "
                 "loads the insurance premium or makes a lender cautious. Many designated homes "
                 "sell at full value with standard cover and no flooding history.",
        "ask": "Ask the seller for the actual flooding history and any past claims; get a real "
               "buildings-insurance quote NOW (premium AND excess) and check Flood Re applies; "
               "confirm your lender's stance for this postcode.",
        "renegotiate": "If the quote comes back loaded, the extra annual premium capitalised is a "
                       "fair, evidenced reduction - bring the quote to the table.",
        "breaker": "Only if cover is refused or a lender declines - otherwise a price/insurance "
                   "conversation, not a walk-away.",
    }


def _planning(sec, d, s):
    pl = (sec.get("planning") or {})
    n = pl.get("total")
    if not n:
        return None
    byst = ", ".join(f"{st}: {c}" for st, c in (pl.get("by_status") or [])[:5]) or None
    return {
        "key": "planning", "severity": "watch",
        "title": "Nearby planning & development",
        "finding": f"{n} recent planning application(s) recorded near the property"
                   + (f" ({byst})." if byst else "."),
        "means": "A large nearby scheme can cut light, parking or a view - or add amenity and "
                 "lift demand. Direction depends on the scheme, not the count. An extension next "
                 "door rarely moves your price; a block of flats or a change of use can.",
        "ask": "Open each application on the council portal: read the description, the decision, "
               "the height and use-class, the distance to the boundary, and any appeal.",
        "renegotiate": "If an approved scheme will measurably harm the property (light/parking/"
                       "outlook), that is a documented basis to revise the offer.",
        "breaker": False,
    }


def _crime(sec, d, s):
    cr = (sec.get("safety") or {})
    n = cr.get("count") or cr.get("total")
    if not n:
        return None
    return {
        "key": "crime", "severity": "info",
        "title": "Recorded crime nearby",
        "finding": f"{n} street-level crimes recorded near the property in the latest published month.",
        "means": "Recorded crime is context, not a price input - levels track the area, and one "
                 "month is a snapshot. It matters to some buyers and to insurance, not to the "
                 "sold-evidence figure.",
        "ask": "Look at the trend over several months on police.uk, and the category mix "
               "(anti-social vs acquisitive), not a single month's count.",
        "renegotiate": "Not a renegotiation lever on its own.",
        "breaker": False,
    }


def _air(sec, d, s):
    env = (sec.get("environment") or {})
    aq = env.get("air") or {}
    idx = aq.get("index") or aq.get("band") or aq.get("summary")
    if not idx:
        return None
    return {
        "key": "air", "severity": "info",
        "title": "Air quality",
        "finding": f"Local air-quality reading: {idx}.",
        "means": "A liveability and (for some) health consideration; it does not move the figure.",
        "ask": "If it matters to you, check the monitoring station distance and the annual average, "
               "not a single reading.",
        "renegotiate": "Not a renegotiation lever.",
        "breaker": False,
    }


def _planning_constraints(sec, d, s):
    pc = (sec.get("planning_constraints") or {})
    items = pc.get("items") or []
    if not items:
        return None
    labels = sorted({i.get("label") for i in items if i.get("label")})
    serious = any(("article 4" in (l or "").lower() or "flood" in (l or "").lower()) for l in labels)
    return {
        "key": "planning_constraints", "severity": "serious" if serious else "watch",
        "title": "Planning designations on the site",
        "finding": "This property falls within: " + "; ".join(labels) + ".",
        "means": "These control what you can change and how the property is valued. A conservation "
                 "area or Article 4 direction removes permitted-development rights (windows, cladding, "
                 "an extension may all need consent); a flood-risk zone is the statutory EA zone; "
                 "green belt tightly restricts development.",
        "ask": "Ask the seller/agent which alterations already have consent, and the local authority "
               "what the designation specifically restricts here.",
        "renegotiate": "If a planned alteration is blocked or needs costly consent, that is a "
                       "documented basis to revise the offer or your plans.",
        "breaker": "Rarely - but verify any change you're relying on is actually permitted.",
    }


def _tax(sec, d, s):
    mat = (sec.get("material") or {})
    band = mat.get("band") or mat.get("council_tax_band")
    if not band:
        return None
    return {
        "key": "council_tax", "severity": "info",
        "title": "Council tax",
        "finding": f"Council-tax band {band}.",
        "means": "A fixed running cost a buyer prices in - and occasionally a clue the property "
                 "was banded at a different size/state than today.",
        "ask": "Confirm the band on the VOA register and the actual annual charge for the borough.",
        "renegotiate": "Not a renegotiation lever, but a real cost to budget.",
        "breaker": False,
    }


# Public-data checks - each raises a flag ONLY when the free spine actually has the data.
CHECKS = [
    ("flood", _flood),
    ("planning_constraints", _planning_constraints),
    ("planning", _planning),
    ("crime", _crime),
    ("air", _air),
    ("council_tax", _tax),
]

# The defects with NO free per-address feed. We never fabricate a finding for these - we hand the
# reader the exact questions to FORCE, so they learn the answer before paying for a survey/search.
# (key, title, ask, why) - always included, framed as questions, never as findings.
FORCE_QUESTIONS = [
    ("knotweed", "Japanese knotweed",
     "Ask the seller to confirm (on the TA6 form) whether knotweed is or has been present, and for "
     "any treatment plan/guarantee.",
     "Lenders can refuse or retain funds; treatment runs years. There is no public per-address feed - "
     "the seller's disclosure and a surveyor's eye are the only sources."),
    ("cladding", "Cladding / EWS1 (flats & tall buildings)",
     "If a flat or in a building over ~11m, demand the EWS1 form and any remediation status before you "
     "spend a penny on legals.",
     "No EWS1 can make a flat unmortgageable and unsellable. Not in any free dataset - it must come from "
     "the managing agent/freeholder."),
    ("subsidence", "Subsidence / structural history",
     "Ask for any history of subsidence, underpinning, or related insurance claims, and whether cover has "
     "ever been refused or loaded.",
     "Past subsidence follows the building through insurance records; a clay-soil or tree-lined street "
     "raises the question. The history itself is not public per-address."),
    ("lease", "Lease length, ground rent & service charge (if leasehold)",
     "If leasehold, get the exact unexpired term, the ground rent (and any doubling clause), and the "
     "service-charge history before offering.",
     "Under ~80 years marriage value bites and lenders get cautious; runaway service charges are a direct "
     "cost. Terms vary per lease and are not reliably public."),
]


# A lens points the SAME honest dossier at one decision: it leads with the topic, orders the
# relevant public flags first, and emphasises the questions to force for that topic. It never
# hides a real flag (everything still renders) - it just makes each product genuinely distinct.
_LENS = {
    "survey": {
        "lead": "Brief your surveyor on the RIGHT things for this address - the public flags to "
                "confirm and the defects to make them look for, before you pay £400-1,500 for the survey.",
        "flags": ["flood", "planning_constraints", "planning", "air"],
        "force": ["subsidence", "knotweed", "cladding"]},
    "conveyancing": {
        "lead": "The ownership, title, boundary and planning questions to put to your solicitor up "
                "front - the public record's red flags before you sink money into searches and legals.",
        "flags": ["planning_constraints", "planning"],
        "force": ["lease", "cladding"]},
    "insurance": {
        "lead": "Where the public record could LOAD your buildings-insurance premium on this address "
                "- what to get a real quote on before you commit.",
        "flags": ["flood", "planning_constraints"],
        "force": ["subsidence"]},
    "risk": {
        "lead": "The hidden-defect and environmental risk read on this address - flood, ground "
                "stability, radon and planning - in plain English, with what to demand.",
        "flags": ["flood", "planning_constraints", "planning", "air"],
        "force": ["subsidence", "knotweed"]},
}


def _profile_lead(profile):
    """One framing line: the same dossier, pointed at what THIS reader is deciding."""
    return {
        "buyer":   "Before you commit - and before you spend £1,000+ on a survey and searches - here is "
                   "every public red flag on this address, in plain English, with what to ask and what to "
                   "renegotiate.",
        "vendor":  "Here is what a buyer's surveyor and solicitor will raise on this address - so you "
                   "pre-empt it, protect your price, and avoid a renegotiation you didn't see coming.",
        "seller":  "Here is what a buyer's surveyor and solicitor will raise on this address - so you "
                   "pre-empt it, protect your price, and avoid a renegotiation you didn't see coming.",
        "agent":   "The material-information disclosures for this address (Consumer Protection Regulations): "
                   "the public facts that must be on the listing, with the questions to put to your vendor.",
        "investor":"The public red flags that threaten yield, voids, insurability and your exit on this "
                   "address - what to verify before you commit capital.",
    }.get(profile, "Every public red flag on this address, in plain English - what it means, what to ask, "
                   "and what to renegotiate.")


def assess(context, d=None, s=None):
    """Run every public-data check against the gathered free spine. Returns the list of REAL flags
    (data-gated, ordered serious -> info). `context` is area_context.gather()'s dict (or its
    'sections')."""
    sec = (context or {}).get("sections", context) or {}
    flags = []
    for _key, fn in CHECKS:
        try:
            f = fn(sec, d or {}, s or {})
        except Exception:
            f = None
        if f:
            flags.append(f)
    order = {"serious": 0, "watch": 1, "info": 2}
    flags.sort(key=lambda f: order.get(f.get("severity"), 3))
    return flags


def build(context, d=None, s=None, profile="buyer", lens=None):
    """The dossier body as a list of HTML-ish lines (same shape guides.build returns), profile-framed.
    Always returns content (the force-these-questions block stands alone), so the flagship is never
    empty - but it only states FINDINGS where real free data exists. `lens` (survey/conveyancing/
    insurance/risk) points the same honest dossier at one decision: it leads with the topic and
    orders that topic's flags + questions first, WITHOUT hiding any real flag. Returns None only on
    bad input."""
    try:
        flags = assess(context, d, s)
    except Exception:
        flags = []
    lc = _LENS.get((lens or "").strip().lower())
    if lc:
        order = {k: i for i, k in enumerate(lc["flags"])}
        flags = sorted(flags, key=lambda f: order.get(f.get("key"), 99))
        L = [lc["lead"], ""]
    else:
        L = [_profile_lead(profile), ""]
    real = len(flags)
    if real:
        L.append(f"<b>What the public record flags ({real})</b>")
        for f in flags:
            tag = {"serious": "⚠️ ", "watch": "• ", "info": "· "}.get(f.get("severity"), "• ")
            L += ["", f"{tag}<b>{f['title']}</b> - {f['finding']}",
                  f"   <i>What it means:</i> {f['means']}",
                  f"   <i>What to ask:</i> {f['ask']}",
                  f"   <i>Renegotiate:</i> {f['renegotiate']}"]
            br = f.get("breaker")
            if br and br is not True:
                L.append(f"   <i>Deal-breaker?</i> {br}")
            elif br is True:
                L.append("   <i>Deal-breaker?</i> Potentially - verify before you commit.")
    else:
        L.append("<b>The public record raises no specific flag on this address today.</b> That is "
                 "good news, not a clean bill of health - the checks below have no free per-address "
                 "feed, so you still force them yourself.")
    # the always-on questions to FORCE (no free data -> never a fabricated finding)
    L += ["", "<b>Force these before you spend on a survey or searches</b>",
          "These have no free public feed - the answer comes from the seller, solicitor or surveyor. "
          "Demanding them upfront is how you avoid an abortive purchase."]
    fq = FORCE_QUESTIONS
    if lc:                                     # lens: lead with this topic's questions to force
        pri = {k: i for i, k in enumerate(lc.get("force", []))}
        fq = sorted(FORCE_QUESTIONS, key=lambda q: pri.get(q[0], 99))
    for _key, title, ask, why in fq:
        L += ["", f"• <b>{title}</b>", f"   {ask}", f"   <i>Why:</i> {why}"]
    L += ["", "<i>Sources: Environment Agency, local planning registers, police.uk, VOA, air-quality "
          "monitoring - all free public data. Guidance, not a survey, valuation or legal advice. Nothing "
          "here changes the valuation figure.</i>"]
    return L


def summary_line(context, d=None, s=None):
    """A one-liner for a card/teaser: how many real flags + the force-count. Honest, never inflated."""
    flags = assess(context, d, s)
    return (f"{len(flags)} public red flag(s) found · {len(FORCE_QUESTIONS)} questions to force "
            "before you spend on a survey")


def selftest():
    ctx = {"sections": {
        "environment": {"flood": {"severity": "Flood warning area"}, "air": {"index": "Moderate"}},
        "planning": {"total": 4, "by_status": [("Approved", 2), ("Pending", 2)]},
        "planning_constraints": {"ok": True, "items": [
            {"dataset": "conservation-area", "label": "Conservation area", "name": "Trafalgar Square"}]},
        "safety": {"count": 31},
        "material": {"band": "D"},
    }}
    flags = assess(ctx)
    assert [f["key"] for f in flags][:1] == ["flood"], "serious flag must sort first"
    assert {f["key"] for f in flags} == {"flood", "planning_constraints", "planning", "crime", "air", "council_tax"}
    assert any("Conservation area" in f["finding"] for f in flags if f["key"] == "planning_constraints")
    body = build(ctx, profile="buyer")
    assert any("Force these" in x for x in body)
    assert any("knotweed" in x.lower() for x in body)
    assert any("What to ask" in x for x in body)
    # data-gated: an empty spine raises no findings but STILL returns the force-questions dossier
    empty = build({"sections": {}}, profile="vendor")
    assert any("raises no specific flag" in x for x in empty)
    assert any("knotweed" in x.lower() for x in empty)
    assert assess({"sections": {}}) == []
    # profile framing differs
    assert "surveyor" in build({"sections": {}}, profile="agent")[0].lower() or \
           "material" in build({"sections": {}}, profile="agent")[0].lower()
    return "ok"


if __name__ == "__main__":
    print(selftest())
