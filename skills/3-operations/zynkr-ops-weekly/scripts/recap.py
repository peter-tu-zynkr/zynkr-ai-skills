#!/usr/bin/env python3
"""The Monday recap (SKB-044 Phase 2): what changed last week, what needs attention, what was
decided and what is blocked, read from the Weekly Ledger only, never the 331k-character Doc.

Like ledger.py, this script computes and the model executes: every step prints the exact MCP
calls, each with a path to save the tool's result to, word for word.

    recap.py start  --runner-week W [--config PATH]  -> the Weeks reads that decide what can be said
    recap.py blocks --dir D                           -> {"notice": true, ...} when last week never
                                                         closed out, else the block reads and the
                                                         Sales Pulse search
    recap.py pulse  --dir D                           -> the threads to fetch, newest first, or none
                                                         (SKB-091, SKB-096)
    recap.py build  --dir D --today YYYY-MM-DD        -> facts.json + a short summary for the TL;DR
    recap.py render --dir D --tldr tldr.json          -> subject, recipients, recap.html; TL;DR lines
                                                         that cite no real item # are dropped
    recap.py notice --dir D                           -> the owner-only "close-out did not run" mail
    recap.py --selftest

The recap covers the ISO week BEFORE the runner's week. Its subject uses the team's `WB m/d` label;
the ISO key never reaches a reader (references/wording.md). The state rules are zynkr-gm's
derive_state.py, the one copy every brief and recap shares.

SKB-091 adds this week's plan, per person, at most five lines in this order: the meeting's open
actions, items overdue or due within 14 days, P0/P1 items with no dates, then that person's next
steps from the Monday Sales Pulse mail. A line that cites no item # (or, from the Pulse, a deal) is
dropped. The Pulse is the one mail this script reads.

Exit codes are ledger.py's: 2 config or arguments · 3 input refused · 4 structure changed ·
6 a block does not match its Weeks row.
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta
from email.utils import parseaddr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
from ledger import Refuse, pad, parse_values, load_result, read_call, save_run, load_run, emit  # noqa: E402

DEFAULT_RULES = "~/.claude/skills/zynkr-gm/scripts/derive_state.py"
ITEM_NUM = re.compile(r"(?<![\d.])(\d{1,2}\.\d{2})(?![\d.])")
# The Monday Sales Pulse (09:30): its subject prefix and its "Next step this week" lines, whose shape
# /zynkr-gm parses too: `<name> - N of FLOOR cooking: <step 1>; <step 2>`.
PULSE_SUBJECT = "Zynkr Sales Pulse - week of"
# The search's page size, and so the most threads `pulse` fetches: newest first, the first real Pulse
# wins, because Gmail's `from:<domain>` also matches look-alike domains and display names, and one
# newer look-alike must not hide the Pulse (SKB-096).
PULSE_THREADS = 5
# What the CRM writes for a member with nothing to do this week; it is not a step.
PULSE_NO_STEP = "no step this week"


# Zynkr CRM mails it to the team list from its own sender (PLAT-076, from Mon 2026-11-02), so it lands
# in the Inbox, not in Sent; the claude.ai routine that sent it from the owner's account is off. The
# search names the owner's own domain, and only the thread's first message is read, only when its
# sender's address is on that domain exactly: parsed, never a substring, never a subdomain. The
# domain's mail authentication (zynkr.ai: DMARC p=reject) stops an outsider forging that sender, so a
# look-alike mail from anyone else never reaches the team (SKB-096).
def pulse_domain(account):
    """The owner's own domain, from the account address; "" when it has none."""
    local, at, dom = (account or "").strip().lower().rpartition("@")
    return dom if local and at and dom else ""


def pulse_query(account):
    return 'from:%s subject:"%s" newer_than:1d' % (pulse_domain(account), PULSE_SUBJECT)


PULSE_LINE = re.compile(r"^[\s>*•\-]*([A-Za-z][A-Za-z .'/-]{0,40}?) - (\d+) of (\d+) cooking:\s*(.+?)\s*$", re.M)
PLAN_MAX = 5
DECIDED = ("決議", "放棄")                   # what the meeting settled; 行動 is a plan, 進度 a state
OPEN = ("卡關", "風險", "待討論", "待決")      # 待決: weeks before SKB-091


# ── weeks ────────────────────────────────────────────────────────────────────
def previous_week(week):
    m = ledger.monday(week) - timedelta(days=7)
    y, w, _ = m.isocalendar()
    return "%d-W%02d" % (y, w)


def wb_label(week):
    """The team's label: the Monday that opens the week, `WB 10/5`."""
    m = ledger.monday(week)
    return "WB %d/%d" % (m.month, m.day)


def week_range(week):
    m = ledger.monday(week)
    s = m + timedelta(days=6)
    return "%d/%d–%d/%d" % (m.month, m.day, s.month, s.day)


# ── config ───────────────────────────────────────────────────────────────────
def load_all(path=None):
    cfg = ledger.load_config(path)
    raw = json.load(open(cfg["path"], encoding="utf-8"))
    reporters = [r for r in raw.get("reporters", []) if "@" in r and "<" not in r]
    if not reporters:
        raise Refuse(2, "config has no reporters to send the recap to")
    names = {v: k for k, v in raw.get("chat_ids", {}).items()
             if not k.startswith("$") and not k.startswith("users/") and isinstance(v, str)}
    rules = os.path.expanduser(raw.get("sources", {}).get("state_rules", {}).get("path") or DEFAULT_RULES)
    doc_id = raw.get("doc", {}).get("id") or ""
    # Who gets the recap: "owner" (the account alone, the default) while it is new, "team" (every
    # reporter) once the owner has seen it work. A missing or unknown value never reaches the team.
    # `recap_team_from` (YYYY-MM-DD) sets the switch ahead: "team" starts with the recap of that
    # Monday. A date that cannot be read keeps the owner alone.
    audience = raw.get("routine", {}).get("recap_audience") or "owner"
    team_from = str(raw.get("routine", {}).get("recap_team_from") or "").strip()
    cfg.update(team_from=(ledger.norm_date(team_from) or "9999-12-31") if team_from else "")
    # SKB-091: one team address (zynkr-all) replaces the audience switch once it is set
    recap_to = str(raw.get("routine", {}).get("recap_to") or "").strip()
    roster = [k for k in raw.get("chat_ids", {}) if not k.startswith("$") and not k.startswith("users/")]
    aliases = {k: v for k, v in (raw.get("routine", {}).get("name_aliases") or {}).items()
               if not k.startswith("$") and isinstance(v, str)}
    cfg.update(recap_to=recap_to if "@" in recap_to and "<" not in recap_to else "", roster=roster, aliases=aliases)
    cfg.update(reporters=reporters, names=names, rules=rules, audience=audience if audience in ("owner", "team") else "owner",
               doc_url=("https://docs.google.com/document/d/%s/edit" % doc_id) if doc_id and "<" not in doc_id else "",
               tracker_url="https://docs.google.com/spreadsheets/d/%s/edit" % cfg["tracker"],
               ledger_url="https://docs.google.com/spreadsheets/d/%s/edit" % cfg["ledger"])
    return cfg


# ── call-outs in the team's words ─────────────────────────────────────────
def as_date(v):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(v or ""))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def md(d):
    return "%d/%d" % (d.month, d.day)


def why(state, row, today):
    """One zh-TW reason, built from the row itself. derive_state's evidence strings are English
    and machine-shaped; they stay in the run report, never in the team's mail (wording.md)."""
    start, end = as_date(row.get("start")), as_date(row.get("end"))
    if state == "UNDATED":
        missing = [name for name, d in (("開始", start), ("結束", end)) if d is None]
        return "、".join(missing) + ("都還沒排" if len(missing) == 2 else "還沒排")
    if state == "OVERDUE":
        if row.get("status") == "進行中" and end and end < today:
            return "結束日 %s 已過 %d 天" % (md(end), (today - end).days)
        if start and start < today:
            return "原訂 %s 開始，還沒開始" % md(start)
        return "已經過期"
    if state == "ENDS_SOON":
        return ("%s 到期，還有 %d 天" % (md(end), (end - today).days)) if end else "快到期"
    if state == "PROPOSE_DONE":
        note = " ".join(str(row.get("note") or "").split())
        return "備註寫「%s」，狀態還是%s" % (note[:40] + ("…" if len(note) > 40 else ""), row.get("status") or "")
    if state == "UNKNOWN_STATUS":
        return "狀態寫成「%s」，不在清單裡" % (row.get("status") or "")
    return ""


# ── steps ────────────────────────────────────────────────────────────────────
def r_start(runner_week, config=None, now=None, base=None):
    cfg = load_all(config)
    target = previous_week(runner_week)
    k = ledger.week_index(target, cfg["epoch"])
    now = ledger.parse_now(now)
    d = os.path.join(base or os.path.join(ledger.state_dir(), "runs"),
                     "%s-recap-%s" % (target, now.strftime("%Y%m%dT%H%M%S")))
    n = 1
    while os.path.exists(d + ("" if n == 1 else "-%d" % n)):
        n += 1
    d = d + ("" if n == 1 else "-%d" % n)
    os.makedirs(d)
    rng = "Weeks!A%d:R%d" % (1 + k, 2 + k) if k >= 1 else "Weeks!A2:R2"
    run = dict(cfg, dir=d, runner_week=runner_week, week=target, k=k, weeks_range=rng)
    save_run(run)
    calls = [read_call(run, cfg["ledger"], "Weeks!A1:R1", "wh"), read_call(run, cfg["ledger"], rng, "wr")]
    return {"dir": d, "week": target, "label": wb_label(target), "calls": calls}


def snapshot_ok(row, week, cycle):
    row = pad(row, 14)
    try:
        items, first, last = int(row[5]), int(row[6]), int(row[7])
    except ValueError:
        return False
    return (row[0] == week and row[1] == "ok" and row[3] == cycle and row[9] == ledger.LAYOUT
            and 1 <= items <= ledger.SLOT and last == first + items - 1)


def r_blocks(d):
    run = load_run(d)
    wh = parse_values(load_result(os.path.join(d, "wh.txt")), run["ledger"], "Weeks!A1:R1")
    if not wh or pad(wh[0], 14) != ledger.WEEKS_FULL[:14]:
        raise Refuse(4, "Weeks header is not the Phase 2 header (A–N)")
    phase3 = pad(wh[0], 18) == ledger.WEEKS_FULL[:18]
    wr = parse_values(load_result(os.path.join(d, "wr.txt")), run["ledger"], run["weeks_range"])
    k = run["k"]
    if k >= 1:
        prev_row = pad(wr[0], 18) if len(wr) > 0 else [""] * 18
        row = pad(wr[1], 18) if len(wr) > 1 else [""] * 18
    else:
        prev_row, row = None, pad(wr[0], 18) if wr else [""] * 18
    if not snapshot_ok(row, run["week"], run["cycle"]):
        run.update(notice=True, reason="no committed snapshot for %s" % run["week"])
        save_run(run)
        return {"notice": True, "week": run["week"], "label": wb_label(run["week"]),
                "reason": run["reason"], "next": "recap.py notice --dir %s" % d}
    prev_ok = prev_row is not None and snapshot_ok(prev_row, previous_week(run["week"]), run["cycle"])
    calls, pages = [], {}

    def block_pages(prefix, wrow):
        first, last = int(wrow[6]), int(wrow[7])
        out, a = [], first
        while a <= last:
            b = min(a + ledger.PAGE - 1, last)
            out.append(("%s%d" % (prefix, len(out) + 1), "Snapshot!A%d:P%d" % (a, b)))
            a = b + 1
        return out

    pages["s"] = block_pages("s", row)
    if prev_ok:
        pages["p"] = block_pages("p", prev_row)
    for name, rng in pages["s"] + pages.get("p", []):
        calls.append(read_call(run, run["ledger"], rng, name))
    for tab, col, cell in (("Reports", "I", 10), ("Decisions", "I", 12), ("Proposals", "O", 14)):
        if row[cell] == "ok" and (phase3 or cell < 14):
            first, last = ledger.block_slot(tab, k)
            rng = "%s!A%d:%s%d" % (tab, first, col, last)
            pages[tab] = rng
            calls.append(read_call(run, run["ledger"], rng, tab.lower()))
    calls.append(ledger.call("search_gmail_messages", {"user_google_email": run["account"], "page_size": PULSE_THREADS,
                                                       "query": pulse_query(run["account"])},
                             os.path.join(d, "pulse-search.txt")))
    run.update(notice=False, row=row, prev_row=prev_row if prev_ok else None, pages=pages,
               applied=phase3 and row[16] == "ok", pulse="not-read")
    save_run(run)
    return {"notice": False, "week": run["week"], "calls": calls,
            "first_snapshot": not prev_ok, "reports": row[10] == "ok", "decisions": row[12] == "ok",
            "proposals": "Proposals" in pages}


def r_pulse(d):
    """The Pulse search result -> the threads to fetch, newest first, each once. `build` reads them in
    turn and the first that passes `parse_pulse` wins, so a newer look-alike cannot hide the Pulse.
    No Pulse is no failure: the recap goes out without the sales lines and says so."""
    run = load_run(d)
    if run.get("notice") is not False:
        raise Refuse(2, "run `recap.py blocks` first")
    path = os.path.join(d, "pulse-search.txt")
    if not os.path.exists(path):
        raise Refuse(2, "save the Sales Pulse search `blocks` printed first")
    text = load_result(path).strip()
    first = text.split("\n", 1)[0]
    query = pulse_query(run["account"])
    if first == "No messages found for query: '%s'" % query:
        ids = []
    elif first.startswith("Found ") and first.endswith("'%s':" % query):
        ids = re.findall(r"Thread ID: ([0-9a-f]+)", text)
    else:
        run["pulse"] = "unreadable"
        save_run(run)
        return {"pulse": False, "why": "the Pulse search result could not be read"}
    if not ids:
        run["pulse"] = "missing"
        save_run(run)
        return {"pulse": False, "why": "no Sales Pulse since yesterday"}
    ids = list(dict.fromkeys(ids))[:PULSE_THREADS]
    run["pulse"] = "fetched"
    run["pulse_files"] = ["pulse-%d.txt" % i for i in range(1, len(ids) + 1)]
    save_run(run)
    return {"pulse": True, "calls": [ledger.call("get_gmail_thread_content",
                                                 {"user_google_email": run["account"], "thread_id": t},
                                                 os.path.join(d, f)) for t, f in zip(ids, run["pulse_files"])]}


def parse_pulse(text, account):
    """{name: (cooking, floor, [steps])} from the Pulse thread's first message, sent from an address on
    the owner's own domain; None when the thread is not a Pulse or the first message came from anywhere
    else."""
    m = re.search(r"^Subject: (.*)$", text, re.M)
    if not m or not m.group(1).strip().startswith(PULSE_SUBJECT):
        return None
    parts = re.split(r"^=== Message \d+ ===$", text, flags=re.M)
    if len(parts) < 2:
        return None
    first = parts[1]
    head, _, body = first.lstrip("\n").partition("\n\n")
    frm = re.search(r"^From: (.*)$", head, re.M)
    # the address itself, parsed: a display name, a look-alike domain that merely contains the owner's,
    # a subdomain or a second "@" is not it
    sender = parseaddr(frm.group(1))[1].strip().lower() if frm else ""
    local, _, dom = sender.rpartition("@")
    domain = pulse_domain(account)
    if not domain or not local or "@" in local or dom != domain:
        return None
    out = {}
    for name, n, floor, rest in PULSE_LINE.findall(body):
        name = " ".join(name.split())
        if name not in out:
            out[name] = (int(n), int(floor),
                         [s.strip() for s in rest.split(";") if s.strip() and s.strip().lower() != PULSE_NO_STEP][:2])
    return out


def person_of(run, name):
    """A name as the roster spells it: exact, then an alias from the config, then the one roster
    name with the same first word (the Pulse writes `Peter`, the roster `Peter Tu`)."""
    name = " ".join(str(name or "").split())
    if not name:
        return ""
    if name.lower() in ("all", "全體", "全員"):
        return "全體"
    roster = run.get("roster", [])
    if name in roster:
        return name
    if name in run.get("aliases", {}):
        return run["aliases"][name]
    first = name.split()[0].lower()
    hit = [r for r in roster if r.split()[0].lower() == first]
    return hit[0] if len(hit) == 1 else name


def owners_of(run, field):
    return [p for p in (person_of(run, x) for x in re.split(r"[、,，/]", str(field or ""))) if p] or ["負責人未定"]


def build_plan(run, items, actions, flagged, pulse):
    """[{"who", "lines"}] and how many lines were dropped for citing nothing. Order per person:
    the meeting's actions, overdue or due within 14 days, P0/P1 undated, the Pulse; an item already
    listed for that person is not listed again; at most PLAN_MAX lines."""
    plan, seen, dropped = {}, {}, 0

    def add(who, text, cite):
        nonlocal dropped
        if not cite:
            dropped += 1
            return
        lines = plan.setdefault(who, [])
        if cite != "deal" and cite in seen.setdefault(who, set()):
            return
        if len(lines) >= PLAN_MAX:
            return
        seen[who].add(cite)
        lines.append(text)

    for a in actions:
        num = a["#"] if a["#"] in items else ""
        due = as_date(ledger.norm_date(a["期限"]) or a["期限"])
        text = "#%s %s%s" % (num, clip(a["內容"], 50), "（%s 前）" % md(due) if due else "")
        for who in owners_of(run, a["負責人"]):
            add(who, text, num)
    for key in ("overdue", "ends_soon", "undated"):
        for x in flagged.get(key, []):
            for who in owners_of(run, x["負責人"]):
                add(who, "#%s %s — %s" % (x["#"], clip(x["項目"], 30), x["why"]), x["#"])
    for name, (_, _, steps) in (pulse or {}).items():
        for s in steps:
            add(person_of(run, name), "業務：%s" % clip(s, 80), "deal")
    roster = run.get("roster", [])
    order = sorted(plan, key=lambda w: (w in ("全體", "負責人未定"), roster.index(w) if w in roster else len(roster), w))
    return [{"who": w, "lines": plan[w]} for w in order if plan[w]], dropped


def clip(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def read_block(run, key, wrow):
    rows = []
    for name, rng in run["pages"][key]:
        rows += parse_values(load_result(os.path.join(run["dir"], name + ".txt")), run["ledger"], rng)
    rows = [pad(r, 16) for r in rows]
    if len(rows) != int(wrow[5]):
        raise Refuse(6, "%s block has %d rows; its Weeks row says %s" % (wrow[0], len(rows), wrow[5]))
    if ledger.digest([r[3:] for r in rows]) != wrow[8]:
        raise Refuse(6, "%s block does not match its Weeks digest" % wrow[0])
    return rows


def derive(run, rows, prev_rows, today):
    if not os.path.exists(run["rules"]):
        raise Refuse(2, "the state rules are missing: install zynkr-gm (%s)" % run["rules"])
    cur = os.path.join(run["dir"], "rows.json")
    json.dump([dict(zip(ledger.TRACKER_HEADER, r[3:])) for r in rows], open(cur, "w", encoding="utf-8"), ensure_ascii=False)
    args = [sys.executable, run["rules"], cur, "--today", today, "--json"]
    if prev_rows:
        prev = os.path.join(run["dir"], "prev_rows.json")
        json.dump([dict(zip(ledger.TRACKER_HEADER, r[3:])) for r in prev_rows], open(prev, "w", encoding="utf-8"), ensure_ascii=False)
        args += ["--prev", prev]
    out = subprocess.run(args, capture_output=True, text=True)
    if out.returncode != 0:
        raise Refuse(3, "derive_state.py failed: %s" % out.stderr.strip()[:200])
    return json.loads(out.stdout)


def r_build(d, today):
    run = load_run(d)
    if run.get("notice") is not False:
        raise Refuse(2, "run `recap.py blocks` first (or this week takes the notice path)")
    ledger.monday(run["week"])
    rows = read_block(run, "s", run["row"])
    prev = read_block(run, "p", run["prev_row"]) if run.get("prev_row") else None
    names = {r[3]: r[6] for r in rows}
    if prev:
        names.update({r[3]: r[6] for r in prev if r[3] not in names})
    diff = ledger.diff_snapshots(prev, rows, ()) if prev else None
    st = derive(run, rows, prev, today)
    by_id = {r["id"]: r for r in st["rows"]}

    today_d = as_date(today)

    def flagged(state):
        return [{"#": r["id"], "項目": r["item"], "負責人": r["owner"], "why": why(state, r, today_d),
                 "evidence": r.get("evidence", [])}
                for r in st["rows"] if state in r["states"]]

    decisions = {"recorded": "Decisions" in run["pages"], "decided": [], "open": [], "actions": []}
    if decisions["recorded"]:
        drows = parse_values(load_result(os.path.join(d, "decisions.txt")), run["ledger"], run["pages"]["Decisions"])
        for r in (pad(x, 9) for x in drows):
            if r[0] != run["week"]:
                continue
            entry = {"類型": r[2], "內容": r[3], "負責人": r[4], "期限": r[5], "#": r[6], "狀態": r[8]}
            if r[2] in DECIDED:
                decisions["decided"].append(entry)
            elif r[2] == "行動":
                decisions["actions"].append(entry)
            elif r[2] in OPEN or r[2] != "進度":
                decisions["open"].append(entry)
    reports = {"recorded": "Reports" in run["pages"], "posted": [], "missing": [], "blockers": []}
    if reports["recorded"]:
        rrows = parse_values(load_result(os.path.join(d, "reports.txt")), run["ledger"], run["pages"]["Reports"])
        posters = []
        for r in (pad(x, 9) for x in rrows):
            if r[0] != run["week"]:
                continue
            posters.append(r[2])
            if r[7].strip():
                reports["blockers"].append({"who": run["names"].get(r[2]) or r[3] or r[2].split("@")[0],
                                            "部門": r[3], "卡關": r[7]})
        reports["posted"] = sorted(posters)
        reports["missing"] = [run["names"].get(e) or e.split("@")[0] for e in run["reporters"] if e not in posters]
    proposals = {"recorded": "Proposals" in run["pages"], "applied_ran": bool(run.get("applied")), "rows": []}
    if proposals["recorded"]:
        prows = parse_values(load_result(os.path.join(d, "proposals.txt")), run["ledger"], run["pages"]["Proposals"])
        for r in (pad(x, 15) for x in prows):
            if r[0] == run["week"]:
                proposals["rows"].append({"n": r[2], "#": r[3], "項目": r[4], "欄位": r[5], "現值": r[6],
                                          "建議值": r[7], "決定": r[12], "結果": r[14]})
    changes = []
    if diff:
        changes = [c for c in diff["changed"] if not c["cosmetic"]]
    pulse_state, pulse = run.get("pulse", "not-read"), None
    if pulse_state == "fetched":
        # newest first; the first thread that is a real Pulse wins, so a newer look-alike cannot hide it
        found = None
        for name in run.get("pulse_files") or ["pulse.txt"]:
            found = parse_pulse(load_result(os.path.join(d, name)), run["account"])
            if found:
                break
        pulse = found or None
        pulse_state = "found" if pulse else "unreadable"
    facts = {"week": run["week"], "label": wb_label(run["week"]), "range": week_range(run["week"]),
             "today": today, "first_snapshot": prev is None, "items": names,
             "changes": changes, "added": diff["added"] if diff else [], "removed": diff["removed"] if diff else [],
             "overdue": flagged("OVERDUE"), "ends_soon": flagged("ENDS_SOON"),
             "undated": [x for x in flagged("UNDATED") if by_id[x["#"]]["priority"] in ("P0", "P1")],
             "propose_done": flagged("PROPOSE_DONE"), "paused": flagged("PAUSED"),
             "unknown_status": flagged("UNKNOWN_STATUS"),
             "decisions": decisions, "reports": reports, "proposals": proposals, "pulse": pulse_state,
             "links": {"tracker": run["tracker_url"], "doc": run["doc_url"], "ledger": run["ledger_url"]}}
    facts["plan"], facts["plan_dropped"] = build_plan(run, names, decisions["actions"], facts, pulse)
    json.dump(facts, open(os.path.join(d, "facts.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    run.update(built=True)
    save_run(run)
    return {"week": run["week"], "label": facts["label"], "first_snapshot": facts["first_snapshot"],
            "changes": len(changes) + len(facts["added"]) + len(facts["removed"]),
            "overdue": [x["#"] for x in facts["overdue"]], "ends_soon": [x["#"] for x in facts["ends_soon"]],
            "undated": [x["#"] for x in facts["undated"]], "propose_done": [x["#"] for x in facts["propose_done"]],
            "decided": len(decisions["decided"]), "open_decisions": len(decisions["open"]),
            "blockers": len(reports["blockers"]), "proposals": len(proposals["rows"]) if proposals["recorded"] else None,
            "plan": {p["who"]: len(p["lines"]) for p in facts["plan"]}, "plan_dropped": facts["plan_dropped"],
            "pulse": pulse_state,
            "facts": os.path.join(d, "facts.json"),
            "tldr": "write at most 3 lines to tldr.json (a JSON list); each must cite an item # from facts.items"}


# ── rendering ────────────────────────────────────────────────────────────────
def esc(s):
    return html.escape(str(s), quote=False)


FIELD = {"狀態": "狀態", "開始": "開始", "結束": "結束", "負責人": "負責人", "協助者": "協助者", "Priority": "優先",
         "重要": "重要", "緊急": "緊急", "項目（正規化）": "名稱", "主類別": "主類別", "子類別": "子類別", "備註": "備註"}


def gate_tldr(lines, items):
    kept, dropped = [], []
    for line in lines[:3]:
        line = str(line).strip()
        cited = [m for m in ITEM_NUM.findall(line) if m in items]
        (kept if line and cited else dropped).append(line)
    return kept, dropped + [str(x) for x in lines[3:]]


def subject_for(facts):
    n_changes = len(facts["changes"]) + len(facts["added"]) + len(facts["removed"])
    parts = []
    parts.append("第一次記錄" if facts["first_snapshot"] else "變更 %d 件" % n_changes)
    parts.append("決議 %d 件" % len(facts["decisions"]["decided"]) if facts["decisions"]["recorded"] else "決議沒記到")
    parts.append("逾期 %d 件" % len(facts["overdue"]))
    return "【週報】%s 那週 — %s" % (facts["label"], " · ".join(parts))


def li(text):
    return "<li>%s</li>" % text


def render_html(facts, tldr):
    o = ['<div style="font-family:-apple-system,Segoe UI,Noto Sans TC,sans-serif;font-size:14px;line-height:1.6;color:#0F0F0E;max-width:680px">']
    o.append("<p>%s（%s）的週報，資料來自主追蹤表每週五的快照和週報帳本。</p>" % (esc(facts["label"]), esc(facts["range"])))
    if tldr:
        o.append("<h3>重點</h3><ul>%s</ul>" % "".join(li(esc(t)) for t in tldr))
    o.append("<h3>這週的計畫</h3>")
    for p in facts.get("plan", []):
        o.append("<p><b>%s</b></p><ul>%s</ul>" % (esc(p["who"]), "".join(li(esc(x)) for x in p["lines"])))
    if not facts.get("plan"):
        o.append("<p>這週沒有排定的行動、到期或缺日期的項目</p>")
    if facts.get("pulse") != "found":
        o.append("<p>業務的下一步沒有列：%s</p>" % ("今天 10 點前沒有收到 Sales Pulse" if facts.get("pulse") == "missing"
                                                   else "Sales Pulse 這次讀不到"))
    o.append("<h3>上週改了什麼</h3>")
    if facts["first_snapshot"]:
        o.append("<p>這是第一張快照，下週起才有前後可以比</p>")
    elif not (facts["changes"] or facts["added"] or facts["removed"]):
        o.append("<p>主追蹤表上週沒有任何變動</p>")
    else:
        rows = [li("#%s %s — %s：%s → %s" % (esc(c["#"]), esc(c["項目"]), esc(FIELD.get(c["column"], c["column"])),
                                           esc(c["old"] or "（空白）"), esc(c["new"] or "（空白）")))
                for c in facts["changes"]]
        rows += [li("#%s %s — 新增（%s）" % (esc(a["#"]), esc(a["項目"]), esc(a["狀態"]))) for a in facts["added"]]
        rows += [li("#%s %s — 從表上移除了" % (esc(r["#"]), esc(r["項目"]))) for r in facts["removed"]]
        o.append("<ul>%s</ul>" % "".join(rows))
    o.append("<h3>要注意的</h3>")
    groups = []
    for key, title in (("overdue", "逾期"), ("ends_soon", "兩週內到期"), ("undated", "P0/P1 還沒排日期"),
                       ("propose_done", "備註說做完了，狀態還沒改"), ("unknown_status", "狀態寫法不在清單裡")):
        if facts[key]:
            items = "".join(li("#%s %s（%s）— %s" % (esc(x["#"]), esc(x["項目"]), esc(x["負責人"] or "沒有負責人"),
                                                     esc(x["why"]))) for x in facts[key])
            groups.append("<p><b>%s（%d 件）</b></p><ul>%s</ul>" % (title, len(facts[key]), items))
    o.append("".join(groups) if groups else "<p>沒有逾期、快到期或缺日期的項目</p>")
    o.append("<h3>上週談定的事</h3>")
    dec = facts["decisions"]
    if not dec["recorded"]:
        o.append("<p>上週的決議沒有記到帳本，請看週四的 Doc 區塊</p>")
    elif not (dec["decided"] or dec["open"]):
        o.append("<p>上週會議沒有記下決議</p>")
    else:
        if dec["decided"]:
            o.append("<ul>%s</ul>" % "".join(
                li("%s%s%s" % ("放棄：" if x.get("類型") == "放棄" else "", esc(x["內容"]),
                               (" — " + esc("，".join(v for v in (x["負責人"], x["期限"]) if v)))
                               if (x["負責人"] or x["期限"]) else ""))
                for x in dec["decided"]))
        if dec["open"]:
            o.append("<p>還沒定案</p><ul>%s</ul>" % "".join(li(esc(x["內容"])) for x in dec["open"]))
    pr = facts.get("proposals") or {}
    if pr.get("recorded"):
        o.append("<h3>上週的變更提案</h3>")
        prs = pr["rows"]

        def pline(x):
            return li("#%s %s — %s：%s → %s" % (esc(x["#"]), esc(x["項目"]), esc(FIELD.get(x["欄位"], x["欄位"])),
                                              esc(x["現值"] or "（空白）"), esc(x["建議值"])))
        if not prs:
            o.append("<p>上週沒有變更提案</p>")
        elif not pr["applied_ran"]:
            o.append("<p>提案記下了，但週末沒有記到核准結果（可能沒有回覆，或套用那一步沒有跑完），%d 件都沒有套用</p>" % len(prs))
        else:
            for key, title in (("would-apply", "試行中：核准了，但試行期間不寫進總表。如果套用，會改這些"),
                               ("to-apply", "核准了，已寫進總表（有人手改過的格子會跳過）"),
                               ("applied", "已套用到總表"), ("退回", "退回"), ("未回覆", "回覆裡沒寫到，這次不套用")):
                xs = [x for x in prs if x["結果"] == key]
                if xs:
                    o.append("<p><b>%s（%d 件）</b></p><ul>%s</ul>" % (title, len(xs), "".join(pline(x) for x in xs)))
    o.append("<h3>卡關</h3>")
    rep = facts["reports"]
    if not rep["recorded"]:
        o.append("<p>上週的週報沒有記到帳本</p>")
    else:
        o.append("<ul>%s</ul>" % "".join(li("%s：%s" % (esc(b["who"]), esc(b["卡關"]))) for b in rep["blockers"])
                 if rep["blockers"] else "<p>沒有人回報卡關</p>")
        if rep["missing"]:
            o.append("<p>上週沒交週報：%s</p>" % esc("、".join(rep["missing"])))
    links = facts["links"]
    o.append('<p style="color:#6F6B62;font-size:12px">主追蹤表 <a href="%s">開啟</a>%s · 週報帳本 <a href="%s">開啟</a></p>'
             % (esc(links["tracker"]), (' · 週報 Doc <a href="%s">開啟</a>' % esc(links["doc"])) if links["doc"] else "",
                esc(links["ledger"])))
    o.append("</div>")
    return "".join(o)


def audience_for(run):
    """Who gets this recap: every reporter when the audience is `team` and the recap's Monday is on or
    after `recap_team_from` (when set); the owner alone otherwise."""
    if run.get("recap_to"):
        return "team"
    if run["audience"] != "team":
        return "owner"
    if run.get("team_from") and ledger.monday(run["runner_week"]).isoformat() < run["team_from"]:
        return "owner"
    return "team"


def r_render(d, tldr_path):
    run = load_run(d)
    if not run.get("built"):
        raise Refuse(2, "run `recap.py build` first")
    facts = json.load(open(os.path.join(d, "facts.json"), encoding="utf-8"))
    try:
        lines = json.load(open(tldr_path, encoding="utf-8")) if tldr_path else []
    except (OSError, ValueError) as e:
        raise Refuse(3, "cannot read the TL;DR (%s)" % e)
    if not isinstance(lines, list):
        raise Refuse(3, "the TL;DR must be a JSON list of lines")
    kept, dropped = gate_tldr(lines, facts["items"])
    subject = subject_for(facts)
    body = render_html(facts, kept)
    path = os.path.join(d, "recap.html")
    open(path, "w", encoding="utf-8").write(body)
    run.update(rendered=True, subject=subject)
    save_run(run)
    audience = audience_for(run)
    to = run.get("recap_to") or (",".join(run["reporters"]) if audience == "team" else run["account"])
    return {"subject": subject, "to": to, "audience": audience, "body_path": path, "body_format": "html",
            "tldr_kept": len(kept), "tldr_dropped": dropped,
            "sent_check": "search in:sent newer_than:3d for this exact subject before sending; send only if absent"}


def r_notice(d):
    run = load_run(d)
    if not run.get("notice"):
        raise Refuse(2, "this week does not take the notice path")
    label = wb_label(run["week"])
    subject = "【週報】%s 那週沒有產出：週五的快照沒有記到" % label
    body = ("<p>%s（%s）那週，主追蹤表週五的快照沒有記到週報帳本（%s），所以這週一的週報沒有寄出。</p>"
            "<p>週五晚上會照常再拍一張，下週一的週報會從那張開始比。要補看這週的狀況，請直接開主追蹤表。</p>"
            "<p><a href=\"%s\">主追蹤表</a> · <a href=\"%s\">週報帳本</a></p>"
            % (esc(label), esc(week_range(run["week"])), esc(run["reason"]), esc(run["tracker_url"]), esc(run["ledger_url"])))
    path = os.path.join(d, "notice.html")
    open(path, "w", encoding="utf-8").write(body)
    return {"subject": subject, "to": run["account"], "body_path": path, "body_format": "html"}


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("start")
    s.add_argument("--runner-week", required=True)
    s.add_argument("--config")
    for name in ("blocks", "notice", "pulse"):
        p = sub.add_parser(name)
        p.add_argument("--dir", required=True)
    b = sub.add_parser("build")
    b.add_argument("--dir", required=True)
    b.add_argument("--today", required=True)
    r = sub.add_parser("render")
    r.add_argument("--dir", required=True)
    r.add_argument("--tldr")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        if a.cmd == "start":
            emit(r_start(a.runner_week, a.config))
        elif a.cmd == "blocks":
            emit(r_blocks(a.dir))
        elif a.cmd == "build":
            emit(r_build(a.dir, a.today))
        elif a.cmd == "render":
            emit(r_render(a.dir, a.tldr))
        elif a.cmd == "notice":
            emit(r_notice(a.dir))
        elif a.cmd == "pulse":
            emit(r_pulse(a.dir))
        else:
            ap.print_help()
            return 2
    except Refuse as e:
        print("recap.py: %s" % e, file=sys.stderr)
        return e.code
    return 0


# ── selftest ─────────────────────────────────────────────────────────────────
def selftest():
    import shutil
    import tempfile
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append("%s: got %r, want %r" % (name, got, want))

    check("previous week", previous_week("2026-W41"), "2026-W40")
    check("previous week across a year", previous_week("2027-W01"), "2026-W53")
    check("WB label", wb_label("2026-W41"), "WB 10/5")
    check("range", week_range("2026-W41"), "10/5–10/11")
    # the plan (SKB-091): order, the five-line cap, an item listed once, uncited lines dropped, names
    prun = {"roster": ["Ann Lee", "Bob Wu"], "aliases": {"Fish": "Bob Wu"}}
    check("a first name finds the roster name", person_of(prun, "Ann"), "Ann Lee")
    check("an alias finds the roster name", person_of(prun, "Fish"), "Bob Wu")
    check("an unknown name stays", person_of(prun, "Zed"), "Zed")
    check("All is everyone", person_of(prun, "All"), "全體")
    pitems = {n: "x" for n in ("1.01", "1.02", "1.03", "1.04", "1.05", "1.06")}
    pacts = [{"內容": "交付", "負責人": "Ann Lee", "期限": "2026-10-20", "#": "1.01"},
             {"內容": "找講師", "負責人": "Ann Lee", "期限": "", "#": "新"},
             {"內容": "全員看", "負責人": "All", "期限": "", "#": "1.02"},
             {"內容": "一起做", "負責人": "Ann Lee、Bob Wu", "期限": "", "#": "1.03"}]
    pflag = {"overdue": [{"#": "1.01", "項目": "x", "負責人": "Ann Lee", "why": "過期"}],
             "ends_soon": [{"#": "1.04", "項目": "x", "負責人": "Ann Lee", "why": "快到"}],
             "undated": [{"#": "1.05", "項目": "x", "負責人": "Ann Lee", "why": "沒日期"},
                         {"#": "1.06", "項目": "x", "負責人": "Ann Lee", "why": "沒日期"}]}
    plan, pdrop = build_plan(prun, pitems, pacts, pflag, {"Ann": (1, 5, ["s1", "s2"]), "Fish": (0, 5, ["claim 5 leads"])})
    check("plan: people in roster order, everyone last", [p["who"] for p in plan], ["Ann Lee", "Bob Wu", "全體"])
    check("plan: actions, then due, then undated; an item once; five at most, so the Pulse waits",
          plan[0]["lines"], ["#1.01 交付（10/20 前）", "#1.03 一起做", "#1.04 x — 快到", "#1.05 x — 沒日期", "#1.06 x — 沒日期"])
    check("plan: the Pulse's steps come last, under the roster name", plan[1]["lines"], ["#1.03 一起做", "業務：claim 5 leads"])
    check("plan: an action for a new item cites nothing and is dropped", pdrop, 1)
    pulse_text = ("Thread ID: t1\nSubject: Zynkr Sales Pulse - week of Oct 12 to Oct 18\nMessages: 2\n\n"
                  "=== Message 1 ===\nFrom: Owner <owner@example.com>\n\n3 of 7 KPIs met\nNext step this week\n"
                  "Ann - 2 of 5 cooking: follow up the Acme quote; drop the Beta deal; a third\n"
                  "- Zed Q - 0 of 5 cooking: claim 5 leads\n\n=== Message 2 ===\nFrom: y\n\n"
                  "> Ann - 9 of 5 cooking: quoted, not read\n")
    check("the Pulse: first message only, two steps at most", parse_pulse(pulse_text, "owner@example.com"),
          {"Ann": (2, 5, ["follow up the Acme quote", "drop the Beta deal"]), "Zed Q": (0, 5, ["claim 5 leads"])})
    check("a thread that is not the Pulse is not read",
          parse_pulse(pulse_text.replace("Zynkr Sales Pulse", "Re: Pulse"), "owner@example.com"), None)
    check("the Pulse is looked for from the owner's own domain, in all mail, not only Sent",
          pulse_query("Owner@Example.com"), 'from:example.com subject:"Zynkr Sales Pulse - week of" newer_than:1d')
    check("the CRM's own sender on the owner's domain is read",
          parse_pulse(pulse_text.replace("Owner <owner@example.com>", "Zynkr CRM <support@example.com>"),
                      "owner@example.com"),
          {"Ann": (2, 5, ["follow up the Acme quote", "drop the Beta deal"]), "Zed Q": (0, 5, ["claim 5 leads"])})
    for spoof in ('"owner@example.com" <eve@example.net>', "owner@example.com.evil.net",
                  "crm@mail.example.com", "eve@example.net@example.com"):
        check("a sender that only contains the domain is not on it (%s)" % spoof,
              parse_pulse(pulse_text.replace("Owner <owner@example.com>", spoof), "owner@example.com"), None)
    check("a look-alike Pulse from anyone else is not read",
          parse_pulse(pulse_text.replace("Owner <owner@example.com>", "Eve <eve@example.net>"), "owner@example.com"), None)
    check("no account, no Pulse", parse_pulse(pulse_text, ""), None)
    check("the CRM's 'no step this week' is not a step",
          parse_pulse(pulse_text.replace("- Zed Q - 0 of 5 cooking: claim 5 leads", "Zed Q - 5 of 5 cooking: no step this week"),
                      "owner@example.com")["Zed Q"], (5, 5, []))
    kept, dropped = gate_tldr(["#1.03 SEO 改雙週一篇", "大家辛苦了", "1.99 不存在", "4.10 延期", "第四行"],
                              {"1.03": "SEO", "4.10": "x"})
    check("tldr keeps cited lines", kept, ["#1.03 SEO 改雙週一篇"])
    check("tldr drops uncited and unknown", dropped, ["大家辛苦了", "1.99 不存在", "4.10 延期", "第四行"])

    tmp = tempfile.mkdtemp(prefix="recap-selftest-")
    try:
        rules = os.path.join(tmp, "derive_state.py")
        # a stand-in for zynkr-gm's script: flags every 進行中 row whose 結束 is before --today
        open(rules, "w").write(
            "import json,sys\n"
            "rows=json.load(open(sys.argv[1]));today=sys.argv[sys.argv.index('--today')+1]\n"
            "out=[]\n"
            "for r in rows:\n"
            "  st=['OVERDUE'] if r['狀態']=='進行中' and r['結束']<today and r['結束'][:1]=='2' else []\n"
            "  d=lambda v: v if v[:1]=='2' else None\n"
            "  out.append({'id':r['#'],'item':r['項目（正規化）'],'priority':r['Priority'],'owner':r['負責人'],'states':st,'evidence':['end '+r['結束']+' overdue'] if st else [],'start':d(r['開始']),'end':d(r['結束']),'status':r['狀態'],'note':r['備註']})\n"
            "print(json.dumps({'rows':out,'summary':{},'today':today}))\n")
        cfgp = os.path.join(tmp, "cfg.json")
        json.dump({"google_account": "owner@example.com", "reporters": ["a@example.com", "b@example.com"],
                   "chat_ids": {"Ann": "a@example.com", "users/1": "b@example.com"},
                   "doc": {"id": "DOC"},
                   "sources": {"main_tracker": {"id": "TRK", "tab": "T", "cycle": "2026H2"},
                               "ledger": {"id": "LED", "epoch_week": "2026-W40"},
                               "state_rules": {"path": rules}},
                   "routine": {"recap_audience": "team"}}, open(cfgp, "w"), ensure_ascii=False)

        def item(num, status, end):
            return [num, "1.0 M", "1.1 S", "item " + num, "", "", "P1", "Ann", "", "YYYY-MM-DD", end, status, ""]

        def block(week, at, items):
            return [[week, at, "2026H2"] + i for i in items]

        w40 = block("2026-W40", "2026-10-02T18:07:00+08:00",
                    [item("1.01", "未開始", "YYYY-MM-DD"), item("1.02", "進行中", "2026-10-30"), item("1.10", "進行中", "2026-09-30")])
        w41 = block("2026-W41", "2026-10-09T18:06:00+08:00",
                    [item("1.01", "進行中", "YYYY-MM-DD"), item("1.02", "進行中", "2026-10-30"), item("1.10", "進行中", "2026-09-30")])

        def wrow(week, rows, reports="", decisions=""):
            items = [r[3:] for r in rows]
            k = ledger.week_index(week, "2026-W40")
            first = 2 + 100 * k
            return [week, "ok", rows[0][1], "2026H2", "TRK", str(len(rows)), str(first), str(first + len(rows) - 1),
                    ledger.digest(items), ledger.LAYOUT, reports, "", decisions, ""]

        def fmt(rng, rows):
            if not rows:
                return "No data found in range '%s' for x@example.com." % rng
            width = len(rows[0])
            return "\n".join(["Successfully read %d rows from range '%s' in spreadsheet LED for x@example.com:" % (len(rows), rng)]
                             + ["Row %2d: %s" % (i, list(r) + [""] * max(0, width - len(r))) for i, r in enumerate(rows, 1)])

        def serve(calls, sheet, pulse=None):
            # pulse: one thread's text, or a list of them, newest first, as threads 1a2b, 1a2c, ...
            pulses = pulse if isinstance(pulse, list) else [pulse] if pulse else []
            for c in calls:
                if c["tool"].endswith("search_gmail_messages"):
                    q = c["args"]["query"]
                    open(c["save"], "w", encoding="utf-8").write(
                        "Found %d messages matching '%s':\n\n" % (len(pulses), q)
                        + "".join("  %d. Message ID: m%d\n     Thread ID: %x\n" % (i + 1, i + 1, 0x1a2b + i)
                                  for i in range(len(pulses))) if pulses
                        else "No messages found for query: '%s'" % q)
                    continue
                if c["tool"].endswith("get_gmail_thread_content"):
                    open(c["save"], "w", encoding="utf-8").write(pulses[int(c["args"]["thread_id"], 16) - 0x1a2b])
                    continue
                rng = c["args"]["range_name"]
                tab, r0, r1 = re.match(r"^(\w+)!A(\d+):[A-Z](\d+)$", rng).groups()
                g = sheet[tab]
                got = [g[i - 1] if i - 1 < len(g) else [] for i in range(int(r0), int(r1) + 1)]
                while got and not any(x.strip() for x in got[-1]):
                    got.pop()
                open(c["save"], "w", encoding="utf-8").write(fmt(rng, got))

        def ledger_sheet(weeks_rows, w40rows, w41rows, rep=None, dec=None, props=None, header=None):
            snap = [ledger.SNAPSHOT_HEADER] + [[""] * 16] * 200
            for i, r in enumerate(w40rows):
                snap[1 + i] = r
            for i, r in enumerate(w41rows):
                snap[101 + i] = r
            reports = [ledger.REPORTS_HEADER] + [[""] * 9] * 40
            for i, r in enumerate(rep or []):
                reports[21 + i] = r
            decisions = [ledger.DECISIONS_HEADER] + [[""] * 9] * 90
            for i, r in enumerate(dec or []):
                decisions[ledger.block_slot("Decisions", 1)[0] - 1 + i] = r
            proposals = [ledger.PROPOSALS_HEADER] + [[""] * 15] * 90
            for i, r in enumerate(props or []):
                proposals[41 + i] = r
            return {"Weeks": [header or (ledger.WEEKS_HEADER + ledger.WEEKS_BEAT_HEADER)] + weeks_rows,
                    "Snapshot": snap, "Reports": reports, "Decisions": decisions, "Proposals": proposals}

        rep = [["2026-W41", "2026-10-05T01:00:00Z", "a@example.com", "#Sales", "做完 A", "做 B", "", "等報價", "tagged"]]
        dec = [["2026-W41", "2026-10-08", "決議", "1.02 改月底交", "Ann", "2026-10-30", "1.02", "x"],
               ["2026-W41", "2026-10-08", "待決", "要不要外包", "", "", "", "x"],
               ["2026-W41", "2026-10-08", "行動", "跟客戶確認", "Ann", "2026-10-20", "1.02", "x", "已排定"],
               ["2026-W41", "2026-10-08", "放棄", "1.01 舊版不做了", "", "", "1.01", "x", ""],
               ["2026-W41", "2026-10-08", "卡關", "等報價", "Ann", "", "", "x", ""],
               ["2026-W41", "2026-10-08", "進度", "1.10 做一半", "Ann", "", "1.10", "x", "進行中"]]
        sheet = ledger_sheet([wrow("2026-W40", w40), wrow("2026-W41", w41, "ok", "ok")], w40, w41, rep, dec)
        st = r_start("2026-W42", cfgp, "2026-10-12T09:10:00+08:00", base=os.path.join(tmp, "runs"))
        check("recap targets the previous week", st["week"], "2026-W41")
        serve(st["calls"], sheet)
        bl = r_blocks(st["dir"])
        check("recap not a notice", bl["notice"], False)
        serve(bl["calls"], sheet)
        check("no Pulse yet: nothing to fetch", r_pulse(st["dir"])["pulse"], False)
        built = r_build(st["dir"], "2026-10-12")
        check("recap changes", built["changes"], 1)
        check("recap overdue from the state rules", built["overdue"], ["1.10"])
        check("recap decisions: 決議 and 放棄 settle, 待決 and 卡關 stay open, 行動 and 進度 are neither",
              (built["decided"], built["open_decisions"]), (2, 2))
        check("recap plan: the action, then the overdue item", (built["plan"], built["pulse"]), ({"Ann": 2}, "missing"))
        check("recap blockers", built["blockers"], 1)
        tl = os.path.join(tmp, "tldr.json")
        json.dump(["#1.01 開始進行", "沒有編號的一句"], open(tl, "w"), ensure_ascii=False)
        out = r_render(st["dir"], tl)
        check("recap subject", out["subject"], "【週報】WB 10/5 那週 — 變更 1 件 · 決議 2 件 · 逾期 1 件")
        check("recap recipients", out["to"], "a@example.com,b@example.com")
        check("recap drops an uncited line", out["tldr_dropped"], ["沒有編號的一句"])
        body = open(out["body_path"], encoding="utf-8").read()
        check("recap shows the change", "#1.01 item 1.01 — 狀態：未開始 → 進行中" in body, True)
        check("recap names the blocker by display name", "Ann：等報價" in body, True)
        check("recap lists who did not post", "上週沒交週報：b" in body, True)
        check("recap escapes html", "<script>" not in body, True)
        check("recap plan in the mail", "<b>Ann</b></p><ul><li>#1.02 跟客戶確認（10/20 前）</li>" in body, True)
        check("recap says the Pulse was missing", "業務的下一步沒有列：今天 10 點前沒有收到 Sales Pulse" in body, True)
        check("recap shows a drop as one", "放棄：1.01 舊版不做了</li>" in body, True)

        # the Pulse found: its steps join the plan under the roster name
        stp = r_start("2026-W42", cfgp, "2026-10-12T10:05:00+08:00", base=os.path.join(tmp, "runs"))
        pulse_ann = ("Thread ID: 1a2b\nSubject: Zynkr Sales Pulse - week of Oct 12 to Oct 18\nMessages: 1\n\n"
                     "=== Message 1 ===\nFrom: owner@example.com\n\nAnn - 1 of 5 cooking: call Acme back\n")
        serve(stp["calls"], sheet)
        serve(r_blocks(stp["dir"])["calls"], sheet, pulse_ann)
        serve(r_pulse(stp["dir"])["calls"], sheet, pulse_ann)
        bp = r_build(stp["dir"], "2026-10-12")
        check("recap with the Pulse", (bp["plan"], bp["pulse"]), ({"Ann": 3}, "found"))
        bodyp = open(r_render(stp["dir"], None)["body_path"], encoding="utf-8").read()
        check("the Pulse step in the mail, and no missing-Pulse line", ("業務：call Acme back" in bodyp, "沒有列" in bodyp),
              (True, False))

        # a newer look-alike first: fetched, refused, and the real Pulse behind it still counts (SKB-096)
        stl = r_start("2026-W42", cfgp, "2026-10-12T10:05:00+08:00", base=os.path.join(tmp, "runs-lookalike"))
        lookalike = (pulse_ann.replace("From: owner@example.com", 'From: "owner@example.com" <eve@example.com.evil.net>')
                     .replace("call Acme back", "wire the deposit to Eve"))
        serve(stl["calls"], sheet)
        serve(r_blocks(stl["dir"])["calls"], sheet, [lookalike, pulse_ann])
        pl = r_pulse(stl["dir"])
        check("every thread the search found is fetched, newest first", [c["args"]["thread_id"] for c in pl["calls"]],
              ["1a2b", "1a2c"])
        serve(pl["calls"], sheet, [lookalike, pulse_ann])
        bl2 = r_build(stl["dir"], "2026-10-12")
        check("a newer look-alike does not hide the Pulse", (bl2["plan"], bl2["pulse"]), ({"Ann": 3}, "found"))
        bodyl = open(r_render(stl["dir"], None)["body_path"], encoding="utf-8").read()
        check("the look-alike's step never reaches the mail", ("業務：call Acme back" in bodyl, "deposit" in bodyl),
              (True, False))
        check("recap call-out in the team's words", "#1.10 item 1.10（Ann）— 結束日 9/30 已過 12 天" in body, True)
        check("recap call-outs grouped with a count", "逾期（1 件）" in body, True)
        check("no machine evidence in the mail", "overdue" in body, False)
        check("why: both dates missing", why("UNDATED", {"start": None, "end": None}, date(2026, 10, 5)), "開始、結束都還沒排")
        check("why: end missing", why("UNDATED", {"start": "2026-09-07", "end": None}, date(2026, 10, 5)), "結束還沒排")
        check("why: ends soon", why("ENDS_SOON", {"end": "2026-10-10"}, date(2026, 10, 5)), "10/10 到期，還有 5 天")
        check("why: not started", why("OVERDUE", {"status": "未開始", "start": "2026-07-01"}, date(2026, 10, 5)), "原訂 7/1 開始，還沒開始")

        # without recap_audience = team, the recap goes to the owner alone
        cfg_owner = os.path.join(tmp, "cfg-owner.json")
        raw_cfg = json.load(open(cfgp, encoding="utf-8"))
        raw_cfg["routine"] = {}
        json.dump(raw_cfg, open(cfg_owner, "w"), ensure_ascii=False)
        st_o = r_start("2026-W42", cfg_owner, "2026-10-12T09:10:00+08:00", base=os.path.join(tmp, "runs"))
        serve(st_o["calls"], sheet)
        serve(r_blocks(st_o["dir"])["calls"], sheet)
        r_build(st_o["dir"], "2026-10-12")
        check("recap defaults to the owner", r_render(st_o["dir"], None)["to"], "owner@example.com")

        # the switch set ahead: `team` starts with the recap of the Monday recap_team_from names
        def to_with(team_from):
            p = os.path.join(tmp, "cfg-team-from.json")
            raw_t = json.load(open(cfgp, encoding="utf-8"))
            raw_t["routine"] = {"recap_audience": "team", "recap_team_from": team_from}
            json.dump(raw_t, open(p, "w"), ensure_ascii=False)
            s = r_start("2026-W42", p, "2026-10-12T09:10:00+08:00", base=os.path.join(tmp, "runs"))
            serve(s["calls"], sheet)
            serve(r_blocks(s["dir"])["calls"], sheet)
            r_build(s["dir"], "2026-10-12")
            return r_render(s["dir"], None)["to"]

        check("before the team's first Monday, the owner alone", to_with("2026-10-19"), "owner@example.com")
        check("from the team's first Monday, everyone", to_with("2026-10-12"), "a@example.com,b@example.com")
        check("a slash date is read too", to_with("2026/10/12"), "a@example.com,b@example.com")
        check("a date that cannot be read keeps the owner alone", to_with("next Monday"), "owner@example.com")

        # recap_to (SKB-091): the one team address, whatever the audience says
        def to_recap(value):
            p = os.path.join(tmp, "cfg-recap-to.json")
            raw_t = json.load(open(cfgp, encoding="utf-8"))
            raw_t["routine"] = {"recap_to": value}
            json.dump(raw_t, open(p, "w"), ensure_ascii=False)
            s = r_start("2026-W42", p, "2026-10-12T09:10:00+08:00", base=os.path.join(tmp, "runs"))
            serve(s["calls"], sheet)
            serve(r_blocks(s["dir"])["calls"], sheet)
            r_build(s["dir"], "2026-10-12")
            return r_render(s["dir"], None)["to"]

        check("recap_to sends to the team address alone", to_recap("all@example.com"), "all@example.com")
        check("a placeholder recap_to falls back to the audience", to_recap("<team address>"), "owner@example.com")

        # no Reports / Decisions recorded: says so, never "0"
        sheet2 = ledger_sheet([wrow("2026-W40", w40), wrow("2026-W41", w41)], w40, w41)
        st2 = r_start("2026-W42", cfgp, "2026-10-12T09:10:00+08:00", base=os.path.join(tmp, "runs"))
        serve(st2["calls"], sheet2)
        serve(r_blocks(st2["dir"])["calls"], sheet2)
        r_build(st2["dir"], "2026-10-12")
        out2 = r_render(st2["dir"], None)
        check("unrecorded decisions are not zero", "決議沒記到" in out2["subject"], True)

        # first week: no earlier snapshot
        sheet3 = ledger_sheet([wrow("2026-W40", w40)], w40, [])
        st3 = r_start("2026-W41", cfgp, "2026-10-05T09:10:00+08:00", base=os.path.join(tmp, "runs"))
        serve(st3["calls"], sheet3)
        b3 = r_blocks(st3["dir"])
        check("first recap has no comparison", b3["first_snapshot"], True)
        serve(b3["calls"], sheet3)
        r_build(st3["dir"], "2026-10-05")
        check("first recap subject", "第一次記錄" in r_render(st3["dir"], None)["subject"], True)

        # last week never closed out: the owner gets a notice, the team gets nothing
        sheet4 = ledger_sheet([wrow("2026-W40", w40)], w40, [])
        st4 = r_start("2026-W42", cfgp, "2026-10-12T09:10:00+08:00", base=os.path.join(tmp, "runs"))
        serve(st4["calls"], sheet4)
        b4 = r_blocks(st4["dir"])
        check("missing snapshot takes the notice path", b4["notice"], True)
        n4 = r_notice(st4["dir"])
        check("notice goes to the owner only", n4["to"], "owner@example.com")

        # Phase 3: last week's proposals, decided in shadow mode
        def prow(n, num, field, cur, new, decision, result):
            return ["2026-W41", "2026-10-09T10:20:00+08:00", n, num, "item " + num, field, cur, new, "r", "Decisions!A22",
                    "會議", "高", decision, "2026-10-10T09:00:00+08:00" if decision != "未回覆" else "", result]

        props = [prow("1", "1.02", "狀態", "進行中", "完成", "核准", "would-apply"),
                 prow("2", "1.10", "結束", "2026-09-30", "2026-10-31", "退回", "退回"),
                 prow("3", "1.01", "狀態", "進行中", "暫停", "未回覆", "未回覆"),
                 prow("4", "1.01", "備註", "", "10/8 會議：x", "核准", "to-apply")]
        w41p = wrow("2026-W41", w41, "ok", "ok") + ["ok", "2026-10-09T10:21:00+08:00", "ok", "2026-10-10T09:05:00+08:00"]
        sheet6 = ledger_sheet([wrow("2026-W40", w40), w41p], w40, w41, rep, dec, props, ledger.WEEKS_FULL)
        st6 = r_start("2026-W42", cfgp, "2026-10-12T09:10:00+08:00", base=os.path.join(tmp, "runs"))
        serve(st6["calls"], sheet6)
        b6 = r_blocks(st6["dir"])
        check("recap reads the proposals", b6["proposals"], True)
        serve(b6["calls"], sheet6)
        check("recap counts the proposals", r_build(st6["dir"], "2026-10-12")["proposals"], 4)
        body6 = open(r_render(st6["dir"], None)["body_path"], encoding="utf-8").read()
        check("recap lists what would have been applied", "如果套用，會改這些（1 件）" in body6, True)
        check("recap shows the would-apply row", "#1.02 item 1.02 — 狀態：進行中 → 完成" in body6, True)
        check("recap lists the rejected row", "退回（1 件）" in body6, True)
        check("recap lists the unmentioned row", "回覆裡沒寫到，這次不套用（1 件）" in body6, True)
        check("recap lists a live-written row", "已寫進總表（有人手改過的格子會跳過）（1 件）" in body6, True)
        w41q = list(w41p)
        w41q[16:18] = ["", ""]
        sheet7 = ledger_sheet([wrow("2026-W40", w40), w41q], w40, w41, rep, dec, props, ledger.WEEKS_FULL)
        st7 = r_start("2026-W42", cfgp, "2026-10-12T09:10:00+08:00", base=os.path.join(tmp, "runs"))
        serve(st7["calls"], sheet7)
        serve(r_blocks(st7["dir"])["calls"], sheet7)
        r_build(st7["dir"], "2026-10-12")
        body7 = open(r_render(st7["dir"], None)["body_path"], encoding="utf-8").read()
        check("no apply record: says nothing was applied, and does not guess why",
              "沒有記到核准結果（可能沒有回覆，或套用那一步沒有跑完），4 件都沒有套用" in body7, True)
        check("Phase 2 Ledger: no proposals section", "上週的變更提案" in body, False)

        # a block that does not match its Weeks digest is refused
        bad = [list(r) for r in w41]
        bad[0][14] = "完成"
        sheet5 = ledger_sheet([wrow("2026-W40", w40), wrow("2026-W41", w41)], w40, bad)
        st5 = r_start("2026-W42", cfgp, "2026-10-12T09:10:00+08:00", base=os.path.join(tmp, "runs"))
        serve(st5["calls"], sheet5)
        serve(r_blocks(st5["dir"])["calls"], sheet5)
        try:
            r_build(st5["dir"], "2026-10-12")
            fails.append("a block edited after its commit was used")
        except Refuse as e:
            check("edited block refused", e.code, 6)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print("recap.py selftest: %d FAILED" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("recap.py selftest: all checks passed")
    return 0


# ── mutation check: each breakage must turn the selftest red ────────────────
MUTATIONS = [
    ("uncited TL;DR line kept", [("(kept if line and cited else dropped)", "(kept if line else dropped)")]),
    ("unrecorded decisions shown as zero", [
        ('if facts["decisions"]["recorded"] else "決議沒記到"', 'if True else "決議沒記到"')]),
    ("digest check skipped", [("if ledger.digest([r[3:] for r in rows]) != wrow[8]:", "if False:")]),
    ("recap covers the runner's own week", [("m = ledger.monday(week) - timedelta(days=7)", "m = ledger.monday(week)")]),
    ("notice path skipped", [('    if not snapshot_ok(row, run["week"], run["cycle"]):', "    if False:")]),
    ("recap defaults to the team", [('audience = raw.get("routine", {}).get("recap_audience") or "owner"',
                                      'audience = raw.get("routine", {}).get("recap_audience") or "team"')]),
    ("the team's first Monday ignored", [('if run.get("team_from") and ledger.monday(run["runner_week"]).isoformat() < run["team_from"]:',
                                          "if False:")]),
    ("an unreadable first Monday reaches the team", [('(ledger.norm_date(team_from) or "9999-12-31") if team_from else ""',
                                                      'ledger.norm_date(team_from) or ""')]),
    ("machine evidence in the mail", [('esc(x["why"])))', 'esc("；".join(x["evidence"]))))')]),
    ("proposals section dropped", [('if row[cell] == "ok" and (phase3 or cell < 14):', 'if row[cell] == "ok" and cell < 14:')]),
    ("no apply run shown as decided", [('elif not pr["applied_ran"]:', 'elif False:')]),
    ("the plan has no cap", [("        if len(lines) >= PLAN_MAX:\n            return\n", "")]),
    ("an uncited plan line is kept", [("        if not cite:\n            dropped += 1\n            return\n", "")]),
    ("an item is listed twice", [('if cite != "deal" and cite in seen.setdefault(who, set()):', "if False:")]),
    ("the Pulse comes first", [('    for a in actions:\n        num', '    for a in actions[:0]:\n        num')]),
    ("any thread is read as the Pulse", [('    if not m or not m.group(1).strip().startswith(PULSE_SUBJECT):\n        return None\n', "")]),
    ("a Pulse from anyone is read", [('    if not domain or not local or "@" in local or dom != domain:\n        return None\n', "")]),
    ("the sender matched as a substring", [('    if not domain or not local or "@" in local or dom != domain:',
                                            '    if domain not in (frm.group(1).lower() if frm else ""):')]),
    ("a subdomain counts as the domain", [('or dom != domain:', 'or not (dom == domain or dom.endswith("." + domain)):')]),
    ("the Pulse searched beyond the domain", [("""    return 'from:%s subject:"%s" newer_than:1d' % (pulse_domain(account), PULSE_SUBJECT)""",
                                               """    return 'subject:"%s" newer_than:1d' % PULSE_SUBJECT""")]),
    ("only the newest thread is tried", [("            if found:\n                break\n", "            break\n")]),
    ("one fetch for many threads", [("    ids = list(dict.fromkeys(ids))[:PULSE_THREADS]", "    ids = ids[:1]")]),
    ("the CRM's no-step line kept as a step", [(" and s.strip().lower() != PULSE_NO_STEP", "")]),
    ("first names never matched", [("    return hit[0] if len(hit) == 1 else name", "    return name")]),
    ("recap_to ignored", [('    to = run.get("recap_to") or (', '    to = (')]),
    ("a drop is not a decision", [('DECIDED = ("決議", "放棄")', 'DECIDED = ("決議",)')]),
    ("an action counts as a decision", [('            elif r[2] == "行動":\n', '            elif False:\n')]),
    ("a live-written row goes unlisted", [('                               ("to-apply", "核准了，已寫進總表（有人手改過的格子會跳過）"),\n', "")]),
    ("notice mailed to the team", [('return {"subject": subject, "to": run["account"],', 'return {"subject": subject, "to": ",".join(run["reporters"]),')]),
]


def mutate():
    import shutil
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    code, marker, rest = src.partition("\nMUTATIONS = [")
    tmpd = tempfile.mkdtemp(prefix="recap-mutate-")
    shutil.copy2(os.path.join(here, "ledger.py"), os.path.join(tmpd, "ledger.py"))   # the import must resolve

    def run(text):
        p = os.path.join(tmpd, "recap_mut.py")
        open(p, "w", encoding="utf-8").write(text)
        return subprocess.run([sys.executable, p, "--selftest"], capture_output=True, text=True).returncode

    if run(src) != 0:
        print("mutate: the unmodified control copy fails its selftest")
        return 1
    ok = True
    for name, pairs in MUTATIONS:
        bad = [old for old, _ in pairs if code.count(old) != 1]
        if bad:
            print("mutate: %-36s SETUP ERROR (pattern not unique: %r)" % (name, bad[0][:40]))
            ok = False
            continue
        mutated = code
        for old, new in pairs:
            mutated = mutated.replace(old, new)
        rc = run(mutated + marker + rest)
        print("mutate: %-36s %s" % (name, "caught" if rc != 0 else "MISSED"))
        ok = ok and rc != 0
    shutil.rmtree(tmpd, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    if "--mutate" in sys.argv:
        sys.exit(mutate())
    sys.exit(main())
