# Source map — the SOR read set (roles, not IDs)

Every source is addressed by its **role key** in the private config (`config.example.json`); the real Drive ID is resolved at runtime from `sources.<key>.id`. Never hard-code IDs in this repo. Read only the authoritative slice named below — the rest of each doc is downstream copy and loses on conflict.

| Role key | What it is | Authoritative slice (read ONLY this) | Rank | Read policy | Cloud (Drive connector) | Local (workspace-mcp) |
|---|---|---|---|---|---|---|
| `sources.vms_v2` | Vision-Mission-Strategy v2 (Doc) | TOP section "H2 2026 alignment" only. Body = May snapshot; alignment section wins on conflict. Thesis, two levers, cuts, guardrails. | 1 | on `modifiedTime` change; force monthly | read | read |
| `sources.integrated_refresh` | H2 2026 Plan — Integrated Refresh (Doc) | "2026-07-28 Refresh (v2)" addendum only: 減法 thesis, P0 list (14), management fixes, open decisions, four constraints C1–C4. §1–§13 lose. | 1 | on `modifiedTime` change; force monthly | read | read |
| `sources.main_tracker` | H2 Planning Main Tracker (Sheet) | tab 「H2 專案項目」 — cols `#` · `項目` · `Priority` · `負責人` · `開始` · `結束` · `狀態` · `備註` (also 主類別/子類別/重要/緊急/協助者; keep). **THE status source** for scope · priority · owner · status. Vocab: 未開始 / 進行中 / 放棄 / 完成 / 暫停 (完成 · 暫停 added 2026-08-24; there is still no 延遲). 完成 and 放棄 are terminal — drop them from open-work counts and owner load; see `derived-state-rules.md`. Other tabs (H1 回顧總結, 專案項目小記, ②③④) = reference only. | 2 | every run | read (`get_file_metadata` MAX_ALLOWED, then the `# H2 專案項目` section; never `read_file_content`, which samples ~22 rows) | read (`read_sheet_values` on the tab, resolve columns by header text) |
| `sources.ledger` | [3.3] Weekly Ledger 週帳本 (Sheet) — **machine-owned** by zynkr-ops-weekly (SKB-044) | Fixed rows per ISO week k (from `epoch_week`): `Weeks` row 2+k (which beats recorded the week · approval state in O/Q) · `Snapshot` rows 2+100k… (a full tracker copy every Friday) · `Reports` / `Decisions` 2+20k… (Monday posts · Thursday's 決議 / 待決) · `Proposals` / `Updates` 2+40k… (Friday approvals · applied changes). `scripts/ledger_read.py` computes every range. **Evidence and history, never status**: it records the tracker, it does not replace it. | 3 | every run | read (`get_file_metadata` MAX_ALLOWED → CSV per tab; see *How to read a Sheet in the cloud*) | read (`read_sheet_values`, ≤50 rows per range, via `ledger_read.py`) |
| `sources.ops_weekly` | [3.1] 營運每週彙報 Operation weekly (Doc, tab 「每週事項 2026」) | Newest `## <Mon DD, YYYY>` block only (newest first; blocks are Thursday-dated). STALLED needs the newest **two** blocks. Fixed skeleton: `#Team update` · `#Demand Marketing` · `#Sales` · `#Operation` · `# Knowledge product` · `# AI enablement` (+ Tech product · People · Finance), each with `Metrics:` bullets (mostly bare `#`). | 3 | every run | read (large → extract) | read (large → extract; see below) |
| `sources.okr_kpi_tracker` | H2 2026 — OKR & KPI Tracker (Sheet) | tabs `OKRs` (O1–O5, Q3/Q4 targets, Status) + `KPI Dashboard` (19 metric rows; `Actual` column). Tab `Initiatives Q3-Q4` is a **stale mirror** of the tracker — never read for status. May also host the skill's state tabs (see SKILL.md). | 4 | KPI Dashboard every run; OKRs at month / quarter | read | read + cell write (`modify_sheet_values`, P1 only) |
| `sources.ops_heal_tracker` | Ops H2 gap-audit 行動追蹤表 (Sheet) | tabs `修復清單` (heal list, progress SOT for 3.x) + `待決事項` (open decisions → brief ④). | 5 | every run | read | read |
| `sources.course_tracker` | Course project tracker (Sheet) | tab `專案管理總表` — task status/dates for 4.05 / 4.07 (Claude Code course line). project-status-update owns the email; zynkr-gm reads status only. | 5 | every run | read | read |
| `sources.finance_ledger` | **Zynkr Finance Ledger (Sheet) — THE books** | tab `Monthly Summary` for runway/burn (cash = cumulative `total` at the last closed month; burn = mean `net` over `constraints.burn_window`); tab `Income` for cash-basis revenue (2.06); tab `Transactions` for `max(date)` = books-as-of. Bank-reconciled to the 富邦 statement monthly. **`never_write: true`** — appends belong to `/zynkr-accounting`, and the `Financial Model` tab's month columns are spilled arrays that break on write. | 5 | every run | read | read |
| `sources.knowledge_directory` | GM Knowledge Directory (Doc) | SOR precedence table + `核心文件` entries + `Maintenance` rules. Governance input for `learn`. | gov | monthly (`learn`) + on `modifiedTime` change | read | read; append-only write via `learn --apply` |
| `sources.org_taxonomy` | Org Taxonomy (Doc) | live tab "Org Taxonomy v2" — LOB 0–9 + DRIs. Owner resolution. | gov | monthly | read | read |
| `sources.plan_docs.<lob>` | 7 function plans: `1.0` `2.0` `3.0` `4.0` `6.0` `7.0` `8.0` (Docs, single tab) | TOP "2026-08-06 Refresh — aligned to the H2 Planning Main Tracker" block only (P0/P1 tracker IDs + owner + optional date range; retired KPIs; 已定案/還在摸索 labels). Where a later "2026-08-10 Addendum" exists it wins over both. **No status lives here.** Body §1–§9 = May cut, superseded. Note: tracker `#` renumbered 2026-08-21 to match Org Taxonomy v2 — Tech = `6.x`, People = `7.x` (no translation needed; OKR-tracker `Tracker #` refs updated same day). 8.0 has no tracker rows; EAE (LOB 5) is tracked under 4.01. | 6 | on `modifiedTime` change only (key doc-watch on target IDs, not H2-folder shortcuts) | read | read |
| `sources.eae_readme` | [5.0] Enterprise AI Enablement — README (Doc) | 1-page pointer (五階段交付, consult-* chain, offering SOR link). Not a plan; no tracker rows of its own (EAE lives under 4.01). | 6 | on `modifiedTime` change | read | read |
| `sources.skills_knowledge_map` | [6.0] Zynkr Skills Knowledge Map (Doc) — **the skills KB** | ONE category section per read: the `## <N>. <Category>` heading matching the LOB in hand (e.g. `## 0. Strategy & Leadership 策略與領導`), plus `## At a glance` when you need the totals and `## The Skill Map — six pages` when the question is which team runs what (each page's teams and counts, with links). Each `### slug (id)` under a category carries the skill's one-liner, source count, readiness, its **Skill Map home** (`Skill Map: <page> · <team>` — the one page it counts on, SKB-068) and, for a parent skill, its sub-agents. Appendix A = broken/dead knowledge sources; Appendix B = most-shared docs. **This is the answer to "what skills exist now"** — never keep a skill list in this repo. | 6 | on `modifiedTime` change (it is regenerated, not hand-edited) | read | read |
| `sources.livestream_notes_folder` | 直播筆記 output folder (Drive folder) | Newest file `modifiedTime` only — health check that curate-livestream-transcripts ran this week. Never run it. | health | every run | list | list |
| `sources.move_log` | GM knowledge move log (Sheet) | append one row per `learn --apply` change (before → after). | gov | write on `learn --apply` | — | append |
| `sources.core_folder` / `sources.h2_planning_folder` | Drive folders holding the 0-level originals / the H2 suite | folder listings for `learn` drift (name · type · modifiedTime · shortcut target). | gov | monthly | list | list |
| `sources.onboarding_master` | Onboarding 母本 (shared facts) | read for ⛔ deprecated paths only. `never_write: true` — shared-fact changes are proposed, never applied. | gov | monthly | read | read |

Non-Drive reads (tools, not `sources.*` keys): CRM via `mcp__zynkr` (`list_deals`, `list_tasks`) for 2.x / 4.01; CMS Supabase `articles` for 1.03; Calendar for the calendar clock (cloud connector only — the workspace-mcp Calendar API is disabled locally). See `kpi-map.md`.

The GM's own week: the `[Weekly Insights] <week>` mail that `/weekly-insights run` sends from the GM's laptop once a week, when the week closes on Wednesday evening (Gmail — cloud: `search_threads` + `get_thread`; local: the Gmail search tools). Read ONLY the plain-text block between `=== FOR THE GM BRIEF · <week> ===` and `=== END ===`. Rank: evidence, alongside the function SOTs — it fills the GM's block-04 line, feeds block-03 `PROPOSE_DONE` evidence and block 08, and never changes status. Absent → block 08 says the laptop recap did not arrive. See SKILL.md §3.4b.

The team's week, from zynkr-ops-weekly's mail (subjects and links only, never bodies): the Monday team recap `【週報】WB m/d 那週 — …` (or its notice `【週報】… 那週沒有產出…`), linked from block 03 when it has already arrived; it often lands after 09:00, so its absence is never a failure. A `【週報】` subject containing `沒有產出` is the recap's owner-only notice that Friday's snapshot never ran: report it in block 08, never as a change list. The Friday approval mail `【待核准】WB m/d 那週 · N 件（<ISO week>）`, linked as the close-it target of an unconfirmed approval. Both are sent from the GM's own account, so they sit in Sent. See SKILL.md §3.1b.

## How to read a Sheet in the cloud

The Drive connector's `read_file_content` **samples** a Sheet: about 22 rows of a wide tab and about 40 of a narrow one, then stops without saying so. The Main Tracker read that way ends at row 2.08 of 55. Use `get_file_metadata(fileId, snippetVerbosity: MAX_ALLOWED)` instead: its `contentSnippet` holds every tab as a `# <tab>` heading followed by CSV, with every row. The W41 routine (2026-10-05) found this out on its own. Three limits:

- The CSV is **not quoted**. A cell's commas and line breaks come through raw, so a free-text cell (備註, 內容, 原因, 上週, 本週, 卡關) splits its row into extra fields and extra lines. A data row is a line that starts with its key (a tracker `#`, a week key); other lines continue the previous row's free text. Read a row only by the fields before its first free-text column.

- The whole response is capped at about 80k characters, and tabs come in sheet order. When the snippet ends before a tab you need, say so in block 08 rather than reading what is there as complete. The Ledger is the case to watch: `Snapshot` grows about 11k characters a week, keeps its oldest weeks first and sits before `Reports`, `Decisions` and `Proposals`, so after about six weeks (mid-November 2026) the cloud read loses the newest snapshots and every tab after them. CHANGED and STALLED then come from local runs only.
- CSV drops a row's leading empty cells. A `Weeks` row whose first field is not an ISO week key (e.g. `ok,2026-10-06T09:10…`) has lost its column positions: treat that week as "no snapshot recorded" and do not read its other cells.

When the result is too big for one tool reply, the harness saves it to a file: slice that file with python, one `# <tab>` section at a time.

⚠ Runway / burn used to be listed here as "accounting Supabase". **That was never true** — the `zynkr-accounting` app is stalled and holds no books. Since 2026-09-13 the source is `sources.finance_ledger`, a Drive Sheet, which is why runway is now computable on a scheduled cloud run as well as locally.

## Precedence

- Strategy: `vms_v2` "H2 2026 alignment" > VMS body. `integrated_refresh` addendum > its §1–§13. When the two alignments differ, the newer dated block wins and the brief cites both dates.
- Plans: Refresh block (and any later dated addendum) > plan body.
- Status / scope / owner: **Main Tracker** > OKR & KPI Tracker (OKRs; Initiatives tab is stale) > plan docs > narrative docs. Function SOTs (`ops_heal_tracker`, `course_tracker`, `finance_ledger`, CRM) are evidence for progress, never for scope.
- The Weekly Ledger (`sources.ledger`) is the cycle's record: its `Snapshot` is last Friday's copy of the tracker (for CHANGED and STALLED), never a substitute for reading the tracker today. Its `Decisions` and `Reports` rank with the weekly log as evidence of what happened; for what was posted or decided in a given week, prefer the Ledger, which is stamped once for that week, over the weekly-log Doc, whose blocks are copied forward and can show last week's text under this week's date.
- Never restate a number from a narrative doc; every number cites SOR + as-of date.

## ⛔ Deprecated paths (from the 母本; respect, never resurrect)

- Knowledge-Management product line **paused for H2** (both B/C routes 放棄).
- Career Development line = **harvest-only** (no new build).
- No retired pricing tiers (Skool / Marketplace pricing, old B2C tiers) — pricing SOR is the offering sheet, not plan docs.
- No Custom GPTs.

## How to read a big doc

`get_doc_as_markdown(document_id, include_comments=false)` has no range/tab parameter; `ops_weekly` (~266k chars), `vms_v2` and the plan docs will overflow context. Procedure: (1) call with `include_comments=false`; (2) when the harness saves the oversize result to a file, do NOT read it whole — run `python3 scripts/extract_newest_block.py <dump-file> --blocks 1|2` (weekly log: newest `## <Mon DD, YYYY>` block(s)) or `--heading "H2 2026 alignment"` (VMS) · `--heading "2026-08-06 Refresh"` (plan docs; `--heading "2026-08-10 Addendum"` too where one exists, it wins) · `--heading "2026-07-28 Refresh"` (integrated_refresh). Always name the dated heading: `--heading` takes the first heading containing the text, and a bare "Refresh" matches the Integrated Refresh doc's own title, whose section is the whole doc; (3) read only the extract. Gate every plan-doc / VMS read on `modifiedTime` from the doc-watch state so steady-state runs read no plan doc at all. Cloud (Drive connector `read_file_content`) returns the same full text — apply the same extract before reasoning.

`skills_knowledge_map` is the same shape (~230k chars since the 2026-10-07 rebuild, one `##` per category): dump it, then
`python3 scripts/extract_newest_block.py <dump-file> --heading "0. Strategy"` — one category, never the whole Doc
(`--heading "The Skill Map"` for the team view). `--heading` takes the first heading containing the text and ignores
the export's `0\.` escapes and `&amp;`; with no match it exits 1 and prints the Doc's top headings. It also reads the
dump file as the harness saves it (JSON, `{"result": …}`). (Until SKB-068 the script had no `--heading` at all, though
this file named it for the VMS and plan docs since SKB-006 and for this Doc since 2026-08-17 — a run that tried it was
refused, then read the wrong slice or the whole dump.)

## Freshness — the skills KB is a render, not a live feed

The Knowledge Map is **generated** by `scripts/skills-index/build_knowledge_doc.py` in
`zynkr-skill-builder`; it is only as current as the last rebuild. So do not trust it blind — check
it against the workbench's full index (public and team skills), which costs one call:

```bash
gh api repos/peter-tu-zynkr/zynkr-skill-builder/contents/generated/skills-index.json \
  -H 'Accept: application/vnd.github.raw' | python3 -c "import json,sys; print(len(json.load(sys.stdin)))"
```

(The workbench is private, so this needs `gh` signed in as a collaborator; without it, say the count
was not checked. Never count `zynkr.ai/api/skills` instead: it lists public skills only.) Compare that count with the
**index rows** number that opens the `## At a glance` → *Skills covered* line (`138 index rows: 105 skills and 33
sub-agents…`) — rows with rows, sub-agents included. (Before SKB-068 that line counted skills only, so this check read
"47 behind" on 2026-10-06, when the Doc lacked 15 skills and still listed one retired.) If the registry is ahead, say so in the brief's
evidence line — **"skills KB is N behind, re-run build_knowledge_doc.py"** — and treat the Doc as a
floor, not a ceiling. Never silently brief off a stale KB, and never patch the gap by typing skill
names into this repo: the fix is always to regenerate the Doc.
