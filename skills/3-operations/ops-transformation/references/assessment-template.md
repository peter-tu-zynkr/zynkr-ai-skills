<!--
CONTRACT — this document is read back. Keep the numbered section headings and the two table
header rows exactly as they are.
  · /ops-transformation redesign loads SIPOC_TABLE from "## 1.", DIAGNOSTIC_RESULT from "## 2."
    and the gaps from "## 4."
  · /consult-brd-writer takes the BRD's as-is flow from "## 1." and keeps its step numbers
Step numbers issued here are permanent for the engagement (process-step-card.md §1).
-->
# [Assessment] {{COMPANY}} — {{PROCESS}}

- **Status:** Draft
- **Date:** {{TODAY}} · **Client:** {{COMPANY}} ({{DEAL_URL}})
- **Run by:** /ops-transformation assess
- **Brief:** {{PROCESS_BRIEF}}
- **Outcome wanted:** {{OUTCOME}}

## 1. As-is process — numbered SIPOC

| # | Supplier | Input | Process | Output | Customer | Systems today |
|---|---|---|---|---|---|---|
| 1 | {{SUPPLIER_1}} | {{INPUT_1}} | {{PROCESS_1}} | {{OUTPUT_1}} | {{CUSTOMER_1}} | {{SYSTEMS_1}} |

## 2. Diagnosis — same step numbers

| # | Classification | Tech suggestion → layer | ROI | Gaps | Rationale |
|---|---|---|---|---|---|
| 1 | {{QUADRANT_1}} | {{TECH_1}} → {{LAYER_1}} | {{ROI_1}} | {{GAPS_1}} | {{RATIONALE_1}} |

## 3. Recommendation

- **Transform now:** {{TRANSFORM_NOW}}
- **Defer:** {{DEFER}}

## 4. Knowledge and data gaps to raise with the client

- {{GAP_1}}

## 5. Next

- /consult-brd-writer takes the BRD's as-is flow from section 1 and keeps these step numbers.
- After the client signs the BRD, /ops-transformation redesign picks this document up.

<!--
Placeholder guide (fill, then delete this comment block):
  {{COMPANY}} · {{PROCESS}}  the client company · the process assessed, short (e.g. 報價流程)
  {{TODAY}}                  YYYY-MM-DD
  {{DEAL_URL}}               https://platform.zynkr.ai/deals/{deal_id}
  {{PROCESS_BRIEF}}          PROCESS_BRIEF from Step 1, one or two sentences
  {{OUTCOME}}                what the client wants from the change: cost · speed · quality · scale
  SIPOC rows                 SIPOC_TABLE, one row per step; keep the `(assumed)` marks
  Diagnosis rows             DIAGNOSTIC_RESULT, keyed by the same step numbers
  {{TRANSFORM_NOW}} · {{DEFER}}  step numbers with a few words each
  {{GAP_n}}                  one line per gap, process-step-card.md §7:
                             N · Gap · knowledge — <what the step needs to know> → <source> (retrieved | enforced · new | exists) — <link | link needed | to write>
                             N · Gap · data — <what the step needs to see> → <store (system)> (new | exists)
                             "None found" is a valid line.
-->
