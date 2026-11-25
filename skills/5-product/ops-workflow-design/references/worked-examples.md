# Worked Examples

Two examples — one read, one draft — to anchor what the jobs produce. Each flow is a file in
`scripts/fixtures/`, and the frontmatter below is that file's, line for line: the kit's selftest
parses both files exactly as Atlas does, and the workbench's test keeps this page equal to them.

---

## Example 1 — READ: the architecture template

**Input from user:** "Explain this flow", with the file `example-1.md` (for a flow that lives in
Atlas: its slug or link, read with `get_artifact_body`).

```yaml
---
name: architecture-template
originalName: Architecture template
type: workflow
category: operations
description: "A shape reference: a generic AI-assisted workflow with one of each common step on the three lanes."
executed_by: internal-user
steps:
  - "input | input | Manual input"
  - "ai | llm | AI process"
  - "doc | artifact | Document"
  - "decide | gate | Decision"
  - "db | store | Database"
  - "ai_yes | llm | AI process"
  - "kb_one | knowledge | Knowledge for retrieval"
  - "manual_yes | hitl | Manual operation"
  - "kb_two | knowledge | Knowledge for retrieval"
  - "manual_no | hitl | Manual operation"
  - "out | output | Output to human | by=external"
flow:
  - "input -> ai"
  - "ai -> decide"
  - "decide -> ai_yes | Yes"
  - "decide -> manual_no | No"
  - "ai_yes -> manual_yes"
  - "manual_no -> out"
  - "doc ~> ai"
  - "ai ~> doc"
  - "db ~> decide"
  - "decide ~> db"
  - "kb_one ~> ai_yes"
  - "kb_two ~> manual_yes"
---
```

**Steps you take:**

1. Read the flow text. The kinds give the lanes: `input` and `output` sit in the front end (the
   frontmatter's `executed_by: internal-user`, and `by=external` on `out`); `llm`, `gate` and `hitl`
   in the backend; `artifact`, `store` and `knowledge` in the data lane.
2. Lint it: `python3 -I <skill>/scripts/flow_svg.py lint example-1.md` exits 1:

   ```
   Lint of example-1.md · Architecture template
   Hard rule violations (ship-blockers):
   - V4 — manual_yes (Manual operation): a human step with no ~> line to a store or artifact, so its decision leaves no record. Fix: write the decision down: `<hitl step> ~> <decision log>`, with the log as a store step (`Decision log (new)` when it does not exist yet).
   - V4 — manual_no (Manual operation): a human step with no ~> line to a store or artifact, so its decision leaves no record. Fix: write the decision down: `<hitl step> ~> <decision log>`, with the log as a store step (`Decision log (new)` when it does not exist yet).
   Total: 2 hard, 0 soft.
   ```

3. Walk what lint can't: there is no `start` and no `end` step (V9, by eye), and the knowledge
   titles don't read `[RAG] <name> v<n>`.
4. Number the steps. The titles carry no numbers, so number them in spine order, each branch
   right after its gate, and say so. The body has no step cards, so Input · Process · Output are
   `not in the flow text`.
5. Reads, Writes and Knowledge come from the `~>` lines and their direction: `doc ~> ai` is a read,
   `ai ~> doc` a write, `kb_one ~> ai_yes` knowledge `ai_yes` relies on.

**Output to the user:**

> **Flow**: Architecture template (`example-1.md`)
>
> A generic AI-assisted workflow, laid out as a shape reference on the three lanes.
>
> - **Outcome**: no `start` or `end` step. The flow begins at a manual input from someone on the
>   team, and ends either at an output to an external person (the No branch) or at a manual
>   operation with no line out of it (the Yes branch).
> - **Steps** — the titles carry no numbers, so they are numbered here: spine first, each branch
>   right after its gate. Input · Process · Output: not in the flow text (the titles are the shapes'
>   names).
>   - **1 · Manual input** (`input`) — Front end · internal — Reads: none · Writes: none · Knowledge: none
>   - **2 · AI process** (`ai`) — Backend · AI — Reads: Document · Writes: Document · Knowledge: none
>   - **3 · Decision** (`decide`) — Backend · rules (gate) — Reads: Database · Writes: Database · Knowledge: none
>   - **4 · AI process** (`ai_yes`, Yes) — Backend · AI — Reads: none · Writes: none · Knowledge: Knowledge for retrieval (`kb_one`)
>   - **5 · Manual operation** (`manual_yes`, after 4) — Backend · human — Reads: none · Writes: none · Knowledge: Knowledge for retrieval (`kb_two`) · no line leaves it: the branch stops here
>   - **6 · Manual operation** (`manual_no`, No) — Backend · human — Reads: none · Writes: none · Knowledge: none
>   - **7 · Output to human** (`out`, after 6) — Front end · external — Reads: none · Writes: none · Knowledge: none
> - **Decision gates**: 3 — Yes → 4 · No → 6.
> - **Store directory**: data — **Document** (`doc`, durable document) — written by 2 · read by 2 ·
>   **Database** (`db`, system of record) — written by 3 · read by 3. Knowledge — two
>   **Knowledge for retrieval** sources: `kb_one` read by 4, `kb_two` read by 5; nothing in the flow
>   maintains them, and neither names its source. Step 2 is an AI step with no knowledge line, so
>   it answers from the model alone: worth flagging on a real flow.
> - **Convention notes**: V4 (hard, lint) — 5 and 6 are manual operations that write to no store,
>   so their decisions leave no record; V9 (by eye) — no `start` or `end` step. Both are expected in
>   a shape reference, and both would block a real flow.
>
> Source: `example-1.md`

---

## Example 2 — DRAFT: invoice approval flow

**Input from user:** "Draw this: customer uploads a CSV of invoices, AI extracts line items, a
reviewer approves anything over $10k, everything else auto-posts, results stored in InvoiceLog and
the customer gets notified."

**Steps you take:**

1. **Layer extraction** (`architecture-principles.md` §4.1):

   | Step | Layer | Kind |
   |---|---|---|
   | Customer uploads CSV | Front end · external | `input` |
   | AI extracts line items | Backend · AI | `llm` |
   | "Total over $10k?" | Backend · rules (gate) | `gate` |
   | Reviewer approves | Backend · human | `hitl` |
   | Auto-post | Backend · rules | `deterministic` |
   | Write InvoiceLog | Data · data table | `store` |
   | Extraction schema (what fields to pull) | Data · knowledge (enforced) | `knowledge` |
   | Notify customer | Front end · external | `output` |

2. **Step cards** (`process-step-card.md`) — numbered, Input · Process · Output, layer, Reads ·
   Writes · Knowledge. "Write InvoiceLog" is not a step of its own: it is the `Writes:` line of the
   two steps that post. The extraction schema is not a step either: it is the `Knowledge:` line of
   step 2, and it does not exist yet, so it is `(new)` with `to write` where a link would go. All
   the fields are fillable, so there is no question for the user. The cards go in the file's body,
   under the frontmatter.

   - **1 · Upload the invoice CSV** — Front end · external — Input: the customer's invoice CSV · Process: upload the file · Output: the file, received · Reads: none · Writes: none · Knowledge: none
   - **2 · Extract line items** — Backend · AI — Input: the CSV (1) · Process: extract the line items and totals · Output: draft invoices · Reads: none · Writes: none · Knowledge: Extraction schema (enforced · new) — to write
   - **3 · Total over $10k?** — Backend · rules (gate) — Input: the draft invoices (2) · Process: compare each total to $10k · Output: Yes → 4, No → 5 · Reads: none · Writes: none · Knowledge: none
   - **4 · Reviewer approves** — Backend · human — Input: an invoice over $10k · Process: approve or reject it · Output: the approved invoice, and the decision · Reads: none · Writes: Invoice log (exists) · Knowledge: none
   - **5 · Auto-post** — Backend · rules — Input: an invoice up to $10k · Process: post it · Output: a posted invoice · Reads: none · Writes: Invoice log (exists) · Knowledge: none
   - **6 · Notify the customer** — Front end · external — Input: the invoice approved in 4 or posted in 5 · Process: look up the logged result and send the notice · Output: the customer, notified · Reads: Invoice log (exists) · Writes: none · Knowledge: none
   - Store directory: **Invoice log** (data · exists) — written by 4, 5 · read by 6 · **Extraction schema** (knowledge · enforced · new) — read by 2 · maintained by: nobody yet · source: to write · kept current by: owner needed

3. **The flow text** (`scaffold.md`), in order:
   1. The spine: `start`, one step per card, `end`, and the `->` lines, with `Yes` and `No` on the
      gate's branches. Both branches rejoin at step 6 within a column, so the spine stays one path.
   2. The front end: `executed_by: external-user` puts the customer's steps on the external row.
   3. Stores and knowledge: one `store` (the invoice log) and one `knowledge` step (the schema),
      then one `~>` line per Reads, Writes and Knowledge entry. The schema is only read, so it sits
      under step 2, its first reader, on both drawings: there is nothing to place.
   4. Phases: `## Intake` and `## Approval`.

The frontmatter of the file, `example-2.md` (its body holds the step cards and the store directory):

```yaml
---
name: invoice-approval-flow
originalName: Invoice approval
type: workflow
category: operations
description: "A customer uploads invoices, AI extracts the line items, a reviewer approves anything over $10k, the rest posts itself, and the customer is told."
executed_by: external-user
steps:
  - "## Intake"
  - "start | start | Start · a customer has invoices to send"
  - "upload | input | 1 Upload the invoice CSV"
  - "extract | llm | 2 Extract line items"
  - "schema | knowledge | [RAG] Extraction schema v1"
  - "## Approval"
  - "big | gate | 3 Total over $10k?"
  - "review | hitl | 4 Reviewer approves"
  - "post | deterministic | 5 Auto-post"
  - "log | store | Invoice log"
  - "notify | output | 6 Notify the customer"
  - "end | end | End · customer notified"
flow:
  - "start -> upload"
  - "upload -> extract"
  - "extract -> big"
  - "big -> review | Yes"
  - "big -> post | No"
  - "review -> notify"
  - "post -> notify"
  - "notify -> end"
  - "schema ~> extract | the fields to pull"
  - "review ~> log"
  - "post ~> log"
  - "log ~> notify"
page:
  - "## Intake | The customer sends the file and AI reads it"
  - "## Approval | Over $10k waits for a person; the rest posts itself"
  - "upload | note=One CSV, a row per invoice"
  - "extract | note=AI · reads every row | run=extract-invoice prompt"
  - "big | note=Rules · compares each total"
  - "review | note=A person approves or rejects"
  - "post | note=Rules · no person involved"
  - "notify | note=An email with the result"
  - "schema | note=The fields step 2 pulls | link=https://example.com/extraction-schema | tip=Opens the extraction schema"
  - "log | note=Every approved or posted invoice"
---
```

The `page:` list is for the page drawing (step 7): Atlas ignores it. Its one link is a
placeholder address for the example; in a real flow a link is one the user gave.

4. **Lint** — `python3 -I <skill>/scripts/flow_svg.py lint example-2.md`:

   ```
   Lint of example-2.md · Invoice approval
   Clean — no convention violations.
   ```

   Then the checks lint can't do: V1 — the invoice log is a durable record, and the schema is a
   `knowledge` step, not a cylinder ✓ · V2 — upload and notify only show and take input ✓ · V3 —
   the branch leaves a gate, not the AI step ✓ · V10 — every kind matches its card ✓ · V7 — no
   `offpage` step ✓.
5. **Pick the drawing.** The user asked for a drawing, not for Atlas, so it is a page drawing in
   the overview (step 7). Does the team or a client run it? Yes: a reviewer approves invoices every
   week. So the reply offers the detailed version in Atlas, in one line under the drawing.
6. **The Atlas draft**, only after a yes to that offer: `draft_new_item(type: "workflow", slug: "invoice-approval-flow",
   body: <the whole file>, notes: "New flow: invoice approval, drafted from a description")`. Then
   `list_pending` and `get_draft` on the new version: its sha256 equals `shasum -a 256 example-2.md`.
   Approve nothing.
7. **The page drawing**, the overview:
   `python3 -I <skill>/scripts/flow_svg.py render example-2.md --embed --out invoice-approval.html`
   and `table example-2.md --out invoice-approval-steps.html`; `lint example-2.md --layout stacked`
   exits 0; then look at it. The ten steps sit in two columns, one per phase: Intake's steps
   stacked in the first, Approval's in the second. Each work card carries its number and its note,
   and step 2 names what runs it. The invoice log reads `W 4 5 · R 6` and draws one line, from
   step 4; the schema draws its one line into step 2. The schema's name is underlined and opens its
   page; only the gate's branches carry labels; and hovering step 5 keeps its two lines dark and
   calls out the gate, the invoice log and step 6.

**Output to the user:**

> Drew "Invoice approval": 10 steps on three lanes, numbered 1–6 like the cards below. Lint is
> clean and the kind checks pass. The drawing is the overview: the invoice log draws one line, and
> its tags name the other steps that write and read it.
>
> - **1 · Upload the invoice CSV** — Front end · external — Input: the customer's invoice CSV · Process: upload the file · Output: the file, received · Reads: none · Writes: none · Knowledge: none
> - **2 · Extract line items** — Backend · AI — Input: the CSV (1) · Process: extract the line items and totals · Output: draft invoices · Reads: none · Writes: none · Knowledge: Extraction schema (enforced · new) — to write
> - **3 · Total over $10k?** — Backend · rules (gate) — Input: the draft invoices (2) · Process: compare each total to $10k · Output: Yes → 4, No → 5 · Reads: none · Writes: none · Knowledge: none
> - **4 · Reviewer approves** — Backend · human — Input: an invoice over $10k · Process: approve or reject it · Output: the approved invoice, and the decision · Reads: none · Writes: Invoice log (exists) · Knowledge: none
> - **5 · Auto-post** — Backend · rules — Input: an invoice up to $10k · Process: post it · Output: a posted invoice · Reads: none · Writes: Invoice log (exists) · Knowledge: none
> - **6 · Notify the customer** — Front end · external — Input: the invoice approved in 4 or posted in 5 · Process: look up the logged result and send the notice · Output: the customer, notified · Reads: Invoice log (exists) · Writes: none · Knowledge: none
>
> Store directory: **Invoice log** (data · exists) — written by 4, 5 · read by 6 · **Extraction
> schema** (knowledge · enforced · new) — read by 2; nobody has written it yet, so it is the first
> thing to create, with an owner.
>
> A reviewer runs this every week: want the detailed version drafted in Atlas for review?
>
> Drawing: `invoice-approval.html` · steps table: `invoice-approval-steps.html`

After a yes, step 6 files the draft, and the reply ends with the review link instead: the link
`draft_new_item` returned, and the workflow beside it (the same address with
`/workflows/invoice-approval-flow` in place of `/review`). It waits for a reviewer; approve nothing.

---

## What these examples *don't* show

- Edits: see `SKILL.md`, EDIT.
- Lint-only output: see `validation.md` for the report format.
- A chart handed over as a PDF or PNG: see `SKILL.md`, READ.
- Sequence diagrams: out of scope. Flow text has no lifelines.
