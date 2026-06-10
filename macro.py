#!/usr/bin/env python3
"""macro.py - forward-looking market context. KNOWN, DATED FACTS only.

A home is worth what the market will pay, and what buyers will pay is shaped by
the cost of borrowing and the tax on the purchase. We do NOT forecast those into
the valuation figure - a number you cannot defend is worthless. Instead we surface
the scheduled, factual macro backdrop *next to* the figure, so a vendor or buyer
reads the number in the context of what is actually coming.

UPDATE THIS FILE. Every figure carries the date a human last checked it and the
source. When a rate decision passes or a fiscal event lands, edit AS_OF and the
numbers below. Nothing here is scraped at runtime: a wrong macro claim would break
the trust the whole product is built on, so a human keeps it honest. If the data
goes stale (older than ~6 weeks) the forward-looking lines self-suppress.

Sources:
  Bank Rate / MPC dates - https://www.bankofengland.co.uk/monetary-policy
  SDLT rates (England & NI) - https://www.gov.uk/stamp-duty-land-tax
"""
from datetime import date

# -- last reviewed by a human. Bump this whenever you edit the figures below. --
AS_OF = date(2026, 6, 6)
STALE_DAYS = 45

# ---- Bank of England Bank Rate ------------------------------------------------
BASE_RATE = 3.75                 # %, held since December 2025
NEXT_MPC = date(2026, 6, 18)     # next scheduled MPC decision (announced ~noon)
RATE_LEAN = "hold"               # market-implied lean: 'hold' | 'cut' | 'hike'
RATE_LEAN_DETAIL = ("a hold, with an outside cut to 3.50% if CPI cools")

# ---- Stamp Duty Land Tax (England & Northern Ireland) -------------------------
# Standard residential bands and first-time-buyer relief. Unchanged since 1 Apr 2025.
SDLT_BANDS = [(125_000, 0.0), (250_000, 0.02), (925_000, 0.05),
              (1_500_000, 0.10), (float("inf"), 0.12)]
SDLT_FTB_NIL = 300_000           # first-time buyers pay nothing up to here
SDLT_FTB_CEILING = 500_000       # no first-time-buyer relief above here
SDLT_FTB_BANDS = [(300_000, 0.0), (500_000, 0.05)]


def _stale():
    return (date.today() - AS_OF).days > STALE_DAYS


def _banded(price, bands):
    """Marginal-rate stamp duty across a band table."""
    tax, lo = 0.0, 0
    for hi, rate in bands:
        if price > lo:
            tax += (min(price, hi) - lo) * rate
            lo = hi
        else:
            break
    return int(round(tax))


def sdlt(price, first_time=False):
    """The actual SDLT a buyer pays on this price. England & NI, single dwelling,
    replacing a main residence (no 5% second-home surcharge)."""
    if first_time and price <= SDLT_FTB_CEILING:
        return _banded(price, SDLT_FTB_BANDS)
    return _banded(price, SDLT_BANDS)


def _rate_note():
    base = f"Bank Rate has held at {BASE_RATE:.2f}% since December 2025."
    if not _stale() and NEXT_MPC >= date.today():
        when = f"{NEXT_MPC.day} {NEXT_MPC.strftime('%b %Y')}"   # platform-safe (no %-d)
        return (f"{base} The next decision is {when}; "
                f"markets lean to {RATE_LEAN_DETAIL}. Steady borrowing costs keep "
                f"mortgage affordability flat - supportive of demand, not a tailwind.")
    return f"{base} Borrowing costs are steady, which keeps affordability flat - supportive of demand, not a tailwind."


def outlook(price=None, audience="agent"):
    """Structured forward-context for one valuation. Plain data, no HTML.
    Does NOT alter the figure - it sits beside it. Returns None if nothing to say."""
    upcoming = NEXT_MPC >= date.today() and not _stale()
    out = {
        "as_of": AS_OF.isoformat(),
        "stale": _stale(),
        "base_rate": BASE_RATE,
        "next_mpc": NEXT_MPC.isoformat() if upcoming else None,
        "next_mpc_str": f"{NEXT_MPC.day} {NEXT_MPC.strftime('%b')}" if upcoming else None,
        "rate_note": _rate_note(),
        "lines": [_rate_note()],
    }
    if price:
        std = sdlt(price, first_time=False)
        ftb = sdlt(price, first_time=True)
        out["sdlt_standard"] = std
        out["sdlt_ftb"] = ftb if price <= SDLT_FTB_CEILING else None
        # property-specific stamp-duty line
        if price <= SDLT_FTB_CEILING and ftb < std:
            out["sdlt_note"] = (f"Stamp duty at this level is about {_money(std)} "
                                f"(first-time buyers: {_money(ftb)}).")
        else:
            out["sdlt_note"] = f"Stamp duty at this level is about {_money(std)}."
        out["lines"].append(out["sdlt_note"])
        # the cliff edges that genuinely move buyer behaviour near a threshold
        if SDLT_FTB_NIL < price <= SDLT_FTB_CEILING:
            out["lines"].append(
                f"This sits above the {_money(SDLT_FTB_NIL)} first-time-buyer nil-rate band, "
                f"so first-timers pay 5% on the slice above {_money(SDLT_FTB_NIL)} - it narrows the first-time-buyer pool.")
        elif price > SDLT_FTB_CEILING:
            out["lines"].append(
                f"Above {_money(SDLT_FTB_CEILING)} there is no first-time-buyer relief at all - "
                f"the buyer pool here is movers and investors, not first-timers.")
    return out


def _money(n):
    return f"£{int(round(n)):,}"


if __name__ == "__main__":
    import json, sys
    p = int(sys.argv[1]) if len(sys.argv) > 1 else 415000
    print(json.dumps(outlook(p), indent=2))
