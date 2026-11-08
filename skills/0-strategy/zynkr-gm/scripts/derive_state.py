#!/usr/bin/env python3
"""derive_state.py — derive GM states (ENDS_SOON / OVERDUE / UNDATED / CHANGED / PROPOSE_DONE) from Main Tracker rows.

Input: JSON array of row dicts as read from the Main Tracker tab 「H2 專案項目」, keys exactly:
  "#","主類別","子類別","項目（正規化）","重要","緊急","Priority","負責人","協助者","開始","結束","狀態","備註"
(the alias "項目" is accepted for the item column). Category header rows (id like "1.0" or
empty 項目) are skipped.

Tracker status vocabulary (observed 2026-08-24): 未開始 / 進行中 / 放棄 / 完成 / 暫停. 完成 and 暫停
were added by the GM on 2026-08-24; 延遲 still does not exist and stays INFERRED (OVERDUE). A row
carrying any other value gets UNKNOWN_STATUS — surfaced, never silently mapped. This script never
writes back to the tracker.

Status classes:
  TERMINAL  放棄 · 完成  — no live schedule, no owner load, no date asks
  PAUSED    暫停        — no live schedule (so no deadline/date flags), but still owned and surfaced
  LIVE      未開始 · 進行中

Rules (today = --today):
  ENDS_SOON     結束 is a real date, today <= 結束 <= today+14, and 狀態 is LIVE
  OVERDUE       (狀態 == 進行中 and 結束 < today) OR (狀態 == 未開始 and 開始 < today)
  UNDATED       Priority in {P0,P1}, 狀態 is LIVE, and 開始 or 結束 is blank / a `YYYY-MM-DD` placeholder
  CHANGED       any of 狀態/開始/結束/負責人 differs from the --prev snapshot (new rows count as CHANGED)
  PROPOSE_DONE  狀態 == 進行中 and 備註 says the whole item is done: 完成|結案|上線|shipped|done
                preceded by 已/已經/already or opening a segment (「完成 2026-09-21」); not 「快完成」,
                「WBS 10/12 完成」, 「完成度」 or a future date (「上線 11/20」); and before 已 the clause
                names nothing, 全部, or the item itself (「drip 已上線」), never a part (「銷售頁已上線」)
  DONE          狀態 == 完成 (terminal; excluded from load and from every deadline/date flag)
  PAUSED        狀態 == 暫停 (no schedule; check the weekly log — a "paused" row that is actually
                running is a real SOR divergence and belongs in the brief)
  UNKNOWN_STATUS 狀態 outside the vocabulary above
Placeholder dates ("YYYY-MM-DD", "MM-DD", "TBD", blank) are treated as undated.

Output (--json): {today, rows:[{id,item,priority,owner,status,start,end,note,done_clause,states,evidence}],
                  summary:{...counts + id lists}, by_owner:{owner:{p0,p1,undated,overdue,ends_soon}}}
Default output is a compact text report of the same.

Python 3 stdlib only.
"""
import argparse
import datetime as dt
import json
import re
import sys

ITEM_KEYS = ("項目（正規化）", "項目(正規化)", "項目")
STATUS_KEY, START_KEY, END_KEY, OWNER_KEY, PRIO_KEY, NOTE_KEY, ID_KEY = "狀態", "開始", "結束", "負責人", "Priority", "備註", "#"
CHANGE_FIELDS = (STATUS_KEY, START_KEY, END_KEY, OWNER_KEY)
DONE_WORDS = re.compile(r"完成|結案|上線|(?<![A-Za-z])(?:shipped|done)(?![A-Za-z])", re.IGNORECASE)
# A done-word counts only when the note says the WHOLE item is finished: 「已上線」「已經完成」, or the word
# opens a segment (「完成 2026-09-21」「｜完成」「4. 結案」). Mid-sentence hits are progress notes about a
# step — 「快完成」, 「WBS 10/12 完成」, 「銷售頁 11/2 上線」 — and were false PROPOSE_DONE flags (recap W44).
DONE_ALREADY = re.compile(r"(?:已經|已经|已|already)\s*$", re.IGNORECASE)
DONE_SEGMENT_START = re.compile(r"(?:^|[｜|：:；;。\n]|(?:^|[｜|：:；;。\n])\s*(?:\d+[.、)）]|[-•*]))\s*$")
DONE_MEASURE_AFTER = re.compile(r"^(?:度|率|前|後|后|日|時間|时间|目標|目标)")
DONE_DATE_AFTER = re.compile(r"^\s*[:：]?\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}/\d{1,2})")
# 「X 已上線」 counts only when X is the item itself: the clause before 已 names nothing (「已經完成」), says
# all of it in whole-item words (「全部已完成」「整個專案已完成」「狀態：完成」), or names the item, an alias in its
# parentheses, or at least half of its name, with such words or without (「drip 已上線」「Drip 全部已上線」 on
# 電子報 Drip). A clause that names something else is a step of the item: 「一頁式銷售頁已上線」 on a course,
# 「MCP server 9/27 已上線」 on a platform. Both were flagged for the recap of 9 Nov (SKB-118). When nothing but a
# date stands between a colon and the done-word, X is the label before the colon: 「銷售頁：完成」「銷售頁：已上線」.
# After ｜ a done-word opens a new statement, as the tracker marks a finished item: 「KPI list ｜ 完成 2026-09-21」.
# A separator inside parentheses, and a clock time's colon (14:00), split nothing.
DONE_CLAUSE_SEP = re.compile(r"[｜|；;。，,、\n]|(?<!\d)[:：]|[:：](?!\d)")
DONE_LABEL_SEP = "：:"
DONE_QUOTE_END = re.compile(r"[｜|；;。，,、\n]")
DONE_WHOLE = re.compile(r"全部|全案|本案|此案|專案|本專案|整個|整體|都|狀態|進度|目前|現況|備註|all|everything|status|progress",
                        re.IGNORECASE)
DONE_PARENS = re.compile(r"（[^）]*）|\([^)]*\)")
DONE_NOISE = re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}/\d{1,2}|\d{1,2}[:：]\d{2}|\d+[.、)）](?!\d)|[-•*]|\s+")
STATUS_NOT_STARTED, STATUS_ACTIVE, STATUS_DROPPED, STATUS_DONE, STATUS_PAUSED = "未開始", "進行中", "放棄", "完成", "暫停"
KNOWN_STATUSES = frozenset({STATUS_NOT_STARTED, STATUS_ACTIVE, STATUS_DROPPED, STATUS_DONE, STATUS_PAUSED})
TERMINAL_STATUSES = frozenset({STATUS_DROPPED, STATUS_DONE})      # no owner load, no flags
NO_SCHEDULE_STATUSES = TERMINAL_STATUSES | frozenset({STATUS_PAUSED})  # no deadline / date flags
HEADER_ID = re.compile(r"^\d+\.0$")
OWNER_SPLIT = re.compile(r"[+＋/、,，&]|\s+and\s+|\s+&\s+")
ENDS_SOON_DAYS = 14


def norm(v):
    return "" if v is None else str(v).strip()


def get(row, *keys):
    for k in keys:
        if k in row:
            return norm(row[k])
    # tolerate keys with stray whitespace
    stripped = {norm(k): v for k, v in row.items()}
    for k in keys:
        if k in stripped:
            return norm(stripped[k])
    return ""


def parse_date(text, today):
    """Return (date|None, kind) where kind ∈ {'date','placeholder','blank'}."""
    s = norm(text)
    if not s:
        return None, "blank"
    if re.search(r"[YMDymd]{2}", s) or s.upper() in ("TBD", "TBC", "N/A", "-", "—", "待定"):
        return None, "placeholder"
    s2 = s.replace("/", "-").replace(".", "-")
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s2)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))), "date"
        except ValueError:
            return None, "placeholder"
    m = re.match(r"^(\d{1,2})-(\d{1,2})$", s2)  # MM-DD → assume today's year
    if m:
        try:
            return dt.date(today.year, int(m.group(1)), int(m.group(2))), "date"
        except ValueError:
            return None, "placeholder"
    return None, "placeholder"


def squash(text):
    return DONE_NOISE.sub("", text).lower()


def masked(text):
    """The text with each parenthesized span blanked, same length: a separator inside one splits nothing."""
    return DONE_PARENS.sub(lambda m: " " * len(m.group(0)), text)


def clause_start(note, upto):
    """Where the clause that runs up to `upto` begins: just after the last separator before it."""
    return max((s.end() for s in DONE_CLAUSE_SEP.finditer(masked(note), 0, upto)), default=0)


def names_item(text, names):
    """The text is the item: its name, an alias in its parentheses, or at least half of its name."""
    return any(text in n and 2 * len(text) >= len(n) for n in names)


def about_item(clause, item):
    """Whether the clause a done-word is about names the whole item: it names nothing, says all of it in
    whole-item words alone (DONE_WHOLE: 「全部都」「整個專案」), or names the item (names_item), with such
    words or without (「線上課 全部」). Without an item to compare, none or a blank 項目, every clause is."""
    item = item or ""
    subject = squash(DONE_PARENS.sub("", clause))
    names = [n for n in [squash(DONE_PARENS.sub("", item))] + [squash(p[1:-1]) for p in DONE_PARENS.findall(item)] if n]
    if not names or not subject or names_item(subject, names):
        return True
    rest = DONE_WHOLE.sub("", subject)
    return not rest or names_item(rest, names)


def quote(note, lo, end):
    """The clause a done-word stands in, from `lo` to the end of its clause, as the recap quotes it."""
    nxt = DONE_QUOTE_END.search(masked(note), end)
    text = " ".join(note[lo:nxt.start() if nxt else len(note)].split())
    return text if len(text) <= 40 else text[:39] + "…"


def done_match(note, today, item=None):
    """(the done-word, the clause it stands in) when the note says the whole item is finished, else None
    (see DONE_ALREADY / DONE_SEGMENT_START / DONE_WHOLE)."""
    for m in DONE_WORDS.finditer(note):
        before, after = note[:m.start()], note[m.end():]
        if DONE_MEASURE_AFTER.match(after):            # 完成度 · 完成率 · 上線日 · 上線前 — a measure, not a fact
            continue
        already = DONE_ALREADY.search(before)
        seg = None if already else DONE_SEGMENT_START.search(before)
        if already:
            lo = clause_start(note, already.start())
            subject = note[lo:already.start()]
            if lo and note[lo - 1] in DONE_LABEL_SEP and not squash(DONE_PARENS.sub("", subject)):
                colon = lo - 1                          # 「銷售頁：已上線」: the label is what is done
                lo = clause_start(note, colon)
                subject = note[lo:colon]
        elif seg:
            sep = before[seg.start()] if seg.start() < len(before) else ""
            if sep and sep in DONE_LABEL_SEP:           # 「銷售頁：完成」: the label is what is done
                lo = clause_start(note, seg.start())
                subject = note[lo:seg.start()]
            else:                                       # 「完成 2026-09-21」「1. x\n2. 結案」: a new statement
                lo, subject = clause_start(note, m.start()), ""
        else:
            continue
        if not about_item(subject, item):
            continue                                    # 「銷售頁已上線」 — a step of the item
        d = DONE_DATE_AFTER.match(after)
        if d and (parse_date(d.group(1), today)[0] or today) > today:   # 「上線 11/20」 is a plan
            continue
        return m.group(0), quote(note, lo, m.end())
    return None


def done_word(note, today, item=None):
    """The done-word that says the whole item is finished, or None (see done_match)."""
    found = done_match(note, today, item)
    return found[0] if found else None


def is_header(row):
    rid = get(row, ID_KEY)
    item = get(row, *ITEM_KEYS)
    return (not item) or bool(HEADER_ID.match(rid))


def split_owners(owner):
    parts = [p.strip() for p in OWNER_SPLIT.split(owner) if p and p.strip()]
    return parts or (["(unassigned)"] if not owner else [owner])


def index_rows(rows):
    return {get(r, ID_KEY): r for r in rows if not is_header(r) and get(r, ID_KEY)}


def derive(rows, today, prev_rows=None):
    prev = index_rows(prev_rows) if prev_rows else {}
    out = []
    for r in rows:
        if is_header(r):
            continue
        rid = get(r, ID_KEY)
        item = get(r, *ITEM_KEYS)
        prio = get(r, PRIO_KEY).upper()
        owner = get(r, OWNER_KEY)
        status = get(r, STATUS_KEY)
        start_raw, end_raw, note = get(r, START_KEY), get(r, END_KEY), get(r, NOTE_KEY)
        start, start_kind = parse_date(start_raw, today)
        end, end_kind = parse_date(end_raw, today)
        states, evidence = [], []

        if end and status not in NO_SCHEDULE_STATUSES and 0 <= (end - today).days <= ENDS_SOON_DAYS:
            states.append("ENDS_SOON")
            evidence.append(f"結束 {end.isoformat()} in {(end - today).days}d")
        if status == "進行中" and end and end < today:
            states.append("OVERDUE")
            evidence.append(f"狀態 進行中 but 結束 {end.isoformat()} < today ({(today - end).days}d)")
        elif status == "未開始" and start and start < today:
            states.append("OVERDUE")
            evidence.append(f"狀態 未開始 but 開始 {start.isoformat()} < today ({(today - start).days}d)")
        if prio in ("P0", "P1") and status not in NO_SCHEDULE_STATUSES and (start is None or end is None):
            states.append("UNDATED")
            missing = []
            if start is None:
                missing.append(f"開始 {start_kind}" + (f" '{start_raw}'" if start_raw else ""))
            if end is None:
                missing.append(f"結束 {end_kind}" + (f" '{end_raw}'" if end_raw else ""))
            evidence.append(f"{prio} without dates: " + "; ".join(missing))
        if prev:
            p = prev.get(rid)
            if p is None:
                states.append("CHANGED")
                evidence.append("not in prev snapshot (new row)")
            else:
                diffs = []
                for f in CHANGE_FIELDS:
                    b, a = get(p, f), get(r, f)
                    if b != a:
                        diffs.append(f"{f}: {b or '∅'} → {a or '∅'}")
                if diffs:
                    states.append("CHANGED")
                    evidence.extend(diffs)
        done = done_match(note, today, item) if status == "進行中" and note else None
        if done:
            states.append("PROPOSE_DONE")
            evidence.append(f"備註 matches done-word: {done[0]!r} in 「{done[1]}」 (status still 進行中)")
        if status == STATUS_DONE:
            states.append("DONE")
            evidence.append(f"狀態 {STATUS_DONE} — terminal; dropped from owner load and from deadline/date flags")
        if status == STATUS_PAUSED:
            states.append("PAUSED")
            evidence.append(f"狀態 {STATUS_PAUSED} — no live schedule; confirm against the weekly log before trusting it")
        if status and status not in KNOWN_STATUSES:
            states.append("UNKNOWN_STATUS")
            evidence.append(f"狀態 {status!r} is outside the vocabulary {sorted(KNOWN_STATUSES)} — not mapped")

        out.append({
            "id": rid, "item": item, "priority": prio, "owner": owner, "helper": get(r, "協助者"),
            "status": status, "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "start_raw": start_raw, "end_raw": end_raw, "note": note,
            "done_clause": done[1] if done else "",
            "states": states, "evidence": evidence,
        })
    return out


def summarise(derived, prev_given):
    by_ps, by_state = {}, {}
    lists = {"p0_undated": [], "p1_undated": [], "p0_overdue": [], "overdue": [], "ends_soon": [],
             "propose_done": [], "changed": [], "dropped": [], "done": [], "paused": [],
             "unknown_status": []}
    by_owner = {}
    for d in derived:
        by_ps.setdefault(d["priority"] or "?", {}).setdefault(d["status"] or "?", 0)
        by_ps[d["priority"] or "?"][d["status"] or "?"] += 1
        for s in d["states"]:
            by_state[s] = by_state.get(s, 0) + 1
        if d["status"] == STATUS_DROPPED:
            lists["dropped"].append(d["id"])
        if d["status"] == STATUS_DONE:
            lists["done"].append(d["id"])
        if d["status"] == STATUS_PAUSED:
            lists["paused"].append(d["id"])
        if "UNKNOWN_STATUS" in d["states"]:
            lists["unknown_status"].append(d["id"])
        if "UNDATED" in d["states"]:
            lists["p0_undated" if d["priority"] == "P0" else "p1_undated"].append(d["id"])
        if "OVERDUE" in d["states"]:
            lists["overdue"].append(d["id"])
            if d["priority"] == "P0":
                lists["p0_overdue"].append(d["id"])
        if "ENDS_SOON" in d["states"]:
            lists["ends_soon"].append(d["id"])
        if "PROPOSE_DONE" in d["states"]:
            lists["propose_done"].append(d["id"])
        if "CHANGED" in d["states"]:
            lists["changed"].append(d["id"])
        if d["status"] in TERMINAL_STATUSES:
            continue
        for o in split_owners(d["owner"]):
            slot = by_owner.setdefault(o, {"p0": [], "p1": [], "undated": [], "overdue": [], "ends_soon": []})
            if d["priority"] == "P0":
                slot["p0"].append(d["id"])
            elif d["priority"] == "P1":
                slot["p1"].append(d["id"])
            if "UNDATED" in d["states"]:
                slot["undated"].append(d["id"])
            if "OVERDUE" in d["states"]:
                slot["overdue"].append(d["id"])
            if "ENDS_SOON" in d["states"]:
                slot["ends_soon"].append(d["id"])
    summary = {"rows": len(derived), "counts_by_priority_status": by_ps, "counts_by_state": by_state,
               "prev_snapshot_given": prev_given, **lists}
    return summary, by_owner


def render_text(result):
    s = result["summary"]
    lines = [f"today={result['today']}  rows={s['rows']}  prev={'yes' if s['prev_snapshot_given'] else 'no'}",
             "counts by priority×status: " + json.dumps(s["counts_by_priority_status"], ensure_ascii=False),
             "counts by state: " + json.dumps(s["counts_by_state"], ensure_ascii=False)]
    for k in ("p0_undated", "p1_undated", "p0_overdue", "overdue", "ends_soon", "propose_done", "changed",
              "dropped", "done", "paused", "unknown_status"):
        lines.append(f"{k}: {', '.join(s[k]) or '-'}")
    lines.append("")
    for d in result["rows"]:
        if not d["states"]:
            continue
        lines.append(f"{d['id']} [{d['priority']}] {d['item']} · {d['owner']} · {d['status']} · {','.join(d['states'])}")
        for e in d["evidence"]:
            lines.append(f"    - {e}")
    lines.append("")
    lines.append("by owner:")
    for o, v in result["by_owner"].items():
        lines.append(f"  {o}: p0={v['p0']} p1={v['p1']} undated={v['undated']} overdue={v['overdue']} ends_soon={v['ends_soon']}")
    return "\n".join(lines)


def run(rows, today, prev_rows=None):
    derived = derive(rows, today, prev_rows)
    summary, by_owner = summarise(derived, prev_rows is not None)
    return {"today": today.isoformat(), "rows": derived, "summary": summary, "by_owner": by_owner}


def _row(i, cat, item, prio, owner, start, end, status, note=""):
    return {"#": i, "主類別": cat, "子類別": "", "項目（正規化）": item, "重要": "", "緊急": "", "Priority": prio,
            "負責人": owner, "協助者": "", "開始": start, "結束": end, "狀態": status, "備註": note}


SAMPLE_TODAY = dt.date(2026, 8, 17)
SAMPLE_ROWS = [
    _row("1.0", "1.0 Marketing", "", "", "", "", "", "", ""),                                   # header → skipped
    _row("1.03", "1.0", "SEO 文章", "P1", "Peter", "2026-07-01", "YYYY-MM-DD", "未開始"),           # OVERDUE (start<today) + UNDATED
    _row("1.08", "1.0", "電子報 Drip", "P0", "Alex", "2026-08-01", "2026-09-30", "進行中", "drip 已上線"),  # PROPOSE_DONE
    _row("2.01", "2.0", "業務流程結構化", "P0", "Peter", "2026-09-01", "2026-10-31", "未開始"),           # nothing
    _row("2.03", "2.0", "業務分潤系統", "P0", "Alex", "YYYY-MM-DD", "YYYY-MM-DD", "未開始"),           # UNDATED
    _row("3.05", "3.0", "Metrics 儀表", "P2", "Bea", "", "", "放棄"),                                # dropped
    _row("4.01", "4.0", "企業 AI 診斷", "P0", "Peter", "2026-08-03", "2026-08-28", "進行中"),           # ENDS_SOON (11d)
    _row("4.05", "4.0", "陪跑課", "P0", "Peter+Cleo", "2026-07-15", "2026-08-10", "進行中"),          # OVERDUE (end<today)
    _row("7.01", "7.0", "公司 KPI 制度", "P0", "Peter/Bea", "2026-08-31", "2026-08-31", "未開始"),      # ENDS_SOON (14d), two owners
    # --- vocab added 2026-08-24: 完成 / 暫停, plus a P0 放棄 (the P2 放棄 above never caught the leak) ---
    _row("4.02", "4.0", "企業 AI 導入", "P0", "Peter", "2026-08-03", "2026-08-28", "完成"),              # DONE: no ENDS_SOON, no load
    _row("4.07", "4.0", "Vibe Coding", "P0", "Cleo", "YYYY-MM-DD", "YYYY-MM-DD", "暫停"),             # PAUSED: no UNDATED ask
    _row("3.02", "3.0", "增加講師 — 內部", "P0", "Cleo", "YYYY-MM-DD", "YYYY-MM-DD", "放棄"),           # P0 放棄: must NOT leak into p0_undated
    _row("9.99", "9.0", "未知狀態列", "P2", "Alex", "", "", "審核中"),                                   # UNKNOWN_STATUS
]
SAMPLE_PREV = [dict(r) for r in SAMPLE_ROWS]
SAMPLE_PREV[2]["狀態"] = "未開始"          # 1.08 status changed
SAMPLE_PREV[7]["負責人"] = "Peter"          # 4.05 owner changed
SAMPLE_PREV = [r for r in SAMPLE_PREV if r["#"] != "7.01"]  # 7.01 is new


def selftest():
    res = run(SAMPLE_ROWS, SAMPLE_TODAY, SAMPLE_PREV)
    by_id = {r["id"]: r for r in res["rows"]}
    assert "1.0" not in by_id and len(by_id) == 12, list(by_id)
    assert set(by_id["1.03"]["states"]) == {"OVERDUE", "UNDATED"}, by_id["1.03"]
    assert by_id["1.08"]["states"] == ["CHANGED", "PROPOSE_DONE"], by_id["1.08"]
    assert by_id["2.01"]["states"] == [], by_id["2.01"]
    assert by_id["2.03"]["states"] == ["UNDATED"], by_id["2.03"]
    assert by_id["3.05"]["states"] == [], by_id["3.05"]
    assert by_id["4.01"]["states"] == ["ENDS_SOON"] and "in 11d" in by_id["4.01"]["evidence"][0], by_id["4.01"]
    assert set(by_id["4.05"]["states"]) == {"OVERDUE", "CHANGED"}, by_id["4.05"]
    assert set(by_id["7.01"]["states"]) == {"ENDS_SOON", "CHANGED"}, by_id["7.01"]
    s = res["summary"]
    assert s["p0_undated"] == ["2.03"] and s["p1_undated"] == ["1.03"], s
    assert s["overdue"] == ["1.03", "4.05"] and s["p0_overdue"] == ["4.05"], s
    assert s["ends_soon"] == ["4.01", "7.01"] and s["propose_done"] == ["1.08"], s
    assert s["changed"] == ["1.08", "4.05", "7.01"] and s["dropped"] == ["3.05", "3.02"], s
    assert s["counts_by_priority_status"]["P0"] == {"進行中": 3, "未開始": 3, "完成": 1, "暫停": 1, "放棄": 1}, \
        s["counts_by_priority_status"]
    # --- vocab 2026-08-24: 完成 is terminal, 暫停 has no schedule, 放棄 leaks nothing ---
    assert by_id["4.02"]["states"] == ["DONE"], by_id["4.02"]              # NOT ENDS_SOON despite 結束 in 11d
    assert by_id["4.07"]["states"] == ["PAUSED"], by_id["4.07"]            # NOT UNDATED
    assert by_id["3.02"]["states"] == [], by_id["3.02"]                    # P0 放棄 → no flags at all
    assert by_id["9.99"]["states"] == ["UNKNOWN_STATUS"], by_id["9.99"]
    assert s["done"] == ["4.02"] and s["paused"] == ["4.07"] and s["unknown_status"] == ["9.99"], s
    assert "4.02" not in s["ends_soon"] and "3.02" not in s["p0_undated"], s
    bo = res["by_owner"]
    assert "Bea" in bo and bo["Bea"]["p0"] == ["7.01"], bo   # split on '/', 放棄 row excluded
    assert bo["Cleo"]["overdue"] == ["4.05"], bo
    assert bo["Cleo"]["p0"] == ["4.05", "4.07"], bo["Cleo"]   # 暫停 still owned; 放棄 3.02 excluded
    assert "4.02" not in bo["Peter"]["p0"], bo["Peter"]          # 完成 drops out of GM load
    assert bo["Peter"]["p0"] == ["2.01", "4.01", "4.05", "7.01"], bo["Peter"]
    assert bo["Alex"]["undated"] == ["2.03"], bo["Alex"]
    # without prev → no CHANGED anywhere
    res2 = run(SAMPLE_ROWS, SAMPLE_TODAY)
    assert not any("CHANGED" in r["states"] for r in res2["rows"])
    # date parsing edge cases
    assert parse_date("YYYY-MM-DD", SAMPLE_TODAY) == (None, "placeholder")
    assert parse_date("2026/8/5", SAMPLE_TODAY)[0] == dt.date(2026, 8, 5)
    assert parse_date("08-28", SAMPLE_TODAY)[0] == dt.date(2026, 8, 28)
    assert parse_date("", SAMPLE_TODAY) == (None, "blank")
    # done-word must say the WHOLE item is finished (W44 recap flagged 「快完成」 and a WBS milestone)
    t = SAMPLE_TODAY
    for note, want in (("drip 已上線", "上線"), ("完成 2026-08-10｜名單：x", "完成"), ("備註｜完成", "完成"),
                       ("1. 規劃稿\n2. 結案", "結案"), ("已經完成，等驗收", "完成"), ("Done", "Done"),
                       ("already shipped", "shipped"), ("1. x\n4. 10-19 回信：快完成。名單已於 9 月匯入", None),
                       ("章程 8/8、WBS 8/12 完成；銷售頁 9/2 上線", None), ("尚未完成", None), ("還沒上線", None),
                       ("完成度 80%", None), ("上線日 8/20", None), ("上線 9/20", None), ("完成 8/10", "完成"),
                       ("abandoned", None), ("not done yet", None), ("", None)):
        assert done_word(note, t) == want, (note, done_word(note, t), want)
    # ... and before 已 the note names nothing, all of it, or the item itself: never a part (recap 9 Nov)
    for note, item, want in (("drip 已上線", "電子報 Drip", "上線"), ("drip（第二版）已上線", "電子報 Drip", "上線"),
                             ("控制台已上線", "知識平台（控制台）", "上線"), ("全部已完成", "線上課", "完成"),
                             ("11/3 已上線", "線上課", "上線"), ("完成 2026-08-10｜名單：x", "線上課", "完成"),
                             ("2026-11-03（A/B 1:1）：一頁式銷售頁已上線、見證已放上", "線上課", None),
                             ("搜尋 API（X-010）9/27 已上線；索引改善中", "知識平台（控制台）", None),
                             ("MCP server already shipped", "Knowledge platform", None),
                             # code review of #131: a label before a colon is the subject, while ｜ starts a new
                             # statement (the tracker's 「…｜完成 <date>」); a clock time and a colon in parentheses
                             # split nothing; and one word of the name is a part of it
                             ("銷售頁：完成", "線上課", None), ("KPI list ｜ 完成 2026-08-01", "KPI", "完成"),
                             ("主要用於公司內部營運｜完成 2026-08-01", "使用 Zynkr", "完成"),
                             ("線上課：完成", "線上課", "完成"), ("狀態：完成", "線上課", "完成"), ("11/3｜完成", "線上課", "完成"),
                             ("11/3 14:00 已上線", "線上課", "上線"), ("drip（v2: final）已上線", "電子報 Drip", "上線"),
                             ("頁已上線", "線上課程銷售頁", None), ("廣告已上線", "線上課程銷售頁與廣告", None),
                             # round 2: a label before 「：已」 too; whole-item words together, or beside the
                             # item's name; and a blank 項目 compares nothing
                             ("銷售頁：已上線", "線上課", None), ("銷售頁:已完成", "線上課", None),
                             ("銷售頁：11/3 已上線", "線上課", None), ("狀態：銷售頁已上線", "線上課", None),
                             ("線上課：已完成", "線上課", "完成"), ("狀態：已完成", "線上課", "完成"),
                             ("全部都已完成", "線上課", "完成"), ("整個專案已完成", "線上課", "完成"),
                             ("目前都已上線", "線上課", "上線"), ("線上課 全部已完成", "線上課", "完成"),
                             ("Drip 全部已上線", "電子報 Drip", "上線"), ("銷售頁全部已上線", "線上課", None),
                             ("銷售頁已上線", "", "上線")):
        assert done_word(note, t, item) == want, (note, item, done_word(note, t, item), want)
    assert done_match("線上課：完成", t, "線上課") == ("完成", "線上課：完成")
    assert done_match("11/3 14:00 已上線", t, "線上課") == ("上線", "11/3 14:00 已上線")
    assert done_match("線上課：已完成", t, "線上課") == ("完成", "線上課：已完成")
    assert done_match("章程 8/8｜drip 已上線，等驗收", t, "電子報 Drip") == ("上線", "drip 已上線")
    step = derive([_row("9.01", "9.0", "線上課", "P1", "Ann", "2026-08-01", "2026-12-30", "進行中", "銷售頁已上線")], t)[0]
    assert "PROPOSE_DONE" not in step["states"] and step["done_clause"] == "", step
    assert by_id["1.08"]["done_clause"] == "drip 已上線" and "「drip 已上線」" in by_id["1.08"]["evidence"][-1], by_id["1.08"]
    render_text(res)
    print("derive_state selftest OK")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rows", nargs="?", help="rows.json — JSON array of tracker row dicts (current snapshot)")
    ap.add_argument("--today", help="YYYY-MM-DD (default: system date)")
    ap.add_argument("--prev", help="prev_rows.json — earlier snapshot for CHANGED detection")
    ap.add_argument("--json", action="store_true", help="emit full JSON")
    ap.add_argument("--selftest", action="store_true", help="run embedded sample and exit 0/1")
    args = ap.parse_args(argv)
    if args.selftest:
        try:
            return selftest()
        except AssertionError as e:
            print(f"SELFTEST FAILED: {e!r}", file=sys.stderr)
            return 1
    if not args.rows:
        ap.error("rows.json is required (or use --selftest)")
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    with open(args.rows, encoding="utf-8") as fh:
        rows = json.load(fh)
    prev = None
    if args.prev:
        with open(args.prev, encoding="utf-8") as fh:
            prev = json.load(fh)
    if not isinstance(rows, list):
        print("rows.json must be a JSON array of objects", file=sys.stderr)
        return 1
    res = run(rows, today, prev)
    if args.json:
        json.dump(res, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print(render_text(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
