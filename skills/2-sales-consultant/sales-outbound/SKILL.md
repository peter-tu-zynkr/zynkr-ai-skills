---
name: sales-outbound
description: >-
  Turn ONE person's interest signal into a tracked CRM lead AND a ready-to-send reply. The
  signal is a copied DM / chat thread (Threads, IG, LINE, FB Messenger, WhatsApp, email), one
  row from an event feedback or registration form, a website enquiry, or business-card text —
  one named person who showed interest and left an email address, optionally with a profile
  link. An open deal on their email stops the run; otherwise it claims them in Zynkr CRM
  (company + contact, a deal owned by the runner, a verbatim source note, a follow-up task)
  and drafts the reply as a Gmail DRAFT (never sent), in the signal's language and Peter's
  voice, with three calendar-checked 台北時間 slots when the ask is a meeting. Trigger on
  /sales-outbound or when Peter pastes a DM, a feedback-form row, or an enquiry and says
  "draft a reply", "draft an outbound mail", "回這個", "幫我擬回覆", "把這個 lead 建進 CRM 並擬信", "log this
  lead and draft the email", "turn this DM into a draft", "這個回饋幫我建客戶並擬信". Mode B — a
  five-touch outbound SEQUENCE for someone who has NEVER replied: trigger on "一週五封", "連續開發信",
  "跑一整套序列", "同一個人五次", "五封序列", or when Peter points at the 陌開名單 roster; it claims each person
  first (contact + a deal owned by the claimer), then drafts all five mails (see
  references/sequence-5touch.md). Mode C — ONE mail to a COMPANY's shared inbox from the company
  directory list: trigger on "Mode C", "公司名單", "工商名錄", "對公司窗口開發"; it claims the row,
  researches the company, drafts one mail and files only a CRM company with a research note and a
  no-reply reminder; the contact and the deal come only once the company replies ("{公司} 回信了")
  (see references/sequence-company.md). Distinct from sales-client-sourcing (BATCH-enriches a WHOLE
  survey Sheet), sales-inbound (the weekly sweep of inbound website consult EMAILS) and
  sales-follow-up (ONE completed demo transcript on an EXISTING deal).
category: sales-consultant
project: sales-outbound
platform: claude
status: Done
visibility: public
author: Peter Tu
sheetId: "2.09"
input: "ONE person's interest signal carrying an email — a pasted DM/chat thread, an event feedback or form row, a website enquiry, or business-card text; optionally their profile URL."
process: "Parse the signal → enrich from any profile link → pick-up gate (an open deal on the email stops the run) → claim the lead (company + contact, a deal owned by the runner, note, task) → /sales-research brief → calendar slots for a meeting → Gmail draft → report."
output: "A CRM lead (company + contact + a deal owned by the runner + note + task) and a Gmail draft, with three 台北時間 slots for a meeting; an open deal on the email stops it instead."
synergy: ["sales-research"]
reads: ["gov-subsidy-mechanics", "sales.crm-data-standards", "company.outbound-touches-sheet", "company.contact-email", "company.line-url", "company.sales-pipeline-rules", "company.crm-tag-rules", "doc-style", "company.company-directory-sheet", "company.workflow-library-folder"]
house-style: bound

---

# Sales Outbound

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill sales-outbound
```

Interest reaches Peter from everywhere — a Threads/IG/LINE/FB DM, an event feedback
form, a website enquiry, a card handed over after a talk. Whenever one of those names
a person, carries an email, and shows what they want, Peter wants two things to happen
at once: the person should become a **tracked lead in the CRM**, and a **reply should
be sitting in his inbox as a draft**, ready to tweak and send.

This skill does both from a single paste. He drops the signal in (and, if handy,
the person's profile link), and it:

1. **Collects the client context** — parses the signal for name, the email they
   gave, what they want, and who initiated; enriches role / company /
   industry from any profile URL.
2. **Claims the client in the CRM** — first the **pick-up gate**: if the email already
   has an open deal, the run stops and names its owner. Otherwise find-or-create company +
   contact, a **new deal owned by the person running the skill**, a **verbatim source
   note**, and a **follow-up task** for the next step — all before any draft.
3. **Drafts the reply** — a Gmail **draft** (never sent), in the signal's
   language and Peter's voice, that moves the next step forward — with three
   calendar-checked slots when that next step is a meeting.

**What counts as a signal** — any ONE of these, for ONE named person:
a copied DM / chat thread · a row from an event feedback or registration form ·
a website enquiry · the text off a business card · a forwarded email. What matters
is that it names a person, carries an email, and shows what they want. It is NOT a
whole spreadsheet of people (that is `sales-client-sourcing`) and NOT a meeting
transcript (that is `sales-follow-up`).

It runs **autonomously**: parse → enrich → pick-up gate → write CRM → research the company →
check calendar → draft email → report. No mid-run confirmation — the email lands as a *draft* (safe, Peter reviews
before sending) and the CRM write is one atomic statement. Tagging the new contact comes after
that statement, as its own small step (step 4): a failed tag never undoes the lead.

## Three modes

| | 前提 | 輸入 | 產出 |
|---|---|---|---|
| **Mode A** | 對方**已經回過話**，談到 demo／通話 | 一段貼上的 DM／對話 | 1 個 lead ＋ 公司研究 ＋ 1 封回覆草稿 |
| **Mode B** | 對方**完全沒講過話** | 陌開名單裡的一個人 | CRM 認領（聯絡人 ＋ deal）＋ 5 封序列草稿 ＋ 接觸紀錄 |
| **Mode C** | 公司**完全沒講過話**，只有窗口信箱 | 公司名單裡的一家公司 | 認領 ＋ 研究卡 ＋ 1 封開發信草稿 ＋ 接觸紀錄 ＋ CRM 公司（含研究卡備註、未回提醒）；**對方回覆後**才建聯絡人 ＋ 交易 |

**Mode C 的完整做法在 `references/sequence-company.md`**（文末「Mode C · 公司窗口一封開發信」有不能忘的幾條）。

**Mode B 的完整做法在 `references/sequence-5touch.md`**，信的長相（節奏、主旨、第 2–5 封骨架、交付文件格式）在 `references/sequence-template.md`，頁尾在 `references/email-format.md`。走之前三份都讀。
不要把 Mode A 的推論預設（`stage=contacted`、`lifecycle=sql`）套到 Mode B——
那些是給「已經有回應」的人用的；Mode B 的人一律 `還沒接觸過 → 已聯絡，待回覆`。

**Mode B 的認領是 CRM 裡的一筆 deal，在寫任何一封信之前**（`sequence-5touch.md` 步驟 0）：
每一位先過認領關卡（跟 Mode A 第 4 步同樣六步），已經有進行中 deal 的人退出這一批、回報是誰在跟；
其餘的人建好聯絡人（`lifecycle_stage=lead`），再建一筆負責人＝認領人的 deal，然後才開始寫信。
對方一回信，Gmail 同步就有聯絡人和 deal 可掛，也看得到該找誰；下一個人再挑到同一個 email，關卡就會擋下來。
每筆 deal 掛一個任務「五封未回 → 結案 lost（no_decision）」，到期日是第 5 封寄出日再加 7 天（五封的寄出日照管線規則的間隔與星期算，見文末 Mode B 段第 6 點），第 1 封改期就關掉舊任務、照新日期重建（`sequence-5touch.md` 0.3）；
五封都沒回，就由 `/sales-manager` REVIEW 把它結成 lost、結案原因 `no_decision`，pipeline 不會堆著冷掉的 deal。
`Outbound touches` 試算表照寫：`AI名單` 分頁的認領人給陌開名單 app 用，`接觸紀錄` 分頁記接觸，但關卡只看 CRM。
步驟 0 新建的聯絡人在步驟 7 貼標籤：來源取政策的 `outbound-mode-b-source`，加上看到的缺漏對應的 待確認，依 `company.crm-tag-rules`（`sequence-5touch.md` 7.1）。

> **下表的空白是公司事實——逐一從 Atlas 讀**（`zynkr-atlas` MCP 的 `get_knowledge`，key 見表，值在 `value:` 那一行）。Atlas 連不上、沒有這個 key、或沒有 `value:` 那一行，就停下來問；絕不帶著空白直接執行。

| 空白 | 在 `sequence-5touch.md` 哪裡用 | Atlas key |
|---|---|---|
| `<your-outbound-touches-sheet-id>` | 步驟 0 名單（`AI名單` 分頁）· 步驟 6 接觸紀錄（`接觸紀錄` 分頁） | `company.outbound-touches-sheet` |
| `<your-company-contact-email>` | 步驟 1 取時段的日曆——公司聯絡人的，不是執行者自己的 | `company.contact-email` |
| `<your-line-url>` | 第 1 封結尾的 LINE 官方帳號 | `company.line-url` |

`<your-google-workspace-account>` 與 `<your-sales-account>` 是執行者自己的帳號，不在 Atlas，用你自己的。

Gmail 草稿則**看環境**：有可用的 Gmail MCP 就用，沒有就走 Playwright 網頁版
（reference 裡的選擇器與地雷是後者實測出來的）。走之前先確認這台機器有哪些工具。
兩條路都要讓草稿**帶著寄件人自己的 Gmail 簽名**（2026-10-19 起，`SKB-085`）：MCP 照步驟 6 的參數建，
Playwright 照 `sequence-5touch.md` 步驟 5，不要讓 `fill()` 把簽名蓋掉。

## How this differs from its neighbours

- **sales-client-sourcing** — takes a WHOLE event/workshop survey **Sheet** and
  batch-enriches it into new columns (官網 · 公司背景 · 陌生開發策略 · Hot Lead).
  It writes back to the Sheet only — no CRM records, no email. Natural pairing:
  run it to triage the sheet, then run THIS skill on each hot row.
- **sales-specialist** — the **business-card** pipeline (OCR a card image → contact
  + company + 名片 note + follow-up draft). Same shape, different input: use it when
  the signal arrives as a photographed card rather than as text.
- **sales-inbound** — a weekly BATCH job that sweeps the two inbound sales inboxes
  (`website@zynkr.ai` AI 顧問服務 inquiries and the `[2.1] Inbound Sales` label), de-dupes
  them into deals and drafts each first reply by this skill's steps 5–6. Use it for the
  inbox sweep, not a single pasted signal.
- **project-init** — once a deal is qualified, opens the client project: numbered
  Drive folder + kickoff set + the deal's folder line. It never creates a deal —
  the deal comes from here, from sales-inbound or from a demo.
- **sales-outbound** (this one) — takes ONE person's **interest signal**
  (pre-meeting) and produces a lead record + a drafted reply. No Drive folder, no
  meeting parsing, no Weekly Update. Mode C included: it creates the company's deal once the
  company replies, and the `[N]` project folder still waits for project-init at `qualified`
  (owner, 2026-11-09).

## Fixed facts (don't re-derive these)

- **Supabase project_id**: `uomieoqlkazknjgmfdda` (the shared Zynkr project; CRM tables are `crm_*`)
- **Google account** for all Gmail tools: `<your-google-workspace-account>`
- **Writing style is NOT owned by this file.** Besides the House style block at the end
  (《[2.0]》 + 《[3.2]》), this surface's rules live under `[@] 寫作指南`
  (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime with
  `get_doc_as_markdown` (no tab parameter — use only `# 最終產出`, ignore `# 指令工程`):
  《[2.2] 內文風格指南》 **Part 3 §八 業務信件** (positive rules; its address is the Atlas
  reference `doc-style` — read it with `mcp__zynkr-atlas__get_knowledge`; if Atlas cannot be
  reached or has no `doc-style`, say so in the report and draft on 《[2.0]》 + 《[3.2]》 alone) and
  《[3.2] 禁用詞清單》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg` **category X**
  (sales-email forbidden patterns). The Doc wins over the rules restated below.
- **CRM record URLs** for the report: `https://crm.zynkr.ai/deals/{id}` · `.../contacts/{id}` · `.../companies/{id}` — `{id}` is the uuid the SQL returns.
- **The owner is the claimer** — the person running the skill, whose email and `workspace_id` `mcp__zynkr__whoami` gives (`{{OWNER_EMAIL}}` and `{{WORKSPACE_ID}}` in the SQL). Their member id and the default pipeline (`銷售流程`) are resolved **live** (inside the SQL, or by `mcp__zynkr__list_workspace_members` on the MCP path) — never hardcode an id, and never default the owner to `company.contact-email` when the claimer is someone else.
- **Do NOT log the drafted email as a CRM activity.** Peter's Gmail is already synced into the CRM (`app/lib/integrations/sync.ts`, 15-min cron): the moment he sends the draft, it auto-appears on the contact's 電子郵件 timeline as an outbound email. Logging it here would duplicate that row.

---

## Workflow

### 1 · Acquire + parse the signal

The signal usually arrives as **pasted text**. It may also be a pointer Peter expects
you to go read yourself — a Google Sheet URL plus a name ("the feedback from Rebecca"),
or a Gmail thread. Go fetch it rather than asking him to paste it again. Also capture
anything he hands alongside:
- A **profile URL** (Threads / IG / LinkedIn / FB / a website) → for enrichment in step 2.
- A **CRM record URL** (`…/contacts/{id}` or `…/companies/{id}`) → pass that uuid so
  the deal links to the existing record instead of creating a duplicate.

Pull these fields (infer logically, never fabricate — leave blank if absent):
- **Name / handle** of the counterparty.
- **Email** they gave (the reply will go here; it's also the find-or-create key).
- **Phone**, when the source carries one (forms usually do).
- **What they want** — a demo, a call, "send me info", joining a beta, buying. On a
  DM this is what they *agreed to*; on a feedback row it is what they *asked for*,
  which is softer — see *Inference defaults*.
- **The next step** — becomes the follow-up task and the email's ask.
- **Who initiated** — Peter reached out (outbound) vs they came to him (inbound) → `lead_source`.
- **Language** of the signal (zh-TW vs EN) → the draft matches it.
- **The single most quotable line they wrote**, verbatim — the draft opens by
  mirroring it, and the CRM note stores it unedited.

**Per-shape notes**
- **Feedback / registration form row** — read the header row too, so each answer is
  attributed to the right question; keep the free-text answers verbatim, including the
  "what else would you like to learn" style column, which is usually the real buying
  signal. Note which event they attended → that is the `lead_source`.
- **Business-card text** — if it is still an image, use `sales-specialist` instead.
- **Website enquiry** — if it is a whole inbox's worth, use `sales-inbound` instead.

### 2 · Enrich from the profile link

If a profile URL (or a resolvable handle) is present, fetch it with `WebFetch` and pull:
display name, bio/role, company, industry, follower count, any public contact email
or links. Fold this into the contact's `title` + the company record + the note. If no
link is given, skip — don't guess a bio.

### 3 · Build the client card

Assemble a compact summary and keep it for the report:

```
客戶名片
- 姓名 / 帳號 · …
- Email · …
- 身分 / 公司 · …            ← from enrichment
- 來源 · Threads DM（Peter 主動 / 對方來訊）
- 對話結論 · 同意看 30 分鐘 demo
- 下一步 · 約時間、寄會議連結
- 語言 · zh-TW
```

### 4 · Claim the client in the CRM — the pick-up gate first

**One open deal per client.** The person who picks a client up makes a deal owned by
themselves **before** any draft, and the next person who picks up the same email must see that
the client is taken. So the gate is the first CRM step of the run, and nothing is written, and no
mail drafted, until it has passed.

> **The pick-up rule and the deal name are written in Atlas** (`get_knowledge`, key `sales.crm-data-standards`, on the `zynkr-atlas` MCP server): the claim rule, and §1's deal name. The six steps below are how this skill runs the rule, and they run as written even when Atlas cannot be reached; only the deal name then falls back to the `{{DEAL_NAME}}` example in `references/lead-insert.sql`, and the report says so.

**The claimer** is the person running the skill: `mcp__zynkr__whoami` gives their name and email,
and their member id is the `mcp__zynkr__list_workspace_members` row with that email.

#### 4a · The gate — six steps, on the `zynkr` MCP, before anything is written

1. **Normalise the email** — trim it and lower-case it.
2. **Find the contact** — `mcp__zynkr__list_contacts(search=<email>, limit=100)`. The search is a
   substring match over both addresses, so keep only rows whose `email` or `secondary_email`,
   trimmed and lower-cased, equals the email exactly: `b@example.com` does not match
   `a.b@example.com`.
3. **No contact → step 6.** A new client.
4. **Find their open deals** — `mcp__zynkr__list_deals(stage=<stage>, limit=100)` once for each
   open stage, `new`, `contacted`, `qualified` and `proposal`, keeping the rows whose `contact_id`
   is one of the matched contacts. `list_deals` cannot filter by contact, so if any of the four
   calls returns exactly 100 rows the check is not sound: stop, create nothing, and say so. `won`
   and `lost` deals do not count: a client whose deals are all closed is free to claim again.
5. **An open deal → stop.** No contact, deal, note, task, tag or draft: the run ends here. Name the
   owner by matching the deal's `owner_id` to an `id` from `mcp__zynkr__list_workspace_members`,
   and report one line:
   `<email> 已有進行中的 deal：<deal_number> · <stage> · 負責人 <member name> · 最後活動 <last_activity_at, YYYY-MM-DD>`.
   When the owner is the runner, the same line applies: carry the work on in that deal
   (`/sales-follow-up` after a meeting), not a second one.
6. **Claim** — write the lead (4b) with the claimer as the owner of the contact it creates and of
   the deal, plus the follow-up task. Only then go on to the calendar and the draft. After the
   claim, count the claimer's open deals (the cap line in *Inference defaults*): over the cap is a
   warning in the report, never a refusal.

**Then check the company — a warning, never a stop** (owner, 2026-11-09). A teammate may already be
talking to this person's company: an open deal on a colleague's address, or a company-list mail
(`/sales-outbound` Mode C) that has no contact yet. Skip this check when the email is on a personal
mail service (gmail.com, yahoo.com, yahoo.com.tw, hotmail.com, outlook.com, icloud.com, msn.com and
the like) and the signal names no company. Otherwise:

- `mcp__zynkr__list_companies(search=<the email's domain>)`, and once more by the company's name when
  the signal names one; keep rows whose `domain` equals the email's domain, or whose name matches
  ignoring case and the legal suffix.
- For each kept company: its open deals are the rows of the four `list_deals` calls above whose
  `company_id` is that company (no new calls), and `mcp__zynkr__get_company` shows any `description`
  line `公司名單冷開發（Mode C，YYYY-MM-DD，認領人 <名字>）`.
- Report each hit in one line and carry on: `<公司> 已有人在跟：<deal_number> · <stage> · 負責人 <member
  name>` or `<公司> 在 <YYYY-MM-DD> 由 <認領人> 用 Mode C 寫過`. The claimer talks to that teammate
  before sending anything; the claim itself goes ahead, because one open deal is per person, not per
  company.

#### 4b · Write the lead

Read `references/lead-insert.sql`, fill the placeholders, run it via
`mcp__supabase__execute_sql(project_id="uomieoqlkazknjgmfdda", query=...)`.

`{{OWNER_EMAIL}}` is the claimer's email and `{{WORKSPACE_ID}}` the `workspace_id`, both from
`whoami`; the SQL resolves the claimer only inside that workspace and never picks one itself. The SQL carries the same gate inside the
statement: if a deal claimed after 4a was already saved when the statement started, it writes
nothing and returns `blocked = true` with that deal's number, stage, owner and last activity.
Treat that exactly as 4a step 5: stop, no draft, report the line. It takes no lock, so two claims
running at the same instant can both pass; that true race is caught afterwards by
`/sales-manager` REVIEW's 重複認領 check.

An owner email that matches no user in that workspace fails with a NOT NULL error (usually on
`workspace_id`). One statement:
- resolves the claimer (inside `{{WORKSPACE_ID}}`) and the default pipeline live,
- runs the gate (exact `email` / `secondary_email` match, open stages only),
- **find-or-creates the company** (case-insensitive by name; skipped if no company),
- **find-or-creates the contact** (by email or secondary email; reused if it already exists),
- inserts a **new deal owned by the claimer**,
- logs a **`note`** activity (the verbatim conversation + who they are) and a **`task`**
  activity (the agreed next step, due in `{{TASK_DUE_DAYS}}` days, assigned to the claimer).

It returns `company_id`, `contact_id`, `deal_id`, `note_id`, `task_id`, plus
`contact_existed` / `company_existed` booleans so you can say so in the report, and `blocked`.

**Escaping:** every `{{…}}` placeholder is replaced with a **SQL literal** — quote
text and double any single quote (`O'Brien` → `'O''Brien'`), or write `NULL`. For an
absent company, set `{{COMPANY_NAME}}` to an empty string `''` (the SQL then creates
no company and the deal's `company_id` is NULL).

**If the Supabase MCP is not authenticated** — you can tell because only
`mcp__supabase__authenticate` / `complete_authentication` are exposed and
`execute_sql` is missing — fall back to the `zynkr` MCP CRUD tools instead of
blocking. Run the gate in 4a exactly as written, all six steps: its matched contact is your
dedupe. Then `create_contact` (only when the gate matched none) → `create_deal` →
`create_note` → `create_task`. Each is a two-call handshake (`confirm:false` to preview, then
the identical call with `confirm:true`). They resolve workspace + pipeline natively, but three
things the SQL did for free you must now pass explicitly: **`legal_basis`**
(`consent` — the same house value baked into the SQL), **`lifecycle_stage`** (the
tool defaults to `opportunity`), and **`owner_id`** = the claimer's member id on both
`create_contact` and `create_deal` — never omitted: `create_contact` leaves the owner empty
without it. The whole name goes in `first_name`, and `last_name` stays empty (`sales.crm-data-standards` §3). `create_task` takes `deal_id`, `due_at` (ISO 8601 with `+08:00`) and
`assignee_id` = the claimer. On either path, write
the phone and title the signal gave (`{{PHONE}}` / `{{TITLE}}`, or `phone` / `title` on
`create_contact`); the 待確認 gaps below are judged on what was written, not on the signal.

See *Inference defaults* below for the enum fields.

**Tag the contact.** After the insert, tag the contact **only when this run created it**
(`contact_existed` false). An existing contact keeps its tags: a missing 來源 there is
`/sales-manager` REVIEW's to find. Use the `zynkr` MCP. This is the tool's own handshake, not a
question to Peter: each tag is
`mcp__zynkr__apply_tag(group=…, name=…, entity_type="contact", entity_id=<contact_id>, source="rule")`
to preview, then the same call with `confirm:true`. Both groups come from fixed rules, so `source`
is `rule`.
- **來源** (`group="source"`) — the value on the policy's `outbound-mode-a-source` line, but only
  when its entry in `source-to-lead-source` equals the deal's `lead_source`. When they differ (an
  event feedback row is `workshop`, an introduction `referral`), apply none and write
  `標籤建議：來源=<the channel they came through>`.
- **待確認** (`group="review"`) — one value from `review-values` per gap: no phone → 電話缺漏, no
  title → 待補職稱, a company email or company name but no company record → 未關聯公司. The insert
  always sets `legal_basis`, so 同意權未確認 does not arise here.

Never infer a tag from a job title or an industry. Read the result back with
`mcp__zynkr__list_tags(entity_type="contact", entity_id=<contact_id>)` and report what it shows.
When the policy or either tag tool is missing, apply nothing and put **no** tag suggestion into
`{{NOTE_BODY}}`: the insert is a find-or-create, so before it runs you cannot know whether the
contact is new, and a suggestion followed by hand on an existing contact would change a complete
record. Only after the insert returns `contact_existed` false, and only when
`mcp__zynkr__create_note` is among your tools, write the 來源 and 待確認 suggestions in one
`mcp__zynkr__create_note(contact_id=…, subject="標籤建議", body=…)`; otherwise write none. A tag
refused after the insert goes into that same kind of note.

> **The CRM tag rules are company policy — read them from Atlas** (`get_knowledge`, key `company.crm-tag-rules`, on the `zynkr-atlas` MCP server; each list is a `<name>: <value>` line at the top, and the `value:` line is the version date). Apply only a value those lines name: `group` is the platform's English key (`source`, `relationship`, `product`, `size`, `interest`, `review`) and `name` is the policy's value. Apply no tag when Atlas cannot be reached, the key or a line you need is missing, `mcp__zynkr__list_tags` or `mcp__zynkr__apply_tag` is not among your tools, or `apply_tag` answers `not_found` or `invalid_input` (an archived value, a group that does not fit the record): write each tag you would have applied as one line `標籤建議：<group>=<value>` in a CRM note on the record, say so in the report, and carry on with the run. When the policy itself cannot be read, write the evidence instead of a value (`標籤建議：主題=<what they asked about, in brief>`, `標籤建議：來源=<the channel they came through>`); never pick a value from memory or from an older copy of this file. On `conflict`, read the record back with `list_tags`, report what it shows, and do not retry. Any other error (`forbidden`, `rate_limited`, `internal`, …) is handled like `not_found`: no tag, a suggestion, no retry, and no stopping to ask.

#### 4c · Research the company before the draft

The reply is the first thing the client reads from us, so it is written knowing who they are.
After the claim and before step 5, in Mode A (Mode B makes no company, and Mode C writes its own
research card in `references/sequence-company.md` step 2):

1. **This conversation already holds a `/sales-research` brief on this company**, run earlier in
   it or pasted by the user from the company page → use that brief, and run nothing.
2. **Otherwise run `/sales-research` now** with the `company_id` and `contact_id` the claim
   returned, and what the signal already says about the company, then go on to step 5. It runs
   under its *Run by a lead skill* rule: notes only, with no company created and no field written,
   and nothing asked. Never look for an earlier brief in the CRM instead: no CRM tool
   reads a record's timeline, so a note filed there cannot be seen from here
   (`/sales-discovery-prep` step 2 works the same way).
3. **A person, or a one-person business** (the claim made no company, or the company is the person
   themselves) → `/sales-research` takes its person case: two or three lines on the contact, never
   a full brief.

The draft's point of view (step 6) may use what the brief found, and nothing it did not find; a
claim the brief marks unverified stays out of the mail. When the research cannot run or fails
(no web search, a refused write), draft anyway: the mail is a draft, and the report's 研究 row
says why there is no brief.

### 5 · If the ask is a meeting, derive three REAL slots

**Never invent availability.** Whenever the draft will propose a call / demo / meeting,
read the calendar first — a guessed window is usually already booked.

1. **Read the events.** Use
   `mcp__claude_ai_Google_Calendar__list_events(startTime=…, endTime=…, timeZone="Asia/Taipei", orderBy="startTime")`
   across the next 5–10 working days.
   ⚠️ Do **NOT** use `mcp__google-workspace__get_events` — the Calendar API is disabled
   on Peter's GCP project (`963483219986`) and it returns a hard error.
2. **Find the bookable windows.** Peter's calendar marks them with events literally
   titled **`Available`** (and **`Not available`** for the inverse). Take each
   `Available` block and subtract every real meeting overlapping it. A leftover
   shorter than 30 minutes is not a slot.
3. **Pick three, Taipei afternoon first**, spread across different days. Peter is in
   Amsterdam, so his morning is the prospect's afternoon. Sort the windows by the
   Amsterdam clock:
   - **First choice:** a window before 12:00 Amsterdam. That is the Taipei afternoon,
     about 15:00–19:00 台北時間. Fill all three from these when there are enough.
   - **Fallback:** a window from 12:00 Amsterdam on. That is the Taipei evening, 19:00 or
     later. Use one only when the first-choice windows in range give fewer than three.
   - **Never** a window that lands before 12:00 台北時間. That is Peter's night.

   A window that crosses 12:00 Amsterdam counts as first choice for its morning part.
   When the prospect has said which days they cannot do, drop those days before you
   sort. If the days left give fewer than three windows, offer the ones there are and
   keep the escape line. Never make up a slot from an hour that is not marked
   `Available`. Express each as the whole remaining window (`15:30–18:00`), not one
   fixed time — let the prospect choose inside it.
4. **Convert to Taipei and say so.** Peter's calendar is `Europe/Amsterdam`; almost
   every prospect is in Taiwan (+886), 6–7 hours ahead, so an unlabelled 「下午」 means
   two different things. Label the block **「（台北時間）」**. Keep the Amsterdam
   equivalents for the CRM note and your report — not for the email.
5. **Record them on the deal** so Peter needn't re-convert when she replies.

If the ask is not a meeting (send info, share a link), skip this step entirely.

### 6 · Draft the reply (Gmail draft — never send)

Draft the outbound reply with
`mcp__google-workspace__draft_gmail_message(user_google_email="<your-google-workspace-account>", to="<their email>", subject="…", body="<the mail as HTML>", body_format="html", include_signature=true)`.

**The draft must carry the sender's Gmail signature** — the card with logo, title, phone and
links that Peter's sent mail always ends with. Two settings do it, and both are required:
- `include_signature=true` appends the signature saved in Gmail settings.
- `body_format="html"`, because that signature is HTML. On a plain-text draft it is flattened
  into one run-on line with no logo, and a draft sent that way can go out with none at all
  (seen 2026-10-19: the same signature came through whole only on the HTML draft).

Write the mail as plain text first, then turn it into HTML mechanically: escape `&` `<` `>`,
turn every line break into `<br>`, wrap the whole body in `<div dir="ltr">…</div>`, and nothing
else (no bold, no lists, no styling). A URL may become `<a href="…">…</a>`.

To revise a draft you already made this run, create it again with the same call and delete
the old one (`mcp__claude_ai_Gmail__delete_draft`). Do not use `mcp__claude_ai_Gmail__update_draft`
here: given a plain `body` it rewrites the draft as plain text and clears the HTML, signature included.

Rules for the draft:
- **Match the signal's language** (zh-TW reply to a zh-TW signal, EN to EN).
- **Peter's voice** — warm, concise, peer-to-peer; mirror the tone of the source (if
  the DM was casual and friendly, so is the email). No corporate boilerplate.
- **Open by mirroring their own words** — quote back the concrete thing they said they
  wanted. On a feedback row, that is the verbatim free-text answer. This is what makes
  the mail land as a reply rather than a pitch.
- **Earn the meeting with a point of view** — one short paragraph of substance (how
  Peter would approach their problem, what order he'd do it in) before the ask. Never
  jump straight from greeting to calendar.
- **Move the next step forward** — if a meeting is the ask, offer the three slots from
  step 5; if "send info", point to it.
- **Concrete subject line**, naming their problem in their words.
- **The sales-mail rules are 《[2.2] 內文風格指南》 Part 3 §八 and 《[3.2] 禁用詞清單》 category X**
  (see *Fixed facts*) — read them; the Doc wins over this summary. The load-bearing few:
  - Greeting `Hi <名>，` / `哈囉 <名>，` / `<名> 你好，` / `<名> 您好，` (cold, HR, senior), full-width
    comma. 你／您 follows the counterpart and only ever steps **down**, never back up.
  - 我們 for company commitments, 我 for what Peter does himself — mixing is deliberate.
  - A standard outbound mail runs **280–400 字**, blank-line paragraphs of 1–3 sentences.
  - Numbered lists are plain **`1. 2. 3.`** — NOT 1️⃣2️⃣3️⃣, never circled ①②③. Emoji numerals are
    a *UI* convention and are banned in email by 禁用詞清單 S and X.
  - At most **two lists in the whole mail**: the three things to discuss, and the slot block.
    Everything else is prose — a bullet wall is the 項目符號牆 category X forbids.
  - The dash is the **half-width ` — ` with one space each side**. Never the full-width ——.
  - Headings/taglines take **no 句號 (。)**; `·` for series separators; no Markdown in the body.
  - Sign off `Best regards,` + `Peter`. Type no signature block in the body: Gmail adds the
    signature card under the sign-off (see the draft call above).
- **The slot block is fixed house wording** (Peter's own). Three slots, a fourth escape
  line, then the invite promise:

  ```
  不曉得以下有沒有方便的時間（台北時間）？

  1. 9/8（二）16:00–18:00
  2. 9/9（三）15:30–18:00
  3. 9/10（四）15:00–16:00
  4. 或其他你方便的時間

  確認後我會寄出會議邀請。
  ```
- **Sign off** `Best regards,` then `Peter`.
- **Create a draft, never send.** Peter reviews and sends himself.
- **Verify before reporting** — confirm the draft carries label `DRAFT` and that
  `in:sent to:<their email>` returns nothing. Say so in the report.

### 7 · Report

Show the client card, then a compact artifact table:

```
已建立 lead 並擬好回信草稿：王小明（範例科技 ExampleCo）

| 產出 | 連結 / 狀態 |
|------|------------|
| CRM Deal | <deal url>（負責人 <claimer>） |
| 聯絡人 | <contact url>（新建 / 既有） |
| 公司 | <company url>（新建 / 既有） |
| 活動 | note · 1 task |
| 標籤 | 來源=… · 待確認=…（已讀回）／ 未貼，標籤建議已記在 note（原因） |
| 研究 | /sales-research 寫在公司的 note ／ 聯絡人兩三行 ／ 沿用本次對話的研究 ／ 沒跑（原因） |
| Gmail 草稿 | 已放進收件匣，待你過目後寄出（已確認未寄出） |
```

When the mail carries slots, also show them with their Amsterdam equivalents and the
`Available` block each came from — that is what lets Peter sanity-check you did read
the calendar rather than guess. Mark each one Taipei afternoon or Taipei evening. If an
evening slot is in the mail, say why: the afternoon windows in range gave fewer than three.

If the contact already existed, say so: every deal they had was `won` or `lost`, so the gate
let you attach a new deal to the same person rather than duplicating them. A run the gate
stopped reports only its one line (4a step 5) — no table, no draft — and a run over the cap adds
the cap line from *Inference defaults*.

---

## Inference defaults (Peter overrides by just saying so)

Pick the closest enum from the conversation; use the fallback when there's no signal.

- **stage** (`new|contacted|qualified|proposal|won|lost`) — they engaged, whether they
  **agreed to a demo / call / clear next step** or said a softer "sounds interesting,
  maybe" → **`contacted`**; bare first reply → `new`. A **feedback / form row is `new`** —
  they described a need, but nothing has been agreed and Peter has not replied yet.
  **This skill never sets `qualified`.** Rule 8 of `company.sales-pipeline-rules` lets a deal into
  `qualified` only once its notes carry one line `資格：痛點＝…；決策者＝…；預算＝…；時程＝…` with all
  four parts filled, and a DM does not fill them. The move comes after the discovery call:
  `/sales-discovery` writes that line, and `/sales-follow-up` or `/consult-shadowing-scheduler`
  moves the deal once all four parts are filled.
- **lead_source** (`content|workshop|referral|outbound|other`) — **Peter messaged them
  first** → **`outbound`**; they came via a post/content → `content`; **they name an
  event or livestream they attended → `workshop`**; warm intro → `referral`; unclear
  → `other`.
- **contact lifecycle_stage** (`subscriber|lead|mql|sql|opportunity|customer|…`) —
  demo/call agreed → **`sql`**; **attended something and self-described a need →
  `mql`**; otherwise **`lead`**.
- **company** — a personal gmail/yahoo address with no employer named means **no
  company record**. Leave it null and note it; guessing an employer poisons the CRM.
  Create it after the first call, when they've told you.
- **priority** (`low|medium|high`) — default **`medium`**; eager / near-term → `high`.
- **deal_type** — **`new_business`** (this is a fresh lead).
- **value** — **`NULL`** unless a concrete figure was discussed (beta / early chats have none).
- **close_date** — `NULL` unless a date was stated.
- **task_due_days** — from the follow-up rhythm in `company.sales-pipeline-rules` (read it with the
  line below). A lead who just wrote to us has no reply history, so it is `followup-fast-days`.
  A contact who already existed gets the rhythm their reply lag earns (median days between our
  mail and their reply, last 90 days, from Gmail). When the signal names a deadline ("下週五前要",
  "this month"), add the line `客戶時限：YYYY-MM-DD（原話）` to `{{DEAL_NOTES}}` and make the task
  due on the earlier of the rhythm's date and that deadline. An interval Peter promised in the
  thread ("我三天後回你") wins over both.
- **claimer's open-deal count** — after the claim, count the claimer's open deals (the rows of
  the four open-stage `list_deals` calls whose `owner_id` is theirs). At or over
  `max-open-deals`, the claim still stands — warn, never refuse — and say so in the report:
  `<owner> 現在有 M 筆 open deal（上限 <max-open-deals>）— 先跑 /sales-manager 放掉 stale 的`.

> **The pipeline thresholds are company policy — read them from Atlas** (`get_knowledge`, key `company.sales-pipeline-rules`, on the `zynkr-atlas` MCP server; each threshold is a `<name>: <value>` line at the top, and the `value:` line is the version date). If Atlas cannot be reached, the key is missing, or a line you need is missing, say so and ask; never fall back to a number from memory or from an older copy of this file.

## Why it's built this way

- **One paste → both outputs.** The point is to kill the two-step (log the lead, then
  go write the email). Peter pastes once; the lead is tracked and the reply is waiting.
- **Email is a draft, not a send.** Outbound to a real prospect is Peter's call —
  the skill prepares, he approves. That's also why it needn't confirm before running.
- **Find-or-create, one open deal per client.** A person can come back for a second deal, but
  they shouldn't be duplicated as a contact, and two people must never chase the same client —
  so contact/company are keyed (email / name), and a new deal is booked only when the contact
  has none open. Re-running on the same email stops at the gate instead of booking a second
  deal; a client whose deals are all won or lost gets a fresh one.
- **The claim comes before the draft.** The deal, owned by whoever picked the client up, is the
  claim: made first, it is what the next person's gate finds. The claimer runs the skill in
  their own session, so the draft lands in their own mailbox.
- **Don't log the email activity.** The Gmail→CRM sync already captures it on send —
  logging here would double the row. The skill writes the *note* (the source signal,
  which the sync can't see) and the *task*, and leaves the email to the sync.
- **Slots come from the calendar, never from memory.** Peter sits in Amsterdam and
  nearly every prospect sits in Taipei, six hours ahead — so an invented "next Tuesday
  afternoon" is both probably booked and ambiguous about whose afternoon it means.
  Both failures cost a round-trip and read as careless. Three real windows plus an
  escape line converts in a single reply.
- **One signal shape in, one shape out.** The input parser is the only thing that
  differs between a DM, a feedback row and a card — everything downstream (CRM write,
  calendar, draft, report) is identical. That is why this skill absorbed the extra
  input types instead of a near-duplicate skill being cloned for each one.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.

---

## Mode B · 五封序列

完整步驟、職位切角表、外洩防線、實測地雷全在 **`references/sequence-5touch.md`**；
五封骨架與交付文件格式在 **`references/sequence-template.md`**。這裡只放不能忘的幾條：

1. **時段一律取自 Peter 日曆名為 `Available` 的事件**，並扣掉壓在上面的既有會議。沒標就問人，不要編。
   先排台北下午（Peter 的阿姆斯特丹上午），不夠三格才用台北晚上；台北中午以前是 Peter 的半夜，不給。
2. **階梯是 ask → ask → 長相 → 純給 → 放手。** 第 4 封必須零 ask，否則第 5 封還沒寄就被封鎖。
3. **`[2.7] 政府補助 knowledge` 絕對不可外發**（它自己第 5 節標了「內部資訊，勿外流」）。
   顧問姓名、拆帳、加價機制、盤點數字、難度分級一律不得進信裡。
   第 4 封的判斷點與時程一句改從知識庫卡片 `gov-subsidy-mechanics` 取，卡片沒寫的不寫；
   卡名、連結和卡片 `---` 以下的頁尾（Keywords、source_type）同樣不得進信。

   > **第 4 封的補助判斷點是知識庫卡片——從 Atlas 讀**（`mcp__zynkr-atlas__get_knowledge`，key `gov-subsidy-mechanics`，只用 `---` 以上的正文）。Atlas 連不上或沒有這張卡，就停下來問；絕不憑記憶或舊版檔案寫補助內容。
4. **草稿建好 ≠ 已寄出。** 接觸紀錄的 Remark 要註明「尚未寄出」，寄出後才拿掉。
5. **五封就停。** 沒回的改 `暫時沒需求`，那筆 deal 結成 lost、結案原因 `no_decision`（`/sales-manager` REVIEW 依步驟 0 掛的任務批次處理）。一天一批、一批不超過 `outbound-batch-max` 人。
6. **每 `sequence-gap-days` 天一封、第 1 封寄在 `sequence-first-weekday` 那天**，時段只放第 1 封，三格落在 T+2 到 T+8，而且早於第 4 封（T+3g）。
   序列的數字（一批幾人、間隔、第 1 封的星期、停損人數、每週時段下限、多久後再聯絡）都是 `company.sales-pipeline-rules` 開頭的行，讀法見 *Inference defaults* 最後那一行；這份檔案和 reference 不寫這六個值。五封、一天一批、第 5 封之後再等 7 天才結案、第 1 封的時段落在 T+2 到 T+8 而且早於第 4 封，是序列本身的形狀，寫在這裡。
7. **先認領、後寫信**（`sequence-5touch.md` 步驟 0）。每一位先過認領關卡（Mode A 第 4 步 4a 的六步，email 精確比對、只看進行中的四個階段），
   同一個 email 在同一批只留第一位（後面的標「同批重複」），已經有進行中 deal 的人**退出這一批**，回報「<email> 已有進行中的 deal：<交易> · <stage> · 負責人 <成員名> · 最後活動 <日期>」。
   其餘的人建聯絡人（既有就沿用，`lifecycle_stage` 一定要帶 `lead`，工具預設是 `opportunity`）＋一筆 deal ＋一個「五封未回 → 結案 lost（no_decision）」任務，
   聯絡人與 deal 的 `owner_id` 都是認領人：接觸紀錄的 `接觸人員`（沒有就用 `認領人`），用 `list_workspace_members` 對成員 id，對不到就跳過那一位，不要猜。
   **全部認領完才開始寫第一封。** 步驟 7 不再建聯絡人，只替步驟 0 新建的聯絡人貼 來源（政策的 `outbound-mode-b-source`）與缺漏對應的 待確認（`source: "rule"`），寫完用 `list_tags` 讀回，不另外再問一次；
   標籤規則讀不到、沒有標籤工具、或工具拒絕，就不貼，改記一行 `標籤建議：` note（讀法與降級見上方 Workflow 第 4 步的 `company.crm-tag-rules` 那一行）。

> 這批人是付過錢、上過 9–17 場的學員，`zynkr.ai` 網域信譽與《彼得的外商隨筆》電子報共用。
> 被檢舉成垃圾郵件是整個網域一起遭殃，不是這一封的事。

---

## Mode C · 公司窗口一封開發信

完整步驟在 **`references/sequence-company.md`**；信的長相、外洩防線、建草稿的地雷沿用 Mode B 的三份 reference。這裡只放不能忘的幾條：

1. **認領時先問認領人「這家主要要賣什麼」**，答案寫進公司 description，回覆後用在交易名稱，不要自己推。
2. **研究卡只寫查得到的**，推論要標明是推論；信裡講不出具體事就講到產業層級為止。
3. **只寄一封**：研究開場 → 三個痛點畫面 → 兩三句工作流 → 一句補助 → 30 分鐘 discovery call＋三個時段＋第四個逃生口，不提價格；寫時數是對 Mode B「時數不進客戶看得到的東西」的例外，owner 2026-11-09 核准、只限 Mode C。時段取法同 Mode B。不補寄第二封。
4. **工作流取自內部工作流資料夾，不附檔、不貼連結**，難度分級、階段與工作流編號不進信。
5. **認領是名單那一列；寄出時 CRM 只建公司**（研究卡與信的內容寫成一筆公司 note，description 一行 `公司名單冷開發（Mode C，YYYY-MM-DD，認領人 <名字>）`）＋一個掛在公司的任務 `Mode C <n> 天未回 → 接觸紀錄改暫時沒需求`（`<n>` 是 `company.sales-pipeline-rules` 的 `mode-c-reply-days`，到期＝寄出日＋`<n>` 天）。不建聯絡人、交易、專案資料夾；`create_company` 預設 `opportunity`，建完改 `lead`。`來源` 標籤只能貼聯絡人，所以公司只貼 規模／待確認，規模只看員工數證據。
6. **對方回覆後才建**：先用回信人的 email 過認領關卡，再對四個未結案階段逐一 `list_deals(stage=…)`，留下聯絡人或公司對得上的（剛好 100 筆就停）；已有交易就把回信人掛上去、不新建，沒有才建交易（名稱照 `sales.crm-data-standards` §1、`stage=contacted`、notes 第一行以 `Mode C` 開頭、不寫 `專案資料夾：`）→ 關掉未回提醒 → 追蹤任務。專案資料夾等 `qualified` 由 `/project-init` 開。退信、自動回覆不算回覆；「不需要」或過了 `mode-c-reply-days` 還沒回，接觸紀錄改 `暫時沒需求`、關掉提醒。

> **下表的空白是公司事實——逐一從 Atlas 讀**（`get_knowledge`，值在 `value:` 那一行）。Atlas 連不上、沒有這個 key、或沒有 `value:` 那一行，就停下來問；絕不帶著空白直接執行。

| 空白 | 在 `sequence-company.md` 哪裡用 | Atlas key |
|---|---|---|
| `<your-company-directory-sheet-id>` | 名單、步驟 1 認領 | `company.company-directory-sheet` |
| `<your-workflow-library-folder-id>` | 步驟 3 信裡的工作流來源 | `company.workflow-library-folder` |
| `<your-outbound-touches-sheet-id>` · `<your-company-contact-email>` | 步驟 5 接觸紀錄 · 步驟 3 信裡的時段 | 同 Mode B |
