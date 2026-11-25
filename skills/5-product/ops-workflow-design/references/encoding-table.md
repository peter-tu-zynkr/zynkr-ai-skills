# Encoding Table — kind → role → shape → lane

The bridge between a semantic concept (from `architecture-principles.md` and
`shape-color-principles.md`) and what the flow text and the drawing carry. In flow text, a step's
**kind** is the whole encoding: the kind names the colour role, the role names the shape and the
colours, and the kind decides the lane. Nothing else is written down.

**How to use this table:**

- **Drafting:** pick the semantic concept → write its kind in the step line
  (`"<id> | <kind> | <title>"`). The kit (`scripts/flow_svg.py render`) and Atlas's canvas draw the
  rest.
- **Reading flow text:** the kind is the role. Read the row, and you have the layer and the mode.
- **Reading a chart handed over as an image (PDF or PNG):** match each box's shape and colour family
  against the rows below, and mark what you read off the picture `(inferred)`. A kit drawing names
  every role it uses in its legend. Accept any colour in the same family: the family carries the
  meaning, not the exact shade.
- **Linting:** the kind settles the lane, the shape and the colour, so a drawing cannot break V1,
  V2, V3, V8 or V10; a wrong kind can (`validation.md`, the rules whose home is "kind").

**The colours live in one file:** `flow-colours.json`, one role per row below, under the role's name.
Never write a colour value: not in flow text, not on the page around a drawing, not in a reply.
Workflow drawings use workflow colours only, never a brand colour.

---

## Encoding table

| # | Semantic concept | Kind | Registry role | Colour family | Shape the kit draws | Lane · row |
|---|---|---|---|---|---|---|
| 1 | Terminal · start / end | `start` · `end` | `terminal` | yellow | terminal (rounded ends) | Front end · the person's row |
| 2 | FE — a person puts something in | `input` | `input` | red, darker (input direction) | manual input (slanted top) | Front end · external or internal |
| 3 | FE — a person receives a result | `output` | `output` | red, lighter (output direction) | manual input (slanted top) | Front end · external or internal |
| 4 | FE — context document (this session only) | `context` · page-only | `context` | red, lighter | document (wavy bottom) | Front end · external or internal |
| 5 | BE — HITL manual operation (human in the loop) | `hitl` | `hitl` | light blue | manual operation (trapezoid) | Backend · manual process |
| 6 | BE — AI / agentic step (LLM) | `llm` | `llm` | blue | process (rectangle) | Backend · state machine / AI |
| 7 | BE — deterministic step (rules, a script, a state change) | `deterministic` | `deterministic` | purple | process (rectangle) | Backend · state machine / AI |
| 8 | BE — decision / gate (deterministic) | `gate` | `gate` | light purple | decision (diamond) | Backend · state machine / AI |
| 9 | DB — durable system of record | `store` | `store` | green | database (cylinder) | Data · data table |
| 10 | DB — durable document | `artifact` | `artifact` | green | document (wavy bottom) | Data · data table |
| 11 | DB — knowledge: retrieved or enforced | `knowledge` | `knowledge` | dark green | document (wavy bottom) | Data · knowledge |
| 12 | Off-page link · hand-off to another flow | `offpage` | `offpage` | yellow | off-page (pentagon) | Backend · state machine / AI |
| 13 | Merge / fork control | `junction` · page-only | `junction` | light purple | junction (circle with a cross) | Backend · state machine / AI |
| 14 | The lane frame (the scaffold itself) | — | the registry's `lanes` | neutral grey | lane headers and a faint fill per layer | structural |
| 15 | Ephemeral context (this session only) | `ephemeral` · page-only | `ephemeral` | light green, dashed outline | document (wavy bottom) | Data · data table — **never** the cylinder |

- **Who sits at the front end:** `input`, `output`, `context`, `start` and `end` take the row of the
  person in the frontmatter's `executed_by` (`external-user` or `internal-user`); a step's own
  `by=external` or `by=internal` overrides it. Atlas's canvas places them the same way.
- **Page-only kinds** (rows 4, 13 and 15): the kit draws them; Atlas has no kind for them yet and
  would drop the step, so `lint` warns and a flow that uses one stays a page drawing.
- **Row 14** has no kind: the registry's `lanes` block holds the lane headers, the faint fill of
  each layer and the lane titles in English and zh-TW (the same titles Atlas's canvas shows).

### Lines

| Line | Flow text | Registry | Drawn as |
|---|---|---|---|
| Spine — the order the work runs in | `a -> b[ \| label]` | `edges.spine` | solid neutral dark grey, the heavier line |
| Plumbing — reads, writes and knowledge | `a ~> b[ \| label]` | `edges.plumbing` | thin dashed grey, beneath the spine; the arrow points the way the data moves |

---

## Colour family quick reference (reading an image)

| Family | Layer / mode | Rows |
|---|---|---|
| Red (darker and lighter) | Front end — a person puts in, receives, or works from session context | 2, 3, 4 |
| Light blue | Backend — a person executes (HITL) | 5 |
| Blue | Backend — an LLM executes | 6 |
| Purple (solid and light) | Backend — fixed rules: a step, a gate, a merge or fork | 7, 8, 13 |
| Green | Data — a durable record or document | 9, 10 |
| Dark green | Data — knowledge a step relies on | 11 |
| Light green, dashed | Session-only context | 15 |
| Yellow | Boundaries — where the flow starts and ends, and hand-offs | 1, 12 |
| Neutral grey | The lane frame — structural only | 14 |

---

## Hard rules embedded in the table

- **Row 9 (the cylinder, `store`) — HARD RULE (V1).** A cylinder is *only* a durable system of
  record. **Never** a vector index, a RAG store or a knowledge base: that is row 11, a `knowledge`
  step titled `[RAG] <name> v<n>`, read through `~>` lines.
- **Row 8 (the diamond, `gate`) — HARD RULE (V3).** A decision is a `gate`, and a gate is always
  drawn as the deterministic diamond. If you are tempted to let the model pick the branch
  ("the LLM decides"), restructure: the LLM suggests (`llm`) → a gate enforces (`gate`), and the
  labelled branches leave the gate (V6).
- **Row 6 (`llm`) — checked by lint (V5).** Every `llm` step needs a gate, a HITL step, or a labelled
  error or retry line after it.

---

## What's *not* in this table (intentionally)

- **The colour values** — `flow-colours.json`, by role name. A change there is a new registry
  version, and every drawing is stamped with the version it was drawn with.
- **Placement** — columns, phases and the one-spine rule (V14): `scaffold.md` §6.
- **Sequence diagrams and infrastructure icons** — out of scope: flow text has no lifelines and no
  cloud shapes.
