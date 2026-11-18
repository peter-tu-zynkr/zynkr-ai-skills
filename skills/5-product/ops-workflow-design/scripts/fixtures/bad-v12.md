---
name: bad-v12
originalName: Expense check with a long question
type: workflow
description: "Breaks V12 only: the gate's question is too long for its diamond."
executed_by: internal-user
steps:
  - "start | start | Start · an expense is filed"
  - "file | input | 1 File the expense"
  - "rule | gate | 2 Is the total above the limit finance set for this year?"
  - "approve | hitl | 3 Manager approves"
  - "pay | deterministic | 4 Pay it out"
  - "ledger | store | Expense ledger"
  - "end | end | End · expense paid"
flow:
  - "start -> file"
  - "file -> rule"
  - "rule -> approve | Yes"
  - "rule -> pay | No"
  - "approve -> pay"
  - "pay -> end"
  - "approve ~> ledger"
  - "pay ~> ledger"
---

A synthetic flow for the kit's selftest: `lint` must exit 1 with V12 on `rule`.
