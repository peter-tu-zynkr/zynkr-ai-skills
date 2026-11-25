---
name: architecture-template
originalName: Architecture template
type: workflow
category: operations
description: "A shape reference: a generic AI-assisted workflow with one of each common step on the three lanes."
executed_by: internal-user
steps:
  - "input | input | Manual input"
  - "ai | llm | AI process"
  - "doc | artifact | Document"
  - "decide | gate | Decision"
  - "db | store | Database"
  - "ai_yes | llm | AI process"
  - "kb_one | knowledge | Knowledge for retrieval"
  - "manual_yes | hitl | Manual operation"
  - "kb_two | knowledge | Knowledge for retrieval"
  - "manual_no | hitl | Manual operation"
  - "out | output | Output to human | by=external"
flow:
  - "input -> ai"
  - "ai -> decide"
  - "decide -> ai_yes | Yes"
  - "decide -> manual_no | No"
  - "ai_yes -> manual_yes"
  - "manual_no -> out"
  - "doc ~> ai"
  - "ai ~> doc"
  - "db ~> decide"
  - "decide ~> db"
  - "kb_one ~> ai_yes"
  - "kb_two ~> manual_yes"
---

# Architecture template

One of each common step, laid out on the three lanes: a shape reference, not a process anyone runs.
The titles are the shapes' names, so the steps carry no numbers, and the body has no step cards.
