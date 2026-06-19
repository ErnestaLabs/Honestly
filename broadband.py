#!/usr/bin/env python3
"""broadband.py - fixed-broadband availability context via Ofcom Connected Nations open data.

Ofcom publishes the Connected Nations report annually (and a Spring interim update), which
includes a bulk postcode-level CSV of fixed-broadband coverage across the UK. The most recent
release is Connected Nations 2024, with fixed coverage data from July 2024:

  https://www.ofcom.org.uk/phones-and-broadband/coverage-and-speeds/connected-nations-2024/data-downloads-2024

The postcode file (202407-fixed-coverage-postcodes-r01.zip, ~32 MB) contains per-postcode
columns for superfast (>=30 Mbit/s download), ultrafast (>=100 Mbit/s), and predicted speeds.
It is published under the Open Government Licence v3.0.

WHY A LIVE PER-POSTCODE LOOKUP IS NOT POSSIBLE (honest answer):
  Ofcom publishes this data ONLY as a bulk ZIP download — there is no free, documented,
  per-postcode REST API endpoint. The Ofcom Coverage Checker website (checker.ofcom.org.uk)
  provides an interactive UI but does not expose a public API. The Ofcom developer portal
  (api.ofcom.org.uk) requires an account and is not a free open data endpoint.

  Downloading and loading the 32 MB ZIP file on every call would be impractical at runtime.
  The correct production approach is to ingest the CSV once into a local SQLite/Postgres table
  and query it. Until that ingestion pipeline is built, this module returns an honest
  {"ok": False, "reason": ...} so the UI can render a 'not available' state without blocking.

Surfaces:
  lookup(postcode) -> see docstring below

CLI:
  python broadband.py SE15 6JH
"""
import urllib.request, urllib.error

_SRC = "Ofcom Connected Nations 2024 (OGL v3.0)"
_URL = "https://www.ofcom.org.uk/phones-and-broadband/coverage-and-speeds/connected-nations-2024/data-downloads-2024"
_UA  = {"User-Agent": "honestly-broadband/1.0 (+https://t.me/usehonestly_bot)"}

_NOT_AVAILABLE_REASON = (
    "Ofcom broadband coverage is published as a bulk Connected Nations CSV "
    "(no free per-postcode lookup API). Ingest the postcode CSV into a local "
    "database to enable live lookups."
)


def lookup(postcode):
    """Return fixed-broadband availability for a UK postcode from free Ofcom open data.

    Returns {"ok": True, "max_download_mbps": int|None, "max_upload_mbps": int|None,
             "ultrafast": bool|None, "superfast": bool|None,
             "source": str, "url": str, "raw": dict} on success,
             else {"ok": False, "reason": str}. Never raises.

    Current status: Ofcom's Connected Nations dataset is published only as a bulk postcode
    CSV (not a live API). Until the ingestion pipeline is built, this function returns the
    honest not-available response defined above. The public contract (return shape) is stable
    so the UI can wire the broadband panel now and light it up when ingestion is ready.
    """
    if not postcode or not str(postcode).strip():
        return {"ok": False, "reason": "no postcode supplied"}
    return {"ok": False, "reason": _NOT_AVAILABLE_REASON}


if __name__ == "__main__":
    import sys, json
    pc = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "SE15 6JH"
    result = lookup(pc)
    print(json.dumps(result, indent=2, ensure_ascii=False))
