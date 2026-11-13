# Proposal rules — what `propose` may suggest, and on what

`propose` turns this week's evidence into suggested changes to the Main Tracker, and the owner
approves each one by reply before anything is written (`SKB-044`, decision D3; 新增 and 放棄 since
`SKB-091`). This
file is what you read before writing `proposals.json`. `scripts/proposals.py check` enforces every
rule marked **checked**; the rest are judgement, and the owner sees your judgement in the mail.

## The evidence you have

- **`decisions`** — this week's `Decisions` block, which `minutes` wrote from the
  meeting: each row has `會議日期`, `類型`, `內容`, `負責人`, `期限`, `關聯 #` (the item it concerns,
  or 「新」 for an item the tracker does not hold yet) and `狀態`. `類型` is one of:
  - `決議` — decided;
  - `放棄` — an item stops;
  - `行動` — an action with an owner (`狀態` 已排定 when it has a date, 待定 when not);
  - `進度` — where an item stands (`狀態` holds it: 進行中, 完成 …);
  - `卡關`, `風險`, `待討論` — open; older weeks also have `待決`.
- **`harvest`** — this week's `Harvest` lines that `collect` tied to a tracker item (`SKB-128`; the
  `Reports` block until then): each has `name` (whose harvest), `kind` (`shipped` · `moving` ·
  `waiting`), `text` (the line as the harvest wrote it) and `item` (the item's `#`). A line `collect`
  tied to no item is not listed: it is evidence about nothing.
- **`items`** — the live tracker: `#`, `項目（正規化）`, `Priority`, `負責人`, `開始`, `結束`, `狀態`,
  `備註`.

Never the Doc, never mail, never Chat. A change you cannot tie to a `ref` in `decisions` or
`harvest` is not a proposal.

**A meeting row is evidence only for its own item, and only when it settles something**
(**checked**): cite a `decisions` row only when its `類型` is `決議`, `行動`, `放棄` or `進度` and its
`關聯 #` is the item you are changing. `卡關`, `風險`, `待討論` and `待決` are questions the meeting
left open; a decision about 1.01 says nothing about 1.02. Cite at most three rows per proposal
(**checked**).

**A harvest line is evidence only for the item it is tied to, and only when it is work done**
(**checked**): cite a `harvest` row only when its `item` is the item you are changing and its `kind` is
`shipped` or `moving`. A `waiting` line is an ask, not progress. The tie is `collect`'s reading of one
line, so read the line yourself before you lean on it: if it is plainly about something else, do not
cite it.

**What the harvest can carry on its own** (**checked**), with no meeting row for the item:
- only `狀態`, and only to `進行中` or `完成`. Work shows that an item moves or that it is done. It
  cannot show that an item is paused, dropped or not started, and it moves no date and adds no note;
- `完成` needs a `shipped` line tied to the item, no line of the week still `moving` or `waiting` on
  that item in anyone's harvest, and no row of the meeting about the item this week. The harvest closed
  the night before the meeting, so where the meeting recorded a plan, a blocker or a status for the
  item, that is the newer word: cite its `決議` or its `進度` marked 完成, or leave `完成` to the
  meeting. Then judge the line: one shipped step of a larger item is `進行中`, not `完成`;
- it is 中 or 低, never 高, and its row is recorded with 來源 「收成」. The 【週結】 marks it
  「只有收成佐證」, so the owner knows no meeting record stands behind it.

A line that is still `moving` is never cited for `完成` (**checked**), whatever stands beside it.

## What may be suggested

Three fields on an item that is not closed (**checked**: `完成` and `放棄` items are never touched,
nor an item number that appears twice in the tracker), and one new item:

| Field | Allowed change | Evidence it needs |
|---|---|---|
| `狀態` | any of 未開始 · 進行中 · 暫停 · 完成 · 放棄 (**checked**) | `完成` needs a `決議`, a `進度` row whose `狀態` is 完成, or the harvest as above (**checked**). `放棄` needs the meeting's `放棄` row for that item (**checked**), and brings its own dated 備註 line, `10/15 放棄：<the meeting's words>`, which the mail shows and `apply` appends. Any other move rests on a meeting row; `進行中` may rest on the harvest alone |
| `結束` | a real `YYYY-MM-DD` (**checked**) | a decision row for that item (`關聯 #`) whose `期限` is that very date, written in full (`2026-11-15` or `2026/11/15`; a bare `11/15` names no year and backs nothing) (**checked**) |
| `備註` | the current text, unchanged, then a line break and exactly one new line that starts with its date (`10/15 …`); on an empty `備註`, just that line (**checked**) | a decision row (**checked**) |
| `新增` | a new item: `項目` (2 to 60 characters, not already in the tracker), `子類別` (one of the tracker's sections, `1.1 …`), `負責人` (one name on the roster); `#` left empty — `check` gives it the section's next free number (**checked**) | only the meeting's `行動` rows with `關聯 #` 「新」, owned by that person or by All, and no harvest line beside them; 高 or 中, never 低 (**checked**) |

- **完成 needs a delivery, not an intention.** A decision that says the item shipped, was handed
  over or went live, or a shipped harvest line that is the whole item. "Should be done by Friday" is a
  new `結束`, not 完成.
- **Overdue is derived, never written.** There is no `逾期` status (**checked**: it is not in the
  vocabulary). The Monday recap shows overdue items; it is never a proposal.
- **Silence is not evidence.** An item nobody mentioned this week gets no proposal. The recap calls
  out long silences on its own.
- **Dates move only when someone named one.** If the meeting said "next week", there is no date to
  propose; leave it for the owner.
- **Never put done-words in `備註`** (完成 · 做完 · 結案 · 上線 · shipped · done) (**checked**): the
  state rules (zynkr-gm `derive_state.py`) read `備註` and would flag the item as done. Propose
  `狀態` instead.
- **A no-op is refused** (**checked**): a proposal whose value is already there, dates compared as
  dates (`2026/10/30` is `2026-10-30`).
- **A new item comes only from the meeting.** The harvest never adds an item (**checked**): work the
  tracker does not hold shows in the Doc as 「不在 Tracker」, for the meeting to decide. The new row
  gets the owner's name as text, 狀態 未開始 and nothing else; the owner swaps the name for a person
  chip and fills the rest by hand.

## Confidence

| 信心 | When |
|---|---|
| 高 | A decision row names this item and says exactly this |
| 中 | A decision row supports it, but you inferred the field or the value. Or only the harvest supports it, and its line says exactly this |
| 低 | Only the harvest supports it, and you inferred the value from a line that does not say it outright (**checked**: a change with no meeting record of it is 中 or 低, never 高) |

## The reason line

`原因` is one line in zh-TW, at most 160 characters, with no line break (**checked**), in the voice of
`references/wording.md`: what happened, in the team's words, and why it moves this field. Not how
you found it. Examples:

- `週四會議把交期改到 11/15`
- `會議記錄寫已交付給客戶`
- `Bob 這週的收成寫訪談已經開始`

## The shape of `proposals.json`

```json
[
  {"#": "1.01", "欄位": "結束", "建議值": "2026-11-15", "原因": "週四會議把交期改到 11/15",
   "證據": ["Decisions!A42"], "信心": "高"},
  {"#": "1.10", "欄位": "狀態", "建議值": "進行中", "原因": "Bob 這週的收成寫訪談已經開始",
   "證據": ["Harvest!A163"], "信心": "中"},
  {"#": "1.02", "欄位": "狀態", "建議值": "放棄", "原因": "週四會議決定不做，改外包",
   "證據": ["Decisions!A44"], "信心": "高"},
  {"欄位": "新增", "項目": "回報管道", "子類別": "1.1 客戶成功", "負責人": "Ann",
   "原因": "週四會議請 Ann 建回報管道", "證據": ["Decisions!A45"], "信心": "高"}
]
```

At most one proposal per item and field (**checked**), at most 40 in a week (**checked**), and the
mail they make must stay under 8,500 characters of text (**checked**): the thread `apply` reads
quotes the mail whole. When `check` says the mail is too long, drop the weakest proposals. An
empty list is a fine answer: the Ledger records the week as "recorded, none", and the 【週結】 still
goes out with the week's summary and asks for no reply.
