---
name: skill-sourcer
sheetId: "6.03"
description: "Aggregate skill candidates from any source, classify against the Zynkr taxonomy, check for duplicates in the GitHub Project pipeline, and propose new skills as issues for review."
category: engineer
project: skill-sourcer
platform: claude
status: WIP
visibility: public
author: Peter Tu
input: "GitHub link, URL, file path, or pasted raw text describing a potential skill; or a client's approved [PRD] Doc from /ops-prd-writer"
output: "Issue created in peter-tu-zynkr/zynkr-skill-idea (label skill-proposal) and added to the skills pipeline GitHub Project with Pipeline Status=proposed, Keep=?. On approval the issue gets the triage-ready label."
synergy: []
type: agent
skills: ["skill-classifier", "skill-deduplicator", "skill-extractor", "skill-proposer"]
handoff: ["skill-triager"]
disable-model-invocation: true
security_audits:
  gen_agent_trust_hub: pending
  socket: pending
  snyk: pending
house-style: bound

---

# Skill Sourcer

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill skill-sourcer
```

Ingest a skill candidate from any source, classify it, check for duplicates in the pipeline, and propose it for review.

> **Where this fits:** the **first step** of the canonical skill chain — `/skill-sourcer` → `/skill-triager` → `/skill-author` → `/skill-qa` → `/skill-publish` → `/skill-triager` (confirm-ship). After you approve (`Keep=yes`), the next hop is `/skill-triager` picking up the `triage-ready` label. See `architecture.md` in the repo root for the full chain.

> **Source of truth:** every pipeline entry is a GitHub Issue in the idea repo, and its **labels are the status of record**: `triage-ready` once approved, then `building`, `shipped`, `parked` or `rejected`. The issue is also added to GitHub Project `<your-skills-pipeline-project>` (e.g., `owner/N`) with custom fields (Pipeline Status, Keep, Category, Intake Source, Build *); those fields are for display only, and nothing routes on them. The legacy Google Sheet is deprecated — do not read or write to it.

> **`<your-skills-pipeline-project>` is a company fact — read it from Atlas** (`get_knowledge`, key `company.skills-pipeline-project`, on the `zynkr-atlas` MCP server; the value is the `value:` line, and its `cli:` line is the ready `gh project item-list` command). If Atlas cannot be reached, the key is missing, or there is no `value:` line, ask for it; never run with the blank still in it. Pass the value to both subagents.

---

## Step 1 — Collect input

Accept input in any of these forms:

- **GitHub link** → fetch README and skill/agent files from the repo
- **URL** → fetch and extract skill-relevant content
- **File path** → read the file directly
- **Pasted text** → use as-is
- **A client PRD** — a Google Doc titled `[PRD] <SPEC_ID> — <title>` written by `/ops-prd-writer`, or its spec ID
  (a client's code such as `ACME-001`, never one of Zynkr's own spec codes `PLAT` · `WEB` · `SKB` · `ACC` ·
  `CMS` · `KMS` · `ADM` · `LRN` · `ATL`) → **skip Steps 2–7** and follow `references/client-prd-intake.md`,
  which files, labels and reports on its own. A client build is not an
  idea: it files a `[Client Build]` issue labelled `client-build`, which `/skill-triager` holds until the workbench
  is private.

Also check the `inbox/` folder for any dropped files not yet processed.

Inform the user what input was detected and how it will be processed.

---

## Step 2 — Extract skill intent (subagent)

Spawn the **skill-extractor** subagent with the raw input.

It returns a structured extract:
- name, title, description
- input / output
- who it helps
- source URL

Display the extract to the user and ask: **"Does this look right? Anything to correct before we classify?"**

Wait for confirmation or corrections before proceeding.

---

## Step 3 — Classify into taxonomy (subagent)

Spawn the **skill-classifier** subagent with the confirmed extract.

It returns:
- category number (0–9) and name
- confidence level
- reasoning

Display the result. If confidence is **medium or low**, show the runner-up and ask the user to confirm the category before proceeding.

---

## Step 4 — Check pipeline for duplicates (subagent)

Spawn the **skill-deduplicator** subagent with the confirmed extract and classifier output.

It reads all items from GitHub Project `<your-skills-pipeline-project>` via `gh project item-list` and checks each one for overlap.

It returns a verdict: `exact_duplicate`, `near_duplicate`, `partial_overlap`, or `new`.

**If `exact_duplicate` or `near_duplicate`:**
> "We already have **[skill name]** (status label: [label], Keep: [keep]) which covers this. Here's how they overlap: [summary]. Skipping."
> Stop here.

**If `partial_overlap`:**
> "This overlaps partially with **[skill name]**: [summary]. It's different enough to potentially stand alone."
> Ask: **"Do you want to proceed with a proposal anyway?"**

**If `new`:**
> "No existing entry covers this. Proceeding to proposal."

---

## Step 5 — Add to pipeline (subagent)

Spawn the **skill-proposer** subagent with all outputs from previous steps.

It will:
1. Create a GitHub Issue in `peter-tu-zynkr/zynkr-skill-idea` titled `[Skill Proposal] {{category_number}} — {{title}}` with structured body and label `skill-proposal`
2. Add the issue to GitHub Project `<your-skills-pipeline-project>` and set custom fields: `Pipeline Status=proposed`, `Keep=?`, `Category={{category_number}}-{{slug}}`, `Intake Source=skill-sourcer`, `Build Repo=zynkr-skill-builder`, `Build Target Path={{category_number}}-{{cat-slug}}/{{slug}}`, `Build Status=not-started`, `Artifact=issue-only`
3. Display the issue URL and ask: **"Approve now (this adds the `triage-ready` label; Keep=yes mirrors it on the board), or leave it for later review?"**

If the user approves immediately:
4. Update the Project item for display: `Keep=yes`, `Pipeline Status=approved`
5. Add the `triage-ready` label to the issue: the label is the approval of record, and the signal for `/skill-triager` to pick it up
6. Optionally create a markdown idea record in `peter-tu-zynkr/zynkr-skill-idea` at `skills/approved/{{slug}}.md`. If created, set `Artifact=synced`.

---

## Step 6 — Sync approved skills (standalone mode)

This step runs when the user says **"sync approved skills"** outside of the normal intake flow.

Use this as a **reconciliation / backfill** command, not the primary approval path.

1. List the approved set of record: the open issues in `zynkr-skill-idea` labelled `triage-ready`
2. For each issue, check:
   - Is it on the board, with `Keep=yes` and `Pipeline Status=approved`?
   - Markdown idea record exists at `skills/approved/{slug}.md`?
   - `Artifact` field matches actual state?
3. Repair gaps:
   - Add the issue to the board if missing, and set `Keep=yes` and `Pipeline Status=approved` for display
   - Create the markdown idea record if absent
   - Update `Artifact` to `synced` / `issue-only` / `spec-only` to match reality
4. List the board items with `Keep=yes` whose issue carries none of `triage-ready`, `building`, `shipped`, `parked` or `rejected`: approved on the board only. Don't add the label; the label is the approval of record, so ask the user whether to approve each one
5. Report repairs grouped by action taken

---

## Step 6.5 — Sync READMEs

Run this step **after every approval** (in normal intake flow) and **at the end of standalone sync mode**.

### A — Local README

Nothing to edit by hand: the skills README's Taxonomy table lists categories only, and its skill tree is generated by `scripts/build-taxonomy-tree.ts` when `ingest-skills.yml` runs.

### B — GitHub idea artifacts

Every approved idea must have:
- GitHub issue (labels: `skill-proposal`, `triage-ready`) — created in Step 5
- Project membership with custom fields set
- Optional markdown idea record at `zynkr-skill-idea/skills/approved/{slug}.md`

Also maintain `SOURCED.md` in `peter-tu-zynkr/zynkr-skill-idea` as a human-readable index:

```markdown
# Sourced Skills Pipeline

External skills approved for adoption into Zynkr. Sourced via skill-sourcer. Triaged via /skill-triager. Built in zynkr-skill-builder.

| Skill | Category | Description | Source | GitHub Issue | Idea Spec | Date |
|-------|----------|-------------|--------|--------------|-----------|------|
```

Append one row per newly approved skill. Use `gh api` to read the current file, update it, and push back via `gh api` PUT. If the file doesn't exist yet, create it with the header + the new row.

### C — Build handoff tracking

This skill is the curation stop gate. It does **not** start implementation in `zynkr-skill-builder`.

Maintain handoff-ready tracker fields on every approved Project item:

- `Build Repo` → default `zynkr-skill-builder`
- `Build Target Path` → expected slug or destination path
- `Build Status` → starts as `not-started`
- `Built Skill URL` → empty until shipped

These fields are for display. `/skill-triager` (the middle layer) reads the issue's labels and body to triage approved issues and dispatch builds to `zynkr-skill-builder`.

### Status model

The board shows two layers, for display only (the issue's label is the status of record):

- `Pipeline Status` = business / curation stage
  - `proposed`, `researching`, `approved`, `building`, `shipped`, `parked`
- `Build Status` = implementation stage
  - `not-started`, `context-prep`, `building`, `testing`, `ready-to-ship`, `shipped`, `external`, `dropped`

Interpretation:

- Use `shipped` in `Pipeline Status` when the capability is live, whether in `zynkr-skill-builder` or through a stable external/platform path.
- Use `external` in `Build Status` when the capability exists outside `zynkr-skill-builder` and should not get a Zynkr repo link.
- Use `Built Skill URL` only for shipped capabilities that live in `zynkr-skill-builder`.

---

## Step 7 — Done

Summarize:
- What was sourced
- Where it was classified
- Duplicate verdict
- Issue created (if new)
- Project membership set
- Markdown idea record link (if approved and created)

**Completion checklist (all must be ticked before done):**
- [ ] Input collected and source identified
- [ ] Skill extract confirmed by user
- [ ] Category confirmed (with user sign-off if confidence was medium/low)
- [ ] Dedup check completed against GitHub Project `<your-skills-pipeline-project>`
- [ ] If new: issue created in `zynkr-skill-idea` with `skill-proposal` label
- [ ] If new: issue added to Project with `Pipeline Status=proposed`, `Keep=?`, Category set
- [ ] If approved: `Keep=yes`, `Pipeline Status=approved`, `triage-ready` label added
- [ ] If approved: `Build Repo=zynkr-skill-builder`, `Build Status=not-started`, `Build Target Path` set
- [ ] If approved: `SOURCED.md` in `zynkr-skill-idea` updated

Ask: **"Want to source another skill?"**

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
