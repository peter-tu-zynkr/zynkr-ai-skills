#!/usr/bin/env python3
"""The Weekly Ledger (SKB-044): the machine-owned memory of the weekly project cycle.

This script computes; it never talks to Google. Every step prints the exact MCP calls the model
must make, each with a path to save the tool's result to, word for word. The next step reads
those files back. The model never works out a range, a row number or a cell value itself.

    ledger.py week [--now ISO]                   the ISO week key in Taipei time
    ledger.py schema                             every Ledger tab's header row
    ledger.py snapshot start --week W [--config PATH] [--now ISO]
    ledger.py snapshot pages   --dir D           -> already done, or the tracker reads
    ledger.py snapshot plan    --dir D           -> the block write + read-back + recheck calls
    ledger.py snapshot check   --dir D           -> the Weeks commit call, only if all checks pass
    ledger.py snapshot confirm --dir D           -> the receipt's delivered= value
    ledger.py block start --tab T --week W --rows R.json [--config PATH]
    ledger.py block plan|check|confirm --dir D   -> one beat's rows into its weekly block of tab T,
                                                    committed by that beat's cell in the Weeks row
    ledger.py rows reports --reports reports.json --routing routing.json --week W
                                                 -> rollup's parsed posts as Reports rows
    ledger.py rows decisions --input decisions.json --week W --meeting YYYY-MM-DD --source URL
                                                 -> the meeting's resolutions as Decisions rows
    ledger.py diff --a A.json --b B.json [--updates U.json]
                                                 -> every changed cell between two snapshots,
                                                    each marked logged (an Updates row) or manual
    ledger.py --selftest | --mutate

Layout v1. Week k counts from the config's epoch week. Its Weeks row is 2+k and its Snapshot block
is rows 2+100k .. 101+100k. Nothing ever appends at "the end of a tab": the read tool shows at
most 50 rows, so finding the end would mean trusting a long read, and a wrong guess there is
the one mistake that overwrites history. The Weeks row is written LAST, after the block has been
read back and the tracker re-read; a week counts as snapshotted only when that row says ok.

Exit codes: 0 ok · 2 config or arguments · 3 input refused (missing, truncated, wrong file or
range, row-count mismatch) · 4 structure changed · 5 out of space · 6 check failed (do not
commit) · 7 confirm failed.
"""
import argparse
import ast
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

LAYOUT = "layout v1"
SLOT = 100            # rows per week in Snapshot; changing it moves every later week's block
PAGE = 50             # read_sheet_values shows at most 50 rows
TPE = timezone(timedelta(hours=8))   # Asia/Taipei has no DST; a fixed offset needs no tz database
WARN_WEEKS = 8

TRACKER_HEADER = ["#", "主類別", "子類別", "項目（正規化）", "重要", "緊急", "Priority",
                  "負責人", "協助者", "開始", "結束", "狀態", "備註"]
SNAPSHOT_HEADER = ["week", "snapshot_at", "cycle"] + TRACKER_HEADER                 # A–P
WEEKS_HEADER = ["week", "status", "snapshot_at", "cycle", "tracker_id", "items",
                "first_row", "last_row", "digest", "note"]                           # A–J
UPDATES_HEADER = ["週", "時間", "cycle", "#", "項目", "欄位", "舊值", "新值", "原因", "證據",
                  "來源", "提議", "核准", "proposal"]                                # A–N
REPORTS_HEADER = ["week", "posted_at", "owner", "部門", "上週", "本週", "數字", "卡關", "format"]  # A–I
# What `decisions` extracts from the meeting section: a resolution is decision · owner · date; one
# missing an owner or a date stays 待決 (open), never promoted.
DECISIONS_HEADER = ["week", "會議日期", "類型", "內容", "負責人", "期限", "關聯 #", "來源"]   # A–H
# Phase 2 widens Weeks: each beat that writes a weekly block owns a status cell and a time cell
# in the week's row. Empty = never recorded; "ok" over an empty block = recorded, and none.
WEEKS_BEAT_HEADER = ["reports", "reports_at", "decisions", "decisions_at"]           # K–N
TABS = [("Weeks", WEEKS_HEADER + WEEKS_BEAT_HEADER), ("Updates", UPDATES_HEADER),
        ("Snapshot", SNAPSHOT_HEADER), ("Reports", REPORTS_HEADER), ("Decisions", DECISIONS_HEADER)]
COLS = {"Weeks": "N", "Updates": "N", "Snapshot": "P", "Reports": "I", "Decisions": "H"}
# tab -> (rows per week, header, its Weeks status column, its Weeks time column)
BLOCKS = {"Reports": (20, REPORTS_HEADER, "K", "L"),
          "Decisions": (20, DECISIONS_HEADER, "M", "N")}

CATEGORY_RE = re.compile(r"^\d+\.0$")
WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")


class Refuse(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


# ── weeks and time ───────────────────────────────────────────────────────────
def parse_now(s=None):
    if not s:
        return datetime.now(TPE)
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=TPE)
    return d.astimezone(TPE)


def week_of(now):
    y, w, _ = now.astimezone(TPE).isocalendar()
    return "%d-W%02d" % (y, w)


def monday(week):
    m = WEEK_RE.match(week or "")
    if not m:
        raise Refuse(2, "not an ISO week key: %r (expected like 2026-W40)" % week)
    try:
        return date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
    except ValueError:
        raise Refuse(2, "no such ISO week: %s" % week)


def week_index(week, epoch):
    k = (monday(week) - monday(epoch)).days // 7
    if k < 0:
        raise Refuse(2, "week %s is before the Ledger's epoch week %s" % (week, epoch))
    return k


def weeks_row(k):
    return 2 + k


def slot(k):
    return 2 + SLOT * k, 1 + SLOT * (k + 1)


def stamp(now):
    return now.astimezone(TPE).replace(microsecond=0).isoformat()


# ── reading what the model saved ─────────────────────────────────────────────
def load_result(path):
    if not os.path.exists(path):
        raise Refuse(3, "missing saved result: %s" % path)
    text = open(path, encoding="utf-8").read().strip()
    if text.startswith("{"):
        try:
            obj = json.loads(text)
        except ValueError:
            obj = None
        if isinstance(obj, dict) and isinstance(obj.get("result"), str):
            text = obj["result"].strip()
    return text


HEAD_RE = re.compile(r"^Successfully read (\d+) rows from range '(.*)' in spreadsheet (\S+) for \S+:$")
ROW_RE = re.compile(r"^Row\s+(\d+): (\[.*\])$")


def parse_values(text, sid, rng):
    """Rows of a read_sheet_values result, refusing anything partial or for another range."""
    first = text.split("\n", 1)[0]
    if first.startswith("No data found in range "):
        if "'%s'" % rng not in first:
            raise Refuse(3, "empty-range result is for another range: %s" % first)
        return []
    m = HEAD_RE.match(first)
    if not m:
        raise Refuse(3, "not a read_sheet_values result: %r" % first[:120])
    n, got_rng, got_sid = int(m.group(1)), m.group(2), m.group(3)
    if got_sid != sid:
        raise Refuse(3, "read came from spreadsheet %s, expected %s" % (got_sid, sid))
    if got_rng != rng:
        raise Refuse(3, "read covers %r, expected %r" % (got_rng, rng))
    rows = []
    for line in text.split("\n")[1:]:
        if line.startswith("... and ") and line.endswith(" more rows"):
            raise Refuse(3, "read was truncated at 50 rows (%s); read a smaller range" % line)
        mm = ROW_RE.match(line)
        if not mm:
            if rows and line.strip():
                if line.startswith("Row"):
                    raise Refuse(3, "row line did not parse (was it re-wrapped?): %r" % line[:80])
            if rows:
                break                       # hyperlink / notes / error sections follow the rows
            continue
        if int(mm.group(1)) != len(rows) + 1:
            raise Refuse(3, "row numbers jump at Row %s" % mm.group(1))
        try:
            cells = ast.literal_eval(mm.group(2))
        except (ValueError, SyntaxError):
            raise Refuse(3, "Row %s is not a clean list (was it retyped?)" % mm.group(1))
        if not isinstance(cells, list) or not all(isinstance(c, str) for c in cells):
            raise Refuse(3, "Row %s holds non-text cells" % mm.group(1))
        rows.append(cells)
    if len(rows) != n:
        raise Refuse(3, "result says %d rows but %d were saved" % (n, len(rows)))
    return rows


INFO_HEAD_RE = re.compile(r'^Spreadsheet: "(.*)" \(ID: (\S+)\)')
INFO_TAB_RE = re.compile(r'^\s*- "(.*)" \(ID: (\d+)\) \| Size: (\d+)x(\d+)')


def parse_info(text, sid):
    m = INFO_HEAD_RE.match(text.split("\n", 1)[0])
    if not m:
        raise Refuse(3, "not a get_spreadsheet_info result")
    if m.group(2) != sid:
        raise Refuse(3, "info came from spreadsheet %s, expected %s" % (m.group(2), sid))
    tabs = {}
    for line in text.split("\n")[1:]:
        t = INFO_TAB_RE.match(line)
        if t:
            tabs[t.group(1)] = (int(t.group(3)), int(t.group(4)))
    if not tabs:
        raise Refuse(3, "info lists no tabs")
    return tabs


def quote_tab(tab):
    return "'" + tab.replace("'", "''") + "'"


def pad(row, n):
    return (list(row) + [""] * n)[:n]


# ── the tracker ──────────────────────────────────────────────────────────────
def tracker_pages(tab, grid_rows):
    pages, a = [], 1
    while a <= grid_rows:
        b = min(a + PAGE - 1, grid_rows)
        pages.append((a, b, "%s!A%d:M%d" % (quote_tab(tab), a, b)))
        a = b + 1
    return pages


def assemble(pages, results):
    """Sheet rows keyed by row number; rows a read did not return are empty."""
    by_row = {}
    for (a, b, _), rows in zip(pages, results):
        if len(rows) > b - a + 1:
            raise Refuse(3, "a page returned more rows than it covers")
        for i, cells in enumerate(rows):
            by_row[a + i] = pad(cells, 13)
    return by_row


def tracker_items(by_row):
    header = by_row.get(1)
    if header is None or [c.strip() for c in header] != TRACKER_HEADER:
        raise Refuse(4, "tracker header changed: %r" % (header,))
    items, warnings, seen = [], [], {}
    for r in sorted(k for k in by_row if k >= 2):
        cells = by_row[r]
        if not any(c.strip() for c in cells):
            continue
        num, name = cells[0].strip(), cells[3].strip()
        if not num:
            warnings.append("row %d has data but no # — left out of the snapshot" % r)
            continue
        if CATEGORY_RE.match(num) and not name:
            continue                                     # a category row, not an item
        if CATEGORY_RE.match(num):
            warnings.append("row %d: category-style # %s has an item name — kept as an item" % (r, num))
        if num in seen:
            warnings.append("# %s appears on rows %d and %d — both kept" % (num, seen[num], r))
        seen.setdefault(num, r)
        items.append(cells)
    if not items:
        raise Refuse(3, "the tracker read holds no items")
    if len(items) > SLOT:
        raise Refuse(5, "%d items do not fit a %d-row week block" % (len(items), SLOT))
    return items, warnings


def digest(items):
    blob = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ── config and run folders ───────────────────────────────────────────────────
def load_config(path=None):
    path = os.path.expanduser(path or os.environ.get("ZYNKR_OPS_WEEKLY_CONFIG")
                              or "~/.config/zynkr/ops-weekly.json")
    try:
        cfg = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refuse(2, "config unreadable: %s (%s)" % (path, e))
    src = cfg.get("sources", {})
    mt, led = src.get("main_tracker", {}), src.get("ledger", {})
    need = {"google_account": cfg.get("google_account"), "sources.main_tracker.id": mt.get("id"),
            "sources.main_tracker.tab": mt.get("tab"), "sources.main_tracker.cycle": mt.get("cycle"),
            "sources.ledger.id": led.get("id"), "sources.ledger.epoch_week": led.get("epoch_week")}
    missing = [k for k, v in need.items() if not v or str(v).startswith("<")]
    if missing:
        raise Refuse(2, "config %s is missing %s" % (path, ", ".join(missing)))
    if mt["id"] == led["id"]:
        raise Refuse(2, "the Ledger id equals the Main Tracker id; refusing")
    monday(led["epoch_week"])
    return {"path": path, "account": cfg["google_account"], "tracker": mt["id"], "tab": mt["tab"],
            "cycle": mt["cycle"], "ledger": led["id"], "epoch": led["epoch_week"]}


def state_dir():
    return os.path.expanduser(os.environ.get("ZYNKR_OPS_WEEKLY_STATE")
                              or "~/.local/state/zynkr/ops-weekly")


def call(tool, args, save=None):
    c = {"tool": "mcp__google-workspace__" + tool, "args": args}
    if save:
        c["save"] = save
    return c


def read_call(run, sid, rng, name):
    return call("read_sheet_values",
                {"user_google_email": run["account"], "spreadsheet_id": sid, "range_name": rng},
                os.path.join(run["dir"], name + ".txt"))


def info_call(run, sid, name):
    return call("get_spreadsheet_info", {"user_google_email": run["account"], "spreadsheet_id": sid},
                os.path.join(run["dir"], name + ".txt"))


def load_run(d):
    p = os.path.join(d, "run.json")
    if not os.path.exists(p):
        raise Refuse(2, "not a snapshot run folder: %s" % d)
    return json.load(open(p, encoding="utf-8"))


def save_run(run):
    with open(os.path.join(run["dir"], "run.json"), "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=1)


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


# ── snapshot steps ───────────────────────────────────────────────────────────
def snap_start(week, config=None, now=None, base=None):
    cfg = load_config(config)
    k = week_index(week, cfg["epoch"])
    now = parse_now(now)
    d = os.path.join(base or os.path.join(state_dir(), "runs"),
                     "%s-snapshot-%s" % (week, now.strftime("%Y%m%dT%H%M%S")))
    n = 1
    while os.path.exists(d + ("" if n == 1 else "-%d" % n)):
        n += 1
    d = d + ("" if n == 1 else "-%d" % n)
    os.makedirs(d)
    first, last = slot(k)
    run = dict(cfg, dir=d, week=week, k=k, weeks_row=weeks_row(k), first=first, last=last)
    save_run(run)
    r = weeks_row(k)
    calls = [info_call(run, cfg["tracker"], "ti"), info_call(run, cfg["ledger"], "li"),
             read_call(run, cfg["ledger"], "Weeks!A1:J1", "wh"),
             read_call(run, cfg["ledger"], "Weeks!A%d:J%d" % (r, r), "wr"),
             read_call(run, cfg["ledger"], "Snapshot!A1:P1", "sh")]
    return {"dir": d, "week": week, "calls": calls}


def committed(row, run):
    row = pad(row, 10)
    if row[0] != run["week"] or row[1] != "ok":
        return False
    try:
        items, first, last = int(row[5]), int(row[6]), int(row[7])
    except ValueError:
        return False
    return (row[3] == run["cycle"] and row[9] == LAYOUT and first == run["first"]
            and 1 <= items <= SLOT and last == first + items - 1)


def snap_pages(d):
    run = load_run(d)
    ti = parse_info(load_result(os.path.join(d, "ti.txt")), run["tracker"])
    li = parse_info(load_result(os.path.join(d, "li.txt")), run["ledger"])
    if run["tab"] not in ti:
        raise Refuse(4, "the tracker has no tab %r" % run["tab"])
    grid_rows, grid_cols = ti[run["tab"]]
    if grid_cols < 13:
        raise Refuse(4, "tracker tab is only %d columns wide" % grid_cols)
    for name in ("Weeks", "Updates", "Snapshot"):     # the snapshot's own tabs, not later phases'
        if name not in li:
            raise Refuse(4, "the Ledger has no %s tab" % name)
        if name in ti:
            raise Refuse(4, "the tracker also has a tab named %s; a misdirected write could land there" % name)
    warnings = []
    snap_rows = li["Snapshot"][0]
    if snap_rows < run["last"]:
        raise Refuse(5, "Snapshot has %d rows; week %s needs rows up to %d — grow the grid"
                     % (snap_rows, run["week"], run["last"]))
    if snap_rows < run["last"] + SLOT * WARN_WEEKS:
        warnings.append("Snapshot grid ends at row %d: fewer than %d weeks of room left" % (snap_rows, WARN_WEEKS))
    if li["Weeks"][0] < run["weeks_row"]:
        raise Refuse(5, "Weeks has %d rows; it needs row %d" % (li["Weeks"][0], run["weeks_row"]))
    wh = parse_values(load_result(os.path.join(d, "wh.txt")), run["ledger"], "Weeks!A1:J1")
    sh = parse_values(load_result(os.path.join(d, "sh.txt")), run["ledger"], "Snapshot!A1:P1")
    if not wh or pad(wh[0], 10) != WEEKS_HEADER:
        raise Refuse(4, "Weeks header changed")
    if not sh or pad(sh[0], 16) != SNAPSHOT_HEADER:
        raise Refuse(4, "Snapshot header changed")
    r = run["weeks_row"]
    wr = parse_values(load_result(os.path.join(d, "wr.txt")), run["ledger"], "Weeks!A%d:J%d" % (r, r))
    if wr and wr[0] and pad(wr[0], 10)[0] not in ("", run["week"]):
        raise Refuse(4, "Weeks row %d belongs to %s, not %s — was the epoch changed?" % (r, wr[0][0], run["week"]))
    if wr and committed(wr[0], run):
        return {"already": True, "week": run["week"],
                "delivered": "already-snapshotted;Weeks!A%d" % r, "warnings": warnings}
    pages = tracker_pages(run["tab"], grid_rows)
    run.update(grid=[grid_rows, grid_cols], pages=pages, warnings=warnings)
    save_run(run)
    calls = [read_call(run, run["tracker"], rng, "t%d" % (i + 1)) for i, (_, _, rng) in enumerate(pages)]
    return {"already": False, "week": run["week"], "calls": calls, "warnings": warnings}


def read_tracker(run, prefix):
    pages = [tuple(p) for p in run["pages"]]
    results = [parse_values(load_result(os.path.join(run["dir"], "%s%d.txt" % (prefix, i + 1))),
                            run["tracker"], rng) for i, (_, _, rng) in enumerate(pages)]
    return assemble(pages, results)


def snap_plan(d, now=None):
    run = load_run(d)
    if "pages" not in run:
        raise Refuse(2, "run `snapshot pages` first")
    items, warnings = tracker_items(read_tracker(run, "t"))
    at = stamp(parse_now(now))
    rows = [[run["week"], at, run["cycle"]] + [str(c) for c in cells] for cells in items]
    first, last, n = run["first"], run["last"], len(items)
    ops = [call("modify_sheet_values",
                {"user_google_email": run["account"], "spreadsheet_id": run["ledger"],
                 "range_name": "Snapshot!A%d:P%d" % (first, first + n - 1),
                 "value_input_option": "RAW", "values": rows})]
    if first + n <= last:
        ops.append(call("modify_sheet_values",
                        {"user_google_email": run["account"], "spreadsheet_id": run["ledger"],
                         "range_name": "Snapshot!A%d:P%d" % (first + n, last), "clear_values": True}))
    readback = [read_call(run, run["ledger"], "Snapshot!A%d:P%d" % (first, first + PAGE - 1), "r1"),
                read_call(run, run["ledger"], "Snapshot!A%d:P%d" % (first + PAGE, last), "r2")]
    recheck = [info_call(run, run["tracker"], "ti2")] + [
        read_call(run, run["tracker"], rng, "u%d" % (i + 1)) for i, (_, _, rng) in enumerate(run["pages"])]
    run.update(items=n, snapshot_at=at, digest=digest(items), rows=rows,
               warnings=run.get("warnings", []) + warnings)
    save_run(run)
    return {"week": run["week"], "items": n, "digest": run["digest"], "warnings": run["warnings"],
            "ops": ops, "readback": readback, "recheck": recheck}


def snap_check(d):
    run = load_run(d)
    if "rows" not in run:
        raise Refuse(2, "run `snapshot plan` first")
    first, last, n, rows = run["first"], run["last"], run["items"], run["rows"]
    r1 = parse_values(load_result(os.path.join(d, "r1.txt")), run["ledger"],
                      "Snapshot!A%d:P%d" % (first, first + PAGE - 1))
    r2 = parse_values(load_result(os.path.join(d, "r2.txt")), run["ledger"],
                      "Snapshot!A%d:P%d" % (first + PAGE, last))
    got = [pad(x, 16) for x in r1] + [[""] * 16] * (PAGE - len(r1)) + [pad(x, 16) for x in r2]
    for i, want in enumerate(rows):
        have = got[i] if i < len(got) else [""] * 16
        if have != pad(want, 16):
            col = next(j for j in range(16) if have[j] != pad(want, 16)[j])
            raise Refuse(6, "Snapshot row %d, column %s: planned %r, found %r"
                         % (first + i, SNAPSHOT_HEADER[col], pad(want, 16)[col], have[col]))
    for i in range(n, len(got)):
        if any(c.strip() for c in got[i]):
            raise Refuse(6, "Snapshot row %d should be empty after the last item" % (first + i))
    ti2 = parse_info(load_result(os.path.join(d, "ti2.txt")), run["tracker"])
    if list(ti2.get(run["tab"], (0, 0))) != list(run["grid"]):
        raise Refuse(6, "the tracker tab changed size during the run (%s → %s)"
                     % (run["grid"], ti2.get(run["tab"])))
    again, _ = tracker_items(read_tracker(run, "u"))
    if digest(again) != run["digest"]:
        raise Refuse(6, "the tracker changed during the run (or a read was copied wrong): re-run from start")
    r = run["weeks_row"]
    commit_row = [run["week"], "ok", run["snapshot_at"], run["cycle"], run["tracker"], str(n),
                  str(first), str(first + n - 1), run["digest"], LAYOUT]
    run.update(checked=True, commit_row=commit_row)
    save_run(run)
    return {"commit": call("modify_sheet_values",
                           {"user_google_email": run["account"], "spreadsheet_id": run["ledger"],
                            "range_name": "Weeks!A%d:J%d" % (r, r), "value_input_option": "RAW",
                            "values": [commit_row]}),
            "readback": read_call(run, run["ledger"], "Weeks!A%d:J%d" % (r, r), "wc")}


def snap_confirm(d):
    run = load_run(d)
    if not run.get("checked"):
        raise Refuse(7, "no passed check in this run folder")
    r = run["weeks_row"]
    wc = parse_values(load_result(os.path.join(d, "wc.txt")), run["ledger"], "Weeks!A%d:J%d" % (r, r))
    if not wc or pad(wc[0], 10) != run["commit_row"]:
        raise Refuse(7, "Weeks row %d does not read back as committed: %r" % (r, wc[0] if wc else None))
    return {"week": run["week"], "status": "ok",
            "delivered": "%d-items;Snapshot!A%d:P%d;Weeks!A%d" % (run["items"], run["first"],
                                                                  run["first"] + run["items"] - 1, r)}


# ── per-week blocks for the other beats (Reports, Decisions) ─────────────────
def col_letter(n):
    return chr(ord("A") + n - 1)


def block_slot(tab, k):
    size = BLOCKS[tab][0]
    return 2 + size * k, 1 + size * (k + 1)


def blk_start(tab, week, rows_path, config=None, now=None, base=None):
    if tab not in BLOCKS:
        raise Refuse(2, "no weekly block for tab %r (have %s)" % (tab, ", ".join(sorted(BLOCKS))))
    cfg = load_config(config)
    k = week_index(week, cfg["epoch"])
    size, header, _, _ = BLOCKS[tab]
    rows = load_rows(rows_path)
    width = len(header)
    if len(rows) > size:
        raise Refuse(5, "%d rows do not fit the %d-row %s block" % (len(rows), size, tab))
    for i, r in enumerate(rows):
        if len(r) > width or not all(isinstance(c, str) for c in r):
            raise Refuse(3, "row %d is not %d text cells" % (i + 1, width))
        if pad(r, width)[0] != week:
            raise Refuse(3, "row %d belongs to %r, not %s" % (i + 1, r[0] if r else None, week))
    now = parse_now(now)
    d = os.path.join(base or os.path.join(state_dir(), "runs"),
                     "%s-%s-%s" % (week, tab.lower(), now.strftime("%Y%m%dT%H%M%S")))
    n = 1
    while os.path.exists(d + ("" if n == 1 else "-%d" % n)):
        n += 1
    d = d + ("" if n == 1 else "-%d" % n)
    os.makedirs(d)
    first, last = block_slot(tab, k)
    run = dict(cfg, dir=d, week=week, k=k, tab=tab, weeks_row=weeks_row(k), first=first, last=last,
               rows=[pad(r, width) for r in rows])
    save_run(run)
    r = weeks_row(k)
    calls = [info_call(run, cfg["ledger"], "li"),
             read_call(run, cfg["ledger"], "%s!A1:%s1" % (tab, COLS[tab]), "bh"),
             read_call(run, cfg["ledger"], "Weeks!A1:N1", "wh"),
             read_call(run, cfg["ledger"], "Weeks!A%d:N%d" % (r, r), "wr")]
    return {"dir": d, "week": week, "tab": tab, "rows": len(rows), "calls": calls}


def blk_plan(d):
    run = load_run(d)
    tab, size = run["tab"], BLOCKS[run["tab"]][0]
    header = BLOCKS[tab][1]
    li = parse_info(load_result(os.path.join(d, "li.txt")), run["ledger"])
    if tab not in li or "Weeks" not in li:
        raise Refuse(4, "the Ledger has no %s tab (or no Weeks tab); run the Phase 2 setup" % tab)
    if li[tab][0] < run["last"]:
        raise Refuse(5, "%s has %d rows; week %s needs rows up to %d — grow the grid" % (tab, li[tab][0], run["week"], run["last"]))
    bh = parse_values(load_result(os.path.join(d, "bh.txt")), run["ledger"], "%s!A1:%s1" % (tab, COLS[tab]))
    if not bh or pad(bh[0], len(header)) != header:
        raise Refuse(4, "%s header changed" % tab)
    wh = parse_values(load_result(os.path.join(d, "wh.txt")), run["ledger"], "Weeks!A1:N1")
    if not wh or pad(wh[0], 14) != WEEKS_HEADER + WEEKS_BEAT_HEADER:
        raise Refuse(4, "Weeks header is not the Phase 2 header (A–N); run the Phase 2 setup")
    r = run["weeks_row"]
    wr = parse_values(load_result(os.path.join(d, "wr.txt")), run["ledger"], "Weeks!A%d:N%d" % (r, r))
    if wr and pad(wr[0], 14)[0] not in ("", run["week"]):
        raise Refuse(4, "Weeks row %d belongs to %s, not %s — was the epoch changed?" % (r, wr[0][0], run["week"]))
    first, last, rows, end = run["first"], run["last"], run["rows"], col_letter(len(header))
    ops = []
    if rows:
        ops.append(call("modify_sheet_values",
                        {"user_google_email": run["account"], "spreadsheet_id": run["ledger"],
                         "range_name": "%s!A%d:%s%d" % (tab, first, end, first + len(rows) - 1),
                         "value_input_option": "RAW", "values": rows}))
    if first + len(rows) <= last:
        ops.append(call("modify_sheet_values",
                        {"user_google_email": run["account"], "spreadsheet_id": run["ledger"],
                         "range_name": "%s!A%d:%s%d" % (tab, first + len(rows), end, last), "clear_values": True}))
    readback = [read_call(run, run["ledger"], "%s!A%d:%s%d" % (tab, first, end, last), "rb")]
    run.update(planned=True)
    save_run(run)
    return {"week": run["week"], "tab": tab, "rows": len(rows), "ops": ops, "readback": readback}


def blk_check(d, now=None):
    run = load_run(d)
    if not run.get("planned"):
        raise Refuse(2, "run `block plan` first")
    tab, header, scol, tcol = run["tab"], BLOCKS[run["tab"]][1], BLOCKS[run["tab"]][2], BLOCKS[run["tab"]][3]
    width, end = len(header), col_letter(len(header))
    got = parse_values(load_result(os.path.join(d, "rb.txt")), run["ledger"],
                       "%s!A%d:%s%d" % (tab, run["first"], end, run["last"]))
    got = [pad(x, width) for x in got]
    for i, want in enumerate(run["rows"]):
        have = got[i] if i < len(got) else [""] * width
        if have != want:
            col = next(j for j in range(width) if have[j] != want[j])
            raise Refuse(6, "%s row %d, column %s: planned %r, found %r" % (tab, run["first"] + i, header[col], want[col], have[col]))
    for i in range(len(run["rows"]), len(got)):
        if any(c.strip() for c in got[i]):
            raise Refuse(6, "%s row %d should be empty" % (tab, run["first"] + i))
    r = run["weeks_row"]
    at = stamp(parse_now(now))
    cells = ["ok", at]
    run.update(checked=True, commit_cells=cells)
    save_run(run)
    return {"commit": call("modify_sheet_values",
                           {"user_google_email": run["account"], "spreadsheet_id": run["ledger"],
                            "range_name": "Weeks!%s%d:%s%d" % (scol, r, tcol, r),
                            "value_input_option": "RAW", "values": [cells]}),
            "readback": read_call(run, run["ledger"], "Weeks!%s%d:%s%d" % (scol, r, tcol, r), "wc")}


def blk_confirm(d):
    run = load_run(d)
    if not run.get("checked"):
        raise Refuse(7, "no passed check in this run folder")
    tab, scol, tcol = run["tab"], BLOCKS[run["tab"]][2], BLOCKS[run["tab"]][3]
    r = run["weeks_row"]
    wc = parse_values(load_result(os.path.join(d, "wc.txt")), run["ledger"], "Weeks!%s%d:%s%d" % (scol, r, tcol, r))
    if not wc or pad(wc[0], 2) != run["commit_cells"]:
        raise Refuse(7, "Weeks!%s%d does not read back as committed" % (scol, r))
    n = len(run["rows"])
    where = "%s!A%d:%s%d" % (tab, run["first"], col_letter(len(BLOCKS[tab][1])), run["first"] + n - 1) if n else "%s(none)" % tab
    return {"week": run["week"], "status": "ok", "delivered": "%d-rows;%s;Weeks!%s%d" % (n, where, scol, r)}


def report_rows(reports, routing, week):
    """rollup's parse_reports.py output + parse_routing.py output -> Reports rows, one per poster."""
    heading = routing.get("primary_heading", {}) if isinstance(routing, dict) else {}
    rows = []
    for rec in sorted(reports.get("records", []), key=lambda x: x.get("email", "")):
        nums = rec.get("numbers") or {}
        rows.append([week, str(rec.get("create_time") or ""), str(rec.get("email") or ""),
                     str(heading.get(rec.get("email"), "")),
                     "\n".join(str(x) for x in rec.get("last_week") or []),
                     "\n".join(str(x) for x in rec.get("this_week") or []),
                     "" if nums.get("empty") else str(nums.get("raw") or ""),
                     str(rec.get("blocker") or ""), str(rec.get("format") or "")])
    return rows


ITEM_REF = re.compile(r"(?<![\d.])(\d{1,2}\.\d{2})(?![\d.])")


def decision_rows(decisions, week, meeting, source):
    """The meeting's resolutions -> Decisions rows. Each input item: {"content", "owner", "due",
    optional "item"}. A resolution without an owner or a due date is 待決, as the beat's rule says."""
    if not isinstance(decisions, list):
        raise Refuse(3, "decisions must be a JSON list")
    rows = []
    for i, d in enumerate(decisions):
        if not isinstance(d, dict) or not str(d.get("content") or "").strip():
            raise Refuse(3, "decision %d has no content" % (i + 1))
        content = str(d["content"]).strip()
        owner, due = str(d.get("owner") or "").strip(), str(d.get("due") or "").strip()
        item = str(d.get("item") or "").strip()
        if not item:
            m = ITEM_REF.search(content)
            item = m.group(1) if m else ""
        rows.append([week, meeting, "決議" if owner and due else "待決", content, owner, due, item, source])
    return rows


# ── diff: what changed between two snapshots ─────────────────────────────────
KINDS = {"狀態": "status", "開始": "schedule", "結束": "schedule", "負責人": "owner", "協助者": "owner",
         "重要": "priority", "緊急": "priority", "Priority": "priority", "主類別": "text",
         "子類別": "text", "項目（正規化）": "text", "備註": "text"}
PLACEHOLDER = "YYYY-MM-DD"
DATE_PARTS = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")


def norm_date(v):
    m = DATE_PARTS.match(v.strip())
    return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3))) if m else None


def item_key(key):
    cycle, num = key
    parts = tuple(int(p) if p.isdigit() else p for p in num.split("."))
    return (cycle, parts)


def snapshot_items(rows):
    """One week's block → (week, snapshot_at, {(cycle, #): {column: value}})."""
    week = at = None
    items = {}
    for r in rows:
        r = pad(r, 16)
        if not any(c.strip() for c in r):
            continue
        if week is None:
            week, at = r[0], r[1]
        elif r[0] != week or r[1] != at:
            raise Refuse(3, "one snapshot holds rows from two runs (%s %s / %s %s)" % (week, at, r[0], r[1]))
        items[(r[2], r[3])] = dict(zip(TRACKER_HEADER, r[3:]))
    if week is None:
        raise Refuse(3, "an empty snapshot")
    return week, at, items


def diff_snapshots(rows_a, rows_b, updates=()):
    """Every changed cell from snapshot A to snapshot B. A change is `logged` only when an Updates
    row with the same cycle, #, column and NEW value was written inside (A.snapshot_at,
    B.snapshot_at]; anything else was edited by hand. Matching on the time window, never on a week
    label, is what keeps a late-Sunday apply and a Monday edit apart."""
    wa, ta, a = snapshot_items(rows_a)
    wb, tb, b = snapshot_items(rows_b)
    ca, cb = sorted({k[0] for k in a}), sorted({k[0] for k in b})
    if ca != cb:
        raise Refuse(4, "the snapshots belong to different cycles (%s vs %s); compare within one" % (ca, cb))
    t_from, t_to = parse_now(ta), parse_now(tb)
    if not t_from < t_to:
        raise Refuse(2, "snapshot A (%s) is not older than snapshot B (%s)" % (ta, tb))
    log = []
    for u in updates:
        u = pad(u, 14)
        try:
            t = parse_now(u[1]) if u[1].strip() else None
        except ValueError:
            t = None
        if t is not None and t_from < t <= t_to:
            log.append(u)
    used = set()

    def logged(cycle, num, column, new):
        for i, u in enumerate(log):
            if i not in used and u[2] == cycle and u[3] == num and u[5] == column and u[7] == new:
                used.add(i)
                return True
        return False

    changed = []
    for key in sorted(set(a) & set(b), key=item_key):
        for col in TRACKER_HEADER[1:]:
            old, new = a[key][col], b[key][col]
            if old == new:
                continue
            kind = KINDS[col]
            if col in ("開始", "結束"):
                if old.strip() == PLACEHOLDER and norm_date(new):
                    kind = "dated"
                elif norm_date(old) and new.strip() == PLACEHOLDER:
                    kind = "undated"
            cosmetic = old.strip() == new.strip() or (norm_date(old) is not None and norm_date(old) == norm_date(new))
            changed.append({"cycle": key[0], "#": key[1], "項目": b[key]["項目（正規化）"], "column": col,
                            "old": old, "new": new, "kind": kind, "cosmetic": cosmetic,
                            "logged": logged(key[0], key[1], col, new)})
    added = [{"cycle": k[0], "#": k[1], "項目": b[k]["項目（正規化）"], "狀態": b[k]["狀態"],
              "logged": logged(k[0], k[1], "新增", b[k]["項目（正規化）"])}
             for k in sorted(set(b) - set(a), key=item_key)]
    removed = [{"cycle": k[0], "#": k[1], "項目": a[k]["項目（正規化）"],
                "logged": logged(k[0], k[1], "刪除", "")}
               for k in sorted(set(a) - set(b), key=item_key)]
    manual = [c for c in changed if not c["logged"] and not c["cosmetic"]]
    return {"from": wa, "to": wb, "from_at": ta, "to_at": tb, "changed": changed, "added": added,
            "removed": removed, "manual_edits": len(manual),
            "orphan_log": [log[i] for i in range(len(log)) if i not in used]}


def load_rows(path):
    try:
        rows = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refuse(3, "cannot read rows from %s (%s)" % (path, e))
    if not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
        raise Refuse(3, "%s must hold a JSON list of rows" % path)
    return rows


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    w = sub.add_parser("week")
    w.add_argument("--now")
    sub.add_parser("schema")
    s = sub.add_parser("snapshot")
    s.add_argument("step", choices=["start", "pages", "plan", "check", "confirm"])
    s.add_argument("--week")
    s.add_argument("--config")
    s.add_argument("--dir")
    s.add_argument("--now")
    bk = sub.add_parser("block")
    bk.add_argument("step", choices=["start", "plan", "check", "confirm"])
    bk.add_argument("--tab")
    bk.add_argument("--week")
    bk.add_argument("--rows")
    bk.add_argument("--config")
    bk.add_argument("--dir")
    bk.add_argument("--now")
    rw = sub.add_parser("rows")
    rw.add_argument("kind", choices=["reports", "decisions"])
    rw.add_argument("--reports")
    rw.add_argument("--routing")
    rw.add_argument("--input")
    rw.add_argument("--meeting")
    rw.add_argument("--source", default="")
    rw.add_argument("--week", required=True)
    df = sub.add_parser("diff")
    df.add_argument("--a", required=True, help="older snapshot block: a JSON list of 16-column rows")
    df.add_argument("--b", required=True, help="newer snapshot block")
    df.add_argument("--updates", help="Updates rows (JSON list of 14-column rows)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.mutate:
        return mutate()
    try:
        if a.cmd == "week":
            now = parse_now(a.now)
            emit({"week": week_of(now), "now": stamp(now)})
        elif a.cmd == "schema":
            emit({"layout": LAYOUT, "slot": SLOT,
                  "tabs": [{"tab": t, "range": "%s!A1:%s1" % (t, COLS[t]), "values": [h]} for t, h in TABS]})
        elif a.cmd == "snapshot":
            if a.step == "start":
                if not a.week:
                    raise Refuse(2, "snapshot start needs --week")
                emit(snap_start(a.week, a.config, a.now))
            else:
                if not a.dir:
                    raise Refuse(2, "snapshot %s needs --dir" % a.step)
                fn = {"pages": snap_pages, "plan": snap_plan, "check": snap_check, "confirm": snap_confirm}[a.step]
                emit(fn(a.dir, a.now) if a.step == "plan" else fn(a.dir))
        elif a.cmd == "block":
            if a.step == "start":
                if not (a.tab and a.week and a.rows):
                    raise Refuse(2, "block start needs --tab, --week and --rows")
                emit(blk_start(a.tab, a.week, a.rows, a.config, a.now))
            else:
                if not a.dir:
                    raise Refuse(2, "block %s needs --dir" % a.step)
                fn = {"plan": blk_plan, "check": blk_check, "confirm": blk_confirm}[a.step]
                emit(fn(a.dir, a.now) if a.step == "check" else fn(a.dir))
        elif a.cmd == "rows":
            monday(a.week)
            try:
                if a.kind == "reports":
                    if not (a.reports and a.routing):
                        raise Refuse(2, "rows reports needs --reports and --routing")
                    emit(report_rows(json.load(open(a.reports, encoding="utf-8")),
                                     json.load(open(a.routing, encoding="utf-8")), a.week))
                else:
                    if not (a.input and a.meeting):
                        raise Refuse(2, "rows decisions needs --input and --meeting")
                    emit(decision_rows(json.load(open(a.input, encoding="utf-8")), a.week, a.meeting, a.source))
            except (OSError, ValueError) as e:
                raise Refuse(3, "cannot read the input (%s)" % e)
        elif a.cmd == "diff":
            emit(diff_snapshots(load_rows(a.a), load_rows(a.b), load_rows(a.updates) if a.updates else ()))
        else:
            ap.print_help()
            return 2
    except Refuse as e:
        print("ledger.py: %s" % e, file=sys.stderr)
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

    def refuses(name, code, fn, *args):
        try:
            fn(*args)
        except Refuse as e:
            if e.code != code:
                fails.append("%s: exit %d, want %d (%s)" % (name, e.code, code, e))
            return
        fails.append("%s: did not refuse (want exit %d)" % (name, code))

    def fmt(sid, rng, rows):
        if not rows:
            return "No data found in range '%s' for owner@example.com." % rng
        width = len(rows[0])
        lines = ["Successfully read %d rows from range '%s' in spreadsheet %s for owner@example.com:"
                 % (len(rows), rng, sid)]
        for i, r in enumerate(rows[:50], 1):
            lines.append("Row %2d: %s" % (i, list(r) + [""] * max(0, width - len(r))))
        if len(rows) > 50:
            lines.append("... and %d more rows" % (len(rows) - 50))
        return "\n".join(lines)

    def info(sid, title, tabs):
        out = ['Spreadsheet: "%s" (ID: %s) | Locale: en_US' % (title, sid), "Sheets (%d):" % len(tabs)]
        for i, (name, (r, c)) in enumerate(tabs.items()):
            out.append('  - "%s" (ID: %d) | Size: %dx%d | Conditional formats: 0' % (name, 100 + i, r, c))
        return "\n".join(out)

    # weeks
    check("week Sun 23:59 TPE", week_of(parse_now("2026-10-04T23:59:00+08:00")), "2026-W40")
    check("week Mon 00:00 TPE", week_of(parse_now("2026-10-05T00:00:00+08:00")), "2026-W41")
    check("week from UTC", week_of(parse_now("2026-10-04T16:30:00Z")), "2026-W41")
    check("k W40", week_index("2026-W40", "2026-W40"), 0)
    check("k W41", week_index("2026-W41", "2026-W40"), 1)
    check("k W53", week_index("2026-W53", "2026-W40"), 13)
    check("k 2027-W01", week_index("2027-W01", "2026-W40"), 14)
    check("slot W40", slot(0), (2, 101))
    check("slot W41", slot(1), (102, 201))
    check("weeks row W41", weeks_row(1), 3)
    refuses("week before epoch", 2, week_index, "2026-W39", "2026-W40")
    refuses("no such week", 2, monday, "2027-W53")
    refuses("bad key", 2, monday, "2026-40")

    # parsing
    rows = [["#", "x"], ["1.10", "a　b"], ["2", "it's \"q\"\nline"]]
    check("parse round trip", parse_values(fmt("S", "T!A1:B3", rows), "S", "T!A1:B3"), rows)
    check("parse pads short rows", parse_values(fmt("S", "T!A1:B2", [["a", "b"], ["c"]]), "S", "T!A1:B2"),
          [["a", "b"], ["c", ""]])
    check("parse json wrapper", parse_values(json.loads(json.dumps({"result": fmt("S", "R", rows)}))["result"],
                                             "S", "R"), rows)
    check("parse empty", parse_values(fmt("S", "R", []), "S", "R"), [])
    refuses("truncated", 3, parse_values, fmt("S", "R", [["x"]] * 51), "S", "R")
    refuses("wrong sheet", 3, parse_values, fmt("S", "R", rows), "OTHER", "R")
    refuses("wrong range", 3, parse_values, fmt("S", "R", rows), "S", "R2")
    refuses("dropped row", 3, parse_values, "\n".join(fmt("S", "R", rows).split("\n")[:-1]), "S", "R")
    refuses("retyped row", 3, parse_values, fmt("S", "R", rows).replace("['1.10'", "[1.10"), "S", "R")
    with_errors = fmt("S", "R", rows) + "\n\nDetailed errors:\n- C3: #REF!"
    check("trailing section ignored", parse_values(with_errors, "S", "R"), rows)

    # tracker pages and items
    check("pages 65", [p[2] for p in tracker_pages("H2 專案項目", 65)],
          ["'H2 專案項目'!A1:M50", "'H2 專案項目'!A51:M65"])
    item = ["1.10", "1.0 M", "1.1 S", "名", "重要", "緊急", "P1", "Ann", "Bo", "YYYY-MM-DD", "2026-12-30", "進行中", "備"]
    by_row = {1: TRACKER_HEADER, 2: pad(["1.0", "1.0 M"], 13), 3: item, 4: [""] * 13,
              5: pad(["", "", "", "orphan"], 13), 6: pad(["2.0", "", "", "named"], 13), 7: item}
    items, warns = tracker_items(by_row)
    check("items kept", [i[0] for i in items], ["1.10", "2.0", "1.10"])
    check("1.10 stays text", items[0][0], "1.10")
    check("placeholder date kept", items[0][9], "YYYY-MM-DD")
    check("warnings", len(warns), 3)
    bad = dict(by_row)
    bad[1] = ["#"] + TRACKER_HEADER[1:-1] + ["Notes"]
    refuses("header changed", 4, tracker_items, bad)
    refuses("no items", 3, tracker_items, {1: TRACKER_HEADER})
    crowded = {r: item for r in range(2, 103)}
    crowded[1] = TRACKER_HEADER
    refuses("too many items", 5, tracker_items, crowded)

    # an end-to-end snapshot against fake MCP results
    tmp = tempfile.mkdtemp(prefix="ledger-selftest-")
    try:
        cfgp = os.path.join(tmp, "cfg.json")
        json.dump({"google_account": "owner@example.com",
                   "sources": {"main_tracker": {"id": "TRK", "tab": "H2 專案項目", "cycle": "2026H2"},
                               "ledger": {"id": "LED", "epoch_week": "2026-W40"}}}, open(cfgp, "w"))
        def item_row(cat, i):
            return ["%d.%02d" % (cat, i), "%d.0 M" % cat, "%d.1 S" % cat, "item %d.%d" % (cat, i), "", "",
                    "P1", "Ann", "", "YYYY-MM-DD", "2026-12-30", "進行中", "note\n%d" % i]

        # Row 51 opens the second 50-row page with a SHORT category row: the real tool pads a
        # page only to the width of its own first row, so the rows after it arrive unpadded.
        base_tracker = ([TRACKER_HEADER, ["1.0", "1.0 M"]] + [item_row(1, i) for i in range(1, 49)]
                        + [["2.0", "2.0 S"]] + [item_row(2, i) for i in range(1, 8)])
        base_tracker += [[""] * 13] * (65 - len(base_tracker))
        ledger_tabs = {"Weeks": (100, 10), "Updates": (1000, 14), "Snapshot": (5000, 16)}

        def serve(d, calls, sheet):
            tracker = sheet["TRACKER"]
            for c in calls:
                a = c["args"]
                if c["tool"].endswith("get_spreadsheet_info"):
                    if a["spreadsheet_id"] == "TRK":
                        text = info("TRK", "Main", {"README": (1000, 26), "H2 專案項目": (65, 13)})
                    else:
                        text = info("LED", "Ledger", ledger_tabs)
                    open(c["save"], "w").write(text)
                    continue
                rng = a["range_name"]
                m = re.match(r"^(.*)!A(\d+):([A-Z])(\d+)$", rng)
                tab, r0, r1 = m.group(1), int(m.group(2)), int(m.group(4))
                src = tracker if tab == "'H2 專案項目'" else sheet[tab]
                got = [src[i - 1] if i - 1 < len(src) else [] for i in range(r0, r1 + 1)]
                while got and not any(x.strip() for x in got[-1]):
                    got.pop()
                open(c["save"], "w", encoding="utf-8").write(
                    fmt(a["spreadsheet_id"], rng, [list(x) for x in got]))

        def do_ops(ops, sheet, mangle=None):
            for c in ops:
                a = c["args"]
                m = re.match(r"^(\w+)!A(\d+):([A-Z])(\d+)$", a["range_name"])
                tab, r0, r1 = m.group(1), int(m.group(2)), int(m.group(4))
                grid = sheet[tab]
                while len(grid) < r1:
                    grid.append([""] * 16)
                for i, r in enumerate(range(r0, r1 + 1)):
                    if a.get("clear_values"):
                        grid[r - 1] = [""] * 16
                    else:
                        v = list(a["values"][i])
                        if a.get("value_input_option") != "RAW":
                            # what Sheets does to a USER_ENTERED "1.10": the number 1.1
                            v = [str(float(x)) if re.match(r"^\d+\.\d+$", x) else x for x in v]
                        if mangle:
                            v = mangle(v)
                        grid[r - 1] = v

        def fresh_sheet():
            return {"Weeks": [WEEKS_HEADER], "Updates": [UPDATES_HEADER], "Snapshot": [SNAPSHOT_HEADER],
                    "TRACKER": [list(r) for r in base_tracker]}

        def run_all(sheet, mangle=None, between=None, now="2026-10-02T18:07:12+08:00"):
            st = snap_start("2026-W40", cfgp, now, base=os.path.join(tmp, "runs"))
            d = st["dir"]
            serve(d, st["calls"], sheet)
            pg = snap_pages(d)
            if pg["already"]:
                return d, pg
            serve(d, pg["calls"], sheet)
            pl = snap_plan(d, now)
            do_ops(pl["ops"], sheet, mangle)
            if between:
                between(sheet)
            serve(d, pl["readback"] + pl["recheck"], sheet)
            ck = snap_check(d)
            do_ops([ck["commit"]], sheet)
            serve(d, [ck["readback"]], sheet)
            return d, snap_confirm(d)

        def expect_refusal(name, code, sheet, **kw):
            try:
                run_all(sheet, **kw)
                fails.append("%s: the run committed" % name)
            except Refuse as e:
                check(name, e.code, code)
            check(name + " (nothing committed)", len(sheet["Weeks"]), 1)

        sheet = fresh_sheet()
        try:
            d, res = run_all(sheet)
            check("e2e delivered", res.get("delivered"), "55-items;Snapshot!A2:P56;Weeks!A2")
            snap_nums = [r[3] for r in sheet["Snapshot"][1:56]]
            check("e2e 1.10 stays text", "1.10" in snap_nums and "1.1" not in snap_nums, True)
            check("e2e categories left out", [n for n in snap_nums if n.endswith(".0")], [])
            check("e2e short rows padded", all(len(r) == 16 for r in sheet["Snapshot"][1:56]), True)
            check("e2e newline kept", sheet["Snapshot"][1][15], "note\n1")
            check("e2e weeks row", sheet["Weeks"][1][:2], ["2026-W40", "ok"])
            _, again = run_all(sheet)
            check("second run writes nothing", again.get("delivered"), "already-snapshotted;Weeks!A2")
        except Refuse as e:
            fails.append("e2e run refused: %s" % e)

        # a write that changed an item number (here by hand) must never be committed
        expect_refusal("coerced # caught", 6, fresh_sheet(),
                       mangle=lambda v: v[:3] + ["1.1" if v[3] == "1.10" else v[3]] + v[4:])

        # someone edits the tracker between the first read and the recheck
        def human_edit(s):
            s["TRACKER"][2][11] = "完成"
        expect_refusal("tracker edited mid-run", 6, fresh_sheet(), between=human_edit)

        sheet3 = fresh_sheet()
        # every field but the status: the commit never finished, so the week must be redone
        sheet3["Weeks"].append(["2026-W40", "", "2026-10-02T18:00:00+08:00", "2026H2", "TRK", "55",
                                "2", "56", "0" * 16, LAYOUT])
        try:
            _, res3 = run_all(sheet3)
            check("unfinished Weeks row is redone", res3.get("delivered"), "55-items;Snapshot!A2:P56;Weeks!A2")
        except Refuse as e:
            fails.append("unfinished Weeks row: %s" % e)

        sheet4 = fresh_sheet()
        sheet4["Weeks"].append(["2026-W39", "ok", "", "2026H2", "", "55", "2", "56", "", LAYOUT])
        try:
            run_all(sheet4)
            fails.append("a Weeks row of another week was overwritten")
        except Refuse as e:
            check("epoch drift refused", e.code, 4)

        refuses("ledger id = tracker id", 2, load_config, _write_cfg(tmp, "TRK", "TRK"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # per-week blocks (Phase 2): Reports
    check("block slot W40", block_slot("Reports", 0), (2, 21))
    check("block slot W41", block_slot("Reports", 1), (22, 41))
    rr = report_rows({"records": [
        {"email": "b@example.com", "create_time": "2026-10-05T01:00:00Z", "format": "tagged",
         "last_week": ["做完 A", "做完 B"], "this_week": ["做 C"], "numbers": {"raw": "—", "empty": True},
         "blocker": None},
        {"email": "a@example.com", "create_time": "2026-10-05T02:00:00Z", "format": "legacy",
         "last_week": [], "this_week": ["做 D"], "numbers": {"raw": "營收 10"}, "blocker": "等報價"}]},
        {"primary_heading": {"a@example.com": "#Sales"}}, "2026-W41")
    check("report rows sorted by owner", [r[2] for r in rr], ["a@example.com", "b@example.com"])
    check("report row department", rr[0][3], "#Sales")
    check("report row items joined", rr[1][4], "做完 A\n做完 B")
    check("report row empty numbers blank", rr[1][6], "")
    check("report row blocker", rr[0][7], "等報價")
    tmpb = tempfile.mkdtemp(prefix="ledger-block-")
    try:
        cfgb = _write_cfg(tmpb, "TRK", "LED")
        rows_p = os.path.join(tmpb, "rows.json")
        json.dump(rr, open(rows_p, "w"), ensure_ascii=False)
        weeks_hdr = WEEKS_HEADER + WEEKS_BEAT_HEADER

        def fmt_b(sid, rng, rows):
            return fmt(sid, rng, rows)

        def run_block(sheet, rows_path, mangle=None):
            st = blk_start("Reports", "2026-W41", rows_path, cfgb, "2026-10-06T09:40:00+08:00",
                           base=os.path.join(tmpb, "runs"))
            d = st["dir"]
            for c in st["calls"]:
                a = c["args"]
                if c["tool"].endswith("get_spreadsheet_info"):
                    open(c["save"], "w").write(info("LED", "Ledger", sheet["__tabs__"]))
                    continue
                tab, r0, r1 = re.match(r"^(\w+)!A(\d+):[A-Z](\d+)$", a["range_name"]).groups()
                grid = sheet[tab]
                got = [grid[i - 1] if i - 1 < len(grid) else [] for i in range(int(r0), int(r1) + 1)]
                while got and not any(x.strip() for x in got[-1]):
                    got.pop()
                open(c["save"], "w", encoding="utf-8").write(fmt_b("LED", a["range_name"], got))
            pl = blk_plan(d)
            for c in pl["ops"]:
                a = c["args"]
                tab, r0, r1 = re.match(r"^(\w+)!A(\d+):[A-Z](\d+)$", a["range_name"]).groups()
                grid = sheet[tab]
                while len(grid) < int(r1):
                    grid.append([""] * 11)
                for i, r in enumerate(range(int(r0), int(r1) + 1)):
                    v = [""] * 11 if a.get("clear_values") else list(a["values"][i])
                    grid[r - 1] = mangle(v) if (mangle and not a.get("clear_values")) else v
            rb = pl["readback"][0]
            tab, r0, r1 = re.match(r"^(\w+)!A(\d+):[A-Z](\d+)$", rb["args"]["range_name"]).groups()
            grid = sheet[tab]
            got = [grid[i - 1] if i - 1 < len(grid) else [] for i in range(int(r0), int(r1) + 1)]
            while got and not any(x.strip() for x in got[-1]):
                got.pop()
            open(rb["save"], "w", encoding="utf-8").write(fmt_b("LED", rb["args"]["range_name"], got))
            ck = blk_check(d, "2026-10-06T09:45:00+08:00")
            a = ck["commit"]["args"]
            m = re.match(r"^Weeks!([A-Z])(\d+):([A-Z])(\d+)$", a["range_name"])
            row = int(m.group(2))
            while len(sheet["Weeks"]) < row:
                sheet["Weeks"].append([""] * 14)
            w = pad(sheet["Weeks"][row - 1], 14)
            w[ord(m.group(1)) - 65:ord(m.group(3)) - 64] = a["values"][0]
            sheet["Weeks"][row - 1] = w
            open(ck["readback"]["save"], "w", encoding="utf-8").write(
                fmt_b("LED", ck["readback"]["args"]["range_name"], [w[ord(m.group(1)) - 65:ord(m.group(3)) - 64]]))
            return blk_confirm(d)

        def fresh_b():
            return {"__tabs__": {"Weeks": (100, 14), "Reports": (500, 9), "Decisions": (500, 8)},
                    "Weeks": [weeks_hdr], "Reports": [REPORTS_HEADER], "Decisions": [DECISIONS_HEADER]}

        sb = fresh_b()
        res = run_block(sb, rows_p)
        check("block delivered", res["delivered"], "2-rows;Reports!A22:I23;Weeks!K3")
        check("block Weeks cells", sb["Weeks"][2][10:12], ["ok", "2026-10-06T09:45:00+08:00"])
        check("block leaves the snapshot cells alone", sb["Weeks"][2][:10], [""] * 10)
        empty_p = os.path.join(tmpb, "empty.json")
        json.dump([], open(empty_p, "w"))
        res0 = run_block(fresh_b(), empty_p)
        check("block with no rows still commits", res0["delivered"], "0-rows;Reports(none);Weeks!K3")
        sb2 = fresh_b()
        try:
            run_block(sb2, rows_p, mangle=lambda v: v[:7] + [v[7].strip() + "!"] + v[8:])
            fails.append("a changed Reports cell was committed")
        except Refuse as e:
            check("block read-back mismatch caught", e.code, 6)
        check("block nothing committed after a failed check", len(sb2["Weeks"]), 1)
        sb3 = fresh_b()
        sb3["Weeks"][0] = WEEKS_HEADER     # the Phase 1 header: Phase 2 setup not run
        try:
            run_block(sb3, rows_p)
            fails.append("a block was written without the Phase 2 Weeks header")
        except Refuse as e:
            check("block refuses the old Weeks header", e.code, 4)
        wrong_p = os.path.join(tmpb, "wrong.json")
        json.dump([["2026-W40"] + [""] * 8], open(wrong_p, "w"))
        refuses("block row from another week", 3, blk_start, "Reports", "2026-W41", wrong_p, cfgb,
                "2026-10-06T09:40:00+08:00", os.path.join(tmpb, "runs"))
    finally:
        shutil.rmtree(tmpb, ignore_errors=True)

    # decisions rows (Phase 2)
    dr = decision_rows([{"content": "1.03 SEO 改雙週一篇", "owner": "Bicky", "due": "2026-10-15"},
                        {"content": "官網改版要不要外包", "owner": "", "due": ""},
                        {"content": "延到 4.10 一起做", "owner": "Ann", "due": "2026-10-20", "item": "4.10"}],
                       "2026-W41", "2026-10-08", "https://docs.example.com/x")
    check("decision with owner and date", dr[0][2], "決議")
    check("decision missing owner is open", dr[1][2], "待決")
    check("decision item from text", dr[0][6], "1.03")
    check("decision item given", dr[2][6], "4.10")
    check("decision no item", dr[1][6], "")
    check("decision row width", len(dr[0]), len(DECISIONS_HEADER))
    refuses("decision without content", 3, decision_rows, [{"owner": "x"}], "2026-W41", "2026-10-08", "")
    check("no decisions, no rows", decision_rows([], "2026-W41", "2026-10-08", ""), [])

    # diff (AC-1.3)
    def snap(week, at, items):
        return [[week, at, "2026H2"] + pad(i, 13) for i in items]

    def it(num, status, end="YYYY-MM-DD", note=""):
        return [num, "1.0 M", "1.1 S", "item " + num, "", "", "P1", "Ann", "", "YYYY-MM-DD", end, status, note]

    A_AT, B_AT = "2026-10-02T18:07:00+08:00", "2026-10-09T18:06:00+08:00"
    snap_a = snap("2026-W40", A_AT, [it("1.01", "未開始"), it("1.02", "進行中"), it("1.03", "未開始"),
                                    it("1.04", "未開始"), it("1.05", "未開始"), it("1.06", "進行中", note="abc"),
                                    it("1.10", "進行中")])
    snap_b = snap("2026-W41", B_AT, [it("1.01", "進行中"), it("1.02", "完成"), it("1.03", "未開始", end="2026-11-30"),
                                    it("1.05", "暫停"), it("1.06", "進行中", note="abc "), it("1.10", "進行中"),
                                    it("2.01", "未開始")])

    def upd(at, num, col, old, new):
        return ["2026-W41", at, "2026H2", num, "item " + num, col, old, new, "", "", "會議", "", "", ""]

    updates = [upd("2026-10-09T10:00:00+08:00", "1.01", "狀態", "未開始", "進行中"),   # logged
               upd("2026-10-01T10:00:00+08:00", "1.02", "狀態", "進行中", "完成"),     # before A: not this week
               upd("2026-10-08T09:00:00+08:00", "1.05", "狀態", "未開始", "進行中")]   # then hand-edited to 暫停
    d = diff_snapshots(snap_a, snap_b, updates)
    by = {(c["#"], c["column"]): c for c in d["changed"]}
    check("diff logged change", by[("1.01", "狀態")]["logged"], True)
    check("diff manual change", by[("1.02", "狀態")]["logged"], False)
    check("diff out-of-window log ignored", by[("1.02", "狀態")]["kind"], "status")
    check("diff placeholder → date is dated", by[("1.03", "結束")]["kind"], "dated")
    check("diff logged then hand-edited is manual", by[("1.05", "狀態")]["logged"], False)
    check("diff cosmetic whitespace", by[("1.06", "備註")]["cosmetic"], True)
    check("diff unchanged 1.10 absent", ("1.10", "狀態") in by, False)
    check("diff added", [x["#"] for x in d["added"]], ["2.01"])
    check("diff removed", [x["#"] for x in d["removed"]], ["1.04"])
    check("diff manual count", d["manual_edits"], 3)
    check("diff orphan log", [u[3] for u in d["orphan_log"]], ["1.05"])
    check("diff numeric order", [c["#"] for c in d["changed"]][:2], ["1.01", "1.02"])
    refuses("diff across cycles", 4, diff_snapshots, snap_a,
            [["2026-W41", B_AT, "2027H1"] + pad(it("1.01", "進行中"), 13)])
    refuses("diff newer first", 2, diff_snapshots, snap_b, snap_a)
    refuses("diff mixed runs", 3, snapshot_items, snap_a + [["2026-W40", "2026-10-03T09:00:00+08:00", "2026H2"] + pad(it("9.01", "x"), 13)])

    if fails:
        print("ledger.py selftest: %d FAILED" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("ledger.py selftest: all checks passed")
    return 0


def _write_cfg(tmp, tracker_id, ledger_id):
    p = os.path.join(tmp, "cfg-%s-%s.json" % (tracker_id, ledger_id))
    json.dump({"google_account": "owner@example.com",
               "sources": {"main_tracker": {"id": tracker_id, "tab": "T", "cycle": "C"},
                           "ledger": {"id": ledger_id, "epoch_week": "2026-W40"}}}, open(p, "w"))
    return p


# ── mutation check: each one-line breakage must turn the selftest red ────────
MUTATIONS = [
    # (name, [(old, new), ...]) — every pair is applied; each old text must occur exactly once
    ("truncation not detected", [
        ('raise Refuse(3, "read was truncated', 'pass  # raise Refuse(3, "read was truncated'),
        ("if len(rows) != n:", "if False:")]),
    ("USER_ENTERED instead of RAW", [
        ('"value_input_option": "RAW", "values": rows})]', '"value_input_option": "USER_ENTERED", "values": rows})]')]),
    ("category filter removed", [
        ("if CATEGORY_RE.match(num) and not name:", "if False and CATEGORY_RE.match(num) and not name:")]),
    ("slot off by one", [
        ("return 2 + SLOT * k, 1 + SLOT * (k + 1)", "return 3 + SLOT * k, 2 + SLOT * (k + 1)")]),
    ("already ignores status", [
        ('if row[0] != run["week"] or row[1] != "ok":', 'if row[0] != run["week"]:')]),
    ("padding removed", [
        ("by_row[a + i] = pad(cells, 13)", "by_row[a + i] = cells")]),
    ("recheck skipped", [
        ('if digest(again) != run["digest"]:', "if False:")]),
    ("read-back compare skipped", [
        ("if have != pad(want, 16):", "if False:")]),
    ("diff ignores the time window", [
        ("if t is not None and t_from < t <= t_to:", "if t is not None:")]),
    ("block read-back compare skipped", [
        ("        if have != want:\n            col = next(j for j in range(width)", "        if False:\n            col = next(j for j in range(width)")]),
    ("an open decision promoted", [
        ('"決議" if owner and due else "待決"', '"決議"')]),
    ("block accepts another week's rows", [
        ("        if pad(r, width)[0] != week:", "        if False:")]),
    ("diff logs on any new value", [
        ("and u[5] == column and u[7] == new:", "and u[5] == column:")]),
]


def mutate():
    import subprocess
    import tempfile
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    code, marker, rest = src.partition("\nMUTATIONS = [")   # never mutate the list itself
    tmpd = tempfile.mkdtemp(prefix="ledger-mutate-")
    ok = True

    def run(text):
        p = os.path.join(tmpd, "ledger_mut.py")
        open(p, "w", encoding="utf-8").write(text)
        return subprocess.run([sys.executable, p, "--selftest"], capture_output=True, text=True).returncode

    if run(src) != 0:
        print("mutate: the unmodified control copy fails its selftest")
        return 1
    for name, pairs in MUTATIONS:
        bad = [old for old, _ in pairs if code.count(old) != 1]
        if bad:
            print("mutate: %-32s SETUP ERROR (pattern not unique: %r)" % (name, bad[0][:40]))
            ok = False
            continue
        mutated = code
        for old, new in pairs:
            mutated = mutated.replace(old, new)
        rc = run(mutated + marker + rest)
        print("mutate: %-32s %s" % (name, "caught" if rc != 0 else "MISSED"))
        ok = ok and rc != 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
