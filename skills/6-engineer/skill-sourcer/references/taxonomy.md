# Zynkr Skills Taxonomy & Pipeline Index

## Source of truth — the GitHub Project

The skills pipeline lives in GitHub Project `<your-skills-pipeline-project>`, a company fact
read from Atlas (`SKILL.md` says how). Every entry is an issue in `zynkr-skill-idea` added to
the Project with custom fields (Pipeline Status, Keep, Category, Intake Source, Build *); the
values each step sets are in `SKILL.md` and `agents/proposer.md`.

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
| 5 | Development Ops | CI/CD, code review, deployment, infrastructure |
| 6 | Tech | engineering tools, APIs, agent infra, dev utilities |
| 7 | People & Talent | recruiting, performance, org design, HR |
| 8 | Finance & Admin | budgeting, invoicing, reporting, admin |
| 9 | Legal | contracts, compliance, legal research, risk |
