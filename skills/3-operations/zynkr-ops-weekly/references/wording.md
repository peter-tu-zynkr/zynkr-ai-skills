# Wording

Everything the weekly loop publishes (all four of its skills, SKB-091) is read by six colleagues, in zh-TW, in a chat room and a Doc
they use all day. It should read like a competent teammate wrote it, not like a report
generator emitted it.

The house rules come from **`/content-translator`** (skill `1.13`). That skill exists to remove
翻譯腔 from translated text; the same failure shows up here for a different reason — text
assembled from field names, status enums and internal mode names has exactly the same stiff,
machine-shaped smell. Apply its Step 2 rules and its Step 3 self-check to anything this skill
writes.

**This matters most for the lines that are *not* in `message-templates.md`.** Each team's
section, the minutes, the recap mail body and every failure notice are composed fresh each run, so they are
where the register actually drifts.

---

## The four habits that cause it

### 1. 官腔 — bureaucratic verbs

The Doc and the chat are not a government filing.

| Don't | Do |
|---|---|
| 本週週報開始**徵集** | 這週的週報開始**收**囉 |
| 週四議程已**產出** | 週四的議程**整理好了** |
| **決議候選** — 本週 0 項 | **這次沒有要決定的事** |
| 六位回報者**皆**用舊格式回報 | 六位**都還在用舊格式** |

### 2. Half-translated lines

Leaving one English word in a Chinese sentence is the loudest tell. Keep only brand names,
code identifiers and acronyms with no Chinese standard (`API`, `KPI`, `Doc`, `SEO`).

| Don't | Do |
|---|---|
| KPI **off-target** 3 項 | KPI **沒達標** 3 項 |
| 逾期與 **carry-over** | 逾期和**一直沒動的** |
| 下週各部門 **focus** | 下週各部門**要做的事** |
| 完整 **recap** 已寄出 | **完整版**已經寄到大家信箱 |
| 事項 — **Not started** | 事項 — **還沒開始** |

### 3. Internal names leaking out

`collect`, `sections`, `tidy`, `骨架`, `unrouted_heading`, `↻` thresholds and cell references are
this skill's vocabulary, not the team's. Translate them at the boundary — the mapping table is
in `message-templates.md`.

| Don't | Do |
|---|---|
| ⚠ **sections** 這週沒有完成 | ⚠ 這週的**各組進度**沒寫進 Doc |
| 下週**骨架**已開 | **下週的區塊也開好了** |
| 共 57 項候選中已濾除**範本／連結標籤** | （just show the items; the filtering is not news） |

### 4. Explaining your own machinery

A reader wants the finding, not the method. Parenthetical notes about how many candidates were
scored and what was filtered belong in the run report, which only Peter reads — never in the
Doc block.

> 連續3週以上未動（前5項，共57項候選中已濾除範本／連結標籤）— …

becomes

> 這幾件連續三週以上沒動 — …

---

## Rhythm

Short sentences for the finding, longer only when explaining. Conversational particles
(`囉`、`吧`、`喔`) are fine in Chat, sparingly, and belong nowhere in the Doc. Drop the subject
pronoun when context carries it. Use `·` for a series, and no ending 句號 on headings or
one-line items.

## Say the awkward thing plainly

The most common failure is a line that hides a bad result behind neutral phrasing. If there
were no decisions, say there were none **and why**. If a number cannot be checked, say it
cannot be checked — not that it is on target.

| Don't | Do |
|---|---|
| KPI off-target — 無法比對 | KPI 這欄還沒有人填數字，所以沒辦法看有沒有達標 |
| 決議候選 — 本週 0 項 | 這次沒有要決定的事：沒有人寫卡關，Tracker 上也沒有停住或逾期、需要拍板的項目 |
| Tracker 狀態不一致：#1.03 | #1.03 看起來做完了（SKB-070 已上線），Tracker 還寫進行中：要改成完成嗎？ |

## Frozen strings — never reword

Two strings are machine-readable idempotency keys, not prose. Changing either one makes the
loop write duplicates:

- `〔自動彙整 <week> · <stamp>〕` — `sections` and `tidy` search the section for `〔自動彙整 <week>`
- `— zynkr-ops-weekly · <week>` — the Chat footer every delivering beat looks for

Since v4 (SKB-091) one beat posts to the space: `collect`, once a week, and only when someone's
harvest is missing. Step 1 matches the footer **together with** its opening words, which are frozen
too; the rest of the line may change:

| mode | the post opens with |
|---|---|
| `collect` | 還沒收到這幾位的週報 |

A ⚠ failure notice opens with ⚠ and so never counts as a mode's post. That is the point: a retry
after its own failure notice must still run.

The `notice` mail's subject prefix `【排程沒跑完】` is frozen for the same reason: the run finds an
earlier send by its exact subject, and no other beat's mail may start with it.

`↻N週` is also fixed: `norm_key()` in `render_block.py` strips it with the regex
`↻\s*\d+\s*週`, so appending words to it silently breaks carry-over matching.

`tidy` adds one line of its own, as the kept block's last line, above the items it carried
forward. The items are real bullets, not typed `·` lines (the owner, 10-25), so an owner can
mark one `Done` or `Drop` like any of their own bullets and the chip survives. `sections` writes the
block as bullets and `tidy` folds its header in, so a block reads, one item
per bullet, the labels as words alone:

```
〔自動彙整 WB 10/19 · 10-20 09:40〕
● 上週
    ○ 官網改版 完成
    ○ 名單匯入 WIP ↻2週
● 本週
    ○ LINE 名單清理
● 還沒收掉的
    ○ 陌開三名客戶〔WB 9/7 起〕
    ○ 建立 Zynkr 知識庫〔WB 9/7 起〕
```

The labels are frozen like the ones above: `walk_block` in `tidy_blocks.py` and `LABEL_RE` in
`carryover.py` know a formatted block only by `上週` · `本週` · `數字` · `卡關` · `沒寫` ·
`還沒收掉的` alone on a bullet.

Plain, and deliberately not a status report: **不要解釋自己的機制**. It does not say how many
blocks were archived, which weeks they came from, or that a tidy ran at all — the reader wants
the list, not the bookkeeping. `〔WB 9/7 起〕` is the one piece of provenance kept, because
"how long has this been sitting there" is the question the Thursday meeting actually asks.

## Two week vocabularies, on purpose

`<week>` above is the **week-beginning label**, `WB 9/14` — the Monday that opens the week.
That is what the team reads, in the Doc and in the space.

The **ISO key**, `2026-W38`, stays in two machine-only places: the launchd state files
(`<week>.<mode>.done`, which is how `project-manager`'s `run_week.sh` knows a beat is settled) and the
`week=` field of the receipt line. Neither is ever read by a person, both need to be
year-qualified and sortable, and the scheduler derives its own key independently — it greps
the receipt for `status=ok`, the mode and the week.

This is a deliberate split, not drift. Do not "fix" it by unifying them: a label without a
year is wrong for a state file, and an ordinal nobody can place is wrong for a chat message.
