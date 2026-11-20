# Validation / Lint Rules

Fourteen rules (V1–V14), plus two checks only a layout or a parser can make. Each rule cites the
principle behind it (from `architecture-principles.md`), how to detect it in flow text, and how to
fix it. Apply them on every read, and as the self-check after every draft and edit.

---

## Where each rule is checked

Every rule has one home:

- **lint** — `flow_svg.py lint` checks it mechanically and names the rule and the step ids: V4, V5,
  V6, V9, V12 (label length) and V14, plus two boxes or labels that overlap, and a step or line
  Atlas would not draw (`parse`). `lint --layout stacked` checks the page drawing: the same rules
  without V14, with the overlaps and the card text measured on the stacked drawing its
  `--register`, `--stack` and `--lang` make (a title, a note or a phase line that takes too many
  lines is a V12).
- **kind** — settled when you pick each step's kind. The kind decides the step's lane, shape and
  fill, so a drawing can't break these rules; a wrong kind can. Check the kinds against the cards
  and the titles: V1, V2, V3, V8 and V10.
- **renderer** — `render` keeps it on every drawing, so a kit drawing needs no check: V12 (the
  legend and empty lanes) and V13 (a) and (b).
- **judgment** — read the flow: V7.
- **retired** — no longer a rule: V11 and V13 (c). The renderer sets the text size.

| Rule | In short | Home | Severity |
|---|---|---|---|
| V1 | `store` only for a durable system of record | kind | hard |
| V2 | No business logic in the front end | kind | hard |
| V3 | A gate decides, not an LLM | kind | hard |
| V4 | HITL leaves a durable audit trail | lint | hard |
| V5 | An LLM step has a fallback | lint | soft |
| V6 | Gate branches are labelled | lint | hard |
| V7 | Offpage is a boundary, not a hiding place | judgment | soft |
| V8 | Lanes run FE → BE → DB | kind | hard |
| V9 | Start and end at the boundaries | lint | soft |
| V10 | Colour matches meaning | kind | soft |
| V11 | Node text size | retired | — |
| V12 | Clean-register hygiene | lint (label length) · renderer (legend, empty lanes) | soft |
| V13 | Straight lines, legible lane headers | renderer (a, b) · retired (c) | soft |
| V14 | One spine; at most 3 steps per column | lint | hard |
| — | Two boxes or labels overlap | lint | hard |
| — | A step or line Atlas would not draw, or a title or phase name it would cut (`parse`) | lint | hard |

Severity sorts the report: a hard rule is a ship-blocker, a soft one an observation. **Lint exits 1
on every rule it finds, soft ones included**, so a kit drawing ships with neither. On a chart read
as an image, a soft finding is flagged, not blocking.

`lint` also **warns** on a page-only kind (`context`, `junction`, `ephemeral`): the kit draws the
step, but Atlas has no kind for it and would drop it, so the flow stays a page drawing. It warns on
a step option it can't read (a `by=` or `col=` with a bad value, an unknown option) too. A warning
never changes the exit.

---

## Hard rules (ship-blockers)

### V1 — `store` only for a durable system of record · kind

- **Principle**: `architecture-principles.md` §2 rule 5 ("Vector DB is an index, not truth"); §1.3
  A) Durable vs ephemeral.
- **Detect**: a `store` step (drawn as the cylinder) whose title or card says index, vector,
  embedding, RAG, retrieval or knowledge: something searched for meaning rather than a record kept.
- **Fix**: make it a `knowledge` step titled `[RAG] <name> v<n>`, read through `~>` lines. Keep
  `store` for durable records such as `WorkflowInstance`, `DecisionLog` or `CommandLog`.

### V2 — No business logic in the front end · kind

- **Principle**: §2 rule 1 ("FE shows intent; BE owns meaning").
- **Detect**: an `input` or `output` step whose title decides, calculates or applies a rule
  ("Calculate discount", "Check eligibility"). Pure UX is fine: "Validate the format", "Show the
  confirmation".
- **Fix**: split it. The front-end step keeps the surface (`input` or `output`), and a backend step
  (`deterministic`, `llm` or `hitl`) takes the meaning.

### V3 — A gate decides, not an LLM · kind

- **Principle**: `shape-color-principles.md` §5 rule 3 ("Prefer deterministic gates for
  branching").
- **Detect**: an `llm` step whose outgoing `->` lines choose between business outcomes (approve or
  reject, tier A or tier B): the model picks the branch. A `gate` always draws as a deterministic
  decision, so the kind settles the colour; what is left to check is that branching happens at a
  gate. An error or retry line out of an LLM step is a fallback (V5), not a decision.
- **Fix**: LLM suggests → gate enforces. One `->` from the `llm` step to a `gate`, and the labelled
  branches leave the gate.

### V4 — HITL leaves a durable audit trail · lint

- **Principle**: §2 rule 2 ("HITL appears in FE, but belongs to BE"); §5.1 (the HITL spec requires
  an audit record).
- **Detect**: a `hitl` step with no `~>` line to a `store` or `artifact` step.
- **Fix**: write the decision down: `<hitl step> ~> <decision log>`, with the log as a `store` step
  (`Decision log (new)` when it doesn't exist yet).

### V6 — Gate branches are labelled · lint

- **Principle**: `shape-color-principles.md` §5 (decisions are questions; outcomes must be
  explicit). Atlas warns on the same thing.
- **Detect**: a `->` line out of a `gate` with no label after the `|`.
- **Fix**: label it: `big -> review | Yes`, or the outcome's name. Unlabelled branches are
  ambiguity.

### V8 — Lanes run FE → BE → DB · kind

- **Principle**: the scaffold (`scaffold.md`).
- **Detect**: nothing to check on a kit drawing: lanes come from kinds and always run FE · BE · DB,
  top to bottom. A wrong lane is a wrong kind (V1, V2, V10). On a chart handed over as an image,
  check the order by eye.
- **Fix**: redraw it from flow text.

### V14 — One spine; at most 3 steps per column · lint

- **Principle**: two registers, `SKILL.md` ("one step per real step … at most three steps in a
  column"). The rule was always implied; an owner's ruling on 2026-09-01 made it a rule.
- **Detect**: a column holding **4 or more** steps, counted **across all lanes** after layout. Lint
  names the column as `col=` counts it, from 0, and its steps.
- **Where it applies**: Atlas's columns, which is what plain `lint` lays out. The page drawing
  builds its own columns (a phase is a run of columns, and its steps stack top to bottom inside
  them, `page-drawing.md`), so `lint --layout stacked` does not count V14. The rule's first half
  holds on both: one spine. On a page each column is one stretch of that spine read top to
  bottom, never a second path beside it.
- **Fix**: pick **one** path as the spine and run it left to right. Alternative paths leave the
  spine through an `offpage` step that names their own flow, and rejoin, if they do, as a
  plumbing line, never as another row. A column's budget is the spine step, one store or sign-off,
  and one knowledge source. A source that steps only read takes `col=` to sit under its reader
  (`scaffold.md`).
- **Why it's hard, not soft**: this is not cosmetics. A reader follows a process along one axis;
  parallel branch rows force them to read in two dimensions, and the sequence is lost. Fixing it
  late means re-deciding what the flow is *about*, which is a re-architecture, not a nudge, so it
  belongs before the draft.

### Overlap · lint

- **Detect**: two boxes, two labels or two phase bands overlap after layout. For phase bands lint
  names the steps in the columns both phases hold, each with its `col=`; `lint --json` lists every
  step's column.
- **Fix**: reorder the steps or the phases, or move one step with `col=`, so each phase holds
  neighbouring columns. A shorter title or label helps too.

### Parse — a step or line Atlas would not draw · lint

- **Detect**: the file holds something Atlas's parser drops: more than 200 steps or 300 flow lines,
  a step line without its three parts, an id that breaks the id rule (`scaffold.md` §7) or is used
  twice, an unknown kind, a second step naming the same `ref=`, a flow line that is neither
  `a -> b` nor `a ~> b`, or a flow line naming a step that isn't there. Also a file that does not
  open with its `---` line (a header pasted above it: Atlas then reads no steps at all), and a title
  over 60 characters or a phase name over 40, which Atlas cuts.
- **Fix**: fix the line: each step is `"<id> | <kind> | <title>"`, each flow line `"a -> b"` or
  `"a ~> b"`. Start the file at its `---`, and shorten a long title (the detail goes on the step
  card) or phase name. Atlas drops such a step or line, or cuts the title or the name, without a
  word, so the canvas would not show what the file says.

---

## Soft rules (observations)

### V5 — An LLM step has a fallback · lint

- **Principle**: §1.2 (LLM execution needs a deterministic shadow, a confidence threshold and a
  fallback path); §5.2 (the LLM spec checklist).
- **Detect**: an `llm` step with a path to an `output`, an `end` or an `offpage` step that passes no
  `gate` or `hitl` step, and with no error path of its own: a line back to an earlier step (a retry),
  or a labelled branch beside its main line, the line out with no label. A label on its only line out
  names the next step, and a step whose every line out is labelled sorts its result: neither is an
  error path, so each of its paths needs a check.
- **Fix**: add (a) a `gate` downstream that checks confidence or validity, (b) a `hitl` step that
  reviews the output, or (c) an error or retry line: a labelled branch out of the AI step beside its
  main line, or a line back to an earlier step.

### V7 — Offpage is a boundary, not a hiding place · judgment

- **Principle**: `shape-color-principles.md` §2 (the off-page link row).
- **Detect**: an `offpage` step whose title implies business logic ("Calculate eligibility",
  "Apply discount tiers"), or one that does work mid-flow instead of handing off.
- **Fix**: move the logic into a backend step (`deterministic`, `llm` or `hitl`). Keep the `offpage`
  step a pure hand-off ("Invoke the refund flow", "Emit RefundRequested").
- **Not V10**: the kind fits a hand-off; the work sits in the wrong step. Report it once, as V7.

### V9 — Start and end at the boundaries · lint

- **Principle**: `shape-color-principles.md` §2 (the terminal row).
- **Detect**: a `start` step with an incoming `->` line, or an `end` step with an outgoing one. By
  eye: a flow with no `start` or no `end` step at all.
- **Fix**: one `start` that only leads out, and an `end` (or more than one) that only takes lines
  in. Readers need to know where the flow begins and ends.

### V10 — Colour matches meaning · kind

- **Principle**: §6 / the Shape × Color convention.
- **Detect**: a kit drawing takes each step's fill from its kind through the registry, so the
  colour is wrong only when the kind is: a step whose kind contradicts its card (an `llm` step a
  person does, a `deterministic` step that is an LLM call, a `store` that is a document).
- **Fix**: change the kind. Never write a colour: colours live only in `flow-colours.json`.

### V12 — Clean-register hygiene · lint and renderer

- **Principle**: two registers, `SKILL.md`.
- **Lint** — a label longer than its place can hold: a step title that takes more than three lines
  in its box, a line label of more than two lines, or a phase name wider than its band. Fix:
  shorten it (verb + noun), and put the detail in the prose under the frontmatter.
- **Renderer** — both registers draw the legend and leave out a lane row that holds no step;
  `--register clean` shows labels only on the branches out of a gate or a junction.
- The rest of the clean register is how you write the flow text: short titles, and one `knowledge`
  step per source (`SKILL.md`, Two registers).

### V13 — Straight lines and legible lane headers · renderer

- **Principle**: readers track straight lines far more easily, and the lane titles are the first
  thing they read.
- **(a) Straight lines** — kept by the renderer: steps sit on shared rows and columns, and the
  router draws right-angled lines.
- **(b) Legible lane headers** — kept by the renderer: lane header fills come from the registry,
  which keeps dark fills off headers.
- **(c) Pinned text size** — retired: the renderer sets one text size.

### V11 — Node text size · retired

The renderer sets the text size of every step and label; there is nothing to pin.

---

## Lint output format

`lint` prints this report (and `lint --json` the same as JSON); a VALIDATE report keeps it:

```
Lint of <slug or file> · <title>
Hard rule violations (ship-blockers):
- V<#> — <step id> (<title>)[, <step id> (<title>)…]: <what is wrong>. Fix: <the fix>.
Soft observations:
- V<#> — <step id> (<title>): <what is wrong>. Fix: <the fix>.
Warnings:
- <code> — <what Atlas would drop, or the option it can't read>
Total: N hard, M soft.
```

Every line gives the rule, its severity (by the group it sits in), the step ids it is about (the
flow's own `id`s, never positions) and the fix. A group with nothing in it is left out. A finding
the kinds or judgment turned up (V1, V2, V3, V7, V8, V10) goes in its group the same way.

If clean, the report ends "Clean — no convention violations." instead of the total. Don't pad.

---

## Quick spot-checks (do these in under a minute)

From `architecture-principles.md` §10, restated for flow text:

1. Can behaviour change by changing an `input` or `output` title alone? → V2 (business logic
   leaked into the front end).
2. Is there a canonical source for each rule? → a `gate` that applies a policy should have a
   `knowledge` step for that policy, read into it with a `~>` line. If not, something's missing.
3. Is any decision only in chat or session context? → it should be persisted: V4.
4. Does every LLM step have a gate or a fallback after it? → V5.
5. Does every `knowledge` step name its source? → its title reads `[RAG] <name> v<n>`, and its
   card carries the link.
