---
name: bad-v4
originalName: Claim review with no record
type: workflow
description: "Breaks V4 only: a person reviews the claim, and nothing records the decision."
executed_by: external-user
steps:
  - "start | start | Start · a claim arrives"
  - "send | input | 1 Send the claim"
  - "check | deterministic | 2 Check the fields"
  - "review | hitl | 3 Review the claim"
  - "tell | output | 4 Tell the claimant"
  - "end | end | End · claimant told"
flow:
  - "start -> send"
  - "send -> check"
  - "check -> review"
  - "review -> tell"
  - "tell -> end"
---

A synthetic flow for the kit's selftest: `lint` must exit 1 with V4 on `review`.
