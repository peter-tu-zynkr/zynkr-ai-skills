---
name: invoice-approval-flow
originalName: Invoice approval
type: workflow
category: operations
description: "A customer uploads invoices, AI extracts the line items, a reviewer approves anything over $10k, the rest posts itself, and the customer is told."
executed_by: external-user
steps:
  - "## Intake"
  - "start | start | Start · a customer has invoices to send"
  - "upload | input | 1 Upload the invoice CSV"
  - "extract | llm | 2 Extract line items"
  - "schema | knowledge | [RAG] Extraction schema v1"
  - "## Approval"
  - "big | gate | 3 Total over $10k?"
  - "review | hitl | 4 Reviewer approves"
  - "post | deterministic | 5 Auto-post"
  - "log | store | Invoice log"
  - "notify | output | 6 Notify the customer"
  - "end | end | End · customer notified"
flow:
  - "start -> upload"
  - "upload -> extract"
  - "extract -> big"
  - "big -> review | Yes"
  - "big -> post | No"
  - "review -> notify"
  - "post -> notify"
  - "notify -> end"
  - "schema ~> extract | the fields to pull"
  - "review ~> log"
  - "post ~> log"
  - "log ~> notify"
page:
  - "## Intake | The customer sends the file and AI reads it"
  - "## Approval | Over $10k waits for a person; the rest posts itself"
  - "upload | note=One CSV, a row per invoice"
  - "extract | note=AI · reads every row | run=extract-invoice prompt"
  - "big | note=Rules · compares each total"
  - "review | note=A person approves or rejects"
  - "post | note=Rules · no person involved"
  - "notify | note=An email with the result"
  - "schema | note=The fields step 2 pulls | link=https://example.com/extraction-schema | tip=Opens the extraction schema"
  - "log | note=Every approved or posted invoice"
---

# Invoice approval

A customer uploads a CSV of invoices. An AI step extracts the line items, and a gate sends every
invoice over $10k to a reviewer and posts the rest itself. Both paths write the invoice log, and the
customer is told the result. Input: the customer's invoice CSV. Output: every invoice approved or
posted, logged, and the customer notified.

## Steps

**1 · Upload the invoice CSV** — when a customer has invoices to send · Front end · external
- Input: the customer's invoice CSV
- Process: upload the file
- Output: the file, received
- Reads: none
- Writes: none
- Knowledge: none

**2 · Extract line items** — on upload · Backend · AI
- Input: the CSV (step 1)
- Process: extract the line items and totals
- Output: draft invoices
- Reads: none
- Writes: none
- Knowledge: Extraction schema (enforced · new) — to write

**3 · Total over $10k?** — Backend · rules (gate)
- Input: the draft invoices (step 2)
- Process: compare each total to $10k
- Output: Yes → 4, No → 5
- Reads: none
- Writes: none
- Knowledge: none

**4 · Reviewer approves** — when step 3 says Yes · Backend · human
- Input: an invoice over $10k
- Process: approve or reject it
- Output: the approved invoice, and the decision
- Reads: none
- Writes: Invoice log (exists)
- Knowledge: none

**5 · Auto-post** — when step 3 says No · Backend · rules
- Input: an invoice up to $10k
- Process: post it
- Output: a posted invoice
- Reads: none
- Writes: Invoice log (exists)
- Knowledge: none

**6 · Notify the customer** — after 4 or 5 · Front end · external
- Input: the invoice approved in 4 or posted in 5
- Process: look up the logged result and send the notice
- Output: the customer, notified
- Reads: Invoice log (exists)
- Writes: none
- Knowledge: none

## Store directory

- **Invoice log** (data · exists) — every approved or posted invoice
  - Written by 4, 5 · read by 6 · join key: invoice id
- **Extraction schema** (knowledge · enforced · new) — the fields step 2 pulls from each invoice
  - Read by 2 · maintained by: nobody yet · source: to write (before step 2 can rely on it) · kept current by: owner needed
