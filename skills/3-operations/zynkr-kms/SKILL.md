---
name: zynkr-kms
sheetId: "3.02"
description: >-
  The knowledge-curator (WRITE) half of Peter's support loop. After a support /
  inbound-sales ticket is resolved it reads the thread, learns Peter's actual answer and — only
  after Peter approves — drafts it as a clean, LLM-friendly card in the **知識庫** in Zynkr Atlas
  (the published collection `kb`, via the `zynkr-atlas` MCP server; the single source of truth):
  each draft is filed in its section and linked to the facts it cites, and serves no one until
  Peter publishes it in Atlas. Canonical numbers and policies become `fact` cards; answers become
  reference cards that CITE those facts instead of restating numbers; a change to a published card
  goes to Peter as a correction packet. Every run it first catches the members-only Google Drive
  backup (one Doc per section plus a JSON snapshot) up with Atlas, one way.
  Trigger whenever Peter says "/zynkr-kms", "learn from resolved tickets", "update the support KB",
  "curate the KB", "把已回覆的 support 信變成知識庫", "更新知識庫", "整理 KB", "let the KB learn", or
  hands over a resolved support/sales thread and wants the answer captured — and also on
  "備份知識庫", "back up the KB", "sync the KB to Drive", "mirror the KB", "KB 有沒有備份",
  "reconcile the KB mirror". This is the WRITE side; /zynkr-support is the READ side.
category: operations
project: zynkr-kms
platform: claude
status: WIP
visibility: public
author: Peter Tu
input: "Resolved Support／Inbound-Sales Gmail threads (or one Peter specifies); the 知識庫 is the `kb` collection in Zynkr Atlas (SOT), mirrored one-way to a Google Drive backup"
process: "Mirror catch-up → pull resolved, un-ingested threads → extract Peter's answer (PII-stripped) → classify section and fact vs reference → propose for approval → draft filed, linked cards (facts first) → correction packets → label threads once published"
output: "Filed, linked drafts in Atlas 審核; correction packets for Peter; the Drive backup caught up (changed Docs + snapshot); threads labelled KMS-ingested once published"
synergy: ["zynkr-support"]
reads: ["kb", "tone-voice-rules", "term-mapping-table", "company.contact-email"]
house-style: bound

---

# Zynkr KMS — Support Knowledge Curator (Atlas 知識庫 + Drive mirror)

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill zynkr-kms
```

`/zynkr-support` *reads* the 知識庫 to draft replies. This skill is the other half of the loop: it
**learns from resolved tickets and drafts the answers back** so the 知識庫 heals and the drafter
stops falling back to `[[NEEDS PETER]]` holding replies.

You think like a **KMS specialist**, not a transcriber. For every resolved thread you reason
through three lenses before anything is drafted:

1. **Intent taxonomy** — what *kind* of question is this?
2. **Where it goes** — which **section** does it belong in, and is it a new card or a change to one?
3. **Structure for the LLM** — a canonical `fact` card, or a reference card that cites facts?

The golden rule: **extract, never invent.** Facts come only from what Peter actually wrote. A bad
card silently poisons every future auto-reply, so the bar is high and **nothing enters the 知識庫
without Peter twice**: he approves the proposal here (Step 4), and he publishes each draft in Atlas.

> **This skill governs TWO stores, and the arrow between them only points one way.**
>
> ```
> Zynkr Atlas 知識庫 (collection kb)  ──(mirror)──▶  Google Drive Docs
>   (SOT · drafts wait in 審核)                       (read-only backup)
> ```
>
> - **Zynkr Atlas** (`https://atlas.zynkr.ai`, the `zynkr-atlas` MCP server) — the source of
>   truth: the published collection `kb`, one collection per section under it (`kb.<slug>`), the
>   cards filed in those. This skill writes **drafts only**; a person publishes them in Atlas's
>   審核. `/zynkr-support` and `/sales-inbound` read the published cards, never the mirror.
> - **Google Drive** `客服知識庫 (KMS) · Atlas 鏡像 · 僅團隊` (its ID is `mirror_folder_id` in `~/.config/zynkr/kms.json`; missing → stop and ask, never search for a folder by name) —
>   the **backup mirror**, readable by the workspace's members only: one Doc per section plus a
>   restore copy, `_KB-SNAPSHOT.json`. Rewritten from Atlas at the start of every run (Step 0).
>   Never authoritative, never read back into Atlas; a human edit made there is destroyed on the
>   next mirror. If the two disagree, Atlas is right.

## Configuration

This skill drafts into a **知識庫** it does not ship.

1. **Why it is withheld:** the cards are the company's own — its prices, policies and past
   answers — and they change every week, so a copy in this file would be out of date the day it
   shipped.
2. **The configure slot:** the `zynkr-atlas` MCP server, connected with an Atlas token of your
   workspace minted with 「可以建立草稿」, and that workspace's published collection `kb`. The Drive
   mirror (Step 0) takes a second token, minted with 「可以匯出知識（給鏡像用）」 alone, in
   `~/.config/zynkr/kb-mirror.env`, and a Drive folder of your own.
3. **What the 知識庫 must contain:** a published collection keyed `kb`; under it, one collection
   per section (`kb.<slug>`); in the sections, `fact` notes for the canonical numbers and policies
   and `reference` notes (one per resolved question) that cite the facts they rest on; and two
   style cards keyed `tone-voice-rules` and `term-mapping-table`.
4. **The Zynkr default:** the `kb` collection of Zynkr's own Atlas workspace and the members-only
   Drive folder `客服知識庫 (KMS) · Atlas 鏡像 · 僅團隊`. There is nothing to fill in beyond the two
   tokens.
5. **Not found:** if Atlas cannot be reached, the token reads no `kb` collection, or the walk in
   Step 3 cannot finish, draft nothing: go straight to Step 7, label only what Step 0's
   `pending_published` names, and report why. Never write to another knowledge base, the Drive
   copy or memory instead. A mirror that cannot run (no export token, a refusal) is reported, and
   the run goes on: the mirror is a backup. Steps 1–7 need only the manifest Step 0 downloads.
6. **Loaded at run time:** the skill reads it on every run; nothing from it is copied into this
   file.

---

## Resources you'll use (fixed facts — don't re-derive)

- **知識庫 access** — the **`zynkr-atlas` MCP server**. The tools you'll use:
  - `mcp__zynkr-atlas__list_knowledge` — the walk: the sections and every published card, by key,
    without text (Step 3)
  - `mcp__zynkr-atlas__search_knowledge` — dedupe by words
  - `mcp__zynkr-atlas__get_knowledge` — read one card, with its 「Part of」 and 「Cites」 lines
  - `mcp__zynkr-atlas__draft_note` — the only write: a NEW draft, filed under its section
    (`collection`) and linked to the published notes it cites (`cites`)
  - `mcp__zynkr-atlas__whoami` — the workspace's slug, for links
- **What this skill can never do over MCP** — edit, publish, archive or verify a published card,
  or touch a company fact (`company.*`). A change to a published card is a **correction packet**
  for Peter (Step 5c); publishing is his act in 審核.
- **Links** — a card: `https://atlas.zynkr.ai/w/<workspace-slug>/knowledge/<key>`; the 知識庫:
  `https://atlas.zynkr.ai/w/<workspace-slug>/knowledge`; 審核: `https://atlas.zynkr.ai/w/<workspace-slug>/review`.
  The slug is the one `whoami` names (Zynkr's is `zynkr`).
- **Google account**: `<your-google-workspace-account>` — **MCP server `google-workspace`** for all Gmail tools.
  Gmail is still where tickets live; only the 知識庫 moved.
- **Source labels** (nested — a query names each by its **search name**: the full path in lowercase,
  with every space, `/` and `&` turned into `-`; the quoted full path matches nothing):
  - Support: `[3] Operation/[3.8] Support` — `label:[3]-operation-[3.8]-support`
  - Inbound Sales: `[2] Sales & consultant/[2.1] Inbound Sales` —
    `label:[2]-sales---consultant-[2.1]-inbound-sales`
- **Ingest-ledger label**: `KMS-ingested` — applied once a thread's answer is **published** in the
  知識庫, to each message of Peter's (or a website form's) up to the answer learned (Step 7). The
  idempotency record: Step 1's searches leave out each message that carries it.
- **Drive mirror** (the backup half — full mechanics in `references/drive-mirror.md`):
  - Folder `客服知識庫 (KMS) · Atlas 鏡像 · 僅團隊` — `<mirror_folder_id>` from `~/.config/zynkr/kms.json`, members only
    (`references/drive-mirror.md` → *Who may read it*)
  - `scripts/kb-drive-mirror.mjs` (v2) — reads the `kb` collection through Atlas with the export
    token and renders it locally; never uploads. Card bodies stay on disk, out of context.
  - The working folder `~/.workspace-mcp/attachments/kb-mirror/` — the `google-workspace` MCP only
    uploads from under `~/.workspace-mcp/attachments/`. Every run first downloads Drive's
    `_MANIFEST.json` and `_KB-SNAPSHOT.json` into it (Step 0) and builds on those. Pass it as an
    absolute path.
  - `mcp__google-workspace__update_drive_file` — uploads a Doc in place by its ID
    (`source_format: "md"` converts Markdown → native Doc and **keeps the Doc ID**). It rewrites
    Google Docs, Sheets and Slides only, never a JSON file.
  - `mcp__google-workspace__create_drive_file` — writes the two JSON files as new files every run
    (`fileUrl: "file://…"`), and `update_drive_file` with `trashed: true` moves the pair they
    replace to Drive's bin. Their IDs therefore change every run: Step 0 finds them by name.
  - ⚠️ **The export token is a secret.** It lives in `~/.config/zynkr/kb-mirror.env`
    (`ATLAS_MCP_TOKEN=…`, `chmod 600`), minted by the owner with 「可以匯出知識（給鏡像用）」 and
    nothing else, renewed every 90 days. Never print it, paste it into chat, or put it on a
    command line; the script reads the file itself.
- **Companion files**:
  - `references/intent-taxonomy.md` — intent categories, aliases, and the intent → section map
  - `references/entry-schema.md` — the card shapes: what `draft_note` takes, the body and its
    footer, the correction packet
  - `references/new-section-playbook.md` — how a **new section** is drafted and published
  - `references/drive-mirror.md` — the Drive backup: arrow of truth, Doc-ID registry, how a run
    goes, how to verify it, and how to restore from the snapshot

---

## Step 0: Catch the Drive mirror up (every run)

Peter publishes drafts in Atlas between runs, so the mirror starts every run by catching up.
`/zynkr-kms mirror` (or "back up the KB", "sync the KB to Drive") is this step alone, in full.
How a run goes, the Doc registry and the checks: `references/drive-mirror.md`.

1. **Download Drive's pair** over the working folder's copies — every run, on every machine. Each
   run writes the pair as new files (point 5), so find it by name, never by an ID from an earlier
   run: `mcp__google-workspace__list_drive_items` on the folder
   (`<mirror_folder_id>`, `order_by: "createdTime desc"`), then the newest file named
   exactly `_MANIFEST.json` and the newest named exactly `_KB-SNAPSHOT.json`
   (`_KB-SNAPSHOT-CRM-<date>.json` is another file). Note their IDs, and the IDs of any older copy
   of either name, which a stopped run left behind: point 5 bins them all. Download the two with
   `mcp__google-workspace__get_drive_file_download_url`, then copy each saved file in. Drive's pair
   is the record; the local copies may be another machine's, or a stopped run's. If either name is
   missing or a download fails, stop and report it: Steps 1–7 read and write the manifest's
   `pending[]`.
2. **Render** —
   `node scripts/kb-drive-mirror.mjs --out <absolute path of ~/.workspace-mcp/attachments/kb-mirror>`
   (add `--full` for `/zynkr-kms mirror`). It reads Atlas with the export token, writes only the
   working folder, and decides by itself when a run must be full.
3. **Read its JSON summary**: `upload[]` names the files to upload; `pending_published` names the
   drafts that are published and still in `pending[]`, each with its Gmail `thread` (Step 7 labels
   those, then drops them); `removed`, `removed_sections` and `orphans` go to the report.
4. **Check who can read** — `mcp__google-workspace__get_drive_file_permissions` on the folder
   (`<mirror_folder_id>`), on each Doc before you write it, and on each JSON file
   once it is written (it is new, and takes the folder's readers): no `anyone` link, no domain
   grant, and every named reader a member of the Atlas workspace (ask when you cannot tell). The
   mirror copies team-only text; whatever reads wider gets nothing written — say so.
5. **Upload** every file in `upload[]`, in its order. **Stop at the first file that fails or is
   skipped** and upload nothing after it — never the two JSON files — so Drive's pair never claims
   a Doc it does not hold.
   - **A Doc** goes in place, found in the registry **by its section key** — never by the number in
     its file name — with `mcp__google-workspace__update_drive_file` (`file_path`,
     `source_format: "md"`, `name` = the entry's `doc_title`). A section with no Doc yet gets one
     with `mcp__google-workspace__import_to_google_doc`; add its ID to the registry. A key in
     `removed_sections` keeps its Doc: tell Peter, never delete it.
   - **The two JSON files** come last, `_KB-SNAPSHOT.json` then `_MANIFEST.json`, each as a NEW
     file, because `update_drive_file` cannot rewrite one: `mcp__google-workspace__create_drive_file`
     with `file_name` its name, `folder_id` the folder, `mime_type: "application/json"` (never
     converted to a Doc) and `fileUrl: "file://<its absolute path in the working folder>"`. Never
     pass `content`: the snapshot holds every card's text. Check each new file's readers (point 4);
     if one reads wider, stop and tell Peter.
   - **Once both are written,** move to the bin the pair point 1 downloaded and every older copy it
     noted: `mcp__google-workspace__update_drive_file` with that `file_id` and `trashed: true`. Bin
     nothing else: never a Doc, never `_KB-SNAPSHOT-CRM-<date>.json`. If either new file failed,
     bin nothing. The next run then takes the newest of each name, and a manifest and a snapshot
     from two runs make it full by itself.
6. **If it exits 1**, upload nothing, put the line it printed in the report and go on with Step 1
   (the queue).
   A refusal rewrote nothing; after a failed write, the next run's download replaces what it left.
   A line naming `ATLAS_MCP_TOKEN` means the env file is missing, malformed, expired or revoked —
   Peter mints a new token; never work around it.

---

## Step 1: Pull the *resolved, not-yet-ingested* queue

This is the **inverse** of `/zynkr-support`: the drafter handles threads Peter *hasn't* replied to;
this skill harvests threads he *has* replied to and that aren't ingested yet.

If Peter handed you a **specific thread** (pasted link or "learn from this one"), use just that —
skip the queue search.

Otherwise search both queues with `mcp__google-workspace__search_gmail_messages`, with
`page_size: 100`; while an answer names a `next_page_token`, call again with it as `page_token`.
Every search in this step pages the same way (one page is 10 messages by default):

```
(label:[3]-operation-[3.8]-support OR label:[2]-sales---consultant-[2.1]-inbound-sales) from:me -label:KMS-ingested newer_than:90d
```

Fallback for website-form sales inquiries answered as fresh emails (only if Peter asks you to sweep
website inquiries too):

```
from:website@zynkr.ai -label:KMS-ingested newer_than:90d
```

Dedupe by thread ID. Gmail keeps a label on each message, not on the thread, so
`-label:KMS-ingested` leaves out only the messages that carry it. A thread ingested before comes
back whenever a reply of Peter's in it carries no label (a later answer, or one an old run left
unlabelled): process it like any other, and Step 3's dedupe finds what the 知識庫 already holds,
so only a new answer is drafted.

A thread named in the working folder's `_MANIFEST.json` `pending[]` (its
`thread`) already has a draft — waiting in 審核, or published and not yet labelled (Step 7): list
it as such and do not re-process it. If nothing is left, tell Peter the 知識庫 is already up to
date and stop. Otherwise list what you found (subject · sender · queue) and say you're reviewing N
threads.

---

## Step 2: Confirm the thread is *learnable*, then extract

Call `mcp__google-workspace__get_gmail_thread_content` on each thread ID. A thread is **learnable
only if all three hold**:

1. The **last message is from Peter** (`<your-google-workspace-account>` / `<your-company-contact-email>` / any zynkr.ai sender) — i.e. he replied.
2. An **earlier inbound carried a real question** from the inquirer.
3. Peter's reply contains a **real answer** — concrete facts, not a holding reply.

> **`<your-company-contact-email>` is a company fact — read it from Atlas** (`get_knowledge`, key `company.contact-email`, on the `zynkr-atlas` MCP server; the value is the `value:` line). If Atlas cannot be reached, the key is missing, or there is no `value:` line, ask for it; never run with the blank still in it. `<your-google-workspace-account>` is your own account, not a fact.

**Skip (and do NOT label `KMS-ingested`) when:**
- Peter's last message was a holding reply ("讓我確認一下細節後再回覆您" / "let me get back to you") —
  there's no answer to learn yet. Leaving it un-labelled means it gets re-checked next run.
- The thread is spam / out-of-scope / a thank-you with no Q&A content.

**Done — label it, draft nothing,** when the thread comes back with nothing new: every answer in
it is already in the 知識庫 (Step 3's dedupe finds each one), and all that follows the last of them
is a thank-you or a closing line. Step 7 labels it, so it stops coming back until Peter answers
something new in it. A holding reply is never this: it stays unlabelled (above).

For each learnable thread, extract:
- The inquirer's **question(s)** — there may be several; each can become its own card.
- Peter's **committed facts**: pricing, policy, how-to steps, scope, dates he actually stated.
- **Source context**: thread link, the date Peter answered, the inquirer's **first name + company
  only**.

**Guardrails while extracting:**
- **Never invent or "improve" facts.** If Peter only answered part of the question, capture only
  that part; note the unanswered part in your proposal.
- **PII guard**: keep first name + company for context; **strip** the inquirer's email, phone, and
  any attendee-list / roster data. None of it reaches the 知識庫.

---

## Step 3: Apply the three lenses → draft a proposed card

**Once per run, before the first thread, walk the 知識庫's keys:**
`mcp__zynkr-atlas__list_knowledge(collection: "kb", max_chars: 60000)`. While `truncated` is
true, call it again with `after` set to `next_after` (same collection and budget). Every key the
pages list is **the set**: the sections (kind `collection`, filed under `kb`) and their cards, each
with its title, the section it is filed in and the keys it cites. The sections in the set are the
live vocabulary; `references/intent-taxonomy.md` says what each covers. If a page fails or an answer
arrives cut off (no `truncated` at its end), the set is unknown: draft nothing this run
(Configuration, point 5).

For each question you extracted:

### Lens 1 — Intent taxonomy
Classify into the best-fit section from `references/intent-taxonomy.md` (`kb.pricing-quoting`,
`kb.course-content`, `kb.scheduling-logistics`, `kb.team-training-enterprise`,
`kb.technical-howto`, `kb.access-account`, `kb.refund-policy`, `kb.instructor-profile`,
`kb.brand-product-vision`, `kb.ai-workflow-architecture`, …). If nothing fits well, **propose a
new section** — flag it for Peter; never silently invent one or dump it in `kb.other` without
saying so.

> **Style rules are not Q&A.** When Peter gives a **tone / wording / term** rule (e.g.
> `parachute`→「和團隊諮詢、觀察流程」, `discovery call`→「線上會議」), it belongs on a style card
> in `kb.tone-style`: a new row in the 用語對照表 is a **correction packet** for
> `term-mapping-table` (read it with `get_knowledge(key: "term-mapping-table", max_chars: 60000)`
> and quote the rows around where the new one goes). A broader voice rule is a packet for
> `tone-voice-rules`.

### Lens 2 — Where it goes (which section, new card or a change)
- Map the intent → its section key (`kb.<slug>`), one that is in the set.
- **Dedupe**, three ways:
  1. `mcp__zynkr-atlas__search_knowledge` with the question's key terms — one or two words a call,
     zh and EN apart (the search matches every word of a query literally). Keep only hits whose
     key is in the set.
  2. The set's titles in that section.
  3. `pending[]` in the working folder's `_MANIFEST.json` — the drafts this skill filed, which
     `list_knowledge` lists only once they are published.

  A near-duplicate **published** card that says the same → the answer is already there; nothing
  to draft. One that says otherwise → a **correction packet** for it (Step 5c), never a second
  card — **unless Peter's reply is older than the card's last update** (the dates the set lists):
  the card may have moved past it, so ask Peter which is current (⚠ in Step 4) and draft no
  packet that could put an old value back. A near-duplicate in **`pending[]`** → nothing new; say
  it is waiting, or published if the set lists it. This matters most for
  `kb.pricing-quoting` and `kb.refund-policy`, where stale answers are harmful.

### Lens 3 — Structure for the LLM (fact card vs. citing reference card)
The 知識庫 has **two kinds of card** (full spec in `references/entry-schema.md`):

- **`fact` card** — canonical, reusable truths whose *numbers/terms live once*: the pricing table,
  refund policy, standard durations. Its key is a stable kebab-case id (e.g. `pricing-rates`),
  never one starting `company.`.
- **`reference` card** — maps one inquiry to the facts and **cites** them (`cites`, by key) rather
  than restating the numbers. Its key is `qa.<english-slug>`.

**Decide which you're drafting.** If the answer rests on a fact that could appear in other answers
or changes over time (price, rate, policy, lead time):
1. Is there already a published fact for it? Check with `get_knowledge(key: "<fact-key>")` and the
   set. → the reference card just lists it in `cites` and describes the *mapping/logic*, **no
   restated numbers**.
2. No fact yet? → propose a **NEW fact draft** (the numbers go there). The reference card that
   cites it **waits for the next run**: a draft can cite only published notes, so it is drafted
   once Peter has published the fact.
3. The fact exists but Peter's reply changes it (new rate)? → a **correction packet** for the fact
   — one edit in Atlas, and every citing card is current.

Draft each proposed card with these fields (they map 1:1 onto `draft_note`):

```
kind:        fact | reference
key:         fact → stable kebab-case id (e.g. pricing-rates) · reference → qa.<english-slug>
title:       fact → short human title (e.g. 授課費率表)
             reference → the canonical, normalized question (e.g. 一天 N 小時的 AI 課程如何報價？)
body:        fact → the canonical numbers/terms (table/bullets), incl. explicit 未定範圍 caveats
             reference → the mapping/logic ("依 FACT:pricing-rates …"), NOT the restated numbers
             then `---` and the footer: Keywords · source_type (references/entry-schema.md)
collection:  the section key, e.g. kb.pricing-quoting (facts: kb.core-facts)
cites:       the published keys the answer rests on (a company fact by key, never its value)
```

Only inline a hard number in a reference card when it is specific to this ticket and lives in
**no** fact (then preserve it verbatim).

---

## Step 4: Propose, then wait for approval (the write gate)

Present **one table** of everything you intend to do — nothing is drafted yet:

```
Proposed 知識庫 changes from N resolved threads:

| # | Action            | Section            | Key              | Preview                        | Flag             |
|---|-------------------|--------------------|------------------|--------------------------------|------------------|
| 1 | CORRECTION packet | kb.core-facts      | pricing-rates    | 實體 rate → new line           | ⚠ pricing change |
| 2 | NEW reference     | kb.pricing-quoting | qa.half-day-quote | Q: … · cites pricing-rates    | —                |
| 3 | NEW fact          | kb.core-facts      | refund-window    | (canonical fact)               | ⚠ new fact       |
| 4 | HELD reference    | kb.refund-policy   | qa.refund-window | waits for refund-window        | next run         |
| 5 | NEW SECTION       | kb (new)           | kb.logistics-overseas | collection draft          | ⚠ new category   |
```

Then show the **full card** for each proposed draft, and the **full packet** for each correction,
below the table.

**Always flag for explicit confirmation:**
- ⚠ **Pricing / policy change** — "this replaces the older answer on the published card; confirm
  the current rate before you apply it."
- ⚠ **New section** — proposing a category that doesn't exist yet.
- ⚠ **Older than the card** — Peter's reply predates the card's last update and disagrees with
  it: which is current? (Lens 2). No packet until he says.
- ⚠ **Ambiguous intent** or **partial answer**.

Peter approves all / edits / rejects per row. **Only approved rows proceed to Step 5.** If he
rejects a thread entirely, do not label it ingested (Step 7).

---

## Step 5: Draft the approved cards in Atlas

**Order matters:** a new section first (5d), then fact drafts (5a), then the reference drafts whose
`cites` are all published (5b). A draft is filed only under a **published** collection and cites
only **published** notes, so a card whose section or fact is itself a draft this run is held for
the next one.

### 5a / 5b — a NEW fact or reference card
`mcp__zynkr-atlas__draft_note` with `key`, `kind` (`fact` or `reference`), `title`, `body` (text,
`---`, the footer), `collection` (the section key) and `cites` (published keys only).

The answer starts 「Drafted note `<key>`」 and says what it is filed under and what it cites —
compare it with what you asked (a draft cannot be read back with `get_knowledge`, which serves
published notes only). Then record it, at once:

```
node scripts/kb-drive-mirror.mjs pending-add --out <the working folder> --key <key> --collection <section key> --title "<title>" --thread <gmail thread id>
```

If it exits 1 (no manifest in the working folder, or one it could not write), say so in the
report: the draft is in 審核, but the next run cannot see it waiting. A v1 manifest, from before
the first v2 run, takes the entry like a v2 one.

**When draft_note refuses**, nothing was written; never work around it:
- `key_taken` — a note already holds the key: a card dedupe missed, or a draft or archived note.
  Stop that row and report it; never retry under another key unasked.
- `collection_not_found` — the section is not published (a draft section, or a typo): hold the card.
- `cite_not_found` — a cited key is not a published note: hold the card, name the key.
- `daily_cap` — this token's 20 drafts for today are spent: stop drafting, report the rows left.
- `not_permitted` — the token cannot draft (minted without 「可以建立草稿」, or its holder can no
  longer write): stop and tell Peter.
- `fact_key` — never draft a `company.` key: company facts are the owner's, in the app.

### 5c — a change to a published card: the correction packet
This skill never edits a published card. Each approved change goes to Peter as a packet he applies
by hand in Atlas (format in `references/entry-schema.md`):

```
Correction · `<key>` — <title>
Link:     https://atlas.zynkr.ai/w/<workspace-slug>/knowledge/<key>
Old:      <the line(s) as the card reads now, quoted from get_knowledge>
New:      <the line(s) as they should read>
Evidence: <Gmail thread permalink> · <YYYY-MM-DD> · Peter: 「<his words>」
⚠ price / policy change — confirm before applying     (only when it is one)
```

**Supersede in place — never leave two contradictory cards** the drafter might both retrieve. The
thread stays un-labelled, so the next run checks the card again: once it reads the packet's new
line, the packet is **applied** — label the thread (Step 7) and say so in the report.

### 5d — a NEW SECTION (the intent has no section yet)
Follow `references/new-section-playbook.md`: `draft_note` with `key: "kb.<slug>"`, `kind:
"collection"`, `collection: "kb"`, the section's title and its body (what it covers, then
`Aliases: …`). Its cards wait until Peter publishes it. Record it with `pending-add` like a card.

---

## Step 6: Upload the manifest

`pending-add` changed the working folder's `_MANIFEST.json`, so write it to Drive as a new file, as
in Step 0.5 (`create_drive_file`, `mime_type: "application/json"`, its readers checked). Then bin
the `_MANIFEST.json` it replaces, the newest one Drive held before it: the one Step 0.5 wrote, or
Step 0.1's if Step 0.5 wrote none. Drive's copy of `pending[]` is then current. Write it even when
Step 0's upload stopped part-way: the next run sees a manifest and a snapshot from different runs
(the first time, a v1 snapshot) and renders every Doc again. If the write fails, bin nothing and
name the new drafts' keys in the report: the next run cannot see them in `pending[]`. Nothing else
in the mirror changes until Peter publishes — the next run's Step 0 picks that up.

---

## Step 7: Mark ingested + report

Label `KMS-ingested` **only a thread whose answer is published** in the 知識庫:
- its answer was already there (dedupe found it; nothing drafted), including a thread that came
  back with nothing after its answer but a thank-you or a closing line (Step 2);
- its drafts are published: every `pending[]` entry for the thread is in Step 0's
  `pending_published`;
- its correction packet was applied (the card now reads the new line).

Do **not** label a thread with a draft still waiting, a held card, an open packet, or one that was
skipped or rejected.

- Resolve the ledger label's **ID**: `mcp__google-workspace__list_gmail_labels` and find
  `KMS-ingested`. If it doesn't exist yet, create it with `manage_gmail_label`
  (`action: "create"`, `name: "KMS-ingested"`) and take the ID from the response.
- **Choose the messages from the thread itself**, never from Step 1's search: read it with
  `get_gmail_thread_content` (the copy Step 2 read, or read it now for a thread from `pending[]`)
  and take each message from Peter or from `website@zynkr.ai` — what Step 1's searches match —
  dated no later than **the answer learned**: for a thread published from `pending[]`, the newest
  `drafted_at` among its entries in the working folder's `_MANIFEST.json` (a UTC time); otherwise
  the newest message Step 2 read. A later message stays unlabelled: no run has read its answer
  yet, and the next one learns from it.
- Find each chosen message's ID with `search_gmail_messages` and
  `rfc822msgid:<its Message-ID line, without the angle brackets>`.
- Apply the label with `mcp__google-workspace__batch_modify_gmail_message_labels`: those IDs as
  `message_ids`, the label **ID** (not the name) in `add_label_ids`. **Never the thread ID in
  their place:** it is the ID of the thread's first message alone, so only that message gets the
  label and Peter's reply still matches Step 1's search (three June threads were labelled that
  way).
- Then take out of `pending[]` each published key whose thread you labelled, and each one with no
  `thread`: `node scripts/kb-drive-mirror.mjs pending-drop --out <the working folder> --key <key>`.
  Write the manifest again, as in Step 6. A key whose thread you could not label stays, and the
  next run names it again.

Then give Peter a single summary:

```
知識庫 — N drafts from M threads, waiting in 審核:

✅ Drafted (X):
  - [kb.section] `key` — Q: … — [sender / company]
✏️  Correction packets (Y):
  - `key` — what changes (⚠ price / policy) — link
🆕 New section drafts (Z):
  - `kb.<slug>` — title (publish it before its cards can be drafted)
⏸️  Held for the next run (H):
  - `key` — waits for `<key>` to be published
✔️  Published and labelled (P):
  - `key` — thread labelled KMS-ingested, dropped from pending[]
⏭️  Skipped (W):
  - [Subject] — [reason: holding reply / no answer yet / out of scope / still waiting in 審核]
💾 Drive mirror: <full | incremental> — S Docs uploaded · <sections> sections · <orphans> orphans · <pending> pending
   (or the line it stopped on)
⚠️  For your attention:
  - [anything you want Peter to double-check]

Review: https://atlas.zynkr.ai/w/<workspace-slug>/review
知識庫: https://atlas.zynkr.ai/w/<workspace-slug>/knowledge
Backup: https://drive.google.com/drive/folders/<mirror_folder_id>
```

If a new section was drafted, add its row to `references/intent-taxonomy.md` (a workbench change)
once Peter has published it.

---

## Things to be careful about

- **Extraction, not generation.** Every fact in the 知識庫 must trace to something Peter wrote.
  Holding replies teach nothing — skip them.
- **One source of truth: Atlas.** Drive is a *backup*, not a second 知識庫. Never author a card in
  Drive, never cite the mirror as current, and never read a Drive edit back into Atlas. If the two
  disagree, Atlas is right and the mirror is stale.
- **Drafts only.** This skill never edits, publishes, archives or verifies a card. A change to a
  published card is a correction packet; the rest is Peter's in Atlas.
- **Canonical numbers live once.** Pricing/policy/rates go in a `fact` card; reference cards
  **cite** it. A change is made in one place rather than chased across cards.
- **A card cites only published notes.** Draft the fact, hold the card that cites it until the fact
  is published.
- **Stop on `key_taken`.** It means a note already holds that key — find out which, never invent a
  second key to get past it.
- **Never draft a company fact.** `company.*` keys are the owner's, in the app; a card that rests on
  one cites it by key and never copies its value.
- **The export token never leaves its file.** Not in chat, not in a command line, not in a report.
- **PII never lands in the 知識庫** — first name + company only.
- **Idempotency is the label, plus `pending[]`.** A message carrying `KMS-ingested` is never
  harvested again, so Step 7 labels each of Peter's messages up to the answer learned — found by
  its Message-ID, never by the thread ID — and leaves a later one for the next run; a thread named
  in `pending[]` is skipped until Step 7 labels it and drops its keys. A skipped thread stays
  un-labelled so it's reconsidered once truly answered. A thread that comes back with a newer
  answer, or one Peter hands you, goes through Step 3's dedupe, so only what is new is drafted;
  one that comes back with nothing after its answer but a thank-you or a closing line is done, and
  labelled (Step 2).
- **zh-TW default**, bilingual keywords — match how Peter and his inquirers actually search.
- **A draft is not approval.** The gates are Peter's approval in Step 4 and his publish in Atlas.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
