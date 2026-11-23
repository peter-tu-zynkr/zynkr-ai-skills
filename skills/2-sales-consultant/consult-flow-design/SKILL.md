---
name: consult-flow-design
sheetId: "2.41"
description: >-
  Draw a consulting engagement's operations as a paired AS-IS / TO-BE process
  flow set — written from the engagement's own documents (session notes, 痛點
  ledgers, [Plan] docs, BRD) and recorded back on the CRM deal. ALL flow text,
  drawing, editing, and lint mechanics are delegated to the installed
  ops-workflow-design skill, which files each flow as a Zynkr Atlas workflow
  draft, or renders it as an SVG page drawing when Atlas can't take a draft;
  this wrapper adds engagement resolution, the as-is/to-be pairing discipline,
  flow naming, and CRM linkage. Trigger on /consult-flow-design or when Peter
  says "畫客戶的 as-is/to-be 流程", "客戶流程圖", "幫這個案子畫流程",
  "把客戶流程視覺化", "map the client's operations", "visualize the engagement
  workflow", or "draw the as-is and to-be for this client". Distinct from
  ops-workflow-design (the generic flow specialist — any flow, no engagement
  context; a flow or an Atlas workflow with no client context still routes
  THERE), from consult-solution-planning (produces the [Plan] narrative this
  skill draws), and from ops-flow-optimization / ops-transformation (they
  design the flow's CONTENT; this skill only visualizes what the engagement
  documents already say).
category: sales-consultant
project: consult-flow-design
platform: claude
status: Done
visibility: public
author: Peter Tu
input: "The engagement (deal URL / company name) — source docs are gathered from its [N] folder; optionally the pair's existing Atlas workflows to update"
process: "Resolve engagement + gather [Notes]/[Plan]/[BRD] docs → check ops-workflow-design installed → assemble as-is and to-be narratives (confirm) → delegate flow text + V1–V14 lint + Atlas draft or page drawing per flow → append both links to the deal → report"
output: "A paired [N] {{COMPANY}} — as-is / — to-be flow set on the FE/BE/DB convention, lint-clean, as Atlas workflow drafts or SVG drawings, both links on the CRM deal"
synergy:
  - "ops-workflow-design"
  - "consult-solution-planning"
  - "consult-brd-writer"
house-style: bound

---

# Consult Flow Design

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill consult-flow-design
```

An engagement's documents describe two processes: how the client works today
(session notes, 痛點 ledger 現況流程 fragments) and how they will work after
the build ([Plan] docs, BRD 目標流程). This skill turns those into the
engagement's visual deliverable — a **paired as-is / to-be flow set** with
matching lanes, so the delta reads at a glance — and records both flows'
links on the CRM deal.

It is a **thin delegation wrapper**: every flow mechanic (the flow text, the
FE/BE/DB lanes, Shape × Color encoding, layout, V1–V14 lint, the Atlas draft or
the page drawing) belongs to the installed `ops-workflow-design` skill and is
exercised by invoking it, never by copying it. What this wrapper owns is the
consulting context: which engagement, which documents, the two-flow pairing
discipline, the naming, and the CRM record.

## How this differs from its neighbours

- **ops-workflow-design** — the generic flow specialist: any flow, no
  engagement context. A flow or an Atlas workflow with no client attached
  still routes there. This skill calls it; it never calls this skill.
- **consult-solution-planning** — produces the [Plan] narrative (the to-be in
  prose). This skill sits downstream and DRAWS that narrative.
- **ops-flow-optimization / ops-transformation** — design what
  the flow SHOULD BE. This skill designs nothing: it visualizes what the
  engagement documents already say, and stops when they say too little.

## Fixed facts (don't re-derive these)

- **Google account** for all Gmail/Drive/Docs tools: `<your-google-workspace-account>`
- **Drive parent folder** (`[3.1] 顧問部門：專案 (Project tracking)`, where numbered project folders live): `1hkXPX7OXPFOU0BcloPbJSFp8O0zArM8t`
- **CRM deal URL** for the report/backlink: `https://crm.zynkr.ai/deals/{deal_id}`

## Hard rules

1. **Never draw a to-be without an as-is beside it.** The comparison IS the
   deliverable. If Peter asks for one flow only, explain the pairing
   discipline and proceed single-flow only on an explicit confirm.
2. **Never write or draw a flow yourself.** All flow text, drawing, editing,
   and linting goes through an invocation of /ops-workflow-design. If it's not
   installed, hard-STOP (step 2). Do not re-derive its convention here.
3. **Never create a project folder.** No `[N]` folder ⇒ STOP and route to
   /project-init (it opens the folder once the deal is qualified).
4. **Never draw before the step-3 narrative confirm.** Flows are expensive
   to redo once filed: each Atlas draft waits for a reviewer, and a workflow
   holds one waiting draft at a time.
5. **Client-facing email is ALWAYS a Gmail draft** — if Peter asks to send the
   drawings to the client, draft via
   `mcp__google-workspace__draft_gmail_message`. Never send.
   Pass `body_format="html"` and `include_signature=true` (the body written as plain text, then
   `& < >` escaped and line breaks turned into `<br>`), so the draft carries the sender's Gmail signature.
6. **Approve nothing.** The pair's Atlas drafts wait for a reviewer, who
   decides them in Atlas.

---

## Workflow

### 1 · Resolve the engagement and gather its documents

- **Deal** — from a `…/deals/{id}` URL, or by company name. Prefer
  `mcp__zynkr__get_deal` / `mcp__zynkr__list_deals`
- **Folder** — the deal's `notes` carry a `專案資料夾：<url>` backlink; extract
  the folder id. If missing, list the parent
  (`mcp__google-workspace__list_drive_items`, folder_id
  `1hkXPX7OXPFOU0BcloPbJSFp8O0zArM8t`) and match `[N] Company（…）` by name.
- **No folder at all** → STOP. Point at /project-init 客戶案 (it opens one
  once the deal is qualified). Hard rule 3.
- **Sources** — `mcp__google-workspace__list_docs_in_folder` on the `[N]`
  folder; read whatever exists of `[Notes]` session notes, 痛點 ledger,
  `[Plan]`, `[BRD]` via `mcp__google-workspace__get_doc_content`. If the
  material is too thin to support a flow (no 現況 description, or no 目標
  flow), say exactly what's missing and point at /consult-session-notes or
  /consult-solution-planning — never invent process steps to fill gaps.
- **An earlier pair** — if the deal notes already carry a `流程圖：` block
  whose links are Atlas workflows or SVG paths, this run updates that pair
  (step 4) rather than drafting a new one. A block whose links are
  `lucid.app` was recorded before Lucid was retired: there is nothing to
  update, so draft a new pair from the sources, and step 6 writes the new
  links over the retired ones. A block with one Atlas or SVG link and one
  retired `lucid.app` link updates the first (step 4) and draws only the
  other flow new; step 6 writes its link over the retired line.

### 2 · PRECONDITION — is ops-workflow-design installed?

Check the available-skills listing for `ops-workflow-design`. If absent,
hard-STOP and print its install snippet so Peter can install it — the same
command as this skill's own (top of this file) with
`--skill ops-workflow-design` instead. Nothing downstream works without it;
do not attempt to draw directly as a fallback (hard rule 2).

### 3 · Assemble the two process narratives — and confirm

From the gathered sources, write two ordered step lists (not flows — prose
narratives the base skill can draw from):

- **as-is** — from the 現況 material: session notes, ledger 現況流程
  fragments. Every step: actor · action · tool, plus a layer hint where the
  sources make it obvious (front-end touchpoint / manual vs system step /
  what gets stored where).
- **to-be** — from the 目標 material: the [Plan] doc, the BRD's target flow.
  Same actor vocabulary and the same kinds of step as the as-is, so the two
  flows share their lanes and the delta is visible, not just implied.
- Tag each step with its source doc — if a step appears in neither, it
  doesn't go in the narrative.

Present both narratives side by side for a quick confirm **before any
drawing** (hard rule 4). Peter adjusts in text, which is cheap; re-drafts are
not. In the same message, ask where the pair goes: "Both into Atlas as
workflow drafts?" — ops-workflow-design files an Atlas draft only on the
user's word. The client runs both flows, so both qualify; without the Atlas
tools, or with a token that may not draft, both become page drawings.

### 4 · Delegate the flow text and its lint

For each confirmed narrative, **run /ops-workflow-design's DRAFT job**,
passing:

- the narrative (ordered steps with actor/tool/layer hints),
- the exact flow title — `[N] {{COMPANY}} — as-is` then
  `[N] {{COMPANY}} — to-be`, where `[N]` is the engagement's Drive folder
  number (so flow and workspace pair by eye) — and, for Atlas, two slugs on
  one stem (`<N>-<company>-as-is`, `<N>-<company>-to-be`, in lowercase latin
  letters, digits and dashes),
- the instruction that both flows use the same actor vocabulary, the same
  `executed_by`, and the same step kind for the same kind of work. The lanes
  then line up by themselves: they always run FE · BE · DB, and a lane row
  with no step in it is left out, so a row that shows in one flow and not
  the other is part of the delta,
- Peter's answer from step 3: Atlas drafts, or page drawings.

The base skill owns everything visual: the flow text, the step kinds and
their Shape × Color encoding, the register, the lint, and the look at a page
drawing. Do not second-guess its shape or color decisions here. If the deal
notes already carry the pair (Atlas or SVG links, step 1), or Peter names an
existing Atlas workflow, delegate its **EDIT** job against that workflow
instead of drafting a new one.

### 5 · Relay the lint verdict — before anything is filed

/ops-workflow-design lints each flow (rules V1–V14) before it files the
Atlas draft or renders the page drawing, and fixes the text until the flow
comes back clean (an update of an earlier pair: until the edit adds no
finding the flow did not already have). Both flows must be clean before either is filed: a fix
after filing is another draft for a reviewer. This wrapper never lints by
itself — it only relays the base skill's verdict.

What comes back for each flow: the Atlas review link and the workflow's own
page (`…/w/<workspace>/workflows/<slug>`), or the SVG path.

### 6 · Record the flow links on the deal

Append both links to the deal notes with `mcp__zynkr__update_deal`
(read current notes first, append, write back): the Atlas workflow page for
an Atlas draft — it keeps its address once the draft is published — or the
SVG path for a page drawing.

`mcp__zynkr__update_deal` REPLACES `notes` wholesale, so append in three steps:

1. `mcp__zynkr__get_deal(id="<deal_id>")` — read the current `notes`
2. build the new value: the existing notes, then a blank line, then the block below
3. `mcp__zynkr__update_deal(id="<deal_id>", notes="<combined>", confirm=true)`

The block:

```
流程圖：
as-is：<Atlas workflow link or SVG path>
to-be：<Atlas workflow link or SVG path>
```

Call it once without `confirm` to preview, then again with `confirm=true`. Never
send `notes` without the existing text in front of it — the field is overwritten,
not appended, and skipping the read loses every earlier backlink. An update
of an earlier pair keeps its block: the workflow pages don't move. A block
of retired `lucid.app` links is not appended to: in step 2 of the three, write
the new links over its `as-is：` and `to-be：` lines, or over the one retired line
when the other already links Atlas or an SVG, so the deal keeps one
`流程圖：` block and no dead link.

### 7 · Report — and offer, don't auto, the next step

A compact artifact table, then the delta in one sentence:

```
流程圖已產出：宏宇精密 — 報價流程自動化

| 產出 | 內容 |
|------|------|
| as-is | [4] 宏宇精密 — as-is（<Atlas workflow link>）· lint clean · 等候審核 |
| to-be | [4] 宏宇精密 — to-be（<Atlas workflow link>）· lint clean · 等候審核 |
| CRM backlink | <deal url> — notes 已附兩張圖連結 |
| 差異一句話 | 報價計算與追蹤信從人工（3 個 HITL 步驟）改為系統自動，人只留最終核准 |
```

For page drawings, each row carries the SVG path instead, and says the file
is on this machine. Then **ask** — never do unprompted: a proposal deck from
the pair (via /zynkr-slide), or /consult-brd-writer if the engagement has no
BRD yet.

---

## Why it's built this way

- **Delegation, not a fork.** The FE/BE/DB convention is a living standard —
  its reference files, its kit and a V1–V14 lint that ops-workflow-design
  updates in one place. A copied-in version would drift the first week; a
  wrapper that invokes the installed skill inherits every improvement for
  free.
- **The pair is the deliverable.** A to-be alone is a proposal sketch; an
  as-is beside it, same lanes, is an argument. Consulting clients buy the
  delta — hence hard rule 1 and the shared-lane requirement in step 4.
- **Confirm narratives, not drafts.** Text is the cheapest medium to be wrong
  in. A filed draft waits for a reviewer, and a workflow holds one waiting
  draft at a time, so a wrong flow costs a review round and a new version —
  the step-3 gate spends minutes to save one.
- **Named after the workspace.** `[N]` in the flow titles mirrors the Drive
  folder number, so the flow set, the folder, and the deal cross-reference
  without a registry.
- **Sources over invention.** The moment this skill invents a process step,
  it stops being documentation and starts being (unreviewed) consulting.
  Content design belongs to consult-solution-planning and the operations
  skills; thin sources here mean STOP, not improvise.

## Inference defaults (Peter overrides by just saying so)

- **Where the pair goes** → Atlas workflow drafts, on Peter's yes at step 3;
  page drawings when the Atlas tools can't draft.
- **Flow set shape** → two separate flows: two workflows in Atlas, or two SVG
  files. Never one flow holding both.
- **Register** → clean for page drawings (these face the client); audit on
  request. Atlas's canvas draws its own way.
- **Step-title language** → zh-TW, matching the engagement documents; a page
  drawing renders with `--lang zh-TW`.
- **`[N]`** → the engagement's Drive folder number, read in step 1.
- **New vs update** → new drafts; the EDIT job only when the deal notes
  already carry the pair (Atlas or SVG links; a pair of retired `lucid.app`
  links is drawn new, and a retired `lucid.app` link beside an Atlas one
  draws only its own flow new) or Peter names an existing workflow.
- **Handoffs (deck / BRD)** → OFF; offered in step 7, run only on a yes.

## Provenance

Wraps `ops-workflow-design` (5.03) 2.0.0 by delegation (2026-11-18) — flow
text in, an Atlas review link or an SVG path back; no mechanics copied;
breaks only if that contract changes.

## Reference files

None shipped — deliberately. The FE/BE/DB three-layer model, the Shape ×
Color encoding table, the flow-text scaffold, and the V1–V14 lint rules live
single-sourced in ops-workflow-design's own reference files and kit; this
wrapper invokes that skill rather than mirroring its knowledge, so there is
nothing local to drift.

## Limitations

- Visualizes documented state only — it will not design, optimize, or extend
  a flow (operations skills / consult-solution-planning), and it will not
  interview anyone to fill gaps.
- Flow quality is bounded by document quality: thin `[Notes]`/`[Plan]`
  material yields a STOP-and-route, not a speculative flow.
- Unusable without ops-workflow-design installed — every flow, draft and
  drawing goes through it, including lint verdicts this wrapper merely
  relays.
- Files drafts, never approves them: the pair is live in Atlas only once a
  reviewer decides it there.
- One engagement per run; a portfolio-wide sweep is repeated runs.
- Records links on the deal but never emails the client — sharing is always a
  Gmail draft Peter sends himself.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
