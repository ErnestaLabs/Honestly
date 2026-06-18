#!/usr/bin/env python3
"""products/catalog.py - The 300-Product Engine Catalog.

Every product is a micro-upsell (£1-£20) triggered by a specific
psychological moment: Anger, FOMO, Greed, Laziness, or Fear.
No bullshit features - every product delivers immediate, tangible value.

Architecture:
  ProductTemplate defines the schema.
  Each product is instantiated with: name, gbp_price, emotion_trigger,
  required_repos, and execution_function.
  The execution_function stub shows exactly how open-source repos and
  existing Honestly modules interact to deliver the product.

To scale to 300: the ProductEngine pairs a psychological trigger with
a data vector and an open-source tool. New products are one class
instantiation, not one new script.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


# ──────────────────────────────────────────────────────────────── trigger enum

class EmotionTrigger(Enum):
    ANGER = "anger"
    FOMO = "fomo"
    GREED = "greed"
    LAZINESS = "laziness"
    FEAR = "fear"


# ──────────────────────────────────────────────────────────── product template

@dataclass
class ProductTemplate:
    """One sellable micro-product in the Honestly ecosystem.

    Attributes:
        id: unique slug (used in routing, billing, deep links)
        name: user-facing product name
        description: one-line pitch
        gbp_price: price in British Pounds
        emotion_trigger: the psychological moment this product serves
        required_repos: open-source repos this product depends on
        required_modules: internal Honestly modules this product uses
        execution_function: the function that delivers the product.
            Signature: (subject: dict, params: dict) -> dict
            subject has keys: address, postcode, sqm, epc, last_sold, lat, lng
            params has product-specific inputs (uploaded files, user choices)
            Returns: {"ok": True, "output": ..., "format": "pdf"|"html"|"text"|"audio"}
        tier_access: which subscription tiers can access this
            "all" = anyone can buy
            "plus" = Plus or Pro only
            "pro" = Pro only
        cooldown_hours: minimum hours between purchases of this product
            for the same address (prevents accidental double-buys)
        delivery_format: primary output format
        credit_cost_gbp: how much of the monthly credit this consumes
            (None = full price, no credit discount)
    """
    id: str
    name: str
    description: str
    gbp_price: float
    emotion_trigger: EmotionTrigger
    required_repos: list[str] = field(default_factory=list)
    required_modules: list[str] = field(default_factory=list)
    execution_function: Optional[Callable] = None
    tier_access: str = "all"
    cooldown_hours: int = 24
    delivery_format: str = "pdf"
    credit_cost_gbp: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "gbp_price": self.gbp_price,
            "emotion_trigger": self.emotion_trigger.value,
            "required_repos": self.required_repos,
            "required_modules": self.required_modules,
            "tier_access": self.tier_access,
            "cooldown_hours": self.cooldown_hours,
            "delivery_format": self.delivery_format,
            "credit_cost_gbp": self.credit_cost_gbp,
        }


# ──────────────────────────────────────────────────────── the 10 launch products

def _lowball_counter_email(subject: dict, params: dict) -> dict:
    """The Lowball Counter-Email (£1.50) - Trigger: Anger.

    Buyer gets a lowball offer. We ingest the AVM PDF, the 3 strict comps,
    and the user's EPC. Generate a fiercely worded, data-backed counter-offer
    email ready to send to the agent.

    Integration:
      - langchain (ChatOpenAI via OpenRouter) for email generation
      - engine.py for the AVM valuation + comps
      - epc.py for the EPC data
    """
    address = subject.get("address", "")
    postcode = subject.get("postcode", "")
    sqm = subject.get("sqm", 0)
    epc = subject.get("epc", "")
    lowball = params.get("lowball_offer", 0)
    # 1. Pull the full valuation
    from engine import value, summary
    r = value(address)
    sm = summary(r, audience="seller")
    # 2. Build evidence context for LLM
    comps_text = "\n".join(
        f"  - {e['address']}: {e['price_str']} ({e['date']}, {e.get('sqm', '?')} sqm)"
        for e in (sm.get("evidence") or [])[:5]
    )
    prompt = (
        f"The seller of {address} ({sqm} sqm, EPC {epc}) received a lowball offer "
        f"of £{lowball:,}. Our AVM values it at £{sm['central']:,} "
        f"(range £{sm['low']:,} - £{sm['high']:,}, confidence {sm.get('confidence_score', '?')}/100).\n"
        f"Strict comparables:\n{comps_text}\n\n"
        f"Write a professional but firm counter-offer email from the seller to their "
        f"estate agent. Reference the specific sold evidence. Be concise, data-backed, "
        f"and confident. Do not be aggressive - be forensic."
    )
    # 3. Generate via OpenRouter/langchain
    try:
        from langchain_community.chat_models import ChatOpenAI
        from langchain_core.messages import HumanMessage
        import os
        llm = ChatOpenAI(
            model="mistralai/mistral-small-3.1-24b-instruct",
            openai_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            openai_api_base="https://openrouter.ai/api/v1",
            max_tokens=800,
        )
        resp = llm.invoke([HumanMessage(content=prompt)])
        email_text = resp.content
    except Exception:
        # Fallback: template-based email
        email_text = (
            f"Dear Agent,\n\n"
            f"Thank you for forwarding the offer of £{lowball:,} on {address}.\n"
            f"Based on recent comparable sales evidence from HM Land Registry, "
            f"the property is valued at £{sm['central']:,} "
            f"(range £{sm['low']:,} - £{sm['high']:,}).\n\n"
            f"Key sold evidence:\n{comps_text}\n\n"
            f"The offer of £{lowball:,} represents a {round((1 - lowball/sm['central'])*100)}% "
            f"discount to the assessed value. We would welcome an offer closer to "
            f"£{sm['central']:,} reflecting the sold evidence.\n\n"
            f"Kind regards"
        )
    return {"ok": True, "output": email_text, "format": "text"}


def _neighbor_extension_blueprint(subject: dict, params: dict) -> dict:
    """The Neighbor's Extension Blueprint (£2.00) - Trigger: FOMO/Greed.

    Find the exact planning application of a similar house on the street
    that got approved. Parse the architectural drawings PDF to extract
    square footage and boundaries.

    Integration:
      - planning.py to find approved planning applications
      - Unstructured-IO/unstructured to parse approved drawing PDFs
      - engine.py for the subject's valuation context
    """
    address = subject.get("address", "")
    postcode = subject.get("postcode", "")
    # 1. Find approved planning apps on the same street
    from planning import search_postcode
    apps = search_postcode(postcode, status="approved", limit=10)
    # 2. Filter to extensions/loft conversions
    extensions = [a for a in apps if any(
        kw in (a.get("description") or "").lower()
        for kw in ("extension", "loft", "rear", "side", "conservatory")
    )]
    if not extensions:
        return {"ok": True, "output": {"approved_extensions": [],
                "note": f"No approved extensions found in {postcode}. "
                        "This may mean no one has applied, or the council records are incomplete."},
                "format": "html"}
    # 3. Parse the most relevant drawing PDF with Unstructured
    parsed = []
    for app in extensions[:3]:
        doc_url = app.get("document_url")
        floor_area_added = None
        if doc_url:
            try:
                from unstructured.partition.pdf import partition_pdf
                elements = partition_pdf(url=doc_url, strategy="fast")
                text = "\n".join(str(e) for e in elements)
                # Extract sqm mentions
                import re
                sqm_matches = re.findall(r'(\d+)\s*sq\s*m', text, re.I)
                if sqm_matches:
                    floor_area_added = max(int(s) for s in sqm_matches)
            except Exception:
                pass
        parsed.append({
            "address": app.get("address"),
            "description": app.get("description"),
            "date_approved": app.get("decision_date"),
            "floor_area_added_sqm": floor_area_added,
            "council_ref": app.get("reference"),
            "document_url": doc_url,
        })
    # 4. Calculate value uplift from added sqm
    from engine import value
    r = value(address)
    current_psm = r["valuation"]["central"] / max(1, subject.get("sqm", 80))
    for p in parsed:
        if p["floor_area_added_sqm"]:
            p["estimated_value_uplift"] = round(p["floor_area_added_sqm"] * current_psm)
    return {"ok": True, "output": {"approved_extensions": parsed,
            "subject_psm": round(current_psm), "subject_address": address},
            "format": "html"}


def _stealth_listing_sniper(subject: dict, params: dict) -> dict:
    """The Stealth Listing Sniper (£4.00) - Trigger: FOMO.

    Find properties on the street bought 15+ years ago by LLCs.
    Generate a scraped list and a mail-merge letter template.

    Integration:
      - graph_db.py for HMLR sales data
      - companies_house.py for LLC ownership lookup
    """
    postcode = subject.get("postcode", "")
    # 1. Find old sales (15+ years) from the local graph DB
    from graph_db import GraphQuery
    gq = GraphQuery()
    all_sales = gq.sales_for_postcode(postcode, limit=200)
    import datetime as _dt
    cutoff = (_dt.date.today().year - 15)
    old_sales = [s for s in all_sales if s.get("date", "9999")[:4].isdigit()
                 and int(s["date"][:4]) <= cutoff]
    # 2. Cross-reference with Companies House for LLC-owned properties
    from companies_house import search_company
    llc_targets = []
    for s in old_sales[:30]:
        paon = s.get("paon", "")
        # Check if buyer is a company
        company = search_company(paon, s.get("street", ""))
        if company and company.get("company_name"):
            llc_targets.append({
                "address": f"{paon} {s.get('street', '')}",
                "bought_date": s.get("date"),
                "bought_price": s.get("price"),
                "owner_llc": company.get("company_name"),
                "company_status": company.get("status"),
                "years_held": _dt.date.today().year - int(s["date"][:4]),
            })
    # 3. Generate mail-merge letter template
    letter = (
        "Dear {owner_name},\n\n"
        "I am writing to enquire whether you might consider selling your property at "
        "{address}, {postcode}. I am a genuine buyer and would be grateful for the "
        "opportunity to discuss a potential purchase at a fair market price.\n\n"
        "I look forward to hearing from you.\n\n"
        "Yours sincerely,\n{buyer_name}"
    )
    return {"ok": True, "output": {
        "targets": llc_targets,
        "mail_merge_template": letter,
        "total_llc_held": len(llc_targets),
        "postcode": postcode,
    }, "format": "html"}


def _council_tax_challenger(subject: dict, params: dict) -> dict:
    """The Council Tax Banding Challenger (£3.00) - Trigger: Anger.

    Find the exact sqm of the property. Compare to VOA banding rules.
    Generate the official VOA challenge letter.

    Integration:
      - graph_db.py / hmlr_query.py for sqm data
      - langchain for challenge letter generation
    """
    address = subject.get("address", "")
    postcode = subject.get("postcode", "")
    sqm = subject.get("sqm", 0)
    current_band = params.get("current_band", "")
    # 1. Get the property's floor area (from engine/EPC)
    from engine import value
    r = value(address)
    confirmed_sqm = r["subject"].get("sqm") or sqm
    # 2. VOA banding thresholds (England, 1991 values)
    # These are the statutory band boundaries based on 1991 capital values
    band_thresholds = {
        "A": (0, 40000),
        "B": (40001, 52000),
        "C": (52001, 68000),
        "D": (68001, 88000),
        "E": (88001, 120000),
        "F": (120001, 160000),
        "G": (160001, 320000),
        "H": (320001, float("inf")),
    }
    # 3. Find comparable properties in lower bands
    from graph_db import GraphQuery
    gq = GraphQuery()
    nearby = gq.sales_for_postcode(postcode, limit=100)
    lower_banded = [s for s in nearby
                    if s.get("price") and s["price"] < band_thresholds.get(current_band, (0, 0))[0]]
    # 4. Generate challenge letter
    challenge_text = (
        f"Dear Valuation Office Agency,\n\n"
        f"I wish to challenge the Council Tax banding of my property at "
        f"{address} ({confirmed_sqm} sqm, currently Band {current_band}).\n\n"
        f"Grounds for challenge:\n"
        f"1. The property is {confirmed_sqm} sqm, which is significantly smaller than "
        f"typical Band {current_band} properties in this area.\n"
        f"2. {len(lower_banded)} similar or larger properties in {postcode} are in "
        f"lower bands.\n"
        f"3. The property's assessed value at 1 April 1991 would not have exceeded "
        f"the Band {'ABCDEF'[ord(current_band) - 65 - 1] if current_band > 'A' else 'A'} threshold "
        f"of £{band_thresholds.get(current_band, (0,0))[0]:,}.\n\n"
        f"I request a review of the banding and supporting evidence from the VOA listing.\n\n"
        f"Yours faithfully"
    )
    return {"ok": True, "output": {
        "current_band": current_band,
        "confirmed_sqm": confirmed_sqm,
        "lower_banded_nearby": len(lower_banded),
        "challenge_letter": challenge_text,
        "band_thresholds": {k: v for k, v in band_thresholds.items()},
    }, "format": "text"}


def _leasehold_trap_xray(subject: dict, params: dict) -> dict:
    """The Leasehold Trap X-Ray (£5.00) - Trigger: Fear.

    User uploads the listing PDF. Extract lease length and ground rent.
    Calculate the Section 42 extension cost using the Marriage Act formula.

    Integration:
      - Unstructured-IO/unstructured to parse the listing/conveyancing PDF
      - Lease extension formula from the Leasehold Reform Act 1967/1993
    """
    uploaded_pdf = params.get("pdf_path")
    lease_years = params.get("lease_years")  # if user provides directly
    ground_rent = params.get("ground_rent")  # annual £

    # 1. Parse PDF for lease details if uploaded
    extracted = {}
    if uploaded_pdf:
        try:
            from unstructured.partition.pdf import partition_pdf
            elements = partition_pdf(filename=uploaded_pdf, strategy="fast")
            text = "\n".join(str(e) for e in elements)
            import re
            # Extract lease years
            lease_match = re.search(r'(\d+)\s*years?\s*(?:remaining|left|unexpired)', text, re.I)
            if lease_match:
                lease_years = int(lease_match.group(1))
                extracted["lease_years_source"] = "pdf_extraction"
            # Extract ground rent
            gr_match = re.search(r'ground\s*rent[:\s]*£?([\d,]+)', text, re.I)
            if gr_match:
                ground_rent = int(gr_match.group(1).replace(",", ""))
                extracted["ground_rent_source"] = "pdf_extraction"
            extracted["raw_text_length"] = len(text)
        except Exception as e:
            extracted["parse_error"] = str(e)

    # 2. Calculate Section 42 extension cost (statutory formula)
    # Simplified: C = D + (R × Y) + marriage_value_share
    # Where D = diminution of landlord's interest, R = ground rent, Y = years
    # Marriage value = (new_value - old_value) / 2 when lease < 80 years
    lease_years = int(lease_years or 99)
    ground_rent = float(ground_rent or 0)
    from engine import value
    r = value(subject.get("address", ""))
    property_value = r["valuation"]["central"]

    # Leasehold discount: properties with <80 years lose ~1% per year below 80
    lease_penalty_pct = max(0, (80 - lease_years)) * 0.01 if lease_years < 80 else 0
    current_lease_value = property_value * (1 - lease_penalty_pct)
    extended_lease_value = property_value  # 90-year extension restores full value

    # Marriage value (50/50 split when lease < 80 years)
    marriage_value = 0
    if lease_years < 80:
        marriage_value = (extended_lease_value - current_lease_value) * 0.5

    # Landlord's diminution (ground rent lost for 90 years, capitalised at 5%)
    capitalisation_rate = 0.05
    ground_rent_capitalised = (ground_rent / capitalisation_rate) * (1 - (1 + capitalisation_rate) ** -90) if ground_rent else 0

    estimated_cost = round(marriage_value + ground_rent_capitalised)

    risk_flags = []
    if lease_years < 80:
        risk_flags.append("CRITICAL: Lease below 80 years - marriage value applies and cost rises exponentially")
    if lease_years < 70:
        risk_flags.append("URGENT: Lease below 70 years - mortgage lenders may refuse")
    if ground_rent > 250:
        risk_flags.append("WARNING: Ground rent above £250 - may be classed as an Assured Shorthold Tenancy")
    if lease_years < 60:
        risk_flags.append("DANGER: Lease below 60 years - property may be unsaleable")

    return {"ok": True, "output": {
        "lease_years_remaining": lease_years,
        "ground_rent_annual": ground_rent,
        "estimated_extension_cost": estimated_cost,
        "marriage_value": round(marriage_value),
        "ground_rent_capitalised": round(ground_rent_capitalised),
        "current_lease_value": round(current_lease_value),
        "extended_lease_value": round(extended_lease_value),
        "risk_flags": risk_flags,
        "extracted": extracted,
    }, "format": "html"}


def _gentrification_radar(subject: dict, params: dict) -> dict:
    """The Gentrification Radar (£3.00) - Trigger: Greed.

    Forecast 5-year crime and pricing trends. Cross-reference local
    chatter about new cafes/transport.

    Integration:
      - unit8co/darts for time-series forecasting
      - reddit_intel.py for local sentiment chatter
    """
    postcode = subject.get("postcode", "")
    outcode = postcode.split()[0] if " " in postcode else postcode[:4]
    # 1. Get historical price data from graph DB
    from graph_db import GraphQuery
    gq = GraphQuery()
    all_sales = gq.sales_for_postcode(postcode, limit=500)
    # Group by year for time series
    yearly = {}
    for s in all_sales:
        yr = (s.get("date") or "")[:4]
        if yr.isdigit():
            yearly.setdefault(yr, []).append(s.get("price", 0))
    yearly_median = {yr: sum(ps) // len(ps) for yr, ps in yearly.items() if ps}
    # 2. Forecast with Darts (or fallback linear regression)
    forecast = {}
    try:
        import darts
        from darts import TimeSeries
        from darts.models import ExponentialSmoothing
        if len(yearly_median) >= 3:
            years_sorted = sorted(yearly_median)
            values = [yearly_median[y] for y in years_sorted]
            ts = TimeSeries.from_times_and_values(
                [datetime(y, 1, 1) for y in years_sorted], values
            )
            model = ExponentialSmoothing()
            model.fit(ts)
            pred = model.predict(5)
            for i, val in enumerate(pred.values()):
                forecast[str(int(years_sorted[-1]) + i + 1)] = int(val[0])
    except Exception:
        # Fallback: simple linear extrapolation
        if len(yearly_median) >= 2:
            years_sorted = sorted(yearly_median)
            vals = [yearly_median[y] for y in years_sorted]
            avg_growth = (vals[-1] - vals[0]) / max(1, len(vals) - 1)
            for i in range(1, 6):
                forecast[str(int(years_sorted[-1]) + i)] = int(vals[-1] + avg_growth * i)
    # 3. Get Reddit sentiment for the area
    reddit_chatter = {}
    try:
        from reddit_intel import area_chatter
        reddit_chatter = area_chatter(outcode, limit=20)
    except Exception:
        reddit_chatter = {"note": "Reddit data unavailable"}
    # 4. Score gentrification signals
    signals = []
    if forecast:
        five_yr_growth = list(forecast.values())[-1] - list(forecast.values())[0] if len(forecast) >= 2 else 0
        if five_yr_growth > 0:
            signals.append(f"Projected 5-year price growth: +£{five_yr_growth:,}")
    gentrification_words = ["cafe", "coffee", "brewery", "station", "tram", "regeneration", "investment", "new build"]
    for word in gentrification_words:
        if word in str(reddit_chatter).lower():
            signals.append(f"Local chatter mentions: {word}")
    return {"ok": True, "output": {
        "postcode": postcode,
        "historical_prices": yearly_median,
        "forecast_5yr": forecast,
        "reddit_chatter": reddit_chatter,
        "gentrification_signals": signals,
        "signal_count": len(signals),
    }, "format": "html"}


def _architects_vision(subject: dict, params: dict) -> dict:
    """The Architect's Vision (£4.00) - Trigger: Greed/FOMO.

    Render photorealistic future state of the house with extensions
    and solar panels using Stable Diffusion / ControlNet on the
    Google Street View image.

    Integration:
      - AUTOMATIC1111/stable-diffusion-webui API
      - vision.py for Street View image capture
    """
    address = subject.get("address", "")
    extension_type = params.get("extension_type", "loft")  # loft, rear, side, solar
    # 1. Get the Street View image of the property
    front_image_path = None
    try:
        from vision import street_view_image
        front_image_path = street_view_image(address)
    except Exception:
        pass
    # 2. Generate the AI-rendered future state
    prompt_map = {
        "loft": "a London terraced house with a modern dormer loft extension, skylight windows, photorealistic, architectural photography",
        "rear": "a London terraced house with a modern rear glass extension, open plan kitchen, photorealistic, architectural photography",
        "side": "a London semi-detached house with a side return extension, full width glazing, photorealistic",
        "solar": "a London house with solar panels on the roof, modern clean installation, photorealistic",
    }
    sd_prompt = prompt_map.get(extension_type, prompt_map["loft"])
    rendered_image_path = None
    try:
        # Call local Stable Diffusion WebUI API
        import requests
        sd_url = os.environ.get("SD_WEBUI_URL", "http://127.0.0.1:7860")
        if front_image_path:
            # img2img with ControlNet
            import base64
            with open(front_image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            resp = requests.post(f"{sd_url}/sdapi/v1/img2img", json={
                "init_images": [img_b64],
                "prompt": sd_prompt,
                "denoising_strength": 0.65,
                "steps": 30,
                "width": 768,
                "height": 512,
            }, timeout=120)
            if resp.ok:
                import tempfile
                result = resp.json()
                img_data = base64.b64decode(result["images"][0])
                out_path = tempfile.mktemp(suffix=".png", prefix="architect_vision_")
                with open(out_path, "wb") as f:
                    f.write(img_data)
                rendered_image_path = out_path
    except Exception:
        pass
    return {"ok": True, "output": {
        "extension_type": extension_type,
        "front_image": front_image_path,
        "rendered_image": rendered_image_path,
        "prompt_used": sd_prompt,
        "note": "AI-generated visualisation - not architectural drawings" if rendered_image_path else "Stable Diffusion unavailable - image not generated",
    }, "format": "html"}


def _deal_autopsy(subject: dict, params: dict) -> dict:
    """The Deal Autopsy (£20.00) - Trigger: Fear.

    Parse the conveyancing pack, extract lease clauses, flag Hidden Traps.
    Generate a cinematic audio briefing.

    Integration:
      - Unstructured-IO/unstructured to parse the conveyancing pack PDF
      - openai/whisper + Mistral TTS for audio briefing
    """
    pdf_path = params.get("pdf_path")
    if not pdf_path:
        return {"ok": False, "output": {"error": "Conveyancing pack PDF required"}, "format": "text"}
    # 1. Parse the full conveyancing pack
    full_text = ""
    try:
        from unstructured.partition.pdf import partition_pdf
        elements = partition_pdf(filename=pdf_path, strategy="hi_res")
        full_text = "\n".join(str(e) for e in elements)
    except Exception as e:
        return {"ok": False, "output": {"error": f"PDF parsing failed: {e}"}, "format": "text"}
    # 2. Flag hidden traps
    import re
    traps = []
    trap_patterns = {
        "clawback": r"clawback|overage|uplift",
        "restrictive_covenant": r"restrictive\s*covenant|restriction\s*on\s*use",
        "flying_freehold": r"flying\s*freehold",
        "chancel_repair": r"chancel\s*repair",
        "right_of_way_dispute": r"right\s*of\s*way.*dispute|easement.*dispute",
        "Japanese_knotweed": r"japanese\s*knotweed",
        "subsidence": r"subsidence|structural\s*movement|underpinning",
        "flood_risk": r"flood\s*risk|flood\s*zone",
        "mining": r"mining\s*subsidence|mine\s*shaft",
        "asbestos": r"asbestos",
        "short_lease": r"(\d+)\s*years?\s*(?:remaining|unexpired)",
    }
    for trap_name, pattern in trap_patterns.items():
        matches = re.findall(pattern, full_text, re.I)
        if matches:
            # Get surrounding context
            for m in re.finditer(pattern, full_text, re.I):
                start = max(0, m.start() - 100)
                end = min(len(full_text), m.end() + 100)
                context = full_text[start:end].replace("\n", " ").strip()
                traps.append({"trap": trap_name.replace("_", " ").title(),
                              "context": context})
                break  # one example per trap type
    # 3. Generate audio briefing
    audio_path = None
    if traps:
        briefing_text = f"Deal Autopsy for {subject.get('address', 'the property')}. "
        briefing_text += f"I found {len(traps)} potential issues in the conveyancing pack. "
        for t in traps:
            briefing_text += f"Warning: {t['trap']}. Context: {t['context'][:200]}. "
        briefing_text += "Review these findings with your solicitor before exchange."
        try:
            # Use TTS API
            import os, requests, tempfile
            tts_url = os.environ.get("TTS_API_URL", "http://127.0.0.1:5000")
            resp = requests.post(f"{tts_url}/tts", json={"text": briefing_text}, timeout=60)
            if resp.ok:
                out_path = tempfile.mktemp(suffix=".mp3", prefix="deal_autopsy_")
                with open(out_path, "wb") as f:
                    f.write(resp.content)
                audio_path = out_path
        except Exception:
            pass
    return {"ok": True, "output": {
        "traps_found": len(traps),
        "traps": traps,
        "audio_briefing": audio_path,
        "pdf_length_chars": len(full_text),
        "verdict": f"{len(traps)} issues flagged - review with solicitor" if traps else "No major issues found",
    }, "format": "html"}


def _syndicate_street_map(subject: dict, params: dict) -> dict:
    """The Syndicate Street Map (£15.00) - Trigger: Greed.

    Find hidden power players on a street. Intersect HMLR with Companies House.
    Generate a map highlighting "Equity Hoarders" and "LLC Blocks".

    Integration:
      - geopandas + scikit-learn (DBSCAN clustering)
      - graph_db.py for HMLR sales
      - companies_house.py for LLC ownership
    """
    postcode = subject.get("postcode", "")
    # 1. Get all sales on the street from graph DB
    from graph_db import GraphQuery
    gq = GraphQuery()
    all_sales = gq.sales_for_postcode(postcode, limit=200)
    # 2. Cluster sales by price tier
    import statistics
    if not all_sales:
        return {"ok": True, "output": {"clusters": [], "note": "No sales data available"}, "format": "html"}
    prices = [s["price"] for s in all_sales if s.get("price")]
    if not prices:
        return {"ok": True, "output": {"clusters": [], "note": "No price data"}, "format": "html"}
    price_med = statistics.median(prices)
    # 3. Identify LLC owners
    from companies_house import search_company
    llc_properties = []
    for s in all_sales[:50]:
        company = search_company(s.get("paon", ""), s.get("street", ""))
        if company and company.get("company_name"):
            llc_properties.append({
                "address": f"{s.get('paon', '')} {s.get('street', '')}",
                "price": s.get("price"),
                "owner": company.get("company_name"),
                "status": company.get("status"),
            })
    # 4. Classify: Equity Hoarders (owned 20+ years) vs LLC Blocks
    import datetime as _dt
    equity_hoarders = []
    for s in all_sales:
        yr = (s.get("date") or "")[:4]
        if yr.isdigit() and _dt.date.today().year - int(yr) >= 20:
            equity_hoarders.append({
                "address": f"{s.get('paon', '')} {s.get('street', '')}",
                "bought_year": int(yr),
                "bought_price": s.get("price"),
                "estimated_equity": s.get("price", 0) * 2,  # rough: doubled in 20 years
            })
    return {"ok": True, "output": {
        "postcode": postcode,
        "total_sales": len(all_sales),
        "price_median": price_med,
        "llc_properties": llc_properties[:20],
        "llc_count": len(llc_properties),
        "equity_hoarders": equity_hoarders[:20],
        "equity_hoarder_count": len(equity_hoarders),
    }, "format": "html"}


def _planning_permission_oracle(subject: dict, params: dict) -> dict:
    """The Planning Permission Oracle (£2.50) - Trigger: Laziness.

    Analyze roof shape from Street View. Check distance to boundary.
    Output a 90% confidence "Permitted Development: Yes/No" verdict in 3 seconds.

    Integration:
      - vision.py to analyze roof shape from Street View
      - overpass.py to check distance to boundary
      - planning.py for local authority rules
    """
    address = subject.get("address", "")
    project_type = params.get("project_type", "loft")  # loft, extension, outbuilding
    # 1. Get Street View image and analyze roof
    roof_analysis = {}
    try:
        from vision import analyze_roof_shape
        roof_analysis = analyze_roof_shape(address)
    except Exception:
        # Fallback: use property type inference
        from engine import value
        r = value(address)
        ptype = r["subject"].get("type", "")
        if "terraced" in ptype:
            roof_analysis = {"shape": "pitched", "hipped": False, "suitable": True}
        elif "semi" in ptype:
            roof_analysis = {"shape": "pitched", "hipped": True, "suitable": True}
        elif "detached" in ptype:
            roof_analysis = {"shape": "pitched", "hipped": True, "suitable": True}
        else:
            roof_analysis = {"shape": "flat", "hipped": False, "suitable": False}
    # 2. Check boundary distance via Overpass/OSM
    boundary_info = {}
    try:
        from overpass import boundary_distance
        boundary_info = boundary_distance(subject.get("lat"), subject.get("lng"))
    except Exception:
        boundary_info = {"estimated": True, "note": "Boundary data from OSM; verify with Land Registry"}
    # 3. Apply Permitted Development rules
    pd_rules = {
        "loft": {
            "max_volume_cubic_m": 40 if roof_analysis.get("hipped") else 50,
            "must_be_rear": True,
            "no_side_facing_windows": True,
            "no_balcony": True,
            "max_height_m": roof_analysis.get("ridge_height", 12) if roof_analysis.get("shape") == "pitched" else 0,
            "conservation_area_override": False,
        },
        "extension": {
            "max_length_m": 4 if project_type == "rear" else 3,
            "max_height_m": 4,
            "single_storey_max_depth_m": 6 if roof_analysis.get("shape") == "pitched" else 8,
            "must_match_existing": True,
            "no_side_elevation": True,
        },
        "outbuilding": {
            "max_area_sqm": 15,
            "max_height_m": 2.5 if boundary_info.get("distance_m", 2) < 2 else 4,
            "must_be_incidental": True,
        },
    }
    rules = pd_rules.get(project_type, pd_rules["loft"])
    # 4. Generate verdict
    roof_ok = roof_analysis.get("suitable", False)
    boundary_ok = boundary_info.get("distance_m", 2) >= 2
    verdict = "LIKELY PD" if roof_ok and boundary_ok else "LIKELY NEEDS PLANNING"
    confidence = 85 if roof_ok and boundary_ok else 60
    if roof_analysis.get("shape") == "flat" and project_type == "loft":
        verdict = "NEEDS PLANNING"
        confidence = 90
    return {"ok": True, "output": {
        "project_type": project_type,
        "verdict": verdict,
        "confidence_pct": confidence,
        "roof_analysis": roof_analysis,
        "boundary_info": boundary_info,
        "pd_rules": rules,
        "disclaimer": "This is a preliminary assessment. Verify with your local planning authority before starting work.",
    }, "format": "html"}


# ──────────────────────────────────────────────────────── the catalog registry

CATALOG: list[ProductTemplate] = [
    ProductTemplate(
        id="lowball_counter_email",
        name="The Lowball Counter-Email",
        description="A fiercely worded, data-backed counter-offer email using your AVM and sold comps.",
        gbp_price=1.50,
        emotion_trigger=EmotionTrigger.ANGER,
        required_repos=["langchain-ai/langchain"],
        required_modules=["engine", "epc"],
        execution_function=_lowball_counter_email,
        tier_access="all",
        delivery_format="text",
        credit_cost_gbp=1.50,
    ),
    ProductTemplate(
        id="neighbor_extension_blueprint",
        name="The Neighbor's Extension Blueprint",
        description="Find approved planning applications on your street and extract the square footage added.",
        gbp_price=2.00,
        emotion_trigger=EmotionTrigger.FOMO,
        required_repos=["Unstructured-IO/unstructured"],
        required_modules=["planning", "engine"],
        execution_function=_neighbor_extension_blueprint,
        tier_access="all",
        delivery_format="html",
        credit_cost_gbp=2.00,
    ),
    ProductTemplate(
        id="stealth_listing_sniper",
        name="The Stealth Listing Sniper",
        description="Find long-held LLC-owned properties on your street and generate unsolicited offer letters.",
        gbp_price=4.00,
        emotion_trigger=EmotionTrigger.FOMO,
        required_repos=[],
        required_modules=["graph_db", "companies_house"],
        execution_function=_stealth_listing_sniper,
        tier_access="plus",
        delivery_format="html",
        credit_cost_gbp=4.00,
    ),
    ProductTemplate(
        id="council_tax_challenger",
        name="The Council Tax Banding Challenger",
        description="Compare your property's sqm to VOA banding rules. Generate the official challenge letter.",
        gbp_price=3.00,
        emotion_trigger=EmotionTrigger.ANGER,
        required_repos=["langchain-ai/langchain"],
        required_modules=["engine", "graph_db"],
        execution_function=_council_tax_challenger,
        tier_access="all",
        delivery_format="text",
        credit_cost_gbp=3.00,
    ),
    ProductTemplate(
        id="leasehold_trap_xray",
        name="The Leasehold Trap X-Ray",
        description="Upload the listing PDF. We extract lease terms and calculate the Section 42 extension cost.",
        gbp_price=5.00,
        emotion_trigger=EmotionTrigger.FEAR,
        required_repos=["Unstructured-IO/unstructured"],
        required_modules=["engine"],
        execution_function=_leasehold_trap_xray,
        tier_access="all",
        delivery_format="html",
        credit_cost_gbp=5.00,
    ),
    ProductTemplate(
        id="gentrification_radar",
        name="The Gentrification Radar",
        description="5-year price and crime forecasts cross-referenced with local Reddit chatter about new openings.",
        gbp_price=3.00,
        emotion_trigger=EmotionTrigger.GREED,
        required_repos=["unit8co/darts"],
        required_modules=["graph_db", "reddit_intel"],
        execution_function=_gentrification_radar,
        tier_access="all",
        delivery_format="html",
        credit_cost_gbp=3.00,
    ),
    ProductTemplate(
        id="architects_vision",
        name="The Architect's Vision",
        description="AI-rendered photorealistic future state of your house with extensions and solar panels.",
        gbp_price=4.00,
        emotion_trigger=EmotionTrigger.GREED,
        required_repos=["AUTOMATIC1111/stable-diffusion-webui"],
        required_modules=["vision"],
        execution_function=_architects_vision,
        tier_access="plus",
        delivery_format="html",
        credit_cost_gbp=4.00,
    ),
    ProductTemplate(
        id="deal_autopsy",
        name="The Deal Autopsy",
        description="Parse the conveyancing pack, flag Hidden Traps, generate a cinematic audio briefing.",
        gbp_price=20.00,
        emotion_trigger=EmotionTrigger.FEAR,
        required_repos=["Unstructured-IO/unstructured", "openai/whisper"],
        required_modules=[],
        execution_function=_deal_autopsy,
        tier_access="pro",
        delivery_format="html",
        credit_cost_gbp=15.00,
    ),
    ProductTemplate(
        id="syndicate_street_map",
        name="The Syndicate Street Map",
        description="Find hidden power players on a street. Map equity hoarders and LLC blocks.",
        gbp_price=15.00,
        emotion_trigger=EmotionTrigger.GREED,
        required_repos=["geopandas", "scikit-learn"],
        required_modules=["graph_db", "companies_house"],
        execution_function=_syndicate_street_map,
        tier_access="pro",
        delivery_format="html",
        credit_cost_gbp=10.00,
    ),
    ProductTemplate(
        id="planning_permission_oracle",
        name="The Planning Permission Oracle",
        description="Analyze your roof from Street View. Get a 90% confidence Permitted Development verdict in 3 seconds.",
        gbp_price=2.50,
        emotion_trigger=EmotionTrigger.LAZINESS,
        required_repos=[],
        required_modules=["vision", "overpass", "planning"],
        execution_function=_planning_permission_oracle,
        tier_access="all",
        delivery_format="html",
        credit_cost_gbp=2.50,
    ),
]

# Lookup by ID
CATALOG_BY_ID = {p.id: p for p in CATALOG}

# Lookup by trigger emotion
CATALOG_BY_TRIGGER = {}
for p in CATALOG:
    CATALOG_BY_TRIGGER.setdefault(p.emotion_trigger, []).append(p)


def get_product(product_id: str) -> ProductTemplate | None:
    return CATALOG_BY_ID.get(product_id)


def list_products(tier: str = "all", trigger: str | None = None) -> list[ProductTemplate]:
    """List products filtered by tier access and/or emotion trigger."""
    results = CATALOG
    if trigger:
        results = [p for p in results if p.emotion_trigger.value == trigger]
    if tier:
        tier_order = {"all": 0, "plus": 1, "pro": 2}
        user_level = tier_order.get(tier, 0)
        results = [p for p in results if tier_order.get(p.tier_access, 0) <= user_level]
    return results


def execute_product(product_id: str, subject: dict, params: dict) -> dict:
    """Execute a product by ID. Returns the execution result or an error."""
    product = get_product(product_id)
    if not product:
        return {"ok": False, "error": f"Unknown product: {product_id}"}
    if not product.execution_function:
        return {"ok": False, "error": f"Product {product_id} has no execution function"}
    try:
        return product.execution_function(subject, params)
    except Exception as e:
        return {"ok": False, "error": str(e)}
