# Visual Decision Framework (content relationship → visual building blocks)

> The judgment bible for slide-visual-selector (the third leg of the slide assistant relay).
> Purpose: take each page from `▸ Pages`, **look only at this page's "content relationship / message to convey"**, and map it to a set of directly-renderable building blocks: `{archetype, visual elements = pptxgenjs primitives, layout skeleton}`.
> Alignment: archetype names strictly match the archetype enum in SKILL.md; every visual element maps to a pptxgenjs primitive so the downstream slide-pptx skill can render it 1:1.


> **Brand-neutrality note**: this file's "brand note" column and rules consistently use **generic role terms** (decision color / accent color / dark base color / display font / numbering font); the actual color values and fonts are determined by the brand guide loaded via `./brand-source.md`, defaulting to a neutral preset when no brand is set. This file contains no specific brand's color codes or internal information.

---

## Core principle: define the message first, then choose the form

This framework holds a single belief, borrowed from Gene Zelazny's *Say It With Charts*:

> **What decides how a page should look is not "the data," nor "the topic," but "the one sentence (the message) this page wants to say."**

The same dataset—say "revenue across five regions"—yields completely different visuals depending on the message you want to make:

- Want to say "the East region is far ahead" → this is a **ranking** relationship → a sorted bar chart.
- Want to say "the East region accounts for half the whole company" → this is a **composition** relationship → a pie chart.
- Want to say "the East region has climbed steadily over three years" → this is a **trend** relationship → a line chart.

The data is identical, but because the message (the content relationship) differs, the form differs. So this framework's judgment is **not** "does this page have numbers," but "what is the relationship between the things on this page, and which single sentence do I want the audience to remember." Nail that sentence first, and the form almost falls out automatically.

This is also why Zelazny's flow is: **message → comparison type → chart form**, with the chart always being the last step, never the first.

### The title carries the conclusion (Minto's Pyramid Principle)

Paired with Barbara Minto's *The Minto Pyramid Principle*: each page's **title is that page's conclusion (the action title)**, not a topic name.

- ❌ Topic name: "Q3 Revenue"
- ✅ Action title: "Q3 revenue grew 28%, driven by the single East market"

Once the title is written as a conclusion, the visual's job is pinned down: **the visual's only job is to "act out" the title sentence for the audience**—not to decorate, not to supplement, not to open a new topic. When judging the visual, always ask back: "Does this visual support the conclusion in the title?" If not, either change the visual, or the title was written wrong.

Combining these two principles, this leg's per-page judgment flow is:

```
Read the action title (this page's conclusion)
  → Ask: to support this conclusion, what "relationship" do the contents have to each other? (18 types in the table below)
  → Map to {archetype, visual elements = pptxgenjs primitives, layout skeleton}
  → The visual serves only that conclusion, opens no new topic
```

---

## Table of contents

- [Core principle: define the message first, then choose the form](#core-principle-define-the-message-first-then-choose-the-form)
- [Three rules that must hold](#three-rules-that-must-hold)
- [Quick lookup table (content relationship → building blocks)](#quick-lookup-table-content-relationship--building-blocks)
- [archetype enum and render-primitive mapping](#archetype-enum-and-render-primitive-mapping)
- [Detailed judgment for each content relationship](#detailed-judgment-for-each-content-relationship)
  - [1. assertion single claim / high emphasis → big-statement](#1-assertion-single-claim--high-emphasis--big-statement)
  - [2. parallel list parallel points → bulleted-list](#2-parallel-list-parallel-points--bulleted-list)
  - [3. comparison trade-off → two-column-compare](#3-comparison-trade-off--two-column-compare)
  - [4. ranking ranking / size → data-chart (bar)](#4-ranking-ranking--size--data-chart-bar)
  - [5. time-series trend → data-chart (line)](#5-time-series-trend--data-chart-line)
  - [6. composition make-up / share → data-chart (pie/stacked)](#6-composition-make-up--share--data-chart-piestacked)
  - [7. correlation correlation → data-chart (scatter)](#7-correlation-correlation--data-chart-scatter)
  - [8. distribution distribution → data-chart (histogram bar)](#8-distribution-distribution--data-chart-histogram-bar)
  - [9. process steps / pipeline → process-diagram](#9-process-steps--pipeline--process-diagram)
  - [10. funnel funnel → process-diagram (trapezoid)](#10-funnel-funnel--process-diagram-trapezoid)
  - [11. hierarchy conceptual hierarchy → process-diagram (pyramid)](#11-hierarchy-conceptual-hierarchy--process-diagram-pyramid)
  - [12. causal cause / feedback → process-diagram (arrows)](#12-causal-cause--feedback--process-diagram-arrows)
  - [13. positioning two-axis positioning → matrix (belongs to the two-column-compare family)](#13-positioning-two-axis-positioning--matrix-belongs-to-the-two-column-compare-family)
  - [14. tabular multi-attribute structured data → data-chart (table)](#14-tabular-multi-attribute-structured-data--data-chart-table)
  - [15. quotation quote / testimonial → quote](#15-quotation-quote--testimonial--quote)
  - [16. concept definition / single concept → image-led / big-statement](#16-concept-definition--single-concept--image-led--big-statement)
  - [17. divider section transition → section (rendered with big-statement/title)](#17-divider-section-transition--section-rendered-with-big-statementtitle)
  - [18. title / CTA opening and closing action → title / closing-CTA](#18-title--cta-opening-and-closing-action--title--closing-cta)
- [Anti-patterns (revert or revise on sight)](#anti-patterns-revert-or-revise-on-sight)
- [Sources and positioning](#sources-and-positioning)

---

## Three rules that must hold

Before judging any page, these three must hold first; otherwise handle them before choosing an archetype.

1. **One page, one message.** A page supports only one conclusion. If this page's content points are actually talking about two or three things, or need >6 bullets / >1 main figure to finish saying, this is a **paging problem, not an archetype problem**—flag it and ask the user to go back to the previous leg `slide-page-splitter` to split the page; don't force it by shrinking the font or cramming in two figures. Forcing an archetype when information density is over the limit is just endorsing bad paging.

2. **The title carries the conclusion (action title).** The visual comes to support the conclusion in the title. If during judgment you find "there's no visual that can support this sentence," it's usually because the title is still stuck at a topic name (like "Market Overview")—rewrite the title into a conclusion first, then choose the visual.

3. **Brand imagery rule: "prefer structural diagrams over decoration."**
   - Prefer **structural diagrams** (flows, hierarchies, matrices, comparison panels) to express relationships, rather than stuffing in a stock image for ambiance. One right diagram > one pretty but information-free image.
   - **The decision color is the decision color, used at most once per page**: mark it only on "the one decision / the one key number you want the audience to take from this page." An all-orange page = no focus.
   - **The accent color is the accent-verb color, at most 1 per title**: only the most critical verb/word in the title gets the accent color; more dilutes it.
   - Color and font always **follow the brand loaded via `./brand-source.md` (neutral preset if none is set)**; this framework only marks "where to emphasize," it does not hard-code non-brand color codes. Font semantics: titles / big-statement headlines use the **display font**; numbering / issue numbers / codes use the **numbering font**; full-bleed transition backgrounds use the **dark base color**.

---

## Quick lookup table (content relationship → building blocks)

> Usage: read this page's action title + content points → find the most-matching row in the "detection cues" column → take its archetype and primitive recipe directly. A page falls into **one** type only; if it looks like two types at once, go back to rule 1 (it usually needs paging).

| Content relationship | Detection cues (what you see in ▸ Pages) | archetype | building blocks (pptxgenjs primitives) | Brand note |
|---|---|---|---|---|
| **assertion** single claim / high emphasis | Only one impactful conclusion, one key number, one slogan; low density | `big-statement` | large `addText` (display font 48–64) + optional dot-grid `addShape` backing | The word/number to emphasize gets the decision color (this page is that one time) |
| **parallel list** parallel points, no order | 3–6 mutually independent points, no order, no need to compare | `bulleted-list` | `addText` bullets, or a row of `ROUNDED_RECTANGLE` + `addText` cards | The card-title verb can take 1 accent color |
| **comparison** A vs B(/C) trade-off | Option A vs B, before/after, current vs target, us vs competitor | `two-column-compare` | side-by-side `addShape` panels + `addText`, or `addTable` | The recommended column's header gets the brand primary color / decision color (once) |
| **ranking** cross-item ranking / size | "Who's biggest / top three / how big the gap," comparing magnitudes across categories | `data-chart` | `addChart(BAR)` horizontal, **sorted** | The bar to highlight gets the decision color, the rest grayscale |
| **time-series** change over time / trend | Multiple periods, month/quarter/year, "growth / decline / trajectory" | `data-chart` | `addChart(LINE)`; when periods are few (≤4), use `addChart(BAR, col)` | The conclusion line gets the brand primary color, the rest faded |
| **composition** part to whole / make-up | "Share / make-up / structure / X percent," summing to 100% | `data-chart` | `addChart(PIE/DOUGHNUT)` (≤5 slices) or stacked `addChart(BAR)` | The star slice gets the decision color, the rest in the same color ramp; use sparingly |
| **correlation** two variables correlated | "The higher X, the more Y…" "the two are related," scatter | `data-chart` | `addChart(SCATTER)` | The trend band / outlier points can be called out with the decision color |
| **distribution** distribution / spread | "Concentrated in / spread out / which band it falls in," frequency distribution | `data-chart` | `addChart(BAR)` histogram (bins as X axis) | The main peak bin gets the decision color |
| **process** steps / sequence / pipeline | "First… then… finally" "flow / pipeline," ordered | `process-diagram` | a row of `pres.shapes.ROUNDED_RECTANGLE` + `pres.shapes.LINE` / `'rightArrow'` (string) arrows + `addText`, numbered 1→N | The endpoint / key step can take the decision color once |
| **funnel** narrowing stage by stage / funnel | "Conversion / drop-off / filtered down layer by layer," decreasing volume | `process-diagram` | wide-to-narrow stacked `addShape('trapezoid', …)` + `addText` labels | The final conversion layer gets the decision color |
| **hierarchy** conceptual hierarchy | "Pyramid / hierarchy / base→top," top-down subordination | `process-diagram` (pyramid) | `addShape('triangle', …)`, or horizontal bands of `pres.shapes.RECTANGLE` / `addShape('trapezoid', …)` + `addText` | The top / core layer gets the decision color |
| **causal** cause / feedback | "Leads to / because→therefore / virtuous cycle / flywheel" | `process-diagram` | `addShape` nodes + **directional** `addShape('rightArrow', …)` / `pres.shapes.LINE`; feedback uses `addShape('curvedRightArrow', …)` looping arrows | The key factor gets the decision color |
| **positioning** two-axis positioning | "Four quadrants / high-low × high-low / which cell it lands in" | `two-column-compare` (matrix variant) | 2 `LINE` axes + 4 quadrant labels `addText` + data points `OVAL` | Our / target quadrant's point gets the decision color |
| **tabular** multi-attribute structured data | Many rows × many columns, each cell needs an exact value | `data-chart` (table) | `addTable(rows, opts)` | Header filled with brand primary color; recommended row gets a light brand-color fill |
| **quotation** quote / testimonial | Customer testimonial, famous quote, strong endorsement, third-party words | `quote` | large quote marks + quote `addText` + small attribution `addText`; dark-base full-bleed card | A key word in the quote can take 1 accent color |
| **concept** definition / single concept | Explaining one term / one motif / one metaphor | `image-led` or `big-statement` | `addText` definition + structural motif (concentric/layered) `addShape`, or `addImage` illustration | Use a diagram, not a decorative image; the core circle gets the brand color |
| **divider** section transition | Page type = `section`, announcing the next beat | `section` (rendered with `big-statement`/`title`) | full-bleed dark-base `addShape` + display-font `addText` + accent-color label + numbering-font number | Full-bleed dark-base background; number in Mono; label gets 1 accent color |
| **title** opening cover | Page type = `title`, deck name + subtitle + speaker | `title` | wordmark/logo `addImage` + `addText` big title / subtitle | Dark background, light text; logo follows the brand loaded via `./brand-source.md` (neutral preset if none is set) |
| **CTA** closing call to action | Page type = `closing`, "next step / contact / now" | `closing-CTA` | `addText` single big action line + contact info / QR `addImage` | The action button / keyword gets the decision color (the 1 time on this page) |

> Mapping to the upstream ▸ Pages page-type enum (`title / section / content / data / quote / closing`): `title`/`section`/`quote`/`closing` mostly fall straight into the same-named family; `content` further splits into assertion / parallel list / comparison / process / funnel / hierarchy / causal / positioning / concept; `data` further splits into ranking / time-series / composition / correlation / distribution / tabular. **The page type is only a coarse classification; what truly pins the archetype is the content relationship.**

---

## archetype enum and render-primitive mapping

The archetype enum (strictly aligned with SKILL.md; this framework must not add enum values):

```
title / big-statement / bulleted-list / two-column-compare /
data-chart / process-diagram / image-led / quote / closing-CTA
```

Note four "logical archetypes" in the table above are actually **rendered onto an existing archetype**, not new enum values:

- `section` (divider) → rendered with `big-statement` (or the `title` section variant).
- `matrix` (positioning) → belongs to the **two-column-compare family**, rendered with axes + quadrants.
- `pyramid` (hierarchy) → belongs to the **process-diagram family**.
- `concept` → falls to `image-led` or `big-statement` depending on content.

Every visual element must map 1:1 to one of the pptxgenjs primitives below (a 16:9 widescreen canvas ≈ **13.33" × 7.5"**, reserving a 0.5" margin; coordinate unit is inches):

| Visual element | pptxgenjs primitive | Note |
|---|---|---|
| Text block / big text / quote | `addText(text, {x,y,w,h,fontSize,color,bold,align})` | Title, big-statement headline, description, attribution |
| Bullets | `addText([{text, options:{bullet:true, breakLine:true}}, …])` | **Use `bullet:true`, don't type the unicode "•"** (it creates a double bullet) |
| Table | `addTable(rows, opts)` | Comparison table, multi-attribute data; `colW` controls column width |
| Chart | `addChart(pres.charts.<TYPE>, data, opts)` | `BAR / LINE / PIE / DOUGHNUT / SCATTER`; bar uses `barDir:'col'` (vertical) or `'bar'` (horizontal) |
| Shapes (the four common ones) | `addShape(pres.shapes.<SHAPE>, {x,y,w,h,fill,line})` | Only **`RECTANGLE / ROUNDED_RECTANGLE / OVAL / LINE`** have the `pres.shapes.<UPPERCASE>` convenience alias |
| Shapes (advanced: funnel / pyramid / arrows) | `addShape('<name>', {x,y,w,h,fill,line})` (**string literal**) or `addShape(pres.ShapeType.<name>, {…})` | `'trapezoid'` (funnel layer), `'triangle'` (pyramid), `'rightArrow'`/`'chevron'` (process arrows), `'curvedRightArrow'`/`'circularArrow'` (feedback loop)—**these have no `pres.shapes.*` alias** |
| Image / icon | `addImage({path|data, x,y,w,h})` | image-led main image, logo, QR; icons converted from react-icons to PNG (handled by the slide-pptx skill) |

> **⚠ Shape-naming trap (crashes rendering directly).** pptxgenjs's `pres.shapes` only exposes four UPPERCASE convenience aliases (`pres.shapes.RECTANGLE / OVAL / ROUNDED_RECTANGLE / LINE`). `trapezoid`, `triangle`, `rightArrow`, `chevron`, `curvedRightArrow`, `circularArrow` **have no** `pres.shapes.*` alias—writing `pres.shapes.trapezoid` yields `undefined`, and `addShape(undefined, …)` directly throws `Missing/Invalid shape parameter`. There are only two correct forms: pass a **string literal** `addShape('trapezoid', {…})`, or use the raw enum `addShape(pres.ShapeType.trapezoid, {…})`. Wherever the text below mentions `trapezoid/triangle/rightArrow/...`, it always means the "string literal" primitive entry point—please have the downstream slide-pptx skill render it accordingly, and **do not** add the `pres.shapes.` prefix.

> Rendering details (exact x/y/w/h, color-code conversion, QA) are all handled by the downstream **slide-pptx skill**. This leg only provides "relative blocks + primitive type + where to apply brand color," and does not hard-code pixel-level coordinates.

---

## Detailed judgment for each content relationship

Each subsection has a fixed format: **when to use / how to detect from ▸ Pages / building-block recipe / worked example / common mistakes**.

---

### 1. assertion single claim / high emphasis → big-statement

**When to use.** This page has only **one sentence** for the audience to remember: an impactful conclusion, a key number, a positioning slogan. Its power comes from whitespace and type size, not from explaining it across three lines. Zelazny's spirit: when the message is strong enough, the best chart is "no chart."

**How to detect.** The ▸ Pages content points number only 1 (or 1 sentence + 1 supporting line), information density is marked low, the page type is often `section` or `content`, and the title itself is already a complete conclusion sentence.

**Building-block recipe.**
- Star: 1 `addText`, display font 48–64pt, centered or top-left-leaning, occupying the page's main visual.
- Optional backing: `addShape` as a dot-grid (a set of small `OVAL` arranged) or a single brand-color `OVAL`/`RECTANGLE` as a background accent, placed behind the text.
- Layout skeleton: big text centered / top-left, the rest whitespace; dark background with light text is common.

**Worked example.**
Title "We cut quoting time from 3 days to 4 hours" → `addText` "4 hours" 64pt centered ("4 hours" gets the decision color, the only time on this page), a line below `addText` "It used to take 3 days" 24pt gray; background of a faint dot-grid `OVAL` cluster.

**Common mistakes.** Pairing a claim with an unrelated stock image for ambiance (violates "diagram, don't decorate"); or forcibly expanding it into 4 bullets, diluting the impact.

---

### 2. parallel list parallel points → bulleted-list

**When to use.** 3–6 points that are **mutually independent, have no order, and need no comparison**. They are in a "parallel" relationship—if there's order it's a process, if they need comparison it's a comparison.

**How to detect.** ▸ Pages has 3–6 content points, parallel to each other, with no sequence words like "first / next," no quantitative comparison. >6 points → go back to rule 1 and split the page.

**Building-block recipe.**
- Form A (pure bullets): top-left title with `addText` + below it `addText` bullets (`bullet:true, breakLine:true`, left-aligned, **not centered**).
- Form B (carded, looks better with 3–4 points): a row of `ROUNDED_RECTANGLE` (`addShape`) as card bases, each card with `addText` title + description; cards equal-width and evenly divided.
- The right side can leave a column for `addImage` (icon or illustration), with the image as support.

**Worked example.**
Title "Three things improved at once after adoption" → three `ROUNDED_RECTANGLE` cards in a row (speed / cost / satisfaction), each card title verb taking 1 accent color, body text 14–16pt.

**Common mistakes.** Mistaking ordered steps for parallel bullets (the sense of flow is lost—that's a process); centering the bullets (messy reading flow); cramming in more than 6 points.

---

### 3. comparison trade-off → two-column-compare

**When to use.** To view the differences between **two (at most three) objects side by side**: option A vs B, before/after, current vs target, us vs competitor. Minto's trade-off argument most often lands here—only side by side can you see the trade-off; top-to-bottom bullets can't.

**How to detect.** ▸ Pages shows paired objects with paired attributes ("A: fast but expensive / B: slow but cheap"), or before/after, pros/cons comparison.

**Building-block recipe.**
- Form A (panels): title band + below it two left/right groups of `addShape` (`RECTANGLE`/`ROUNDED_RECTANGLE`) panels, each with `addText` title + bullets; column widths symmetric.
- Form B (comparison table): `addTable`, first column is the attribute, the following columns are each object, row-by-row aligned.
- The recommended / winning column: fill the header or panel top with the brand primary color, or apply the decision color to the key-difference cell (once per page).

**Worked example.**
Title "In-house vs outsource: in-house total cost overtakes after three years" → `addTable` three rows (upfront cost / maintenance / flexibility) × two columns (in-house/outsource), with the winning cell of the "three-year total cost" row taking the decision color.

**Common mistakes.** Still using two-column panels for three or more objects (can't fit—switch to `addTable` or split the page); comparison attributes not left/right aligned (the comparison can't be seen); both columns taking the brand color (no focus).

---

### 4. ranking ranking / size → data-chart (bar)

**When to use.** The message is "**who's big, who's small / who's first / how big the gap**"—comparing magnitudes across categories. Corresponds to **item comparison** among Zelazny's five types.

**How to detect.** ▸ Pages's page type is mostly `data`, the content points are a set of categories + their respective values, and the title talks about "most / top N / leading / lagging."

**Building-block recipe.**
- `addChart(pres.charts.BAR, …)`, use horizontal bars (`barDir:'bar'`) when categories are many / labels are long, vertical bars (`barDir:'col'`) when few.
- **Always sort** (largest to smallest or smallest to largest); a ranking chart loses its meaning unsorted.
- The bar to highlight takes the decision color, the rest grayscale, to make the star pop.
- You can add a large-number callout `addText` (60–72pt) stating the key takeaway.

**Worked example.**
Title "East-region revenue equals the other four regions combined" → horizontal `BAR`, five regions sorted largest to smallest, the East bar in the decision color and the rest gray; top-right callout "52%".

**Common mistakes.** Bars not sorted; forcing a ranking into a pie chart (a pie shows composition, not ranking); >8 categories all crammed into one chart (consider Top N + Other, or split the page).

---

### 5. time-series trend → data-chart (line)

**When to use.** The message is "**how it changes over time**"—growth, decline, fluctuation, inflection. Corresponds to **time series** among Zelazny's five types.

**How to detect.** ▸ Pages has a time axis (month / quarter / year / period) + corresponding values, and the title talks about the trajectory.

**Building-block recipe.**
- Many periods (≥5) → `addChart(pres.charts.LINE, …)`, X axis time, Y axis value.
- Very few periods (≤4) → switch to `addChart(pres.charts.BAR, {barDir:'col'})`; a few vertical bars are clearer than a short line.
- The conclusion line takes the brand primary color; with multiple lines, only the star line stands out and the rest are faded gray.
- Inflection points can be annotated with `addText` / a small `OVAL` for the event.

**Worked example.**
Title "After adopting AI, complaints fell for three straight quarters" → `LINE`, three quarters of complaint volume, main line in brand color, with `addText` next to the last point marking "-41%" in the decision color.

**Common mistakes.** Forcing a line chart on two or three periods (looks like there's no data—switch to vertical bars); all lines in vivid colors (can't tell the star); unequal time-axis spacing drawn as if equal.

---

### 6. composition make-up / share → data-chart (pie/stacked)

**When to use.** The message is "**part to whole**"—how much one piece is of the whole, summing to 100%. Corresponds to **component comparison** among Zelazny's five types.

**How to detect.** ▸ Pages shows "share / make-up / structure / X percent," with the items summing to one whole.

**Building-block recipe.**
- Slices **≤5** → `addChart(pres.charts.PIE)` or `DOUGHNUT`; the star slice takes the decision color, the rest in the same color ramp.
- Many slices, or comparing "the composition of multiple wholes" at once → switch to stacked `addChart(pres.charts.BAR)` (stacked bars), which reads better than multiple pies.
- **Use pies sparingly**: a pie is only powerful when "one piece clearly dominates"; when you need to compare each slice precisely, a bar is always more accurate than a pie.

**Worked example.**
Title "Eighty percent of revenue comes from a single product line" → `DOUGHNUT` two slices (main line 80% decision color / rest 20% gray), center `addText` "80%".

**Common mistakes.** Pie with >5 slices (the eye can't compare the angles, see anti-patterns); using a pie for ranking; placing multiple pies side by side to compare composition (switch to stacked bar).

---

### 7. correlation correlation → data-chart (scatter)

**When to use.** The message is "**whether two variables are related**"—as X rises, does Y follow up/down. Corresponds to **correlation** among Zelazny's five types.

**How to detect.** ▸ Pages shows two quantitative dimensions at once, each sample is a point, and the title talks about "the more… the more… / positive correlation / no relationship."

**Building-block recipe.**
- `addChart(pres.charts.SCATTER, …)`, one dimension each for X/Y.
- State the trend direction with one `addText` sentence ("upper-right trend = the more invested, the higher the return"); the trend band or key outlier can be called out with the decision color.
- With many points, you don't need to label every point, only the star.

**Worked example.**
Title "Ad budget and deals closed show strong positive correlation" → `SCATTER` (X=budget, Y=deals), the cluster slanting upper-right, an `addText` sentence for the trend direction, the outlier high-efficiency point in the decision color.

**Common mistakes.** Forcing a scatter on just two or three points (too few samples—switch to a table or just say it); mistaking a time series for a scatter (time is ordered, use a line).

---

### 8. distribution distribution → data-chart (histogram bar)

**When to use.** The message is "**whether the data is concentrated or spread out, and which band it falls in**"—frequency distribution, interval distribution. Corresponds to **frequency distribution** among Zelazny's five types.

**How to detect.** ▸ Pages shows "distribution / falls in / concentrated in / most people in the X interval," and the X axis is intervals (bins) not categories.

**Building-block recipe.**
- `addChart(pres.charts.BAR, {barDir:'col'})` as a histogram: the X axis is continuous intervals, the Y axis is frequency.
- The main-peak interval (the tallest bar) takes the decision color.
- The difference from ranking: a histogram's X axis is **ordered intervals** and is **not re-sorted**; ranking is discrete categories and must be sorted.

**Worked example.**
Title "Seventy percent of customers complete an order within 1 hour" → histogram `BAR` (X=order-completion-time interval, Y=count), the <1hr bar in the decision color.

**Common mistakes.** Arbitrarily reordering the distribution's intervals (destroys the distribution shape); using a pie to express a distribution (the shape can't be seen); bins too fine and noisy (merge intervals).

---

### 9. process steps / pipeline → process-diagram

**When to use.** The message is "**an ordered flow / steps / stages / pipeline**." The order itself is the point—bullets can't express the "flow."

**How to detect.** ▸ Pages shows sequence words (first / then / finally / →), or an explicit sequence of stage names.

**Building-block recipe.**
- A row of `addShape(pres.shapes.ROUNDED_RECTANGLE, …)` nodes, each with `addText`, evenly dividing the page width by the number of steps.
- Connect nodes with `pres.shapes.LINE` or `addShape('rightArrow', …)` / `addShape('chevron', …)` (string literals, no `pres.shapes.` prefix) arrows, all in a consistent direction.
- Number each node 1→N (numbering in `addText` with the numbering font).
- Steps >5 → consider two rows or going back to the previous leg to split the page.

**Worked example.**
Title "Four steps to turn an inquiry into a closed deal" → four `ROUNDED_RECTANGLE` in a row (inquiry→evaluation→proposal→signing), connected with `addShape('rightArrow', …)`, numbered 1–4 in Mono, the endpoint "signing" card in the decision color.

**Common mistakes.** Drawing unordered parallel points as an arrowed flow (implies a non-existent order); inconsistent arrow direction; too many steps crammed together (split the page).

---

### 10. funnel funnel → process-diagram (trapezoid)

**When to use.** The message is "**filtered down layer by layer, narrowing stage by stage**"—conversion funnel, drop-off, recruiting pipeline. It's a special case of process: ordered stages + decreasing volume.

**How to detect.** ▸ Pages shows a decreasing sequence like "conversion / drop-off / impression→click→sign-up→pay," often with each layer's count or conversion rate.

**Building-block recipe.**
- **Stack** `addShape('trapezoid', {…})` from wide to narrow (each layer narrower than the one above; `trapezoid` is a string literal, not `pres.shapes.trapezoid`) to form a funnel shape.
- Each layer `addText` label + value / conversion rate (placed inside the layer or right-aligned).
- The final conversion layer (the narrowest one) takes the decision color—that's the number you want the audience to remember on this page.

**Worked example.**
Title "100 impressions end in 3 closed deals" → four `trapezoid` layers (impressions 100→clicks 25→sign-ups 9→deals 3), narrowing layer by layer, the deals layer in the decision color, with `addText` on the right marking each layer's conversion rate.

**Common mistakes.** Drawing the funnel with equal-width rectangles (no narrowing can be seen = the funnel semantics are lost); too many layers (>5, merge); forcing a non-decreasing flow into a funnel.

---

### 11. hierarchy conceptual hierarchy → process-diagram (pyramid)

**When to use.** The message is "**top-down subordination / base to top**"—pyramid hierarchy, Maslow-style structure, strategic levels.

**How to detect.** ▸ Pages shows "base / core / top / hierarchy / the higher up, the more…," with items in a containment or supporting relationship rather than parallel.

**Building-block recipe.**
- Stacked horizontal bands: one large `addShape('triangle', {…})` cut into a few layers, or several wide-to-narrow `pres.shapes.RECTANGLE` / `addShape('trapezoid', {…})` bands stacked into a pyramid (`triangle`/`trapezoid` are string literals).
- Each layer `addText` layer name + description.
- The core layer (top or bottom, depending on the meaning) takes the decision color.

**Worked example.**
Title "Capability pyramid: data governance before AI" → `triangle` three-band (bottom: data governance / middle: process automation / top: AI decisions), the bottom layer in the brand primary color emphasizing "the prerequisite," the top layer in the decision color.

**Common mistakes.** Mistakenly drawing parallel items as a pyramid (implies a non-existent hierarchy); too many pyramid layers to read; the top/bottom semantic direction reversed (the base should be at the bottom).

---

### 12. causal cause / feedback → process-diagram (arrows)

**When to use.** The message is a "**because→therefore**" causal chain, or a "**virtuous cycle / flywheel**" feedback loop. The point is the **directionality** of the arrows.

**How to detect.** ▸ Pages shows "leads to / drives / because→therefore / the more… the more… cycle / flywheel."

**Building-block recipe.**
- Causal chain (linear): nodes use `pres.shapes.ROUNDED_RECTANGLE` / `pres.shapes.OVAL` + directional `addShape('rightArrow', …)` / `pres.shapes.LINE` to connect, the arrow meaning "leads to."
- Feedback loop (cyclical): nodes wrap into a ring, connected with curved arrows `addShape('curvedRightArrow', …)` / `addShape('circularArrow', …)` (string literals), or several `pres.shapes.LINE` segments joined into a ring, forming a closed loop.
- The key factor (the flywheel's starting point or bottleneck) takes the decision color.

**Worked example.**
Title "Content flywheel: post→traffic→subscribers→more material→post more" → four `OVAL` nodes in a ring, connected with `addShape('curvedRightArrow', …)` into a closed loop, the starting point "post" in the decision color.

**Common mistakes.** Using an undirected `LINE` for causality (no direction can be seen—causality must have arrows); drawing a plain flow (no feedback) as a ring; a ring with too many nodes obscuring the main cause.

---

### 13. positioning two-axis positioning → matrix (belongs to the two-column-compare family)

**When to use.** The message is "**where it lands on two dimensions each**"—a 2×2 matrix, high-low × high-low, four-quadrant positioning.

**How to detect.** ▸ Pages shows two opposing dimensions (high/low × high/low), needing to sort a few objects into four cells.

**Building-block recipe.** (rendering belongs to the two-column-compare family)
- 2 `LINE`s (one horizontal, one vertical) forming a cross axis, with `addText` at the axis ends marking the dimension names (e.g. "cost low↔high," "value low↔high").
- Each of the 4 quadrants `addText` one quadrant label (e.g. "star / question mark / cash cow / dog").
- Place data points with `OVAL` (`addShape`) into the corresponding quadrant, with `addText` beside marking the name.
- Our / target quadrant's point takes the decision color.

**Worked example.**
Title "We sit in the high-value low-cost sweet spot" → cross `LINE` axes, four quadrant labels, each competitor `OVAL` scattered, our point in the upper-right "sweet spot" in the decision color.

**Common mistakes.** Axes not clearly labeled with the meaning of each end (the reader doesn't know the direction); too many points to see the clustering; using a table instead of a matrix (loses the power of the "spatial positioning" message).

---

### 14. tabular multi-attribute structured data → data-chart (table)

**When to use.** The message needs "**many rows × many columns, every cell showing an exact value**"—spec table, feature matrix, price list, scorecard. When people need to look up cell values rather than see a trend, a table is more honest than a chart.

**How to detect.** ▸ Pages is structured row × column data, each cell has a concrete value, and there's no single "trend / share" message that can be abstracted into one chart.

**Building-block recipe.**
- `addTable(rows, opts)`, first row the header, first column the items.
- Header filled with brand primary color, white text; the recommended row or key column gets a light brand-color fill.
- Use `colW` to control column width, `fontSize` 12–16 to keep readability; rows >8, consider splitting the page.

**Worked example.**
Title "Feature comparison of three plans at a glance" → `addTable`, rows = features, columns = plan A/B/C, header filled with brand color, the recommended plan's column with a light brand-color fill, has/has-not shown as a check/cross within `addText`.

**Common mistakes.** Forcibly spreading data that actually has a "single trend / share" message into a table (it should be abstracted into a chart); a table filling the whole page with no whitespace; type too small to read.

> Boundary with comparison: only 2–3 objects and the message is "which to choose (trade-off)" → two-column-compare; multi-attribute, the message is "look up values," and the objects can be many → tabular.

---

### 15. quotation quote / testimonial → quote

**When to use.** This page borrows **a third party's words**—a customer testimonial, a famous quote, an authoritative endorsement. The power comes from "this isn't me saying it, it's them saying it."

**How to detect.** ▸ Pages page type = `quote`, the content is a passage of quote + source.

**Building-block recipe.**
- Large quote marks (enlarge the `addText` " " marks, or one large `addText` quote-mark symbol).
- The quote `addText` (large or italic, centered / left-aligned).
- The attribution `addText` small text toward the bottom (name / title / company).
- A full-bleed dark-base `addShape` card as the background, with lots of whitespace.

**Worked example.**
Title (can be omitted or written as the conclusion "the customer says the key point for us") → full-bleed dark-base card, quote "「導入後我們省下整個週末的對帳時間。」" 42pt, with "整個週末" in the quote taking 1 accent color, attribution below "— 王經理，XX 公司財務長".

**Common mistakes.** The quote too long (>2 sentences, consider excerpting); unclear attribution (a quote without a source has no credibility); pairing the quote with an unrelated stock headshot as decoration.

---

### 16. concept definition / single concept → image-led / big-statement

**When to use.** This page explains **one term, one motif, one metaphor**—making an abstract concept clear through structure.

**How to detect.** ▸ Pages content is "what X is / the core of X is…," developed around a single concept, with no quantification and no parallel list.

**Building-block recipe.**
- Text-leaning, the concept can be defined in one sentence → `big-statement`: large `addText` definition + small-text supplement.
- The concept has a **structural motif** (concentric, layered, hub-and-spoke) → `image-led`: use `addShape` (concentric `OVAL`, layered `RECTANGLE`, central `OVAL` + radiating `LINE`) to draw out the structure, with `addText` labeling each part. The core circle takes the brand color.
- Only use `addImage` when a real-object illustration is truly needed, but still prefer **a diagram over decoration**.

**Worked example.**
Title "The Zynkr Method is three concentric circles" → three concentric `OVAL` (core: decisions / middle ring: process / outer ring: tools), each ring `addText` labeled, the core circle in the decision color.

**Common mistakes.** Using a metaphor stock image (iceberg / lightbulb) in place of a real structural diagram (violates "diagram, don't decorate"); cramming too many sub-points into the concept (it's actually a parallel list, or should be split into pages).

---

### 17. divider section transition → section (rendered with big-statement/title)

**When to use.** A pure **section break**—announcing "we're entering the next beat," giving the audience a point to breathe and reorient.

**How to detect.** ▸ Pages page type = `section`, the content is only a section name / one transition line + possibly a section number.

**Building-block recipe.** (rendered onto `big-statement` or the `title` section variant)
- Full-bleed dark-base background `addShape` (`RECTANGLE` filling the page).
- Section title `addText` in display font, large.
- Section label / category `addText`, the keyword taking 1 accent color.
- Section number `addText` in the numbering font (e.g. "02 / 04").

**Worked example.**
Entering chapter two "Then, let's talk money" → full-bleed dark-base background, big title "然後，談錢" in display font, top-left "02" in numbering font, label "商業模式" with the keyword in the accent color.

**Common mistakes.** Stuffing substantive content into a transition page (a transition should be empty; content is the next page's job); inconsistent style across transition pages (transitions should use one unified template across the deck).

---

### 18. title / CTA opening and closing action → title / closing-CTA

**When to use.** The deck's **cover** (the opening first impression) and the **closing call to action** (and now what, after listening).

**How to detect.** ▸ Pages page type = `title` (deck name + subtitle + speaker / occasion) or `closing` (contact / next step / act now).

**Building-block recipe.**
- `title`: wordmark/logo `addImage` (following the brand loaded via `./brand-source.md` (neutral preset if none is set)) + big title `addText` (display font) + a subtitle line + speaker / occasion toward the bottom; dark background, light text, lots of whitespace.
- `closing-CTA`: a single clear action `addText` large text (**give only one action**) + contact info / QR `addImage`; the action button / keyword takes the decision color (the only 1 time on this page); a dark-background close echoing the cover, forming a "dark—light—dark" sandwich.

**Worked example.**
Cover: logo centered at the top, main title "把報價從 3 天變 4 小時", subtitle "Zynkr × XX 公司 導入分享", speaker toward the bottom.
Closing: big text "下一步：預約 30 分鐘導入評估", QR `addImage` below, "預約" in the decision color.

**Common mistakes.** Stuffing content into the cover (the cover is a first impression, not an outline); a CTA giving three or four actions (the audience does none—give only one); the CTA page using the decision color in several places (rule 3, at most once per page).

---

## Anti-patterns (revert or revise on sight)

These must never appear in ▸ Visuals; if you see one during judgment, revise it or send it back to the previous leg.

| Anti-pattern | Why it's wrong | What to do instead |
|---|---|---|
| **Pie with >5 slices** | The eye can't compare subtle angle differences; beyond 5 slices it becomes a color-block collage | Switch to a sorted horizontal `BAR`; if you really must show composition, Top4 + "Other" |
| **3D chart / 3D pie** | Perspective distorts area and length; the data is lied about visually | Always 2D; a data chart's job is accuracy, not flash |
| **Multiple messages on one page** | Violates rule 1; the audience doesn't know which sentence to remember | Go back to `slide-page-splitter` and split the page, one conclusion per page |
| **Decorative image as filler** | Violates "diagram, don't decorate"; a stock image carries no information, just takes space | Replace with a structural diagram; real whitespace beats fake decoration |
| **Decision-color overuse** | The decision color is the decision color; an all-orange page = no decision focus | At most once per page, marking only that one key number / action |
| **Unsorted bars for ranking** | A ranking chart unsorted = the rank can't be seen | Always sort for ranking; only distribution preserves interval order |
| **Forcing a chart without data** | Drawing a chart with no quantifiable numbers = a hollow chart | Switch to `big-statement` or `bulleted-list`, which is more honest |
| **Bullets >6 points** | Exceeds short-term memory load, and usually means paging wasn't done well | Go back to the previous leg to split the page, or group into cards |
| **Unicode "•" as bullets** | pptxgenjs stacks up a double bullet | Use `addText`'s `bullet:true` |
| **`pres.shapes.trapezoid` / `.triangle` / `.rightArrow` etc.** | These have no `pres.shapes.*` alias, resolve to `undefined`, and `addShape` crashes outright | Switch to a string literal `addShape('trapezoid', …)` or `pres.ShapeType.trapezoid` |

---

## Sources and positioning

- **Gene Zelazny's *Say It With Charts*** — the root of this framework: **define the message first, then choose the form**; the five chart-selection types **component / item / time-series / frequency / correlation** map respectively to this framework's composition / ranking / time-series / distribution / correlation. Zelazny's flow "message → comparison type → chart form" is the source of the data-chart sub-criteria.
- **Barbara Minto's *The Minto Pyramid Principle*** — **the title carries the conclusion (action title)**: each page's title is a conclusion, not a topic, and the visual only comes to support that conclusion. Trade-off arguments map to comparison / positioning.
- **visualframeworks.com** — an **inspiration-style catalog** of 100+ visual frameworks, organized into families like matrix / hierarchy / flow / comparison / system / temporal / structural, but **deliberately gives no "content → which one to use" matching rules**. So this framework's value is precisely supplying that judgment layer; when you need a richer diagram vocabulary (hub-and-spoke, Venn, layer cake, causal loop, etc.), you can draw on it to expand the building-block shape combinations—but the matching still returns to this framework's "content relationship" criterion, not picking the prettiest one from the catalog.

> One-sentence positioning: visualframeworks.com gives you "which diagrams are available to choose," Zelazny gives you "the message decides the form," Minto gives you "the title is the conclusion"; this framework joins the three into one operable judgment line, so slide-visual-selector picks the right archetype and pptxgenjs primitives the moment it sees a page.
