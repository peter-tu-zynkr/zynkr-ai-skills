---
name: sales-research
description: >-
  Runs AI background research on a company (and optionally a contact) in the
  Zynkr CRM and writes a concise, sales-context zh-TW brief back onto
  that record as a CRM note (備註) via `mcp__zynkr__create_note`. The research
  runs on the Claude Code side — WebSearch/WebFetch plus the Taiwan government
  registry APIs keyed off the 統一編號 — and only the write-back touches the
  platform, so it spends NO workspace AI quota. The platform's own "AI 背景研究"
  button and its MCP twin `mcp__zynkr__research_company` do the same job but
  bill the workspace AI budget; prefer this skill unless Peter asks for that
  one by name. Trigger EAGERLY whenever Peter says "trigger company
  research", "research this company", "研究這間公司", "查一下這間公司背景",
  "幫我查一下[公司名]", "look into [company]", "跑一下背景研究", or asks to
  research/enrich/look up a company or contact that is or is about to be in
  the Zynkr CRM — even if he only names the company and doesn't spell out
  "research." Also fire immediately after a company/contact gets created in
  this conversation if he asks for research on it in the same breath (e.g.
  "create a company for X, also trigger company research"). /sales-outbound,
  /sales-inbound and /sales-specialist run it as their own step on a new lead,
  before the first draft. Otherwise do NOT fire automatically after every
  company/contact creation on your own initiative — only when asked, in this
  call or the next.
category: sales-consultant
project: sales-research
platform: claude
status: Done
visibility: public
author: Peter Tu
sheetId: "2.11"
input: "A company name/domain (and optionally a contact name), or an existing Zynkr CRM company_id / contact_id."
process: "Resolve the CRM company record and our past dealings → web research + 統編 registry lookups (business model, size/HQ, industry risks, sales-fit angle) → dated zh-TW brief flagged unverified → CRM note via create_note → optional contact note → report."
output: "A dated 🔎 AI 背景研究 note on the company's CRM timeline, plus an optional note on a named contact (a person with no company: a short note on the contact alone). Additive."
synergy: []
reads: ["zynkr-service-offerings"]
house-style: bound

---

# Sales Research

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill sales-research
```

Given a company (and optionally a contact) in the Zynkr CRM, this skill runs targeted
web research on it — what it does, size/HQ, notable facts, and a sales-fit angle for
Zynkr's own products/services — and writes a concise, dated, zh-TW brief back as a
**note on that record's CRM timeline**, flagged as AI-researched and unverified.
Trigger it whenever Peter asks to research, look into, or check the background of a
company or contact tied to the CRM.

## Why this exists

Zynkr CRM itself (`crm.zynkr.ai`) has an "AI 背景研究" button on the
company/contact/deal detail page that runs a Claude tool-use loop
(`app/lib/ai/research.ts`, `generateBrief`: up to 8 web searches, `RESEARCH_MODEL`)
and saves a zh-TW markdown brief as a CRM note. Its MCP twin,
`mcp__zynkr__research_company`, presses the same button from here.

**Prefer this skill anyway.** Both platform-side routes bill the workspace AI
quota and cap out at ~8 generic web searches. This skill runs the research on the
Claude Code side — where the model and the search budget are already paid for —
and touches the platform only for the write-back, which is a plain
`create_note` CRUD call. That buys two things: it costs no CRM AI quota, and it
can reach sources the platform loop can't, notably the Taiwan government registry
APIs keyed off the 統一編號 (see step 2). Use `research_company` only if Peter
asks for the platform's own pipeline by name.

Because this is a rebuild rather than the audited in-app pipeline, **always label
the output as AI-researched and unverified** — the same posture the platform's own
feature takes (an aid to the salesperson, not a source of truth).

## How this differs from its neighbours

- **sales-outbound** — logs one person's interest signal as a lead and drafts
  the reply. It enriches the contact from a *profile URL the prospect handed
  over* (LinkedIn/IG/Threads bio), and hands the company to this skill after the
  claim and before the draft (its step 4c), unless the conversation already
  holds a brief. Its Mode C writes its own research card instead.
- **sales-inbound** — a weekly batch sweep of inbound consulting-inquiry
  emails into deals. It hands each new lead's company to this skill before the
  first reply (its step 4b); a lead it cannot research is listed as 待研究.
- **sales-specialist** — the business-card pipeline; its Step 5 hands each
  card's company to this skill.
- **sales-research** (this one) — takes a company (± contact) already in, or
  about to enter, the CRM and does dedicated background research on it, on
  demand, independent of any particular conversation thread.

If the research turns up that this is a live consulting/demo lead worth a
human follow-up, say so in the report — but don't create deals or tasks beyond
what's described below; that's the calling skill's (or Peter's) job.

---

## Workflow

**Run by a lead skill.** `/sales-outbound` (step 4c), `/sales-inbound` (step 4b) and
`/sales-specialist` (Step 5) run this skill as their own step, on a lead they have just filed. Then
these rules hold over the steps below:

- **Which company.** The `company_id` the caller passed, or else the company on the contact
  (`get_contact`, step 1). With neither, the note goes on the contact (step 1's person case), even
  when the email domain or the registry points to a company: add two or three lines on that company
  and end the note with 「公司尚未建檔：<公司名>」, so the deal owner can file it. Never
  `create_company`: the caller left the company out on purpose (none was named, the address is free
  mail, or its duplicate check could not be trusted).
- **Notes only.** No `update_company` either. A value the research found for a field (統編, address,
  headcount) goes in the note, for the deal owner to set.
- **The registry by name, only on an exact match.** A 統編 found by name counts only when one
  registered company, and only one, carries that name (its 有限公司 or 股份有限公司 ending aside), or
  when the lead gave the 統編 itself. Otherwise leave Track A out, and the note says the registry
  was not matched.
- **It asks nothing.** Each `create_note` previews and then confirms, as the caller's own writes do.
  Anything it would have asked goes into its report: `/sales-specialist` puts it to the user at its
  own review of the research, and the other two list it in theirs.

What the caller hands over with the ids (a sourcing row's website and background, a card's notes)
counts as what we already know: check it, rather than search for the same facts again.

### 1 · Resolve the CRM company record

You need a `company_id` before you can write a company brief. A person with no
company is the one exception. Figure out which case you're in:

- **Given a `company_id` directly** (e.g. from earlier in the conversation) → skip to
  step 2, no lookup needed.
- **Given a `contact_id` alone** → `mcp__zynkr__get_contact`. A `company_id` on the
  contact → use it. None → if their email domain is a company's, use it as the
  domain in the next case; otherwise it is the person case below.
- **Given a name/domain, record likely exists** → `mcp__zynkr__list_companies`
  and match by name/domain (case-insensitive, tolerate spacing/casing
  differences). Found → use that id.
- **A person or a one-person business, with no company to file it on** → search
  the registry once by name (Track A). A registration turns up → it is a company,
  and the next case applies. None, and no 統一編號 → skip the rest of Track A. Read
  only their public site and social profiles, and write two or three lines on the
  contact with
  `mcp__zynkr__create_note(contact_id=<id>, subject="AI 背景研究 · <name> <YYYY-MM-DD>", body=…)`,
  opening with `🔎 AI 背景研究` and ending with the ⚠️ line of step 3. Preview, then
  `confirm: true`, then go to step 6: a short note needs none of the sections.
  Never create a company just to hold the note. With no contact in the CRM either,
  ask.
- **No match for a company, or Peter is asking you to create the company right now** (never when
  a lead skill runs this one) →
  do the research first (step 2), then `mcp__zynkr__create_company` with the
  real structured fields you found (name, domain, industry, address, tax_id,
  employee_count), and land the brief itself as a note in step 4. Do **not**
  stuff the brief into `description` — see step 4 for why. Preview (`confirm`
  omitted/false), show Peter what would be created, then re-call with
  `confirm: true`.
- **Owner** — the person running this skill (`mcp__zynkr__whoami` → `owner_id`)
  unless told otherwise.

A contact may be named alongside the company (e.g. "research this company for
王 at 範例科技"). If so, resolve or note the `contact_id` too — you'll use
it in step 5.

**Read what we already know before searching outward.** A brief that repeats the
web but misses that a colleague met their COO last month is worse than none.
`mcp__zynkr__list_deals` with the company name as `search` → `get_deal` on each
hit for its stage, owner and `notes` (no CRM tool reads the timeline itself). If
the company has its own domain (not a free-mail one), also search Gmail for
`from:@<domain> OR to:@<domain>` and skim the subjects and latest messages. Note
who on our side spoke with whom at the company, when, and what came of it; that
becomes the brief's 過往往來 section. Read only: this step writes nothing.

### 2 · Do the research

Two tracks. Run the registry track **first** whenever the company is Taiwanese and
you have (or can find) a 統一編號 — it is fast, free, authoritative, and it anchors
whatever the web track turns up.

#### Track A · Government registry, keyed off the 統編

Take the 統編 from `get_company` → `tax_id`, or find it by company name. Use `curl`,
not `WebFetch` — WebFetch summarises through a small model, and a value that
overturns a CRM record should come from the raw bytes.

- **經濟部商業司 公司登記** — the authoritative name (including the 有限 / 股份有限
  type), 公司狀況, 設立 + 最後核准變更 dates, 資本總額 and 實收資本額, 代表人,
  registered address:
  ```bash
  curl -sS -g 'https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6?$format=json&$filter=Business_Accounting_NO%20eq%20<統編>&$skip=0&$top=1'
  ```
- **董監事 · 所營事業 · 財政部稅籍** — the g0v mirror returns all three in one call,
  including the shareholding split and the registered business-scope codes:
  ```bash
  curl -sS 'https://company.g0v.ronny.tw/api/show/<統編>'
  ```
  **所營事業 is the highest-signal field in the whole brief.** It says what the
  company registered to *do*, which often contradicts how it presents itself — a
  headhunting firm carrying `I301010 資訊軟體服務業` and `I501010 產品設計業` is
  building software whatever its website says. 董監事 出資額 ÷ 已發行股份總數 gives
  you the ownership split, which tells you how short the decision chain is.
- **Industry licence registers**, where one applies. Recruitment agencies, for
  instance, appear in 勞動部's 私立就業服務機構 open data with licence number,
  expiry and **員工人數** — often the only public headcount that exists:
  ```bash
  curl -sSL 'https://apiservice.mol.gov.tw/OdService/download/A17000000J-020013-IFV'  # XML
  ```

Treat third-party directories (twincn, datagovtw, findcompany, iyp) as leads only.
They lag the registry and routinely show superseded company types and addresses —
believing one over the registry has already produced a false "登記名稱存疑" flag.

#### Track B · Web

A handful of targeted searches, not an open-ended crawl:

1. `WebSearch` the company name (+ domain if known) for what they do, recent
   facts (funding, news, leadership), and anything the registry can't show.
   Pin down four things: the core business and main products or services, the
   business model (who pays, for what), the value proposition they claim, and
   who their customers are. These are what the first conversation is about.
2. If an official site/About page turns up, `WebFetch` it. Many Taiwanese
   corporate sites sit behind Cloudflare and return 403 with
   `cf-mitigated: challenge` to both `curl` and `WebFetch` — when that happens,
   say the claim is unverified rather than repeating it as fact. Check with
   `curl -sS -D - -o /dev/null <url> | grep -i cf-mitigated` so the report can
   state *why* it failed.
3. If a contact was named, one more search on their name + company for
   role/background — skip if nothing surfaces, don't guess.
4. One search on the **industry**, not the company: a risk or shift it faces now
   (tariffs, a new regulation, a labour shortage, a price swing). Keep it only
   with a dated source; it often explains why the timing is right.
5. Think about the **sales-fit angle**. Read what we sell from Atlas
   (`mcp__zynkr-atlas__get_knowledge`, key `zynkr-service-offerings`): its four
   product lines and the stages of the enterprise AI Enablement line. Then match by
   the company's size: why might *this* company plausibly be interested, and in
   which line? Ground it in what the research actually surfaced, and put no price
   in the brief. If Atlas cannot be read, write the angle without naming a line or
   a plan, and say so under 本次未能查證. The registry is especially good for this:
   a tiny headcount next to a self-built software product is a structural
   capability gap, and that gap is the opening.

If the research comes up thin (obscure company, no useful web presence), say
so plainly in the brief rather than padding it with generic filler.

### 3 · Structure the brief

Write in zh-TW, matching the platform's own tone — compact, sales-oriented,
not a Wikipedia dump. Use this shape:

```markdown
🔎 AI 背景研究

**<主題> — <YYYY-MM-DD>**｜統編 <統編>

**一句話：** 一句話講完最會改變接觸方式的那件事

**過往往來** 我方誰、何時、和對方誰談過，結果如何（出處：CRM 交易 · 信件）；沒有就寫「無」
**公司登記（<來源>）** 查得到出處的硬事實：名稱 · 狀態 · 資本 · 地址 · 董監事
**所營事業** 登記碼 + 中文名，特別是與自我定位不符的那幾項
**其他官方登記** 稅籍 · 產業許可（含員工人數、許可效期）
**業務與商業模式** 核心業務 · 主要產品與服務 · 誰付錢買什麼 · 自稱的價值主張 · 客戶是誰
**產業動態** 產業此刻面對的風險或變化，附日期與出處
**銷售脈絡** 推論，每一點都扣回上面的事實
**本次未能查證** 明說查不到什麼、為什麼查不到

⚠️ AI 自動研究，未經人工查證 — 使用前請自行確認
```

Two rules about this shape:

- **The first line must be exactly `🔎 AI 背景研究`** — that is the marker the
  platform's own research writes, so the note reads as one of the family.
- **Keep verified fact and inference in separate sections, and name the source
  on the fact side.** A brief that blends "the registry says 430 萬實收" with
  "they probably need help productising" is a brief nobody can safely quote.
  The 未能查證 section is not an admission of failure — it is what stops the
  next reader repeating an unchecked claim as established.

Keep it to a short paragraph or two per section — someone will skim this on a
timeline, not read a report.

### 4 · Write it back as a CRM note — NOT into `description`

**The write target is a note**, for these reasons:

- On `crm.zynkr.ai`, **備註 is the note tab** — `crm_activities` rows with
  `kind='note'`. That is what Peter sees on a record.
- `crm_companies.description` is a different thing. The company detail page
  selects it and then never renders it; the only place it surfaces in the whole
  UI is the *create company* modal, labelled 說明. After save it is invisible.
  A brief written there is a brief nobody will ever read.
- The platform's own AI 背景研究 writes `crm_activities` too, never `description`.

So: `mcp__zynkr__create_note(company_id=<id>, subject="AI 背景研究 · <主題> <YYYY-MM-DD>",
body=<the brief from step 3>)` — preview first, then `confirm: true`.

Three mechanics that bite:

- **`subject` is not rendered for `kind='note'`.** The card shows `body` only.
  Put everything you want seen in `body` and open it with the literal
  `🔎 AI 背景研究` line. Still set `subject` — it shows in search and elsewhere.
- **Never put the string `⏳ 研究中` in a note body.** The detail page
  substring-matches it and renders your finished note as a stuck "researching…"
  spinner with a 停止 button instead of your content.
- Notes are additive — no read-merge-write, nothing to clobber. If the record
  already carries an older brief, write a new note saying what changed and what
  it corrects rather than rewriting history.

**Structured fields are a separate and welcome write.** When the research yields
a hard value for a column the CRM actually has — `employee_count`, `industry`,
`tax_id`, `address`, `domain` — set it with `update_company`, passing only fields
that are empty on the record (`get_company` shows them). A value already there
stays, even when the research disagrees: a person may have curated it, so the note
names the difference instead, and only Peter's word changes that field. That is how
a fact becomes filterable instead of prose. A lead skill's run writes no field at
all (*Run by a lead skill*, above).

### 5 · Contact-level note (only if a contact was named)

`create_note` takes a `contact_id` too — use it. Do **not** file a task: a task
says something needs doing, and this is a record.

- `contact_id`: the resolved contact
- `body`: the contact portion of the brief, opening with `🔎 AI 背景研究`, plus a
  one-line pointer back to the company record's fuller brief
- `subject`: `AI 背景研究 — <contact name> · <YYYY-MM-DD>`
- Preview, then `confirm: true`.

Only create a task if the research surfaced something that genuinely needs a
human action, and say so in the report.

### 6 · Report

Tell Peter what you found and where it landed — a short summary of the brief
plus which record(s) got updated, e.g.:

```
研究完成，已寫入公司 timeline 的 note：

**範例科技**（公司 id ...）
- 登記事實：實收 500 萬 · 員工 12 人 · 所營事業含資訊軟體服務業
- 銷售脈絡：小團隊已有內部工具 → 缺的是導入量能，適合談顧問與訓練而非工具
- 已建立 note（timeline 可見）；employee_count 一併補進欄位
- 未能查證：官網擋自動存取（Cloudflare challenge），產品功能描述沿用前次研究

⚠️ AI 自動研究，未經查證，回覆客戶前請自行確認關鍵事實
```

Say plainly what did not land. A failed CRM write, an unresolved company_id, or
a central claim that stayed unverified all belong in the report rather than
under a success line that papers over them.

---

## Things to be careful about

- **This is a workaround, not the platform's audited pipeline.** Always
  include the ⚠️ unverified disclaimer in what you write to the CRM — don't
  let a confident-sounding brief get mistaken for a vetted fact.
- **Never fabricate.** If web research doesn't surface something (size,
  funding, a contact's role), leave it out rather than guessing.
- **Write to notes, never to `description`.** The UI never renders that column,
  so a brief filed there is silently lost. Step 4 has the detail.
- **Don't spend CRM AI quota unasked.** `mcp__zynkr__research_company` and the
  in-app button both bill the workspace AI budget. This skill exists to do the
  same job from the Claude Code side, where it costs nothing.
- **The registry outranks the directories.** When twincn/datagovtw/findcompany
  disagree with 商業司 about a company's name, type or address, 商業司 wins —
  and name the source you used in the brief.
- **Preview-then-confirm on every CRM write** (`create_note`, `create_company`,
  `update_company`, `create_task` all require `confirm: true` to actually
  apply) — show Peter the preview first if this is a new company being
  created, since that's a bigger commitment than adding a note.
- **Don't create deals, contacts, or companies you weren't asked to create.**
  If the company/contact doesn't exist and Peter only asked for "research,"
  ask whether he wants it created too rather than assuming. When a lead skill
  runs this one, it creates none and asks nothing (*Run by a lead skill*, above).
- **Scope stays research + write-back.** If the findings suggest a real sales
  or consulting opportunity, flag it in the report — don't spin up a deal or
  hand off to another skill unprompted.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
