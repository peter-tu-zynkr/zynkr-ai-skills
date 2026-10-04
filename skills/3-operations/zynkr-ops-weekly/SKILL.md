---
name: zynkr-ops-weekly
sheetId: "3.19"
description: >-
  The weekly operations loop that keeps a Google Chat space and a weekly operations Google Doc
  in sync. Ten scheduled modes run one beat each: `recap` (Mon 09:00 — mail last week's tracker
  changes, call-outs, decisions and blockers, read from the Weekly Ledger, never the Doc), `nudge` (Mon 09:00 — post the four-line
  template plus last week's decisions), `rollup` (Tue 09:00 — read the week's `#週報` posts,
  route each one to its department heading using the owner person-chips already in the Doc, and
  write a clearly-marked auto-summary block), `chase` (Tue 09:30 — @ the owners who did not
  post), `agenda` (Wed 17:00 — re-sweep for late arrivals, then produce carry-over, overdue,
  KPI-off-target and the ≤3 decisions the Thursday meeting must actually make), and `decisions`
  (Thu 22:00 — post the resolutions back to the space, record them in the Weekly Ledger, send the
  recap mail and assert it actually went out), and `tidy` (Fri 09:00 — keep the newest
  auto block under each department, archive the stacked older copies to the 封存 tab, and carry
  still-open items forward one per line), and `snapshot` (Fri 18:00, catching up through Sun —
  copy every Main Tracker item into the machine-owned Weekly Ledger once per ISO week), `propose`
  (Fri 10:00 — suggest the week's tracker changes from the Ledger and mail the owner one numbered
  list to approve by reply) and `apply` (Fri 18:00 through Sun — read that reply and record each
  decision; in shadow mode nothing reaches the tracker). Routing is never hardcoded: it is read at
  run time from the Doc's own owner chips, so changing the Doc changes both the routing and the
  recap-mail recipient list. Trigger EAGERLY on "/zynkr-ops-weekly", "營運週報", "週報彙整",
  "把大廳的週報整理進 Doc", "roll up the chat updates", "誰還沒回報", "補件提醒", "週四議程",
  "產週會議程", "會後回貼決議", "recap 信", "weekly ops loop", "ops weekly rollup", or any ask to
  collect / chase / summarise the team's weekly updates, build the weekly meeting agenda, or
  publish the meeting's decisions. BOUNDARY — do NOT hijack: /zynkr-gm (the founder's own
  company-level Monday brief, reads this Doc but never writes it), /project-status-update (one
  project's status email from its own tracker), /planning-tracker-sync (the H2 tracker block and
  its own nudges), /project-client-status (client-facing consulting status), /admin-meeting-prep
  (per-meeting packets for external meetings). This skill owns two artefacts — the weekly
  operations Doc's current week section, with one channel loop around it, and the Weekly Ledger.
category: operations
project: zynkr-ops-weekly
platform: claude
status: WIP
visibility: public
author: Peter Tu
input: "A mode (one beat from The cadence table, or status) and an optional 'as of' date; all identifiers come from the private config at ~/.config/zynkr/ops-weekly.json."
process: "Anchor on today → resolve the target Thursday (Monday's posts belong to the NEXT Thursday) → load config → check idempotency → read routing from the Doc's owner chips → sweep Chat by createTime → parse the four lines → write a marked block → assert delivery."
output: "Per mode: a Chat post, a marked 〔自動彙整〕 block per department in this week's Doc section, the Wednesday agenda, a recap email, a Friday tracker snapshot, and a Friday approval mail."
synergy: [zynkr-gm, project-status-update, planning-tracker-sync, ops-flow-optimization, admin-governance]
executed_by: internal-user
house-style: bound

---

# zynkr-ops-weekly

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill zynkr-ops-weekly
```

A small team posts its weekly update into a Google Chat space on Monday, and discusses
operations from a weekly Google Doc on Thursday. Nothing connects the two, so the Doc records
what people *intended* to do (week after week, near-verbatim) while the actual progress stays
in chat scrollback. This skill is the connective tissue: it collects, routes, chases, and
closes the loop — one scheduled beat at a time.

It is built around a single discovery about the Doc: **every department heading already carries
its owner's Google Docs person chip**, keyed by email. That is a routing table someone is
already maintaining by hand for other reasons. So this skill keeps **no department map of its
own** — it reads the chips at run time. Change the Doc, and routing *and* the recap-mail
recipient list both follow.

**It writes narrowly.** Auto-content only ever lands inside a block stamped
`〔自動彙整 WB 9/14 · 09-15 12:00〕`. It never edits a line a human wrote. A bot that silently
rewrites prose in a doc people are actively editing is a bot nobody trusts by week two.

---

## The cadence

| When | Mode | Who | What happens |
|---|---|---|---|
| Mon 09:00 | `recap` | skill | Mail last week's tracker changes, call-outs, decisions and blockers, read from the Weekly Ledger. Runs before `nudge` |
| Mon 09:00 | `nudge` | skill | Post the four-line template + last week's decisions + the Tue 09:00 cut-off |
| Mon (all day) | — | team | People post `#週報` in the space |
| **Tue 09:00** | `rollup` | skill | Read the window, route by owner chip, write the marked block, backfill metrics |
| **Tue 09:30** | `chase` | skill | Owners in the Doc − people who posted → @ the difference |
| Wed 17:00 | `agenda` | skill | Re-sweep for late arrivals, then carry-over · overdue · KPI · ≤3 decisions |
| **Thu 21:00** | — | team | The weekly meeting. Discuss exceptions and decisions only; edit the Doc live |
| **Thu 22:00** | `decisions` | skill | Resolutions → space (3 lines) + Weekly Ledger + recap mail + **assert the send**; no decisions → one line, no mail |
| Thu 23:00 | `scaffoldNextWeek` | **Apps Script** | Duplicate the newest week section, re-stamp next Thursday. Runs **after** `decisions` — see Step 4.1 |
| **Fri 09:00** | `tidy` | skill | Keep the newest auto block per department, archive the rest to the 封存 tab, carry still-open items one per line |
| Fri 10:00 | `propose` | skill | Suggest this week's tracker changes from the Ledger's decisions and reports; record them; mail the owner one 【待核准】 list |
| Fri → Sun 22:00 | — | owner | Reply to that mail: 「全部核准」 · 「核准 1 3」 · 「退回 2」. `apply` confirms in the thread what it recorded |
| Fri 18:00 (to Sun 23:00) | `snapshot` | skill | Copy every Main Tracker item into the Weekly Ledger, once per ISO week. Monday's recap compares two of these to say what changed |
| Fri 18:00 (to Sun 23:00) | `apply` | skill | Read the owner's reply and record each decision. Shadow mode: nothing is written to the tracker yet |

`chase` must run **after** `rollup` — it cannot know who is missing until the roll-up has
resolved who posted. Both beats sit on Tuesday morning so that the Doc's Thursday section is
already full two days before anyone opens it.

**Why the scaffold is not this skill's job.** The split is by *whether judgement is needed*, not
by preference. Duplicating a section is purely mechanical and must never fail, so it belongs to
Apps Script, whose authorisation does not expire. In the week this skill breaks entirely, the
skeleton still opens and Thursday still has a page. See `references/scaffold.md`.

> **Why the Doc used to grow without bound, and what actually stopped it.** Every writer here
> is insert-only and the scaffold copies the newest section *verbatim*, so each section inherits
> every `〔自動彙整〕` block ever written. Audited 2026-09-15: 34 sections / 5,325 lines, the
> newest section holding 22 blocks of which only 4 were that week's, sections grown 130 → 292
> lines in four weeks.
>
> Two fixes were attempted. Moving whole old **sections** to an archive tab was built and
> **rolled back the same day** (`SKB-029`) — it had to move human-written content, risked the
> owner person chips, and did not fit in one Apps Script run. Trimming the stacked **blocks**
> inside the newest section (`SKB-030`, the Friday `tidy` beat) does fit: it only ever touches
> this skill's own output, never reaches a chip, and deletes only copies whose originals sit in
> the frozen previous section. Section size is now stable instead of linear. **Read both specs
> before proposing a third.**

---

## Configuration (private — never in this repo)

This repository is public. The method is here; the **identifiers are not**. At runtime load
`~/.config/zynkr/ops-weekly.json` (schema in `references/config.example.json`, notes in
`references/config.README.md`; override the path with `ZYNKR_OPS_WEEKLY_CONFIG`).

| Config key | Role |
|---|---|
| `google_account` | account for every `google-workspace` MCP call |
| `space.id` | the Chat space, in `spaces/<id>` form — **the `spaces/` prefix is required** |
| `space.name` | human label, for report lines only |
| `doc.id` · `doc.tab_id` · `doc.tab_name` | the weekly operations Doc and the tab that holds the week sections |
| `doc.archive_tab_id` · `doc.archive_tab_name` | the **sibling tab** `tidy` moves old auto blocks into. It must be a tab in the *same* Doc: `carryover.py` reads all tabs as one stream to compute `↻N週`, so a separate file resets every streak and blinds the Wednesday agenda |
| `chat_ids` | **the only hardcoded map** — 6 rows of Chat `users/<id>` → email. See below |
| `reporters` | the emails expected to post each week (6 people; excludes non-reporting members) |
| `sources.main_tracker` · `sources.okr_kpi_tracker` | sheets read to backfill metrics and overdue items. `main_tracker.tab` is the tab `snapshot` copies; `main_tracker.cycle` (`2026H2`) keeps one half-year's item numbers apart from the next |
| `sources.ledger.id` · `sources.ledger.epoch_week` | the machine-owned Weekly Ledger, and the ISO week its row layout counts from. **Never change `epoch_week` after the first snapshot**: every week's rows are computed from it |
| `routine.apply_mode` | what `apply` does with an approved change: `shadow` (record it, write nothing to the tracker) unless it says exactly `live`. `live` is refused until Phase 3b ships |
| `routine.recap_audience` | who gets the Monday recap: `owner` (the account alone) while it is new, `team` (every reporter) once the owner has seen it work. Missing means `owner`. `routine.recap_team_from` (`YYYY-MM-DD`) sets the switch ahead: `team` starts with that Monday's recap |
| `sources.state_rules.path` | optional; where zynkr-gm's `derive_state.py` lives. Default `~/.claude/skills/zynkr-gm/scripts/derive_state.py` |
| `routine.*` | how the eight beats are scheduled — mechanism, model, timezone, per-beat windows. See `references/scheduling.md` |

If a required value is missing or still a placeholder, **fail loud** (`config: doc.id unset`).
Never guess an id, and never fall back to a hardcoded department map.

### Why `chat_ids` has to exist

Chat and Docs do not share an identity space. The Chat payload **carries no email field at
all**; the Doc gives an email and no user id. Nothing bridges them automatically — the People
API resolves the id but exposes no name or email for domain profiles. So the bridge is six
hardcoded rows, and only six. Everything else is read from the Doc.

The map has **two key forms**, and a real space yields a mix of both: the MCP renders a sender
as a **display name** when that person is in the account's personal Contacts, and as
`users/<21-digit id>` when they are not. Key each person by the form their messages actually
arrive as, and keep both if unsure — a person joining Contacts later would otherwise silently
stop resolving.

---

## Required reading (before acting)

| File | Read when |
|---|---|
| `references/post-format.md` | Always — the four-line format, what each line feeds, and the parse rules |
| `references/routing.md` | Always — how to read owner chips out of the Doc, and the off-by-one |
| `references/doc-write-rules.md` | Any mode that writes — marked blocks, tab targeting, idempotency |
| `references/message-templates.md` | Composing any Chat post or the recap mail |
| `references/wording.md` | **Always, before writing any zh-TW the team will read** — house voice, per `/content-translator` |
| `references/scaffold.md` | Installing or debugging the Apps Script half |
| `references/ledger.md` | `snapshot`, or anything that reads the Weekly Ledger — the layout, the commit order, how to read one week back |
| `references/proposal-rules.md` | `propose` — what may be suggested, on what evidence, and what `check` refuses |

`propose` reads `references/proposal-rules.md`, `ledger.md`, `wording.md` and the approval section of
`message-templates.md`; `apply` reads `ledger.md`. Neither touches the Doc or Chat.
`snapshot` reads only `references/ledger.md`: it touches no Doc, no Chat and no prose, so the
"Always" rows above do not apply to it. `recap` reads `references/ledger.md`, `wording.md` and the
recap section of `message-templates.md`, and nothing about the Doc or Chat.

---

## Step 0 — Anchor on today, and get the off-by-one right

Resolve today in `Asia/Taipei`. Compute:

- **Week label** — `WB 9/14`, the **Monday that opens the week**. This is what goes in every
  stamp, every Chat footer and the recap subject: it is the day the team posts, and it is a date
  a reader can place without counting. It replaced the ISO ordinal (`W38`) on 2026-09-15.
- **ISO week key** — `2026-W38`. Machine-only: the launchd state files and the receipt line's
  `week=` field. Never shown to the team. `references/wording.md` explains why both exist.
- **The window** — Monday 00:00 of the current ISO week → now.
- **The target Thursday** — the Doc names its sections by **Thursday** date (`Aug 27`,
  `Aug 20`, …), but the team reports on **Monday**.

`snapshot`, `propose` and `apply` need only the ISO week key. The runner passes it as `week=`; they have no target
Thursday and no window, so the off-by-one below does not apply to it.

> **Monday's posts belong to the Thursday that is coming, not the one that just passed.**
> This is the single easiest thing to get wrong, and it silently writes a whole week's
> updates into the previous meeting's section. Assert it: the target Thursday must be
> **≥ today**. If the newest section in the Doc is already in the past, the scaffold did not
> run — say so loudly rather than writing into a stale section.

## Step 1 — Load config and check idempotency

Load the private config; fail loud on placeholders. Then check whether this mode already ran
for this ISO week:

- Chat-delivering modes (`nudge`, `chase`, `agenda`, `decisions`) — list the space's messages
  for today and look for this skill's own marker line (each template ends with a
  `— zynkr-ops-weekly · <week>` footer). Found → stop and report "already ran".
- `rollup` — look for a `〔自動彙整 <week>` stamp inside the target Thursday section. Found →
  do not write a second block; re-run in *append-new-only* mode (Step 4.4).
- `propose` — the Ledger's `Weeks` O cell plus the recorded approval thread. `proposals.py pages`
  answers `already`, or `resume` when the rows are recorded but the mail is not.
- `apply` — the Ledger's `Weeks` Q cell. `proposals.py apply-decide` answers `already-applied`.
- `snapshot` — the Ledger's `Weeks` row for the ISO week. `ledger.py snapshot pages` answers
  `already` when that row reads `ok`, and nothing is written.
- `tidy` — idempotent by construction, so no marker is needed: once a group holds a single
  block there is nothing left to archive and `tidy_blocks.py` returns an empty `archive` list.
  A second run in the same week is a no-op, which is what makes it safe to retry.

> **Until 2026-10-06, match the old week shape too.** The label changed from `W38` to
> `WB 9/14` on 2026-09-15, so a section written before then is stamped `〔自動彙整 2026-W38`
> and a footer posted before then reads `· W38`. Search for **either**. Matching only the new
> shape makes `rollup` write a duplicate block and makes `decisions` conclude the loop never
> ran and refuse to send the recap. `references/wording.md` → "The changeover".

## Step 2 — Read routing from the Doc (every run)

Fetch the Doc **as markdown** — `get_doc_as_markdown`. This matters:
`get_doc_content` returns plain text and **silently strips person chips**, which is exactly the
data the routing depends on. In markdown a chip arrives as `[Sam Rivera](mailto:owner-a@example.com)`.

Pipe it through `scripts/parse_routing.py` to get `{heading → owner email}`. Rules, precedence
and the heading-grouping details are in `references/routing.md`.

Sanity-check the result before using it: every email must appear in `reporters` or be a known
non-reporting owner. An unexpected address means a chip changed — surface it in the report
rather than dropping the section.

## Step 3 — Read the week's posts (`rollup`, `chase`, `agenda`)

Call `get_messages` with the **`space_id` and a `createTime` window**.

> Do **not** use `search_messages` to find the posts. It is a *client-side* scan bounded by
> `max_spaces` × `page_size`; the Chat API's underlying `spaces.messages.list` supports only
> `createTime` and `thread.name` filters and has no full-text search at all. Used for
> retrieval it under-scans silently and reports "nothing found" for messages that exist.

Paginate until the window is covered. Then `scripts/parse_reports.py` turns the raw messages
into records — one per reporter — resolving the sender through `chat_ids` and splitting the
four lines. Posts without the `#週報` tag are ignored: the space is a mixed channel and carries
plenty of other traffic.

**While the format is still being adopted**, pass `--accept-untagged`. The team's pre-tag
shapes (`上禮拜進度` … `本週待辦`, `這個禮拜我的 focus`) carry no tag, so a tag-only parse
returns nothing and the first roll-up reads as total non-compliance. Each record is stamped
`format: "tagged" | "legacy"`; report how many are still legacy, and drop the flag once that
number has been zero for two weeks. An optional format is not a format.

## Step 4 — Mode bodies

### 4.1 `nudge` (Mon 09:00)

Read **last week's** Doc section and extract its decisions — from the **Doc**, not from the
recap mail that was sent. Mail is a delivery channel, never a data dependency; a failed send
should cost an archive copy, not break the chain.

Post the template from `references/message-templates.md` with those decisions quoted above it
and the Tue 09:00 cut-off stated. Reference last week's decisions so people report *against*
something.

**Then assert the scaffold fired.** Confirm a section for the *upcoming* Thursday exists. This
is the "prove it fired" check for the Apps Script half. It lives here rather than in `decisions`
because the scaffold trigger runs later on Thursday evening than `decisions` does — checking at
that moment would fail every week for the wrong reason, and a notice that cries wolf weekly is
worse than no notice. Missing → post a failure notice and stop; do **not** create the section
here, because rebuilding it loses the owner person chips, which no API can recreate.

### 4.2 `rollup` (Tue 09:00)

1. Parse the window (Step 3).
2. Resolve routing (Step 2). For each record, its owner email selects the department heading(s)
   it belongs under. One owner may hold several headings — write the block under each, or under
   the primary one if the report names a department explicitly.
3. **Backfill metrics.** Reporters fill the `數字:` line only with what they have on hand. For
   the rest, read `sources.main_tracker` / `sources.okr_kpi_tracker` and fill the Doc's metric
   slots from there. Cite the source cell for every number written. Never invent a number and
   never carry one forward from a prior week — an empty slot is information.
4. **Compute carry-over.** `scripts/carryover.py` compares this week's items to prior sections
   and emits `↻N週` counts. An item at `↻3週` or higher is agenda material by default.

   Two things it deliberately does **not** count, both learned from the real Doc:
   **template rows** — a label like `Funnel` or `CTR` that appears in most sections carries no
   work and would otherwise dominate the agenda; and **drifting matches** — the walk-back
   requires a near-exact match, because loose matching chains across unrelated items and
   invents long streaks. Digits are stripped before comparison, so `90%` → `92%` is correctly
   one item rather than two.
5. Write one marked block per department under its heading — `references/doc-write-rules.md`.
6. **Record the posts in the Weekly Ledger** (`SKB-044`), after the Doc blocks are verified, so
   Monday's recap reads a sheet instead of this Doc. `ledger.py` works out every range and value;
   make its printed calls exactly and save each result unchanged, as in 4.7.
   1. Save `parse_reports.py`'s output and the routing as files, then
      `python3 scripts/ledger.py rows reports --reports <reports.json> --routing <routing.json> --week <ISO week>`
      and save what it prints as `rows.json`.
   2. `python3 scripts/ledger.py block start --tab Reports --week <ISO week> --rows rows.json` →
      make the four printed calls.
   3. `block plan --dir <dir>` → make the `ops` calls, then the `readback` call.
   4. `block check --dir <dir>` → make its `commit` call, then its `readback` call.
   5. `block confirm --dir <dir>` → add its `delivered` to the receipt.

   **This step never decides `status`.** `chase` waits for an ok `rollup`, and a Ledger hiccup
   must not cost the team its chase. If any step exits non-zero, keep the receipt's status as the
   Doc work earned it and add `ledger-reports-failed;<reason>` to `delivered=`; Monday's recap
   then says the week's posts were not recorded, which is true. The beat is stamped done either
   way, so to fill the gap run this step again by hand (`/zynkr-ops-weekly rollup` interactively
   reaches it with the Doc blocks already present); the block is rewritten in place, so nothing
   duplicates.
7. Report: who posted, who did not, what was written where. The "did not" list is `chase`'s input.

### 4.3 `chase` (Tue 09:30)

`missing = reporters − posters`. Empty → post nothing and report full coverage; a chase message
that chases nobody teaches people to ignore chase messages.

Otherwise post one short message naming the missing people and the Wed 12:00 cut-off. Name them
in plain text — `send_message` posts text, and reliable programmatic @-mentions need the
annotation payload the MCP tool does not currently expose.

> If `chase` names the same person two weeks running, the problem is the format or the routing,
> not the person. Say that in the report.

### 4.4 `agenda` (Wed 17:00)

1. **Re-sweep the window first** (Mon 00:00 → now) to pick up anything that arrived after the
   chase. Append only records not already stamped in the Doc — match on reporter + ISO week so
   a re-run cannot duplicate.
2. Assemble, in this order, and cap it: **carry-over `↻N週`** · **overdue** (from the tracker)
   · **KPI off-target** · **≤3 decisions**. The decisions come from the reporters' `卡關:` line —
   that is the only field in the format that forces a decision, which is why it cannot be
   dropped.
3. Write the agenda at the **top of the target Thursday section**, in its own marked block.
4. Post a short pointer to the space with the Doc link — the agenda itself lives in the Doc.

If there are more than three candidate decisions, choose the three with the largest blast
radius and list the rest under a "not this week" line. An agenda that lists everything makes no
decisions.

### 4.5 `decisions` (Thu 22:00)

Runs **after** the meeting, against the section as the humans edited it live.

The hour is not arbitrary and is the one beat that must be re-timed if the meeting moves. It sits
in the gap between the meeting ending and the 23:00 scaffold: fire it *during* the meeting and it
recaps a section nobody has edited yet — and it does not merely write to the Doc, it mails every
owner-chip address, so a premature run is a wrong email to the whole team, not a stale line.

**Precondition — refuse to recap a week the loop never ran.** Before anything else, look for this
week's `〔自動彙整 W<week>` stamp in the target section. Missing → `rollup` never ran, so nothing in
that section has been through the loop and the meeting had nothing to work from. Post a one-line
notice to the space, send **no mail**, and stop. This is what makes the five triggers safe to
install on any day of the week: a mid-week install, a public holiday or a failed Tuesday can no
longer put a recap of a week that never happened in front of the whole team.

1. Extract resolutions: **decision · owner · date**. A resolution missing an owner or a date is
   not a resolution — list it as still open rather than promoting it.
1b. **Record them in the Weekly Ledger** (`SKB-044`), before posting or mailing anything, so the
   record exists even in a week this beat ends up holding its mail. Monday's recap reads it.
   1. Save the resolutions, open ones included, as a JSON list of
      `{"content", "owner", "due", "item"}` (`item` = the tracker `#` it concerns, or empty), then
      `python3 scripts/ledger.py rows decisions --input <file> --week <ISO week> --meeting <this Thursday, YYYY-MM-DD> --source <link to this week's Doc section>`
      and save what it prints as `rows.json`. No resolutions at all → save `[]`: zero decisions is
      a fact worth recording, not a missing record.
   2. `block start --tab Decisions --week <ISO week> --rows rows.json`, then `block plan`, `block
      check` and `block confirm`, making every printed call exactly, as in `rollup` step 6.

   Like `rollup` step 6, **this step never decides `status`**: a failure adds
   `ledger-decisions-failed;<reason>` to `delivered=` and the beat carries on.
1c. **No resolutions is a result, not a failure** (`SKB-044`). When step 1 finds no resolution with
   an owner and a date, still run step 1b (it records the open items, or `[]` when there are
   none), then post the **one-line** no-decisions message (`references/message-templates.md`)
   instead of step 2's three lines, and skip steps 3 and 4: no mail goes out, because nothing was
   decided and Monday's recap carries the overdue items. Receipt `status=ok delivered=no-decisions;chat-verified` plus whatever step 1b added.
   Never hold the post, never report `failed` and never wait for the Doc to fill in later: this
   beat already runs after the meeting. On 2026-10-01 a run held everything and gave up after three
   attempts, so the team heard nothing that week.
2. `send_message` — three lines to the space. Short, because next Monday's `nudge` quotes it.
3. `send_gmail_message` — the full recap to **the owner-chip emails read in Step 2**, not to a
   list maintained here. Contents: decisions · owner · date / overdue and carry-over / KPI
   off-target / next week's focus per department / a link back to this week's Doc section.

   **Search `in:sent` for this week's subject BEFORE composing, and skip the send if it is
   already there.** A non-ok run is now retried up to three times inside its window, so this
   step can legitimately be reached more than once in one evening. Step 1's idempotency check
   guards the Chat post, not the mail, and this mail goes to the whole team: the one failure
   this loop must never produce is three copies of the same recap in six inboxes.
4. **Assert it fired.** Immediately search `in:sent` for the subject just used, within the last
   few minutes. Not found → post a one-line failure notice to the space and say so in the
   report. This is the SDD "prove it fired" rule, and it is here for a concrete reason: two
   consecutive weekly sends once failed unnoticed because nothing checked. A dead token must
   surface within a week, not five.
5. The Weekly Ledger's `Decisions` tab (step 1b) is the decisions register. The older plan of a
   register sheet (`sources.decisions_register`) was never configured, so nothing else is written.
6. **Do not check the scaffold here.** Apps Script fires within an *hour window*, and the
   scaffold trigger runs later on Thursday evening than this mode does — so at this point next
   week's section legitimately does not exist yet. Asserting it here produces a weekly false
   alarm, which trains everyone to ignore the notice that matters. The check lives in `nudge`
   (Step 4.1), which runs Monday: clear of the window, and a day before `rollup` needs it.

### 4.6 `tidy` (Fri 09:00)

Runs the morning after the scaffold. Its whole job is to undo the one thing the scaffold does
badly: it copies the week section forward **verbatim**. The auto blocks travel with it and
`rollup` only ever prepends. By 2026-09-15 a single section carried **22 blocks in 7 groups**,
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
   scaffold, three days before `rollup` needs the section.
2. Fetch the Doc as markdown and run `scripts/tidy_blocks.py`. It returns, per department
   group: the block to `keep`, the blocks to `archive`, and the still-open items to `carry`.
   It writes nothing and makes every judgement call — do not re-derive its decisions by hand.
3. **Copy the archived blocks to the 封存 tab first, and verify they landed.** Append under a
   `<section label>` heading so the trail stays readable. Only then delete. Copy → assert →
   delete, never the other order.
4. **Delete the archived blocks from the live tab, by descending index.** Use
   `inspect_doc_structure(tab_id, detailed=true)` to map each block line to its range, sort
   descending, and `batch_update_doc` with `tab_id` on **every** operation. The index rules and
   the tab trap are in `references/doc-write-rules.md`; they are not optional here.
5. **Write the carried items into the kept block**, one item per line, under a `· 還沒收掉的 —`
   line, each as `· <item>〔<since> 起〕`. They go *inside* the kept block because auto-content may
   only live inside a stamped block — that is what keeps the guardrail true. `carry` includes the
   items already on an archived block's own `還沒收掉的` list, with their **original** `since` week
   — before `SKB-039` those were dropped one Friday after being rescued — and items an archived
   block's `上週` reported still open (`進行中`/`卡住`/…) that its `本週` did not plan again. If the
   kept block already has a `· 還沒收掉的 —` line, append under it; never write a second one.
6. Re-read the section and confirm: one stamp per group, the human lines below each block
   untouched, and the archived text present in the 封存 tab.
7. **Remove closed human bullets** (`SKB-039`). A bullet whose status chip reads `Done` or `Drop`
   is deleted from this new section — the week it was closed in keeps it. **You never choose a
   line or an index yourself; `tidy_blocks.py` does, and every step below is a gate.**
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

   The script only returns a bullet that sits, with its whole subtree, verbatim in the previous
   week's section under the same heading — the same safety argument as the block delete, enforced
   rather than assumed. An item closed on Friday morning in the new section is left for next week.
   **Residual risk:** `batch_update_doc` has no revision guard. An edit landing between the 7.2
   fetch and the 7.3 delete — keep it short, it is the whole reason 7.3 follows at once — is not
   seen before the delete. The post-check then catches any damage to lines that REMAIN, but not a
   change to a line that was deleted (say `Done` flipped back to `In Progress` in that window);
   that line survives only in the previous section.

The archive tab is belt-and-braces, not load-bearing — the originals are already in the prior
section. If the copy fails, **stop before deleting** and report; a failed archive is a delayed
tidy, a failed delete after a successful archive is a duplicated section. Step 7 runs last and
on its own: if it fails, the block tidy has still landed, so report `partial`, not `failed`.

### 4.7 `snapshot` (Fri 18:00, catching up through Sun 23:00)

Copies every item of the Main Tracker's `H2 專案項目` tab into the machine-owned Weekly Ledger,
once per ISO week (`SKB-044`). It reads the tracker and writes **only the Ledger**: it posts
nothing, mails nothing and never opens the Doc, so skip Steps 2 and 3. Monday's recap compares
two of these snapshots to say what changed. Read `references/ledger.md` first.

**`scripts/ledger.py` works out every range, row and value; you only make the calls it prints.**
Each printed call is `{"tool", "args", "save"}`: call `tool` with `args` copied exactly, then save
the tool's whole result, unchanged, to the `save` path with the Write tool. Never retype, trim,
reformat or summarise a result. The next step parses it and refuses anything that does not
match, and that refusal is the point: a copied cell that drifted is how `1.10` becomes `1.1`.

1. **The week.** Use the `week=` argument the runner passes (`week=2026-W40`). Without one (an
   interactive backfill), run `python3 scripts/ledger.py week` and use its `week`. Never work it
   out again later in the run. If a `config=<path>` argument is present, add `--config <path>` to
   the `start` command below.
2. `python3 scripts/ledger.py snapshot start --week <W>` → make the five printed calls, save each
   result, and keep the printed `dir`.
3. `python3 scripts/ledger.py snapshot pages --dir <dir>`.
   - `"already": true` → the week is done. Receipt `status=ok` with the `delivered` it prints, and
     write nothing.
   - Otherwise make the printed tracker reads and save each one.
4. `python3 scripts/ledger.py snapshot plan --dir <dir>`. A non-zero exit means stop: nothing has
   been written, so the receipt is `status=failed` with the reason it printed. Otherwise make the
   `ops` calls in order, exactly as printed (RAW writes into the Ledger), then make every
   `readback` and `recheck` call and save each result.
5. `python3 scripts/ledger.py snapshot check --dir <dir>`.
   - Exit 0 → make the printed `commit` call, then its `readback` call, and save that result.
   - Exit 6 saying the tracker changed during the run → start again from step 2, **once**. A
     second exit 6 is `status=failed`.
   - Any other non-zero exit → `status=failed`. Do not make the commit call.
6. `python3 scripts/ledger.py snapshot confirm --dir <dir>` → receipt `status=ok` with the
   `delivered` it prints. A non-zero exit here is `status=partial`,
   `delivered=block-written;weeks-row-not-confirmed`.

**Rules for this mode.** Never compute a range, row number or value yourself. Never use
`USER_ENTERED`. Never write to the Main Tracker: no printed call does. Write the `Weeks` row only
through the call `check` printed. It is what marks the week done, so it is always the last write.

### 4.8 `status` (on demand)

Read-only. Print what the loop currently sees: target Thursday, who has posted, what is
already stamped in the Doc, which triggers ran this week. Writes nothing — use it to debug
before reaching for a mode that writes.

### 4.9 `recap` (Mon 09:00, before `nudge`)

The week's team recap, by mail, about **the ISO week that just ended** (`SKB-044` decision D2:
the recap moved from Thursday night to Monday morning). It reads only the Weekly Ledger, plus
zynkr-gm's state rules, never the Doc, so it does not inherit the Doc's multi-hour reads. It
writes nothing: no Ledger cell, no tracker cell, no Chat post.

`scripts/recap.py` works out every range, fact and the subject; you make its printed calls exactly,
save each result unchanged, and write the TL;DR. Skip Steps 2 and 3.

1. **The week.** Use the `week=` argument the runner passes; that is the current week, and
   `recap.py` works out the one before it. If a `config=<path>` argument is present, add
   `--config <path>` to `start`.
2. `python3 scripts/recap.py start --runner-week <W>` → make the two printed calls; keep the `dir`.
3. `python3 scripts/recap.py blocks --dir <dir>`.
   - `"notice": true` → last week never closed out (no committed snapshot). Run
     `recap.py notice --dir <dir>` and send that mail (to the owner only) through steps 7–9.
     Receipt `status=ok`, `delivered=notice-sent`.
   - Otherwise make the printed block reads and save each one.
4. `python3 scripts/recap.py build --dir <dir> --today <today, YYYY-MM-DD>` → it prints the counts
   and the path of `facts.json`. A non-zero exit means stop with `status=failed` and the reason;
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

**Who receives it** is `routine.recap_audience`, decided by the owner, never by this run: `owner`
sends it to the account alone, `team` to every address in `reporters` — from the Monday
`routine.recap_team_from` names when it is set. `render` works this out and prints `to`; send to
exactly that.

### 4.10 `propose` (Fri 10:00, after `tidy`)

Suggests this week's changes to the Main Tracker and mails them to the owner for sign-off
(`SKB-044` Phase 3). It reads the tracker and this week's `Decisions` and `Reports` blocks in the
Ledger — never the Doc — and writes **only the Ledger** and **one mail to the owner**. It never
writes the tracker: that is `apply`'s job, after the owner has said yes. Skip Steps 2 and 3. Read
`references/proposal-rules.md` before writing a single proposal.

`scripts/proposals.py` works out every range and checks every proposal; make its printed calls
exactly and save each result unchanged, as in 4.7.

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
   the run folder, one object per suggested change: `{"#", "欄位", "建議值", "原因", "證據", "信心"}`.
   `證據` lists the `ref`s the change rests on. Nothing to suggest is a fine answer: save `[]`.
6. `python3 scripts/proposals.py check --dir <dir> --input <dir>/proposals.json`. A refusal names
   the proposal and the rule: fix that proposal or drop it, and run `check` again. Exit 5 means
   the mail would be too long to read back (the thread `apply` reads quotes it whole): drop the
   weakest proposals. It writes `rows.json` (`rows_path`), and when there are rows, the mail.
   Then record the rows: `python3 scripts/ledger.py block start --tab Proposals --week <W> --rows
   <rows_path>`, `block plan`, `block check`, `block confirm`, making every printed call exactly,
   as in `rollup` step 6. Pass the file `check` wrote; never retype rows. **The Ledger record
   comes before the mail, always.** No rows → receipt `status=ok`, `delivered=no-proposals` once
   `confirm` passes; nothing is mailed.
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
send the mail to anyone but `mail.to`, never send it before `block confirm` has passed, and never
send it twice: only `sent` says when to send. **Any refusal from `proposals.py` is a
`status=failed` receipt with its reason**, and you write nothing to fix it: never a Ledger block of
your own, never a file in the state folder (`approval.json` and its neighbours are the script's,
and a refusal that names one is addressed to the owner).

### 4.11 `apply` (Fri 18:00 → Sun 23:00, after `snapshot`)

Reads the owner's reply to this week's 【待核准】 mail and records each decision. **Phase 3a runs in
shadow mode** (`routine.apply_mode` is `shadow` unless it says exactly `live`): it writes the
decisions into the Ledger and writes nothing to the Main Tracker. The live write is Phase 3b;
until it ships, `apply-start` and `apply-decide` refuse `live`. Skip Steps 2 and 3. It needs no
stamp from `propose`: it reads this week's `Weeks` row itself.

1. **The week**, as in 4.10.
2. `python3 scripts/proposals.py apply-start --week <W>` → make the printed calls exactly (the
   thread fetch carries `include_analysis`, which is how drafts are seen), save each result, keep
   the `dir`. When it printed a Gmail search instead of a thread fetch (no thread was recorded),
   run `python3 scripts/proposals.py apply-thread --dir <dir>` and make the fetch it prints;
   `"found": false` → go on to step 3, which reports the missing mail.
3. `python3 scripts/proposals.py apply-decide --dir <dir>`, then by its `status`:
   Every `write` below is the same block write: `python3 scripts/ledger.py block start --tab <tab>
   --week <W> --rows <rows_path>`, then `block plan`, `block check` and `block confirm`, making
   every printed call exactly. Pass the file `apply-decide` wrote; never retype rows.
   - `waiting` → no decision yet: `no-reply-yet`, `draft-open` (a reply draft is open in the
     thread), `asked-to-restate`, or `reply-unreadable`. A `send` call comes with
     `reply-unreadable` (asking the owner to restate) and with `draft-open;noted` (telling the owner
     a draft is holding things up): make it exactly once, and when it went through, run
     `python3 scripts/proposals.py apply-sent --dir <dir>` so the next look does not send it again.
     Receipt `status=waiting` with its `delivered`, adding `;sent` when the send went through. The
     runner looks again in two hours, and from Sunday 21:00 on every tick.
   - `failed` → `approval-mail-not-found`, `approval-mail-differs;…` (the mail in the thread is not
     the mail that was sent), `proposals-changed;…` (the Proposals block was edited after the
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
     was recorded. That message is what makes the week's decision final. When it went through,
     write its `write` (the `Updates` block, which marks the week applied in `Weeks`), then receipt
     `status=ok`, its `delivered` plus `;confirmed`. If the send fails, write nothing more and
     receipt `status=partial` with the reason: the week stays unapplied and the next look decides
     and confirms again.
   - Any refusal (a non-zero exit) → receipt `status=failed` with its reason. Write nothing to fix
     it: never a Ledger block of your own, never a file in the state folder.

**Rules for this mode.** The owner's newest reply that says anything beyond thanks decides, until
the confirmation is in the thread; after it, replies change nothing. `Weeks` Q (applied) is written
only after the confirmation, so a decision in the `Proposals` block without it is provisional and
nothing reads it as applied. A row the reply does not name stays 未回覆 and is not applied. A reply
that is unreadable, asks a question, or approves anything while saying more than thanks decides
nothing and gets one restate request. Never write the Main Tracker in shadow mode, and never send
anything except the `send` call `apply-decide` printed.

## Step 5 — Report, and receipt the run

Every run ends with a compact report: mode, ISO week, target Thursday, records parsed, who is
missing, what was written where, what was delivered, and — for `decisions` — the send
assertion result. If a step was skipped, say which and why.

**Then end the report with a receipt line, on its own line, exactly in this shape:**

```
ZYNKR-OPS-WEEKLY-RESULT: mode=<mode> week=<ISO week> status=ok|partial|failed delivered=<short>
```

`week=` here stays the **ISO key** (`2026-W38`), not the `WB 9/14` label the team reads. This
line is machine-facing, it needs to be year-qualified and sortable, and it sits next to the
`<week>.<mode>.done` state files that use the same key. See `references/wording.md`.

`status=ok` means **every** side effect this mode owes actually landed and you verified it —
the message is in the space, the block is in the Doc, the mail is in `in:sent`, the Ledger's
`Weeks` row reads back `ok`. Anything
short of that is `partial` (some landed) or `failed` (none did), with the reason in
`delivered=`. Examples:

```
ZYNKR-OPS-WEEKLY-RESULT: mode=rollup week=2026-W36 status=ok delivered=6-blocks-verified
ZYNKR-OPS-WEEKLY-RESULT: mode=agenda week=2026-W36 status=partial delivered=doc-written;chat-404-app-not-configured
ZYNKR-OPS-WEEKLY-RESULT: mode=nudge week=2026-W36 status=failed delivered=none;mcp-timeout
ZYNKR-OPS-WEEKLY-RESULT: mode=tidy week=2026-W41 status=ok delivered=9-archived;8-kept;38-carried;3-closed
ZYNKR-OPS-WEEKLY-RESULT: mode=tidy week=2026-W38 status=failed delivered=none;scaffold-did-not-fire
ZYNKR-OPS-WEEKLY-RESULT: mode=decisions week=2026-W41 status=ok delivered=no-decisions;chat-verified;0-rows;Decisions(none);Weeks!M3
ZYNKR-OPS-WEEKLY-RESULT: mode=snapshot week=2026-W40 status=ok delivered=55-items;Snapshot!A2:P56;Weeks!A2
ZYNKR-OPS-WEEKLY-RESULT: mode=snapshot week=2026-W40 status=ok delivered=already-snapshotted;Weeks!A2
ZYNKR-OPS-WEEKLY-RESULT: mode=snapshot week=2026-W41 status=failed delivered=none;tracker-changed-during-run
ZYNKR-OPS-WEEKLY-RESULT: mode=recap week=2026-W42 status=ok delivered=recap-sent-to-6
ZYNKR-OPS-WEEKLY-RESULT: mode=recap week=2026-W42 status=ok delivered=already-sent
ZYNKR-OPS-WEEKLY-RESULT: mode=recap week=2026-W42 status=ok delivered=notice-sent
```

`apply` alone may receipt `status=waiting` (no decision yet): it stamps nothing, clears the attempt
count, and the runner looks again two hours later.

```
ZYNKR-OPS-WEEKLY-RESULT: mode=propose week=2026-W42 status=ok delivered=approval-mail;5-rows;thread-1a2b3c
ZYNKR-OPS-WEEKLY-RESULT: mode=propose week=2026-W42 status=ok delivered=no-proposals
ZYNKR-OPS-WEEKLY-RESULT: mode=apply week=2026-W42 status=waiting delivered=no-reply-yet
ZYNKR-OPS-WEEKLY-RESULT: mode=apply week=2026-W42 status=waiting delivered=reply-unreadable;sent
ZYNKR-OPS-WEEKLY-RESULT: mode=apply week=2026-W42 status=ok delivered=shadow;4-approved;1-rejected;0-pending;confirmed
ZYNKR-OPS-WEEKLY-RESULT: mode=apply week=2026-W42 status=partial delivered=shadow;4-approved;1-rejected;0-pending;confirm-send-failed
```

For `snapshot`, `recap`, `propose` and `apply` the runner also checks that the receipt names the week it passed, so a backfill of
another week can never mark this one done.

This line is not decoration and it is not for humans. `run_ops_weekly.sh` parses it and stamps
the week done **only** on `status=ok`; anything else retries on the next tick inside the window
and gives up after three attempts. **Never write `status=ok` because the run finished — write it
because you checked.** The scheduler has no other way to tell a delivered beat from a beat that
politely explained why it could not run: `claude -p` exits 0 either way. It waved through a
silent Monday and a half-failed Wednesday in W36 before this line existed.

---

## Guardrails

- **Never edit a human's line.** Auto-content lives only inside `〔自動彙整 …〕` blocks. Promotion
  or deletion of that content is a human act, at Thursday's meeting. **One exception, `tidy` step 7
  only:** a bullet whose status chip reads `Done`/`Drop` is removed from the newest section, and
  only a range `tidy_blocks.py --closed` returned, re-confirmed with `--expect` on fresh reads and
  verified with `--postcheck` after. A heading is never in such a range.
- **Never rebuild the Doc's skeleton.** Person chips cannot be created by Apps Script or the
  Docs REST API — only copied. Rebuilding loses the routing table. Copy, or do nothing.
- **Never write to a past section.** If the target Thursday is behind today, stop and report.
- **Never invent a metric.** Cite the cell, or leave the slot empty.
- **Never treat mail as an input** — with one designed exception: `apply` reads the owner's reply
  to this week's 【待核准】 mail, in the recorded thread, through `proposals.py`, and answers only in
  that thread (one restate request, one confirmation). Everything else reads state from the Doc,
  the tracker and the Ledger.
- **Fail loud on config.** Placeholder id → stop; a wrong id writes into someone else's file.
- **Never write the Main Tracker.** No mode writes it in Phase 3a. `snapshot` and `propose` read it
  and write only the Ledger, through the calls the scripts print; `apply` in shadow mode records the
  owner's decisions in the Ledger only. The live write is Phase 3b. Since 2026-10-04 a hook
  (`scripts/tracker_guard.py`, see `references/scheduling.md`) refuses any tracker write from every
  beat but `apply`.
- **Nothing is proposed without evidence, and nothing is applied without a reply.** Every proposal
  passes `proposals.py check`; a row the owner's reply does not name stays 未回覆.
- **The recap writes nothing and mails once.** It reads the Ledger, sends one mail to the
  audience the config names, and never adds a recipient or writes a cell.
- **A week is snapshotted only when its `Weeks` row reads `ok`.** Rows in `Snapshot` without that
  row are an unfinished run, and the next run rewrites them.
- **Write like a colleague, not a report generator.** Every published line is zh-TW that six
  people read in a chat room. No 官腔 (`徵集`/`產出`/`決議候選`), no half-translated lines
  (`KPI off-target`, `carry-over`, `Not started`), no internal mode names (`rollup`, `骨架`)
  and no parenthetical explanations of your own filtering. `references/wording.md` carries
  the rules and the frozen strings; it applies to the free text you compose at run time,
  not just to the templates.

## Limitations

- `send_message` posts plain text; @-mentions render as names, not live mentions.
- Metric backfill only covers metrics that exist in the configured sheets; anything measured
  outside them stays a human line.
- The Apps Script half must be installed once by hand, and `installTriggers()` must actually be
  *run* — pasting the file does not schedule anything. See `references/scaffold.md`.
- **`tidy` bounds the newest section, not the whole Doc.** The 46 older sections keep whatever
  they accumulated before 2026-09-15 — they are frozen, so they no longer grow, but nothing
  shrinks them either. The Doc still grows by one (now lean) section a week. Trimming the
  historical backlog is a human cut-and-paste, and `SKB-029` is why it is not automated.
- **`tidy`'s carried list is only as good as the status words people write.** It reads
  `完成`/`Done` as closed and everything else as open. An item finished but never marked stays
  on the list; that is deliberate — the alternative is silently dropping live work. An item
  leaves the list when its owner reports it `完成` on a later `· 上週` line, or someone deletes it.
- **Closed-bullet removal needs the status chip.** A human bullet leaves the new week only when
  its chip (or a trailing typed word) reads `Done`/`Drop`/`完成`/`放棄`/`取消`. A finished item
  still marked `In Progress` stays, and so does a `Done` item with an open sub-item under it.
- The skill half runs on **launchd**, not a claude.ai cloud routine: there is no Google Chat
  connector, the cloud sandbox cannot read the private config, and the Drive connector cannot do
  the chip-preserving Doc writes. See `references/scheduling.md`.
- **Not built yet: writing the tracker's 狀態 column.** No skill writes it today
  (`planning-tracker-sync` never writes the Main Tracker either). `SKB-044` Phase 3 adds a
  propose → approve → apply loop as its only writer. Auto-promotion of an auto-summary line into
  a human line is deliberately not built.
- **`snapshot` stores person chips as display names.** A renamed Google profile looks like an
  owner change in the diff.
- **The Ledger's grid is grown by hand.** `ledger.py` warns when fewer than eight weeks of rows
  remain and refuses a week that does not fit; `references/ledger.md` says how to grow it.
- **A copy mistake made identically in both tracker reads cannot be caught.** Every other
  mismatch fails the check before anything is committed.

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
