# The Weekly Ledger

The Ledger is the weekly project cycle's memory (`SKB-044`). It is a Google Sheet that only this
skill writes, and only through the calls `scripts/ledger.py` prints. People read it; nobody edits
it. Its id is `sources.ledger.id` in the private config.

The Main Tracker stays the source of truth for status. The Ledger holds what the tracker has no
room for: a copy of every item each week, and (from Phase 3) a log of every change the cycle
makes. Machine-owned data is kept out of the sheet people edit, so a sort or a stray paste there
can never corrupt the history.

## Tabs

`ledger.py schema` prints every header and is the only place they are defined.

| Tab | Columns | Written by |
|---|---|---|
| `Weeks` | A–J: week · status · snapshot_at · cycle · tracker_id · items · first_row · last_row · digest · note. K–N (Phase 2): reports · reports_at · decisions · decisions_at. O–R (Phase 3): proposals · proposals_at · applied · applied_at | `snapshot` writes A–J last; `rollup` writes K–L, `decisions` M–N, `propose` O–P, `apply` Q–R, each as its own commit |
| `Updates` | 週 · 時間 · cycle · # · 項目 · 欄位 · 舊值 · 新值 · 原因 · 證據 · 來源 · 提議 · 核准 · proposal | `apply`, 40 rows a week, written last and only once the owner's decision is confirmed in the thread; empty in shadow mode. Its `Weeks` Q cell is what "applied" means |
| `Proposals` (Phase 3) | week · proposed_at · n · # · 項目 · 欄位 · 現值 · 建議值 · 原因 · 證據 · 來源 · 信心 · 決定 · 決定_at · 結果 | `propose` writes the rows, 40 a week; `apply` rewrites them with the owner's 決定 and the 結果 (would-apply in shadow mode · applied · skipped · 退回 · 未回覆). That rewrite is a block write too, so it re-stamps `Weeks` O–P: after `apply`, `proposals_at` is when the decisions were recorded, and each row's `proposed_at` keeps when it was proposed. A 決定 is provisional until `Weeks` Q reads `ok`: `apply` writes the `Updates` block (and with it Q) only after its confirmation is in the approval thread |
| `Snapshot` | week · snapshot_at · cycle, then the tracker's 13 columns exactly as named | `snapshot` |
| `Reports` (Phase 2) | week · posted_at · owner · 部門 · 上週 · 本週 · 數字 · 卡關 · format | `rollup`, one row per poster |
| `Decisions` (Phase 2) | week · 會議日期 · 類型 · 內容 · 負責人 · 期限 · 關聯 # · 來源 | `decisions`; 類型 is 決議, or 待決 when the owner or the date is missing |

A beat's cell pair in the `Weeks` row is how a reader tells "none" from "never recorded": an empty
status cell means the beat never recorded the week, while `ok` over an empty block means it
recorded it and there was nothing. Phase 4 adds its own tab (evidence) when it is built.

**Weekly blocks.** `Reports` and `Decisions` hold 20 rows a week, `Proposals` and `Updates` 40;
week k owns rows 2 + size·k … 1 + size·(k + 1). `ledger.py block` writes any of them, checks the
`Weeks` header reaches its own cells (A–N for the Phase 2 blocks, A–R for the Phase 3 ones), reads
the block back, and commits the beat's cell pair last.

## Layout v1: every week has fixed rows

Week *k* counts from `sources.ledger.epoch_week` (`2026-W40` is *k* = 0):

- its `Weeks` row is **2 + k**
- its `Snapshot` block is rows **2 + 100k … 101 + 100k** (100 rows; the tracker has 55 items)

| Week | k | Weeks row | Snapshot block |
|---|---|---|---|
| 2026-W40 | 0 | 2 | 2–101 |
| 2026-W41 | 1 | 3 | 102–201 |
| 2026-W53 | 13 | 15 | 1302–1401 |
| 2027-W01 | 14 | 16 | 1402–1501 |

**Why fixed rows instead of appending.** `read_sheet_values` shows at most 50 rows, so finding
"the end of the tab" would mean trusting a long read copied by hand. A wrong end is the one
mistake that writes over history. Fixed blocks mean no step ever needs to know where a tab ends,
and a half-finished run is simply overwritten in place by the next one.

`Reports` and `Decisions` use the same rule with 20 rows per week: rows **2 + 20k … 21 + 20k**.
`ledger.py block` writes them (start → plan → check → confirm, the same read-back before the
commit), and the commit is the beat's own cell pair in the week's `Weeks` row.

**Never change `epoch_week` or the slot size** once a week has been written: every later week's
rows are computed from them. `ledger.py` refuses when the `Weeks` row it computes holds a
different week.

## The order a snapshot commits in

1. Read the tracker in 50-row pages (`'H2 專案項目'!A1:M50`, `A51:M65`).
2. Write the week's rows into its block as RAW text, then clear the rest of the block.
3. Read the block back, and read the tracker again.
4. `check` compares both, cell by cell, with what was planned. Any difference stops the run here.
5. Only then write the `Weeks` row (`status = ok`, the item count, the rows used, a digest), and
   read it back.

A week counts as snapshotted **only when its `Weeks` row reads `ok`**. Rows in a block without that
row are an unfinished run and mean nothing.

## Reading one week back

1. Read the week's `Weeks` row. Not `ok` → the week has no snapshot. Say so; never fall back to
   an earlier week without saying which.
2. Read its block in two pages (`Snapshot!A<first>:P<first+49>`, then the rest), never more than
   50 rows at once.
3. Take exactly `items` rows, starting at `first_row`. Rows match across weeks by `cycle` plus `#`.

Monday's "did Friday's close-out run?" check (Phase 2) is step 1 for the previous ISO week.

**What changed between two weeks:** `ledger.py diff --a <older block> --b <newer block> --updates
<Updates rows>`. A cell change counts as logged only when an `Updates` row with the same cycle, `#`,
column and new value was written between the two snapshot times, never by matching week labels. A
change made and then changed again by hand therefore shows as manual, and its log row is listed as
an orphan.

## Setup (done once, 2026-10-02)

Created through the Google Workspace tools, not by a beat. Setup needs create, move and resize
tools that no scheduled run should hold.

1. `ledger.py schema` → `create_spreadsheet(title="[3.3] Weekly Ledger 週帳本（machine-owned · 請勿手改）", sheet_names=["Weeks","Updates","Snapshot"])`.
2. `update_drive_file` → into the PMO folder `[3.3] 專案管理 PMO`, with a "machine-owned" description.
3. Write the three header rows RAW, exactly as `schema` prints them.
4. Grow `Snapshot` to 5,400 rows (`resize_sheet_dimensions(insert_rows=4400)`), which is about a
   year of weeks, and freeze row 1 on each tab.
5. Put the id in `sources.ledger.id`, and `epoch_week` = the first week to be snapshotted.

**Phase 2 setup (once, before installing Phase 2).** `create_sheet` → `Reports`, then `Decisions`;
write their header rows RAW exactly as `schema` prints them; write `Weeks!K1:N1` (reports ·
reports_at · decisions · decisions_at). `ledger.py block` refuses to write until the `Weeks` header
reads A–N, so a half-done setup cannot be written into.

**Phase 3 setup (once, before installing Phase 3a).** `create_sheet` → `Proposals`; write its header
row RAW exactly as `schema` prints it and freeze row 1; grow `Proposals` and `Updates` to 2,100 rows
(a year of 40-row weeks); write `Weeks!O1:R1` (proposals · proposals_at · applied · applied_at).
`ledger.py block` refuses the Phase 3 blocks until the `Weeks` header reads A–R; the Phase 2 blocks
need only A–N, so `rollup` and `decisions` keep working while the setup is half done.

**Growing the grid.** `ledger.py` warns when fewer than eight weeks of rows remain, and refuses a
week whose block would not fit (exit 5). Add rows to the end of `Snapshot` with
`resize_sheet_dimensions(insert_rows=…)`. Appending rows never moves an existing block.

## Rehearsing

Rehearse against a throwaway copy of the Ledger, never the real one before the week's unforced
run. Create it as in Setup steps 1 and 3, make a copy of the config whose `sources.ledger.id` points at
it, and run the runner with `ZYNKR_OPS_WEEKLY_CONFIG`, `ZYNKR_OPS_WEEKLY_STATE` and
`ZYNKR_OPS_WEEKLY_LOG` set. The runner passes the config on as `config=<path>`. Delete the copy and
its config afterwards.

## Known limits

- Person chips are stored as display names.
- A copy mistake made identically in both tracker reads cannot be caught; it would surface as a
  spurious change the following week.
- `modify_sheet_values` cannot be limited to one spreadsheet. The calls carry the Ledger id, and
  the Ledger's tab names do not exist in the tracker, so a call aimed at the wrong file fails on
  its range instead of writing.
