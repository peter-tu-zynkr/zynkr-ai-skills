---
name: synthetic-layout
originalName: Layout cases
type: workflow
description: "A synthetic flow that exercises the layout: longest paths, a back edge, companions, col= and collisions."
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
  - "early | deterministic | 2.5 Flag early rows | col=2"
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

A synthetic flow for the kit's selftest. The columns it exercises:

- `start -> show` is shorter than the spine, so `show` takes the longest path's column.
- `fix -> score` returns to a step already on the walk: a back edge, drawn but not counted.
- `rows`, `fixlog` and `learned` are written by a step, so each sits under its writer.
- `guide` and `notes` are only read and carry no `col=`, so both aim at column 0; `notes` moves
  right.
- `early` asks for `col=2`, which `clean` holds, so it moves right past every step that came
  before it in the file, and pushes `handoff` along.
