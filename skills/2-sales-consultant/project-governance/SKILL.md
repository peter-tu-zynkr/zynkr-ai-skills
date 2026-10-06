---
name: project-governance
sheetId: "2.45"
description: >-
  The weekly hygiene sweep across the WHOLE client project portfolio — inventory
  every numbered [N] project folder under the projects Drive parent AND the CRM
  deal that owns each one (linked by the deal's 專案資料夾 line, or by company
  name), diff the two against six invariants (deal↔folder backlink, the
  project's kickoff set, session-record recency, [N] numbering, activity pulse,
  document chain), and emit a zh-TW ready-to-apply changelist in the chat.
  Strictly READ-ONLY — it proposes fixes named to the owning skill but never
  applies one: no Doc creation, no folder moves, no CRM writes, not even a
  deal-note append. Trigger on /project-governance or when Peter says
  "顧問案健檢", "專案健檢", "檢查顧問專案", "顧問 portfolio 盤點", "案子有沒有漏",
  "consult drift check", "audit the engagement folders", or "portfolio hygiene
  sweep". Distinct from admin-governance (local _INDEX.md ↔ Drive KNOWLEDGE
  governance — a different universe), from project-client-status (ONE
  engagement, client-facing, writes a Gmail draft; this is ALL engagements,
  internal, writes nothing), and from project-init (it OWNS the fixes this
  report proposes — folders, numbering, backlinks, the project set).
category: sales-consultant
project: project-governance
platform: claude
status: Done
visibility: public
author: Peter Tu
input: "Optional: look-back windows (notes-recency days, activity-pulse days), or a single company to spot-check; defaults 21 / 14, whole portfolio"
process: "Inventory the [N] folders under the projects Drive parent → read every deal's 專案資料夾 line (read-only CRM) and attribute each folder → cross-check six invariants (backlink, kickoff set, session records, numbering, pulse, document chain) → findings + 建議動作 → 本次未檢查"
output: "A zh-TW portfolio hygiene report in the chat — findings per engagement with owning-skill fix pointers, a summary table, and an explicit not-checked list; nothing written anywhere"
synergy:
  - "project-init"
  - "sales-inbound"
  - "project-client-status"
  - "admin-governance"
house-style: bound

---

# Project Governance

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill project-governance
```

Every client project leaves a paper trail in two places — a numbered `[N]`
folder in Drive and a deal in the CRM — and the whole suite assumes the two
stay in lockstep. They drift anyway: a backlink never written, a `[Notes]` doc
that stopped three weeks ago, a `[PRD]` with no `[BRD]` behind it. This skill
is the weekly sweep that catches the drift: it inventories both sides of the
whole portfolio, diffs them against six invariants, and emits a zh-TW
changelist where every finding names the exact fix and the skill that owns it.

It is deliberately **read-only** — the report lives in the chat reply and
nowhere else. It never creates a Doc, never renames a folder, never touches a
deal, not even to append a note. A sweep that can write needs babysitting; a
sweep that only reports can run every Monday without fear.

## The project's life, as this sweep reads it

- **Before the sale**, no client folder opens: `/sales-inbound` and
  `/sales-outbound` create the deal only. Until 2026-10-05 `/sales-inbound` also
  opened a folder for each inbound lead and linked it from the deal, so older
  leads may have one. Not every folder is a build project — talks, partnerships
  and coaching land in the same parent, including the folders `/sales-inbound`'s
  optional proposal mode still files for them.
- **At qualified** (`SKB-045`: the deal is labelled `qualified` after the
  discovery call), `/project-init 客戶案` reuses the deal's folder or
  numbers a new `[N]`, lays the project set (`[Kickoff] <專案名稱>`,
  `[專案管控表]`, `[Charter]`, `[Business Case]`, `[復盤]`, and the sub-folders
  `[1] 會議` · `[2] 素材` · `[3] 交付物` · `[4] 封存`) and writes the deal's
  `專案資料夾：` line. From then on — `qualified`, `proposal` or `won`,
  "qualified or later" below — the project should be open. Projects that got
  there before `/project-init` did this may have only the inbound kickoff doc.
- **During the work**, `/consult-session-notes` files a `[Notes]` doc per
  session (shadowing notes go into the `Shadowing — YYYY-MM-DD` sub-folders),
  and people paste weekly updates into the `[Kickoff]`. The documents follow
  one chain: `[Assessment]` (`/ops-transformation assess`) → `[BRD]`
  (`/consult-brd-writer`, usually after the sale) → `[Blueprint]`
  (`/ops-transformation redesign`) → `[PRD]` (`/ops-prd-writer`) → `[UAT]`
  (`/gtm-uat-writer`). Coaching and training work may never need a BRD.
- **At the end**, the `[復盤]` is filled in, or the folder leaves the parent.

The CRM's stages are `new` · `contacted` · `qualified` · `proposal` · `won` ·
`lost` — nothing after `won` — so a won project's progress is read from its
documents, never from its stage.

## How this differs from its neighbours

- **admin-governance** — the pattern source, but a different universe: it
  reconciles local `_INDEX.md` files against Drive KNOWLEDGE folders (LOB
  docs). This skill reconciles the client *project* portfolio — CRM deals ↔
  `[N]` project folders.
- **project-client-status** — ONE engagement, client-facing, produces a Gmail
  draft. This skill is ALL engagements, internal-only, and writes nothing.
- **project-init** — it OWNS the fixes this report proposes: `/project-init`
  opens every client project once its deal is qualified (folder, `[N]`
  numbering, the project set, the deal backlink). This skill points at it; it
  never does its job.

## Fixed facts (don't re-derive these)

- **Google account** for all Drive/Docs tools: `<your-google-workspace-account>`
- **Drive parent folder** (`[2.2] 業務與顧問部門：專案`, where the numbered `[N]` folders live): `1hkXPX7OXPFOU0BcloPbJSFp8O0zArM8t`
- **Closed-projects archive** (`[Archive] [2.2] 結案專案`, beside the parent; a finished project's folder moves here and keeps its `[N]`): `1OP38Kx8oBxHuZjXL-LEsQETsNj0SSA7u`
- **CRM deal URL** for report lines: `https://platform.zynkr.ai/deals/{deal_id}`
- Every call this skill makes is a **read**, by design — it never writes.

## Hard rules

1. **Read-only, absolutely.** No Doc creation, no folder moves or renames, no
   CRM writes — not even a deal-note append. The report exists only in the
   chat reply.
2. **A missing folder is never a task.** A deal at qualified or later with no
   folder is listed once (it may not be a client project at all), with
   `/project-init 客戶案` as the way to open one; a `new` or `contacted` deal
   needs no folder. This skill never creates a folder under any circumstances.
3. **Every finding carries a 建議動作** naming the owning skill (or the exact
   one-line manual edit) that can actually do it. A problem without a routed
   fix is not a finding, it's noise.
4. **One cause, one finding.** A project at qualified or later that nobody has
   opened yet (neither `[Kickoff] <專案名稱>` nor `[專案管控表]` in its folder;
   an inbound kickoff doc does not count) gets one finding —
   I1's *Not opened* when the deal has no line, I2 when it has one — and
   I3 and I6 stay quiet for it: they would only repeat the same cause.
5. **Honesty over completeness.** Anything skipped — a file loose in the
   parent, a folder only a lost deal owns, a deal listing that hit its limit —
   is listed under 本次未檢查, never silently dropped.

## What this skill explicitly does not do

- Does **not** fix anything. /project-init opens client projects once the deal is qualified
  (folder, numbering, project set, backlink); /consult-session-notes files `[Notes]`;
  /consult-brd-writer (`[BRD]`), /ops-transformation (`[Assessment]`,
  `[Blueprint]`), /ops-prd-writer (`[PRD]`) and /gtm-uat-writer (`[UAT]`) own
  the document chain.
- Does **not** write to the CRM — no note appends, no stage moves, no tasks.
- Does **not** create, move, rename, or trash anything in Drive.
- Does **not** read Doc *contents* — it audits existence, titles, and
  `modifiedTime` only. An empty `[BRD]` with the right title passes I6.
- Does **not** audit the sales pipeline. `new` and `contacted` deals with no
  folder are counted in one line, never listed; a deal at qualified or later
  with no folder is listed once, never judged (hard rule 2).
- Does **not** email anyone. (If a finding ever turns into client-facing
  mail, that runs through the owning skill's Gmail-DRAFT rule — never sent.)

---

## Workflow

### 1 · Resolve scope

Defaults: whole portfolio · notes-recency window **21 days** · activity-pulse
window **14 days**. Peter may override either window or name a single company
to spot-check.

Single-company mode: the deal via `mcp__zynkr__get_deal` by id, or
`mcp__zynkr__list_deals(search="<company>")` by name; its folder via the
`專案資料夾：<url>` line in the deal notes, else the one `[N]` folder whose
name carries the company name. Then run steps 2–6 on that pair only; per hard
rule 2, never create anything.

Compute both cutoffs as dates up front and print them in the report header.

### 2 · Inventory Drive

List the parent: `mcp__google-workspace__list_drive_items(user_google_email=
"<your-google-workspace-account>", folder_id="1hkXPX7OXPFOU0BcloPbJSFp8O0zArM8t",
page_size=100)`. Keep the **folders**; a file loose in the parent goes to
本次未檢查. Read each folder's number from its leading `[N]`; the rest of the
name is free text (owners write `[N] 公司（專案）`, `[N] 專案`, and older shapes),
so a name is never a reason to skip a folder. List the closed-projects archive
once too, names only: its `[N]` numbers count as taken for I4, and nothing in it
is audited (a live deal whose line points there reads as moved out).

Then list *each* folder to capture its contents with `modifiedTime`: the
kickoff documents, the project set, and any `[Assessment]` / `[Notes]` /
`[BRD]` / `[Blueprint]` / `[PRD]` / `[UAT]` / `[復盤]` doc. Also list the
sub-folders that hold documents — `[1] 會議`, `[3] 交付物` and every
`Shadowing — YYYY-MM-DD` — a document filed there counts. This pass feeds I2,
I3 and I6.

### 3 · Inventory the CRM and attribute every folder (read-only)

`mcp__zynkr__list_deal_stages` first, to read the stage vocabulary rather than
assuming it. Then `mcp__zynkr__list_deals(limit=100)`, and fetch **every** row
with `mcp__zynkr__get_deal`: `list_deals` does not return `notes`, and the
`專案資料夾：<url>` line inside the notes (anywhere in the text) is what ties a
deal to its folder, whatever the folder is called.

Attribute each folder to its deal, **live deals first**. A live deal is `won`
or open (any stage but `won` and `lost`), and it always outranks a `lost` one,
so a lost lead's old link never takes a folder from the client's live deal:

1. **A live deal's line** — the won or open deals whose line carries the
   folder's id. Two or more is a *Fork* (I1).
2. **A live deal's name** — when no live line points at the folder: the won or
   open deals whose company name the folder name contains. Exactly one owns
   the folder; two or more is a folder-side *Ambiguous* (I1). The name is the
   company's (`mcp__zynkr__get_company`) with its legal suffix dropped —
   股份有限公司, 有限公司, 公司, Co., Ltd., Ltd., Inc. — because folders are
   named by what people call the client; a deal without a company uses its
   deal name up to the first ` — `, `（`, `(` or ` - `. Compare ignoring case,
   spaces and bracket width.
3. **A lost deal** — no live deal claims it, but a lost deal's line or name
   does: 未成交案的資料夾, listed under 本次未檢查, not audited.
4. **Nobody** — an orphan (I1).

Then sort what you have:

- **Audited** — a folder a live deal owns. These are the engagements of steps
  4 and 5.
- **Closed** — an audited folder whose `[復盤]` was modified after its
  `[Kickoff] <專案名稱>`: the project is finished. One 已結案 line; I2, I3 and
  I6 skip it.
- **Moved out** — a live deal whose line points at a folder that still exists
  outside the parent (`list_drive_items` on the id answers): archived. One
  已移出 [2.2] line, and nothing else for that deal.
- **Qualified, no folder** — any other deal at qualified or later that has no
  `專案資料夾：` line and no folder attributed to it (a line whose folder is
  gone is I1's *Dangling*, never also listed here). It may be an event, a
  beta seat or a program call rather than a client project, so it is never a
  finding: list every one in a single 未列入 line with the way to open one if
  it is a client project.
- **Early, no folder** — a `new` or `contacted` deal without one, the sales
  pipeline: one count line.

`list_deals` returns the newest 100 by activity and is scoped to your own
workspace, so if the count comes back at exactly 100, say so in the report and
treat the inventory as partial — a governance sweep that silently saw only
part of the portfolio is worse than one that admits the edge. For the activity
pulse, use `last_activity_at` from the same rows. Every call here is a read.

### 4 · Cross-check the six invariants

Run every audited engagement through `./references/hygiene-checklist.md` —
that file is the contract for what each invariant checks, which tool + field
answers it, and the exact 問題 → 建議動作 line format. In one breath:

| ID | Invariant | Applies to | Window |
|----|-----------|------------|--------|
| I1 | deal ↔ folder: a deal at qualified or later carries the line; no dangling, orphan, forked or ambiguous link | every folder and deal | — |
| I2 | the kickoff set is in the folder | qualified or later: `/project-init`'s set | — |
| I3 | a fresh session record (`[Notes]`, a kickoff doc, `[1] 會議`) | `proposal` · `won` | 21d |
| I4 | `[N]` numbering: no gaps, no duplicates, no folder without a number | every folder; archived numbers count as taken | — |
| I5 | the deal shows CRM activity (else 停滯) | open | 14d |
| I6 | document chain: each document has the ones it is built from | every audited engagement | — |

### 5 · Emit the report

zh-TW, findings-only: one section per engagement **with** findings; quiet
engagements roll into a single ✅ count line. A folder no deal owns (an I1
orphan) gets its own `## [N]` section the same way. Shape:

```
顧問案健檢 — 2026-10-05（回溯 21 / 14 天：會議紀錄看 2026-09-14 以後 · CRM 活動看 2026-09-21 以後）

## [4] 宏宇精密（報價流程自動化）— 2 項發現
- I3 · 問題：最新的會議紀錄停在 2026-09-05（[Notes] 與 [Kickoff] 都是），已超過 21 天
  建議動作：跑 /consult-session-notes 補最近一次會議的紀錄
- I6 · 問題：[UAT] 在資料夾裡，但它依據的 [PRD] 不在（deal 已成交：https://platform.zynkr.ai/deals/…）
  建議動作：跑 /ops-prd-writer 補 [PRD]，再確認 [UAT] 有照它寫

## [7] 王小明工作室（官網改版）— 1 項發現
- I1 · 問題：deal 已成交，notes 沒有 專案資料夾 那一行；資料夾以公司名對到 [7]，裡面還沒有專案文件
  建議動作：跑 /project-init 客戶案 交易-202610-004：沿用 [7]、補齊專案文件並寫上 專案資料夾 那一行

✅ 其餘 3 個 engagement 乾淨（[1] [2] [6]）
已結案：[3]（[復盤] 2026-09-20 更新）

| 統計 | 數量 |
|------|------|
| 檢查的 engagement | 5（成交 3 · 還沒成交、已有資料夾 2） |
| 乾淨 | 3 |
| 發現（依 invariant）| I1×1 · I2×0 · I3×1 · I4×0 · I5×0 · I6×1 |

未列入：
- 已到 qualified 以後但沒有專案資料夾：活動合辦（交易-202607-003）· Beta 席位（https://platform.zynkr.ai/deals/…）— 是客戶案的話跑 /project-init 客戶案 開案
- 12 筆還在 new／contacted、也沒有資料夾的交易（Sales 的 pipeline）

本次未檢查：
- [5] 某某公司（詢價）：只有未成交的交易對到，屬未成交案的資料夾
- 母資料夾裡的散檔「[1] SEO 寫作自動化討論.mp4」：不是資料夾
```

Every finding line quotes its evidence (the stale date, the missing title,
the deal URL); every 建議動作 names the owning skill. Findings sort by
engagement number; within an engagement, by invariant ID. A deal with no
交易編號 is named by its URL.

### 6 · Close with 本次未檢查

The report is not done until the honesty list is written — even when empty
("本次未檢查：無"). Include: files loose in the parent, folders only a lost
deal owns, a deal listing that came back at its limit, and any listing call
that errored mid-sweep. An audit that silently skips is worse than no audit.

---

## Why it's built this way

- **Report-only, borrowed from admin-governance.** A weekly ritual must be
  safe to fire without review; the moment a sweep can write, every run needs
  babysitting and the ritual dies. Proposing beats fixing.
- **Fixes route to owning skills.** project-init owns opening the project once
  the deal is qualified; the writers own their documents. One fix implementation per
  artifact means the fix logic can't fork — this report is a dispatcher, not
  a second implementation.
- **The link, not the name.** Folder names come in several shapes, and the
  `專案資料夾：` line is the one convention every reader of the folder
  already uses. Names only break a tie when no line exists.
- **Documents, not stages, after the sale.** The CRM stops at `won`, and the
  BRD usually comes after it, so a stage can't say which documents a project
  should have by now. What a document needs is fixed: the ones it is built
  from.
- **Findings-only sections + a ✅ roll-up.** At portfolio scale most
  engagements are clean most weeks; admin-governance's "Clean ✓" discipline
  keeps the signal-to-noise high enough that Peter actually reads it.
- **The checklist lives in a reference file.** The six invariants are a
  contract (tool + field + fix-line format); keeping them out of the workflow
  prose means they can tighten without the workflow churning.

## Inference defaults (Peter overrides by just saying so)

- **Windows** → 21 days (notes recency) · 14 days (activity pulse).
- **Scope** → whole portfolio; single-company only when a company is named.
- **"Open deal"** → any stage that isn't `won` or `lost` per
  `list_deal_stages` (confirm the actual slugs at run time).
- **"Qualified or later"** → `qualified`, `proposal` or `won`: the stages at
  which a client project should be open (`SKB-045` D2; it was `won` until
  2026-10-03).
- **I3's stages** → `proposal` or `won`. An opened `qualified` project is not
  checked for session records yet; I5's activity pulse covers it.
- **Report language** → zh-TW body; invariant IDs stay English (I1–I6).
- **Sort order** → by engagement number, then invariant ID.

## Provenance

Pattern-borrowed from `admin-governance` (3.05) — structure only, no copied
content; no drift exposure. Renamed from `consult-governance` and moved to
the Project team on 2026-10-02 (`SKB-045`), when the sweep started following
projects past the sale.

## Reference files

- `./references/hygiene-checklist.md` — the six invariant definitions: what
  each checks, the tool + field that answers it, violation shapes, and the
  exact 問題 → 建議動作 line format the report must use.

## Limitations

- Proposes only — someone (or the owning skill) still has to run the fixes;
  next week's sweep is the verification that they happened.
- Attribution by name is heuristic: a folder no line points at and no single
  deal's company matches reads as an orphan.
- Audits titles and `modifiedTime`, never contents — an empty `[BRD]` passes
  I6, and a kickoff doc renamed away from its convention reads as missing.
- A finished project without a `[復盤]` (projects that got past qualified
  before `/project-init` opened them) stays audited until its folder leaves the parent; a `[復盤]`
  edited before the end closes a project early, and I3 goes quiet for it.
- A folder sitting in Drive's trash may read as moved out rather than gone.
- Activity pulse only sees what the CRM recorded — un-logged calls and
  offline work show up as 停滯 (the I5 fix line says how to correct that).
- Point-in-time snapshot; it keeps no history and computes no week-over-week
  trend.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
