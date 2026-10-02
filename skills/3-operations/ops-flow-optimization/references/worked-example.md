# Worked example — event roster reconciliation

This runs `ops-flow-optimization` end-to-end on one process: reconciling an event's sign-up list, attendance list, and CRM into a clean follow-up list. It is the companion case to training workshop **4.6 流程重構工作坊**. All names and addresses below are illustrative placeholders (`example.com`).

---

## Step 1 — Collect the flow

**Outcome the process must deliver:** a clean follow-up list (who to email) + an exception list (who needs a human to decide), and an updated CRM.

**The process, as done today (as-is):**

1. Export the sign-up list to CSV
2. Export the attendance list to CSV
3. Eyeball / VLOOKUP the two lists to match people by name and email
4. Mark the no-shows
5. Clean up duplicates and missing fields by hand
6. Copy the survivors into a follow-up spreadsheet
7. Re-check the follow-up list against the CRM so you don't email someone twice
8. Hand the list off; someone drafts and sends follow-up emails

**Known pain:** step 3 is slow and error-prone; step 7 always turns up people who were already in the CRM *after* they'd been copied in step 6; duplicates in step 5 get missed.

---

## Step 2 — I → P → O validation

| # | Step | Input | Process | Output | Flag |
|---|---|---|---|---|---|
| 1 | Export sign-ups | event platform | export | sign-up CSV | ok |
| 2 | Export attendance | check-in tool | export | attendance CSV | ok |
| 3 | Match lists | 2 CSVs | join on email; fuzzy on name | matched rows | **fuzzy process** — exact-match and human-judgment match are two different things jammed together |
| 4 | Mark no-shows | matched rows | flag signed-up-but-absent | no-show flags | ok |
| 5 | Clean dup / missing | matched rows | dedup + fix missing fields | cleaned rows | **fuzzy process** — dedup (a rule) and missing-field triage (a judgment) are two steps |
| 6 | Copy to follow-up sheet | cleaned rows | copy/paste | follow-up sheet | **no real output** — copy/paste adds no value; it's a container move |
| 7 | Re-check vs CRM | follow-up sheet + CRM | dedup against CRM | de-duped list | **ambiguous transition + ordering smell** — this is the same "dedup" work as step 5, done late |
| 8 | Hand off + send | de-duped list | draft + send emails | emails sent | ok (but two steps: draft, send) |

**Fixes applied in Step 2:** split step 3 into *exact match* + *fuzzy match (human judgment)*; split step 5 into *dedup (rule)* + *missing-field triage (judgment)*; drop step 6 (pure container move, no value).

---

## Step 3 — Dependency map

- **Hard:** 1 and 2 must precede any matching (can't reconcile lists that don't exist yet). Matching must precede no-show marking.
- **Hard:** the CRM check (old step 7) reads the CRM — but it does **not** depend on anything step 6 produced. It only needs the reconciled people. So its late position is **habitual, not forced.** ← re-sequence candidate.
- **Handoff:** the final draft-and-send changes owner (ops → marketing). Mark it.
- **Trigger:** "event has ended" kicks the flow off.

---

## Step 4 — Friction elimination

| Where | Type | Fix |
|---|---|---|
| Step 6 (copy to follow-up sheet) | **Duplicative / no-value** | Eliminate — the reconciled table *is* the follow-up list; don't copy it into a second sheet |
| Steps 5 & 7 both dedup | **Duplicative** | Merge into one dedup pass (see Step 5 re-sequencing — pull the CRM in early so you dedup against sign-ups, attendance, *and* CRM at once) |
| Step 3 fuzzy match | **Missing** (no exception path) | Add a "needs human review" branch + an exception list, instead of forcing a guess inline |

**Value-flow check:** every surviving step now transforms data, makes a decision, or writes a durable record. The copy/paste step (no transformation, no decision, no durable record) failed the test and was cut.

---

## Step 5 — Re-sequence (with payoff gate + "what breaks?")

| Step moved | From → To | Payoff | "What breaks?" | Verdict |
|---|---|---|---|---|
| Pull in CRM contacts | after copy (step 7) → alongside the two CSVs, before matching | **less rework** — dedup once against all three sources instead of discovering CRM dups after copying | Nothing — the CRM read has no dependency on the follow-up sheet | **keep move** |
| Exact-match gate | — → *before* fuzzy match | **less rework / lower risk** — cheap deterministic join first, so a human only ever reviews the genuinely ambiguous residue | Nothing — exact match needs no judgment | **keep move** |
| Mark no-shows | after matching (step 4) → after the single dedup | **less rework** — flag absentees once, on the deduplicated roster, instead of on rows the dedup will merge | Nothing — the no-show flag reads only the roster | **keep move** |
| Group follow-ups by company | scattered → grouped | none (cosmetic) | Nothing | **reject — no payoff** |

Three accepted moves, all buying *less rework*; one rejected for being cosmetic. This is a healthy log.

---

## Step 6 — The streamlined "ideal flow" spine (Before → After)

**Before:** export → export → match(fuzzy+exact jammed) → mark no-shows → clean(dedup+triage jammed) → **copy to sheet** → re-check vs CRM(late dedup) → hand off+send. *(8 steps, dedup done twice, a no-value copy, fuzzy guessing inline.)*

**After** — as process step cards (`process-step-card.md`). This input was a raw as-is map, so:
*Layer / Reads / Writes / Knowledge: not assigned yet → `ops-transformation`.* Old → new numbers:
1 → 1 · 2 → 2 · the CRM load from 7 → 3 (pulled up front, Step 5) · 3 split → 4 (exact) and 5 (fuzzy) · new → 6 (the human-review branch from the friction log) · 5's dedup + 7's re-check → 7 · 4 → 8 (moved after dedup, Step 5) · 5's triage → 9 · 6 dropped · 8 split → 10 (draft) and 11 (send).

**1 · Export sign-ups** — when the event closes
- Input: the event platform
- Process: export the sign-up list
- Output: sign-up CSV

**2 · Export attendance** — when the event closes
- Input: the check-in tool
- Process: export the attendance list
- Output: attendance CSV

**3 · Load CRM contacts** — when the event closes
- Input: the CRM
- Process: export the contacts the event could match
- Output: CRM contact list

**4 · Exact-match join** — after 1–3
- Input: the three lists (steps 1–3)
- Process: join on email across all three — the cheap deterministic gate first
- Output: matched rows, plus an unmatched residue

**5 · Fuzzy-match the residue** — after 4
- Input: the unmatched residue (step 4)
- Process: suggest a likely match for each row and put it on the exception list for human review — judgment isolated, not inline
- Output: exception list of suggested matches

**6 · Review suggested matches** — when the exception list has entries
- Input: the exception list (step 5)
- Process: confirm or reject each suggested match
- Output: confirmed matches

**7 · Dedup once** — after 4 and 6
- Input: matched rows (step 4) and confirmed matches (step 6)
- Process: remove duplicates across the unified set
- Output: one clean roster

**8 · Mark no-shows** — after 7
- Input: the clean roster
- Process: flag signed up but absent
- Output: the follow-up list

**9 · Triage missing fields** — after 7
- Input: roster rows with missing fields
- Process: decide fix, chase or drop for each
- Output: entries on the exception list

**10 · Draft follow-ups** — after 8 · owner changes here
- Input: the follow-up list
- Process: draft one follow-up email per person
- Output: draft emails

**11 · Send follow-ups** — after 10
- Input: the draft emails
- Process: send them
- Output: emails sent

*One dedup pass. No copy step. Exact-before-fuzzy so humans only touch ambiguity. CRM joined early so no post-hoc surprises.*

**Hand-off:** this clean spine now goes to `ops-transformation` (which step is objective-high-frequency → deterministic? which is subjective → LLM suggests + human gate? assign FE/BE/DB), and then to `ops-workflow-design` to draw it as a Lucid swimlane and run the V1–V14 lint. This skill's job — a streamlined, I→P→O-clean, friction-free, sensibly-ordered spine — is done.
