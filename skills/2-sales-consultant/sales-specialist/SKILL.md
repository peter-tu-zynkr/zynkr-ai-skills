---
name: sales-specialist
sheetId: "2.02"
description: "Business card pipeline — OCR extraction, schema normalization, Zynkr platform contact + company creation, company research, and personalized follow-up email drafting. Takes business-card IMAGES specifically — the OCR pass is the point. When the lead signal already arrives as text (a DM thread, an event feedback row, a website enquiry), use sales-outbound instead; for a WHOLE event survey sheet, use sales-client-sourcing."
category: sales-consultant
project: sales-specialist
platform: claude
status: Done
visibility: public
author: Peter Tu
input: "Business card image(s) — single or batch"
process: "OCR via Claude Vision → schema review → pick-up gate (an open deal stops the card before any write) → Zynkr platform write (contact + company + 名片 note + tags) → /sales-research brief → follow-up draft → claim (a deal owned by the runner) → Gmail save"
output: "Contact + company + 名片 note on the Zynkr platform, a deal owned by the runner, and a follow-up email in Gmail Drafts; a card whose email has an open deal gets neither"
synergy: ["sales-research"]
type: agent
skills: ["sales-follow-up-mail"]
reads: ["sales.crm-data-standards", "company.sales-pipeline-rules", "company.crm-tag-rules"]
house-style: bound

---

# Sales Specialist

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill sales-specialist
```

Automate the full post-trade-show workflow: extract contact info from business card images, land them on the Zynkr platform, research each company, and draft personalized follow-up emails. Use this skill after a conference, expo, or networking event where you've collected business cards and want them turned into working CRM records plus drafts ready to send before context fades.

**Not this skill when — the signal is already text.** What this skill owns is the OCR pass
from a photographed card. A DM thread, an event feedback row or a website enquiry goes to
`/sales-outbound`; a WHOLE event survey sheet goes to `/sales-client-sourcing`. Everything
downstream (CRM write, research, follow-up draft) is the same either way — only the parser
differs.

---

## Step 0 — Load Config

Read the config file at:
`./sales-specialist-config.md`

Read the contact schema at:
`./references/contact-schema.md`

Store:
- `EMAIL_SIGN_OFF` — the sign-off from config: `Best regards,` then `Peter`, with nothing after it
- `SCHEMA_FIELDS` — the 12-field list: name, title, company, email, phone, mobile, website, address, linkedin, industry, notes, card_date

**Check the CRM tools.** The platform is written only through the `zynkr` MCP's own tools (Step 4
and Step 6), never with SQL. Before the first card, check that `whoami`, `list_workspace_members`,
`list_contacts`, `list_deals`, `list_companies`, `get_company`, `create_company`, `update_company`,
`create_contact`, `create_note`, `create_deal` and `create_task` are all among its tools. If one is
missing:
```
⚠️  The zynkr MCP has no <tool>. Nothing has been written.
```
Stop and say which: without them there is nowhere to write the cards, and a card written only in
part is worse than none. `apply_tag` and `list_tags` are not on the list, since a missing one only
turns the tags into a suggestion (Step 4, item 6).

---

## Step 1 — Card Intake

Ask the user:
```
Please share your business card image(s).
You can paste one image or multiple at once for batch processing.
```

Detect intake mode:
- **Single card** — 1 image → proceed to Step 2
- **Batch** — multiple images → process all in Step 2, then review all at once in Step 3

Store images as `CARD_IMAGES[]`.

---

## Step 2 — OCR & Extract

For each card image, use Claude Vision to extract all visible text and map it to the 12-field schema:

**Extraction rules:**
- Read every element on the card: name, title, company, logos, contact details, addresses, URLs, QR code domain (if visible), social handles
- Map each piece of data to the correct schema field
- If a field is not present on the card, set it to `—`
- For `industry`: infer from company name/website if not explicitly stated; use a short label (e.g., "SaaS", "製造業", "零售", "FinTech")
- For `card_date`: default to today's date unless user specifies otherwise
- If text is ambiguous (e.g., could be phone or fax), use field label context clues on the card

Store extracted data as `CONTACTS[]` — one object per card with all 12 fields.

---

## Step 3 — Schema Review

For each contact, display a clean table:

```
| Field      | Extracted Value |
|------------|-----------------|
| name       | [value]         |
| title      | [value]         |
| company    | [value]         |
| email      | [value]         |
| phone      | [value]         |
| mobile     | [value]         |
| website    | [value]         |
| address    | [value]         |
| linkedin   | [value]         |
| industry   | [value]         |
| notes      | [value]         |
| card_date  | [value]         |
```

For batch mode, display all contacts in a numbered list (`Contact 1 of N`, etc.).

Ask:
```
Does this look correct?
- Type [OK] to proceed
- Type [EDIT field=value] to correct a field (e.g., EDIT email=david@company.com)
- Type [ADD note=...] to append to the notes field
```

Accept corrections until user types `OK`. Update `CONTACTS[]` with confirmed data.

---

## Step 3.2 — Pick-up Gate

One open deal per client: the person who picks a client up makes a deal owned by themselves
before any draft, and nobody drafts to a client a teammate already has. Run this gate right after
the cards are confirmed in Step 3, for every card with an email, before Step 4 writes anything to
the platform.

> **The pick-up rule and the deal name are written in Atlas** (`get_knowledge`, key `sales.crm-data-standards`, on the `zynkr-atlas` MCP server): the claim rule, and §1's deal name. The six steps below are how this skill runs the rule, and they run as written even when Atlas cannot be reached; only the deal name then falls back to `<name>（<company>）名片交流`, and the summary says so.

**The claimer** is the person running the skill: `mcp__zynkr__whoami` gives their email, and their
member id is the `mcp__zynkr__list_workspace_members` row with that email.

A card with **no email** cannot be checked or mailed: it still goes to Step 4 and is recorded, but
it gets no claim and no draft, and the Step 8 summary says so.

**One card per person first.** Normalise every card's email (step 1) and de-duplicate the batch on
it: the first card wins, and each later one is reported as 「同批重複」 under the first card's
result. A duplicate gets nothing of its own (no platform write, no claim, no draft), so two cards
for one person can't both claim.

For every remaining card with an email, on the `zynkr` MCP:

1. **Normalise the email** — trim it and lower-case it.
2. **Find the contact** — `mcp__zynkr__list_contacts(search=<email>, limit=100)`. The search is a
   substring match over both addresses, so keep only rows whose `email` or `secondary_email`,
   trimmed and lower-cased, equals the email exactly: `b@example.com` does not match
   `a.b@example.com`.
3. **No contact → step 6.** A new client: Step 4 creates the contact.
4. **Find their open deals** — `mcp__zynkr__list_deals(stage=<stage>, limit=100)` once for each
   open stage, `new`, `contacted`, `qualified` and `proposal` (once for the whole batch), keeping
   the rows whose `contact_id` is one of the matched contacts. `list_deals` cannot filter by
   contact, so if any of the four calls returns exactly 100 rows the check is not sound: stop,
   write nothing, claim nothing, draft nothing, and say so. `won` and `lost` deals do not count: a
   client whose deals are all closed is free to claim again.
5. **An open deal → stop for this card.** It skips Steps 3.5 to 7: no platform write (no company
   created, no company column backfilled, no contact, no 名片 note), no research, deal, task or
   draft. Name the owner by matching the deal's `owner_id` to an `id` from
   `mcp__zynkr__list_workspace_members`, and keep one line for the Step 8 summary:
   `<email> 已有進行中的 deal：<deal_number> · <stage> · 負責人 <member name> · 最後活動 <last_activity_at, YYYY-MM-DD>`.
   In a batch, carry on with the next card.
6. **Claim at the draft** — the card goes on to Step 3.5 and Step 4. When its email is approved
   (`[OK]` in Step 6), the claim runs **before** the draft is saved (Step 6, *Claim*). A card you
   `[SKIP]` is not picked up: no deal.

**Then check the company — a warning, never a stop** (owner, 2026-11-09). A teammate may already be
talking to this person's company: an open deal on a colleague's address, or a company-list mail
(`/sales-outbound` Mode C) that has no contact yet. Skip this check when the email is on a personal
mail service (gmail.com, yahoo.com, yahoo.com.tw, hotmail.com, outlook.com, icloud.com, msn.com and
the like) and the signal names no company. Otherwise:

- `mcp__zynkr__list_companies(search=<the email's domain>, limit=100)` when that domain is not a
  personal mail service, and `mcp__zynkr__list_companies(search=<search term>, limit=100)` when the
  signal names a company, the search term being its name cut before the first comma, parenthesis,
  `%`, `*` or backslash, at most 60 characters (the tool turns those characters into spaces and
  keeps only the first 60, so a whole name like `範例科技 Co., Ltd.` finds nothing). Keep rows whose
  `domain` equals the email's domain (never a personal mail service's), or whose name matches
  ignoring case and the legal suffix.
- For each kept company: its open deals are the rows of the four `list_deals` calls above whose
  `company_id` is that company (no new calls), and `mcp__zynkr__get_company` shows any `description`
  line `公司名單冷開發（Mode C，YYYY-MM-DD，認領人 <名字>）`.
- Report each hit in one line and carry on: `<公司> 已有人在跟：<deal_number> · <stage> · 負責人 <member
  name>` or `<公司> 在 <YYYY-MM-DD> 由 <認領人> 用 Mode C 寫過`. The claimer talks to that teammate
  before sending anything; the claim itself goes ahead, because one open deal is per person, not per
  company.

---

## Step 3.5 — Website Lookup (auto-fill if missing)

For each card the gate did not stop (Step 3.2) where `website` is `—` or blank:

Run a WebSearch query: `"[company name]" official website`

Parse the top result for the company's official domain. Apply these rules:
- Accept only the company's own domain (skip directories like twincn.com, iyp.com.tw, etc.)
- If a clear official site is found, set `website` to the full URL (e.g., `https://example.com`)
- If no clear official site found, leave `website` as `—`

Display the result inline (no separate confirmation step needed):
```
🌐 Website found: [URL] (auto-filled)
```
or:
```
🌐 Website: not found — left blank
```

Update `CONTACTS[]` with the resolved website before proceeding to the platform write.

---

## Step 4 — Zynkr Platform Write

The **Zynkr platform is the only destination** for a card. Everything lands at
`https://crm.zynkr.ai/contacts`, where the funnel is actually worked — there
is no spreadsheet copy to keep in sync, and no field is dropped on the way:

| Card field | Lands in |
|---|---|
| name | the contact's `first_name` (whole, as printed) |
| title | the contact's `title` |
| email | the contact's `email` (the dedup key) |
| mobile | the contact's `phone` — the number you'd actually use |
| company | the company's `name` (find-or-create) |
| website | the company's `domain` (lower-cased, without its scheme, `www.` or path) |
| industry | the company's `industry` |
| address | the company's `address` |
| phone (office) | the company's `phone` — belongs to the company, not the person |
| linkedin · notes · card_date | a `名片` note on the contact |

> The old `B2B Customer List` Google Sheet is gone (deleted 2026-11): the platform holds the whole
> card.

Run this **autonomously** for every confirmed card the gate did not stop (no extra approval gate —
they already signed off in Step 3); a card without an email comes here too. A card Step 3.2
stopped, or a 「同批重複」, skips this step entirely: no company created, no column backfilled.
For each of those contacts in `CONTACTS[]`:

**1. Clean the values.** Translate the `—` sentinel (and any blank) to an empty
string for every field before using it. The platform should never store a literal `—`.

**2. Use the name as printed.** The whole name goes in `first_name` and `last_name` stays empty
(`sales.crm-data-standards` §3) — don't split it into 姓/名. If the card prints both a Chinese
and a romanized name (e.g. `王大明 / David Wang`), use the Chinese name if present,
otherwise the romanized one — and store it whole (`王大明`, or `David Wang`).

**3. Keep both numbers.** The mobile goes to the contact's `phone` and the office line to the
company's `phone`, so neither is lost. If the card shows only one number, it goes to the contact
alone, so the contact always has a number.

**4. Write the card, on the `zynkr` MCP.** One record at a time, in the order below. Each write is
the two-call handshake: `confirm:false` previews, then the identical call with `confirm:true`. It
finds or creates the company, fills only the company fields that are still empty (**never**
overwriting a value a person curated), creates the contact **only if the email isn't already on
the platform** (as anyone's email or secondary email), and attaches the 名片 note. It creates no
deal: the claim waits for the draft (Step 6).

**The owner is the claimer** — the person running the skill. Their member id is the
`mcp__zynkr__list_workspace_members` row with the `whoami` email, as in Step 3.2 (look it up here
if no card went through that gate), and it is the `owner_id` of the company and the contact.
Never use the company contact address when the claimer is someone else: the deal in Step 6 is
owned by the claimer, and the contact is too. Keep each id the moment its tool returns it: the
company's for Step 5 and Step 6, the contact's for the note, the tags and the claim.

- **Company**, when the card has one: `mcp__zynkr__list_companies(search=<search term>, limit=100)`,
  the search term being the name cut before its first comma, parenthesis, `%`, `*` or backslash, at
  most 60 characters (the tool turns those characters into spaces and keeps only the first 60, so a
  whole name like `範例科技 Co., Ltd.` finds nothing). Take the row whose `name` equals the card's
  full company name, ignoring case. None among fewer than 100 rows →
  `mcp__zynkr__create_company(name=…, domain=…, industry=…, address=…, phone=<the office line, when
  the card has both numbers>, owner_id=<claimer's member id>)`, with `domain` the website,
  lower-cased, without its scheme, `www.` or path. None among exactly 100 rows → the check is not
  sound: create no company, file the contact without one, and say so in the summary. A row found →
  `mcp__zynkr__get_company(id=…)`, then `mcp__zynkr__update_company(id=…, …)` with only the fields
  that are empty there and that the card has (`domain`, `industry`, `address`, and `phone` only when
  the card has both numbers, as in item 3), so a value a person curated is never overwritten. If
  none qualifies, make no call.
- **Contact**, only when Step 3.2 matched no contact or the card has no email (with no key to match
  on, it always creates one). Right before creating, repeat Step 3.2's exact email match with
  `mcp__zynkr__list_contacts`: a match now means the card is already on the platform (item 5).
  Otherwise `mcp__zynkr__create_contact(first_name=<the whole name as printed>,
  email=…, title=…, phone=<the mobile, else the only number>, company_id=…,
  owner_id=<claimer's member id>, lifecycle_stage="lead", legal_basis="consent")`. Pass
  `lifecycle_stage` every time: the tool defaults to `opportunity`. Leave out whatever the card
  lacks, `last_name` always. The tool has no `lead_status`, so that field stays empty: the 名片
  note says where the contact came from (owner, 2026-11-15).
- **名片 note**, on every contact created here (Step 2 always gives the card a date):
  `mcp__zynkr__create_note(contact_id=…, subject="名片 · <card_date>", body=…)`, the body being these
  lines, each only when the card has it: `LinkedIn: …`, `名片日期: …`, `公司電話: …` (only when the
  card has both numbers), `備註: …`. The tool takes one parent, so the note sits on the contact,
  where the contact's page and its deals' pages show it.

**A write that fails stops this card there** (owner, 2026-11-15). Retry nothing now and delete
nothing: the card keeps the ids its tools already returned and makes none of its later writes in
this step, and the summary names the write that failed with the tool's error. The rest of the batch
carries on. The company's backfill is the one exception: a `get_company` or `update_company` that
fails stops nothing. The company keeps the values it had, the summary names the fields left unfilled
with the tool's error, and the card goes on to its contact. A card that stopped before its contact
existed goes no further: no tag, research, claim or draft (Step 6, *Claim*, item 1). A card whose
contact exists goes on to research, claim and draft; only its note and tags wait. The retry at the
end (Step 8) goes on from the write that failed, with those ids. Never run such a card again from
the top: its email would now match the contact it made, so this step would skip it as already on
the platform and its 名片 note would never be written; a card with no email would get a second
contact; and once its deal exists, Step 3.2 would stop it on its own deal.

**5. Report each card.**
- `create_contact` returned an `id` → created; that `id` is the `contact_id`. Display:
  ```
  ✓ [Contact Name] @ [Company] — added → https://crm.zynkr.ai/contacts/[contact_id]
  ```
- Step 3.2, or the re-check right before creating, matched a contact → it already exists
  (de-duped). Display:
  ```
  ⏭️ [Contact Name] — already on the platform (matched by email), skipped
  ```
  Note this also means **no note was written** for that card — the note is attached
  to a newly created contact only, so a re-scan never stacks duplicate notes.
- A write failed → Display:
  ```
  ✗ [Contact Name] — FAILED at <write>: <the tool's error> · made so far: <company / contact links, or nothing>
  ```
- A card with no email cannot be checked for a duplicate: add
  `(no email: not checked for a duplicate)` to its line.
- The company's backfill failed → add `(company fields not filled: <fields> — <the tool's error>)`
  to its line.

A failed card stays in `CONTACTS[]` with the ids it has, so the retry at the end can finish it, and
one card's platform hiccup never blocks the others. Because the platform is the only destination, a
card that stopped before anything was written is **not recorded anywhere**: say so explicitly in
the Step 8 summary rather than reporting the contact as processed.

**6. Tag the contact this run created.** An existing contact keeps its tags: a missing 來源 there is
`/sales-manager` REVIEW's to find. Use the `zynkr` MCP. This is the tool's own
handshake, not a question to the user: each tag is
`mcp__zynkr__apply_tag(group=…, name=…, entity_type="contact", entity_id=<contact_id>, source="rule")`
to preview, then the same call with `confirm:true`. Both groups come from fixed rules, so `source`
is `rule`.

- **來源** (`group="source"`) — 名片交換, when the policy's `source-values` line lists it and its
  entry in `source-to-lead-source` is `other`, the `lead_source` of the deal in Step 6. Otherwise
  apply none and write `標籤建議：來源=名片交換`.
- **待確認** (`group="review"`) — one value from `review-values` per gap in what was written: no
  phone → 電話缺漏, no title → 待補職稱, a company email or a company name but no company record →
  未關聯公司. `create_contact` always sets `legal_basis`, so 同意權未確認 does not arise. A card with no email
  stays blank: `review-values` has no value for it, and none is invented.

Never infer a tag from a job title or an industry. Read the result back with
`mcp__zynkr__list_tags(entity_type="contact", entity_id=<contact_id>)` and report what it shows.

> **The CRM tag rules are company policy — read them from Atlas** (`get_knowledge`, key `company.crm-tag-rules`, on the `zynkr-atlas` MCP server; each list is a `<name>: <value>` line at the top, and the `value:` line is the version date). Apply only a value those lines name: `group` is the platform's English key (`source`, `review`) and `name` is the policy's value. Apply no tag when Atlas cannot be reached, the key or a line you need is missing, `mcp__zynkr__list_tags` or `mcp__zynkr__apply_tag` is not among your tools, or `apply_tag` answers `not_found` or `invalid_input`: write each tag you would have applied as one line `標籤建議：<group>=<value>` in one `mcp__zynkr__create_note(contact_id=…, subject="標籤建議", body=…)` on the contact, say so in the summary, and carry on with the run. When the policy itself cannot be read, write the evidence instead of a value (`標籤建議：來源=名片`, `標籤建議：缺=<電話、職稱、公司>`); never pick a value from memory or from an older copy of this file. On `conflict`, read the contact back with `list_tags`, report what it shows, and do not retry. Any other error (`forbidden`, `rate_limited`, `internal`, …) is handled like `not_found`: no tag, a suggestion, no retry, and no stopping to ask.

---

## Step 5 — Company Research

For each contact the gate did not stop, the research comes from `/sales-research`, the same way
`/sales-discovery-prep` step 2 gets it:

1. **This conversation already holds a `/sales-research` brief on the card's company**, run earlier
   in it or pasted by the user from the company page → use that brief, and run nothing.
2. **Otherwise run `/sales-research`** with the ids Step 6's claim uses: the contact Step 4 created
   (its `contact_id`) or the one the gate matched, and the company Step 4 found or created (its id;
   none → no `company_id`). Hand it the card's own notes too. It runs under its *Run by a lead skill*
   rule: it files notes only, never creating the company Step 4 left out or writing a field, and
   what it would have asked comes back in its report, for the review below. It reads
   the government registry by 統編 as well as the web, and files the brief as a note on the company,
   where the next skill and the deal owner find it. Never look for an earlier brief in the CRM
   instead: no CRM tool reads a record's timeline.
3. **A person, or a one-person business** (no company on the card, or the company is the person
   themselves) → `/sales-research` takes its person case: two or three lines on the contact.

Keep what the brief found as the contact's `RESEARCH_SUMMARY` for Step 6, in this shape. Write only
what the brief says; a claim it marks unverified stays out of the summary:

```
## Company: [Company Name]

### Overview
[2–3 sentences from the brief: what they do, business model, size/stage]

### Recent News
- [a dated item from the brief]
- [another, or "No recent news found"]

### Personalization Hook
[The single detail from the brief most worth referencing in the follow-up email]
```

Display the research summary to the user. Ask:
```
Research looks good? [OK] or [EDIT] to add/change context.
```

---

## Step 6 — Follow-up Email Draft

For each contact with an email that the gate in Step 3.2 cleared, launch the `followup-email-writer` agent using the Agent tool.

Pass the following in the prompt:
```
## Contact Info
[all 12 fields from CONTACTS[i]]

## Company Research Summary
[RESEARCH_SUMMARY for this contact]

## Meeting Context
[CONTACTS[i].notes — or "No specific notes" if empty]

## Language
[Detect from card: if Chinese characters on card → zh-TW; otherwise → en]

## Sign-off
[EMAIL_SIGN_OFF from config]
```

Wait for the agent to complete. Display the drafted email.

Ask:
```
Email looks good?
- [OK] → save to Gmail Drafts
- [EDIT subject=...] / [EDIT body=...] → adjust the email
- [SKIP] → skip this contact's email
```

Accept edits until user approves.

**Claim** — on `[OK]`, before Step 7 saves the draft, make the deal that claims this client.
Each write is a two-call handshake: `confirm:false` previews, then the identical call with
`confirm:true` applies.

1. **Contact** — the contact Step 4 created (its `contact_id`), or the one the gate matched.
   If neither exists (the platform write failed and was not retried), there is nothing to claim
   on: no deal and no draft for this card, and the summary says so.
2. **Company** — the company Step 4 found or created (its id); none → no `company_id`.
3. **Deal** — `mcp__zynkr__create_deal(name=<the deal name, sales.crm-data-standards §1>,
   contact_id=…, company_id=…, owner_id=<claimer's member id>, stage="new", lead_source="other",
   priority="medium")`.
   A business-card exchange is `other`. Always pass `owner_id`.
4. **Task** — `mcp__zynkr__create_task(deal_id=<deal id>, subject="等 <name> 回覆名片跟進信",
   due_at=<today + followup-fast-days, ISO 8601 with +08:00>, assignee_id=<claimer's member id>)`:
   someone met at an event has no reply history, so the rhythm is the fast one.
5. **Cap** — count the claimer's open deals (the rows of the four open-stage `list_deals` calls
   whose `owner_id` is theirs, plus the deals this run made). At or over `max-open-deals` the claim
   still stands — warn, never refuse — and the summary says
   `<owner> 現在有 M 筆 open deal（上限 <max-open-deals>）— 先跑 /sales-manager 放掉 stale 的`.

If the deal write fails, save no draft for that card: an unclaimed client gets no mail. Say so in
the summary. A failed deal or task write stops the card there under Step 4's rule: no draft, the
deal kept when it was made, and the retry at the end goes on from that write.

> **The pipeline thresholds are company policy — read them from Atlas** (`get_knowledge`, key `company.sales-pipeline-rules`, on the `zynkr-atlas` MCP server; each threshold is a `<name>: <value>` line at the top, and the `value:` line is the version date). If Atlas cannot be reached, the key is missing, or a line you need is missing, say so and ask; never fall back to a number from memory or from an older copy of this file.

---

## Step 7 — Save to Gmail Drafts

This skill never sends. Every approved email is saved as a draft for a person to send, like the rest of the sales family.

For each approved email whose card was claimed in Step 6, use `mcp__google-workspace__draft_gmail_message`:
- `user_google_email`: `<your-google-workspace-account>`
- `to`: contact email from `CONTACTS[i]`
- `subject`: subject line from agent output
- `body`: the email body from agent output, with its sign-off, converted to HTML mechanically: escape `&` `<` `>`, turn every line break into `<br>`, wrap it in `<div dir="ltr">…</div>`, add nothing else
- `body_format`: `"html"`
- `include_signature`: `true` — Gmail adds Peter's signature card (logo, title, phone) under the sign-off, the way his own sent mail ends. The body's sign-off stays the two lines `Best regards,` / `Peter`; the card is not a second sign-off. HTML is required because the signature is HTML: on a plain-text draft it is flattened into one line, or lost (`SKB-085`, 2026-10-19; this replaces the 17 Oct `include_signature=false`)

Display confirmation per contact:
```
✓ [Contact Name] — email saved to Drafts
```

---

## Step 8 — Pipeline Summary

Display final completion summary:

```
=============================================
📇 Business Card Pipeline — Complete
=============================================

Processed: [N] contact(s)

[Contact 1 Name] @ [Company]
  ✓ Added to the Zynkr platform (or ⏭️ already existed / ✗ FAILED at <write> — made so far: <links, or nothing>)
  ✓ 名片 note attached
  ✓ 標籤：來源=[value] · 待確認=[values]（已讀回）(or ⚠️ 未貼，標籤建議已記在 note（原因） / ⏭️ existing contact, tags left alone)
  ✓ Claimed — deal [交易 number], owner [claimer] (or ⏭️ skipped / no email)
  ✓ Email saved to Drafts

[Contact 2 Name] @ [Company]
  ⛔ [email] 已有進行中的 deal：[交易 number] · [stage] · 負責人 [member name] · 最後活動 [date]
  — no platform write, no deal, no draft
  ↳ 同批重複: [the later card(s) with the same email], nothing written for them
  ...

Contacts: https://crm.zynkr.ai/contacts
=============================================
```

If any card shows `✗ FAILED`, list those cards again underneath, each with what it already has
(company, contact, deal, with links) and the write that failed, and offer to retry: each from its
failed write with those ids, then the rest of that card's run (a contact made by the retry goes on
to its note, tags, research, claim and draft; a claim finished by the retry gets its draft). Never
from the top (Step 4 says why). A card that stopped before anything was written exists nowhere but
the image it came from. Then the cap line (Step 6, *Claim*), if the claimer is at or over it.

---

## Error Handling

- If OCR fails to extract a field: mark it `?` and flag it in the review table
- If a platform write fails: the card stops at that write (Step 4) and the rest of the batch carries on. Keep the card flagged with the ids it has, always offer to retry at the end from that write — never from the top — and never report it as processed. A card that stopped before anything was written is recorded nowhere.
- If `/sales-research` cannot run, or its brief finds nothing recent: note "No recent news found" (and why there is no brief, when there is none) and proceed to the email with what the card and the brief do say
- If saving the Gmail draft fails: display the error; offer to copy email text to clipboard instead
- Never silently skip a step — always surface errors clearly

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
