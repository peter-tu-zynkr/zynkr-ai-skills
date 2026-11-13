# scripts

Deterministic steps for the weekly Doc, so the model never re-derives an index or a range. Each reads
JSON or markdown and writes JSON on stdout, and can be tested without any network call. The routing
parser and the Ledger code are the core's (`../../zynkr-ops-weekly/scripts/`), never copied here.

| Script | In → Out |
|---|---|
| `carryover.py` | Doc markdown → `↻N週` per item, and the items open longest |
| `minutes.py` | the meeting's Fireflies listing + transcript + tracker `#`s → the one transcript to read, then a check of the model's `minutes.json`, and the Ledger rows, the Doc block and `fill.json` from it |
| `sections.py` | The team blocks for Thursday's meeting (`SKB-091` AC-13): the Ledger's `Harvest` rows + Monday's recap facts + routing → 進度 · 卡關 · 下一步 · 待討論 per heading, in `render_block.py`'s block shape so `render_block.py ops` writes them. `items` lists the harvest items the model says again as short zh-TW lines, and `render --short` uses them, cutting at 80 only an item with no usable line (`SKB-127`). From the harvest's totals row it writes the stretch the harvest covers, its counts, and how many lines each part does not list (`SKB-128`). In a week whose lines `collect` tied to tracker items it writes 進度 by item, asks in 待討論 about a status the week's work overtook and about an item nobody touched for three recorded weeks, and keeps the lines it wrote for Monday's recap. `--selftest`, `--mutate` |
| `render_block.py` | the week's evidence + routing (+ carry-over) → the `〔自動彙整〕` block per heading |
| `tidy_blocks.py` | Doc markdown → per group the block to keep, the blocks to archive, the open items to carry. With `--closed`: Drive plain-text export + structure → the `Done`/`Drop` bullets to delete, as index ranges. With `--fill`: `fill.json` + structure → each team's 下一步 and 待討論 as operations |
| `test_tidy_blocks.py` | The `tidy` suite; `--mutate` breaks real lines of `tidy_blocks.py` one at a time |
| `scaffold.gs` | **Apps Script**, not Python — duplicates next week's skeleton. See `../references/scaffold.md` |

## The pipeline after the meeting (`tidy`)

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

# 3. fill — the meeting's actions and open topics under each team's kept block (SKB-091)
tidy_blocks.py --fill fill.json --input m6 --structure s6 --tab t.0 > fill-plan.json
#    … apply fill-plan.json's ops in one batch_update_doc …
tidy_blocks.py --fill-check fill-plan.json --input m7
```

`minutes.py --selftest` (and `--mutate`) covers the minutes check.

All inputs may be saved MCP tool results (`{"result": "..."}`) as-is. Write every block with
`batch_update_doc`, `tab_id` set on **every** operation, inserting **bottom-up** by index;
`../references/doc-write-rules.md` explains why both matter.

## Testing

`python3 test_tidy_blocks.py --mutate` runs the `tidy` suite and then breaks real lines of
`tidy_blocks.py` one at a time; every mutation must turn the suite red. It runs an UNmutated control
copy first and refuses to report anything if that fails — until 2026-09-30 the harness itself produced
uncompilable mutants, so every mutation "passed" and proved nothing.

`carryover.py` is the one worth exercising on real data, because its output is a *judgement* rather
than a transformation, and both of its failure modes are invisible on small fixtures:

- **Template rows.** On the real Doc, 16 of 76 "items" were skeleton labels (`Funnel`, `TOF`,
  `Website`, `CTR`) that repeat every week by design. They are excluded when the corpus is large enough
  for the ratio to mean something **and** the line carries no status — both conditions, because in a
  short document "appears in every section" is exactly what a genuinely stuck item looks like.
- **Drifting matches.** Loose similarity chains: each week it matches a slightly different item and the
  streak walks across unrelated work, which produced a confident `↻35週` for an item present in 5% of
  sections. The threshold is deliberately strict.

Sanity check on any new corpus: an item's `weeks` should not greatly exceed its
`template_ratio × section count`. When it does, the chain has drifted.
