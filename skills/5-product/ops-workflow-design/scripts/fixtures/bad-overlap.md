---
name: bad-overlap
originalName: Order with interleaved phases
type: workflow
description: "Breaks the overlap rule only: the two phases share columns, so their bands overlap."
executed_by: external-user
steps:
  - "## Prepare"
  - "start | start | Start · an order arrives"
  - "pack | deterministic | 1.2 Pack the order"
  - "## Pay"
  - "charge | deterministic | 1.1 Charge the card"
  - "end | end | End · order shipped"
flow:
  - "start -> charge"
  - "charge -> pack"
  - "pack -> end"
---

A synthetic flow for the kit's selftest: `lint` must exit 1 with an overlap, because the steps
are written in a different order from the one the work runs in.
