# Semantic → Lucid Encoding Table

The bridge between semantic concept (from `architecture-principles.md` and `shape-color-principles.md`) and concrete Lucid Standard Import JSON fields.

**How to use this table:**

- When **reading** a Lucid JSON: read each node's `BlockClass` + `FillColor` → look up the row → that's the semantic role.
- When **drafting** a Lucid spec: pick the semantic concept → use the `shapeType` and `FillColor` columns to build the node.
- When **linting**: any mismatch between a node's lane and its color family is a violation (see `validation.md`).

The hex values are extracted from the canonical `[@] Architecture template` (Lucid doc id `bb9ba9aa-b4c2-4ad2-a432-87f6a805c4e0`). Use them as exact targets when drafting. When reading, accept any visually-similar hex in the same family (e.g., anything `#ff[d-f][0-f][0-d][0-f]ff` reads as "red family" → FE).

---

## Encoding table

| # | Semantic concept | `shapeType` (used by `lucid_add_block` and in the spec) | `BlockClass` (appears in `fetch` output) | `FillColor` | Default lane |
|---|---|---|---|---|---|
| 1 | Terminal · Start / End | `Terminator` | `TerminatorBlockV2` (newer) or `TerminatorBlock` | `#ffe342ff` (yellow) | any |
| 2 | FE — manual input from user | `Manual input` | `ManualInputBlock` | `#ffd9d9ff` (red, darker — input direction) | FE / External or Internal |
| 3 | FE — output to human | `Manual input` | `ManualInputBlock` | `#fff0f0ff` (red, lighter — output direction) | FE / External or Internal |
| 4 | FE — context document (ephemeral, in-session) | `Document` | `DocumentBlock` | `#fff0f0ff` (red, lighter) | FE |
| 5 | BE — HITL manual operation (human in the loop) | `Manual operation` | `ManualOperationBlockNew` | `#edf5ffff` (light blue) | BE / Backend manual process |
| 6 | BE — AI / agentic process step (LLM) | `Process` | `ProcessBlock` | `#cfe4ffff` (blue) | BE / State machine · AI assistant |
| 7 | BE — deterministic process step (rules / state machine) | `Process` | `ProcessBlock` | purple family (e.g. `#9391ffff`) | BE / State machine · AI assistant |
| 8 | BE — decision / gate (deterministic preferred) | `Decision` | `DecisionBlock` | `#dedeffff` (light purple) | BE / State machine · AI assistant |
| 9 | DB — durable system-of-record (cylinder) | `Database` | `DatabaseBlock` | `#e3fae3ff` (green) | DB / Data base data table |
| 10 | DB — durable artifact (document persisted) | `Document` | `DocumentBlock` | `#e3fae3ff` (green) | DB / Data base data table |
| 11 | DB — RAG / knowledge artifact (for retrieval) | `Document` | `DocumentBlock` | `#c3f7c8ff` (dark green) | DB / Knowledge base knowledge |
| 12 | Off-page link · cross-workflow handoff | `Off-page link` | `OffPageLinkBlock` | `#fff7a1ff` (yellow) | any (boundary only) |
| 13 | Merge / fork control (Or-junction) | `Or` | `OrBlock` | `#dedeffff` (purple) | BE |
| 14 | Swimlane container (the scaffold itself) | — (not a block; built into the spec) | `AdvancedSwimLaneBlock` | neutral `#dfe3e8ff` | structural |
| 15 | Ephemeral context (session-only, light green) | `Document` | `DocumentBlock` | `#ecffec` family (lighter than `#e3fae3ff`) | DB lane or floating — **not** the cylinder |

---

## Color family quick reference

When you see this hex range, read it as this layer:

| Family | Hex pattern | Layer / mode |
|---|---|---|
| Red | `#ff[d-f][0-f][0-f][0-f]ff` (e.g., `#ffd9d9`, `#fff0f0`) | FE — human interaction |
| Light blue | `#e[c-d]f5ff` family | BE HITL manual process |
| Blue | `#cfe4ff` family | BE LLM / agentic |
| Purple | `#d[e-f]d[e-f]ff` / `#9391ff` family | BE deterministic (process or decision gate) |
| Green | `#e3fa[e-f][0-f]` family | DB durable system-of-record |
| Light green | `#ecffe[0-f]` family | Ephemeral context (rare) |
| Dark green | `#c3f7c8` family | RAG / knowledge for retrieval |
| Yellow | `#ffe342` / `#fff7a1` family | Terminator or off-page link (boundary markers) |
| Neutral grey | `#dfe3e8` family | Swimlane container — structural only |

---

## Hard rules embedded in the table

- **Row 9 (Cylinder, green) — HARD RULE.** `DatabaseBlock` is *only* for durable system-of-record. **Never** for vector / RAG / knowledge index. If you need RAG, use row 11 (`DocumentBlock` dark-green).
- **Row 8 (Decision, purple) — HARD RULE.** Decisions stay purple by default. If you're tempted to color a decision blue ("LLM decides"), restructure: LLM suggests → deterministic gate enforces.
- **Row 6 (LLM Process, blue) — soft rule.** Every blue `ProcessBlock` needs a downstream fallback path (deterministic gate, HITL escalation, or error edge). See validation rule V5.

---

## What's *not* in this table (intentionally)

- The full Lucid Standard Import JSON schema — fetch `lucid://diagram-specification` at runtime; it can change.
- Cloud architecture shapes (AWS, GCP, Azure icons) — only relevant for infrastructure diagrams, not process flows. Use `lucid://shape-libraries/*` if you ever need them.
- Endpoint / arrow styles — fetch `lucid://endpoint-styles`. Default is `Equilateral Arrow`.

---

## Standard Import quick-map (drafting via `lucid_create_diagram_from_specification`)

The `shapeType` column above is the `add_block` / `fetch` vocabulary. The **Standard-Import `type`** (lowercase) is what goes in the create-spec JSON:

| Semantic | Standard-Import `type` | BlockClass (fetch) | FillColor |
|---|---|---|---|
| Terminal · Start/End | `terminator` | TerminatorBlockV2 | `#ffe342` |
| FE input | `manualInput` | ManualInputBlock | `#ffd9d9` |
| FE output | `manualInput` | ManualInputBlock | `#fff0f0` |
| HITL manual op | `manualOperation` | ManualOperationBlockNew | `#edf5ff` |
| BE LLM step | `process` | ProcessBlock | `#cfe4ff` |
| BE deterministic step | `process` | ProcessBlock | `#9391ff` |
| Decision gate | `decision` | DecisionBlock | `#dedeff` |
| DB cylinder | `database` | DatabaseBlock | `#e3fae3` |
| Durable doc | `document` | DocumentBlock | `#e3fae3` |
| RAG knowledge doc | `document` | DocumentBlock | `#c3f7c8` |

Gotchas (full notes in `SKILL.md` §8):
- Set every node's `fontSize` to **10**; short labels balloon on default.
- `swimLanes` render **flat** (no nested sub-lanes) — one lane per sub-band, group via the title; lane widths must sum to the pool dimension.
- `lucid_add_line` / `lucid_edit_item` endpoint styles are **Capitalized** (`None`, `Equilateral Arrow`); the create-spec uses lowercase (`none`, `arrow`).
- No native legend block — build colour chips (filled rectangles whose own text is the label).
