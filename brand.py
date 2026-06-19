#!/usr/bin/env python3
"""brand.py - the ONE source of brand truth for every Honestly deliverable.

The PDF (report.py) and the interactive HTML (appraise.interactive_chart) both
import from here so the palette, the logo and the API-to-deliverable contract can
never drift between surfaces. This mirrors the engine.summary() principle: one
dict, many renderings, zero disagreement.

Contents:
  * PALETTE     - the live brand palette (hex for CSS, rgb tuples for fpdf),
                  taken from site/tailwind.config.js (the live source of truth).
  * logo_*()    - the EXACT logo file (Brand Asset Rule: never an SVG/font/canvas
                  recreation), as a path for fpdf and as a base64 data URI so the
                  self-contained HTML stays offline.
  * DELIVERABLE_MAP - every API the system uses, its class (DATA/MEDIA/CHANNEL),
                  the PDF section and HTML panel it renders in, and the citation it
                  earns. The build contract: no API without a home in both surfaces.
  * references(report_data) - the academic-style, source-gated citation list shared
                  identically by the PDF and the HTML. Built only from sources
                  actually present in that report - honest by construction.
"""
import os, base64, datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
TODAY = datetime.date.today()
DATESTR = f"{TODAY.day} {TODAY:%B %Y}"


# -- palette (live brand, from site/tailwind.config.js) -----------------------
def _rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

# hex strings (CSS / HTML) keyed by role
HEX = {
    "navy":  "#0e2747",   # structure, axes, headings, dark bands
    "green": "#15807f",   # sold comparables, central value
    "teal":  "#2aa39a",   # secondary accent, range band
    "gold":  "#d89a32",   # recommended-guide marker (replaces old terracotta)
    "cream": "#f6f3ec",   # panel fill / page on dark
    "paper": "#fbf9f4",   # page background
    "ink":   "#1c1a16",   # body text
    "muted": "#6b6557",   # secondary text
    "sand":  "#c9c1ad",   # hairlines on dark
    "pale":  "#e7eef0",   # pale teal band fill
    "line":  "#e7e1d4",   # hairlines on light
    "white": "#ffffff",
}
# rgb tuples (fpdf) under the same keys
RGB = {k: _rgb(v) for k, v in HEX.items()}


class _Palette:
    """Attribute access for both forms: PALETTE.navy (hex) and PALETTE.navy_rgb (tuple)."""
    def __init__(self):
        for k, v in HEX.items():
            setattr(self, k, v)
            setattr(self, k + "_rgb", RGB[k])

PALETTE = _Palette()

# explicit chart colour roles (three legible, distinct roles + range band)
CHART = {
    "structure": HEX["navy"],   # axes, labels, gridlines
    "sold":      HEX["green"],  # sold comparable bars + central value line
    "guide":     HEX["gold"],   # recommended-guide marker
    "band":      HEX["teal"],   # assessed-range band (used at low opacity)
}


# -- the logo (EXACT file bytes - never recreated) ----------------------------
LOGO_LOCKUP   = os.path.join(_HERE, "site", "img", "logo-lockup.png")
LOGO_LOCKUP_C = os.path.join(_HERE, "site", "img", "logo-lockup-compact.png")
LOGO_WORDMARK = os.path.join(_HERE, "site", "img", "logo-wordmark-clean.png")
LOGO_ICON     = os.path.join(_HERE, "site", "img", "logo-icon.png")

_LOGO_CACHE = {}


def logo_path(which="lockup"):
    """Filesystem path to the exact logo file for fpdf2's pdf.image()."""
    return {"lockup": LOGO_LOCKUP, "lockup-compact": LOGO_LOCKUP_C,
            "wordmark": LOGO_WORDMARK, "icon": LOGO_ICON}.get(which, LOGO_LOCKUP)


_LOGO_FILENAME = {"lockup": "logo-lockup.png", "lockup-compact": "logo-lockup-compact.png",
                  "wordmark": "logo-wordmark-clean.png", "icon": "logo-icon.png"}


def logo_url(which="lockup"):
    """Public URL of the exact logo file for a HOSTED surface (the blog / Mini App), served
    flat at /img/<file> from site/img. Unlike logo_data_uri (which base64-inlines the asset
    so an offline PDF/HTML deliverable is self-contained), this references the file by URL:
    the browser downloads each logo ONCE and caches it across every page, instead of carrying
    ~600KB of inline base64 in every single HTML document. Same EXACT asset (Brand Asset Rule),
    never recreated. Returns '' if the asset is missing so the caller falls back to text."""
    name = _LOGO_FILENAME.get(which, _LOGO_FILENAME["lockup"])
    p = os.path.join(_HERE, "site", "img", name)
    return ("/img/" + name) if os.path.exists(p) else ""


def logo_data_uri(which="lockup"):
    """base64 data URI of the exact logo PNG, so the self-contained HTML embeds the
    real asset and renders offline. Returns '' if the asset is missing (caller falls
    back to text, never to a generated graphic - Brand Asset Rule)."""
    if which in _LOGO_CACHE:
        return _LOGO_CACHE[which]
    p = logo_path(which)
    uri = ""
    try:
        with open(p, "rb") as f:
            uri = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    except Exception:
        uri = ""
    _LOGO_CACHE[which] = uri
    return uri


TAGLINE = "A defensible value: sold evidence, confidence and proof"


# -- the API -> deliverable contract ------------------------------------------
# class:    DATA    renders a section (PDF) and a panel (HTML)
#           MEDIA   renders an embedded asset/link in both
#           CHANNEL delivery/payment - footer provenance / CTA only, no content
# Each row is the single place an API is declared; report.build and
# interactive_chart iterate this to render, and references() reads it to cite.
DELIVERABLE_MAP = [
    {"id": "hmlr_direct", "klass": "DATA",  "provider": "HM Land Registry (Price Paid + HPI, direct)",
     "contributes": "sold proof rows, subject sale history and HPI uplift",
     "pdf_section": "Comparable evidence", "html_panel": "comps"},
    {"id": "epc",         "klass": "DATA",  "provider": "EPC Register (DLUHC)",
     "contributes": "floor area and EPC score",
     "pdf_section": "Material information", "html_panel": "material"},
    {"id": "postcodes_io","klass": "DATA",  "provider": "Postcodes.io",
     "contributes": "latitude/longitude, admin area, nearest postcodes",
     "pdf_section": "Location & connectivity", "html_panel": "location"},
    {"id": "distance_mx", "klass": "DATA",  "provider": "Google Distance Matrix",
     "contributes": "travel times to transport and amenities",
     "pdf_section": "Location & connectivity", "html_panel": "location"},
    {"id": "addr_val",    "klass": "DATA",  "provider": "Google Address Validation",
     "contributes": "verified, normalised subject address",
     "pdf_section": "Subject", "html_panel": "hero"},
    {"id": "overpass",    "klass": "DATA",  "provider": "OpenStreetMap / Overpass",
     "contributes": "amenities, transport nodes, boundaries",
     "pdf_section": "Area & amenities", "html_panel": "area"},
    {"id": "police",      "klass": "DATA",  "provider": "Police.uk",
     "contributes": "street-level crime counts",
     "pdf_section": "Safety", "html_panel": "safety"},
    {"id": "flood",       "klass": "DATA",  "provider": "Environment Agency (real-time flood-monitoring)",
     "contributes": "active flood warnings and monitored flood areas",
     "pdf_section": "Environment", "html_panel": "environment"},
    {"id": "air_quality", "klass": "DATA",  "provider": "Open-Meteo / Copernicus CAMS",
     "contributes": "European air-quality index and pollutants",
     "pdf_section": "Environment", "html_panel": "environment"},
    {"id": "planning",    "klass": "DATA",  "provider": "PlanIt (UK planning aggregator)",
     "contributes": "nearby planning applications",
     "pdf_section": "Planning & development", "html_panel": "planning"},
    {"id": "planning_data", "klass": "DATA", "provider": "planning.data.gov.uk (MHCLG open data)",
     "contributes": "statutory planning designations on the site (conservation area, Article 4, flood zone, green belt)",
     "pdf_section": "Planning & development", "html_panel": "planning"},
    {"id": "companies_house", "klass": "DATA", "provider": "Companies House (REST API)",
     "contributes": "corporate/overseas landlord identity and directors for a corporately-owned property",
     "pdf_section": "Material information", "html_panel": "material"},
    {"id": "council_tax", "klass": "DATA",  "provider": "VOA (Council Tax)",
     "contributes": "council-tax band",
     "pdf_section": "Material information", "html_panel": "material"},
    {"id": "google_solar","klass": "DATA",  "provider": "Google Solar API",
     "contributes": "building-level roof solar potential and estimated generation",
     "pdf_section": "Solar & energy", "html_panel": "solar"},
    {"id": "macro",       "klass": "DATA",  "provider": "Bank of England + ONS",
     "contributes": "Bank Rate, MPC date, HPI momentum",
     "pdf_section": "Market outlook", "html_panel": "market"},
    {"id": "reddit",      "klass": "DATA",  "provider": "UK property subreddits (social sentiment)",
     "contributes": "local market sentiment (not value evidence)",
     "pdf_section": "Market intelligence", "html_panel": "market"},
    {"id": "static_map",  "klass": "MEDIA", "provider": "Google Maps (Static Map)",
     "contributes": "subject location map image",
     "pdf_section": "Location & connectivity", "html_panel": "location"},
    {"id": "street_view", "klass": "MEDIA", "provider": "Google Maps (Street View)",
     "contributes": "frontage photo",
     "pdf_section": "Subject", "html_panel": "hero"},
    {"id": "routes",      "klass": "MEDIA", "provider": "Google Maps (Routes)",
     "contributes": "door-knock route map (agent audience)",
     "pdf_section": "Location & connectivity", "html_panel": "location"},
    {"id": "vision",      "klass": "DATA",  "provider": "Google Cloud Vision",
     "contributes": "finish-tier proposal from listing photos",
     "pdf_section": "Basis of assessment", "html_panel": "condition"},
    {"id": "gemini",      "klass": "DATA",  "provider": "Google Gemini",
     "contributes": "plain-English narrative grounded in the figures",
     "pdf_section": "Executive summary", "html_panel": "hero"},
    {"id": "voxtral",     "klass": "MEDIA", "provider": "Mistral Voxtral",
     "contributes": "spoken glass-box walkthrough",
     "pdf_section": "Interactive companion", "html_panel": "audio"},
    {"id": "vertex",      "klass": "DATA",  "provider": "Google Vertex AI (calibration model)",
     "contributes": "calibrated, capped, disclosed live-market steer",
     "pdf_section": "Basis of assessment", "html_panel": "build_up"},
    {"id": "payrequest",  "klass": "CHANNEL", "provider": "PayRequest.me",
     "contributes": "fiat/crypto purchase",
     "pdf_section": "Footer", "html_panel": "footer"},
    {"id": "telegram",    "klass": "CHANNEL", "provider": "Telegram Bot API",
     "contributes": "delivery of the file and the hosted link",
     "pdf_section": "Footer", "html_panel": "footer"},
]

# id -> row, for quick lookup by renderers
MAP_BY_ID = {row["id"]: row for row in DELIVERABLE_MAP}


# -- citations (academic style), one per API id that can earn one -------------
# Static citation metadata; the year/accessed date is stamped at render time.
# url is the public, verifiable source. Publishers named accurately.
_CITATIONS = {
    "hmlr_direct": ("HM Land Registry", "Price Paid Data and UK House Price Index (Open Government Licence v3.0)",
                    "https://landregistry.data.gov.uk/"),
    "epc":         ("Department for Levelling Up, Housing and Communities", "Energy Performance of Buildings Register",
                    "https://epc.opendatacommunities.org/"),
    "postcodes_io":("Postcodes.io", "Open UK postcode and geolocation data (Ordnance Survey / ONS, OGL)",
                    "https://postcodes.io/"),
    "distance_mx": ("Google", "Distance Matrix API (travel times)",
                    "https://developers.google.com/maps/documentation/distance-matrix"),
    "addr_val":    ("Google", "Address Validation API",
                    "https://developers.google.com/maps/documentation/address-validation"),
    "overpass":    ("OpenStreetMap contributors", "Amenity, transport and boundary data via the Overpass API (ODbL)",
                    "https://www.openstreetmap.org/copyright"),
    "police":      ("Home Office / data.police.uk", "Street-level crime data (Open Government Licence v3.0)",
                    "https://data.police.uk/"),
    "flood":       ("Environment Agency", "Real-time flood-monitoring API: active warnings and monitored flood areas (Open Government Licence v3.0)",
                    "https://environment.data.gov.uk/flood-monitoring/doc/reference"),
    "air_quality": ("Open-Meteo; Copernicus Atmosphere Monitoring Service (CAMS)", "European air-quality index and pollutant concentrations",
                    "https://open-meteo.com/en/docs/air-quality-api"),
    "planning":    ("PlanIt (planit.org.uk)", "Planning application records aggregated from UK local-authority registers",
                    "https://www.planit.org.uk/"),
    "planning_data": ("Ministry of Housing, Communities & Local Government", "planning.data.gov.uk: statutory planning and environmental designations by location (Open Government Licence v3.0)",
                    "https://www.planning.data.gov.uk/"),
    "companies_house": ("Companies House", "Company Information API: company profile, status and officers (Open Government Licence v3.0)",
                    "https://developer.company-information.service.gov.uk/"),
    "council_tax": ("Valuation Office Agency", "Council Tax bands",
                    "https://www.gov.uk/council-tax-bands"),
    "ofsted":     ("Ofsted", "School inspection reports",
                    "https://reports.ofsted.gov.uk/"),
    "google_solar":("Google", "Solar API (buildingInsights): roof solar potential and estimated annual generation",
                    "https://developers.google.com/maps/documentation/solar"),
    "macro":       ("Bank of England; Office for National Statistics", "Bank Rate, MPC schedule and UK House Price Index",
                    "https://www.bankofengland.co.uk/monetary-policy"),
    "reddit":      ("UK property subreddits (r/HousingUK, r/PropertyUK)", "Public discussion threads, cited as social-media sentiment - not evidence of value",
                    "https://www.reddit.com/r/HousingUK/"),
    "hitman_red":  ("hitman.red (Ernesta Labs Exclusive Preview)", "Social-sentiment listening across public UK property forums - quoted as social-media sentiment, not evidence of value",
                    "https://hitman.red"),
    "static_map":  ("Google", "Maps Static API",
                    "https://developers.google.com/maps/documentation/maps-static"),
    "street_view": ("Google", "Street View Static API",
                    "https://developers.google.com/maps/documentation/streetview"),
    "routes":      ("Google", "Routes API",
                    "https://developers.google.com/maps/documentation/routes"),
    "vision":      ("Google", "Cloud Vision API (image property analysis)",
                    "https://cloud.google.com/vision"),
    "gemini":      ("Google", "Gemini API (narrative generation, grounded in the report figures)",
                    "https://ai.google.dev/"),
    "voxtral":     ("Mistral AI", "Voxtral text-to-speech (spoken walkthrough)",
                    "https://mistral.ai/"),
    "vertex":      ("Google", "Vertex AI (calibration model; output capped and disclosed)",
                    "https://cloud.google.com/vertex-ai"),
    # HMRC is not an API row but is cited when SDLT/CGT lines render:
    "hmrc":        ("HM Revenue & Customs", "Stamp Duty Land Tax and Capital Gains Tax rates",
                    "https://www.gov.uk/government/organisations/hm-revenue-customs"),
    "ntselat":     ("National Trading Standards Estate & Letting Agency Team", "Material Information in Property Listings (Parts A, B and C)",
                    "https://www.nationaltradingstandards.uk/work-areas/estate-letting-agency/"),
}


def _present(report_data):
    """Return the set of citation ids whose data actually appears in this report.

    Honest by construction: a source is cited only when its data is present.
    report_data is engine.summary()'s dict, optionally augmented by the caller with
    flags like {'schools': [...], 'market_analysis': {...}, 'reddit': {...}}.
    """
    d = report_data or {}
    ids = set()
    # always-on: the sold evidence and material-information guidance
    ids.add("ntselat")              # the PDF always renders the Material Information section
    if d.get("evidence") or d.get("lite_basis") or d.get("crosscheck"):
        ids.add("hmlr_direct")
    if d.get("epc"):
        ids.add("epc")
    if d.get("schools"):
        ids.add("ofsted")
    macro = d.get("macro")
    if macro:
        ids.add("macro")
        if macro.get("momentum"):
            ids.add("hmlr_direct")  # ONS HPI series powers momentum
    # net-proceeds / tax lines always render SDLT-or-CGT context
    ids.add("hmrc")
    # geo + location: present when we have coordinates
    if d.get("lat") and d.get("lng"):
        ids.add("postcodes_io")
    # market analysis layer (when the caller attached it)
    ma = d.get("market_analysis")
    if ma:
        if ma.get("reddit") or d.get("reddit"):
            ids.add("reddit")
        if ma.get("hpi"):
            ids.add("hmlr_direct")
    if d.get("reddit"):
        ids.add("reddit")
    # extra context sources, cited when the caller marks them present
    for k in ("police", "flood", "air_quality", "planning", "planning_data", "companies_house",
              "overpass", "distance_mx", "addr_val", "static_map", "street_view", "routes",
              "vision", "gemini", "voxtral", "vertex", "council_tax", "google_solar",
              "ofsted"):
        if d.get(k):
            ids.add(k)
    if d.get("tax"):
        ids.add("council_tax")
    return ids


def references(report_data):
    """The numbered, academic-style References list - identical for PDF and HTML.

    Returns a list of dicts: {"n": int, "publisher": str, "title": str, "url": str,
    "accessed": "Accessed <DATESTR>"}. Only sources actually present in this report
    are cited. Ordered by a stable canonical sequence so the numbering is repeatable.
    """
    present = _present(report_data)
    # canonical ordering: anchor evidence first, then official records, then context, then AI/media
    order = ["hmlr_direct", "epc", "council_tax", "ntselat", "ofsted",
             "postcodes_io", "distance_mx", "addr_val", "overpass", "police",
             "flood", "air_quality", "planning", "planning_data", "companies_house", "google_solar", "macro", "hmrc", "reddit",
             "static_map", "street_view", "routes", "vision", "gemini", "voxtral",
             "vertex"]
    out, n = [], 0
    for cid in order:
        if cid not in present or cid not in _CITATIONS:
            continue
        pub, title, url = _CITATIONS[cid]
        n += 1
        out.append({"n": n, "id": cid, "publisher": pub, "title": title,
                    "url": url, "accessed": f"Accessed {DATESTR}"})
    return out


def reference_str(c):
    """Render one citation dict as a single academic-style line."""
    return f"{c['n']}. {c['publisher']}. {c['title']}. {c['url']} ({c['accessed']})."


# The authoritative public datasets and official guidance that underpin UK house-price
# reporting. These are not "sources we queried for this page" (those are _CITATIONS, gated by
# _present); they are the primary statistics and statutory guidance a serious reader should go
# to next. We link OUT to them as ordinary editorial follow links - citing the official record
# is exactly the E-E-A-T / topical-authority signal search and answer engines reward, and it is
# how a credible research page is meant to behave. Government and national-statistics sources
# only; never a competitor listings portal as a "source".
OFFICIAL_SOURCES = [
    ("Office for National Statistics", "UK House Price Index, statistical bulletin",
     "https://www.ons.gov.uk/economy/inflationandpriceindices/bulletins/housepriceindex/latest"),
    ("HM Land Registry", "Price Paid Data (Open Government Licence v3.0)",
     "https://www.gov.uk/government/statistical-data-sets/price-paid-data"),
    ("HM Land Registry", "UK House Price Index, search and download tool",
     "https://landregistry.data.gov.uk/app/ukhpi"),
    ("Office for National Statistics", "House price statistics for small areas",
     "https://www.ons.gov.uk/peoplepopulationandcommunity/housing/bulletins/housepricestatisticsforsmallareasinenglandandwales/latest"),
    ("Bank of England", "Bank Rate and monetary policy",
     "https://www.bankofengland.co.uk/monetary-policy/the-interest-rate-bank-rate"),
    ("GOV.UK", "Stamp Duty Land Tax: rates and calculator",
     "https://www.gov.uk/stamp-duty-land-tax"),
    ("National Trading Standards Estate & Letting Agency Team",
     "Material Information in property listings (Parts A, B and C)",
     "https://www.nationaltradingstandards.uk/work-areas/estate-letting-agency/"),
]


def official_sources():
    """The curated authoritative-source list as numbered citation dicts (follow links)."""
    return [{"n": i, "publisher": pub, "title": title, "url": url,
             "accessed": f"Accessed {DATESTR}"}
            for i, (pub, title, url) in enumerate(OFFICIAL_SOURCES, 1)]


if __name__ == "__main__":
    # selftest: palette is well-formed, logo embeds, references gate honestly.
    assert len(RGB) == len(HEX)
    for k, t in RGB.items():
        assert len(t) == 3 and all(0 <= x <= 255 for x in t), k
    uri = logo_data_uri("lockup")
    print("logo lockup embeds:", bool(uri), f"({len(uri)} bytes data URI)")
    print("DELIVERABLE_MAP rows:", len(DELIVERABLE_MAP),
          "| DATA:", sum(1 for r in DELIVERABLE_MAP if r["klass"] == "DATA"),
          "| MEDIA:", sum(1 for r in DELIVERABLE_MAP if r["klass"] == "MEDIA"),
          "| CHANNEL:", sum(1 for r in DELIVERABLE_MAP if r["klass"] == "CHANNEL"))
    # minimal report -> few citations
    minimal = {"evidence": [{"x": 1}]}
    refs_min = references(minimal)
    print("\nminimal report references:")
    for c in refs_min:
        print("  " + reference_str(c))
    # rich report -> many citations
    rich = {"evidence": [1], "epc": 72, "schools": [1], "positioning": {"stuck": []},
            "macro": {"momentum": {"x": 1}}, "lat": 51.5, "lng": -0.1, "tax": "C",
            "market_analysis": {"reddit": {}, "hpi": {}}, "police": True, "flood": True,
            "air_quality": True, "planning": True, "overpass": True}
    refs_rich = references(rich)
    print(f"\nrich report references ({len(refs_rich)}):")
    for c in refs_rich:
        print("  " + reference_str(c))
    # every DATA/MEDIA api id must have a citation template (coverage of the contract)
    missing = [r["id"] for r in DELIVERABLE_MAP
               if r["klass"] in ("DATA", "MEDIA") and r["id"] not in _CITATIONS]
    assert not missing, f"DATA/MEDIA rows missing a citation template: {missing}"
    print("\nOK - every DATA/MEDIA API has a citation template; CHANNEL rows correctly have none.")
