# Slide Use-Case Playbooks (use-case → default recipe)

> The knowledge core of `zynkr-slide`. Every cell answers one thing: **"What kind of deck is this, and therefore which direction should the three relay stages push?"**
> The content is **generic slide-design principles** — it contains no brand-specific IP (branding is always loaded at runtime by `./brand-source.md`).
> Usage: in Step 1, use the "detection clues" to map the user's request to a use-case; in Step 3, copy that cell's "mapped occasion / page budget / default density / per-stage emphasis" into `SLIDE_PACKET ▸ Brief`.

---

## How to use this playbook

- **One deck, one use-case**. Grab the primary one; for hybrids (e.g. "report quarterly numbers to a client"), pick the main use-case and borrow one or two directives from the secondary one.
- **The occasion (occasion enum) is still the existing four-way choice in storyline** (`external pitch / internal update / training / fundraise`). The use-case is a finer-grained "playbook key"; under each use-case we write the **suggested mapping** to which occasion — so stage 1 still receives an enum it recognizes, while the directives add flavor. The user can change the occasion during intake.
- **The per-stage emphasis directives are concrete instructions to be copied verbatim into ▸ Brief**, not background notes. You may tweak them slightly to fit the material when copying, but keep them "executable."
- **The page budget is a target, not a hard cap**; take the upper end when there's lots of material, the lower end when there's little. How many pages to actually split into is always stage 2's call.
- **No matching use-case found** → fall back to the generic skeleton of the mapped occasion (equivalent to using the three stages' original behavior), and write "default per occasion, no extra flavor" for the per-stage emphasis in ▸ Brief.

---

## Quick-reference table

| use-case | mapped occasion | page budget | default density | one-line positioning |
|---|---|---|---|---|
| `deep-dive` | internal update (default) / training / external pitch | 15–25 | medium→high | dissect one thing to the bone; the evidence chain skips no link |
| `business-review` | internal update | 12–18 | medium (KPI pages can go high) | report results against targets, close on a decision request |
| `data-presentation` | internal update (default) / external pitch | 10–18 | medium (mostly single-chart pages) | one chart, one conclusion — conclusion first, then chart |
| `all-hands` | internal update | 8–14 | low | broad audience, inspirational, a repeatable through-line |
| `planning` | internal update | 10–16 | low→medium | vision → current state → goals → roadmap → commitment |
| `pitch` (existing) | external pitch | 10–16 | medium | amplify the pain, the solution, the evidence, a single CTA |
| `update` (existing) | internal update | 8–14 | medium | TL;DR up front, progress and decisions |
| `teach` (existing) | training | 12–20 | medium | framework first then cases, reproducible steps |
| `fundraise` (existing) | fundraise | 12–18 | medium | problem → market → solution → evidence → team → the ask |

---

## The four new playbooks (v1 focus)

### `deep-dive` — deep analysis / technical deep-dive / in-depth topic study

- **Detection clues**: "deep dive", "深入", "深度剖析", "技術細節", "完整分析", "拆解原理", "root cause", "為什麼會這樣", "把這件事講透"; the audience is mostly insiders / technical / core decision-makers; they want **rigor and insight**, not an overview.
- **Mapped occasion**: defaults to `internal update`; if the main goal is "teach the audience an analytical framework" → `training`; if the deep-dive is used to persuade externally → `external pitch`. Let the user decide during intake.
- **Narrative skeleton bias**: problem/phenomenon → hypothesis → **unpack the evidence chain layer by layer** → counterexamples/boundary conditions → conclusion and so-what → action/open questions. One extra layer of "evidence → inference" depth beyond a normal deck.
- **Page budget**: 15–25 (long is allowed, dense is allowed). **Default density**: medium→high.
- **Per-stage emphasis**:
  - **Storyline (stage 1)**: weight the "non-sequitur" and "evidence gap" checks in the logic review more heavily; every beat must force out a single **so-what** ("so what does this layer of analysis mean?"); the evidence chain must not skip levels — flag any missing link as to-be-filled.
  - **Pagination (stage 2)**: the density ceiling may be relaxed to "high"; prioritize `data` pages; a single beat may be split into an "overview page + layer-by-layer expansion pages"; carry a long chain across multiple pages rather than cramming a single page.
  - **Visuals (stage 3)**: prefer `data-chart` / `two-column-compare` (including before/after comparisons) / `process-diagram`; visuals must **reveal causality and impact** (not decorate); still one main visual per page; use process-diagram to mark 1→N for a complex chain. (Use only layout names within the nine-archetype enum; before/after is a content signal that maps to `two-column-compare`.)

### `business-review` — business review / performance retrospective / QBR / monthly or quarterly meeting

- **Detection clues**: "business review", "QBR", "季度回顧", "經營檢討", "業績回顧", "月會/季會", "vs target", "達標/未達標", "KPI 回顧", "複盤"; the audience is managers/teams.
- **Mapped occasion**: `internal update` (but weighting "against targets" and "decision request" more heavily than a normal update).
- **Narrative skeleton bias**: TL;DR conclusion → overall vs target → line-item breakdown (which hit/missed target, and by how much) → highlights → risks/laggards and countermeasures → **decision request** → next steps.
- **Page budget**: 12–18. **Default density**: medium (KPI/dashboard pages may go high).
- **Per-stage emphasis**:
  - **Storyline (stage 1)**: the TL;DR must be in the very first beat; every line item must be compared against its target (hit/missed/by how much); the close must be an explicit **decision request**, not "thanks for listening."
  - **Pagination (stage 2)**: prioritize `data` pages to carry KPI vs target; give each major laggard its own page with cause and countermeasure; split highlights and risks onto separate pages, never mixed on one page.
  - **Visuals (stage 3)**: `data-chart` (bar for attainment rate, line for trend) + big-number callouts; `two-column-compare` for "target vs actual"; hit/miss is only a semantic cue — color values and restraint on the decision color are decided by the brand.

### `data-presentation` — data presentation / research results / dashboard walkthrough

- **Detection clues**: "數據簡報", "data presentation", "research results", "報數字", "把這份數據講清楚", "圖表", "dashboard 導讀", "analytics"; the subject is a batch of numbers/charts that need to be **turned into conclusions**.
- **Mapped occasion**: defaults to `internal update`; reporting data to clients/investors → `external pitch`.
- **Narrative skeleton bias**: a single overall takeaway → background/data source and definitions → **one chart, one conclusion, unpacked one at a time** (one so-what per chart) → composite pattern → conclusion/recommendation.
- **Page budget**: 10–18. **Default density**: medium (mostly single-chart pages).
- **Per-stage emphasis**:
  - **Storyline (stage 1)**: each beat = one "data conclusion," not "one chart"; **conclusion before chart** (Zelazny's principle); avoid "data dumping" (a page crammed with charts but no claim).
  - **Pagination (stage 2)**: mark most pages as `data`; one chart, one conclusion per page; write the title as a **data-conclusion sentence** ("Q3 new-customer growth 38%") rather than "XX trend chart."
  - **Visuals (stage 3)**: `data-chart` is primary, strictly following the chart sub-criteria (bar/line/pie/table); pair each chart with a big-number callout that states the takeaway; **reject decorative charts that carry no information**; for pure precise values use a table, not a chart.

### `all-hands` / `planning` — all-hands / company-wide meeting; quarterly planning / vision communication

> The two scenarios share a low-density, broad-audience orientation, but the beats differ; during intake, distinguish whether it's an "inspirational all-hands" or a "roadmap-style planning."

- **Detection clues**:
  - all-hands: "all-hands", "全員", "全體大會", "town hall", "kickoff", "願景溝通", "對全公司講".
  - planning: "planning", "規劃", "roadmap", "藍圖", "季度規劃", "OKR 溝通", "里程碑".
  - Common: the audience is **broad, cross-functional, non-expert**.
- **Mapped occasion**: `internal update`.
- **Narrative skeleton bias**:
  - all-hands: where we are (status/context) → one through-line (inspirational) → three big things → the why + progress for each → **what it means for everyone** → call to action. Pronounced emotional/logical arc, few details.
  - planning: a one-line vision → current state → goals/OKRs → **roadmap (milestone timeline)** → resources/ownership → risks → commitment.
- **Page budget**: all-hands 8–14; planning 10–16. **Default density**: all-hands low; planning low→medium (roadmap page leans medium).
- **Per-stage emphasis**:
  - **Storyline (stage 1)**: the through-line must be **repeatable by the whole room**, with a pronounced emotional/logical arc; use little jargon; every section ties back to "what it means for you / for us." The planning variant follows "vision → current state → goals → roadmap → commitment."
  - **Pagination (stage 2)**: hold density at "low"; use plenty of `section` pages as signposts; let `big-statement` carry each major point; give the planning roadmap its own page (timeline); avoid dense bullet lists.
  - **Visuals (stage 3)**: `big-statement` / `image-led` are primary (`section` is a page type, not a layout — section pages are carried by `big-statement` or a title section-divider variant); planning uses `process-diagram` to draw the milestone timeline; few tables, few dense charts; color can be bolder (still respecting "the decision color at most once per page").

---

## The four existing occasions (the playbook only adds page count / density / light flavor; narrative skeletons reuse the storyline built-in table)

> The narrative-arc templates for these four are already written in `slide-storyline-designer`'s Step 3 table; the playbook **does not rewrite** them — it only adds the page budget, default density, and light per-stage emphasis that zynkr-slide needs.

### `pitch` — external pitch
- Mapped occasion `external pitch` | pages 10–16 | density medium.
- Per stage: **stage 1** amplify the pain, close on a single CTA; **stage 2** give evidence/cases their own pages; **stage 3** `image-led` + `big-statement` to carry emotion, `data-chart` to carry evidence, a strong `closing-CTA` at the end.

### `update` — internal update
- Mapped occasion `internal update` | pages 8–14 | density medium.
- Per stage: **stage 1** lead with the TL;DR; **stage 2** split progress vs target, risks, and decision requests onto separate pages; **stage 3** keep it lean, use `data-chart` to mark progress, minimal decoration.

### `teach` — training
- Mapped occasion `training` | pages 12–20 | density medium.
- Per stage: **stage 1** framework first then cases, emphasize reproducible steps; **stage 2** one page per step / common mistake; **stage 3** `process-diagram` to walk the flow, worked examples in `two-column-compare` (right/wrong).

### `fundraise` — fundraise
- Mapped occasion `fundraise` | pages 12–18 | density medium.
- Per stage: **stage 1** walk the full 8-part arc (problem → market → solution → evidence → team → the ask), none may be missing; **stage 2** give traction/data their own pages; **stage 3** `data-chart` to carry traction, `big-statement` to carry the vision, the closing `closing-CTA` = an explicit ask (amount and use of funds).

---

## Universal rules (true for every use-case, mapped from the three stages' built-in principles)

- **Set the message first, then choose the form** (Zelazny): for the same data, a different conclusion calls for a different visual. The title always carries its own conclusion.
- **One point per page / one main visual per page**: density overflow is a pagination problem — return it to stage 2; don't force-fit by shrinking text.
- **Restraint with color**: the decision color at most once per page; the actual color values are always decided by the brand (`./brand-source.md`) — the playbook never hard-codes colors.
- **No fabricating material**: missing data/cases are marked "to-be-filled" and handed back to the user; no stage invents anything on its own.
