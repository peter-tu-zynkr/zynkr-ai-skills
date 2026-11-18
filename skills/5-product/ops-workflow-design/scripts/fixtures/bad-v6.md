---
name: bad-v6
originalName: Lead routing with an unlabelled branch
type: workflow
description: "Breaks V6 only: one branch out of the gate has no label."
executed_by: external-user
steps:
  - "start | start | Start · a lead fills in the form"
  - "form | input | 1 Fill in the form"
  - "score | deterministic | 2 Score the lead"
  - "hot | gate | 3 Hot lead?"
  - "call | hitl | 4 Call the lead"
  - "nurture | deterministic | 5 Add to the newsletter"
  - "crm | store | Lead list (CRM)"
  - "end | end | End · lead followed up"
flow:
  - "start -> form"
  - "form -> score"
  - "score -> hot"
  - "hot -> call | Yes"
  - "hot -> nurture"
  - "call -> end"
  - "nurture -> end"
  - "call ~> crm"
  - "nurture ~> crm"
---

A synthetic flow for the kit's selftest: `lint` must exit 1 with V6 on `hot`.
