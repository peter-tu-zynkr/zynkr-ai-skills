# Drive `[6.2]` mirror + the Atlas check — what `confirm-ship` does after CI

## Why this file exists

`ingest-skills.yml` and the public shelf automate everything downstream of a merge to `main`:

```
merge → ingest.ts → content/ → build-marketplace.ts → generated/skills-index.json   (the full index: public + team)
      → build-taxonomy-tree.ts → skills/README.md → auto-commit
      → export-stage.yml → the public skills only → the shelf peter-tu-zynkr/zynkr-ai-skills
      → zynkr.ai/api/skills/sync → Supabase → marketplace
```

It touches **git, Supabase and the website. Nothing else.** What is left for `confirm-ship`:

| Surface | What writes it | What `confirm-ship` does |
|---|---|---|
| **Zynkr Atlas** — the record of every skill, its versions and its knowledge | the workbench merge arrives there as a version waiting for approval | **read only**: compare the folder tree Atlas serves with the merge's, and say whether the merge is live, waiting or not yet there. Never approve. |
| **Drive `[6.2]` mirror** | nothing automated | copy the merged files to Drive (Procedure A) |
| **The Zynkr Skill Map** — the team's visual map of every skill, by 部門 | its own generator, from `main` and Atlas's live list | **nothing**: name the skill in the report for the map's next rebuild. Never edit a map page from here. |

The mirror runs at `confirm-ship` because that is post-merge: the files are on `main` and can be
copied.

The mirror is a **team surface** (readable by the zynkr.ai domain) and carries **every** skill,
whether it is marked `visibility: public` or `team`; a team skill gets its Drive folder exactly
like a public one. Take the set of skills from the workbench's full index
(`generated/skills-index.json` on `main`, read with `gh api`), never from `zynkr.ai/api/skills`,
which lists public skills only.

### ⚠️ The Skills Index Sheet is retired: do not read or write it

The `[6.0] Zynkr Skills Index` Google Sheet was archived on 2026-11-06 (`SKB-115`). Atlas holds
the record of every skill, and the Skill Map is the visual. The Sheet stays readable as history
in its folder's `_archive`. A copy of this skill that still says to write a row there is out of
date: skip that step and update the skill.

## Fixed IDs (committed literals — do not re-derive them from a Drive search)

- **Drive folder** `[6.2] Skills & Knowledge Library` (inside `[6] 產品部門 (Product)` since 2026-11-03): `1Q0XwdR574cNUVlT7lYVbpzNbVsup2KAu`
  - `1 Skills/` — `1r92r__bUGZ61ZJP5fGcHGg_mnTaicFhz`
  - `2 Knowledge/` — `1jkloCgEHHfy83R-PFPTZBCllh4znvhi2`

Category folders under `1 Skills/` (the eight with a recorded ID):

| Repo dir | Drive folder | ID |
|---|---|---|
| `0-strategy` | `0 Strategy & Leadership 策略與領導` | `1igX5f8UQu5vy9c3tMCT5yLFxA89Wm2kt` |
| `1-brand-marketing` | `1 Brand & Marketing 品牌與行銷` | `1IoMVkF0Me2iSJnnSC-0_wyqx8KLjOgsc` |
| `2-sales-consultant` | `2 Sales & Consultant 銷售與顧問` | `1R_c1NR_cnhqkXs-MMYvCjuKZTLtO2YPD` |
| `3-operations` | `3 Operations 營運` | `1fQRS_m4CssL9KPjizei3TmTIcot-5agP` |
| `4-training` | `4 Training 培訓` | `1Amn0jHj8Mv9wfj2nQNysc3BMDgyznnY5` |
| `5-product` | `5 Product 產品` | `1GEGRw6-2vASi3IqMUA5Y7Sla26VFxpCx` |
| `6-engineer` | `6 Engineer 工程` | `1r4ulOn6hW3K1haR5oKhFbE4hzJK6mzU_` |
| `7-people-talent` | `7 People & Talent 人才與招募` | `1Rn-RrM8TwpUk4O37QjorEf6GmN_b2B9U` |

`8-finance-admin` and `9-legal` have no row above, so no folder ID is recorded for them. When the
skill being shipped is in one of those, look for its category folder under `1 Skills/` first, and
create it, named to match the pattern above, only if it is missing.

## What gets created

- **Always** — `1 Skills/<category folder>/<slug>/` holding `SKILL.md` (raw, `text/markdown`).
- **When the skill ships knowledge** — `2 Knowledge/<slug>/` holding every other git-tracked
  file in the skill directory, **flattened**: `references/foo.md` becomes `references__foo.md`,
  `scripts/bar.py` becomes `scripts__bar.py`.
- Skill ships only `SKILL.md` ⇒ **do not create** a knowledge folder. If a legacy
  `_SOURCES.md`-only folder already exists for it (the 2026-08-28 pass made one for most skills,
  including ones that ship nothing but a `SKILL.md`), **leave the folder alone**: do not delete it
  and do not count it as knowledge.

## Deciding "is there knowledge" — one command, not a judgement call

```bash
git ls-tree -r --name-only origin/main -- "skills/<N-cat>/<slug>" | grep -v '/SKILL\.md$'
```

The count of those lines is the answer: non-zero means a knowledge folder with that many files,
zero means none.

## Procedure A — mirror to Drive

1. Resolve the category folder ID from the table above.
2. Create `1 Skills/<cat>/<slug>/`.
3. Stage the files. **Uploads must be staged under `~/.workspace-mcp/attachments/`** and passed
   as a `file://` URL — anything outside that directory is refused by the sandbox, and passing
   file bodies inline round-trips them through the model instead of copying bytes.
4. Upload `SKILL.md` with `mime_type="text/markdown"`.
5. If, and only if, the knowledge count is non-zero: create `2 Knowledge/<slug>/` and upload the
   flattened files. Mime types: `.md` → `text/markdown`; `.json`, `.py`, `.sh`, `.gs` →
   `text/plain`.
6. Delete the staging directory afterwards.

## Procedure B — check Atlas (read only)

The question is whether the version Atlas serves **is this merge**. Atlas numbers its versions
itself and the SKILL.md carries none, so compare git trees, never numbers. With the `zynkr-atlas`
MCP server connected:

1. `list_installs` — find the folder `skills/<N-cat>/<slug>` (a sub-agent ships inside its
   parent's folder: use the parent's). Its `tree` is the git tree of the version Atlas serves.
2. Compare it to the merged folder, **fetching first** (a stale `origin/main` still holds the
   old tree, which is the one Atlas serves, and would read as live):
   ```bash
   git fetch -q origin main
   git rev-parse "origin/main:skills/<N-cat>/<slug>"
   git log -1 --format=%cI origin/main -- "skills/<N-cat>/<slug>"   # when the folder last changed
   ```
3. Only if they differ, or the folder is not listed: `list_pending` — is a version of the slug
   under `versions`, with a `requested_at` **after** the folder's last change? An older pending
   version is an earlier merge's, not this one. Some read-only Atlas tokens do not offer
   `list_pending`; then say so.

Report exactly one state:

- **live** — the two trees are equal: Atlas serves this merge. Name the `version`.
- **waiting** — the trees differ (or the folder is new) and `list_pending` has a version of the
  slug requested after the folder's last change. Name its `semver`. The owner decides it in Atlas after reading `get_draft`, which also
  shows whether that version holds this merge (SDD §5.6).
- **not yet in Atlas** — the trees differ (or the folder is new) and `list_pending` has nothing
  for the slug requested after the folder's last change: the merge has not reached Atlas yet. Re-check later; if it stays that way, it is
  a gap to raise, not to fix here.
- **not live, pending not checked** — the trees differ and `list_pending` is not available.

**Never approve or publish from `confirm-ship`**: an approve puts the version live for everyone
who reads the workspace, and it waits for the owner's word (SDD §5.6). Without the MCP server,
say "Atlas not checked" and carry on.

## Verify before flipping the issue to `shipped`

- Confirm the uploaded `SKILL.md`'s frontmatter `name` matches the slug — a mis-parented file
  opens the wrong skill.
- Confirm the knowledge folder's file count equals the count from the command above.
- The Atlas state is in the report: live, waiting, not yet in Atlas, not live (pending not
  checked), or not checked.

## Gotchas that have already cost time

- **`.md` content cannot be replaced in place.** `update_drive_file` handles only native
  Docs/Sheets/Slides. A refresh means create-new + trash-old, so **file IDs churn while folder
  IDs survive**.
- **Two folders legitimately share the slug name** — one under `1 Skills/`, one under
  `2 Knowledge/`. A Drive search by name returns both. They are not duplicates; do not
  "clean up" either.
- **`_SOURCES.md` is not universal.** Folders created before the 2026-08-28 pass do not have
  one, and it is generated from the Knowledge Map Doc's three-group logic. Do not hand-author
  one to make a folder look complete.
- **The mirror is one-way**: `zynkr-skill-builder/skills/` → Drive. Never edit in Drive; the
  next sync destroys it. It mirrors team skills too — the shelf is the public copy, not this one.
