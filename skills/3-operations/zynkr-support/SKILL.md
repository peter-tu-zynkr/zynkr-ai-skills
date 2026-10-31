---
name: zynkr-support
sheetId: "3.01"
description: "The READ half of Peter's support loop (formerly support-reply-drafter). Parses Peter's Gmail support queue and the website-form notifications that are not AI-consulting inquiries, detects unreplied inquiries, identifies each inquirer's intent, and matches it against the **知識庫 in Zynkr Atlas** (the published `kb` collection — the single source of truth — read through the `zynkr-atlas` MCP server's search_knowledge / get_knowledge) to draft a safe reply on the thread. Drafts match the inbound language (zh-TW or EN). When the KB has no confident answer, or Atlas cannot be reached, it does NOT guess — it leaves a holding reply with an inline `[[NEEDS PETER: ...]]` block flagging exactly what's missing and notifies Peter. Once Peter supplies the real answer, this skill hands the resolved thread off to /zynkr-kms, which drafts it into the 知識庫 for Peter to publish, so the next identical question resolves automatically. Trigger whenever Peter says '/zynkr-support', 'draft support replies', 'process support inbox', '回覆 support 信箱', '清 support queue', '幫我回 support 信', or otherwise asks to handle the support inbox. The [2.1] Inbound Sales label and the website's AI 顧問服務 inquiries belong to /sales-inbound, which logs the lead and drafts the first reply; this skill lists them and drafts nothing on them."
category: operations
project: zynkr-support
platform: claude
status: WIP
visibility: public
author: Peter Tu
input: "Unreplied Support threads and website-form notifications in Gmail (the Inbound-Sales label is /sales-inbound's); answers come from the Atlas 知識庫 (kb), via the zynkr-atlas MCP"
process: "Pull the unreplied queue → read each thread: language, intent → list the 知識庫's keys once → search + get the cards, their cited facts, the tone-style cards → a proper reply, or a holding reply + [[NEEDS PETER]] → once Peter answers, hand off to /zynkr-kms"
output: "One Gmail draft per thread; a summary (drafted / needs Peter / skipped); for threads Peter has since answered, trigger the /zynkr-kms hand-off"
synergy: ["zynkr-kms"]
reads: ["kb", "tone-voice-rules", "term-mapping-table", "company.contact-email"]
house-style: bound

---

# Zynkr Support — Support Reply Drafter (READ side, Atlas 知識庫 backed)

Peter runs a small support inbox. The job here is to clear it: read each
unreplied thread, **work out what the inquirer actually wants, find the answer in the knowledge
base, and leave a draft Peter only needs to skim and send.**

This skill is the **READ** half of a two-skill loop:

- **/zynkr-support (this skill)** — reads the KB, drafts replies, and flags gaps it can't answer.
- **/zynkr-kms** — after Peter answers a gap, learns that answer and writes it back into the KB.

So the loop is self-healing: every gap this skill flags becomes a KB card via /zynkr-kms, and the
next identical question gets a confident auto-draft. The two skills share **one** knowledge base:
the **知識庫 in Zynkr Atlas** — the published collection `kb`, one collection per section under
it, read here through the `zynkr-atlas` MCP server. The Google Drive copy
(`[3.2] 客服知識庫 (KMS)`) is a one-way backup mirror that /zynkr-kms writes from Atlas — never
read it for answers.

The drafts must be **safe to send** — never invent product behavior, pricing, dates, or
commitments. When the KB doesn't cover something, say so and surface it rather than guessing.
**Price and quote questions are the highest-risk category**: unless an exact rate/quote is in the KB
*or* Peter supplied it in the current conversation, treat any pricing ask as low-confidence and
write a holding reply with a `[[NEEDS PETER]]` block.

---

## Configuration

This skill answers from a **知識庫** it does not ship.

1. **Why it is withheld:** the cards are the company's own — its prices, policies and past
   answers — and they change every week, so a copy in this file would be out of date the day it
   shipped.
2. **The configure slot:** the `zynkr-atlas` MCP server, connected with an Atlas token of your
   workspace, and that workspace's published collection `kb`.
3. **What the 知識庫 must contain:** a published collection keyed `kb`; under it, one collection
   per section (`kb.<slug>`); in the sections, `fact` notes for the canonical numbers and policies
   and `reference` notes (one per resolved question) that cite the facts they rest on; and two
   style cards keyed `tone-voice-rules` and `term-mapping-table`.
4. **The Zynkr default:** the `kb` collection of Zynkr's own Atlas workspace. There is nothing to
   fill in: a token of that workspace is the whole setup.
5. **Not found:** if Atlas cannot be reached, the token reads no `kb` collection, or the walk in
   Step 4 cannot finish, every reply is a holding reply with a `[[NEEDS PETER]]` block and the
   report says why. A missing style card is named in the report, and drafts follow the house
   voice alone. Never fall back to another knowledge base, the Drive copy or memory.
6. **Loaded at run time:** the skill reads it on every run; nothing from it is copied into this
   file.

---

## The 9-step scope (what this skill is, end to end)

1. **Parse mail** — pull the unreplied Support / website-form queue (the Inbound-Sales label and AI 顧問服務 inquiries are /sales-inbound's).
2. **Detect the unanswered inquiry** — the thread's last message is from the inquirer, not Peter.
3. **Identify the inquirer's intent** — walk the 知識庫 once, then classify against its sections.
4. **Match intent → find the answer** — `search_knowledge` + `get_knowledge`, then the facts each card cites.
5. **Write the reply** as a Gmail draft *if* a confident answer exists.
6. **Notify Peter** when no answer is found — holding reply + inline `[[NEEDS PETER]]` block.
7. **Peter supplies the missing context + answer** (replies to the customer / tells the skill).
8. **Hand the resolved thread off to /zynkr-kms.**
9. **/zynkr-kms drafts the new answer into the KB**, Peter publishes it, and next time /zynkr-support finds it itself.

Steps 1–6 are this run. Steps 7–9 are the learning loop (see **Step 9** below).

---

## Resources you'll use

- **Gmail labels** (both nested — use the **full path** in queries):
  - Support: `[3] Operation/[3.8] Support` (ID `Label_1343405731176716360`)
  - Inbound Sales: `[2] Sales & consultant/[2.1] Inbound Sales` (ID `Label_1203655627141795093`) — /sales-inbound's queue; listed, never drafted on here
- **Website form sender**: `website@zynkr.ai` — discovery-call / contact-form inquiries arrive as
  notifications *from* this address. Fallback queue source (see Step 1).
- **KB access** — the **`zynkr-atlas` MCP server** (Zynkr Atlas, read with a token of your
  workspace). It serves published notes only; a draft is never served. Read-side tools:
  - `mcp__zynkr-atlas__list_knowledge` — the published notes filed under a collection, by key,
    without their text; one page per call (`next_after`, `truncated`)
  - `mcp__zynkr-atlas__search_knowledge` — keyword search over the workspace's published notes:
    every word of the query must appear, matched literally
  - `mcp__zynkr-atlas__get_knowledge` — one note by key: its text, its dates, and the 「Part of」
    (its section) and 「Cites」 (the notes it rests on) lines
  - `mcp__zynkr-atlas__whoami` — the workspace's slug, for links
- **KB links** (for your summary): `https://atlas.zynkr.ai/w/<workspace>/knowledge/<key>`, where
  `<workspace>` is the slug `whoami` names (Zynkr's is `zynkr`); the 知識庫 itself is
  `…/knowledge/kb`.
- **Google account**: `<your-google-workspace-account>` — **MCP server `google-workspace`** for all Gmail tools.

### KB structure (what you're retrieving from)

The walk in Step 4 lists all of it:

- **`kb`** is the 知識庫 itself, and each **section** is a collection under it, keyed `kb.<slug>`
  (`kb.pricing-quoting`, `kb.core-facts`, `kb.tone-style`, …). Every card is filed in one
  section. A section's own note (`get_knowledge(key: "kb.<slug>")`) holds its description and an
  `Aliases:` line.
- **`fact` cards** (kind `fact`) — canonical numbers/policies (pricing table, refund policy,
  durations), each keyed by a stable id (e.g. `pricing-rates`). The numbers live here, once.
- **qa cards** (kind `reference`, keys `qa.…`) — one per past resolved inquiry; the body carries
  the *logic*, and its 「Cites」 line names the fact(s) it rests on. **The numbers are in the
  cited facts, not in the qa card**: read each cited key with `get_knowledge`.
- **A card's footer**, under its text after a `---` line: `Keywords:` (its search words),
  `source_type:` (where it came from), and sometimes `Flags:` or `Unverify note:`. The footer is
  never reply material.
- **`kb.tone-style`** holds the two ALWAYS-READ style cards, `tone-voice-rules` and
  `term-mapping-table` (the anti-Chinglish 晶晶體 用語對照表): read both by key once per run
  (Step 5); every draft must follow them.

> **Label gotcha (learned the hard way):** the Gmail labels are *nested*, so the leaf name alone
> (`label:"[3.8] Support"`) matches **nothing** — use the full path
> (`label:"[3] Operation/[3.8] Support"`). The labels also may not be reliably applied yet (no
> filter set up), so a label search returning zero does **not** mean the queue is empty. Always run
> the sender fallback in Step 1 before declaring the queue clear.

---

## Step 1 — Parse mail: pull the unreplied queue

Run these searches with `mcp__google-workspace__search_gmail_messages` and union the results
(dedupe by thread ID):

```
label:"[3] Operation/[3.8] Support" -from:me
```

Then the **sender fallback** (the label isn't reliably applied), scoped to recent website forms and
leaving out the AI-consulting inquiries:

```
from:website@zynkr.ai -from:me newer_than:14d -"Interest: AI 顧問服務"
```

**One owner per inbox.** The `[2.1] Inbound Sales` label and every `Interest: AI 顧問服務` inquiry
belong to **/sales-inbound**, which logs the lead and drafts the first reply. Never draft on them
here: two drafts on one thread is what this rule prevents. If one turns up anyway (a label on the
wrong thread), list it under *Owned by /sales-inbound* in the report.

**Only declare the queue empty if both return zero.** If the label search is empty but the
fallback found threads, tell Peter at the end that auto-labeling isn't set up (he likely needs a
Gmail filter). Otherwise list what you found — subject, sender, snippet, queue — and say you're
processing N threads.

---

## Step 2 — Detect the unanswered inquiry

Call `mcp__google-workspace__get_gmail_thread_content` on each thread ID:

- **Last message from Peter** (<your-google-workspace-account> / <your-company-contact-email> / any zynkr.ai sender) → he already replied. Skip;
  don't duplicate a draft.
- **Last message from the inquirer** → this thread needs a draft. Continue.

> **`<your-company-contact-email>` is a company fact — read it from Atlas** (`get_knowledge`, key `company.contact-email`, on the `zynkr-atlas` MCP server; the value is the `value:` line). If Atlas cannot be reached, the key is missing, or there is no `value:` line, ask for it; never run with the blank still in it. `<your-google-workspace-account>` is your own account, not a fact.

### Website-form notifications (special case)

Threads **from `website@zynkr.ai`** are *not* real conversations — they're a form-submission
notification to Peter's own inbox. Body looks like:

```
New discovery call inquiry
Name: 王小明
Email: inquirer@example.com
Company: ...
Interest: 團隊訓練
Source page: consult
Brief context: <the actual question>
```

For these:
- The **real inquirer email is the `Email:` line in the body**, NOT the `From:`. Parse it out.
- Use `Name:` / `Company:` / `Interest:` / `Brief context:` as the question content.
- **Do not reply in-thread** — that just emails `website@zynkr.ai`. These get a **fresh email to
  the customer** (Step 7).
- Check if already handled: search sent/drafts to that customer (`to:<email> from:me`). If a reply
  or draft exists, skip and list as already-handled.

> An `Interest: AI 顧問服務` inquiry is **/sales-inbound**'s: it logs the lead and drafts the first
> reply, so this skill leaves it alone (the Step 1 fallback query already excludes it). Website
> forms with any other interest (e.g. 團隊訓練) stay here.

For each thread needing a draft, extract: sender name + email · subject · the inquirer's actual
question(s) (there may be several) · inbound language (Step 3).

---

## Step 3 — Detect the inbound language

From the latest inbound message body:
- More than ~30% CJK (Han) characters → draft in **Traditional Chinese (zh-TW)**.
- Otherwise → **English**.

If bilingual/ambiguous, default to the language of the opening greeting ("Hi" → EN, "你好" → zh-TW),
and match the language of the inquirer's **most recent** message.

---

## Step 4 — Walk the 知識庫, then identify the intent

**Once per run, before the first thread, walk the 知識庫's keys:**
`mcp__zynkr-atlas__list_knowledge(collection: "kb", max_chars: 60000)`. While `truncated` is
true, call it again with `after` set to `next_after` (same collection and budget). Every key the
pages list is **the set**: the 知識庫's sections (kind `collection`) and its cards. Only a note in
the set, or a company fact that a card in it cites, may be quoted in a reply.

If a page fails, Atlas cannot be reached, or an answer arrives cut off (no `truncated` at its
end), the set is unknown: **quote nothing this run**. Every thread gets a holding reply (Step 6),
and the report says the walk failed. Never fall back to the CRM, the Drive copy or memory. If a
page says `depth_limited`, the cards it could not list are outside the set; name that in the
report.

Then, for each question the inquirer asked, classify it into **exactly one section**: one of the
set's `collection` rows, by key and title. Pick the **most specific** fit, and judge by what the
*answer* would be (when the fit is unclear, read the section's note for its aliases):

- "How much for in-house team training?" → `kb.pricing-quoting` if the answer is a rate;
  `kb.team-training-enterprise` if the answer is program scope.
- One thread can yield **multiple** intents (e.g. a pricing Q + a scheduling Q) — split them; each
  gets its own retrieval pass.
- If nothing fits, tag `kb.other` — but flag it in the summary so /zynkr-kms can consider a new section.

---

## Step 5 — Match intent → find the answer in the KB (search-then-fetch)

Retrieval is **search-first**, cheap, and repeatable — run it per question:

1. **Once per run**: read the two ALWAYS-READ style cards by key —
   `mcp__zynkr-atlas__get_knowledge(key: "tone-voice-rules")` and
   `mcp__zynkr-atlas__get_knowledge(key: "term-mapping-table", max_chars: 60000)` (the table is
   long). Every draft follows their voice rules and the 用語對照表 term mappings (they kill
   晶晶體 Chinglish).
2. **Search**: `mcp__zynkr-atlas__search_knowledge` with **one or two words** from the question —
   nouns and product-specific words. Every word of a query must appear in a card, so keep zh and
   EN in separate queries (`報價`, then `price`) and skip filler ("how", "請問", "可以"). Broaden
   by dropping a word or trying a synonym if the first pass is thin. **Drop every hit whose key is
   not in the set:** Atlas holds more than the 知識庫.
3. **Fetch**: `mcp__zynkr-atlas__get_knowledge` on the best 1–3 hits, then follow each card's
   「Cites」 line: read every cited key with `get_knowledge`. For a qa card, that is where the
   numbers are. A cited `company.…` fact gives its value on its `value:` line. A fact card hit
   gives you the canonical numbers directly.
4. **Weak or ambiguous results → browse the section**: scan the set's rows filed in the intent's
   section (`part_of` = its key) by title for the closest question, then fetch it. If the intent
   was ambiguous, re-classify and try the other section the same way.

**The KB is the only source of truth.** Don't pad answers with generic "best practice" advice that
isn't in the KB — Peter wants drafts that sound like *him*, not a generic support bot.

---

## Step 6 — Decide confidence, then draft / notify

Ask: *Does the KB answer each question the inquirer asked?*

> **Pricing supplied in conversation:** if the KB has no rate but **Peter gave the exact
> pricing/quote in the current conversation**, treat that as authoritative and draft the real
> quote. Still add a light `[[NEEDS PETER]]` note for anything you had to *infer* (currency, whether
> in-person includes travel/venue/materials, validity period).

### High confidence (KB covers it, or Peter supplied it in-conversation) → write the reply

1. **Greeting** — inquirer's first name if available; match language.
2. **Acknowledge** the question (one short sentence).
3. **Answer** — facts pulled straight from the retrieved cards, paraphrased into a natural reply
   (don't copy headings or bullet markup; resolve cited fact numbers into plain prose).
4. **Offer follow-up** — short closing line.
5. **Sign-off** — `Peter` (Peter signs in English even on zh-TW replies).

Tone: friendly + professional, per the `tone-voice-rules` card; apply every `term-mapping-table`
row (e.g. never "discovery call" in zh-TW — 「線上會議」). Contractions OK in EN. zh-TW: 您 for
first-time inquirers, 你 only if already on first-name terms. Avoid corporate jargon ("we strive
to", "as per our policy").

### Low confidence (KB missing / only partial / walk failed) → holding reply + notify Peter

This is also every thread's reply when the walk in Step 4 failed or Atlas cannot be reached: the
`[[NEEDS PETER]]` block then says so instead of listing searches.

The reply must be sendable as-is if Peter approves, but Peter must see what's missing. Structure:

1. Greeting + acknowledge.
2. Honest line: "Let me get back to you on this with the right details" (EN) /
   "讓我確認一下細節後再回覆您" (zh-TW).
3. Sign-off.

Then **prepend the body with a `[[NEEDS PETER: ...]]` block** listing: the question(s) the KB didn't
answer · which sections you checked + terms you searched · a clearly-marked guess if you have
one · "Delete this block before sending."

```
[[NEEDS PETER:
- Inquirer asked whether the course platform supports SSO login for their team — searched
  「SSO」, 「單一登入」, then "SAML"; checked kb.access-account + kb.technical-howto, no card
  covers it
- Guess: route to a sales conversation, not self-serve
- Delete this block before sending
]]

Hi Sharon,

Thanks for reaching out about SSO setup. Let me confirm a few details on our end and I'll get back
to you within the next day or two with specifics.

Best,
Peter
```

---

## Step 7 — Create the draft in Gmail

**Normal threads (a real Support conversation):**
`mcp__google-workspace__draft_gmail_message` with:
- `to`: the original sender's email
- `subject`: prefix the original with `Re: ` (unless it already starts with `Re:`)
- `body`: your draft (with the `[[NEEDS PETER]]` block on top if low-confidence)
- `thread_id`: the thread ID — **critical**; it makes the draft a reply inside the thread.

**Website-form notifications (from `website@zynkr.ai`):**
`mcp__google-workspace__draft_gmail_message` with:
- `to`: the **customer email parsed from the body** (`Email:` line) — never `website@zynkr.ai`
- `subject`: a clean customer-facing subject (e.g. `AI 課程報價｜團隊訓練（Zynkr）`)
- `body`: your draft
- **Do NOT set `thread_id`** — fresh outbound email to the customer.

**Both kinds:** also pass `body_format="html"` and `include_signature=true`, with the draft
converted mechanically from plain text (escape `&` `<` `>`, every line break → `<br>`, wrap it in
`<div dir="ltr">…</div>`, nothing else). That puts Peter's Gmail signature card under the
sign-off, as on his own sent mail. The signature is HTML, so a plain-text draft flattens it into
one line or loses it (`SKB-085`, 2026-10-19). The `[[NEEDS PETER]]` block converts the same way.

If `draft_gmail_message` errors, fall back to `draft_email` (alternate Gmail MCP) only if
`google-workspace` is unavailable. That fallback carries no signature, so say so in the report.

---

## Step 8 — Report back to Peter

```
Processed N threads (Support + website forms):

✅ Drafted with confident answer (M):
  - [Subject] — [sender] — [queue] — [intent → cards used]

⚠️  Drafted holding reply, NEEDS PETER (K):
  - [Subject] — [sender] — [queue] — [one-line: what's missing]

⏭️  Skipped (already replied / handled / spam) (J):
  - [Subject] — [sender] — [reason]

➡️  Owned by /sales-inbound, not drafted (L):
  - [Subject] — [sender] — [Inbound Sales label | AI 顧問服務 inquiry]
```

Link each card used as `https://atlas.zynkr.ai/w/<workspace>/knowledge/<key>` (Resources). If
the walk failed or Atlas could not be reached, say so on the first line, before the counts.

If everything was confident with no NEEDS PETER items, just say so plainly. Also surface when
relevant: **labels not applied** (label searches empty, fallback found threads → suggest a Gmail
filter); **sales leads** (a website form under another interest that reads like a consulting lead → mention /sales-inbound).

**Crucially, list the `⚠️ NEEDS PETER` threads explicitly** — these are the open loop that Step 9
closes once Peter answers them.

---

## Step 9 — The learning loop: hand off to /zynkr-kms

This is what makes the KB self-healing. A `[[NEEDS PETER]]` flag is only half the job — the other
half is making sure the same question never goes unanswered again.

1. **Peter supplies the answer.** After you flag a gap, Peter either edits your holding draft with
   the real answer and sends it, or tells you the answer directly in this conversation.
2. **Once a flagged thread has Peter's real answer**, hand that thread off to **/zynkr-kms** so the
   answer is captured. Concretely, when Peter says the gap is answered (or you can see his reply on
   the thread), tell him:

   > "That answer isn't in the KB yet — want me to run **/zynkr-kms** on this thread so the next
   > identical question auto-drafts?"

   and on his go-ahead, invoke **/zynkr-kms** with that thread (the `Skill` tool, or surface it for
   Peter to run). Pass along: the thread link, the inquirer's question, and Peter's answer.
3. **/zynkr-kms does the write side** — it reasons about intent → which section → whether a new
   fact card is needed, proposes the card, and on Peter's approval drafts it into the 知識庫,
   filed in its section and linked to the facts it cites. A correction to an existing card goes
   to Peter as a packet he applies in Atlas. It then marks the thread `KMS-ingested` so it isn't
   re-learned.
4. **Peter publishes the draft in Atlas.** A draft is never served: until he publishes it, this
   skill cannot find it.

Result: the gap this skill flagged becomes a KB card, and the next time that question arrives,
Step 5 finds it and Step 6 drafts a confident reply. **You (read) and /zynkr-kms (write) share one
KB and work hand in hand.** Do not write to the KB yourself — drafting replies is this skill's job;
curating the KB is /zynkr-kms's job.

---

## Things to be careful about

- **Never commit Peter to a delivery date, refund, discount, pricing, or feature** not explicitly in
  the KB *or* supplied by Peter in this conversation. Any such ask with no authoritative source is
  automatically low-confidence → holding reply.
- **Price quotes:** even with an authoritative rate, don't invent the *scope* around it —
  travel fees, materials, minimum hours, multi-day discounts, validity windows. Quote only the rate
  you were given; flag the rest in `[[NEEDS PETER]]`.
- **Cite, don't restate-and-drift:** the canonical numbers live in fact cards. Resolve a cited
  fact into the reply, but if a qa card's body and its cited fact ever disagree, **trust the fact
  card** and flag the mismatch for /zynkr-kms.
- **Check card freshness:** `get_knowledge` shows each card's last-verified date. A card whose
  footer has a `Flags:` line naming `HELD`, `NEEDS_PETER` or `VOLATILE`, or an `Unverify note:`
  line, is NOT a confident source; treat it as a gap. That holds for a published card too: a flag
  stays until Peter takes it out. (`always-read` marks the two style cards and is no warning.)
- **Only the set counts:** a search hit whose key the walk did not list — another collection's
  note, a skill's note, a company fact found by search alone — is never quoted.
- **No fallback:** when Atlas cannot be reached, never read the CRM's old 知識庫, the Drive copy or
  memory instead. Holding replies only.
- **The Google Drive KB copy is a backup mirror, not a source** — never pull answers from it; the
  Atlas 知識庫 is the source of truth and the mirror can lag it.
- **Website-form notifications:** reply goes to the customer email in the body, as a fresh email (no
  `thread_id`). In-thread replies silently email `website@zynkr.ai`.
- **Don't reply on threads Peter already replied to** — Step 2 inspection is the real filter, not the
  search query (Gmail keeps the label after a reply).
- **No signatures/footers Peter didn't ask for** (no "Sent from my iPhone", taglines, calendar links
  unless they're in the KB). His own Gmail signature card is the one he asked for: step 7 attaches it.
- **Spam / out-of-scope** (vendor pitch, recruiter) → skip, don't draft; mention it in the summary.
- **One draft per thread.** If a draft already exists, don't create a second — list it as
  already-drafted.
- **Search-first, don't bulk-read.** `search_knowledge` + a few `get_knowledge` reads is the
  standard read; the walk lists keys only, once per run. If you find yourself reading whole
  sections card by card for every thread, re-classify the intent or improve your search words
  instead.

---

## When the KB returns nothing across the whole run

If retrieval comes up empty for every thread, draft holding replies for everything with
`[[NEEDS PETER]]` blocks (this is still useful triage) and tell Peter in the summary — that's a
signal the KB has a coverage gap that /zynkr-kms should fill once he answers. If it came up empty
because Atlas could not be reached or the walk failed, say that instead: the gap is the
connection, not the 知識庫.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
