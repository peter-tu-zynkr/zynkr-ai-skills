---
name: sales-inbound
description: >-
  Turn this week's inbound sales mail into tracked work and first replies. It
  owns two inboxes: the website's "AI 顧問服務" consulting inquiries (the
  discovery-call emails from website@zynkr.ai) and the [2.1] Inbound Sales Gmail
  label. For each real lead it creates a CRM deal in Supabase and drafts the
  first reply as a Gmail draft (never sent); the client folder and kickoff doc
  come later, from /project-init at qualified. Use this skill whenever Peter runs
  /sales-inbound or says things like "process this week's consult inbounds",
  "處理本週顧問諮詢", "有沒有新的顧問諮詢", "check for new consulting leads",
  "turn the discovery-call inquiries into deals", "intake the consult requests",
  "回覆 inbound sales", "清 sales inbox", "處理詢價信", or otherwise asks to triage /
  log inbound AI-consulting requests or inbound sales mail — even if he doesn't
  name the CRM or the exact phrase. It is also the skill a
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
input: "Inbound sales mail: website@zynkr.ai AI 顧問服務 inquiries and the [2.1] Inbound Sales label"
process: "Sweep both inboxes → filter real leads → pick-up gate (an open deal on the email, any owner, keeps the mail for that deal) → a CRM deal owned by the inbox owner → first-reply draft (never sent) → report; the folder waits for /project-init"
output: "Per new lead: a CRM deal owned by the inbox owner and a first-reply Gmail draft; a lead with an open deal reported with its owner; proposals listed for Peter"
synergy:
  - "sales-outbound"
  - "zynkr-support"
reads:
  - "kb"
  - "sales.crm-data-standards"
  - "company.sales-pipeline-rules"
  - "company.crm-tag-rules"
house-style: bound

---

# Sales Inbound

Peter gets inbound sales mail two ways: consulting inquiries through the Zynkr
website's consult page, and mail that lands under the `[2.1] Inbound Sales` Gmail
label. This skill clears both once a week: it reads the week's mail, and for every
genuine lead it lays down what the sales motion needs — a **CRM deal** his team can
track and a **first-reply draft** so the lead hears back.

The client folder and its kickoff doc are not this skill's. A lead is not a project
yet: `/project-init` opens the numbered folder, the kickoff documents and the deal's
`專案資料夾：` line once the deal reaches **qualified**, after the discovery call.

It runs **fully autonomously**: parse → filter → create → draft → report. No mid-run
confirmation. The whole point is that Peter runs it (or a cron does) and comes
back to a finished pipeline. Because it writes real CRM records and Gmail drafts,
the safety comes from being *idempotent* — it skips tests and skips any lead whose
email already has an open deal, under any owner, so re-running the same week never creates
duplicates and never takes a client a teammate is already working. A reply
is only ever a draft: Peter reads it and sends it himself.

## Configuration

A first reply may state a price or scope only from a **知識庫** this skill does not ship.

1. **Why it is withheld:** the cards are the company's own — its prices, policies and past
   answers — and they change every week, so a copy in this file would be out of date the day it
   shipped.
2. **The configure slot:** the `zynkr-atlas` MCP server, connected with an Atlas token of your
   workspace, and that workspace's published collection `kb`.
3. **What the 知識庫 must contain:** a published collection keyed `kb`; under it, one collection
   per section (`kb.<slug>`); in the sections, `fact` notes for the canonical prices and policies
   and `reference` notes (one per resolved question) that cite the facts they rest on.
4. **The Zynkr default:** the `kb` collection of Zynkr's own Atlas workspace. There is nothing to
   fill in: a token of that workspace is the whole setup.
5. **Not found:** if Atlas cannot be reached, the token reads no `kb` collection, or the walk in
   step 5 cannot finish, the run still logs every lead and drafts every reply, but each price or
   scope answer becomes a holding line with a `[[NEEDS PETER]]` block, and the report says why.
   Never fall back to another knowledge base, the Drive copy or memory.
6. **Loaded at run time:** the skill reads it on every run; nothing from it is copied into this
   file.

## One owner per inbox

Each inbox has exactly one owner, so a lead never gets two drafts:

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
  in the report for Peter, who decides how to take it up.
- **Not a prospect** — a vendor pitch, a newsletter, an automated mail. Skip it and
  say so in the report.

## Fixed facts (don't re-derive these)

- **Google account** for all Gmail/Drive tools: `<your-google-workspace-account>`
- **CRM deal URL** for the report/doc: `https://platform.zynkr.ai/deals/{deal_id}`
- **The owner of a new lead is the inbox's owner** — the person running the skill: `mcp__zynkr__whoami`
  gives their email, and their member id is the `mcp__zynkr__list_workspace_members` row with that
  email. `create_deal` resolves the pipeline (`銷售流程`) itself. Resolve both live; never hardcode an id.

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

### 3 · The pick-up gate — de-dup against the CRM

Before creating anything, check which of these leads a deal already covers. One open deal per
client: a lead whose email has an open deal belongs to that deal, whoever owns it, and must be
left alone.

> **The pick-up rule is written in Atlas** (`get_knowledge`, key `sales.crm-data-standards`, on the `zynkr-atlas` MCP server). The six steps below are how this skill runs it, and they run as written even when Atlas cannot be reached.

**One row per person first.** Normalise every lead's email (step 1) and de-duplicate the batch on
it: the first occurrence wins, and each later one is reported as 「同批重複」 under the first
one's result, with no contact, deal, task or draft of its own. Otherwise two inquiries from one
person in the same sweep would both pass the gate and both claim.

Then run the six steps on the `zynkr` MCP for every remaining lead. Steps 2–4 can be read once for
the batch: the four `list_deals` calls serve every lead.

1. **Normalise the email** — trim it and lower-case it.
2. **Find the contact** — `mcp__zynkr__list_contacts(search=<email>, limit=100)`. The search is a
   substring match over both addresses, so keep only rows whose `email` or `secondary_email`,
   trimmed and lower-cased, equals the email exactly: `b@example.com` does not match
   `a.b@example.com`.
3. **No contact → step 6.** A genuinely new lead.
4. **Find their open deals** — `mcp__zynkr__list_deals(stage=<stage>, limit=100)` once for each
   open stage, `new`, `contacted`, `qualified` and `proposal`, keeping the rows whose `contact_id`
   is one of the matched contacts. `list_deals` cannot filter by contact, so if any of the four
   calls returns exactly 100 rows the check is not sound: stop the run, create nothing, and say so
   rather than risk double-booking a lead. `won` and `lost` deals do not count: a contact whose
   deals are all closed gets a new deal (step 4), on the same contact.
5. **An open deal → the mail is that deal's.** No contact, deal, task, tag or reply draft for this
   lead. Name the owner by matching the deal's `owner_id` to an `id` from
   `mcp__zynkr__list_workspace_members`, and report one line:
   `<email> 已有進行中的 deal：<deal_number> · <stage> · 負責人 <member name> · 最後活動 <last_activity_at, YYYY-MM-DD>`.
   Carry on with the next lead.
6. **Claim** — the lead goes on to step 4, which reuses the matched contact or creates it, and
   makes the deal, both owned by the inbox's owner, before step 5 drafts anything.

Checking up front is the point: it stops you creating a second deal for a lead that turns out
to be a repeat, or one a teammate already has.

### 4 · For each surviving lead, create the CRM deal

Three calls in this order, so each hands its id to the next.
Every write previews first — call it once without `confirm`, then again with
`confirm=true` to apply.

1. **Company** — skip when `Company` is blank.
   `mcp__zynkr__list_companies(search="<Company>")`; on no match,
   `mcp__zynkr__create_company(name="<Company>", confirm=true)`. Keep the id.
2. **Contact** — the contact step 3 matched (exact email or secondary email), reused as it is;
   only when it matched none,
   `mcp__zynkr__create_contact(first_name="<Name>", email="<Email>",
   phone="<phone, if the inquiry gives one>", title="<title, if it gives one>",
   company_id="<company id, if any>", legal_basis="consent",
   lifecycle_stage="lead", owner_id="<inbox owner's member id>", confirm=true)`. Keep the id.
   `legal_basis` is required by the tool — an inbound form submission is `consent`. Always pass
   `owner_id`: without it the tool leaves the contact with no owner. Leave out
   `phone` and `title` when the inquiry does not carry them.
3. **Deal** — `mcp__zynkr__create_deal(name="<DEAL_NAME>", contact_id=…,
   company_id=…, owner_id="<inbox owner's member id>", stage="new", service_tier="advisory",
   priority="medium", lead_source="content", close_date="<today + 30 days>", notes="<NOTES>",
   confirm=true)`. The pipeline, the 交易 number and the `created` activity are handled for
   you; the owner is passed explicitly, so the deal is the inbox owner's claim.
4. **Follow-up task** — `mcp__zynkr__create_task(subject="回覆 <Name> 的諮詢並約時間",
   deal_id=<deal id>, due_at=<today + followup-fast-days, ISO 8601 with +08:00>,
   assignee_id="<inbox owner's member id>", confirm=true)`.
   They just wrote to us, so they have no reply history and the policy's rhythm is the fast one.
   Without this task the deal lands in `/sales-manager`'s 沒有下一步 bucket the day it is made.
   When the inquiry names a deadline ("十一月底前要辦內訓"), add the line
   `客戶時限：YYYY-MM-DD（原話）` under `{{NOTES}}` and make the task due on the earlier of the
   two dates.
5. **Owner's open-deal count** — count the owner's open deals (stage not `won`/`lost`). At or
   over `max-open-deals`, the lead is still logged — a warning, never a refusal; the report says
   `<owner> 現在有 M 筆 open deal（上限 <max-open-deals>）— 先跑 /sales-manager 放掉 stale 的`.
6. **Tags** — only on a contact this run created in item 2; an existing contact keeps its tags
   (a missing 來源 there is `/sales-manager` REVIEW's to find). By `company.crm-tag-rules` (its line
   is below), each tag is
   `mcp__zynkr__apply_tag(group=…, name=…, entity_type="contact", entity_id=<contact id>, source=…)`,
   previewed, then repeated with `confirm=true`.
   - **來源** (`group="source"`, `source="rule"`) — the `source-values` value the policy's 來源 table
     gives for how they reached us, applied only when its entry in `source-to-lead-source` equals
     the `lead_source` item 3 set. When the channel cannot be told, apply 其他 and add the 待確認
     value 來源不明 (policy §1). When they differ, apply none and write
     `標籤建議：來源=<the channel they came through>`.
   - **主題** (`group="interest"`, `source="ai"`) — the `interest-values` the inquiry itself asks
     about, and none when it names none. Never from their title or their company's industry.
   - **待確認** (`group="review"`, `source="rule"`) — only for a gap item 2 could not fill: no phone →
     電話缺漏, no title → 待補職稱, a company email or company name but no linked company → 未關聯公司,
     and 來源不明 as the 來源 bullet says.

   Read them back with `mcp__zynkr__list_tags(entity_type="contact", entity_id=…)`. A tag left
   unapplied (see the line below) goes into one
   `mcp__zynkr__create_note(contact_id=…, subject="標籤建議", body=…)`, previewed then confirmed; the
   deal is logged either way.

> **The CRM tag rules are company policy — read them from Atlas** (`get_knowledge`, key `company.crm-tag-rules`, on the `zynkr-atlas` MCP server; each list is a `<name>: <value>` line at the top, and the `value:` line is the version date). Apply only a value those lines name: `group` is the platform's English key (`source`, `relationship`, `product`, `size`, `interest`, `review`) and `name` is the policy's value. Apply no tag when Atlas cannot be reached, the key or a line you need is missing, `mcp__zynkr__list_tags` or `mcp__zynkr__apply_tag` is not among your tools, or `apply_tag` answers `not_found` or `invalid_input` (an archived value, a group that does not fit the record): write each tag you would have applied as one line `標籤建議：<group>=<value>` in a CRM note on the record, say so in the report, and carry on with the run. When the policy itself cannot be read, write the evidence instead of a value (`標籤建議：主題=<what they asked about, in brief>`, `標籤建議：來源=<the channel they came through>`); never pick a value from memory or from an older copy of this file. On `conflict`, read the record back with `list_tags`, report what it shows, and do not retry. Any other error (`forbidden`, `rate_limited`, `internal`, …) is handled like `not_found`: no tag, a suggestion, no retry, and no stopping to ask.

> **The pipeline thresholds are company policy — read them from Atlas** (`get_knowledge`, key `company.sales-pipeline-rules`, on the `zynkr-atlas` MCP server; each threshold is a `<name>: <value>` line at the top, and the `value:` line is the version date). If Atlas cannot be reached, the key is missing, or a line you need is missing, say so and ask; never fall back to a number from memory or from an older copy of this file.

**`lead_status` / `deal_status` stay empty** — the MCP cannot set them on the
contact. The attribution lives on the deal as `lead_source="content"` — look there, not on the
contact. A new contact's 來源 tag agrees with it (item 6).

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
That rule is how this inquiry came in, never the contact's existing 來源 tag: a contact an earlier
outbound round filed still opens an inbound deal here. It does not need the tag policy: without it
the deal opens the same way and only the tags wait.

`create_deal` returns the new `deal_id`; the report links it. If step 3 found an
open deal on this lead's email, you never reach here, and the report names that deal's owner.

**No folder, no kickoff doc.** Don't create a Drive folder or a kickoff doc, and
don't add a `專案資料夾：` line to the deal. `/project-init` does all three when the
deal reaches qualified, after the discovery call, and the skills that need the
folder (`/consult-shadowing-scheduler`, `/gtm-uat-writer`, `/project-governance`)
read that line. A lead that never qualifies leaves no orphan folder behind.

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
- **What it may say about price or scope.** Only what the 知識庫 in Zynkr Atlas states,
  read on the `zynkr-atlas` MCP server the way /zynkr-support reads it:
  1. **Once per run, walk its keys:** `mcp__zynkr-atlas__list_knowledge(collection: "kb",
     max_chars: 60000)`, called again with `after` set to `next_after` while `truncated`
     is true. Every key the pages list is **the set**. A failed page, or an answer cut off
     with no `truncated` at its end, is a failed walk.
  2. **Search, then read:** `mcp__zynkr-atlas__search_knowledge` with one or two words,
     zh and EN in separate queries (`報價`, then `price`), dropping every hit whose key is
     not in the set; then `mcp__zynkr-atlas__get_knowledge` on the best hits and on every
     key a card's 「Cites」 line names. A qa card's numbers are in the facts it cites, and a
     cited `company.…` fact gives its value on its `value:` line.
  3. **Only the text, only a sure card.** Quote only what sits above a card's `---` line:
     its footer (`Keywords:`, `source_type:`, `Flags:`, `Unverify note:`) is never reply
     material, and `source_type:` can hold a Gmail thread link. A card whose footer has a
     `Flags:` line naming `HELD`, `NEEDS_PETER` or `VOLATILE`, or an `Unverify note:` line,
     is not a sure source: treat it as no card (`always-read` is no warning).
  4. **No card, no number.** When the answer isn't there, or the walk failed or Atlas
     cannot be reached (no fallback to the CRM or the Drive copy), write a holding line with
     a `[[NEEDS PETER: what is missing]]` block on top instead of a guessed number — the
     same rule /zynkr-support follows.
- **Create a draft, never send.** Confirm the draft exists and that `in:sent` holds
  nothing new to that address before you report.

### 6 · Report what happened

End with a compact summary table the user can scan in one glance — one row per
inquiry, including the skipped ones so nothing is silently dropped:

```
本週進件：官網 N 封 · Inbound Sales K 封，建立 M 筆

| # | 來源 | 姓名 | 公司 | 結果 | 交易 | 跟進任務 | 標籤 | 回覆草稿 |
|---|------|------|------|------|------|----------|------|----------|
| 1 | 官網 | Jane | 轉職計劃中 | ✅ 已建立 | [deal](url) | 10/28 到期 | 來源 · 主題 ×2 · 待確認 ×1（已讀回） | ✅ 已擬 |
| 2 | 官網 | GA4 Test | Zynkr Test | ⏭️ 跳過（測試） | — | — | — | — |
| 3 | Inbound Sales | 小明 | 某公司 | ⏭️ 已有進行中的 deal（負責人 <member name>） | [deal](url) | — | — | ⏭️ 歸那筆 deal |
```

Under the table, the gate's one line for every lead an open deal already holds (step 3.5), so the
owner can be told. In the 標籤 column name the values applied; a lead whose tags were not applied says
`標籤建議已記在 note` and why. Then any owner at or over the open-deal cap (step 4.5), the proposals found under the Inbound Sales label (sender · subject · one line),
any `[[NEEDS PETER]]` drafts (and, when the 知識庫 walk failed, that it did, so every price
answer waited), and state the headline in prose (e.g. "Created 2 deals +
2 reply drafts; skipped 1 test and 1 already-processed; 1 proposal waiting for you").

---

## Why it's built this way

- **Idempotent over confirm-first.** Peter chose autonomous mode, so correctness
  can't depend on him eyeballing a preview. The pick-up gate in step 3 (an exact email
  match, open deals only) is what makes an unattended or scheduled re-run safe, and what
  keeps a teammate's client theirs.
- **The platform creates the deal, not a hand-written statement.**
  `mcp__zynkr__create_deal` is the same path the CRM's own "Create Deal" uses,
  so it assigns the pipeline and 交易 number and logs the `created` activity on
  its own. A skill run leaves the database in the state a manual click would.
  Company → contact → deal are three writes: if one fails midway you
  can be left with a company and contact but no deal. That is recoverable and
  visible; re-running finds them and continues. Report it rather than retrying
  blindly.
- **The folder waits for qualified.** A lead is not a project yet. `/project-init`
  opens the numbered folder once discovery qualifies the deal, so a lead that never
  converts leaves no orphan folder, and one skill numbers every project (D2).
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
explicitly on the `create_deal` call in step 4 — if Peter asks to change one,
change it there.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
