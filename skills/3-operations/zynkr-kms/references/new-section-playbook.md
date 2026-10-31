# New-Section Playbook — the Atlas 知識庫

The 知識庫 is the published collection `kb` in Zynkr Atlas, organized as **sections** — one
collection per intent, `kb.<slug>`, filed under `kb` — holding **fact and reference cards**. You
don't create the 知識庫: the sections already exist (`intent-taxonomy.md`, and the walk in Step 3
of the skill). You only use this playbook when a Peter-approved card has an intent with **no
section yet** (Step 5d of the skill).

## When a new section is justified

- Two or more `kb.other` cards have started looking alike (a real recurring theme), OR
- A resolved thread's intent clearly doesn't fit any existing section, and Peter approved the
  new category in the Step-4 gate (⚠ new-category flag).

Never add a section silently. It changes the routing vocabulary both skills share.

## Drafting the section

A section is a collection note, drafted like a card with `mcp__zynkr-atlas__draft_note`:

```jsonc
{
  "key": "kb.logistics-overseas",    // kb. + a kebab-case slug, unique — the intent tag
  "kind": "collection",
  "title": "海外授課安排",             // its zh-TW title, as the other sections have
  "body": "What it covers, phrased for routing (one or two sentences).\n\nAliases: 海外 · 出國授課 · overseas · abroad · international",
  "collection": "kb"                 // filed directly under the root
}
```

- The body is what the section covers, then a paragraph `Aliases: a · b · c` — bilingual; they
  aid routing, and `search_knowledge` matches them.
- Record it at once with `pending-add` (Step 5 of the skill), with `--collection kb`.

## It waits for Peter — and so do its cards

A draft collection holds nothing: `draft_note` files a card only under a **published**
collection, and answers `collection_not_found` otherwise. So the cards that motivated the
section are **held**, and the run summary names both (🆕 New section drafts · ⏸️ Held). Peter
publishes the section in 審核; the next run drafts the held cards into it.

## After Peter publishes it

1. The next run's walk lists it, and Step 0's mirror gives it a Doc file (`NN-<slug>.md`, the
   next free number): create the Doc with `import_to_google_doc` and add its row to the
   registry in `drive-mirror.md`.
2. Draft the held card(s) into it (Step 5a/5b).
3. Add a row for it to `references/intent-taxonomy.md` (key, nn, titles, covers, aliases) so
   it's first-class next time.

> **History note:** before 2026-07-15 the 知識庫 was a folder of Google Docs; from then until
> ATL-114 it lived in the CRM. Both are retired. The old folder
> (`1LpymoVhy4YrxDBi81Sw6CRQQbZAiSLQ6`) now holds the Drive mirror, rewritten from Atlas.
