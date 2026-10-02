#!/usr/bin/env python3
"""The Monday recap (SKB-044 Phase 2): what changed last week, what needs attention, what was
decided and what is blocked, read from the Weekly Ledger only, never the 331k-character Doc.

Like ledger.py, this script computes and the model executes: every step prints the exact MCP
calls, each with a path to save the tool's result to, word for word.

    recap.py start  --runner-week W [--config PATH]  -> the Weeks reads that decide what can be said
    recap.py blocks --dir D                           -> {"notice": true, ...} when last week never
                                                         closed out, else the block reads
    recap.py build  --dir D --today YYYY-MM-DD        -> facts.json + a short summary for the TL;DR
    recap.py render --dir D --tldr tldr.json          -> subject, recipients, recap.html; TL;DR lines
                                                         that cite no real item # are dropped
    recap.py notice --dir D                           -> the owner-only "close-out did not run" mail
    recap.py --selftest

The recap covers the ISO week BEFORE the runner's week. Its subject uses the team's `WB m/d` label;
the ISO key never reaches a reader (references/wording.md). The state rules are zynkr-gm's
derive_state.py, the one copy every brief and recap shares.

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
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
from ledger import Refuse, pad, parse_values, load_result, read_call, save_run, load_run, emit  # noqa: E402

DEFAULT_RULES = "~/.claude/skills/zynkr-gm/scripts/derive_state.py"
ITEM_NUM = re.compile(r"(?<![\d.])(\d{1,2}\.\d{2})(?![\d.])")


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
    audience = raw.get("routine", {}).get("recap_audience") or "owner"
    cfg.update(reporters=reporters, names=names, rules=rules, audience=audience if audience in ("owner", "team") else "owner",
               doc_url=("https://docs.google.com/document/d/%s/edit" % doc_id) if doc_id and "<" not in doc_id else "",
               tracker_url="https://docs.google.com/spreadsheets/d/%s/edit" % cfg["tracker"],
               ledger_url="https://docs.google.com/spreadsheets/d/%s/edit" % cfg["ledger"])
    return cfg


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
    rng = "Weeks!A%d:N%d" % (1 + k, 2 + k) if k >= 1 else "Weeks!A2:N2"
    run = dict(cfg, dir=d, runner_week=runner_week, week=target, k=k, weeks_range=rng)
    save_run(run)
    calls = [read_call(run, cfg["ledger"], "Weeks!A1:N1", "wh"), read_call(run, cfg["ledger"], rng, "wr")]
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
    wh = parse_values(load_result(os.path.join(d, "wh.txt")), run["ledger"], "Weeks!A1:N1")
    if not wh or pad(wh[0], 14) != ledger.WEEKS_HEADER + ledger.WEEKS_BEAT_HEADER:
        raise Refuse(4, "Weeks header is not the Phase 2 header (A–N)")
    wr = parse_values(load_result(os.path.join(d, "wr.txt")), run["ledger"], run["weeks_range"])
    k = run["k"]
    if k >= 1:
        prev_row = pad(wr[0], 14) if len(wr) > 0 else [""] * 14
        row = pad(wr[1], 14) if len(wr) > 1 else [""] * 14
    else:
        prev_row, row = None, pad(wr[0], 14) if wr else [""] * 14
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
    for tab, col, cell in (("Reports", "I", 10), ("Decisions", "H", 12)):
        if row[cell] == "ok":
            first, last = ledger.block_slot(tab, k)
            rng = "%s!A%d:%s%d" % (tab, first, col, last)
            pages[tab] = rng
            calls.append(read_call(run, run["ledger"], rng, tab.lower()))
    run.update(notice=False, row=row, prev_row=prev_row if prev_ok else None, pages=pages)
    save_run(run)
    return {"notice": False, "week": run["week"], "calls": calls,
            "first_snapshot": not prev_ok, "reports": row[10] == "ok", "decisions": row[12] == "ok"}


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

    def flagged(state):
        return [{"#": r["id"], "項目": r["item"], "負責人": r["owner"], "evidence": r["evidence"]}
                for r in st["rows"] if state in r["states"]]

    decisions = {"recorded": "Decisions" in run["pages"], "decided": [], "open": []}
    if decisions["recorded"]:
        drows = parse_values(load_result(os.path.join(d, "decisions.txt")), run["ledger"], run["pages"]["Decisions"])
        for r in (pad(x, 8) for x in drows):
            if r[0] != run["week"]:
                continue
            entry = {"內容": r[3], "負責人": r[4], "期限": r[5], "#": r[6]}
            (decisions["decided"] if r[2] == "決議" else decisions["open"]).append(entry)
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
    changes = []
    if diff:
        changes = [c for c in diff["changed"] if not c["cosmetic"]]
    facts = {"week": run["week"], "label": wb_label(run["week"]), "range": week_range(run["week"]),
             "today": today, "first_snapshot": prev is None, "items": names,
             "changes": changes, "added": diff["added"] if diff else [], "removed": diff["removed"] if diff else [],
             "overdue": flagged("OVERDUE"), "ends_soon": flagged("ENDS_SOON"),
             "undated": [x for x in flagged("UNDATED") if by_id[x["#"]]["priority"] in ("P0", "P1")],
             "propose_done": flagged("PROPOSE_DONE"), "paused": flagged("PAUSED"),
             "unknown_status": flagged("UNKNOWN_STATUS"),
             "decisions": decisions, "reports": reports,
             "links": {"tracker": run["tracker_url"], "doc": run["doc_url"], "ledger": run["ledger_url"]}}
    json.dump(facts, open(os.path.join(d, "facts.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    run.update(built=True)
    save_run(run)
    return {"week": run["week"], "label": facts["label"], "first_snapshot": facts["first_snapshot"],
            "changes": len(changes) + len(facts["added"]) + len(facts["removed"]),
            "overdue": [x["#"] for x in facts["overdue"]], "ends_soon": [x["#"] for x in facts["ends_soon"]],
            "undated": [x["#"] for x in facts["undated"]], "propose_done": [x["#"] for x in facts["propose_done"]],
            "decided": len(decisions["decided"]), "open_decisions": len(decisions["open"]),
            "blockers": len(reports["blockers"]), "facts": os.path.join(d, "facts.json"),
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
    o = ['<div style="font-family:-apple-system,Segoe UI,Noto Sans TC,sans-serif;font-size:14px;line-height:1.6;color:#1d1d1f;max-width:680px">']
    o.append("<p>%s（%s）的週報，資料來自主追蹤表每週五的快照和週報帳本。</p>" % (esc(facts["label"]), esc(facts["range"])))
    if tldr:
        o.append("<h3>重點</h3><ul>%s</ul>" % "".join(li(esc(t)) for t in tldr))
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
    notes = []
    for key, title in (("overdue", "逾期"), ("ends_soon", "兩週內到期"), ("undated", "P0/P1 還沒排日期"),
                       ("propose_done", "備註說做完了，狀態還沒改"), ("unknown_status", "狀態寫法不在清單裡")):
        for x in facts[key]:
            notes.append(li("%s · #%s %s（%s）— %s" % (title, esc(x["#"]), esc(x["項目"]), esc(x["負責人"] or "沒有負責人"),
                                                   esc("；".join(x["evidence"])))))
    o.append("<ul>%s</ul>" % "".join(notes) if notes else "<p>沒有逾期、快到期或缺日期的項目</p>")
    o.append("<h3>上週談定的事</h3>")
    dec = facts["decisions"]
    if not dec["recorded"]:
        o.append("<p>上週的決議沒有記到帳本，請看週四的 Doc 區塊</p>")
    elif not (dec["decided"] or dec["open"]):
        o.append("<p>上週會議沒有記下決議</p>")
    else:
        if dec["decided"]:
            o.append("<ul>%s</ul>" % "".join(li("%s — %s，%s" % (esc(x["內容"]), esc(x["負責人"]), esc(x["期限"])))
                                              for x in dec["decided"]))
        if dec["open"]:
            o.append("<p>還沒定案</p><ul>%s</ul>" % "".join(li(esc(x["內容"])) for x in dec["open"]))
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
    o.append('<p style="color:#6e6e73;font-size:12px">主追蹤表 <a href="%s">開啟</a>%s · 週報帳本 <a href="%s">開啟</a></p>'
             % (esc(links["tracker"]), (' · 週報 Doc <a href="%s">開啟</a>' % esc(links["doc"])) if links["doc"] else "",
                esc(links["ledger"])))
    o.append("</div>")
    return "".join(o)


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
    to = ",".join(run["reporters"]) if run["audience"] == "team" else run["account"]
    return {"subject": subject, "to": to, "audience": run["audience"], "body_path": path, "body_format": "html",
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
    for name in ("blocks", "notice"):
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
            "  out.append({'id':r['#'],'item':r['項目（正規化）'],'priority':r['Priority'],'owner':r['負責人'],'states':st,'evidence':['結束 '+r['結束']] if st else []})\n"
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

        def serve(calls, sheet):
            for c in calls:
                rng = c["args"]["range_name"]
                tab, r0, r1 = re.match(r"^(\w+)!A(\d+):[A-Z](\d+)$", rng).groups()
                g = sheet[tab]
                got = [g[i - 1] if i - 1 < len(g) else [] for i in range(int(r0), int(r1) + 1)]
                while got and not any(x.strip() for x in got[-1]):
                    got.pop()
                open(c["save"], "w", encoding="utf-8").write(fmt(rng, got))

        def ledger_sheet(weeks_rows, w40rows, w41rows, rep=None, dec=None):
            snap = [ledger.SNAPSHOT_HEADER] + [[""] * 16] * 200
            for i, r in enumerate(w40rows):
                snap[1 + i] = r
            for i, r in enumerate(w41rows):
                snap[101 + i] = r
            reports = [ledger.REPORTS_HEADER] + [[""] * 9] * 40
            for i, r in enumerate(rep or []):
                reports[21 + i] = r
            decisions = [ledger.DECISIONS_HEADER] + [[""] * 8] * 40
            for i, r in enumerate(dec or []):
                decisions[21 + i] = r
            return {"Weeks": [ledger.WEEKS_HEADER + ledger.WEEKS_BEAT_HEADER] + weeks_rows,
                    "Snapshot": snap, "Reports": reports, "Decisions": decisions}

        rep = [["2026-W41", "2026-10-05T01:00:00Z", "a@example.com", "#Sales", "做完 A", "做 B", "", "等報價", "tagged"]]
        dec = [["2026-W41", "2026-10-08", "決議", "1.02 改月底交", "Ann", "2026-10-30", "1.02", "x"],
               ["2026-W41", "2026-10-08", "待決", "要不要外包", "", "", "", "x"]]
        sheet = ledger_sheet([wrow("2026-W40", w40), wrow("2026-W41", w41, "ok", "ok")], w40, w41, rep, dec)
        st = r_start("2026-W42", cfgp, "2026-10-12T09:10:00+08:00", base=os.path.join(tmp, "runs"))
        check("recap targets the previous week", st["week"], "2026-W41")
        serve(st["calls"], sheet)
        bl = r_blocks(st["dir"])
        check("recap not a notice", bl["notice"], False)
        serve(bl["calls"], sheet)
        built = r_build(st["dir"], "2026-10-12")
        check("recap changes", built["changes"], 1)
        check("recap overdue from the state rules", built["overdue"], ["1.10"])
        check("recap decisions", (built["decided"], built["open_decisions"]), (1, 1))
        check("recap blockers", built["blockers"], 1)
        tl = os.path.join(tmp, "tldr.json")
        json.dump(["#1.01 開始進行", "沒有編號的一句"], open(tl, "w"), ensure_ascii=False)
        out = r_render(st["dir"], tl)
        check("recap subject", out["subject"], "【週報】WB 10/5 那週 — 變更 1 件 · 決議 1 件 · 逾期 1 件")
        check("recap recipients", out["to"], "a@example.com,b@example.com")
        check("recap drops an uncited line", out["tldr_dropped"], ["沒有編號的一句"])
        body = open(out["body_path"], encoding="utf-8").read()
        check("recap shows the change", "#1.01 item 1.01 — 狀態：未開始 → 進行中" in body, True)
        check("recap names the blocker by display name", "Ann：等報價" in body, True)
        check("recap lists who did not post", "上週沒交週報：b" in body, True)
        check("recap escapes html", "<script>" not in body, True)

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
