# Message templates

All output is zh-TW. **Read `wording.md` before composing anything** — these templates set the
voice, and every free-text line the model writes at run time (agenda bullets, failure notices,
the recap mail body) has to match it.

Every Chat post ends with the footer line — it is the idempotency marker the next run looks
for, so it is not decoration and its exact shape is frozen:

```
— zynkr-ops-weekly · WB 8/24
```

Each mode's **first line** is frozen too: Step 1 knows a mode already posted today only by the
footer **and** that first line together (`nudge` 這週的週報開始收囉 · `chase` 還缺這幾位的週報 ·
`agenda` 週四的議程整理好了 · `decisions` 今天談定的事 / 今天的會沒有談定的決議). Since SKB-070 two
modes post on a Thursday, so the footer alone no longer tells them apart. The rest of each line may
change; that opening may not (`wording.md` → frozen strings).

Keep posts short. Chat scrolls; anything past a screen is not read. The Doc is where length is
allowed to live.

---

## `nudge` — Mon 09:00

Quote last week's decisions **read from the Doc**, so people report against something concrete.

```
這週的週報開始收囉，週二早上 09:00 截止

上週四談定的事
· <決議 1> — <owner>，<日期>
· <決議 2> — <owner>，<日期>
· <決議 3> — <owner>，<日期>

回報照這個格式就好，四行：

#週報
上週:
- 事項 — 完成 / 進行中 / 卡住
本週:
- 事項
數字: 報名 72 / 訂閱 +18        （沒有就寫 —）
卡關: 需要誰決定什麼            （沒有就寫 無）

— zynkr-ops-weekly · WB 8/24
```

Re-post the format **verbatim** every week. The ask has already drifted once; repetition of the
exact shape is what stops a variant from becoming the norm.

The status words are Chinese on purpose. `parse_reports.py` accepts both, but the team writes
Chinese, and a template that asks for `Done / WIP / Blocked` is asking them to code-switch for
no reason.

---

## `chase` — Tue 09:30

Only when someone is actually missing. Naming nobody teaches people to skip the message.

```
還缺這幾位的週報，週四早上 9 點前補都算數

· <Name A>
· <Name B>

議程週四早上就會整理好，沒補到的就不會出現在上面

— zynkr-ops-weekly · WB 8/24
```

Plain text names, not live @-mentions: `send_message` posts text, and reliable programmatic
mentions need an annotation payload the tool does not expose.

---

## `agenda` — Thu 09:00 (pointer only)

The agenda itself lives in the Doc. This post is a pointer.

```
週四的議程整理好了 → <doc link with #tab and heading anchor>

這次要決定的三件事
· <決策 1>
· <決策 2>
· <決策 3>

另外：逾期 <n> 件 · 連續三週以上沒動 <m> 件 · KPI 沒達標 <k> 項
會議只談這些，進度不再一個部門一個部門唸

— zynkr-ops-weekly · WB 8/24
```

Each decision is phrased as the choice it asks for — 「#2.04 停了 6 週：繼續做（做到哪天）、交給誰，還是先放掉？」
— not as a status line. Since SKB-070 the candidates come from the evidence too (4.4), not only from
the `卡關` line.

If there are still no decisions to make, say so plainly and say why — an agenda that pretends to
have three decisions is worse than an honest empty line. This line takes the place of the 三件事
block only: the post still opens with 「週四的議程整理好了 → <link>」 and ends with the footer, which
is how Step 1 knows the agenda already posted.

```
這次沒有要決定的事：沒有人寫卡關，Tracker 上也沒有停住或逾期、需要拍板的項目
```

---

## `decisions` — Thu 22:00 (Chat, three lines)

Short by design — next Monday's `nudge` quotes it.

```
今天談定的事
· <決議 1> — <owner>，<日期>
· <決議 2> — <owner>，<日期>
· <決議 3> — <owner>，<日期>

完整版已經寄到大家信箱，下週的區塊也開好了

— zynkr-ops-weekly · WB 8/24
```

**When nothing was decided** (`SKB-044`): one line instead of three, and no mail. Say what
happened, not what people should have done. If some items came up without an owner or a date,
add their count in brackets; with none, leave the brackets out.

```
今天的會沒有談定的決議（2 件還缺負責人或日期，先列為還沒定案）

— zynkr-ops-weekly · WB 10/5
```

---

## `propose` — Fri 10:00 (the 【待核准】 mail, to the owner only)

`scripts/proposals.py check` renders it from the checked rows; never compose it by hand.

Subject: `【待核准】WB 10/12 那週 · 5 件（2026-W42）` — the ISO key is in the subject on purpose:
`apply` finds the thread by it.

Body, in order:

1. One line: how many changes, and how to answer — 「全部核准」、「核准 1 3」、「退回 2」或「全部核准 退回 2」.
2. One line on how a reply is read: write only 核准, 退回 and the numbers (a thanks is fine), never
   「除了 2 都核准」; an approving reply that asks a question or says anything else gets asked to
   restate; `apply` confirms in the thread what it recorded, and until that confirmation a newer
   complete reply replaces an older one; replies before Sunday 22:00 count; rows the reply does
   not name are not applied.
3. While `routine.apply_mode` is `shadow`: **試行中** — approved rows are recorded, not written, and
   Monday's recap shows what would have changed.
4. The table: 編號 · 項目 · 欄位 · 現在 → 建議 (a 備註 row shows only 「加一行：<the new line>」) ·
   為什麼 · 證據 (the decision or report, in its own words) · 把握.
5. The footer marker `〔zynkr-ops-weekly〕 待核准 <ISO week>`.

The mail goes out as HTML, and the send adds a flattened text copy of it; that copy is what `sent`
and `apply` read. `sent` requires it to be, word for word, the mail `check` wrote and records its
hash with the rows'; `apply` requires the thread's mail and the week's Ledger rows to match those
hashes (or, when no thread was recorded, the mail to be the one the Ledger rows render), so a value
changed on the way never reaches a decision. Each row's 編號 and `#item` sit side by side in it (`4#1.03`), which names a missing
row. `check` refuses a mail whose text runs past 6,000 characters: every reply quotes it.

`apply` writes in the thread only as plain text starting with the marker, which is how the next run
tells its own messages from the owner's:

- **When a reply cannot be read** (once per reply): what it could not read, the four example
  replies, and the range of row numbers.
- **When a reply draft has stayed open two hours** (once a week): that nothing is recorded until it
  is sent or deleted.
- **When a reply is recorded**: the reply's time, then 核准 · 退回 · 沒寫到、這次不套用 as row
  numbers, and that later replies change nothing this week. This message is what makes the
  week's decision final.

---

## `decisions` — Thu 22:00 (recap mail)

Subject: `【營運週報】2026-08-27（WB 8/24）— 決議 3 件 · 逾期 2 件`

Recipients: **the owner-chip emails read from the Doc this run** — never a list kept in config.
Someone joins or leaves, the Doc changes, and routing and this list move together.

Body sections, in order:

1. **這週談定的事** — 決議 · owner · 日期. A decision missing an owner or a date is not a
   decision; list it under **還沒定案** instead of promoting it.
2. **逾期和一直沒動的** — items at `↻3週` or more, with how long they have been open.
3. **KPI 沒達標** — 指標 · 目前 · 目標 · 數字出處的儲存格.
4. **下週各部門要做的事** — one line per department, from the `本週:` lines.
5. **這週的 Doc 區塊** — direct link.

Written as an HTML mail via `send_gmail_message`. Plain, legible, no images.

---

## `recap` — Mon 09:00 (mail, SKB-044)

Subject: `【週報】WB 10/5 那週 — 變更 4 件 · 決議 2 件 · 逾期 1 件`. The first week reads `第一次記錄`
instead of a change count, and a week whose decisions never reached the Ledger reads `決議沒記到`,
never `決議 0 件`. The ISO key stays out of the subject: it is machine-only.

Recipients: `routine.recap_audience` decides. `owner` while the recap is new, `team` (every
address in `reporters`) once the owner has seen it work; `routine.recap_team_from` (a Monday,
`YYYY-MM-DD`) lets the owner set that switch ahead of time. The mail itself is built by
`scripts/recap.py render` from the Ledger; the run writes only the TL;DR.

Body sections, in order:

1. **重點** — at most three lines the run writes, each citing the item number it is about. A line
   without one is dropped before sending.
2. **上週改了什麼** — every changed cell in the Main Tracker between the last two Friday snapshots,
   `#1.03 SEO 文章 — 狀態：進行中 → 完成`, plus items added and removed.
3. **要注意的** — 逾期 · 兩週內到期 · P0/P1 還沒排日期 · 備註說做完了但狀態沒改, each with its evidence,
   from zynkr-gm's state rules.
4. **上週談定的事** — 決議 · 負責人 · 期限, then 還沒定案. Not recorded → say so and point to the Doc.
5. **卡關** — from the week's `#週報` posts, and who did not post.
6. Links to the Main Tracker, the Doc and the Ledger.

The 1.2 notice (`【週報】WB 10/5 那週沒有產出：週五的快照沒有記到`) goes to the owner only: a recap
built on a missing snapshot would be wrong, and a team that receives a "the robot broke" mail
learns nothing it can act on.

---

## Failure notice — any mode

Posted to the space when an assertion fails. The point is that a broken loop announces itself
in the room where people already are, rather than dying quietly in a log.

Name the beat in Chinese — `nudge` / `rollup` / `agenda` are internal names and mean nothing to
the people reading:

| mode | 說法 |
|---|---|
| `nudge` | 週報提醒 |
| `rollup` | 週報彙整 |
| `chase` | 補件提醒 |
| `agenda` | 週四議程 |
| `decisions` | 會後回貼 |
| `recap` | 週一回顧信 |
| `tidy` | 週五整理 |
| `propose` | 待核准信 |
| `snapshot` | 週五快照 |
| `apply` | 套用核准 |

```
⚠ 這週的<說法>沒跑完：<一句話講原因>

<需要誰做什麼>

— zynkr-ops-weekly · WB 8/24
```

Concrete cases that must produce one:

| Assertion | Notice |
|---|---|
| Recap mail not found in `in:sent` after sending | 信沒寄出去，決議目前只在大廳和 Doc 裡 |
| Target Thursday section missing at rollup | 下週的區塊沒開，Apps Script 的排程可能沒裝或沒跑到 |

These notices go to the space and can only be sent by a beat that is running. A beat that never
started, hung, or gave up says nothing here; the runner's `notice` mail below covers it.

---

## `notice` — mail to the owner only (SKB-070)

Sent by the `notice` mode when a beat of the week gave up, or its window closed before it ran. It
goes to `google_account` and nobody else: the team learns nothing it can act on from "the robot
broke", and the owner can.

Subject, exact (the run compares it with the subjects in `in:sent` before sending, so it must not
change between tries): `【排程沒跑完】WB 10/12 那週：週四議程、會後回貼`. Use the `label` the prompt
gives, list the beats in the order given, joined by 、, named from the 說法 table above. With
`rehearsal=1`, put `【演練】` in front. The prefix is deliberately not 【營運週報】: `decisions` looks for
its own recap by subject, and must never mistake this mail for it.

Body, plain text, one block per beat:

```
WB 10/12 那週有排程沒跑完：

· 週四議程（agenda）— 試了三次都沒成功，這週不會再試
  影響：週四的會沒有自動整理好的議程，要從 Doc 和大廳直接看
  要做的事：想補就在 Claude Code 跑 /zynkr-ops-weekly agenda；不補也沒關係，下週會照常

細節在 ~/Library/Logs/zynkr-ops-weekly.log

〔zynkr-ops-weekly〕 notice 2026-W42
```

What each code means, in words the owner reads at a glance:

| code | 說法 |
|---|---|
| `gaveup` | 試了三次都沒成功，這週不會再試 |
| `failed-<n>` | 失敗 <n> 次之後，時段就過了 |
| `never-ran` | 整個時段都沒跑到（筆電沒開、在睡，或前一步太晚才完成） |

One line of impact per beat, from what that beat would have delivered: a missing `decisions` means
no recap mail and no Ledger record of the meeting; a missing `snapshot` means Monday's recap has
nothing to compare; a missing `propose` or `apply` means no tracker changes this week. Never guess a
cause beyond the code.
