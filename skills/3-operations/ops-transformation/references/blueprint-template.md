<!--
CONTRACT — this document is read back. Keep the numbered section headings exactly as they are.
  · /ops-prd-writer builds the PRD's design sketch from "## 3." and "## 5.", its data and
    knowledge lines from "## 4.", and adds every gap that waits in "## 6." to Out of scope
  · /ops-workflow-design draws "## 3." and puts these step numbers on the Lucid nodes
Every card follows process-step-card.md §2; write `none` rather than leaving a line out.
-->
# [Blueprint] {{COMPANY}} — {{PROCESS}}

- **Status:** Draft
- **Date:** {{TODAY}} · **Client:** {{COMPANY}} ({{DEAL_URL}})
- **Run by:** /ops-transformation redesign
- **Sources:** {{ASSESSMENT_LINK}} · {{BRD_LINK}} ({{BRD_VERSION}})
- **Renumbering:** {{OLD_NEW_MAP}}

## 1. As-is — numbered SIPOC

{{SIPOC_TABLE}}

## 2. Diagnosis

{{DIAGNOSTIC_TABLE}}

## 3. Redesigned flow — step cards in flow order

**{{N}} · {{STEP_NAME}}** — {{TRIGGER}} · {{LAYER}}
- Input: {{INPUT}}
- Process: {{PROCESS_STEP}}
- Output: {{OUTPUT}}
- Reads: {{READS}}
- Writes: {{WRITES}}
- Knowledge: {{KNOWLEDGE}}
- Tool: {{TOOL}}

## 4. Store directory

- **{{STORE}}** (data · {{NEW_OR_EXISTS}}) — {{HOLDS}}
  - Written by {{N}} · read by {{N}} · join key: {{JOIN_KEY}}
  - Columns: {{COLUMNS}}
- **{{SOURCE}}** (knowledge · {{RETRIEVED_OR_ENFORCED}} · {{NEW_OR_EXISTS}}) — {{HOLDS}}
  - Read by {{N}} · maintained by: {{MAINTAINER}} · source: {{LINK}} · kept current by: {{OWNER}}

## 5. MVP stack

- {{STACK_LINE}}

## 6. Gaps — and the card that closes each

- {{GAP_LINE}} → {{CLOSED_BY_OR_WAITS}}

## 7. Next

- /ops-workflow-design draws section 3; its node numbers are these step numbers.
- /ops-prd-writer writes the PRD from the signed BRD and this blueprint.

<!--
Placeholder guide (fill, then delete this comment block):
  {{COMPANY}} · {{PROCESS}}     same as the [Assessment] this blueprint continues
  {{TODAY}} · {{DEAL_URL}}      YYYY-MM-DD · https://platform.zynkr.ai/deals/{deal_id}
  {{ASSESSMENT_LINK}}           [Assessment](<doc url>)
  {{BRD_LINK}} · {{BRD_VERSION}}  [BRD](<doc url>) · its version line, e.g. v1.0 (signed)
  {{OLD_NEW_MAP}}               the one-line old → new map of the last pass that renumbered, or `none`
  {{SIPOC_TABLE}} · {{DIAGNOSTIC_TABLE}}  sections 1 and 2 of the [Assessment], copied unchanged
  Section 3                     Step 5 item 3: one card per step and sub-task, in flow order. Steps not
                                redesigned get a `kept as is` card (process-step-card.md §5).
                                Drop `Tool:` on a kept-as-is card.
  Section 4                     Step 5 item 4: data stores first, then knowledge sources (§4 format);
                                say each finding under its entry
  Section 5                     Step 5 item 5, deduped across steps
  Section 6                     Step 5 item 6, one gap per line in the §7 form, then the card that
                                closes it, or `waits — <why>`
-->
