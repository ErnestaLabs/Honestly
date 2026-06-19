#!/usr/bin/env python3
"""market_study.py - the cross-district data study ("UK city-centre index").

This is the network's one original-data story: it reads every published district's OWN
stored model from the database and lays the city centres side by side - days on market,
asking-vs-sold gap, stuck-stock share and price per square metre. Nothing here is fetched
or invented; every figure traces to a district page that already cites its source. The
study issues no valuation and blends nothing - it reports the same official transaction and
listing figures the district pages report, aggregated into league tables.

Honesty posture (ABSOLUTE, carried from blog.py):
  * Sold figures are HM Land Registry Price Paid Data; asking figures are live listings.
    They are reported beside each other, never blended into a "value".
  * The asking-vs-sold gap is a COMPOSITION signal, not a discount: the live stock (which
    skews to smaller, cheaper city-centre flats) is a different mix from the trailing sold
    set (which includes larger units). A negative gap means the stock on sale today is
    cheaper stock - it is never evidence that homes are "underpriced". The copy says so.
  * Every district contributes only its own real numbers (the Alaska rule).

Public surface:
  gather_study(*, store_mod=None) -> the canonical study model (agg + league tables + rows)
  write_csv(study, path)          -> the public raw-data download (the backlink magnet)
"""
import os
import statistics

import brand

# the report's slug / public path (served by server.py like any other blog page)
STUDY_SLUG = "uk-city-centre-index"
STUDY_CSV = "uk-city-centre-index.csv"


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _load_sentiment():
    """Best-effort load of the captured social-sentiment artifact (study_sentiment.json).
    It is captured out-of-band via the Hit MCP when that tooling is connected, then frozen
    to disk so the headless build (which has no MCP) can render it. Returns {} when absent
    so the section simply omits - never raises, never blocks the build."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "study_sentiment.json")
    try:
        import json
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _row_from_model(m):
    """One league-table row from a district's stored model, or None if it has no usable
    sold basis. Pulls only that district's own figures."""
    sold = m.get("sold") or {}
    lst = m.get("listings") or {}
    if not sold.get("ok"):
        return None
    rec = sold.get("recency") or {}
    sold_med = _f(sold.get("median_price"))
    if not sold_med:
        return None
    ask_med = _f(lst.get("asking_median")) if lst.get("ok") else None
    gap = round((ask_med / sold_med - 1) * 100) if (ask_med and sold_med) else None
    avail = lst.get("available_n") or 0
    stuck = lst.get("stuck_n") or 0
    stuck_share = round(stuck / avail * 100) if avail else None
    return {
        "city": m["city"]["name"],
        "series": m["city"]["series"],
        "city_slug": m["city"]["slug"],
        "country": m["city"].get("country", ""),
        "district": m["district"],
        "slug": m["slug"],
        "generated_at": m.get("generated_at"),
        "sold_median": int(sold_med),
        "psm_median": int(_f(sold.get("psm_median"))) if sold.get("psm_median") else None,
        "sales_12m": rec.get("last_12m"),
        "on_market": lst.get("n") if lst.get("ok") else None,
        "asking_median": int(ask_med) if ask_med else None,
        "asking_gap_pct": gap,
        "mean_dom": lst.get("mean_dom") if lst.get("ok") else None,
        "available_n": avail or None,
        "stuck_n": stuck or None,
        "stuck_share_pct": stuck_share,
        "under_offer_n": lst.get("under_offer_n") if lst.get("ok") else None,
    }


def gather_study(*, store_mod=None):
    """Build the canonical study model from every published district's stored model.

    Returns {ok: False, reason} when there is nothing to aggregate, else a dict carrying
    the aggregate medians, the four league tables, the derived narrative figures, the per-
    district rows, the source references and the as-of date. Best-effort: never raises."""
    if store_mod is None:
        try:
            import store as store_mod
        except Exception:
            return {"ok": False, "reason": "no database"}

    rows = []
    try:
        metas = store_mod.list_blog_posts()
    except Exception as exc:                                # pragma: no cover
        return {"ok": False, "reason": f"db read failed: {exc}"}
    for meta in metas:
        post = store_mod.get_blog_post(meta["slug"], with_model=True)
        m = (post or {}).get("model") or {}
        if not m:
            continue
        r = _row_from_model(m)
        if r:
            rows.append(r)

    if len(rows) < 3:
        return {"ok": False, "reason": f"only {len(rows)} districts with a sold basis"}

    def table(key, reverse=True):
        have = [r for r in rows if r.get(key) is not None]
        return sorted(have, key=lambda r: r[key], reverse=reverse)

    def med(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(statistics.median(vals)) if vals else None

    cities = sorted({r["city"] for r in rows})
    countries = sorted({(r.get("country") or "").strip() for r in rows if (r.get("country") or "").strip()})
    by_dom = table("mean_dom", reverse=True)
    by_gap = table("asking_gap_pct", reverse=True)
    by_stuck = table("stuck_share_pct", reverse=True)
    by_psm = table("psm_median", reverse=True)

    neg_gap = [r for r in by_gap if (r.get("asking_gap_pct") or 0) < 0]
    as_of = max((r["generated_at"] for r in rows if r.get("generated_at")), default="")

    agg = {
        "n_districts": len(rows),
        "n_cities": len(cities),
        "cities": cities,
        "countries": countries,
        "as_of": as_of,
        "total_on_market": sum(r["on_market"] or 0 for r in rows),
        "total_sales_12m": sum(r["sales_12m"] or 0 for r in rows),
        "median_sold_median": med("sold_median"),
        "median_asking_gap_pct": med("asking_gap_pct"),
        "median_mean_dom": med("mean_dom"),
        "median_stuck_share_pct": med("stuck_share_pct"),
        "median_psm": med("psm_median"),
        # derived narrative figures (each traces to the rows above)
        "neg_gap_count": len(neg_gap),
        "dom_slowest": by_dom[0] if by_dom else None,
        "dom_fastest": by_dom[-1] if by_dom else None,
        "dom_spread_x": (round(by_dom[0]["mean_dom"] / by_dom[-1]["mean_dom"], 1)
                         if by_dom and by_dom[-1]["mean_dom"] else None),
        "psm_top": by_psm[0] if by_psm else None,
        "psm_bottom": by_psm[-1] if by_psm else None,
        "psm_spread_x": (round(by_psm[0]["psm_median"] / by_psm[-1]["psm_median"], 1)
                         if by_psm and by_psm[-1]["psm_median"] else None),
        "stuck_top": by_stuck[0] if by_stuck else None,
    }

    sentiment = _load_sentiment()

    refs = []
    order = ["pd_sold", "pd_listings"]
    for i, cid in enumerate(order, 1):
        if cid in brand._CITATIONS:
            pub, title, url = brand._CITATIONS[cid]
            refs.append({"n": i, "publisher": pub, "title": title, "url": url,
                         "accessed": f"Accessed {brand.DATESTR}"})
    if sentiment and sentiment.get("voices"):
        refs.append({"n": len(refs) + 1, "publisher": "Reddit",
                     "title": sentiment.get("source_label", "Public UK property forums"),
                     "url": "https://www.reddit.com/r/HousingUK/",
                     "accessed": f"Captured {sentiment.get('captured_at', brand.DATESTR)}"})

    return {
        "ok": True,
        "slug": STUDY_SLUG,
        "csv": STUDY_CSV,
        "generated_at": as_of,
        "agg": agg,
        "by_dom_slowest": by_dom,
        "by_asking_gap": by_gap,
        "by_stuck_share": by_stuck,
        "by_psm": by_psm,
        "rows": rows,
        "sentiment": sentiment,
        "references": refs,
    }


def write_csv(study, path):
    """Write the public raw-data download. One row per district, headers self-describing,
    so a journalist or analyst can re-run the league tables themselves."""
    import csv
    rows = study.get("rows") or []
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["city", "district", "sold_median_gbp", "price_per_sqm_gbp",
                    "sales_last_12m", "on_market", "asking_median_gbp", "asking_vs_sold_pct",
                    "avg_days_on_market", "available", "stuck_90d_plus", "stuck_share_pct",
                    "under_offer", "as_of"])
        for r in rows:
            w.writerow([r["city"], r["district"], r["sold_median"], r["psm_median"],
                        r["sales_12m"], r["on_market"], r["asking_median"],
                        r["asking_gap_pct"], r["mean_dom"], r["available_n"], r["stuck_n"],
                        r["stuck_share_pct"], r["under_offer_n"], r["generated_at"]])
    return path


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    s = gather_study()
    if not s.get("ok"):
        print("no study:", s.get("reason"))
    else:
        a = s["agg"]
        print(f"{a['n_districts']} districts / {a['n_cities']} cities as of {a['as_of']}")
        print(f"median DOM {a['median_mean_dom']} | median gap {a['median_asking_gap_pct']}% "
              f"| median stuck {a['median_stuck_share_pct']}% | median psm {a['median_psm']}")
        print(f"slowest {a['dom_slowest']['city']} {a['dom_slowest']['district']} "
              f"{a['dom_slowest']['mean_dom']}d vs fastest {a['dom_fastest']['city']} "
              f"{a['dom_fastest']['district']} {a['dom_fastest']['mean_dom']}d "
              f"({a['dom_spread_x']}x)")
        print(f"{a['neg_gap_count']}/{a['n_districts']} districts list below their sold median")
