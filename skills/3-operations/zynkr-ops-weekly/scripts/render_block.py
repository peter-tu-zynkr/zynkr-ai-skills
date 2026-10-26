#!/usr/bin/env python3
"""Render the marked 〔自動彙整〕 block for each department heading.

    render_block.py --reports reports.json --routing routing.json \
                    [--carryover carryover.json] --week "WB 9/14" --stamp "09-15 12:00"

Emits one block per routed heading, plus the diagnostics the run report must surface:
reporters whose owner email matches no heading, and headings with no report this week.

The block is the ONLY place auto-content is allowed to live, and its stamp doubles as the
idempotency key -- before writing, the caller searches the section for `〔自動彙整 <week>`.
Nothing here ever rewrites a human's line.
"""
import argparse
import json
import re
import sys

# The stamp is the idempotency key -- `rollup` searches the section for `〔自動彙整 <week>`
# before writing. Do not reword it, ever.
#
# <week> is the WEEK-BEGINNING label, `WB 9/14` (the Monday that opens the week), NOT an ISO
# week ordinal. Changed 2026-09-15. Sections written before then carry `2026-W38`-style keys,
# which the search no longer matches: the window for matching both shapes closed on 2026-10-06.
STAMP = "〔自動彙整 {week} · {stamp}〕"

# zh-TW throughout: the team writes Chinese, and a block that reads "事項 Not started" makes
# the reader code-switch mid-line for no reason. `parse_reports.py` accepts both spellings on
# the way in, so this only changes what gets written to the Doc.
STATUS_LABEL = {"DONE": "完成", "WIP": "進行中", "BLOCKED": "卡住",
                "NOT_STARTED": "還沒開始", "ABANDONED": "放棄", "UNSET": "沒寫狀態"}


def norm_key(text):
    text = re.sub(r"↻\s*\d+\s*週", "", text)
    text = re.sub(r"\b(done|wip|blocked|not\s*started|in\s*progress)\b", "", text, flags=re.I)
    text = re.sub(r"[*_`~〔〕（）()\[\]:：,，。.\-—–·、/／%]", "", text)
    text = re.sub(r"\d+", "", text)
    return re.sub(r"\s+", "", text).strip().lower()


def carry_lookup(carryover):
    if not carryover:
        return {}
    return {norm_key(i["text"]): i["weeks"] for i in carryover.get("items", []) if i["weeks"] > 1}


def render(record, carries):
    """[(label, [items])] in the block's order. The labels are frozen: tidy_blocks.walk_block and
    carryover.LABEL_RE know a block only by them."""
    out = []

    if record["last_week"]:
        parts = []
        for item in record["last_week"]:
            label = STATUS_LABEL.get(item["status"], item["status"])
            weeks = carries.get(norm_key(item["text"]))
            tag = f" ↻{weeks}週" if weeks and item["status"] != "DONE" else ""
            parts.append(f"{item['text']} {label}{tag}")
        out.append(("上週", parts))

    if record["this_week"]:
        out.append(("本週", [i["text"] for i in record["this_week"]]))

    nums = record["numbers"]
    if nums["parsed"]:
        out.append(("數字", [f"{k} {v}" for k, v in nums["parsed"].items()]))
    elif nums["raw"] and not nums.get("empty"):
        out.append(("數字", [nums["raw"]]))

    if record["blocker"]:
        out.append(("卡關", [record["blocker"]]))

    if record["missing_lines"]:
        zh = {"last_week": "上週", "this_week": "本週", "numbers": "數字", "blocker": "卡關"}
        out.append(("沒寫", ["、".join(zh[k] for k in record["missing_lines"])]))

    return out


def body_text(sections):
    """The block under its stamp, as written since 2026-10-25 (the owner: one item per bullet, no
    typed `·` lines): each label on its own line, each item one tab in. ops() makes it a list, and
    the tab is what makes an item a sub-bullet."""
    lines = []
    for label, items in sections:
        lines.append(label)
        lines += ["\t" + re.sub(r"\s+", " ", i).strip() for i in items if i.strip()]
    return "\n".join(lines)


def utf16(text):
    """Docs indices count UTF-16 code units: an emoji is two."""
    return len(text.encode("utf-16-le")) // 2


def ops(blocks, at, tab_id):
    """batch_update_doc operations writing each block at `at[heading]` (the heading's end_index),
    highest first. Per block: insert the stamp and body, clear any bullet and indent the text took
    from the paragraph it landed on, then one bullet list over the body. Docs counts leftover indent
    as an extra level, and will not nest the first line of a list: the first body line is a label,
    so it never needs to."""
    out = []
    for b in sorted(blocks, key=lambda b: at[b["heading"]], reverse=True):
        i = at[b["heading"]]
        text = b["stamp_line"] + "\n" + b["body"] + "\n"
        end = i + utf16(text) - 1
        out += [{"type": "insert_text", "index": i, "text": text},
                {"type": "create_bullet_list", "start_index": i, "end_index": end, "list_type": "NONE"},
                {"type": "update_paragraph_style", "start_index": i, "end_index": end,
                 "indent_start": 0, "indent_first_line": 0},
                {"type": "create_bullet_list", "start_index": i + utf16(b["stamp_line"]) + 1,
                 "end_index": end, "list_type": "UNORDERED"}]
    return [{**o, "tab_id": tab_id} for o in out]


def main():
    if sys.argv[1:2] == ["ops"]:
        op = argparse.ArgumentParser(description="the write operations for render_block's blocks")
        op.add_argument("cmd")
        op.add_argument("--blocks", required=True, help="render_block.py's output")
        op.add_argument("--at", required=True,
                        help='JSON {"<heading>": <that heading\'s end_index>} from inspect_doc_structure')
        op.add_argument("--tab", required=True, help="the tab id every operation must carry")
        a = op.parse_args()
        blocks = json.load(open(a.blocks, encoding="utf-8"))["blocks"]
        at = json.load(open(a.at, encoding="utf-8"))
        missing = [b["heading"] for b in blocks if b["heading"] not in at]
        if missing:
            raise SystemExit(f"render_block ops: no index for {missing} — write nothing")
        json.dump(ops(blocks, at, a.tab), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reports", required=True)
    ap.add_argument("--routing", required=True)
    ap.add_argument("--carryover")
    ap.add_argument("--week", required=True, help='week-beginning label, e.g. "WB 9/14"')
    ap.add_argument("--stamp", required=True, help='timestamp shown in the block, e.g. "08-24 12:00"')
    args = ap.parse_args()

    reports = json.load(open(args.reports, encoding="utf-8"))
    routing = json.load(open(args.routing, encoding="utf-8"))
    carryover = json.load(open(args.carryover, encoding="utf-8")) if args.carryover else None
    carries = carry_lookup(carryover)

    by_email = {r["email"]: r for r in reports["records"]}
    header = STAMP.format(week=args.week, stamp=args.stamp)

    blocks, no_report = [], []
    for heading in routing["headings"]:
        # A grouped sub-heading is covered by its parent's block; don't write it twice.
        if heading.get("grouped_with_previous"):
            continue
        email = heading["owner_email"]
        record = by_email.get(email)
        if not record:
            no_report.append({"heading": heading["heading"], "owner_email": email})
            continue
        if not heading.get("primary", True):
            continue  # one owner, several headings -> block goes under the primary one
        body = render(record, carries)
        if not body:
            no_report.append({"heading": heading["heading"], "owner_email": email,
                              "reason": "posted but empty"})
            continue
        blocks.append({
            "heading": heading["heading"],
            "owner_email": email,
            "owner_name": heading.get("owner_name"),
            "stamp_line": header,
            "body": body_text(body),
            "text": header + "\n" + body_text(body),
            "lines": 1 + sum(1 + len(items) for _, items in body),
        })

    routed_emails = {h["owner_email"] for h in routing["headings"]}
    unroutable = [e for e in by_email if e not in routed_emails]

    json.dump({
        "week": args.week,
        "stamp": header,
        "idempotency_key": f"〔自動彙整 {args.week}",
        "blocks": blocks,
        "headings_without_report": no_report,
        "reporters_without_heading": unroutable,
        "unrouted_headings": [u["heading"] for u in routing.get("unrouted", [])],
        "counts": {"blocks": len(blocks), "no_report": len(no_report),
                   "unroutable_reporters": len(unroutable)},
    }, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")

    if unroutable:
        print(f"render_block: {len(unroutable)} reporter(s) have no heading chip: "
              f"{', '.join(unroutable)}", file=sys.stderr)


if __name__ == "__main__":
    main()
