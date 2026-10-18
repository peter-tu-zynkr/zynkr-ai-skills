---
name: zynkr-skills
sheetId: "6.02"
description: "The front-door router for the Zynkr assistant ecosystem. Takes ANY input from the user — a URL, a file path, a slug, a vague idea, a question about pipeline state — figures out which Zynkr skill it belongs to, reads the relevant state across GitHub Project / issues / on-disk / live marketplace, and either auto-invokes the right sub-skill or asks one targeted clarifying question. Use this skill whenever the user drops something into the conversation without specifying which skill should handle it — every undirected URL, file mention, idea, status question, or 'what should I do with this?' is a candidate. Especially fire on phrases like 'I found this', 'I just built X', 'where am I with Y', 'what's in my queue', 'I have an idea about', '幫我看一下這個', '/zynkr-skills', or when the user pastes a link with no further direction. Triggers MORE eagerly than the specific skills below it — when in doubt, route through /zynkr-skills rather than asking the user to remember the right slash command. Also fire on deck / 簡報 requests — 'make me a deck', '幫我做簡報', '做投影片', 'pitch deck', 'deep dive 簡報', 'all-hands 簡報', '把這份資料做成簡報' — and route them to /zynkr-slide (the slide-relay orchestrator)."
category: engineer
project: zynkr-skills
platform: claude
status: WIP
visibility: public
author: Peter Tu
input: "Anything: a URL, local file path, skill slug, free-text idea, status question, or pasted content. The skill classifies the input shape before doing anything else."
process: "Classify input shape → look up state across the four signals (Project / issues / on-disk / live API) when the input references a skill-pipeline item → route to the right sub-skill via the Skill tool when confidence is high (for the four it cannot start, print the command), or ask one targeted clarifying question when ambiguous. Surfaces queue / dashboard views on read-only queries."
output: "Either: (a) an auto-invocation of the right Zynkr sub-skill, or its printed command for the four the Skill tool cannot start (most common); (b) one targeted clarifying question when intent is genuinely ambiguous; (c) a compact state table when the user asks 'what's in my queue' / 'where is X'."
synergy: ["skill-sourcer", "skill-triager", "skill-publish", "skill-finder", "content-newsletter-draft", "training-lecture-transcript", "sales-specialist", "cv-customizer", "zynkr-support", "content-governance", "zynkr-content-writer", "training-srt-optimizer", "zynkr-slide"]
type: agent
skills: ["skill-sourcer", "skill-triager", "skill-author", "skill-qa", "skill-publish", "skill-finder"]
handoff: ["skill-sourcer", "skill-triager", "skill-author", "skill-qa", "skill-publish"]
executed_by: internal-user
house-style: exempt — pure router — selects a child skill, drafts nothing itself

---

# Zynkr Skills

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill zynkr-skills
```

The **front-door router** for everything Peter drops into the assistant. Take any input — a URL, a path, a slug, a half-formed idea, a "where am I with X?" question — figure out which Zynkr capability it belongs to, read the relevant state, and route. This is Zynkr's mission expressed as a skill: *gather knowledge, turn it into a capability, add it to the knowledge base* — applied recursively to the assistant itself.

> **Where this fits:** `/zynkr-skills` sits **above** the canonical skill-authoring chain (`/skill-sourcer` → `/skill-triager` → `/skill-author` → `/skill-qa` → `/skill-publish`) and beside the content skills (`/content-newsletter-draft`, `/sales-specialist`, `/training-lecture-transcript`, etc.). It does not replace any of them. Power users still call them directly. `/zynkr-skills` is the catch-all for unstructured input.

---

## Step 1 — Classify the input

Pattern-match the user's input against the table below. **First match wins.** Heuristics are intentionally crude — false positives bounce to Step 3 (clarification), so a wrong guess here is cheap.

| Signal in input | Input type |
|---|---|
| `https://github.com/<owner>/<repo>` or `https://skills.sh/...` referencing a SKILL.md or repo of skills | `external-skill-url` |
| `https://github.com/peter-tu-zynkr/zynkr-skill-idea/issues/<N>` or `#<N>` referring to an idea-repo issue | `pipeline-issue-ref` |
| User says "qa `<slug>`", "check this skill", "健檢", "does this pass QA", "review this skill" — OR drops a SKILL.md with an explicit QA/review verb | `qa-request` |
| A folder path or file path that resolves to a `SKILL.md` on disk | `local-skill-md` |
| A Google Doc titled `[PRD] …` (check a Doc's title before falling through to `google-doc`), or a client spec ID such as `ACME-001` with a build verb ("build ACME-001", "build this PRD", "這份 PRD 可以開工了"). Zynkr's own spec codes (`PLAT` · `WEB` · `SKB` · `ACC` · `CMS` · `KMS` · `ADM` · `LRN` · `ATL`) are internal specs, never a client PRD | `client-prd` |
| `https://docs.google.com/document/...` | `google-doc` |
| `.srt` / `.vtt` extension OR `youtu.be` / `youtube.com/watch` URL OR words like "transcript", "字幕", "逐字稿" | `transcript` |
| Image of a business card (jpg/png/heic) or words like "business card", "名片" | `sales-specialist` |
| Question-shaped — starts with `what / where / how many / show me / list / 還有什麼 / 還有哪些` | `query` |
| Free text mentioning a known sub-skill domain (newsletter / 電子報, CV / 履歷, support 信箱, article 文章) | `typed-text` |
| Free text asking to build a deck / 簡報 / 投影片 / presentation / pitch deck (make / build / 做 / produce) | `deck-request` |
| Anything else | `unclassified` |

State what you detected to the user in one sentence so they can correct if needed:

> "Looks like a `<input-type>` — let me check the state and route you."

---

## Step 2 — Look up state (only when input references a skill-pipeline item)

For `external-skill-url`, `pipeline-issue-ref`, or `local-skill-md` inputs, gather state from these four signals **in parallel** (use multiple Bash calls in one turn):

| Signal | How to read | What you learn |
|---|---|---|
| GitHub Project | `gh project item-list <N> --owner <owner> --limit 200 --format json` on Project `<your-skills-pipeline-project>` (`owner/N`) — match by slug (derived from URL or frontmatter `name`) | Display only: Pipeline Status, Build Status, Keep, Intake Source and Built Skill URL for the state card. Never route on them — the issue label is the status of record |
| Issue + labels | `gh issue list --repo peter-tu-zynkr/zynkr-skill-idea --state all --search "<slug>" --json number,title,labels,state` | Existence of an issue, current label (`triage-ready` / `building` / `shipped` / `parked` / `rejected`), open vs closed |
| On-disk SKILL.md | `ls skills/<N-cat>/<slug>/SKILL.md` (run from the repo root) | Whether scaffold or publish already landed in the repo |
| Full index · `/api/skills` | `gh api repos/peter-tu-zynkr/zynkr-skill-builder/contents/generated/skills-index.json -H 'Accept: application/vnd.github.raw'` and match the slug — the workbench's full index, public and team skills alike. For a skill marked `visibility: public` (no key means team) also `curl -sL https://www.zynkr.ai/api/skills` and grep for slug | Whether the skill is shipped (on `main` and in the index) and, for a public skill, whether it is live on the marketplace. zynkr.ai lists public skills only, so a team skill is never there |

Pick the slug from either the URL last segment (`.../tree/main/skills/<slug>`) or the SKILL.md frontmatter `name`. If you can't resolve a slug, skip the state lookup and treat as `unclassified`.

> **`<your-skills-pipeline-project>` is a company fact — read it from Atlas** (`get_knowledge`, key `company.skills-pipeline-project`, on the `zynkr-atlas` MCP server; the value is the `value:` line, and its `cli:` line is the ready `gh project item-list` command). If Atlas cannot be reached, the key is missing, or there is no `value:` line, ask for it; never run with the blank still in it. The reconcile sweep below reads the same Project.

---

## Step 3 — Decide the route

Switch on `(input-type, state)` using the table below. Auto-invoke means use the **Skill** tool with the sub-skill's name; the sub-skill loads its own SKILL.md and runs.

The Skill tool cannot start a skill whose frontmatter sets `disable-model-invocation: true` — today `/skill-sourcer`, `/skill-triager`, `/skill-qa` and `/skill-publish`; Claude Code blocks the call. For those four, "auto" means: state the route in one sentence, then print the exact slash command for Peter to run, as in **Nudge** (Step 4). For a finished `local-skill-md`, print `/skill-qa <path>`, then `/skill-publish <path>` once it passes.

### Skill-pipeline inputs

| Input × State | Action | Confidence |
|---|---|---|
| `external-skill-url`, no prior state | Invoke `/skill-sourcer <URL>` | High → auto |
| `client-prd` | Invoke `/skill-sourcer` with the PRD: its client-PRD intake files a `[Client Build]` issue labelled `client-build` | High → auto |
| `pipeline-issue-ref` for a client build (labelled `client-build`, titled `[Client Build] …`, or `**Intake**: client-prd` in its body — any one) + `triage-ready` | Invoke `/skill-triager`; it holds a client build while the workbench is public | High → auto |
| `pipeline-issue-ref`, label = `triage-ready`, slug not yet in the full index, no `**Built via**` line in the body | Invoke `/skill-triager` (cue Option A) | High → auto |
| `pipeline-issue-ref`, `**Built via**: skill-publish` in the body, slug not yet in the full index | Render: "Built by `/skill-publish`; its PR is not merged yet. Merge it, then confirm-ship." Don't cue Option A: it would scaffold a competing stub | High → no-op |
| `pipeline-issue-ref`, label = `building`, on-disk file absent | Nudge: "Run `/skill-author` on branch `skill/<slug>` to write the body" — don't auto-invoke; authoring needs you in the loop | High → nudge |
| `local-skill-md`, slug matches an open `triage-ready` or `building` issue | Print `/skill-qa <path>` first. Once the QA run shows **PASS**, print `/skill-publish <path>` (continuation mode). On **ERROR** → stop at the QA report, don't route to publish. On **WARN-only** → list the warnings and ask "publish anyway?" before printing the publish command. | High → auto (QA → publish on PASS) |
| `local-skill-md`, no matching open issue | Print `/skill-qa <path>` first, then `/skill-publish <path>` (fresh-intake mode) once it passes (same ERROR/WARN handling). | High → auto (QA → publish on PASS) |
| `pipeline-issue-ref`, PR merged + slug in the full index + open issue still carries `building` or `triage-ready` (a `/skill-publish` fresh intake stays `triage-ready`) | Invoke `/skill-triager` (cue Option D `confirm-ship`) | High → auto |
| `pipeline-issue-ref`, label = `shipped` | Render: "Already shipped — live at `https://www.zynkr.ai/ai-skills-marketplace` (slug `<slug>`)." — or, for a team skill, "Already shipped — team skill on workbench `main` (slug `<slug>`)." Then, if it isn't installed under `~/.claude/skills/`, offer its install line (the manifest's `install_command` when it sets one, else `npx skills add … --skill <slug>`) so it's invocable locally (marketplace-live ≠ installed in your session) — never for a client build, which the client receives as its own copy. | High → no-op (offer local install if missing) |
| `pipeline-issue-ref`, label = `parked` / `rejected` | Render the state, ask if user wants to revive | Medium → ask |

### QA inputs (standalone — any skill, any lifecycle stage)

`/skill-qa` is also the on-demand health-check. Explicit QA intent never auto-publishes.

| Input × State | Action | Confidence |
|---|---|---|
| `qa-request` + a local SKILL.md path or folder | Print `/skill-qa <path>` (standalone); report the verdict once it has run. | High → auto |
| `qa-request` + slug resolving to an in-pipeline `building` issue | Resolve the on-disk path (`skills/<N-cat>/<slug>/SKILL.md`) or the `skill/<slug>` branch head; print `/skill-qa <path>`. | High → auto |
| `qa-request` + slug of an already-`shipped` skill | Print `/skill-qa <slug>` for the in-tree `main` copy (re-audit / regression check). | High → auto |
| `qa-request` + an `external-skill-url` / candidate not yet in the pipeline | Print `/skill-qa <path>` for the fetched SKILL.md as a pre-intake quality probe. On PASS, offer: "Want to source this? → `/skill-sourcer`." | High → auto, then offer |
| `qa-request` but no resolvable artifact | Ask once: "Point me at the SKILL.md (path, slug, or URL) to QA." | Medium → ask |

### Knowledge-pipeline inputs (broader Zynkr scope)

| Input × Context | Action | Confidence |
|---|---|---|
| `google-doc` + the URL is a newsletter draft → invoke `/content-governance` | High → auto |
| `google-doc` + unclear intent | Ask: "Newsletter draft to sync to Notion, or something else?" | Medium → ask |
| `transcript` (`.srt` / `.vtt`) | Invoke `/training-srt-optimizer` | High → auto |
| `transcript` (video URL or long YouTube link, no .srt yet) | Invoke `/training-lecture-transcript` | Medium → confirm |
| `sales-specialist` image | Invoke `/sales-specialist` | High → auto |
| `typed-text` mentioning newsletter / 電子報 | Invoke `/content-newsletter-draft` | Medium → confirm intent |
| `typed-text` mentioning CV / 履歷 / resume | Invoke `/cv-customizer` | Medium → confirm |
| `typed-text` mentioning article / 文章 outline | Invoke `/zynkr-content-writer` | Medium → confirm |
| `typed-text` about support inbox / 客服 | Invoke `/zynkr-support` | High → auto |
| `deck-request` — build a slide deck / 簡報 / 投影片 (from material, a topic, or a resume-mid-relay packet) | Invoke `/zynkr-slide` | High → auto |

### Read-only state queries

| Query shape | Action |
|---|---|
| "What's in my triage queue?" / "show me triage-ready" | `gh issue list ... --label triage-ready` and render a table |
| "Where is `<slug>`?" / "status of `<slug>`?" | Run the Step 2 four-signal lookup and render a one-screen state card |
| "Does `<slug>` pass QA?" / "is `<slug>` QA-clean?" | Resolve the artifact (on-disk → branch → `main`), print `/skill-qa <slug>` for a report-only run, then render its PASS/FAIL verdict card. Read-only — never publishes. |
| "What shipped this week?" | `gh issue list ... --label shipped --search "closed:>2026-mm-dd"` and render |
| "What's stuck?" / "what's in approved >7 days?" | `gh issue list ... --label triage-ready --json number,title,updatedAt`, keep the issues not updated in 7 days, render |
| "Reconcile pipeline" / "close shipped" / "did anything ship without closing?" / "what's deployed but still open?" | Run the **Reconcile sweep** (section below) — diff live marketplace vs open proposals, close the matches. |

### Unclassified / ambiguous

Ask **one** targeted clarifying question. Never chain questions — if the user's answer is still unclear, default to the most likely sub-skill and let them course-correct. The "one question max" rule mirrors `/skill-finder`'s decision logic.

Example clarifications:
- "Is this a skill candidate I should source, or a newsletter topic?"
- "Do you want me to polish this transcript, or trim the .srt timing?"
- "I see two open issues for `<slug>` — #N (open, approved) and #M (open, parked). Which one are you asking about?"

---

## Step 4 — Render or invoke

### Auto-invoke

When confidence is **High** and the action is `auto`:

1. State your route in one sentence: "Routing to `/training-srt-optimizer` for this .srt."
2. Invoke the sub-skill via the **Skill** tool, passing the relevant input as `args`.
3. Let the sub-skill drive from there. Don't re-implement its logic inline.

For `/skill-sourcer`, `/skill-triager`, `/skill-qa` and `/skill-publish`, step 2 is printing the command instead, as in **Nudge**: the Skill tool cannot start them (Step 3).

**QA → publish order.** When the route is a finished `local-skill-md` for a build issue, print `/skill-qa <path>` first and read its verdict once Peter has run it. Print `/skill-publish <path>` only on a **PASS** (zero ERROR-tier findings). On FAIL, stop at the QA report — never route an ERROR-tier skill to publish.

### Nudge

When confidence is **High** but the action is **nudge** (e.g. `/skill-author` needs you in the loop and shouldn't be auto-invoked):

```
Next step: run `/skill-author` on branch `skill/<slug>`. The stub SKILL.md is at
skills/<N-cat>/<slug>/SKILL.md with `<!-- TODO -->` markers in the body.
```

Print the suggested command in a fenced code block so the user can copy-paste.

### State render

For read-only state queries, render a compact table:

```
Slug: eng-find-skills
Issue: #84 (CLOSED)
Labels: shipped, skill-proposal, category:6-engineer
Project: Pipeline=shipped, Build=shipped, Built Skill URL=...
Marketplace: ✅ live at https://www.zynkr.ai/ai-skills-marketplace
Recommended next step: nothing — fully shipped.
```

For a team skill the `Marketplace:` line reads `— team skill, not listed (by design)`.

Always end with a **"Recommended next step"** line so the user knows what to do (even if the answer is "nothing").

### Ask

For ambiguous inputs, use one of two shapes:
- A plain-text question if it's open-ended.
- An `AskUserQuestion` call if there are 2–4 discrete options to choose between.

Default to AskUserQuestion when the options are discrete — it surfaces choices more cleanly than a free-form question.

---

## Reconcile sweep — close shipped-but-open proposals

The closer in the canonical chain is `/skill-triager confirm-ship`, which runs **only** at the tail of `/skill-sourcer → /skill-triager → /skill-author → /skill-qa → /skill-publish`. Any skill that reaches workbench `main` by another path — a direct repo edit, a bulk renumber / rename / move migration, or hand-authoring straight into `zynkr-skill-builder/skills/` — never triggers it, so its proposal issue and Project card stay open forever. This sweep is the safety net: it reconciles **what is actually shipped** against **what is still open** and closes the gap.

Fire on: "reconcile pipeline", "close shipped", "did anything ship without closing?", "what's deployed but still open?", "/zynkr-skills reconcile", or proactively after any bulk deploy that bypassed `/skill-publish`.

**Step A — gather both sides (parallel Bash calls):**
1. **Shipped skills** — the workbench's full index: `gh api repos/peter-tu-zynkr/zynkr-skill-builder/contents/generated/skills-index.json -H 'Accept: application/vnd.github.raw'` (or, when run inside the repo, `git show origin/main:generated/skills-index.json`), and collect every `slug` with its `visibility` (no key means team; if the rows carry none, read the key from the skill's SKILL.md on `origin/main`). Never take this set from `zynkr.ai/api/skills` — it lists public skills only, so a team skill would never close.
2. **Live public skills** — `curl -sL https://www.zynkr.ai/api/skills` and collect every `slug`.
3. **Open proposals** — `gh issue list --repo peter-tu-zynkr/zynkr-skill-idea --state open --label skill-proposal --json number,title,labels --limit 300`.
4. **Board cards** — `gh project item-list <N> --owner <owner> --limit 300 --format json` on Project `<your-skills-pipeline-project>` (read from Atlas, Step 2), keyed by issue number; gives each card's `build Target Path` (authoritative slug) and item `id`.

**Step B — match.** For each open proposal resolve its slug in priority order: (1) board `build Target Path` basename, (2) the issue-title token after `—`, (3) frontmatter `name`. An issue is a **close candidate** when that slug is shipped — a **team** skill in the full index, or a **public** skill in the full index *and* on `/api/skills` — or it already carries a `shipped` label but the issue is still open. A public skill that is in the index but not yet on zynkr.ai is waiting for the shelf (a skill new to the shelf is held until the owner promotes it): list it, do not close it. Proposals whose slug is **not** in the index are backlog — leave them untouched.

**Step C — present, then close as a batch.** Render the candidates as a table (`#`, slug, live id, current label) and take **one** confirmation for the whole batch. Then for each:
- `gh issue edit <n> --repo peter-tu-zynkr/zynkr-skill-idea --add-label shipped --remove-label triage-ready --remove-label building` (ignore "label not found").
- `gh issue close <n> --repo peter-tu-zynkr/zynkr-skill-idea --reason completed --comment "✅ Shipped & reconciled — live as \`<name>\` (id \`<id>\`, on the shelf and zynkr.ai). Closed by \`/zynkr-skills\` reconcile sweep."` — for a team skill: `--comment "✅ Shipped & reconciled — team skill \`<name>\` (id \`<id>\`) on workbench main. Closed by \`/zynkr-skills\` reconcile sweep."`
- If the issue has a board card, flip Pipeline Status to `shipped`:
  ```bash
  gh project item-edit --id <ITEM_ID> \
    --project-id PVT_kwHOD5_Uxc4BXm5- \
    --field-id  PVTSSF_lAHOD5_Uxc4BXm5-zhSyoFY \
    --single-select-option-id f78f4d69     # Pipeline Status = shipped
  ```
  Option IDs for `Pipeline Status` (recorded only here): `proposed=eaebedb8, researching=9bc18971, approved=9b603bf5, building=44751778, shipped=f78f4d69, parked=a81222d7`.

**Idempotent and conservative.** Never closes an issue whose slug is not in the full index, nor a public one that is not yet live on `/api/skills`. Re-running with nothing newly shipped reports "0 to reconcile." End with the count closed and the marketplace link.

---

## Reuse, don't reinvent

`/zynkr-skills` is a thin coordination layer. It does **not** re-implement the logic in any sub-skill. Specifically:

- For state-aware routing patterns, see `../skill-triager/SKILL.md` (Step 2 "Detect the intake source" + Step 3 Option A/D switch) and `../skill-publish/SKILL.md` (Step 1 mode detection — continuation vs fresh-intake).
- For dedup / classify subagents, those are owned by `/skill-sourcer` (`../skill-sourcer/agents/{classifier,deduplicator,proposer}.md`). If `/zynkr-skills` needs classification, print `/skill-sourcer` and let it run those agents.
- For GitHub Project field IDs, use the `Pipeline Status` IDs recorded in the Reconcile sweep above; `../skill-triager/SKILL.md` records none (its Option D works on labels).

---

## Out of scope

The plan deliberately leaves these out of v1:

- **Broad drift / health checks** — orphan PRs, mismatched categories, stale branches. (The **Reconcile sweep** above now covers the specific “shipped but the issue is still open” drift; wider health-checking is still a separate concern.)
- **Fully automatic close-on-ship** — having every `ingest-skills.yml` run close the matching proposal with no human in the loop. The Reconcile sweep is the on-demand version; the hands-off CI version needs a cross-repo PAT secret and lives in the builder repo's workflows, not in this skill.
- **Scheduled digests** — weekly "here's what's stuck" reports. Use `/loop /zynkr-skills "what's in my queue?"` if you want that, no need to bake it in.
- **Replacing direct invocation of the sub-skills** — they remain first-class entry points. `/zynkr-skills` is one of several front doors, not the only one.

---

## Done

Summarise what you routed to and why. Example:

> Printed `/skill-sourcer <URL>` because the input was an `external-skill-url` (vercel-labs/skills/find-skills) with no prior pipeline state. Once you run it, it takes the extract → classify → dedup → propose chain.

Ask: **"Anything else to route?"**
