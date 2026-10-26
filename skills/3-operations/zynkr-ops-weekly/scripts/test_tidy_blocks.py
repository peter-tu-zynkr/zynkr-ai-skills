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


# ── 18. carried items as bullets; Done/Drop chips the markdown cannot see (10-25) ─────
# The owner's 10-25 screenshots: carried `·` lines marked Done stayed for weeks, and a re-carried
# line came back open because re-typing it lost its chip. Only the Drive export shows chips.
CARRY_MD = """\
## Oct 29, 2026

### #Tech [Sam Rivera](mailto:owner-a@example.com)

〔自動彙整 WB 10/26 · 10-27 09:00〕

· 本週 — 新功能

〔自動彙整 WB 10/19 · 10-20 09:00〕

· 本週 — 舊事 ／ 自己的待辦 ／ 已經是子彈的事

· 還沒收掉的 —

· 建立知識庫〔WB 8/31 起〕

· 寫文件〔WB 9/7 起〕

- 已經是子彈的事〔WB 8/24 起〕
- 自己的待辦
"""
CARRY_EXPORT = """\
Oct 29, 2026
#Tech Sam Rivera
〔自動彙整 WB 10/26 · 10-27 09:00〕
· 本週 — 新功能
〔自動彙整 WB 10/19 · 10-20 09:00〕
· 本週 — 舊事 ／ 自己的待辦 ／ 已經是子彈的事
· 還沒收掉的 —
· 建立知識庫〔WB 8/31 起〕Done
· 寫文件〔WB 9/7 起〕
* 已經是子彈的事〔WB 8/24 起〕
* 自己的待辦
Oct 22, 2026
"""
TODAY = __import__("datetime").date(2026, 10, 30)
g = T.analyse(CARRY_MD.split("\n"), today=TODAY, export_lines=export(CARRY_EXPORT))["groups"][0]
check("a carried item with a Done chip in the export is not carried again",
      sorted(c["text"] for c in g["carry"]), ["寫文件", "舊事"])
g0 = T.analyse(CARRY_MD.split("\n"), today=TODAY)["groups"][0]
check("without the export the chip is invisible (why tidy step 2 passes --export)",
      "建立知識庫" in [c["text"] for c in g0["carry"]], True)
check("an item already on the group's bullets (carried or the owner's own) is not carried twice",
      [c["text"] for c in g["carry"] if c["text"] in ("自己的待辦", "已經是子彈的事")], [])
check("new carried items need a 還沒收掉的 line in the kept block", g["carry_header_needed"], True)
try:
    T.closed_in_export(["Oct 1, 2026", "· x"], "Oct 29, 2026")
    refused = False
except SystemExit:
    refused = True
check("a missing section in the export is refused, not read as no chips", refused, True)

HDR_MD = """\
## Oct 29, 2026

### #Ops [Sam Rivera](mailto:owner-a@example.com)

〔自動彙整 WB 10/26 · 10-27 09:00〕

· 本週 — 甲

〔自動彙整 WB 10/19 · 10-20 09:00〕

· 本週 — 甲

- 舊的事〔WB 8/24 起〕
"""
g = T.analyse(HDR_MD.split("\n"), today=TODAY)["groups"][0]
check("carried bullets below the group keep their 還沒收掉的 line, even with nothing new",
      (g["carry"], g["carry_header_needed"]), ([], True))
g = T.analyse(HDR_MD.replace("· 本週 — 甲\n\n〔", "· 本週 — 甲\n\n· 還沒收掉的 —\n\n〔", 1)
              .split("\n"), today=TODAY)["groups"][0]
check("a kept block that already has the line needs no second one", g["carry_header_needed"], False)
g = T.analyse(HDR_MD.replace("- 舊的事〔WB 8/24 起〕\n", "- 舊的事\n").split("\n"), today=TODAY)["groups"][0]
check("an owner's own bullet below is not a carried list", g["carry_header_needed"], False)

DOT_EXPORT = """\
Oct 29, 2026
#Sales Sam Rivera
〔自動彙整 WB 10/19 · 10-20 09:00〕
· 上週 — 甲 完成
· 這次要決定的事 — P2 外包 Drop
· 還沒收掉的 —
· 更新一篇seo〔WB 8/24 起〕Done
· 寫文件〔WB 9/7 起〕Pause
· P2 Update content matrix Drop
· 新完成的事〔WB 9/14 起〕Done
Oct 22, 2026
#Sales Sam Rivera
〔自動彙整 WB 10/19 · 10-20 09:00〕
· 上週 — 甲 完成
· 這次要決定的事 — P2 外包 Drop
· 還沒收掉的 —
· 更新一篇seo〔WB 8/24 起〕Done
· 寫文件〔WB 9/7 起〕Pause
· P2 Update content matrix Drop
· 新完成的事〔WB 9/14 起〕
"""
r = T.closed_bullets(export(DOT_EXPORT), set(), set())
check("a carried · line and a chipped · line marked Done/Drop a week ago are removed",
      [e["line"] for e in r["closed"]],
      ["更新一篇seo〔WB 8/24 起〕Done", "P2 Update content matrix Drop"])
check("a · line closed only this week waits a week",
      [e["line"] for e in r["skipped"]], ["新完成的事〔WB 9/14 起〕Done"])
check("a · line is removed alone: it has no sub-items",
      [len(e["lines"]) for e in r["closed"]], [1, 1])
check("an auto summary line ending in 完成 or Drop is never a candidate",
      [e["line"] for e in r["closed"] + r["skipped"] if "—" in e["line"]], [])
check("a chip glued to 〕 is still read as the status",
      [e["status"] for e in r["closed"]], ["Done", "Drop"])

DOT_STRUCT = structure(
    "Oct 29, 2026\n",                         # 0
    "#Sales \n",                              # 10
    "〔自動彙整 WB 10/19 · 10-20 09:00〕\n",      # 20
    "· 上週 — 甲 完成\n",                        # 30
    "· 這次要決定的事 — P2 外包 Drop\n",            # 40
    "· 還沒收掉的 —\n",                          # 50
    "· 更新一篇seo〔WB 8/24 起〕\n",               # 60  the Done chip is gone from the preview
    "· 寫文件〔WB 9/7 起〕\n",                     # 70
    "·  Update content matrix \n",           # 80  both chips gone
    "· 新完成的事〔WB 9/14 起〕\n",                 # 90
    "Oct 22, 2026\n",                         # 100
)
res = T.locate_closed(r, DOT_STRUCT, set())
check("a closed · line is pinned to its own paragraph despite the chips the preview drops",
      sorted((e["start_index"], e["end_index"]) for e in res["closed"]), [(60, 70), (80, 90)])


# ── 19. last week's agenda, mid-line chips, finished blocks (the owner, 10-25) ──────────────
# The Oct 29 section still held the Oct 22 agenda, and `Claude Code 課程` kept four `Done` rows
# whose chip has typed progress after it. Shapes copied from that morning's export.
NAMES19 = {"Sam Rivera"}
MD19 = """\
## Nov 5, 2026
### #Team update
### # Knowledge product [Sam Rivera](mailto:owner-a@example.com)
## Claude Code 課程
## Workshop 規劃
## Finance [Sam Rivera](mailto:owner-a@example.com)
"""
HEADS19 = T.heading_keys(MD19, NAMES19)
AGENDA = """\
〔自動彙整 WB 10/26 · 10-29 09:00〕本週會議議程
· 連續三週以上沒動 — Build financial model ↻23週
· 這次要決定的事 — Bicky 交接 4 件事怎麼拍板 Drop 掉的那兩件不談
· 這週先不談 — LMS ↻21週"""
COURSE = """\
Claude Code 課程
Current progress
* 專案重要時間軸：
   * 9/1全影片平台送審、10/15正式開課
* 課程剪輯   Done 進度：2-4
* 課程第一階段 QC  Done 進度：1-2
* 課程作業本   Done  進度：第一章（完）
Metrics
* Course signed up #"""
OTHERS = """\
Workshop 規劃
* 講座大綱 Done 進度：草稿
* 報名頁 In Progress Done 一半
* 講師 完成 邀請信 還在談
* 新開的 Done 進度：1/3
Finance Sam Rivera
* 月結 Done 進度：9 月
* 年度預算 Done 進度：草案"""
EXPORT19 = f"""\
Nov 5, 2026
{AGENDA}
#Team update
# Knowledge product Sam Rivera
{COURSE}
{OTHERS}
Oct 29, 2026
{AGENDA}
#Team update
# Knowledge product Sam Rivera
{COURSE}
{OTHERS.replace("* 新開的 Done 進度：1/3", "* 新開的 In Progress 進度：1/3")}
"""
r = T.closed_bullets(export(EXPORT19), NAMES19, HEADS19)
got19 = {e["line"]: e for e in r["closed"]}
skip19 = {e["line"]: e["reason"] for e in r["skipped"]}
agenda_head = "〔自動彙整 WB 10/26 · 10-29 09:00〕本週會議議程"
check("last week's agenda, copied forward verbatim, is removed", agenda_head in got19, True)
check("…as one block: its stamp and every `·` line under it",
      got19[agenda_head]["lines"], AGENDA.split("\n"))
check("a Drop typed inside an agenda line does not make it a bullet candidate",
      [l for l in got19 if l.startswith("·")], [])
check("a Done chip with typed progress after it closes the bullet",
      [l for l in got19 if l.startswith("課程")],
      ["課程剪輯   Done 進度：2-4", "課程第一階段 QC  Done 進度：1-2", "課程作業本   Done  進度：第一章（完）"])
check("the timeline and Metrics around them stay", any("時間軸" in l or "signed" in l for l in got19), False)
check("a line that also says In Progress is not closed",
      any("報名頁" in l for l in list(got19) + list(skip19)), False)
check("a typed 完成 mid-line is a verb, not a chip", any("講師邀請" in l for l in list(got19) + list(skip19)), False)
check("a mid-line Done closed only this week waits a week",
      "新開的 Done 進度：1/3" in skip19 and "新開的 Done 進度：1/3" not in got19, True)
check("a whole sub-heading whose chipped items are all Done is offered for closing, not deleted",
      r["done_blocks"], [{"heading": "Claude Code 課程", "done": 3}])
check("…never a department heading, and never a block with an open item",
      [b["heading"] for b in r["done_blocks"] if b["heading"] != "Claude Code 課程"], [])

FRESH19 = EXPORT19.replace("Oct 29, 2026\n" + AGENDA, "Oct 29, 2026\n"
                           + AGENDA.replace("10-29 09:00", "10-22 09:00").replace("↻23週", "↻22週"))
r2 = T.closed_bullets(export(FRESH19), NAMES19, HEADS19)
check("an agenda that differs from last week's is this week's — it stays",
      (agenda_head in [e["line"] for e in r2["closed"]], agenda_head in [e["line"] for e in r2["skipped"]]),
      (False, True))

STRUCT19 = structure(
    "Nov 5, 2026\n",                                          # 0
    "〔自動彙整 WB 10/26 · 10-29 09:00〕本週會議議程\n",            # 10
    "· 連續三週以上沒動 — Build financial model ↻23週\n",          # 20
    "· 這次要決定的事 — Bicky 交接 4 件事怎麼拍板 Drop 掉的那兩件不談\n",  # 30
    "· 這週先不談 — LMS ↻21週\n",                               # 40
    "#Team update\n",                                         # 50
    "# Knowledge product \n",                                 # 60
    "Claude Code 課程\n",                                       # 70
    "Current progress\n",                                     # 80
    "專案重要時間軸：\n",                                          # 90
    "9/1全影片平台送審、10/15正式開課\n",                            # 100
    "課程剪輯    進度：2-4\n",                                     # 110 the Done chip is gone
    "課程第一階段 QC   進度：1-2\n",                               # 120
    "課程作業本    進度：第一章（完）\n",                             # 130
    "Metrics\n",                                              # 140
    "Course signed up #\n",                                   # 150
    "Workshop 規劃\n",                                          # 160
    "講座大綱  進度：草稿\n",                                     # 170
    "報名頁   一半\n",                                          # 180
    "講師 完成 邀請信 還在談\n",                                     # 190
    "新開的  進度：1/3\n",                                       # 200
    "Finance \n",                                             # 210
    "月結  進度：9 月\n",                                        # 220
    "年度預算  進度：草案\n",                                     # 230
    "Oct 29, 2026\n",                                         # 240
)
res19 = T.locate_closed(r, STRUCT19, NAMES19)
check("the agenda pins to one range from its stamp to its last line, the mid-line chips to theirs",
      sorted((e["start_index"], e["end_index"]) for e in res19["closed"]
             if "講座" not in e["line"] and "月結" not in e["line"] and "年度" not in e["line"]),
      [(10, 50), (110, 120), (120, 130), (130, 140)])


# Carried items as ○ sub-bullets (10-25): the markdown indents them under the header, with a blank
# line between. They must still count as visible (not carried twice), the header must not be
# written again, and a Done one must still be found by step 7.
NEST_MD = """\
## Nov 5, 2026
### #Sales
〔自動彙整 WB 10/19 · 10-20 09:40〕
· 本週 — 甲件事
· 還沒收掉的 —

  - 寫文件〔WB 9/7 起〕
  - 乙件事〔WB 9/14 起〕
〔自動彙整 WB 10/12 · 10-13 09:40〕
· 本週 — 寫文件 ／ 乙件事
"""
r = analyse(NEST_MD)
check("a sub-bullet under the header is visible: never carried again", r["groups"][0]["carry"], [])
check("…and the header is not written a second time", r["groups"][0]["carry_header_needed"], False)
check("…and it is not swept into the auto block that is kept",
      any("寫文件" in l for l in r["groups"][0]["keep"]["lines"]), False)
NEST_EX = export("Nov 5, 2026\n#Sales\n· 還沒收掉的 —\n   * 寫文件〔WB 9/7 起〕Done\n   * 乙件事〔WB 9/14 起〕\n"
                 "Oct 29, 2026\n#Sales\n· 還沒收掉的 —\n   * 寫文件〔WB 9/7 起〕Done\n   * 乙件事〔WB 9/14 起〕\n")
check("a sub-bullet marked Done a week ago is removed, alone",
      [e["lines"] for e in T.closed_bullets(NEST_EX, set(), set())["closed"]], [["   * 寫文件〔WB 9/7 起〕Done"]])


# ── 20. the kept block as bullets — tidy step 8 (the owner, 10-25) ──────────
# `· 上週 — 甲 完成 ／ 乙 WIP` becomes a `上週` bullet with the items under it. The week after, rollup
# writes a typed block above it, and tidy must still read the formatted one as ONE block: archive
# all of it, carry from it, and never take its sub-bullets for the team's lines.
FMT_MD = """\
## Nov 5, 2026
### #Sales [Sam Rivera](mailto:owner-a@example.com)
〔自動彙整 WB 11/2 · 11-03 09:40〕
· 上週 — 甲件事 完成 ／ 丙件事 WIP
· 本週 — 丁件事
〔自動彙整 WB 10/26 · 10-27 09:40〕

- 上週
  - 舊事 完成
- 本週
  - 甲件事
  - 丙件事
  - 戊件事（A ／ B）
- 卡關
  - 等報價
- 還沒收掉的
  - 寫文件〔WB 9/7 起〕
- 我自己的一行
"""
g = analyse(FMT_MD, today=__import__("datetime").date(2026, 11, 6))["groups"][0]
check("a formatted block is archived whole: through its last label, its sub-bullets included",
      (g["archive"][0]["lines"][-1], "  - 等報價" in g["archive"][0]["lines"]), ("- 還沒收掉的", True))
check("…but never the carried sub-bullets or the team's line below it",
      [l for l in g["archive"][0]["lines"] if "寫文件" in l or "我自己" in l], [])
check("a formatted 本週 is carried like a typed one, brackets kept whole",
      g["carry"], [{"text": "戊件事（A ／ B）", "since": "WB 10/26"}])
check("the carried sub-bullets lose their header with the archived block → a new one is needed",
      g["carry_header_needed"], True)

FMT_EX = ("#Sales Sam Rivera\n〔自動彙整 WB 10/26 · 10-27 09:40〕\n* 上週\n   * 舊事 完成\n   * 乙事 Done\n"
          "* 還沒收掉的\n   * 寫文件〔WB 9/7 起〕Done\n")
fr = T.closed_bullets(export("Nov 5, 2026\n" + FMT_EX + "Oct 29, 2026\n" + FMT_EX), NAMES, set())
check("step 7 never deletes a summary sub-bullet (`* 上週` / `   * 乙事 Done`), only the carried one",
      [e["lines"] for e in fr["closed"]], [["   * 寫文件〔WB 9/7 起〕Done"]])

import carryover as C
check("carryover counts the carried and the team's bullets, never the summary's",
      [i["raw"] for i in C.sections(FMT_MD)[0]["items"]], ["寫文件〔WB 9/7 起〕", "我自己的一行"])

check("an item splits on ／ only outside brackets",
      T.split_items("· 上週 — 審核（Hahow ／ 學員） 完成 ／ 乙 / 丙 ／ https://a.b/c"),
      ["審核（Hahow ／ 學員） 完成", "乙", "丙", "https://a.b/c"])

PLAN_MD = """\
## Nov 5, 2026
### #Sales [Sam Rivera](mailto:owner-a@example.com)
〔自動彙整 WB 11/2 · 11-03 09:40〕
· 上週 — 甲件事 完成 ／ 乙（A ／ B） WIP
· 還沒收掉的 —

  - 寫文件〔WB 9/7 起〕
- 我自己的一行
## Oct 29, 2026
"""
PLAN_ST = structure("Nov 5, 2026\n", "#Sales \n", "〔自動彙整 WB 11/2 · 11-03 09:40〕\n",
                    "· 上週 — 甲件事 完成 ／ 乙（A ／ B） WIP\n", "· 還沒收掉的 —\n", "寫文件〔WB 9/7 起〕\n",
                    "我自己的一行\n", "Oct 29, 2026\n")
fp = T.format_plan(PLAN_MD.split("\n"), PLAN_ST, "t.9")
new = "上週\n\t甲件事 完成\n\t乙（A ／ B） WIP\n還沒收掉的"
check("step 8 plans one block: un-bullet, re-tab the carried item, re-type, bullet — in that order",
      [(o["type"], o.get("start_index", o.get("index")), o.get("end_index"), o.get("text"), o.get("list_type"))
       for o in fp["ops"]],
      [("create_bullet_list", 30, 59, None, "NONE"), ("update_paragraph_style", 30, 59, None, None),
       ("insert_text", 50, None, "\t", None), ("delete_text", 30, 49, None, None),
       ("insert_text", 30, None, new, None),
       ("create_bullet_list", 30, 59 + T.utf16(new) - 19 + 1, None, "UNORDERED")])
check("…every operation names the tab", {o["tab_id"] for o in fp["ops"]}, {"t.9"})
check("…the stamp and the team's line are outside every range read before the re-type",
      all(o.get("start_index", o.get("index")) >= 30 and (o.get("end_index") or 0) < 60 for o in fp["ops"][:-1]),
      True)

LINK_MD = PLAN_MD.replace("乙（A ／ B） WIP", "[乙](https://x.y) WIP")
check("a line holding a link is skipped — re-typing would drop it",
      [b["reason"][:28] for b in T.format_plan(LINK_MD.split("\n"), PLAN_ST, "t.9")["skipped"]],
      ["a line in it holds a link — "])
TWIN_MD = PLAN_MD.replace("- 我自己的一行\n", "- 我自己的一行\n### #Ops\n〔自動彙整 WB 11/2 · 11-03 09:40〕\n"
                                            "· 上週 — 甲件事 完成 ／ 乙（A ／ B） WIP\n")
TWIN_ST = structure("Nov 5, 2026\n", "#Sales \n", "〔自動彙整 WB 11/2 · 11-03 09:40〕\n",
                    "· 上週 — 甲件事 完成 ／ 乙（A ／ B） WIP\n", "· 還沒收掉的 —\n", "寫文件〔WB 9/7 起〕\n",
                    "我自己的一行\n", "#Ops \n", "〔自動彙整 WB 11/2 · 11-03 09:40〕\n",
                    "· 上週 — 甲件事 完成 ／ 乙（A ／ B） WIP\n", "Oct 29, 2026\n")
tw = T.format_plan(TWIN_MD.split("\n"), TWIN_ST, "t.9")
check("two departments with the same stamp and summary: the heading above tells them apart",
      sorted((b["owner"], b["start_index"]) for b in tw["blocks"]),
      [("#Ops", 90), ("#Sales Sam Rivera", 30)])

DONE_MD = PLAN_MD.replace("· 上週 — 甲件事 完成 ／ 乙（A ／ B） WIP\n· 還沒收掉的 —\n",
                          "- 上週\n  - 甲件事 完成\n  - 乙（A ／ B） WIP\n- 還沒收掉的\n")
check("the post-write check reads the bullets back as the same summary",
      T.format_check({"section": "Nov 5, 2026", "blocks": [
          {"owner": "#Sales Sam Rivera", "stamp": "〔自動彙整 WB 11/2 · 11-03 09:40〕",
           "rows": ["· 上週 — 甲件事 完成 ／ 乙（A ／ B） WIP", "· 還沒收掉的 —"]}]}, DONE_MD.split("\n")),
      {"ok": True, "problems": []})
check("…and fails when a typed line is left behind",
      T.format_check({"section": "Nov 5, 2026", "blocks": [
          {"owner": "#Sales Sam Rivera", "stamp": "〔自動彙整 WB 11/2 · 11-03 09:40〕",
           "rows": []}]}, PLAN_MD.split("\n"))["ok"], False)
tw2 = T.format_plan(TWIN_MD.replace("### #Ops", "### #Sales").split("\n"),
                    [dict(x, text_preview="#Sales \n") if x["text_preview"] == "#Ops \n" else x for x in TWIN_ST], "t.9")
check("a block the heading cannot place (it matches both twins) is skipped; the unique one is not",
      ([x["start_index"] for x in tw2["blocks"]], [x["reason"][:7] for x in tw2["skipped"]]), ([30], ["matches"]))
check("a section heading twice in the structure: step 8 refuses outright",
      refuses(lambda: T.format_plan(PLAN_MD.split("\n"), PLAN_ST + [PLAN_ST[0]], "t.9")), True)
check("an already-formatted block is left alone", T.format_plan(DONE_MD.split("\n"), PLAN_ST, "t.9")["ops"], [])


# ── 21. rollup writes bullets (10-26) — the writer and the readers must agree ─
# render_block writes `上週` / `\t甲 完成`; Docs shows it as `- 上週` / `  - 甲 完成`. Whatever the
# writer emits must read back through walk_block as the summary it meant, or Friday archives it
# wrong — the writer and reader live in two files, so this is the test that ties them.
import render_block as R
REC = {"last_week": [{"text": "官網改版", "status": "DONE"}, {"text": "名單匯入（Kit ／ CSV）", "status": "WIP"}],
       "this_week": [{"text": "LINE 名單清理"}, {"text": "SEO\n三篇上稿"}],
       "numbers": {"parsed": {"報名": "72"}, "raw": "", "empty": False},
       "blocker": "", "missing_lines": ["blocker"]}
SECS = R.render(REC, {})
BODY = R.body_text(SECS)
check("rollup's body: labels alone, each item one tab in, an item's line break flattened",
      BODY.split("\n"), ["上週", "\t官網改版 完成", "\t名單匯入（Kit ／ CSV） 進行中", "本週", "\tLINE 名單清理",
                         "\tSEO 三篇上稿", "數字", "\t報名 72", "沒寫", "\t卡關"])
AS_MD = ["## Nov 5, 2026", "### #Sales", "〔自動彙整 WB 11/2 · 11-03 09:40〕", ""] + \
        [("  - " + l[1:]) if l.startswith("\t") else "- " + l for l in BODY.split("\n")] + ["- 我自己的一行"]
_, rows, _ = T.walk_block(AS_MD, 2)
check("…and reads back through walk_block as the summary it meant, the team's line outside",
      rows, ["· 上週 — 官網改版 完成 ／ 名單匯入（Kit ／ CSV） 進行中", "· 本週 — LINE 名單清理 ／ SEO 三篇上稿",
             "· 數字 — 報名 72", "· 沒寫 — 卡關"])
check("…and carryover counts none of it as the team's items",
      [i["raw"] for i in C.sections("\n".join(AS_MD))[0]["items"]], ["我自己的一行"])

blk = {"heading": "#Sales", "stamp_line": "〔自動彙整 WB 11/2 · 11-03 09:40〕", "body": "上週\n\t甲 完成"}
blk2 = {**blk, "heading": "#Ops"}
w = R.ops([blk, blk2], {"#Sales": 100, "#Ops": 300}, "t.9")
n = R.utf16(blk["stamp_line"] + "\n" + blk["body"] + "\n")
check("rollup's write: highest block first; insert, clear bullet + indent, then bullet the body only",
      [(o["type"], o.get("index", o.get("start_index")), o.get("end_index"), o.get("list_type")) for o in w],
      [("insert_text", 300, None, None), ("create_bullet_list", 300, 300 + n - 1, "NONE"),
       ("update_paragraph_style", 300, 300 + n - 1, None),
       ("create_bullet_list", 300 + R.utf16(blk["stamp_line"]) + 1, 300 + n - 1, "UNORDERED"),
       ("insert_text", 100, None, None), ("create_bullet_list", 100, 100 + n - 1, "NONE"),
       ("update_paragraph_style", 100, 100 + n - 1, None),
       ("create_bullet_list", 100 + R.utf16(blk["stamp_line"]) + 1, 100 + n - 1, "UNORDERED")])
check("…every operation names the tab", {o["tab_id"] for o in w}, {"t.9"})

# Friday: step 5 adds a typed `· 還沒收掉的 —` under rollup's bullets. Step 8 must re-type that
# mixed block whole, or one typed line stays behind every week.
MIX_MD = """\
## Nov 5, 2026
### #Sales [Sam Rivera](mailto:owner-a@example.com)
〔自動彙整 WB 11/2 · 11-03 09:40〕
- 上週
  - 甲件事 完成
· 還沒收掉的 —

  - 寫文件〔WB 9/7 起〕
## Oct 29, 2026
"""
MIX_ST = structure("Nov 5, 2026\n", "#Sales \n", "〔自動彙整 WB 11/2 · 11-03 09:40〕\n", "上週\n",
                   "甲件事 完成\n", "· 還沒收掉的 —\n", "寫文件〔WB 9/7 起〕\n", "Oct 29, 2026\n")
mx = T.format_plan(MIX_MD.split("\n"), MIX_ST, "t.9")
check("a mixed block (rollup's bullets + step 5's typed header) is re-typed whole",
      [o.get("text") for o in mx["ops"] if o["type"] == "insert_text"], ["\t", "上週\n\t甲件事 完成\n還沒收掉的"])


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
     'raw = FOOTNOTE_RE.sub("", sec[k])', 'raw = sec[k]'),
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
    ("the copy proof is skipped", 'if not copied(tree, entry):', 'if False:'),
    ("children of a closed parent are listed again",
     '            res["closed"].append(entry)\n        i = j', '            res["closed"].append(entry)\n        i += 1'),
    ("the closed chip matches any case",
     r'CLOSED_TAIL_RE = re.compile(r"(?:\s+|(?<=〕))(Done|Drop|Dropped|完成|已完成|放棄|取消)$")',
     r'CLOSED_TAIL_RE = re.compile(r"(?:\s+|(?<=〕))(Done|Drop|Dropped|完成|已完成|放棄|取消)$", re.I)'),
    # SKB-039 — where they are
    ("status chips are not stripped from keys", 'for b in {a, STATUS_WORD_RE.sub("", a)}:', 'for b in {a}:'),
    ("person names are not stripped", 'b = b.replace(name, "")', 'pass'),
    ("a truncated preview is compared whole", '(truncated and k.startswith(pk))', 'False'),
    ("the line above is not checked",
     'if q is None or not preview_matches(paragraphs[q], line_keys(above, names)):', 'if False:'),
    ("the line below is not checked",
     'if r is None or not preview_matches(paragraphs[r], line_keys(below, names)):', 'if False:'),
    ("an ambiguous bullet takes the first place",
     'if len(spots) != 1:\n            skipped.append(', 'if not spots:\n            skipped.append('),
    ("step 8 formats a block that matches two places",
     'if len(spots) != 1:\n            res["skipped"]', 'if not spots:\n            res["skipped"]'),
    ("sub-items are not checked against the Doc",
     'if not all(preview_matches(paragraphs[p + d], line_keys(entry["lines"][d], names))\n'
     '                       for d in range(n)):',
     'if not preview_matches(paragraphs[p], line_keys(entry["lines"][0], names)):'),
    ("a duplicated target heading is tolerated",
     'if len(heads) != 1:\n        raise SystemExit(f"tidy --closed:', 'if not heads:\n        raise SystemExit(f"tidy --closed:'),
    ("step 8 tolerates a duplicated section heading",
     'if len(heads) != 1:\n        raise SystemExit(f"tidy --format:', 'if not heads:\n        raise SystemExit(f"tidy --format:'),
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
    # 10-25 — carried items as bullets, chips the markdown cannot see
    ("the export's Done chip is ignored by the carry", 'if normalise(text) in chip_closed:', 'if False:'),
    ("a missing export section reads as no chips",
     'raise SystemExit(f"tidy: section {label!r} not in the export — wrong file?")', 'return set()'),
    ("bullets under the heading are not checked for duplicates",
     '                live.add(normalise(strip_status(text)))\n', ''),
    ("carried bullets below do not need the 還沒收掉的 line",
     'carried or CARRIED_BULLET_RE.match(FOOTNOTE_RE.sub("", nxt_line))),', 'carried),'),
    ("an existing 還沒收掉的 line is not noticed", 'not has_header and bool(', 'bool('),
    ("· lines are never considered for removal",
     'm = BULLET_RE.match(sec[i]) or DOT_ITEM_RE.match(sec[i])', 'm = BULLET_RE.match(sec[i])'),
    ("any · line may be removed, summaries included",
     r'r"^()·\s*((?:P\d\s+.*|.*〔\s*(?:WB\s*\d{1,2}/\d{1,2}|\d{4}-W\d{1,2})\s*起\s*〕.*?))\s*$")',
     r'r"^()·\s*(.*?)\s*$")'),
    ("a chip glued to 〕 is not read",
     r'CLOSED_TAIL_RE = re.compile(r"(?:\s+|(?<=〕))', r'CLOSED_TAIL_RE = re.compile(r"(?:\s+)'),
    ("a · line's priority chip is never stripped from its key",
     'dot, t = "·", t[1:].lstrip()', 'pass'),
    ("a status chip glued to 〕 stays in the preview key",
     r'r"(?:(?<=\s)|(?<=〕)|^)(Done', r'r"(?:(?<=\s)|^)(Done'),
    # 10-25 — last week's agenda, mid-line chips, finished blocks
    ("a mid-line Done chip is never read", 'return CLOSED_MID_RE.search(text)', 'return None'),
    ("a typed 完成 mid-line counts as a chip",
     r'r"(?<=\s)(Done|Drop|Dropped)(?=\s)"', r'r"(?<=\s)(Done|Drop|Dropped|完成)(?=\s)"'),
    ("a mid-line chip ignores an open word on the same line",
     'if not OPEN_ANY_RE.search(text):\n            return CLOSED_MID_RE', 'if True:\n            return CLOSED_MID_RE'),
    ("last week's agenda is never removed", 'if AGENDA_RE.match(sec[i].strip()):', 'if False:'),
    ("an agenda is removed without proof",
     '            if copied(tree, entry):\n                res["closed"].append(entry)',
     '            if True:\n                res["closed"].append(entry)'),
    ("the agenda block stops at its stamp",
     'while j < len(sec) and sec[j].strip().startswith("·"):', 'while False:'),
    ("a department heading is offered for closing",
     'or any(n in sec[a] for n in names):', 'or False:'),
    ("a finished-looking block with an open item is offered anyway",
     'if done >= 2 and not opened:', 'if done >= 2:'),
    ("step 8 leaves a mixed block's typed line behind",
     'if not any(sec[k].strip().startswith("·") for k in body):',
     'if not all(sec[k].strip().startswith("·") for k in body):'),
    ("a formatted label's sub-bullets are not read as its items",
     'kids.append(c.group(2))', 'pass'),
    ("the carried sub-bullets are swallowed into the block they outlive",
     'if label != CARRY_LABEL and inline is None:', 'if inline is None:'),
    ("step 7 takes a summary sub-bullet for a closed work item",
     'if i in machine:', 'if False:'),
    ("an item is split on a ／ inside brackets",
     'elif k in cuts and depth == 0:', 'elif k in cuts:'),
    ("the heading above does not break a tie between twin blocks",
     'spots = [i for i in spots if i and above.startswith(', 'spots = [i for i in spots if i or above.startswith('),
    ("an indented sub-bullet is not seen as visible",
     r'MD_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*?)\s*$")', r'MD_BULLET_RE = re.compile(r"^[-*]\s+(.*?)\s*$")'),
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

