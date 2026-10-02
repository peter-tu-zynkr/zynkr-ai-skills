# Hygiene checklist — the six portfolio invariants

This file is the contract for `/project-governance` step 4. Each invariant
defines: **what it checks**, **how** (tool + field), **what a violation looks
like**, and the **proposed-fix line format** the report must use. The skill is
READ-ONLY — every fix here is a *proposal* routed to the skill that owns it.

**Who is audited** (SKILL.md step 3): every folder under the parent that a
**live** deal owns — `won` or open (any stage but `won` and `lost`) — by its
`專案資料夾：` line, or by company name when no live line points at the
folder. A live deal always outranks a `lost` one; a folder only a lost deal
claims is listed, not audited, and a lost deal's links are never judged. A
**closed** project (its `[復盤]` modified after its `[Kickoff]`) gets one
已結案 line and skips I2, I3 and I6. And one cause gives one finding: a won
project nobody has opened yet (neither half of the project set) gets I1's
*Won, not opened* or I2's, and I3 and I6 skip it.

## Shared finding format

Every violation becomes exactly one finding line pair under its engagement:

```
- I<n> · 問題：<one concrete sentence, with the observed value — a date, a number, a name>
  建議動作：<the exact fix, named to the owning skill, or a one-line manual edit>
```

Rules: one finding per violation (no bundling); the 問題 line quotes evidence
(the stale date, the missing title, the duplicate number); the 建議動作 line
names the owning skill with a leading `/` when one exists. A deal without a
交易編號 is named by its URL.

---

## I1 — Deal ↔ folder backlink

**What it checks.** A won deal that owns a folder carries a
`專案資料夾：<url>` line pointing at it — `/project-init` writes that line when
it opens the project, and every reader of the folder finds it through the
line. Every live deal's line points at a folder that exists. Every folder has
exactly one live owner, and no live deal matches two folders.

**How.** `mcp__zynkr__get_deal` for every deal in the list (`notes` comes back
only from `get_deal`); find `專案資料夾：https://drive.google.com/drive/folders/<id>`
anywhere in the notes. Folder side: the step-2 parent listing. A live deal's
line whose id is not in the parent: list that id
(`list_drive_items(folder_id=<id>)`) to tell a folder that moved out from one
that is gone.

**Violations** (live deals only — a lost deal's links are history):
- *Won, not opened*: a won deal without a line, owning a folder by company name
  that holds neither `[Kickoff] <專案名稱>` nor `[專案管控表]` — `/project-init`
  never ran on it.
- *Won, line missing*: as above, but the folder holds the project set — only
  the line is missing.
- *Dangling*: a line whose folder no longer exists. (A folder that still
  exists outside the parent has been moved out — archived — and is not a
  finding: one 已移出 [2.2] line, SKILL.md step 3.)
- *Orphan folder*: a folder nobody claims — no line and no name, live or lost.
- *Fork*: a folder two or more live deals' lines point at. A lost deal's line
  to the same folder does not count: a restarted client keeps its old lead's
  link, and its quotes stay findable from there.
- *Ambiguous* — two shapes, one fix: a live deal without a line whose company
  name two or more folders carry, or a folder no live line points at whose name
  two or more live deals' companies match. Every reader of the folder stops on
  that tie.

**Fix lines.**
```
建議動作：跑 /project-init 客戶案 <交易編號>：沿用 [<n>]、補齊專案文件並寫上 專案資料夾 那一行
建議動作：deal notes 補上 專案資料夾：<folder url>（照 /project-init 的格式先讀再接一行；本技能不寫入）
建議動作：找回資料夾，或把 deal notes 那一行改成現在的資料夾網址
建議動作：確認這是哪筆交易：已有交易（任何階段）就在那筆 deal 的 notes 手動補上 專案資料夾：<此資料夾 url>，已成交的再跑 /project-init 客戶案 <交易>（它從這一行沿用資料夾）；還沒有交易就用 /sales-outbound 建交易（它不開資料夾），再手動補上同一行；都不是就把資料夾移出 [2.2]
建議動作：人工裁決哪個 deal 是本案，從另一個 deal 的 notes 移除 專案資料夾 那一行
建議動作：人工選定是哪筆交易，在它的 notes 補上 專案資料夾：<folder url>，讓讀資料夾的技能不必猜
```

## I2 — The kickoff set

**What it checks.** A **won** project's folder holds the set `/project-init`
lays: `[Kickoff] <專案名稱>` and `[專案管控表] …` (with `[Charter]`,
`[Business Case]` and `[復盤]`). An **open** deal's folder holds a kickoff or
context doc of any convention: `/sales-inbound`'s `<交易名稱> — 專案啟動`, or
the older `[Kickoff] … — 專案脈絡與會議紀錄`.

**How.** The step-2 per-folder listing; title-based only — contents are never
read. The project's `[Kickoff]` is `[Kickoff] <專案名稱>`; an inbound kickoff
(`<交易名稱> — 專案啟動`, or `[Kickoff] … — 專案脈絡與會議紀錄`) is **not** half of
the set, exactly as `/project-init` reads it, so a won folder holding only
that is *Won, not opened*. Left in a won project's folder it is expected:
`/project-init` links it from the new `[Kickoff]` and keeps it.

**Violations.**
- *Won, not opened*: the deal has its line, but the folder holds neither
  `[Kickoff] <專案名稱>` nor `[專案管控表]` (without the line, I1 reports it).
  Projects won before `/project-init` opened them land here once.
- *Won, half a set*: the folder holds one of the two but not the other.
- *Open, no kickoff*: an open deal's folder with downstream documents
  (`[BRD]`, `[Notes]`, …) but no kickoff doc, or an entirely empty folder.

**Fix lines.**
```
建議動作：跑 /project-init 客戶案 <交易編號>：沿用 [<n>]、補齊專案文件
建議動作：跑 /project-init 客戶案 <交易編號>：它沿用 [<n>]，看到已有一部分專案文件會停下來問，選「只補缺的」（已存在的文件一字不動）
建議動作：照 /sales-inbound 的「<交易名稱> — 專案啟動」格式手動補一份（/sales-inbound 只處理 7 天內的新詢問，不會回頭補）
```

## I3 — Session-record recency (default window: 21 days)

**What it checks.** Every engagement *past discovery* — stage `proposal` or
`won` — has a session record modified within the window. A session record is
any `[Notes]` doc (`/consult-session-notes` files one per session, shadowing
ones inside `Shadowing — YYYY-MM-DD`), a kickoff doc — the project's
`[Kickoff]` or an inbound one; people paste updates and meeting notes into
them — or any doc in `[1] 會議`.

**How.** Stage from the step-3 CRM inventory; titles + `modifiedTime` from the
step-2 listing, sub-folders included. Take the newest of all of them.

**Violation.** The newest record's `modifiedTime` is older than the cutoff, or
there is no record at all.

**Fix line.**
```
建議動作：跑 /consult-session-notes 補最近一次會議的紀錄（最後一份停在 <date>）
```
A project that is really finished stops appearing here once its `[復盤]` is
filled in (it becomes 已結案) or its folder leaves the parent.

## I4 — [N] numbering continuity

**What it checks.** Folder numbers run 1…max with no gaps and no duplicates,
and every folder in the parent starts with `[N]`. The rest of the name is free
text — the owners write several shapes — so it is never judged here.

**How.** Read `^\[(\d+)\]` from every **folder** name in the parent listing.
Files are not numbered: a file loose in the parent goes to 本次未檢查.

**Violations.** A gap (`[6]` absent while `[7]` exists) · a duplicate number ·
a folder with no `[N]` prefix.

**Fix lines.** (Drive renames keep the folder id, so a rename never breaks an
existing backlink.)
```
建議動作：確認 [<n>] 是被刪除還是漏建 — 編號由 /project-init（成交開案）或 /sales-inbound（新詢問）分配，缺號通常代表資料夾被移走
建議動作：在資料夾名稱前補上 [<下一個號碼>]（本技能不改名）
```

## I5 — Activity pulse (default window: 14 days)

**What it checks.** Open deals that own a folder and show no CRM activity in
the window are flagged 停滯 — the "is anyone driving this?" signal before the
sale. Won deals are not pulsed: delivery work lives in Drive, not in the CRM's
activity log.

**How.** Use `last_activity_at`, returned on every `mcp__zynkr__list_deals` row.
It is stamped by the application each time work is logged through the CRM or
the MCP — it is not computed from the activity rows, so it reflects activity
that went through the platform. (Anything written straight to the database
behind the platform's back does not move it. That is one more reason the 2.x
suite no longer does that.)

⚠️ The activity rows themselves are **not readable over the MCP** — there is no
`list_activities` tool, so you cannot show *what* the last activity was, only
when it happened. Report the date and the silence; do not characterise the
activity you cannot see.

**Violation.** An audited open deal whose last activity predates the cutoff.

**Fix line.**
```
建議動作：安排下一步（聯繫客戶或開 follow-up task）；若近況其實在 Drive 端，補一筆 CRM note 讓 pulse 反映實況
```

## I6 — Document chain

**What it checks.** Each document is built from the ones before it, so a later
document without its sources was written blind:

| Document | Written by | Needs in the folder |
|---|---|---|
| `[Assessment]` | `/ops-transformation assess` (during Consult) | — |
| `[BRD]` | `/consult-brd-writer` (usually after the sale) | — |
| `[Blueprint]` | `/ops-transformation redesign` | `[BRD]` · `[Assessment]` |
| `[PRD]` | `/ops-prd-writer` | `[BRD]` |
| `[UAT]` | `/gtm-uat-writer` | `[PRD]` |

A `[PRD]` is owed only its `[BRD]`: `/ops-prd-writer` expects the `[Blueprint]`
too, but Peter can tell it to go from the BRD alone, so a missing blueprint is
not drift. Nothing is owed because of a **stage** either: the BRD usually comes
after the sale, and coaching or training work may never need one.

**How.** Doc titles from the step-2 listing (root, `[1] 會議`, `[3] 交付物`).
Title-prefix match only — an empty doc with the right title passes; content
quality is out of scope.

**Violation.** A document present while one it needs is missing — one finding
per missing source.

**Fix lines.**
```
建議動作：跑 /ops-transformation assess 補 [Assessment]
建議動作：跑 /consult-brd-writer 補 [BRD]
建議動作：跑 /ops-prd-writer 補 [PRD]（需先有已簽核的 [BRD]）
```
Add after the fix: 「再確認 [<later>] 有照它寫」.

---

## What this checklist does not govern

- Report layout beyond the finding-line format (that lives in SKILL.md step 5).
- The window defaults (21 / 14) — Peter overrides them per run.
- The sales pipeline: open deals without a folder are counted, not audited;
  won deals without a folder are listed, not judged.
- Any write of any kind. If a fix looks one-keystroke trivial, it still routes
  to the owning skill or to Peter's hands.
