---
name: consult-shadowing-scheduler
sheetId: "2.13"
description: >-
  Book a consulting deal's shadowing session in one pass: read the CRM deal, find
  the client's [N] Drive project folder from the deal notes, read the user's own
  calendar for free time, propose 3–5 candidate slots, and on the user's confirm lay
  down the whole kit — a calendar hold, a "Shadowing — YYYY-MM-DD" subfolder inside
  the project folder, a client logistics Gmail DRAFT (never sent), a CRM follow-up
  task, and a deal-notes backlink. Trigger EAGERLY on /consult-shadowing-scheduler
  or whenever the user says "排 shadowing 時間", "約跟拍", "安排現場觀察", "幫我跟
  <client> 約 shadowing", "schedule the shadowing", "book the shadowing session",
  "find time to shadow the client", or otherwise wants an on-site observation
  session scheduled for a consulting engagement — even if they only name the
  company. It reuses the folder project-init opened (at qualified) and the deal
  Sales created; it never creates either. consult-brd-writer takes the transcript
  after the session; this skill only books the session and preps the client.
category: sales-consultant
project: consult-shadowing-scheduler
platform: claude
status: Done
visibility: public
author: Peter Tu
input: "A CRM deal (URL or company name), optionally a preferred date window and session duration"
process: "get_deal → resolve the client's [N] Drive folder from deal notes (else one name match) → read the user's own calendar → slot-confirm gate → create the calendar hold + shadowing subfolder + logistics Gmail draft + CRM task → backlink + report"
output: "A confirmed calendar hold, a shadowing subfolder in the client's project folder, a client-ready logistics mail draft (never auto-sent), and a CRM task — all linked on the deal"
synergy:
  - "sales-inbound"
  - "project-init"
  - "consult-brd-writer"
house-style: bound

---

# Consult Shadowing Scheduler

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill consult-shadowing-scheduler
```

After a consulting deal is qualified, the next step is a **shadowing session**
— the consultant sits with the client's team and watches the real workflow
run. Booking it is pure admin friction. This skill collapses it into one pass:
read the deal, find the client's existing `[N]` project folder, propose free
slots from the user's own calendar, then — on their pick — create the calendar
hold, the dated subfolder, the client logistics mail **as a Gmail draft (hard
rule: never sent)**, and the CRM task, backlinking everything onto the deal.
**The user** is whoever runs the skill and will do the shadowing: the slots
come from their calendar, and the hold, the draft and the task are theirs. To
book a colleague's session, the colleague runs it.

It is deliberately **gated, not autonomous**: nothing is created until the
user confirms a slot — a wrong-day hold, or an invite accidentally mailed to the
client, is worse than one follow-up question. Re-runs update, never duplicate.

## How this differs from its neighbours

- **project-init** — it opens the numbered `[N]` folder once the deal is
  qualified (the deal itself comes from Sales). This skill assumes both exist and
  only adds a subfolder + activity to them. If there is no 專案資料夾 link and no
  single folder matches the company, it STOPs and points at /project-init.
- **consult-brd-writer** — consumes the shadowing transcript AFTER the session;
  this skill runs before, and its subfolder is where that transcript lands.

## Fixed facts (don't re-derive these)

- **Google account** for all Gmail/Drive tools: `<your-google-workspace-account>`
- **Calendar** — the claude.ai Google Calendar connector
  (`mcp__claude_ai_Google_Calendar__*`) on calendar `<your-google-workspace-account>`;
  the Google Workspace connector's calendar tools (`query_freebusy`, `manage_event`,
`get_events`) work only where its Calendar API is enabled, which it isn't on the owner's Google Cloud project.
- **Drive parent folder** (`[2.2] 業務與顧問部門：專案`, home of the numbered `[N]` folders): `1hkXPX7OXPFOU0BcloPbJSFp8O0zArM8t` — orientation only; this skill never creates anything directly in it
- **CRM deal URL** for the report/backlink: `https://platform.zynkr.ai/deals/{deal_id}`
- Ownership needs no lookup and no hardcoded id: every `mcp__zynkr__*` write is made as the user, on their own workspace, and defaults the owner to them.

## Scheduling defaults (the user overrides any of these by saying so)

**The client's day** 09:30–17:30 `Asia/Taipei` · **the user's day** the same, unless they work from another time zone (step 3) · **slot-search window** next 10 business days · **session duration** 2 hours.

---

## Workflow

### 1 · Resolve the deal

The user hands over a deal URL or a company name.

- Deal URL → `mcp__zynkr__get_deal(id="<deal uuid>")`
- Company name → `mcp__zynkr__list_deals(search="<company>")`, then `get_deal`
  on the match. More than one match → confirm with the user before acting.

`get_deal` returns `notes`, `contact_id` and `company_id`. The contact name and
email come from `mcp__zynkr__get_contact(id=…)`, the company name from
`mcp__zynkr__get_company(id=…)` — the two follow-up reads that replace what the
old join returned in one row.

Capture the **contact name + email**, and scan `notes` for the 專案資料夾 line
that project-init appended
(`專案資料夾：https://drive.google.com/drive/folders/<folder_id>`). Extract the
folder id — that `[N]` folder anchors everything this skill creates.

**No 專案資料夾 line → match the folder by name, once.** List the projects parent
(`mcp__google-workspace__list_drive_items(user_google_email="<your-google-workspace-account>", folder_id="1hkXPX7OXPFOU0BcloPbJSFp8O0zArM8t")`)
and look for a `[N] <Company>（…）` folder whose company part matches the deal's
company name, ignoring case, spaces and punctuation.

- **Exactly one match** → use it, and tell the user the deal is missing its backlink
  (`/project-init` writes it: `專案資料夾：<folder url>` on its own line).
- **None, or more than one** → **STOP.** Tell the user the deal has no project folder
  yet and point at `/project-init` (it opens one once the deal is qualified). Never
  invent a folder here.

### 2 · Collect constraints

Settle: date window · duration · on-site (現場) vs remote (遠端) — the last
one drives the mail's `{{MODE}}`/`{{LOCATION_OR_LINK}}`. Ask only for what's
missing; apply the defaults for the rest and **say which defaults applied**
(e.g. "用預設：客戶與你都是台北時間 09:30–17:30（你不在台灣請告訴我）、未來 10 個工作天、2 小時").

### 3 · The user's free time → 3–5 candidate slots

Slots come from the user's own availability: any free stretch of their working
time in the window can be offered. Unlike `/sales-outbound`, which offers only
events titled `Available`, this skill needs no such blocks.

**Business days** are Monday to Friday minus Taiwan's public holidays, which a
calendar shows only if it subscribes to them. Read them from Google's public
holiday calendar; no subscription is needed:

```
mcp__claude_ai_Google_Calendar__list_events(
  calendarId = "zh-tw.taiwan#holiday@group.v.calendar.google.com",
  startTime = "<window start>", timeZone = "Asia/Taipei",
  endTime = "<window end>"  # the default window: start + 4 weeks, which holds 10 business days even over Lunar New Year
)
```

A weekday is a day off when any of its events has a description starting with
`國定假日` (補假 days included). An observance (`假日節慶`), such as 重陽節, never
makes a day off on its own. For the default window, count 10 business days
after skipping. At the gate, name the days skipped and every weekday
observance kept:

「略過國定假日：10/9 國慶日補假 · 未略過的節慶：9/28 教師節，若放假請告訴我」

Google's list can lag, and a day off it calls an observance shows up only in
the second list.

Then read the user's own calendar:

```
mcp__claude_ai_Google_Calendar__list_events(
  calendarId = "<your-google-workspace-account>",
  startTime = "<window start, ISO 8601 +08:00>", endTime = "<window end>",
  timeZone = "Asia/Taipei", orderBy = "startTime", pageSize = 250
)
```

Every event is busy except one marked free (`transparency: transparent` or
`availability: AVAILABILITY_FREE`), one the user declined, and one titled
`Available`: some people mark the time they offer that way (`Not available`
stays busy). Compare instants, not clock times: an event's own time zone may be
Europe/Amsterdam, and its `dateTime` carries the offset. Pass the response's
`nextPageToken` back as `pageToken` until the window is covered.

**The user's own day.** If any event the user organized (`organizer.self`)
carries another `start.timeZone`, they may work from there. Unless they have
already said, ask before offering anything: which hours they work in that
zone, and which days in the window they'll be in Taiwan. On a day in Taiwan
their day is the client's day, and a 現場 session can only go on such a day.
Otherwise a 遠端 slot has to fit both days: someone working 08:00–17:00 in
Amsterdam meets the client's Taipei day from 14:00 Taipei time (15:00 once
Europe leaves summer time). If the two days overlap by less than the session,
say so and ask for a shorter session or a day in Taiwan.

Derive **3–5 candidate slots** that fit ALL of: inside the client's working
hours and the user's own, on business days · full duration, zero overlap with
busy blocks · **no same-day adjacency to long meetings** (a day carrying a ≥2h
meeting gets no slot butted against it — shadowing is draining) · spread across
days, not stacked on one.

### 4 · GATE — confirm the slot (nothing is created before this)

Present the candidates as a table and stop:

```
建議時段（Asia/Taipei · 2 小時）：
| # | 日期 | 時間 | 備註 |
|---|------|------|------|
| 1 | 2026-08-12（週三） | 10:00–12:00 | 全天無其他長會議 |
| 2 | 2026-08-13（週四） | 14:00–16:00 | 上午空、下午僅此段 |
| 3 | 2026-08-17（週一） | 09:30–11:30 | 新週開場，前後乾淨 |

選一個，或直接給我你要的時段。
另外：要把客戶（王小明 <jane@example.com>）加進行事曆邀請嗎？
（加入 = Google 會「立刻」寄邀請信給對方）— 預設：否
```

When the user works from another time zone, add a column with each slot in
their own time, as `/sales-outbound` does.

The user picks a number **or gives a slot of their own** (theirs wins, even
outside the defaults). The **same gate** settles the attendee question: an
external attendee is emailed the moment the event is created, so the default is
**NO** — the client hears about the time via the reviewed draft. Explicit yes
opts in.

### 5 · Create the kit (in this order)

**a) Calendar hold** — via `mcp__claude_ai_Google_Calendar__create_event`:

```
mcp__claude_ai_Google_Calendar__create_event(
  calendarId  = "<your-google-workspace-account>",
  summary     = "[Shadowing] {{COMPANY}} — 現場跟拍",
  startTime   = "2026-08-12T10:00:00+08:00", endTime = "2026-08-12T12:00:00+08:00",
  timeZone    = "Asia/Taipei",   # overrides the offsets above: use the zone the slot was given in
  description = "Deal: https://platform.zynkr.ai/deals/{deal_id}\n專案資料夾: <folder url>",
  attendees   = [],  # the client ONLY if opted in at the gate: [{"email": "<contact email>"}]
  addGoogleMeetUrl = <true for 遠端, false for 現場>
)
```

Capture the event link (`htmlLink`). A remote session gets its Meet link from
`addGoogleMeetUrl`.

**b) Shadowing subfolder** — inside the `[N]` folder, named
**`Shadowing — YYYY-MM-DD`**. Check for an existing one first (idempotency):

```
mcp__google-workspace__list_drive_items(user_google_email="<your-google-workspace-account>", folder_id="<[N] folder id>")
## no "Shadowing — 2026-08-12" folder yet →
mcp__google-workspace__create_drive_file(
  user_google_email = "<your-google-workspace-account>",
  file_name = "Shadowing — 2026-08-12", folder_id = "<[N] folder id>",
  mime_type = "application/vnd.google-apps.folder", content = " "
)
```

This subfolder is where the session's **recording and transcript later land** —
consult-brd-writer's input home downstream. Note its URL.

**c) Logistics Gmail DRAFT** — read `./references/shadowing-mail-template.md`,
fill the placeholders from the deal + confirmed slot (zh-TW primary; EN
variant only if the deal correspondence is in English), then:

```
mcp__google-workspace__draft_gmail_message(
  user_google_email = "<your-google-workspace-account>",
  to      = "<contact email from the deal>",
  subject = "【Zynkr 顧問】{{COMPANY}} 現場跟拍（Shadowing）安排 — {{SESSION_DATE}}",
  body    = "<filled template>"
)
```

**Hard rule: this mail is a DRAFT, never a send.** Never call any send tool on
it — the user reviews and sends it.

**d) CRM task + notes backlink** —

**Check before you create.** The old statement was idempotent; `create_task` is
not, so a re-run would book the session twice. Call
`mcp__zynkr__list_tasks(filter="all", limit=200)` first and look for a task on
this deal whose subject is already `跟拍 shadowing @ <YYYY-MM-DD>`. Found →
skip, and say so. (That listing is capped at 200; if it returns exactly 200,
you cannot rule out a duplicate — ask the user rather than guessing.)

Otherwise `mcp__zynkr__create_task(deal_id="<deal_id>",
subject="跟拍 shadowing @ <YYYY-MM-DD>", body="行事曆：<event url>
Shadowing 資料夾：<subfolder url>", due_at="<session date>T09:00:00+08",
confirm=true)`. It is created as the user and assigned to them — no ids to look up.

Then append the links to the deal notes. `update_deal` REPLACES `notes`:
`mcp__zynkr__get_deal(id="<deal_id>")` first, append

```
Shadowing <YYYY-MM-DD>：
行事曆：<event url>
資料夾：<subfolder url>
```

to what comes back, then `mcp__zynkr__update_deal(id="<deal_id>",
notes="<combined>", confirm=true)`.

Finally, **offer (ask-only)** a stage nudge: if the deal is still
`new`/`contacted`, ask whether to move it to `qualified`. On yes, use
`mcp__zynkr__move_deal_stage(id="<deal_id>", stage="qualified", confirm=true)`
— **only that tool.** Writing the column directly moves the stage but skips the
`stage_change` timeline entry and the automation event. Never nudge unasked.

### 6 · Report

```
Shadowing 已排定：範例科技 — 2026-08-12（週三）10:00–12:00

| 產出 | 狀態 / 連結 |
|------|------------|
| 時段 | 2026-08-12 10:00–12:00（Asia/Taipei · 2h）|
| 行事曆 | <event link>（未邀請客戶）|
| Shadowing 資料夾 | <subfolder url>（在 [N] 專案資料夾內）|
| 客戶信 | Gmail 草稿（待你審閱寄出）|
| CRM 任務 | 跟拍 shadowing @ 2026-08-12（due 當天）|
```

If the user works from another time zone, give the 時段 row in their time too.
Name what still needs a human: sending the draft, and — if the client wasn't
invited at the gate — telling them the confirmed time.

---

## Idempotency — re-running the same deal + date

A re-run must **update, not duplicate**: the
`list_drive_items` check in 5b reuses an existing `Shadowing — YYYY-MM-DD`
folder; the `list_tasks` check in 5d skips a task that already exists; for the
event, search the day (`mcp__claude_ai_Google_Calendar__list_events` with
`fullText = "[Shadowing] {{COMPANY}}"`) and change it with
`mcp__claude_ai_Google_Calendar__update_event` (with 5a's `timeZone`) if the time moved, rather
than creating a second hold. A changed slot supersedes the draft — create the
new one, tell the user to delete the old, append a correction line to deal notes.

## Why it's built this way

- **Gated, not autonomous** — a wrong artifact here has external blast radius
  (a mis-set attendee emails the client instantly). One gate settles both
  slot and attendee; before it, the skill only reads.
- **Draft-only client mail** — the mail carries commitments (date, recording
  consent); the user's voice check before send is non-negotiable.
- **Reuses the `[N]` folder** — numbering belongs to project-init; a second
  authority would fork the sequence.
- **The dated subfolder is the pipeline seam** — consult-brd-writer reads the
  transcript from exactly `[N]/Shadowing — YYYY-MM-DD`.
- **Adjacency rule over raw free/busy** — a technically-free slot after a 3h
  meeting is a bad shadowing slot; the judgment is encoded, not left to the user.

## Reference files

- `./references/shadowing-mail-template.md` — the client logistics mail
  (zh-TW primary + EN variant) with the placeholder table and filling notes.

## Limitations

- Requires a deal whose `[N]` folder can be found, either through the 專案資料夾
  line in its notes or through a single `[N] <Company>（…）` folder matching its
  company. Otherwise it stops (by design) rather than create folders or deals itself.
- Slots come from **the user's own calendar** and Taiwan's public holidays;
  client availability is confirmed via the mail draft, not negotiated live.
  Holidays where the user lives count only if their calendar shows them.
- Session output belongs downstream: /consult-transcriber files the transcript,
  /consult-session-notes the notes, /consult-brd-writer the BRD.
- The client is never emailed by this skill: the invite only if the user opts
  in at the gate, the logistics mail only when they send the draft.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
