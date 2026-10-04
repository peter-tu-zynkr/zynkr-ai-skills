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
output: "Structured Needs Definition Summary and Strategic Discovery Summary, logged as a [DISCOVERY] meeting on the client's CRM deal, ready for the follow-up and the proposal"
synergy:
  - "sales-research"
  - "project-init"
  - "sales-follow-up"
  - "sales-proposal-writer"
type: agent
skills: ["sales-discovery-pains", "sales-discovery-vision"]
house-style: bound

---

# Sales Discovery

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill sales-discovery
```

Run a two-stage consulting intake before any solution conversation. Stage 1 surfaces the client's pain points and a 5D problem map. Stage 2 zooms out to company vision, product lines, organization, and decision conditions. Use this skill on the discovery call, before any proposal. It produces the discovery summaries and logs them on the client's CRM deal, where the follow-up, the proposal and, once the deal is won, the consulting work pick them up.

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

## Step 4 — Save the summaries on the deal, then hand off

Present both summaries. Then log them on the client's CRM deal, so that the person who follows up,
writes the proposal or runs the consulting work finds them there and not only in this chat:

1. **Find the deal.** Run `mcp__zynkr__list_deals(search="<deal name or 交易 number>")`. The search
   matches the deal's name and number only, not the company field, but deal names usually start
   with the company name. Confirm the match with the user by company and contact, and read it with `mcp__zynkr__get_deal(id=…)`. This skill
   never creates a deal; Sales opens it (`/sales-inbound`, `/sales-outbound`). If there is no deal,
   say so, print the summaries, and skip to the hand-off.
2. **Log the call as a meeting.** Call `mcp__zynkr__log_meeting(deal_id=…, subject="[DISCOVERY] 痛點與願景摘要",
   body=…, occurred_at=<when the call happened, ISO 8601>)`. The deal is the only parent. Preview it, show
   the user the preview, and re-call with `confirm:true` only after they agree.
   - Pass `occurred_at` whenever the call was not today.
   - The body is `STAGE1_SUMMARY` under 「痛點（需求定義）」, then `STAGE2_SUMMARY` under 「願景（策略探索）」, in the
     client's language and exactly as the user agreed them.
   - If only one stage ran, log that one and say which.
3. **Use a meeting entry and nothing else.** Never write the summaries into the deal's `notes` field. Other
   skills parse its link lines (`專案資料夾：<url>`, `部署紀錄（<SPEC_ID>）：<url>`), and `update_deal`
   replaces the whole field. Never use the description either, which is not shown on the deal. The call
   happened, so log it as a meeting, not a note.
4. **Say what was saved:** the subject, the date, and the deal it went on. No tool reads a deal's timeline
   back yet (`get_deal` returns the fields only), so the next skill does not see this entry on its own.
   Hand the summaries on in the same conversation, or tell the user they are on the deal's timeline.

Then ask:

```
Discovery saved to the deal. Next step options:
1. Follow up after the call — /sales-follow-up drafts the reply and brings the deal up to date
2. Write the proposal — /sales-proposal-writer prices what the client asked for
3. Validate specific pain points — re-enter Stage 1 with a different angle
4. Schedule a human consulting follow-up — contact <your-company-contact-email>
```

When handing to `/sales-follow-up`, tell it that this call is already logged on the deal as a
`[DISCOVERY]` meeting, so it skips its own `[DEMO]` note and the call lands on the timeline once.

Process mapping and redesign come after the deal is won. They belong to the consulting and
operations-transformation teams, not to this hand-off.

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
