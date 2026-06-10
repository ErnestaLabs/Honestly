# Project brief for Hermes

> **⚠️ This file is a pointer.** The canonical operating instructions for Hermes
> (the @usehonestly_bot front-of-house agent) live in **`HERMES_PROMPT.md`** in
> this same directory. Read that file for the full system prompt: role, tools,
> glass-box chain, audio walkthrough, constraints, voice, and live facts.

**What changed:** HERMES_PROMPT.md now supersedes this brief. It reflects the
current live state (103 tests, Voxtral audio walkthrough, NTSELAT compliance
starter, schools + Ofsted integration). Keeping two docs in sync is error-prone
— HERMES_PROMPT.md is the single source of truth for how Hermes operates.

**Project root:** `C:\Users\Hello\propertydata`
**Live host:** `root@187.77.100.209`, systemd unit `honestly.service`
**Bot:** [@usehonestly_bot](https://t.me/usehonestly_bot) - Telegram

You are connected to **Honestly**: an honest, automated UK property-valuation
Telegram bot. One address in, one evidence-backed valuation out - no black-box
number, the comparable sales and the working are shown. Built on the PropertyData
API, with Google Maps (Street View, routes) and BoE/ONS macro data. Pure Python
stdlib over the raw Telegram Bot API - no web framework, no third-party runtime deps
except `fpdf2` (PDF) and `paramiko` (deploy only).

---

## What it does (the product)

A user sends an address, picks who they are (**vendor / buyer / agent**), answers a
short intake wizard (beds, baths, condition, investment y/n, and a typed quote/asking
figure), and gets a mobile-native valuation: one assessed range anchored on sold
evidence, steered within a tight, disclosed cap by the live market. The number is the
same for everyone; what differs by audience is what you *do* with it (see `products.py`).

**The honesty is the product.** Sold prices (HM Land Registry, the floor of fact) anchor
value; a condition-adjusted AVM and a bounded live-market adjustment steer it to what the
market will pay today. Asking prices are positioning, never evidence - they are never used
to value. Every input traces to a free, verifiable source.

---

## Monetisation (Telegram Stars only - XTR)

In-app digital goods MUST use Telegram Stars (`currency="XTR"`, `provider_token=""`).
Never swap in a card/provider-token processor - it is non-compliant for digital goods.

- **First valuation per user = the FULL kit, free.** A taste of everything.
- **£9.99/mo membership (⭐650) = the BASE cost of USING the service.** Membership does
  NOT make valuations free.
- On top of the base, a **per-valuation ladder** (Stars = £ x 60):
  - £2.50 (⭐150) - valuation PDF only
  - £3.50 (⭐210) - + interactive HTML report
  - £5.00 (⭐300) - + action plan + door-knock route / 20 mapped targets
  - £7.50 (⭐450) - + ready-to-send email template
- Only the **PROPHET** comp code (the owner) gets the full kit free, every time.

Entitlements live in `entitlements.json`: `comp` (permanent free), `sub_until` (ISO),
`free_credits`, `first_done` (free-taste used). Redeem codes: `PROPHET` (comp),
`TAUK` (one free credit).

---

## Architecture / key files

| File | Role |
|---|---|
| `bot.py` | **Entry point.** Telegram long-poll loop, intake wizard, Stars invoicing, entitlements, delivery. Run: `python bot.py` (needs `TELEGRAM_BOT_TOKEN`). |
| `engine.py` | The valuation engine. `engine.value(address, key, beds, finish, investment, asking, quoted)` -> result dict. `engine.summary(r, audience, ...)` -> audience-framed figures. |
| `appraise.py` | Lower-level appraisal math, comp selection, condition discounting, and `interactive_chart()` (the tap-interactive HTML companion). |
| `report.py` | `build(r, audience, slug, interactive=True)` -> `(pdf_path, html_path)`. The branded PDF + HTML companion. `interactive=False` for PDF-only tiers (no HTML, no false "attached chart" claim). |
| `products.py` | Audience-specific deliverables: `target_listings`, `plan_of_action`, `email_template`. |
| `maps_tools.py` | Server-side Google Maps: `geocode`, `street_view`, `static_map`, `route` (optimised order), `places_search`, and `directions_url` (KEYLESS shareable route link). |
| `cardimg.py` | The figures "card" image. |
| `macro.py` / `macro_live.py` | BoE base rate + ONS HPI context; `macro_live.py --refresh` warms the cache (`macro_live_cache.json`). |
| `server.py` | Optional web surface / Telegram Mini App over the same `engine.summary()`. Not required for the bot. |
| `test_bot.py` | The test suite. 85 tests. Run: `python -m unittest test_bot` (set `PYTHONIOENCODING=utf-8`). |
| `_deploy_vps.py` | Deploy tool. `python _deploy_vps.py push` (code-only), `status`, `diag`. |

State/data: `entitlements.json` (users), `vrules.json`, `macro_live_cache.json`, and many
`cr_*.json` / `scan_*.json` working datasets. The `*.md` files prefixed with `CASE_`,
`DECISION_`, `valuation_*`, `appraisal_*` are working analysis artifacts, not code.

---

## How to run / test / deploy

```bash
# run the bot locally (reads .env)
python bot.py

# full test suite (must stay green - currently 85 passing)
PYTHONIOENCODING=utf-8 python -m unittest test_bot

# deploy code to the VPS (pushes .py only, warms macro cache, restarts service)
python _deploy_vps.py push
python _deploy_vps.py status     # health + recent logs
python _deploy_vps.py diag       # egress + foreground startup probe
```

Python on this machine: `C:\Users\Hello\AppData\Local\Programs\Python\Python313\python.exe`.

---

## HARD CONSTRAINTS - do not violate

1. **Secrets stay in `.env`, never in code, never echoed, never deployed.**
   `TELEGRAM_BOT_TOKEN`, `PROPERTYDATA_KEY`, `GOOGLE_MAPS_API_KEY` live only in
   `C:\Users\Hello\propertydata\.env`. The deploy tool has a hard block: `.env` is
   NEVER in its upload list. Same for the password files (`.vps_pw`, `.vps_secret`).
2. **The Google Maps API key is UNRESTRICTED and server-side ONLY.** It must NEVER
   appear in anything a user receives. User-facing maps use the KEYLESS
   `maps_tools.directions_url()` (a plain `google.com/maps/dir/?api=1&...` link) -
   never an embedded key, never a JS map that needs one.
3. **Digital goods = Telegram Stars (XTR), empty provider_token.** No card processors.
4. **No em dashes anywhere in copy or output.** Use hyphens. (The only em dash allowed
   is in `report.py`'s `_SUBST` sanitiser, which strips them.)
5. **Membership is the base, not free valuations.** The ladder is charged on top. Only
   `comp` (PROPHET) is free every time.
6. **Keep `test_bot.py` green** before any deploy.
7. **Do not read or transmit** `_PRIVATE_notes_DO_NOT_SEND.md` or anything `_PRIVATE*`.

---

## Current state (as of this brief)

Live and healthy. Latest deploy shipped: interactive keyless Google Maps route links
(replacing static map pictures), a genuinely tap-interactive HTML chart with an honest
PDF cross-reference, the corrected membership-on-top pricing, and condition options that
discount below-average homes. All 85 tests green.
