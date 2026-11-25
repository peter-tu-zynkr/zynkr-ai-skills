---
name: synthetic-layout
originalName: Layout cases
type: workflow
description: "A synthetic flow that exercises the stacked layout: phases, a split column, the front end over its step, data boxes, a retry, a skip and col=."
executed_by: internal-user
steps:
  - "## Collect"
  - "start | start | Start · a batch is due"
  - "pull | input | 1.1 Pull the batch | by=external"
  - "clean | deterministic | 1.2 Clean the rows"
  - "rows | store | Row table"
  - "guide | knowledge | [RAG] Cleaning guide v1"
  - "notes | knowledge | [RAG] Field notes v2"
  - "## Check"
  - "score | llm | 2.1 Score each row"
  - "fit | gate | 2.2 Scores fit?"
  - "fix | hitl | 2.3 Fix the outliers"
  - "fixlog | artifact | Fix record"
  - "auto | deterministic | 2.4 Accept the batch"
  - "early | deterministic | 2.5 Flag early rows | col=0"
  - "learned | knowledge | [RAG] Learned rules v1"
  - "## Hand off"
  - "handoff | offpage | 3.1 Send to reporting"
  - "show | output | 3.2 Show the summary"
  - "end | end | End · batch done"
flow:
  - "start -> pull"
  - "pull -> clean"
  - "clean -> score"
  - "score -> fit"
  - "fit -> fix | No"
  - "fit -> auto | Yes"
  - "fix -> score | rescore"
  - "auto -> handoff"
  - "handoff -> show"
  - "show -> end"
  - "start -> show"
  - "clean ~> rows"
  - "guide ~> clean"
  - "notes ~> score"
  - "fix ~> fixlog"
  - "fix ~> learned"
  - "rows ~> score"
  - "early ~> rows"
---

A synthetic flow for the kit's selftest. The cells it exercises, the same on Atlas's canvas and on
the page since ATL-147 (one placement rule for both):

- Each phase takes columns of its own: Collect column 0, Check columns 1 and 2, Hand off column 3.
- Check holds five backend steps, one more than a column holds, so they split as evenly as they go,
  the fuller column first: `score`, `fit` and `fix` in column 1, `auto` and `early` in column 2.
- `start` and `pull` sit over the step after them, `show` over the step before it. With an internal
  and an external front-end step, the front end takes two bands.
- `rows` sits under the step that first writes it (`clean`; `early` writes it later), `fixlog`
  under its writer, `guide` and `notes` under their first reader, after the stores and artifacts in
  their stack. `learned`, which no step reads, sits under `fix`, the step that keeps it, after
  `notes`.
- `fix -> score` returns to a step higher in its stack: a retry. It moves nothing, and its line
  loops back beside the column.
- `start -> show` skips ahead and moves nothing.
- `early` asks for `col=0`, which moves nothing: it stays under `auto` in column 2, and lint notes
  it (`col_ignored`).
