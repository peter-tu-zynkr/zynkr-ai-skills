---
name: sales-discovery
sheetId: "2.06"
description: "Two-stage consulting discovery — pain-point intake then company vision exploration — to produce a needs definition and strategic discovery summary before any solution work. Runs as a live interview on the call, or after the call straight from a transcript, a Google Doc or handwritten notes."
category: sales-consultant
project: sales-discovery
platform: claude
status: Done
visibility: public
author: Peter Tu
input: "A consulting client (founder, department head or senior manager) ready to discuss challenges and strategy, or the transcript, Doc or notes of a discovery call already held"
process: "Live: Stage 1 pain-point discovery with 5D problem exploration, then Stage 2 vision/strategy/product/organization exploration, one question at a time. After the call: both summaries written from the record, with no interview"
output: "Needs Definition and Strategic Discovery summaries, logged as a [DISCOVERY] meeting on the client's CRM deal, with the deal's 資格 line filled from what was said"
synergy:
  - "sales-research"
  - "project-init"
  - "sales-follow-up"
  - "sales-proposal-writer"
type: agent
skills: ["sales-discovery-pains", "sales-discovery-vision"]
reads: ["company.crm-tag-rules", "company.sales-pipeline-rules"]
house-style: bound

---

# Sales Discovery

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill sales-discovery
```

Run a two-stage consulting intake before any solution conversation. Stage 1 surfaces the client's pain points and a 5D problem map. Stage 2 zooms out to company vision, product lines, organization, and decision conditions. Use this skill on the discovery call, or after it with the record of the call, and always before any proposal. It produces the discovery summaries and logs them on the client's CRM deal, where the follow-up, the proposal and, once the deal is won, the consulting work pick them up.

---

## Step 1 — Confirm intent and starting point

Ask the user:

```
Where would you like to start?
1. Pain-point discovery (Stage 1) — surface specific operational/process challenges
2. Strategic discovery (Stage 2) — directly explore vision, products, and organization
3. Full discovery (both stages in sequence) — recommended for new engagements
4. After the call — write both summaries from the transcript, a Google Doc or notes
```

If the user is unsure, default to **Full discovery** and run Stage 1 first.

If the user hands over a transcript, a Google Doc or notes, or says the call has already happened, that is
option 4 and there is nothing to ask: go to Step 1a. Options 1–3 are a live interview and the person answering is
the client. Never run them on a deal owner describing a call afterwards.

---

## Step 1a — After the call: write the summaries from the record

This mode interviews nobody and launches neither agent. The person running it is the deal owner, not the client.

1. **Read the record**, whichever the user gives:
   - A Fireflies meeting (a name, an id or an `app.fireflies.ai/view/<id>` URL):
     `mcp__fireflies__fireflies_get_transcript(transcriptId="<id>")`. Given only a name, resolve it with one
     `mcp__fireflies__fireflies_search` and confirm by title, date and attendees. Every Fireflies call spends one
     request of a small daily budget, so never loop over meetings.
   - A Google Doc URL: `mcp__google-workspace__get_doc_content(document_id=<url>)`.
   - Pasted text or handwritten notes. This is the usual record when the client did not agree to a recording.

   With no readable record, ask for one and stop. Never write from what someone remembers of the call in this chat.
2. **Name people as the CRM has them**, never by a transcript's speaker label or a spelling heard in the audio. Find
   the deal now, as in Step 4 item 1, and confirm it once; Step 4 does not search or ask again. If it has a
   `contact_id`, read the name with `mcp__zynkr__get_contact`. With no deal or no contact, ask how the client writes
   their name and write the summaries all the same: Step 4 item 1 says what happens without a deal.
3. **Note when the call happened** for `occurred_at`. If the record does not say, ask.
4. **Write the two summaries.**
   - `STAGE1_SUMMARY` has the sections `sales-discovery-pains` closes with: Background & Industry · Team & Role ·
     Current Projects & Challenges · 5D Exploration Results (Diagnose · Distill · Desire · Drag · Deadline).
   - `STAGE2_SUMMARY` has the four sections `sales-discovery-vision` closes with: Company Vision & Strategic
     Priorities · Product Lines & Value Proposition · Organizational Structure & Bottlenecks · Decision Conditions &
     Available Resources.
   - Every line comes from the record. A section the call did not reach reads 「會中沒聊到」. Never fill one from
     the company brief, from the industry, or by inference.
   - Keep the client's own words where they named the cost of the problem or what matters most to them.
5. **Show both summaries and ask once:** 「這樣有抓到這場會議嗎？（Yes / Adjust）」 On Adjust, change what they name
   and show it again. On Yes, go to Step 4.

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

These writes are the deal owner's to agree. After a live interview, wait until the client has left the conversation,
because the preview shows the deal's internal notes.

Present both summaries (after Step 1a they have just been agreed, so go straight on). Then log them on the client's
CRM deal, so that the person who follows up, writes the proposal or runs the consulting work finds them there and not
only in this chat:

1. **Find the deal.** After Step 1a it is already found and confirmed: start at item 2. Otherwise run `mcp__zynkr__list_deals(search="<deal name or 交易 number>")`. The search
   matches the deal's name and number only, not the company field, but deal names usually start
   with the company name. Confirm the match with the user by company and contact, and read it with `mcp__zynkr__get_deal(id=…)`. This skill
   never creates a deal; Sales opens it (`/sales-inbound`, `/sales-outbound`). If there is no deal,
   say so, print the summaries, and skip to the hand-off, opening it with "No deal found, so nothing was saved." in
   place of its first sentence.
2. **Log the call as a meeting.** Call `mcp__zynkr__log_meeting(deal_id=…, subject="[DISCOVERY] 痛點與願景摘要",
   body=…, occurred_at=<when the call happened, ISO 8601>)`. The deal is the only parent. Preview it
   together with the tag writes of item 3 (and their `標籤建議` note, if any) and the line of item 4, show the
   user all of it as one preview, and re-call each with `confirm:true` only after they agree: one question, not two.
   - Pass `occurred_at` whenever the call was not today.
   - The body is `STAGE1_SUMMARY` under 「痛點（需求定義）」, then `STAGE2_SUMMARY` under 「願景（策略探索）」, in the
     client's language and exactly as the user agreed them.
   - If only one stage ran, log that one and say which.
3. **The tags in that preview.** `company.crm-tag-rules` gives this call the tags below. Every one is
   `source="ai"`, because it is read from what the client said. They go on the deal's contact and,
   for 產品 and 關係, on its company too (both ids from `get_deal`; when the deal has no `company_id`,
   skip the company; when it has no `contact_id`, skip the contact and its 主題, and file any
   suggestion note on the company with `company_id`; with neither, apply no tag and say so):
   - **主題** (`group="interest"`) — the `interest-values` topics the client said they care about
     (contact only).
   - **產品** (`group="product"`) — a `product-values` line the client named as wanted. What we only
     recommended does not count.
   - **關係** (`group="relationship"`) — a `relationship-values-skills-write` value, only when the
     client said it or the relationship is explicit.

   Nothing said, no tag; never from a job title or the industry. Read
   `mcp__zynkr__list_tags(entity_type=…, entity_id=…)` first and skip a value already there. Each tag is
   `mcp__zynkr__apply_tag(group=…, name=…, entity_type=…, entity_id=…, source="ai")`, previewed with the
   meeting, then repeated with `confirm:true`; read the result back with `list_tags`. A tag left
   unapplied goes into one `mcp__zynkr__create_note(contact_id=…, subject="標籤建議", body=…)` (or
   `company_id=…` when the deal has no contact), in the same preview and the same agreement.

   > **The CRM tag rules are company policy — read them from Atlas** (`get_knowledge`, key `company.crm-tag-rules`, on the `zynkr-atlas` MCP server; each list is a `<name>: <value>` line at the top, and the `value:` line is the version date). Apply only a value those lines name: `group` is the platform's English key (`source`, `relationship`, `product`, `size`, `interest`, `review`) and `name` is the policy's value. Apply no tag when Atlas cannot be reached, the key or a line you need is missing, `mcp__zynkr__list_tags` or `mcp__zynkr__apply_tag` is not among your tools, or `apply_tag` answers `not_found` or `invalid_input` (an archived value, a group that does not fit the record): write each tag you would have applied as one line `標籤建議：<group>=<value>` in a CRM note on the record, say so in the report, and carry on with the run. When the policy itself cannot be read, write the evidence instead of a value (`標籤建議：主題=<what they asked about, in brief>`, `標籤建議：來源=<the channel they came through>`); never pick a value from memory or from an older copy of this file. On `conflict`, read the record back with `list_tags`, report what it shows, and do not retry. Any other error (`forbidden`, `rate_limited`, `internal`, …) is handled like `not_found`: no tag, a suggestion, no retry, and no stopping to ask.
4. **The qualification line in that preview.** Rule 8 of `company.sales-pipeline-rules` (`get_knowledge`, on the
   `zynkr-atlas` MCP server) lets a deal move to `qualified` only once its `notes` field carries one line
   `資格：痛點＝…；決策者＝…；預算＝…；時程＝…`, each part in the client's words or one sentence from the call. If
   Atlas cannot be reached, write the line in this shape anyway. Draft it from the summaries:
   - A part the call did not settle stays `…`. Never put 「會中沒聊到」 here: the rule reads a blank or `…` as not
     filled, and any words as filled.
   - Take `notes` from `get_deal`, add the line at the end with a blank line above it, and keep every other line
     verbatim, in order, because `mcp__zynkr__update_deal(id=…, notes=<the whole field>)` replaces the whole field.
     If a `資格：` line is already there, fill only its blank or `…` parts.
   - After `confirm:true`, read `get_deal` back: the line is there and every other line survived.
   - Name the parts still `…`: those are the next questions, and the deal stays where it is. This skill never
     moves a stage.
5. **Use a meeting entry for everything else.** Never write the summaries into the deal's `notes` field: item 4's
   line is the only thing this skill adds there. Other skills parse its link lines (`專案資料夾：<url>`,
   `部署紀錄（<SPEC_ID>）：<url>`), and `update_deal` replaces the whole field. Never use the description either,
   which is not shown on the deal. The call happened, so log it as a meeting, not a note. The one note this skill
   may write is item 3's `標籤建議` note, and it holds tag suggestions, never the summaries.
6. **Say what was saved:** the subject, the date, the deal it went on, the `資格：` line as `get_deal` read it back,
   and the tags as `list_tags` read them back (or the `標籤建議` note and why). No tool reads a deal's timeline
   back yet (`get_deal` returns the fields only), so the next skill does not see this entry on its own.
   Hand the summaries on in the same conversation, or tell the user they are on the deal's timeline.

Then ask:

```
Discovery saved to the deal. Next step options:
1. Follow up after the call — /sales-follow-up drafts the reply and brings the deal up to date
2. Write the proposal — /sales-proposal-writer prices what the client asked for
3. Validate specific pain points — re-enter Stage 1 with a different angle
```

After Step 1a, leave out option 3: it is a live interview with the client.

When both this skill and `/sales-follow-up` run on one call, this skill goes first, so the `資格：` line is on the
deal when the follow-up looks at the stage. Tell `/sales-follow-up` that this call is already logged on the deal as
a `[DISCOVERY]` meeting, so it skips its own `[DEMO]` note and the call lands on the timeline once.

**The next step on the deal.** Rule 7 of `company.sales-pipeline-rules` wants an open task with a due date on every
deal a skill touches. `/sales-follow-up` and `/sales-proposal-writer` each leave one. If the user picks neither, and
`mcp__zynkr__list_tasks(filter="open", limit=200)` shows no task with a due date on this deal, create one:
`mcp__zynkr__create_task(subject=<the next step agreed on the call, else 問清楚：<the first part still …>>, deal_id=…,
due_at=<by the rhythm of rule 4>)`, previewed, then repeated with `confirm:true`.

Process mapping and redesign come after the deal is won. They belong to the consulting and
operations-transformation teams, not to this hand-off.

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
