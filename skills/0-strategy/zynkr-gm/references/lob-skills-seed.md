# LOB → instrument-skills (H2 2026)

## Read the KB, not this list

**What skills exist is not written down here.** It is read at run time from
`sources.skills_knowledge_map` — the [6.0] Zynkr Skills Knowledge Map Doc — one `## <N>. <Category>`
section per LOB (see `source-map.md` for the extract + freshness check). Category number = LOB
number, so "which skills does 3.0 Operations have" is one heading lookup.

This file holds only what the KB **cannot** tell you, and which therefore has to be curated:

1. **Chain order** — the KB lists skills; it does not say `seo-program-planner` runs before
   `seo-article-pipeline`, or that the consult-* chain has a fixed sequence.
2. **Which skill moves which tracker item** — the mapping from an H2 P0/P1 number to an instrument.
3. **Gaps** — a skill that does not exist cannot appear in the KB. Only a human notices absence.
4. **Tracker numbering quirks** — none since the 2026-08-21 renumber: tracker `#` now matches the LOB number (Tech = `6.x`, People = `7.x`).
   5.0 Product and 8.0 Finance have no tracker rows.

So: the KB answers *what exists*, this file answers *what to reach for and in what order*, and
skill-finder (5.01) answers *which skill for an arbitrary task*. When the two disagree about
whether a skill exists, **the KB wins and this file is stale** — say so in the brief rather than
quietly trusting the table below. Never add a skill name here to "fix" a KB that is behind;
regenerate the KB instead.

⚠️ The columns below name skills as of 2026-08-17. Treat them as a curated reading of the KB, not
as the registry.

| LOB | H2 P0 / P1 items | Instrument skills (chain order where it matters) | Gaps (no skill) |
|---|---|---|---|
| 0 Strategy | — | **zynkr-gm** (0.02, this skill) + the **planning cycle suite** (0.03–0.10), which runs in cycle order: `planning-prework-pack` → `planning-1on1-annual-digest` (per person) + `planning-evidence-pack` (the numbers) → *the room* → `planning-session-synth` → `planning-tracker-builder` → `planning-suite-reconciler` → then weekly `planning-tracker-sync`, with `planning-lob-gap-audit` per LOB after. Nearest neighbours project-planning · admin-governance · product-planning | org design; performance/KPI *system* (7.01) — the metering exists, the policy does not |
| 1.0 Marketing & Brand | P0 1.08 電子報; P1 1.01 About · 1.02 Story line · 1.03 SEO 文章 · 1.09 re-engage · 1.10 見證 · 1.11 合作廠商 | 1.08 → content-newsletter-draft · zynkr-content-writer · content-governance; 1.03 → seo-program-planner → seo-article-pipeline (persona → questions → angles → keywords → intent → demand → brief → outline → finalizer) → seo-publish-article; 1.02 → zynkr-slide / slide-storyline-designer; social → social-publish-article · content-fission; 1.09 → sales-client-sourcing (list enrichment) | 1.05 成效分析 · 1.06 Google Ads · 1.10 見證 · 1.12 Referral |
| 2.0 Sales & Consulting | P0 2.01 業務流程結構化 · 2.02 業務 On-board · 2.03 分潤系統 · 2.04 企業戶陌生開發 · 2.06 高 LTV 課程 | pipeline review → sales-manager (conducts the sales skills below); 2.04 / 2.06 → sales-outbound · sales-research · sales-follow-up · sales-client-sourcing · sales-specialist · sales-inbound; 2.01 → ops-flow-optimization · ops-transformation · ops-workflow-design; 2.02 → training-* · zynkr-recruiter (onboarding side) | 2.03 分潤 (finance logic) · 2.08–2.13 標案 / 補助 / 參展 / 通路 |
| 3.0 Operations | P0 3.02 內部講師 · 3.04 加開線下場次; P1 3.01 LINE@ · 3.06 內部導入 Zynkr | 3.04 → accupass-agent · guest-lecturer-program · admin-meeting-prep; 3.06 → zynkr-support · zynkr-kms · admin-governance · skill-finder; hygiene → project-status-update · project-note-specialist · admin-video-document | 3.01 LINE@ 營運 (LINE connector is platform-side, not a skill) · 3.02 內部講師 · 3.05 Metrics 儀表 |
| 4.0 Knowledge & Training | P0 4.01 企業 AI 診斷 · 4.05 陪跑課 · 4.07 Vibe Coding; P1 4.04 Workshop | 4.01 → consult-* chain: sales-inbound → sales-discovery (as-is / to-be) → consult-transcriber → consult-session-notes → consult-solution-planning → consult-flow-design → consult-brd-writer → ops-prd-writer → gtm-uat-writer → gtm-launch-comms → gtm-info-session → project-client-status → gtm-adoption-reporter → project-governance; 4.05 / 4.07 → project-status-update · training-lecture-transcript · training-lecture-recap · training-process-video · curate-livestream-transcripts · training-srt-*; slides → zynkr-slide; KB → zynkr-kms / zynkr-support | 4.14 訂閱制 · 4.15 會員經營 |
| 5.0 Product (taxonomy only) | — | product-planning · ops-workflow-design · product-optimize-prompt · skill-finder | — |
| 6.0 Tech & Platform (tracker 6.x) | P0 6.02 使用 Zynkr 並擴展功能 · 6.03 業務團隊分潤系統; P1 6.01 課程平台 | shipping gates for the product repos (SKB-057–060) → eng-preflight · eng-migration-guard · eng-verify · eng-ship-watch; meta / skill-pipeline tooling: zynkr-skills · skill-sourcer · skill-triager · skill-qa · skill-publish · eng-find-skills · agent-browser (Vercel / Supabase plugin skills exist runtime-only) | platform build / ops (deploy, incident, 分潤 billing) — no builder skill |
| 7.0 People & Talent (tracker 7.x) | P0 7.01 KPI 制度; P2 7.03 Training | zynkr-recruiter + recruiter-* (hiring); cv-customizer · career-consult (candidate side); training-* for 7.03 | 7.01 KPI / performance (zynkr-gm partly fills the metering) · org design · onboarding |
| 8.0 Finance / 9.0 Legal | not in tracker | **zero skills**; runway meter = zynkr-gm reading `sources.finance_ledger` (the Sheet, not the stalled accounting app); monthly close = `/zynkr-accounting` | everything (accounting lives in the app, not a skill) |

Refresh cadence: the *existence* half needs no refresh — it is read from the KB every run. `learn`
re-derives the curated half (chain order · item→instrument mapping · gaps) from the KB + the tracker
each quarter, or on demand when a skill ships; the brief only cites deltas.

## Boundary — who owns the weekly

Category 0 now has two weeklies, and they are not the same artifact. Do not answer for the other:

| Ask | Owner |
|---|---|
| 「GM 週報 / 這週重點 / 本週 focus / 本月重點 / 哪些 P0 delay 了 / H2 進度盤點 / KPI off-target」, runway, the founder brief | **zynkr-gm** (this skill) |
| 「tracker 同步 / Team Weekly 的 tracker 區塊 / 誰該被 nudge / snapshot the tracker」 | `planning-tracker-sync` (0.09) |
| 「週報」 bare, "weekly report", the Monday cron on the course project | `project-status-update` (3.09) |
| The team's weekly loop: Monday `#週報` posts, the Thursday meeting's decisions, the Monday `【週報】WB m/d` team recap, the Friday 【待核准】 tracker approvals, and the Weekly Ledger behind them | `zynkr-ops-weekly` (3.19, SKB-044). zynkr-gm only **reads** its Ledger (§3.1b) |
| 「什麼 deal 該追」, pipeline review, a stalled deal | `sales-manager` (REVIEW mode). The brief names the pipeline's state at LOB level and routes deal-level work there |

`planning-tracker-sync` derives per-item state with **this skill's rules** — it holds a verbatim copy
of `derived-state-rules.md` and calls `scripts/derive_state.py` when zynkr-gm is installed. So does
`zynkr-ops-weekly`'s Monday recap (`recap.py` runs the installed `derive_state.py` on two Ledger
snapshots). That makes zynkr-gm the upstream owner: changing a threshold, a state name or
`derive_state.py`'s input keys changes the team weekly and the team recap too. See the consumer
note at the top of `derived-state-rules.md`.

**The tracker is getting one writer.** Under SKB-044 the Main Tracker's 狀態 · 結束 · 備註 are
meant to change only through the Friday cycle: `propose` mails the GM a list, the GM approves by reply, and `apply` writes
the approved values (while `apply_mode` is `shadow` it records them and writes nothing, so owners
still type by hand). A hook refuses every other tracker write, but only inside zynkr-ops-weekly's
own beats; people can still edit the sheet. So a brief that finds a finished or re-dated item
places it in the Friday cycle, and asks the owner to type it only while the cycle is in shadow.
