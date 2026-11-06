---
name: ops-weekly-tracker
sheetId: "3.26"
description: >-
  The only writer of a small team's Main Tracker in the weekly loop. After the meeting it proposes the
  week's tracker changes from the meeting's decisions, records them in the
  machine-owned Weekly Ledger and mails them as one 【週結】 for the owner to answer (propose); it
  then writes exactly what the owner's reply approves, cell by cell (apply), and copies the tracker
  into the Ledger once per ISO week (snapshot). A script refuses any change without evidence or a
  reply, and a hook refuses every tracker write but apply's. Trigger on "/ops-weekly-tracker",
  "週結", "待核准", "核准 tracker 變更", "更新 Main Tracker", "tracker snapshot", "propose tracker
  changes", "apply the approved changes". BOUNDARY — do NOT hijack: /zynkr-ops-weekly (the Monday
  recap and Wednesday collect), /ops-weekly-doc (the weekly Doc: sections, minutes, tidy),
  /project-manager (the schedule and missed-beat notices), /planning-tracker-sync (the H2 tracker
  block; never writes the Main Tracker).
category: operations
project: ops-weekly-tracker
platform: claude
status: WIP
visibility: public
author: Peter Tu
input: "A mode (propose, apply or snapshot) and the ISO week the runner passes as week=; all identifiers come from the private config at ~/.config/zynkr/ops-weekly.json."
process: "Read the tracker and this week's Ledger blocks → propose changes that cite their evidence → record them before mailing the 【週結】 once → read the owner's reply → write only approved cells, re-reading each first → copy the tracker into the Ledger → receipt."
output: "A Proposals and an Updates block in the Weekly Ledger, one 【週結】 mail and its confirmation, the approved Main Tracker cells, and the week's Snapshot block."
synergy: [zynkr-ops-weekly, ops-weekly-doc, project-manager, planning-tracker-sync, zynkr-gm]
executed_by: internal-user
house-style: bound

---

# ops-weekly-tracker

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill ops-weekly-tracker
```

The tracker's part of the weekly loop (`SKB-091`). The loop is split by the store each part writes:

| Skill | Writes | Beats |
|---|---|---|
| `zynkr-ops-weekly` | mail, Chat, the Weekly Ledger | `recap` (Mon), `collect` (Wed) |
| `ops-weekly-doc` | the weekly operations Doc | `sections` (Wed), `minutes` · `tidy` (after the meeting) |
| **`ops-weekly-tracker`** (this skill) | **the Main Tracker**, and its own Ledger blocks | `propose` (after the meeting) · `apply` · `snapshot` (Fri → Sun) |
| `project-manager` | nothing but its notice mail | runs the beats on time, mails the owner when one did not run |

`project-manager`'s runner starts each beat with `/ops-weekly-tracker <mode> week=<ISO week>`, and in a
rehearsal `config=<path>`. Use the week as given; never work it out again mid-run.

**`<core>`** below is the `zynkr-ops-weekly` folder next to this skill's base directory
(`<base>/../zynkr-ops-weekly`). The Ledger code lives there and only there: this skill calls
`<core>/scripts/ledger.py` and reads `<core>/references/`, never a copy. `scripts/proposals.py` finds
it the same way (`ZYNKR_OPS_WEEKLY_SCRIPTS` overrides) and refuses a core of another version.

| When | Mode | What happens |
|---|---|---|
| Thu 20:00 → 23:00, Fri 08:00 → 11:00, after `tidy` | `propose` | Suggest this week's tracker changes from the Ledger's evidence; record them; mail the 【週結】 |
| until Sun 22:00 Taipei | — | The owner replies: 「全部核准」 · 「核准 1 3」 · 「退回 2」 |
| Fri 11:00 → Sun 17:00 | `apply` | Read the owner's reply, record each decision, confirm in the thread, then write the approved cells (live) |
| Fri 11:00 → Sun 22:00, after `apply` (or from Sun 22:30 Taipei without it) | `snapshot` | Copy every Main Tracker item into the Ledger, once per ISO week |

The 【週結】 deadline is on the team's clock, Sunday 22:00 Taipei. The modes' windows are on the
runner's clock (`SKB-114`), which need not be Taipei's; on it `apply` looks on every tick from an
hour before the deadline until half an hour after it.

## Configuration

The same private file as the rest of the loop, `~/.config/zynkr/ops-weekly.json` (override with
`ZYNKR_OPS_WEEKLY_CONFIG`); its schema and notes are `<core>/references/config.example.json` and
`<core>/references/config.README.md`. This skill reads `google_account`, `sources.main_tracker`
(`id`, `tab`, `cycle`), `sources.ledger` (`id`, `epoch_week`), `routine.weekly_to` (the team address the
【週結】 goes to; `propose` refuses without it), `routine.apply_mode` and, for the live write,
`routine.sheets_credentials` (the Google OAuth file `scripts/notes_append.py` refreshes its token
from; by default `~/.google_workspace_mcp/credentials/<google_account>.json`). If a value is missing
or still a placeholder, **fail loud**; never guess an id.

## Required reading (before acting)

| File | Read when |
|---|---|
| `<core>/references/ledger.md` | Every mode: the Ledger's layout, the commit order, how a block is written |
| `references/proposal-rules.md` | `propose`: what may be suggested, on what evidence, and what `check` refuses |
| `<core>/references/wording.md` and the approval section of `<core>/references/message-templates.md` | `propose`, before writing a word the owner will read |

None of the modes opens the Doc or posts to Chat.

## Workflow — the modes

Every printed call is `{"tool", "args", "save"}`: call `tool` with `args` copied exactly, then save the
tool's whole result, unchanged, to the `save` path with the Write tool. Never retype, trim, reformat or
summarise a result. The next step parses it and refuses anything that does not match, and that
refusal is the point: a copied cell that drifted is how `1.10` becomes `1.1`.

A **block write** below is always the same four steps: `python3 <core>/scripts/ledger.py block start
--tab <tab> --week <W> --rows <rows_path>`, then `block plan`, `block check` and `block confirm`,
making every printed call exactly. Pass the file the script wrote; never retype rows.

### `propose` (Thu 20:00 → 23:00, Fri 08:00 → 11:00, after `tidy`)

Suggests this week's changes to the Main Tracker and mails the week's **【週結】** to the team
(`routine.weekly_to`; `SKB-091`). The mail opens with the week itself, from the meeting's rows in the
`Decisions` block: what was decided and dropped, progress, and each person's blockers and next
steps. Then come the proposed changes, which only the owner's reply approves. A change sets 結束,
狀態 or 備註 on an item, drops one (放棄) or adds one (新增). It reads the tracker and this week's
`Decisions` and `Reports` blocks in the Ledger — never the Doc — and writes **only the Ledger** and
**that one mail**. It never writes the tracker: that is `apply`'s job, after the owner has said
yes. A week with nothing to propose still mails its summary. Read `references/proposal-rules.md`
before writing a single proposal.

`scripts/proposals.py` works out every range and checks every proposal; make its printed calls
exactly and save each result unchanged, as in `snapshot`.

1. **The week.** Use the `week=` argument the runner passes. If a `config=<path>` argument is
   present, add `--config <path>` to `start`.
2. `python3 scripts/proposals.py start --week <W>` → make the six printed calls, save each result,
   keep the `dir`.
3. `python3 scripts/proposals.py pages --dir <dir>`.
   - `"already": true` → this week's proposals are recorded and mailed. Receipt `status=ok` with the
     `delivered` it prints.
   - `"resume": true` → the proposals are recorded but the mail never went out. Skip to step 7
     with the `mail` and `sent_search` it printed: never propose a second time.
   - Otherwise make the printed tracker reads and save each one.
4. `python3 scripts/proposals.py context --dir <dir>` → the items and this week's evidence rows,
   each with its Ledger cell (`Decisions!A42`), also saved as `context.json`.
5. **Propose.** Following `references/proposal-rules.md`, write a JSON list to `proposals.json` in
   the run folder, one object per suggested change: `{"#", "欄位", "建議值", "原因", "證據", "信心"}`,
   or for a new item `{"欄位": "新增", "項目", "子類別", "負責人", "原因", "證據", "信心"}`.
   `證據` lists the `ref`s the change rests on. Nothing to suggest is a fine answer: save `[]`.
6. `python3 scripts/proposals.py check --dir <dir> --input <dir>/proposals.json`. A refusal names
   the proposal and the rule: fix that proposal or drop it, and run `check` again. Exit 5 means
   the mail would be too long to read back (the thread `apply` reads quotes it whole): drop the
   weakest proposals. It writes `rows.json` (`rows_path`) and the mail, always.
   Then record the rows: `python3 <core>/scripts/ledger.py block start --tab Proposals --week <W> --rows
   <rows_path>`, `block plan`, `block check`, `block confirm`, making every printed call exactly,
   as in the block write above. Pass the file `check` wrote; never retype rows. **The Ledger record
   comes before the mail, always.** No rows still records the week (an empty block) and still mails
   the summary: go on to step 7.
7. **Mail it, once.** Make the `sent_search` call and save the result, then run
   `python3 scripts/proposals.py sent --dir <dir>`:
   - `{"found": false}` → `send_gmail_message` to exactly `mail.to`, with exactly `mail.subject`, the
     contents of `mail.body_path` as the body, `body_format="html"` and `include_signature=false`.
     Then make the same `sent_search` call again (same save path) and run `sent` again. If the send
     call itself returned an error, run `python3 scripts/proposals.py sent --dir <dir>
     --send-failed` instead (nothing went out, so the next attempt may send) and receipt
     `status=failed`, `delivered=send-failed` with the error.
   - `{"calls": [...]}` → make the call (it fetches the thread), save it, run `sent` again. It
     checks the subject and that the mail in Sent is, word for word, the mail `check` wrote.
   - `{"found": true}` → receipt `status=ok` with its `delivered`.
   - Exit 6 → the mail is not in Sent yet, an earlier attempt sent it within the hour, or it went
     out different from the mail `check` wrote. Never send again in this run: receipt
     `status=failed`, `delivered=send-not-verified` with the reason. A later attempt resumes at
     step 3 and finds it.
   - Exit 3 → the search or thread result is not what `sent` expects, or two approval mails are in
     Sent; receipt `status=failed` with the reason.

**Rules for this mode.** Every change goes through `check`. Never write the Main Tracker, never
send the mail to anyone but `mail.to` (the team address), never send it before `block confirm` has passed, and never
send it twice: only `sent` says when to send. **Any refusal from `proposals.py` is a
`status=failed` receipt with its reason**, and you write nothing to fix it: never a Ledger block of
your own, never a file in the state folder (`approval.json` and its neighbours are the script's,
and a refusal that names one is addressed to the owner).

### `apply` (Fri 11:00 → Sun 17:00)

Reads the owner's reply to this week's 【週結】 mail, records each decision and confirms it in the
thread. **In live mode it then writes the approved changes into the Main Tracker, cell by cell**
(`SKB-091`). `routine.apply_mode` is `shadow` unless it says exactly `live`; in shadow it records the
decisions in the Ledger and writes nothing to the tracker. A week keeps the mode its 【週結】 was
proposed in (`propose` records it with the thread): turning `live` on mid-week changes the weeks
proposed after it, never a mail that told the team nothing would be written. Only the owner's reply counts, whoever
else is on the thread. It needs no stamp from `propose`: it reads this week's `Weeks` row itself.

1. **The week**, as in `propose`.
2. `python3 scripts/proposals.py apply-start --week <W>` → make the printed calls exactly (the
   thread fetch carries `include_analysis`, which is how drafts are seen), save each result with
   the Write tool as in `snapshot`, and keep the `dir`. Never save a result through Bash: the `Weeks` row
   holds the Main Tracker's id, so the guard refuses any Bash command that carries it. Run each
   script command on its own. When it printed a Gmail search instead of a thread fetch (no thread was recorded),
   run `python3 scripts/proposals.py apply-thread --dir <dir>` and make the fetch it prints;
   `"found": false` → go on to step 3, which reports the missing mail.
3. `python3 scripts/proposals.py apply-decide --dir <dir>`, then by its `status`:
   Every `write` below is the same block write: `python3 <core>/scripts/ledger.py block start --tab <tab>
   --week <W> --rows <rows_path>`, then `block plan`, `block check` and `block confirm`, making
   every printed call exactly. Pass the file `apply-decide` wrote; never retype rows.
   - `waiting` → no decision yet: `nothing-proposed-yet` (this week's `propose` has not recorded:
     it failed or has yet to be caught up), `approval-mail-not-sent-yet` (it recorded its rows but the
     【週結】 is not in Sent: the send failed, and a catch-up sends it), `no-reply-yet`, `draft-open` (a reply draft is open in the
     thread), `asked-to-restate`, or `reply-unreadable`. A `send` call comes with
     `reply-unreadable` (asking the owner to restate) and with `draft-open;noted` (telling the owner
     a draft is holding things up): make it exactly once, and when it went through, run
     `python3 scripts/proposals.py apply-sent --dir <dir>` so the next look does not send it again.
     Receipt `status=waiting` with its `delivered`, adding `;sent` when the send went through. The
     runner looks again in two hours, and on every tick from Sunday 21:00 to 22:30 Taipei, around
     the deadline.
   - `failed` → `approval-mail-differs;…` (the mail in the thread is not the mail that was sent), `proposals-changed;…` (the Proposals block was edited after the
     mail) or `confirmation-disagrees-with-the-Proposals-block`: receipt `status=failed` with its
     `delivered`. Send nothing, write nothing.
   - `ok` → nothing left to decide. With a `write` (the empty `Updates` block of a week with no
     proposals, or of a week whose confirmation went out before its `Updates` write landed), write
     it first. Receipt `status=ok` with its `delivered`.
   - `recheck` → a decision to record: write its one `write` (the `Proposals` block), then make the
     `then` calls (that block and the thread, read again), save each result, and run
     `apply-decide` again. It answers `confirm`, or `recheck` once more when the owner replied
     while you were writing.
   - `confirm` → make its `send` call exactly once: the confirmation, in the thread, listing what
     was recorded. That message is what makes the week's decision final. If the send fails, write
     nothing more and receipt `status=partial` with the reason: the week stays unapplied and the
     next look decides and confirms again. When it went through:
     - **shadow** (it has a `write`): write it (the `Updates` block, which marks the week applied in
       `Weeks`), then receipt `status=ok`, its `delivered` plus `;confirmed`.
     - **live** (it has `then`, the tracker's size): make that call, save it, and go on to step 4.
   - `live` → the confirmation went out in an earlier look, but the write did not finish. Make its
     `then` call, save it, and go on to step 4.
   - Any refusal (a non-zero exit) → receipt `status=failed` with its reason. Write nothing to fix
     it: never a Ledger block of your own, never a file in the state folder.
4. **The live write** (only after `confirm` or `live` in live mode).
   1. `python3 scripts/proposals.py live-pages --dir <dir>` → make the printed tracker reads and
      save each one.
   2. `python3 scripts/proposals.py live-plan --dir <dir>` compares every approved row with the
      tracker as it is now. Then, in this order:
      - its `resize` call, when it is not `null` (a 新增 past the last row grows the grid);
      - every `writes` call, exactly as printed;
      - every `notes` command, each through Bash on its own, exactly as printed. Each appends one
        line to one 備註 cell through the Sheets API and keeps the cell's links. Exit 3 means the
        cell is not what the plan saw: edited since, or a formula, a number or an emoji, which
        cannot take a line. Carry on: this look's read-back then differs, and the next look skips
        that cell and names why. Any other non-zero exit: stop and receipt `status=partial` with
        its message;
      - every `then` read, saved.

      `skipped` lists the cells someone edited by hand since the proposal, items closed or
      renumbered since, and 備註 lines `notes_append.py` could not add (the owner adds those by
      hand; a 放棄 there still gets its 狀態): they are not written, and the receipt counts them.
   3. `python3 scripts/proposals.py live-check --dir <dir>` reads every planned cell back.
      - `ok` → write its `write` (the `Updates` block, which marks the week applied in `Weeks`),
        then receipt `status=ok`, its `delivered` plus `;confirmed`.
      - `failed` → a cell reads back differently. Nothing is recorded as applied: receipt
        `status=partial` with its `delivered` and the cells it names. The next look plans again
        from what the tracker holds then, and only reads back what already landed.

**Rules for this mode.** The owner's newest reply that says anything beyond thanks decides, until
the confirmation is in the thread; after it, replies change nothing. `Weeks` Q (applied) is written
only after the confirmation, so a decision in the `Proposals` block without it is provisional and
nothing reads it as applied. A row the reply does not name stays 未回覆 and is not applied. A reply
that is unreadable, asks a question, or approves anything while saying more than thanks decides
nothing and gets one restate request. Never write the Main Tracker in shadow mode. In live mode,
write only what `live-plan` printed, in its order: never a cell of your own, never a refused write
again in another shape. Never send anything except the `send` call `apply-decide` printed.

### `snapshot` (Fri 11:00 → Sun 22:00, after `apply`, or from Sun 22:30 Taipei without it)

Copies every item of the Main Tracker's `H2 專案項目` tab into the machine-owned Weekly Ledger,
once per ISO week (`SKB-044`). It reads the tracker and writes **only the Ledger**: it posts
nothing, mails nothing and never opens the Doc. Monday's recap compares
two of these snapshots to say what changed. Read `<core>/references/ledger.md` first.

**`<core>/scripts/ledger.py` works out every range, row and value; you only make the calls it prints.**
Each printed call is `{"tool", "args", "save"}`: call `tool` with `args` copied exactly, then save
the tool's whole result, unchanged, to the `save` path with the Write tool. Never retype, trim,
reformat or summarise a result. The next step parses it and refuses anything that does not
match, and that refusal is the point: a copied cell that drifted is how `1.10` becomes `1.1`.

1. **The week.** Use the `week=` argument the runner passes (`week=2026-W40`). Without one (an
   interactive backfill), run `python3 <core>/scripts/ledger.py week` and ask the person which week to
   snapshot: that `week` or the one before, each named by its Monday's date. Go on only with their
   answer. The script answers on Taipei's clock, where late on Sunday the week has already turned while
   the runner's may not have, so the weekend just ending is then the earlier one. Never work it out
   again later in the run. If a `config=<path>` argument is present, add `--config <path>` to the
   `start` command below.
2. `python3 <core>/scripts/ledger.py snapshot start --week <W>` → make the five printed calls, save each
   result, and keep the printed `dir`.
3. `python3 <core>/scripts/ledger.py snapshot pages --dir <dir>`.
   - `"already": true` → the week is done. Receipt `status=ok` with the `delivered` it prints, and
     write nothing.
   - Otherwise make the printed tracker reads and save each one.
4. `python3 <core>/scripts/ledger.py snapshot plan --dir <dir>`. A non-zero exit means stop: nothing has
   been written, so the receipt is `status=failed` with the reason it printed. Otherwise make the
   `ops` calls in order, exactly as printed (RAW writes into the Ledger), then make every
   `readback` and `recheck` call and save each result.
5. `python3 <core>/scripts/ledger.py snapshot check --dir <dir>`.
   - Exit 0 → make the printed `commit` call, then its `readback` call, and save that result.
   - Exit 6 saying the tracker changed during the run → start again from step 2, **once**. A
     second exit 6 is `status=failed`.
   - Any other non-zero exit → `status=failed`. Do not make the commit call.
6. `python3 <core>/scripts/ledger.py snapshot confirm --dir <dir>` → receipt `status=ok` with the
   `delivered` it prints. A non-zero exit here is `status=partial`,
   `delivered=block-written;weeks-row-not-confirmed`.

**Rules for this mode.** Never compute a range, row number or value yourself. Never use
`USER_ENTERED`. Never write to the Main Tracker: no printed call does. Write the `Weeks` row only
through the call `check` printed. It is what marks the week done, so it is always the last write.

## Receipt

Every run ends with a compact report (mode, ISO week, what was written where, what was mailed), then a
receipt line on its own line, exactly in this shape:

```
ZYNKR-OPS-WEEKLY-RESULT: mode=<mode> week=<ISO week> status=ok|partial|failed|waiting delivered=<short>
```

`week=` is the ISO key the runner passed. `status=ok` means every side effect this mode owes landed
and you checked it: the block reads back, the `Weeks` cell reads `ok`, the mail is in Sent. Anything
short of that is `partial` (some landed) or `failed` (none did), with the reason in `delivered=`. Only
`apply` may say `waiting` (no decision yet). The runner stamps the week done **only** on `status=ok`
naming the mode and week it passed, and retries anything else; `claude -p` exits 0 either way, so
**never write `status=ok` because the run finished — write it because you checked.**

```
ZYNKR-OPS-WEEKLY-RESULT: mode=propose week=2026-W45 status=ok delivered=approval-mail;5-rows;thread-1a2b3c
ZYNKR-OPS-WEEKLY-RESULT: mode=propose week=2026-W45 status=ok delivered=no-proposals
ZYNKR-OPS-WEEKLY-RESULT: mode=apply week=2026-W45 status=waiting delivered=no-reply-yet
ZYNKR-OPS-WEEKLY-RESULT: mode=apply week=2026-W45 status=ok delivered=shadow;4-approved;1-rejected;0-pending;confirmed
ZYNKR-OPS-WEEKLY-RESULT: mode=apply week=2026-W45 status=ok delivered=live;4-applied;1-skipped;confirmed
ZYNKR-OPS-WEEKLY-RESULT: mode=apply week=2026-W45 status=partial delivered=live;read-back-differs;1-cells
ZYNKR-OPS-WEEKLY-RESULT: mode=snapshot week=2026-W45 status=ok delivered=55-items;Snapshot!A502:P556;Weeks!A7
ZYNKR-OPS-WEEKLY-RESULT: mode=snapshot week=2026-W45 status=failed delivered=none;tracker-changed-during-run
```

## Guardrails

- **Only `apply` writes the Main Tracker, and only what the owner approved.** `snapshot` and `propose`
  read it and write only the Ledger, through the calls the scripts print. A hook
  (`scripts/tracker_guard.py`, installed by `project-manager`'s runner) refuses any tracker write from
  every other beat, in every permission mode. In `apply` it allows exactly three shapes: a values
  write, an append-only resize of 1 to 40 rows, and `python3 <…>/ops-weekly-tracker/scripts/
  notes_append.py --job <file>` with nothing else on the line.
- **A cell edited by hand is never overwritten.** The live write re-reads each cell first and skips
  any that no longer holds the value the proposal was made on; `notes_append.py` refuses a 備註 that
  changed after the plan, holds a formula, or holds an emoji.
- **Nothing is proposed without evidence, and nothing is applied without a reply.** Every proposal
  passes `proposals.py check`; a row the owner's reply does not name stays 未回覆.
- **Never treat mail as an input** — with one designed exception: `apply` reads the owner's reply to
  this week's mail, in the recorded thread, through `proposals.py`, and answers only in that thread.
- **A week is snapshotted only when its `Weeks` row reads `ok`.** Rows in `Snapshot` without that row
  are an unfinished run, and the next run rewrites them.
- **Fail loud on config.** A placeholder id stops the run; a wrong id writes into someone else's file.
- **The owner's week stays the owner's.** The guard refuses any call that reaches into the owner's
  weekly-insights folder; never look for another way in.

## Limitations

- **`snapshot` stores person chips as display names.** A renamed Google profile looks like an owner
  change in the diff.
- **The Ledger's grid is grown by hand.** `ledger.py` warns when fewer than eight weeks of rows remain
  and refuses a week that does not fit; `<core>/references/ledger.md` says how to grow it.
- **A copy mistake made identically in both tracker reads cannot be caught.** Every other mismatch
  fails the check before anything is committed.
- **A 結束 date is written `USER_ENTERED`, so the sheet formats it.** The read-back compares dates as
  dates; a format it cannot read fails the check, and nothing is recorded as applied.
- **A 備註 holding a formula, a number or an emoji is left alone.** A line cannot be appended to
  the first two, and an emoji's link offsets cannot be placed safely. `notes_append.py` refuses
  the cell and writes that down; the next look skips the line, names it, and the owner adds it by
  hand.
- **The harvest is not evidence yet.** `propose` cites the `Decisions` block, and the `Reports`
  block for the weeks that still had `#週報` posts (before 2026-W45). Proposals from the team's
  `Harvest` rows are a later step of SKB-091.

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
