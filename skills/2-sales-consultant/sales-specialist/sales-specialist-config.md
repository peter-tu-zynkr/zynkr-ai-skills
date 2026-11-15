---
name: sales-specialist-config
description: "Configuration for the business card pipeline skill — Zynkr platform target, field mapping, and email defaults."
---

# Business Card Pipeline Config

## Zynkr platform (the only destination)

| Setting | Value |
|---------|-------|
| **How it writes** | Only through the `zynkr` MCP's tools, never with SQL: `create_company` · `update_company` · `create_contact` · `create_note` (Step 4), then `create_deal` · `create_task` at the draft (Step 6). `SKILL.md` Step 0 stops before the first card when one is missing |
| **Contacts page** | `https://crm.zynkr.ai/contacts` |
| **Owner** | The claimer — the person running the skill: the `mcp__zynkr__list_workspace_members` row with the email `mcp__zynkr__whoami` gives, passed as `owner_id` on the company and the contact (`SKILL.md` Step 4). The deal made at the draft (`SKILL.md` Step 6) is theirs too |

### Card → platform field mapping (all 12 fields have a home)

| Card field | Lands in |
|------------|----------|
| name | the contact's `first_name` (whole name as printed; `last_name` left blank) |
| title | the contact's `title` |
| email | the contact's `email` (dedup key) |
| mobile | the contact's `phone` (the only number, when the card has one) |
| company | the company's `name` (find-or-create) |
| website | the company's `domain` (lower-cased, without its scheme, `www.` or path) |
| industry | the company's `industry` |
| address | the company's `address` |
| phone (office) | the company's `phone` (when the card has both numbers) |
| linkedin · notes · card_date | body of the `名片` note on the contact (`create_note`) |

Enriching an existing company only fills fields that are still empty, so a card
can never overwrite something curated by hand.

### Contact defaults (passed on every `create_contact`, `SKILL.md` Step 4)

| Field | Default | Why |
|-------|---------|-----|
| `lifecycle_stage` | `lead` (prospect) | a freshly-met card is top-of-funnel; the tool would default to `opportunity` |
| `legal_basis` | `consent` | required field; the card was handed over |
| `lead_status` | not set | the tool has no such field; the 名片 note records where the contact came from (owner, 2026-11-15) |

## Retired: the B2B Customer List Sheet

Deleted in November 2026. The platform holds the whole card, so there is no Sheet to append to or
read from.

## Google Account

```
user_google_email: <your-google-workspace-account>
```

## Email Defaults

| Setting | Value |
|---------|-------|
| **From** | <your-google-workspace-account> |
| **Default action** | Save as Draft (never auto-send) |
| **Language** | Match the contact's card language (Chinese card → Traditional Chinese email; English card → English email) |
| **Tone** | Professional, warm, brief — reference one specific detail from company research |
| **Style guide** | `SKILL.md` → *House style* |

## Email Sign-off

```
Best regards,
Peter
```

> Every drafted email ends with these two lines and nothing after them: no title, phone, address or signature block, the same as sales-follow-up's drafts.
