#!/usr/bin/env python3
"""open_items.py — the team's open bullets in one week section of the weekly Doc (SKB-151).

WHY THIS EXISTS
    A bullet leaves next week's section only when a Done/Drop chip closes it (tidy step 7, SKB-039),
    and nobody sets the chips: a 「· 還沒收掉的 —」 list of twenty items, the oldest from WB 8/24, none
    chipped. The loop already knows much of what is finished (the harvest's 完成 lines on Wednesday,
    the meeting on Thursday), but it had no list of what is OPEN in the Doc to hold that against.
    This is that list, and each bullet's id is what the three beats pass between them:

        sections (Wed)   reconcile: a 完成 harvest line ↔ an open bullet → 待討論「會後收掉」
        minutes  (Thu)   the meeting confirms, objects, or closes a bullet itself → closures.json
        tidy     (Thu)   --closures: the bullet leaves next week's section, under SKB-039's gates

WHAT COUNTS AS AN OPEN BULLET
    A `*` bullet (any depth) or a typed one-item `·` line (DOT_ITEM_RE) of the team's, under a heading,
    that no chip or typed word closes. Never: a line of an auto block (walk_block's machine lines, and
    everything a 會議紀錄 or 議程 block holds up to the next heading), a heading, a line above the
    section's first heading, a Metrics template line. It writes nothing and reads only the files given.

THE ID
    `b` + a hash of the heading line and the bullet's text, both as the export prints them, spaces
    dropped. The scaffold copies the section verbatim, so the same bullet has the same id in next
    week's copy; an edited bullet gets a new id, and evidence about the old wording never reaches it.
    Two identical bullets under one heading share an id: both are left out (`ambiguous`), as tidy's
    rule 4 would refuse them anyway.

Usage:
    python3 open_items.py --export e.txt --markdown doc.md --section "Nov 19, 2026" > open.json
    python3 open_items.py --selftest
"""
import argparse
import hashlib
import json
import re
import sys

import tidy_blocks as T

PERSON_RE = re.compile(r"\[([^\]]+)\]\(mailto:([^)\s]+)\)")
SINCE_RE = re.compile(r"〔\s*(WB\s*\d{1,2}/\d{1,2}|\d{4}-W\d{1,2})\s*起\s*〕")
MINUTES_RE = re.compile(r"^〔自動彙整[^〕]*〕\s*(會議紀錄|本週會議議程)\s*$")
METRIC_RE = re.compile(r"#\s*$")          # `Weekly Impression #`, `Out reach #`: a template row
# A status typed rather than chipped, as the team writes it: `… In progress`, `… In progress, add to …`.
TYPED_STATUS_RE = re.compile(r"\s+In progress\b,?", re.IGNORECASE)


def bullet_id(heading, text):
    key = "%s\x1f%s" % (T.nonspace(heading), T.nonspace(text))
    return "b" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def people(markdown, names):
    """({heading key: (name, email)}, {heading key: markdown levels}). A key two headings share with
    different person chips (`本週重點 [Ann]`, `本週重點 [Bob]`) names no one: the export line's own chip
    decides those."""
    out, levels, clash = {}, {}, set()
    for line in markdown.split("\n"):
        m = T.MD_HEADING_RE.match(line.strip())
        if not m:
            continue
        keys = T.heading_keys(line.strip(), names)
        for k in keys:
            levels.setdefault(k, set()).add(len(line.strip()) - len(line.strip().lstrip("#")))
        who = PERSON_RE.findall(T.FOOTNOTE_RE.sub("", m.group(1)))
        if not who:
            continue
        for k in keys:
            if out.setdefault(k, who[0]) != who[0]:
                clash.add(k)
    for k in clash:
        out.pop(k, None)
    return out, levels


def heading_person(line, names, emails):
    """The person chip printed in an export heading line (`#Sales (Folder) Ding Huan Wu`), or None."""
    s = re.sub(r"\[[a-z]{1,3}\]", "", T.FOOTNOTE_RE.sub("", line)).strip()
    n = next((n for n in sorted(names, key=len, reverse=True) if n in s), None)
    return (n, emails.get(n)) if n else None


def is_closed(text, dot=False):
    """tidy step 7's own reading of a bullet's status: a closing chip, unless the line also says open.
    A typed `·` item closes only on a chip at its end, as tidy reads it: a mid-line `Done` there is not
    one tidy removes, so it stays open here too, where evidence can still close it."""
    if T.CLOSED_TAIL_RE.search(text):
        return True
    return not dot and not T.OPEN_ANY_RE.search(text) and bool(T.CLOSED_MID_RE.search(text))


def _core(text):
    t = T.PRIORITY_RE.sub("", text.strip())
    t = T.STATUS_WORD_RE.sub("", t)            # before 〔… 起〕 goes: `…〕WIP` is a status only after a 〕
    t = SINCE_RE.sub(" ", t)
    return re.sub(r"\s{2,}", " ", TYPED_STATUS_RE.sub("", t)).strip(" ·—-")


def tail_name(text, names):
    """The person chip at the END of a bullet (`P0 X Peter Tu In Progress`), where the team puts it.
    A name inside the sentence (`跟 Peter Tu 確認報價`) is who the work is with, not whose it is."""
    core = _core(text)
    return next((n for n in sorted(names, key=len, reverse=True) if core.endswith(n)), None)


def label_of(text, names):
    """The bullet as a person would say it: no priority chip, status word, trailing person chip or
    〔… 起〕. A bullet that is nothing but chips keeps its text, so a line never reads blank."""
    t = _core(text)
    n = tail_name(text, names)
    if n:
        t = t[:-len(n)].strip(" ·—-")
    return t or re.sub(r"\s{2,}", " ", SINCE_RE.sub(" ", text)).strip()


def open_items(export_lines, markdown, section):
    names = set(T.MAILTO_NAME_RE.findall(markdown))
    headings = T.heading_keys(markdown, names)
    owners, levels = people(markdown, names)
    emails = dict(PERSON_RE.findall(markdown))
    # a team heading sits one level under the dated section; only deeper headings inherit its person
    team = 1 + min((n for n in (len(l.strip()) - len(l.strip().lstrip("#")) for l in markdown.split("\n")
                                if T.SECTION_RE.match(l.strip())) if n), default=1)
    marks = T.export_sections(export_lines)
    hit = [k for k, (_, lab) in enumerate(marks) if lab == section]
    if not hit:
        raise SystemExit("open_items: section %r not in the export — wrong file, or the wrong week?" % section)
    a = marks[hit[0]][0] + 1
    b = marks[hit[0] + 1][0] if hit[0] + 1 < len(marks) else len(export_lines)
    sec = [T.clean(l) for l in export_lines[a:b]]

    def heading(line):
        return line.lstrip("﻿").startswith("#") or bool(T.line_keys(line, names) & headings)

    machine = set()
    for k, line in enumerate(sec):
        if "〔自動彙整" not in line:
            continue
        machine |= T.walk_block(sec, k)[2] | {k}
        if MINUTES_RE.match(line.strip()):
            # the meeting's own block: 決議 · 待辦 · … are the machine's lines up to the next heading
            j = k + 1
            while j < len(sec) and not (sec[j].strip() and heading(sec[j])):
                machine.add(j)
                j += 1

    items, skipped = [], {"closed": 0, "machine": 0, "before_heading": 0, "metrics": 0, "ambiguous": 0}
    head, who, in_metrics, stack = None, None, False, []
    for k, line in enumerate(sec):
        s = line.strip()
        if not s:
            continue
        if heading(line):
            head, stack = s, []
            in_metrics = T.nonspace(s.lstrip("#")) == "Metrics"
            keys = T.line_keys(line, names)
            found = heading_person(s, names, emails) or next((owners[x] for x in keys if x in owners), None)
            lv = set().union(*(levels.get(x, set()) for x in keys)) if keys else set()
            if found:
                who = found
            elif not (lv and min(lv) > team):
                who = None              # a team heading with no chip (`#Team update`) is no one's
            # else: a sub-heading with no chip is its parent's (`##Operation BAU`)
            continue
        if s == "Metrics":              # a Metrics label typed as plain text, not a heading
            in_metrics = True
            continue
        m = T.BULLET_RE.match(line) or T.DOT_ITEM_RE.match(line)
        if not m:
            continue
        if k in machine:
            skipped["machine"] += 1
            continue
        if head is None:
            skipped["before_heading"] += 1
            continue
        depth, text = len(m.group(1)), m.group(2)
        while stack and stack[-1][0] >= depth:
            stack.pop()
        parent = stack[-1][1] if stack else None
        stack.append((depth, text))
        if in_metrics or METRIC_RE.search(text) or (parent and METRIC_RE.search(parent)):
            skipped["metrics"] += 1
            continue
        dot = m.re is T.DOT_ITEM_RE
        if is_closed(text, dot):
            skipped["closed"] += 1
            continue
        named = tail_name(text, names)
        person = (named, emails.get(named)) if named else who
        since = SINCE_RE.search(text)
        kids, open_kids = 0, []
        for j in range(k + 1, len(sec)):
            c = T.BULLET_RE.match(sec[j])
            if dot or not c or len(c.group(1)) <= depth:
                break                   # tidy's own subtree: the bullets right under it, deeper
            kids += 1
            if not is_closed(c.group(2)):
                open_kids.append(c.group(2))
        items.append({"id": bullet_id(head, text), "heading": head, "text": text,
                      "label": label_of(text, names), "person": person[0] if person else None,
                      "email": person[1] if person else None, "depth": depth, "parent": parent,
                      "since": re.sub(r"\s+", " ", since.group(1)) if since else None, "sub_items": kids,
                      "open_sub_items": open_kids})
    seen = {}
    for it in items:
        seen[it["id"]] = seen.get(it["id"], 0) + 1
    twice = {i for i, n in seen.items() if n > 1}
    skipped["ambiguous"] = sum(1 for it in items if it["id"] in twice)
    items = [it for it in items if it["id"] not in twice]
    return {"section": section, "items": items, "skipped": skipped}


# ── selftest ────────────────────────────────────────────────────────────────
MD = """\
## Nov 26, 2026
## Nov 19, 2026
### #Team update / discuss
### #Sales ([Folder](https://x.example/f)) [Ding Huan Wu](mailto:dh@example.com)
#### ##Sales BAU
### #Tech product [Peter Tu](mailto:peter@example.com)
#### Finance [Peter Tu](mailto:peter@example.com)
### #Ops [Bob Wu](mailto:bob@example.com)
#### 本週重點 [Bob Wu](mailto:bob@example.com)
### #Mkt [Ann Lee](mailto:ann@example.com)
#### 本週重點 [Ann Lee](mailto:ann@example.com)
"""

EXPORT = """\
Nov 26, 2026
#Team update / discuss
* P0 copied Peter Tu In Progress
Nov 19, 2026
〔自動彙整 WB 11/9 · 11-13 03:42〕會議紀錄
* 決議
   * 分潤系統先放棄
* 待辦
   * 修正自動化擷取設定 — Peter Tu · Done
#Team update / discuss
* P0 Zynkr knowledge base Peter Tu In Progress
* 社群發文：Mark 接 In progress
#Sales (Folder) Ding Huan Wu
〔自動彙整 WB 11/16 · 11-18 22:05〕
* 進度
   * 不在 Tracker｜完成：業務八大類矩陣已發布
* 還沒收掉的[a]
   * 5 筆陌開陪跑 deal〔WB 11/2 起〕
   * 業務藍圖問題排解上線〔WB 11/2 起〕Done
   * sales follow up〔WB 10/19 起〕
   * sales follow up〔WB 10/19 起〕
Metrics
* Out reach #
* Inbound #
##Sales BAU
* 拜訪清單整理
   * 名單 A
#Tech product Peter Tu
· 還沒收掉的 —[b]
      * 合作方：報價〔WB 11/2 起〕完成
      * Atlas 搬遷收尾〔WB 11/2 起〕
* P1 Zynkr atlas In Progress
* Finance Peter Tu
* P1 Funnel calculation In Progress
* 跟 Ding Huan Wu 確認報價
* Peter Tu In Progress
· P2 課程剪輯 Done 進度：2-4
* 官網改版
   * 首頁 Done
   * 價格頁
#Ops Bob Wu
本週重點 Bob Wu
* 乙件事
#Mkt Ann Lee
本週重點 Ann Lee
* 丙件事
Nov 12, 2026
#Team update / discuss
"""


def selftest():
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append("%s\n    got:  %r\n    want: %r" % (name, got, want))

    res = open_items(EXPORT.split("\n"), MD, "Nov 19, 2026")
    by = {it["label"]: it for it in res["items"]}
    check("the open bullets, in order", [it["label"] for it in res["items"]],
          ["Zynkr knowledge base", "社群發文：Mark 接", "5 筆陌開陪跑 deal",
           "拜訪清單整理", "名單 A", "Atlas 搬遷收尾", "Zynkr atlas", "Funnel calculation",
           "跟 Ding Huan Wu 確認報價", "Peter Tu In Progress", "課程剪輯 進度：2-4", "官網改版", "價格頁",
           "乙件事", "丙件事"])
    check("the meeting's own block is the machine's", "分潤系統先放棄" in by, False)
    check("an auto block's lines are the machine's", any("八大類" in x for x in by), False)
    check("a carried item under a formatted 還沒收掉的 is the team's", by["5 筆陌開陪跑 deal"]["since"], "WB 11/2")
    check("a chipped Done is not open", any("排解上線" in x for x in by), False)
    check("a typed 完成 is not open", any("合作方" in x for x in by), False)
    check("two identical bullets are both left out", res["skipped"]["ambiguous"], 2)
    check("Metrics template rows are not work", res["skipped"]["metrics"], 2)
    check("a heading's person chip owns its bullets", by["5 筆陌開陪跑 deal"]["email"], "dh@example.com")
    check("a sub-heading with no chip is its parent's", by["拜訪清單整理"]["person"], "Ding Huan Wu")
    check("a chip in the bullet names its person", by["Zynkr knowledge base"]["person"], "Peter Tu")
    check("a top heading with no chip is no one's", by["社群發文：Mark 接"]["person"], None)
    check("a status stuck to 〕 is not part of the label",
          label_of("整理優化過往業務開發〔WB 11/2 起〕WIP", set()), "整理優化過往業務開發")
    check("a heading printed as a bullet is a heading", "Finance" in by, False)
    check("sub-items are counted", by["拜訪清單整理"]["sub_items"], 1)
    check("a sub-item knows its parent", by["名單 A"]["parent"], "拜訪清單整理")
    check("the id is the same in next week's verbatim copy",
          by["Zynkr knowledge base"]["id"], bullet_id("#Team update / discuss", "P0 Zynkr knowledge base Peter Tu In Progress"))
    check("a name inside the sentence is who the work is with, not whose it is",
          (by["跟 Ding Huan Wu 確認報價"]["person"], "跟 Ding Huan Wu 確認報價" in by), ("Peter Tu", True))
    check("a bullet that is only chips keeps its text as the label", "Peter Tu In Progress" in by, True)
    check("a typed · item with Done mid-line stays open, as tidy reads it",
          "課程剪輯 進度：2-4" in by, True)
    check("two people's same-named sub-headings keep their own person",
          (by["乙件事"]["person"], by["丙件事"]["person"]), ("Bob Wu", "Ann Lee"))
    check("open sub-items are named, closed ones are not", by["官網改版"]["open_sub_items"], ["價格頁"])
    check("the newest section is read only when asked for",
          [it["label"] for it in open_items(EXPORT.split("\n"), MD, "Nov 26, 2026")["items"]], ["copied"])
    try:
        open_items(EXPORT.split("\n"), MD, "Nov 5, 2026")
        fails.append("a missing section must stop the run")
    except SystemExit:
        pass
    if fails:
        print("open_items.py selftest: %d failed" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("open_items.py selftest: all checks passed")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--export", help="get_drive_file_content output (chips rendered)")
    ap.add_argument("--markdown", help="get_doc_as_markdown output (headings and person chips)")
    ap.add_argument("--section", help='the week section, as its heading reads: "Nov 19, 2026"')
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not (a.export and a.markdown and a.section):
        ap.error("--export, --markdown and --section are all needed")
    res = open_items(T.load_export(a.export), T.read_tool_file(a.markdown), a.section)
    json.dump(res, sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
