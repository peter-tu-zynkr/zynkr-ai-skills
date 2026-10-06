#!/usr/bin/env python3
"""ledger_read.py — read the Weekly Ledger for the GM brief (SKB-062). Read-only, stdlib only.

The Ledger is the weekly project cycle's machine-owned Sheet (SKB-044, written only by
zynkr-ops-weekly). It keeps a fixed-row layout, so every range here is computed, never searched:
week k (counted from `sources.ledger.epoch_week`) owns `Weeks` row 2+k, `Snapshot` rows
2+100k..101+100k, `Reports` and `Decisions` rows 2+20k..21+20k, `Proposals` and `Updates` rows
2+40k..41+40k. The layout is defined by zynkr-ops-weekly's `ledger.py`; this script mirrors it and
`--selftest` pins the table in that skill's `references/ledger.md`.

    ledger_read.py plan  --epoch 2026-W40 --today 2026-10-12
        -> the brief's week, the week it looks back on (last week) and the one Weeks range to read
    ledger_read.py weeks --epoch E --today D --ledger ID <saved Weeks result>
        -> last week's beat health, approval state, the snapshot weeks to use as --prev and for
           STALLED, and every block range to read next (each <= 50 rows)
    ledger_read.py rows  --week W --items N --ledger ID <saved Snapshot page>...
        -> that week's snapshot as derive_state.py rows (JSON array on stdout)
    ledger_read.py block --kind decisions|proposals|reports|updates --week W --epoch E --ledger ID <saved result>
        -> the week's rows as dicts, plus counts (JSON)
    ledger_read.py --selftest

Every <saved ...> file is a read_sheet_values result saved verbatim. A result for another
spreadsheet or another range, a truncated read, or a Weeks row holding a different week is refused
(exit 3 or 4) rather than read around: a wrong row here would put another week's facts in the brief.
"""
import argparse
import ast
import json
import re
import sys
from datetime import date, timedelta

TRACKER_HEADER = ["#", "主類別", "子類別", "項目（正規化）", "重要", "緊急", "Priority",
                  "負責人", "協助者", "開始", "結束", "狀態", "備註"]
WEEKS_HEADER = ["week", "status", "snapshot_at", "cycle", "tracker_id", "items", "first_row",
                "last_row", "digest", "note", "reports", "reports_at", "decisions", "decisions_at",
                "proposals", "proposals_at", "applied", "applied_at"]                       # A–R
BLOCKS = {  # kind: (tab, rows per week, last column, header)
    "reports": ("Reports", 20, "I", ["week", "posted_at", "owner", "部門", "上週", "本週", "數字", "卡關", "format"]),
    "decisions": ("Decisions", 20, "H", ["week", "會議日期", "類型", "內容", "負責人", "期限", "關聯 #", "來源"]),
    "proposals": ("Proposals", 40, "O", ["week", "proposed_at", "n", "#", "項目", "欄位", "現值", "建議值", "原因",
                                         "證據", "來源", "信心", "決定", "決定_at", "結果"]),
    "updates": ("Updates", 40, "N", ["週", "時間", "cycle", "#", "項目", "欄位", "舊值", "新值", "原因", "證據",
                                     "來源", "提議", "核准", "proposal"]),
}
SNAPSHOT_SLOT = 100
PAGE = 50                                     # read_sheet_values shows at most 50 rows
STALLED_MIN_AGE_DAYS = 14                     # derived-state-rules.md
BEATS = [("snapshot", 1, 2), ("rollup", 10, 11), ("decisions", 12, 13), ("propose", 14, 15), ("apply", 16, 17)]

WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")
HEAD_RE = re.compile(r"^Successfully read (\d+) rows from range '(.*)' in spreadsheet (\S+) for \S+:$")
ROW_RE = re.compile(r"^Row\s+(\d+): (\[.*\])$")


class Refuse(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


# ── weeks ────────────────────────────────────────────────────────────────────
def monday(week):
    m = WEEK_RE.match(week or "")
    if not m:
        raise Refuse(2, "not an ISO week key: %r (expected like 2026-W40)" % week)
    try:
        return date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
    except ValueError:
        raise Refuse(2, "no such ISO week: %s" % week)


def week_of(d):
    y, w, _ = d.isocalendar()
    return "%d-W%02d" % (y, w)


def shift(week, n):
    return week_of(monday(week) + timedelta(days=7 * n))


def week_index(week, epoch):
    k = (monday(week) - monday(epoch)).days // 7
    if k < 0:
        raise Refuse(2, "week %s is before the Ledger's epoch week %s" % (week, epoch))
    return k


def weeks_row(week, epoch):
    return 2 + week_index(week, epoch)


def block_rows(kind, week, epoch):
    size = SNAPSHOT_SLOT if kind == "snapshot" else BLOCKS[kind][1]
    k = week_index(week, epoch)
    return 2 + size * k, 1 + size * (k + 1)


def pages(tab, first, last, last_col):
    out, r = [], first
    while r <= last:
        end = min(last, r + PAGE - 1)
        out.append("%s!A%d:%s%d" % (tab, r, last_col, end))
        r = end + 1
    return out


def parse_date(text):
    try:
        return date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


# ── reading a saved read_sheet_values result ─────────────────────────────────
def parse_values(text, sid, rng):
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
        raise Refuse(3, "read came from spreadsheet %s, expected the Ledger %s" % (got_sid, sid))
    if got_rng != rng:
        raise Refuse(3, "read covers %r, expected %r" % (got_rng, rng))
    rows = []
    for line in text.split("\n")[1:]:
        if line.startswith("... and ") and line.endswith(" more rows"):
            raise Refuse(3, "read was truncated at 50 rows (%s); read a smaller range" % line)
        mm = ROW_RE.match(line)
        if not mm:
            if rows:
                break
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


def pad(row, n):
    return list(row) + [""] * (n - len(row))


def range_of(text):
    m = HEAD_RE.match(text.split("\n", 1)[0])
    if m:
        return m.group(2)
    m = re.match(r"^No data found in range '(.*)'", text)
    if m:
        return m.group(1)
    raise Refuse(3, "not a read_sheet_values result: %r" % text[:120])


# ── plan ─────────────────────────────────────────────────────────────────────
def weeks_range(last_week, epoch):
    hi = weeks_row(last_week, epoch)
    lo = max(2, hi - PAGE + 1)
    return lo, hi, "Weeks!A%d:R%d" % (lo, hi)


def plan(epoch, today):
    this_week = week_of(today)
    last_week = shift(this_week, -1)
    lo, hi, rng = weeks_range(last_week, epoch)        # refuses a last week before the epoch
    return {"brief_week": this_week, "last_week": last_week, "weeks_range": rng,
            "call": "read_sheet_values(spreadsheet_id=<sources.ledger.id>, range_name=%r) -> save the result "
                    "verbatim, then run: ledger_read.py weeks --epoch %s --today %s --ledger <id> <file>"
                    % (rng, epoch, today.isoformat())}


# ── weeks: health + what to read next ───────────────────────────────────────
def snapshot_ok(row):
    return row[1] == "ok" and row[5].isdigit() and row[6].isdigit() and row[7].isdigit()


def weeks(epoch, today, sid, text):
    p = plan(epoch, today)
    last_week = p["last_week"]
    lo, hi, rng = weeks_range(last_week, epoch)
    rows = [pad(r, len(WEEKS_HEADER)) for r in parse_values(text, sid, rng)]
    by_week = {}
    for i, r in enumerate(rows):
        n = lo + i
        k = n - 2
        wk = shift(epoch, k)
        if r[0] and r[0] != wk:
            raise Refuse(4, "Weeks row %d holds %s, expected %s — was the Ledger's epoch changed?" % (n, r[0], wk))
        by_week[wk] = (n, r)
    if last_week not in by_week:
        row = [""] * len(WEEKS_HEADER)
        row_no = hi
    else:
        row_no, row = by_week[last_week]

    health = []
    for beat, sc, ac in BEATS:
        st = row[sc]
        health.append({"beat": beat, "status": st or "never recorded", "at": row[ac],
                       "cell": "Weeks!%s%d" % (chr(ord("A") + sc), row_no)})
    if row[14] == "ok" and row[16] == "ok":
        approval = "confirmed"
    elif row[14] == "ok":
        approval = "unconfirmed"          # recorded, not confirmed; an ask only when the week's
                                          # Proposals block holds >= 1 row (an empty week stamps O too)
    else:
        approval = "no proposals recorded"

    # --prev: the week before last (so CHANGED covers last week plus the weekend); else last week
    prev = None
    for cand in (shift(last_week, -1), last_week):
        if cand in by_week and snapshot_ok(by_week[cand][1]):
            prev = cand
            break
    # STALLED: the newest snapshot at least 14 days old
    stall = None
    for wk in sorted(by_week, key=monday, reverse=True):
        r = by_week[wk][1]
        at = parse_date(r[2])
        if snapshot_ok(r) and at and (today - at).days >= STALLED_MIN_AGE_DAYS:
            stall = wk
            break

    def snap_reads(wk):
        r = by_week[wk][1]
        first, last = int(r[6]), int(r[7])
        lo_b, hi_b = block_rows("snapshot", wk, epoch)
        if not (lo_b <= first <= last <= hi_b):
            raise Refuse(4, "%s's snapshot rows %d–%d fall outside its block %d–%d" % (wk, first, last, lo_b, hi_b))
        return {"week": wk, "items": int(r[5]), "snapshot_at": r[2], "ranges": pages("Snapshot", first, last, "P")}

    reads = {"prev": snap_reads(prev) if prev else None,
             "stall": snap_reads(stall) if stall else None}
    for kind, (tab, _size, col, _h) in BLOCKS.items():
        a, b = block_rows(kind, last_week, epoch)
        reads[kind] = {"week": last_week, "ranges": pages(tab, a, b, col)}
    return {"brief_week": p["brief_week"], "last_week": last_week, "weeks_row": row_no,
            "health": health, "approval": approval,
            "prev_note": None if prev == shift(last_week, -1) else
            ("no snapshot for %s; CHANGED is measured from %s" % (shift(last_week, -1), prev) if prev else
             "no snapshot for %s or %s; CHANGED is not measured" % (shift(last_week, -1), last_week)),
            "stalled_available": stall is not None, "reads": reads}


# ── rows: a snapshot week -> derive_state rows ───────────────────────────────
def rows(week, items, sid, texts):
    out = []
    for text in texts:
        rng = range_of(text)
        for r in parse_values(text, sid, rng):
            r = pad(r, 3 + len(TRACKER_HEADER))
            if r[0] != week:
                raise Refuse(4, "a row in %s belongs to %r, not %s" % (rng, r[0], week))
            out.append(dict(zip(TRACKER_HEADER, r[3:3 + len(TRACKER_HEADER)])))
    if len(out) != items:
        raise Refuse(3, "%s's Weeks row says %d items but the pages hold %d" % (week, items, len(out)))
    return out


# ── block: one week's rows of Reports / Decisions / Proposals / Updates ──────
def block(kind, week, sid, text, epoch):
    tab, _size, col, header = BLOCKS[kind]
    rng = range_of(text)
    if not rng.startswith(tab + "!"):
        raise Refuse(3, "this is a read of %s, not %s" % (rng, tab))
    a, b = block_rows(kind, week, epoch)
    if rng not in pages(tab, a, b, col):
        raise Refuse(3, "%s is not %s's %s block (%s)" % (rng, week, tab, ", ".join(pages(tab, a, b, col))))
    got = [dict(zip(header, pad(r, len(header)))) for r in parse_values(text, sid, rng)]
    key = header[0]
    mine = [r for r in got if r[key] == week]
    stray = [r[key] for r in got if r[key] and r[key] != week]
    if stray:
        raise Refuse(4, "%s holds rows for %s inside %s's block" % (rng, sorted(set(stray)), week))
    res = {"kind": kind, "week": week, "rows": mine, "count": len(mine)}
    if kind == "proposals":
        res["by_decision"] = {}
        for r in mine:
            d = r["決定"] or "未決定"
            res["by_decision"][d] = res["by_decision"].get(d, 0) + 1
    if kind == "decisions":
        res["open"] = [r for r in mine if r["類型"] == "待決"]
    if kind == "reports":
        res["blocked"] = [{"owner": r["owner"], "卡關": r["卡關"]} for r in mine if r["卡關"].strip()]
    return res


# ── cli ──────────────────────────────────────────────────────────────────────
def read(path):
    """A saved tool result: stripped, and unwrapped when it was saved as {"result": "..."}."""
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if text.startswith("{"):
        try:
            obj = json.loads(text)
        except ValueError:
            obj = None
        if isinstance(obj, dict) and isinstance(obj.get("result"), str):
            text = obj["result"].strip()
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["plan", "weeks", "rows", "block"])
    ap.add_argument("files", nargs="*")
    ap.add_argument("--epoch")
    ap.add_argument("--today")
    ap.add_argument("--ledger")
    ap.add_argument("--week")
    ap.add_argument("--items", type=int)
    ap.add_argument("--kind", choices=sorted(BLOCKS))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        today = date.fromisoformat(a.today) if a.today else date.today()
        if a.cmd == "plan":
            out = plan(a.epoch, today)
        elif a.cmd == "weeks":
            out = weeks(a.epoch, today, a.ledger, read(a.files[0]))
        elif a.cmd == "rows":
            out = rows(a.week, a.items, a.ledger, [read(f) for f in a.files])
        elif a.cmd == "block":
            out = block(a.kind, a.week, a.ledger, read(a.files[0]), a.epoch)
        else:
            ap.print_help()
            return 2
    except Refuse as e:
        print("REFUSED (%d): %s" % (e.code, e), file=sys.stderr)
        return e.code
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


# ── selftest ─────────────────────────────────────────────────────────────────
def _result(sid, rng, rows_):
    if not rows_:
        return "No data found in range '%s' in spreadsheet %s for x@y." % (rng, sid)
    lines = ["Successfully read %d rows from range '%s' in spreadsheet %s for x@y:" % (len(rows_), rng, sid)]
    lines += ["Row %2d: %s" % (i + 1, json.dumps(r, ensure_ascii=False)) for i, r in enumerate(rows_)]
    return "\n".join(lines)


def selftest():
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append("%s: got %r, want %r" % (name, got, want))

    def refuses(name, code, fn, *args):
        try:
            fn(*args)
            fails.append("%s: did not refuse" % name)
        except Refuse as e:
            if e.code != code:
                fails.append("%s: refused with %d, want %d" % (name, e.code, code))

    E = "2026-W40"
    # the layout table in zynkr-ops-weekly/references/ledger.md
    for wk, k, wrow, snap in (("2026-W40", 0, 2, (2, 101)), ("2026-W41", 1, 3, (102, 201)),
                              ("2026-W53", 13, 15, (1302, 1401)), ("2027-W01", 14, 16, (1402, 1501))):
        check("k " + wk, week_index(wk, E), k)
        check("Weeks row " + wk, weeks_row(wk, E), wrow)
        check("Snapshot block " + wk, block_rows("snapshot", wk, E), snap)
    check("Reports W41", block_rows("reports", "2026-W41", E), (22, 41))
    check("Proposals W41", block_rows("proposals", "2026-W41", E), (42, 81))
    check("Updates W40", block_rows("updates", "2026-W40", E), (2, 41))
    check("week across a year", shift("2027-W01", -1), "2026-W53")
    refuses("week before epoch", 2, week_index, "2026-W39", E)
    check("pages of 100", pages("Snapshot", 102, 201, "P"), ["Snapshot!A102:P151", "Snapshot!A152:P201"])

    p = plan(E, date(2026, 10, 12))
    check("plan brief week", p["brief_week"], "2026-W42")
    check("plan last week", p["last_week"], "2026-W41")
    check("plan Weeks range", p["weeks_range"], "Weeks!A2:R3")
    refuses("a brief in the epoch week has no last week", 2, plan, E, date(2026, 9, 30))

    SID = "LED"

    def wrow(week, snap_at, items, first, rep="", dec="", prop="", app=""):
        return [week, "ok" if snap_at else "", snap_at, "2026H2", "T", str(items) if snap_at else "",
                str(first) if snap_at else "", str(first + items - 1) if snap_at else "", "d", "layout v1",
                rep, "x" if rep else "", dec, "x" if dec else "", prop, "x" if prop else "", app, "x" if app else ""]

    # Monday 2026-10-19 (W43): W40, W41 snapshotted; W42 fully run but apply never confirmed
    rows_w = [wrow("2026-W40", "2026-10-02T18:31:01+08:00", 55, 2),
              wrow("2026-W41", "2026-10-09T18:20:00+08:00", 55, 102, "ok", "ok", "ok", "ok"),
              wrow("2026-W42", "2026-10-16T18:20:00+08:00", 56, 202, "ok", "ok", "ok", "")]
    t = _result(SID, "Weeks!A2:R4", rows_w)
    w = weeks(E, date(2026, 10, 19), SID, t)
    check("weeks last week", w["last_week"], "2026-W42")
    check("approval unconfirmed", w["approval"], "unconfirmed")
    check("health apply", [h["status"] for h in w["health"]], ["ok", "ok", "ok", "ok", "never recorded"])
    check("apply cell", w["health"][4]["cell"], "Weeks!Q4")
    check("prev = week before last", w["reads"]["prev"]["week"], "2026-W41")
    check("prev ranges", w["reads"]["prev"]["ranges"], ["Snapshot!A102:P151", "Snapshot!A152:P156"])
    check("stall = newest >= 14 days old", w["reads"]["stall"]["week"], "2026-W40")
    check("decisions range", w["reads"]["decisions"]["ranges"], ["Decisions!A42:H61"])
    check("proposals ranges", w["reads"]["proposals"]["ranges"], ["Proposals!A82:O121"])
    check("prev note empty", w["prev_note"], None)

    # the first brief after the Ledger began: only W40 exists → CHANGED from W40, no STALLED yet
    t2 = _result(SID, "Weeks!A2:R3", [wrow("2026-W40", "2026-10-02T18:31:01+08:00", 55, 2),
                                      ["", "", "", "", "", "", "", "", "", "", "ok", "x"]])
    w2 = weeks(E, date(2026, 10, 12), SID, t2)
    check("first brief: prev is the week before last", w2["reads"]["prev"]["week"], "2026-W40")
    check("first brief: stalled not available", w2["stalled_available"], False)
    check("first brief: snapshot never recorded", w2["health"][0]["status"], "never recorded")
    check("first brief: rollup ok", w2["health"][1]["status"], "ok")
    check("first brief: no proposals", w2["approval"], "no proposals recorded")

    refuses("another spreadsheet", 3, weeks, E, date(2026, 10, 19), "OTHER", t)
    refuses("another range", 3, weeks, E, date(2026, 10, 19), SID, _result(SID, "Weeks!A1:R4", rows_w))
    refuses("epoch drift", 4, weeks, E, date(2026, 10, 19), SID,
            _result(SID, "Weeks!A2:R4", [wrow("2026-W39", "x", 1, 2)] + rows_w[1:]))
    refuses("truncated", 3, parse_values, _result(SID, "Weeks!A2:R4", rows_w) + "\n... and 9 more rows", SID, "Weeks!A2:R4")
    bad = list(rows_w)
    bad[1] = wrow("2026-W41", "2026-10-09T18:20:00+08:00", 55, 2)
    refuses("snapshot rows outside the block", 4, weeks, E, date(2026, 10, 19), SID, _result(SID, "Weeks!A2:R4", bad))

    # rows
    def snap(week, n, status="進行中"):
        return [week, "t", "2026H2", "1.%02d" % n, "c", "s", "item %d" % n, "", "", "P0", "Peter Tu", "",
                "2026-09-01", "2026-10-31", status, ""]
    pages_ = [_result(SID, "Snapshot!A102:P151", [snap("2026-W41", i) for i in range(1, 51)]),
              _result(SID, "Snapshot!A152:P156", [snap("2026-W41", i) for i in range(51, 56)])]
    rr = rows("2026-W41", 55, SID, pages_)
    check("rows count", len(rr), 55)
    check("rows keys", rr[0]["項目（正規化）"], "item 1")
    check("rows status", rr[54]["狀態"], "進行中")
    refuses("rows count mismatch", 3, rows, "2026-W41", 56, SID, pages_)
    refuses("rows of another week", 4, rows, "2026-W42", 55, SID, pages_)

    # block
    dec = _result(SID, "Decisions!A42:H61", [["2026-W42", "10/15", "決議", "A", "Mark", "10/20", "1.08", "doc"],
                                            ["2026-W42", "10/15", "待決", "B", "", "", "", "doc"]])
    b = block("decisions", "2026-W42", SID, dec, E)
    check("decisions count", b["count"], 2)
    check("decisions open", [r["內容"] for r in b["open"]], ["B"])
    prop = _result(SID, "Proposals!A82:O121", [["2026-W42", "t", "1", "1.08", "x", "狀態", "進行中", "完成", "", "", "",
                                              "高", "核准", "t", "would-apply"],
                                             ["2026-W42", "t", "2", "2.02", "y", "結束", "", "2026-11-30", "", "", "",
                                              "中", "", "", ""]])
    bp = block("proposals", "2026-W42", SID, prop, E)
    check("proposals by decision", bp["by_decision"], {"核准": 1, "未決定": 1})
    refuses("block of another tab", 3, block, "reports", "2026-W42", SID, dec, E)
    refuses("another week's block range", 3, block, "decisions", "2026-W43", SID, dec, E)
    refuses("stray week in block", 4, block, "decisions", "2026-W43", SID,
            _result(SID, "Decisions!A62:H81", [["2026-W42", "", "決議", "x", "", "", "", ""]]), E)
    refuses("a partial block range", 3, block, "decisions", "2026-W42", SID,
            _result(SID, "Decisions!A42:H42", []), E)
    check("empty block", block("updates", "2026-W42", SID, _result(SID, "Updates!A82:N121", []), E)["count"], 0)

    # read(): a result saved inside its {"result": ...} wrapper, with surrounding whitespace
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp()
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n" + json.dumps({"result": t}) + "\n")
    check("wrapped result unwraps", weeks(E, date(2026, 10, 19), SID, read(tmp))["last_week"], "2026-W42")
    os.unlink(tmp)
    t3 = _result(SID, "Weeks!A2:R3", [["", "", "", "", "", "", "", "", "", "", "ok", "x"]])
    w3 = weeks(E, date(2026, 10, 12), SID, t3)
    check("no snapshot at all: prev note", w3["prev_note"], "no snapshot for 2026-W40 or 2026-W41; CHANGED is not measured")

    if fails:
        print("SELFTEST FAILED (%d):\n  %s" % (len(fails), "\n  ".join(fails)))
        return 1
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
