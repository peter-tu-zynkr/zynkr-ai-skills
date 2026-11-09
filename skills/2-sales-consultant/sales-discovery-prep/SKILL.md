---
name: sales-discovery-prep
category: sales-consultant
project: sales-discovery-prep
platform: claude
status: Done
visibility: public
author: Peter Tu
sheetId: "2.17"
description: "Prepare for ONE booked discovery call before it happens. Give it a CRM deal (name, 交易 number or id): it gathers what we already know (the deal, the 🔎 AI 背景研究 brief, the mail thread, the calendar invite), reads the house question bank, writes two hypotheses each with a question that tests it, picks a client-specific 30-minute question list with why-we-ask, expected answers and how to respond, drafts the agenda mail as a threaded Gmail draft (never sent), and saves one [會前準備] note on the deal after a single confirmation. Trigger on /sales-discovery-prep or when the user says 'prep the discovery call', 'prepare for my call with <company>', 'what should I ask <company>', 'discovery call questions', '準備探索會議', '會前準備', '探索會議要問什麼', '幫我準備明天的會', '列探索會議問題', '幫我寫議程信'. BOUNDARY — do NOT hijack: /sales-research (the company brief — this skill reads it and runs it first when missing), /sales-discovery (runs ON or after the call and logs the [DISCOVERY] summary), /sales-follow-up (the mail after the call), /sales-outbound (the first reply that books the call), /sales-manager (decides which deal needs prep and calls this skill)."
input: "One CRM deal with a discovery call booked (name, 交易 number or id), plus the company's 🔎 AI 背景研究 brief (this conversation, pasted, or run /sales-research first)"
process: "Resolve the deal → gather deal, research brief, mail thread, invite → read the question bank (Atlas, else references/) → two hypotheses → tailored question list with why / expected answer / response → agenda Gmail draft → confirm once → create_note"
output: "A dated [會前準備] note on the deal (hypotheses, question list with expected answers) and, if the call is a day or more away, an unsent agenda-mail Gmail draft"
synergy: ["sales-research", "sales-discovery", "sales-follow-up", "sales-manager"]
handoff: ["sales-discovery"]
reads: ["sales.sop-discovery-call", "company.sales-pipeline-rules"]
house-style: bound
---

# sales-discovery-prep

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill sales-discovery-prep
```

Turn what we already know about a client into a plan for the 30-minute discovery call: two hypotheses worth
testing, the questions to ask (each with why we ask it, what the client will probably say, and how to respond),
and the agenda mail that goes out the day before. The plan is saved as one note on the deal for the deal owner, who
runs the call. Each hypothesis is tested in the call by its own question; nothing reads the note back afterwards,
because no CRM tool reads a deal's timeline.

> **Where this fits:** `/sales-outbound` (the reply that books the call) → `/sales-research` (the company brief) →
> **`/sales-discovery-prep`** → the call → `/sales-follow-up` (the follow-up mail), with `/sales-discovery` first when
> the needs summary is wanted. `/sales-manager` hands a deal here when someone asks to prep its call.

**What it never does:** send a mail, write the deal's `notes` field, move a deal stage, or invent a fact about the
client. Expected answers are guesses and are labelled as guesses.

---

## Step 1 — Resolve the deal, the company and the contact

1. `mcp__zynkr__list_deals(search="<deal name or 交易 number>")` → `mcp__zynkr__get_deal(id=…)`. More than one
   hit → list them and ask which. No hit → stop: this skill never creates a deal (that is `/sales-outbound`).
2. Read `stage`. Expect `contacted` (a call is booked but the four facts are not known yet). If the deal is already
   `qualified` or later, say so and ask whether this is a second discovery call before going on.
3. `mcp__zynkr__get_company(id=<company_id>)` and `mcp__zynkr__get_contact(id=<contact_id>)`. Address the contact by
   the name **they write** (their mail signature or the CRM record). Never derive a name from a meeting transcript.
4. Compare the runner with the deal's owner: `mcp__zynkr__whoami` gives the runner's id as `owner_id`, and `get_deal`
   gives the deal's. The deal owner runs the call and signs the agenda mail. When the two differ, Step 6 drafts no
   mail and the report says 「請交易負責人在自己的對話跑」; the note in Step 7 is still written. A deal with no
   owner has nobody to sign the mail: ask who runs the call before Step 6.

## Step 2 — Gather what we already know

No CRM tool reads a deal's timeline of notes, meetings and mails, so collect the inputs this way:

| Input | Where it comes from |
|---|---|
| The deal | `get_deal`: `name`, `stage`, `lead_source`, `deal_type`, `notes` (the summary paragraph and any `客戶時限：` line) |
| The 🔎 AI 背景研究 brief | In priority order: (a) a brief `/sales-research` produced earlier **in this conversation**; (b) the user pastes the note from the company page; (c) neither → run `/sales-research` on the company now, then continue. Never prepare a call without it |
| The client's own words | `mcp__google-workspace__search_gmail_messages(query="from:@<domain> OR to:@<domain>")` → `get_gmail_thread_content` on the latest thread: what they asked for, in their words, and the Message-ID / References for threading |
| The call itself | `mcp__google-workspace__get_events` for the next 14 days, matched on the contact's email: date, time (台北時間), length, meeting link, attendees |

Missing the call time is fine: Step 6 then leaves placeholders and says so.

## Step 3 — Read the question bank

Read the house question bank at run time; do not work from memory:

```text
mcp__zynkr-atlas__get_knowledge(key="sales.sop-discovery-call")
```

It holds the four-step questioning logic, the question groups (痛點 · 決策者 · 預算 · 時程 · 導入條件) with the
reason for each question, the opening line, the boss opener, and the agenda-mail template. Also read
`company.sales-pipeline-rules` for the 客戶時限 rule.

**Atlas not reachable, or the note is not served in this workspace** (a public install outside Zynkr) → use
`references/question-bank.md` in this folder, and say in the report which source was used.

## Step 4 — Write two hypotheses

From the industry, the contact's role and what they wrote, guess the two things they are most likely stuck on.

| Rule | Why |
|---|---|
| Each hypothesis cites its evidence (a line from the brief or their mail) | A guess with no source cannot be weighed before you test it |
| Each one gets **one** question that would confirm or kill it | Hypotheses are for asking, not for telling the client |
| Write them as guesses: 「可能」「推測」 | They go on the deal; nobody should read them as facts |

## Step 5 — Pick and tailor the question list

Build a list that fits 30 minutes (about 10–12 questions; the bank's timing: 痛點 3–20 min, 決策 · 預算 · 時程
20–25 min, summary 25–30).

| Group | How many | Rule |
|---|---|---|
| 痛點 | 4–5 | Follow the four steps (現在怎麼做 → 代價 → 試過什麼 → 想做到什麼). Always include 「為什麼是現在」 and the 核心價值 question |
| 決策者 | 2 | Always include 「誰做最後決定」 and 「您會怎麼跟老闆報告」 |
| 預算 | 1–2 | Range only. If the brief suggests they will not name a number, lead with the cost question |
| 時程 | 1–2 | Ask for a fixed date (budget cycle, peak season, a launch) |
| 導入條件 | 2–3 | **Only** when the sale is a system or an AI rollout. Open the group with the bank's why-we-ask line |
| Hypotheses | 2 | The two testing questions from Step 4, placed where they fit |

For every question write four things:

1. **問** — the bank's question, reworded for this client (their tools, their industry, the thing they wrote about).
   Keep one question per line; never stack two.
2. **為什麼問** — the bank's purpose for that question.
3. **預想回答** — one or two answers the client is likely to give, grounded in the brief or their mail. Mark each
   「（推測）」.
4. **你可以怎麼接** — the next probe, using the bank's probes where they apply (「都很重要」→「如果只能先解決一件」;
   「要回去報告」→「老闆最在意成本、風險還是時間」; no number → ask the cost first).

Add the opening line from the bank. If the contact is the owner or the boss, add the boss opener (使命 → 怎麼衡量 →
十年後 → 成功的關鍵) before the pain questions.

## Step 6 — Draft the agenda mail

Draft it only when the runner is the deal owner (Step 1), the call is **at least a day away** and no agenda has gone
out yet (search the sent mail for the meeting date). Otherwise skip, and say why.

- Fill the bank's agenda template: the contact's name as they write it, the date and time (台北時間) and the link
  from the calendar event, the sender's name from Step 1. Unknown values stay as ＜＞ placeholders, named in the report.
- Write it in the language of the client's own mail.
- Thread it onto their latest mail:

```text
mcp__google-workspace__draft_gmail_message(
  user_google_email="<your-google-workspace-account>", to=<contact email>, cc=<the thread's Cc>,
  thread_id=<id>, in_reply_to=<last Message-ID>, references=<chain>,
  subject="Re: <original subject>", body=<the mail as HTML>,
  body_format="html", include_signature=true)
```

**Never send it.** The person running the call reads it and sends it.

## Step 7 — Preview, confirm once, write the note

Show the whole prep in the chat: the hypotheses, the question list, the opening, the agenda-draft status. Ask once:
**「這份會前準備要存到交易上嗎？」** Edits come back here and are shown again.

On yes, preview then apply:

```text
mcp__zynkr__create_note(deal_id=<id>, subject="[會前準備] <公司名> 探索會議 · <YYYY-MM-DD>", body=<below>)
→ the same call with confirm=true
```

Note body (zh-TW):

```text
[會前準備] <公司名> 探索會議
會議：<日期 時間（台北時間）或「時間未定」>｜出席：<客戶方>／<我方>
依據：🔎 AI 背景研究 <日期>；往來信件 <n> 封；題庫 <Atlas sales.sop-discovery-call 或 references 備份>

兩個假設（推測）
1. <假設> — 依據：<出處> → 要驗證：<問題>
2. <假設> — 依據：<出處> → 要驗證：<問題>

問題清單（30 分鐘）
痛點
1. 問：<問題>
   為什麼問：<目的>
   預想回答：<回答>（推測）
   你可以怎麼接：<追問>
決策者 / 預算 / 時程 / 導入條件（同一格式）

開場：<開場詞>
議程信：<已擬草稿，未寄出 | 未擬：原因>

預想回答是會前的推測。兩個假設在會中用各自那一題驗證。
```

Never write the deal's `notes` field and never move the stage: the stage moves after the call, when the four facts
are known (`/sales-follow-up` or the deal owner).

## Step 8 — Report

Three lines: the deal and the call time; the note written (or not) and the question count; the agenda draft
(drafted, skipped and why, or placeholders left). Then name the next step: after the call, give the transcript to
`/sales-follow-up` for the follow-up mail, and to `/sales-discovery` first when the needs summary is wanted.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under `[@] 寫作指南`
(`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at run time:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` — the universal core, plus
  the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before writing the agenda mail and the note, and scan the draft against 《[3.2]》 before showing it. If
Drive is unreachable, say so in the output rather than proceeding unchecked. Never re-implement either list inside
this file.
