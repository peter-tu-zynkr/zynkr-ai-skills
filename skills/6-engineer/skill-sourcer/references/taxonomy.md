# Zynkr Skills Taxonomy & Pipeline Index

## The pipeline — issues, labels and the GitHub Project

Every pipeline entry is an issue in `zynkr-skill-idea`, and its labels are the status of record.
The issue is also added to GitHub Project `<your-skills-pipeline-project>`, a company fact read
from Atlas (`SKILL.md` says how), with custom fields (Pipeline Status, Keep, Category, Intake
Source, Build *) for display; the values each step sets are in `SKILL.md` and `agents/proposer.md`.

### Retired 2026-05-15 — the Skills Pipeline sheet (do not read or write)

| Sheet | ID | Tab |
|-------|-----|-----|
| [Zynkr Skills Pipeline](https://docs.google.com/spreadsheets/d/<your-pipeline-sheet-id>) | `<your-pipeline-sheet-id>` | `Pipeline` |

It was the pipeline's record until 2026-05-15, when the GitHub Project replaced it. Its shape,
for reading old rows only — **Columns:** Source, Date Added, Skill Name, Link, Description,
Category, Category Name, Status, Overlap, Keep, GitHub Issue, Notes · **Status lifecycle:**
`proposed` → `approved` → `in-progress` → `built` · **Keep column:** `Y` (approved) / `N`
(rejected) / `?` (pending review).

### Archived sheets (read-only, no longer written to)
- [Validation Inventory](https://docs.google.com/spreadsheets/d/1q4H54EH9oBHeu8GHb7R4rDyG-LXUe-vSk9zg_VsH91I) — raw research dump, migrated 2026-04-11
- [Master Table](https://docs.google.com/spreadsheets/d/139n3rHIyIQuU1eaSuXVyDjWRBC9JaB4C_aHXkd12_pM) — operational skills by LOB, migrated 2026-04-11

---

## Taxonomy (0–9)

| # | Function | Hints |
|---|----------|-------|
| 0 | Strategy & Leadership | vision, OKRs, decisions, market analysis |
| 1 | Brand & Marketing | content, copywriting, campaigns, social, SEO |
| 2 | Sales & Consulting | proposals, pitches, CRM, client documents |
| 3 | Operations | SOPs, project tracking, process automation |
| 4 | Training | learning content, transcripts, courses, onboarding |
| 5 | Product (`product`) | roadmap, UX, GTM, product analytics |
| 6 | Engineer (`engineer`) | platform, infra, automation, data, tooling, CI/CD, code review, deployment, APIs, agent infra, dev utilities |
| 7 | People & Talent | recruiting, performance, org design, HR |
| 8 | Finance & Admin | budgeting, invoicing, reporting, admin |
| 9 | Legal | contracts, compliance, legal research, risk |
