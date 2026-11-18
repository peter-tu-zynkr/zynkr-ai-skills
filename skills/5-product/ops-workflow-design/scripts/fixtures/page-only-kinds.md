---
name: page-only-kinds
originalName: Reply drafting with page-only steps
type: workflow
description: "One step of each page-only kind: a context note, a junction and ephemeral notes."
executed_by: external-user
steps:
  - "## Intake"
  - "start | start | Start · a request arrives"
  - "ask | input | 1 Send the request"
  - "notes | context | Call notes (this session) | col=2"
  - "draft | llm | 2 Draft the reply"
  - "scratch | ephemeral | Draft notes (session only)"
  - "## Reply"
  - "check | gate | 3 Reply complete?"
  - "fork | junction | Send and file"
  - "send | output | 4 Send the reply"
  - "file | deterministic | 5 File the reply"
  - "log | store | Reply log"
  - "end | end | End · reply sent and filed"
flow:
  - "start -> ask"
  - "ask -> draft"
  - "draft -> check"
  - "check -> fork | Yes"
  - "check -> draft | No, redo"
  - "fork -> send"
  - "fork -> file"
  - "send -> end"
  - "file -> end"
  - "notes ~> draft"
  - "draft ~> scratch"
  - "file ~> log"
---

A synthetic flow for the kit's selftest: `render` draws `notes`, `fork` and `scratch` in their
rows' shapes and fills, `lint` exits 0 and warns three times, and Atlas drops the three steps.
