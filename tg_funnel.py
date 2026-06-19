#!/usr/bin/env python3
"""tg_funnel.py - the Telegram re-engagement / micro-sell engine.

A bot user is a persistent channel: once someone values a property we hold their chat_id,
so a delivered Lite report does not have to be a one-shot paywall. It becomes a sequence of
honest, value-led nudges and small Pro unlocks - the in-chat analog of email_funnel.py.

Honesty contract (same as everywhere): a nudge NEVER invents a figure or a per-factor
valuation penalty. It offers a real Pro piece (the negotiation brief, the value-unlock plan,
the scenario matrix, the evidence room) or simply tempts them back for another free Lite
valuation. No fabricated urgency, no fake "your home dropped 4%".

Safety + respect (so we keep the channel and stay the right side of Telegram + PECR):
  - DRY_RUN by default: nothing is sent until HONESTLY_TG_LIVE=1 is set. Building/testing
    this module never messages a real user.
  - Opt-out is permanent: a /stop records store.tg_optout(chat_id) and is checked before
    every send; opted-out chats are skipped and their pending nudges cancelled.
  - Frequency cap: at most one nudge per TG_MIN_GAP_HOURS (default 16h) per chat.
  - Quiet hours: only send when the local hour is in [TG_QUIET_START, TG_QUIET_END)
    (default 8-22). 'Ping any time' is tunable via env - but not 3am by default, because
    that is how a bot gets reported and the channel lost.

Surfaces:
  start(chat_id, token, audience)   queue the nudge sequence for one delivered report
  run_due(now=None, sender=None)    send every nudge now due (cron/loop calls this)
  stop(chat_id)                     opt this chat out (wire to a /stop command)

CLI:  python tg_funnel.py selftest
"""
import os
import time

import store

DAY = 86400.0
HOUR = 3600.0


def _live():
    return os.environ.get("HONESTLY_TG_LIVE", "") in ("1", "true", "True", "yes")


def _hours(name, default_hours):
    try:
        v = os.environ.get(name)
        return float(v) * HOUR if v else default_hours * HOUR
    except Exception:
        return default_hours * HOUR


# step -> (kind, default-delay-hours-after-delivery). Tunable via env for testing/aggression.
SEQUENCE = [
    (1, "nudge_primary",  "TG_D1_HOURS", 3),     # a few hours later: the audience's key unlock
    (2, "nudge_scenario", "TG_D2_HOURS", 20),    # next morning: the scenario matrix angle
    (3, "nudge_freeback", "TG_D3_HOURS", 72),    # +3 days: free re-engagement (no sell)
    (4, "nudge_last",     "TG_D4_HOURS", 168),   # +7 days: last honest nudge + full Pro
]


def _schedule(now):
    return [(step, kind, now + _hours(env, dh)) for (step, kind, env, dh) in SEQUENCE]


# ------------------------------------------------------------- honest offers
# Each offer is a REAL Pro piece (or a free re-engagement). Prices are pounds; the bot turns
# them into a Stars invoice. The button carries a callback the bot maps to that invoice -
# the purchase flow itself stays in bot.py; this module only tempts and links.
OFFERS = {
    "negotiation": ("Negotiation brief",
                    "the evidence pack to justify a lower offer - every comparable, the gaps, the ask"),
    "valueplan":   ("Value-unlock plan",
                    "the £ return on each improvement before you list, ranked by payback"),
    "scenarios":   ("Scenario matrix",
                    "the same sold evidence re-run at any asking price, so you can see the trade-off"),
    "evidence":    ("Evidence room",
                    "every comparable with its exclusion reason and the full price-influence ledger"),
    "pro":         ("Full Pro report",
                    "the impact dashboard, positioning strategy, scenarios and evidence room - all of it"),
}


def _primary_offer(audience):
    a = (audience or "").lower()
    if a == "buyer":
        return "negotiation"
    if a in ("vendor", "seller", "agent"):
        return "valueplan"
    return "pro"


def _kb(label, audience):
    """One honest call-to-action button. It routes to the REAL existing Decision pack via the
    bot's own buy callback (buy:<audience>:full -> the Stars invoice that already ships) - we
    never advertise a micro-SKU that does not exist. A 'mute these' opt-out is always one tap
    away (callback tg_stop -> store.tg_optout)."""
    aud = (audience or "vendor").lower()
    if aud not in ("vendor", "buyer", "agent"):
        aud = "vendor"
    return {"inline_keyboard": [
        [{"text": label, "callback_data": f"buy:{aud}:full"}],
        [{"text": "No thanks, mute these", "callback_data": "tg_stop"}],
    ]}


def _slug_label(slug):
    """A followed-area slug ('london-se15' / 'se15') -> a readable label ('SE15')."""
    parts = [p for p in str(slug or "").replace("/", "-").split("-") if p]
    return (parts[-1].upper() if parts else "your area")


def _ctx(row):
    """Build the small context a nudge needs from the appraisal behind this queued row. For an
    area-refresh nudge the 'token' is a followed-area slug, not an appraisal token, so there is no
    appraisal to read - we surface the area label instead."""
    token = row.get("token")
    if row.get("kind") == "nudge_area_refresh":
        return {"address": "your property", "district": _slug_label(token),
                "audience": row.get("audience"), "token": token}
    ap = (store.get_appraisal(token) if token else None) or {}
    summ = ap.get("summary") or ap.get("summary_json") or {}
    if isinstance(summ, str):
        try:
            import json as _j
            summ = _j.loads(summ)
        except Exception:
            summ = {}
    address = ap.get("address") or summ.get("address") or "your property"
    short = str(address).split(",")[0]
    pc = ap.get("postcode") or summ.get("postcode") or ""
    district = ap.get("postcode_district") or (store.district_of(pc) if pc else "") or "your area"
    audience = row.get("audience") or ap.get("audience") or summ.get("audience")
    return {"address": short, "district": district, "audience": audience, "token": token}


def _render(kind, ctx):
    """Return (text, keyboard) for a nudge. Honest, value-led; no fabricated figures."""
    addr, district, aud, token = ctx["address"], ctx["district"], ctx["audience"], ctx["token"]
    if kind == "nudge_primary":
        offer = _primary_offer(aud)
        name, desc = OFFERS[offer]
        verb = ("Still weighing up your offer on" if offer == "negotiation"
                else "Still deciding how to price" if offer == "valueplan"
                else "Still thinking about")
        return (f"{verb} <b>{addr}</b>? Your free report proved the number - the "
                f"<b>{name}</b> is {desc}. It is built from the exact same evidence, nothing invented.",
                _kb(f"Unlock the {name}", aud))
    if kind == "nudge_scenario":
        return (f"One thing the free report does not show for <b>{addr}</b>: the trade-off "
                f"between asking prices. The <b>Scenario matrix</b> re-runs the same sold "
                f"evidence at any price you pick, so you can see what each one likely costs you "
                f"in time on market - real evidence, not a guess.",
                _kb("Unlock the Scenario matrix", aud))
    if kind == "nudge_freeback":
        return (f"No pressure on the Pro report. But fresh sales land in <b>{district}</b> every "
                f"week, and your free valuation moves with them. Want an up-to-date one for "
                f"<b>{addr}</b> or any other address? Just send it - still free, still every "
                f"comparable with its HM Land Registry link.",
                {"inline_keyboard": [[{"text": "No thanks, mute these", "callback_data": "tg_stop"}]]})
    if kind == "nudge_last":
        name, desc = OFFERS["pro"]
        return (f"Last one from me on <b>{addr}</b>. If you want to act on the number rather "
                f"than just know it, the <b>{name}</b> is {desc}. Either way the free report is "
                f"yours to keep. Reply /stop and I will not nudge you again.",
                _kb(f"Unlock the {name}", aud))
    if kind == "nudge_area_refresh":
        # the retention loop for a FOLLOWED area: fresh sold evidence has landed, so the free
        # valuation moves with it. Honest - we never quote a fabricated new figure, we invite a
        # free re-run. The only button is the mute (the value is the free refresh itself).
        return (f"Fresh sales have landed in <b>{district}</b>. Your free Honestly valuation moves "
                f"with the local evidence - want an up-to-date figure for your property, or any "
                f"address in {district}? Just send it. Still free, still every comparable with its "
                f"HM Land Registry link.",
                {"inline_keyboard": [[{"text": "No thanks, mute these", "callback_data": "tg_stop"}]]})
    return (f"Your valuation for <b>{addr}</b> is ready whenever you need it.", None)


def start(chat_id, token, audience=None, *, now=None):
    """Queue the nudge sequence for one delivered Lite report. Idempotent per (chat, token);
    a no-op if the chat has opted out. Returns {ok, queued}."""
    if store.is_tg_optout(chat_id):
        return {"ok": False, "reason": "opted_out", "queued": 0}
    if store.has_tg_queue(chat_id, token):
        return {"ok": True, "queued": 0, "note": "already_queued"}
    now = time.time() if now is None else now
    n = 0
    for step, kind, when in _schedule(now):
        if store.enqueue_tg(chat_id, token, audience, step, kind, when):
            n += 1
    store.log_event("tg_funnel_start", token=str(chat_id), detail={"appraisal": token, "queued": n})
    return {"ok": True, "queued": n}


def stop(chat_id):
    """Opt a chat out of all nudges (wire to a /stop command or the 'mute' button)."""
    return store.tg_optout(chat_id)


def _read_follows():
    """(chat_id, slug) pairs from the bot entitlements 'follows' lists - who follows which area.
    Lazy + best-effort (the bot writes these via follow_area)."""
    out = []
    try:
        import bot
        ent = bot.load_ent() or {}
        for uid, rec in ent.items():
            cid = rec.get("chat_id") or uid
            for slug in (rec.get("follows") or []):
                if slug:
                    out.append((str(cid), slug))
    except Exception as e:
        store._log("tg _read_follows:", str(e)[:160])
    return out


def nudge_followed_areas(now=None, follows=None, fresh_at=None):
    """The retention loop's missing half: enqueue an area-refresh nudge for each followed area whose
    evidence is NEWER than the last nudge we sent that user for it. Re-uses run_due for the actual
    send (so opt-out, the frequency cap and quiet hours all still apply). Honest + non-spammy:
      - skips opted-out chats and any area with a nudge still pending,
      - only fires when the area's freshness timestamp beats the last area nudge we sent,
      - the area's freshness comes from its published blog post's updated_at (the 'new evidence'
        signal), injectable as fresh_at(slug)->ts for tests.
    Returns {areas, enqueued}. Call it from the same cron/loop that calls run_due."""
    now = time.time() if now is None else now
    follows = _read_follows() if follows is None else follows
    if fresh_at is None:
        def fresh_at(slug):
            post = store.get_blog_post(slug, with_html=False)
            return (post or {}).get("updated_at") if post else None
    enq = 0
    for chat_id, slug in follows:
        if store.is_tg_optout(chat_id):
            continue
        if store.has_pending_tg(chat_id, slug):          # one pending area nudge per area at a time
            continue
        fresh = fresh_at(slug)
        if not fresh:
            continue                                     # no published evidence to point at yet
        last = store.last_area_nudge_at(chat_id, slug)
        if last is not None and float(fresh) <= float(last):
            continue                                     # nothing new since we last nudged them
        if store.enqueue_tg(chat_id, slug, None, 0, "nudge_area_refresh", now):
            enq += 1
    if enq:
        store.log_event("tg_area_refresh_enqueued", token="", detail={"enqueued": enq})
    return {"areas": len(follows), "enqueued": enq}


def _within_quiet_hours(now):
    start_h = int(float(os.environ.get("TG_QUIET_START", "8")))
    end_h = int(float(os.environ.get("TG_QUIET_END", "22")))
    h = time.localtime(now).tm_hour
    return start_h <= h < end_h


def _send_live(chat_id, text, keyboard):
    """Real send via the bot. Imported lazily so tests never need the bot/token."""
    import bot
    return bot.say(chat_id, text, keyboard=keyboard)


def run_due(now=None, sender=None, limit=200):
    """Send every nudge now due. Honors opt-out, the per-chat frequency cap and quiet hours.
    sender(chat_id, text, keyboard) is injectable (tests pass a capture); when omitted, a real
    send is used ONLY if HONESTLY_TG_LIVE=1 - otherwise this is a dry run that marks intended
    sends without messaging anyone. Returns {due, sent, skipped, dry}."""
    now = time.time() if now is None else now
    dry = sender is None and not _live()
    if sender is None:
        sender = (lambda cid, t, kb: {"dry": True}) if dry else _send_live
    min_gap = _hours("TG_MIN_GAP_HOURS", 16)
    rows = store.due_tg(now=now, limit=limit)
    sent = skipped = 0
    for row in rows:
        chat_id = row["chat_id"]
        if store.is_tg_optout(chat_id):
            store.mark_tg(row["id"], "cancelled"); skipped += 1; continue
        if not _within_quiet_hours(now):
            skipped += 1; continue                      # leave pending; a later run picks it up
        last = store.last_tg_sent_at(chat_id)
        if last is not None and (now - last) < min_gap:
            skipped += 1; continue                      # frequency cap: try again next run
        text, kb = _render(row["kind"], _ctx(row))
        try:
            sender(chat_id, text, kb)
            store.mark_tg(row["id"], "sent", sent_at=now)
            store.log_event("tg_nudge_sent", token=str(chat_id),
                            detail={"kind": row["kind"], "appraisal": row["token"], "dry": dry})
            sent += 1
        except Exception as e:
            store.mark_tg(row["id"], "failed")
            store._log("tg run_due send:", str(e)[:200])
    return {"due": len(rows), "sent": sent, "skipped": skipped, "dry": dry}


def _selftest():
    """Dry-run the whole engine in a throwaway DB: queue a sequence, fast-forward, capture the
    sends, prove ordering, the frequency cap, quiet hours and a permanent opt-out. No network."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store.DB_PATH = path
    store._INITED = False
    # deterministic: no quiet-hours/gap interference for the ordering assertions
    os.environ.update({"TG_QUIET_START": "0", "TG_QUIET_END": "24", "TG_MIN_GAP_HOURS": "0"})

    t0 = 1_700_000_000.0
    tok = store.record_appraisal({"address": "58 Cronin Street, London SE15 6JH",
                                  "guide_value_str": "Offers Over £515,000", "audience": "vendor"},
                                 address="58 Cronin Street, London SE15 6JH",
                                 postcode="SE15 6JH", audience="vendor")
    chat = "99001"
    s = start(chat, tok, "vendor", now=t0)
    assert s["queued"] == len(SEQUENCE), s

    captured = []
    sender = lambda cid, text, kb: captured.append((cid, text, kb))

    # nothing due yet (first nudge is +3h)
    r0 = run_due(now=t0 + 60, sender=sender)
    assert r0["sent"] == 0, r0

    # fast-forward past every delay, but the frequency cap is 0 here so all fire in order
    r1 = run_due(now=t0 + 8 * DAY, sender=sender)
    assert r1["sent"] == len(SEQUENCE), r1
    kinds = [c[1][:40] for c in captured]
    assert len(captured) == len(SEQUENCE), captured
    assert "58 Cronin Street" in captured[0][1]
    # the primary nudge for a vendor must offer the value-unlock plan, not a buyer brief
    assert "Value-unlock plan" in captured[0][1], captured[0][1]
    # honesty: no fabricated penalty language anywhere
    blob = " ".join(c[1] for c in captured).lower()
    for bad in ("penalty", "dropped 4%", "-4%", "applied to the value"):
        assert bad not in blob, bad
    # queue drained
    assert run_due(now=t0 + 9 * DAY, sender=sender)["due"] == 0

    # opt-out is permanent: re-queue, stop, and prove nothing sends
    tok2 = store.record_appraisal({"address": "1 Test Road"}, address="1 Test Road",
                                  postcode="SE15 6JH", audience="buyer")
    start(chat, tok2, "buyer", now=t0 + 10 * DAY)
    stop(chat)
    captured.clear()
    r2 = run_due(now=t0 + 30 * DAY, sender=sender)
    assert r2["sent"] == 0 and not captured, r2
    assert store.is_tg_optout(chat)

    # quiet hours: a fresh chat at 3am local must defer, not send
    tok3 = store.record_appraisal({"address": "2 Night Road"}, address="2 Night Road",
                                  postcode="SE15 6JH", audience="buyer")
    start("42", tok3, "buyer", now=t0)
    os.environ.update({"TG_QUIET_START": "8", "TG_QUIET_END": "22"})
    three_am = time.mktime(time.struct_time((2025, 6, 1, 3, 0, 0, 0, 0, -1)))
    captured.clear()
    r3 = run_due(now=three_am + 8 * DAY, sender=sender)
    assert r3["sent"] == 0 and r3["skipped"] >= 1, r3

    # --- the area-refresh retention loop (the missing half of follow_area) ---
    os.environ.update({"TG_QUIET_START": "0", "TG_QUIET_END": "24", "TG_MIN_GAP_HOURS": "0"})
    captured.clear()
    acid, follows = "70001", [("70001", "london-se15")]
    res = nudge_followed_areas(now=t0 + 40 * DAY, follows=follows, fresh_at=lambda s: t0 + 39 * DAY)
    assert res["enqueued"] == 1, res
    r4 = run_due(now=t0 + 40 * DAY + 60, sender=sender)
    assert r4["sent"] >= 1 and any("Fresh sales" in c[1] and "SE15" in c[1] for c in captured), (r4, captured)
    # nothing newer than the last nudge -> no re-nudge
    assert nudge_followed_areas(now=t0 + 41 * DAY, follows=follows,
                                fresh_at=lambda s: t0 + 39 * DAY)["enqueued"] == 0
    # newer evidence -> nudge again
    assert nudge_followed_areas(now=t0 + 42 * DAY, follows=follows,
                                fresh_at=lambda s: t0 + 41 * DAY)["enqueued"] == 1
    # an opted-out follower is never enqueued
    stop(acid)
    assert nudge_followed_areas(now=t0 + 50 * DAY, follows=follows,
                                fresh_at=lambda s: t0 + 49 * DAY)["enqueued"] == 0

    print("tg_funnel selftest OK:",
          f"{len(SEQUENCE)} nudges queue+fire in order, vendor->value-unlock, "
          "honesty clean, opt-out permanent, quiet-hours deferred, area-refresh loop fires on "
          "fresh evidence + respects opt-out.")
    try:
        os.remove(path)           # best-effort: Windows may still hold the sqlite handle
    except OSError:
        pass


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        _selftest()
    else:
        print(__doc__)
