# Process step card — one format for every process step

> **Seed:** `docs/process-shared/process-step-card.md` (SKB-040; knowledge lane SKB-042). Copied byte-identically into
> `references/process-step-card.md` of `ops-transformation` (3.10),
> `ops-flow-optimization` (3.14) and `ops-workflow-design` (5.03). Edit the seed, then
> re-copy all three in the same commit. No CI gate holds the copies identical yet — compare them by
> hand (`cmp`) before you push.

Whoever reads a process should be able to answer two questions at any step, without scrolling to
another section:

1. **What goes in, what happens, what comes out?** — the step's Input · Process · Output (IPO).
2. **Does this step touch a system, which data, and what must it know?** — its layer, the data it
   Reads and Writes, and the Knowledge it relies on (the FE / BE / DB view; the DB is the bottom
   lane, and it holds both data and knowledge — §3).

Splitting these into two places — a SIPOC table here, an architecture table there — is exactly
what this format exists to prevent. Every step carries both, on one card.

---

## 1. Number every step

- Numbers are hierarchical, `parent.child`: steps in a grouped flow (stages, beats, days) are
  `1.1, 1.2, 2.1…`; the sub-tasks a redesign breaks step 3 into are `3.1, 3.2…`. A flat flow is
  just `1, 2, 3`.
- The number is the step's id **everywhere**: in the chat output, in the document, in the store
  directory (§4), and on the Lucid node (`ops-workflow-design` puts it on the node's first line).
  Someone holding the chart and the document must be able to match them by number alone.
- If you add, remove, merge or move a step, renumber and say so in one line — an `old → new` map. Never
  renumber silently. Keep the parent number and renumber only the children under it (a step added
  between 3.1 and 3.2 makes the old 3.2 into 3.3; step 4 stays step 4), so numbers outside the
  change never move. Whatever comes downstream — the final blueprint, the Lucid chart — uses the
  numbers of the **last** pass that renumbered.

## 2. The card

Every step uses the same lines, in this order:

```
**N · Step name** — when / trigger · layer
- Input: what must exist for the step to start (and who or what supplies it)
- Process: one verb + object — the single piece of work
- Output: the artifact or state change it leaves behind (and who or what receives it)
- Reads: the data stores it reads — or "none"
- Writes: the data stores it writes, and any knowledge source it maintains, marked (knowledge) — or "none"
- Knowledge: the knowledge sources it relies on, each with its link — or "none" (§3)
```

Rules:

- **Input · Process · Output are always present.** A step with no real output is a note, not a
  step — merge or drop it (`ops-flow-optimization` Step 2). A step doing two things is two
  steps.
- **Layer · Reads · Writes · Knowledge are required whenever the step touches a system** — every
  to-be or redesigned flow, and every flow that is going onto a Lucid chart. See §5 for the as-is
  case.
- **"none" is a value, not a blank.** `Reads: none · Writes: none · Knowledge: none` tells the
  reader the step needs nothing from the bottom lane. Those are the most useful lines on the card —
  never leave them out on a to-be step, not even in a compact one-line card.
- **Where a step is triggered from is its Input, not a Read.** The inbox an email arrives in, the
  form a file is uploaded through: those go on `Input:`. `Reads:` is for stores the step looks
  something up in.
- **The trigger** (`when / trigger` in the header) may be left out only when it is simply "after the
  previous step".
- **A card may sit on one line** when it is short, as long as it keeps every field:
  `N · name — layer — Input: … · Process: … · Output: … · Reads: … · Writes: … · Knowledge: …`. A
  summary line that drops Input · Process · Output, or leaves out a `none`, is not a card.
- **Name the store, then the tool:** `Invoice log (Airtable)`, not `Airtable`. Mark a store that
  does not exist yet with **(new)**.
- **One step, one layer.** If an AI drafts and a person approves, those are two steps.
- Bullets, not tables, for to-be cards: a reader scans one card top to bottom. A table is fine
  as an at-a-glance summary **in addition** to the cards, never instead of them. The one
  exception is the as-is SIPOC (§5).

## 3. Layer vocabulary

The same words as the Lucid lanes in `ops-workflow-design`, so a card and a chart node always agree:

| Layer | What it means | Lucid lane · colour |
|---|---|---|
| **Front end** | A person sees or types something: a form, a mail, a chat post, a dashboard | FE lane · red family (darker = input, lighter = output) |
| **Backend · human** | A person decides, reviews or approves (HITL) | BE manual lane · light blue |
| **Backend · rules** | Fixed logic: rule-based automation, a state machine, a script | BE machine lane · purple |
| **Backend · AI** | An LLM step. Needs a gate or a human downstream | BE machine lane · blue |

Two qualifiers may follow a layer, nothing else: **external / internal** after Front end (who the
person is — a customer, or someone on the team), and **(gate)** after Backend · rules when the step
is a decision that branches the flow. `Front end · external`, `Backend · rules (gate)`.

A **person seeing or typing** is Front end; a **person deciding or approving** is Backend · human. A
reviewer who opens a queue and approves rows is Backend · human — the approval is the step.

**"Needs a gate or a human downstream"** means: before the AI step's output is sent, published, or
written to a system of record, a Backend · rules gate or a Backend · human step checks it.

### The bottom lane: data and knowledge

**The database is never a step's layer.** The bottom lane holds two kinds of thing a step uses, and
the card names both:

| On the card | What it is | Lucid (`ops-workflow-design`) | Atlas workflow |
|---|---|---|---|
| `Reads:` / `Writes:` | A **data store** — a system of record: a log, a table, a record, a state | `Data base data table` sub-lane | a `store` step |
| `Knowledge:` | A **knowledge source** — what the step must know to do the work well: rules, policies, playbooks, price lists, FAQs, past examples, templates | `Knowledge base knowledge` sub-lane · dark-green document labelled `[RAG] <name> v<version>` | a `knowledge` step |

A "save the record" sub-task is a Backend · rules step whose `Writes:` names the store. A step that
**maintains** a knowledge source — writes a KB card, updates the rule table — names that source on
its `Writes:` line, marked `(knowledge)`; `Knowledge:` is only for what a step relies on.

A knowledge source is one of two kinds (`ops-workflow-design` architecture principles §1.3):

- **retrieved** — searched by meaning at run time: retrieval (RAG) over the canonical documents —
  FAQs, past cases, manuals. The index is not the truth; it points to them.
- **enforced** — applied exactly, every time: a codified policy, a rule table, a price list, a
  schema, a prompt rule set. An exact lookup is enforced, not retrieved. Versioned like code.

Write each source as `<source> (retrieved | enforced · new | exists) — <link | link needed | to
write>`, and separate two sources with `;` —
`Knowledge: Discount rules (enforced · new) — to write; Price list (enforced · exists) — <Sheet URL>`.

- **The link is the canonical source** — an Atlas knowledge key, a Doc or Sheet URL, a repo path.
  Use only a link the input, the conversation or Atlas actually gives you; never invent one. When the
  `zynkr-atlas` server is connected and the source could be a published Zynkr knowledge node, look it
  up (`get_knowledge`) before you settle for `link needed`.
- **`link needed`** — the source exists, but you have no link. **`to write`** — the source is
  `(new)`: nobody has written it yet, so there is nothing to link, and someone has to write it
  before the step can rely on it.
- **Know-how that lives only in someone's head is not a source yet.** On a `kept as is` card, or on
  a redesigned card whose knowledge gap waits, write it as `Knowledge: tacit — <who knows it>` (an
  as-is SIPOC records it in Systems today instead). It is a knowledge gap (§7), not a source: it
  stays out of the store directory until a card turns it into a `(new)` source.
- A chart node carries the source's name, not its link — keep the link on the card and in the store
  directory.
- **An AI step always has a real Knowledge line.** `Knowledge: none` on a Backend · AI step means it
  answers from the model alone — say in a few words why that is safe, or call it a gap (§7).
- A person can need knowledge too: a reviewer applying a policy, a quoter using a price list. Put it
  on their card; that is often exactly the knowledge to pull out of their head (§7).

Mapping from the `operations-automation-validation` tech suggestion: **Human** → Backend · human ·
**Rule-based** or **State Machine** → Backend · rules · **LLM** → Backend · AI.

## 4. Store directory

Any flow that touches two or more stores or knowledge sources ends with a directory — the same
facts as the cards, read from the bottom lane's side. Data stores first, then knowledge sources:

```
- **Store name** (data · new | exists) — what it holds
  - Written by N, N · read by N, N · join key: <the field that links a row to a step's subject>
  - Columns: … (new stores only)
- **Source name** (knowledge · retrieved | enforced · new | exists) — what it holds
  - Read by N, N · maintained by: <N | outside this flow (<who>) | nobody yet> · source: <link | link needed | to write> · kept current by: <owner | owner needed>
```

Every store named on a Reads / Writes line and every source named on a Knowledge line appears here
(`tacit` lines excepted — §3), and every step number listed here exists above. These are findings —
say so: a data store nothing writes, or nobody reads; a knowledge source with `link needed`,
`owner needed`, or maintained by `nobody yet`; a `(new)` source, because someone has to write it
before the step can rely on it. A data store written outside this flow (the ERP's own inventory) says
`written outside this flow`, and a source kept outside it (a policy the legal team keeps) says
`maintained by: outside this flow (legal)` — neither is a finding. `kept current by` names the one
person or team accountable for it; that can be the outside team. Name an owner only when the input
names one; an inferred owner is marked `(assumed)`, and otherwise it is `owner needed` — never
invent one.

## 5. As-is versus to-be

- **As-is** (discovery, SIPOC mapping, a raw process someone describes): Input · Process · Output on
  every step, plus Supplier and Customer. In place of Reads / Writes / Knowledge, give **Systems
  today** — where the step's input and output live now (an inbox, a spreadsheet, paper, someone's
  head), and where the data and know-how the person relies on live (a price list on one desktop,
  looked up by hand in the ERP, "only Amy knows"). Those last two are where the gaps (§7) show up.
  Layer is optional: the redesign assigns it. Here a **numbered SIPOC table** is the card —
  `| # | Supplier | Input | Process | Output | Customer | Systems today |`, one row per step —
  because the as-is card has exactly those fields and a table compares them best.
- **To-be** (redesign, the optimization of a redesigned flow, anything drawn on Lucid): the full
  card. Reads, Writes and Knowledge are required.
- **A step the redesign leaves alone** stays in the to-be flow as a card marked `kept as is`:
  its Input · Process · Output, `Layer: kept as is (manual today)` — or the layer it already has —
  and Reads / Writes / Knowledge taken from its Systems today (know-how only in someone's head stays
  `Knowledge: tacit — <who>`, §3), so the store directory still counts the systems it touches.
- **Carry, don't drop.** A skill that does not assign layers itself (`ops-flow-optimization`)
  still carries every line it was handed — on to-be cards layer, Reads, Writes, Knowledge, Tool; on
  an as-is SIPOC Supplier, Customer, Systems today — through to its output, unchanged. A step that skill **adds** (a split, a missing connector) gets its Input ·
  Process · Output and the line `Layer / Reads / Writes / Knowledge: to assign →
  ops-transformation` on its own card.
- **Reading a chart back** (`ops-workflow-design` READ): node labels are short, so Input and Output
  are often inferred from the edges — mark an inferred field `(inferred)`, and write `not shown on
  the chart` rather than inventing one (once above the cards, when no node carries it — a template
  with generic labels). Knowledge nodes are the ones in the `Knowledge base knowledge` sub-lane,
  or any dark-green `DocumentBlock` when the lanes carry other names. The arrowhead rule is the same
  as for stores: arrowhead at the step means the step relies on the source (its `Knowledge:` line),
  arrowhead at the source means the step maintains it (its `Writes:` line, marked `(knowledge)`). `(new | exists)`, "what it holds" and the join key go in the
  store directory only when the chart says them. A store a chart draws twice on purpose (last
  week's and this week's copy of a log) is one entry in the directory, with a note that it is
  drawn twice — not two half-used stores.

## 6. Example (to-be, four steps of an invoice flow)

**2 · Extract line items** — on upload · Backend · AI
- Input: the invoice PDF (from step 1, the customer upload)
- Process: extract vendor, date, line items and total
- Output: a draft invoice record with a confidence score
- Reads: none
- Writes: none (the draft passes to step 3)
- Knowledge: Extraction schema (enforced · new) — to write; Past corrected invoices (retrieved · exists) — link needed

**3 · Route by amount and confidence** — Backend · rules (gate)
- Input: the draft invoice record (step 2)
- Process: send totals over $10k, or confidence under 0.8, to review (step 4); the rest to auto-post (step 5)
- Output: the routed record
- Reads: none
- Writes: none
- Knowledge: none

**4 · Reviewer approves** — when step 3 routes to review · Backend · human
- Input: the routed record, shown beside the source PDF
- Process: approve, edit or reject
- Output: an approved record and the decision
- Reads: Invoice log (exists) — to check for duplicates
- Writes: Invoice log (exists) · Decision log (new) · Past corrected invoices (knowledge) — every edit the reviewer makes becomes an example
- Knowledge: Approval policy (enforced · exists) — link needed

**5 · Auto-post** — when step 3 routes to auto-post · Backend · rules
- Input: the routed record (step 3)
- Process: post the invoice
- Output: a posted invoice
- Reads: none
- Writes: Invoice log (exists)
- Knowledge: none

Store directory:

- **Invoice log** (data · exists) — every posted invoice
  - Written by 4, 5 · read by 4 · join key: invoice id
- **Decision log** (data · new) — every human decision and its reason
  - Written by 4 · read by — (nothing reads it yet: a finding — who audits it?)
  - Columns: invoice id, decision, reviewer, reason, decided_at
- **Extraction schema** (knowledge · enforced · new) — the fields and formats step 2 must return
  - Read by 2 · maintained by: nobody yet · source: to write (before step 2 can rely on it) · kept current by: owner needed
- **Past corrected invoices** (knowledge · retrieved · exists) — invoices a reviewer fixed, as examples for step 2
  - Read by 2 · maintained by: 4 · source: link needed · kept current by: owner needed
- **Approval policy** (knowledge · enforced · exists) — who may approve what, up to which amount
  - Read by 4 · maintained by: outside this flow (finance) · source: link needed · kept current by: finance

## 7. Gaps to call out

Two gaps clients rarely see on their own. Whoever assesses a flow (`operations-automation-validation`)
checks every step for both and says so; whoever redesigns it (`operations-process-redesign`) closes
each one with a card, or says why it waits.

- **Knowledge gap — pull the knowledge out of the step.** The step's quality depends on knowledge
  that lives inside the process: in one person's head, in old emails, in a long prompt pasted every
  time, re-explained case by case — or that is written down but not connected, looked up by hand in a
  separate file each time. Signals: "only Amy knows", "it depends on the client", answers
  differ by who does it, new staff take months to get it right, AI drafts come out generic or wrong
  on specifics. The fix is a knowledge source in the bottom lane that the step reads — **retrieved**
  (RAG) when it is searched by meaning, **enforced** when it is applied exactly, every time (a rule
  table, a price list). Separating it from the
  process lane is what raises accuracy, more than a bigger model or a longer prompt.
- **Data gap — connect the step to its data.** The step needs data it is not connected to: someone
  looks it up by hand in another system, retypes it, works from an old export or from memory, or
  decides without data that exists elsewhere. Signals: copy-paste between systems, "I check the ERP
  and type it in", numbers that are a week stale. The fix is a `Reads:` line to the data store,
  naming the store and the system it lives in.

Write each gap on one line, under the step's number:

```
N · Gap · knowledge — <what the step needs to know> → <source> (retrieved | enforced · new | exists) — <link | link needed | to write>
N · Gap · data — <what the step needs to see> → <store (system)> (new | exists)
```

- Call a gap only for a reason you can name — what the client said, or what the step plainly needs.
  Mark an inferred one `(assumed)`.
- "None found" is a valid result for a step; do not invent gaps to fill the table.
- Both gaps are about what a step needs to **read**. A step that keeps no record of what it decided
  or sent is a different finding — say it in the rationale, not as a gap.
- A gap is closed in the to-be flow by a card that reads the source (`Knowledge:`) or the store
  (`Reads:`). A gap the redesign does not close stays listed with the reason it waits. Never drop
  one silently.
