#!/usr/bin/env python3
"""The meeting's minutes (SKB-091 AC-14): find the Thursday meeting's transcript by its calendar title and
date, then check what the model read out of it before anything is written.

Like ledger.py, this script computes and never talks to Google or Fireflies. Each step prints the
exact calls to make, with a path to save each result to word for word; the next step reads them back.

    minutes.py start --week W [--config PATH] [--now ISO]
        -> a run folder, the Fireflies listing call for the meeting day and the tracker's size
    minutes.py find  --dir D
        -> the tracker reads (#, 項目) and the one transcript titled `meeting.calendar_title` on that
           Thursday (Taipei) with the call that fetches it; or "found": false: read the meeting's Doc
           section as edited instead
    minutes.py check --dir D --input minutes.json [--now ISO]
        -> refuses an owner off the roster, an item # the tracker lacks, a date that is not a date;
           writes rows.json (the Ledger's Decisions block), block.json (the Doc's 會議紀錄 block, for
           render_block.py ops) and fill.json (each person's 下一步 and 待討論, for tidy)

minutes.json, written by the model from the transcript (or the Doc) and nothing else:

    {"source": "fireflies" | "doc",
     "decisions": [{"text", "item"?}],
     "actions":   [{"what", "owner": name | [names] | "", "due": "YYYY-MM-DD" | "", "item"?, "new"?: true}],
     "blockers":  [{"text", "owner"?, "item"?, "since"?: "YYYY-MM-DD"}],
     "topics":    [{"text", "owner"?}],
     "dropped":   [{"item", "text"}],
     "progress":  [{"item", "text", "state"?}]}

An owner is a roster name exactly as the tracker writes it (the config's `chat_ids` display names) or
`All`. An action with no owner or no date stays open (狀態 待定). A blocker first seen more than seven
days before the meeting is a risk (類型 風險).

Exit codes are ledger.py's: 2 config or arguments · 3 input refused · 4 no transcript.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta

LEDGER_API = 2


def core_dir():
    """zynkr-ops-weekly's scripts folder, which holds ledger.py (SKB-091: the Ledger code stays in the
    core and the other skills read it there, never a copy). ZYNKR_OPS_WEEKLY_SCRIPTS overrides it."""
    here = os.path.dirname(os.path.abspath(__file__))
    env = os.environ.get("ZYNKR_OPS_WEEKLY_SCRIPTS")
    tried = ([env] if env else []) + [here, os.path.normpath(os.path.join(here, "..", "..", "zynkr-ops-weekly", "scripts"))]
    for d in tried:
        if os.path.exists(os.path.join(d, "ledger.py")):
            return d
    raise SystemExit("minutes.py: zynkr-ops-weekly's ledger.py not found (looked in %s). Install zynkr-ops-weekly, "
                     "or set ZYNKR_OPS_WEEKLY_SCRIPTS to its scripts folder." % ", ".join(tried))


sys.path.insert(0, core_dir())
import ledger as L  # noqa: E402
if getattr(L, "API", 1) != LEDGER_API:
    raise SystemExit("minutes.py: zynkr-ops-weekly's ledger.py speaks API %s, this script needs %s; install both "
                     "skills at the same version" % (getattr(L, "API", 1), LEDGER_API))

BLOCK_ROWS = L.BLOCKS["Decisions"][0]
ITEM_RE = re.compile(r"^\d{1,2}\.\d{2}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VOCAB = ("未開始", "進行中", "暫停", "完成", "放棄")
RISK_DAYS = 7
MAX_TEXT = 200
TITLE = "會議紀錄"                     # the block's title after its stamp, like the old 本週會議議程


# ── the week ─────────────────────────────────────────────────────────────────
def meeting_day(week):
    return L.monday(week) + timedelta(days=3)


def wb_label(week):
    m = L.monday(week)
    return "WB %d/%d" % (m.month, m.day)


def md(d):
    return "%d/%d" % (d.month, d.day)


def load_settings(path):
    raw = json.load(open(path, encoding="utf-8"))
    title = str((raw.get("meeting") or {}).get("calendar_title") or "").strip()
    if not title or title.startswith("<"):
        raise L.Refuse(2, "config %s has no meeting.calendar_title" % path)
    names = [k for k in (raw.get("chat_ids") or {}) if not k.startswith("$") and not k.startswith("users/")]
    if not names:
        raise L.Refuse(2, "config %s: chat_ids holds no display names, so there is no roster" % path)
    return {"title": title, "roster": names + ["All"]}


def doc_heading(d):
    """The week section's heading as the scaffold writes it: `Nov 5, 2026`, the day never zero-padded
    (`MONTHS[m] + ' ' + getDate()` in scaffold.gs). strftime's %d would give `Nov 05, 2026`, a heading
    the Doc never holds (W45 review, 10-31)."""
    return "%s %d, %d" % (d.strftime("%b"), d.day, d.year)


# ── start ────────────────────────────────────────────────────────────────────
def m_start(week, config=None, now=None, base=None):
    cfg = L.load_config(config)
    st = load_settings(cfg["path"])
    now = L.parse_now(now)
    thu = meeting_day(week)
    d = os.path.join(base or os.path.join(L.state_dir(), "runs"), "%s-minutes-%s" % (week, now.strftime("%Y%m%dT%H%M%S")))
    n = 1
    while os.path.exists(d + ("" if n == 1 else "-%d" % n)):
        n += 1
    d = d + ("" if n == 1 else "-%d" % n)
    os.makedirs(d)
    run = dict(cfg, dir=d, week=week, meeting=thu.isoformat(), title=st["title"], roster=st["roster"],
               heading=doc_heading(thu))
    L.save_run(run)
    listing = {"tool": "mcp__fireflies__fireflies_get_transcripts",
               "args": {"fromDate": (thu - timedelta(days=1)).isoformat(), "toDate": (thu + timedelta(days=1)).isoformat(),
                        "keyword": st["title"], "scope": "title", "format": "json", "limit": 10},
               "save": os.path.join(d, "listing.json")}
    calls = [listing, L.info_call(run, cfg["tracker"], "ti")]
    return {"dir": d, "week": week, "meeting": thu.isoformat(), "calls": calls}


# ── find ─────────────────────────────────────────────────────────────────────
def taipei_date(s):
    if not s:
        return None             # parse_now(None) means "now": an entry with no date is never today's
    try:
        return L.parse_now(s).date()
    except (ValueError, TypeError):
        return None


def pick(listing, title, thu):
    """The transcripts titled `title` held on `thu` (Taipei). Never "the latest": a recording on another
    day or under another title is not this meeting, whatever its date."""
    if isinstance(listing, dict) and isinstance(listing.get("result"), str):
        listing = json.loads(listing["result"])
    if not isinstance(listing, list):
        raise L.Refuse(3, "the Fireflies listing is not a JSON list (was it saved with format json?)")
    found = [t for t in listing if isinstance(t, dict) and str(t.get("title") or "").strip() == title
             and taipei_date(t.get("dateString")) == thu]
    return sorted(found, key=lambda t: -(t.get("duration") or 0))


def tracker_pages(run):
    """Columns A–D of the tracker tab in 50-row reads, as far as its grid goes: a read past the grid
    is an API error, not an empty page."""
    tabs = L.parse_info(L.load_result(os.path.join(run["dir"], "ti.txt")), run["tracker"])
    if run["tab"] not in tabs:
        raise L.Refuse(4, "the tracker has no tab %r (has %s)" % (run["tab"], ", ".join(sorted(tabs))))
    grid = tabs[run["tab"]][0]
    return [(a, min(a + L.PAGE - 1, grid), "%s!A%d:D%d" % (L.quote_tab(run["tab"]), a, min(a + L.PAGE - 1, grid)))
            for a in range(1, grid + 1, L.PAGE)]


def m_find(d):
    run = L.load_run(d)
    run["pages"] = tracker_pages(run)
    reads = [L.read_call(run, run["tracker"], rng, "t%d" % (i + 1)) for i, (_, _, rng) in enumerate(run["pages"])]
    p = os.path.join(d, "listing.json")
    if not os.path.exists(p):
        raise L.Refuse(3, "missing saved result: %s" % p)
    try:
        listing = json.load(open(p, encoding="utf-8"))
    except ValueError as e:
        raise L.Refuse(3, "the Fireflies listing is not JSON (%s)" % e)
    found = pick(listing, run["title"], date.fromisoformat(run["meeting"]))
    if not found:
        run["source"] = "doc"
        L.save_run(run)
        return {"found": False, "meeting": run["meeting"], "heading": run["heading"], "calls": reads,
                "next": "read the %s section of the Doc as edited (get_doc_as_markdown) and say the minutes come from the Doc" % run["heading"]}
    t = found[0]
    run["source"], run["transcript"] = "fireflies", t["id"]
    L.save_run(run)
    out = {"found": True, "id": t["id"], "date": t.get("dateString"), "meeting": run["meeting"],
           "calls": [{"tool": "mcp__fireflies__fireflies_get_transcript", "args": {"transcriptId": t["id"]},
                      "save": os.path.join(d, "transcript.txt")}] + reads}
    if len(found) > 1:
        out["warning"] = "%d recordings of this meeting; took the longest (%s), the others: %s" % (
            len(found), t["id"], ", ".join(x["id"] for x in found[1:]))
    return out


# ── check ────────────────────────────────────────────────────────────────────
def tracker_index(run):
    """# -> 項目 from the paged read of columns A–D."""
    by_row = {}
    for i, (a, b, rng) in enumerate(run["pages"]):
        rows = L.parse_values(L.load_result(os.path.join(run["dir"], "t%d.txt" % (i + 1))), run["tracker"], rng)
        for j, cells in enumerate(rows):
            by_row[a + j] = L.pad(cells, 4)
    if [c.strip() for c in by_row.get(1, [])] != L.TRACKER_HEADER[:4]:
        raise L.Refuse(4, "tracker header changed: %r" % (by_row.get(1),))
    return {c[0].strip(): c[3].strip() for r, c in by_row.items()
            if r >= 2 and ITEM_RE.match(c[0].strip()) and c[3].strip()}


def text_of(x, key, where):
    v = x.get(key) if isinstance(x, dict) else None
    if not isinstance(v, str) or not v.strip():
        raise L.Refuse(3, "%s has no %s" % (where, key))
    v = re.sub(r"\s+", " ", v).strip()
    if len(v) > MAX_TEXT:
        raise L.Refuse(3, "%s: %s is longer than %d characters; say it shorter" % (where, key, MAX_TEXT))
    return v


def owners_of(x, roster, where, required=False):
    v = x.get("owner", "")
    names = [v] if isinstance(v, str) else v
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise L.Refuse(3, "%s: owner must be a name or a list of names" % where)
    names = [n.strip() for n in names if n.strip()]
    bad = [n for n in names if n not in roster]
    if bad:
        raise L.Refuse(3, "%s: %s is not on the roster (%s)" % (where, ", ".join(bad), ", ".join(roster)))
    if required and not names:
        raise L.Refuse(3, "%s has no owner" % where)
    return names


def date_of(x, key, where):
    v = str(x.get(key) or "").strip()
    if not v:
        return None
    if not DATE_RE.match(v):
        raise L.Refuse(3, "%s: %s %r is not a full date (YYYY-MM-DD)" % (where, key, v))
    try:
        return date.fromisoformat(v)
    except ValueError:
        raise L.Refuse(3, "%s: %s %r is no such date" % (where, key, v))


def item_of(x, items, where, required=False, new_ok=False):
    v = str(x.get("item") or "").strip().lstrip("#")
    if new_ok and x.get("new") is True:
        if v:
            raise L.Refuse(3, "%s is marked new but names #%s" % (where, v))
        return "新"
    if not v:
        if required:
            raise L.Refuse(3, "%s names no item #" % where)
        return ""
    if v not in items:
        raise L.Refuse(3, "%s: #%s is not in the tracker%s" % (where, v, " (mark it new if it is new work)" if new_ok else ""))
    return v


def entries(data, key):
    v = data.get(key, [])
    if not isinstance(v, list):
        raise L.Refuse(3, "%s must be a list" % key)
    return v


def check(data, run, items, now):
    if not isinstance(data, dict):
        raise L.Refuse(3, "minutes.json must be an object")
    src = data.get("source")
    if src not in ("fireflies", "doc"):
        raise L.Refuse(3, "source must be fireflies or doc")
    if src != run.get("source"):
        raise L.Refuse(3, "source says %s but find chose %s" % (src, run.get("source") or "nothing (run find)"))
    roster, thu, week = run["roster"], date.fromisoformat(run["meeting"]), run["week"]
    source = "Fireflies %s" % run["transcript"] if src == "fireflies" else "Doc %s" % run["heading"]
    rows, prog, warnings = [], [], []
    doc = {"決議": [], "待辦": [], "卡關": [], "待討論": [], "放棄": []}
    fill = {n: {"下一步": [], "待討論": []} for n in roster if n != "All"}
    cite = "〔%s 會議〕" % md(thu)
    opened, risks, unrouted = [], [], []

    def to_fill(names, label, line):
        targets = [n for n in roster if n != "All"] if "All" in names else names
        if not targets:
            unrouted.append(line)
        for n in targets:
            fill[n][label].append(line + cite)

    def row(kind, content, owner="", due="", item="", state=""):
        rows.append([week, run["meeting"], kind, content, owner, due, item, source, state])

    for i, x in enumerate(entries(data, "decisions")):
        w = "decision %d" % (i + 1)
        t, it = text_of(x, "text", w), item_of(x, items, w)
        row("決議", t, item=it)
        doc["決議"].append(t + (" · #%s" % it if it else ""))
    for i, x in enumerate(entries(data, "dropped")):
        w = "dropped %d" % (i + 1)
        it, t = item_of(x, items, w, required=True), text_of(x, "text", w)
        row("放棄", t, item=it)
        doc["放棄"].append("#%s %s — %s" % (it, items[it], t))
    for i, x in enumerate(entries(data, "actions")):
        w = "action %d" % (i + 1)
        t, names = text_of(x, "what", w), owners_of(x, roster, w)
        due, it = date_of(x, "due", w), item_of(x, items, w, new_ok=True)
        if due and due < thu:
            warnings.append("%s is due %s, before the meeting" % (w, due.isoformat()))
        state = "已排定" if names and due else "待定"
        row("行動", t, "、".join(names), due.isoformat() if due else "", it, state)
        line = "%s — %s · %s%s" % (t, "、".join(names) or "負責人未定", md(due) if due else "日期未定",
                                   " · #%s" % it if it and it != "新" else (" · 新項目" if it == "新" else ""))
        doc["待辦"].append(line)
        if state == "待定":
            opened.append(line)
        to_fill(names, "下一步", "%s%s" % (t, "（%s 前）" % md(due) if due else ""))
    for i, x in enumerate(entries(data, "blockers")):
        w = "blocker %d" % (i + 1)
        t, names = text_of(x, "text", w), owners_of(x, roster, w)
        it, since = item_of(x, items, w), date_of(x, "since", w)
        if since and since > thu:
            raise L.Refuse(3, "%s: since %s is after the meeting" % (w, since.isoformat()))
        age = (thu - since).days if since else 0
        kind = "風險" if age > RISK_DAYS else "卡關"
        row(kind, t + ("（自 %s）" % md(since) if since else ""), "、".join(names), "", it)
        line = t + (" — %s" % "、".join(names) if names else "") + (" · 已卡 %d 天，列為風險" % age if kind == "風險" else "")
        doc["卡關"].append(line)
        if kind == "風險":
            risks.append(line)
        to_fill(names, "待討論", t)
    for i, x in enumerate(entries(data, "topics")):
        w = "topic %d" % (i + 1)
        t, names = text_of(x, "text", w), owners_of(x, roster, w)
        row("待討論", t, "、".join(names))
        doc["待討論"].append(t + (" — %s" % "、".join(names) if names else ""))
        to_fill(names, "待討論", t)
    for i, x in enumerate(entries(data, "progress")):
        w = "progress %d" % (i + 1)
        it, t = item_of(x, items, w, required=True), text_of(x, "text", w)
        state = str(x.get("state") or "").strip()
        if state and state not in VOCAB:
            raise L.Refuse(3, "%s: state %r is not a 狀態 (%s)" % (w, state, " / ".join(VOCAB)))
        prog.append([week, run["meeting"], "進度", t, "", "", it, source, state])

    if len(rows) > BLOCK_ROWS:
        raise L.Refuse(3, "%d decisions, actions, blockers and topics do not fit the %d-row block; merge the smallest"
                       % (len(rows), BLOCK_ROWS))
    room = BLOCK_ROWS - len(rows)
    if len(prog) > room:
        warnings.append("%d progress lines left out of the Ledger: the block holds %d rows" % (len(prog) - room, BLOCK_ROWS))
    rows += prog[:room]

    sections = [(k, v) for k, v in doc.items() if v]
    if not sections:
        sections = [("決議", ["這次會議沒有談定的事"])]
    stamp_line = "〔自動彙整 %s · %s〕%s" % (wb_label(week), now.strftime("%m-%d %H:%M"), TITLE)
    body = "\n".join(sum(([k] + ["\t" + s for s in v] for k, v in sections), []))
    block = {"heading": run["heading"], "stamp_line": stamp_line, "body": body, "text": stamp_line + "\n" + body}
    decided = len(doc["決議"]) + len(doc["待辦"]) + len(doc["放棄"])
    return {"rows": rows, "block": block, "fill": {n: v for n, v in fill.items() if v["下一步"] or v["待討論"]},
            "summary": {"source": src, "transcript": run.get("transcript"), "rows": len(rows),
                        "decisions": len(doc["決議"]), "actions": len(doc["待辦"]), "open_actions": opened,
                        "blockers": len(doc["卡關"]), "risks": risks, "topics": len(doc["待討論"]),
                        "dropped": len(doc["放棄"]), "progress": min(len(prog), room), "unrouted": unrouted,
                        "warnings": warnings,
                        "doc_key": {"starts": "〔自動彙整 %s · " % wb_label(week), "ends": "〕" + TITLE},
                        "delivered": ("no-decisions;" if not decided else "%d-decided;" % decided)
                                     + ("transcript-found" if src == "fireflies" else "doc-fallback")}}


def m_check(d, input_path, now=None):
    run = L.load_run(d)
    if "source" not in run:
        raise L.Refuse(2, "run `find` first")
    try:
        data = json.load(open(input_path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise L.Refuse(3, "cannot read %s (%s)" % (input_path, e))
    res = check(data, run, tracker_index(run), L.parse_now(now))
    for name, obj in (("rows.json", res["rows"]), ("block.json", {"blocks": [res["block"]]}), ("fill.json", res["fill"])):
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
    return dict(res["summary"], dir=d, block=res["block"]["text"],
                files={"rows": os.path.join(d, "rows.json"), "block": os.path.join(d, "block.json"),
                       "fill": os.path.join(d, "fill.json")})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("start")
    s.add_argument("--week", required=True)
    s.add_argument("--config")
    s.add_argument("--now")
    f = sub.add_parser("find")
    f.add_argument("--dir", required=True)
    c = sub.add_parser("check")
    c.add_argument("--dir", required=True)
    c.add_argument("--input", required=True)
    c.add_argument("--now")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.mutate:
        return mutate()
    try:
        if a.cmd == "start":
            L.emit(m_start(a.week, a.config, a.now))
        elif a.cmd == "find":
            res = m_find(a.dir)
            L.emit(res)
            return 0 if res["found"] else 4
        elif a.cmd == "check":
            L.emit(m_check(a.dir, a.input, a.now))
        else:
            ap.print_help()
            return 2
    except L.Refuse as e:
        print("minutes.py: %s" % e, file=sys.stderr)
        return e.code
    return 0


# ── selftest ─────────────────────────────────────────────────────────────────
def selftest():
    import shutil
    import tempfile
    fails = []

    def ok(name, cond, got=None):
        if not cond:
            fails.append("%s%s" % (name, "" if got is None else ": got %r" % (got,)))

    def refuses(name, fn, *args):
        try:
            fn(*args)
        except L.Refuse:
            return
        fails.append("%s: did not refuse" % name)

    tmp = tempfile.mkdtemp(prefix="minutes-selftest-")
    try:
        cfg = os.path.join(tmp, "cfg.json")
        json.dump({"google_account": "ops@example.com",
                   "sources": {"main_tracker": {"id": "TRK", "tab": "H2 項目", "cycle": "2026H2"},
                               "ledger": {"id": "LED", "epoch_week": "2026-W40"}},
                   "chat_ids": {"$note": "x", "Ann Lee": "ann@x", "Ben Wu": "ben@x", "users/123": "cy@x"},
                   "meeting": {"calendar_title": "Team Weekly Meeting"}}, open(cfg, "w"))
        st = m_start("2026-W43", cfg, "2026-10-23T08:05:00+08:00", base=tmp)
        d = st["dir"]
        ok("start: meeting is Thursday", st["meeting"] == "2026-10-22", st["meeting"])
        ok("start: listing call for the day around it", st["calls"][0]["args"]["fromDate"] == "2026-10-21"
           and st["calls"][0]["args"]["toDate"] == "2026-10-23" and st["calls"][0]["args"]["format"] == "json")
        ok("start: the tracker's size", st["calls"][1]["tool"].endswith("get_spreadsheet_info") and len(st["calls"]) == 2)
        open(os.path.join(d, "ti.txt"), "w").write('Spreadsheet: "T" (ID: TRK)\n  - "Other" (ID: 1) | Size: 900x5\n'
                                                  '  - "H2 項目" (ID: 2) | Size: 72x13\n')
        run = L.load_run(d)
        ok("start: roster is the display names plus All", run["roster"] == ["Ann Lee", "Ben Wu", "All"], run["roster"])
        ok("start: heading in the Doc's format", run["heading"] == "Oct 22, 2026", run["heading"])
        ok("heading: a single-digit day is not zero-padded, as the scaffold writes it",
           doc_heading(meeting_day("2026-W45")) == "Nov 5, 2026", doc_heading(meeting_day("2026-W45")))

        def listing(*ts):
            json.dump([{"id": i, "title": ti, "dateString": ds, "duration": du} for i, ti, ds, du in ts],
                      open(os.path.join(d, "listing.json"), "w"))
        listing(("A", "Team Weekly Meeting", "2026-10-22T13:00:00.000Z", 33.4),
                ("B", "Team Weekly Meeting", "2026-10-15T13:00:00.000Z", 25.5),
                ("C", "Sales sync", "2026-10-22T05:00:00.000Z", 40))
        r = m_find(d)
        ok("find: the meeting's transcript", r["found"] and r["id"] == "A", r)
        ok("find: the fetch call", r["calls"][0]["args"] == {"transcriptId": "A"})
        ok("find: tracker reads stop at the grid", [c["args"]["range_name"] for c in r["calls"][1:]]
           == ["'H2 項目'!A1:D50", "'H2 項目'!A51:D72"], r["calls"][1:])
        listing(("A", "Team Weekly Meeting", "2026-10-21T17:00:00.000Z", 9))     # 01:00 Thu Taipei, 22 Oct
        ok("find: the date is Taipei's", m_find(d).get("id") == "A")
        ok("find: an entry with no date is never today's", taipei_date(None) is None and taipei_date("") is None)
        listing(("A", "Team Weekly Meeting", "2026-10-21T15:00:00.000Z", 9))     # 23:00 Wed Taipei
        ok("find: another day is not the meeting", m_find(d)["found"] is False)
        listing(("A", "Team weekly meeting", "2026-10-22T13:00:00.000Z", 9))
        ok("find: another title is not the meeting", m_find(d)["found"] is False)
        listing(("A", "Team Weekly Meeting", "2026-10-22T13:00:00.000Z", 9),
                ("B", "Team Weekly Meeting", "2026-10-22T13:20:00.000Z", 30))
        r = m_find(d)
        ok("find: two recordings take the longer, and say so", r["id"] == "B" and "warning" in r, r)
        json.dump({"result": json.dumps([{"id": "A", "title": "Team Weekly Meeting",
                                          "dateString": "2026-10-22T13:00:00.000Z"}])},
                  open(os.path.join(d, "listing.json"), "w"))
        ok("find: a wrapped result reads too", m_find(d).get("id") == "A")

        rows = [["#", "主類別", "子類別", "項目（正規化）"], ["1.0", "1.0 Marketing", "", ""],
                ["1.08", "1.0 Marketing", "1.3 名單", "電子報"], ["2.01", "2.0 Sales", "2.1", "業務流程"],
                ["1.04", "1.0 Marketing", "1.1", "短影音"]]

        def save_pages(rows):
            for i, (a, b, rng) in enumerate(run["pages"]):
                part = rows[a - 1:b]
                body = "\n".join("Row %2d: %r" % (j + 1, c) for j, c in enumerate(part))
                text = ("Successfully read %d rows from range '%s' in spreadsheet TRK for ops@example.com:\n%s"
                        % (len(part), rng, body)) if part else "No data found in range '%s'." % rng
                open(os.path.join(d, "t%d.txt" % (i + 1)), "w").write(json.dumps({"result": text}))
        run = L.load_run(d)
        save_pages(rows)
        items = tracker_index(run)
        ok("tracker: items by #, category rows left out", items == {"1.08": "電子報", "2.01": "業務流程", "1.04": "短影音"}, items)
        open(os.path.join(d, "t2.txt"), "w").write("Successfully read 1 rows from range 'Other!A51:D72' in spreadsheet TRK for x:\nRow  1: ['9.01', '', '', 'x']")
        refuses("tracker: a read of another range is refused", tracker_index, run)
        save_pages([["#", "主類", "子類別", "項目"]] + rows[1:])
        refuses("tracker: a changed header is refused", tracker_index, run)
        save_pages(rows)

        now = L.parse_now("2026-10-23T08:20:00+08:00")
        base = {"source": "fireflies",
                "decisions": [{"text": "電子報 11/3 起跑 sweep", "item": "1.08"}],
                "actions": [{"what": "寄送 Skills 連結", "owner": "Ann Lee", "due": "2026-10-24"},
                            {"what": "安裝 Skillsync", "owner": "All", "due": ""},
                            {"what": "製作銷售講座素材", "owner": ["Ann Lee", "Ben Wu"], "due": "2026-10-30", "item": "2.01"},
                            {"what": "建立回報管道", "owner": "", "due": "2026-10-30", "new": True}],
                "blockers": [{"text": "名單匯入卡在 Kit 方案", "owner": "Ben Wu", "since": "2026-10-08"},
                             {"text": "時區設定抓 local", "since": "2026-10-20"}],
                "topics": [{"text": "相容性檢查技能", "owner": "Ann Lee"}],
                "dropped": [{"item": "1.04", "text": "短影音不做了"}],
                "progress": [{"item": "1.08", "text": "冷名單重新確認信已寄", "state": "進行中"}]}
        res = check(base, run, items, now)
        R = res["rows"]
        ok("rows: nine columns each", all(len(r) == len(L.DECISIONS_HEADER) == 9 for r in R))
        ok("rows: kinds in order", [r[2] for r in R] == ["決議", "放棄", "行動", "行動", "行動", "行動", "風險", "卡關", "待討論", "進度"],
           [r[2] for r in R])
        ok("rows: a dated owned action is scheduled", R[2][4:9] == ["Ann Lee", "2026-10-24", "", "Fireflies A", "已排定"], R[2])
        ok("rows: an undated action stays open", R[3][8] == "待定" and R[3][4] == "All", R[3])
        ok("rows: joint owners", R[4][4] == "Ann Lee、Ben Wu" and R[4][6] == "2.01", R[4])
        ok("rows: an ownerless action stays open, new item", R[5][8] == "待定" and R[5][6] == "新", R[5])
        ok("rows: a blocker 14 days old is a risk", R[6][2] == "風險" and R[6][3].endswith("（自 10/8）"), R[6])
        ok("rows: a blocker 2 days old is not", R[7][2] == "卡關")
        ok("rows: progress carries its state", R[9][6:9] == ["1.08", "Fireflies A", "進行中"], R[9])
        ok("rows: week and meeting", R[0][:2] == ["2026-W43", "2026-10-22"])
        b = res["block"]
        ok("block: stamp names the week and its title", b["stamp_line"] == "〔自動彙整 WB 10/19 · 10-23 08:20〕會議紀錄", b["stamp_line"])
        ok("block: under the meeting's heading", b["heading"] == "Oct 22, 2026")
        ok("block: labels in order", [l for l in b["body"].split("\n") if not l.startswith("\t")] == ["決議", "待辦", "卡關", "待討論", "放棄"])
        ok("block: an undated action says so", "\t安裝 Skillsync — All · 日期未定" in b["body"].split("\n"), b["body"])
        ok("block: a risk says how long", "已卡 14 天，列為風險" in b["body"])
        ok("block: a dropped item names it", "\t#1.04 短影音 — 短影音不做了" in b["body"].split("\n"))
        ok("block: progress stays out of the Doc", "冷名單" not in b["body"])
        F = res["fill"]
        ok("fill: All reaches everyone", "安裝 Skillsync〔10/22 會議〕" in F["Ann Lee"]["下一步"]
           and "安裝 Skillsync〔10/22 會議〕" in F["Ben Wu"]["下一步"], F)
        ok("fill: a dated action says by when", "寄送 Skills 連結（10/24 前）〔10/22 會議〕" in F["Ann Lee"]["下一步"], F["Ann Lee"])
        ok("fill: joint owners each get it", sum("銷售講座" in x for x in F["Ben Wu"]["下一步"]) == 1)
        ok("fill: blockers and topics are 待討論", F["Ben Wu"]["待討論"] == ["名單匯入卡在 Kit 方案〔10/22 會議〕"]
           and F["Ann Lee"]["待討論"] == ["相容性檢查技能〔10/22 會議〕"], F)
        S = res["summary"]
        ok("summary: unrouted lines named", S["unrouted"] == ["建立回報管道（10/30 前）", "時區設定抓 local"], S["unrouted"])
        ok("summary: open actions", len(S["open_actions"]) == 2, S["open_actions"])
        ok("summary: delivered", S["delivered"] == "6-decided;transcript-found", S["delivered"])
        ok("summary: the idempotency key", S["doc_key"] == {"starts": "〔自動彙整 WB 10/19 · ", "ends": "〕會議紀錄"})

        def variant(**kw):
            v = json.loads(json.dumps(base))
            for k, val in kw.items():
                v[k] = val
            return v
        refuses("owner off the roster", check, variant(actions=[{"what": "x", "owner": "Peter", "due": ""}]), run, items, now)
        refuses("a users/ key is no roster name", check, variant(actions=[{"what": "x", "owner": "users/123"}]), run, items, now)
        refuses("an unknown item", check, variant(decisions=[{"text": "x", "item": "9.99"}]), run, items, now)
        refuses("an unknown item on an action", check, variant(actions=[{"what": "x", "item": "9.99"}]), run, items, now)
        refuses("new with a number", check, variant(actions=[{"what": "x", "item": "1.08", "new": True}]), run, items, now)
        refuses("a partial date", check, variant(actions=[{"what": "x", "due": "10/30"}]), run, items, now)
        refuses("a compact date", check, variant(actions=[{"what": "x", "due": "20261030"}]), run, items, now)
        refuses("no such date", check, variant(actions=[{"what": "x", "due": "2026-02-30"}]), run, items, now)
        refuses("a blocker from the future", check, variant(blockers=[{"text": "x", "since": "2026-10-23"}]), run, items, now)
        refuses("dropped without an item", check, variant(dropped=[{"text": "x"}]), run, items, now)
        refuses("progress with a made-up state", check, variant(progress=[{"item": "1.08", "text": "x", "state": "done"}]), run, items, now)
        refuses("an action without words", check, variant(actions=[{"what": " ", "owner": "Ann Lee"}]), run, items, now)
        refuses("a line too long", check, variant(topics=[{"text": "長" * 201}]), run, items, now)
        refuses("a source find did not choose", check, variant(source="doc"), run, items, now)
        refuses("too many rows", check, variant(topics=[{"text": "t%d" % i} for i in range(BLOCK_ROWS)]), run, items, now)
        res = check(variant(progress=[{"item": "1.08", "text": "p%d" % i} for i in range(BLOCK_ROWS)]), run, items, now)
        ok("progress past the block is left out, and said", len(res["rows"]) == BLOCK_ROWS and res["summary"]["warnings"], res["summary"])
        res = check({"source": "fireflies"}, run, items, now)
        ok("no decisions: one line and the receipt word", res["block"]["body"] == "決議\n\t這次會議沒有談定的事"
           and res["summary"]["delivered"] == "no-decisions;transcript-found", res["block"])
        res = check(variant(actions=[{"what": "x", "owner": "Ann Lee", "due": "2026-10-20"}]), run, items, now)
        ok("a due date before the meeting is warned", any("before the meeting" in w for w in res["summary"]["warnings"]))

        listing(("A", "Other", "2026-10-22T13:00:00.000Z", 9))
        ok("doc fallback: find says so", m_find(d)["found"] is False)
        run = L.load_run(d)
        res = check({"source": "doc", "decisions": [{"text": "x"}]}, run, items, now)
        ok("doc fallback: rows cite the Doc", res["rows"][0][7] == "Doc Oct 22, 2026" and res["summary"]["delivered"] == "1-decided;doc-fallback",
           res["rows"][0])
        json.dump({"source": "doc", "topics": [{"text": "x", "owner": "Ben Wu"}]}, open(os.path.join(d, "in.json"), "w"))
        out = m_check(d, os.path.join(d, "in.json"), "2026-10-23T08:30:00+08:00")
        ok("check writes its three files", all(os.path.exists(p) for p in out["files"].values()))
        ok("block.json is render_block's shape", json.load(open(out["files"]["block"]))["blocks"][0]["heading"] == "Oct 22, 2026")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("minutes.py selftest: %d failed" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("minutes.py selftest: all checks passed")
    return 0


def mutate():
    import shutil
    import tempfile
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    code, marker, rest = src.partition("\nMUTATIONS = [")
    tmpd = tempfile.mkdtemp(prefix="minutes-mutate-")
    shutil.copy2(os.path.join(core_dir(), "ledger.py"), os.path.join(tmpd, "ledger.py"))

    def run(text):
        p = os.path.join(tmpd, "minutes_mut.py")
        open(p, "w", encoding="utf-8").write(text)
        return subprocess.run([sys.executable, p, "--selftest"], capture_output=True, text=True).returncode

    if run(src) != 0:
        print("mutate: the unmodified control copy fails its selftest")
        return 1
    ok = True
    for name, pairs in MUTATIONS:
        bad = [old for old, _ in pairs if code.count(old) != 1]
        if bad:
            print("mutate: %-40s SETUP ERROR (pattern not unique: %r)" % (name, bad[0][:40]))
            ok = False
            continue
        mutated = code
        for old, new in pairs:
            mutated = mutated.replace(old, new)
        rc = run(mutated + marker + rest)
        print("mutate: %-40s %s" % (name, "caught" if rc != 0 else "MISSED"))
        ok = ok and rc != 0
    shutil.rmtree(tmpd, ignore_errors=True)
    return 0 if ok else 1


MUTATIONS = [
    ("the latest transcript, whatever its day", [("             and taipei_date(t.get(\"dateString\")) == thu]", "]")]),
    ("any title", [("str(t.get(\"title\") or \"\").strip() == title", "True")]),
    ("UTC date, not Taipei's", [("        return L.parse_now(s).date()", "        return datetime.fromisoformat(s.replace('Z', '+00:00')).date()")]),
    ("the first recording, not the longest", [("key=lambda t: -(t.get(\"duration\") or 0)", "key=lambda t: 0")]),
    ("roster check lost", [("    bad = [n for n in names if n not in roster]", "    bad = []")]),
    ("users/ keys on the roster", [("and not k.startswith(\"users/\")]", "]")]),
    ("item check lost", [("    if v not in items:\n", "    if False:\n")]),
    ("new items numbered anyway", [("        if v:\n            raise L.Refuse(3, \"%s is marked new", "        if False:\n            raise L.Refuse(3, \"%s is marked new")]),
    ("partial dates pass", [("    if not DATE_RE.match(v):", "    if False:")]),
    ("risk threshold off by one", [("kind = \"風險\" if age > RISK_DAYS else", "kind = \"風險\" if age >= RISK_DAYS - 5 else")]),
    ("undated actions scheduled", [("state = \"已排定\" if names and due else \"待定\"", "state = \"已排定\" if names else \"待定\"")]),
    ("All not expanded", [("targets = [n for n in roster if n != \"All\"] if \"All\" in names else names", "targets = names")]),
    ("the meeting date not cited", [("            fill[n][label].append(line + cite)", "            fill[n][label].append(line)")]),
    ("block overflow not refused", [("    if len(rows) > BLOCK_ROWS:", "    if False:")]),
    ("progress overflow kept", [("    rows += prog[:room]", "    rows += prog")]),
    ("progress written to the Doc", [("        prog.append([week, run[\"meeting\"], \"進度\", t, \"\", \"\", it, source, state])",
                                      "        prog.append([week, run[\"meeting\"], \"進度\", t, \"\", \"\", it, source, state]); doc[\"決議\"].append(t)")]),
    ("the block's title lost", [("    stamp_line = \"〔自動彙整 %s · %s〕%s\" % (wb_label(week), now.strftime(\"%m-%d %H:%M\"), TITLE)",
                                 "    stamp_line = \"〔自動彙整 %s · %s〕\" % (wb_label(week), now.strftime(\"%m-%d %H:%M\"))")]),
    ("reads past the grid", [("(L.quote_tab(run[\"tab\"]), a, min(a + L.PAGE - 1, grid)))", "(L.quote_tab(run[\"tab\"]), a, a + L.PAGE - 1))")]),
    ("source mismatch accepted", [("    if src != run.get(\"source\"):", "    if False:")]),
    ("no-decisions never said", [("(\"no-decisions;\" if not decided else", "(\"0-decided;\" if not decided else")]),
    ("future blockers accepted", [("        if since and since > thu:", "        if False:")]),
    ("the heading zero-padded", [("    return \"%s %d, %d\" % (d.strftime(\"%b\"), d.day, d.year)", "    return d.strftime(\"%b %d, %Y\")")]),
    ("an undated entry is today's", [("    if not s:\n        return None", "    if False:\n        return None")]),
]

if __name__ == "__main__":
    sys.exit(main())
