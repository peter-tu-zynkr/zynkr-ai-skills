# The Apps Script half

`scripts/scaffold.gs` duplicates the newest week section and re-stamps it with the next
Thursday. It runs on **Thursday at 23:00 Taipei**, anywhere in that hour (`TRIGGER_HOUR`), after the
meeting. It reads only the top of the tab: the scan stops at the second dated heading, and the check
after the insert reads only down to where that heading moved (`SKB-143`).

## Why this is not the skill's job

The split is by **whether judgement is needed**, not by preference.

- Duplicating a section is purely mechanical and must never fail. Apps Script authorisation does
  not expire, so in the week the skill breaks entirely, the skeleton still opens and Thursday
  still has a page to meet from.
- Deciding which department a chat message belongs under **is** judgement. Doing it in Apps
  Script would mean calling an LLM from `UrlFetchApp` and maintaining prompt logic in two places,
  plus wiring the Chat advanced service. The skill already reads Chat and already writes the
  Doc — that step stays in the skill.

## Why it must copy, not rebuild

Each department heading carries its owner's **person chip**, and that chip is the routing table.

> **Neither Apps Script nor the Docs REST API can create a person chip.** They can only copy an
> existing one.

So "generate a clean skeleton from a template" is not an available option — it silently
downgrades every chip to plain text and destroys routing. Copying the previous section is the
only method that preserves them, and copying happens to be the thing Apps Script does most
reliably.

## Why Thursday, not Wednesday

Tuesday's roll-up needs a section to write into. If the skeleton is created on Wednesday,
Tuesday has nowhere to go. Creating it Thursday evening closes this week and opens next week in
one move, so **exactly one future section is ever open**, and nobody has to remember to copy
anything.

## Install

1. Open the Doc → Extensions → Apps Script. Paste `scripts/scaffold.gs`.
2. **Point `DOC_ID` at a duplicate of the Doc first.** Leave `DRY_RUN = true`.
3. Run `checkScaffold()` and read the log. It never writes.
4. In the duplicate, delete the newest week section, from its dated heading down to the next one: a
   run opens a week only once the newest one's meeting has passed, so without this it would write
   nothing on any day but the meeting's Thursday evening. Set `DRY_RUN = false`, run
   `scaffoldNextWeek()`, then **open the duplicate and check the person chips survived**. If they
   came through as plain text, use the `mailto` fallback documented at the bottom of the script —
   visually plainer, still machine-readable.
5. Only then change `DOC_ID` to the real Doc.
6. **Run `installTriggers()` by hand, once.**

> Pasting the file schedules nothing. The trigger exists only after `installTriggers()` has
> actually executed. This is the step most likely to be skipped, and skipping it looks exactly
> like success until the following Tuesday.

## Update the live copy

A change to `scripts/scaffold.gs` reaches the Doc only when someone pastes it. Nothing deploys it.

1. Open the Doc → Extensions → Apps Script, and note the live values of the constants at the top:
   `DOC_ID`, `TAB_ID`, `TRIGGER_DAY`, `TRIGGER_HOUR` and `TZ`. The file in the repo carries defaults,
   and `TAB_ID` changes when the year's tab does.
2. Replace the whole file with the new `scripts/scaffold.gs`, put those values back, set
   `DRY_RUN = false`, and save.
3. Run `checkScaffold()` straight away. It never writes, whatever `DRY_RUN` says. Its log says how long
   the tab took to open and how many of its elements the scan read, in how long, then what a run would
   do now: open next week, or nothing, and why. If it throws, or names a week you did not expect, set
   `DRY_RUN = true` and save before the next trigger, then find out why.
4. Leave the trigger as it is. It calls `scaffoldNextWeek` by name, and a paste keeps that name. Run
   `installTriggers()` again only when `TRIGGER_DAY`, `TRIGGER_HOUR` or `TZ` change.
5. If the team keeps a copy of the live file outside Apps Script, replace that too, so the next person
   starts from what runs.

## Verify it fired

`tidy` checks that a section for the coming Thursday exists before it touches anything
(its step 1), and fails with a `status=failed` receipt if not; `project-manager` then mails the owner
that the 會後整理 did not run. That is the "prove it fired" check for this half — the script's own
success is otherwise invisible until someone opens the Doc and finds nowhere to write. (Until v4,
Monday's `nudge` made this check.)

The check deliberately runs only after the scaffold's hour: Apps Script fires anywhere in a one-hour
*window* after the meeting, so a check inside it would fail for the wrong reason. `tidy` opens after
midnight Taipei, once the window has closed (`project-manager`'s `beats.py --selftest` holds it there
in summer and in winter), and almost six days before `sections`, the next mode that needs the section.

Schedule lives in three constants at the top of the script — `TRIGGER_DAY`, `TRIGGER_HOUR`,
`TZ`. Change one and re-run `installTriggers()`; it deletes its own prior trigger first, so that
is idempotent. **If you ever move the scaffold off Thursday night, move the check with it**, and keep `tidy`'s
first window after the scaffold's hour.

## Known traps

| Trap | What happens | Handled by |
|---|---|---|
| Tabbed document | `doc.getBody()` returns the main body, not the tab — edits go nowhere visible | `getTabBody_()` walks `getTabs()` for `t.0`, then `asDocumentTab().getBody()` |
| Date parsing | Section headings are `Aug 27, 2026`; a locale-dependent parse silently misreads them | Explicit `DATE_RE` + month table, no `new Date(string)` |
| A long tab | The tab gains a section every week, and until `SKB-143` the script read every element of it twice: once to find the sections, once to count them after the insert. On 12 Nov 2026 a run hit Apps Script's 30-minute limit and wrote nothing | The scan stops at the second dated heading, and the check reads only down to where that heading moved. `test_scaffold.mjs` proves the reads are the same at 50 sections and at 2,000 |
| Double-run | A second run opens a second future week | A run stops when the newest section is dated after today in `TZ`: next week is already open. After missed weeks each run opens the next missing week, so a catch-up takes one run per missing week and then stops. Until `SKB-143` the guard looked for next Thursday's heading among the headings already there, where it never is, so it never stopped a run |
| A run before the meeting | It would copy the week before the meeting has edited it, and the trigger would then find next week open | On a day before the newest section's, the run says next week is already open; on that day itself it opens next week only from `OPENS_FROM_HOUR`, an hour before the trigger's |
| A mistyped date | A heading such as `Nov 26, 2027` would hold the scaffold for a year; `Nov 31, 2026` would open a misdated week | A newest section more than a week ahead, or a dated heading that is not a real date, stops the run with an error before it writes. A section opened by hand two weeks ahead, to skip a week, trips the same error until it is at most a week ahead: let the scaffold open the skipped week and leave it empty |
| A section dated off the trigger's day | Each new section is the newest plus seven days, so the off day carries into every section after it. `tidy` looks for the Thursday and reports `scaffold-did-not-fire` every week until someone re-dates the heading | Date a moved meeting's section by its Thursday anyway |
| Element types | A blind `copy()` loses list bullets and tables | Explicit branch on `PARAGRAPH` / `LIST_ITEM` / `TABLE` |
| macOS TCC | Scripts under `~/Desktop` can trip permission prompts | Keep the canonical copy in the repo, paste into the Apps Script editor |
| Panel shows the wrong time | The Triggers panel renders times in the **project** timezone, not the trigger's — a project set to another zone displays a different clock than `TZ` actually uses | Set the project timezone to `TZ` in Project Settings; the trigger itself is already correct |
| Hour window, not a minute | `atHour(23)` fires anywhere in 23:00–24:00 | Anything that must run after the scaffold must clear the whole window |
| Index shift on copy | Reading and writing in one loop re-reads the same element and duplicates it — seen live as ~100 copies of the date heading | Snapshot all source elements first. The post-condition then reads the top of the tab and expects the new heading, the old newest right after the copies and the second-newest where it moved, with no other dated heading among them |
