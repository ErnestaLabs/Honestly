#!/usr/bin/env python3
"""products.py - the personalised, audience-specific deliverables.

The valuation is the same honest number for everyone. What changes by audience is
what you DO with it, so each component here is written for one reader:

  agent   - win the instruction and work the street: action plan, prospecting
            email, a door-knock route over 20 nearby targets, an actual map.
  vendor  - sell for the most without being talked up by an agent: action plan,
            agent-vetting email, the live competition (your rivals) mapped.
  buyer   - offer well and negotiate from evidence: offer plan, an offer email to
            the agent, the live alternatives mapped.

Everything is grounded in the same engine output (sold evidence, live market,
macro context). No hype, no invented numbers - if a piece of data is missing the
component degrades to what it can honestly say.
"""
import os
import appraise
from appraise import money, pos_loc, listing_link, postcode_of

# coordinate fields a PropertyData listing might carry, in order of preference
_LAT = ("latitude", "lat")
_LNG = ("longitude", "lng", "lon", "lng")


def _coord(x):
    lat = next((x.get(k) for k in _LAT if x.get(k) not in (None, "")), None)
    lng = next((x.get(k) for k in _LNG if x.get(k) not in (None, "")), None)
    try:
        return (float(lat), float(lng)) if lat is not None and lng is not None else None
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ nearby schools (Ofsted)
def nearby_schools(r, key, n=6):
    """Nearest state schools with phase, distance and a link to the OFFICIAL Ofsted report.

    Pulled from PropertyData's schools endpoint (same key, no new dependency). We show
    only what the record states - name, phase, type, distance, pupils - and link each
    school to its public Ofsted page so the reader verifies the rating at source. We
    never assert a rating ourselves. Best-effort: returns [] on any failure, never raises."""
    subj = r["subject"]
    pc = postcode_of(subj.get("address", ""))
    if not pc:
        return []
    try:
        resp = appraise.api("schools", key, postcode=pc)
    except Exception:
        return []
    data = (resp or {}).get("data") or {}
    nearest = []
    # state schools live under data.state.nearest; tolerate shape drift
    for bucket in ("state", "independent"):
        b = data.get(bucket)
        if isinstance(b, dict) and isinstance(b.get("nearest"), list):
            for s in b["nearest"]:
                s = dict(s); s["sector"] = bucket
                nearest.append(s)
    if not nearest:
        return []
    def _dist(s):
        try:    return float(s.get("distance"))
        except (TypeError, ValueError): return 99.0
    nearest.sort(key=_dist)
    out = []
    for s in nearest[:n]:
        name = (s.get("name") or "").strip()
        if not name:
            continue
        out.append({
            "name": name,
            "phase": (s.get("phase") or "").strip(),
            "type": (s.get("type") or "").strip(),
            "sector": s.get("sector", "state"),
            "pupils": s.get("num_pupils"),
            "distance": _dist(s) if _dist(s) < 99 else None,
            "ofsted_url": (s.get("url") or "").strip(),
        })
    return out


def schools_brief(schools):
    """One compact HTML block for the bot card. '' when there is nothing honest to say."""
    if not schools:
        return ""
    import html as _html
    lines = ["🎓 <b>Schools nearby</b> <i>(rating: verify on Ofsted)</i>"]
    for s in schools[:5]:
        bits = [s["name"]]
        if s.get("phase"): bits.append(s["phase"])
        if s.get("distance") is not None: bits.append(f"{s['distance']:.1f} mi")
        label = _html.escape(" · ".join(bits))
        if s.get("ofsted_url"):
            lines.append(f'• <a href="{_html.escape(s["ofsted_url"])}">{label}</a>')
        else:
            lines.append(f"• {label}")
    return "\n".join(lines)


# ------------------------------------------------------------------ target listings
def target_listings(r, key, audience, n=20):
    """Up to n live nearby listings to act on, ranked for this audience.
      agent  - reduction/instruction opportunities first (longest on market), then fresh
      vendor - the fiercest competition first (highest asking in the band)
      buyer  - best-value available alternatives first (lowest asking, not under offer)
    Each row: address, loc, price, beds, dom, status, link, coord. Best-effort; [] on failure."""
    subj = r["subject"]
    pdtype = r.get("pdtype") or "flat"
    try:
        listings = appraise.pull_listings(subj, key, pdtype) or []
    except Exception:
        listings = []
    here = subj["address"].split(",")[0].strip().lower()
    rows, seen = [], set()
    for x in listings:
        if not (x.get("price") and x.get("address")):
            continue
        a0 = x["address"].split(",")[0].strip().lower()
        if a0 == here or a0 in seen:                 # drop the subject and duplicates
            continue
        seen.add(a0)
        rows.append(x)

    if audience == "agent":
        rows.sort(key=lambda x: (0 if (x.get("days_on_market") or 0) >= 90 else 1,
                                 -(x.get("days_on_market") or 0)))
    elif audience == "vendor":
        rows.sort(key=lambda x: -(x.get("price") or 0))
    else:  # buyer
        rows = [x for x in rows if not x.get("sstc")]
        rows.sort(key=lambda x: (x.get("price") or 0))

    out = []
    for x in rows[:n]:
        pname, plink = listing_link(x.get("url"))
        out.append({
            "address": x["address"], "loc": pos_loc(x["address"]),
            "price": x["price"], "price_str": money(x["price"]),
            "beds": x.get("bedrooms"), "dom": x.get("days_on_market") or 0,
            "status": "Under offer" if x.get("sstc") else "Available",
            "portal": pname, "link": plink, "coord": _coord(x),
        })
    return out


def target_map(targets, subj, out_path="_targets.png"):
    """A real map: the subject plus the target listings, markered. Returns the path or
    None. Prefers listing coordinates; falls back to address strings (Google geocodes
    them). Caps at 20 markers so the static-map URL stays well within limits."""
    import maps_tools
    pts = []
    sc = None
    if subj.get("lat") and subj.get("lng"):
        sc = f"{subj['lat']},{subj['lng']}"
    pts.append(sc or subj["address"])
    for t in targets[:19]:
        c = t.get("coord")
        pts.append(f"{c[0]},{c[1]}" if c else t["address"])
    res = maps_tools.static_map(out_path, markers=pts, size="640x640")
    return out_path if res.get("ok") else None


# ------------------------------------------------------------------ plan of action
def _g(d):
    """Common figures pulled once for the copy below."""
    return (d.get("guide_value_str") or "", d.get("range_str") or "",
            money(d["central"]) if d.get("central") else "", d.get("address") or "this property")


def plan_of_action(d, r, audience):
    """A short, numbered action plan written for the reader. Returns a list of lines."""
    guide, rng, central, addr = _g(d)
    pos = d.get("positioning")
    mom = (d.get("macro") or {}).get("momentum")
    stuck = (pos.get("stuck") or 0) if pos else 0
    if audience == "agent":
        L = ["<b>Action plan - win it and work the street</b>",
             f"1. Lead with evidence, not a number. Open the pitch on the {len(r['compsA'])} "
             f"comparable sales, then land the figure: assessed {rng}.",
             f"2. Recommend listing at {guide}. The sold evidence supports it; a higher quote "
             f"wins the instruction, not the sale."]
        if stuck:
            L.append(f"3. Use the {stuck} stuck listings above this price as your proof that "
                     f"over-asking sits. That is your close.")
        else:
            L.append("3. Show how a correctly-priced launch draws offers in the first two weeks.")
        L.append("4. Work the door-knock route below - you have just valued this street, so you "
                 "are the local expert at every door.")
        L.append("5. Target the longest-listed homes first: a reduction conversation is an "
                 "instruction conversation.")
        if mom:
            L.append(f"6. Frame the timing honestly: {mom['headline']}")
    elif audience == "vendor":
        L = ["<b>Action plan - sell for the most, honestly</b>",
             f"1. List at {guide}, not at the highest number an agent quotes you. Homes that "
             f"over-ask sit, then reduce, and a reduced listing signals weakness.",
             "2. Interview agents with this report in hand. Ask each to justify their figure "
             "against the sold comparables; the evidence is your defence against an inflated quote.",
             "3. Spend on presentation, not price: declutter, fix the obvious, get the photos "
             "right. Condition moves the achievable figure more than the asking price does."]
        if stuck:
            L.append(f"4. {stuck} comparable homes priced above you are stuck unsold. Price below "
                     f"them on purpose and you take their buyers.")
        else:
            L.append("4. Launch at the guide and review demand at two weeks - viewings and offers, "
                     "not the asking price, tell you if it is right.")
        if mom:
            L.append(f"5. Mind the timing: {mom['headline']} It shapes buyer budgets while you are on the market.")
    else:  # buyer
        L = ["<b>Action plan - offer well, negotiate from evidence</b>",
             f"1. Fair value is {rng}. Open around {guide} - anchored to what comparable homes "
             f"actually sold for, not the asking price.",
             "2. Put the evidence in writing with your offer. A seller argues with an opinion; "
             "they cannot argue with completed sales."]
        if stuck:
            L.append(f"3. Your leverage: {stuck} comparable homes have sat unsold 90+ days. A long "
                     f"listing means the seller is closer to yes than on day one.")
        else:
            L.append("3. Check days-on-market before you offer - the longer it has been listed, "
                     "the more room you have.")
        L.append("4. Make the offer subject to survey, and hold a firm walk-away number above the "
                 "top of the range.")
        if mom:
            L.append(f"5. Timing: {mom['headline']} Weaker momentum is negotiating room.")
    return L


# ------------------------------------------------------------------ email template
def email_template(d, r, audience):
    """A ready-to-send email/script the reader can copy. Returns {subject, body}."""
    guide, rng, central, addr = _g(d)
    short = addr.split(",")[0]
    pos = d.get("positioning")
    if audience == "agent":
        subject = f"Your home on {short} - what the sold evidence says it's worth"
        body = (f"Hi,\n\n"
                f"I value homes on your street, and I have just put together an evidence-backed "
                f"appraisal for a property like yours near {short}.\n\n"
                f"The short version: comparable homes nearby have sold in the range {rng}. I am "
                f"happy to share the full breakdown - every comparable links to its HM Land "
                f"Registry record, so you can check the figures yourself, no obligation.\n\n"
                f"If you have ever wondered what yours would fetch today, reply and I will send it over.\n\n"
                f"Best regards,\n[Your name]\n[Agency] - [phone]")
    elif audience == "vendor":
        subject = f"{short} - please justify your valuation against these sold comparables"
        body = (f"Hi,\n\n"
                f"Thank you for your valuation of {short}. Before I instruct, I would like to "
                f"understand how the figure is supported.\n\n"
                f"From the sold evidence I have, comparable homes have completed in the range "
                f"{rng}. Could you confirm the specific recently-sold comparables behind your "
                f"number, and the guide price you would actually launch at?\n\n"
                f"I am looking for the agent who will achieve the best price, not the one who "
                f"quotes the highest to win the instruction.\n\n"
                f"Best regards,\n[Your name]")
    else:  # buyer
        subject = f"Offer for {short}"
        body = (f"Hi,\n\n"
                f"Thank you for your time on {short}. I would like to submit an offer of "
                f"{guide}.\n\n"
                f"This is grounded in the sold evidence: comparable homes nearby have completed "
                f"in the range {rng}, and I am ready to proceed quickly with a mortgage in "
                f"principle in place. My offer is subject to survey.\n\n")
        if pos and pos.get("stuck"):
            body += ("I have noted that several comparable homes have been on the market for some "
                     "time at higher prices, so I have pitched this at a level I can move on without delay.\n\n")
        body += "I look forward to hearing the seller's response.\n\nBest regards,\n[Your name]"
    return {"subject": subject, "body": body}
