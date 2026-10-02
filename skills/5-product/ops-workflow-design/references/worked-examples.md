# Worked Examples

Two examples — one read, one draft — to anchor what the protocols produce.

---

## Example 1 — READ: the canonical `[@] Architecture template`

**Input from user:** "Read this chart: https://lucid.app/lucidchart/bb9ba9aa-b4c2-4ad2-a432-87f6a805c4e0/edit"

**Steps you take:**

1. Extract doc id `bb9ba9aa-b4c2-4ad2-a432-87f6a805c4e0`.
2. Call `mcp__lucid__fetch` with that id.
3. Identify lanes: top swimlane `Front end user` (with sub-lanes `External user`, `Internal user`); middle `Backend system / process policy` (sub-lanes `Backend manual process`, `Backend state machine / AI assistant`); bottom `Data base / knowledge base` (sub-lanes `Data base data table`, `Knowledge base knowledge`).
4. Tag nodes against `encoding-table.md`:
   - `WjM.n7tEMPmM` `ManualInputBlock` `#ffd9d9ff` → FE manual input (Internal user)
   - `-jM.8Y_5tZln` `ProcessBlock` `#cfe4ffff` → BE LLM process step
   - `dkM.X~sIl5DW` `DocumentBlock` `#e3fae3ff` → DB durable document
   - `DkM.RMEaEThF` `DecisionBlock` `#dedeffff` → BE deterministic decision
   - `UlM.43gkZl7L` `ManualOperationBlockNew` `#edf5ffff` → BE HITL
   - `dlM.rrlo2WGW` `ProcessBlock` `#cfe4ffff` → BE LLM process step
   - `BnM.-sXv9~YE` `ManualOperationBlockNew` `#edf5ffff` → BE HITL
   - `7nM.qS-GAeuu` `DocumentBlock` `#c3f7c8ff` → DB RAG knowledge
   - `LnM.dxA3ExJx` `DocumentBlock` `#c3f7c8ff` → DB RAG knowledge
   - `TkM.x.zytY2a` `DatabaseBlock` `#e3fae3ff` → DB durable cylinder
   - `.mM.oP9X.Je1` `ManualInputBlock` `#fff0f0ff` → FE output to human (External user)
5. Walk edges. Decision `DkM.RMEaEThF` branches `Yes → dlM.rrlo2WGW` (LLM process) and `No → UlM.43gkZl7L` (HITL).
6. Lint with `validation.md` — V4 on both manual operations, V14 on one overfull column, V9 for the missing terminators (see the output).

**Output to the user:**

> **Chart**: `[@] Architecture template` (`bb9ba9aa-...`)
>
> A generic AI-assisted human workflow template, structured as the canonical 3-lane scaffold.
>
> - **Outcome**: no Start / End terminators. The flow starts at a manual input from an internal user and ends either at an output to an external human (the No branch) or at a manual operation with no outgoing edge (the Yes branch).
> - **Steps** — the nodes carry no numbers, so they are numbered here, spine first, each branch right after its gate. Input · Process · Output: not shown on the chart (the template's labels are generic shape names).
>   - **1 · Manual input** — Front end · internal — Reads: none · Writes: none · Knowledge: none
>   - **2 · AI process** — Backend · AI — Reads: Document · Writes: Document (two-headed edge) · Knowledge: none
>   - **3 · Decision** — Backend · rules (gate) — Reads: Database · Writes: Database (two-headed edge) · Knowledge: none
>   - **4 · AI process** (Yes) — Backend · AI — Reads: none · Writes: none · Knowledge: Knowledge for retrieval
>   - **5 · Manual operation** (after 4) — Backend · human — Reads: none · Writes: none · Knowledge: Knowledge for retrieval · no outgoing flow edge — the branch stops here
>   - **6 · Manual operation** (No) — Backend · human — Reads: none · Writes: none · Knowledge: none
>   - **7 · Output to human** (after 6) — Front end · external — Reads: none · Writes: none · Knowledge: none
> - **Decision gates**: 3 — Yes → 4 · No → 6.
> - **Store directory**: data — **Document** (durable) — read and written by 2 · **Database** (cylinder) — read and written by 3. Knowledge — two **Knowledge for retrieval** documents (retrieved), one read by 4 and one by 5; no links on the chart. Step 2 is an AI step with no knowledge edge, so it answers from the model alone — worth flagging on a real flow.
> - **Convention notes**: V4 (hard) — 5 and 6 are manual operations that reach no durable store before the flow ends, so their decisions leave no audit trail; V14 (hard) — one column (centre x ≈ 1680) stacks four nodes: Output to human, a manual operation, an AI process and a knowledge document; V9 (soft) — no Start / End terminators. All three are expected in a shape reference, and would block a real flow.
>
> Edit: <https://lucid.app/lucidchart/bb9ba9aa-b4c2-4ad2-a432-87f6a805c4e0/edit>

---

## Example 2 — DRAFT: invoice approval flow

**Input from user:** "Draw this: customer uploads a CSV of invoices, AI extracts line items, a reviewer approves anything over $10k, everything else auto-posts, results stored in InvoiceLog and the customer gets notified."

**Steps you take:**

1. Layer extraction (using `architecture-principles.md` §4.1):

   | Step | Layer | Mode |
   |---|---|---|
   | Customer uploads CSV | FE / External user | Manual input |
   | AI extracts line items | BE | LLM / agentic |
   | "Total > $10k?" | BE | Deterministic decision |
   | Reviewer approves | BE / Backend manual process | HITL |
   | Auto-post | BE / State machine | Deterministic process |
   | Write InvoiceLog | DB / Data table | Durable cylinder |
   | Extraction schema (what fields to pull) | DB / Knowledge base | Enforced knowledge |
   | Notify customer | FE / External user | Output to human |

2. Step cards (`process-step-card.md`) — numbered, Input · Process · Output, layer, Reads / Writes / Knowledge. "Write InvoiceLog" from the table above is not a step of its own: it becomes the `Writes:` line of the two steps that post. The extraction schema is not a step either: it is the `Knowledge:` line of step 2, and it does not exist yet, so it is `(new)` with `to write` where a link would go. All IPO fields are fillable, so no question to the user.

   - **1 · Upload CSV** — Front end · external — Input: invoice CSV · Process: upload · Output: file received · Reads: none · Writes: none · Knowledge: none
   - **2 · Extract line items** — Backend · AI — Input: the CSV (1) · Process: extract line items and totals · Output: draft invoices · Reads: none · Writes: none · Knowledge: Extraction schema (enforced · new) — to write
   - **3 · Total > $10k?** — Backend · rules (gate) — Input: draft invoices (2) · Process: compare total to $10k · Output: Yes → 4, No → 5 · Reads: none · Writes: none · Knowledge: none
   - **4 · Reviewer approves** — Backend · human — Input: invoices over $10k · Process: approve or reject · Output: approved invoice · Reads: none · Writes: InvoiceLog · Knowledge: none
   - **5 · Auto-post** — Backend · rules — Input: invoices up to $10k · Process: post · Output: posted invoice · Reads: none · Writes: InvoiceLog · Knowledge: none
   - **6 · Notify customer** — Front end · external — Input: the invoice approved in 4 or posted in 5 · Process: look up the logged result and send the notification · Output: customer notified · Reads: InvoiceLog · Writes: none · Knowledge: none
   - Store directory: **InvoiceLog** (data · exists) — written by 4, 5 · read by 6 · **Extraction schema** (knowledge · enforced · new) — read by 2 · maintained by: nobody yet · source: to write · kept current by: owner needed
3. Place each in its lane (per `scaffold.md`).
4. Pick shape + color (per `encoding-table.md`):

   | Node | shapeType | FillColor |
   |---|---|---|
   | Start terminator | `Terminator` | `#ffe342ff` |
   | Upload CSV | `Manual input` | `#ffd9d9ff` |
   | Extract line items (LLM) | `Process` | `#cfe4ffff` |
   | Total > $10k? | `Decision` | `#dedeffff` |
   | Reviewer approves (HITL) | `Manual operation` | `#edf5ffff` |
   | Auto-post (deterministic) | `Process` | purple-family `#9391ffff` |
   | InvoiceLog | `Database` | `#e3fae3ff` |
   | `[RAG] Extraction schema v1` | `Document` | `#c3f7c8ff` (Knowledge base knowledge sub-lane) |
   | Notify customer | `Manual input` | `#fff0f0ff` |
   | End terminator | `Terminator` | `#ffe342ff` |

5. Build the spec on top of the scaffold (3 stacked swimlanes with sub-lanes labeled per `scaffold.md`). Edges:
   - `Start → Upload CSV → Extract line items → Total > $10k?`
   - Decision `Yes` → `Reviewer approves` → `InvoiceLog`
   - Decision `No` → `Auto-post` → `InvoiceLog`
   - `InvoiceLog → Notify customer → End`
   - `[RAG] Extraction schema v1 ⇢ Extract line items` (dashed, arrowhead at the step — it relies on the schema; `v1` is the version it will ship as once written)

6. Call `mcp__lucid__lucid_create_diagram_from_specification`.

7. Self-lint:
   - V1: cylinder is green durable ✓
   - V2: no `ProcessBlock` in FE ✓
   - V3: Decision is purple ✓
   - V4: HITL branch reaches InvoiceLog cylinder ✓
   - V5: LLM step has a downstream deterministic gate ✓
   - V6: Yes/No labels present ✓
   - V8: lane order correct ✓
   - V9: Start + End terminators present ✓
   - Clean ✓

**Output to the user:**

> Drafted "Invoice approval flow" — 10 nodes across 3 lanes; nodes numbered 1–6 like the steps below. Clean against the convention.
>
> - **1 · Upload CSV** — Front end · external — Input: invoice CSV · Process: upload · Output: file received · Reads: none · Writes: none · Knowledge: none
> - **2 · Extract line items** — Backend · AI — Input: the CSV (1) · Process: extract line items and totals · Output: draft invoices · Reads: none · Writes: none · Knowledge: Extraction schema (enforced · new) — to write
> - **3 · Total > $10k?** — Backend · rules (gate) — Input: draft invoices (2) · Process: compare each total to $10k · Output: Yes → 4, No → 5 · Reads: none · Writes: none · Knowledge: none
> - **4 · Reviewer approves** — Backend · human — Input: invoices over $10k · Process: approve or reject · Output: approved invoice · Reads: none · Writes: InvoiceLog · Knowledge: none
> - **5 · Auto-post** — Backend · rules — Input: invoices up to $10k · Process: post · Output: posted invoice · Reads: none · Writes: InvoiceLog · Knowledge: none
> - **6 · Notify customer** — Front end · external — Input: the invoice approved in 4 or posted in 5 · Process: look up the logged result and send the notification · Output: customer notified · Reads: InvoiceLog · Writes: none · Knowledge: none
>
> Store directory: **InvoiceLog** (data · exists) — written by 4, 5 · read by 6 · **Extraction schema** (knowledge · enforced · new) — read by 2; nobody has written it yet, so it is the first thing to create, with an owner.
>
> Edit: <https://lucid.app/lucidchart/{new-doc-id}/edit>

---

## What these examples *don't* show

- Edits / modifications: see `SKILL.md` §4 for the edit protocol.
- Lint-only output: see `validation.md` for the report format.
- Multi-page charts: same protocol, just iterate per page via `page_index`.
- Sequence diagrams: out of scope — use `mcp__lucid__lucid_create_sequence_diagram` directly.
