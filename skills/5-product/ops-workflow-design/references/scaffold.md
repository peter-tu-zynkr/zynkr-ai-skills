# The Flow-Text Scaffold

Every new flow starts from this scaffold. A flow is flow text: the workflow body Zynkr Atlas
stores, `steps:` and `flow:` lines under `## <phase>` headers. You never place a step by
coordinates. Its **kind** decides its lane, the **spine** decides its column, and the renderer (the
kit's `render`, or Atlas's canvas) does the rest, the same way in both.

---

## 1) The lanes (top → bottom, fixed)

```
┌──────────────────────────────────────────────────────────────────┐
│ Front end                                                        │
│   ├── External user                  input · output              │
│   └── Internal user                  input · output              │
├──────────────────────────────────────────────────────────────────┤
│ Backend                                                          │
│   ├── Manual process (HITL)          hitl                        │
│   └── State machine / AI assistant   llm · deterministic · gate  │
├──────────────────────────────────────────────────────────────────┤
│ Data and knowledge                                               │
│   ├── Data table (durable)           store · artifact            │
│   └── Knowledge (retrieval)          knowledge                   │
└──────────────────────────────────────────────────────────────────┘
```

The order is mandatory and the renderer keeps it: FE on top, BE in the middle, DB at the bottom
(V8). The diagram names each row by its role; a drawing titles it as Atlas's canvas does
("Front end user", "Data base / knowledge base"…), from the colour registry, in English or zh-TW
(`render --lang`).

## 2) Lanes by kind

| Kind | Encoding row | Lane · band | What it is |
|---|---|---|---|
| `start` · `end` | 1 | the boundaries | Where the flow begins and ends (V9). |
| `input` | 2 | Front end · external or internal | A person types, uploads or sends something. |
| `output` | 3 | Front end · external or internal | A person sees or receives a result. |
| `hitl` | 5 | Backend · manual process | A person decides, reviews or approves. |
| `llm` | 6 | Backend · state machine / AI | An LLM step. Needs a gate or a person after it (V5). |
| `deterministic` | 7 | Backend · state machine / AI | Fixed logic: rules, a script, a state change. |
| `gate` | 8 | Backend · state machine / AI | A deterministic decision that branches the flow. |
| `store` | 9 | Data · data table | A durable system of record (V1). |
| `artifact` | 10 | Data · data table | A durable document. |
| `knowledge` | 11 | Data · knowledge | A source a step relies on: retrieved or enforced. |
| `offpage` | 12 | the boundaries | A hand-off to another flow (V7). |
| `context` | 4 | Front end | Page-only: a context document, session-only. |
| `junction` | 13 | Backend | Page-only: a merge or fork control. |
| `ephemeral` | 15 | Data and knowledge | Page-only: session-only context, never the cylinder. |

Row 14 is the lane frame itself. The three page-only kinds are drawn on pages; Atlas has no kind for
them and would drop the step, so a flow that uses one stays a page drawing. Shapes and colour roles
per row are in `encoding-table.md`; the colours themselves are only in `flow-colours.json`.

**Who sits at the front end.** The frontmatter's `executed_by: external-user | internal-user` puts
every `input`, `output`, `start` and `end` step with that person by default. A step's own
`by=external` or `by=internal` overrides it, for a flow where a customer uploads and someone on the
team reviews.

**Quick placement, when a step could go two ways** — ask in this order:

1. Is a person directly interacting with it? A customer → `input` or `output`, `by=external`;
   someone on the team → `input` or `output`, `by=internal`.
2. Else, is a person executing it (approve, review, override)? → `hitl`.
3. Else, is a machine executing it? Fixed rules → `deterministic`, or `gate` when it branches; a
   model → `llm`.
4. Else, does it hold data? A durable record → `store` (a document → `artifact`); a source for
   retrieval or a rule set applied exactly → `knowledge`.
5. None of these: it is `start`, `end` or `offpage`.

If a step still feels like two kinds, re-read `architecture-principles.md` §2. The smell test: "FE
shows intent; BE owns meaning."

## 3) Phases

`"## <phase>"` lines inside `steps:` group the steps below them, up to the next header: one header
per stage, beat or day. A phase name has at most 40 characters, and a header with no steps under it
is dropped. A phase is a run of steps in file order, so write the steps in the order the work runs.
A step number's first part usually matches its phase (phase 2 holds `2.1`, `2.2`…).

## 4) The spine — `->`

`"a -> b[ | label]"` lines are the main path, drawn solid: the order the work runs in, from `start`
to `end`.

- **One spine.** One path runs left to right. Every other path leaves through an `offpage` step that
  names its own flow, or rejoins the spine within a column or two.
- **Only a gate branches.** Every `->` line out of a `gate` carries a label (V6): `Yes` / `No`, or
  the outcome's name. A model that picks a branch is V3.
- **A retry is fine.** A line back to an earlier step (`check -> draft | fails`) is drawn, but it
  does not push its target to the right: it reads as a return, not as another stage.

## 5) Plumbing — `~>`: Reads, Writes and Knowledge

`"a ~> b[ | label]"` lines are the plumbing, drawn as thin dashed lines beneath the spine. The
direction is the meaning:

| Line | On the step card | Means |
|---|---|---|
| `store ~> step` | `Reads: store` | The step looks something up in the store. |
| `step ~> store` | `Writes: store` | The step writes the store. |
| `source ~> step` | `Knowledge: source` | The step relies on the knowledge source. |
| `step ~> source` | `Writes: source (knowledge)` | The step maintains the source. |

- A step that reads and writes one store has two lines, one each way.
- Every `Reads`, `Writes` and `Knowledge` entry on a card is one line, and every line is one entry:
  writing the cards first is how you find every store and source before the plumbing.
- One `knowledge` step per source, and one line per source into each step that uses it. Merging
  sources into one step hides which source feeds which step.
- Labels on plumbing are optional and short ("the fields to pull"). The clean register draws
  labels only on the branches out of a gate or a junction.
- A plumbing line has a store, artifact or knowledge step at one end (on a page drawing, a context
  or ephemeral step too). Two work steps are joined by
  `->` (the work hands on); data one passes to the other goes through the store they share.

## 6) Columns, and at most 3 steps per column (V14)

A flow has two sets of columns. **On a page** the kit builds its own: each phase is a run of
columns and its steps stack inside them, so nothing below applies and `col=` is not read
(`page-drawing.md` §3). **On Atlas's canvas**, and in `render --layout canvas`, columns are
placed this way, and V14 counts them:

- **The spine sets the column.** Columns count from 0 at `start`. Each step sits one column right
  of the furthest step whose `->` line leads to it.
- **A store, artifact or knowledge step that a step writes into** (`step ~> store`) takes that
  step's column, so it sits under the step that writes it. With several writers it takes the
  rightmost writer's column, which can sit in the next phase: give it `col=` to keep it in its own.
- **Anything else that no `->` line leads to** — typically a source or a store that steps only
  read (`source ~> step`) — stays in column 0. Give it `col=N`, the column of the step that reads
  it.
- **`col=N`** always wins over the computed column.
- **One band holds one step per column.** A second step aimed at a taken cell in the same band moves
  to the next free column on its right. That is how a gate's two branches end up side by side when
  they share a band. The step that moved keeps its new cell, and the steps after it don't move
  with it: a later step in the band aimed at that cell moves on in turn, in the order the file
  lists them. One crowded cell can so shift a run of the band right while the other bands stay,
  and spill a phase into its neighbour. `lint --json` lists the column each step landed in
  (`columns`); pin the step that moved with `col=`, or give the branch a band of its own.

**V14: no column holds more than three steps, counted across all lanes.** The budget for a column
is the spine step, one store or sign-off, and one knowledge source. A gate's branches put two steps
in the next column: keep each branch short and rejoin, or send the other path out through an
`offpage` step. `lint` counts after layout and names the column and its steps. A lane stacking
three or more parallel rows of steps is a matrix, not a flow.

## 7) Ids, titles and step numbers

- **Ids:** lowercase letters, digits and `_`, starting with a letter, at most 32 characters, unique
  in the file. Short and meaningful: `extract`, `review`, `log`.
- **Titles:** at most 60 characters (Atlas cuts the rest), with no `|` or `"`.
- **Step numbers go in the titles.** Every work step's title starts with its number, from the step
  card (`process-step-card.md` §1): `1.1 Diff vs last week`, and a gate's the same way:
  `1.2 Last week closed out?`. `start`, `end`, stores and knowledge carry no number: the store
  directory says which steps touch them. A number at the start of any title (`3`, `1.2`, or a range
  such as `2.3–2.6` for a step that stands for several) is read as the step's number, so a count
  goes later in the title: `Collect the 12 fields`, not `12 fields collected`. A word that only
  starts with digits (`10x`, `24h`) stays in the title. A step left out of the flow on purpose
  (housekeeping that would clutter the spine) is named in the prose as text-only.
- **Store titles** name the store, then the tool: `Invoice log (Airtable)`.
- **Knowledge titles** read `[RAG] <name> v<n>`: `[RAG] Extraction schema v1`, where `v1` is the
  version it ships as once written. The link stays on the card and in the store directory, not in
  the title.
- **Clean register:** at most four words after the number. Both registers show the number on a tab
  at the top of the box, so a drawing and its step cards match by number alone.

## 8) Caps

200 steps and 300 flow lines; titles past 60 characters and phase names past 40 are cut, and a step
with an unknown kind is dropped. A flow anywhere near the caps is generated, not drawn: split it
into flows joined by `offpage` steps.

---

## 9) A starter file

```yaml
---
name: <slug>
originalName: <Process name>
type: workflow
category: <a digit 0–9, or a category name such as operations>
description: "<one sentence: what the flow does, from its start to its end>"
executed_by: internal-user
steps:
  - "## <Phase 1>"
  - "start | start | Start · <the trigger>"
  - "<id> | input | 1.1 <title>"
  - "<id> | llm | 1.2 <title>"
  - "<id> | gate | 1.3 <question>?"
  - "## <Phase 2>"
  - "<id> | hitl | 2.1 <title>"
  - "<id> | store | <Store name> (<tool>)"
  - "<id> | knowledge | [RAG] <name> v1 | col=<the reader's column>"
  - "end | end | End · <the outcome>"
flow:
  - "start -> <id>"
  - "<gate id> -> <id> | Yes"
  - "<gate id> -> <id> | No"
  - "<hitl id> ~> <store id> | <what it writes>"
  - "<knowledge id> ~> <llm id>"
page:
  - "## <Phase 1> | <one line on what happens in this phase>"
  - "<id> | note=<a few words on the step> | run=<what runs it>"
  - "<id> | note=<what the store holds> | link=<https://… its source> | tip=<what opens>"
---

# <Process name>

<What the flow does, from its start to its end, in a few lines: its Input · Process · Output.>

## Steps

<One step card per step, numbered as the titles are (process-step-card.md §2).>

## Store directory

<Every store, then every knowledge source (process-step-card.md §4).>
```

Add `skills:` or `reads:` to the frontmatter only when a step binds a skill (`ref=<skill-slug>`)
or an Atlas note (`ref=atlas:<key>`). Add no `visibility` key.

---

## 10) When the scaffold doesn't apply

- **A pure sequence diagram** (API call timing, messages passed between services): out of scope.
  Flow text has no lifelines.
- **A single-user tool with almost no backend:** still the same lanes; the backend may hold one
  step.
- **An architecture-only component diagram** (system components, no process flow): out of scope.
  For the FE/BE/DB view as a slide page, use `slide-arch-diagram`.

Otherwise: use the scaffold. Always.
