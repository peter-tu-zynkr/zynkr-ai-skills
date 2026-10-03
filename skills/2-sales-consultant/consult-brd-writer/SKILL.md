---
name: consult-brd-writer
sheetId: "2.12"
description: >-
  Turn a consulting engagement's discovery material into the BRD the client
  signs: a business-facing zh-TW requirements Google Doc in the client's
  numbered [N] Drive folder, backlinked to the CRM deal. It reads
  sales-discovery summaries, shadowing transcripts, session notes and the
  [Assessment] from /ops-transformation assess.
  Trigger on /consult-brd-writer or when Peter says "幫我寫 BRD",
  "把訪談整理成需求文件", "把 shadowing 筆記變成需求文件", "draft the BRD", or
  hands over discovery notes or a transcript wanting a requirements document
  out of it — fire eagerly even if he never says the letters "BRD". Distinct
  from sales-discovery (CONDUCTS the interviews; this skill consumes their
  output), from project-init (opens the project folder at qualified, writes no
  requirements doc), and from ops-prd-writer (writes the
  buildable PRD once the client has signed THIS skill's BRD).
category: sales-consultant
project: consult-brd-writer
platform: claude
status: Done
visibility: public
author: Peter Tu
input: "Discovery summaries, session notes or a shadowing transcript, the [Assessment] from /ops-transformation assess if filed, and the client's CRM deal URL or company name"
process: "Acquire sources → extract as-is / to-be / requirements → outline approval gate → generate from the BRD template → create the Google Doc in the client's [N] folder → backlink to the CRM deal → report"
output: "A client-grade [BRD] Google Doc in the client's [N] folder; once the client signs it, ops-prd-writer turns it into the PRD"
synergy:
  - "sales-discovery"
  - "project-init"
  - "consult-shadowing-scheduler"
  - "ops-transformation"
  - "ops-prd-writer"
house-style: bound

---

# Consult BRD Writer

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill consult-brd-writer
```

By the time discovery is done, an engagement has a pile of raw material —
sales-discovery summaries, shadowing transcripts, recording notes, session
notes, the as-is assessment — but nothing a client can sign. This skill turns the
pile into the document the engagement runs on: a **BRD** (business-facing, zh-TW),
created in the client's numbered `[N]` Drive folder and backlinked to the deal.
When the client signs it, the Ops transformation team takes over:
`/ops-transformation redesign` designs the fix, and `/ops-prd-writer` turns the
signed BRD into the buildable spec.

It is deliberately **not** autonomous end-to-end: requirements docs get signed by
clients, so it stops at an outline gate (step 3) — Peter approves the skeleton
first, the prose second.

## How this differs from its neighbours

- **sales-discovery** — CONDUCTS the pain-point / vision interviews and produces
  the discovery summaries. This skill sits downstream and consumes them.
- **project-init** — opens the client's project folder at qualified (or reuses the
  inbound one), no requirements doc; it creates the workspace this skill writes INTO.
- **ops-transformation** — its `assess` entry point files an `[Assessment]` during
  Consult: the numbered as-is process, the diagnosis and the knowledge and data
  gaps. This skill takes the BRD's as-is flow from it, keeping the step numbers.
- **ops-prd-writer** — downstream: once the client signs this BRD, it writes the
  buildable PRD from the BRD and the redesign blueprint. (PRD mode used to live
  in this skill.)

## Fixed facts (don't re-derive these)

- **Google account** for all Gmail/Drive/Docs tools: `<your-google-workspace-account>`
- **Drive parent folder** (`[2.2] 業務與顧問部門：專案`, where numbered project folders live): `1hkXPX7OXPFOU0BcloPbJSFp8O0zArM8t`
- **CRM deal URL** for the doc/report/backlink: `https://platform.zynkr.ai/deals/{deal_id}`

## Hard rules

1. **Never create a competing folder.** If the client has no `[N]` folder yet, STOP
   and route to /sales-inbound (inbound lead) or /project-init (qualified deal); see step 1.
2. **Never generate the full document before the step-3 gate is approved.**
3. **Client-facing email is ALWAYS a Gmail draft** — if Peter asks to send the doc
   to the client, use `mcp__google-workspace__draft_gmail_message`. Never send.

---

## Workflow

### 1 · Acquire the sources and resolve the client workspace

Discovery material can arrive three ways:

- **Pasted text** — use it directly.
- **A Google Doc / Gemini Notes link** — read with
  `mcp__google-workspace__get_doc_content(user_google_email="<your-google-workspace-account>", document_id="<id>")`.
  Gemini Notes docs have a `Notes` tab (summary + action items) and a `Transcript`
  tab (verbatim) — read both; the transcript carries the real detail.
- **Multiple sources** — read all of them; they cross-validate each other in step 2.

**Huge transcripts:** a multi-hour shadowing transcript will not survive one-pass
extraction. Read it in sections, summarize each section into *process segments*
(actor · step · tool · pain · quote), then merge the segment summaries before
step 2. Extract from the merged segments, not from raw text.

Then resolve the CRM deal and the Drive folder:

- **Deal** — from a `…/deals/{id}` URL, or by company name. Prefer
  `mcp__zynkr__get_deal` / `mcp__zynkr__list_deals`
- **Folder** — the deal's `notes` carry a `專案資料夾：<url>` backlink (written by
  sales-inbound / project-init); extract the folder id from it. If
  missing, list the parent (`mcp__google-workspace__list_drive_items`, folder_id
  `1hkXPX7OXPFOU0BcloPbJSFp8O0zArM8t`) and match `[N] Company（…）` by company name.
- **No folder at all** → STOP. Tell Peter this client has no project workspace yet
  and point at /sales-inbound (inbound lead) or /project-init 客戶案 (qualified
  deal). Hard rule 1: never create a competing folder.

Finally, list the folder
(`mcp__google-workspace__list_docs_in_folder(user_google_email="<your-google-workspace-account>", folder_id="<folder id>")`)
and look for an **`[Assessment]`** filed by `/ops-transformation assess`. If there is one,
read it with `mcp__google-workspace__get_doc_as_markdown`: its section 1 is the numbered
as-is process (Supplier · Input · Process · Output · Customer · Systems today), and its
section 4 lists the knowledge and data gaps. An existing **`[BRD]`** in the folder means
this run revises it (step 4).

### 2 · Extract the skeleton

From the merged sources, pull the document's bones — with a source tag on every
claim (which interview / transcript section it came from):

- **Stakeholders** — who appeared, role, what they own in the process.
- **As-Is flow** — the current process as numbered steps, one line each: input →
  process → output, and the system or person the step runs on today. When an
  `[Assessment]` is filed, take its section 1 steps with their numbers instead of
  re-deriving them, and say where the discovery material adds to them or
  contradicts them. Those numbers then stay the same in the redesign blueprint, the
  Lucid chart and the PRD.
- **To-Be flow** — the target process the client agrees to, numbered the same way
  (a new step goes under the step it belongs to: 3.1, 3.2), input → process → output
  on each line, the automated or changed steps marked. Layers and data stores are
  NOT this document's job; `/ops-transformation redesign` adds them after the client
  signs.
- **Pains → numbered requirements** — each pain becomes an `R-n` requirement
  (title · description · 必要/重要/加分 priority · source). Numbers are permanent:
  once issued, never reshuffled. An `[Assessment]` gap the client should hear about
  (knowledge or data the process has no direct line to) is a pain like any other.
- **Scope line** — what's in, and explicitly what's NOT (the 不做什麼 list matters
  as much as the backlog).
- **Success metrics** — baseline → target → how measured.

### 3 · GATE — outline approval

Present, and then **wait**:

1. The proposed document outline (section by section).
2. The numbered requirement list — one line each.
3. **Open questions** — anything the sources left ambiguous, as explicit asks.
4. The proposed title (and, on a revision, what changes from the current version).

Peter replies approve / adjust; re-gate only if the requirement list itself
changed. Hard rule 2: no full-document prose before this gate clears.

### 4 · Generate the Doc into the `[N]` folder

Read `./references/brd-template.md`, fill every placeholder, delete the
placeholder-guide comment block, and create the Doc via the reliable two-step
(creating a Doc directly in a folder via `create_drive_file` returns HTTP 400):

```
## 1. create the doc (lands in My Drive root)
mcp__google-workspace__create_doc(
  user_google_email = "<your-google-workspace-account>",
  title   = "[BRD] {{COMPANY}} — {{PROJECT}}",
  content = "<filled-in template>"
)
## 2. move it into the client's project folder
mcp__google-workspace__update_drive_file(
  user_google_email = "<your-google-workspace-account>",
  file_id     = "<doc id from step 1>",
  add_parents = "<the [N] folder id from step 1 of the workflow>"
)
```

A revision of an existing `[BRD]`, including the bump to `v1.0` when the client
signs, rewrites that document in place instead of creating a second one, so every
link to it keeps working. Fill the template with the new version line, then:
`mcp__google-workspace__update_drive_file(user_google_email="<your-google-workspace-account>", file_id="<existing [BRD] id>", content="<filled-in template>", source_format="txt")`
(the template is styled for plain text, so it goes in as text).

### 5 · Backlink the Doc to the CRM deal (+ offer, don't auto, a stage nudge)

Append the Doc URL to the deal's notes (the same pattern sales-inbound uses):

`mcp__zynkr__update_deal` REPLACES `notes` wholesale, so append in three steps:

1. `mcp__zynkr__get_deal(id="<deal_id>")` — read the current `notes`
2. build the new value: the existing notes, then a blank line, then the block below
3. `mcp__zynkr__update_deal(id="<deal_id>", notes="<combined>", confirm=true)`

Call it once without `confirm` to preview, then again with `confirm=true`. Never
send `notes` without the existing text in front of it — the field is overwritten,
not appended, and skipping the read loses every earlier backlink.

Then **ask** two optional follow-ups — never do them unprompted:

- **Stage nudge** — "A requirements doc exists now; move the deal to `proposal`?"
  Ask only while the deal is still before `proposal`. Under the skill teams the BRD is
  usually written after the deal is won, and moving a `won` deal to `proposal` would move it
  backwards, so never offer it then.
  On yes: `mcp__zynkr__move_deal_stage(id="<deal_id>", stage="proposal", confirm=true)`.
  **Only this tool moves a stage.** Writing the column directly changes the stage
  but skips the `stage_change` timeline entry and the automation event, so the
  move stops being visible to anyone reading the deal afterwards.
- **Review task** — "Log a 客戶審閱 follow-up task?" On yes:
  `mcp__zynkr__create_task(deal_id="<deal_id>", …, confirm=true)`. It is created
  as you, on your workspace — no owner id to look up and none to hardcode.

### 6 · Report

A compact artifact table, then the headline in prose:

```
需求文件已產出：宏宇精密 — 報價流程自動化

| 產出 | 內容 |
|------|------|
| 文件 | [BRD] 宏宇精密 — 報價流程自動化（<doc url>）|
| 資料夾 | [4] 宏宇精密（報價流程自動化）|
| CRM backlink | <deal url> — notes 已附文件連結 |
| 需求數 | R-1 … R-7（必要 4 · 重要 2 · 加分 1）|
| 待 Peter | 2 個 open questions（見上）· stage nudge 未執行 |
```

Then the hand-off: once the client signs (version `v1.0`), the Ops transformation
team continues with `/ops-transformation redesign`, then `/ops-prd-writer`.

---

## Why it's built this way

- **Gate before prose.** sales-inbound runs autonomously because its artifacts
  are cheap and internal; a requirements doc is client-visible and
  quasi-contractual — the gate is where a wrong list is still cheap to fix.
- **The folder is resolved, never created.** One numbered workspace per
  engagement is the invariant the whole 2.x suite leans on; a second folder for
  the same client would fork the record. Hence the hard STOP.
- **One document, one signature.** The BRD is what the client signs. The buildable
  spec belongs to the Ops transformation team and is written after that signature
  (`/ops-prd-writer`), so it never has to be rewritten when the BRD changes before
  sign-off.
- **One set of step numbers.** The as-is steps keep the `[Assessment]`'s numbers, so
  the client, the designer and the builder can point at the same step in the BRD,
  the blueprint, the Lucid chart and the PRD.

## Inference defaults (Peter overrides by just saying so)

- **Doc language** → zh-TW body.
- **Requirement priority** → 必要 only when the client said so or the as-is flow
  breaks without it; otherwise 重要; 加分 for pure nice-to-haves.
- **BRD version** → `v0.1（草稿）`; bumps to `v1.0` on client confirmation.
  `/ops-transformation redesign` and `/ops-prd-writer` read `v1.0` or later as signed.
- **Stage nudge / review task** → OFF; offered in step 5, executed only on a yes.

## Reference files

- `./references/brd-template.md` — the zh-TW client-grade BRD skeleton (fill, then
  delete its placeholder-guide comment).

## Limitations

- Consumes discovery material; it will not interview anyone (sales-discovery)
  or bootstrap a missing workspace (sales-inbound / project-init).
- Requirements come only from the provided sources — thin discovery yields a thin
  BRD with more open questions at the gate; it never invents requirements.
- It writes the BRD only. The buildable PRD is `/ops-prd-writer`'s, after the
  client signs.
- One document per run.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
