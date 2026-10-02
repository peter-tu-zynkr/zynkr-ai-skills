"""Tests for tidy_blocks.py. Run: python3 test_tidy_blocks.py

WHY THESE ARE ADVERSARIAL
    SKB-029 shipped with 28 green assertions and still threw on its first live run, because the
    mock `Body` let `removeChild` take any element — it tested the happy path instead of the
    constraint that actually existed. A mock that cannot fail proves nothing.

    So every test here is written against the thing that would go WRONG, not the thing that
    should go right: a human line pulled into a block, a heading that fails to split a group,
    blocks arriving out of order, a done item resurrected, an item carried twice. Each one is
    checked to fail when the relevant line of tidy_blocks.py is broken — see MUTATIONS at the
    bottom, which is a runnable proof, not a comment.
"""
import re
import subprocess
import sys
from pathlib import Path

import tidy_blocks as T

HERE = Path(__file__).resolve().parent
FAILURES = []


def check(name, got, want):
    if got != want:
        FAILURES.append(f"{name}\n      got:  {got!r}\n      want: {want!r}")


def analyse(md, today=None):
    return T.analyse(md.split("\n"), today=today)


# ── 1. a human's lines must never be pulled into a block ─────────────────────
# The live Doc puts auto `·` lines directly under the heading and the owner's own `-` bullets
# below them. Over-reaching by one line here means the tidy deletes someone's work.
HUMAN = """\
## Sep 24, 2026

### #Content [Sam Rivera](mailto:owner-a@example.com)

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 本週 — 甲 ／ 乙

〔自動彙整 WB 9/14 · 09-15 09:00〕

· 本週 — 丙

- Update content matrix
- SEO planning
"""
r = analyse(HUMAN)
g = r["groups"][0]
check("human bullets stay out of the kept block",
      [l for l in g["keep"]["lines"] if l.strip().startswith("-")], [])
check("human bullets stay out of archived blocks",
      [l for b in g["archive"] for l in b["lines"] if l.strip().startswith("-")], [])
check("archived block stops before the human bullets",
      [l.strip() for l in g["archive"][0]["lines"] if l.strip()],
      ["〔自動彙整 WB 9/14 · 09-15 09:00〕", "· 本週 — 丙"])

# The boundary must hold even when a `·` line comes AFTER the human bullet — a person can type a
# middle dot too. Without this case the boundary test above could never fail: an over-reaching
# extent only moves `end` on a `·` line, and there was none past the human bullets.
HUMAN_DOT = """\
## Sep 24, 2026

### #Content [Sam Rivera](mailto:owner-a@example.com)

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 本週 — 甲

- Update content matrix

· a note a person typed with a middle dot
"""
r = analyse(HUMAN_DOT)
check("a human line ends the block even when a `·` line follows it",
      [l.strip() for l in r["groups"][0]["keep"]["lines"] if l.strip()],
      ["〔自動彙整 WB 9/21 · 09-22 09:00〕", "· 本週 — 甲"])

# ── 2. a heading between two blocks must split the group ─────────────────────
# Without the split, two departments' blocks merge and one department's current block gets
# archived as if it were an older copy of the other's.
TWO_DEPTS = """\
## Sep 24, 2026

### #A [a](mailto:a@z.ai)

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 本週 — 甲

### #B [b](mailto:b@z.ai)

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 本週 — 乙
"""
r = analyse(TWO_DEPTS)
check("a heading splits groups", len(r["groups"]), 2)
check("group 1 owner", r["groups"][0]["owner"], "#A a")
check("group 2 owner", r["groups"][1]["owner"], "#B b")
check("neither group archives anything", r["totals"]["archive"], 0)

# ── 3. write order must not be trusted ───────────────────────────────────────
# `rollup` prepends, so newest is normally first. A hand-edit or a re-run can reverse that, and
# keeping blocks[0] blindly would archive the CURRENT week and leave a stale block in its place.
OUT_OF_ORDER = """\
## Sep 24, 2026

### #A [a](mailto:a@z.ai)

〔自動彙整 WB 9/7 · 09-08 09:00〕

· 本週 — 舊

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 本週 — 新
"""
r = analyse(OUT_OF_ORDER, today=T.date(2026, 9, 25))
check("keeps the newest even when written last", r["groups"][0]["keep"]["week"], "WB 9/21")
check("archives the older one", [b["week"] for b in r["groups"][0]["archive"]], ["WB 9/7"])

# ── 4. both week shapes must order correctly during the changeover ───────────
# Sections written before 2026-09-15 carry `2026-W38`; after, `WB 9/14`. Both are live at once,
# and an ordering that mishandles either picks the wrong block to keep.
check("ISO week key", T.week_key("2026-W38", "09-15"), (2026, 38))
check("WB key equals the ISO week of that Monday",
      T.week_key("WB 9/14", "09-15", today=T.date(2026, 9, 15)), (2026, 38))
check("WB and ISO for the same week compare equal",
      T.week_key("WB 9/14", "09-15", today=T.date(2026, 9, 15)) == T.week_key("2026-W38", ""),
      True)
check("a later WB sorts above an earlier ISO",
      T.week_key("WB 9/21", "09-22", today=T.date(2026, 9, 22)) > T.week_key("2026-W38", ""),
      True)

MIXED = """\
## Sep 24, 2026

### #A [a](mailto:a@z.ai)

〔自動彙整 2026-W38 · 09-15 09:00〕

· 本週 — 舊

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 本週 — 新
"""
r = analyse(MIXED, today=T.date(2026, 9, 25))
check("mixed shapes keep the newer WB block", r["groups"][0]["keep"]["week"], "WB 9/21")

# ── 5. a done item must never be carried ─────────────────────────────────────
# An earlier pass matched only 完成 and missed the English `Done`, over-counting open items by 8.
DONE = """\
## Sep 24, 2026

### #A [a](mailto:a@z.ai)

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 上週 — 甲乙 完成 ／ 丙丁 Done

· 本週 — 戊己

〔自動彙整 WB 9/14 · 09-15 09:00〕

· 本週 — 甲乙 ／ 丙丁 ／ 庚辛
"""
r = analyse(DONE, today=T.date(2026, 9, 25))
carried = [c["text"] for c in r["groups"][0]["carry"]]
check("完成 item not carried", "甲乙" in carried, False)
check("English Done item not carried", "丙丁" in carried, False)
check("an item nobody closed IS carried", carried, ["庚辛"])
check("the carried item records where it came from",
      r["groups"][0]["carry"][0]["since"], "WB 9/14")

# The case above cannot catch a lost `Done`: its done report sits in the KEPT block, whose items
# are suppressed as still visible anyway. Here the report sits in an ARCHIVED block, so only the
# done-detection stands between `丙丁` and the carried list.
DONE_ARCHIVED = """\
## Oct 1, 2026

### #A [a](mailto:a@z.ai)

〔自動彙整 WB 9/28 · 09-29 09:00〕

· 本週 — 新新

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 上週 — 丙丁 Done ／ 甲乙 完成

· 本週 — 戊己

〔自動彙整 WB 9/14 · 09-15 09:00〕

· 本週 — 甲乙 ／ 丙丁 ／ 庚辛
"""
r = analyse(DONE_ARCHIVED, today=T.date(2026, 10, 2))
check("an English Done reported in an ARCHIVED block closes the item",
      [c["text"] for c in r["groups"][0]["carry"]], ["戊己", "庚辛"])

# ── 6. an item already visible in the kept block is not carried twice ────────
# The carried list exists to rescue items that would DISAPPEAR when their block is archived.
# An item still printed in the kept block has not disappeared, so repeating it is just noise.
ALREADY = """\
## Sep 24, 2026

### #A [a](mailto:a@z.ai)

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 上週 — 甲甲 進行中

· 本週 — 乙乙

〔自動彙整 WB 9/14 · 09-15 09:00〕

· 本週 — 甲甲 ／ 丙丙
"""
r = analyse(ALREADY, today=T.date(2026, 9, 25))
check("item visible in the kept block's 上週 is not carried",
      [c["text"] for c in r["groups"][0]["carry"]], ["丙丙"])

# A two-character Chinese item is real work and must survive the length floor.
SHORT = """\
## Sep 24, 2026

### #A [a](mailto:a@z.ai)

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 本週 — 甲甲

〔自動彙整 WB 9/14 · 09-15 09:00〕

· 本週 — 發文 ／ 對帳
"""
r = analyse(SHORT, today=T.date(2026, 9, 25))
check("short Chinese items are not dropped by the length floor",
      [c["text"] for c in r["groups"][0]["carry"]], ["發文", "對帳"])

# ── 7. the trailing status word must not make one item look like two ─────────
check("status stripped from the tail", T.strip_status("每週發文 完成"), "每週發文")
check("status stripped, English", T.strip_status("outreach Done"), "outreach")
check("a bare item is untouched", T.strip_status("每週發文"), "每週發文")
check("status word inside the text is kept",
      T.strip_status("完成 PM skills"), "完成 PM skills")

# ── 8. boilerplate must not dominate the carried list ────────────────────────
NOISY = """\
## Sep 24, 2026

### #A [a](mailto:a@z.ai)

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 本週 — 甲

〔自動彙整 WB 9/14 · 09-15 09:00〕

· 本週 — 例行性 ／ 無 ／ — ／ 真的要做的事
"""
r = analyse(NOISY, today=T.date(2026, 9, 25))
check("noise filtered, real item kept",
      [c["text"] for c in r["groups"][0]["carry"]], ["真的要做的事"])

# ── 9. a URL's slashes must not split one item into several ──────────────────
URL = """\
## Sep 24, 2026

### #A [a](mailto:a@z.ai)

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 本週 — 甲

〔自動彙整 WB 9/14 · 09-15 09:00〕

· 本週 — 看 [板子](https://example.com/a/b/c) 這件事
"""
r = analyse(URL, today=T.date(2026, 9, 25))
check("a URL is not an item separator", len(r["groups"][0]["carry"]), 1)

# ── 10. degenerate inputs must not crash or invent work ──────────────────────
ONE_BLOCK = """\
## Sep 24, 2026

### #A [a](mailto:a@z.ai)

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 本週 — 甲
"""
r = analyse(ONE_BLOCK, today=T.date(2026, 9, 25))
check("a lone block archives nothing", r["totals"]["archive"], 0)
check("a lone block carries nothing", r["totals"]["carry"], 0)

NO_BLOCKS = """\
## Sep 24, 2026

### #A [a](mailto:a@z.ai)

- just a human bullet
"""
r = analyse(NO_BLOCKS)
check("a section with no blocks yields no groups", r["groups"], [])
check("a section with no blocks is a no-op", r["totals"]["blocks"], 0)

# ── 11. the newest section is the target, not the first one that parses ──────
TWO_SECTIONS = """\
## Sep 24, 2026

### #A [a](mailto:a@z.ai)

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 本週 — 新

## Sep 17, 2026

### #A [a](mailto:a@z.ai)

〔自動彙整 WB 9/14 · 09-15 09:00〕

· 本週 — 舊
"""
r = analyse(TWO_SECTIONS, today=T.date(2026, 9, 25))
check("targets the newest section", r["section"], "Sep 24, 2026")
check("does not reach into the previous section", r["totals"]["blocks"], 1)

# ── 12. headings that are not real HEADING2 still count as week sections ─────
# Only 23 of the live Doc's 34 week headings are real HEADING2; a level-locked regex skips 11.
check("h3 week heading is still a section",
      bool(T.SECTION_RE.match("### Sep 17, 2026")), True)
check("h4 week heading is still a section",
      bool(T.SECTION_RE.match("#### Apr 9, 2026")), True)

# ── 13. a carried list must survive its block being archived (SKB-039) ──────
# The bug this fixes: only `· 本週` was read from an archived block, so everything a previous tidy
# had rescued onto `· 還沒收掉的 —` vanished the next Friday, done or not. Measured on the live
# Oct 1 section: 26 open items would have gone, nine of one owner's dating from WB 8/24.
CARRIED = """\
## Oct 1, 2026[^c10]

### #A [a](mailto:a@z.ai)

〔自動彙整 WB 9/28 · 09-29 09:00〕

· 本週 — 新事

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 上週 — 舊事 完成 ／ 半路的事 進行中 ／ 報過的事 沒寫狀態 ／ 完成 CRM handoff 進行中 ／ Get Done list 進行中 ／ 課程作業 完成 60%

· 本週 — 中事 ／ 完成Claude code QC

〔自動彙整 WB 9/14 · 09-15 09:00〕

· 上週 — 專案W2進度-90% 完成 ／ Claude code QC 完成

· 本週 — 專案W2進度 ／ 課程作業

· 還沒收掉的 —

· 甲件事〔WB 8/24 起〕

· 舊事〔WB 8/31 起〕

· 跟 客戶甲 — 導入諮詢 聊〔WB 9/7 起〕

· 乙件事[^c5]〔2026-W37 起〕

· 丙件事〔WB 9/7 起〕[^c6]

· 丁件事 完成〔WB 9/7 起〕

· 請假一週〔WB 9/7 起〕

· 請假制度草案〔WB 9/7 起〕
"""
r = analyse(CARRIED, today=T.date(2026, 10, 2))
check("a comment on the week heading does not hide the section", r["section"], "Oct 1, 2026")
c = {x["text"]: x["since"] for x in r["groups"][0]["carry"]}
check("a carried item is carried again", "甲件事" in c, True)
check("it keeps the week it was FIRST seen, not the archived block's", c.get("甲件事"), "WB 8/24")
check("a carried item reported done in an archived 上週 is not carried", "舊事" in c, False)
check("an item containing an em dash is still one carried item",
      c.get("跟 客戶甲 — 導入諮詢 聊"), "WB 9/7")
check("a comment footnote is not part of the item", c.get("乙件事"), "2026-W37")
check("a comment at the END of a carried line does not drop it", c.get("丙件事"), "WB 9/7")
check("an item marked done inline on its carried line is not carried",
      "丁件事 完成" in c or "丁件事" in c, False)
check("being on leave is not a task", "請假一週" in c, False)
check("the archived block's own 本週 is still carried", c.get("中事"), "WB 9/21")
check("done-words are ignored when comparing: '完成X' is closed by 'X 完成'",
      "完成Claude code QC" in c, False)
check("punctuation and digits are ignored when comparing: 'W2進度' closed by 'W2進度-90% 完成'",
      "專案W2進度" in c, False)
check("an item reported still open, and not planned again, is carried", c.get("半路的事"), "WB 9/21")
check("an item reported with no status is not carried as open", "報過的事" in c, False)
# The status sits at the END. A plan that starts with the verb 完成, or a partial `完成 60%`, is open.
check("an open item whose text STARTS with 完成 is carried", c.get("完成 CRM handoff"), "WB 9/21")
check("the word Done inside an open item does not close it", c.get("Get Done list"), "WB 9/21")
check("'完成 60%' is partial progress: the planned item is still carried", c.get("課程作業"), "WB 9/14")
check("a task ABOUT leave is still a task", c.get("請假制度草案"), "WB 9/7")

# An item both on a carried list and in a later 本週 is ONE item, as old as its oldest sighting —
# including across New Year, where `WB 8/24` must read as last August, not next.
TWICE = """\
## Jan 7, 2027

### #A [a](mailto:a@z.ai)

〔自動彙整 WB 1/4 · 01-05 09:00〕

· 本週 — 新事

〔自動彙整 WB 12/28 · 12-29 09:00〕

· 本週 — 同一件事

〔自動彙整 WB 12/21 · 12-22 09:00〕

· 還沒收掉的 —

· 同一件事〔WB 8/24 起〕
"""
r = analyse(TWICE, today=T.date(2027, 1, 8))
check("one item seen twice is carried once, with its oldest week (across New Year)",
      r["groups"][0]["carry"], [{"text": "同一件事", "since": "WB 8/24"}])
check("WB 8/24 read in January is last August",
      T.week_key("WB 8/24", "", today=T.date(2027, 1, 5)), T.date(2026, 8, 24).isocalendar()[:2])
check("WB 12/28 read on Jan 2 is last December",
      T.week_key("WB 12/28", "", today=T.date(2027, 1, 2)), T.date(2026, 12, 28).isocalendar()[:2])

# An item already on the KEPT block's carried list is still visible — carrying it again duplicates it.
KEPT_LIST = """\
## Oct 1, 2026

### #A [a](mailto:a@z.ai)

〔自動彙整 WB 9/28 · 09-29 09:00〕

· 本週 — 新事

· 還沒收掉的 —

· 甲件事〔WB 8/24 起〕

〔自動彙整 WB 9/21 · 09-22 09:00〕

· 本週 — 甲件事
"""
r = analyse(KEPT_LIST, today=T.date(2026, 10, 2))
check("an item on the kept block's carried list is not carried twice", r["groups"][0]["carry"], [])


# ── 14. closed human bullets: what may be removed (SKB-039, rules 1–3) ─────
# Plain-text export shape, as `get_drive_file_content` returns it: bare date lines, `* ` bullets
# nested by three spaces, chips printed as words, comment anchors as `[a]`.
def export(text):
    return text.split("\n")


NAMES = {"Sam Rivera"}
MD = """\
## Oct 8, 2026
### #Team update
### #Sales [Sam Rivera](mailto:owner-a@example.com)
#### Finance [Sam Rivera](mailto:owner-a@example.com)
"""
HEADS = T.heading_keys(MD, NAMES)
check("markdown headings key like the export prints them",
      {"#Teamupdate", "#Sales", "Finance"} <= HEADS, True)

EXPORT = """\
每週事項 2026
Oct 8, 2026[a]
〔自動彙整 WB 10/5 · 10-06 09:00〕
· 上週 — 甲 完成
#Team update
* P0 Weekly focus Done
* P0 Define KPI Sam Rivera Done
* P1 Build financial model Pause
* P0 CRM progress In Progress
* P1 Get the migration done
#Sales Sam Rivera
* P2 企業講座開發 Drop
* P0 Set up tools Done
   * Google drive
   * Notion
* P0 Launch Done
   * Landing page Done
   * Ads In Progress
* P0 Launch2 Done
   * Ads2 In Progress
   * Landing2 Done
* P0 Commented Done[c]
* P0 Parent Done
   * Child Done
* P1 Newly closed Done
* P1 Grown Done
   * Added later
* P1 Two weeks old Done
* P1 Source for tech talent Done
   * Finance Sam Rivera
Oct 1, 2026
#Team update
* P0 Weekly focus Done
* P0 Define KPI Sam Rivera Done
* P1 Build financial model Pause
* P0 CRM progress In Progress
* P1 Get the migration done
#Sales Sam Rivera
* P2 企業講座開發 Drop
* P0 Set up tools Done
   * Google drive
   * Notion
* P0 Launch Done
   * Landing page Done
   * Ads In Progress
* P0 Launch2 Done
   * Ads2 In Progress
   * Landing2 Done
* P0 Commented Done[a]
* P0 Parent Done
   * Child Done
* P1 Newly closed In Progress
* P1 Grown Done
* P1 Source for tech talent Done
   * Finance Sam Rivera
Sep 24, 2026
#Sales Sam Rivera
* P1 Two weeks old Done
"""
r = T.closed_bullets(export(EXPORT), NAMES, HEADS)
got = [e["line"] for e in r["closed"]]
skip = {e["line"]: e["reason"] for e in r["skipped"]}
check("targets the newest section — a comment anchor on its date does not hide it",
      (r["section"], r["previous"], r["refused"]), ("Oct 8, 2026", "Oct 1, 2026", None))
check("Done and Drop bullets are returned",
      [l for l in got if l in ("P0 Weekly focus Done", "P2 企業講座開發 Drop")],
      ["P0 Weekly focus Done", "P2 企業講座開發 Drop"])
check("Pause and In Progress are never returned",
      [l for l in got if "Pause" in l or "In Progress" in l], [])
check("an auto `·` line ending 完成 is never a candidate", [l for l in got if "甲" in l], [])
check("a task that merely ends in the word 'done' is not a closed chip",
      "P1 Get the migration done" in got, False)
check("a closed bullet takes its sub-items with it",
      next(e["lines"] for e in r["closed"] if e["line"] == "P0 Set up tools Done"),
      ["* P0 Set up tools Done", "   * Google drive", "   * Notion"])
check("a closed bullet with an OPEN sub-item is left alone", "P0 Launch Done" in skip, True)
check("…but its own closed sub-item still goes", "Landing page Done" in got, True)
check("an open FIRST sub-item protects its parent too", "P0 Launch2 Done" in skip, True)
check("a comment anchor re-lettered between weeks ([a] → [c]) still proves the copy",
      "P0 Commented Done" in got, True)
check("a closed child of a closed parent is not listed twice",
      ("P0 Parent Done" in got, "Child Done" in got), (True, False))
check("closed THIS week in the new section (not a copy) is left alone",
      "P1 Newly closed Done" in skip and "P1 Newly closed Done" not in got, True)
check("a subtree that changed since the copy is left alone", "P1 Grown Done" in skip, True)
check("a subtree holding a heading is left alone — its chip routes the week",
      "P1 Source for tech talent Done" in skip, True)
check("proof comes from the PREVIOUS week only, not two weeks back",
      "P1 Two weeks old Done" in skip, True)
check("the owner heading is recorded",
      next(e["owner"] for e in r["closed"] if e["line"] == "P2 企業講座開發 Drop"), "#Sales Sam Rivera")

# The proof must come from under the SAME heading: #Ops closed its item overnight, and #Sales'
# identical line from last week proves nothing about #Ops.
OWNER = """\
Oct 8, 2026
#Ops
* P0 Weekly focus Done
#Sales
* P0 Weekly focus Done
Oct 1, 2026
#Ops
* P0 Weekly focus In Progress
#Sales
* P0 Weekly focus Done
"""
r = T.closed_bullets(export(OWNER), set(), set())
check("an identical line under ANOTHER heading does not prove a copy",
      [(e["owner"], e["line"]) for e in r["closed"]], [("#Sales", "P0 Weekly focus Done")])

r = T.closed_bullets(export("Oct 8, 2026\n* P0 Weekly focus Done\n"), set(), set())
check("one section only: refused, nothing returned", (bool(r["refused"]), r["closed"]), (True, []))
r = T.closed_bullets(export("Oct 15, 2026\n* P0 X Done\nOct 1, 2026\n* P0 X Done\n"), set(), set())
check("the section after the target must be exactly one week earlier",
      (bool(r["refused"]), r["closed"]), (True, []))
# A stray line reading exactly last week's date inside the new week would otherwise become the
# boundary, and the proof would run against the new week's own lower half.
STRAY = """\
Oct 8, 2026
#A
* P0 X Done
Oct 1, 2026
* P0 X Done
Oct 1, 2026
#A
* P0 X In Progress
"""
r = T.closed_bullets(export(STRAY), set(), set())
check("a stray copy of last week's date line is refused", (bool(r["refused"]), r["closed"]), (True, []))
# …but the export covers EVERY tab, and the 封存 tab repeats week labels on purpose. Caught on the
# live Doc on 09-30: a whole-export uniqueness check refused every real run.
ARCHIVE_TAB = (OWNER + "Sep 24, 2026\n#Ops\n* P0 Older In Progress\n"
               + "每週事項 封存\nOct 8, 2026\n〔自動彙整 WB 9/28 · 09-29 09:00〕\nOct 1, 2026\n")
r = T.closed_bullets(export(ARCHIVE_TAB), set(), set())
check("week labels repeated in a later tab do not refuse the run",
      (r["refused"], [e["line"] for e in r["closed"]]), (None, ["P0 Weekly focus Done"]))

# The very first line of the section: its line above is the week heading itself.
FIRST = """\
Oct 8, 2026
* P0 First Done
#A
* P1 Other In Progress
Oct 1, 2026
* P0 First Done
#A
* P1 Other In Progress
"""
FIRST_STRUCT = [
    {"type": "paragraph", "start_index": 0, "end_index": 10, "text_preview": "Oct 8, 2026\n"},
    {"type": "paragraph", "start_index": 10, "end_index": 20, "text_preview": " First \n"},
    {"type": "paragraph", "start_index": 20, "end_index": 30, "text_preview": "#A\n"},
    {"type": "paragraph", "start_index": 30, "end_index": 40, "text_preview": " Other \n"},
    {"type": "paragraph", "start_index": 40, "end_index": 50, "text_preview": "Oct 1, 2026\n"},
    {"type": "paragraph", "start_index": 50, "end_index": 60, "text_preview": "tail\n"},
]
res = T.locate_closed(T.closed_bullets(export(FIRST), set(), set()), FIRST_STRUCT, set())
check("a Done bullet on the section's first line pins against the week heading",
      [(e["start_index"], e["end_index"]) for e in res["closed"]], [(10, 20)])


# ── 15. pinning a closed bullet to Docs API indices (rule 4) ────────────────
# Previews drop every chip — priority, status, person AND file — and stop at 100 characters with
# no trailing newline. These structures are hand-written in that shape, not generated from the
# export, so they cannot agree with the code by construction.
def para(start, end, text):
    return {"type": "paragraph", "start_index": start, "end_index": end, "text_preview": text}


def structure(*previews):
    """Consecutive paragraphs, 10 indices apiece — enough to read ranges at a glance."""
    return [para(10 * k, 10 * k + 10, t) for k, t in enumerate(previews)]


def pin(exp, struct, names=frozenset(), heads=frozenset()):
    return T.locate_closed(T.closed_bullets(export(exp), set(names), set(heads)), struct, set(names))


def ranges(res):
    return {(e["owner"], e["line"]): (e["start_index"], e["end_index"]) for e in res["closed"]}


LONG = "Rebuild the onboarding flow so a new member can reach a first useful answer in under ten min"
LOC_EXPORT = f"""\
Oct 8, 2026
#Team update
* P0 Define KPI Sam Rivera Done
* P1 {LONG}utes flat Done
#Ops
* P0 Weekly focus Done
#Sales
* P0 Weekly focus Done
* P0 Set up tools Done
   * Google drive
Oct 1, 2026
#Team update
* P0 Define KPI Sam Rivera Done
* P1 {LONG}utes flat Done
#Ops
* P0 Weekly focus Done
#Sales
* P0 Weekly focus Done
* P0 Set up tools Done
   * Google drive
"""
LOC_STRUCT = structure(
    "Oct 8, 2026\n",            # 0
    "#Team update\n",           # 10
    "\n",                       # 20  an empty paragraph the export does not print
    " Define KPI  \n",          # 30
    " " + LONG[:99],            # 40  truncated: no newline
    "#Ops\n",                   # 50
    " Weekly focus \n",         # 60
    "#Sales\n",                 # 70
    " Weekly focus \n",         # 80
    " Set up tools \n",         # 90
    "Google drive\n",           # 100
    "Oct 1, 2026\n",            # 110
    # Last week, as the scaffold left it: the same lines with the same neighbours. A search that
    # ran past the target section would find every bullet here a second time.
    "#Team update\n", "\n", " Define KPI  \n", " " + LONG[:99], "#Ops\n", " Weekly focus \n",
    "#Sales\n", " Weekly focus \n", " Set up tools \n", "Google drive\n",
    "Sep 24, 2026\n",           # 210
    "tail\n",                   # 220
)
res = pin(LOC_EXPORT, LOC_STRUCT, NAMES)
rng = ranges(res)
check("a person chip missing from the preview still matches",
      rng.get(("#Team update", "P0 Define KPI Sam Rivera Done")), (30, 40))
check("a preview cut off at 100 characters matches by prefix",
      rng.get(("#Team update", f"P1 {LONG}utes flat Done")), (40, 50))
check("two identical lines each pin to their own paragraph",
      (rng.get(("#Ops", "P0 Weekly focus Done")), rng.get(("#Sales", "P0 Weekly focus Done"))),
      ((60, 70), (80, 90)))
check("a bullet with sub-items becomes ONE range covering them",
      rng.get(("#Sales", "P0 Set up tools Done")), (90, 110))
check("ranges come back in the order to delete them: highest first",
      [e["start_index"] for e in res["closed"]], [90, 80, 60, 40, 30])
check("nothing is skipped when everything lines up", res["skipped"], [])

res = pin(LOC_EXPORT, LOC_STRUCT, set())
check("without the person names a chip line cannot be pinned — skipped, not guessed",
      ("P0 Define KPI Sam Rivera Done" in [e["line"] for e in res["skipped"]],
       ("#Team update", "P0 Define KPI Sam Rivera Done") in ranges(res)), (True, False))

BAD_CHILD = LOC_STRUCT[:10] + [para(100, 110, "Something else\n")] + LOC_STRUCT[11:]
res = pin(LOC_EXPORT, BAD_CHILD, NAMES)
check("sub-items that do not line up skip the bullet",
      "P0 Set up tools Done" in [e["line"] for e in res["skipped"]], True)

# The collision the adversarial review built from the live Doc: an open bullet whose FILE chip
# vanished from its preview reads exactly like the Done bullet, and a typed `90%` after a status
# chip makes a third look different. Only the neighbours can tell them apart.
COLLIDE = """\
Oct 8, 2026
#Knowledge
* P1 Complete seed content In Progress 90%
* P1 Complete seed content Done
* P2 Plan the camp In Progress
* P1 Complete seed content 課綱v2.docx In Progress
Oct 1, 2026
#Knowledge
* P1 Complete seed content In Progress 90%
* P1 Complete seed content Done
* P2 Plan the camp In Progress
* P1 Complete seed content 課綱v2.docx In Progress
"""
COLLIDE_STRUCT = structure(
    "Oct 8, 2026\n", "#Knowledge\n",
    " Complete seed content  90%\n",     # 20  open, typed 90% survives
    " Complete seed content  \n",        # 30  the Done bullet
    " Plan the camp \n",                 # 40
    " Complete seed content  \n",        # 50  open — its file chip is gone from the preview
    "Oct 1, 2026\n", "tail\n")
check("a Done bullet is never pinned to the open line that previews the same",
      ranges(pin(COLLIDE, COLLIDE_STRUCT)), {("#Knowledge", "P1 Complete seed content Done"): (30, 40)})

# Each neighbour check must carry weight on its own. ABOVE differs, below is the same:
ABOVE = """\
Oct 8, 2026
#A
* P1 First kick In Progress
* P1 Ship it Done
* P1 Measure In Progress
* P1 Second kick In Progress
* P1 Ship it 規格.docx In Progress
* P1 Measure In Progress
Oct 1, 2026
#A
* P1 First kick In Progress
* P1 Ship it Done
* P1 Measure In Progress
* P1 Second kick In Progress
* P1 Ship it 規格.docx In Progress
* P1 Measure In Progress
"""
ABOVE_STRUCT = structure("Oct 8, 2026\n", "#A\n", " First kick \n", " Ship it \n", " Measure \n",
                         " Second kick \n", " Ship it \n", " Measure \n", "Oct 1, 2026\n", "tail\n")
check("the line ABOVE tells two identical previews apart",
      ranges(pin(ABOVE, ABOVE_STRUCT)), {("#A", "P1 Ship it Done"): (30, 40)})

# …and BELOW differs, above is the same:
BELOW = """\
Oct 8, 2026
#A
* P1 Kick In Progress
* P1 Ship it Done
* P1 First measure In Progress
* P1 Kick In Progress
* P1 Ship it 規格.docx In Progress
* P1 Second measure In Progress
Oct 1, 2026
#A
* P1 Kick In Progress
* P1 Ship it Done
* P1 First measure In Progress
* P1 Kick In Progress
* P1 Ship it 規格.docx In Progress
* P1 Second measure In Progress
"""
BELOW_STRUCT = structure("Oct 8, 2026\n", "#A\n", " Kick \n", " Ship it \n", " First measure \n",
                         " Kick \n", " Ship it \n", " Second measure \n", "Oct 1, 2026\n", "tail\n")
check("the line BELOW tells two identical previews apart",
      ranges(pin(BELOW, BELOW_STRUCT)), {("#A", "P1 Ship it Done"): (30, 40)})

# When even the neighbours are identical, there is no telling — skip, never take the first.
TWINS = """\
Oct 8, 2026
#A
* P1 Kick In Progress
* P1 Ship it 規格.docx In Progress
* P1 Measure In Progress
* P1 Kick In Progress
* P1 Ship it Done
* P1 Measure In Progress
Oct 1, 2026
#A
* P1 Kick In Progress
* P1 Ship it 規格.docx In Progress
* P1 Measure In Progress
* P1 Kick In Progress
* P1 Ship it Done
* P1 Measure In Progress
"""
TWINS_STRUCT = structure("Oct 8, 2026\n", "#A\n", " Kick \n", " Ship it \n", " Measure \n",
                         " Kick \n", " Ship it \n", " Measure \n", "Oct 1, 2026\n", "tail\n")
res = pin(TWINS, TWINS_STRUCT)
check("two equally good places: skipped, not the first one taken",
      (res["closed"], [e["line"] for e in res["skipped"]]), ([], ["P1 Ship it Done"]))


def refuses(fn):
    try:
        fn()
        return False
    except SystemExit:
        return True


# The second copy sits AFTER the previous section, so only the uniqueness check can refuse it.
check("refuses when the target heading appears twice in the structure",
      refuses(lambda: pin(LOC_EXPORT, LOC_STRUCT + [para(130, 140, "Oct 8, 2026\n")], NAMES)), True)
# A foreign date line right after the target, with the real previous week still present once.
WRONG_NEXT = LOC_STRUCT[:11] + [para(105, 110, "Sep 17, 2026\n")] + LOC_STRUCT[11:]
check("refuses when the structure's next section is not the export's previous one",
      refuses(lambda: pin(LOC_EXPORT, WRONG_NEXT, NAMES)), True)
check("refuses when last week's date appears twice in the structure",
      refuses(lambda: pin(LOC_EXPORT, LOC_STRUCT + [para(230, 240, "Oct 1, 2026\n")], NAMES)), True)
check("refuses overlapping ranges",
      refuses(lambda: T.assert_disjoint([{"start_index": 50, "end_index": 70},
                                         {"start_index": 40, "end_index": 60}])), True)
check("adjacent ranges are not an overlap",
      refuses(lambda: T.assert_disjoint([{"start_index": 50, "end_index": 70},
                                         {"start_index": 40, "end_index": 50}])), False)


# ── 16. re-check before the delete, post-check after it ─────────────────────
# The export and the structure are two separate reads, and people edit the Doc. The plan is
# re-derived from FRESH reads right before deleting and must come out identical; afterwards the
# section must be the old one minus exactly the planned lines.
plan = pin(LOC_EXPORT, LOC_STRUCT, NAMES)
check("an unchanged Doc reproduces the plan",
      refuses(lambda: T.expect_same(plan, pin(LOC_EXPORT, LOC_STRUCT, NAMES))), False)
FLIPPED = LOC_EXPORT.replace("* P0 Set up tools Done\n   * Google drive\nOct 1",
                             "* P0 Set up tools In Progress\n   * Google drive\nOct 1", 1)
check("a status flipped since the plan (invisible in previews) blocks the delete",
      refuses(lambda: T.expect_same(plan, pin(FLIPPED, LOC_STRUCT, NAMES))), True)
SHIFTED = [para(p["start_index"] + (5 if p["start_index"] >= 30 else 0),
                p["end_index"] + (5 if p["end_index"] > 30 else 0), p["text_preview"]) for p in LOC_STRUCT]
check("an index that moved since the plan blocks the delete",
      refuses(lambda: T.expect_same(plan, pin(LOC_EXPORT, SHIFTED, NAMES))), True)
# The plan is also the post-check's baseline: ANY edit to the section in between must stop the
# delete, or the post-check would later fail on a line nobody deleted.
check("an edit elsewhere in the section, same ranges, still blocks the delete",
      refuses(lambda: T.expect_same(plan, {**plan, "section_lines": plan["section_lines"]
                                           + ["* P1 Added meanwhile In Progress"]})), True)

gone = {e["at"] + d for e in plan["closed"] for d in range(len(e["lines"]))}
AFTER = "\n".join(["Oct 8, 2026"] + [l for k, l in enumerate(plan["section_lines"]) if k not in gone]
                  + LOC_EXPORT.split("\n")[10:])
check("post-check passes when exactly the planned lines are gone",
      refuses(lambda: T.postcheck(plan, export(AFTER))), False)
TOO_MUCH = AFTER.replace("#Sales\n", "", 1)
check("post-check fails when anything else is gone too",
      refuses(lambda: T.postcheck(plan, export(TOO_MUCH))), True)
check("post-check fails when a planned line is still there",
      refuses(lambda: T.postcheck(plan, export(LOC_EXPORT))), True)
# Deleting a commented line re-letters every comment anchor after it in the export.
RELETTERED = AFTER.replace("#Ops", "#Ops[b]", 1)
check("post-check ignores comment anchors re-lettered by the delete",
      refuses(lambda: T.postcheck(plan, export(RELETTERED))), False)


# ── 17. the CLI end to end, on saved MCP tool results ───────────────────────
import contextlib
import io
import json
import tempfile

TMP = Path(tempfile.mkdtemp(prefix="tidy_test_"))
(TMP / "export.json").write_text(json.dumps(
    {"result": "File: \"x\"\n\n--- CONTENT ---\r\n" + LOC_EXPORT.replace("\n", "\r\n")}), encoding="utf-8")
(TMP / "struct.json").write_text(json.dumps(
    {"result": "Document structure analysis for x:\n\n" + json.dumps({"elements": LOC_STRUCT}) + "\n\nnote"}),
    encoding="utf-8")
(TMP / "doc.md").write_text(MD, encoding="utf-8")


def cli(*argv):
    out, old = io.StringIO(), sys.argv
    sys.argv = ["tidy_blocks.py", *argv]
    try:
        with contextlib.redirect_stdout(out):
            T.main()
        return 0, out.getvalue()
    except SystemExit as e:
        return (e.code if isinstance(e.code, int) else 1), out.getvalue()
    finally:
        sys.argv = old


BASE = ["--closed", "--export", str(TMP / "export.json"), "--structure", str(TMP / "struct.json"),
        "--markdown", str(TMP / "doc.md")]
code, out = cli(*BASE, "--section", "Oct 8, 2026")
check("the CLI reads wrapped tool results and plans the deletes",
      (code, len(json.loads(out)["closed"]) if code == 0 else None), (0, 5))
(TMP / "plan.json").write_text(out, encoding="utf-8")
check("the CLI refuses a section that is not the newest",
      cli(*BASE, "--section", "Oct 1, 2026")[0] != 0, True)
check("the CLI --expect passes on an unchanged Doc",
      cli(*BASE, "--section", "Oct 8, 2026", "--expect", str(TMP / "plan.json"))[0], 0)
(TMP / "after.txt").write_text(AFTER, encoding="utf-8")
check("the CLI --postcheck passes after the planned delete",
      cli("--closed", "--export", str(TMP / "after.txt"), "--postcheck", str(TMP / "plan.json"))[0], 0)
check("the CLI --postcheck fails when nothing was deleted",
      cli("--closed", "--export", str(TMP / "export.json"), "--postcheck", str(TMP / "plan.json"))[0] != 0,
      True)


# ── MUTATIONS: prove the tests above can actually go red ─────────────────────
# Each mutation breaks one real line of tidy_blocks.py; if the suite still passes, the matching
# test is decorative and must be rewritten. Every anchor must occur EXACTLY once.
MUTATIONS = [
    ("block extent ignores the human-line boundary",
     'elif s:\n            break', 'elif s:\n            pass'),
    ("groups never split on a heading",
     'if any(HEADING_RE.match(sec[k].strip()) for k in range(a + 1, b)):',
     'if False:'),
    ("keep blindly trusts write order",
     'blocks.sort(key=lambda b: b["key"], reverse=True)', 'pass'),
    ("done-detection loses the English Done",
     r'(完成|已完成|\bDone\b|✅|結案)\s*$", re.IGNORECASE)', r'(完成|已完成|✅|結案)\s*$", re.IGNORECASE)'),
    ("noise is not filtered", 'or text in NOISE', 'or False'),
    # SKB-039 — carry
    ("a comment on the week heading hides the section",
     r'\s*(?:\[\^[^\]]*\]\s*)*$")', r'\s*$")'),
    ("an archived block's carried list is ignored again",
     'elif m := CARRIED_RE.match(s):', 'elif False:'),
    ("an item's oldest week is not kept", 'elif wk < found[key]["_wk"]:', 'elif False:'),
    ("a WB label is never pulled back a year", 'if d > today + timedelta(days=14):', 'if False:'),
    ("a carried item reported done is carried anyway", 'close_key(text) in closed', 'False'),
    ("done-words are compared literally",
     'return normalise(DONE_WORDS_RE.sub("", strip_status(item)))', 'return normalise(strip_status(item))'),
    ("a comment at the end of a carried line drops it",
     '                s = FOOTNOTE_RE.sub("", sec[k]).strip()\n                if is_line(s, "本週"):',
     '                s = sec[k].strip()\n                if is_line(s, "本週"):'),
    ("an inline 完成 on a carried line is ignored",
     'if tail and DONE_RE.search(tail.group(0)):', 'if False:'),
    ("an open 上週 item that was not planned again is lost",
     'if OPEN_RE.search(x) and normalise(strip_status(x)) not in planned]', 'if False]'),
    ("leave is carried as work", 'or NOISE_RE.match(text)', 'or False'),
    # SKB-039 — which bullets
    ("a comment anchor on the export's date line hides the section",
     r'\s*(?:\[[a-z]{1,3}\]\s*)*$")', r'\s*$")'),
    ("the previous section is not checked to be the week before",
     'if parse_label(prev_label) != parse_label(label) - timedelta(days=7):', 'if False:'),
    ("the proof reads every older section, not just the previous one",
     'prev = [clean(l) for l in lines[s1 + 1:s2]]', 'prev = [clean(l) for l in lines[s1 + 1:]]'),
    ("a heading inside the subtree is not refused", 'if any(heading(l) for l in tree):', 'if False:'),
    ("an open sub-item does not protect its parent", 'if open_child:', 'if False:'),
    ("the proof ignores the heading it sits under",
     ' and owner(prev, k) == entry["owner"]', ''),
    ("the copy proof is skipped", 'if not proved:', 'if False:'),
    ("children of a closed parent are listed again",
     '            res["closed"].append(entry)\n        i = j', '            res["closed"].append(entry)\n        i += 1'),
    ("the closed chip matches any case",
     r'CLOSED_TAIL_RE = re.compile(r"\s+(Done|Drop|Dropped|完成|已完成|放棄|取消)$")',
     r'CLOSED_TAIL_RE = re.compile(r"\s+(Done|Drop|Dropped|完成|已完成|放棄|取消)$", re.I)'),
    # SKB-039 — where they are
    ("status chips are not stripped from keys", 'for b in {a, STATUS_WORD_RE.sub("", a)}:', 'for b in {a}:'),
    ("person names are not stripped", 'b = b.replace(name, "")', 'pass'),
    ("a truncated preview is compared whole", '(truncated and k.startswith(pk))', 'False'),
    ("the line above is not checked",
     'if q is None or not preview_matches(paragraphs[q], line_keys(above, names)):', 'if False:'),
    ("the line below is not checked",
     'if r is None or not preview_matches(paragraphs[r], line_keys(below, names)):', 'if False:'),
    ("an ambiguous bullet takes the first place", 'if len(spots) != 1:', 'if not spots:'),
    ("sub-items are not checked against the Doc",
     'if not all(preview_matches(paragraphs[p + d], line_keys(entry["lines"][d], names))\n'
     '                       for d in range(n)):',
     'if not preview_matches(paragraphs[p], line_keys(entry["lines"][0], names)):'),
    ("a duplicated target heading is tolerated", 'if len(heads) != 1:', 'if not heads:'),
    ("the structure's section boundary is not checked",
     'if end is None or nonspace(paragraphs[end]["text_preview"]) != nonspace(prev_label):',
     'if end is None:'),
    ("overlapping ranges are not refused", 'if b["end_index"] > a["start_index"]:', 'if False:'),
    # SKB-039 — before and after the delete
    ("the fresh re-check is not compared", 'if plan_signature(plan) != plan_signature(res):', 'if False:'),
    ("the post-check is not compared", 'if want != got:', 'if False:'),
    # second adversarial pass (09-30)
    ("done is detected anywhere in an item, not at its end",
     r'DONE_RE = re.compile(r"(完成|已完成|\bDone\b|✅|結案)\s*$"', r'DONE_RE = re.compile(r"(完成|已完成|\bDone\b|✅|結案)"'),
    ("any item starting with 請假 is dropped as leave",
     r'NOISE_RE = re.compile(r"^(請假|休假)\s*[一二三兩半\d]*\s*[週周天日]?$")', r'NOISE_RE = re.compile(r"^(請假|休假)")'),
    ("a stray copy of a week's date line is tolerated in the export",
     'if len(marks) > 2 and parse_label(marks[2][1]) >= parse_label(prev_label):', 'if False:'),
    ("week labels must be unique across every tab of the export",
     'if len(marks) > 2 and parse_label(marks[2][1]) >= parse_label(prev_label):',
     'if [l for _, l in marks].count(prev_label) != 1 or [l for _, l in marks].count(label) != 1:'),
    ("a stray copy of last week's date is tolerated in the structure",
     'if sum(nonspace(p.get("text_preview", "")) == nonspace(prev_label) for p in paragraphs) != 1:',
     'if False:'),
    ("comment anchors are compared literally", 'return EXPORT_MARK_RE.sub("", line).rstrip()', 'return line.rstrip()'),
    ("the pin search runs past the target section",
     'for p in range(start, end - n + 1):', 'for p in range(start, len(paragraphs) - n + 1):'),
    ("--expect ignores edits elsewhere in the section",
     '"section": res["section"], "section_lines": res["section_lines"],', '"section": res["section"],'),
    ("an open FIRST sub-item is not looked at", 'for l in tree[1:] if OPEN_ANY_RE.search(l)', 'for l in tree[2:] if OPEN_ANY_RE.search(l)'),
    ("the section's first line has no heading above it", 'if sec[k].strip()), label)', 'if sec[k].strip()), "")'),
    ("the section's last line has no heading below it", 'if sec[k].strip()), prev_label)', 'if sec[k].strip()), "")'),
]


def run_mutations():
    src = (HERE / "tidy_blocks.py").read_text(encoding="utf-8")
    test_src = (HERE / "test_tidy_blocks.py").read_text(encoding="utf-8") \
        .replace("import tidy_blocks as T", "import _mutant_tidy_blocks as T")
    mutant, runner = HERE / "_mutant_tidy_blocks.py", HERE / "_mutant_test.py"

    def run(module_src):
        mutant.write_text(module_src, encoding="utf-8")
        runner.write_text(test_src, encoding="utf-8")
        for stale in (HERE / "__pycache__").glob("_mutant*"):
            stale.unlink()                 # a stale .pyc of the same size would run the WRONG mutant
        return subprocess.run([sys.executable, "-B", str(runner)],
                              capture_output=True, text=True, cwd=HERE)

    print("\nMUTATION CHECK — each line below must make the suite FAIL")
    try:
        # Control first. Until 2026-09-30 this harness rewrote `def run_mutations():` into
        # `def pass:`, so every mutant was a SyntaxError and every mutation "failed the suite".
        control = run(src)
        if control.returncode != 0:
            print("  HARNESS BROKEN — the UNmutated copy fails, so no result below would mean anything")
            print((control.stdout + control.stderr)[-600:])
            return False
        print("  control: the unmutated copy passes")
        all_caught = True
        for name, find, repl in MUTATIONS:
            n = src.count(find)
            if n != 1:
                print(f"  ?? {name}: anchor found {n} times — must be exactly once")
                all_caught = False
                continue
            p = run(src.replace(find, repl))
            broken = "SyntaxError" in p.stderr or "IndentationError" in p.stderr
            caught = p.returncode != 0 and not broken
            print(f"  {'OK' if caught else 'LEAK'} {name}"
                  f"{'  <-- the mutant does not even compile' if broken else ''}"
                  f"{'  <-- tests did NOT catch this' if not caught and not broken else ''}")
            all_caught &= caught
        return all_caught
    finally:
        mutant.unlink(missing_ok=True)
        runner.unlink(missing_ok=True)


if __name__ == "__main__":
    n = len([l for l in Path(__file__).read_text(encoding="utf-8").splitlines()
             if l.startswith("check(")])
    if FAILURES:
        print(f"FAILED {len(FAILURES)} assertion(s):\n")
        for f in FAILURES:
            print("  - " + f)
        sys.exit(1)
    print(f"all assertions passed ({n} checks)")
    if "--mutate" in sys.argv:
        sys.exit(0 if run_mutations() else 1)

