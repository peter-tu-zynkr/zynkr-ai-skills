---
name: zynkr-ops-weekly
sheetId: "3.19"
description: >-
  The core of a small team's weekly operations loop: the machine-owned Weekly Ledger every part of
  the loop records into, the Monday recap and plan mailed to the team (recap), and the Wednesday
  collect that reads each person's weekly harvest into the Ledger and chases whoever has none in
  the team's Google Chat space (collect). The weekly Doc belongs to /ops-weekly-doc, the Main Tracker
  to /ops-weekly-tracker and the schedule to /project-manager. Routing is read at run time from the
  Doc's own owner person chips, never hardcoded. Trigger EAGERLY on "/zynkr-ops-weekly", "營運週報",
  "週報彙整", "誰還沒回報", "補件提醒", "recap 信", "週一回顧", "這週計畫", "weekly ops loop", "weekly
  ledger", or any ask to recap the team's week, plan the week ahead, or collect and chase the weekly
  updates. BOUNDARY — do NOT hijack: /zynkr-gm (the founder's own company-level Monday brief),
  /ops-weekly-doc (the weekly Doc), /ops-weekly-tracker (the Main Tracker), /project-manager (the
  schedule and missed-beat notices), /project-status-update (one project's status email),
  /planning-tracker-sync (the H2 tracker block and its own nudges), /weekly-insights (one
  person's own week).
category: operations
project: zynkr-ops-weekly
platform: claude
status: WIP
visibility: public
author: Peter Tu
input: "A mode (recap, collect or status) and the ISO week the runner passes as week=; all identifiers come from the private config at ~/.config/zynkr/ops-weekly.json."
process: "Load config → read the Weekly Ledger (and for collect, the week's harvest files) through scripts that plan every range → write only Ledger blocks → mail or post once, asserting it landed → receipt."
output: "Per mode: the Monday recap-and-plan mail, the week's Harvest block in the Ledger and one Chat line naming who has no harvest yet, or a read-only status."
synergy: [ops-weekly-doc, ops-weekly-tracker, project-manager, weekly-insights, zynkr-gm, planning-tracker-sync]
executed_by: internal-user
house-style: bound

---

# zynkr-ops-weekly

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill zynkr-ops-weekly
```

A small team works a weekly rhythm: each person's week closes on Wednesday, the team meets on
Thursday, the meeting's outcomes land in the Main Tracker on Friday, and Monday opens the next week
with what changed. This skill is the core of the loop that runs that rhythm: it owns the **Weekly
Ledger**, the machine-owned sheet every part of the loop records into, and the two beats that write
mail, Chat and the Ledger alone.

The loop is split by the store each part writes (`SKB-091`, v4):

| Skill | Writes | Beats |
|---|---|---|
| **`zynkr-ops-weekly`** (this skill) | **mail, Chat, the Weekly Ledger** | `recap` (Mon), `collect` (Wed) |
| `ops-weekly-doc` | the weekly operations Doc | `sections` (Wed), `minutes` · `tidy` (after the meeting) |
| `ops-weekly-tracker` | the Main Tracker, and its own Ledger blocks | `propose` (after the meeting) · `apply` · `snapshot` (Fri → Sun) |
| `project-manager` | nothing but its notice mail | runs the beats on time, mails the owner when one did not run |

The other two writers call this skill's `scripts/ledger.py` and `scripts/parse_routing.py` and read its
`references/`; they never keep a copy. Every department heading in the Doc carries its owner's Google
Docs person chip, keyed by email: that is the routing table, read at run time, so the loop keeps **no
department map of its own**.

---

## The week

| When | Beat | Skill | What happens |
|---|---|---|---|
| Mon 08:00 → 20:00 | `recap` | this one | Mail the team last week's recap and this week's plan, read from the Ledger |
| Wed 20:00 Taipei | — | `weekly-insights` | Each person's week closes; the harvest routine writes `harvest-<person>.md` (`SKB-094`) |
| Wed 14:30 → 21:00 | `collect` | this one | Read the harvest into the Ledger's Harvest block; one Chat line names whoever has none |
| Wed 14:30 → 23:00 | `sections` | `ops-weekly-doc` | Each team's 進度 · 卡關 · 下一步 · 待討論 in this week's Doc section |
| Thu 21:00 Taipei | — | team | The weekly meeting |
| Thu 23:00 Taipei | `scaffoldNextWeek` | Apps Script | Copy the newest week section forward |
| Thu 18:30 → 23:00, Fri 08:00 → 11:00 | `minutes` | `ops-weekly-doc` | The meeting's minutes from its transcript, into the Doc and the Ledger |
| Thu 19:00 → 23:00, Fri 08:00 → 11:00 | `tidy` | `ops-weekly-doc` | Trim the copied section; fill next week's actions |
| Thu 20:00 → 23:00, Fri 08:00 → 11:00 | `propose` | `ops-weekly-tracker` | The 【週結】: this week's tracker changes, for the owner's reply |
| Fri 11:00 → Sun 17:00 | `apply` | `ops-weekly-tracker` | Write what the owner approved |
| Fri 11:00 → Sun 22:00 | `snapshot` | `ops-weekly-tracker` | Copy the tracker into the Ledger |

Times marked Taipei are the team's clock. The beats' windows are on the runner's clock (`SKB-114`),
which need not be Taipei's: on it every window lies between 08:00 and 23:00, and the harvest, the
meeting and the scaffold each come before the beat that reads it.

`project-manager`'s runner starts each beat in its window, hands it to the skill above, and mails the
owner when one gave up or never ran. The full table, prerequisites included, is `beats.py --list` in
`project-manager`. The runner starts this skill with `/zynkr-ops-weekly <mode> week=<ISO week>`, and
in a rehearsal `config=<path>`. Use the week as given; never work it out again mid-run.

## Configuration (private — never in this repo)

This repository is public. The method is here; the **identifiers are not**. At runtime load
`~/.config/zynkr/ops-weekly.json` (schema in `references/config.example.json`, notes in
`references/config.README.md`; override the path with `ZYNKR_OPS_WEEKLY_CONFIG`). The whole loop reads
this one file; each skill names the keys it uses.

| Config key | Role |
|---|---|
| `google_account` | account for every `google-workspace` MCP call |
| `space.id` · `space.name` | the Chat space, in `spaces/<id>` form — **the `spaces/` prefix is required** — and its label |
| `doc.id` · `doc.tab_id` · `doc.tab_name` · `doc.archive_tab_id` · `doc.archive_tab_name` | the weekly operations Doc, the tab of week sections, and the sibling tab `tidy` archives into (`ops-weekly-doc`) |
| `chat_ids` | **the only hardcoded map** — Chat `users/<id>` → email, so `collect` can @-mention. See below |
| `reporters` | the team's addresses: who a `team` recap goes to when `routine.recap_to` is not set, and (before 2026-W45) who was expected to post `#週報`. Keep it non-empty: `recap.py` refuses an empty list |
| `sources.main_tracker` | the Main Tracker: `id`, `tab` (the tab `snapshot` copies) and `cycle` (`2026H2`), which keeps one half-year's item numbers apart from the next |
| `sources.ledger.id` · `sources.ledger.epoch_week` | the Weekly Ledger, and the ISO week its row layout counts from. **Never change `epoch_week` after the first snapshot**: every week's rows are computed from it |
| `harvest.output_folder_id` | the Drive folder the Wednesday harvest routine writes `<WEEK>/harvest-<person>.md` into (`SKB-094`); `collect` reads it |
| `meeting.calendar_title` | the weekly meeting's calendar title; `minutes` finds the transcript by it and the date, never "the latest" |
| `routine.recap_to` · `routine.weekly_to` | who gets the Monday recap and the Friday 【週結】: the team address. `routine.recap_audience` (`owner` · `team`) is read until `recap_to` is set |
| `routine.apply_mode` | what `apply` does with an approved change: `shadow` (record it, write nothing) unless it says exactly `live` |
| `routine.notice_from` | the first ISO week whose missed beats `project-manager` mails the owner about. Set it to the week you install, never earlier. Missing, or not a week = no notices |
| `sources.state_rules.path` | optional; where zynkr-gm's `derive_state.py` lives. Default `~/.claude/skills/zynkr-gm/scripts/derive_state.py` |
| `routine.model` | the model the runner starts each beat with. See `project-manager`'s `references/scheduling.md` |

If a required value is missing or still a placeholder, **fail loud** (`config: doc.id unset`). Never
guess an id, and never fall back to a hardcoded department map.

### Why `chat_ids` has to exist

Chat and Docs do not share an identity space. The Chat payload **carries no email field at all**; the
Doc gives an email and no user id. Nothing bridges them automatically — the People API resolves the id
but exposes no name or email for domain profiles. So the bridge is a short hardcoded map, and only that.
Key each person by the form their messages arrive as (a display name when they are in the account's
Contacts, `users/<21-digit id>` when not), and keep both if unsure.

## Required reading (before acting)

| File | Read when |
|---|---|
| `references/ledger.md` | Every mode: the Ledger's layout, the commit order, how to read one week back |
| `references/wording.md` | **Always, before writing any zh-TW the team will read** — house voice, per `/content-translator` |
| `references/message-templates.md` | Composing the recap mail or the Chat line |
| `references/routing.md` | `collect`: who is expected, from the Doc's owner chips |

## Step 0 — Anchor on today

Resolve today in `Asia/Taipei`, only for the dates the team reads, such as what is due or overdue: the
runner's clock need not be Taipei's (`SKB-114`), so its day can differ. The **ISO week key**
(`2026-W45`) is machine-only: the runner passes it
as `week=`, and it goes in the receipt. The **week label** (`WB 11/2`, the Monday that opens the week)
is what the team reads in every subject and footer. `references/wording.md` explains why both exist.

## Step 1 — Load config and check idempotency

Load the private config; fail loud on placeholders. Each mode then checks whether it already delivered
this ISO week, as its section says: `recap` looks for its own subject in Sent, `collect` for the
week's Harvest cell in the Ledger's `Weeks` row. A beat that already delivered writes nothing and
receipts `status=ok` with `already-…`.

## The modes

**Saved by the runner (`SKB-118`).** Under the runner each call a script prints also carries
`"saved_by": "runner"`: the runner saves its result itself, exactly as the tool returned it, the moment
the call returns, and says so. Make the call with `args` copied exactly, and do not save it: the guard
refuses a Write to that path. Wherever a step below says to save a printed call's result, a call marked
so is already saved. Never edit or rewrite a saved result, with any tool: every step refuses one that
changed after the runner saved it. When a step says a result is missing, does not parse or changed, make
that call again exactly as printed and run the step again; if it still refuses, receipt `status=failed`
with its message.

### `collect` (Wed 14:30 → 21:00)

Each person's week, from the Wednesday harvest routine's files (`SKB-094`) into the Ledger's
`Harvest` block, then one Chat line for whoever had a quiet week. It replaces the `#週報` posts and
the `Reports` tab from 2026-W45. `scripts/harvest.py` works out every call. Make each one exactly as
printed and save its result unchanged to the path it gives, as in `recap`. When a script exits
non-zero, stop: receipt `status=failed delivered=<its message>`.

1. `python3 scripts/harvest.py start --week <ISO week>`. Make its calls: this week's `Weeks` row, the
   search for the week folder, which is named after the Wednesday the routine closed, and last week's
   `Weeks` row (`SKB-128`), which says whether the Ledger holds a snapshot of the tracker.
2. `python3 scripts/harvest.py files --dir <dir>`:
   - `already` means the week is recorded. Receipt `status=ok` with its `delivered` and do nothing else.
   - `waiting` means the routine has not finished. Receipt `status=waiting` with its `delivered`. The
     runner looks again an hour later, until 21:00. A harvest still not ready by then reaches the owner
     as one 【排程沒跑完】 (`no-harvest`), and `sections` goes ahead from 21:00 with 「本週無資料」.
   - Otherwise, make its one call, the listing of the week folder.
3. `python3 scripts/harvest.py read --dir <dir>`. It returns `waiting` (as above), or calls to make:
   the run file, each `harvest-<person>.md`, and last week's snapshot block when the Ledger holds one.
4. **Tie each line to the tracker item it moves (`SKB-128`).** Run `python3 scripts/harvest.py tags --dir
   <dir>`. It returns `waiting` (as above), or `"tags": "none"` when there is no snapshot to read or no
   line to tie (go to step 5 with no `--tags`), or `lines`, the lines `collect` keeps, and `items`, the
   tracker's open items with their owner and status. For each line, decide which one item it is work on:
   - the item whose deliverable the line names: the same product, page, course, client step or spec. The
     line and the item's name share the thing itself, not just a word;
   - a line can move an item that is someone else's. The owner is there to tell items apart, never to rule
     one out;
   - when two items fit, take the narrower one. When none plainly fits, leave it empty. An empty tag only
     moves the line to 「不在 Tracker」 in the Doc. A wrong one puts a false claim before the meeting, and
     before the owner on Friday.

   Save `{"<line id>": "<item #>", …}` to the `save` path it prints: one entry per line, each id exactly as
   listed, `""` for a line the tracker holds no item for. An id carries a hash of its line, so a tag from
   another run never fits.
5. `python3 scripts/harvest.py check --dir <dir> --tags <the save path>`. It returns `waiting` while the
   run file is not `ok`. Otherwise it writes `rows.json` and names who had a 「本週無資料」 week.
   - **What it keeps.** Per person, at most 15 lines by kind (`SKB-128`): 4 waiting, 8 shipped and 3
     moving, a share a kind does not use going to shipped, then waiting, then moving. One `totals` row says
     how many lines of each kind the harvest held, and `left_out` in the output how many lines were not
     kept. Within a kind the workstreams take turns, so a long first workstream does not take the kind's
     whole share. With a longer roster the cap comes down, only as far as the 80-row block needs: a person
     who holds few lines leaves the rows they do not use to the others. Two harvest files are never
     recorded under one name: the roster's own spelling keeps it, and a file whose name is only an alias
     or a first word of someone who has their own keeps the name it was written with. A line that only
     says nothing waits is not an item, and a harvest with no line of any kind is a quiet week.
   - **What it will not read.** A harvest file that holds bullets but none under a kind marker is
     refused (exit 3): its shape changed, and recording it as 「本週無資料」 would drop a whole week
     without a word. The beat fails and the owner hears. The markers are read as the routine writes them
     and in the shapes a model drifts to (a bullet before the marker, a colon or a count in it, another
     case, a heading). `unread` in the output counts bullets that sat before a workstream's first marker.
     A bullet set deeper than its list's first one is a detail of the line above it and joins that line.
   - **What it ties.** A kept line's row carries the item its tag names when that item is in last week's
     snapshot, still open (not 完成, not 放棄) and on one row of the tracker. Any other tag is left out, and
     `tags` in the output says which and why (`rejected`, `missing`, `unknown`). Read it. A tag left out is
     not an error: no snapshot, no tags file or one that does not parse only leaves every line without an
     item, and never fails the beat.
6. Record the block (`references/ledger.md`): `python3 scripts/ledger.py block start --tab Harvest
   --week <ISO week> --rows <rows_path>`, then `block plan`, `block check` and `block confirm`. Make
   each step's calls in turn, exactly as in `recap`'s Ledger reads; `block plan` reads the 80-row
   block back in two pages, and `block check` needs both.
   **Skill versions** (`SKB-110`; only when `routine.skills_block` is `true`). Call `list_installs` on
   the `zynkr-atlas` MCP server and save its result unchanged to `<dir>/installs.txt`. Run
   `python3 scripts/skills.py rows --week <ISO week> --list <dir>/installs.txt --out <dir>/skills-rows.json`,
   then record it as above with `--tab Skills --rows <dir>/skills-rows.json`. Its `block plan` reads the
   200-row block back in four pages. A failure here skips the block and never fails the beat: Atlas
   not answering, or a script exiting non-zero. Note `skills-failed`, and Monday's recap leaves out 技能更新.
7. **The chase.** Run `python3 scripts/harvest.py chase --dir <dir>`.
   - `send`: make its one `send_message` call exactly as printed, check the result names the message
     it posted, then run `harvest.py chased --dir <dir>`. The line @-mentions each quiet person once
     and asks whether it was a quiet week.
   - `none` or `already`: post nothing.
   - The chase never fails the beat, because the Ledger block is what `sections` and Monday's recap
     read. A post that fails adds `chase-failed` and is not tried again.
8. Receipt `status=ok delivered=<block confirm's delivered>;chase-<send|none|already|failed>;tags-<tagged>-of-<lines>`
   (the two numbers from `check`'s `tags`; `tags-none` when it had no snapshot or no tags file), adding
   `;skills-<ok|failed>` when `routine.skills_block` is on, and `;grid-low-<tab>` for each tab a
   `block plan` warned has fewer than eight weeks of rows left.

### `recap` (Mon 08:00 → 20:00)

The week's team recap, by mail, about **the ISO week that just ended** (`SKB-044` decision D2:
the recap moved from Thursday night to Monday morning). It reads the Weekly Ledger, zynkr-gm's
state rules and one mail, the Monday Sales Pulse (09:30 Taipei, before the recap's window), never the Doc, so it does not inherit
the Doc's multi-hour reads. It writes nothing: no Ledger cell, no tracker cell, no Chat post.
Since `SKB-091` it also carries **this week's plan**, per person: at most five lines, in order,
from the meeting's open actions, items overdue or due within 14 days, P0/P1 items with no dates,
and that person's next steps from the Pulse. `recap.py` builds it; a line that cites no item # never
reaches the mail, and a line from the Pulse is the Pulse's own step, so the Pulse is its source.
From 2026-W45 the mail's 卡關 are the waiting lines of last week's harvest (`Harvest`, which `collect`
records); before that they came from the `#週報` posts in `Reports`. `collect` keeps four waiting lines
a person, so the mail also says how many more each harvest held (`另有沒列出的：Ann 2 件`, from the
`totals` row, `SKB-128`).

Since `SKB-128` the mail opens with **上週進度**, before the plan: the stretch last week's harvest
covers, then per person what it held and the lines Thursday's block showed for it, by tracker item.
`sections` keeps those lines on this Mac (`<state>/<week>.progress.json`); a person it kept none for
gets the harvest's own text, cut at a space. It is the harvest that closed on Wednesday, the one the
meeting saw: work from Thursday on shows a week later, and the section says so. The plan then takes
what the harvest left open, after a person's actions and on top of the five lines: at most two items
they still had in motion (`#6.10 … — 上週還在進行`) and two lines waiting on them (`在等你：…`). An
item the plan already names for them, by an action or a due date, is not repeated. A week whose
harvest was not recorded says so under 上週進度, and the rest of the mail is as it was.

`scripts/recap.py` works out every range, fact and the subject; you make its printed calls exactly,
save each result unchanged, and write the TL;DR.

1. **The week.** Use the `week=` argument the runner passes; that is the current week, and
   `recap.py` works out the one before it. If a `config=<path>` argument is present, add
   `--config <path>` to `start`.
2. `python3 scripts/recap.py start --runner-week <W>` → make the two printed calls; keep the `dir`.
3. `python3 scripts/recap.py blocks --dir <dir>`.
   - `"notice": true` → last week never closed out (no committed snapshot). Run
     `recap.py notice --dir <dir>` and send that mail (to the owner only) through steps 7–9.
     Receipt `status=ok`, `delivered=notice-sent`.
   - Otherwise make the printed calls (the block reads and one Gmail search for the Sales Pulse)
     and save each one.
   - Then `python3 scripts/recap.py pulse --dir <dir>`: with `"pulse": true`, make its calls (every
     thread the search found, newest first, at most five, each fetched as HTML so the Pulse keeps one
     person per list item) and save each; with `false`, go on — the mail says the sales lines are
     missing.
   - Then `python3 scripts/recap.py skills --dir <dir>` (`SKB-110`). The reads it compares were among
     `blocks`' calls: the week's Skills block and the latest earlier week's that `collect` recorded (up
     to eight weeks back).
     - It lists `bash` commands: read-only `gh api` lookups of the pull request behind each commit.
       Run each and save its output unchanged to its `save` path. A command that fails leaves its line
       without the PR title.
     - It names `missing` reads: save those results from `blocks`' calls, then run it again.
     - `"skills": false`: go on. The mail has no 技能更新 block (`why` says why; an unreadable read or a
       Weeks grid that stops before V is one of them, never a reason to stop).

     The recap compares weeks that `collect` recorded, so it still writes nothing.
4. `python3 scripts/recap.py build --dir <dir> --today <today, YYYY-MM-DD>` → it prints the counts,
   the plan's line count per person, whether the Pulse was read, and the path of `facts.json`. A non-zero exit means stop with `status=failed` and the reason;
   nothing has been sent.
5. **Write the TL;DR.** Read `facts.json`. Write **at most three** lines, in zh-TW and in the voice of
   `references/wording.md`, about what most needs the team's attention. **Every line cites the item
   number it is about** (`#1.03`). Save them as a JSON list to `tldr.json` in the run folder. Write
   about what the facts show, never about how they were gathered.
6. `python3 scripts/recap.py render --dir <dir> --tldr <dir>/tldr.json` → `subject`, `to` and
   `body_path`. Lines that cite no real item number are dropped, and it says which.
7. **Never send twice.** `search_gmail_messages` with `sent_check.query` and `sent_check.page_size`
   exactly as `render` (or `notice`) printed them, then read the subject of each message it finds.
   One that starts with `sent_check.prefix` → this week's mail already went: do not send; receipt
   `status=ok`, `delivered=already-sent`. The recap's prefix leaves out its counts, which change with
   the day (逾期 N 件), so a send made yesterday still counts. (Gmail's `subject:` search misses 【】
   and CJK text, so compare the subjects yourself.)
8. `send_gmail_message` to exactly `to`, with exactly `subject`, the contents of `body_path` as the
   body, and `body_format="html"`. No cc, no bcc, no other recipients.
9. **Assert it fired.** Make the `sent_check` search again and find a message whose subject equals
   `subject`. Found → receipt
   `status=ok`, `delivered=recap-sent-to-<count of addresses in to>`. Not found → `status=failed`,
   `delivered=send-not-found`.

**Who receives it** is decided by the owner, never by this run: `routine.recap_to` (the team
address, `SKB-091`) when it is set; otherwise `routine.recap_audience` — `owner` sends it to the
account alone, `team` to every address in `reporters`, from the Monday `routine.recap_team_from`
names when it is set. `render` works this out and prints `to`; send to exactly that.

### `status` (on demand)

Read-only. Print what the Ledger holds for this ISO week: its `Weeks` row (which blocks are recorded
and when), and which harvest files are in this week's folder. Writes nothing — use it to debug before
reaching for a mode that writes. Which beats ran, and why one did not, is `/project-manager`'s check-in.

## Receipt

Every run ends with a compact report (mode, ISO week, what was read, what was written where, what was
delivered), then a receipt line on its own line, exactly in this shape:

```
ZYNKR-OPS-WEEKLY-RESULT: mode=<mode> week=<ISO week> status=ok|partial|failed delivered=<short>
```

`week=` stays the **ISO key** (`2026-W45`), not the `WB 11/2` label the team reads: the line is
machine-facing, year-qualified and sortable, and it sits next to the `<week>.<mode>.done` state files
that use the same key. `status=ok` means **every** side effect this mode owes landed and you verified
it — the mail is in `in:sent`, the block reads back, the `Weeks` cell reads `ok`. Anything short of that
is `partial` (some landed) or `failed` (none did), with the reason in `delivered=`.

```
ZYNKR-OPS-WEEKLY-RESULT: mode=recap week=2026-W45 status=ok delivered=recap-sent-to-6
ZYNKR-OPS-WEEKLY-RESULT: mode=recap week=2026-W45 status=ok delivered=already-sent
ZYNKR-OPS-WEEKLY-RESULT: mode=recap week=2026-W45 status=ok delivered=notice-sent
```

This line is not decoration. `project-manager`'s `run_week.sh` parses it and stamps the week done
**only** on `status=ok` naming the mode and week it passed; anything else retries on the next tick
inside the window and gives up after three attempts. **Never write `status=ok` because the run finished
— write it because you checked.** `claude -p` exits 0 either way.

---

## Guardrails

- **Never write the Doc or the Main Tracker.** Those are `ops-weekly-doc`'s and `ops-weekly-tracker`'s;
  the runner denies the Doc tools to this skill's beats, and a hook refuses any tracker write.
- **Never invent a metric.** Cite the cell, or leave the slot empty.
- **The owner's week stays the owner's.** The guard refuses a call that names the owner's
  weekly-insights folder, searches from or above it, or globs into it; never look for another way in,
  and never search from `~` or `~/.claude`.
- **Never treat mail as an input** — with one designed exception: `recap` reads the Monday Sales
  Pulse, which Zynkr CRM mails to the team list (`SKB-096`; the claude.ai routine that sent it from
  the owner's account is off), parsed by `recap.py` for its "Next step this week" lines. Only the
  thread's first message counts, and only when its sender's address is on the owner's own domain
  exactly: parsed, never a substring, never a subdomain. The domain's mail authentication stops an
  outsider forging that sender, so a look-alike mail from anyone else is never read.
  Every other state comes from the Ledger, the harvest files and the Doc.
- **Fail loud on config.** Placeholder id → stop; a wrong id writes into someone else's file.
- **The recap mails once.** It reads the Ledger, sends one mail to the address the config names, and
  never adds a recipient or writes a cell.
- **Write like a colleague, not a report generator.** Every published line is zh-TW that the team reads.
  No 官腔 (`徵集`/`產出`/`決議候選`), no half-translated lines (`KPI off-target`, `carry-over`), no
  internal mode names (`collect`, `骨架`) and no parenthetical explanations of your own filtering.
  `references/wording.md` carries the rules and the frozen strings.

## Limitations

- `send_message` posts plain text; @-mentions render as names, not live mentions.
- The beats run on **launchd** on the owner's Mac, through `project-manager`; a Mac that is asleep
  through a window misses the beat, and `project-manager` mails the owner about it.
- **The Ledger's grid is grown by hand.** `ledger.py` warns when fewer than eight weeks of rows remain
  and refuses a week that does not fit; `references/ledger.md` says how to grow it.

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
