---
name: zynkr-ops-weekly
sheetId: "3.19"
description: >-
  The core of a small team's weekly operations loop: the machine-owned Weekly Ledger every part of
  the loop records into, the Monday recap and plan mailed to the team (recap), and the Thursday
  collect that reads each person's Wednesday harvest into the Ledger and chases whoever has none in
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
| **`zynkr-ops-weekly`** (this skill) | **mail, Chat, the Weekly Ledger** | `recap` (Mon), `collect` (Thu) |
| `ops-weekly-doc` | the weekly operations Doc | `sections` (Thu), `minutes` · `tidy` (Fri) |
| `ops-weekly-tracker` | the Main Tracker, and its own Ledger blocks | `propose` (Fri) · `apply` · `snapshot` (Fri → Sun) |
| `project-manager` | nothing but its notice mail | runs the beats on time, mails the owner when one did not run |

The other two writers call this skill's `scripts/ledger.py` and `scripts/parse_routing.py` and read its
`references/`; they never keep a copy. Every department heading in the Doc carries its owner's Google
Docs person chip, keyed by email: that is the routing table, read at run time, so the loop keeps **no
department map of its own**.

---

## The week

| When (Taipei) | Beat | Skill | What happens |
|---|---|---|---|
| Mon 10:00 → 23:30 | `recap` | this one | Mail the team last week's recap and this week's plan, read from the Ledger |
| Wed 20:00 | — | `weekly-insights` | Each person's week closes; the harvest routine writes `harvest-<person>.md` (`SKB-094`) |
| Thu 09:00 → 13:00 | `collect` | this one | Read the harvest into the Ledger's Harvest block; one Chat line names whoever has none |
| Thu 09:30 → 13:30 | `sections` | `ops-weekly-doc` | Each team's 進度 · 卡關 · 下一步 · 待討論 in this week's Doc section |
| Thu 21:00 | — | team | The weekly meeting |
| Thu 23:00 | `scaffoldNextWeek` | Apps Script | Copy the newest week section forward |
| Fri 08:00 → 17:30 | `minutes` | `ops-weekly-doc` | The meeting's minutes from its transcript, into the Doc and the Ledger |
| Fri 09:00 → 17:30 | `tidy` | `ops-weekly-doc` | Trim the copied section; fill next week's actions |
| Fri 10:00 → 17:30 | `propose` | `ops-weekly-tracker` | The 【週結】: this week's tracker changes, for the owner's reply |
| Fri 18:00 → Sun 23:00 | `apply` · `snapshot` | `ops-weekly-tracker` | Write what the owner approved; copy the tracker into the Ledger |

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
| `reporters` | the emails expected to report each week |
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

Resolve today in `Asia/Taipei`. The **ISO week key** (`2026-W45`) is machine-only: the runner passes it
as `week=`, and it goes in the receipt. The **week label** (`WB 11/2`, the Monday that opens the week)
is what the team reads in every subject and footer. `references/wording.md` explains why both exist.

## Step 1 — Load config and check idempotency

Load the private config; fail loud on placeholders. Each mode then checks whether it already delivered
this ISO week, as its section says: `recap` looks for its own subject in Sent, `collect` for the
week's Harvest cell in the Ledger's `Weeks` row. A beat that already delivered writes nothing and
receipts `status=ok` with `already-…`.

## The modes

### `collect` (Thu 09:00 → 13:00)

Each person's week, from the Wednesday harvest routine's files (`SKB-094`) into the Ledger's
`Harvest` block, then one Chat line for whoever had a quiet week. It replaces the `#週報` posts and
the `Reports` tab from 2026-W45. `scripts/harvest.py` works out every call. Make each one exactly as
printed and save its result unchanged to the path it gives, as in `recap`. When a script exits
non-zero, stop: receipt `status=failed delivered=<its message>`.

1. `python3 scripts/harvest.py start --week <ISO week>`. Make its two calls: this week's `Weeks` row
   and the search for the week folder, which is named after the Wednesday the routine closed.
2. `python3 scripts/harvest.py files --dir <dir>`:
   - `already` means the week is recorded. Receipt `status=ok` with its `delivered` and do nothing else.
   - `waiting` means the routine has not finished. Receipt `status=waiting` with its `delivered`. The
     runner looks again an hour later, until 13:00. A harvest still not ready by then reaches the owner
     as one 【排程沒跑完】 (`no-harvest`), and `sections` goes ahead at 13:00 with 「本週無資料」.
   - Otherwise, make its one call, the listing of the week folder.
3. `python3 scripts/harvest.py read --dir <dir>`. It returns `waiting` (as above), or calls to make:
   the run file and each `harvest-<person>.md`.
4. `python3 scripts/harvest.py check --dir <dir>`. It returns `waiting` while the run file is not
   `ok`. Otherwise it writes `rows.json` (one row per line of a harvest, at most 15 per person,
   waiting lines first) and names who had a 「本週無資料」 week.
5. Record the block (`references/ledger.md`): `python3 scripts/ledger.py block start --tab Harvest
   --week <ISO week> --rows <rows_path>`, then `block plan`, `block check` and `block confirm`. Make
   each step's calls in turn, exactly as in `recap`'s Ledger reads.
6. **The chase.** Run `python3 scripts/harvest.py chase --dir <dir>`.
   - `send`: make its one `send_message` call exactly as printed, check the result names the message
     it posted, then run `harvest.py chased --dir <dir>`. The line @-mentions each quiet person once
     and asks whether it was a quiet week.
   - `none` or `already`: post nothing.
   - The chase never fails the beat, because the Ledger block is what `sections` and Monday's recap
     read. A post that fails adds `chase-failed` and is not tried again.
7. Receipt `status=ok delivered=<block confirm's delivered>;chase-<send|none|already|failed>`.

### `recap` (Mon 10:00 → 23:30)

The week's team recap, by mail, about **the ISO week that just ended** (`SKB-044` decision D2:
the recap moved from Thursday night to Monday morning). It reads the Weekly Ledger, zynkr-gm's
state rules and one mail, the Monday Sales Pulse (09:30), never the Doc, so it does not inherit
the Doc's multi-hour reads. It writes nothing: no Ledger cell, no tracker cell, no Chat post.
Since `SKB-091` it also carries **this week's plan**, per person: at most five lines, in order,
from the meeting's open actions, items overdue or due within 14 days, P0/P1 items with no dates,
and that person's next steps from the Pulse. `recap.py` builds it; a line that cites no item #
(or, from the Pulse, a deal) never reaches the mail.

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
   - Then `python3 scripts/recap.py pulse --dir <dir>`: with `"pulse": true`, make its one call (the
     Pulse thread) and save it; with `false`, go on — the mail says the sales lines are missing.
4. `python3 scripts/recap.py build --dir <dir> --today <today, YYYY-MM-DD>` → it prints the counts,
   the plan's line count per person, whether the Pulse was read, and the path of `facts.json`. A non-zero exit means stop with `status=failed` and the reason;
   nothing has been sent.
5. **Write the TL;DR.** Read `facts.json`. Write **at most three** lines, in zh-TW and in the voice of
   `references/wording.md`, about what most needs the team's attention. **Every line cites the item
   number it is about** (`#1.03`). Save them as a JSON list to `tldr.json` in the run folder. Write
   about what the facts show, never about how they were gathered.
6. `python3 scripts/recap.py render --dir <dir> --tldr <dir>/tldr.json` → `subject`, `to` and
   `body_path`. Lines that cite no real item number are dropped, and it says which.
7. **Never send twice.** `search_gmail_messages` with `in:sent newer_than:3d`, then read the
   subjects of what comes back. One equals `subject` exactly → do not send; receipt `status=ok`,
   `delivered=already-sent`. (Gmail's `subject:` search misses 【】 and CJK text, so compare the
   subjects yourself.)
8. `send_gmail_message` to exactly `to`, with exactly `subject`, the contents of `body_path` as the
   body, and `body_format="html"`. No cc, no bcc, no other recipients.
9. **Assert it fired.** Search `in:sent newer_than:1d` again and find the subject. Found → receipt
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
  Pulse, only from Sent and only the thread's first message from the owner's own account (the
  routine sends it from there), parsed by `recap.py` for its "Next step this week" lines. A
  look-alike mail from anyone else is never read.
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
