# Client-PRD intake

A client's approved PRD, written by `/ops-prd-writer`, enters the build pipeline here. A client build is not an
idea, so it skips steps 2–5 of the main flow: no extraction, no deduplication against ideas, and no proposal for the
public marketplace. It is built only inside the private workbench. While the workbench is public, `/skill-triager`
holds it (SKB-054), and the issue waits on the board.

## 1 · Read the PRD

- **Find the Doc.** A Doc URL → use it. A spec ID such as `ACME-001` → resolve the client's `[N]` folder (the deal's
  `專案資料夾：` line, or one name match under the projects parent `1hkXPX7OXPFOU0BcloPbJSFp8O0zArM8t`) and search it:
  `mcp__google-workspace__search_drive_files(user_google_email="<your-google-workspace-account>", query="'<folder id>' in parents and name contains '[PRD] ACME-001'")`.
- **Read it as Markdown** with `mcp__google-workspace__get_doc_as_markdown`. Plain text drops the `**AC-n**` markers.
- **Take:**
  - `SPEC_ID` and `TITLE` from the H1 `# <SPEC_ID> — <TITLE>`;
  - the `Size / DoD` line;
  - the number of `**AC-n**` pairs;
  - the client and deal from the `Client:` line.
- **Malformed?** A PRD with no H1 or no AC pairs goes back to `/ops-prd-writer`. Stop and say which shape is
  missing.
- **Approved?** The PRD's Status line reads `Draft` until the build ships, so ask once: "Is `<SPEC_ID>` approved for
  build?" No → stop; the PRD isn't ready for Build.

## 2 · Pick the category

Spawn the **skill-classifier** subagent with what the build does (the PRD's title and Context section), never the
client's name. It returns the functional category the skill folder will live in, `skills/<N>-<category>/`. A
medium or low confidence shows the runner-up and asks, as in the main flow.

## 3 · File the issue

Make sure the label exists first (`--force` makes a re-run harmless), then file:

```bash
gh label create client-build --repo peter-tu-zynkr/zynkr-skill-idea --force \
  --description "Built for one client from an approved PRD"
gh issue create --repo peter-tu-zynkr/zynkr-skill-idea \
  --title "[Client Build] <SPEC_ID> — <TITLE>" \
  --label client-build --label "category:<N>-<category>" \
  --body-file <body.md>
```

The `client-build` label, the `[Client Build]` title and the `**Intake**: client-prd` line below each tell the
Build skills this is a client build, and any one of them is enough to hold it. Keep all three.

The body points at the PRD; it never copies acceptance criteria, which stay in the client's Doc:

```
**Intake**: client-prd
**Spec ID**: <SPEC_ID>
**PRD**: <doc url>
**Deal**: https://platform.zynkr.ai/deals/<deal id>
**Client folder**: <[N] folder url>
**Size / DoD**: <from the PRD>
**Acceptance criteria**: <n> in the PRD
**Approved for build**: <YYYY-MM-DD>, by <who said yes>
**Slug**: <clientslug>-<purpose> (proposed; /skill-triager confirms)
**Build Repo**: zynkr-skill-builder (a skill) · <owner/repo> (a web app, built in its own repo)
```

Then add the issue to the Pipeline Project and set its fields the way `agents/proposer.md` does (`gh project
item-add`, then `gh project item-edit` per field):

| Field | Value |
|---|---|
| Pipeline Status | `approved` |
| Keep | `yes` |
| Category | `<N>-<category>` |
| Intake Source | `skill-sourcer` (the `client-build` label is what marks a client build) |
| Build Repo | `zynkr-skill-builder`, or `external` for a web app built in its own repo |
| Build Target Path | `<N>-<category>/<slug>` |
| Build Status | `not-started` |
| Artifact | `spec-only` (the PRD is the spec) |

Then add the `triage-ready` label. The Project is private, so client builds belong on it.

## 4 · Report

The issue URL, the proposed slug and category, and the state: "`/skill-triager` holds a client build until the
workbench is private; nothing is built yet." Once the build is deployed, `/skill-deploy` records where it runs.
