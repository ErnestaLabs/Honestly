#!/usr/bin/env python3
"""council_tax.py - council-tax band context (no external call, VOA-cited).

Material-information context that sits BESIDE the figure - never an input to the
valuation. The band itself comes from the resolved subject (it arrives via the data
provider). This module turns that band letter into honest, sourced context: the 1991
open-market value bracket the band represents in England, set by the Valuation Office
Agency. It does NOT invent the annual bill, which is set per billing authority and
would be a fabrication to assert without the council's own figure.

Source: Valuation Office Agency (VOA) council-tax bands (England, 1991 valuation date).

Surfaces:
  band_context(band, country="England") -> {ok, band, bracket_1991, note, lines:[...]}

CLI:
  python council_tax.py band C
  python council_tax.py selftest
"""
import sys, json

# England council-tax bands - 1991 open-market value brackets (VOA).
_ENGLAND = {
    "A": "up to GBP 40,000",
    "B": "GBP 40,001 to 52,000",
    "C": "GBP 52,001 to 68,000",
    "D": "GBP 68,001 to 88,000",
    "E": "GBP 88,001 to 120,000",
    "F": "GBP 120,001 to 160,000",
    "G": "GBP 160,001 to 320,000",
    "H": "over GBP 320,000",
}
_SRC = "Valuation Office Agency (VOA) council-tax bands, England (1991 valuation date)"


def band_context(band, country="England"):
    """Turn a council-tax band letter into its VOA 1991 value bracket + an honest note.
    Returns {ok, band, bracket_1991, note, lines} or {ok: False, reason}. Never raises."""
    if not band:
        return {"ok": False, "reason": "no council-tax band on record"}
    b = str(band).strip().upper()[:1]
    if country and country.lower() not in ("england", "uk", ""):
        return {"ok": True, "band": b, "bracket_1991": None,
                "note": "Bands outside England use different value brackets (Wales/Scotland).",
                "lines": [f"Council-tax band {b}."], "source": _SRC}
    bracket = _ENGLAND.get(b)
    if not bracket:
        return {"ok": False, "reason": f"unrecognised England band: {band}"}
    note = ("The band reflects what the property was worth on 1 April 1991, not today. "
            "The annual charge is set by the local billing authority and is not asserted here.")
    lines = [f"Council-tax band {b} - 1991 value bracket {bracket}.",
             "Set by the Valuation Office Agency; the annual bill is set by the local council."]
    return {"ok": True, "band": b, "bracket_1991": bracket, "note": note,
            "lines": lines, "source": _SRC}


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    if sys.argv[1] == "band":
        print(json.dumps(band_context(sys.argv[2]), indent=2, ensure_ascii=False))
    elif sys.argv[1] == "selftest":
        c = band_context("C")
        if c.get("ok"):
            print("council_tax ok | band", c["band"], "|", c["bracket_1991"])
        else:
            print("council_tax degraded:", c.get("reason"))
    else:
        print("unknown command:", sys.argv[1])


if __name__ == "__main__":
    main()
