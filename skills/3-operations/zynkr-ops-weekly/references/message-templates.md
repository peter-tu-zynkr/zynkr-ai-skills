# Message templates

All output is zh-TW. **Read `wording.md` before composing anything** — these templates set the
voice, and every free-text line the model writes at run time (the recap mail body, the run report) has to
match it.

Every Chat post ends with the footer line — it is the idempotency marker the next run looks
for, so it is not decoration and its exact shape is frozen:

```
— zynkr-ops-weekly · WB 8/24
```

Each post's **first line** is frozen too: a beat knows it already posted today only by the footer
**and** that first line together, so no other line that carries the footer is taken for the post. Since v4 (SKB-091) the one beat that posts to Chat is `collect`; its line is built in
`SKB-091.9` (AC-12). The rest of each line may change; that opening may not (`wording.md` → frozen strings).

Keep posts short. Chat scrolls; anything past a screen is not read. The Doc is where length is
allowed to live.

---

## `propose` — Fri 10:00 (the 【週結】 mail, to the team)

`ops-weekly-tracker`'s `scripts/proposals.py check` renders it from the checked rows; never compose it
by hand. It goes to `routine.weekly_to`; only the reply of `google_account` (the owner) decides anything.

Subject: `【週結】WB 10/12 那週 · 5 件變更提案（2026-W42）`, or `… · 沒有變更提案（2026-W42）` — the ISO
key is in the subject on purpose: `apply` finds the thread by it.

Body, in order:

1. One line: the week first, then the tracker's proposed changes.
2. The week, from the meeting's rows in the Ledger: 這週會議定的事 (決議 and 放棄), 進度, then per
   person 卡關 · 風險 · 下一步 (an action owned by All under 全體; one with no owner under 負責人未定).
   Cut at 2,500 characters, ending 「還有 N 行沒列出，見週會 Doc 的會議紀錄。」
3. With nothing proposed: 「這週沒有總表變更提案，這封不用回覆。」 and the footer marker; nothing else.
4. One line: how many changes, that only the owner's reply counts, and how to answer —
   「全部核准」、「核准 1 3」、「退回 2」或「全部核准 退回 2」.
5. One line on how a reply is read: write only 核准, 退回 and the numbers (a thanks is fine), never
   「除了 2 都核准」; an approving reply that asks a question or says anything else gets asked to
   restate; `apply` confirms in the thread what it recorded, and until that confirmation a newer
   complete reply replaces an older one; replies before Sunday 22:00 count; rows the reply does
   not name are not applied.
6. While `routine.apply_mode` is `shadow`: **試行中** — approved rows are recorded, not written, and
   Monday's recap shows what would have changed.
7. The table: 編號 · 項目 · 欄位 · 現在 → 建議 · 為什麼 · 證據 (the meeting row or report, in its own
   words) · 把握. A 備註 row shows only 「加一行：<the new line>」, a 放棄 「未開始 → 放棄；備註加一行：
   10/15 放棄：…」, a 新增 「新項目，放在 <section>，負責人 <name>」.
8. The footer marker `〔zynkr-ops-weekly〕 週結 <ISO week>`, and that nothing reaches the tracker
   before the owner replies.

The mail goes out as HTML, and the send adds a flattened text copy of it; that copy is what `sent`
and `apply` read. `sent` requires it to be, word for word, the mail `check` wrote and records its
hash with the rows'; `apply` requires the thread's mail and the week's Ledger rows to match those
hashes (or, when no thread was recorded, the mail to be the one the Ledger rows render), so a value
changed on the way never reaches a decision. Each row's 編號 and `#item` sit side by side in it (`4#1.03`), which names a missing
row. `check` refuses a mail whose text runs past 8,500 characters: every reply quotes it.

`apply` writes in the thread only as plain text starting with the marker, which is how the next run
tells its own messages from the owner's:

- **When a reply cannot be read** (once per reply): what it could not read, the four example
  replies, and the range of row numbers.
- **When a reply draft has stayed open two hours** (once a week): that nothing is recorded until it
  is sent or deleted.
- **When a reply is recorded**: the reply's time, whether the approved rows are written now (live:
  「核准的現在寫進總表，有人手改過的格子會跳過」) or only recorded (shadow: 「試行中，不會寫進總表」),
  then 核准 · 退回 · 沒寫到、這次不套用 as row numbers, and that later replies change nothing this week. This message is what makes the
  week's decision final.

---

## `recap` — Mon 10:00 (mail, SKB-044)

Subject: `【週報】WB 10/5 那週 — 變更 4 件 · 決議 2 件 · 逾期 1 件`. The first week reads `第一次記錄`
instead of a change count, and a week whose decisions never reached the Ledger reads `決議沒記到`,
never `決議 0 件`. The ISO key stays out of the subject: it is machine-only.

Recipients: `routine.recap_to`, the team address, when it is set (`SKB-091`). Otherwise
`routine.recap_audience` decides: `owner` while the recap is new, `team` (every address in
`reporters`) once the owner has seen it work; `routine.recap_team_from` (a Monday, `YYYY-MM-DD`)
lets the owner set that switch ahead of time. The mail itself is built by
`scripts/recap.py render` from the Ledger; the run writes only the TL;DR.

Body sections, in order:

1. **重點** — at most three lines the run writes, each citing the item number it is about. A line
   without one is dropped before sending.
2. **這週的計畫** — per person (roster order, 全體 last), at most five lines: the meeting's
   actions (`#1.02 跟客戶確認（10/20 前）`), items overdue or due within 14 days, P0/P1 with no dates,
   then `業務：<step>` from the Sales Pulse. Every line cites an item # (the Pulse's steps name a
   deal); one that does not is dropped. Without a Pulse by 10:00: 「業務的下一步沒有列：今天 10 點前
   沒有收到 Sales Pulse」.
3. **上週改了什麼** — every changed cell in the Main Tracker between the last two Friday snapshots,
   `#1.03 SEO 文章 — 狀態：進行中 → 完成`, plus items added and removed.
4. **要注意的** — 逾期 · 兩週內到期 · P0/P1 還沒排日期 · 備註說做完了但狀態沒改, each with its evidence,
   from zynkr-gm's state rules.
5. **上週談定的事** — 決議 and 放棄 (`放棄：…`) with 負責人 and 期限, then 還沒定案 (卡關 · 風險 ·
   待討論). Not recorded → say so and point to the Doc.
6. **上週的變更提案** — what the 【週結】 decided: applied (live: 「核准了，已寫進總表」), would-apply
   (shadow), 退回, not named.
7. **卡關** — from the week's `#週報` posts, and who did not post.
8. Links to the Main Tracker, the Doc and the Ledger.

The 1.2 notice (`【週報】WB 10/5 那週沒有產出：週五的快照沒有記到`) goes to the owner only: a recap
built on a missing snapshot would be wrong, and a team that receives a "the robot broke" mail
learns nothing it can act on.

---

## When a beat fails — no notice in the space (SKB-091)

Until v4 a beat that caught its own failure posted a ⚠ line to the space. Since v4 only `collect`
may post there, so a beat that fails says so in its run report and ends with a `status=failed`
receipt, and nothing else. The runner retries it while its window is open; once it gives up, or its
window closes, `project-manager` mails the owner one 【排程沒跑完】 that names the beat and what it
affects (`project-manager/references/notice-mail.md`). The team hears of a missed beat from Peter,
not from a bot.

When the run report names a beat to a person, use the beat's Chinese name, never its mode:

| mode | 說法 |
|---|---|
| `recap` | 週一回顧信 |
| `collect` | 週四收週報 |
| `sections` | 週四各組進度 |
| `minutes` | 週五會議紀錄 |
| `tidy` | 週五整理 |
| `propose` | 週結信 |
| `apply` | 套用核准 |
| `snapshot` | 週末快照 |

---

## `notice` — moved to project-manager (SKB-091)

The 【排程沒跑完】 mail to the owner is `project-manager`'s since v4: its template is
`project-manager/references/notice-mail.md`.
