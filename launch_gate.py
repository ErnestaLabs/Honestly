#!/usr/bin/env python3
"""Local finish gate for Honestly.

Run this before deploying. It is intentionally boring: compile, tests, product smoke,
public-source smoke, deploy manifest check. If this fails, do not push to VPS.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
COMMERCIAL_WORDS = ("PropertyData", "Street Data", "StreetData", "Chimnie", "PaTMa")
USER_FACING_BANNED = (
    "wired", "missing", "requires", "lookup_required", "best_effort", "best-effort",
    "pending", "not available", "n/a", "Confirm with seller", "no public floor-area",
)


def run(cmd, timeout=300):
    print("$", " ".join(cmd))
    p = subprocess.run(cmd, cwd=ROOT, text=True, encoding="utf-8", errors="replace",
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if p.stdout:
        print(p.stdout.rstrip())
    if p.returncode:
        raise SystemExit(p.returncode)


def import_deploy_files():
    spec = importlib.util.spec_from_file_location("_deploy_vps", os.path.join(ROOT, "_deploy_vps.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.FILES


def check_deploy_manifest():
    missing = []
    rels = {rel for rel, _ in import_deploy_files()}
    required = {
        "bot.py", "server.py", "webapp/index.html", "engine.py", "land_registry.py", "geo.py", "epc.py", "data/epc_public_cache.json", "appraise.py",
        "products.py", "store.py", "report.py", "brand.py", "decision_models.py",
        "scenario.py", "action_plan.py", "price_ledger.py", "verification.py",
        "area_context.py", "ai.py", "area_report.py", "email_funnel.py", "email_send.py", "blog.py", "blog_images.py", "ads.py", "press_review.py", "press_review.json", "social_sentiment.py", "social_sentiment.json", "seo_audit.py", "cities.py", "demand.py", "market_analysis.py", "market_district.py", "market_study.py", "publish_daily.py", "deploy/honestly-web.service", "site/img/logo-lockup.png",
        "site/img/logo-lockup-compact.png", "site/img/logo-wordmark-clean.png",
        "site/img/logo-icon.png",
    }
    for rel in sorted(required):
        if rel not in rels:
            missing.append(f"not in FILES: {rel}")
        elif not os.path.exists(os.path.join(ROOT, rel.replace("/", os.sep))):
            missing.append(f"missing local file: {rel}")
    if missing:
        raise SystemExit("Deploy manifest incomplete:\n" + "\n".join(missing))
    print("deploy manifest: ok")


def product_smoke():
    import brand
    import engine
    import report

    r = engine.value("58 Cronin Street, London SE15 6JH", finish="high")
    d = engine.summary(r, "vendor", tier="pro")
    assert d["central"] == 530000, d
    assert d["range_str"].replace("£", "GBP ").endswith("500,000 - GBP 565,000"), d["range_str"]
    assert d["confidence"]["grade"] == "Good", d["confidence"]
    assert d.get("sqm") == 103, d
    assert d.get("floor_area_source") == "public EPC register", d
    assert d.get("floor_area_status") == "official_public_exact", d
    assert d.get("epc") == "C", d
    vf = d.get("valuation_formula") or {}
    assert vf.get("evidence", {}).get("strict_comparable_count", 0) >= 5, vf
    assert vf.get("evidence", {}).get("evidence_role") == "strict_comparables", vf
    strict_rule = vf.get("filter", {}).get("strict_comparable_rule", "")
    for phrase in ("minimum 5 comparables", "<=0.5 miles by default", "up to 1 mile only", "sold within 6 months ideally", "extended to 12 months only to reach 5", "verified/inferred bedrooms", "tenure caveated", "otherwise proof/context only"):
        assert phrase in strict_rule, strict_rule
    strict_rows = [row for row in (d.get("evidence") or []) if row.get("strict_comparable")]
    assert len(strict_rows) >= 5, d.get("evidence")
    for row in strict_rows[:5]:
        assert row.get("sqm"), row
        assert row.get("floor_area_source"), row
        assert row.get("justification"), row
        assert row.get("strict_reject_reason") is None, row
    forbidden_fields = {"street_enrichment", "chimnie_enrichment", "patma_crosscheck", "avm_crosscheck"}
    leaked = forbidden_fields & set(d)
    assert not leaked, leaked
    en = d.get("honestly_enrichment") or {}
    assert en.get("source") == "Honestly public-data enrichment", en
    assert en.get("commercial_data") is False, en
    assert en.get("proof", {}).get("source") == "HM Land Registry Price Paid Data", en
    assert en.get("decision_signals"), en
    assert en.get("monitoring_triggers"), en
    assert en.get("formula", {}).get("name") == "Honestly Transparent AVM v1", en
    assert en.get("google_context", {}).get("address_validation"), en
    assert en.get("free_api_context", {}).get("postcodes_io"), en

    contract = d.get("mandatory_output_contract") or {}
    required_contract_keys = {
        "sold_proof_rows_subject_sale_history_hpi_uplift",
        "floor_area_and_epc_score",
        "latitude_longitude_admin_area_nearest_postcodes",
        "travel_times_to_transport_and_amenities",
        "verified_normalised_subject_address",
        "amenities_transport_nodes_boundaries",
        "street_level_crime_counts",
        "active_flood_warnings_and_monitored_flood_areas",
        "european_air_quality_index_and_pollutants",
        "nearby_planning_applications",
        "council_tax_band",
        "building_level_roof_solar_potential_and_estimated_generation",
        "bank_rate_mpc_date_hpi_momentum",
        "local_market_sentiment_not_value_evidence",
        "subject_location_map_image",
        "frontage_photo",
        "door_knock_route_map_agent_audience",
        "finish_tier_proposal_from_listing_photos",
        "plain_english_narrative_grounded_in_figures",
        "spoken_glass_box_walkthrough",
        "calibrated_capped_disclosed_live_market_steer",
        "fiat_crypto_purchase",
        "delivery_of_file_and_hosted_link",
    }
    assert required_contract_keys <= set(contract), sorted(required_contract_keys - set(contract))
    summary_blob = json.dumps({"contract": contract, "enrichment": d.get("honestly_enrichment")}, ensure_ascii=False)
    low_blob = summary_blob.lower()
    for bad in USER_FACING_BANNED:
        assert bad.lower() not in low_blob, f"user-facing banned term in summary JSON: {bad}\n{summary_blob[:1200]}"

    refs = brand.references(d)
    ref_text = "\n".join(str(x) for x in refs)
    for word in COMMERCIAL_WORDS:
        assert word not in ref_text, f"commercial source leaked into references: {word}\n{ref_text}"

    with tempfile.TemporaryDirectory() as td:
        # Fast AVM v2 harness check: validates research metrics/report plumbing without
        # calling engine 10 more times inside the gate.
        bt_json = os.path.join(td, "avm_v2_backtest.json")
        bt_md = os.path.join(td, "avm_v2_backtest.md")
        run([sys.executable, "tools/avm_backtest.py", "--fixture", "research/avm_v2_fixture_cases.json", "--out", bt_json, "--markdown", bt_md, "--no-engine"], timeout=60)
        bt = json.load(open(bt_json, encoding="utf-8"))
        assert bt.get("schema") == "honestly_avm_v2_backtest_v1", bt
        assert "baseline" in (bt.get("metrics") or {}), bt

        pdf, html = report.build(r, "vendor", outdir=td, slug="gate", interactive=False, tier="lite")
        assert os.path.exists(pdf), pdf
        assert os.path.getsize(pdf) > 4000, os.path.getsize(pdf)
        try:
            from pypdf import PdfReader
            text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf).pages)
            for bad in USER_FACING_BANNED + ("None sqm", "--bedroom", "Waltham", "Leyton", "Walthamstow", "Stratford"):
                assert bad.lower() not in text.lower(), bad
            for good in ("103 sqm", "Comparable evidence (sold)", "Comparable justifications"):
                assert good in text, good
        except ImportError:
            pass
    print("product smoke: ok")


def main():
    compile_files = [
        "engine.py", "bot.py", "server.py", "area_report.py", "email_funnel.py", "email_send.py", "blog.py", "blog_images.py", "ads.py", "press_review.py", "social_sentiment.py", "seo_audit.py", "cities.py", "demand.py", "market_analysis.py", "market_district.py", "market_study.py", "publish_daily.py", "land_registry.py", "geo.py", "epc.py", "appraise.py",
        "products.py", "store.py", "report.py", "brand.py", "decision_models.py",
        "scenario.py", "action_plan.py", "price_ledger.py", "verification.py",
        "area_context.py", "ai.py", "avm_v2.py", "tools/avm_backtest.py", "tools/build_avm_fixture.py", "_deploy_vps.py",
    ]
    run([sys.executable, "-m", "py_compile", *compile_files], timeout=120)
    run([sys.executable, "-m", "unittest", "discover", "-p", "test_*.py"], timeout=300)
    check_deploy_manifest()
    product_smoke()
    print("LAUNCH GATE: PASS")


if __name__ == "__main__":
    main()
