---
name: ops-weekly-doc
sheetId: "3.25"
description: >-
  The writer of a small team's weekly operations Google Doc in the weekly loop. On Thursday it
  writes each team's section (進度 · 卡關 · 下一步 · 待討論) from the team's harvest, inside marked
  〔自動彙整〕 blocks only (sections); on Friday it writes the meeting's minutes from the Fireflies
  transcript into the Doc and the Weekly Ledger (minutes), then trims the copied week section and
  fills next week's with the agreed actions (tidy). It never edits a human's line, never rebuilds
  the skeleton the Apps Script scaffold copies, and never writes a past week. Trigger on
  "/ops-weekly-doc", "週會紀錄", "會議紀錄寫進 Doc", "整理週報 Doc", "tidy the weekly doc", "write the
  team sections", "meeting minutes from Fireflies". BOUNDARY — do NOT hijack: /zynkr-ops-weekly (the
  Monday recap and Thursday collect), /ops-weekly-tracker (the Main Tracker: 【週結】, apply,
  snapshot), /project-manager (the schedule), /project-minutes-sync (one client project's minutes
  into its own tracker), /admin-meeting-prep (packets for external meetings).
category: operations
project: ops-weekly-doc
platform: claude
status: WIP
visibility: public
author: Peter Tu
input: "A mode (sections, minutes or tidy) and the ISO week the runner passes as week=; all identifiers come from the private config at ~/.config/zynkr/ops-weekly.json."
process: "Anchor on today and the target Thursday → read routing from the Doc's owner chips → read the week's evidence → write marked blocks only, through scripts that plan every range → read back and assert → receipt."
output: "Each team's 〔自動彙整〕 block in this week's section, the meeting's minutes block and Decisions rows, and a tidied week section with next week's actions filled in."
synergy: [zynkr-ops-weekly, ops-weekly-tracker, project-manager, project-minutes-sync, zynkr-gm]
executed_by: internal-user
house-style: bound

---

# ops-weekly-doc

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill ops-weekly-doc
```

The Doc's part of the weekly loop (`SKB-091`). The loop is split by the store each part writes:

| Skill | Writes | Beats |
|---|---|---|
| `zynkr-ops-weekly` | mail, Chat, the Weekly Ledger | `recap` (Mon), `collect` (Thu) |
| **`ops-weekly-doc`** (this skill) | **the weekly operations Doc**, and the minutes' Ledger rows | `sections` (Thu), `minutes` · `tidy` (Fri) |
| `ops-weekly-tracker` | the Main Tracker, and its own Ledger blocks | `propose` (Fri) · `apply` · `snapshot` (Fri → Sun) |
| `project-manager` | nothing but its notice mail | runs the beats on time, mails the owner when one did not run |

`project-manager`'s runner starts each beat with `/ops-weekly-doc <mode> week=<ISO week>`, and in a
rehearsal `config=<path>`. Use the week as given; never work it out again mid-run.

**`<core>`** below is the `zynkr-ops-weekly` folder next to this skill's base directory
(`<base>/../zynkr-ops-weekly`). The routing parser and the Ledger code live there and only there.

| When (Taipei) | Mode | What happens |
|---|---|---|
| Thu 09:30 → 13:30, after `collect` (or from 13:00 without it) | `sections` | Each team's 進度 · 卡關 · 下一步 · 待討論 in this week's section, from the Ledger's Harvest rows |
| Thu 21:00 | — | The weekly meeting. The team edits the Doc live |
| Thu 23:00 | `scaffoldNextWeek` | **Apps Script**: duplicates the newest week section and re-stamps next Thursday |
| Fri 08:00 → 17:30 | `minutes` | The meeting's decisions, actions and blockers from its Fireflies transcript, into the Doc and the Ledger |
| Fri 09:00 → 17:30, after `minutes` | `tidy` | Keep the newest auto block per department, archive the rest, carry open items, fill next week's 下一步 |

**Why the scaffold is not this skill's job.** Duplicating a section is purely mechanical and must never
fail, so it belongs to Apps Script, whose authorisation does not expire. In the week this skill breaks
entirely, the skeleton still opens and Thursday still has a page. See `references/scaffold.md`.

> **`tidy` is what keeps the Doc bounded.** Every writer here is insert-only and the scaffold copies the
> newest section *verbatim*, so without `tidy` each section would inherit every `〔自動彙整〕` block ever
> written, and every closed bullet. `tidy` deletes only copies whose originals sit in the frozen
> previous section (`SKB-029`, `SKB-030`).

## Configuration

The same private file as the rest of the loop, `~/.config/zynkr/ops-weekly.json` (override with
`ZYNKR_OPS_WEEKLY_CONFIG`); its schema and notes are `<core>/references/config.example.json` and
`<core>/references/config.README.md`. This skill reads `google_account`, `doc.id` · `doc.tab_id` ·
`doc.tab_name`, `doc.archive_tab_id` · `doc.archive_tab_name` (a sibling tab in the *same* Doc:
`scripts/carryover.py` reads all tabs as one stream to compute `↻N週`), `reporters`, `sources.ledger`
and `meeting.calendar_title`. If a value is missing or still a placeholder, **fail loud**; never guess
an id, and never fall back to a hardcoded department map.

## Required reading (before acting)

| File | Read when |
|---|---|
| `<core>/references/routing.md` | Every mode: how to read owner chips out of the Doc, and the off-by-one |
| `references/doc-write-rules.md` | Every mode: marked blocks, tab targeting, idempotency |
| `<core>/references/wording.md` | **Always, before writing any zh-TW the team will read** |
| `references/scaffold.md` | Installing or debugging the Apps Script half |
| `<core>/references/ledger.md` | `minutes`, which writes Decisions rows |

## Step 0 — Anchor on today, and get the off-by-one right

Resolve today in `Asia/Taipei`. Compute:

- **Week label** — `WB 11/2`, the **Monday that opens the week**: what goes in every stamp the team
  reads. **ISO week key** — `2026-W45`, machine-only: the receipt's `week=`.
- **The target Thursday** — the Doc names its sections by **Thursday** date. On Thursday it is
  **today**; on Friday, before the scaffold has run, it is still yesterday's section for `minutes`, and
  next Thursday's (the scaffold's new section) for `tidy`.

> **Never write into a past section.** Assert the target Thursday is the one this mode owns. If the
> newest section in the Doc is already in the past on Friday, the scaffold did not run: say so loudly
> rather than writing into a stale section.

## Step 1 — Read routing from the Doc (every run)

Fetch the Doc **as markdown** — `get_doc_as_markdown`. `get_doc_content` returns plain text and
**silently strips person chips**, which is exactly the data the routing depends on. Pipe it through
`<core>/scripts/parse_routing.py` to get `{heading → owner email}`; rules are in
`<core>/references/routing.md`. Every email must appear in `reporters` or be a known non-reporting
owner; an unexpected address means a chip changed, so surface it in the report.

## The modes

### `sections` (Thu 09:30 → 13:30, after `collect`)

One `〔自動彙整〕` block under each team heading of **this Thursday's** section, holding 進度 · 卡關 ·
下一步 · 待討論 for that heading's owner. The inputs are the Ledger's `Harvest` rows (from this
morning's `collect`) and Monday's recap facts: overdue items, last week's meeting actions, the Pulse,
paused items, and items that look done but are not marked 完成. `scripts/sections.py` decides every
line. The write path is the fixed one in `references/doc-write-rules.md`. If a script exits non-zero,
stop and do not write the Doc: receipt `status=failed delivered=<its message>`.

1. `python3 scripts/sections.py start --week <ISO week>`. Make every Ledger read it prints (the
   `Weeks` row, then the `Harvest` block in pages of 50 rows), saving each result unchanged to the
   path it gives. Keep its `label` (`WB 11/2`).
2. **Routing** (above): save `parse_routing.py`'s output as `routing.json`.
3. **Idempotency.** In the markdown you just read, find this Thursday's section and search it for
   `〔自動彙整 <label>`. If it is there, receipt `status=ok delivered=already-written` and stop. Friday's
   fill writes into the *kept* block, which still carries last week's stamp, so it never matches.
4. `python3 scripts/sections.py render --dir <dir> --routing routing.json --stamp "<MM-DD HH:MM>"`.
   Save what it prints as `blocks.json`.
   - **What it writes:**
     - a person with no harvest, a quiet harvest, or no `collect` at all gets 「本週無資料」 under 進度;
     - 待討論 offers at most three keep / hand over / drop choices, then the sure gaps;
     - 下一步 is left out when last week's `tidy` already filled the meeting's actions into the kept block.
   - **What it never writes:** a person it cannot name, and a heading it cannot route.
5. `inspect_doc_structure(tab_id, detailed=true)`. Write `{"<heading>": <end_index>}` to `at.json`
   for each block's heading **inside this Thursday's section**; a heading repeats in every week, so
   match it between this section's date heading and the next. Run `python3 scripts/render_block.py ops
   --blocks blocks.json --at at.json --tab <tab_id>` and apply what it prints in **one**
   `batch_update_doc`, exactly as listed.
6. Read the Doc again and confirm one `〔自動彙整 <label>` stamp per block heading in the section.
7. Receipt `status=ok delivered=<n>-blocks;quiet-<n>;harvest-<recorded|not-recorded>;facts-<found|none>`.
   The report names `owners_without_name` (an owner chip missing from `chat_ids`) and
   `harvest_without_heading` (a person with a harvest but no heading), so the owner can fix either.

### `minutes` (Fri 08:00 → 17:30)

The meeting's minutes, from its own transcript, into Thursday's section (the meeting just held) and
the Ledger's `Decisions` block. `scripts/minutes.py` finds the transcript and checks what you read
out of it; it never talks to Google or Fireflies itself. Each step prints the calls to make and a
path to save each result to **word for word**; the next step reads them back.

1. `python3 scripts/minutes.py start --week <ISO week>`. Make its two calls: the Fireflies listing
   for the meeting day (saved as `listing.json`) and the tracker's size.
2. `python3 scripts/minutes.py find --dir <dir>`. It picks the one transcript titled
   `meeting.calendar_title` on that Thursday (Taipei), never the latest one, and prints the fetch
   call plus the tracker reads (`#` and 項目). Make them all.
   - **Exit 4, no transcript:** read Thursday's section of the Doc as edited (`get_doc_as_markdown`)
     and take the minutes from there, with `"source": "doc"`. Say so in the report.
3. **Read the transcript and write `minutes.json`** in the shape the script's docstring gives:
   decisions, actions (`what`, `owner`, `due`, `item`, `new`), blockers, topics, dropped, progress.
   - Write only what was said. An owner is a roster name exactly as the config's `chat_ids` writes it,
     `All`, or `""` when nobody took it. A `due` is a date someone said, or `""`; never infer one.
   - `item` is a tracker `#` when the talk was plainly about that item; leave it out when unsure.
   - Transcription mangles names; map a misheard name only when the context settles it.
4. `python3 scripts/minutes.py check --dir <dir> --input minutes.json`. It refuses an owner off the
   roster, an item `#` the tracker lacks, a date that is not a full date, text over 200 characters
   and more rows than the block holds. Fix `minutes.json` and run it again until it passes. Then it
   writes `rows.json`, `block.json` and `fill.json`.
5. **The Ledger first.** `python3 <core>/scripts/ledger.py block start --tab Decisions --week <ISO
   week> --rows <dir>/rows.json`, then `plan`, `check` and `confirm` as `<core>/references/ledger.md`
   describes. An action without an owner and a date is written 狀態 `待定`; it stays open.
6. **Then the Doc.** Search Thursday's section for a line that starts with `doc_key.starts` and
   ends with `doc_key.ends`. If one is there, the minutes are already written: write nothing. If not,
   read `inspect_doc_structure` for the tab, save `{"<heading>": <that heading's end_index>}` as
   `at.json`, and run `python3 scripts/render_block.py ops --blocks <dir>/block.json --at at.json
   --tab <tab_id>`. Apply its operations in **one** `batch_update_doc`, then re-read the section and
   confirm the block is there once, under the date heading.
7. Keep `fill.json`: `tidy` writes it into next week's section (step 9).

Fireflies is read here and nowhere else. The minutes never go to the Chat space, and the progress
lines go to the Ledger only. Receipt `delivered=` is the `delivered` value `check` printed.

### `tidy` (Fri 09:00 → 17:30, after `minutes`)

Runs the morning after the scaffold. Its whole job is to undo the one thing the scaffold does
badly: it copies the week section forward **verbatim**. The auto blocks travel with it and
`sections` (the Tuesday `rollup` until v4) only ever prepends. By 2026-09-15 a single section carried **22 blocks in 7 groups**,
four deep under some departments. That is the growth engine of the Doc, and it is what the owner's
08-27 comment was about. Finished human bullets travel too: a `Done` or `Drop` line was re-pasted
into every new week until someone deleted it by hand (the owner's 09-18 comments, `SKB-039`).

> **Why this is safe to delete, and the one assumption it rests on.** Every block `tidy`
> removes is a *copy* the scaffold made of a block that still sits in the **previous week's
> section**, which is frozen and never edited again. Removing it destroys nothing. If the
> scaffold ever stops copying forward, this argument dies and `tidy` must be re-proved before
> it runs again.

1. **Refuse to tidy a past section.** Resolve the target Thursday as in Step 0 and assert it is
   **≥ today**. On a Friday that is only true if Thursday's scaffold fired. If it did not, stop
   and report — and say so loudly, because this is the earliest the loop can detect a failed
   scaffold, six days before `sections` needs the section.
2. Fetch the Doc as markdown, and the Drive plain-text export with `get_drive_file_content` — the
   only read that shows a `Done`/`Drop` chip. Save the export as `e0` and run
   `python3 scripts/tidy_blocks.py --input <markdown> --export e0`. It returns, per department
   group: the block to `keep`, the blocks to `archive`, the still-open items to `carry` and
   `carry_header_needed`. Without `--export` an item someone marked `Done` is carried again,
   reopened, because the markdown hides the chip. It writes nothing and makes every judgement
   call — do not re-derive its decisions by hand.
3. **Copy the archived blocks to the 封存 tab first, and verify they landed.** Append under a
   `<section label>` heading so the trail stays readable. Only then delete. Copy → assert →
   delete, never the other order.
4. **Delete the archived blocks from the live tab, by descending index.** Use
   `inspect_doc_structure(tab_id, detailed=true)` to map each block line to its range, sort
   descending, and `batch_update_doc` with `tab_id` on **every** operation. The index rules and
   the tab trap are in `references/doc-write-rules.md`; they are not optional here.
5. **Write the carried items as bullets, after the kept block's last line** (the owner, 10-25).
   If `carry_header_needed`, first add a `· 還沒收掉的 —` line as the kept block's new last line;
   never write a second one. Then insert each item as its own paragraph, `\t<item>〔<since> 起〕` —
   one leading tab, no `·` — and make them **sub-bullets of that line** (the owner, 10-25). Docs
   nests a line only under a level-0 line of the same list, so in ONE `batch_update_doc`
   (`tab_id` on every operation): `create_bullet_list` `UNORDERED` from the `· 還沒收掉的 —`
   paragraph through the last item (the tabs become level 1), then `create_bullet_list`
   `list_type: "NONE"` over the header paragraph alone, then `update_paragraph_style`
   `indent_start: 0, indent_first_line: 0` over it, so the header is a plain typed line again and
   the items read as ○ sub-bullets under it. Items already under the header extend that list:
   include them in the range. Recipe and the traps: `references/doc-write-rules.md`. A bullet
   ends the block, so the next `tidy` reads these as the team's lines: they are never archived and
   never re-typed, so a chip someone adds stays. When an owner marks one `Done` or `Drop`, step 7
   removes it the week after. `carry` includes the items on an archived block's own `還沒收掉的`
   list, with their **original** `since` week, and items an archived block's `上週` reported still
   open (`進行中`/`卡住`/…) that its `本週` did not plan again. It leaves out anything a bullet under
   the same heading already names, and anything a chip in `e0` marks `Done`/`Drop`.
6. Re-read the section and confirm: one stamp per group, the human lines below each block
   untouched, the carried items present as bullets, and the archived text present in the 封存 tab.
7. **Remove closed human bullets** (`SKB-039`). A bullet whose status chip reads `Done` or `Drop`
   is deleted from this new section — the week it was closed in keeps it. So is a typed `·` line
   that is one work item: a carried item from before 10-25 (`· 更新一篇seo〔WB 8/24 起〕Done`) or one
   that starts with a priority chip (`· P2 Update content matrix Drop`). A summary line such as
   `· 上週 — 甲 完成` never is. A chip with typed progress after it closes a bullet too
   (`* 課程剪輯   Done 進度：2-4`). So does last week's agenda: the `〔自動彙整 …〕本週會議議程`
   block the scaffold copied in goes whole; the week it was written keeps it (the owner, 10-25).
   **You never choose a line or an index yourself; `tidy_blocks.py` does, and every step below is a gate.**
   Run it only after step 6 confirmed the block writes — the Drive export can lag a write by
   about a minute, and a stale export makes the script skip or refuse rather than delete.
   1. **Plan.** Fetch the Drive plain-text export with `get_drive_file_content` (the only read path
      that renders `P0`/`Done`/`Drop` chips) and a **fresh** `inspect_doc_structure(tab_id,
      detailed=true)` (steps 4–5 moved every index). Save them as `e1` and `s1`, then run exactly:
      `python3 scripts/tidy_blocks.py --closed --export e1 --structure s1 --markdown <step-2
      markdown> --section "<target Thursday>" > plan.json`
      The markdown supplies the headings and person names the other two reads hide.
      - **Non-zero exit** (no JSON — e.g. wrong tab, the export and structure disagree on the
        section boundary): delete nothing, report `partial` with the message.
      - `refused` set, or `closed` empty: step 7 is done; report it (with `skipped[]`) and stop.
   2. **Re-check on fresh reads, then delete at once.** Fetch the export and the structure
      **again**, save them as `e2` and `s2`, and run exactly — note the **different output file**,
      a `> plan.json` here would empty the plan it is checking against:
      `python3 scripts/tidy_blocks.py --closed --export e2 --structure s2 --markdown <step-2
      markdown> --section "<target Thursday>" --expect plan.json > recheck.json`
      Non-zero exit means the section changed since the plan: **delete nothing**, report
      `partial`, and let the next hourly retry start over from 7.1. On exit 0, go straight to 7.3 —
      no other tool call in between.
   3. **Delete** every `closed[]` range from `plan.json` in one `batch_update_doc` of `delete_text`
      operations, `tab_id` on **every** operation, **in the order listed** (highest index first).
      Nothing else.
   4. **Post-check.** Fetch the export a third time as `e3` and run:
      `python3 scripts/tidy_blocks.py --closed --export e3 --section "<target Thursday>"
      --postcheck plan.json`
      It passes only if the section is exactly the planned one minus the deleted lines. If the
      export still shows the deleted lines, wait a minute and fetch once more before judging. If it
      fails, report `failed` with its message and **do not delete again this run** — the fix is
      File › Version history, and every deleted line is still in the previous section.
   5. `skipped[]` is reported, never deleted. Each entry says why: an open sub-item, a heading
      inside it, not a verbatim copy under the same heading in last week's section, or no single
      place in the Doc that matches it together with the lines above and below.
   6. `done_blocks[]` is **asked about, never deleted**: a sub-heading whose chipped items are all
      `Done`/`Drop`, none open — `Claude Code 課程` after the course launched, which the owner
      closed by hand on 10-25. Only a person knows a project is over. Put each one in the run's
      report as 「整塊看起來做完了：<heading>（<done> 項都 Done／Drop）— 要整塊收掉嗎？」; the
      owner deletes it, or says so and a session removes it. Department headings are never
      offered.

   The script only returns a bullet that sits, with its whole subtree, verbatim in the previous
   week's section under the same heading — the same safety argument as the block delete, enforced
   rather than assumed. An item closed on Friday morning in the new section is left for next week.
   **Residual risk:** `batch_update_doc` has no revision guard. An edit landing between the 7.2
   fetch and the 7.3 delete — keep it short, it is the whole reason 7.3 follows at once — is not
   seen before the delete. The post-check then catches any damage to lines that REMAIN, but not a
   change to a line that was deleted (say `Done` flipped back to `In Progress` in that window);
   that line survives only in the previous section.
8. **Make the kept blocks bullets** (the owner, 10-25: no typed `·` lines after tidying, one
   item per bullet). Rollup writes `· 上週 — 甲 完成 ／ 乙 WIP`; after this step the block reads
   ```
   〔自動彙整 WB 10/19 · 10-20 09:40〕
   ● 上週
       ○ 甲 完成
       ○ 乙 WIP
   ● 本週 …
   ● 還沒收掉的
       ○ 更新一篇seo〔WB 8/24 起〕
   ```
   The stamp stays a plain line: it is the idempotency key. Items split on `／` only outside
   brackets. **You never compute an index; the script does.**
   1. Fresh reads: the markdown as `m4` and `inspect_doc_structure(tab_id, detailed=true)` as `s4`.
      `python3 scripts/tidy_blocks.py --format --input m4 --structure s4 --tab <tab_id>
      --section "<target Thursday>" > fmt.json`
   2. Apply `fmt.json`'s `ops` in **one** `batch_update_doc`, exactly as listed. They already
      carry `tab_id` and run highest block first; per block: un-bullet and zero the indent, a tab
      before each carried item, re-type the summary as `label` + `\t`-item lines, one bullet list
      over all of it (the trap this avoids: `references/doc-write-rules.md`).
   3. Re-read the markdown as `m5` and run
      `python3 scripts/tidy_blocks.py --format-check fmt.json --input m5`. Not `ok` → report
      `partial` with its `problems`; the summary text is still in the previous section.
   4. `skipped[]` is reported, never forced: a line in the block that is not a summary line, a
      comment or link in it (re-typing would drop it), no single place in the Doc that matches it,
      or carried items that do not line up.

   `sections` writes the block as bullets already (the old rollup did since 10-26), so this step
   mostly meets a mixed block, those bullets plus step 5's typed `· 還沒收掉的 —`, and re-types it whole; a block
   from before 10-26 is typed throughout. A block already in bullets is left alone, so a re-run
   writes nothing. Every reader takes both
   shapes: `walk_block` turns a formatted block back into its typed lines, so next Friday archives
   it whole and carries from it, step 7 never takes its sub-bullets for the team's, and
   `carryover.py` skips them. Receipt: add `;<n>-formatted` to `delivered`.
9. **Fill next week's 下一步 and 待討論 from the meeting** (`SKB-091`, AC-15). Take `fill.json` from
   this week's newest `minutes` run folder (`<state>/runs/<ISO week>-minutes-*`). If `minutes` did
   not pass its check this week, skip this step and say so.
   1. Fresh reads: the markdown as `m6` and `inspect_doc_structure(tab_id, detailed=true)` as `s6`.
   2. `python3 scripts/tidy_blocks.py --fill <run>/fill.json --input m6 --structure s6 --tab <tab_id>
      > fill-plan.json`. Per department it writes that heading's people's agreed actions under
      `下一步` and their open topics and blockers under `待討論`. The kept block is usually
      Thursday's `sections` block, which may hold those labels already: the new items then go under
      that label, after its last item, as more of its sub-bullets. A label the block lacks goes right
      under the stamp. Each item cites the meeting (`〔10/22 會議〕`). An `All` action goes to every
      team.
   3. Apply `fill-plan.json`'s `ops` in **one** `batch_update_doc`, exactly as listed.
   4. Re-read the markdown as `m7` and run `python3 scripts/tidy_blocks.py --fill-check
      fill-plan.json --input m7`. Not `ok` → report `partial` with its `problems`.
   5. `skipped[]` and `unplaced[]` are reported, never forced: a heading that still holds two blocks,
      a stamp with no single place in the Doc, a block whose lines read differently in the structure,
      a block with a bold, italic or struck-through line (the fill does not write beside styled text),
      a label typed as a `·` line, held twice, or with no item to follow (or a last item holding a
      link or comment, which the new lines would take on, or a note under it, which they would nest
      under), a block already filled (every item is already there, so a re-run writes nothing), a name
      no heading carries.

   Receipt: add `;<n>-filled` to `delivered`, and `;<m>-not-filled` when `fill-plan.json`'s
   `not_filled` is above 0: the teams the meeting gave items to that this fill passed over (a re-run's
   "already filled" is not counted). Thursday's sections leave 下一步 to Friday once the tidy is done,
   so these items reach no team section unless someone adds them; the report names each with why.

The archive tab is belt-and-braces, not load-bearing — the originals are already in the prior
section. If the copy fails, **stop before deleting** and report; a failed archive is a delayed
tidy, a failed delete after a successful archive is a duplicated section. Steps 7 to 9 run last,
each on its own: if one fails, the block tidy has still landed, so report `partial`, not `failed`.

## Receipt

Every run ends with a compact report (mode, ISO week, target Thursday, what was written where, what was
skipped and why), then a receipt line on its own line, exactly in this shape:

```
ZYNKR-OPS-WEEKLY-RESULT: mode=<mode> week=<ISO week> status=ok|partial|failed delivered=<short>
```

`week=` is the ISO key the runner passed. `status=ok` means every side effect this mode owes landed and
you read it back: the block is in the Doc, the rows read back from the Ledger. Anything short of that is
`partial` (some landed) or `failed` (none did), with the reason in `delivered=`. The runner stamps the
week done **only** on `status=ok` naming the mode and week it passed, and retries anything else; `claude
-p` exits 0 either way, so **never write `status=ok` because the run finished — write it because you
checked.**

```
ZYNKR-OPS-WEEKLY-RESULT: mode=tidy week=2026-W45 status=ok delivered=9-archived;8-kept;38-carried;3-closed
ZYNKR-OPS-WEEKLY-RESULT: mode=tidy week=2026-W45 status=failed delivered=none;scaffold-did-not-fire
```

## Guardrails

- **Never edit a human's line.** Auto-content lives only inside `〔自動彙整 …〕` blocks. Promotion or
  deletion of that content is a human act, at the meeting. **One exception, `tidy` step 7 only:** a
  bullet whose status chip reads `Done`/`Drop` is removed from the newest section, and only a range
  `tidy_blocks.py --closed` returned, re-confirmed with `--expect` on fresh reads and verified with
  `--postcheck` after. A heading is never in such a range.
- **Never rebuild the Doc's skeleton.** Person chips cannot be created by Apps Script or the Docs REST
  API — only copied. Rebuilding loses the routing table. Copy, or do nothing.
- **Never write to a past section.** If the target Thursday is behind the one this mode owns, stop and
  report.
- **Never write the Main Tracker, never mail, never post to Chat.** The runner denies those tools; a
  hook refuses any tracker write.
- **Fail loud on config.** A placeholder id stops the run; a wrong id writes into someone else's file.
- **Write like a colleague, not a report generator.** Every line the team reads is zh-TW: no 官腔, no
  half-translated lines, no internal mode names. `<core>/references/wording.md` carries the rules.

## Limitations

- The Apps Script half must be installed once by hand, and `installTriggers()` must actually be *run*
  — pasting the file does not schedule anything. See `references/scaffold.md`.
- **`tidy` bounds the newest section, not the whole Doc.** Older sections keep whatever they
  accumulated before 2026-09-15; trimming that backlog is a human cut-and-paste (`SKB-029`).
- **`tidy`'s carried list is only as good as the status words people write.** It reads `完成`/`Done` as
  closed and everything else as open; an item finished but never marked stays on the list.
- **Closed-bullet removal needs the status chip.** A human bullet leaves the new week only when its
  chip (or a trailing typed word) reads `Done`/`Drop`/`完成`/`放棄`/`取消`.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file. `snapshot` writes no prose, so
it skips both reads.
