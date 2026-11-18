---
name: bad-v9
originalName: Sign-up that loops back to the start
type: workflow
description: "Breaks V9 only: an incomplete form goes back to the start step instead of to the form."
executed_by: external-user
steps:
  - "start | start | Start · someone wants an account"
  - "form | input | 1 Fill in the sign-up form"
  - "check | gate | 2 Form complete?"
  - "create | deterministic | 3 Create the account"
  - "users | store | User table"
  - "welcome | output | 4 Show the welcome page"
  - "end | end | End · account ready"
flow:
  - "start -> form"
  - "form -> check"
  - "check -> create | Yes"
  - "check -> start | No"
  - "create -> welcome"
  - "welcome -> end"
  - "create ~> users"
---

A synthetic flow for the kit's selftest: `lint` must exit 1 with V9 on `start`.
