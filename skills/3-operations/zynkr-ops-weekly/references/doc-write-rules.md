# Writing into the Doc

The Doc is a document people are actively editing. Everything here follows from one rule:
**a bot that silently rewrites human prose is a bot nobody trusts by week two.**

## The marked block

Auto-content only ever appears inside a block stamped with the week and a timestamp:

```
〔自動彙整 WB 9/14 · 09-15 12:00〕
● 上週
    ○ 官網改版 完成
    ○ 名單匯入 進行中 ↻2週
● 本週
    ○ LINE 名單清理、SEO 三篇上稿
● 數字
    ○ 報名 72
    ○ 訂閱 +18   〔KPI Dashboard!C14〕
● 卡關
    ○ 名單匯入需要決定是否買 Kit 方案
```

Bullets since 2026-10-26 (the owner: one item per bullet, no typed `·` lines). Sections from
before then hold the same lines typed, `· 上週 — 官網改版 完成 ／ 名單匯入 進行中 ↻2週`; every
reader takes both shapes (`tidy_blocks.walk_block`, `carryover.LABEL_RE`). The labels alone on
a bullet are what mark the block as the machine's — never reword them. `render_block.py ops`
computes the write: insert, clear any bullet and indent the text took from where it landed, then
one list over the body.

`WB 9/14` is the **week beginning** — the Monday that opens the week, which is also the day
the team posts. It replaced the ISO ordinal (`W38`) on 2026-09-15: a week number is a figure
the reader has to stop and count, and everything else in this Doc is dated.

- One block per department heading, placed **directly under the heading**, above whatever a
  human has written there.
- The stamp is also the idempotency key. Before writing, search the target section for
  `〔自動彙整 <week>`. Present → do not write a second block.
- Never modify, reflow, or delete a line outside a stamped block.
- Friday's `tidy` (step 8) re-types any block still holding a typed `·` line — one from before
  10-26, or its own `· 還沒收掉的 —` under rollup's bullets — into the same bullet shape.
- Promotion (turning an auto line into a real Doc line) and deletion are **human acts**, done at
  Thursday's meeting. The skill never promotes its own output.
- Every number carries its source in `〔…〕`. A number without a citation should not be written.

## Targeting the tab — the part that bites

The Doc is tabbed. Verified behaviour of the tools:

| Tool | Tab support | Use it for |
|---|---|---|
| `batch_update_doc` | **Yes** — every operation takes an optional `tab_id` | All writes |
| `inspect_doc_structure` | **Yes** — `tab_id` + `detailed=true` | Getting real indices inside the tab |
| `insert_doc_elements` | **No tab parameter at all** | **Do not use on this Doc** — it cannot target the tab |
| `get_doc_as_markdown` | No tab parameter — returns the whole Doc | Reading routing + sections (parse the tab out) |

So the write path is fixed: `inspect_doc_structure(tab_id, detailed=true)` to find indices, then
`batch_update_doc` with `tab_id` set on **every** operation. Omitting `tab_id` on even one
operation in the batch sends that operation to the main body — which on a tabbed document is not
the tab you are looking at, and the edit lands somewhere invisible.

The same trap exists in Apps Script, where `doc.getBody()` returns the main body rather than the
tab; see `scaffold.md` for the `getTabs()` walk that avoids it.

## Index arithmetic

`inspect_doc_structure(detailed=true)` returns `elements[]` with `start_index`, `end_index` and
`text_preview`. Match the department heading by its `text_preview`, then insert at the index
immediately after that heading's `end_index`.

> **Insert bottom-up.** Every insertion shifts the indices of everything after it. Writing
> several department blocks in one batch using indices read from a single inspection corrupts
> every position after the first. Sort the insertions by index **descending** and apply them in
> that order, so each write only shifts text that has already been placed.

Alternative, when a section is being built from scratch rather than patched: insert everything
with `end_of_segment: true` (no index arithmetic at all), then do a second pass with real
indices for formatting. That is the documented two-phase workflow, and it is the safer path
whenever the target is the end of the tab.

## Removing a block — the Friday `tidy` (SKB-030)

`tidy` is the only mode that deletes, and it deletes **only** whole stamped blocks that
`tidy_blocks.py` marked for archiving — plus, in its step 7, the `Done`/`Drop` bullets,
single-item `·` lines and last week's agenda block that `tidy_blocks.py --closed` returned
(SKB-039, below). Those `·` lines are the one exception to "never part of a block": a carried item
sits inside its block, and removing it a week after it was closed is the point. The agenda block
(`〔自動彙整 …〕本週會議議程`) goes whole, and only as a verbatim copy of the previous week's: the
scaffold copied it forward, and until Thursday's `agenda` writes the new one it is last week's
agenda sitting in this week (the owner, 10-25). It never removes any other line of a block, never
any other human line, and never the block it decided to keep. A whole finished sub-heading
(`done_blocks`) is only ever asked about.

Carried items are written as ○ sub-bullets under the `· 還沒收掉的 —` line since 2026-10-25.
Indices as in every other insert: from one fresh `inspect_doc_structure`, and the bullet
operations after the insert, with the ranges recomputed from where the text landed. The recipe,
proven on the live Doc the same day, in one `batch_update_doc`:

1. Each item paragraph starts with exactly one tab (`\t<item>〔<since> 起〕`).
2. `create_bullet_list` `UNORDERED` from the header paragraph through the last item.
3. `create_bullet_list` `list_type: "NONE"` over the header paragraph alone, then
   `update_paragraph_style` `indent_start: 0, indent_first_line: 0` over it.

The traps, each hit on 10-25:
- **Docs will not nest the first line of a list.** Tabs on every paragraph of a new list all
  come out level 0; the level-0 header in the range is what lets the items reach level 1.
- **Leftover indent adds a level.** A paragraph that was typed or un-bulleted keeps its indent
  (`deleteParagraphBullets` even adds some), and `createParagraphBullets` counts it on top of
  the tab: one tab came out level 2. Zero `indent_start`/`indent_first_line` first.
- **`create_bullet_list` with `nesting_level` does not help here:** it inserts the same tabs.
- To re-nest existing bullets: `NONE` over them, zero the indent, then steps 1–3.

- **Copy to the 封存 tab first, verify, then delete.** The order is the whole safety design. A
  crash between the two leaves the content duplicated, which is visible and repairable; the
  reverse order loses it. SKB-029 threw exactly here and survived only because the copy went
  first.
- **Delete by descending index**, for the same reason insertions go bottom-up: each deletion
  shifts everything after it. Collect every range from one `inspect_doc_structure(tab_id,
  detailed=true)` call, sort descending, then issue them in that order.
- **Never delete the last paragraph of the tab.** A Docs segment must end with one. In practice
  every block group is followed by a heading or a human line, so this cannot arise — but assert
  it rather than assume it. This is the Docs-API face of the Apps Script error that killed
  SKB-029: `Can't remove the last paragraph in a document section.`
- **Re-read and confirm one stamp per group** before reporting `status=ok`. A partial delete
  that leaves half a block is worse than no delete, because the next run sees a single block
  and treats the group as already tidy.

## Removing a closed human bullet — `tidy` step 7 (SKB-039)

- **Each read path hides something.** The Drive plain-text export (`get_drive_file_content`) is
  the only one that prints dropdown chips (`P0`, `Done`, `Drop`). `inspect_doc_structure` is the
  only one with indices, and its previews drop every chip — priority, status, person, file — and
  stop at 100 characters. `get_doc_as_markdown` is the only one that marks headings, including
  list-item headings such as `Finance` that the export prints as `* Finance <owner>`. So
  `tidy_blocks.py --closed` needs all three, and you never hand-match a bullet to an index.
- **Same text is not same paragraph.** An open bullet whose file chip vanished from its preview
  reads exactly like a Done bullet. The script pins a bullet only where it AND the nearest
  non-empty lines above and below it all match, at exactly one place; otherwise it skips.
- **A range covers the bullet and all its sub-items**, whole paragraphs with their newlines, so
  the list closes up cleanly. A range that would contain a heading is never produced.
- **A chip need not end the line.** `* 課程剪輯   Done 進度：2-4` is closed: the person typed the
  progress after the chip. Mid-line, only the English chip words `Done`/`Drop`/`Dropped` count,
  between spaces, and never on a line that also says `In Progress`/`進行中`/…; a typed `完成`
  mid-line is a verb as often as a status, so it counts only at the end (10-25).
- **Plan → fresh re-check (`--expect`) → delete → `--postcheck`.** The plan is re-derived from
  new reads right before the delete and must be identical (no status flipped, no index moved);
  afterwards the section must be the planned one minus exactly the deleted lines. The Docs API
  offers no revision guard on `batchUpdate` here, so issue the delete straight after the re-check.
  An edit in that window to a line that REMAINS is caught by the post-check; a change to a line
  that was deleted is not, and that line then lives only in the previous section.
- **The export covers every tab.** The 封存 tab repeats week labels, so section checks look only
  at the leading run of dated sections — never "is this label unique in the whole export".

## Verify the write

Re-read the section after writing and confirm the stamp is present exactly once. Docs writes
can partially apply when an index is stale; a silent partial write is worse than a failure,
because the next run's idempotency check sees the stamp and skips the repair.

## What never gets written here

- The H2 tracker's status column — that belongs to `planning-tracker-sync`.
- A fresh week skeleton — that belongs to Apps Script, and rebuilding it would destroy the owner
  person chips that make routing work. Chips can be **copied** but not **created**, by any API.
- Anything into a section whose Thursday is already in the past.
