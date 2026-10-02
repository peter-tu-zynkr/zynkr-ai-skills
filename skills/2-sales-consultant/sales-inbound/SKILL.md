---
name: sales-inbound
description: >-
  Turn this week's inbound sales mail into tracked work and first replies. It
  owns two inboxes: the website's "AI 顧問服務" consulting inquiries (the
  discovery-call emails from website@zynkr.ai) and the [2.1] Inbound Sales Gmail
  label. For each real lead it creates a CRM deal in Supabase, a numbered Google
  Drive project folder and a kickoff doc inside it, and drafts the first reply
  as a Gmail draft (never sent). Use this skill whenever Peter runs
  /sales-inbound or says things like "process this week's consult inbounds",
  "處理本週顧問諮詢", "有沒有新的顧問諮詢", "check for new consulting leads",
  "turn the discovery-call inquiries into deals", "intake the consult requests",
  "回覆 inbound sales", "清 sales inbox", "處理詢價信", or otherwise asks to triage /
  log inbound AI-consulting requests or inbound sales mail — even if he doesn't
  name the CRM, the Drive folder, or the exact phrase. It is also the skill a
  scheduled weekly sales-inbound run should invoke. The Support label and the
  other website forms belong to /zynkr-support; one pasted signal belongs to
  /sales-outbound.
category: sales-consultant
project: sales-inbound
platform: claude
status: Done
visibility: public
author: Peter Tu
sheetId: "2.04"
input: "Inbound sales mail: website@zynkr.ai AI 顧問服務 inquiries and the [2.1] Inbound Sales label; optionally a forwarded proposal or partnership email"
process: "Sweep both inboxes → filter real leads → idempotently create a CRM deal + numbered Drive folder + kickoff doc → draft the first reply (never sent) → report; optional proposal mode opens a Notion ticket"
output: "Per real lead: a CRM deal, a numbered Drive folder, a kickoff doc and a first-reply Gmail draft; proposals listed for Peter; (optional) a Notion ticket"
synergy:
  - "sales-outbound"
  - "zynkr-support"
house-style: bound

---

# Sales Inbound

Peter gets inbound sales mail two ways: consulting inquiries through the Zynkr
website's consult page, and mail that lands under the `[2.1] Inbound Sales` Gmail
label. This skill clears both once a week: it reads the week's mail, and for every
genuine lead it lays down what the sales motion needs — a **CRM deal** his team can
track, a **Drive project folder** to hold the work, a **kickoff doc** so whoever
picks it up starts with context, and a **first-reply draft** so the lead hears back.

It runs **fully autonomously**: parse → filter → create → draft → report. No mid-run
confirmation. The whole point is that Peter runs it (or a cron does) and comes
back to a finished pipeline. Because it writes real CRM records and Drive files,
the safety comes from being *idempotent* — it skips tests and skips any lead that
already has a deal, so re-running the same week never creates duplicates. A reply
is only ever a draft: Peter reads it and sends it himself.

## One owner per inbox

Two skills used to draft on the same threads, so a lead could get two drafts. The
rule now:

- **This skill** owns the website's `Interest: AI 顧問服務` inquiries and every thread
  under `[2] Sales & consultant/[2.1] Inbound Sales`: it logs the lead and drafts the
  first reply.
- **/zynkr-support** owns `[3] Operation/[3.8] Support` and the website forms with any
  other interest (e.g. 團隊訓練). It lists anything of this skill's it comes across
  and drafts nothing on it.
- **/sales-outbound** takes one signal Peter pastes by hand (a DM, a card, a form
  row). This skill is the weekly sweep.

## The inbound email shape

Every real inquiry is plain text from `website@zynkr.ai` and looks like this:

```
Subject: New discovery call inquiry from Jane
From:    website@zynkr.ai

New discovery call inquiry

Name: Jane
Email: inquirer@example.com
Company: 轉職計劃中
Interest: AI 顧問服務
Source page: consult

Brief context:
我希望透過諮詢...
```

The signal that an email is a consulting lead is the line **`Interest: AI 顧問服務`**.
The five fields you parse are `Name`, `Email`, `Company`, `Interest`, and the
free-text under `Brief context:`. (`Company` is often a real org, but sometimes a
personal phrase like "轉職計劃中" or blank — that's fine, carry it through as-is.)

**Inbound Sales threads** are real conversations, not form notifications: the lead
is the sender. Take `Name` and `Email` from the `From:` line, `Company` from the
signature or the email domain (none for a free-mail address), and the context from
the latest message they sent. Three kinds turn up there:

- **A lead** — someone asking about Zynkr's services, a price or a call. Log it and
  draft the reply (steps 3–5).
- **A proposal** — a 講座提案, 合作邀請 or introduction. No deal and no draft: list it
  in the report for Peter, who can run the optional proposal mode below.
- **Not a prospect** — a vendor pitch, a newsletter, an automated mail. Skip it and
  say so in the report.

## Fixed facts (don't re-derive these)

- **Google account** for all Gmail/Drive tools: `<your-google-workspace-account>`
- **Drive parent folder** (where numbered project folders go): `1hkXPX7OXPFOU0BcloPbJSFp8O0zArM8t`
- **CRM deal URL** for the report/doc: `https://platform.zynkr.ai/deals/{deal_id}`
- Owner (`Peter Tu`) and pipeline (`銷售流程`) are looked up live inside the SQL — don't hardcode their ids.

---

## Workflow

### 1 · Pull the week's inquiries

Search Gmail for the consult inbounds from the last 7 days:

```
mcp__google-workspace__search_gmail_messages(
  user_google_email = "<your-google-workspace-account>",
  query = 'from:website@zynkr.ai "Interest: AI 顧問服務" newer_than:7d'
)
```

Then the second inbox this skill owns, the Inbound Sales label:

```
mcp__google-workspace__search_gmail_messages(
  user_google_email = "<your-google-workspace-account>",
  query = 'label:"[2] Sales & consultant/[2.1] Inbound Sales" -from:me newer_than:7d'
)
```

Tag every result with its inbox (`website` or `inbound-sales`). Then fetch the bodies in one batch with
`mcp__google-workspace__get_gmail_messages_content_batch(message_ids=[...])`.
A thread can contain several messages (auto-reply, follow-ups) but they share a
Thread ID — **dedupe by Thread ID** and keep only the original inquiry (the one
that actually carries the `Name:` / `Email:` block). Read an Inbound Sales thread
whole (`mcp__google-workspace__get_gmail_thread_content`): when its last message is
Peter's, he has already replied, so skip it and list it as handled.

If neither search matches, say so plainly ("No new inbound sales mail this week") and stop.
That's a perfectly good outcome, not a failure.

### 2 · Parse and filter out the noise

For each inquiry, extract `Name`, `Email`, `Company`, and `Brief context`. For an
Inbound Sales thread, parse it as the shape section describes and sort it into lead,
proposal or not a prospect; only leads go on to step 3.

**Skip test / spam rows** — these are not real leads and must not reach the CRM:
- the email is `@zynkr.ai`, or
- the name, company, or email contains `test`, `測試`, `ga4`, or similar dummy markers.

Skipping is normal — name what you skipped and why in the final report so Peter
can sanity-check your judgment.

### 3 · De-dup against the CRM

Before creating anything, check which of these leads already have a deal — they
were processed on a previous run and must be left alone.

Resolve the batch in two reads. First `mcp__zynkr__list_deals(limit=100)` once,
and keep the `contact_id` of every row. Then, per lead,
`mcp__zynkr__list_contacts(search="<email>")` — no match means a genuinely new
lead; a match whose id appears in that contact_id set is **already handled** →
skip it entirely (no deal, no folder, no doc). The rest are your work list.

Checking up front is the point: it stops you creating an orphan folder for a
lead that turns out to be a repeat.

⚠️ `list_deals` returns the newest 100 rows by activity and cannot filter by
contact. If it comes back with exactly 100, the de-dup is no longer sound —
stop and say so rather than risk double-booking a lead.

### 4 · For each surviving lead, create the three artifacts

Do these in order so each can reference the one before it.

**a) The CRM deal.** Three calls in this order, so each hands its id to the next.
Every write previews first — call it once without `confirm`, then again with
`confirm=true` to apply.

1. **Company** — skip when `Company` is blank.
   `mcp__zynkr__list_companies(search="<Company>")`; on no match,
   `mcp__zynkr__create_company(name="<Company>", confirm=true)`. Keep the id.
2. **Contact** — `mcp__zynkr__list_contacts(search="<Email>")`; on no match,
   `mcp__zynkr__create_contact(first_name="<Name>", email="<Email>",
   company_id="<company id, if any>", legal_basis="consent",
   lifecycle_stage="lead", confirm=true)`. Keep the id. `legal_basis` is
   required by the tool — an inbound form submission is `consent`.
3. **Deal** — `mcp__zynkr__create_deal(name="<DEAL_NAME>", contact_id=…,
   company_id=…, stage="new", service_tier="advisory", priority="medium",
   lead_source="content", close_date="<today + 30 days>", notes="<NOTES>",
   confirm=true)`. The pipeline, the 交易 number, the owner, the `created`
   activity and the automation event are all handled for you.

**One field does not survive the move.** The contact's `lead_status` /
`deal_status` cannot be set through the MCP and stay empty. The attribution
still lives on the deal as `lead_source="content"` — look there, not on the
contact.

Values:

| Placeholder    | Value |
|----------------|-------|
| `{{FIRST_NAME}}` | the lead's `Name` |
| `{{EMAIL}}`      | the lead's `Email` |
| `{{COMPANY}}`    | the lead's `Company` (empty string if blank) |
| `{{DEAL_NAME}}`  | **`Name（Company）AI 顧問`** — e.g. `Jane（轉職計劃中）AI 顧問`. If `Company` is blank, use just `Name AI 顧問`. For an Inbound Sales lead, end with what they asked for instead (2–6 字, e.g. `王小明（範例科技）團隊培訓報價`). |
| `{{NOTES}}`      | the `Brief context` text, prefixed with a source line (see below) |

Suggested `{{NOTES}}` value:

```
來源：官網 consult 頁面 · Interest: AI 顧問服務

諮詢內容：
<Brief context>
```

For an Inbound Sales lead the source line is `來源：Inbound Sales 信件 · <subject>`, and
`lead_source` follows how they found Peter: `content` (a post or the website),
`workshop` (an event or livestream they name), `referral` (a warm introduction),
otherwise `other`. Never `outbound`: they wrote in.

`create_deal` returns the new `deal_id` — carry it into (b) and (c). If step 3
already flagged this lead as handled, you never reach here: skip its folder and
doc too, and say so in the report.

**b) The Drive project folder.** The folder name is **`[N] Company（Name）`** —
e.g. `[1] 轉職計劃中（Jane）`. If `Company` is blank, use `[N] Name`.

Compute `N` by listing the parent folder and scanning **folders** (not files) for
a leading `[number]`:

```
mcp__google-workspace__list_drive_items(
  user_google_email = "<your-google-workspace-account>",
  folder_id = "1hkXPX7OXPFOU0BcloPbJSFp8O0zArM8t"
)
```

`N` = (highest `[number]` found among folders) + 1, or `1` if none are numbered.
When you create several folders in one run, keep incrementing locally so each
lead gets a distinct number. List the parent **once** at the start of the run and
track the counter yourself — don't re-list between leads.

Create the folder:

```
mcp__google-workspace__create_drive_file(
  user_google_email = "<your-google-workspace-account>",
  file_name  = "[N] Company（Name）",
  folder_id  = "1hkXPX7OXPFOU0BcloPbJSFp8O0zArM8t",
  mime_type  = "application/vnd.google-apps.folder",
  content    = " "
)
```

Capture the new folder's id from the response. (The tool rejects a completely
empty call, so pass a single-space `content` even for a folder — it's ignored.)

**c) The kickoff doc.** Read `references/starting-doc-template.md` and fill its
placeholders (`{{DEAL_NAME}}`, `{{TODAY}}`, `{{NAME}}`, `{{EMAIL}}`, `{{COMPANY}}`,
`{{CONTEXT}}`, `{{DEAL_URL}}`). Create it as a real Google Doc, then move it into
the project folder — this two-step path is reliable, whereas creating a Doc
directly via `create_drive_file` with the document mime-type returns HTTP 400:

```
# 1. create the doc (lands in My Drive root)
mcp__google-workspace__create_doc(
  user_google_email = "<your-google-workspace-account>",
  title   = "{{DEAL_NAME}} — 專案啟動",
  content = "<filled-in template>"
)
# 2. move it into the project folder (capture the doc id from step 1)
mcp__google-workspace__update_drive_file(
  user_google_email = "<your-google-workspace-account>",
  file_id    = "<doc id>",
  add_parents = "<new folder id from step b>"
)
```

Capture the doc's link for the report.

**d) Link the folder back to the deal** so the team can jump from CRM to the
workspace. Append the folder URL to the deal's notes:

`mcp__zynkr__update_deal` REPLACES `notes` wholesale, so append in three steps:

1. `mcp__zynkr__get_deal(id="<deal_id>")` — read the current `notes`
2. build the new value: the existing notes, then a blank line, then the block below
3. `mcp__zynkr__update_deal(id="<deal_id>", notes="<combined>", confirm=true)`

The block is exactly one line, on its own, with the full-width colon:

```
專案資料夾：https://drive.google.com/drive/folders/<new folder id from step b>
```

That line is the contract: `/consult-shadowing-scheduler`, `/gtm-uat-writer` and `/project-governance`
find the client folder by matching it, and `/project-init` writes the same line when it opens a won deal.
Don't reword it or add text after the URL.

Call it once without `confirm` to preview, then again with `confirm=true`. Never
send `notes` without the existing text in front of it — the field is overwritten,
not appended, and skipping the read loses every earlier backlink.

### 5 · Draft the first reply (Gmail draft — never send)

One draft per new lead, unless one already exists: first search
`in:sent to:<their email>` and the drafts folder, and when either finds a reply, skip it
and say so in the report.

- **Where it goes.** A website inquiry gets a fresh email to the address on its
  `Email:` line, never a reply in the `website@zynkr.ai` thread (that would only email
  the website). An Inbound Sales lead gets a reply inside its thread: pass `thread_id`
  and keep the subject, prefixed `Re: `.
- **How it reads.** Follow `/sales-outbound` steps 5 and 6, exactly as written there:
  read Peter's calendar first and offer three real windows in 台北時間 when the ask is a
  call (the fixed slot block, house wording), mirror their own words, add one short
  paragraph of substance before the ask, match their language, and sign off as Peter.
  Run only those two steps: its step 4 inserts a new deal, and this lead already has one.
- **What it may say about price or scope.** Only what the Zynkr 知識庫 states
  (`mcp__zynkr__search_kb`, then `mcp__zynkr__get_kb_article`). When the answer isn't
  there, write a holding line with a `[[NEEDS PETER: what is missing]]` block on top
  instead of a guessed number — the same rule /zynkr-support follows.
- **Create a draft, never send.** Confirm the draft exists and that `in:sent` holds
  nothing new to that address before you report.

### 6 · Report what happened

End with a compact summary table the user can scan in one glance — one row per
inquiry, including the skipped ones so nothing is silently dropped:

```
本週進件：官網 N 封 · Inbound Sales K 封，建立 M 筆

| # | 來源 | 姓名 | 公司 | 結果 | 交易 | 資料夾 | 回覆草稿 |
|---|------|------|------|------|------|--------|----------|
| 1 | 官網 | Jane | 轉職計劃中 | ✅ 已建立 | [deal](url) | [1] 轉職計劃中（Jane） | ✅ 已擬 |
| 2 | 官網 | GA4 Test | Zynkr Test | ⏭️ 跳過（測試） | — | — | — |
| 3 | Inbound Sales | 小明 | 某公司 | ⏭️ 跳過（已存在） | [deal](url) | — | ⏭️ 已回過 |
```

Then list the proposals found under the Inbound Sales label (sender · subject · one line),
any `[[NEEDS PETER]]` drafts, and state the headline in prose (e.g. "Created 2 deals +
2 folders + 2 docs + 2 reply drafts; skipped 1 test and 1 already-processed; 1 proposal
waiting for you").

---

## Why it's built this way

- **Idempotent over confirm-first.** Peter chose autonomous mode, so correctness
  can't depend on him eyeballing a preview. The dedup-by-email check in step 3
  is what makes an unattended or scheduled re-run safe.
- **The platform creates the deal, not a hand-written statement.**
  `mcp__zynkr__create_deal` is the same path the CRM's own "Create Deal" uses,
  so it assigns the pipeline and 交易 number, logs the `created` activity and
  emits the automation event on its own. A skill run leaves the database in the
  state a manual click would. The trade against the old single atomic statement
  is that company → contact → deal are now three writes: if one fails midway you
  can be left with a company and contact but no deal. That is recoverable and
  visible; re-running finds them and continues. Report it rather than retrying
  blindly.
- **Numbered folders are sequential, not timestamped.** Peter tracks consult
  projects by a simple running count (`[1]`, `[2]`, …). Scanning existing folders
  for the max keeps the sequence continuous even across weeks and reruns.
- **One owner per inbox.** /zynkr-support used to draft KB answers on the same
  Inbound Sales threads this skill logged, so a lead could get two drafts. The sales
  inboxes are this skill's now, and the Support inbox is /zynkr-support's.
- **Skipped rows stay visible.** Tests and duplicates are filtered, but always
  reported — a silent skip looks identical to "found nothing", and Peter needs to
  trust that a real lead never quietly vanished.

## Defaults you can safely assume (and Peter can override later)

`stage=new` · `service_tier=advisory (顧問訂閱)` · `priority=medium` ·
`lead_source=content` for a website inquiry (the enum has no "website" value; `content` is the closest; an Inbound Sales lead follows step 4)
· `value=NULL` (unknown at intake) · `close_date=today+30`. They are passed
explicitly on the `create_deal` call in step 4a — if Peter asks to change one,
change it there.

---

## Optional mode — inbound sales / proposal lead intake (folded in from inbound-sales-project-init)

The autonomous weekly flow above handles website **consult** inquiries
(`Interest: AI 顧問服務`) → CRM deal + Drive folder + kickoff doc. For a one-off
**inbound sales / proposal lead** — a forwarded 講座提案 / 合作邀請 / introduction
email — run this interactive branch instead, which additionally captures
attachments and opens a Notion ticket in the Consultant service DB:

1. **Locate & read the email** — a Gmail link / message ID / search hint, or a
   pasted body. Capture `Subject` / `From` / `Date` / `Message-ID` and every
   attachment (`filename`, `mime_type`, `attachment_id`); download attachments so
   they can be re-uploaded to Drive.
2. **Derive a glance-able project name**: `<Org/Sender> - <Topic> (<Key hook>)`
   (e.g. `範例科技 - 王 講座提案 (從痛點到系統的發想框架)`). Pick Team(s) — HR/人資 →
   `Human Resources`, revenue-bearing → also `Business Development`, product/UX →
   `Product Design`, existing client → `Account Management` — and Priority
   (default `Medium`).
3. **Re-read the Notion Consultant-service DB schema** before writing (don't trust
   a frozen snapshot); stop and ask if a property name has drifted.
4. **Create the Drive folder** → a **context Google Doc** (metadata, inbound
   source block, verbatim original letter, proposal breakdown, open questions,
   next actions) → move the doc into the folder → **re-upload the attachments**
   into the folder.
5. **Create the Notion ticket** at status **Consult intake** in the Consultant
   service DB and **bidirectionally link Drive ↔ Notion**.

> This branch was merged in from the former `inbound-sales-project-init` skill
> (deprecated 2026-06-06). Its config (`inbound-sales-config.md`, Notion data-source
> id) and `references/context-doc-template.md` live in git history at
> `skills/2-sales-consultant/inbound-sales-project-init/` (the commit before the
> merge) — restore them into this skill's `references/` when you wire the Notion
> branch live.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
