# The Page Drawing

A workflow on a page is drawn one way: **lanes, with each phase's steps stacked in a column**. The
kit's `render` draws it from the flow text. This file says what the drawing holds, what you add in
the flow text to fill it, and what to check when you look at it.

It became the standard on 2026-11-20 (SKB-154). Before that the kit drew a page in Atlas's own
columns, one step to a column: a 23-step flow came out thirteen columns wide, with a title and
nothing else on each card. The drawings people read most easily had been built by hand instead.
This layout is what those drawings had in common, now drawn by the kit.

Since 2026-11-21 (SKB-158) the page drawing is the **overview** unless someone asks for the detail:
each data box draws one line, and its tags list the rest (§7). A drawing made before then drew every
line; rendered again, it draws the overview.

---

## 1) What the drawing holds

| # | Pattern | What the reader gets |
|---|---|---|
| 1 | **Three lanes, a narrow gutter.** FE · BE · DB in large letters, the lane's full name small beneath. | Who does a step, from where it sits. |
| 2 | **A phase is a run of columns.** The phase's name sits above its columns, with one line on what happens there and a bracket over the columns it spans. A solid rule parts two phases; a dashed one parts two columns of the same phase. | The stages of the work, before any box is read. |
| 3 | **Steps stack inside a column.** A phase's backend steps run top to bottom, at most four to a column. A front-end step sits over the backend step it belongs to. | The whole flow on about one screen: 28 steps fit seven columns. |
| 4 | **A card says three things.** The step's number and name; under it a note of a few words on what kind of step this is; under that, in monospace, what runs it. | Enough to follow the flow without opening the step cards. |
| 5 | **A store sits under the step that writes it** and lists the numbers of the steps that write it (`W`) and read it (`R`). The kit takes both from the `~>` lines; a step with no number has its line and no tag. In the overview the store draws one line, from that step, and its tags carry the rest (§7). | Where data lands, and every step that touches it, without a line for each. |
| 6 | **Two kinds of line.** Solid is the next step. Thin dashed grey is a read or a write, and the arrow points the way the data moves. In the overview only a branch out of a gate carries a label. | The order of the work, apart from its data. |
| 7 | **Hovering a step calls out what it touches.** Its lines stay dark, and the cards it joins by any line in the flow text, drawn or listed, stay at full strength with a heavier outline. Every other line and card fades. A keyboard reader gets the same on a linked card. | One step's connections, the listed reads and writes included, in a drawing with forty lines. |
| 8 | **A card links to its source** when the flow text gives one: the name is underlined, and the link opens in a new tab with a tooltip saying what opens. | The skill, the note or the page behind a step, one click away. |
| 9 | **The page around it.** A legend above the drawing, a box that scrolls sideways, a button that fits the whole drawing to the page's width, and a table of the steps under it, numbered as the drawing is. | The legend stays readable at any zoom, and the detail sits next to the picture. |

A drawing that lacks 3, 4, 5, 7 or 8 is the old one-step-per-column drawing. Render it again.

---

## 2) What you write: the `page:` list

Everything a card shows beyond its title comes from one more list in the flow text's frontmatter.
Atlas reads `steps:` and `flow:` only, so `page:` changes nothing there: the same file still
drafts into Atlas.

```yaml
page:
  - "## Intake | The customer sends the file and AI reads it"
  - "extract | note=AI · reads every row | run=extract-invoice prompt"
  - "schema | note=The fields step 2 pulls | link=https://example.com/extraction-schema | tip=Opens the extraction schema"
  - "review | break"
```

| Line | Meaning |
|---|---|
| `"## <phase name> \| <one line>"` | The line under a phase's name. The name is the one in `steps:`. Two lines at most on the drawing. |
| `"<step id> \| note=<a few words>"` | The card's second line: what kind of step this is, in the reader's words (`Rules · same config, same list`). On a store, what it holds. `note=` may repeat; a card takes three lines of notes at most, under a title of three lines at most. |
| `… \| run=<what runs it>` | The card's third line, in monospace: the script, the connector, the prompt or the person. A step with `ref=` and no `run=` shows its ref (`/skill-slug`, `atlas:key`). |
| `… \| link=<https://…> \| tip=<what opens>` | Makes the card a link. `link=` takes an `https://` or `http://` address and nothing else; `tip=` is the tooltip. |
| `… \| break` | This step starts a new column inside its phase. |

Rules:

1. **A link is one someone gave you or one you opened.** A step with no known source gets no
   `link=`: list it in the reply as a link still to add. Never guess an address.
2. **Notes stay short.** A note is a few words, not the step card. Input · Process · Output stay
   on the step cards.
3. **A gate's note** draws under the diamond, to the right of its lower corner. Keep it to two
   short lines.
4. A line that names a step or a phase the file doesn't have, an option the kit doesn't know, or a
   link that isn't `http(s)` is skipped, and `lint` says so as a note. So is an option the drawing
   has no place for: `break` on a store (a store follows its writer), `note=` or `run=` on a
   junction (it shows its name only), and a phase line for a phase that holds only stores.
5. A line written twice for one step adds its notes together; a second `run=`, `link=` or `tip=`
   replaces the first.

---

## 3) How the columns are made

The kit decides the columns; the flow text only nudges them.

- Each phase takes its own run of columns, in the order `steps:` lists the phases.
- Inside a phase the backend steps fill a column top to bottom. Past four they spread over as few
  columns as hold them, as evenly as they go, the fuller columns first: five steps become three
  and two, nine become three columns of three, ten become four, three and three. `--stack N`
  changes the four (2 to 6).
- A front-end step sits in the column of the backend step it belongs to: a `start`, an `input` or
  a `context` document over the step after it, an `output` or an `end` over the step before it.
- A store or an artifact sits under the first step that writes it; when no step writes it, under
  the first that reads it. A knowledge source sits under its first reader.
- A phase that holds only stores gets no column and no heading: its stores sit under the steps
  that use them.
- `col=` is not read here. It places a step on Atlas's canvas only.

When a column reads badly, change the text, in this order:

1. **Move the phase boundary.** A phase that holds two different stages wants two `## <phase>`
   headers.
2. **`<id> | break`** at the step where a new column should start: before a gate whose branches
   need room, or where a retry loops back.
3. **Shorten** a title, a note or a label.
4. **`--stack 3`** for a flow whose cards all carry three lines.

Never squeeze instead: no title cut short to make room, no line laid over another or through a box.

---

## 4) Putting it on a page

```bash
python3 -I <skill>/scripts/flow_svg.py render <flow.md> --embed --lang zh-TW --out <name>.html
python3 -I <skill>/scripts/flow_svg.py table  <flow.md> --lang zh-TW --out <name>-steps.html
```

- **The overview is the default.** Add `--register audit` only when someone asks for every line on
  the page (§7).
- **`--embed`** writes one HTML fragment: the legend, the fit button, the scroll box and the
  drawing inline. Paste it into the page where the drawing goes. It writes no colour of its own
  outside the drawing: its text and borders take the page's. The figure breaks out of a narrow
  reading column to the drawing's own width, up to the window's, with a negative left margin, so
  a column that is a grid or a flex column does not grow to fit it. It centres on the column it
  sits in, so it belongs in a centred reading column, not beside a sidebar.
- **The drawing goes on the page inline**, as `--embed` writes it. An `<img>` shows the same
  picture with no hover and no links.
- **`table`** writes the table for under the drawing: one row per work step, numbered as the
  drawing is, with what it does, what runs it, and the stores it reads and writes, taken from the
  same `~>` lines. It carries no style of its own: style it as the page styles its tables. Its
  hooks are `table.zflow-steps`, `.zflow-num` (the step number), `code.zflow-run` (what runs the
  step, on its own line) and `td.zflow-none` (an empty Reads or Writes).
- **Without `--embed`**, `render` writes a standalone SVG with its title and legend inside: for a
  file someone opens on its own, or a look while drafting.
- Workflow colours stay inside the drawing. The page's own colours stop at its edge.

---

## 5) What to check when you look

Open the page fragment in a browser (SKILL.md, DRAFT step 7) and check:

1. Every phase that holds a step has its line, and no phase name is cut.
2. No card's text runs past its box; no gate note runs into the next column.
3. No line crosses a box or lies along another line.
4. Hover a step with several lines: its lines and the cards they join stay at full strength, and
   the rest fade. Hover a data box: every step on its tags lights, drawn line or not.
5. Every underlined name opens the page its tooltip names.
6. The fit button shows the whole drawing; pressing it again returns to full size.

`lint --layout stacked` reports an overlap or a card with too many lines before you look. Give it
the `--register`, `--stack` and `--lang` you render with: it measures the drawing those flags make.

---

## 6) Atlas's columns: `--layout canvas`

`render --layout canvas` draws the flow in the columns Atlas's canvas gives it, one step to a row
and column, with no notes, links or hover. Use it only to preview how a draft will sit in Atlas.
V14 (at most three steps in a column) is counted on these columns, and plain `lint` checks it: a
flow that will be drafted into Atlas passes plain `lint`. A page drawing answers to
`lint --layout stacked`, which builds its own columns and so has no V14 to break.

---

## 7) The overview and the detail

`render` on a page draws the **overview** (`--register clean`, the default for `--layout stacked`).
`--register audit` draws the **detail**, as Atlas's canvas does:

| Line in the flow text | Overview | Detail |
|---|---|---|
| `a -> b`, the spine | drawn | drawn |
| `~>` between a step and a data box (any step in the DB lane: a store, an artifact, a knowledge source, the page-only `ephemeral`) | one per box: the line from the step that placed the box in its column (§3) — its first writer, or, for a knowledge source or a box no step writes, its first reader; the first in the file when two share that column | every one |
| `~>` from a step with no number to a data box | drawn: a tag lists numbers, so it could list none | drawn |
| `~>` that joins no data box (a context document, a hand-off) | drawn | drawn |
| a label | only on a branch out of a gate or a junction | every one |

What the overview leaves undrawn it lists. The box's `W` and `R` tags name every step that writes or
reads it, the steps table gives each step its Reads and Writes, and hovering a step calls out every
card it joins. `render` prints the count on stderr ("drew 41 steps and 47 lines (33 more reads and
writes listed on their stores)"), and the note under the legend tells the reader where to look.

The flow text never loses a line to make the overview: the detail, the tags and the table are all
drawn from it. The detail lives in Atlas, whose canvas draws every line, or on a page drawn with
`--register audit` when someone asks for every line there.
