---
name: synthetic-placement
originalName: Placement edges
type: workflow
description: "A synthetic flow for three placement rules no other fixture reaches: a lead at a column boundary, knowledge under its leftmost reader though a later step writes it, and a data box with no line."
executed_by: internal-user
steps:
  - "## Prepare"
  - "start | start | Start · a batch is due"
  - "check | deterministic | 1 Check the batch"
  - "split | deterministic | 2 Split it"
  - "price | deterministic | 3 Price each part"
  - "confirm | input | 4 Confirm the prices"
  - "apply | deterministic | 5 Apply the prices"
  - "send | deterministic | 6 Send the batch"
  - "guide | knowledge | [RAG] Pricing guide v1"
  - "archive | store | Archive"
  - "## Close"
  - "review | deterministic | 7 Review the run"
  - "update | deterministic | 8 Update the guide"
  - "end | end | End · the batch is sent"
flow:
  - "start -> check"
  - "check -> split"
  - "split -> price"
  - "price -> confirm"
  - "confirm -> apply"
  - "apply -> send"
  - "send -> review"
  - "review -> update"
  - "update -> end"
  - "guide ~> apply"
  - "guide ~> check"
  - "guide ~> review"
  - "update ~> guide"
---

A synthetic flow for the kit's selftest, for three placement rules no other fixture reaches. Atlas's
canvas and the page place it the same way (ATL-147). Each case is built so that every wrong variant of
its rule tried in review puts a step in another cell, in the kit and in Atlas:

- Prepare holds five backend steps and splits them three and two: `check`, `split` and `price` in
  column 0, `apply` and `send` in column 1. Close's two steps take column 2.
- `confirm`, an input, leads into `apply`, so it starts column 1 with it, over `apply`, though the
  step before it sits in column 0.
- `guide`, a knowledge source, is read from columns 1, 0 and 2, in that order in the file, and kept
  up to date by `update` in column 2. It sits under its leftmost reader, `check`, in column 0: not
  under the reader listed first or last, not under its rightmost reader, and not under the step that
  writes it, as a store would.
- `archive` has no line at all. It sits with the step above it in the file that is not a data box,
  `send`, in column 1: not in column 0, not in the last column, not with the step after it
  (`review`, column 2), and not with `guide`, the data box just above it.
