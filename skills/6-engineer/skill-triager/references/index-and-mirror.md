# The Atlas check — what `confirm-ship` does after CI

(The file keeps its old name, `index-and-mirror.md`, because Atlas keys a note on it.)

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
| **The Zynkr Skill Map** — the team's visual map of every skill, by 部門 | its own generator, from `main` and Atlas's live list | **nothing**: name the skill in the report for the map's next rebuild. Never edit a map page from here. |

The check covers **every** skill, whether it is marked `visibility: public` or `team`. Take the set
of skills from the workbench's full index (`generated/skills-index.json` on `main`, read with
`gh api`), never from `zynkr.ai/api/skills`, which lists public skills only.

### ⚠️ Two copies are retired: do not read or write them

- **The `[6.0] Zynkr Skills Index` Google Sheet**, archived on 2026-11-06 (`SKB-115`). It stays
  readable as history in its folder's `_archive`.
- **The Drive `[6.2] Skills & Knowledge Library` mirror**, retired on 2026-11-13 (`SKB-129`).
  `confirm-ship` no longer copies a merged skill to Drive: Atlas records every approved version,
  and the workbench holds every file.

A copy of this skill that still says to write a Sheet row or upload to `[6.2]` is out of date: skip
that step and update the skill.

## The Atlas check (read only)

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

- The Atlas state is in the report: live, waiting, not yet in Atlas, not live (pending not
  checked), or not checked.
