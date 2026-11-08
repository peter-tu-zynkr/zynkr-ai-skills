#!/usr/bin/env python3
"""sections.py — the team blocks for Thursday's meeting (SKB-091 AC-13): under each team heading of this
Thursday's section, one 〔自動彙整〕 block with 進度 · 卡關 · 下一步 · 待討論, from the Ledger's Harvest rows (collect,
just before) and Monday's recap facts (the tracker as of last week, the meeting's actions, the Pulse).

    sections.py start --week W [--config PATH]              -> the Weeks row and the Harvest block to read
    sections.py render --dir D --routing R --stamp "11-05 09:40"
                                                            -> blocks in render_block's shape, for
                                                               `render_block.py ops`
    sections.py --selftest | --mutate

What goes where, per person (the heading's owner chip, named through chat_ids):
  進度    the harvest's shipped (完成) and moving (進行中) lines, then the Pulse's sales steps;
          「本週無資料」 when there is no harvest for them
  卡關    the harvest's waiting lines, then items overdue as of Monday
  下一步  last week's meeting actions, only when last week's tidy did not already fill them into the
          kept block (`<last week>.tidy.done`), so the team never reads the same action twice
  待討論  at most three keep / hand over / drop choices (paused items), then the sure gaps: items the
          state rules say look done but are not marked 完成
It writes nothing and reads nothing itself: the model makes the printed calls, as with ledger.py.
"""
import argparse
import glob
import json
import os
import re
import sys

LEDGER_API = 3   # SKB-118: load_result refuses a result changed after the runner saved it
HERE = os.path.dirname(os.path.abspath(__file__))


def core_dir():
    """zynkr-ops-weekly's scripts folder (ledger.py, recap.py); ZYNKR_OPS_WEEKLY_SCRIPTS overrides it."""
    env = os.environ.get("ZYNKR_OPS_WEEKLY_SCRIPTS")
    tried = ([env] if env else []) + [HERE, os.path.normpath(os.path.join(HERE, "..", "..", "zynkr-ops-weekly", "scripts"))]
    for d in tried:
        if os.path.exists(os.path.join(d, "ledger.py")):
            return d
    raise SystemExit("sections.py: zynkr-ops-weekly's ledger.py not found (looked in %s). Install zynkr-ops-weekly, "
                     "or set ZYNKR_OPS_WEEKLY_SCRIPTS to its scripts folder." % ", ".join(tried))


sys.path.insert(0, HERE)
sys.path.insert(1, core_dir())
import ledger as L  # noqa: E402
import recap as R  # noqa: E402
from render_block import STAMP, body_text  # noqa: E402
if getattr(L, "API", 1) != LEDGER_API or "Harvest" not in L.BLOCKS:
    raise SystemExit("sections.py: the installed zynkr-ops-weekly has no Harvest tab; update it (SKB-091)")

QUIET = "本週無資料"
CHOICES = 3
CAP = {"進度": 6, "卡關": 4, "下一步": 5}


def load_cfg(path=None):
    cfg = L.load_config(path)
    raw = json.load(open(cfg["path"], encoding="utf-8"))
    ids = {k: v for k, v in (raw.get("chat_ids") or {}).items() if not k.startswith("$") and isinstance(v, str)}
    aliases = {k: v for k, v in ((raw.get("routine") or {}).get("name_aliases") or {}).items()
               if not k.startswith("$") and isinstance(v, str)}
    cfg.update(roster=[k for k in ids if not k.startswith("users/")], aliases=aliases,
               names={v: k for k, v in ids.items() if not k.startswith("users/")})
    return cfg


def s_start(week, config=None, now=None, base=None):
    cfg = load_cfg(config)
    k = L.week_index(week, cfg["epoch"])
    now = L.parse_now(now)
    d = os.path.join(base or os.path.join(L.state_dir(), "runs"), "%s-sections-%s" % (week, now.strftime("%Y%m%dT%H%M%S")))
    n = 1
    while os.path.exists(d + ("" if n == 1 else "-%d" % n)):
        n += 1
    d = d + ("" if n == 1 else "-%d" % n)
    os.makedirs(d)
    r = L.weeks_row(k)
    first, last = L.block_slot("Harvest", k)
    # the block is 80 rows and a read shows at most 50 (L.PAGE): one read per page, or the read is refused
    pages = [[a, min(a + L.PAGE - 1, last)] for a in range(first, last + 1, L.PAGE)]
    run = dict(cfg, dir=d, week=week, k=k, weeks_row=r, harvest_pages=pages)
    L.save_run(run)
    return {"dir": d, "week": week, "label": R.wb_label(week),
            "calls": [L.read_call(run, cfg["ledger"], "Weeks!A%d:T%d" % (r, r), "wr")]
            + [L.read_call(run, cfg["ledger"], "Harvest!A%d:H%d" % (a, b), "harvest" if i == 0 else "harvest%d" % (i + 1))
               for i, (a, b) in enumerate(pages)]}


def latest_facts(week):
    """Monday's recap facts: the recap of last week, run this week. None when it never built."""
    hits = sorted(glob.glob(os.path.join(L.state_dir(), "runs", "%s-recap-*" % R.previous_week(week), "facts.json")))
    return hits[-1] if hits else None


def mine(run, who, entries, field="負責人", everyone=False):
    """The entries `who` owns. With `everyone`, an `All` one (recap reads it as 全體) is everyone's: a
    meeting action for the whole team goes to every team's 下一步, as tidy's fill writes it (W45
    review). A tracker item owned by 全體 is no team's here: it would fill every team's 卡關 and take
    one of each team's three 待討論 choices (review round 2, 10-31)."""
    out = []
    for e in entries:
        owners = R.owners_of(run, e.get(field))
        if who in owners or (everyone and "全體" in owners):
            out.append(e)
    return out


def parts_for(run, who, harvest, facts, filled):
    """[(label, [items])] for one person, in the frozen label order; 進度 is always there."""
    rows = [r for r in harvest if r[3] == who]
    out = {"進度": [], "卡關": [], "下一步": [], "待討論": []}
    if not rows or all(r[5] == "quiet" for r in rows):
        out["進度"].append(QUIET)
    for r in rows:
        if r[5] == "shipped":
            out["進度"].append("完成：%s" % R.clip(r[6], 80))
    for r in rows:
        if r[5] == "moving":
            out["進度"].append("進行中：%s" % R.clip(r[6], 80))
        elif r[5] == "waiting":
            out["卡關"].append(R.clip(r[6], 80))
    if facts:
        for p in facts.get("plan", []):
            if p["who"] == who:
                out["進度"] += [line for line in p["lines"] if line.startswith("業務：")]
        out["卡關"] += ["#%s %s — %s" % (x["#"], R.clip(x["項目"], 30), x["why"]) for x in mine(run, who, facts.get("overdue", []))]
        if not filled:
            for a in mine(run, who, facts.get("decisions", {}).get("actions", []), everyone=True):
                due = R.as_date(L.norm_date(a["期限"]) or a["期限"])
                out["下一步"].append("%s%s%s" % ("#%s " % a["#"] if a["#"] else "", R.clip(a["內容"], 50),
                                                 "（%s 前）" % R.md(due) if due else ""))
        out["待討論"] = ["#%s %s：留著、交給別人，還是放棄？" % (x["#"], R.clip(x["項目"], 30))
                       for x in mine(run, who, facts.get("paused", []))][:CHOICES]
        out["待討論"] += ["#%s %s — %s，要標 完成 嗎？" % (x["#"], R.clip(x["項目"], 30), x["why"])
                        for x in mine(run, who, facts.get("propose_done", []))]
    return [(label, items[:CAP.get(label, len(items))]) for label, items in out.items() if items]


def s_render(d, routing_path, stamp, facts_path=None):
    run = L.load_run(d)
    r = run["weeks_row"]
    wr = L.parse_values(L.load_result(os.path.join(d, "wr.txt")), run["ledger"], "Weeks!A%d:T%d" % (r, r))
    row = L.pad(wr[0], 20) if wr else [""] * 20
    if row[0] not in ("", run["week"]):
        raise L.Refuse(4, "Weeks row %d belongs to %s, not %s" % (r, row[0], run["week"]))
    harvested = row[18] == "ok"
    harvest = []
    if harvested:
        got = []
        for i, (a, b) in enumerate(run["harvest_pages"]):
            got += L.parse_values(L.load_result(os.path.join(d, "harvest.txt" if i == 0 else "harvest%d.txt" % (i + 1))),
                                  run["ledger"], "Harvest!A%d:H%d" % (a, b))
        harvest = [L.pad(x, 8) for x in got if L.pad(x, 8)[0] == run["week"]]
    facts_path = facts_path or latest_facts(run["week"])
    facts = json.load(open(facts_path, encoding="utf-8")) if facts_path else None
    filled = os.path.exists(os.path.join(L.state_dir(), "%s.tidy.done" % R.previous_week(run["week"])))
    routing = json.load(open(routing_path, encoding="utf-8"))
    label = R.wb_label(run["week"])
    header = STAMP.format(week=label, stamp=stamp)
    blocks, nameless, routed = [], [], set()
    for h in routing["headings"]:
        if h.get("grouped_with_previous") or not h.get("primary", True):
            continue
        who = run["names"].get(h["owner_email"])
        if not who:
            nameless.append({"heading": h["heading"], "owner_email": h["owner_email"]})
            continue
        routed.add(who)
        body = body_text(parts_for(run, who, harvest, facts, filled))
        blocks.append({"heading": h["heading"], "owner_email": h["owner_email"], "owner_name": who,
                       "stamp_line": header, "body": body, "text": header + "\n" + body,
                       "lines": 1 + len(body.split("\n"))})
    return {"week": label, "stamp": header, "idempotency_key": "〔自動彙整 %s" % label, "blocks": blocks,
            "harvest": "recorded" if harvested else "not-recorded", "facts": facts_path, "next_steps_filled": filled,
            "owners_without_name": nameless,
            "harvest_without_heading": sorted({x[3] for x in harvest} - routed),
            "counts": {"blocks": len(blocks), "quiet": sum(1 for b in blocks if QUIET in b["body"])}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("start")
    s.add_argument("--week", required=True)
    s.add_argument("--config")
    r = sub.add_parser("render")
    r.add_argument("--dir", required=True)
    r.add_argument("--routing", required=True, help="parse_routing.py's output, saved as a file")
    r.add_argument("--stamp", required=True, help='the time shown in the stamp, e.g. "11-05 09:40"')
    r.add_argument("--facts", help="a recap facts.json other than Monday's (by hand only)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.mutate:
        return mutate()
    try:
        if a.cmd == "start":
            L.emit(s_start(a.week, a.config))
        elif a.cmd == "render":
            L.emit(s_render(a.dir, a.routing, a.stamp, a.facts))
        else:
            ap.print_help()
            return 2
    except L.Refuse as e:
        print("sections.py: %s" % e, file=sys.stderr)
        return e.code
    return 0


def selftest():
    import shutil
    import tempfile
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append("%s:\n    got  %r\n    want %r" % (name, got, want))

    tmp = tempfile.mkdtemp(prefix="sections-selftest-")
    os.environ["ZYNKR_OPS_WEEKLY_STATE"] = state = os.path.join(tmp, "state")
    os.makedirs(state)
    try:
        cfgp = os.path.join(tmp, "cfg.json")
        json.dump({"google_account": "owner@example.com",
                   "chat_ids": {"Ann Lee": "ann@example.com", "users/1": "ann@example.com", "Bob Wu": "bob@example.com",
                                "Cat Ho": "cat@example.com"},
                   "routine": {"name_aliases": {"Bobby": "Bob Wu"}},
                   "sources": {"main_tracker": {"id": "TRK", "tab": "T", "cycle": "2026H2"},
                               "ledger": {"id": "LED", "epoch_week": "2026-W40"}}}, open(cfgp, "w"))
        W = "2026-W45"
        k = L.week_index(W, "2026-W40")
        st = s_start(W, cfgp, "2026-11-05T09:35:00+08:00", base=os.path.join(tmp, "runs"))

        def sheet(rng, rows):
            if not rows:
                return "No data found in range '%s' for x." % rng
            return ("Successfully read %d rows from range '%s' in spreadsheet LED for x:\n" % (len(rows), rng)
                    + "".join("Row %2d: %s\n" % (i + 1, r) for i, r in enumerate(rows[:50]))
                    + ("... and %d more rows\n" % (len(rows) - 50) if len(rows) > 50 else ""))

        rr = L.weeks_row(k)
        weeks = [W] + [""] * 17 + ["ok", "2026-11-05T09:20:00+08:00"]
        at = "2026-11-05T09:20:00+08:00"
        harvest = [[W, at, "ann", "Ann Lee", "SEO", "waiting", "needs input: which keyword first", "harvest-ann.md"],
                   [W, at, "ann", "Ann Lee", "SEO", "shipped", "three articles live (abc1234)", "harvest-ann.md"],
                   [W, at, "ann", "Ann Lee", "SEO", "moving", "the FAQ page", "harvest-ann.md"],
                   [W, at, "bob", "Bob Wu", "", "quiet", QUIET, "harvest-bob.md"],
                   [W, at, "dan", "Dan Yu", "Ops", "shipped", "a thing", "harvest-dan.md"],
                   ["2026-W44", at, "ann", "Ann Lee", "SEO", "shipped", "last week's work", "harvest-ann.md"]]
        open(st["calls"][0]["save"], "w").write(sheet("Weeks!A%d:T%d" % (rr, rr), [weeks]))
        first = L.block_slot("Harvest", k)[0]
        grid = (harvest + [["2026-W44", at, "zed", "Zed", "", "shipped", "a row of another week", "harvest-zed.md"]] * 44
                + [[W, at, "cat", "Cat Ho", "財務", "shipped", "books closed", "harvest-cat.md"]])
        for c in st["calls"][1:]:
            a, b = (int(x) for x in re.match(r"^Harvest!A(\d+):H(\d+)$", c["args"]["range_name"]).groups())
            open(c["save"], "w").write(sheet(c["args"]["range_name"], grid[a - first:b - first + 1]))
        facts = {"plan": [{"who": "Ann Lee", "lines": ["#1.02 官網 — 已逾期", "業務：call Acme back"]}],
                 # a tracker item owned by All / 全體 is no team's: it must not fill each 卡關 or take a choice
                 "overdue": [{"#": "9.01", "項目": "全公司盤點", "負責人": "All", "why": "10/28 到期"},
                             {"#": "1.02", "項目": "官網改版", "負責人": "Ann Lee", "why": "10/30 到期"}],
                 "paused": [{"#": "9.02", "項目": "公司活動", "負責人": "全體", "why": ""}]
                 + [{"#": "2.0%d" % i, "項目": "項目%d" % i, "負責人": "Ann Lee、Bob Wu", "why": ""} for i in range(1, 6)],
                 "propose_done": [{"#": "1.05", "項目": "名單匯入", "負責人": "Bobby", "why": "harvest 說上線了"}],
                 "decisions": {"actions": [{"#": "1.03", "內容": "寄提案", "負責人": "Ann Lee", "期限": "2026-11-06", "狀態": "已排定"},
                                           {"#": "", "內容": "整理名單", "負責人": "Bob Wu", "期限": "", "狀態": "待定"},
                                           {"#": "", "內容": "全員填問卷", "負責人": "All", "期限": "", "狀態": "待定"}]}}
        rdir = os.path.join(state, "runs", "2026-W44-recap-20261102T100500")
        os.makedirs(rdir)
        json.dump(facts, open(os.path.join(rdir, "facts.json"), "w"), ensure_ascii=False)
        routing = os.path.join(tmp, "routing.json")
        json.dump({"headings": [{"heading": "行銷", "owner_email": "ann@example.com"},
                                {"heading": "行銷 · SEO", "owner_email": "ann@example.com", "grouped_with_previous": True},
                                {"heading": "業務", "owner_email": "bob@example.com"},
                                {"heading": "財務", "owner_email": "cat@example.com"},
                                {"heading": "外包", "owner_email": "eve@example.com"}]}, open(routing, "w"), ensure_ascii=False)
        out = s_render(st["dir"], routing, "11-05 09:40")
        by = {b["heading"]: b for b in out["blocks"]}
        check("one block per primary heading with a known owner, in the Doc's order",
              [b["heading"] for b in out["blocks"]], ["行銷", "業務", "財務"])
        check("Ann: the four parts, in order", by["行銷"]["body"].split("\n"),
              ["進度", "\t完成：three articles live (abc1234)", "\t進行中：the FAQ page", "\t業務：call Acme back",
               "卡關", "\tneeds input: which keyword first", "\t#1.02 官網改版 — 10/30 到期",
               "下一步", "\t#1.03 寄提案（11/6 前）", "\t全員填問卷",
               "待討論", "\t#2.01 項目1：留著、交給別人，還是放棄？", "\t#2.02 項目2：留著、交給別人，還是放棄？",
               "\t#2.03 項目3：留著、交給別人，還是放棄？"])
        check("Bob: a quiet week, an alias's sure gap past the three choices",
              by["業務"]["body"].split("\n"),
              ["進度", "\t" + QUIET, "下一步", "\t整理名單", "\t全員填問卷",
               "待討論", "\t#2.01 項目1：留著、交給別人，還是放棄？", "\t#2.02 項目2：留著、交給別人，還是放棄？",
               "\t#2.03 項目3：留著、交給別人，還是放棄？", "\t#1.05 名單匯入 — harvest 說上線了，要標 完成 嗎？"])
        check("Cat: a row on the Harvest block's second page is read, and an All action is everyone's",
              by["財務"]["body"], "進度\n\t完成：books closed\n下一步\n\t全員填問卷")
        check("the stamp is this week's", by["行銷"]["stamp_line"], "〔自動彙整 WB 11/2 · 11-05 09:40〕")
        check("diagnostics", (out["owners_without_name"], out["harvest_without_heading"]),
              ([{"heading": "外包", "owner_email": "eve@example.com"}], ["Dan Yu"]))
        open(os.path.join(state, "2026-W44.tidy.done"), "w").write("x")
        out = s_render(st["dir"], routing, "11-05 09:40")
        check("after tidy's fill, 下一步 is not written twice",
              [b["heading"] for b in out["blocks"] if "下一步" in b["body"]], [])
        open(st["calls"][0]["save"], "w").write(sheet("Weeks!A%d:T%d" % (rr, rr), [[W]]))
        out = s_render(st["dir"], routing, "11-05 13:05")
        check("without collect, everyone is 本週無資料", (out["harvest"], out["counts"]["quiet"]), ("not-recorded", 3))
        shutil.rmtree(rdir)
        out = s_render(st["dir"], routing, "11-05 13:05")
        by = {b["heading"]: b for b in out["blocks"]}
        check("without Monday's facts, the harvest alone", (out["facts"], by["財務"]["body"]), (None, "進度\n\t" + QUIET))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("sections.py selftest: %d FAILED" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("sections.py selftest: all checks passed")
    return 0


MUTATIONS = [
    ("the Harvest read stops at its first page", [("for a in range(first, last + 1, L.PAGE)]",
                                                   "for a in range(first, first + 1, L.PAGE)]")]),
    ("a quiet week reads as progress", [('    if not rows or all(r[5] == "quiet" for r in rows):\n', "    if not rows:\n")]),
    ("no cap on the choices", [("for x in mine(run, who, facts.get(\"paused\", []))][:CHOICES]",
                                "for x in mine(run, who, facts.get(\"paused\", []))]")]),
    ("下一步 written twice", [("        if not filled:\n", "        if True:\n")]),
    ("an All action reaches nobody", [('        if who in owners or (everyone and "全體" in owners):', '        if who in owners:')]),
    ("a 全體 tracker item fills every team", [('        if who in owners or (everyone and "全體" in owners):',
                                              '        if who in owners or "全體" in owners:')]),
    ("grouped headings get a block", [('        if h.get("grouped_with_previous") or not h.get("primary", True):',
                                       '        if not h.get("primary", True):')]),
    ("an unknown owner gets a block", [("        if not who:\n            nameless.append", "        if False:\n            nameless.append")]),
    ("an unharvested week is read", [('    harvested = row[18] == "ok"', "    harvested = True")]),
    ("other weeks' harvest rows count", [("if L.pad(x, 8)[0] == run[\"week\"]]", "]")]),
    ("aliases ignored", [("        owners = R.owners_of(run, e.get(field))",
                          "        owners = [e.get(field)]")]),
    ("the Pulse lost", [('                out["進度"] += [line for line in p["lines"] if line.startswith("業務：")]',
                         "                pass")]),
]


def mutate():
    import shutil
    import subprocess
    import tempfile
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    code, marker, rest = src.partition("\nMUTATIONS = [")
    tmpd = tempfile.mkdtemp(prefix="sections-mutate-")
    shutil.copy2(os.path.join(HERE, "render_block.py"), os.path.join(tmpd, "render_block.py"))
    env = dict(os.environ, ZYNKR_OPS_WEEKLY_SCRIPTS=core_dir())

    def run(text):
        p = os.path.join(tmpd, "sections_mut.py")
        open(p, "w", encoding="utf-8").write(text)
        return subprocess.run([sys.executable, p, "--selftest"], capture_output=True, text=True, env=env).returncode

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
    sys.exit(main())
