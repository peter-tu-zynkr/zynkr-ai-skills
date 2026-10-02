---
name: ops-flow-optimization
sheetId: "3.14"
description: "Streamline and re-sequence a business process into a clean 'ideal flow' before it gets built or automated. Canonical slot (course Ch5 §5.5.2): run it right AFTER the as-is→to-be redesign re-chains the flow — polishing the redesigned ordering — though it also works standalone on any messy as-is map. Runs a lean optimization pass: validate Input→Process→Output on every step, map dependencies, eliminate friction (duplicative / looping / missing steps), then apply disciplined re-sequencing only where it buys less rework, lower risk, or higher throughput. Use it whenever a process feels bloated, out of order, or 不順暢 — when someone says '幫我把流程理順', '這流程可以更精簡嗎', 'streamline this workflow', 'is my process in the right order', or right after FE/BE/DB redesign (ops-transformation Stage 3) and before drawing on Lucid. Enforces 'eliminate before you automate.' Does NOT do automation-feasibility scoring or FE/BE/DB layer assignment — hand off to ops-transformation for that."
category: operations
project: ops-flow-optimization
platform: claude
status: Done
visibility: public
author: Peter Tu
input: "A process step list — ideally the redesigned to-be flow (ops-transformation Stage 3 blueprint), or a SIPOC / as-is map — plus the outcome the process must deliver"
process: "I→P→O validation → dependency mapping → friction elimination → disciplined re-sequencing (with a payoff test) → streamlined to-be spine + decision log"
output: "A streamlined 'ideal flow' spine (Before/After), a dependency map, a friction log, and a re-sequence decision log — ready for Lucid or the build"
synergy:
  - "ops-transformation"
  - "ops-workflow-design"
  - "sales-discovery"
house-style: bound

---

# Ops Flow Optimization

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill ops-flow-optimization
```

Take a messy, human-grown business process and turn it into a clean **"ideal flow"** — I→P→O-valid on every step, dependency-ordered, and stripped of friction — *before* anyone builds or automates it. This is the lean-optimization pass that most teams skip: they jump straight from "here's our design" to "let's automate it," and end up **automating waste**. This skill makes you earn a streamlined flow first. Its canonical slot (course Ch5 §5.5.2, "Redesign the Flow") is right **after** the as-is→to-be transformation pass has re-chained the steps (`ops-transformation` Stage 3) and right before drawing on Lucid (`ops-workflow-design`) or building — though it also runs standalone on a raw SIPOC / as-is map whenever a flow feels tangled. It is deliberately *conservative about re-ordering* — it changes sequence only when the change pays for itself.

The one law it enforces: **eliminate before you automate. Anchor the spine to I→P→O and dependencies; only then, rarely, re-sequence — and only for less rework, lower risk, or higher throughput.**

---

## Step 1 — Collect the flow

Ask the user for (accept whatever they have; don't block on all three):

1. **The process, as steps** — a list of the steps in their current order. The redesigned to-be flow from `ops-transformation` Stage 3 is the ideal input (the canonical Ch5 §5.5.2 slot); a SIPOC map from Stage 1 or a rough bullet list is fine too.
2. **The outcome** — what the process must reliably produce when it's done (`乾淨的追蹤名單`, `approved + notified`, `月結報表`). This is the anchor everything gets tested against.
3. **Known pain** — anything that already feels slow, repeated, error-prone, or out of order.

Store as `FLOW`. If steps are vague, do **not** silently invent them — ask one clarifying question, then proceed. Restate the flow back in your own words so the user can correct it before you start cutting.

> If the process isn't understood well enough to list its steps, this is the wrong skill — send the user to `sales-discovery` (pain-point discovery) or `ops-transformation` Stage 1 (SIPOC) first.

---

## Step 2 — Validate Input → Process → Output on every step

This is the anchor. Walk each step and confirm it has all three:

- **Input** — what must exist for this step to start (a file, a record, a prior output, an approval).
- **Process** — the single verb-and-object of work it performs (`Validate request`, `Match on email`, `Draft follow-up`).
- **Output** — the concrete artifact or state change it leaves behind.

For each step, flag:
- **Ambiguous transition** — the output of step N doesn't cleanly become the input of step N+1 (something happens "somehow" in between). Name the missing piece.
- **No real output** — a "step" that produces nothing durable is usually a note, not a step. Merge or drop it.
- **Fuzzy process** — a step doing two things at once. Split it so each has one I→P→O.

**Deliverable: a Before/After I→P→O table.** One row per step: `# · Step · Input · Process · Output · flag`. Number the steps (keep the numbers the input already has — `ops-transformation` assigns them at Stage 1 and numbers sub-tasks beneath them). Carry every column the input has, unchanged: on a Stage 3 blueprint that is **layer · Reads · Writes** (plus Knowledge and Tool on the cards); on a Stage 1 SIPOC (the optional Stage 1.5 pass) it is **Supplier · Customer · Systems today**, which Stage 2's data-digitization check needs. You do not assign layers, but you never drop what you were given. Do not proceed to ordering until every kept step is I→P→O-clean — an out-of-order flow can't be diagnosed on top of undefined steps.

---

## Step 3 — Map dependencies

Now find what actually constrains the order (as opposed to how it's habitually done):

- **Hard dependency** — step B genuinely cannot start until step A's output exists (you can't reconcile a roster before both lists are exported). These fix the spine.
- **Shared data / handoff** — two steps read or write the same record, or one hands work to a different owner. Mark the handoff explicitly. When the steps carry Reads / Writes, read them straight off the cards: a step that reads a store another step writes depends on that step.
- **Trigger** — what kicks the whole flow off, and whether any step waits on an external event.

Draw the dependencies as arrows (or swimlanes if ownership changes hands). The key output is the distinction between **what must be ordered this way (hard dependency)** and **what is merely ordered this way out of habit** — only the latter is a candidate for re-sequencing in Step 5.

**Deliverable: a dependency map** (arrows / swimlanes) separating hard dependencies from habitual ones.

---

## Step 4 — Eliminate friction

Run the lean pass. For every step and transition, test against these three friction types (this is ECRS applied to the flow — Eliminate · Combine · Rearrange · Simplify):

| Friction | What it looks like | Fix |
|---|---|---|
| **Duplicative** | Repeated inputs, double validations, the same data re-entered | Merge, or do it **once** and reuse the output |
| **Unnecessary loop** | A path that returns to an earlier step for no explicit reason | Streamline the sequence; if the loop is a real retry, label it as one (Step 5) |
| **Missing** | A break that causes rework or data loss downstream (a gap where context silently drops) | Add a connector / context node |

Governing test: **the flow should add value as it moves through.** A step that doesn't move the work closer to the outcome — no transformation, no decision, no durable record — is friction. Cut it.

**Deliverable: a friction log** — each item as `where · type (duplicative / loop / missing) · fix`.

---

## Step 5 — Re-sequence — but only with a payoff

Re-ordering is the **last and rarest** move, and the most abused. Most of the "ideal flow" is already fixed by Steps 2–4. Touch the order only where a clear payoff exists. Apply these heuristics (full detail in `references/sequencing-heuristics.md`):

- **Anchor first, optimize second.** Lock the spine as I→P→O per node, then respect dependencies. Only *after* that do you consider a re-order.
- **Cheap checks upstream, expensive work downstream.** Move low-cost gates early (format, required-field, permission, schema) so you never spend heavy work — human review, LLM reasoning, multi-system writes — on input that a 5-cent check would have rejected.
- **Batch high-traffic inputs before scarce decisions; serialize where decisions branch.** If 100 requests feed 1 approver, aggregate before approval. But don't batch *past* the point where an approval outcome changes the downstream path.
- **Keep state writes consistent with the sequence.** Don't create ghost states (e.g. notifying before the durable record exists). A durable write should land at the point the outcome becomes real.
- **No backward loops unless they're explicit retry / escalation paths**, labeled with their condition. An unlabeled loop is almost always hiding missing validation or unclear ownership — fix that instead of drawing the loop.

**The payoff gate — every re-order must buy one of three things:**

> **(1) less rework · (2) lower risk · (3) higher throughput.** If a proposed re-order buys none of these, keep the original dependency-driven order. **Do not reorder to make the diagram prettier.**

**The "what breaks if this step moves?" test.** Before committing any re-order, ask it — and when the steps carry Reads / Writes, check them first: moving a step ahead of the step that writes a store it reads is a break. If moving the step would change meaning, violate a contract, or create an inconsistent state, it is **not** a sequencing tweak — it's a deeper redesign problem (missing input, unclear ownership, undefined output). Send it back to Step 2, don't force the move.

**Deliverable: a re-sequence decision log** — each proposed move as `step moved · from→to · payoff (rework / risk / throughput) · "what breaks?" answer · kept or rejected`. A log with **zero** accepted re-orders is a valid, common, and often correct result.

---

## Step 6 — Emit the streamlined spine + hand off

Compile the deliverable:

1. **The "ideal flow" spine** — the final ordered steps as **process step cards** (`references/process-step-card.md`), Before → After. Each card: `number · name — trigger · layer`, then Input · Process · Output, then every other line the input card carried — Reads, Writes, Knowledge, Tool — unchanged (`none` stays `none`).
   - If the input had no layers at all (a raw as-is map), write `Layer / Reads / Writes / Knowledge: not assigned yet → ops-transformation` once above the spine. If the input was a numbered SIPOC (`ops-transformation`'s optional Stage 1.5), return the spine in that same form — the numbered SIPOC table with Supplier · Customer · Systems today carried through — because that table is the as-is card (`process-step-card.md` §5) and Stage 2 reads it.
   - A step **this pass added** (a split, a missing connector) inside a carded flow gets its Input · Process · Output and the line `Layer / Reads / Writes / Knowledge: to assign → ops-transformation` on its own card.
   - When the cards name two or more stores or knowledge sources, end the spine with the **store directory** (card §4).
   - Renumber after cuts, splits and merges: keep the parent number and renumber only the children under it (`process-step-card.md` §1), and give the `old → new` map in one line. Your numbers are the ones `ops-transformation`'s final blueprint and the Lucid chart use from here on.
2. **Dependency map** (Step 3).
3. **Friction log** — what was eliminated and why (Step 4).
4. **Re-sequence decision log** (Step 5).

Then point at the next stage explicitly — this skill deliberately stops before diagramming and building:

```
Next steps:
1. If you ran this on a raw as-is map: assess automation feasibility + assign FE/BE/DB layers → ops-transformation (Stage 2–3), then re-run this pass on the redesigned flow (course Ch5 §5.5.2)
2. Draw the streamlined spine as a Lucid swimlane (shape = semantics, color = ownership, V1–V14 lint) → ops-workflow-design
3. Iterate — re-run this pass after the process changes
```

---

## Rules

- **Anchor before you optimize.** I→P→O and hard dependencies come first; friction elimination second; re-sequencing last and rarest. Never re-order on top of undefined steps.
- **Eliminate before you automate.** If a step is waste, cutting it beats automating it. This skill's job is to shrink the flow so the *next* stage automates only what's worth automating.
- **A re-order needs a payoff.** Less rework, lower risk, or higher throughput — or it doesn't happen. "Cleaner-looking" is not a payoff.
- **Run the "what breaks if this moves?" test on every proposed re-order.** A move that changes meaning or breaks a contract is a redesign problem, not a sequencing one.
- **Don't hide logic in loops.** Every backward arrow is an explicit, labeled retry / escalation with a condition, or it's a bug to fix.
- **Stay in lane.** Do not score automation ROI, assign FE/BE/DB, or pick tools — that's `ops-transformation`. Do not draw the final diagram or run lint — that's `ops-workflow-design`.
- **Carry, don't drop.** Not assigning FE/BE/DB is not the same as discarding it: every line the input carries — on to-be cards layer, Reads, Writes, Knowledge, Tool; on an as-is SIPOC Supplier, Customer, Systems today — stays on its step through to the final spine. A step you add is marked `to assign → ops-transformation`, never given a guessed layer.

## Reference files

- `references/sequencing-heuristics.md` — the full re-sequencing playbook: every heuristic, the payoff gate, the "what breaks?" test, worked micro-cases.
- `references/worked-example.md` — the method run end-to-end on an event-roster reconciliation flow (the companion case to training workshop 4.6 流程重構工作坊).
- `references/process-step-card.md` — the shared process step card (number · Input · Process · Output · layer · Reads · Writes · Knowledge) the final spine is written in; shared with `ops-transformation` and `ops-workflow-design`.

## Limitations

- **Not discovery.** It optimizes a process you can already list. If the steps aren't understood, run `sales-discovery` or `ops-transformation` Stage 1 (SIPOC) first.
- **Not architecture.** It stops at a clean, ordered spine. Layer assignment, automation feasibility, and MVP-stack choices belong to `ops-transformation`; the Lucid diagram + V1–V14 lint belong to `ops-workflow-design`.
- **Conservative by design.** It will often accept *zero* re-orders. That's the intended behavior — most value comes from I→P→O cleanup and friction removal, not from moving boxes around.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
