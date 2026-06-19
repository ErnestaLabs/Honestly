# -*- coding: utf-8 -*-
"""catalogue.py - the declarative product catalogue + the hybrid Pro economics.

(Named catalogue.py, not products.py - products.py already exists as the schools/listings/plan
brief module. This is the SELLABLE catalogue.)

ONE registry for every paid product across the three profiles (buyer / seller / agent), plus the
investor variant. Mirrors guides.py: a product is one entry in CATALOGUE; the storefront, the
price, the purchase routing and the delivery all derive from it. Adding a product is one row.

The user's spec, encoded exactly:
  * Pro is £14.99/mo (bot.STARS_SUB). It is HYBRID:
      - each profile's FLAGSHIP report + the area/market READS are INCLUDED with Pro (free),
      - PACKS and BUNDLES cost CREDITS from the monthly Pro pool,
      - a NON-subscriber can buy any product standalone at its charm Stars price.
  * Every product is FREE-DATA synthesis. The interpretation / decision IS the product; we never
    resell raw per-record data. The flagship is the Pre-Offer Due-Diligence Dossier
    (due_diligence.py), profile-framed.

`kind`: flagship | read | pack | bundle.  `included` (with Pro) == kind in {flagship, read}.
`credits`: the Pro-pool cost (0 for included).  `price_gbp`: the standalone charm price.
`data_sources`: free spine ids -> drive the citations (brand.DELIVERABLE_MAP).  `producer`:
which builder delivers it (see build()).
"""

STARS_PER_GBP = 60          # mirror bot.STARS_PER_GBP (kept local so this module imports cheaply)


def _charm(v):
    """Charm price: ends in .99, £0.99 floor - the one rule used everywhere (mirrors bot._charm)."""
    return max(0.99, round(v) - 0.01)


def _p(profile, id, name, kind, credits, price_gbp, data_sources, producer, blurb,
       *, bundle=False, discount=None, includes=None, input=None):
    # `input`: an optional {key,label,placeholder} the Mini App collects at purchase and forwards
    # so a need-named diagnostic gets its exact number (the asking price, the agent's proposed cut).
    return {"id": id, "profile": profile, "name": name, "kind": kind,
            "included": kind in ("flagship", "read"), "credits": int(credits),
            "price_gbp": float(price_gbp), "data_sources": list(data_sources),
            "producer": producer, "blurb": blurb, "bundle": bundle,
            "discount": discount, "includes": includes or [], "input": input}


_PD = ["hmlr_ppd", "hmlr_hpi"]                       # sold + index
_RISK = ["flood", "bgs", "ukradon"]                  # hidden-defect spine
_OWN = ["ccod_ocod", "inspire"]                      # ownership + boundary
_PLAN = ["planning_data"]

CATALOGUE = [
    # ---------------- BUYER ----------------
    _p("buyer", "buyer_001", "Red-Flag Interpretation Report", "flagship", 0, 0.0,
       _PLAN + ["flood", "bgs"] + _OWN, "dossier",
       "Every public red flag on the address, in plain English - what it means, what to ask, what to renegotiate."),
    _p("buyer", "buyer_002", "Offer Strategy Playbook", "pack", 2, 4.99,
       _PD + _PLAN + ["flood", "bgs"], "decision",
       "What to offer and why - sold evidence, scenarios, and the levers the flags hand you."),
    _p("buyer", "buyer_003", "Negotiation Talking Points", "pack", 2, 4.99,
       _PLAN + ["flood", "bgs"] + _OWN, "negotiation",
       "The exact, evidence-backed points to make at the table - each tied to a public fact."),
    _p("buyer", "buyer_004", "Survey Prep Checklist", "pack", 1, 2.99,
       _PLAN + ["flood", "bgs", "inspire"], "dossier",
       "Brief your surveyor on the right things - the flags to confirm before you pay for the survey."),
    _p("buyer", "buyer_005", "Conveyancing Red Flags", "pack", 2, 4.99,
       _OWN + _PLAN, "dossier",
       "The ownership, boundary and title questions to put to your solicitor up front."),
    _p("buyer", "buyer_006", "Risk Narrative Guide", "pack", 1, 2.99,
       _RISK + _PLAN, "dossier",
       "Flood, ground stability, radon and planning - what each means for this address and what to demand."),
    _p("buyer", "buyer_007", "Insurance Implications Report", "pack", 1, 2.99,
       _RISK, "dossier",
       "Where the public risk flags could load a premium - what to quote before you commit."),
    _p("buyer", "buyer_008", "Decision Confidence Score", "pack", 1, 2.99,
       _PD + _PLAN + ["flood", "bgs", "police_uk"], "decision",
       "A structured, evidenced read on whether to proceed - and on what terms."),
    _p("buyer", "buyer_009", "Comparable Watchlist Setup", "read", 0, 2.99,
       _PD, "watchlist",
       "Track new sold comparables on this street - we ping you when fresh evidence lands."),
    _p("buyer", "buyer_010", "Buyer's Complete Toolkit", "bundle", 8, 19.99,
       _PD + _PLAN + _RISK + _OWN, "bundle",
       "The full buyer kit - flagship dossier plus every playbook, at a bundle price.",
       bundle=True, discount="20%",
       includes=["buyer_001", "buyer_002", "buyer_003", "buyer_004", "buyer_005",
                 "buyer_006", "buyer_007", "buyer_008"]),
    # ---------------- SELLER ----------------
    _p("seller", "seller_001", "Defensible Pricing Narrative", "flagship", 0, 0.0,
       _PD + _PLAN + ["flood", "bgs"], "dossier",
       "The evidence-backed case for your price - and the buyer objections you can pre-empt."),
    _p("seller", "seller_002", "Buyer Objection Playbook", "pack", 2, 4.99,
       _PLAN + ["flood", "bgs"] + _OWN, "negotiation",
       "Every public flag a buyer's surveyor will raise, with your prepared, evidenced answer."),
    _p("seller", "seller_003", "Marketing Positioning Brief", "pack", 2, 4.99,
       ["hmlr_hpi"] + _PLAN + ["ofcom", "police_uk", "ons_census"], "market",
       "How to position the listing - the area facts that sell, framed for your buyer."),
    _p("seller", "seller_004", "Conveyancing Prep Pack", "pack", 1, 2.99,
       _OWN + _PLAN, "dossier",
       "Get your title, boundary and disclosures in order before they slow the sale."),
    _p("seller", "seller_005", "Flood / Ground Risk Narrative", "pack", 1, 2.99,
       _RISK, "dossier",
       "Get ahead of the risk flags - the honest narrative that stops a late renegotiation."),
    _p("seller", "seller_006", "Buyer Profile Targeting", "pack", 1, 2.99,
       ["ons_census", "police_uk", "ofcom", "voa"], "profile",
       "Who buys on this street, and what they value - aim the marketing at them."),
    _p("seller", "seller_007", "Comparable Watchlist Setup", "read", 0, 2.99,
       _PD, "watchlist",
       "Track new sold comparables on your street - know the moment the evidence moves."),
    _p("seller", "seller_008", "Negotiation Defense Toolkit", "pack", 2, 4.99,
       _PD + _PLAN + ["flood", "bgs"], "negotiation",
       "Hold your price - the evidence and the answers for every lever a buyer will try."),
    _p("seller", "seller_009", "Market Momentum Report", "read", 0, 2.99,
       ["hmlr_hpi", "hmlr_ppd"] + _PLAN, "market",
       "Is your area rising or stalling - demand, momentum and what it means for timing."),
    _p("seller", "seller_010", "Seller's Complete Toolkit", "bundle", 12, 24.99,
       _PD + _PLAN + _RISK + _OWN, "bundle",
       "The full seller kit - flagship plus every playbook and the market read, bundled.",
       bundle=True, discount="17%",
       includes=["seller_001", "seller_002", "seller_003", "seller_004", "seller_005",
                 "seller_006", "seller_008", "seller_009"]),
    _p("seller", "seller_011", "Property Audio Briefing", "pack", 3, 6.99,
       _PD + _PLAN + ["flood", "bgs"], "podcast",
       "A voice briefing of every key fact for your sale — pricing evidence, risk flags and buyer objections. Audio, ready in minutes."),
    # ---- NEED-NAMED: products named after the urgent question the seller is searching ----
    _p("seller", "seller_why_not_selling", "Why isn't my house selling?", "pack", 2, 4.99,
       _PD, "diagnostic",
       "The honest answer from your own sold record: is it priced above what the street sells for, "
       "is the market cold, and exactly what to change. Enter your asking price, get the gap in pounds and the steps.",
       input={"key": "asking", "label": "Your current asking price (£)", "placeholder": "e.g. 450000"}),
    _p("seller", "seller_should_i_cut", "My agent wants to cut my price — should I?", "pack", 2, 4.99,
       _PD, "price_cut",
       "Your agent is pushing a price drop. Is it justified by the sold record, or are they chasing "
       "a quick commission? Enter the price they're proposing — get the verdict in pounds and your counter.",
       input={"key": "quoted", "label": "The price your agent is proposing (£)", "placeholder": "e.g. 420000"}),
    _p("seller", "seller_offer_check", "Is this offer any good — accept or hold?", "pack", 2, 4.99,
       _PD, "offer_check",
       "An offer's in and you've got hours to decide. Lowball, fair, or strong? Enter the offer — get "
       "the verdict against the sold record, your counter figure, and when to hold vs accept.",
       input={"key": "offer", "label": "The offer you've received (£)", "placeholder": "e.g. 430000"}),
    _p("seller", "seller_agent_quote", "An agent valued it high — is it real?", "pack", 2, 4.99,
       _PD, "agent_quote",
       "One agent's number looks too good. Is it realistic, or a pitch to win your instruction that "
       "leaves you reducing in 6 weeks? Enter their valuation — get the honest read.",
       input={"key": "quoted", "label": "The price the agent valued it at (£)", "placeholder": "e.g. 500000"}),
    # ---------------- BUYER AUDIO ----------------
    _p("buyer", "buyer_011", "Property Audio Briefing", "pack", 3, 6.99,
       _PD + _PLAN + ["flood", "bgs"], "podcast",
       "A voice briefing of every key fact about this property — risks, evidence and what to ask. Delivered as audio, ready in minutes."),
    # ---- NEED-NAMED: the buyer's core thought the moment they like a listing ----
    _p("buyer", "buyer_is_overpriced", "Is this house overpriced?", "pack", 2, 4.99,
       _PD, "overpriced",
       "Enter the asking price: is it above what this street actually sells for, by how much, and "
       "what should you offer instead? The gap is your negotiating headroom, in writing from the register.",
       input={"key": "asking", "label": "The listing's asking price (£)", "placeholder": "e.g. 575000"}),
    # ---------------- AGENT ----------------
    _p("agent", "agent_001", "Material Information Compliance Pack", "flagship", 0, 0.0,
       _PLAN + ["flood", "bgs"] + _OWN, "dossier",
       "The CPR material-information disclosures for the listing - every public fact, sourced."),
    _p("agent", "agent_002", "Instruction-Winning Valuation Brief", "pack", 2, 4.99,
       _PD + _PLAN + ["flood", "bgs"], "decision",
       "The evidenced valuation case that wins the instruction - figure, comparables, flags."),
    _p("agent", "agent_003", "Buyer Objection Rebuttal Toolkit", "pack", 2, 4.99,
       _PLAN + ["flood", "bgs"] + _OWN, "negotiation",
       "Pre-built, evidenced rebuttals to every objection a buyer will raise on this property."),
    _p("agent", "agent_004", "Deal Velocity Playbook", "pack", 2, 4.99,
       _PLAN + ["flood", "bgs"] + _OWN, "decision",
       "Surface the deal-killers early - the public flags to clear before they stall the sale."),
    _p("agent", "agent_005", "Buyer Profile Targeting", "pack", 1, 2.99,
       ["ons_census", "police_uk", "ofcom", "voa"], "profile",
       "Who buys here and what they value - aim the marketing and the viewings."),
    _p("agent", "agent_006", "Comparable Watchlist Setup", "read", 0, 2.99,
       _PD, "watchlist",
       "Track new sold comparables on the street for your vendor - fresh evidence, on tap."),
    _p("agent", "agent_007", "Risk Narrative Toolkit", "pack", 1, 2.99,
       _RISK, "dossier",
       "The honest risk narrative - flood, ground, radon - to disclose and to handle on the doorstep."),
    _p("agent", "agent_008", "Market Intelligence Brief", "read", 0, 2.99,
       ["hmlr_hpi", "hmlr_ppd"] + _PLAN + ["police_uk"], "market",
       "The local market read for your pitch - momentum, demand and the area story."),
    _p("agent", "agent_009", "Timeline Roadmap", "pack", 1, 2.99,
       _PD + _PLAN + _RISK + _OWN, "timeline",
       "Offer -> survey -> exchange -> completion: the stages, the risks, and what to chase when."),
    _p("agent", "agent_010", "Agent's Complete Toolkit", "bundle", 12, 24.99,
       _PD + _PLAN + _RISK + _OWN, "bundle",
       "The full agent kit - compliance flagship plus every brief and toolkit, bundled.",
       bundle=True, discount="17%",
       includes=["agent_001", "agent_002", "agent_003", "agent_004", "agent_005",
                 "agent_007", "agent_008", "agent_009"]),
    _p("agent", "agent_011", "Property Audio Briefing", "pack", 3, 6.99,
       _PD + _PLAN + ["flood", "bgs"], "podcast",
       "A voice briefing of the compliance picture, sold evidence and risk flags — ready to share with vendors and buyers alike."),
    # ---- NEED-NAMED (agent-framed): the question an agent asks about a stuck listing ----
    _p("agent", "agent_why_not_selling", "Why isn't this listing selling?", "pack", 2, 4.99,
       _PD, "diagnostic",
       "Your listing's gone quiet. Is it priced above the sold ceiling, is the market cold, what do "
       "you change? Enter the asking price — get the evidenced answer to take back to your vendor.",
       input={"key": "asking", "label": "The listing's current asking price (£)", "placeholder": "e.g. 450000"}),
]

BY_ID = {p["id"]: p for p in CATALOGUE}

# Dossier-family packs each point the SAME honest due-diligence engine at a DISTINCT decision
# (lens), so a buyer who buys two of them gets two genuinely different reads, not the same text.
# The flagships (buyer_001/seller_001/agent_001) take no lens - they are the full dossier.
DOSSIER_LENS = {
    "buyer_004": "survey",        "buyer_005": "conveyancing",
    "buyer_006": "risk",          "buyer_007": "insurance",
    "seller_004": "conveyancing", "seller_005": "risk",
    "agent_007": "risk",
}


def _norm_profile(profile):
    """investor reuses the buyer catalogue (with an investor frame on delivery); seller==vendor."""
    p = (profile or "buyer").strip().lower()
    if p in ("investor", "buyer"):
        return "buyer"
    if p in ("vendor", "seller"):
        return "seller"
    if p == "agent":
        return "agent"
    return "buyer"


def by_profile(profile):
    """Every product for this reader's profile, flagship first then reads, packs, bundle."""
    prof = _norm_profile(profile)
    order = {"flagship": 0, "read": 1, "pack": 2, "bundle": 3}
    return sorted([p for p in CATALOGUE if p["profile"] == prof],
                  key=lambda p: order.get(p["kind"], 9))


def get(pid):
    return BY_ID.get(pid)


def price_stars(p):
    """Standalone Stars price for a product (charm GBP -> Stars). Included products still carry a
    standalone price for the non-subscriber path."""
    return max(1, round(_charm(p["price_gbp"]) * STARS_PER_GBP))


def gbp(p):
    return f"£{_charm(p['price_gbp']):.2f}"


# ---- hybrid economics: how THIS user pays for a product --------------------------------------
def purchase_mode(uid, p):
    """Resolve how a user obtains a product, in priority order:
        'included' - a Pro subscriber, flagship/read -> free
        'credits'  - a Pro subscriber, a pack/bundle, and they have enough monthly credits
        'stars'    - everyone else: buy standalone at the charm Stars price
    Lazy-imports bot so this module stays cheap to import in tests. uid=None -> always 'stars'."""
    if uid is None:
        return "stars"
    try:
        import bot
        pro = bool(bot.subscribed(uid))
    except Exception:
        return "stars"
    if not pro:
        return "stars"
    if p.get("included"):
        return "included"
    try:
        import bot
        if bot.credit_balance(uid) >= max(1, p.get("credits", 0)):
            return "credits"
    except Exception:
        pass
    return "stars"


def card(p, uid=None):
    """A storefront card for the Mini App: price/credit/included state resolved for THIS user."""
    mode = purchase_mode(uid, p)
    return {"id": p["id"], "profile": p["profile"], "name": p["name"], "kind": p["kind"],
            "blurb": p["blurb"], "credits": p["credits"], "stars": price_stars(p), "gbp": gbp(p),
            "included": p["included"], "bundle": p["bundle"], "discount": p["discount"],
            "mode": mode, "input": p.get("input"),
            "need_named": p["producer"] in NEED_NAMED_PRODUCERS,
            "cta": ("Included with Pro" if mode == "included"
                    else f"Use {p['credits']} credit{'s' if p['credits'] != 1 else ''}" if mode == "credits"
                    else f"Get · {gbp(p)}")}


# Need-named products: named after the exact question the user is searching ("Why isn't my house
# selling?", "Is this house overpriced?"). These are the hero of the store - surfaced at the TOP,
# across all profiles, regardless of the audience toggle, so they're never buried among packs.
NEED_NAMED_PRODUCERS = {"diagnostic", "price_cut", "overpriced", "offer_check", "agent_quote"}


def featured(profile, uid=None):
    """This profile's need-named products as storefront cards - the store's hero row. Per-profile:
    an agent never sees 'Why isn't MY house selling?' - they see their own listing-framed versions."""
    prof = _norm_profile(profile)
    return [card(p, uid) for p in CATALOGUE
            if p["producer"] in NEED_NAMED_PRODUCERS and _norm_profile(p["profile"]) == prof]


def catalog_payload(profile, uid=None):
    """The Mini App storefront for this profile + user: the products with their resolved CTA, the
    Pro credit balance, and the flagship pulled out as the hero. One source of truth for the app.
    `featured` carries the need-named products, pinned to the top of the store across profiles."""
    cards = [card(p, uid) for p in by_profile(profile)]
    bal = None
    if uid is not None:
        try:
            import bot
            if bot.subscribed(uid):
                bal = bot.credit_balance(uid)
        except Exception:
            bal = None
    return {"profile": _norm_profile(profile), "credits": bal,
            "featured": featured(profile, uid), "products": cards}


# ---- delivery: each product's producer builds the real, free-data synthesis ------------------
def build(pid, context=None, d=None, s=None, profile=None):
    """Build a product's body (list of lines), or None if there is genuinely no data to deliver.
    Routes to the real producer for the product's family - the flagship + the due-diligence-family
    packs are the Dossier (due_diligence.py), profile-framed; reads are the market/area synthesis;
    decision/negotiation/timeline compose the existing engine decision modules. Honest fallbacks:
    a producer that cannot run yields a clear 'what this needs' line, never a fabricated body."""
    p = get(pid)
    if not p:
        return None
    prof = profile or p["profile"]
    producer = p["producer"]
    try:
        if producer == "dossier":
            import due_diligence
            return due_diligence.build(context, d, s, profile=prof, lens=DOSSIER_LENS.get(pid))
        if producer == "bundle":
            return _build_bundle(p, context, d, s, prof)
        if producer in ("decision", "negotiation", "timeline"):
            return _build_decision(p, context, d, s, prof)
        if producer == "market":
            return _build_market(p, context, d, s, prof)
        if producer == "profile":
            return _build_buyer_profile(p, context, d, s, prof)
        if producer == "watchlist":
            return _build_watchlist(p, context, d, s, prof)
        if producer == "diagnostic":
            return _build_why_not_selling(p, context, d, s, prof)
        if producer == "price_cut":
            return _build_should_i_cut_price(p, context, d, s, prof)
        if producer == "overpriced":
            return _build_is_it_overpriced(p, context, d, s, prof)
        if producer == "offer_check":
            return _build_offer_check(p, context, d, s, prof)
        if producer == "agent_quote":
            return _build_agent_quote_check(p, context, d, s, prof)
        if producer == "podcast":
            return _build_podcast(p, context, d, s, prof)
    except Exception:
        return None
    return None


def _build_bundle(p, context, d, s, prof):
    """A bundle = the flagship dossier + each included pack's body, concatenated under headers."""
    L = [f"<b>{p['name']}</b>", p["blurb"], ""]
    for cid in p.get("includes", []):
        cp = get(cid)
        if not cp:
            continue
        body = build(cid, context, d, s, prof)
        if body:
            L += [f"<b>- {cp['name']} -</b>"] + body + [""]
    return L if len(L) > 3 else None


def _build_decision(p, context, d, s, prof):
    """Offer/negotiation/decision/timeline: compose the real engine decision layer (scenario
    pricing, the decision verdict) with this product's framing. Degrades honestly if the modules
    or the inputs aren't present."""
    L = [f"<b>{p['name']}</b>", p["blurb"], ""]
    got = False
    try:
        import engine
        block = engine.decision_block(d or {}, prof)
        if block:
            L += (block if isinstance(block, list) else [str(block)]); got = True
    except Exception:
        pass
    try:
        import scenario
        pos = (s or {}).get("positioning") if isinstance(s, dict) else None
        mat = scenario.matrix(d or {}, pos)
        if mat:
            L += ["", "<b>If the price moved</b>"] + scenario.lines(mat, prof); got = True
    except Exception:
        pass
    if not got:
        L.append("Run a valuation on this property first - this is built from its figure, its sold "
                 "comparables and its public flags.")
    return L


def _build_market(p, context, d, s, prof):
    """Market/area read: a REAL synthesis from this valuation's own HM Land Registry sold evidence
    (count, price range, recency, type mix) plus the live positioning/momentum the engine computed
    and any cached district sentiment. Built from data we already hold for the property - it never
    falls back to an empty promise, because the sold evidence is always present on a valuation."""
    d = d or {}
    s = s or {}
    L = [f"<b>{p['name']}</b>", p["blurb"], ""]
    district = None
    try:
        import store
        district = store.district_of((s.get("address")) or d.get("address") or "")
    except Exception:
        district = None
    ev = d.get("evidence") or []
    n = d.get("n_comps") or len(ev)
    head = f"<b>{district or 'This area'} - the sold evidence right now</b>"
    L.append(head)
    if d.get("range_str"):
        L.append(f"- Comparable sold range: <b>{d['range_str']}</b>"
                 + (f"; most-likely ~{_money(d.get('central'))}" if d.get("central") else "."))
    if n:
        L.append(f"- Built on <b>{n}</b> verified HM Land Registry sold comparable(s).")
    # recency + type mix straight from the evidence rows the valuation used
    dates = [str(c.get("date") or "")[:4] for c in ev if isinstance(c, dict) and c.get("date")]
    yrs = sorted(y for y in dates if y.isdigit())
    if yrs:
        L.append(f"- Evidence spans <b>{yrs[0]}-{yrs[-1]}</b> ({len([y for y in yrs if y >= yrs[-1]])} from the latest year).")
    types = {}
    for c in ev:
        t = (c.get("type") or c.get("property_type")) if isinstance(c, dict) else None
        if t:
            types[t] = types.get(t, 0) + 1
    if types:
        L.append("- Type mix: " + ", ".join(f"{k} x{v}" for k, v in sorted(types.items(), key=lambda x: -x[1])[:4]) + ".")
    # the engine's live positioning / momentum note (days-on-market, share under offer, etc.)
    pos = d.get("positioning") or {}
    if isinstance(pos, dict) and pos.get("note"):
        L += ["", "<b>Live market temperature</b>", f"- {pos['note']}"]
    # bonus: any cached district sentiment we hold (Reddit/press synthesis), never required
    try:
        if district:
            ma = store.get_market_analysis(district)
            if ma and ma.get("lines"):
                L += ["", f"<b>What's being said about {district}</b>"] + [f"- {x}" for x in ma["lines"][:5]]
    except Exception:
        pass
    L += ["", "<i>Source: HM Land Registry Price Paid (sold comparables) + the live market-temperature "
          "signals behind your valuation. No asking prices, no estimates dressed as sales.</i>"]
    return L


def _build_buyer_profile(p, context, d, s, prof):
    """Who buys on this street - built from type mix (PPD), price tier, crime, broadband and
    council tax band. Never fabricated: only shows signals we actually hold for this address."""
    d = d or {}
    s = s or {}
    ctx = context or {}
    sec = ctx.get("sections", ctx) or {}
    L = [f"<b>{p['name']}</b>", p["blurb"], ""]
    addr = (s.get("address") or d.get("address") or "this address")
    district = None
    try:
        import store
        district = store.district_of(addr)
    except Exception:
        pass
    L.append(f"<b>{district or 'This street'} — who buys here</b>")

    # Property type mix from sold evidence — signals buyer type
    ev = d.get("evidence") or []
    types = {}
    for c in ev:
        t = (c.get("type") or c.get("property_type")) if isinstance(c, dict) else None
        if t:
            types[t] = types.get(t, 0) + 1
    if types:
        top = sorted(types.items(), key=lambda x: -x[1])
        L.append("- Property type mix: " + ", ".join(f"{k} x{v}" for k, v in top[:4]) + ".")
        dominant = (top[0][0] or "").lower()
        if "flat" in dominant or "apartment" in dominant:
            L.append("- Flat stock attracts young professionals, investors and first-time buyers.")
        elif "terraced" in dominant:
            L.append("- Terraced stock attracts families, first-time buyers and downsizers.")
        elif "detached" in dominant or "semi" in dominant:
            L.append("- Detached / semi stock attracts families and upsizers.")

    # Council tax band — wealth and size tier signal
    mat = sec.get("material") or {}
    band = mat.get("band") or mat.get("council_tax_band")
    if band:
        seg = {"A": "entry-level / budget-conscious", "B": "lower-mid", "C": "mid-range",
               "D": "middle-market", "E": "upper-middle", "F": "premium",
               "G": "high-end", "H": "luxury"}.get((band or "").upper(), "")
        L.append(f"- Council tax band {band}" + (f" — {seg} segment." if seg else "."))

    # Broadband — remote workers, tech buyers
    bb = sec.get("broadband") or sec.get("connectivity") or {}
    sp = bb.get("max_download_mbit") or bb.get("max_speed")
    if sp:
        try:
            sp_f = float(sp)
            tier = "ultrafast (attracts remote workers, tech buyers)" if sp_f >= 100 else "standard (adequate for most buyers)"
            L.append(f"- Broadband: up to {sp} Mbit/s — {tier}.")
        except Exception:
            pass

    # Crime — family and investor sensitivity
    safety = sec.get("safety") or {}
    n_crime = safety.get("count") or safety.get("total")
    if n_crime:
        tier = "low-crime" if n_crime < 20 else "moderate-crime" if n_crime < 60 else "higher-crime"
        L.append(f"- Crime: {n_crime} recorded incidents nearby ({tier} area) — weight this for family buyers and investors.")

    if len(L) <= 5:
        L.append("Run the valuation first to populate the evidence — buyer profile builds from the sold comparables and area data the engine gathers.")

    # Targeting recommendations by price tier
    central = d.get("central")
    L += ["", "<b>Who to target and how</b>"]
    if central:
        try:
            v = float(central)
            if v < 200000:
                L.append("- Price tier targets first-time buyers and investors — lead with mortgage costs and rental yield.")
            elif v < 400000:
                L.append("- Price tier targets families and upsizers — lead with space, schools and commute.")
            elif v < 700000:
                L.append("- Price tier targets middle-market professionals and families — lead with finish, garden and area quality.")
            else:
                L.append("- Price tier targets premium and discretionary buyers — lead with exclusivity, specification and privacy.")
        except Exception:
            pass
    L += ["", "<i>Source: HM Land Registry Price Paid (type mix), Ofcom (broadband), Police.uk (crime), VOA (council tax). "
          "Buyer profiling is directional, not actuarial — use viewings to confirm.</i>"]
    return L


def _money(v):
    try:
        return "£" + format(int(v), ",")
    except Exception:
        return str(v)


def _build_watchlist(p, context, d, s, prof):
    """Comparable watchlist: confirm the street being tracked and what triggers a ping. The actual
    follow is set up by the caller (bot.follow_area + the tg_funnel refresh nudge)."""
    addr = ((s or {}).get("address")) or (d or {}).get("address") or "this property"
    return [f"<b>{p['name']}</b>",
            f"You're now tracking new sold comparables around <b>{addr}</b>.",
            "We watch HM Land Registry Price Paid for the street and ping you when a fresh, "
            "comparable sale lands - so your evidence is never stale.",
            "Manage or stop anytime with /stop."]


def start_podcast_job(context, d, s):
    """Start an async podcast generation job. Returns (job_id, addr) or (None, addr).
    Called by bot.py's delivery path BEFORE catalogue.build() so the sentinel never
    reaches the HTML renderer. catalogue.build() is not called for podcast products."""
    try:
        import notebook_client as nc
        if not nc.ping():
            return None, ((s or {}).get("address") or (d or {}).get("address") or "")
        addr = ((s or {}).get("address") or (d or {}).get("address") or "this property")
        nb_id = nc.ensure_notebook(f"Honestly: {addr[:60]}", description=f"Audio briefing for {addr}")
        if not nb_id:
            return None, addr
        lines = []
        ev = (d or {}).get("evidence") or []
        if (d or {}).get("central"):
            lines.append(f"Valuation: {_money(d['central'])} (range {d.get('range_str','n/a')})")
        if (d or {}).get("n_comps") or ev:
            lines.append(f"Based on {(d or {}).get('n_comps', len(ev))} HM Land Registry sold comparables.")
        ctx = context or {}
        sec = ctx.get("sections", ctx) or {}
        flood = (sec.get("flood") or {}).get("risk_label") or ""
        if flood:
            lines.append(f"Flood risk: {flood}.")
        n_plan = (sec.get("planning") or {}).get("total") or 0
        if n_plan:
            lines.append(f"{n_plan} planning applications on record nearby.")
        if not lines:
            lines.append(f"Property address: {addr}")
        nc.add_source_text(nb_id, "\n".join(lines), title=f"Property Summary: {addr[:60]}")
        briefing = (
            f"Create a concise property buyer's briefing for {addr}. "
            "Cover the valuation, sold evidence, key risk flags (flood, ground, planning), "
            "and the top questions a buyer should ask."
        )
        job_id = nc.generate_podcast(nb_id, episode_name=f"Briefing: {addr[:45]}",
                                     briefing_suffix=briefing)
        return job_id, addr
    except Exception:
        return None, ((s or {}).get("address") or (d or {}).get("address") or "")


def _asking_of(d, s):
    """The user-supplied figure (asking / agent quote / offer received), wherever the flow carried
    it. All need-named diagnostics read their single numeric input through here."""
    for src in (s or {}, d or {}):
        for k in ("asking", "quoted", "offer", "list_price", "listing_price"):
            v = src.get(k)
            try:
                if v and float(v) > 1000:
                    return int(float(v))
            except (TypeError, ValueError):
                pass
    return None


def _build_why_not_selling(p, context, d, s, prof):
    """'Why isn't my house selling?' - a need-named diagnostic. Answers the exact question a
    stuck seller is typing at 11pm, from the property's own sold evidence: is it priced above the
    sold ceiling, is the market cold, what to do. The #1 reason a home doesn't sell is price vs the
    sold record - we measure that gap in pounds, then hand back the evidence-backed asking and the
    steps. Honest: every claim ties to a real figure; no asking price -> we say what to send us."""
    d = d or {}
    s = s or {}
    addr = (s.get("address") or d.get("address") or "your property")
    central = d.get("central")
    high = d.get("high")
    sold_med = d.get("sold_median")
    asking = _asking_of(d, s)
    L = [f"<b>{_esc(p['name'])}</b>",
         f"<b>{_esc(addr)}</b> — the honest answer from the sold record, not opinion.", ""]

    reasons = []          # (rank_severity, headline, detail) - ordered, evidence-backed
    steps = []

    # ---- Reason 1: price vs the sold-evidence ceiling (the dominant cause) --------------------
    if asking and high:
        over = asking - high
        over_c = asking - (central or high)
        if over > 0:
            pct = round(over / high * 100)
            reasons.append(("serious",
                f"You're priced above what this street actually sells for.",
                f"You're asking <b>{_money(asking)}</b>. The sold evidence supports up to "
                f"<b>{_money(high)}</b> (most-likely <b>{_money(central)}</b>). That's "
                f"<b>{_money(over)}</b> ({pct}%) above the ceiling buyers can see in the Land "
                f"Registry record. Buyers and their agents check sold prices - an asking price "
                f"above the proven ceiling reads as 'negotiate hard or skip', so viewings dry up."))
            steps.append(f"Reprice to the evidence band: <b>{_money(central)}-{_money(high)}</b>. "
                         f"A move to <b>{_money(high)}</b> brings you to the top of what the record "
                         f"defends; <b>{_money(central)}</b> is where it sells fastest.")
        else:
            reasons.append(("info",
                "Your price is not the problem - it's at or below the sold ceiling.",
                f"You're asking <b>{_money(asking)}</b>, within the sold-evidence range "
                f"(up to {_money(high)}). Price is defensible, so the cause is presentation, "
                f"marketing reach or timing - work the steps below."))
            steps.append("Hold the price - it's evidenced. Refresh the lead photo, the headline "
                         "and the portal description; re-list to reset the 'new' flag.")
    elif central:
        reasons.append(("watch",
            "Tell us your current asking price for the exact gap.",
            f"The sold evidence on this address supports a range up to <b>{_money(high)}</b> "
            f"(most-likely <b>{_money(central)}</b>). Send your current asking price and we'll "
            f"show the precise gap in pounds - the single biggest reason homes sit unsold."))
        steps.append(f"Benchmark your asking against the evidence band "
                     f"<b>{_money(central)}-{_money(high)}</b>.")

    # ---- Reason 2: the market's own proof of overpricing (stuck higher-priced listings) -------
    pos = d.get("positioning") or {}
    if isinstance(pos, dict) and pos.get("note"):
        reasons.append(("watch", "The market is already showing you the ceiling.", pos["note"]))

    # ---- Reason 3: demand / momentum direction -----------------------------------------------
    mom = ((d.get("macro") or {}).get("momentum") or {})
    if isinstance(mom, dict) and (mom.get("headline") or mom.get("note")):
        reasons.append(("info", "The wider market backdrop.",
                        mom.get("headline") or mom.get("note")))

    # ---- Reason 4: independent register cross-check ------------------------------------------
    cc = d.get("crosscheck") or {}
    if cc.get("official_median_str") and asking and cc.get("official_median"):
        if asking > cc["official_median"] * 1.1:
            reasons.append(("watch", "Even the raw register backs the gap.",
                f"HM Land Registry's own median for {cc.get('postcode','your postcode')} is "
                f"<b>{cc['official_median_str']}</b> across {cc.get('official_count','recent')} "
                f"completed sale(s) - independent confirmation your asking sits high."))

    # render the ranked reasons
    order = {"serious": 0, "watch": 1, "info": 2}
    reasons.sort(key=lambda x: order.get(x[0], 3))
    if reasons:
        L.append("<b>What the evidence says</b>")
        for sev, head, detail in reasons:
            tag = {"serious": "⚠️ ", "watch": "• ", "info": "· "}.get(sev, "• ")
            L += ["", f"{tag}<b>{head}</b>", f"   {detail}"]

    # the fix
    if steps:
        L += ["", "<b>What to do about it</b>"]
        for i, st in enumerate(steps, 1):
            L.append(f"{i}. {st}")
        L += [f"{len(steps)+1}. Re-list once repriced so the portals re-flag it as new - a stale "
              "listing is skipped on sight.",
              f"{len(steps)+2}. Lead with the strongest photo and a headline that names the best "
              "feature; most buyers decide from the first image."]

    # ---- Open Notebook: a plain-English narrative read over the assembled facts (best-effort) -
    syn = _notebook_synthesis(addr, reasons, asking, central, high)
    if syn:
        L += ["", "<b>In plain English</b>", syn]

    L += ["", "<i>Source: HM Land Registry Price Paid (sold comparables + the raw register), the "
          "live local listing market (days-on-market, asking vs sold), and Bank of England / ONS "
          "momentum. The interpretation is the product - the figure is your free valuation.</i>"]
    return L


def _build_should_i_cut_price(p, context, d, s, prof):
    """'My agent wants to cut my price — should I let them?' A need-named diagnostic for the exact
    moment a seller is pressured to drop their asking. Answers it from the sold record: is the
    agent's proposed price justified by the evidence, or are they chasing a quick commission? Maps
    straight to the voice-of-customer distrust ('a high quote wins the instruction, not the sale').
    Input: the price the agent is now pushing. No price -> we say what to send."""
    d = d or {}
    s = s or {}
    addr = (s.get("address") or d.get("address") or "your property")
    central = d.get("central")
    high = d.get("high")
    low = d.get("low")
    sold_med = d.get("sold_median")
    proposed = _asking_of(d, s)        # the price the agent is now recommending
    L = [f"<b>{_esc(p['name'])}</b>",
         f"<b>{_esc(addr)}</b> — checked against the sold record, not the agent's hunch.", ""]

    reasons, steps = [], []
    if proposed and central and high:
        if proposed < central:
            short = central - proposed
            reasons.append(("serious",
                "Push back — their price is below what the record supports.",
                f"They want <b>{_money(proposed)}</b>. The sold evidence on this address supports "
                f"<b>{_money(central)}</b> as most-likely, up to <b>{_money(high)}</b>. Their number "
                f"is <b>{_money(short)}</b> below the most-likely value. A cut that deep often means "
                f"the agent wants a fast, certain sale (and a quick commission) more than your best "
                f"price. That's their incentive, not necessarily yours."))
            steps += [
                f"Ask them, in writing, for the comparable <b>sold</b> prices (not asking prices) "
                f"behind <b>{_money(proposed)}</b>. If they can't produce them, the cut isn't evidenced.",
                f"Counter at <b>{_money(central)}</b> — the most-likely figure the record defends — "
                f"and hold for a defined period before considering any further move.",
                "If viewings are the real problem, fix the photos, headline and re-list before "
                "dropping a penny — a price cut is the most expensive lever, use it last."]
        elif proposed < high:
            reasons.append(("watch",
                "Reasonable — their price sits inside the evidence band.",
                f"They want <b>{_money(proposed)}</b>, which falls within the sold-evidence range "
                f"<b>{_money(central)}-{_money(high)}</b>. It's a defensible number, not a giveaway. "
                f"If you've had genuine marketing and few viewings, this is a fair market correction."))
            steps += [
                f"Agree only with a clear plan: re-list as 'new', refreshed lead photo and headline, "
                f"and a review date. A cut without a re-launch just signals weakness.",
                f"Hold <b>{_money(central)}</b> as your floor for negotiation — the record supports it."]
        else:
            reasons.append(("info",
                "Their proposed price is still at or above the sold ceiling.",
                f"They want <b>{_money(proposed)}</b>, at or above the top of what the sold record "
                f"defends (<b>{_money(high)}</b>). If it isn't selling, the issue is unlikely to be "
                f"a small further cut — it's reach, presentation or that you're already at the ceiling."))
            steps += [
                "Before cutting, exhaust the free levers: new photos, a sharper headline, a re-list "
                "to reset the portal 'new' flag, and a wider portal/social push.",
                f"If you do move, <b>{_money(central)}-{_money(high)}</b> is the band the evidence "
                "defends — don't undershoot it on the first cut."]
    else:
        reasons.append(("watch",
            "Tell us the price your agent is proposing.",
            f"The sold evidence on {_esc(addr)} supports a most-likely <b>{_money(central)}</b>"
            + (f" (up to <b>{_money(high)}</b>)" if high else "") + ". Send the figure your agent "
            "is pushing and we'll tell you in pounds whether it's justified — or a quick-sale grab."))

    pos = d.get("positioning") or {}
    if isinstance(pos, dict) and pos.get("note"):
        reasons.append(("info", "What the live market shows.", pos["note"]))
    cc = d.get("crosscheck") or {}
    if cc.get("official_median_str") and proposed and cc.get("official_median") and proposed < cc["official_median"]:
        reasons.append(("watch", "The raw register agrees you have room.",
            f"HM Land Registry's own median for {cc.get('postcode','your postcode')} is "
            f"<b>{cc['official_median_str']}</b> ({cc.get('official_count','recent')} sales) — "
            f"above the price you're being pushed to accept."))

    order = {"serious": 0, "watch": 1, "info": 2}
    reasons.sort(key=lambda x: order.get(x[0], 3))
    if reasons:
        L.append("<b>The verdict</b>")
        for sev, head, detail in reasons:
            tag = {"serious": "⚠️ ", "watch": "• ", "info": "· "}.get(sev, "• ")
            L += ["", f"{tag}<b>{head}</b>", f"   {detail}"]
    if steps:
        L += ["", "<b>What to do</b>"]
        for i, st in enumerate(steps, 1):
            L.append(f"{i}. {st}")

    syn = _notebook_synthesis(addr, reasons, proposed, central, high)
    if syn:
        L += ["", "<b>In plain English</b>", syn]
    L += ["", "<i>Source: HM Land Registry Price Paid (sold comparables + the raw register) and "
          "the live local listing market. The interpretation is the product — the figure is your "
          "free valuation. Not financial advice; the decision is yours.</i>"]
    return L


def _build_is_it_overpriced(p, context, d, s, prof):
    """'Is this house overpriced?' The buyer's core thought the moment they like a listing.
    Answers it from the sold record: is the asking above what the street actually sells for, by
    how much, and what to offer instead. Input: the listing's asking price. Mirror of the seller
    diagnostic, buyer-framed (the gap is the buyer's negotiating headroom)."""
    d = d or {}
    s = s or {}
    addr = (s.get("address") or d.get("address") or "this property")
    central = d.get("central"); high = d.get("high"); low = d.get("low")
    guide = d.get("guide")
    asking = _asking_of(d, s)
    L = [f"<b>{_esc(p['name'])}</b>",
         f"<b>{_esc(addr)}</b> — checked against what this street actually sells for, not the blurb.", ""]
    reasons, steps = [], []
    if asking and high and central:
        over = asking - high
        if over > 0:
            pct = round(over / high * 100)
            reasons.append(("serious", "Yes — it's priced above the sold ceiling.",
                f"They're asking <b>{_money(asking)}</b>. The sold evidence supports up to "
                f"<b>{_money(high)}</b> (most-likely <b>{_money(central)}</b>). That's "
                f"<b>{_money(over)}</b> ({pct}%) over the proven ceiling — and that gap is YOUR "
                f"negotiating headroom, in writing from the register."))
            steps += [
                f"Open at around <b>{_money(guide or central)}</b> — defensible, backed by the sold record.",
                f"Cite the comparable sold prices in your offer; an evidenced offer is far harder to "
                f"dismiss than a round-number lowball.",
                f"Your walk-away is <b>{_money(high)}</b> — above it, you're paying more than the "
                f"street has ever proven, on someone else's optimism."]
        elif asking > central:
            reasons.append(("watch", "Priced at the top of fair — room to negotiate.",
                f"At <b>{_money(asking)}</b> it sits inside the sold range "
                f"<b>{_money(central)}-{_money(high)}</b>, near the top. Not a rip-off, but there's "
                f"room to bring it toward the most-likely <b>{_money(central)}</b>."))
            steps += [f"Open near <b>{_money(guide or central)}</b> and settle by {_money(high)} at most.",
                      "Use any red flags (see the red-flag dossier) as evidenced reasons to hold lower."]
        else:
            reasons.append(("info", "Priced keenly — move fast, others will see it too.",
                f"At <b>{_money(asking)}</b> it's at or below the most-likely value "
                f"(<b>{_money(central)}</b>). This is fair-to-cheap on the sold record — well-priced "
                f"homes attract competition, so don't dawdle, but don't overbid in panic either."))
            steps += [f"A full-asking offer is defensible here; <b>{_money(high)}</b> is the most the "
                      "record justifies if you're pushed into competition.",
                      "Get your finances in order first — a clean, fast offer beats a higher messy one."]
    else:
        reasons.append(("watch", "Tell us the asking price.",
            f"The sold evidence on {_esc(addr)} supports a most-likely <b>{_money(central)}</b>"
            + (f" (up to <b>{_money(high)}</b>)" if high else "") + ". Send the listing's asking "
            "price and we'll tell you in pounds whether it's over the proven ceiling — and what to offer."))
    pos = d.get("positioning") or {}
    if isinstance(pos, dict) and pos.get("note"):
        reasons.append(("info", "The live market is on your side.", pos["note"]))
    cc = d.get("crosscheck") or {}
    if cc.get("official_median_str") and asking and cc.get("official_median") and asking > cc["official_median"] * 1.1:
        reasons.append(("watch", "The raw register backs your case.",
            f"HM Land Registry's median for {cc.get('postcode','this postcode')} is "
            f"<b>{cc['official_median_str']}</b> ({cc.get('official_count','recent')} sales) — "
            f"below the asking, independent proof you have room."))
    order = {"serious": 0, "watch": 1, "info": 2}
    reasons.sort(key=lambda x: order.get(x[0], 3))
    if reasons:
        L.append("<b>The verdict</b>")
        for sev, head, detail in reasons:
            tag = {"serious": "⚠️ ", "watch": "• ", "info": "· "}.get(sev, "• ")
            L += ["", f"{tag}<b>{head}</b>", f"   {detail}"]
    if steps:
        L += ["", "<b>What to offer</b>"]
        for i, st in enumerate(steps, 1):
            L.append(f"{i}. {st}")
    syn = _notebook_synthesis(addr, reasons, asking, central, high)
    if syn:
        L += ["", "<b>In plain English</b>", syn]
    L += ["", "<i>Source: HM Land Registry Price Paid (sold comparables + the raw register) and the "
          "live local listing market. The interpretation is the product — the figure is your free "
          "valuation. Not financial advice; the decision is yours.</i>"]
    return L


def _build_offer_check(p, context, d, s, prof):
    """'Is this offer any good — accept or hold out?' The seller's thought the moment an offer
    lands. Measures the offer against the sold record: lowball, fair, or strong, with the counter
    figure and when to hold vs accept. Input: the offer received."""
    d = d or {}; s = s or {}
    addr = (s.get("address") or d.get("address") or "your property")
    central = d.get("central"); high = d.get("high"); low = d.get("low")
    offer = _asking_of(d, s)
    L = [f"<b>{_esc(p['name'])}</b>",
         f"<b>{_esc(addr)}</b> — measured against what the street actually sells for, not gut feel.", ""]
    reasons, steps = [], []
    if offer and central and high and low:
        if offer >= high:
            reasons.append(("info", "Strong — it's at or above the top of the evidence.",
                f"<b>{_money(offer)}</b> meets or beats the sold-evidence ceiling "
                f"(<b>{_money(high)}</b>). Accepting is well-justified — only hold if you have other "
                f"live interest, because above this you're relying on one optimistic buyer."))
            steps += ["Accept, or use a second viewer to test for a small overbid — but don't risk a "
                      "strong, proceedable buyer chasing a marginal gain.",
                      "Check the buyer's position (chain, finance, timeline) — a clean buyer at this "
                      "price beats a higher offer that may collapse."]
        elif offer >= central:
            reasons.append(("watch", "Fair — within the upper range, with a little room.",
                f"<b>{_money(offer)}</b> sits between the most-likely <b>{_money(central)}</b> and the "
                f"ceiling <b>{_money(high)}</b>. A defensible offer; you can push toward "
                f"<b>{_money(high)}</b> if there's interest, but this is acceptable."))
            steps += [f"Counter once at <b>{_money(high)}</b> and meet in the middle — most buyers "
                      "expect one round.", "If viewings have dried up, lean toward accepting."]
        elif offer >= low:
            short = central - offer
            reasons.append(("watch", "Below the mark — there's room to push.",
                f"<b>{_money(offer)}</b> is <b>{_money(short)}</b> under the most-likely "
                f"<b>{_money(central)}</b> (range from {_money(low)}). Not insulting, but don't take "
                f"the first number — the record supports more."))
            steps += [f"Counter at <b>{_money(central)}</b>, citing the comparable sold prices.",
                      "Hold firm for a defined window before considering a further move."]
        else:
            short = central - offer
            reasons.append(("serious", "Lowball — below what the record supports.",
                f"<b>{_money(offer)}</b> is <b>{_money(short)}</b> below the most-likely "
                f"<b>{_money(central)}</b> and under the bottom of the range (<b>{_money(low)}</b>). "
                f"This is a chancer's opening, not a fair offer."))
            steps += [f"Counter firmly at <b>{_money(central)}</b> with the sold evidence attached — "
                      "an evidenced counter is hard to argue with.",
                      "Don't be rushed by 'take it or leave it'; the record is on your side."]
    else:
        reasons.append(("watch", "Tell us the offer.",
            f"The sold evidence on {_esc(addr)} supports a most-likely <b>{_money(central)}</b>"
            + (f" (range {_money(low)}-{_money(high)})" if low and high else "") + ". Enter the offer "
            "you've received and we'll tell you in pounds whether to accept, counter, or walk."))
    syn = _notebook_synthesis(addr, reasons, offer, central, high)
    if syn:
        L += []  # synthesis appended after the verdict/steps below
    order = {"serious": 0, "watch": 1, "info": 2}
    reasons.sort(key=lambda x: order.get(x[0], 3))
    if reasons:
        L.append("<b>The verdict</b>")
        for sev, head, detail in reasons:
            tag = {"serious": "⚠️ ", "watch": "• ", "info": "· "}.get(sev, "• ")
            L += ["", f"{tag}<b>{head}</b>", f"   {detail}"]
    if steps:
        L += ["", "<b>What to do</b>"]
        for i, st in enumerate(steps, 1):
            L.append(f"{i}. {st}")
    if syn:
        L += ["", "<b>In plain English</b>", syn]
    L += ["", "<i>Source: HM Land Registry Price Paid (sold comparables + the raw register) and the "
          "live local listing market. The interpretation is the product — the figure is your free "
          "valuation. Not financial advice; the decision is yours.</i>"]
    return L


def _build_agent_quote_check(p, context, d, s, prof):
    """'An agent valued my house at £X — is it realistic?' The choosing-an-agent moment. Tests the
    quote against the sold record: realistic, conservative, or 'buying the instruction'. Maps to the
    voice-of-customer distrust (two agents £50k apart; a high quote wins the listing, not the sale).
    Input: the price the agent quoted."""
    d = d or {}; s = s or {}
    addr = (s.get("address") or d.get("address") or "your property")
    central = d.get("central"); high = d.get("high")
    quote = _asking_of(d, s)
    L = [f"<b>{_esc(p['name'])}</b>",
         f"<b>{_esc(addr)}</b> — checked against the sold record, so a high pitch can't quietly cost months.", ""]
    reasons, steps = [], []
    if quote and central and high:
        if quote > high * 1.05:
            over = quote - high
            reasons.append(("serious", "Caution — this looks like buying your instruction.",
                f"They valued it at <b>{_money(quote)}</b>, <b>{_money(over)}</b> above the top of the "
                f"sold evidence (<b>{_money(high)}</b>). A high valuation wins the listing — but homes "
                f"priced above the ceiling sit, go stale, then reduce. The agent gets the board up; you "
                f"carry the months and the eventual cut."))
            steps += [f"Ask them, in writing, for the comparable <b>sold</b> prices (not asking prices) "
                      f"that justify <b>{_money(quote)}</b>. If they can't, it's a pitch, not a valuation.",
                      f"Price to sell, not to flatter: <b>{_money(central)}-{_money(high)}</b> is what the "
                      "record defends.",
                      "Judge agents on evidence and marketing plan, not who flatters you most."]
        elif quote >= central:
            reasons.append(("info", "Realistic — it's within the sold-evidence band.",
                f"<b>{_money(quote)}</b> sits inside the range the record supports "
                f"(<b>{_money(central)}-{_money(high)}</b>). A defensible, honest valuation — a good sign."))
            steps += ["Compare agents on fee, marketing reach and tie-in length now the price is sound.",
                      f"Hold <b>{_money(central)}</b> as your floor in any negotiation."]
        else:
            short = central - quote
            reasons.append(("watch", "Conservative — below the most-likely value.",
                f"<b>{_money(quote)}</b> is <b>{_money(short)}</b> under the most-likely "
                f"<b>{_money(central)}</b>. Either they want a quick, certain sale, or they see something "
                f"specific. Ask which — the record supports more."))
            steps += [f"Ask why they're below <b>{_money(central)}</b> — get the reason in writing.",
                      "A low list can spark competition, but make sure it's a strategy, not just speed."]
    else:
        reasons.append(("watch", "Tell us the agent's figure.",
            f"The sold evidence on {_esc(addr)} supports a most-likely <b>{_money(central)}</b>"
            + (f" (up to <b>{_money(high)}</b>)" if high else "") + ". Enter the price the agent quoted "
            "and we'll tell you in pounds whether it's realistic — or a pitch to win your instruction."))
    order = {"serious": 0, "watch": 1, "info": 2}
    reasons.sort(key=lambda x: order.get(x[0], 3))
    if reasons:
        L.append("<b>The verdict</b>")
        for sev, head, detail in reasons:
            tag = {"serious": "⚠️ ", "watch": "• ", "info": "· "}.get(sev, "• ")
            L += ["", f"{tag}<b>{head}</b>", f"   {detail}"]
    if steps:
        L += ["", "<b>What to do</b>"]
        for i, st in enumerate(steps, 1):
            L.append(f"{i}. {st}")
    syn = _notebook_synthesis(addr, reasons, quote, central, high)
    if syn:
        L += ["", "<b>In plain English</b>", syn]
    L += ["", "<i>Source: HM Land Registry Price Paid (sold comparables + the raw register) and the "
          "live local listing market. The interpretation is the product — the figure is your free "
          "valuation. Not financial advice; the decision is yours.</i>"]
    return L


def _notebook_synthesis(addr, reasons, asking, central, high):
    """Use Open Notebook (a transformation over the assembled facts) to write a short, plain-English
    narrative read. Best-effort: returns None if the service is down or slow - the structured
    diagnosis above stands on its own, so a missing synthesis never weakens the product."""
    try:
        import notebook_client as nc
        if not nc.ping():
            return None
        facts = [f"Property: {addr}."]
        if asking:
            facts.append(f"Current asking price: £{asking:,}.")
        if central:
            facts.append(f"Sold-evidence most-likely value: £{int(central):,}.")
        if high:
            facts.append(f"Sold-evidence ceiling: £{int(high):,}.")
        for _sev, head, detail in reasons:
            import re as _re
            facts.append(f"{head} {_re.sub('<[^>]+>', '', detail)}")
        text = "\n".join(facts)
        out = nc.transform_text(text, transformation_name="Key Insights")
        if out and isinstance(out, str) and len(out.strip()) > 40:
            # Keep it punchy: the top few insight lines, not the full dump.
            lines = [ln.strip() for ln in out.strip().splitlines() if ln.strip()]
            kept = lines[:5] if len(lines) > 5 else lines
            return "<br>".join(_esc(ln) for ln in kept)
    except Exception:
        pass
    return None


def _esc(x):
    return (str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if x is not None else "")


def _build_podcast(p, context, d, s, prof):
    """Returns a rendered product page for podcast products. The audio job is started
    separately by bot.py (via start_podcast_job) before this is ever called — this
    function is only hit by non-bot paths (e.g. server.py HTML preview) and returns
    a safe 'being generated' confirmation rather than a raw sentinel."""
    addr = ((s or {}).get("address") or (d or {}).get("address") or "this property")
    return [
        f"<b>{p['name']}</b>", p["blurb"], "",
        f"Your audio briefing for <b>{addr}</b> is being generated.",
        "We'll send the audio file directly to your Telegram chat within a few minutes.",
        "No action needed — just wait for the message.",
        "",
        "<i>Powered by Open Notebook · solo narrator · en-GB</i>",
    ]


def selftest():
    assert len(CATALOGUE) == 39, f"expected 39 products, got {len(CATALOGUE)}"
    assert len(BY_ID) == 39, "duplicate product ids"
    _expected = {"buyer": 12, "seller": 15, "agent": 12}   # need-named diagnostics added per profile
    for prof in ("buyer", "seller", "agent"):
        ps = by_profile(prof)
        assert len(ps) == _expected[prof], f"{prof} should have {_expected[prof]} products, got {len(ps)}"
        assert sum(1 for x in ps if x["kind"] == "flagship") == 1
        assert ps[0]["kind"] == "flagship", "flagship sorts first"
    for p in CATALOGUE:
        assert (p["credits"] == 0) == p["included"], f"{p['id']}: credits/included mismatch"
        assert p["price_gbp"] == 0 or abs((_charm(p["price_gbp"]) * 100) % 100 - 99) < 1e-6, \
            f"{p['id']} not charm-priced"
    assert price_stars(get("buyer_002")) == 299
    assert price_stars(get("buyer_004")) == 179
    assert price_stars(get("buyer_010")) == 1199
    assert by_profile("investor")[0]["id"] == "buyer_001"
    assert by_profile("vendor")[0]["id"] == "seller_001"
    assert purchase_mode(None, get("buyer_001")) == "stars"
    body = build("buyer_001", {"sections": {"planning": {"total": 2}}}, {}, {}, "buyer")
    assert body and any("Force these" in x for x in body)
    w = build("buyer_009", {}, {"address": "1 Test St"}, {"address": "1 Test St"}, "buyer")
    assert any("tracking new sold" in x.lower() for x in w)
    cp = catalog_payload("buyer", uid=None)
    assert cp["profile"] == "buyer" and len(cp["products"]) == 12
    assert cp["products"][0]["cta"].startswith("Get") or cp["products"][0]["included"]
    return "ok"


if __name__ == "__main__":
    print(selftest())
