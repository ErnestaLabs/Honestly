#!/usr/bin/env python3
"""verification.py - direct public-source verification panel.

No commercial same-data aggregators. This module describes facts already present in an
Honestly summary and identifies the public/direct source behind each one. It never moves
the valuation. Customer-facing statuses are positive: every row is included, either with a
source value or as a decision-check item.
"""


def _money(n):
    try:
        return "£" + f"{int(round(float(n))):,}"
    except Exception:
        return "Included as decision-check item"


def _value(v):
    return v if v not in (None, "", "-") else "Included as decision-check item"


def _row(fact, status, sources, values, note):
    return {
        "fact": fact,
        "status": status,
        "sources": sources,
        "values": values,
        "note": note,
    }


def build(d):
    """Build {ok, rows} from a summary dict.

    Rows are source labels and raw values only. Values that need legal/user confirmation
    are included as decision-check items rather than left blank.
    """
    if not isinstance(d, dict):
        return {"ok": False, "reason": "summary input not usable"}
    rows = []

    evidence = d.get("evidence") or []
    rows.append(_row(
        "Sold evidence",
        "Included",
        ["HM Land Registry Price Paid Data"],
        [{"source": "HMLR", "raw": f"{len(evidence)} proof/comparable row(s) shown"}],
        "Every row is a completed sale. HMLR transaction URIs are used where available; GOV.UK Price Paid Data is the fallback.",
    ))

    basis = d.get("lite_basis") or {}
    if basis:
        rows.append(_row(
            "Valuation basis",
            "Included",
            [basis.get("source") or "HM Land Registry Price Paid Data"],
            [
                {"source": "Type basis", "raw": _value(basis.get("type_basis"))},
                {"source": "Window", "raw": f"{basis.get('window_months')} months" if basis.get("window_months") else "Included as decision-check item"},
                {"source": "Evidence count", "raw": str(basis.get("n_evidence") or d.get("n_comps") or "Included as decision-check item")},
            ],
            basis.get("note") or "The valuation source path is disclosed beside the figure.",
        ))

    epc_reg = d.get("epc_register") or {}
    epc = d.get("epc")
    rows.append(_row(
        "EPC / floor area",
        "Included",
        [d.get("floor_area_source") or epc_reg.get("source") or "Public EPC register / Honestly public-EPC cache"],
        [
            {"source": "EPC", "raw": _value(epc if epc is not None else epc_reg.get("rating"))},
            {"source": "Floor area", "raw": _value(d.get("sqm") or epc_reg.get("floor_area_sqm"))},
        ],
        "EPC/floor area comes from the public EPC register, the public EPC cache, or a labelled public-EPC building proxy.",
    ))

    cross = d.get("crosscheck") or {}
    if cross:
        rows.append(_row(
            "Exact-postcode register cross-check",
            "Included",
            [cross.get("source") or "HM Land Registry Price Paid Data"],
            [
                {"source": "Postcode", "raw": _value(cross.get("postcode"))},
                {"source": "Count", "raw": str(cross.get("official_count") or "Included as decision-check item")},
                {"source": "Median", "raw": cross.get("official_median_str") or _money(cross.get("official_median"))},
            ],
            cross.get("note") or "Exact-postcode sales are shown as a verification cross-check, not blended into the figure.",
        ))

    conf = d.get("confidence") or {}
    if conf:
        rows.append(_row(
            "Confidence",
            "Included",
            ["Honestly confidence model"],
            [{"source": "Score", "raw": f"{conf.get('grade')} ({conf.get('score')}/100)"}],
            conf.get("note") or "Confidence combines evidence depth, public-fact completeness, agreement and stability.",
        ))

    return {"ok": bool(rows), "rows": rows}


def lines(d):
    ver = build(d)
    if not ver.get("ok"):
        return []
    out = []
    for row in ver.get("rows", []):
        vals = "; ".join(f"{v['source']}: {v['raw']}" for v in row.get("values", []))
        out.append(f"{row['fact']} — {row['status']} — {vals}")
    return out
