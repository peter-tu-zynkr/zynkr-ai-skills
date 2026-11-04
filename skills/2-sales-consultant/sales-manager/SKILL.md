---
name: sales-manager
sheetId: "2.46"
description: >-
  The conductor of the Zynkr sales family — it decides which sales skill a given
  input needs, chains them when a job takes more than one, and reads the CRM
  across deals to say which ones need attention now. It owns the deal lifecycle;
  the six skills under it each own one step. Three modes: ROUTE (one input →
  the right child skill), SEQUENCE (a job that needs two or more, e.g. triage a
  whole event survey with sales-client-sourcing then run sales-outbound on each
  Hot Lead row), and REVIEW (deal-level pipeline sweep — what is stalled, what
  has no next step, whose follow-up task is overdue, whose draft is still
  unsent). It may write to the CRM, but never silently: every change is proposed
  as one batch and applied only on a single confirmation. Trigger on
  /sales-manager or when Peter says "什麼 deal 該追", "業務進度盤點", "pipeline
  review", "這週業務要做什麼", "幫我看一下 CRM 有什麼卡住", "handle this lead"
  without naming a skill, or hands over sales input and wants the whole job done
  rather than one step of it. Distinct from zynkr-gm (the company-level GM brief
  across every LOB — this one is the sales pipeline only, and never writes a
  weekly narrative), project-client-status and project-governance (the
  consulting portfolio), and zynkr-skills (which routes the whole skill
  ecosystem, not within sales).
category: sales-consultant
project: sales-manager
platform: claude
status: Done
visibility: public
author: Peter Tu
input: "A sales input with no skill named (signal · survey sheet · card · transcript · company), or a pipeline question like 「什麼 deal 該追」. Optional: guided."
process: "Classify into ROUTE / SEQUENCE / REVIEW → delegate to the child skills, never inline their logic → for REVIEW read the CRM across deals → propose every CRM write as ONE batch → apply on one confirmation → report."
output: "Whatever the delegated children produced (CRM records · Gmail drafts · enriched sheet), plus for REVIEW a deal-level attention list and one confirmed batch of CRM writes."
synergy: []
type: agent
skills: ["sales-client-sourcing", "sales-specialist", "sales-outbound", "sales-follow-up", "sales-research", "sales-proposal-writer"]
reads: ["sales.crm-data-standards", "company.sales-pipeline-rules", "company.crm-tag-rules"]
house-style: bound

---

# Sales Manager

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill sales-manager
```

The sales family has six good single-step skills and nobody holding them together.
Each one takes one input shape and does one job well; none of them knows what happened
before it, what should happen next, or that a deal has been sitting untouched for three
weeks. `sales-manager` is that missing layer — the same relationship `/zynkr-slide` has
to the three slide skills.

It does three things, and **delegates everything else**:

1. **ROUTE** — one input arrives with no skill named; decide which child it belongs to.
2. **SEQUENCE** — the job needs more than one child; run them in order and carry context.
3. **REVIEW** — read the CRM *across* deals and say which need attention now.

## The family it conducts

| Child | id | Owns | Never |
|---|---|---|---|
| `sales-client-sourcing` | 2.01 | A WHOLE event survey Sheet → enriched columns + Hot Lead flags | writes CRM · sends mail |
| `sales-specialist` | 2.02 | A business-card IMAGE → OCR → contact + company + 名片 note + draft | text-only signals |
| `sales-outbound` | 2.09 | ONE lead signal → CRM lead + Gmail draft (+ three 台北時間 slots) | batches |
| `sales-follow-up` | 2.10 | A completed demo transcript → threaded follow-up + deal sync | new leads |
| `sales-research` | 2.11 | A company → background brief written back to the CRM | contacts |
| `sales-proposal-writer` | 2.47 | A deal + the client's asks → a priced 交付文件 proposal, and its revision rounds | the covering email (→ whoever picks up the outbound with the client; no skill drafts it) |

**Delegate, never inline.** If you find yourself writing CRM SQL, parsing a card, or
drafting an email body in this skill, stop — that belongs to a child. This skill's own
output is routing decisions, sequencing, the attention list, and the batch gate.

## How this differs from its neighbours

- **`/zynkr-gm`** — the founder's company-level weekly brief across every LOB, with
  runway, KPI variance and a decisions register. `sales-manager` is the **sales pipeline
  only** and deliberately writes **no weekly narrative**: two skills narrating the same
  week is the failure mode. When Peter wants "這週公司要幹嘛", that is `/zynkr-gm`.
- **`/project-client-status`, `/project-governance`** — the consulting portfolio and its
  hygiene sweep. Different pipeline, different objects.
- **`/zynkr-skills`** — routes the whole skill ecosystem. This one routes *within* sales.
- **The six children** — each is still a first-class entry point. When Peter names a
  skill, run that skill; don't insist on going through the conductor.

## Fixed facts (don't re-derive these)

- **CRM reads** use the `zynkr` MCP server: `list_deals` (optional `stage` filter),
  `list_deal_stages`, `list_tasks`, `list_contacts`, `get_contact`, `get_deal`, `get_company`,
  `whoami`, `list_tags` (`mcp__zynkr__list_tags`, given `entity_type` + `entity_id` it lists one
  record's tags).
- **CRM writes** use `move_deal_stage` (stage changes — never `update_deal` for stage,
  the pipeline side-effects must fire; with `stage: lost` it also takes `loss_reason`, one of
  `price`, `competitor`, `no_decision`, `poor_fit`, `timing`, `other`), `update_deal`,
  `set_task_status`, `create_task`, `create_note`, `mcp__zynkr__apply_tag`, `mcp__zynkr__remove_tag`.
  Every `zynkr` write tool is a two-call handshake: `confirm:false` previews,
  `confirm:true` applies.
- **Record URLs** for the report: `https://platform.zynkr.ai/deals/{id}` · `.../contacts/{id}`.
- **Google account** for anything Gmail/Calendar: `<your-google-workspace-account>`.
- Peter's calendar is `Europe/Amsterdam`; prospects are almost always `Asia/Taipei`.
- **Pipeline rules** — the cap, the floor, the outreach target, the follow-up rhythm and when a
  deal is dropped are one company policy, and so are the words *client touch*, *cooking* and
  *stale*. This file names each threshold and never holds its number.

> **The pipeline thresholds are company policy — read them from Atlas** (`get_knowledge`, key `company.sales-pipeline-rules`, on the `zynkr-atlas` MCP server; each threshold is a `<name>: <value>` line at the top, and the `value:` line is the version date). If Atlas cannot be reached, the key is missing, or a line you need is missing, say so and ask; never fall back to a number from memory or from an older copy of this file.

---

## Workflow

### 1 · Classify the request

| What arrived | Mode |
|---|---|
| One person's signal — DM, feedback row, enquiry, card, transcript, a company name | **ROUTE** |
| A job that plainly needs two or more children (a whole survey sheet; "research them then write") | **SEQUENCE** |
| A question about the pipeline — 「什麼 deal 該追」, "what's stalled", "業務進度盤點" | **REVIEW** |
| Genuinely unclear | Ask **one** question, then default to ROUTE |

Say which mode you picked in one sentence before acting.

### 2 · ROUTE — one input, one child

| The input is | Send it to |
|---|---|
| A photographed business card | `/sales-specialist` |
| A DM, feedback-form row, website enquiry, or card **text** | `/sales-outbound` |
| A completed demo / discovery-call transcript on an existing deal | `/sales-follow-up` |
| A company name, or a deal lacking background | `/sales-research` |
| A WHOLE survey sheet of many people | `/sales-client-sourcing` |
| A client's requirement list / ask sheet, or "write the proposal", or comments on an existing proposal | `/sales-proposal-writer` |

Invoke via the **Skill** tool and let the child drive. Report what it produced.

### 3 · SEQUENCE — carry context across children

Run the children in order, feeding each the previous one's output. The two established chains:

1. **Event survey → funnel.** `/sales-client-sourcing` enriches the whole sheet and flags
   Hot Leads, then `/sales-outbound` runs **per Hot Lead row** to create the CRM lead and
   the draft. Confirm the row count with Peter before fanning out — this creates one deal
   and one Gmail draft each, and ten rows means ten drafts.
2. **Card → informed draft.** `/sales-specialist` lands the contact, then `/sales-research`
   fills the company background, and only then is the follow-up draft written — so it
   opens with something true about their business rather than a generic line.

Never run a child twice on the same object in one pass. If a chain fails halfway, report
what landed and what didn't; do not silently retry a CRM write.

### 4 · REVIEW — the deal-level attention list

Read `company.sales-pipeline-rules` first (see *Fixed facts*), then the pipeline. For each open deal,
find its **last client touch** — the newest inbound email from its contact, meeting, or stage
change. `get_deal` shows the timeline; Gmail `from:<contact email>` fills a gap. Our own sent
mail is not a client touch, so a deal chased every few days with no answer still goes stale.
`list_deals` returns no `created_at`: every "since the deal was created" below reads it from
`get_deal`. Classify every open deal into exactly one bucket, top row first:

**In sequence first.** A Mode B deal exists from the claim, before any client touch, so the stale
test alone would close it while its five mails are still going out. Before the table, look for an
open 「五封未回 → 結案 lost（no_decision）」 task on the deal (`list_tasks`):
- open and **not yet due** → the deal is *in sequence*: it skips 序列結束未回 and 放掉 · stale and
  is tested from 沒有下一步 down (its open task usually makes it 健康). No bucket closes it.
- open and **past `due_at`** → 序列結束未回 (or, with a reply, the task closes as below). Never
  plain 放掉 · stale.

| Bucket | Test |
|---|---|
| **序列結束未回** | A Mode B deal whose sequence ended unanswered: its open task 「五封未回 → 結案 lost（no_decision）」 is past `due_at`, and the contact has sent nothing (no inbound email, no meeting) since the deal was created |
| **放掉 · stale** | Not in sequence, and stale as the policy defines it: `stale-days` or more since the last client touch and since the deal was created |
| **沒有下一步** | Open deal with no open task attached |
| **逾期追蹤** | Has an open task whose `due_at` is in the past |
| **草稿未寄** | A Gmail draft exists for the contact but nothing was ever sent |
| **健康** | None of the above — do not list these individually, just count them |

**序列結束未回** comes from `/sales-outbound` Mode B: the claim at pick-up makes a deal with that
task, due seven days after the fifth mail. Check Gmail `from:<contact email>` since the deal's
creation before you classify. No reply → the batch line `移到 lost（no_decision）`. A reply found
→ the sequence worked: the batch closes the task (`set_task_status`, `done`) instead, and the deal
is classified again without it (usually 沒有下一步, which proposes its follow-up task).

**The pipeline band.** Each owner sits between a floor and a cap: at least `min-cooking-clients`
clients cooking, at most `max-open-deals` open deals. Cooking is the stale line read the other
way. Count clients, not deals, for the floor: one company, or one contact without a company,
counts once. Count deals for the cap. Above the table, write one line per owner:
`<owner> · N of <min-cooking-clients> cooking · M of <max-open-deals> open`, adding `· short K`
when N is below the floor and `· over by K` when M is above the cap. It is a count, not a
roll-up: no LOB, no revenue. Keep the `N of <floor> cooking` words exactly: the Monday sales
pulse and `/zynkr-gm` read that phrase.

- **Below the floor** — say how many leads to claim from the 陌開名單 roster and run
  `/sales-outbound` Mode B. Stale deals are not revived to make up the count: they go in the batch.
- **Over the cap** — the owner's stale deals go first. If they are still over, name their oldest
  `new` / `contacted` deals to hand off or close, and put them in the batch for the owner's call.
- **沒有下一步 and 逾期追蹤 rows** — the one thing to do is a follow-up task due by the policy's
  rhythm: read the client's reply lag from the timeline, pick the fast, normal or slow days, and
  never later than a `客戶時限：` line in the deal's notes.

**Tag checks.** For the contacts on the runner's own open deals (`whoami` names the runner; a
teammate's records are theirs to fix), read `list_tags(entity_type="contact", entity_id=…)` and list
two things under the bucket table, by `company.crm-tag-rules`:
- **待確認 still on** — each `review-values` tag, with what clears it in the policy's 待確認 table.
  When `get_contact` shows the gap filled (a phone, a title, a linked company), put a `remove_tag`
  (`group="review"`) in the batch; otherwise the row says what to fill in. 來源不明 is filled once
  `list_tags` shows a 來源 other than 其他. `get_contact` does not return `legal_basis`, so
  同意權未確認 is never removed here: its row asks the owner to check the consent in the app and
  remove the tag there.
- **No 來源** — the tag is where the person first came from, and a deal's `lead_source` is only how
  that deal came in; policy §1 ties the two on a contact's first deal alone. So use a deal only when
  it is the only deal naming this contact in the deals REVIEW read (all stages, open and closed);
  with more than one, the row asks the owner. Every proposal sits in the one batch the owner agrees. Put a 來源 (`group="source"`, `source="rule"`) in the batch when that deal's
  `lead_source` maps back to exactly one value in `source-to-lead-source`. When it maps back to
  several and one of them is 其他, the batch proposes 其他 with the 待確認 value 來源不明
  (`group="review"`) beside it, as policy §1 says; if the owner picks another of those values in the
  batch, 來源不明 leaves the batch with it. Otherwise the row asks the owner which value it is. Never
  infer it from a job title or an industry.

> **The CRM tag rules are company policy — read them from Atlas** (`get_knowledge`, key `company.crm-tag-rules`, on the `zynkr-atlas` MCP server; each list is a `<name>: <value>` line at the top, and the `value:` line is the version date). `group` is the platform's English key (`source`, `review`) and `name` is the policy's value. If Atlas cannot be reached, the key or a line you need is missing, or any of `mcp__zynkr__list_tags`, `mcp__zynkr__apply_tag`, `mcp__zynkr__remove_tag` is not among your tools, skip the tag checks, put no tag change in the batch, and say so in the report; the rest of REVIEW runs as usual. A tag change in the batch that answers `not_found`, `invalid_input` or any other error except `conflict` (`forbidden`, `rate_limited`, `internal`, …) is left undone and listed in the report, with no retry and no stopping to ask; on `conflict`, read the contact back with `list_tags`, report what it shows, and do not retry. Never fall back to a value from memory or from an older copy of this file.

**重複認領.** One open deal per client is the pick-up rule (Atlas `sales.crm-data-standards`; every
sales skill runs its gate before it claims). The gate leaves a few seconds between its check and
its claim, so two people can, rarely, claim the same client. From the same four open-stage
`list_deals` reads (`new`, `contacted`, `qualified`, `proposal`, `limit=100` each; a read that
returns exactly 100 rows means the check is not sound, so say so), list every `contact_id` with
two or more open deals: each deal's 交易 number, owner and creation date (`created_at` from
`get_deal`; `list_deals` does not return it). Propose nothing on your
own: the owners agree which deal stays, and only then does the other go into the batch as
`移到 lost`, `loss_reason` `other`, with the note `重複認領：保留 <交易 number>`, read back after the
move the same way as a 序列結束未回 deal below.

> **The pick-up rule is written in Atlas** (`get_knowledge`, key `sales.crm-data-standards`, on the `zynkr-atlas` MCP server). This check runs as written even when Atlas cannot be reached.

This file is where the buckets and the band are defined from the policy's words. The team's
Monday sales pulse mail applies the same policy to every member.

Render the five live buckets as one table (deal · owner · days since last client touch · the one thing to do).
Keep it **deal-level**. Do not roll up by LOB, do not write a weekly narrative, do not
compute revenue forecasts — that is `/zynkr-gm`'s job and duplicating it is the one
outcome this skill was explicitly scoped to avoid.

### 5 · The batch gate (this is the safety rule — do not soften it)

`sales-manager` **may** write to the CRM. It **may never** write silently.

Collect every intended change from step 4 into ONE batch, show it in full, and apply it
only after a single explicit confirmation:

```
我打算做這些（一次確認全部）：

移到 lost（no_decision）· 2 個 deal — 序列結束未回：五封都寄了，「五封未回」任務已到期，對方一直沒回
關掉序列任務   · 1 個        — 序列中途有回信：「五封未回」任務關掉，deal 照常追
移到 lost      · 3 個 deal   — 放掉 · stale：客戶 <stale-days> 天以上沒有回應（各附最後一次往來日期）
關掉過期 task  · 8 個        — 早已完成或已無意義
建立追蹤任務   · 2 個 deal   — 開著但沒有下一步（到期日依客戶回覆速度）
加／移除標籤   · 4 位聯絡人 — 待確認已補齊的移除；沒有來源、lead_source 對得上的補上

要我執行嗎？想留下哪一筆，說一聲原因就好
```

Fill `<stale-days>` with the policy's number when you write the batch. Each tag change in it is
`apply_tag` or `remove_tag` (`entity_type="contact"`), previewed, then repeated with `confirm:true`
after the one confirmation, then read back with `list_tags`.
A stale deal moved to `lost` gets one note on the deal — `放掉 · stale（company.sales-pipeline-rules <value date>）：最後一次客戶往來 <date>` —
so whoever reopens it sees why.

A 序列結束未回 deal is closed with
`move_deal_stage(id=…, stage="lost", loss_reason="no_decision")`, previewed, then repeated with
`confirm:true`; its 「五封未回」 task is set `done`; and the deal gets one note,
`create_note(deal_id=…, subject="結案原因", body="結案原因：no_decision（五封未回）")`. A server
older than `PLAT-078` drops an unknown `loss_reason` without an error, so a quiet success proves
nothing: after the move, `get_deal` and check `loss_reason`. When it is not the reason sent, the
`結案原因：` note line is the only record of it, and the report says the server did not record
the loss reason (`PLAT-078` not live). A stale deal the owner keeps gets their reason as a note
instead, and stays out of the batch.

Rules:
- **One confirmation for the whole batch**, not one per row — the point is to clear a
  week's accumulation in a single click.
- **Nothing outside the batch.** If you discover more work mid-apply, finish the batch,
  then propose a second one.
- **Never auto-close a deal as `won`.** Money is Peter's call, always.
- **Stage changes go through `move_deal_stage`**, never `update_deal`.
- On refusal, change nothing and keep the list — he may want it as a to-do instead.

### 6 · Report

State the mode, what each child produced (with record URLs), and — for REVIEW — the
`company.sales-pipeline-rules` version used (its `value:` date), the band lines, the bucket counts,
the two tag-check counts with the `company.crm-tag-rules` version (or why they were skipped), the
重複認領 rows, any deal moved to `lost` whose `get_deal` read-back lacks the `loss_reason` sent, and
exactly what the confirmed batch changed. If the batch was declined,
say so plainly and leave the list.

---

## Modes

- **express** (default) — gather context once at the top, then run without stopping,
  surfacing only the batch gate and any genuine fork. Follows `/zynkr-slide`'s precedent.
- **guided** — pause for review between children. Use when a chain will fan out over
  many rows, or when Peter says so.

## Why it's built this way

- **A conductor, not another sibling.** The child skills were already good; what was
  missing was someone holding the baton. So this skill adds no new sales capability — it
  adds routing, sequencing and the cross-deal view, and delegates the actual work.
- **Batch-preview writes, not read-only and not autonomous.** Read-only was rejected
  because a review nobody executes is a review that didn't happen — Peter stays the
  bottleneck. Fully-autonomous was rejected because the CRM is the single source of truth
  on customers, and a deal wrongly marked `lost` has nothing to raise its hand. One batch,
  one confirmation keeps the speed and keeps the veto. It mirrors what `sales-outbound`
  already does with email: prepare, don't send.
- **Deal-level only, by decision.** The portfolio view lives here rather than in a
  separate skill (a second skill would likely never get built, and "I forgot to chase that
  deal" is the pain that motivated this one) — but it is fenced to deal-level facts so it
  cannot grow into a rival `/zynkr-gm`.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
