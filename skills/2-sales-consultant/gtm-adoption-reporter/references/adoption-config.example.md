# adoption-config.md — example (shape only)

`gtm-adoption-reporter` reads a local `adoption-config.md` when a build has no `[Deployment]` record from /skill-deploy, and for a field the record leaves open (see the skill's Configuration section). This file shows the shape, with blanks only.

The real file lives **outside this repository**. Its rows hold client workspace ids, user emails and go-live dates, which are client PII and commercial terms, so never commit it here or to any other repo (`.gitignore` ignores the name). Copy this file to wherever you keep it, rename it `adoption-config.md`, and replace every `<…>` before use.

One row per client, not per build.

| company | workspace_id | user_emails | features | go_live |
|---|---|---|---|---|
| `<the company name exactly as on the CRM deal>` | `<the client's platform workspace uuid>` | `<user@client.example>, <user@client.example>` | `<feature>, <feature>` | `<YYYY-MM-DD>` |

- **company** — as the CRM deal names it. The skill looks the row up by this name.
- **workspace_id** — the client's workspace uuid on the platform.
- **user_emails** — the people whose use counts, comma-separated.
- **features** — values of `crm_ai_usage.feature` to count. Leave it empty to report the whole workspace.
- **go_live** — the production date, `YYYY-MM-DD`.

A missing row, or a missing file, never stops a run: the skill falls back to the deal's CRM contacts as the user set and says so in the report's 資料覆蓋範圍.
