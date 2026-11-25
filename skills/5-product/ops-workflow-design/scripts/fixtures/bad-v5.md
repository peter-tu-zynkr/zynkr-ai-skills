---
name: bad-v5
originalName: FAQ answer with no check
type: workflow
description: "Breaks V5 only: an AI step's answer goes straight to the customer."
executed_by: external-user
steps:
  - "start | start | Start · a question arrives"
  - "ask | input | 1 Ask a question"
  - "answer | llm | 2 Draft the answer"
  - "faq | knowledge | [RAG] Product FAQ v3"
  - "show | output | 3 Show the answer"
  - "end | end | End · answer shown"
flow:
  - "start -> ask"
  - "ask -> answer"
  - "answer -> show"
  - "show -> end"
  - "faq ~> answer"
---

A synthetic flow for the kit's selftest: `lint` must exit 1 with V5 on `answer`.
