---
name: bad-v14
originalName: Refund with a crowded column
type: workflow
description: "Breaks V14 only: four steps share the column after the gate."
executed_by: external-user
steps:
  - "start | start | Start · a refund is asked for"
  - "ask | input | 1 Ask for a refund"
  - "check | gate | 2 Over $500?"
  - "approve | hitl | 3 Approve the refund"
  - "auto | deterministic | 4 Refund at once"
  - "log | store | Refund log"
  - "policy | knowledge | [RAG] Refund policy v2 | col=3"
  - "tell | output | 5 Tell the customer"
  - "end | end | End · refund settled"
flow:
  - "start -> ask"
  - "ask -> check"
  - "check -> approve | Yes"
  - "check -> auto | No"
  - "approve -> tell"
  - "auto -> tell"
  - "tell -> end"
  - "approve ~> log"
  - "policy ~> approve"
---

A synthetic flow for the kit's selftest: `lint` must exit 1 with V14 on `col=3` (columns count from
0, as `col=` does), which holds `approve`, `auto`, `log` and `policy`.
