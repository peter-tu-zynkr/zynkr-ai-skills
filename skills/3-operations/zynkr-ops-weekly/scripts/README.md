# scripts

Deterministic steps live here so the model never re-derives them. These are the weekly loop's shared
code: `ops-weekly-doc` and `ops-weekly-tracker` call them here (`<core>/scripts/…`) and keep no copy
(SKB-091). `ledger.py` carries an `API` number those skills check before they import it.

| Script | In → Out |
|---|---|
| `parse_routing.py` | Doc markdown → `{heading → owner email}` read from the person chips |
| `ledger.py` | The Weekly Ledger (`SKB-044`). Prints the exact MCP calls for each step of `snapshot` and of every weekly block write, and checks every saved result before the next. Works from files in a run folder, not stdin. See `../references/ledger.md` |
| `recap.py` | The Monday recap (`SKB-044`): reads last week's blocks from the Ledger, runs zynkr-gm's `derive_state.py`, and renders the mail; the run writes only the TL;DR, and lines citing no item number are dropped. `--selftest`, `--mutate` |
| `harvest.py` | Thursday's `collect` (`SKB-091` AC-12): finds the Wednesday harvest routine's week folder, waits while its run file is missing or not `ok`, parses each `harvest-<person>.md` into the Ledger's `Harvest` rows, and plans the one Chat line for the quiet weeks. `--selftest` (the routine's file shapes), `--mutate` |
| `check_manifest.py` | Holds the four skills of the loop to `split-manifest.json`: each folder holds exactly its listed files, no file is in two homes, each SKILL.md runs exactly its modes, and `beats.py` hands each mode to that home. `--mutate` breaks a copy six ways; each must fail |

Moved in SKB-091: `carryover.py`, `render_block.py`, `tidy_blocks.py` (+ its tests) and `scaffold.gs` to
`ops-weekly-doc`; `proposals.py` and `tracker_guard.py` to `ops-weekly-tracker`; `beats.py` and the runner
(now `run_week.sh`) to `project-manager`. `parse_reports.py` retired with the Tuesday rollup.

## The Ledger's snapshot pipeline (run by `ops-weekly-tracker`)

```bash
ledger.py snapshot start --week 2026-W40      # → dir + 5 calls (tracker/Ledger info, Ledger headers, the Weeks row)
ledger.py snapshot pages   --dir "$D"         # → "already": true, or the tracker reads (50 rows a page)
ledger.py snapshot plan    --dir "$D"         # → ops (the block write + clear), readback, recheck
ledger.py snapshot check   --dir "$D"         # → the Weeks commit call, only when every cell matches
ledger.py snapshot confirm --dir "$D"         # → delivered=55-items;Snapshot!A2:P56;Weeks!A2
```

Each step prints calls as `{"tool", "args", "save"}`; the model makes each call with `args` exactly and
saves the whole result to `save`.

`ledger.py diff --a A.json --b B.json [--updates U.json]` compares two weeks' blocks (JSON lists of
16-column rows) and lists every changed cell, plus items added and removed. A change is `logged` only
when an `Updates` row with the same cycle, `#`, column and new value falls inside the window between
the two snapshots; everything else is a manual edit. Monday's recap reads this. `ledger.py --selftest`
runs the whole pipeline against fake MCP results; `--mutate` checks that each deliberate breakage turns
the selftest red.

## Exit codes

`0` success · `2` bad config or a section that does not exist · `3` no owner chips found (the usual
cause is having read the Doc as plain text instead of markdown).

`ledger.py` has its own: `2` config or arguments · `3` input refused (missing, truncated, wrong file or
range, a row count that does not match) · `4` structure changed · `5` out of room in the Ledger · `6`
check failed, do not commit · `7` the commit did not read back.

Diagnostics that must reach the run report are written to **stderr** and also carried in the JSON
(`unrouted_headings`, `reporters_without_heading`). None of these are fatal, and none should be
swallowed.
