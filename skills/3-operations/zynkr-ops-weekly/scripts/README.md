# scripts

Deterministic steps live here so the model never re-derives them. Each reads JSON or markdown
on stdin and writes JSON on stdout, so they compose in a pipe and can be tested without any
network call.

| Script | In → Out |
|---|---|
| `parse_routing.py` | Doc markdown → `{heading → owner email}` read from the person chips |
| `parse_reports.py` | normalised Chat messages + config → one record per reporter, plus who is missing |
| `carryover.py` | Doc markdown → `↻N週` per item, and the agenda candidates above threshold |
| `render_block.py` | reports + routing (+ carry-over) → the `〔自動彙整〕` block per heading |
| `tidy_blocks.py` | Doc markdown → per group the block to keep, the blocks to archive, the open items to carry. With `--closed`: Drive plain-text export + structure → the `Done`/`Drop` bullets to delete, as index ranges |
| `scaffold.gs` | **Apps Script**, not Python — duplicates next week's skeleton. See `../references/scaffold.md` |
| `recap.py` | The Monday recap (`SKB-044`): reads last week's blocks from the Ledger, runs zynkr-gm's `derive_state.py`, and renders the mail; the run writes only the TL;DR, and lines citing no item number are dropped. `--selftest`, `--mutate` |
| `ledger.py` | The Weekly Ledger (`SKB-044`). Prints the exact MCP calls for each step of the Friday `snapshot` and checks every saved result before the next. Unlike the others it works from files in a run folder, not stdin. See `../references/ledger.md` |
| `proposals.py` | The Friday close-out (`SKB-044` Phase 3): `propose` reads the tracker and the week's Ledger evidence, `check` refuses any change outside `../references/proposal-rules.md` and renders the 【待核准】 mail, `sent` guards the one send (`--send-failed` frees it after an error) and checks the mail in Sent is word for word the checked one; `apply-*` reads the owner's reply in that thread (`全部核准` · `核准 1 3` · `退回 2`; strict on purpose: an approving reply that asks or says more than thanks is unreadable), waits while a draft is open, asks once to restate a reply it cannot read (`apply-sent` remembers a request that went out), writes the decision to the `Proposals` block, reads that block and the thread again, confirms in the thread, and only then writes the `Updates` block that marks the week applied; shadow mode writes nothing to the tracker. Works from a run folder, like `ledger.py`, which it imports. `--selftest`, `--mutate` |
| `tracker_guard.py` | The runner's PreToolUse hook (`SKB-044` AC-3.5), not run by the model: refuses any call aimed at the Main Tracker unless it only reads or the beat is `apply` writing values, and (`SKB-070`) any call that reaches into the owner's weekly-insights folder, reads included: one that names it, searches from or above it, or globs below an ancestor of it (see `../references/scheduling.md`). Exit 2 refuses; an error inside it refuses every call but a read. Installed next to `run_ops_weekly.sh`. `--selftest` (44 cases, each run the way Claude Code runs the hook), `--mutate` |
| `beats.py` | The runner's beat selector (`SKB-070`), not run by the model: `select` answers `mode|week|why` for this tick (the beat table, windows, prerequisites, the Thursday wait for the owner's weekly insights, and the `notice` for missed beats); `insights` says whether that week's `meeting.json` is ready. Installed next to `run_ops_weekly.sh`. `--selftest`, `--mutate` |

## The usual pipeline (`rollup`)

```bash
# 1. routing — MUST come from get_doc_as_markdown; get_doc_content strips person chips
parse_routing.py --section "Aug 27, 2026" --input doc.md            > routing.json

# 2. reports — messages normalised from get_messages(space_id, createTime window)
parse_reports.py --config ~/.config/zynkr/ops-weekly.json < msgs.json > reports.json

# 3. carry-over — how long each item has been open
carryover.py --input doc.md --threshold 3                            > carry.json

# 4. the blocks to write
render_block.py --reports reports.json --routing routing.json \
                --carryover carry.json --week "WB 8/24" --stamp "08-24 12:00" > blocks.json
```

Then write `blocks.json` into the Doc with `batch_update_doc`, `tab_id` set on **every**
operation, inserting **bottom-up** by index. `references/doc-write-rules.md` explains why both
of those matter.

## The Friday pipeline (`tidy`)

```bash
# 1. blocks — keep the newest per group, archive the rest, carry what is still open
tidy_blocks.py --input doc.md                                        > tidy.json

# 2. closed human bullets — AFTER the block writes. e = get_drive_file_content (the only read
#    that renders P0/Done/Drop chips), s = inspect_doc_structure(tab_id, detailed=true),
#    doc.md = get_doc_as_markdown (headings + person names). Every run is a gate.
tidy_blocks.py --closed --export e1 --structure s1 --markdown doc.md \
               --section "Oct 8, 2026"                               > plan.json
tidy_blocks.py --closed --export e2 --structure s2 --markdown doc.md \
               --section "Oct 8, 2026" --expect plan.json > recheck.json   # NOT > plan.json
#    … delete plan.json's ranges, in the order listed (highest first) …
tidy_blocks.py --closed --export e3 --section "Oct 8, 2026" --postcheck plan.json
```

All inputs may be saved MCP tool results (`{"result": "..."}`) as-is.

## The Friday-evening pipeline (`snapshot`)

```bash
ledger.py snapshot start --week 2026-W40      # → dir + 5 calls (tracker/Ledger info, Ledger headers, the Weeks row)
ledger.py snapshot pages   --dir "$D"         # → "already": true, or the tracker reads (50 rows a page)
ledger.py snapshot plan    --dir "$D"         # → ops (the block write + clear), readback, recheck
ledger.py snapshot check   --dir "$D"         # → the Weeks commit call, only when every cell matches
ledger.py snapshot confirm --dir "$D"         # → delivered=55-items;Snapshot!A2:P56;Weeks!A2
```

Each step prints calls as `{"tool", "args", "save"}`; the model makes each call with `args`
exactly and saves the whole result to `save`.

`ledger.py diff --a A.json --b B.json [--updates U.json]` compares two weeks' blocks (JSON lists of
16-column rows) and lists every changed cell, plus items added and removed. A change is `logged`
only when an `Updates` row with the same cycle, `#`, column and new value falls inside the window
between the two snapshots; everything else is a manual edit. Monday's recap reads this. `ledger.py --selftest` runs the whole pipeline
against fake MCP results; `ledger.py --mutate` checks that fourteen deliberate breakages each turn
the selftest red (`proposals.py --mutate` sixty, `recap.py --mutate` twelve, `tracker_guard.py --mutate` twenty-three,
`beats.py --mutate` twenty-five).

## Exit codes

`0` success · `2` bad config or a section that does not exist · `3` no owner chips found (the
usual cause is having read the Doc as plain text instead of markdown).

`ledger.py` has its own: `2` config or arguments · `3` input refused (missing, truncated, wrong
file or range, a row count that does not match) · `4` structure changed · `5` out of room in the
Ledger · `6` check failed, do not commit · `7` the commit did not read back.

Diagnostics that must reach the run report are written to **stderr** and also carried in the
JSON: `unmapped_senders`, `unrouted_headings`, `reporters_without_heading`, `duplicates`. None
of these are fatal, and none should be swallowed — a report that vanished silently looks
exactly like a person who never reported.

## Testing

Pure functions, no network. Feed them hand-crafted markdown, or a real Doc export.

`python3 beats.py --selftest` walks the beat table through a whole ISO week (2026-W42): every beat in
its window and order, the prerequisite hold, the `apply` wait, the Thursday wait for the owner's
weekly insights and every notice rule. When `beats.py` replaced the runner's inline selector
(SKB-070) the two were run side by side over every `:05`/`:35` tick of a week across 22 stamp
states: 7,056 answers, and the only 306 that differ are the `agenda` move from Wednesday evening to
Thursday morning.

`python3 test_tidy_blocks.py --mutate` runs the `tidy` suite and then breaks real lines of
`tidy_blocks.py` one at a time; every mutation must turn the suite red. It runs an UNmutated
control copy first and refuses to report anything if that fails — until 2026-09-30 the harness
itself produced uncompilable mutants, so every mutation "passed" and proved nothing.

`carryover.py` is the one worth exercising on real data, because it is the only script whose
output is a *judgement* (what lands on the agenda) rather than a transformation, and both of
its failure modes are invisible on small fixtures:

- **Template rows.** On the real Doc, 16 of 76 "items" were skeleton labels (`Funnel`, `TOF`,
  `Website`, `CTR`) that repeat every week by design. Unfiltered they took the top of the
  agenda. They are excluded when the corpus is large enough for the ratio to mean something
  **and** the line carries no status — both conditions, because in a short document
  "appears in every section" is exactly what a genuinely stuck item looks like.
- **Drifting matches.** Loose similarity chains: each week it matches a slightly different
  item and the streak walks across unrelated work, which produced a confident `↻35週` for an
  item present in 5% of sections. The threshold is deliberately strict.

Sanity check on any new corpus: an item's `weeks` should not greatly exceed its
`template_ratio × section count`. When it does, the chain has drifted.
