---
name: skill-triager
sheetId: "6.08"
description: "Triage the queue of approved skill proposals in peter-tu-zynkr/zynkr-skill-idea (label: triage-ready), present each as a one-screen review packet, and on assign-build fire a repository_dispatch event to zynkr-skill-builder so the pickup-approved-issue workflow scaffolds the SKILL.md. The DevOps-admin middle layer of the skill pipeline. Trigger on phrases like 'triage skills', 'review skill queue', 'skill triage', or '/skill-triager'."
category: engineer
project: skill-triager
platform: claude
status: WIP
visibility: public
author: Peter Tu
input: "None (reads triage-ready issues from peter-tu-zynkr/zynkr-skill-idea) — or a specific issue number"
output: "Issue labels swapped (triage-ready → building/parked/rejected/shipped), build target posted as an issue comment, and on assign-build a repository_dispatch to zynkr-skill-builder"
synergy: ["skill-sourcer"]
handoff: ["skill-author"]
disable-model-invocation: true
house-style: exempt — machine artifact — issue labels, no prose output

---

# Skill Triager

The **gate** of the skill-authoring chain — runs twice:

- **Option A `assign-build`** (front-gate): the second-look approval right after `/skill-sourcer`. Fires `skill-build-request` → `pickup-approved-issue.yml` opens a `skill/<slug>` PR with a stub for `/skill-author` to fill.
- **Option D `confirm-ship`** (back-gate): the audit closer after `/skill-publish` lands the SKILL.md on `main` and `ingest-skills.yml` indexes it. Read-only checks (the zynkr.ai one only for a skill marked `visibility: public`), a Sheet + Drive documentation pass, then flips the issue to `shipped`.

```
/skill-sourcer  →  /skill-triager  →  /skill-author   →  /skill-qa  →  /skill-publish  →  /skill-triager
                    Option A                              (QA gate)                       Option D
                    (this skill, front-gate)                                              (this skill, back-gate)
```

This skill is the **only authorised path** to fire a `skill-build-request` dispatch to `zynkr-skill-builder`. Manual `gh api dispatches` calls are fine for one-offs but should be tracked back onto the issue by hand (label + a comment saying what was dispatched).

---

## Step 1 — Pull the triage queue

Run:

```bash
gh issue list \
  --repo peter-tu-zynkr/zynkr-skill-idea \
  --label triage-ready \
  --state open \
  --json number,title,body,labels,url,createdAt \
  --limit 50
```

Show the user a numbered list: `#<num> — <title> (created <date>)`. Mark a **client build** with
**(client build)**: it was filed from a client's approved PRD by `/skill-sourcer`'s client-PRD intake. An issue is a
client build when it is labelled `client-build`, titled `[Client Build] …`, or carries `**Intake**: client-prd` in its
body. Any one of the three is enough; a missing label never makes it an ordinary idea.

If the queue is empty, report that and ask whether to also pull `skill-proposal`-labelled issues without the `triage-ready` label (these are issues that were created some other way and haven't been through `/skill-sourcer`). If yes, repeat the query with `--label skill-proposal --search 'no:label triage-ready'` semantics.

Ask: **"Which issue do you want to triage? (number, 'all' to process in order, or 'q' to quit)"**

---

## Step 2 — Build the review packet

For the chosen issue, gather and display in one screen:

1. **From the issue:** title, body, labels, author, URL.
2. **From the spec md:** fetch `skills/approved/{slug}.md` from `zynkr-skill-idea`:
   ```bash
   gh api repos/peter-tu-zynkr/zynkr-skill-idea/contents/skills/approved/{slug}.md \
     --jq '.content' | base64 -d
   ```
3. **From the issue's labels** — this is where pipeline state lives:
   - **Category** — the `category:<N>-<slug>` label (e.g. `category:0-strategy`).
   - **Pipeline status** — whichever of `triage-ready` / `building` / `parked` / `rejected` / `shipped` is present.
   - **Dedup verdict and Source URL** — from the issue body; `/skill-sourcer` writes a `**Source**:` line and its dedup finding into the body.

> **The Google Sheet is retired — do not read or write it.** `Zynkr Skills Pipeline`
> (`1_0bYyZ…`) was the pipeline SOT until the move to GitHub; its own header cell now
> reads *"⚠️ SOT moved to GitHub Project DO NOT EDIT THIS SHEET"*. Earlier versions of
> this skill still wrote `Pipeline Status` / `Build Status` / `Build Target` back to it,
> which meant triage was updating a retired store. Everything it used to hold is on the
> issue: status and category as labels, source and dedup verdict in the body, the slug
> in the title. The Sheet stays readable as the pre-cutover history.

Resolve the `slug` from the spec md path if one exists, otherwise from the issue title (kebab-case the post-`[Skill Proposal]` portion).

The build repo is always `peter-tu-zynkr/zynkr-skill-builder`. (`peter-tu-zynkr/zynkr-skills` is archived — if an issue body still names it, say so and carry on with the builder.)

### Detect the intake source

Read the intake source **off the issue body** — it changes the recommended decision in Step 3:

- **`/skill-sourcer`** (raw idea) → Step 3 defaults to **Option A `assign-build`** (the build hasn't happened yet). This is the default when the body carries no build markers.
- **client PRD** (a client build, Step 1, with no `**Built via**` line yet) → Step 3 defaults to **Option A**,
  which holds the build while the workbench is public. The PRD, deal and client folder are linked in the body; the
  acceptance criteria stay in the PRD.
- **`/skill-publish`** (built artifact) → Step 3 defaults to **Option D `confirm-ship`**. Recognised by a `**Built via**: skill-publish` line and a `**Built Skill URL**:` line in the body; the SKILL.md is already in-tree and the triager just verifies and closes the loop. A client build with these lines comes here too, and ships as a client build (Option D).

If the body says `**Built via**: skill-publish` but carries no `**Built Skill URL**:`, flag it: the publisher hasn't committed the artifact yet, and `confirm-ship` needs a committed file to verify against.

---

## Step 3 — Decide

Present the four options below. Wait for the user. The recommended default is set by the `Intake Source` check in Step 2.

### Option A — `assign-build`

The issue is ready to go into the build pipeline.

0. **A client build waits for a private workbench.** For a client build (any of the three markers in Step 1), ask
   GitHub first:
   ```bash
   gh api repos/peter-tu-zynkr/zynkr-skill-builder --jq .private
   ```
   Anything but `true` (`false`, an error, no answer) means **hold**: don't dispatch, because the scaffold would put a
   client's build in a public repo. Comment
   `Held: a client build is built only in the private workbench (SKB-038 flip pending, SKB-054).`, leave
   `triage-ready` on, and stop. On `true`, carry on. Every dispatch for a client build carries
   `-F "client_payload[visibility]=client"` (step 5), so `pickup-approved-issue.yml` skips the whole job if the repo
   is public after all. A web-app build (its body names another **Build Repo**) is built in that repo: record the
   decision as a comment and dispatch nothing.
1. **Confirm `Build Target`** with the user — defaults to the resolved slug, but the user can override (e.g. nest path like `engineer/video-use`).
2. **Ask the build mode:**
   > "Build mode? **rescaffold** (custom Zynkr skill body — for skills we'll implement ourselves) or **lift-and-shift** (mirror the upstream README as-is, set `status: Done` — for external skills we want to track without re-authoring)?"
   - Default: `rescaffold` if the issue has no upstream source URL.
   - Recommend `lift-and-shift` whenever the issue's **Source** field points to an external GitHub repo (i.e. anything except a Peter-authored skill).
   - On `lift-and-shift`, extract `upstream_url` from the issue body's `**Source**:` line (the skill-sourcer always writes it). If missing, ask the user.
   - On `lift-and-shift`, optionally ask for an `upstream_author` override (defaults to the GitHub org from `upstream_url`).
3. **Record the build target** on the issue — post it as a comment so the dispatch payload is auditable from the issue alone:
   ```bash
   gh issue comment <num> --repo peter-tu-zynkr/zynkr-skill-idea \
     --body "Triage: assign-build · target \`<slug>\` · mode \`<rescaffold|lift-and-shift>\`"
   ```
4. **Label swap on issue:**
   ```bash
   gh issue edit <num> --repo peter-tu-zynkr/zynkr-skill-idea \
     --remove-label triage-ready --add-label building
   ```
5. **Fire repository_dispatch:**
   ```bash
   gh api repos/peter-tu-zynkr/zynkr-skill-builder/dispatches \
     -X POST \
     -f event_type=skill-build-request \
     -F "client_payload[issue_number]=<num>" \
     -F "client_payload[issue_repo]=peter-tu-zynkr/zynkr-skill-idea" \
     -F "client_payload[slug]=<slug>" \
     -F "client_payload[category]=<category-number-or-slug>" \
     -F "client_payload[spec_url]=<URL of skills/approved/<slug>.md, if one exists>" \
     -F "client_payload[mode]=<rescaffold|lift-and-shift>" \
     -F "client_payload[visibility]=<client — only for a client build>" \
     -F "client_payload[upstream_url]=<github URL — only if mode=lift-and-shift>" \
     -F "client_payload[upstream_author]=<optional override — only if mode=lift-and-shift>"
   ```
   `mode`, `visibility`, `upstream_url`, `upstream_author` are optional — omit them entirely for the default rescaffold
   path. The scaffold reads the issue's client markers itself; `visibility=client` only lets the workflow skip the
   whole job while the repo is public.
6. **Verify dispatch landed:**
   ```bash
   gh run list --repo peter-tu-zynkr/zynkr-skill-builder \
     --workflow pickup-approved-issue.yml --limit 3
   ```
   Report the run URL to the user.

### Option B — `defer`

Not now, but don't reject.

1. **Labels:** swap `triage-ready` → `parked`. (The label *is* the status — there is nothing else to update.)
3. Optionally prompt the user for a `parked-reason` comment to post on the issue.

### Option C — `reject`

Not happening.

1. **Labels:** add `rejected`, remove `triage-ready`.
2. **Close issue:**
   ```bash
   gh issue close <num> --repo peter-tu-zynkr/zynkr-skill-idea \
     --comment "Triage decision: rejected. <reason>"
   ```
   Ask the user for a one-line reason.

### Option D — `confirm-ship`

The artifact is **already built and committed** (typical for `/skill-publish` intakes). No scaffold is needed — just verify it landed correctly and close the loop on the issue.

> **QA is pre-ship; confirm-ship is post-ship.** By the time you reach Option D the skill has *necessarily* passed QA — the PR could not have merged otherwise, because the `qa.yml` / `publish-skill.yml` QA check blocks any ERROR-tier skill. So Option D does **not** re-run QA; it trusts the merged PR's green QA check as the receipt and verifies the *live* artifact (the post-ship checks below).

**Precondition:** the issue body has a `**Built Skill URL**:` line. If it doesn't, tell the user "the SKILL.md hasn't been committed yet — commit to `zynkr-skill-builder`, then come back" and exit this option.

1. **Confirm the in-tree path** — derive `<path>` from `Built Skill URL` (e.g. `skills/6-engineer/skill-publish/SKILL.md`) or fall back to `skills/<N-cat>/<slug>/SKILL.md`.
2. **Verify the file is live in `main`:**
   ```bash
   gh api repos/peter-tu-zynkr/zynkr-skill-builder/contents/<path> --jq '.path' \
     || echo "MISSING"
   ```
   If `MISSING`: stop, report to user, leave labels untouched for retry.

   Then read the skill's **mark** — the `visibility` key in that file's frontmatter. No key means `team`:
   ```bash
   gh api repos/peter-tu-zynkr/zynkr-skill-builder/contents/<path> -H 'Accept: application/vnd.github.raw' \
     | awk 'NR==1 && /^---/ {f=1; next} f && /^---/ {exit} f && /^visibility:/ {print $2}'
   ```
   `public` → the skill also goes to the public shelf and zynkr.ai, and every step below applies. Anything else is a **team** skill: it lives only in this workbench, so it is shipped once it is on `main` (step 2) and in the full index (step 3) — skip step 4 and use the team wording in steps 6 and 8.
3. **Verify ingest has run** — check the workbench's full index (public and team skills alike; the workbench is private, so read it with `gh`, never an unauthenticated URL):
   ```bash
   gh api repos/peter-tu-zynkr/zynkr-skill-builder/contents/generated/skills-index.json -H 'Accept: application/vnd.github.raw' \
     | python3 -c "import sys,json; print(any(s.get('slug')=='<slug>' or s.get('name')=='<slug>' for s in json.load(sys.stdin)))"
   ```
   If `False`: the most recent push hasn't been ingested yet. Either wait for `ingest-skills.yml` to finish (check `gh run list --workflow ingest-skills.yml --limit 1`) or proceed and let the next ingest catch it.
4. **Public skills only — verify the live API serves it.** zynkr.ai lists public skills only, so a team skill is never there and this check does not apply to it.
   ```bash
   curl -sL https://www.zynkr.ai/api/skills \
     | python3 -c "import sys,json; print(any(s.get('slug')=='<slug>' or s.get('name')=='<slug>' for s in json.load(sys.stdin)))"
   ```
   If `False`: the shelf has not published it yet. `export-stage.yml` stages the public skills after each push, and the shelf (`peter-tu-zynkr/zynkr-ai-skills`) picks the stage up on its next run. A skill **new** to the shelf is held there until the owner dispatches the shelf's workflow with `promote` naming its sheetId (`gh workflow run export.yml -R peter-tu-zynkr/zynkr-ai-skills -f promote=<sheetId>`; a slug works too). The run summary lists held skills by sheetId, never by slug (a new folder may be a client build marked public by mistake). A new sub-agent inside a skill the shelf already publishes isn't held; it goes out on the next run. Re-check before flipping status.
5. **Document it in the Sheet and the Drive mirror** — the two surfaces CI never touches. The pipeline stops at git (and, for a public skill, the shelf → Supabase → marketplace); the portfolio index and the Drive library are written by hand or not at all. Both are **team** surfaces: document team skills here exactly as public ones. Read `./references/index-and-mirror.md` for the committed folder IDs, the column contract and the staging rules. The shape of the work:
   - **Drive — always:** create `1 Skills/<category folder>/<slug>/` and upload the merged `SKILL.md` as `text/markdown`.
   - **Drive — only when the skill ships knowledge:** if
     ```bash
     git ls-tree -r --name-only origin/main -- "skills/<N-cat>/<slug>" | grep -v '/SKILL\.md$'
     ```
     lists anything, create `2 Knowledge/<slug>/` and upload those files **flattened** (`references/foo.md` → `references__foo.md`). A SKILL.md-only skill gets **no** knowledge folder and leaves column `N` blank. ⚠️ Some such skills already have a legacy `_SOURCES.md`-only folder from the 2026-08-28 pass, and their `N` reads `1 file` — that is the older of two competing definitions of the column. Leave those folders alone; the reference explains which definition to write and why the two disagree.
   - **Sheet:** find the row by its `sheetId` in column `C` (append one if the skill is new), then write the four link cells — `C` → GitHub blob (the shelf `zynkr-ai-skills` for a public skill, this workbench for a team skill), `M` → the Drive `SKILL.md` file, `N` → the knowledge folder, `AG` → the skill folder — as `=HYPERLINK("<url>","<label>")` with `value_input_option="USER_ENTERED"`.

   Verify before moving on: re-read `M`/`N`/`AG` and confirm each returns a hyperlink rather than plain text, and that the uploaded file's frontmatter `name` matches the slug — a mis-parented file looks correct in the Sheet and opens the wrong skill.

   **This step does not gate the ship.** The skill is already shipped by the time you get here (on `main`, in the index and, if public, on the marketplace), so a Drive or Sheets failure is a bookkeeping debt, not a broken release: say exactly what is missing, name it again in the Step 5 report, and continue to the next step rather than leaving the issue open.

6. **Post the verification receipt** as an issue comment — the confirmed GitHub path, plus the marketplace URL for a public skill, so the shipped state is self-evidencing from the issue:
   ```bash
   # public skill
   gh issue comment <num> --repo peter-tu-zynkr/zynkr-skill-idea \
     --body "confirm-ship: in main at \`<path>\` · live at https://zynkr.ai/s/<sheetId> · indexed in the Skills Index Sheet + Drive [6.2]"
   # team skill — no zynkr.ai line; it is not there by design
   gh issue comment <num> --repo peter-tu-zynkr/zynkr-skill-idea \
     --body "confirm-ship: in main at \`<path>\` · team skill, in the workbench index · indexed in the Skills Index Sheet + Drive [6.2]"
   ```
7. **Label swap on issue** — remove whichever of `triage-ready` and `building` the issue carries (an Option A build
   carries `building`; a `/skill-publish` fresh intake carries `triage-ready`), then add `shipped`:
   ```bash
   gh issue edit <num> --repo peter-tu-zynkr/zynkr-skill-idea \
     --remove-label building --add-label shipped        # or --remove-label triage-ready
   ```
8. **Close the issue:**
   ```bash
   # public skill
   gh issue close <num> --repo peter-tu-zynkr/zynkr-skill-idea \
     --comment "Triage decision: confirm-ship. Live at https://www.zynkr.ai/ai-skills-marketplace (slug: <slug>). Verified via gh contents + skills-index + /api/skills."
   # team skill
   gh issue close <num> --repo peter-tu-zynkr/zynkr-skill-idea \
     --comment "Triage decision: confirm-ship. Team skill on workbench main (slug: <slug>). Verified via gh contents + the workbench skills-index."
   ```
9. **Offer to install it into the local runtime (author convenience — closes the publish↔invoke gap).** Shipping does **not** install the skill into your own `~/.claude/skills/`, so it is **not invocable in your Claude Code session** until added. Offer to run it now — use `npx skills add` (not the single-file `curl …/s/<id>.md` install) so multi-file skills bring their `references/` along:
   ```bash
   npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill <slug>
   ```
   That is the public shelf. For a **team** skill swap in the workbench URL, `https://github.com/peter-tu-zynkr/zynkr-skill-builder` — that install works only for workbench collaborators.
   On the user's OK, run it and confirm `~/.claude/skills/<slug>/SKILL.md` exists. Skip the offer for non-Claude skills (platform `gpt` / `gemini`) or if the user declines — the ship itself already succeeded regardless.

**A client build** (any of the three markers in Step 1) ships like a team skill: no zynkr.ai check in step 4, the team wording in
steps 6 and 8. Skip step 9: a client build is delivered to the client, not installed here. End by pointing at
`/skill-deploy`, which records where the build runs once it is deployed (staging first, for UAT).

**Why this is different from `assign-build`:** no `repository_dispatch` is fired — the in-tree SKILL.md is already picked up by `ingest-skills.yml` on push, so its index row already exists by the time triage runs (and, for a public skill, the shelf publishes it on its own schedule). Triage's job here is **bookkeeping + verification**, not orchestration.

**Fall-back to `assign-build`:** if for any reason a `/skill-publish` item arrives without a committed artifact (e.g., publisher only created the issue, didn't commit), `assign-build` with `mode=rescaffold` will work — `pickup-approved-issue.yml` is idempotent and won't overwrite an existing file. But this should be rare; the publisher's intended path is commit-then-confirm.

---

## Step 4 — Loop or stop

After each decision, ask: **"Next issue? (number / 'all' to continue / 'q' to stop)"**

In `all` mode, automatically pick the next issue in queue order and return to Step 2.

---

## Step 5 — Report

When the session ends, summarise:

- Triaged: N
- Dispatched to build: M (with workflow run URLs)
- Confirmed-shipped: S (with marketplace URLs for public skills; team skills by path)
- Indexed: the Sheet rows and Drive folders written — and any skill left undocumented, with the reason
- Deferred: D
- Rejected: R

**Completion checklist (per dispatched issue — Option A):**
- [ ] Build target recorded as an issue comment
- [ ] Issue label `triage-ready` removed, `building` added
- [ ] `repository_dispatch` fired to `zynkr-skill-builder`
- [ ] `pickup-approved-issue` workflow run observed

**Completion checklist (per confirmed-shipped issue — Option D):**
- [ ] `gh api contents` confirmed the SKILL.md is in `main`, and its `visibility` mark read (no key = team)
- [ ] `generated/skills-index.json` (the full index, via `gh api`) contains the slug
- [ ] Public skills only: `/api/skills` returns the slug
- [ ] Drive mirror written — `1 Skills/<cat>/<slug>/SKILL.md`, plus `2 Knowledge/<slug>/` **only if** the skill ships files besides its SKILL.md
- [ ] Skills Index Sheet row present and columns `C`/`M`/`N`/`AG` re-read as live hyperlinks (or the gap named in the report)
- [ ] Issue label swapped to `shipped` (the label is the status of record)
- [ ] Public skills: marketplace URL posted on the issue if it wasn't already
- [ ] Issue closed with verification comment
- [ ] Local install offered (`npx skills add … --skill <slug>`) — run on user OK, or skipped for non-Claude skills / on decline

---

## Error handling

- **Issue has no `category:` label:** ask the user which of the 0–9 categories applies, then add the label before dispatching — the scaffolder needs it to pick the folder.
- **Spec md not found at `skills/approved/{slug}.md`:** continue with title-derived description, but flag it to the user; the scaffolder will leave a `_No spec md found_` marker in the SKILL.md. (Most issues have no spec md — only one exists in the repo today — so treat this as the normal case, not an error.)
- **Dispatch returns non-2xx:** report the error and roll back the label swap so the issue stays `triage-ready` for retry.
