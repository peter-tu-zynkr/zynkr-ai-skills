---
name: ops-workflow-design
sheetId: "5.03"
description: "Read, draft, edit and validate process flows as flow text — the workflow body Zynkr Atlas stores: `steps:` and `flow:` lines under `## <phase>` headers — on the FE/BE/DB three-layer convention, and draw each flow one of two ways: as a workflow draft in Zynkr Atlas when a team or a client runs it, a step uses a skill or a note, or it needs sign-off; otherwise as a page drawing, a self-contained SVG that the bundled Python kit renders and lints. Triggers whenever the user asks to diagram, chart, visualize, read, summarize, edit or lint a process or workflow, names an Atlas workflow, or pastes flow text. Fires eagerly on '幫我畫流程圖', '畫流程圖', '流程圖', 'draw this workflow', 'diagram this', 'visualize this process', 'turn this SOP into a flow', 'check this flow', '/ops-workflow-design', and on a pasted lucid.app link: Lucid is retired, so it asks for the flow text, the Atlas workflow, or the chart's exported PDF or PNG instead. Use it even when the user names no tool: if they want a process flow drawn, read back or checked, this skill applies."
category: product
project: ops-workflow-design
platform: claude
status: Done
visibility: public
author: Peter Tu
input: "A process description or step cards, flow text (a file, or an Atlas workflow slug), a change or lint request on a flow, or an exported chart image"
process: "Pick the job (read · draft · edit · validate) → step cards → flow text on the FE/BE/DB convention → lint with the kit → route: an Atlas workflow draft, or a page drawing (phases as columns, steps stacked, hover and links) that is rendered, linted and looked at"
output: "A narrated flow with step cards, an Atlas review link (a draft, never approved), a page drawing (SVG or HTML fragment), or a lint report (rule · severity · step ids · fix)"
synergy: []
house-style: bound

---

# Ops Workflow Design

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill ops-workflow-design
```

This skill reads, drafts, edits and validates process flows on the FE/BE/DB three-layer convention.
Every job works on one **flow text**: the workflow body Zynkr Atlas stores, `steps:` and `flow:`
lines under `## <phase>` headers. The same text is drawn one of two ways. A flow that people run,
that uses a skill or a note, or that needs sign-off becomes a **workflow draft in Atlas**, which a
person reviews. Anything else becomes a **page drawing**: a self-contained SVG that the bundled kit
renders and lints, ready to sit on an HTML page. Lucid is retired: this skill makes no Lucid chart.

Four jobs:

1. **Read** — narrate a flow from its text: an Atlas workflow, a flow file or pasted flow text.
2. **Draft** — turn a process description into step cards, then flow text, then an Atlas draft or a
   page drawing.
3. **Edit** — change a flow without breaking the convention: a new Atlas version, or a new drawing.
4. **Validate** — check a flow against the rules V1–V14 in `references/validation.md`.

---

## Configuration

This skill drafts into a Zynkr Atlas workspace it does not ship.

1. **Why it is withheld:** a flow belongs to the team or the client that runs it, and lives in their
   own workspace, where a person reviews every draft before it serves anyone.
2. **The configure slot:** the `zynkr-atlas` MCP server, connected with an Atlas token of your
   workspace minted with 「可以建立草稿」 (it may draft). The tools this skill calls
   (`mcp__zynkr-atlas__<tool>` when the server is connected under that name):
   - `get_artifact_body` — read a workflow's live body (READ, EDIT)
   - `draft_new_item` — a new workflow, as a draft sent for review (DRAFT)
   - `draft_new_version` — a new version of a workflow, as a draft sent for review (EDIT)
   - `list_pending` and `get_draft` — what waits for review, and a waiting draft's body and diff
3. **What the workspace must contain:** nothing to start with: DRAFT creates the workflow. EDIT
   needs the workflow to exist and to be authored in Atlas.
4. **The Zynkr default:** Zynkr's own Atlas workspace, through the `zynkr-atlas` server. There is
   nothing to fill in beyond the token.
5. **Not found:** without the Atlas tools, or with a token that may not draft (Atlas answers
   `not_permitted`), the skill makes page drawings only. DRAFT returns the flow text and a page
   drawing and says why; READ and EDIT work on flow files and pasted flow text; an Atlas slug gets a
   request for the flow text. Never file the flow anywhere else instead.
6. **Loaded at run time:** the workspace and its workflows are read on every run; nothing from them
   is copied into this file.

The approve tools (`decide_version`, `publish_version`) are never this skill's to call, even when the
token has them: a person decides every draft in Atlas.

**The architecture canon (optional).** `references/architecture-principles.md` is the working copy
of the company's architecture canon, and the skill works from the copy. Open the canon itself only
when a judgment call turns on a principle the copy doesn't settle, or the user asks where a rule
comes from. `<your-architecture-canon-doc>` is a company fact — read it
from Atlas (`get_knowledge`, key `company.architecture-canon`, on the `zynkr-atlas` MCP server; the
value is the `value:` line, and its `url:` line is the link). If Atlas cannot be reached, the key is
missing, or there is no `value:` line, work from the local copy
`references/architecture-principles.md` and say the canon was not read. Never open a link with the
blank still in it.

**The kit** needs `python3`, version 3.9 or newer, and nothing outside its standard library: a
Mac's own `/usr/bin/python3` is enough.

---

## Required reading

The skill is a bridge between the convention and the two renderers. The convention lives in the
references; read them so you can recover the *why* when a judgment call comes up.

| File | Read when |
|---|---|
| `references/architecture-principles.md` | Always: the FE/BE/DB three-layer model, the decision flow, golden rules, anti-patterns. |
| `references/shape-color-principles.md` | When you need Shape × Color restated briefly (shape = what the step is; colour = who owns it and how it runs). |
| `references/encoding-table.md` | Always when you read, draft or edit: each encoding row, its step kind, its shape and its role in the colour registry. |
| `references/scaffold.md` | Always when you draft: the flow-text scaffold — phases, the spine, plumbing, lanes by kind, columns and V14, titles. |
| `references/page-drawing.md` | Always before a page drawing: what the standard drawing holds, the `page:` list that fills its cards, how its columns are made, and what to check when you look. |
| `references/validation.md` | Always when you validate, and as the self-check after every draft or edit: V1–V14 and where each is checked. |
| `references/worked-examples.md` | When you want a READ or a DRAFT to model your output on, written as flow text. |
| `references/process-step-card.md` | Always when you read or draft: the step card (number · Input · Process · Output · layer · Reads · Writes · Knowledge) every step is reported in. Shared with `ops-transformation` and `ops-flow-optimization`. |
| `references/flow-colours.json` | Never by hand: the colour registry the kit reads. It is the only place a colour value lives. |

---

## The flow text

One flow is one Markdown file with YAML frontmatter: exactly the body an Atlas workflow holds, so
the same file drafts into Atlas or renders as a page without a change.

- **`steps:`** — one quoted line per step:
  `"<id> | <kind> | <title>[ | ref=… | by=internal|external | col=N]"`.
  - `id` — lowercase letters, digits and `_`, starting with a letter, at most 32 characters,
    unique in the file.
  - `title` — at most 60 characters, with no `|` or `"`. A work step's title starts with its step
    number (`1.1 Diff vs last week`); a knowledge source's title reads `[RAG] <name> v<n>`.
  - `ref=<skill-slug>` binds the step to a skill and `ref=atlas:<key>` to an Atlas note; `by=` puts
    a front-end step with an external or an internal person; `col=N` sets its column.
- **`"## <phase>"`** lines inside `steps:` start a phase: the steps below, up to the next header.
  A phase name has at most 40 characters.
- **`flow:`** — one quoted line per line drawn:
  - `"a -> b[ | label]"` — the spine: the order the work runs in, drawn solid.
  - `"a ~> b[ | label]"` — plumbing: reads, writes and knowledge, drawn dashed. The direction is
    the meaning: `store ~> step` is a read, `step ~> store` a write, `source ~> step` knowledge the
    step relies on, `step ~> source` a source the step maintains.
  - Everything after a line's first `|` is its label.
- **Kinds** — the twelve Atlas knows: `start` `end` `input` `output` `hitl` `llm` `deterministic`
  `gate` `store` `artifact` `knowledge` `offpage`. Three more are page-only: `context`, `junction`
  and `ephemeral` (encoding rows 4, 13 and 15). The kit draws them; Atlas has no kind for them and
  would drop the step, so a flow that uses one stays a page drawing.
- **Caps** — 200 steps and 300 flow lines; titles past 60 characters and phase names past 40 are
  cut. Atlas drops a step with an unknown kind, and lint reports it as `parse`.
- **`page:`** — optional, read by the kit only: what a card shows on a page beyond its title.
  `"<id> | note=… | run=… | link=https://… | tip=… | break"` for a step, and
  `"## <phase> | <one line>"` for the line under a phase's name
  (`references/page-drawing.md` §2). Atlas ignores the list, so the file still drafts unchanged.
- **The prose** below the frontmatter says what the flow does, then carries the step cards and the
  store directory. Input · Process · Output live there: the grammar has no field for them.

An abridged example (a complete file is `scripts/fixtures/example-2.md`):

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
  - "schema | knowledge | [RAG] Extraction schema v1 | col=2"
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
---
```

---

## The kit — `scripts/flow_svg.py`

One file on Python's standard library. Run it by its full path, with `-I`, from any folder.
`<skill>` below is this skill's base directory: the harness prints it when the skill loads, and an
install puts it at `~/.claude/skills/ops-workflow-design`.

```bash
python3 -I <skill>/scripts/flow_svg.py render <flow.md> [--embed] [--layout stacked|canvas] [--stack 2-6] [--out <file>] [--lang en|zh-TW] [--register audit|clean] [--registry <path>]
python3 -I <skill>/scripts/flow_svg.py table <flow.md> [--lang en|zh-TW] [--out <file>.html]
python3 -I <skill>/scripts/flow_svg.py lint <flow.md> [--layout canvas|stacked] [--register audit|clean] [--stack 2-6] [--lang en|zh-TW] [--json]
python3 -I <skill>/scripts/flow_svg.py --selftest
```

- **`render`** writes the page drawing (`references/page-drawing.md`). The lanes run FE · BE · DB,
  each phase is a run of columns with its steps stacked inside, each step takes its kind's shape
  and fill, and a card shows its number, its name and what `page:` adds: a note, what runs it, a
  link. A store lists the steps that write and read it. Hovering a step lights only its lines.
  - Every colour is written inline from the registry: no external reference, no dark theme. The
    drawing's one style block holds the hover rules and no colour. The root carries the
    registry's version (`data-flow-colours`), and the same input gives the same bytes.
  - **`--embed`** writes an HTML fragment for a page instead of a bare SVG: the legend, a
    fit-to-width button, a box that scrolls sideways and the drawing inline.
  - **`--layout canvas`** draws Atlas's own columns instead, one step to a row and column, with no
    notes, links or hover: a preview of how a draft will sit in Atlas, not a page drawing.
  - `--stack` sets how many backend steps a column holds (4 unless you say). `--lang` picks the
    language of the lane titles and the legend; `--register` is below (Two registers).
- **`table`** writes the steps table for under the drawing: one row per work step, numbered as
  the drawing is, with the stores it reads and writes taken from the `~>` lines.
- **`lint`** names the rule and the step ids, and exits 1 on any rule it finds, soft ones
  included: V4, V5, V6, V9, V12 (label length), V14 (counted after layout), two boxes, labels or
  phase bands that overlap, and a step or line Atlas would not draw or a title or phase name it
  would cut (`parse`). V5, V9 and V12 are soft, the rest hard (`references/validation.md`). It warns, without
  failing, on a page-only kind or a step option it can't read, and notes a `page:` line it
  skipped. `--json` prints the same report as JSON, with the column each step landed in
  (`columns`). A clean flow exits 0.
  - Plain `lint` checks the flow as Atlas will draw it, V14 included. Every flow passes it before
    it is drafted into Atlas.
  - **`lint --layout stacked`** checks the page drawing instead: the same rules without V14 (the
    page builds its own columns), with overlaps and long card text measured on the stacked
    drawing. Give it the `--register`, `--stack` and `--lang` you render with, so it measures the
    drawing you ship: a label the clean register leaves off can't overlap there.
- **Exit 2** from any command means the kit could not run (a missing file, a bad registry). It is
  never a pass: say what it printed.
- **`--selftest`** checks the kit against its fixtures: parsing and columns against Atlas's own
  results, and one bad fixture per lint rule. Run it after an install or an update; it must exit 0.
- **Colours** come only from `references/flow-colours.json`. Never write a colour value: not in
  flow text, not on the page around a drawing, not in a reply. A workflow drawing uses workflow
  colours only, never a brand colour.

---

## Workflow — pick the job

Read the user's message and pick one:

| The user says (or implies) | Job | Go to |
|---|---|---|
| Names an Atlas workflow (a slug or its link), or hands over a flow file or flow text with no direction | **Read** | READ |
| "Read / explain / summarize this flow" | **Read** | READ |
| Pastes a `lucid.app` link (Lucid is retired) | **Read** — the retired answer | READ |
| Hands over a chart exported as PDF or PNG | **Read** — as an image | READ |
| "Draw / diagram / chart / visualize this process", "turn this SOP into a flow", 「幫我畫流程圖」 | **Draft** | DRAFT |
| "Add X to this flow", "change step Y", "move this step" | **Edit** | EDIT |
| "Lint / check this flow", "does this follow our convention?" | **Validate** | VALIDATE |

If it is ambiguous (they hand over a flow *and* a process description), ask one question: "Read the
existing flow, or draft a new one from your description?"

---

## READ — flow text → narrative

**What it takes:**

- **An Atlas workflow** — a slug, or its link (`…/w/<workspace>/workflows/<slug>`; the slug is the
  last part): `get_artifact_body(slug)`. Atlas's answer opens with a header (the title and version,
  `Provenance:`, `Visibility:`, `Cites:`) and then fences the body in a ```` ```markdown ```` block:
  the flow text is that block's content, from its `---` line to the line before the block's closing
  fence. The body may hold fences of its own, so the closing one is the last ```` ``` ```` line
  before `[End of Atlas reference text]`. Save it alone as a `.md` file and work on that. A workflow with no live version yet: `list_pending`
  and `get_draft` show its waiting draft. Without the Atlas tools, ask for the flow text.
- **A flow file, or pasted flow text** — read it as it is.
- **A pasted `lucid.app` link** — Lucid is retired: don't open the link, and never call a Lucid tool,
  even when one is connected. Answer in the user's language, along these lines:
  "Lucid is retired, so I don't open its links. Send me one of these instead: the flow text (its
  `steps:` and `flow:` lines), the Atlas workflow the flow lives in now (a slug or a link), or the
  chart exported as PDF or PNG, which I'll read as an image."
- **An exported chart (PDF or PNG)** — read it as an image: the lanes, each box's shape and colour
  against `references/encoding-table.md`, and the arrows. Number the steps as below, mark everything
  read off the picture `(inferred)`, and offer to write it as flow text (DRAFT).

**Then:**

1. **Lint it** (`lint <flow.md>`) for the convention notes.
2. **Narrate, top-down** — the reader wants the gestalt first:
   - **Outcome** — what the flow starts and ends with (its `start` and `end` steps).
   - **Steps, phase by phase** — under each `## <phase>`, one **process step card** per step in
     spine order (`references/process-step-card.md`), a branch's steps right after the gate that
     leads to them. Each card carries the step id: `**1.1 · Diff vs last week** (`diff`) — when ·
     layer`.
     - Numbers come from the titles. List any gap in the numbering in one line (steps the flow
       leaves to its source document). If the titles carry no numbers, number the steps 1, 2, 3…
       and say so. A work step with no number in a flow that numbers the rest keeps `—` for its
       number, and the gap line names it by id.
     - The layer comes from the kind: `input` and `output` → Front end · external or internal
       (`by=`, else the frontmatter's `executed_by`); `hitl` → Backend · human; `deterministic` →
       Backend · rules; `gate` → Backend · rules (gate); `llm` → Backend · AI; `offpage` → a
       hand-off to another flow.
     - Input · Process · Output come from the cards in the prose when the body carries them;
       otherwise from prose that walks the steps without cards, or from the title and the lines,
       marked `(inferred)`, or `not in the flow text` rather than invented. Say it once above the
       cards when no step carries them.
     - Reads, Writes and Knowledge come from the `~>` lines and their direction
       (`references/scaffold.md`): `none` when there are none.
     - Never group the steps by layer: the reader needs each step's FE / BE / DB on the step itself.
   - **Decision gates** — each `gate` with its labelled branches, by step number.
   - **Store directory** — the `store` and `artifact` steps first, then the `knowledge` steps
     (`references/process-step-card.md` §4): each store once, with written by and read by; each
     source once, with read by and maintained by. Flag a store nothing writes or nothing reads, and
     an `llm` step with no knowledge line: it answers from the model alone. A store the flow draws
     twice on purpose (last week's and this week's copy) is one entry, and say so.
   - **Convention notes** — whatever lint and the judgment rules found, by rule and step id.
3. **End with the source**: the Atlas slug and its link, or the file path.

A worked READ is in `references/worked-examples.md`.

---

## DRAFT — process description → flow text → Atlas draft or page drawing

1. **Extract the layers** with the decision flow in `references/architecture-principles.md` §4.1,
   step by step:
   - Surface: front end external, front end internal, or not front end?
   - Execution: a person (HITL), fixed rules, or an LLM?
   - Persistence: a durable record, session-only context, or nothing?
   - Knowledge: retrieved (searched by meaning) or enforced (applied exactly)?
2. **Write a process step card for every step** (`references/process-step-card.md`) before any flow
   text: a number, Input · Process · Output, the layer from step 1, the stores it Reads and Writes,
   and the knowledge it relies on (`none` when it uses none). If you can't fill Input, Process and
   Output, ask one targeted question instead of guessing. **Keep the source's step numbers**: a
   process from `ops-transformation`, `ops-flow-optimization` or a numbered process document keeps
   its numbers (1.1, 3.2…) unchanged; one with none gets them assigned (stage `.` step), and the
   list goes back with the flow. The cards' Reads, Writes and Knowledge lines are exactly the `~>`
   lines you will write, so writing them first is how you find every store and source.
3. **Write the flow text** (`references/scaffold.md`) in this order. When the user reviews along,
   show the spine before the plumbing: text is cheap to change.
   1. **The spine.** One step per card, start to end, each with its final kind: Front end →
      `input` or `output`; Backend · human → `hitl`; Backend · rules → `deterministic`, or `gate`
      when it branches; Backend · AI → `llm`. Then the `->` lines in the order the work runs, with a
      label on every branch out of a gate. **Decide the spine here (V14):** one path runs left to
      right, and every other path leaves through an `offpage` step that names its own flow.
      Choosing this late is a re-architecture, not a nudge.
   2. **The front end.** `input` where a person types or uploads, `output` where a person sees a
      result. The frontmatter's `executed_by` (`external-user` or `internal-user`) says who sits at
      the front end; `by=` overrides it for one step.
   3. **Stores and knowledge.** One `store` step (or `artifact`, for a durable document) per data
      store and one `knowledge` step per source on the cards, then a `~>` line for every Reads,
      Writes and Knowledge entry, in its direction. Give a source that steps only read a `col=`, so
      it sits under the step that reads it.
   4. **Phases.** A `## <phase>` header over each stage, beat or day.
4. **Lint** — `python3 -I <skill>/scripts/flow_svg.py lint <flow.md>`. Exit 1 names the rule and the
   step ids: fix the text and lint again until it exits 0. Then walk the checks lint can't do
   (`references/validation.md`: the kind checks V1, V2, V3, V8 and V10, and V7). Settle them now: a
   fix after an Atlas draft is filed waits for a reviewer. When lint names a V14 or an overlap,
   `lint --json` lists the column each step landed in (`columns`), so you can see which step moved.
   A flow that will only ever be a page drawing lints with `--layout stacked` instead: V14 counts
   Atlas's columns, which that drawing doesn't use.
5. **Route it** — three questions about the flow:
   - Does the team or a client run it?
   - Does a step use a skill or a note (a step with `ref=`, or one that should have it)?
   - Does it need sign-off before anyone uses it?

   **Material for students, a cohort or a workshop:** the place they draw a workflow is Zynkr
   Atlas, which the course or workshop provides. Every flow there takes its kind's lane from the
   step itself, and a step can bind to the skill it uses. Never tell them they need an account
   with another drawing tool.

   **Any yes** → an Atlas draft (step 6). **All no** → a page drawing (step 7). A flow with a
   page-only kind is a page drawing whatever the answers, and the reply says why: Atlas would drop
   those steps. Without the Atlas tools, or with a token that may not draft, say so and return the
   flow text plus a page drawing (step 7).
6. **An Atlas draft** — only on the user's word. Say which question answered yes and ask "Draft it
   in Atlas?", unless the request already asked for Atlas.
   - The body is the whole linted file, frontmatter included: `name:` equal to the slug,
     `type: workflow`, a `description:`, a `category:` if you know it (a digit 0–9 or a name such as
     `operations`), and **no `visibility` key** — no key means team, and Atlas refuses
     `visibility: client`.
   - A step with `ref=` draws only when Atlas's graph backs it, so list the skill in `skills:` or
     the note in `reads:`. One step per ref: Atlas drops a second step that names the same one. A
     note still in draft is not in the graph yet, so its step stays hidden until the note is
     published. Lint can't see Atlas: check that each ref exists before you file — `get_context`
     for a skill, `get_knowledge` for a note — and drop or fix one that doesn't.
   - Call `draft_new_item(type: "workflow", slug: <a new slug>, body: <the file>, notes: <one line
     for the reviewer>)`. A slug is 2–64 characters of `a–z`, `0–9` and dashes. `slug_taken` means
     the workflow exists: that is an EDIT. Any other refusal (`not_permitted`, `daily_cap`,
     `invalid_category`…) wrote nothing: say what Atlas said, and offer the page drawing.
   - Check it: `list_pending`, then `get_draft` on the new version. Its sha256 equals
     `shasum -a 256 <flow.md>`, so the stored body is the linted one. `parsed: no · would be refused
     now: needs_resolve` is normal for a version Claude drafted: Atlas reads its references before it
     can be approved (the reviewer's 重新解析 in 審核 does it, or approval does it first). Nothing
     for you to do.
   - Return the review link the tool gave (Atlas's review queue, where the draft waits), and the
     workflow's own page beside it: the same address with `/workflows/<slug>` in place of
     `/review`. That page says the draft waits for review until a reviewer approves it, then draws
     the flow.
   - Approve nothing.
7. **A page drawing** (`references/page-drawing.md`).
   - **Fill the cards.** Add a `page:` list: one line under each phase's name, and for each step a
     `note=` of a few words and a `run=` naming what runs it. Add `link=` and `tip=` where the
     step's source is known: the skill's page, the Atlas note, the Sheet, the page that explains
     it. Never guess an address: a step with no known source gets no link, and the reply lists
     those steps as links still to add.
   - **For a page**, `python3 -I <skill>/scripts/flow_svg.py render <flow.md> --embed --out
     <name>.html`, and `table <flow.md> --out <name>-steps.html` for the steps table under it.
     **For a file on its own**, `render <flow.md> --out <name>.svg`. Add `--lang zh-TW` for a
     zh-TW flow and `--register clean` for stakeholders (Two registers, below).
   - `lint --layout stacked`, with the same `--register`, `--stack` and `--lang` as the render,
     exits 0 on the same file; lint again if you changed it since.
   - **Look at it.** With Playwright connected, open the SVG (`browser_navigate`) and take a
     screenshot (`browser_take_screenshot`). Playwright may refuse a `file://` path: then copy the
     SVG into an empty folder of its own, serve that folder to this machine alone
     (`python3 -I -m http.server <port> --bind 127.0.0.1 --directory <folder>`, in the background),
     open `http://127.0.0.1:<port>/<name>.svg`, and stop the server after the screenshot. A
     navigation that times out on an SVG has often loaded it: take the screenshot before you retry.
     Look for cut titles, crowded columns and lines that cross a box, and hover one step with
     several lines (`browser_hover`): only its lines stay dark. For an `--embed` fragment, wrap it
     in a bare HTML page in that folder and open that. Fix the text and render again. When lines
     crowd, give the drawing room: move a phase boundary, start a new column with `<id> | break`
     in `page:`, or send a side path out through `offpage` (`references/page-drawing.md` §3). A
     wide drawing may scroll on its page. Never squeeze it instead: no titles cut short to make
     room, no lines laid over one another or through a box. Without Playwright, the reply says the drawing
     was linted, not looked at. Playwright saves the screenshot in the session's working folder and logs under `.playwright-mcp/` there:
     when that folder is a repository, delete both once you have looked, so neither lands in a
     commit.
   - Return the path of the SVG, or of the fragment and its table.
8. **Report** — a one-paragraph narrative of what you built, the step cards and the store
   directory numbered as the titles are, then the review link or the drawing's path as the last line.

Never make a Lucid chart: Lucid is retired.

A worked DRAFT (CSV upload → AI extract → reviewer approves → invoice log → notify) is in
`references/worked-examples.md`.

---

## EDIT — change a flow

1. **Read first** (READ, briefly), so a new step lands in the right kind, phase and column.

**Lint before and after.** Lint the flow before you change it, then after. The change adds no
finding: every rule and step id the second lint names was in the first, apart from steps you
removed. A finding the flow already had stays unless the user asks for its fix: list it in the
return, by rule and step id, and offer the fix as its own edit. Fixing it unasked widens a review
the user did not ask for.

2. **A workflow in Atlas:**
   1. `list_pending` — if a draft of this workflow already waits, stop: a reviewer decides it in
      Atlas (審核) before another can be filed. Atlas answers `draft_waiting` otherwise.
   2. `get_artifact_body(slug)` — the live body. Save only the flow text, the fenced block's
      content (READ), as a local file and work there. The header above the fence is Atlas's, not
      the workflow's: filed with the body, it would leave the new version with no steps, since its
      first line would no longer be `---` (lint says so).
   3. Make the change. A new or changed step gets its step card first: its number follows
      `references/process-step-card.md` §1 (keep the parent number, renumber only the children it
      displaces, and give the `old → new` map).
   4. Lint it (before and after, above), and walk the checks lint can't do over what you changed.
   5. `draft_new_version(slug, body: <the whole file>, changelog: <one line>)`. Its version must be
      above every version of the workflow, drafts included. Leave `semver` out for a fix, and Atlas
      takes the next patch above the highest; give one for a bigger change (a minor for steps added
      or removed, a major for a new spine).
   6. **Atlas answers `file_owned`** → stop. The workflow is imported from its file in the
      workbench repository, which is its source of truth, so the change goes through the
      workbench, not through Atlas. Say so, and hand back the edited flow text for that change.
   7. `get_draft` shows the diff: only the lines you meant to change.
3. **A page drawing:** edit the flow text, lint (before and after, above), render again to the same
   path, and look (DRAFT step 7). A page drawing whose flow now answers yes to a routing question moves to Atlas with the
   same text: DRAFT step 6, on the user's word.
4. **Return** the review link or the SVG path, one line on what changed, the card of every step you
   added or changed (for a store or a source, its store-directory entry), the `old → new` map if
   anything was renumbered, and the findings the flow already had. Approve nothing.

---

## VALIDATE — check a flow against the convention

1. **Read** the flow (READ, minimally).
2. **Lint it:** `python3 -I <skill>/scripts/flow_svg.py lint <flow.md> --json` — V4, V5, V6, V9,
   V12 (label length), V14, overlaps and `parse` (titles and phase names Atlas would cut included), plus a warning
   for each page-only kind.
3. **Check the kinds** against the cards and the titles: V1, V2, V3, V8 and V10.
4. **Judge** V7.
5. **Report** in `references/validation.md`'s format — rule · severity · step ids · fix — with the
   flow's own step ids:

```
Lint of <slug or file> · <title>
Hard rule violations (ship-blockers):
- V<#> — <step id> (<title>)[, <step id> (<title>)…]: <what is wrong>. Fix: <the fix>.
Soft observations:
- V<#> — <step id> (<title>): <what is wrong>. Fix: <the fix>.
Warnings:
- <code> — <what Atlas would drop, or the option it can't read>
Total: N hard, M soft.  /  Clean — no convention violations.
```

The renderer keeps V12's legend and empty lanes and V13 (a) and (b), so a kit drawing needs no
check for them; V11 and V13 (c) are retired. A chart handed over as an image is checked rule by
rule by eye, with the steps numbered as READ numbered them. If the flow is clean, say so; don't pad.

---

## Two registers: `--register audit` and `--register clean`

A drawing serves one of two audiences. Decide which before drafting, and ask if unsure:

- **Audit** (engineering, "what's under the hood"): every write, every source, full plumbing.
  Denser is fine.
- **Clean** (stakeholders, "make it human-readable", 「視覺友善」): the spine reads at a glance.

The same flow text renders in either register. Both draw a legend, so no one has to memorise the
colour code, and both leave out a lane row that holds no step. Both put each step's number on its
box: a drawing and its step cards match by number alone (`process-step-card.md` §1), whichever
register the drawing is in.

- **`--register audit`** shows every label and writes the step and line counts under the title.
- **`--register clean`** shows labels only on the branches out of a gate or a junction (a decision
  or a fork), and adds a short "how to read this"
  paragraph under the legend. Plumbing draws as a thin dashed grey line and recedes beneath the
  spine.

What the clean register asks of the flow text:

1. One step per real step, and one spine: alternative paths leave through `offpage` steps instead
   of stacking as rows.
2. Short titles: at most four words after the step number, and a `note=` of a few words. The
   detail goes on the step cards.
3. Distinct knowledge stays distinct: one `knowledge` step and one `~>` line per source, so the
   reader still sees which source feeds which step.

Both registers keep the convention and lint clean. The clean one spends its complexity budget on
clarity instead of completeness, and never drops information that changes meaning. Atlas's canvas
draws its own way: the register is a page option.

---

## Anti-patterns the LLM most often falls into

- **A matrix instead of a spine.** Alternative paths stacked as rows make a grid the reader scans in
  two dimensions. One path is the spine; the rest leave through `offpage` steps. V14.
- **A `store` for an index.** `store` is a durable system of record only; retrieval knowledge is a
  `knowledge` step. V1.
- **An LLM that picks the branch.** The LLM suggests; a `gate` enforces. V3.
- **Logic in the front end.** `input` and `output` capture and show; meaning belongs to a backend
  step. V2.
- **A kind picked for its colour.** The kind says what the step is, and the colour follows from the
  registry. V10.
- **Unlabelled gate branches.** Label every branch: `Yes` / `No`, or the outcome's name. V6.
- **HITL with no audit trail.** A `hitl` step writes its decision to a store. V4.
- **All knowledge in one step "to look clean".** Keep which source feeds which step as separate
  `knowledge` steps and lines; merging them hides real couplings.
- **A colour value written anywhere.** Colours live only in `references/flow-colours.json`.
- **A lane drawing built by hand.** A workflow on a page is what `render` writes, placed on the
  page as it is. A hand-built SVG or HTML lane carries its own colours, misses the lint, and can't
  move to Atlas as text. The stacked columns, the hover, the links and the store tags all come
  from the kit: a drawing that needs one of them needs a `page:` line, not a script of its own.
  The host page's brand rules stop at the drawing's edge.
- **One step to a column on a page.** `--layout canvas` is Atlas's preview. On a page it makes a
  long strip of title-only cards that nobody can take in at once.
- **Bare cards.** A page drawing whose cards show a title and nothing else has no `page:` list.
  Write the notes and what runs each step before you render.
- **A link nobody gave.** A `link=` is an address the user gave or one you opened. Never build one
  from a name.
- **The drawing as an image.** An `<img>` of the SVG loses the hover and the links. Put the
  `--embed` fragment on the page.
- **A crowded drawing squeezed to fit.** Lines that overlap or cut through a box hide which step
  feeds which. Give the drawing room (DRAFT step 7) and let it scroll; the fit button shows the
  whole of it.
- **A page-only kind in an Atlas draft.** Atlas drops the step without a word; the flow stays a page
  drawing.
- **Shipping without looking.** A page drawing ships after a clean lint (for an edit, one that adds
  no finding) and a look, or the reply says it was linted, not looked at.
- **Drafting without the user's word, or approving at all.** Draft into Atlas when the user says so;
  a person approves in Atlas.

---

## Output style

- Be terse. The user reads what you say, not your deliberations.
- A drafted or edited flow ends with the review link or the drawing's path as the last line.
- When reading, lead with the outcome (start → end) before details.
- Steps are always numbered step cards (Input · Process · Output · layer · Reads · Writes ·
  Knowledge), never separate FE / BE / DB lists: a reader learns whether a step touches the
  database from the step itself.
- When validating, "clean" is a complete answer.

---

## Limitations

- **An Atlas draft looks like Atlas's canvas, not like the page drawing.** The canvas marks each
  kind with a thin rail and a glyph, not the full fill; the page drawing carries the encoding.
- **Atlas can show less than the page.** The kit draws every step. Atlas hides a step whose `ref=`
  its graph doesn't back, and draws a line between two bound steps only when its graph holds that
  edge.
- **Page-only kinds keep a flow off Atlas** until Atlas has kinds for them.
- **Hover needs a current browser.** The fading uses the CSS `:has()` selector. A browser without
  it shows every line at full strength, and a touch screen has no hover: the drawing still reads,
  and the links still open.
- **Atlas shows none of `page:`.** Notes, links and phase lines are for the page drawing; on
  Atlas's canvas a step's detail comes from the skill or note its `ref=` binds.
- **Out of scope:** sequence diagrams (message timing between services), and architecture-only
  component diagrams; for the FE/BE/DB view as a slide page, use `slide-arch-diagram`.
- A team that still needs a Lucid file takes it from the Atlas workflow's Download Lucid JSON
  button; this skill neither reads nor makes one.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
