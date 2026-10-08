# bug-routing-config.md — example (shape only)

`gtm-bug-ticket` reads a local `bug-routing-config.md` at the start of every run to choose the repository an issue goes to, after the build's `[Deployment]` record (see the skill's Configuration section). This file shows the shape, with blanks only.

The real file lives **outside this repository**: which client's assistant lives in which repo is business-confidential, so never commit it here or to any other repo (`.gitignore` ignores the name). The skill only reads the file; it never edits it.

## Client map

One row per client. A client row always outranks a surface fallback.

| company | repo |
|---|---|
| `<the company name exactly as on the CRM deal>` | `<owner>/<repo>` |

## Surface fallbacks

Only to override the skill's default table. Leave this section out to keep the defaults.

| surface | repo |
|---|---|
| `<product surface, e.g. platform / CRM / KB>` | `<owner>/<repo>` |

With no record and no matching row, or with no file at all, the skill does not guess: its approval step asks you to pick a repository and proposes the exact line for you to add here.
