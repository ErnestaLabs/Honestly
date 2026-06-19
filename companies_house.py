# -*- coding: utf-8 -*-
"""companies_house.py - the free Companies House REST client.

Companies House publishes a free company-information API: company search, the full company
profile, and the officers (directors). It is keyed (a free key), HTTP Basic auth with the key as
the username and an empty password.

What it does and does NOT do for us (honesty - so we never sell a toy):
  * It answers "tell me about THIS company" - profile, status, SIC, address, directors.
  * It does NOT know which company owns a given ADDRESS. The address->company link comes from the
    HMLR CCOD/OCOD ownership dataset (free bulk). So in the dossier, CCOD/OCOD gives the company
    number for a property; THIS module then turns that number into the landlord's identity,
    directors and (with CCOD) portfolio. CH alone, given only an address, cannot name an owner.

Contract (same as every client here): BEST-EFFORT. Never raises into the request path; on any
failure (no key, network, 404, rate limit) returns {"ok": False, "reason": ...}. The key is read
from the environment (COMPANIES_HOUSE_KEY) and NEVER logged.

  python companies_house.py <company_number|search terms>   # live smoke test (needs the env key)
"""
import base64
import json
import os
import sys
import urllib.parse
import urllib.request

BASE = "https://api.company-information.service.gov.uk"
KEY_ENV = "COMPANIES_HOUSE_KEY"


def _key(explicit=None):
    return (explicit or os.environ.get(KEY_ENV) or "").strip()


def _get(path, key, timeout=20):
    """GET a CH endpoint with Basic auth (key as username, empty password). Returns the parsed
    JSON dict, or raises - callers wrap. The key is used only in the Authorization header, never
    logged or returned."""
    token = base64.b64encode((key + ":").encode("utf-8")).decode("ascii")
    req = urllib.request.Request(BASE + path, headers={
        "Authorization": "Basic " + token,
        "Accept": "application/json",
        "User-Agent": "Honestly/1.0 (+usehonestly.co.uk)",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def search(query, key=None, n=5, timeout=20):
    """Company search. Returns {ok, items:[{company_number, title, status, address, type}]} or
    {ok:False, reason}. Never raises."""
    key = _key(key)
    if not key:
        return {"ok": False, "reason": "no COMPANIES_HOUSE_KEY set"}
    if not (query or "").strip():
        return {"ok": False, "reason": "empty query"}
    try:
        q = urllib.parse.urlencode({"q": query, "items_per_page": int(n)})
        data = _get("/search/companies?" + q, key, timeout)
    except Exception as e:
        return {"ok": False, "reason": str(e)[:160]}
    items = []
    for it in (data.get("items") or [])[:n]:
        items.append({
            "company_number": it.get("company_number"),
            "title": it.get("title"),
            "status": it.get("company_status"),
            "type": it.get("company_type"),
            "address": (it.get("address_snippet") or "").strip() or None,
        })
    return {"ok": True, "items": items, "source": "Companies House"}


def company(number, key=None, timeout=20):
    """Full company profile by number. Returns {ok, number, name, status, type, incorporated,
    dissolved, sic, address} or {ok:False, reason}. Never raises."""
    key = _key(key)
    if not key:
        return {"ok": False, "reason": "no COMPANIES_HOUSE_KEY set"}
    num = (str(number or "")).strip()
    if not num:
        return {"ok": False, "reason": "no company number"}
    try:
        d = _get("/company/" + urllib.parse.quote(num), key, timeout)
    except Exception as e:
        return {"ok": False, "reason": str(e)[:160]}
    ro = d.get("registered_office_address") or {}
    addr = ", ".join(x for x in [ro.get("address_line_1"), ro.get("locality"),
                                 ro.get("postal_code")] if x) or None
    return {"ok": True, "number": d.get("company_number"), "name": d.get("company_name"),
            "status": d.get("company_status"), "type": d.get("type"),
            "incorporated": d.get("date_of_creation"), "dissolved": d.get("date_of_cessation"),
            "sic": d.get("sic_codes") or [], "address": addr, "source": "Companies House"}


def officers(number, key=None, n=20, timeout=20):
    """Active directors/officers for a company. Returns {ok, directors:[{name, role, appointed}]}
    or {ok:False, reason}. Never raises."""
    key = _key(key)
    if not key:
        return {"ok": False, "reason": "no COMPANIES_HOUSE_KEY set"}
    num = (str(number or "")).strip()
    if not num:
        return {"ok": False, "reason": "no company number"}
    try:
        d = _get("/company/" + urllib.parse.quote(num) + "/officers?items_per_page=" + str(int(n)),
                 key, timeout)
    except Exception as e:
        return {"ok": False, "reason": str(e)[:160]}
    out = []
    for it in (d.get("items") or []):
        if it.get("resigned_on"):
            continue                       # active officers only
        out.append({"name": it.get("name"), "role": it.get("officer_role"),
                    "appointed": it.get("appointed_on")})
    return {"ok": True, "directors": out[:n], "source": "Companies House"}


def landlord(number, key=None, timeout=20):
    """The landlord card for a corporate owner: profile + active directors, combined. This is what
    the dossier renders once CCOD/OCOD has linked a property to a company number. Returns
    {ok, name, status, type, incorporated, address, directors:[names]} or {ok:False, reason}."""
    prof = company(number, key=key, timeout=timeout)
    if not prof.get("ok"):
        return prof
    offs = officers(number, key=key, timeout=timeout)
    prof = dict(prof)
    prof["directors"] = [o["name"] for o in (offs.get("directors") or []) if o.get("name")]
    return prof


def main():
    arg = " ".join(sys.argv[1:]) or "09446232"
    if not _key():
        print(f"Set {KEY_ENV} in the environment first (the key is never read from a file here).")
        return
    # a bare number -> profile + officers; otherwise a search
    if arg.isalnum() and any(c.isdigit() for c in arg) and len(arg) <= 10 and " " not in arg:
        print(json.dumps(landlord(arg), indent=2)[:1500])
    else:
        print(json.dumps(search(arg), indent=2)[:1500])


if __name__ == "__main__":
    main()
