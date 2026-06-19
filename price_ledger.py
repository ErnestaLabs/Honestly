#!/usr/bin/env python3
"""price_ledger.py - the Pro price-influence ledger (PRODUCT_SPEC section 4, build #71).

The glass box, made comprehensive: every factor that bears on this property's price, each
with its SOURCE and its DIRECTION OF EFFECT. This is the heart of the Pro promise - "factors
in everything that can influence the price" - and it is built to be ruthlessly honest about
ONE thing above all: which factors actually moved the assessed figure and which sit beside it.

Only three things move low/high/central/guide, and the ledger says so plainly:
  1. the SOLD-EVIDENCE ANCHOR (HMLR comparables + the condition-adjusted AVM build-up) - the
     figure itself;
  2. the CONDITION / finish lever - the one input that legitimately moves the figure, applied
     inside the AVM build-up;
  3. the capped, fully-disclosed LIVE-MARKET STEER - bounded to +6% in a rising market / -5%
     in a softening one (engine.apply_market), the only area signal that is actually in the
     number.

Everything else - EPC, solar, lease, rebuild, flood, subsidence, air quality, crime, planning,
connectivity, amenities, schools, demand, live positioning, macro - is shown with the direction
it pushes value, but it is context BESIDE the figure: it did NOT move low/high/central/guide.
That distinction is the honesty contract (PRODUCT_SPEC section 6, rule 1). The ledger READS what
is already in engine.summary() and area_context.gather(); it assembles, it never computes a new
figure, and a factor with no data is simply absent (its honest "not available"), never faked.

  build(d, context=None) -> structured ledger dict
  lines(ledger, audience=None) -> ready markdown for any text surface

d       = the engine.summary() dict (the single source of truth for the figure + enrichment).
context = the area_context.gather() result (optional) - its `sections` carry the free-spine
          area factors (connectivity, amenities, safety, environment, planning, material).
"""
from appraise import money

# direction vocabulary - the honest read of how a factor bears on value.
#   anchor  : this IS the figure basis (sold evidence + condition-adjusted AVM)
#   up      : supports a premium / pushes value up
#   down    : a drag / pushes value down
#   neutral : measured, no clear polarity either way
#   context : informational - real and sourced, but no claimed price polarity
_WORD = {"anchor": "sets the figure", "up": "supports value", "down": "a drag on value",
         "neutral": "neutral", "context": "context"}
_ARROW = {"anchor": "=", "up": "+", "down": "-", "neutral": "=", "context": "."}


def _f(key, factor, source, value, direction, moves_figure, note):
    return {"key": key, "factor": factor, "source": source, "value": value,
            "direction": direction, "moves_figure": moves_figure, "note": note}


# ---- small, conservative polarity readers - return a direction only where the value is
#      unambiguous; otherwise "context" or "neutral". They never invent a value.
def _epc_dir(rating):
    if not rating:
        return None
    r = str(rating).strip().upper()[:1]
    if r in ("A", "B", "C"):
        return "up"
    if r in ("E", "F", "G"):
        return "down"
    if r == "D":
        return "neutral"
    return None


def _lease_dir(term):
    """Short leasehold is a real drag; a long lease or freehold is not. Parse defensively;
    return None when the term cannot be read, so nothing is asserted on a guess."""
    if term is None:
        return None
    s = str(term).strip().lower()
    if "freehold" in s:
        return "neutral"
    yrs = None
    num = "".join(ch if ch.isdigit() else " " for ch in s).split()
    if num:
        try:
            yrs = int(num[0])
        except ValueError:
            yrs = None
    if yrs is None:
        return None
    if yrs < 80:
        return "down"
    if yrs < 125:
        return "neutral"
    return "neutral"


def _flood_dir(text):
    if not text:
        return None
    s = str(text).strip().lower()
    if any(w in s for w in ("high", "significant", "warning", "alert", "severe")):
        return "down"
    if any(w in s for w in ("very low", "low", "no risk", "none", "minimal")):
        return "neutral"
    return "context"


def _aqi_dir(band):
    if not band:
        return None
    s = str(band).strip().lower()
    if any(w in s for w in ("high", "very high")):
        return "down"
    if "low" in s:
        return "neutral"
    return "context"


def _truthy_risk(v):
    """A risk flag (subsidence, pollution, crime band) - down when it signals a present risk,
    neutral when it signals none, None when it cannot be read. Negation is checked FIRST so a
    phrase like 'no risk recorded' is read as reassurance, not as the word 'risk'."""
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("", "false", "0"):
        return "neutral"
    if any(w in s for w in ("none", "no risk", "no record", "not ", "no ", "low", "very low",
                            "minimal", "nil", "clear", "negligible")):
        return "neutral"
    if any(w in s for w in ("high", "medium", "moderate", "present", "yes", "true", "risk")):
        return "down"
    return "context"


def _solar_dir(v):
    if not v:
        return None
    s = str(v).strip().lower()
    if any(w in s for w in ("high", "excellent", "good", "medium")):
        return "up"
    if "low" in s:
        return "context"
    return "context"


def build(d, context=None):
    """Assemble the full price-influence ledger from the summary + area context. Returns
    {ok, tier, factors, movers, context_factors, counts, basis}. Best-effort: never raises."""
    if not isinstance(d, dict):
        return {"ok": False, "reason": "no summary"}
    if not all(isinstance(d.get(k), (int, float)) for k in ("low", "high", "central", "guide")):
        return {"ok": False, "reason": "figure incomplete"}

    sec = ((context or {}).get("sections") or {}) if isinstance(context, dict) else {}
    st = d.get("street_enrichment") or {}
    ch = d.get("chimnie_enrichment") or {}
    factors = []

    # ===================== THE THREE MOVERS (actually in the figure) =====================
    # 1. Sold-evidence anchor + condition model - the figure itself.
    anchor_val = (d.get("sold_anchor_str") or d.get("sold_median_str")
                  or money(d["central"]))
    factors.append(_f(
        "anchor", "Sold-evidence anchor + condition model",
        "HM Land Registry Price Paid Data + HMLR UK HPI where subject history is used, "
        "cross-checked against nearby sold rows",
        anchor_val, "anchor", True,
        "The figure is built on what comparable homes actually sold for, with condition applied "
        "inside our transparent model. This is the value; "
        "everything below is read against it."))

    # 2. Condition / finish - the one lever that legitimately moves the figure.
    factors.append(_f(
        "condition", "Condition / finish",
        "User condition signal -> Honestly condition tier",
        (f"EPC {d['epc']}" if d.get("epc") else None), "anchor", True,
        "Condition is the one input that legitimately moves the figure - it is applied inside "
        "the valuation model, not bolted on. A better finish lifts the assessed value; a poorer "
        "one lowers it."))

    # 3. The capped, disclosed live-market steer (engine.apply_market, +6%/-5%).
    mk = d.get("market") or {}
    if mk and mk.get("pct") is not None:
        pct = mk["pct"]
        sdir = "up" if pct > 0.05 else "down" if pct < -0.05 else "neutral"
        factors.append(_f(
            "market_steer", "Live-market steer (capped, disclosed)",
            "Transparent market context (bounded +6% / -5%)",
            (f"{'+' if pct > 0 else ''}{pct}% ({mk.get('label')})" if pct else
             f"0% ({mk.get('label')})"),
            sdir, True, mk.get("note") or
            "The only live-market signal actually applied to the figure, and it is capped: at "
            "most +6% in a rising market, -5% in a softening one, fully disclosed."))

    # ===================== PROPERTY-INTRINSIC CONTEXT (beside the figure) =================
    # EPC / energy efficiency
    epc_rating = st.get("epc_rating") or ch.get("epc_rating") or d.get("epc")
    epc_pot = st.get("epc_potential")
    epc_dir = _epc_dir(epc_rating)
    if epc_rating and epc_dir:
        val = f"Current {str(epc_rating).upper()[:1]}" + (
            f", potential {str(epc_pot).upper()[:1]}" if epc_pot else "")
        factors.append(_f(
            "epc", "Energy efficiency (EPC)",
            "EPC register", val, epc_dir, False,
            "A higher EPC means lower running costs and broader buyer appeal; a poor rating is a "
            "drag and a future retrofit cost. Context beside the figure, not an input to it."))

    # Solar potential / energy (Google Solar building-level roof when present)
    sol = sec.get("solar") or {}
    solar_v = (sol.get("potential") if sol.get("ok") is not False else None) \
        or ch.get("solar_potential") or (d.get("solar") or {}).get("potential")
    solar_dir = _solar_dir(solar_v)
    if solar_v and solar_dir:
        if sol.get("potential") and sol.get("domestic_kwh_yr"):
            sval = (f"{solar_v} - a domestic array ~{sol['domestic_kwh_yr']:,} kWh/yr")
            ssrc = "Google Solar API (building-level roof)"
        else:
            sval = str(solar_v)
            ssrc = "Public roof/solar context"
        factors.append(_f(
            "solar", "Solar potential", ssrc, sval, solar_dir, False,
            "Usable roof for solar adds a route to lower energy bills and can support value. "
            "Shown beside the figure; never blended into it."))

    # Lease / tenure
    lease = st.get("lease_term") or ch.get("lease_term")
    lease_dir = _lease_dir(lease)
    if lease and lease_dir:
        factors.append(_f(
            "lease", "Lease / tenure",
            "Public tenure records", str(lease), lease_dir, False,
            "A short remaining lease is a genuine drag on value and lender appetite; a long lease "
            "or freehold is not. Material information beside the figure."))

    # Rebuild cost (insurance context - no clean price polarity)
    rebuild = ch.get("rebuild_cost")
    if rebuild:
        factors.append(_f(
            "rebuild", "Rebuild cost",
            "Rebuild-cost context",
            (money(rebuild) if isinstance(rebuild, (int, float)) else str(rebuild)),
            "context", False,
            "The insurance rebuild figure - material information for cover, not a driver of "
            "market value. Shown for completeness."))

    # Subsidence
    subs_dir = _truthy_risk(ch.get("subsidence"))
    if ch.get("subsidence") is not None and subs_dir:
        factors.append(_f(
            "subsidence", "Subsidence risk",
            "Ground-risk context", str(ch.get("subsidence")), subs_dir, False,
            "A recorded subsidence risk weighs on value and insurability; none recorded is "
            "reassurance. Context beside the figure."))

    # Listed building / conservation area (planning constraint - informational)
    if ch.get("listed_building") or ch.get("conservation_area"):
        bits = []
        if ch.get("listed_building"):
            bits.append(f"listed: {ch['listed_building']}")
        if ch.get("conservation_area"):
            bits.append("conservation area")
        factors.append(_f(
            "heritage", "Listed / conservation status",
            "Planning constraints", ", ".join(bits), "context", False,
            "Heritage status cuts both ways - desirability against tighter consent and upkeep. "
            "Shown as context, not scored into the figure."))

    # ===================== AREA CONTEXT (free spine, beside the figure) ===================
    # Flood (Environment Agency/public context)
    flood_v = st.get("flood_risk") or ch.get("flood_risk")
    env = sec.get("environment") or {}
    if not flood_v and env.get("flood"):
        fl = env["flood"]
        flood_v = fl.get("severity") or (fl.get("lines") or [None])[0]
    flood_dir = _flood_dir(flood_v)
    if flood_v and flood_dir:
        factors.append(_f(
            "flood", "Flood risk",
            "Environment Agency flood-risk context", str(flood_v), flood_dir, False,
            "Flood exposure weighs on value and insurance; a very-low classification is "
            "reassurance. Area context, never a price input."))

    # Air quality
    aq = env.get("air") or {}
    aq_band = aq.get("band")
    aq_dir = _aqi_dir(aq_band)
    if aq_band and aq_dir:
        aqv = (f"AQI {round(aq['aqi'])} {aq_band}".strip() if aq.get("aqi") is not None
               else str(aq_band))
        factors.append(_f(
            "air_quality", "Air quality",
            "CAMS / DEFRA air quality", aqv, aq_dir, False,
            "Persistently poor air quality can weigh on desirability; clean air supports it. "
            "Area context beside the figure."))

    # Crime / safety (raw counts carry no clean polarity -> context, unless a band is given)
    saf = sec.get("safety") or {}
    crime_band = ch.get("crime")
    if crime_band:
        cdir = _truthy_risk(crime_band) or "context"
        factors.append(_f(
            "crime", "Crime level",
            "Crime classification context", str(crime_band), cdir, False,
            "Local crime bears on desirability. Shown beside the figure as area context."))
    elif saf.get("total") is not None:
        factors.append(_f(
            "crime", "Recorded crime",
            "Police.uk street-level crime",
            f"{saf['total']} in {saf.get('month', 'the latest month')}",
            "context", False,
            "Street-level crime counts for the most recent published month - area context. A raw "
            "count has no baseline to call a direction, so it is shown, not scored."))

    # Planning & development nearby (direction genuinely ambiguous -> context)
    pl = sec.get("planning") or {}
    if pl.get("total") is not None:
        factors.append(_f(
            "planning", "Planning & development nearby",
            "PlanIt planning applications", f"{pl['total']} application(s) nearby",
            "context", False,
            "Nearby development can lift or weigh on value depending on what it is - shown as "
            "context, never reconciled into the figure."))

    # Connectivity / transport (proximity to transport is a recognised value support)
    loc = sec.get("location") or {}
    legs = loc.get("legs") or []
    area = sec.get("area") or {}
    transport = area.get("transport") or []
    if legs or transport:
        if legs and legs[0].get("time"):
            cv = f"{legs[0].get('label', 'Travel')}: {legs[0]['time']}"
        elif transport:
            cv = f"Nearest station {transport[0].get('name')} ~{transport[0].get('dist_m')} m"
        else:
            cv = legs[0].get("label") if legs else None
        factors.append(_f(
            "connectivity", "Connectivity / transport",
            "Google Distance Matrix / OSM Overpass", cv, "up", False,
            "Strong transport links and short travel times broadly support value. Connectivity "
            "context beside the figure, never an input to it."))

    # Amenities
    counts = area.get("counts") or {}
    if any(counts.values()):
        within = ", ".join(f"{k}: {v}" for k, v in counts.items() if v)
        factors.append(_f(
            "amenities", "Amenities",
            "OSM Overpass",
            f"Within {area.get('radius_m', 800)} m - {within}", "up", False,
            "A well-served neighbourhood supports desirability and value. Area context."))

    # Schools (direct/public education context when present)
    edu = st.get("education")
    if edu:
        if isinstance(edu, (list, tuple)) and edu:
            first = edu[0]
            ev = (first.get("name") if isinstance(first, dict) else str(first))
        elif isinstance(edu, dict):
            ev = edu.get("name") or edu.get("nearest")
        else:
            ev = str(edu)
        if ev:
            factors.append(_f(
                "schools", "Schools",
                "Ofsted / education context", str(ev), "up", False,
                "Proximity to well-rated schools is a recognised value support. Context beside "
                "the figure."))

    # ===================== MARKET CONTEXT (beside the figure) ============================
    # Local demand (when summary carries it)
    dem = d.get("demand") if isinstance(d.get("demand"), dict) else None
    if dem and dem.get("index") is not None:
        idx = dem["index"]
        ddir = "up" if idx >= 60 else "down" if idx <= 40 else "neutral"
        factors.append(_f(
            "demand", "Local demand",
            "Demand index", f"index {idx}", ddir, False,
            "Higher local demand supports achievable price and speed; weak demand the reverse. "
            "Market context beside the figure."))

    # Live positioning (stuck stock above the figure is evidence over-pricing fails)
    posn = d.get("positioning") or {}
    if posn.get("stuck"):
        factors.append(_f(
            "positioning", "Live positioning",
            "Market/listing context",
            f"{posn['stuck']} comparable home(s) priced higher stuck 90+ days",
            "down", False,
            "Comparable homes priced above this that have sat unsold are evidence that the higher "
            "asks are not achievable - a drag on the realistic ceiling, and the buyer's leverage. "
            "It informs strategy, it did not move the figure."))

    # Macro (Bank Rate + HPI momentum)
    macro = d.get("macro") or {}
    mom = macro.get("momentum") or {}
    if mom.get("headline"):
        h = str(mom["headline"]).lower()
        mdir = ("up" if any(w in h for w in ("rising", "growth", "up", "accelerat"))
                else "down" if any(w in h for w in ("falling", "fall", "soften", "down", "cooling"))
                else "neutral")
        factors.append(_f(
            "macro", "Macro (Bank Rate / HPI momentum)",
            "Bank of England + ONS", mom["headline"], mdir, False,
            "The rate and price-momentum backdrop shapes buyer affordability and sentiment. "
            "Forward context beside the figure, never an input to it."))

    # ===================== VERIFICATION (cross-checks, beside the figure) ================
    # Independent HMLR official-sold cross-check
    cc = d.get("crosscheck") or {}
    if cc.get("official_median"):
        div = cc.get("divergence_pct")
        factors.append(_f(
            "hmlr_crosscheck", "Independent HMLR cross-check",
            cc.get("source", "HM Land Registry Price Paid Data (SPARQL, OGL)"),
            (f"register median {cc.get('official_median_str')}"
             + (f", {div:+}% vs our comps" if div is not None else "")),
            "neutral", False,
            "The raw Land Registry register for the exact postcode, an independent reality-check "
            "on the comparable evidence. Shown for verification, never blended into the figure."))

    # Neighbour GBP/sqm corroboration (direct/public source when present)
    npsm = st.get("neighbour_psm_median")
    if npsm:
        factors.append(_f(
            "neighbour_psm", "Neighbour GBP/sqm corroboration",
            "Neighbour sold history",
            f"median {money(int(npsm))}/sqm across {st.get('neighbour_sale_count', 0)} sale(s)",
            "neutral", False,
            "Every neighbouring sale's GBP/sqm, harvested to corroborate the rate behind the "
            "figure. Verification beside the figure."))

    # Data-spine cross-check (verification.py): how the providers agree on the same attributes
    ver = d.get("verification") or {}
    if ver.get("ok") and ver.get("rows"):
        dv, co = ver.get("divergences", 0), ver.get("corroborated", 0)
        bits = []
        if co:
            bits.append(f"{co} corroborated")
        if dv:
            bits.append(f"{dv} diverge")
        factors.append(_f(
            "spine_verification", "Data-spine cross-check",
            "Public/direct attribute agreement",
            ", ".join(bits) or f"{len(ver['rows'])} attribute(s) checked", "neutral", False,
            "Where the providers describe the same attribute - EPC band, council-tax charge, flood "
            "risk - they are cross-checked and any divergence is shown with each source's value. "
            "Verification beside the figure; it never moves the number."))

    movers = [f for f in factors if f["moves_figure"]]
    context_factors = [f for f in factors if not f["moves_figure"]]
    counts = {"up": 0, "down": 0, "neutral": 0, "context": 0, "anchor": 0}
    for f in factors:
        counts[f["direction"]] = counts.get(f["direction"], 0) + 1

    return {
        "ok": True, "tier": "pro",
        "factors": factors,
        "movers": movers,
        "context_factors": context_factors,
        "counts": counts,
        "basis": (
            "Every factor that bears on this property's price, each with its source and the "
            "direction it pushes value. Only the anchor, the condition lever and the capped "
            "(+6% / -5%) live-market steer actually moved low/high/central/guide - the engine's "
            "honest mechanism. Every other factor is real, sourced and shown beside the figure; "
            "none of it was blended into the number. Factors with no data are simply absent."),
    }


def lines(ledger, audience=None):
    """Compact markdown for a text surface. Reads ONLY from the ledger dict."""
    if not ledger or not ledger.get("ok"):
        return []
    L = ["<b>Price-influence ledger</b>",
         "<i>What moved the figure - and what sits beside it.</i>", ""]
    L.append("<b>Moved the figure</b>")
    for f in ledger["movers"]:
        val = f" - {f['value']}" if f.get("value") else ""
        L.append(f"[{_ARROW[f['direction']]}] {f['factor']}{val}  ({f['source']})")
    L.append("")
    L.append("<b>Beside the figure (context, not blended in)</b>")
    for f in ledger["context_factors"]:
        val = f" - {f['value']}" if f.get("value") else ""
        L.append(f"[{_ARROW[f['direction']]}] {f['factor']}{val}: {_WORD[f['direction']]}  "
                 f"({f['source']})")
    L.append("")
    L.append(f"<i>{ledger['basis']}</i>")
    return L


if __name__ == "__main__":
    # smoke render against a synthetic Pro summary - no network, no spend
    demo = {
        "low": 590000, "high": 650000, "central": 620000, "guide": 600000,
        "sold_anchor_str": "£610,000", "sold_median_str": "£605,000", "epc": "C",
        "market": {"pct": 3.0, "label": "Rising market",
                   "note": "Live stock is moving fast - a disclosed +3% steer, within the cap."},
        "positioning": {"stuck": 2, "listings": 5, "median_ask": 640000},
        "macro": {"momentum": {"headline": "Bank Rate held at 4.0%; prices rising modestly."}},
        "crosscheck": {"official_median": 608000, "official_median_str": "£608,000",
                       "divergence_pct": -0.5,
                       "source": "HM Land Registry Price Paid Data (SPARQL, OGL)"},
        "street_enrichment": {"epc_rating": "C", "epc_potential": "B", "lease_term": "Freehold",
                              "flood_risk": "Very Low", "neighbour_psm_median": 6700,
                              "neighbour_sale_count": 9},
        "chimnie_enrichment": {"avm_estimate": 615000, "avm_confidence": 0.86, "anchored": False,
                               "solar_potential": "Medium", "subsidence": "No risk recorded",
                               "rebuild_cost": 410000},
    }
    ctx = {"sections": {
        "environment": {"flood": {"severity": "Very Low"},
                        "air": {"band": "Low", "aqi": 2}},
        "safety": {"total": 41, "month": "2026-04"},
        "planning": {"total": 7},
        "area": {"counts": {"shop": 12, "school": 4}, "radius_m": 800,
                 "transport": [{"name": "Peckham Rye", "dist_m": 300}]},
        "location": {"legs": [{"label": "City of London", "time": "24 min"}]},
    }}
    led = build(demo, context=ctx)
    print(f"factors: {len(led['factors'])}  movers: {len(led['movers'])}  "
          f"counts: {led['counts']}")
    print("\n".join(lines(led)))
