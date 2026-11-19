---
name: sales-outbound
description: >-
  Turn ONE person's interest signal into a tracked CRM lead AND a ready-to-send reply. The
  signal is a copied DM / chat thread (Threads, IG, LINE, FB Messenger, WhatsApp, email), an
  event feedback or registration form row, a website enquiry, or business-card text: one named
  person with an email address. An open deal on their email stops the run; otherwise it claims
  them in Zynkr CRM (company, contact, a runner-owned deal, a source note and a
  task) and drafts the reply as a Gmail DRAFT (never sent) in the signal's language, signed by
  the runner, with three real 台北時間 slots when the ask is a meeting. Trigger on
  /sales-outbound or when Peter pastes a DM, a form row or an enquiry and says
  "draft a reply", "draft an outbound mail", "回這個", "幫我擬回覆", "把這個 lead 建進 CRM 並擬信", "log this
  lead and draft the email", "turn this DM into a draft", "這個回饋幫我建客戶並擬信". Mode B — a
  five-touch SEQUENCE for someone who has NEVER replied: trigger on "一週五封", "連續開發信",
  "跑一整套序列", "同一個人五次", "五封序列", or the 陌開名單 roster; it claims each person (contact +
  deal), then drafts all five mails. Mode C — ONE mail to a COMPANY's shared inbox from the company
  directory list: trigger on "Mode C", "公司名單", "工商名錄", "對公司窗口開發"; it researches the
  company and drafts one mail; the contact and deal wait for its reply ("{公司} 回信了"). Distinct
  from sales-client-sourcing (BATCH-enriches a WHOLE
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
process: "Parse the signal → enrich from any profile link → pick-up gate (an open deal on the email stops the run) → claim the lead (company + contact, a runner-owned deal, note, task) → /sales-research brief → slots from the host's calendar → Gmail draft → report."
output: "A CRM lead (company + contact + runner-owned deal + note + task) and a Gmail draft the runner signs, with three 台北時間 slots from the host's calendar; an open deal stops it."
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
   language and Peter's voice, signed by the person running the skill, that moves the next
   step forward — with three slots checked on the calendar of the person who will hold the
   meeting (the meeting host, Peter for a discovery call) when that next step is a meeting.

**What counts as a signal** — any ONE of these, for ONE named person:
a copied DM / chat thread · a row from an event feedback or registration form ·
a website enquiry · the text off a business card · a forwarded email. What matters
is that it names a person, carries an email, and shows what they want. It is NOT a
whole spreadsheet of people (that is `sales-client-sourcing`) and NOT a meeting
transcript (that is `sales-follow-up`).

It runs **autonomously**: parse → enrich → pick-up gate → write CRM → research the company →
check calendar → draft email → report. No mid-run confirmation — the email lands as a *draft* (safe, the runner reviews
before sending), and the CRM write is five calls to the CRM's own tools (step 4b). A run that stops
part-way says what it made and is finished from there, never run again from the top. Tagging the
new contact comes after those calls, as its own small step: a failed tag never undoes the lead.

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
- **CRM record URLs** for the report: `https://crm.zynkr.ai/deals/{id}` · `.../contacts/{id}` · `.../companies/{id}` — `{id}` is the uuid a create tool returns, or the matched record's.
- **The CRM is written only through the `zynkr` MCP's tools** (step 4b). The skill never writes CRM tables with SQL, so the CRM's own rules apply to every record: the deal gets its 交易 number, and `legal_basis` is required.
- **The owner is the claimer** — the person running the skill, whose email `mcp__zynkr__whoami` gives. Their member id is resolved **live** with `mcp__zynkr__list_workspace_members`, and `create_deal` files the deal in the default pipeline (`銷售流程`) itself — never hardcode an id, and never default the owner to `company.contact-email` when the claimer is someone else.
- **The meeting host** is the person who will attend the call, and step 5 takes the slots from their
  calendar, never the sender's (owner, 2026-11-18, `SKB-147`). **For a discovery call the host is Peter,
  calendar id `<your-company-contact-email>`.** That line is the skill's one named host: a later host is
  a change to it alone. Read the id from Atlas (`get_knowledge`, key `company.contact-email`, on the
  `zynkr-atlas` MCP server; the value is on its `value:` line). If Atlas cannot be reached or the key has
  no `value:` line, there is no host calendar: step 5 gives no slots and the report says why. The host
  is not the claimer: the runner still owns the deal and signs the mail.
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

> **The pick-up rule and the deal name are written in Atlas** (`get_knowledge`, key `sales.crm-data-standards`, on the `zynkr-atlas` MCP server): the claim rule, and §1's deal name. The six steps below are how this skill runs the rule, and they run as written even when Atlas cannot be reached; only the deal name then falls back to `<name> — <what they want>` (e.g. `小明 — Zynkr CRM Beta`), and the report says so.

**The claimer** is the person running the skill: `mcp__zynkr__whoami` gives their name and email,
and their member id is the `mcp__zynkr__list_workspace_members` row with that email.

**The tools come first.** Before the gate's first step, check that `whoami`,
`list_workspace_members`, `list_contacts`, `list_deals`, `list_companies`, `get_company`,
`create_company`, `create_contact`, `create_deal`, `create_note` and `create_task` are all among the
`zynkr` MCP's tools. If one is missing, stop before anything is written and say which: a lead
written only in part is worse than none. The tag tools are not on the list, since a missing one
only turns tags into a suggestion (below).

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

- `mcp__zynkr__list_companies(search=<the email's domain>, limit=100)` when that domain is not a
  personal mail service, and `mcp__zynkr__list_companies(search=<search term>, limit=100)` when the
  signal names a company, the search term being its name cut before the first comma, parenthesis,
  `%`, `*` or backslash, at most 60 characters (the tool turns those characters into spaces and
  keeps only the first 60, so a whole name like `範例科技 Co., Ltd.` finds nothing). Keep rows whose
  `domain` equals the email's domain (never a personal mail service's), or whose name matches
  ignoring case and the legal suffix.
- For each kept company: its open deals are the rows of the four `list_deals` calls above whose
  `company_id` is that company (no new calls), and `mcp__zynkr__get_company` shows any `description`
  line `公司名單冷開發（Mode C，YYYY-MM-DD，認領人 <名字>）`.
- Report each hit in one line and carry on: `<公司> 已有人在跟：<deal_number> · <stage> · 負責人 <member
  name>` or `<公司> 在 <YYYY-MM-DD> 由 <認領人> 用 Mode C 寫過`. The claimer talks to that teammate
  before sending anything; the claim itself goes ahead, because one open deal is per person, not per
  company.

#### 4b · Write the lead

Five writes on the `zynkr` MCP, one record at a time, in this order. Each is a two-call handshake:
`confirm:false` previews, then the identical call with `confirm:true` writes. A later write needs
an earlier one's id, so keep each id the moment its tool returns it. The enum values come from
*Inference defaults* below.

1. **Company** — none when *Inference defaults* says there is none (a personal address, and no
   employer named). Otherwise reuse a company the check above found: the row whose `domain` equals
   the email's domain, when that is not a personal mail service, else the row whose `name` equals
   the company's full name, ignoring case. A name that matched only without its legal suffix is the
   check's warning, not the same company. When neither is found and a search returned exactly 100
   rows, the find is not sound: create no company, file the contact without one, and say so in the
   report. Otherwise, when neither is found,
   `mcp__zynkr__create_company(name=…, domain=…, industry=…, country=…, description=…,
   owner_id=<claimer>)`, with `domain` only when the email's domain is the company's own and the
   other fields only from the signal and the profile link (workflow step 2). A company that
   already exists is left as it is.
2. **Contact** — first run 4a's steps 2–5 again, since a teammate may have picked up the same email
   since the gate. A stop there (an open deal, or a `list_deals` read of exactly 100 rows) ends the
   run as it does in 4a, and the report also lists the company if write 1 made it; a contact found
   now counts as one the gate matched. A matched contact is reused as it is, with no write; when
   several match, the first, and the report names the others. Only when none matches:
   `mcp__zynkr__create_contact(first_name=<the whole name>,
   email=<the normalised email>, title=…, phone=…, company_id=<step 1's, when there is one>,
   owner_id=<claimer>, lifecycle_stage=…, legal_basis="consent")`. Pass `lifecycle_stage` every
   time (the tool defaults to `opportunity`) and `owner_id` every time (without it the contact has
   no owner). `legal_basis` is `consent` (`sales.crm-data-standards` §3). The whole name goes in
   `first_name` and `last_name` stays empty (§3). Leave out what the signal lacks: the 待確認 gaps
   below are judged on what was written.
3. **Deal** — `mcp__zynkr__create_deal(name=<the deal name, sales.crm-data-standards §1>,
   contact_id=…, company_id=<step 1's, when there is one>, owner_id=<claimer>, stage=…,
   lead_source=…, priority=…, notes=…)`, plus
   `value` and `close_date` only when the signal states them. `deal_type` is the tool's default,
   `new_business`. The tool puts the deal in the default pipeline and gives it its 交易 number, but
   returns only the id: the number is read back after the last write (below).
4. **Source note** — `mcp__zynkr__create_note(contact_id=…, subject=…, body=…)`, the subject naming
   the channel and the outcome (`Threads 初次接觸 — 同意 demo`). The body opens with where it came
   from, the channel and any handle (`來源：Threads DM · @example.marketing`), then the conversation
   verbatim and who they are. A note takes one parent: on the contact, it shows on the contact's
   page and on the deal's, whose timeline includes its contact's notes.
5. **Follow-up task** — `mcp__zynkr__create_task(deal_id=…, subject=<the agreed next step, e.g.
   安排 30 分鐘 Demo + 開通 Beta>, body=…, due_at=<task_due_days from today, 09:00 台北時間, ISO 8601
   with +08:00>, assignee_id=<claimer>)`.

**Read the 交易 number back** after the last write, or after the one that failed:
`mcp__zynkr__list_deals(search=<search term>, limit=100)`, the search term being the deal name cut
before its first comma, parenthesis, `%`, `*` or backslash, at most 60 characters, and keep the row
whose `id` is the new deal's. The list puts the latest activity first, and a deal has none until
its task is written, which is why the read comes last. A read that finds nothing stops nothing: the
report then gives the deal by its link alone.

**A write that fails stops the run there.** Retry nothing, delete nothing, and go on to no tag, no
research and no draft. The report lists each record already made, with its link (the deal with
its 交易 number), and names the write that failed with the tool's error. To finish, run the writes
that are left and then the rest of the run, with those ids: in this conversation, or from the
report pasted into a new one. Never start it again from the top. Once the deal exists, a second
run stops at the gate on that deal (4a step 5), so its note, task and draft would never be written.

The second look at write 2 leaves only the contact's and the deal's own calls between it and the
claim. A teammate who claims the same client in that gap makes a second open deal on the contact,
and `/sales-manager` REVIEW's 重複認領 check lists it for the two owners.

**Tag the contact.** After the five writes, tag the contact **only when it is new**: write 2 called
`create_contact`, in this run or in the stopped run it finishes. An existing contact keeps its
tags: a missing 來源 there is `/sales-manager` REVIEW's to find. Use the `zynkr` MCP. This is the
tool's own handshake, not a question to Peter: each tag is
`mcp__zynkr__apply_tag(group=…, name=…, entity_type="contact", entity_id=<contact_id>, source="rule")`
to preview, then the same call with `confirm:true`. Both groups come from fixed rules, so `source`
is `rule`.
- **來源** (`group="source"`) — the value on the policy's `outbound-mode-a-source` line, but only
  when its entry in `source-to-lead-source` equals the deal's `lead_source`. When they differ (an
  event feedback row is `workshop`, an introduction `referral`), apply none and write
  `標籤建議：來源=<the channel they came through>`.
- **待確認** (`group="review"`) — one value from `review-values` per gap: no phone → 電話缺漏, no
  title → 待補職稱, a company email or company name but no company record → 未關聯公司.
  `create_contact` always sets `legal_basis`, so 同意權未確認 does not arise here.

Never infer a tag from a job title or an industry. Read the result back with
`mcp__zynkr__list_tags(entity_type="contact", entity_id=<contact_id>)` and report what it shows.
When the policy or either tag tool is missing, apply nothing and keep the suggestions out of the
source note, which holds the signal as it came. Only when the contact is new (as above), write the
來源 and 待確認 suggestions in one `mcp__zynkr__create_note(contact_id=…, subject="標籤建議", body=…)`;
for a contact that already existed write none, since a suggestion followed by hand there would
change a complete record. A refused tag goes into that same kind of note.

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

### 5 · If the ask is a meeting, derive three REAL slots from the meeting host's calendar

**Never invent availability.** Whenever the draft will propose a call / demo / meeting,
read the calendar first — a guessed window is usually already booked.

**The calendar is the meeting host's** (owner, 2026-11-18, `SKB-147`, correcting `SKB-146`). The slots
must be hours when the person on the call is free, so they come from the calendar of the person who
will hold the meeting, not the sender's. The host is named once, in *Fixed facts* (a discovery call:
Peter, calendar id `<your-company-contact-email>`). When Peter runs the skill, that is his own
calendar. When the sales DRI (業務 DRI) or anyone else runs it, it is still the host's calendar, read
from the runner's session through the Google Calendar connector. The runner signs either way (step 6).

0. **Find the host's calendar.** The connector's tools
   (`mcp__claude_ai_Google_Calendar__list_calendars` and `…__list_events`) must be in this session;
   a session that lists them only by name loads them first (ToolSearch), and that is not a missing
   tool. Take the host's calendar id from *Fixed facts*, trimmed and lower-cased, and read it
   directly in step 1. `list_events` reads a calendar shared with the runner even when it is not in
   their calendar list, and a share the runner never added to that list is the usual case.
   `list_calendars` lists only the calendars the runner owns or has added, so it serves one purpose
   here: the host's time zone. When one of its entries has an `id` equal to the host's id (both
   trimmed and lower-cased), take that entry's `timeZone`; when none does, take the `timeZone`
   `list_events` returns if it returns one, else `Asia/Taipei`, and say in the report which one you
   used. When the runner is the host, that entry is their own calendar. When the runner is someone
   else, the host must have shared the calendar with them with **See all event details**
   (查看所有活動詳細資料): step 2 needs the literal `Available` titles, which a free/busy-only share
   hides. Never fill a gap from the runner's own calendar, a teammate's, or a guess.
1. **Read the events.** Use
   `mcp__claude_ai_Google_Calendar__list_events(calendarId="<the host's calendar id>", startTime=…, endTime=…, timeZone="Asia/Taipei", orderBy="startTime")`
   across the next 5–10 working days.
   ⚠️ Do **NOT** use `mcp__google-workspace__get_events` — the Calendar API is disabled
   on Peter's GCP project (`963483219986`) and it returns a hard error.
   What comes back decides whether there can be slots:
   - **An access error** (not found, forbidden): the host's calendar is not shared with the runner.
     **No slots.**
   - **Events, but none of them has a `summary`:** the share is free/busy only. **No slots.** One
     untitled event among titled ones is a private event, not free/busy access: it is still a busy
     time that step 2 subtracts.
   - **No events at all in range:** **no slots**, and the report names both possible causes: no
     `Available` block in range, or a free/busy-only share.
2. **Find the bookable windows.** The host's calendar marks them with events literally
   titled **`Available`** (and **`Not available`** for the inverse). Take each
   `Available` block and subtract every real meeting overlapping it. A leftover
   shorter than 30 minutes is not a slot. A calendar with no `Available` block in range
   gives **no slots** (*No slots* below), and the report says so.
3. **Pick three, spread across different days**, by the host's own clock: the
   time zone step 0 found.

   **A host in Amsterdam** (`Europe/Amsterdam`, which is Peter's): **Taipei afternoon
   first.** Their morning is the prospect's afternoon. Sort the windows by the
   Amsterdam clock:
   - **First choice:** a window before 12:00 Amsterdam. That is the Taipei afternoon,
     about 15:00–19:00 台北時間. Fill all three from these when there are enough.
   - **Fallback:** a window from 12:00 Amsterdam on. That is the Taipei evening, 19:00 or
     later. Use one only when the first-choice windows in range give fewer than three.
   - **Never** a window that lands before 12:00 台北時間. That is Peter's night.

   A window that crosses 12:00 Amsterdam counts as first choice for its morning part.

   **A host in Taipei** (`Asia/Taipei`): there is no clock to cross. Take the earliest
   windows in range, one per day. **A host in any other time zone:** convert the windows
   to 台北時間 first, keep only the parts that fall between 09:00 and 21:00 台北時間, then the
   same as Taipei, and name the zone in the report.

   For every host: when the prospect has said which days they cannot do, drop those days before you
   sort. If the days left give fewer than three windows, offer the ones there are and
   keep the escape line. Never make up a slot from an hour that is not marked
   `Available`. Express each as the whole remaining window (`15:30–18:00`), not one
   fixed time — let the prospect choose inside it.
4. **Convert to Taipei and say so.** The host's calendar may not be on Taipei time
   (Peter's is `Europe/Amsterdam`); almost
   every prospect is in Taiwan (+886), 6–7 hours ahead, so an unlabelled 「下午」 means
   two different things. Label the block **「（台北時間）」**. Keep the equivalents on
   the host's own clock (Amsterdam for Peter) for the CRM note and your report — not
   for the email.
5. **Record them on the deal** so the runner needn't re-convert when the prospect replies.

**No slots — the ask instead.** When step 0, 2 or 3 leaves no window, the mail offers no
times. In place of the slot block, ask which times suit them (台北時間) and say the invite
follows once they confirm, in the reply's own language and form of address. A zh-TW reply that
uses 你 says 「不曉得你哪些時間方便（台北時間）？確認後我會寄出會議邀請。」; one that uses 您, or
an English reply, says the same in its own words. Never fill the gap with a guessed hour or
any calendar but the host's, the runner's own included. The report names the reason: no calendar
connector in this session, no host calendar id from Atlas, an access error on the host's calendar
(not shared with the runner), the host's events all without a title (a free/busy-only share), no
events at all in range (no `Available` block, or a free/busy-only share: name both), no `Available`
block in range, or none left once step 3 dropped the days or hours that cannot be offered. When the
reason is or may be the sharing, the report also gives the fix, in two steps: the host shares their
calendar with the runner's Google account with **See all event details**, and the runner may also
add it to their own calendar list (so `list_calendars` shows its time zone). The next run can then
offer times.

If the ask is not a meeting (send info, share a link), skip this step entirely.

### 6 · Draft the reply (Gmail draft — never send)

Draft the outbound reply with
`mcp__google-workspace__draft_gmail_message(user_google_email="<your-google-workspace-account>", to="<their email>", subject="…", body="<the mail as HTML>", body_format="html", include_signature=true)`.

**The draft must carry the sender's Gmail signature** — the card with logo, title, phone and
links that the team's sent mail always ends with. The sender is the runner: the draft lands in
their own mailbox, so the card is theirs. Two settings do it, and both are required:
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
  - 我們 for company commitments, 我 for what the signer does themselves — mixing is deliberate.
  - A standard outbound mail runs **280–400 字**, blank-line paragraphs of 1–3 sentences.
  - Numbered lists are plain **`1. 2. 3.`** — NOT 1️⃣2️⃣3️⃣, never circled ①②③. Emoji numerals are
    a *UI* convention and are banned in email by 禁用詞清單 S and X.
  - At most **two lists in the whole mail**: the three things to discuss, and the slot block.
    Everything else is prose — a bullet wall is the 項目符號牆 category X forbids.
  - The dash is the **half-width ` — ` with one space each side**. Never the full-width ——.
  - Headings/taglines take **no 句號 (。)**; `·` for series separators; no Markdown in the body.
  - Sign off `Best regards,` + the runner's name (*The runner signs* below). Type no signature
    block in the body: Gmail adds the signature card under the sign-off (see the draft call above).
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
- **The runner signs** (owner, 2026-11-18, `SKB-146`). Sign off `Best regards,` then the name of
  the person running the skill, from the name `mcp__zynkr__whoami` gives: its first word when the
  name is in Latin letters (`Peter Tu` signs `Peter`), the whole name when it is in Chinese
  characters. Never another person's name, and never a name copied from this file or an example.
- **The mailbox must be the runner's.** Before drafting, check that the Google account the draft
  goes to (`<your-google-workspace-account>`) is the `whoami` email, both trimmed and lower-cased.
  When it is not, draft nothing: a draft in another person's mailbox would carry their signature
  card under the runner's name, and the runner would never see it. The report names the connected
  account, and the mail is drafted from this step once the runner's own account is connected.
- **The house voice holds whoever signs.** The voice rules above are Peter's house voice: a
  teammate's mail reads the same and is signed with their own name.
- **Create a draft, never send.** The runner reviews it and sends it themselves.
- **Verify before reporting** — confirm the draft carries label `DRAFT` and that
  `in:sent to:<their email>` returns nothing. Say so in the report.

### 7 · Report

Show the client card, then a compact artifact table:

```
已建立 lead 並擬好回信草稿：王小明（範例科技 ExampleCo）

| 產出 | 連結 / 狀態 |
|------|------------|
| CRM Deal | <交易 number> · <deal url>（負責人 <claimer>） |
| 聯絡人 | <contact url>（新建 / 既有） |
| 公司 | <company url>（新建 / 既有）／ 沒建（原因） |
| 活動 | note · 1 task |
| 標籤 | 來源=… · 待確認=…（已讀回）／ 未貼，標籤建議已記在 note（原因） |
| 研究 | /sales-research 寫在公司的 note ／ 聯絡人兩三行 ／ 沿用本次對話的研究 ／ 沒跑（原因） |
| Gmail 草稿 | 已放進收件匣，待你過目後寄出（已確認未寄出） |
| 署名 · 時段 | 署名 <runner> · 時段取自 <the host's calendar id> ／ 無時段（原因） ／ 不約會議 |
```

When the mail carries slots, also show them with their equivalents on the host's own
clock (Amsterdam for Peter) and the `Available` block each came from — that is what lets
the runner sanity-check you did read the calendar rather than guess. For an Amsterdam
host, mark each one Taipei afternoon or Taipei evening; if an evening slot is in the
mail, say why: the afternoon windows in range gave fewer than three. When a meeting mail
carries no slots, name which of step 5's reasons left it without them. When step 6 drafted
nothing because the mailbox is not the runner's, the Gmail 草稿 row says 未擬 and names the
connected account.

If the contact already existed, say so: every deal they had was `won` or `lost`, so the gate
let you attach a new deal to the same person rather than duplicating them. A run the gate
stopped reports only its one line (4a step 5) — no table, no draft — plus the company's link when
the second look at 4b write 2 stopped it after write 1 made one. A run over the cap adds
the cap line from *Inference defaults*. A run stopped by a failed write reports the records it made
and the write that failed (4b), with no draft, and says how it is finished.

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
- **value** — **left empty** unless a concrete figure was discussed (beta / early chats have none).
- **close_date** — left empty unless a date was stated (`YYYY-MM-DD`).
- **task_due_days** — from the follow-up rhythm in `company.sales-pipeline-rules` (read it with the
  line below). A lead who just wrote to us has no reply history, so it is `followup-fast-days`.
  A contact who already existed gets the rhythm their reply lag earns (median days between our
  mail and their reply, last 90 days, from Gmail). When the signal names a deadline ("下週五前要",
  "this month"), add the line `客戶時限：YYYY-MM-DD（原話）` to the deal's `notes` and make the task
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
  so contact/company are keyed (email / domain or name), and a new deal is booked only when the contact
  has none open. Re-running on the same email stops at the gate instead of booking a second
  deal; a client whose deals are all won or lost gets a fresh one.
- **The CRM's own tools, never SQL** (owner, 2026-11-15). Every record goes in through the tools
  the runner's own CRM connection offers, so the CRM's rules apply to it: the deal gets its 交易
  number, `legal_basis` is required, and the workspace is the runner's. Five calls are not one
  statement, so a run that stops part-way lists what it made and is finished from the write that
  failed. Run again from the top, it would stop at the gate on its own deal.
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
- **The runner signs; the host's calendar gives the hours** (owner, 2026-11-18: `SKB-146`, its
  calendar half corrected by `SKB-147`). Whoever runs the skill sends the mail, so the name under
  it is theirs. The hours belong to whoever must be free for the call, and today every discovery
  call is Peter's, so a run by the sales DRI offers Peter's hours. For a few hours `SKB-146` took
  them from the runner's own calendar, which offered times when the sender was free and the person
  on the call might not be. Without the host's calendar, shared with event details, the run still
  asks instead of guessing.
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
