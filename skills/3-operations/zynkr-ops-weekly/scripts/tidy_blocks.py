"""Decide which 〔自動彙整〕 blocks to keep, archive and compact — for the Friday `tidy` beat.

WHY THIS EXISTS
    The Apps Script scaffold copies the newest week section forward **verbatim** every Thursday
    at 23:00. The auto blocks travel with it, and `rollup` only ever prepends — so by the time
    anyone looks, one department heading carries four stacked blocks reporting four different
    weeks. On 2026-09-15 the live `Sep 17, 2026` section held **22 blocks in 7 groups**.

    That is the growth engine of the whole Doc, and the thing the owner's 08-27 comment was about.
    This script is the judgement half of the fix: it reads the section and says what should
    happen. It writes nothing. The skill does the Doc writes (SKILL.md Step 4.6).

WHAT IT IS SAFE TO DELETE, AND WHY
    Every block this script marks for archiving is a **copy** the Thursday scaffold made of a
    block that still sits in the previous week's section — which is frozen and never edited
    again. So removing it from the live section destroys nothing. That property is what makes
    this operation fundamentally different from moving whole week sections around, which was
    built and reverted the same day (SKB-029). Do not lose it: if the scaffold ever stops
    copying forward, re-derive the safety argument before trusting this script.

    The block pass never looks at a line outside a stamped block. The department heading above
    and the human bullets below are out of range by construction, so the person chips that drive
    routing are never touched.

    The one exception is `--closed` (SKB-039): a human bullet whose status reads `Done`/`Drop`.
    The same argument makes it safe — the newest section is a copy — and it is enforced rather
    than assumed: a bullet is only returned when it sits verbatim in the previous week's section
    under the same heading, contains no heading, and matches exactly one place in the Doc
    together with the lines directly above and below it.

Usage:
    python3 tidy_blocks.py --input doc.md            # JSON for the skill
    python3 tidy_blocks.py --input doc.md --report   # human-readable rehearsal

    # SKB-039, tidy step 7 — plan, re-check on a fresh read, delete, then post-check
    python3 tidy_blocks.py --closed --export e1.txt --structure s1.json --markdown doc.md \\
        --section "Oct 8, 2026"                          > plan.json
    python3 tidy_blocks.py --closed --export e2.txt --structure s2.json --markdown doc.md \\
        --section "Oct 8, 2026" --expect plan.json      # exit 0 only if nothing moved
    python3 tidy_blocks.py --closed --export e3.txt --section "Oct 8, 2026" --postcheck plan.json
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta

# A week section heading: "Sep 17, 2026". Matched at any heading level ON PURPOSE — only 23 of
# the 34 headings in the live Doc are real HEADING2; the older ones are styled otherwise and a
# level-locked regex silently skips eleven weeks of history. A comment on the heading arrives
# as a footnote ref (`## Sep 3, 2026[^c10]`) and must not hide the section.
SECTION_RE = re.compile(r"^#{1,6}\s*([A-Z][a-z]{2}\s+\d{1,2},\s*\d{4})\s*(?:\[\^[^\]]*\]\s*)*$")
HEADING_RE = re.compile(r"^#{1,6}\s+\S")

# The stamp is a frozen string (references/wording.md). Both shapes must be accepted until no
# live section predates 2026-09-15: `2026-W38` (legacy ISO) and `WB 9/14` (week beginning).
STAMP_RE = re.compile(r"〔自動彙整\s*(.+?)\s*·\s*([^〕]*)〕")
ISO_WEEK_RE = re.compile(r"^(\d{4})-W(\d{1,2})$")
WB_RE = re.compile(r"^WB\s*(\d{1,2})/(\d{1,2})$")

# Status words the team actually writes, harvested from the live Doc rather than invented.
# `Done` is here because an earlier pass that only looked for 完成 over-counted open items by 8.
# Anchored to the END of the item, where the status goes: `完成 CRM handoff 進行中` is open (the
# plan starts with the verb 完成), and `課程作業 完成 60%` is partial progress, not done.
DONE_RE = re.compile(r"(完成|已完成|\bDone\b|✅|結案)\s*$", re.IGNORECASE)
STATUS_RE = re.compile(
    r"\s*(完成|已完成|\bDone\b|WIP|進行中|卡住|沒寫狀態|狀態未填|還沒開始|"
    r"\bNot started\b|\bstarted\b|放棄|\babandoned\b)\s*$",
    re.IGNORECASE,
)
# Explicitly still open — the owner said so. `沒寫狀態` is not here: a 上週 line with no status is
# usually a report of what happened, not a promise still owed.
OPEN_RE = re.compile(r"\s*(WIP|進行中|卡住|還沒開始|\bNot started\b)\s*$", re.IGNORECASE)
# Done-words anywhere in an item, dropped only when COMPARING: `完成Claude code QC` (the plan)
# and `Claude code QC 完成` (the report) are the same item.
DONE_WORDS_RE = re.compile(r"(已完成|完成|\bDone\b)", re.IGNORECASE)

# Items that carry no work. Same class as the template rows carryover.py filters (`Funnel`,
# `CTR`): promoting them would let boilerplate dominate the carried list.
NOISE = {"例行性", "例行", "其他", "n/a", "-", "—", "無"}
# "On leave this week" is not a task — but `請假制度草案` (drafting the leave policy) is.
NOISE_RE = re.compile(r"^(請假|休假)\s*[一二三兩半\d]*\s*[週周天日]?$")

# The team separates items with a fullwidth `／`. An ASCII `/` only counts when it is spaced,
# because the unspaced kind is almost always inside a URL: an earlier `／|/` split tore
# `https://example.com/a/b/c` into four items and left `https:` looking like a status word.
ITEM_SPLIT_RE = re.compile(r"／|(?<=\s)/(?=\s)")

# Shortest item worth carrying. Two, not four: `發文` and `對帳` are real work items, and a
# Latin-tuned floor silently drops every short Chinese one. Junk is handled by NOISE instead.
MIN_ITEM_LEN = 2

# One line of a `· 還沒收掉的 —` list: `· 更新一篇seo〔WB 8/24 起〕`. Keyed on the week label + 起,
# not on the absence of `—`, because an item can itself contain one (`客戶甲 — 導入諮詢`).
CARRIED_RE = re.compile(r"^·\s*(.+?)\s*〔\s*(WB\s*\d{1,2}/\d{1,2}|\d{4}-W\d{1,2})\s*起\s*〕\s*$")
# Since 2026-10-25 a carried item is written as a real list bullet (`- 更新一篇seo〔WB 8/24 起〕` in
# markdown), so the team can mark it Done/Drop like any of their own bullets and step 7 clears it a
# week later. A bullet ends the block (block_extent), so these sit below it, as human lines do.
CARRIED_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*〔\s*(?:WB\s*\d{1,2}/\d{1,2}|\d{4}-W\d{1,2})\s*起\s*〕")
# The same carried item in the export, its chips rendered: `· P2 更新一篇seo〔WB 8/24 起〕` or `* …`.
CARRIED_EXPORT_RE = re.compile(r"^(?:·|\*)\s*(.+?)\s*〔\s*(?:WB\s*\d{1,2}/\d{1,2}|\d{4}-W\d{1,2})\s*起\s*〕$")
MD_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*?)\s*$")
# Since 2026-10-25 tidy formats the block it keeps as bullets (the owner: no typed `·` lines after
# tidying, one item per bullet). `· 上週 — 甲 完成 ／ 乙 WIP` becomes a label bullet with its items
# under it — markdown `- 上週` / `  - 甲 完成`, export `* 上週` / `    * 甲 完成`. These are still
# the machine's lines, never the team's: the label and its sub-bullets belong to the block. The
# one exception is `還沒收掉的`, whose sub-bullets are the carried items the team closes.
LABEL_BULLET_RE = re.compile(r"^(\s*)[-*]\s+(上週|本週|數字|卡關|沒寫|還沒收掉的)\s*(?:—\s*(.*?))?\s*$")
CHILD_RE = re.compile(r"^(\s*)[-*]\s+(.*?)\s*$")
CARRY_LABEL = "還沒收掉的"

# `get_doc_as_markdown` inlines comment anchors as footnote refs (`某件事[^c5]`), and puts them
# at the END of a line too (`…〔WB 8/24 起〕[^c6]`). Strip before matching anything.
FOOTNOTE_RE = re.compile(r"\[\^[^\]]*\]")


def week_key(label, stamp, today=None):
    """Sortable key for either week shape, so a group can be ordered without trusting write order.

    `WB 9/14` carries no year. It is resolved against today and pulled back a year when that
    would put it more than two weeks in the future — a label is never ahead of the run, so
    `WB 8/24` read in January is last August, and `WB 12/28` read on Jan 2 is last December.
    """
    m = ISO_WEEK_RE.match(label)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = WB_RE.match(label)
    if m:
        today = today or date.today()
        month, day = int(m.group(1)), int(m.group(2))
        try:
            d = date(today.year, month, day)
            if d > today + timedelta(days=14):
                d = date(today.year - 1, month, day)
            iso = d.isocalendar()
            return (iso[0], iso[1])
        except ValueError:
            return (0, 0)
    return (0, 0)


def strip_status(item):
    """`每週發文 完成` → `每週發文`. Without this, the same item reads as two different ones."""
    return STATUS_RE.sub("", item).strip()


def normalise(text):
    """Comparison key. Digits go so `90%` → `92%` stays one item, matching carryover.py."""
    text = FOOTNOTE_RE.sub("", text)
    text = re.sub(r"\(https?://[^)]*\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return re.sub(r"[\s\d%（）()【】\[\]·・、，,.。\-–—_:：&＆]+", "", text).lower()


def close_key(item):
    """Key for 'has this been reported done' — status and done-words dropped on both sides."""
    return normalise(DONE_WORDS_RE.sub("", strip_status(item)))


def split_items(line):
    """`· 本週 — a ／ b ／ c` → ['a', 'b', 'c']."""
    if "—" not in line:
        return []
    # A separator inside brackets is part of one item: `入營審核（Hahow ／ 銷售講座學員） 完成`
    # was split in two, and as bullets it showed as two broken items (10-25).
    text = line.split("—", 1)[1]
    cuts = {m.start(): m.end() for m in ITEM_SPLIT_RE.finditer(text)}
    parts, depth, start, k = [], 0, 0, 0
    while k < len(text):
        if text[k] in "（(〔【[":
            depth += 1
        elif text[k] in "）)〕】]":
            depth = max(0, depth - 1)
        elif k in cuts and depth == 0:
            parts.append(text[start:k])
            start = k = cuts[k]
            continue
        k += 1
    parts.append(text[start:])
    return [x.strip() for x in parts if x.strip()]


def is_line(s, word):
    return s.startswith("· " + word) or s.startswith("·" + word)


def sections(lines):
    """[(start_index, label)] for every dated week heading, in document order."""
    return [(i, m.group(1)) for i, line in enumerate(lines)
            if (m := SECTION_RE.match(line.strip()))]


def find_groups(sec):
    """Contiguous runs of auto blocks. A heading between two blocks starts a new group."""
    starts = [i for i, line in enumerate(sec) if "〔自動彙整" in line]
    if not starts:
        return []
    groups, current = [], [starts[0]]
    for a, b in zip(starts, starts[1:]):
        if any(HEADING_RE.match(sec[k].strip()) for k in range(a + 1, b)):
            groups.append(current)
            current = [b]
        else:
            current.append(b)
    groups.append(current)
    return groups


def walk_block(sec, start):
    """Read the block stamped at `start`, typed or formatted.

    Returns (last, rows, machine): the index of its last line; each summary line in the typed
    form, `· 上週 — 甲 完成 ／ 乙 WIP`, whichever shape the Doc holds it in; and the indices of the
    label bullets and their sub-bullets (never a work item of the team's).

    The shape is what keeps human content out of range: the auto lines begin `·` or are a label
    bullet with its sub-bullets, and the team's bullets are neither, so the first of them ends the
    block. The carried sub-bullets under `還沒收掉的` end it too: they outlive the block.
    """
    end, rows, machine = start, [], set()
    k = start + 1
    while k < len(sec):
        raw = FOOTNOTE_RE.sub("", sec[k])
        s = raw.strip()
        if "〔自動彙整" in s or HEADING_RE.match(s):
            break
        lb = LABEL_BULLET_RE.match(raw)
        if s.startswith("·"):
            rows.append(s)
            end = k
        elif lb:
            label, inline = lb.group(2), lb.group(3)
            end = k
            machine.add(k)
            kids, j = [], k + 1
            if label != CARRY_LABEL and inline is None:
                while True:
                    n = next((q for q in range(j, len(sec)) if sec[q].strip()), len(sec))
                    c = CHILD_RE.match(FOOTNOTE_RE.sub("", sec[n])) if n < len(sec) else None
                    if not c or len(c.group(1)) <= len(lb.group(1)):
                        break
                    kids.append(c.group(2))
                    machine.add(n)
                    end, j = n, n + 1
                k = end
            text = inline if inline is not None else " ／ ".join(kids)
            rows.append(f"· {label} — {text}".rstrip())
        elif s:
            break
        k += 1
    return end, rows, machine


def block_extent(sec, start):
    """A block runs from its stamp to its last summary line — see walk_block."""
    return walk_block(sec, start)[0]


def owner_of(sec, index):
    """Nearest heading above the group — the department the blocks belong to."""
    for k in range(index, -1, -1):
        s = sec[k].strip()
        if HEADING_RE.match(s):
            return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s.lstrip("#").strip())
    return "(section top)"


def closed_in_export(export_lines, label):
    """Keys of the carried items a chip marks Done/Drop in section `label` of the Drive export.

    The markdown read drops every dropdown chip, so `· 更新一篇seo〔WB 8/24 起〕` with a `Done` chip
    reads as open there. Re-carrying it re-types the text and loses the chip, so the item came
    back open every week (the owner's 10-25 screenshot). Only the export shows the chip."""
    if export_lines is None:
        return set()
    marks = export_sections(export_lines)
    hit = [k for k, (_, lab) in enumerate(marks) if lab == label]
    if not hit:
        raise SystemExit(f"tidy: section {label!r} not in the export — wrong file?")
    a = marks[hit[0]][0] + 1
    b = marks[hit[0] + 1][0] if hit[0] + 1 < len(marks) else len(export_lines)
    keys = set()
    for line in export_lines[a:b]:
        t = clean(line).strip()
        if not CLOSED_TAIL_RE.search(t):
            continue
        t = CLOSED_TAIL_RE.sub("", t)
        if m := CARRIED_EXPORT_RE.match(t):
            keys.add(normalise(PRIORITY_RE.sub("", m.group(1))))
    return keys


def analyse(lines, target=None, today=None, export_lines=None):
    marks = sections(lines)
    if not marks:
        raise SystemExit("tidy: no dated week section found — is this the right tab?")
    if target:
        hit = [(i, lab) for i, lab in marks if lab == target]
        if not hit:
            raise SystemExit(f"tidy: section {target!r} not in the Doc")
        start, label = hit[0]
    else:
        start, label = marks[0]
    nxt = next((i for i, _ in marks if i > start), len(lines))
    sec = lines[start:nxt]
    chip_closed = closed_in_export(export_lines, label)

    out = []
    for group in find_groups(sec):
        blocks = []
        for s in group:
            stamp = STAMP_RE.search(sec[s])
            wk = stamp.group(1) if stamp else "?"
            last, rows, machine = walk_block(sec, s)
            blocks.append({
                "week": wk,
                "stamp": stamp.group(2) if stamp else "",
                "first": s,
                "last": last,
                "rows": rows,
                "machine": machine,
                "key": (week_key(wk, stamp.group(2) if stamp else "", today),
                        stamp.group(2) if stamp else ""),
            })
        # Do not trust write order. `rollup` prepends, so newest is normally first — but a
        # hand-edit or a re-run can break that, and picking the wrong block to keep would
        # archive the current week and leave a stale one in its place.
        blocks.sort(key=lambda b: b["key"], reverse=True)
        keep, archive = blocks[0], blocks[1:]

        closed, live = set(), set()
        for b in blocks:
            for s in b["rows"]:
                if is_line(s, "上週"):
                    for item in split_items(s):
                        if DONE_RE.search(item):
                            closed.add(close_key(item))
        for s in keep["rows"]:
            for item in split_items(s):
                live.add(normalise(strip_status(item)))
            # An item the kept block already carries is still visible too.
            if m := CARRIED_RE.match(s):
                live.add(normalise(m.group(1)))
        # Bullets under the same heading are visible too: an item already carried as a bullet, or
        # already on someone's own list, must not be carried again.
        top = next((k for k in range(group[0], -1, -1) if HEADING_RE.match(sec[k].strip())), 0)
        bottom = next((k for k in range(group[-1] + 1, len(sec))
                       if HEADING_RE.match(sec[k].strip())), len(sec))
        inside = set().union(*(range(b["first"], b["last"] + 1) for b in blocks))
        for k in range(top + 1, bottom):
            if k in inside:
                continue            # a formatted block's sub-bullets are its summary, read above
            if m := MD_BULLET_RE.match(FOOTNOTE_RE.sub("", sec[k])):
                text = m.group(1)
                if c := CARRIED_BULLET_RE.match(sec[k]):
                    text = c.group(1)
                live.add(normalise(strip_status(text)))

        # Candidates in document order; each one keeps the OLDEST week it was ever seen in, so an
        # item that sat on a carried list since WB 8/24 does not look new because it also appears
        # in a later block's 本週.
        found = {}
        for b in archive:
            planned = set()
            for s in b["rows"]:
                if is_line(s, "本週"):
                    planned |= {normalise(strip_status(x)) for x in split_items(s)}
            for s in b["rows"]:
                if is_line(s, "本週"):
                    items = [(strip_status(x), b["week"]) for x in split_items(s)]
                elif is_line(s, "上週"):
                    # SKB-039: an item reported still open that the owner did not plan again.
                    # Suppressed while its block was kept (it was visible); archiving erases it.
                    items = [(strip_status(x), b["week"]) for x in split_items(s)
                             if OPEN_RE.search(x) and normalise(strip_status(x)) not in planned]
                elif m := CARRIED_RE.match(s):
                    # SKB-039: the carried list is itself content of the block being archived.
                    # Reading only 本週 dropped every carried item one tidy after it was rescued.
                    text = m.group(1)
                    tail = STATUS_RE.search(text)
                    if tail and DONE_RE.search(tail.group(0)):
                        continue            # `· 甲件事 完成〔WB 8/24 起〕` — marked done inline
                    if normalise(text) in chip_closed:
                        continue            # a Done/Drop chip after it, seen only in the export
                    items = [(strip_status(text), m.group(2))]
                else:
                    continue
                for text, since in items:
                    key = normalise(text)
                    # `live` covers the WHOLE kept block, 上週 included. An item still printed
                    # there has not disappeared, so repeating it in the carried list is noise —
                    # the list exists to rescue what archiving would otherwise erase.
                    if (not key or len(key) < MIN_ITEM_LEN or close_key(text) in closed
                            or key in live or text in NOISE or NOISE_RE.match(text)):
                        continue
                    wk = week_key(since, "", today)
                    if key not in found:
                        found[key] = {"text": text, "since": since, "_wk": wk}
                    elif wk < found[key]["_wk"]:
                        found[key].update(since=since, _wk=wk)
        carried = [{"text": c["text"], "since": c["since"]} for c in found.values()]

        # Where step 5 writes: after the kept block's last line. It needs a `· 還沒收掉的 —` line
        # there when it has items to write or when carried bullets already sit below the group
        # (the archived block above them took the old one with it).
        last = max(block_extent(sec, s) for s in group)
        nxt_line = next((sec[k] for k in range(last + 1, len(sec)) if sec[k].strip()), "")
        has_header = any(is_line(s, CARRY_LABEL) for s in keep["rows"])
        out.append({
            "owner": owner_of(sec, group[0]),
            "keep": {"week": keep["week"], "stamp": keep["stamp"],
                     "lines": sec[keep["first"]:keep["last"] + 1]},
            "archive": [{"week": b["week"], "stamp": b["stamp"],
                         "lines": sec[b["first"]:b["last"] + 1]} for b in archive],
            "carry": carried,
            "carry_header_needed": not has_header and bool(
                carried or CARRIED_BULLET_RE.match(FOOTNOTE_RE.sub("", nxt_line))),
        })
    return {"section": label, "groups": out,
            "totals": {
                "blocks": sum(1 + len(g["archive"]) for g in out),
                "keep": len(out),
                "archive": sum(len(g["archive"]) for g in out),
                "carry": sum(len(g["carry"]) for g in out),
            }}


def report(res):
    t = res["totals"]
    print(f"SECTION {res['section']}\n")
    for g in res["groups"]:
        weeks = [b["week"] for b in g["archive"]] or ["—"]
        print(f"{g['owner'][:56]:<56} keep {g['keep']['week']}  archive {', '.join(weeks)}")
        for c in g["carry"]:
            print(f"      · {c['text'][:60]}  〔{c['since']} 起〕")
    print("\n" + "=" * 74)
    print(f"blocks {t['blocks']} → {t['keep']} kept, {t['archive']} archived"
          f" | open items carried: {t['carry']}")


# ── Closed human bullets (SKB-039) ───────────────────────────────────────────
# The scaffold copies human bullets forward too, so a `Done` or `Drop` item is re-pasted into
# every new week until someone deletes it by hand. This pass finds those in the newest section.
#
# THREE READ PATHS, AND WHY ALL THREE
#   Drive plain-text export (`get_drive_file_content`) — the only one that prints dropdown chips
#     (`P2 企業講座開發 Drop`). The decision is made here.
#   `inspect_doc_structure` — the only one with indices. Its previews DROP every chip (priority,
#     status, person, file) and stop at 100 characters. The delete ranges come from here.
#   `get_doc_as_markdown` — the only one that marks headings (`#### Finance [Peter Tu](mailto:…)`,
#     which the export prints as the bullet `* Finance Peter Tu`). Headings and person names
#     come from here.
#
# WHAT MAKES A BULLET SAFE TO DELETE — every one of these, or it is skipped and reported
#   1. Its text ends in a closed status and no sub-item under it is still open.
#   2. It contains no heading. A heading carries the owner chip that routes the week, and chips
#      cannot be recreated by any API.
#   3. The bullet and its whole subtree sit verbatim in the PREVIOUS week's section (exactly
#      seven days earlier), under the same heading. That is the proof it is a scaffold copy: the
#      week it was closed in keeps it.
#   4. It matches exactly ONE run of paragraphs in the structure, and the nearest non-empty
#      paragraphs above and below match the export lines above and below it. Counting matches
#      is not enough — a Done line and an open line whose file chip vanished from its preview
#      read the same, and the counts can agree by coincidence (adversarial review, 09-30).

EXPORT_SECTION_RE = re.compile(
    r"^﻿?\s*([A-Z][a-z]{2}\s+\d{1,2},\s*\d{4})\s*(?:\[[a-z]{1,3}\]\s*)*$")
EXPORT_MARK_RE = re.compile(r"\[[a-z]{1,3}\]")      # the export's comment anchors: `[a]` `[d][e]`
BULLET_RE = re.compile(r"^( *)\*\s+(.*?)\s*$")
PRIORITY_RE = re.compile(r"^P\d\s+")
# English is case-SENSITIVE on purpose: the chip says `Done`; "get the migration done" is a task.
# A chip a person adds after a carried item sits straight against its `〕`: `…〔WB 9/7 起〕Done`.
CLOSED_TAIL_RE = re.compile(r"(?:\s+|(?<=〕))(Done|Drop|Dropped|完成|已完成|放棄|取消)$")
# A chip with typed progress after it: `* 課程剪輯   Done 進度：2-4` (the owner, 10-25). Only the
# English chip words, and only between spaces: a typed 完成 mid-line is a verb as often as a
# status (`完成 CRM EDM drip handoff 並上線`).
CLOSED_MID_RE = re.compile(r"(?<=\s)(Done|Drop|Dropped)(?=\s)")
# Thursday's agenda. The scaffold copies it into the new week, where it is last week's agenda
# until Thursday's `agenda` beat writes the new one (the owner, 10-25).
AGENDA_RE = re.compile(r"^〔自動彙整[^〕]*〕\s*本週會議議程$")
OPEN_ANY_RE = re.compile(
    r"(?:^|\s|(?<=〕))(In Progress|Not Started|Pause|Paused|Blocked|WIP|進行中|卡住|還沒開始|暫停)(?=\s|$)",
    re.IGNORECASE)
# A status chip can sit mid-line (`… In Progress 90%` — the 90% is typed text).
STATUS_WORD_RE = re.compile(
    r"(?:(?<=\s)|(?<=〕)|^)(Done|Drop|Dropped|In Progress|Not Started|Pause|Paused|Blocked|WIP|"
    r"完成|已完成|放棄|取消|進行中|卡住|還沒開始|暫停)(?=\s|$)")
# A typed `·` line that is one work item, not an auto summary line: a carried item
# (`· 更新一篇seo〔WB 8/24 起〕Done`) or one that starts with a priority chip (`· P2 Update content
# matrix Drop`). `· 上週 — 甲 完成` is a summary and never matches: no 起 marker, no chip in front.
# It has no sub-items, so it is removed alone; rules 3 and 4 apply exactly as to a bullet.
DOT_ITEM_RE = re.compile(
    r"^()·\s*((?:P\d\s+.*|.*〔\s*(?:WB\s*\d{1,2}/\d{1,2}|\d{4}-W\d{1,2})\s*起\s*〕.*?))\s*$")
MAILTO_NAME_RE = re.compile(r"\[([^\]]+)\]\(mailto:")
MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")


def nonspace(text):
    return re.sub(r"\s+", "", text)


def clean(line):
    """An export line without its comment anchors. The export letters them per document
    (`[a]`, `[b]`, …), so the same copied line reads `X[a]` in one week and `X[c]` in the next,
    and deleting a commented line re-letters everything after it."""
    return EXPORT_MARK_RE.sub("", line).rstrip()


def parse_label(label):
    return datetime.strptime(re.sub(r",\s*", ", ", label.strip()), "%b %d, %Y").date()


def export_sections(lines):
    """[(index, label)] for every bare `Oct 1, 2026` line in the plain-text export."""
    return [(i, m.group(1)) for i, line in enumerate(lines)
            if (m := EXPORT_SECTION_RE.match(line))]


def line_keys(line, names):
    """Every way an export line can appear in a Docs API preview, which drops all chips.

    Priority, status and person chips are each tried both stripped and kept, because the same
    word can be typed rather than chipped. More variants only widen the candidate set; rule 4
    is what makes the final pick safe.
    """
    t = EXPORT_MARK_RE.sub("", line.strip().lstrip("﻿"))
    dot = ""
    if m := BULLET_RE.match(t):
        t = m.group(2)
    elif t.startswith("·"):
        # A typed `·` line keeps its dot in the preview; the chips after it are what go.
        dot, t = "·", t[1:].lstrip()
    variants = set()
    for a in {t, PRIORITY_RE.sub("", t)}:
        for b in {a, STATUS_WORD_RE.sub("", a)}:
            variants.add(b)
            for name in sorted(names, key=len, reverse=True):
                b = b.replace(name, "")
            variants.add(b)
    return {nonspace(dot + v) for v in variants} - {"", dot}


def heading_keys(markdown, names):
    """Keys of every markdown heading, in the export's shape: person chips gone, links → text."""
    keys = set()
    for line in markdown.split("\n"):
        if m := MD_HEADING_RE.match(line.strip()):
            t = FOOTNOTE_RE.sub("", m.group(1))
            t = re.sub(r"\[[^\]]*\]\(mailto:[^)]*\)", "", t)
            t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
            t = nonspace(t.replace("\\", "").replace("*", ""))
            if t:
                keys.add(t)
    return keys


def closed_bullets(lines, names, headings):
    """Which Done/Drop bullets in the newest section may be removed (rules 1–3), and which may not."""
    names, headings = set(names), set(headings)
    marks = export_sections(lines)
    res = {"section": marks[0][1] if marks else None, "previous": None, "refused": None,
           "closed": [], "skipped": [], "section_lines": [], "done_blocks": []}
    if len(marks) < 2:
        res["refused"] = "fewer than two dated sections — there is nothing to prove a copy against"
        return res
    (s0, label), (s1, prev_label) = marks[0], marks[1]
    res["previous"] = prev_label
    if parse_label(prev_label) != parse_label(label) - timedelta(days=7):
        res["refused"] = (f"the section after {label} is {prev_label}, not the week before —"
                          f" a stray date line or a missing week")
        return res
    # A stray date line inside the new week shows up as last week's label twice in a row. Only the
    # LEADING run of sections is checked: the export covers every tab, and the 封存 tab repeats
    # week labels further down on purpose.
    if len(marks) > 2 and parse_label(marks[2][1]) >= parse_label(prev_label):
        res["refused"] = (f"the section after {prev_label} is {marks[2][1]}, not an older week —"
                          f" a stray date line would move the section boundary")
        return res
    s2 = marks[2][0] if len(marks) > 2 else len(lines)
    sec = [clean(l) for l in lines[s0 + 1:s1]]
    prev = [clean(l) for l in lines[s1 + 1:s2]]
    res["section_lines"] = sec

    def heading(line):
        return line.lstrip("﻿").startswith("#") or bool(line_keys(line, names) & headings)

    def owner(block, i):
        return next((block[k].strip() for k in range(i - 1, -1, -1)
                     if block[k].strip() and heading(block[k])), "(section top)")

    def copied(tree, entry):
        return any(prev[k:k + len(tree)] == tree and owner(prev, k) == entry["owner"]
                   for k in range(len(prev) - len(tree) + 1))

    def status_of(text):
        """The closing chip of one bullet's text, or None. A line that also says it is open is not closed."""
        if tail := CLOSED_TAIL_RE.search(text):
            return tail
        if not OPEN_ANY_RE.search(text):
            return CLOSED_MID_RE.search(text)
        return None

    # A formatted block's label bullets and their sub-bullets are the machine's summary
    # (`* 上週` / `    * 甲 完成`): a 完成 there is a report, never a bullet to delete.
    machine = set().union(*(walk_block(sec, k)[2] for k, l in enumerate(sec) if "〔自動彙整" in l))

    i = 0
    while i < len(sec):
        if i in machine:
            i += 1
            continue
        if AGENDA_RE.match(sec[i].strip()):
            j = i + 1
            while j < len(sec) and sec[j].strip().startswith("·"):
                j += 1
            tree = sec[i:j]
            entry = {"at": i, "line": sec[i].strip(), "status": "上週的議程",
                     "owner": owner(sec, i), "lines": tree}
            if copied(tree, entry):
                res["closed"].append(entry)
            else:
                res["skipped"].append({**entry, "reason": f"not in {prev_label} as-is — this"
                                                          f" week's agenda, not a copy"})
            i = j
            continue
        m = BULLET_RE.match(sec[i]) or DOT_ITEM_RE.match(sec[i])
        tail = None
        if m:
            tail = status_of(m.group(2)) if m.re is BULLET_RE else CLOSED_TAIL_RE.search(m.group(2))
        if not tail:
            i += 1
            continue
        depth, j = len(m.group(1)), i + 1
        if m.re is BULLET_RE:
            while j < len(sec) and (c := BULLET_RE.match(sec[j])) and len(c.group(1)) > depth:
                j += 1
        tree = sec[i:j]
        entry = {"at": i, "line": m.group(2), "status": tail.group(1),
                 "owner": owner(sec, i), "lines": tree}
        if any(heading(l) for l in tree):
            res["skipped"].append({**entry, "reason": "a heading sits inside it — heading chips"
                                                      " route the week and cannot be recreated"})
            i = j
            continue
        open_child = next((l.strip() for l in tree[1:] if OPEN_ANY_RE.search(l)), None)
        if open_child:
            res["skipped"].append({**entry, "reason": f"an item under it is still open: {open_child}"})
            i += 1          # its own closed sub-items still get their turn
            continue
        if not copied(tree, entry):
            res["skipped"].append({**entry, "reason": f"not in {prev_label} as-is under the same"
                                                      f" heading — not a scaffold copy, left alone"})
        else:
            res["closed"].append(entry)
        i = j

    # A heading whose chipped items are ALL Done/Drop, none open, looks finished as a whole
    # (`Claude Code 課程` after the course launched — the owner closed it by hand, 10-25). Only a
    # person knows the project is over, so it is asked about, never deleted.
    # A department heading (`#Sales` with its owner's chip) routes the week and is never offered.
    heads = [k for k, line in enumerate(sec) if line.strip() and heading(line)] + [len(sec)]
    for a, b in zip(heads, heads[1:]):
        if sec[a].lstrip("﻿").startswith("#") or any(n in sec[a] for n in names):
            continue
        done = opened = 0
        for k in range(a + 1, b):
            m = BULLET_RE.match(sec[k]) or DOT_ITEM_RE.match(sec[k])
            if not m or k in machine:
                continue
            if OPEN_ANY_RE.search(m.group(2)):
                opened += 1
            elif status_of(m.group(2)):
                done += 1
        if done >= 2 and not opened:
            res["done_blocks"].append({"heading": sec[a].strip(), "done": done})
    return res


def preview_matches(paragraph, keys):
    """A preview longer than 100 characters is cut off with no trailing newline: compare a prefix."""
    t = paragraph.get("text_preview", "")
    pk = nonspace(t)
    if not pk:
        return False
    truncated = not t.endswith("\n")
    return any(k == pk or (truncated and k.startswith(pk)) for k in keys)


def assert_disjoint(located):
    for a, b in zip(located, located[1:]):
        if b["end_index"] > a["start_index"]:
            raise SystemExit("tidy --closed: overlapping ranges — refusing to delete anything")


def locate_closed(res, paragraphs, names):
    """Pin each closed bullet to one [start_index, end_index) range (rule 4), highest first."""
    if res["refused"]:
        return res
    label, prev_label = res["section"], res["previous"]
    heads = [k for k, p in enumerate(paragraphs)
             if nonspace(p.get("text_preview", "")) == nonspace(label)]
    if len(heads) != 1:
        raise SystemExit(f"tidy --closed: expected one {label!r} heading in the structure,"
                         f" found {len(heads)} — wrong tab?")
    start = heads[0] + 1
    end = next((k for k in range(start, len(paragraphs))
                if EXPORT_SECTION_RE.match(paragraphs[k].get("text_preview", "").strip())), None)
    if end is None or nonspace(paragraphs[end]["text_preview"]) != nonspace(prev_label):
        raise SystemExit(f"tidy --closed: in the structure the section after {label!r} is not"
                         f" {prev_label!r} — the export and the structure disagree")
    if sum(nonspace(p.get("text_preview", "")) == nonspace(prev_label) for p in paragraphs) != 1:
        raise SystemExit(f"tidy --closed: {prev_label!r} appears more than once in the structure —"
                         f" refusing, the section boundary cannot be trusted")

    def filled(k):
        return bool(nonspace(paragraphs[k].get("text_preview", "")))

    sec = res["section_lines"]
    located, skipped = [], list(res["skipped"])
    for entry in res["closed"]:
        i, n = entry["at"], len(entry["lines"])
        above = next((sec[k] for k in range(i - 1, -1, -1) if sec[k].strip()), label)
        below = next((sec[k] for k in range(i + n, len(sec)) if sec[k].strip()), prev_label)
        spots = []
        for p in range(start, end - n + 1):
            if not all(preview_matches(paragraphs[p + d], line_keys(entry["lines"][d], names))
                       for d in range(n)):
                continue
            q = next((k for k in range(p - 1, -1, -1) if filled(k)), None)
            r = next((k for k in range(p + n, len(paragraphs)) if filled(k)), None)
            if q is None or not preview_matches(paragraphs[q], line_keys(above, names)):
                continue
            if r is None or not preview_matches(paragraphs[r], line_keys(below, names)):
                continue
            spots.append(p)
        if len(spots) != 1:
            skipped.append({**entry, "reason": f"matches {len(spots)} places in the Doc with the"
                                               f" lines around it — needs exactly one"})
            continue
        p = spots[0]
        located.append({**entry, "start_index": paragraphs[p]["start_index"],
                        "end_index": paragraphs[p + n - 1]["end_index"]})
    located.sort(key=lambda e: e["start_index"], reverse=True)
    assert_disjoint(located)
    return {**res, "closed": located, "skipped": skipped}


# ── step 8: the kept block as bullets (the owner, 10-25) ─────────────────────
# `· 上週 — 甲 完成 ／ 乙 WIP` → a `上週` bullet with `甲 完成` and `乙 WIP` as sub-bullets, and the
# carried items re-nested under a `還沒收掉的` bullet. The stamp stays a plain line: it is the key.
TYPED_ROW_RE = re.compile(r"^·\s*(上週|本週|數字|卡關|沒寫|還沒收掉的)\s*—\s*(.*?)\s*$")


def unmd(text):
    """Markdown text as the Doc holds it: no person links, link targets or escapes."""
    s = re.sub(r"\[([^\]]*)\]\(mailto:[^)]*\)", "", FOOTNOTE_RE.sub("", text))
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    return re.sub(r"\\(.)", r"\1", s)


def md_text(line):
    """A markdown line as the Doc holds its text: no bullet or heading marks either."""
    s = unmd(line)
    if c := CHILD_RE.match(s):
        s = c.group(2)
    return s.strip().lstrip("#").strip()


def utf16(text):
    """Docs indices count UTF-16 code units: an emoji is two."""
    return len(text.encode("utf-16-le")) // 2


def format_plan(lines, paragraphs, tab_id, target=None):
    """The batch_update_doc operations that turn each typed kept block into bullets, highest first.

    A block is pinned the way step 7 pins a bullet: its stamp and every summary line must match
    the structure's previews at exactly one place in the section, and the carried items under it
    must be the very next paragraphs. Anything else is skipped with a reason, never guessed."""
    marks = sections(lines)
    if not marks:
        raise SystemExit("tidy --format: no dated week section found — is this the right tab?")
    hit = [(i, lab) for i, lab in marks if lab == target] if target else marks[:1]
    if not hit:
        raise SystemExit(f"tidy --format: section {target!r} not in the Doc")
    start, label = hit[0]
    sec = lines[start:next((i for i, _ in marks if i > start), len(lines))]

    heads = [k for k, p in enumerate(paragraphs)
             if nonspace(p.get("text_preview", "")) == nonspace(label)]
    if len(heads) != 1:
        raise SystemExit(f"tidy --format: expected one {label!r} heading in the structure,"
                         f" found {len(heads)} — wrong tab?")
    stop = next((k for k in range(heads[0] + 1, len(paragraphs))
                 if EXPORT_SECTION_RE.match(paragraphs[k].get("text_preview", "").strip())),
                len(paragraphs))
    filled = [k for k in range(heads[0] + 1, stop) if nonspace(paragraphs[k].get("text_preview", ""))]

    res = {"section": label, "blocks": [], "skipped": [], "ops": []}
    for s in (k for k, line in enumerate(sec) if "〔自動彙整" in line):
        if AGENDA_RE.match(sec[s].strip()):
            continue                    # last week's agenda goes whole in step 7, this week's stays
        last, rows, _ = walk_block(sec, s)
        body = [k for k in range(s + 1, last + 1) if sec[k].strip()]
        if not any(sec[k].strip().startswith("·") for k in body):
            continue                    # already bullets (or empty): nothing to do
        # Any typed line re-types the whole block. Since 10-26 rollup writes bullets, and the one
        # typed line is usually step 5's `· 還沒收掉的 —` under them.
        entry = {"owner": owner_of(sec, s), "stamp": sec[s].strip(), "rows": rows}
        why = None
        if any(not TYPED_ROW_RE.match(r) for r in rows):
            why = "a line in it is not a summary line (上週 · 本週 · 數字 · 卡關 · 沒寫 · 還沒收掉的)"
        elif any(FOOTNOTE_RE.search(sec[k]) for k in body):
            why = "a comment is anchored in it — re-typing the line would drop the comment"
        elif any(re.search(r"\]\([^)]*\)", sec[k]) for k in body):
            why = "a line in it holds a link — re-typing would drop the link"
        kids = []
        if not why and is_line(rows[-1], CARRY_LABEL):
            j = last + 1
            while j < len(sec) and (not sec[j].strip() or CARRIED_BULLET_RE.match(sec[j])):
                if sec[j].strip():
                    kids.append(j)
                j += 1
        if why:
            res["skipped"].append({**entry, "reason": why})
            continue

        want = [nonspace(md_text(sec[k])) for k in [s] + body]
        spots = [i for i in range(len(filled) - len(want) + 1)
                 if all(preview_matches(paragraphs[filled[i + d]], {want[d]}) for d in range(len(want)))]
        if len(spots) > 1:
            # Rollup stamps every department alike, and two short blocks can read the same: the
            # heading above breaks the tie.
            above = next((nonspace(md_text(sec[k])) for k in range(s - 1, -1, -1) if sec[k].strip()), "")
            spots = [i for i in spots if i and above.startswith(
                nonspace(paragraphs[filled[i - 1]].get("text_preview", "")))]
        if len(spots) != 1:
            res["skipped"].append({**entry, "reason": f"matches {len(spots)} places in the Doc —"
                                                      f" needs exactly one"})
            continue
        i = spots[0]
        rowps = [paragraphs[filled[i + d]] for d in range(1, len(want))]
        q = i + len(want)
        kidps = [paragraphs[filled[q + d]] for d in range(len(kids)) if q + d < len(filled)]
        after = paragraphs[filled[q + len(kids)]].get("text_preview", "") if q + len(kids) < len(filled) else ""
        if len(kidps) != len(kids) or not all("起〕" in p.get("text_preview", "") or
                                              not p.get("text_preview", "").endswith("\n")
                                              for p in kidps) or (kids and "起〕" in after):
            res["skipped"].append({**entry, "reason": "the carried items under it do not line up"
                                                      " with the Doc — count or text differs"})
            continue

        out = []
        for r in rows:
            m = TYPED_ROW_RE.match(r)
            out.append(m.group(1))
            if m.group(1) != CARRY_LABEL:
                out += ["\t" + unmd(x) for x in split_items(r)]
        new = "\n".join(out)
        r0 = rowps[0]["start_index"]
        r1 = (kidps[0]["start_index"] if kidps else rowps[-1]["end_index"]) - 1
        tail = (kidps[-1] if kidps else rowps[-1])["end_index"] - 1
        grow = utf16(new) - (r1 - r0) + len(kidps)
        ops = [{"type": "create_bullet_list", "start_index": r0, "end_index": tail, "list_type": "NONE"},
               {"type": "update_paragraph_style", "start_index": r0, "end_index": tail,
                "indent_start": 0, "indent_first_line": 0}]
        ops += [{"type": "insert_text", "index": p["start_index"], "text": "\t"} for p in reversed(kidps)]
        ops += [{"type": "delete_text", "start_index": r0, "end_index": r1},
                {"type": "insert_text", "index": r0, "text": new},
                {"type": "create_bullet_list", "start_index": r0, "end_index": tail + grow,
                 "list_type": "UNORDERED"}]
        res["blocks"].append({**entry, "start_index": r0, "items": len(out) - len(rows),
                              "carried": len(kidps), "ops": ops})
    res["blocks"].sort(key=lambda b: b["start_index"], reverse=True)
    for a, b in zip(res["blocks"], res["blocks"][1:]):
        if b["ops"][0]["end_index"] >= a["start_index"]:
            raise SystemExit("tidy --format: overlapping blocks — refusing to write anything")
    res["ops"] = [{**op, "tab_id": tab_id} for b in res["blocks"] for op in b.pop("ops")]
    return res


def format_check(plan, lines):
    """After the write: each formatted block reads back as the same summary, as bullets."""
    marks = sections(lines)
    hit = [i for i, lab in marks if lab == plan["section"]]
    if not hit:
        return {"ok": False, "problems": [f"section {plan['section']!r} not in the Doc"]}
    start = hit[0]
    sec = lines[start:next((i for i, _ in marks if i > start), len(lines))]
    got = {}
    for s in (k for k, line in enumerate(sec) if "〔自動彙整" in line and not AGENDA_RE.match(line.strip())):
        last, rows, machine = walk_block(sec, s)
        typed = any(sec[k].strip().startswith("·") for k in range(s + 1, last + 1))
        got.setdefault((owner_of(sec, s), sec[s].strip()), []).append((rows, typed))
    problems = []
    for b in plan["blocks"]:
        seen = got.get((b["owner"], b["stamp"]), [])
        if len(seen) != 1:
            problems.append(f"{b['owner']}: {len(seen)} blocks stamped {b['stamp']} after the write")
        elif seen[0][1]:
            problems.append(f"{b['owner']}: still has typed · lines")
        elif [split_items(r) or r for r in seen[0][0]] != [split_items(r) or r for r in b["rows"]]:
            problems.append(f"{b['owner']}: the summary reads differently after the write")
    return {"ok": not problems, "problems": problems}


def plan_signature(res):
    """What must be identical between the plan and the fresh re-check just before deleting."""
    return json.loads(json.dumps({
        "section": res["section"], "section_lines": res["section_lines"],
        "closed": [[e["start_index"], e["end_index"], e["lines"]] for e in res["closed"]]}))


def expect_same(plan, res):
    """Refuse unless the fresh read reproduces the plan exactly: same section text (chips
    included — so no status changed) and the same ranges (so no index moved)."""
    if plan_signature(plan) != plan_signature(res):
        raise SystemExit("tidy --closed --expect: the section changed since the plan —"
                         " delete nothing, report partial")


def postcheck(plan, lines):
    """After the delete: the section must equal the plan's section minus exactly the planned lines."""
    marks = export_sections(lines)
    hit = [k for k, (_, lab) in enumerate(marks) if lab == plan["section"]]
    if not hit:
        raise SystemExit(f"tidy --closed --postcheck: {plan['section']!r} not in the export")
    a = marks[hit[0]][0] + 1
    b = marks[hit[0] + 1][0] if hit[0] + 1 < len(marks) else len(lines)
    gone = {e["at"] + d for e in plan["closed"] for d in range(len(e["lines"]))}
    want = [l for k, l in enumerate(plan["section_lines"]) if k not in gone and l.strip()]
    got = [clean(l) for l in lines[a:b] if l.strip()]
    if want != got:
        k = next((k for k, (x, y) in enumerate(zip(want, got)) if x != y), min(len(want), len(got)))
        raise SystemExit(f"tidy --closed --postcheck: the section is not the plan minus the deleted"
                         f" lines (first difference at non-blank line {k}: expected"
                         f" {want[k] if k < len(want) else '(end)'!r}, found"
                         f" {got[k] if k < len(got) else '(end)'!r}). Restore from File ›"
                         f" Version history; the previous section still holds every deleted line")
    return {"section": plan["section"], "deleted_lines": len(gone), "unchanged_lines": len(got)}


def read_tool_file(path):
    """Accept a raw file or a saved MCP tool result (`{"result": "..."}`)."""
    raw = open(path, encoding="utf-8").read()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and isinstance(obj.get("result"), str):
            return obj["result"]
    except ValueError:
        pass
    return raw


def load_structure(path):
    """`inspect_doc_structure(detailed=true)` output → its paragraph elements, in order."""
    raw = read_tool_file(path)
    obj, _ = json.JSONDecoder().raw_decode(raw[raw.index("{"):])
    return [e for e in obj.get("elements", []) if e.get("type") == "paragraph"]


def load_export(path):
    """`get_drive_file_content` output → lines of the document body."""
    raw = read_tool_file(path).replace("\r\n", "\n")
    if "--- CONTENT ---" in raw:
        raw = raw.split("--- CONTENT ---", 1)[1]
    return raw.split("\n")


def report_closed(res):
    print(f"SECTION {res['section']}  (proved against {res['previous']})\n")
    if res.get("refused"):
        print(f"  REFUSED — {res['refused']}")
    for e in res["closed"]:
        subs = len(e["lines"]) - 1
        print(f"  DELETE [{e['start_index']},{e['end_index']})  {e['line'][:60]}"
              + (f"  +{subs} sub-items" if subs else ""))
    for e in res["skipped"]:
        print(f"  keep   {e['line'][:60]}  — {e['reason']}")
    for b in res.get("done_blocks", []):
        print(f"  ask    {b['heading'][:60]}  — all {b['done']} chipped items Done/Drop, none open:"
              f" close the whole block? (a person's call)")
    print(f"\nclosed bullets to remove: {len(res['closed'])} | left alone: {len(res['skipped'])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", help="markdown file (default: stdin)")
    ap.add_argument("--section", help="target section label; default = newest dated section")
    ap.add_argument("--report", action="store_true", help="human-readable instead of JSON")
    ap.add_argument("--closed", action="store_true",
                    help="SKB-039: find Done/Drop bullets to remove")
    ap.add_argument("--export", help="get_drive_file_content output (plain text, chips rendered);"
                                      " without --closed it keeps Done/Drop items off the carry")
    ap.add_argument("--structure", help="inspect_doc_structure(detailed=true) output for the tab")
    ap.add_argument("--markdown", help="get_doc_as_markdown output — headings and person names")
    ap.add_argument("--expect", help="plan.json from the first --closed run: refuse unless identical")
    ap.add_argument("--postcheck", help="plan.json: after the delete, verify the section")
    ap.add_argument("--format", action="store_true",
                    help="step 8: the batch_update_doc operations that make each typed kept block"
                         " bullets (needs --input, --structure, --tab)")
    ap.add_argument("--tab", help="--format: the tab id every operation must carry")
    ap.add_argument("--format-check", help="plan.json from --format: after the write, verify it")
    args = ap.parse_args()

    if args.format or args.format_check:
        lines = (read_tool_file(args.input) if args.input else sys.stdin.read()).split("\n")
        if args.format_check:
            out = format_check(json.load(open(args.format_check, encoding="utf-8")), lines)
        else:
            if not (args.structure and args.tab):
                ap.error("--format needs --structure and --tab")
            out = format_plan(lines, load_structure(args.structure), args.tab, args.section)
        json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    if args.closed:
        if not args.export:
            ap.error("--closed needs --export")
        if args.postcheck:
            plan = json.load(open(args.postcheck, encoding="utf-8"))
            if args.section and plan["section"] != args.section:
                raise SystemExit(f"tidy --closed --postcheck: plan is for {plan['section']!r}")
            json.dump(postcheck(plan, load_export(args.export)), sys.stdout, ensure_ascii=False)
            print()
            return
        if not (args.structure and args.markdown):
            ap.error("--closed needs --structure and --markdown")
        md = read_tool_file(args.markdown)
        names = set(MAILTO_NAME_RE.findall(md))
        res = closed_bullets(load_export(args.export), names, heading_keys(md, names))
        if args.section and res["section"] != args.section:
            raise SystemExit(f"tidy --closed: export's newest section is {res['section']!r},"
                             f" not {args.section!r} — refusing")
        res = locate_closed(res, load_structure(args.structure), names)
        if args.expect:
            expect_same(json.load(open(args.expect, encoding="utf-8")), res)
        if args.report:
            report_closed(res)
        else:
            json.dump(res, sys.stdout, ensure_ascii=False, indent=2)
            print()
        return

    raw = read_tool_file(args.input) if args.input else sys.stdin.read()
    # --export (the Drive plain-text export) lets the carry see Done/Drop chips the markdown drops.
    res = analyse(raw.split("\n"), args.section,
                  export_lines=load_export(args.export) if args.export else None)
    if args.report:
        report(res)
    else:
        json.dump(res, sys.stdout, ensure_ascii=False, indent=2)
        print()


if __name__ == "__main__":
    main()
