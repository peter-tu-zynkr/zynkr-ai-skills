---
name: ops-transformation
sheetId: "3.10"
description: "Three-stage operations transformation pipeline — process discovery (SIPOC), digital transformation assessment, then automation-ready process redesign — to turn pain points into builder-ready blueprints. Client work runs it twice: `assess` (stages 1–2, during Consult) files an [Assessment] in the client's folder, and `redesign` (stage 3, after the client signs the BRD) files the [Blueprint] the PRD is written from."
category: operations
project: ops-transformation
platform: claude
status: Done
visibility: public
author: Peter Tu
input: "A business process to fix: for assess, the pain point plus the client's CRM deal; for redesign, the client's filed [Assessment] and signed [BRD]"
process: "Pick the entry point → resolve the client folder → Stage 1 SIPOC → Stage 2 diagnosis and gaps (assess files these) → Stage 3 step cards, store directory, MVP stack (redesign files these) → note the CRM deal"
output: "An [Assessment] Doc and a [Blueprint] Doc in the client's [N] folder, noted on the deal; with no client, the same content in chat"
synergy:
  - "ops-flow-optimization"
  - "ops-workflow-design"
  - "consult-brd-writer"
  - "ops-prd-writer"
type: agent
skills: ["operations-process-discovery", "operations-automation-validation", "operations-process-redesign"]
house-style: bound

---

# Ops Transformation

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill ops-transformation
```

Turn an inefficient business process into a builder-ready automation blueprint through three sequential stages. Use this skill after `sales-discovery` (or whenever you already have a clear pain point) and you want to design the operational fix end-to-end before handing to an engineer.

**Every process step this skill shows uses the shared process step card** (`references/process-step-card.md`): a number, its Input · Process · Output, and — once the step touches a system — its layer, the data stores it Reads and Writes, and the knowledge sources it relies on, with their links (`none` when it uses none). Data and knowledge both sit in the bottom lane, the same split `ops-workflow-design` draws and Atlas workflows use. The point is that a reader never has to cross-reference a SIPOC table against a separate architecture table to learn whether a step needs the database, or what it must know. Stage 1 numbers the steps; every later stage keeps those numbers, and sub-tasks number beneath them (step 3 → 3.1, 3.2).

---

## Step 0 — Pick the entry point

A client engagement runs this skill twice, once on each side of the BRD sign-off: Consult agrees the problem with the client, and Ops transformation designs the fix once the client has signed it.

| Entry point | When | Runs | Files in the client's `[N]` folder | Next |
|---|---|---|---|---|
| `assess` | During Consult, before the BRD | Steps 1–3: Stage 1 SIPOC, Stage 2 diagnosis and gaps | `[Assessment] <Company> — <Process>` | `/consult-brd-writer` uses its numbered as-is steps; after the client signs, `redesign` |
| `redesign` | After the client signs the BRD | Reads the `[Assessment]` and the `[BRD]` back, then Steps 4–5: Stage 3 and the final blueprint | `[Blueprint] <Company> — <Process>` | `/ops-workflow-design` draws it; `/ops-prd-writer` writes the PRD from the BRD and this blueprint |
| none | Internal work, or a one-sitting run | Steps 1–5 in one sitting | Nothing; for a client, run `assess` and `redesign` instead | — |

Read the entry point from the invocation (`/ops-transformation assess …`, `/ops-transformation redesign …`) or from the ask ("diagnose the client's quoting process" → `assess`; "the BRD is signed, design the fix" → `redesign`). For a client, ask once if it is unclear.

The two documents carry the work across the sign-off, so the step numbers issued in the `[Assessment]` are the same in the BRD, the `[Blueprint]`, the Lucid chart and the PRD.

**Fixed facts** (client runs):
- **Google account** for all Drive and Docs tools: `<your-google-workspace-account>`
- **Projects parent folder** (where the numbered `[N]` client folders live): `1hkXPX7OXPFOU0BcloPbJSFp8O0zArM8t`
- **CRM deal URL**: `https://platform.zynkr.ai/deals/{deal_id}`

---

## Step 1 — Collect inputs

Ask the user for:
1. **Pain-point description** — the inefficient or unclear process to redesign
2. (Optional) `STAGE1_SUMMARY` / `STAGE2_SUMMARY` from `sales-discovery` if available
3. The business outcome they want from the transformation (cost / speed / quality / scale)

Store as `PROCESS_BRIEF`.

For a client run, also get the CRM deal URL or the company name, and resolve the client folder now (Step 6, Resolve), so a missing workspace stops the run before any interviewing.

---

## Step 2 — Stage 1: Process Discovery / SIPOC mapping (subagent)

Display:

```
---------------------------------------------
Stage 1: Process Mining — build the SIPOC map
---------------------------------------------
```

Launch the `operations-process-discovery` agent (`./agents/operations-process-discovery.md`) using the Agent tool, passing `PROCESS_BRIEF` and the absolute path of this skill's `references/process-step-card.md` (every agent launch below passes the same path; each agent also carries the rules it needs inline, so a run still works if the file cannot be read).

The agent walks through:
1. End-to-end process mapping (main stages, owners, where each step happens today) — steps numbered 1, 2, 3…
2. Supplier and Customer per step (one question at a time)
3. Agent-generated Input/Output assumptions, and Systems today where the client did not say (marked `(assumed)`)

Store the final numbered SIPOC table (`| # | Supplier | Input | Process | Output | Customer | Systems today |` — the as-is form of the step card) as `SIPOC_TABLE`.

Ask:
```
Does this SIPOC map look right? (Yes / Adjust)
```

> **Optional Stage 1.5 — quick lean pass on a tangled as-is.** If `SIPOC_TABLE` is too messy to diagnose (duplicated steps, unclear loops), you may invoke `ops-flow-optimization` here for a quick cleanup before Stage 2. Its cleaned, renumbered SIPOC (Supplier · Customer · Systems today carried through) **replaces** `SIPOC_TABLE`, and its numbers are the step ids from then on. The canonical ordering pass, however, runs AFTER Stage 3 — see Stage 3.5 below (course Ch5 §5.5.2: assess first, redesign, then optimize the ordering of the re-chained flow).

---

## Step 3 — Stage 2: Digital Transformation Assessment (subagent)

Display:

```
---------------------------------------------
Stage 2: Diagnose automation suitability
---------------------------------------------
```

Launch the `operations-automation-validation` agent (`./agents/operations-automation-validation.md`), passing `SIPOC_TABLE`.

The agent will produce:
- **Diagnostic table** per step, keyed by the Stage 1 step number — Classification (four quadrants), Tech suggestion (LLM / State Machine / Rule-based / Human) with the layer it becomes (Backend · AI / Backend · rules / Backend · human), ROI, Gaps, Rationale
- **Recommendation summary** — which steps to transform now, which to defer
- **Gaps to raise with the client** — per step, the two gaps clients rarely see on their own: knowledge that should be pulled out of the step into a source it reads (RAG when it is searched by meaning, codified rules or a table when it is applied exactly), and data the step needs but is not connected to. One line each, with a link when the canonical source is known (`references/process-step-card.md` §7)
- A hand-off prompt to Stage 3

Store as `DIAGNOSTIC_RESULT`.

Show the gaps to the user before anything else — they are often the most useful finding for the client.

**`assess` ends here.** File the `[Assessment]` (Step 6, template `references/assessment-template.md`) and hand off: `/consult-brd-writer` takes its as-is flow with the same step numbers, and once the client signs the BRD, `/ops-transformation redesign` continues from it. Do not start Stage 3 in an `assess` run; the redesign waits for the scope the client signs.

Otherwise ask which steps to redesign. Default: all steps marked ROI=High or ROI=Medium.

---

## Step 4 — Stage 3: Process Redesign (subagent)

Display:

```
---------------------------------------------
Stage 3: Redesign — sub-tasks, layers, MVP stack
---------------------------------------------
```

**`redesign` starts here.** Find the `[Assessment]` and the `[BRD]` in the client folder (Step 6, Resolve; list it with `mcp__google-workspace__list_docs_in_folder`) and read both with `mcp__google-workspace__get_doc_as_markdown`. Load `SIPOC_TABLE` from the Assessment's section 1 and `DIAGNOSTIC_RESULT` from its sections 2 and 4. Stage 3 trusts that output and does not re-diagnose (Rules). Take the scope from the BRD: redesign the steps its in-scope requirements touch, and leave its 不做什麼 list out. Read its 三、目標流程 too: those numbered to-be steps are what the client signed, so hand each in-scope step's signed to-be lines to the agent with their numbers, and the agent keeps them. Confirm the step list once before the first agent launch.
- **No `[Assessment]` in the folder** → run Steps 1–3 now, seeding Stage 1 with the BRD's numbered 二、現況流程 so its step numbers stay, file the Assessment (Step 6), then continue.
- **The BRD is still a draft** (its version line is `v0.x`, not `v1.0` or later) → say so and ask whether to go on; the redesign normally waits for the client's signature.
- **More than one `[Assessment]`** (one per process) → ask which; never guess.

For each selected step from `DIAGNOSTIC_RESULT`, launch the `operations-process-redesign` agent (`./agents/operations-process-redesign.md`) one step at a time, passing that step's diagnostic row and its gap lines.

Per step, the agent produces:
- Step title, with its Stage 1 number
- **Sub-task cards** — one per sub-task, numbered under the step (3.1, 3.2…): trigger · layer (Front end / Backend · human / Backend · rules / Backend · AI), Input · Process · Output, Reads and Writes (`none` when the sub-task touches no store), Knowledge — each source retrieved or enforced, new or exists, with its link, `link needed`, or `to write` for a new source (`none` when it needs none) — suggested Tool
- Stores touched — each data store and knowledge source the cards name, `(new)` or `(exists)`, with the sub-tasks that write and read it
- Gaps closed — each gap Stage 2 called out on the step, and the card that closes it or why it waits
- Flow type (Sequential / Decision Tree / Loop / Human-in-the-loop)
- MVP stack recommendation
- 1–3 sentence summary

After each step, ask:
```
Would you like to redesign the next diagnosed step? (Yes / Skip / Stop)
```

> **Optional Stage 3.5 — streamline the redesigned flow (course Ch5 §5.5.2).** Once Stage 3 has re-chained the steps, run the lean ordering pass on the redesigned flow before building anything: validate I→P→O on every step, map dependencies, eliminate friction (duplicative / looping / missing steps), and re-sequence only where it buys less rework, lower risk, or higher throughput. Invoke `ops-flow-optimization` on the **whole to-be flow** — the Stage 3 sub-task cards plus the steps kept as is (Step 5 item 3), in flow order — so it renumbers one flow (keeping parent numbers) rather than a fragment that would collide with the untouched steps; its spine is the final "ideal flow" for the MVP build. The principle: **eliminate before you automate** — don't build steps a lean pass would have deleted.

---

## Step 5 — Final blueprint

Compile all step redesigns into a single deliverable:
1. Numbered SIPOC map with Systems today (Stage 1) — the as-is
2. Diagnostic table, same step numbers (Stage 2)
3. **The redesigned flow** — every step in flow order as a step card, so each one shows its Input · Process · Output and its layer · Reads · Writes · Knowledge in one place. Do not re-split it into a separate layer table.
   - Redesigned steps: their sub-task cards from Stage 3 — or, if Stage 3.5 ran, the cards of the `ops-flow-optimization` spine, with **its** numbers (the last pass that renumbered wins; carry its `old → new` map).
   - Steps not chosen for redesign: a card marked `kept as is` — Input · Process · Output from Stage 1, `Layer: kept as is (manual today)`, and Reads / Writes / Knowledge taken from its Systems today — so the flow has no holes and the store directory counts the systems those steps still touch (`references/process-step-card.md` §5).
4. **Store directory** — the bottom lane, once: every data store any card names (`(new)` / `(exists)`, what it holds, written by · read by, join key, columns for new stores), then every knowledge source (retrieved / enforced, `(new)` / `(exists)`, read by, maintained by, its link, who keeps it current) — merged from the agent's "Stores touched" lists (`references/process-step-card.md` §4). If Stage 3.5 ran, rewrite every step number in the directory through its `old → new` map, so each one still exists in item 3. Say so for each finding: a store nothing writes or nothing reads, a source with `link needed` or no owner, a `(new)` source that has to be written first
5. Consolidated MVP stack (deduped across steps)
6. **Gaps** — every knowledge and data gap Stage 2 called out, and the card that closes it, or why it waits. If Stage 3.5 ran, apply its `old → new` map to the closing cards and check each one still exists; a gap whose card was merged away goes back to "waits". This is the list to walk the client through: what the process needs to know, and what it needs to see, that it has no direct line to today

These step numbers are the ids `ops-workflow-design` puts on the Lucid nodes, so the chart and this blueprint can be read side by side.

**`redesign` files this as the `[Blueprint]`** (Step 6, template `references/blueprint-template.md`), then hands off: `/ops-workflow-design` draws the to-be chart with these step numbers, and `/ops-prd-writer` writes the PRD from the signed BRD and this blueprint.

For a run without a client, ask:
```
Next steps:
1. Hand off blueprint to engineering team
2. Iterate on a specific step
3. Schedule a build session with <your-company-contact-email>
```

> **`<your-company-contact-email>` is a company fact — read it from Atlas** (`get_knowledge`, key `company.contact-email`, on the `zynkr-atlas` MCP server; the value is the `value:` line). If Atlas cannot be reached, the key is missing, or there is no `value:` line, ask for it; never run with the blank still in it.

---

## Step 6 — File it in the client folder (`assess` · `redesign`)

Design work kept only in chat never reaches the BRD, the PRD or the client folder. Both entry points file a Google Doc in the client's numbered `[N]` folder and leave a note on the CRM deal.

**Resolve** (once per run, before any interviewing):
- **Deal** — from a `…/deals/{id}` URL, or by company name: `mcp__zynkr__get_deal` / `mcp__zynkr__list_deals`.
- **Folder** — the deal's `notes` may carry a `專案資料夾：<url>` backlink; take the folder id from it. Otherwise list the projects parent (`mcp__google-workspace__list_drive_items`, folder_id `1hkXPX7OXPFOU0BcloPbJSFp8O0zArM8t`) and match `[N] Company（…）` by company name.
- **No folder** → stop. The client has no project workspace yet: open it first with `/project-init` (client project), which opens it from the qualified CRM deal. Never create a folder here.

**Fill the template** — `references/assessment-template.md` or `references/blueprint-template.md`. Fill every placeholder, keep the numbered section headings (`redesign`, `/consult-brd-writer` and `/ops-prd-writer` read them back), and delete every `<!-- … -->` comment, the contract at the top included.

**Create the Doc in one call**, so the Markdown headings, lists and tables arrive formatted:

```
mcp__google-workspace__import_to_google_doc(
  user_google_email = "<your-google-workspace-account>",
  file_name     = "[Assessment] {{COMPANY}} — {{PROCESS}}",   # or "[Blueprint] {{COMPANY}} — {{PROCESS}}"
  content       = "<filled template>",
  source_format = "md",
  folder_id     = "<the [N] folder id>"
)
```

Never use `create_doc(content=…)` for these documents: it inserts plain text, so every `#`, `|` and `**` would show up literally.

**Then set the exact title.** The import cuts a title at its last ASCII `.` (it treats the rest as a file extension: `Acme Corp. — Quoting` arrives as `Acme Corp`), so rename the new Doc right away: `mcp__google-workspace__update_drive_file(user_google_email=…, file_id="<new id>", name="<the exact title>")`. The re-run check below matches on that title.

**A re-run replaces the document in place.** If the folder already holds a document with the same title, overwrite its content instead of adding a second one, so every link to it keeps working: `mcp__google-workspace__update_drive_file(user_google_email=…, file_id="<existing id>", content="<filled template>", source_format="md")`.

**Note the deal.** `mcp__zynkr__create_note(deal_id="<deal_id>", subject="…", body="…", confirm=true)`. Call it once without `confirm` to preview, then with `confirm=true`. Only the body shows on the deal, so put the title and the link there: `[Blueprint] 宏宇精密 — 報價流程：<doc url>`.

Report the document link, the folder, and the next step from the Step 0 table.

---

## Rules

- Stage 1 may ask discovery questions, but Stage 2 and Stage 3 must trust prior agent output — no re-diagnosing
- Always one question at a time during Stage 1
- Diagnostic table classifications are advisory; flag low-ROI steps but do not auto-skip them
- Never recommend LLM-only solutions for rule-based, low-frequency steps (cost mismatch)
- Every step shown carries its number and Input · Process · Output; every redesigned (to-be) step also carries its layer and Reads / Writes / Knowledge, with `none` written out rather than left blank (`references/process-step-card.md`)
- Knowledge is a source in the bottom lane, never a loose note. Link it only when the client, the context or Atlas gave you the canonical source; otherwise write `link needed`, or `to write` for a `(new)` source — never invent a link, and never invent an owner
- Every gap Stage 2 calls out ends up in the blueprint's Gaps list, closed by a card or marked with why it waits — never dropped silently
- Keep the step numbers stable across all stages; if a step is added, merged or dropped, renumber under the same parent and give the `old → new` map in one line (`references/process-step-card.md` §1)
- A client run files its result: `assess` ends with the `[Assessment]`, `redesign` with the `[Blueprint]`, each in the client's `[N]` folder and noted on the deal (Step 6). Never leave client work only in chat, and never create a client folder

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
