# Card Schema — the Atlas 知識庫 (collection `kb`)

The 知識庫 holds **two kinds of cards**, and keeping them distinct is the whole point:

1. **`fact` cards** — canonical, reusable truths that many answers depend on: the pricing
   table, refund policy, standard durations. **The numbers live here, once.** A fact card's key
   is a stable kebab-case id (e.g. `pricing-rates`), unique in the workspace.
2. **`reference` cards** — one per resolved question. They map an inquiry to the facts and
   **cite** them instead of restating the numbers. A new one's key is `qa.<english-slug>`; the
   cards ATL-114 carried over from the CRM keep keys of the form `qa.<hex>`.

Why split them: a price or policy that's copied into ten answers drifts the moment it changes.
Put it in one fact card, have reference cards cite it, and one edit in Atlas updates every
answer. `get_knowledge` on a reference card names the facts it rests on in its 「Cites」 line,
and `/zynkr-support` reads each of them, so the drafter always sees current numbers — *provided
the fact is published*. A draft can cite only published notes, so a new fact is drafted, and
published, before the card that cites it.

> **Rule of thumb:** if a fact could appear in more than one answer, or is the kind of thing
> that changes over time (price, rate, policy, lead time) — it belongs in a **fact card**, and
> reference cards **cite** it. Don't restate cited numbers inside a reference card's body.

Some numbers are not cards at all. A **company fact** (a key starting `company.`, e.g. the hourly
rate) belongs to the owner: only an owner or admin changes one, in Atlas. It is never filed in a
section and never drafted. A card that rests on one cites it by key and never copies its value.

---

## Drafting a card — `mcp__zynkr-atlas__draft_note`

Both kinds go through the one write tool. It makes a **draft** (草稿, 僅團隊), filed under its
section and linked to what it cites, which serves nobody until a person publishes it in Atlas's
審核.

### A `fact` card

```jsonc
{
  "key": "pricing-rates",            // stable, kebab-case — reference cards cite it verbatim
  "kind": "fact",
  "title": "授課費率表",               // short human title
  "body": "<the canonical fact — a short markdown table and/or bullets; the actual numbers/terms>\n\n---\n\nKeywords: 報價 · 費用 · 鐘點 · pricing · rate · per hour\n\nsource_type: core_fact · <YYYY-MM-DD> · <provenance> · <gmail thread permalink>",
  "collection": "kb.core-facts",     // the two style cards live in kb.tone-style
  "cites": []                        // a fact may cite another, a company fact included, by key
}
```

### A `reference` card

```jsonc
{
  "key": "qa.day-course-quote",
  "kind": "reference",
  "title": "一天 N 小時的 AI 課程怎麼報價？人數會影響價格嗎？",  // canonical, normalized question
  "body": "依 FACT:pricing-rates 報價 — 依實際時數計價、線上／實體費率不同、人數不加價；用客戶需要的時數 × 對應費率即為報價。\n\n---\n\nKeywords: 報價 · 費用 · 一天幾小時 · 人數 · quote · day rate · headcount\n\nsource_type: peter_answer · <YYYY-MM-DD> · inbound 詢價 · <gmail thread permalink>",
  "collection": "kb.pricing-quoting",
  "cites": ["pricing-rates"]         // published keys only
}
```

## The body and its footer

A card's body is its text, then a line `---`, then one paragraph per footer line — the shape the
cards carried over from the CRM have (`D-159`), so every card reads the same way:

```
<the card's text>

---

Keywords: 報價 · 費用 · quote · price

source_type: peter_answer · <YYYY-MM-DD> · inbound 詢價 · <gmail thread permalink>

Flags: NEEDS_PETER
```

- **`Keywords:`** — bilingual (zh-TW + EN), separated by ` · `. `search_knowledge` matches every
  word of a query literally against them, so spend effort here.
- **`source_type:`** — the provenance: `peter_answer` (a reply Peter sent) or `core_fact`, then
  ` · ` the date he answered and a short tag, then ` · ` the thread permalink. **No customer PII
  beyond a first name + company; prefer a generic tag like "inbound 詢價" when the identity adds
  nothing.**
- **`Flags:`** — optional. `NEEDS_PETER` when a detail awaits Peter's confirmation; say in the
  text what it is (「實體是否含交通費 — 尚未定義」) and name it in the proposal, so he settles it
  before he publishes. The carried-over cards may also carry `HELD` (the nine held cards, which
  arrive as drafts), `VOLATILE` or `always-read`, and an `Unverify note:` line; those are Peter's.
  /zynkr-support and /sales-inbound read every flag but `always-read`, and every `Unverify note:`,
  as a warning, on a published card too, so a flag comes out once its cause is settled.

## Field rules

- **`key`** — 2–64 characters: lowercase letters, digits, `.`, `_` and `-`, starting with a letter
  or a digit. **Never renamed** — cards cite it. Never one starting `company.`: `draft_note`
  refuses it (`fact_key`). A key that is already taken — by a published card, a draft or an
  archived note — is refused (`key_taken`): a duplicate to find, never a reason to invent a
  second key.
- **`title`** (reference) — Normalize to how a *future* inquirer would ask, not this one's exact
  words. Strip names, pleasantries, one-off specifics. Good: `一天 N 小時的 AI 課程如何報價？`.
  Bad: `回覆<某某>：你問的報價`.
- **`collection`** — the section's key, `kb.<slug>` (the taxonomy is in `intent-taxonomy.md`),
  exactly one per card. It must be **published**: a section still waiting in 審核 holds the card.
- **`cites`** — zero or more published keys, at most 50. If the answer leans on a canonical fact
  (pricing, policy…), **cite it instead of restating the numbers.** If the needed fact doesn't
  exist yet, propose a new fact draft in the same approval round and hold the card until the fact
  is published. In the body's prose keep the `依 FACT:<key>` convention every card uses — the
  drafter reads it naturally.
- **`body`** (reference) — the *mapping/logic*: how this inquiry resolves against the cited facts
  ("依 FACT:pricing-rates，依時數計價、人數不加價"). Only inline a hard number when it is
  **specific to this ticket and not in any fact** (then preserve it verbatim — never round or
  extrapolate). If Peter answered only part of the question, cover only that part and flag the
  gap.
- **Verification** — a card's verified date and its re-check interval are Atlas's: a person sets
  them on the card's page (「標記已驗證」), never this skill.

## Changing a published card — the correction packet

This skill never edits a published card, and `draft_note` cannot. A change goes to Peter as a
packet he applies by hand in Atlas:

```
Correction · `<key>` — <title>
Link:     https://atlas.zynkr.ai/w/<workspace-slug>/knowledge/<key>
Old:      <the line(s) as the card reads now, quoted from get_knowledge>
New:      <the line(s) as they should read>
Evidence: <Gmail thread permalink> · <YYYY-MM-DD> · Peter: 「<his words>」
⚠ price / policy change — confirm before applying     (only when it is one)
```

- One packet per card. Quote only the lines that change, with enough around them to find them.
- A packet for a **company fact** names it by key and says what the reply states; the owner, or
  an admin, changes it in Atlas.
- A new row for the 用語對照表 is a packet for `term-mapping-table`: quote the rows around where
  it goes.
- The next run reads the card again with `get_knowledge`. Once it carries the packet's new line,
  the packet is applied.

## Worked example — a change and a new card from one thread

A resolved thread confirms a new rate and asks something new:

1. `get_knowledge(key: "pricing-rates")` — say its 「Cites」 line names
   `company.pricing-hourly-rate`: the rate lives in that company fact, not in the card. → a
   **correction packet for the company fact**, ⚠ price change. Once the owner applies it, every
   card that cites the fact is current.
2. The thread also asked 「可以拆成兩個半天嗎？」 → a **new reference draft** in
   `kb.scheduling-logistics`, `cites: ["pricing-rates", "standard-durations"]` (both published),
   its body carrying the logic only.
