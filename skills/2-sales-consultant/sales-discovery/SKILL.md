---
name: sales-discovery
sheetId: "2.06"
description: "Two-stage consulting discovery — pain-point intake then company vision exploration — to produce a needs definition and strategic discovery summary before any solution work."
category: sales-consultant
project: sales-discovery
platform: claude
status: Done
visibility: public
author: Peter Tu
input: "A consulting client (founder, department head, or senior manager) ready to discuss business challenges and company strategy"
process: "Stage 1 pain-point discovery with 5D problem exploration, then Stage 2 vision/strategy/product/organization exploration; one question at a time"
output: "Structured Needs Definition Summary and Strategic Discovery Summary, ready for downstream process mapping or pain-point validation"
synergy:
  - "sales-research"
  - "project-init"
type: agent
skills: ["sales-discovery-pains", "sales-discovery-vision"]
house-style: bound

---

# Sales Discovery

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill sales-discovery
```

Run a two-stage consulting intake before any solution conversation. Stage 1 surfaces the client's pain points and a 5D problem map. Stage 2 zooms out to company vision, product lines, organization, and decision conditions. Use this skill at the very start of a consulting engagement — it produces the discovery summaries that feed downstream operations / transformation work.

---

## Step 1 — Confirm intent and starting point

Ask the user:

```
Where would you like to start?
1. Pain-point discovery (Stage 1) — surface specific operational/process challenges
2. Strategic discovery (Stage 2) — directly explore vision, products, and organization
3. Full discovery (both stages in sequence) — recommended for new engagements
```

If the user is unsure, default to **Full discovery** and run Stage 1 first.

---

## Step 2 — Stage 1: Pain-Point Discovery (subagent)

Display:

```
---------------------------------------------
Stage 1: Pain-Point Discovery (5D framework)
---------------------------------------------
```

Launch the `sales-discovery-pains` agent (`./agents/sales-discovery-pains.md`) using the Agent tool.

The agent will conduct a multi-turn interview through:
1. **Contextualize User Profile** — industry, team size, role, department focus, current challenges
2. **5D Problem Exploration** — Diagnose, Distill, Desire, Drag, Deadline

When the agent produces the **Needs Definition Summary**, store it as `STAGE1_SUMMARY`.

Ask:

```
Does this summary capture your situation accurately? (Yes / Adjust)
- Yes → continue to Stage 2
- Adjust → reopen sales-discovery-pains to refine
```

---

## Step 3 — Stage 2: Strategic Discovery (subagent)

Display:

```
---------------------------------------------
Stage 2: Strategic Discovery (Vision, Product, Org)
---------------------------------------------
```

Launch the `sales-discovery-vision` agent (`./agents/sales-discovery-vision.md`) using the Agent tool, passing `STAGE1_SUMMARY` as context.

The agent will cover four sections:
1. Vision & Strategic Priorities
2. Product Lines & Value Proposition
3. Organization & Execution
4. Decision & Resource Readiness

Store the agent's **Strategic Discovery Summary** as `STAGE2_SUMMARY`.

---

## Step 4 — Hand-off

Present both summaries and ask:

```
Discovery complete. Next step options:
1. Move to process mapping — hand off to `ops-transformation` orchestrator
2. Validate specific pain points — re-enter Stage 1 with a different angle
3. Schedule a human consulting follow-up — contact <your-company-contact-email>
```

> **`<your-company-contact-email>` is a company fact — read it from Atlas** (`get_knowledge`, key `company.contact-email`, on the `zynkr-atlas` MCP server; the value is the `value:` line). If Atlas cannot be reached, the key is missing, or there is no `value:` line, ask for it; never run with the blank still in it. Read it before you launch `sales-discovery-pains` in Stage 1 — that agent's closing offer names the same address, so pass the value in with the launch.

Do not propose solutions inside this skill. Discovery only — downstream agents handle diagnosis, redesign, and implementation.

---

## Rules

- Always one question at a time during interviews
- Always summarize/paraphrase before asking the next question
- Never invent client context
- Output discovery summaries in the client's working language (default zh-TW if unclear)

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
