---
name: bad-overlap
originalName: Invoice check with a long script name
type: workflow
description: "Breaks the overlap rule only, on the page drawing: the script named under its gate runs past the gate's column."
executed_by: internal-user
steps:
  - "start | start | Start · an invoice arrives"
  - "check | gate | 1 Total over the limit?"
  - "hold | deterministic | 2 Hold for review"
  - "post | deterministic | 3 Post it"
  - "end | end | End · invoice handled"
flow:
  - "start -> check"
  - "check -> hold | Yes"
  - "check -> post | No"
  - "hold -> end"
  - "post -> end"
page:
  - "check | run=scripts/finance/check_invoice_total_against_the_limit.py"
---

A synthetic flow for the kit's selftest: `lint --layout stacked` must exit 1 with an overlap. The
page drawing writes what runs a gate under it, on one line, and this gate names a script too long
for its column. Plain `lint` passes the same file: Atlas's canvas ignores `page:`.

Until ATL-147 this fixture interleaved two phases, so their bands shared columns on Atlas's canvas.
Each phase now stacks in columns of its own on the canvas too, and that overlap cannot happen.
