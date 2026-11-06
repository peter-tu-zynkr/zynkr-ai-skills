---
name: content-newsletter-draft
sheetId: "1.06"
description: >-
  Runs one issue of Peter's weekly zh-TW newsletter from topic to Kit: it measures the last issue, builds a reader brief from 讀者原話庫, runs a Hook Lab (six openings scored blind, Peter picks one), drafts both versions in one pass, edits and reader-tests them, then ships the Doc, the Notion card and a Kit draft with a [PROOF] copy to Peter's test inbox, and schedules the issue only on Peter's go. Use this skill whenever Peter says "幫我寫電子報", "來寫電子報", "寫newsletter", "電子報大綱", "這週電子報", or shares a topic/outline and wants it turned into a newsletter. Trigger even if Peter only gives a rough idea.
category: brand-marketing
project: content-newsletter-draft
platform: claude
status: Done
visibility: public
author: Peter Tu
input: "Peter's topic, outline or rough idea for this week's issue, or a 故事候選 from the last two weeks of livestream summaries"
process: "Measure the last issue, then topic, reader brief, Hook Lab (content-hook, content-title, a blind content-reader), shape, whole draft, edit, reader test, ship (Doc, Notion card, Kit draft, [PROOF] copy), and schedule on Peter's go"
output: "An issue Doc with both versions, its Notion card, and a Kit draft with a [PROOF] copy in Peter's inbox; on Peter's go, the issue scheduled for his Tuesday slot"
synergy: []
house-style: bound

---
# Content Newsletter Draft

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill content-newsletter-draft
```

Peter writes a weekly zh-TW newsletter for people who run projects, teams and their own careers with AI. Its strength is that Peter shows real things he built and learned. One run of this skill takes one issue from a topic to a Kit draft, with a [PROOF] copy in Peter's inbox, and schedules it when Peter says go.

The skill calls the zynkr-content-writer agents directly, through the Agent tool. It doesn't go through /zynkr-content-writer, whose paragraph-by-paragraph flow is for articles.

**Needs:**
- the zynkr-content-writer agents: `content-hook`, `content-title`, `content-draft`, `content-editor` and `content-reader`
- the google-workspace and Notion MCP servers
- for steps 0, 8 and 9, a checkout of the `zynkr-newsletter-drip` repo with its Kit key, at SKB-113 or later: its `kit_build.py` has `stats` and `newsletter --proof`, `--schedule` and `--unschedule`

Peter is asked at four points only:
- facts content-hook lacks (step 3)
- the opening and the CTA (step 3)
- a 【虛構】 detail, or a change to the chosen opening (step 6)
- the go to schedule (step 9)

Subagents can't ask him anything, so every question goes through this conversation.

---

## Constants

| What | Value |
|---|---|
| Issue Docs | Drive folder `1RvIRPNg4Kzp_B-9VFZRTXMX4tRgXpSlN`: one Doc per issue, named `(NN) 電子報｜<title>` |
| Content DB | Notion data source `collection://64bd3535-0cb3-4f96-946c-c2240294307c`: one card per issue |
| 讀者原話庫 | Notion data source `collection://1bf0b0a7-403e-46c2-a6e7-1b2acf279667`: readers' own words, role only. Its feedback sources are listed on the database's own page, not here |
| 開場範例庫 | Notion data source `collection://160150a0-92e1-45e5-997a-d90b279dfaf3`: openings worth learning from; content-hook reads it |
| 故事候選 | the `## 故事候選` section of the `逐字稿_*` Docs in Drive folder `1-aXLBpLizM0PyMbYu7TIb3xw50BrFL6a`, written by /curate-livestream-transcripts |
| Kit | `python3 kit_build.py …`, run in the drip checkout (`1.0 brand-marketing/1.5 newsletter-system/zynkr/kit-build/` in the company tree). Copy files live in its `src/newsletters/` |
| Test tag | `newsletter-test`: Peter's inbox only |
| Standing slot | Tuesday 09:00 台北 (Tue 01:00Z) |
| Web home | `https://newsletter.zynkr.ai`, Kit's Creator Profile. Every issue is public: it gets its own page there (`/posts/<slug>`) once it sends, and `stats` gives that page as `url`. Drafts and [PROOF] copies never get one |

**Kit exit codes:**
- 0: done
- 2: a dry run, nothing written
- 3: stopped, nothing written
- 1: Kit holds something that isn't as planned, after a write or found that way. Stop and show Peter the command's output; it says what Kit holds and what to do.

---

## Step 0: Measure the last issue

1. Run `python3 kit_build.py stats --since <45 days ago, YYYY-MM-DD> --json`. Each line is one issue sent to everyone, with its subject, its send time (`taipei`), its rates, already as fractions, and its web page (`url`, empty when it has none). If `stats` isn't a command there, the checkout is older than SKB-113: pull it, and stop if it still isn't.
2. For every line, find the issue's Content DB card by its Email subject. If the card's Status is still `Draft`, set it to `Published`. If the line has a `url` and the card's Web URL is empty, fill it: that is the page later issues link. Leave the card's `URL` column alone; it holds where the idea came from.
3. For every issue that went out at least 3 days ago and whose card's Open % is empty, not only the newest one:
   - **Count the replies.** Search Peter's inbox (it receives the newsletter's reply-to address) for `subject:"<Email subject>" after:YYYY/MM/DD`. Count the messages from readers, leaving out Peter, the newsletter itself and any [PROOF]. Record the count only, never who sent them.
   - **Write the card.** Fill Open %, Click % and Replies.

   An issue sent less than 3 days ago waits for a later run.

**Once a month:** when no 讀者原話庫 row was created this calendar month (its `createdTime`), also do two more things:

- **Show the pattern table.** For every card with a Hook pattern and an Open %, list the pattern, open rate, click rate and replies. Compare them with the baseline of the 8 issues sent from July to early November 2026: open 44.2%, click 0.86% (`stats --since 2026-07-01`). The table proposes; never change a rule from it.
- **Add new reader words.** Add 讀者原話庫 rows from the sources listed on its page.
  - Leave out any quote whose 原話 the database already holds.
  - Record roles only.
  - Tick 可公開引用 only where the source's consent column says yes.
  - Tick 敏感 for layoffs and the like.

## Step 1: Topic

If Peter has given a topic or an outline in this conversation, use it. If not, ask 「你這週想寫什麼主題？給我一個大綱或幾個關鍵想法就好。」 With the question, offer up to five 故事候選 from the `逐字稿_*` Docs of the last 14 days, newest first, each with its 代價 and its pattern.

Then:
- **Number.** NN is the newest issue in the Docs folder, plus one.
- **Overlap.** Check the topic against every past issue title in the folder, not just the last few (《[3.2]》 V). A concept an earlier issue already covered gets one line of callback, not a second explanation. Note that issue's Web URL from its Content DB card, or that it has none: step 5 needs it.

## Step 2: Reader brief

Query 讀者原話庫 for the 3–5 rows whose 主題 and 痛點 fit the topic best.

- Roles only: never a name, an email address or a company.
- A row marked 敏感 is never quoted; describe the situation only.
- A row whose 可公開引用 is unchecked is paraphrased, never quoted.
- If nothing fits, say so and use the reader the outline names.

Keep the rows you used: step 8 links them to the issue.

## Step 3: Hook Lab

1. **Receipts and questions.** Run `content-hook` with the topic, the promise, the reader brief and the source material.
   - If it returns questions, ask Peter all of them in one message.
   - Then run it again with his answers, writing "no answer" for any he skips. It asks only once per issue.
2. **Subjects.** Run `content-title` with `mode: email`. Give it the numbered openings with their receipts, and the subjects of past issues.
3. **Blind scoring.**
   - Shuffle the openings and relabel them A–F.
   - Delete each 模式 line. Keep the key (label → opening → pattern) in this conversation, never in the prompt.
   - Run `content-reader` with `mode: openings`. Give it the relabelled openings with their 真實 lines, the receipts, the reader brief and the topic.
4. **Show Peter the top three**, best first. For each, show:
   - the opening in full
   - its score out of 16, and its weakest item
   - its subject and preview
   - its pattern, revealed now

   In the same message, ask which CTA this issue carries: an event, a link, or none. Peter picks one opening, edits one, or writes his own.
   - If fewer than three survive, run `content-hook` once more with **patterns to skip**: every pattern scored so far, each with the critic's reason. Score only the new openings, blind as before.
   - If still none survives, show the three highest totals with what failed in each, and let Peter decide.
   - If he edits an opening or writes his own, score it with `content-reader` (openings mode, that one opening) and tell him the score. His choice stands.
5. **Record the pick:** its words, its pattern, its subject and preview, and the CTA. Content DB's Hook pattern shortens 表一's 「新聞切入，再講跟你有什麼關係」 to 新聞切入; every other name is the same. If the opening Peter settled on is below the bar (under 12, 代價 0 or 真實 under 2), record that he chose it over the bar: step 7 needs it.

## Step 4: Shape the outline

Build the outline around the chosen opening, following 《[2.2]》 §七:
- 4–5 sections, each a small real story, then what Peter changed or what happened
- 讀者先、我後
- the section where the opening's promise is paid off, named

This step is internal; Peter isn't asked.

## Step 5: Draft

Run `content-draft` with `mode: newsletter`. Give it:
- the chosen opening, word for word, with its subject and preview
- the outline, the reader brief and the receipts
- the house format block below
- the CTA, if Peter named one
- for each callback, the earlier issue's subject as readers saw it (its card's Email subject, or the subject `stats` prints), the month it went out, and its Web URL, or "no web page"

Check its reply with a script, not by eye:
- Tab 1 is 1,200–1,500 字 and Tab 2 1,200–1,400 字, counting every character except whitespace.
- Tab 1 begins with the chosen opening exactly.
- Tab 2 begins with the same sentences: with all whitespace removed from both, Tab 2 starts with the opening.

On a miss, send it back once with the numbers.

## Step 6: Edit

Run `content-editor` with `mode: newsletter`. Give it both tabs, the receipts list, and the chosen opening marked as the opening. It returns:
- 配額表
- 修改清單: 原句 → 類別 → 建議改法, each marked 必改 or 可改
- 【虛構】清單

Then:
- Apply every 必改.
- Apply a 可改 only when it changes no fact, number or quoted words.
- Never change the chosen opening without Peter.
- Ask Peter, in one message:
  - about every 【虛構】 in a 「我」 story, and every 「我」 detail marked 沒有收據. He confirms it, and the tag comes off, or he gives the real detail.
  - about any change the editor suggests inside the chosen opening.

A 【虛構】 in a 「你」 scene just loses its tag.

## Step 7: Reader test

Run `content-reader` with `mode: newsletter`. Give it both tabs, the chosen opening and its promise, the reader brief and the receipts. If Peter chose the opening over the bar (step 3), say so: the reader test then reports the opening's score but doesn't send the draft back for it.

- 通過 → step 8.
- 退回草稿 → back to step 5 once, with its notes; then steps 6 and 7 again.
- If the second draft fails too, show Peter both drafts with both reports. He chooses or edits.

## Step 8: Ship

1. **Doc.** Create `(NN) 電子報｜<title>` in the Docs folder with two tabs: 正式版 (the copy that goes to Kit) and 筆友書信體版本.
   - Use real Doc tabs, or two `#` H1 sections when tabs can't be made.
   - Read the Doc back. Importing HTML turns the text between two `$` in one paragraph into an equation, and merges an `<hr>` into the next paragraph.
2. **Card.** Create the issue's Content DB card, or update it if the topic came from one. Fill:
   - Google Doc, Full Title, No., Email subject and Hook pattern
   - Status `Draft`, Published channel `Newsletter` and Content type `Article`

   Then add the card to the 用在 of each 讀者原話庫 row the brief used.
3. **Copy file.** In the drip checkout, write `src/newsletters/NL-<YYYY-MM>-<slug>.md`.
   - It holds Tab 1 word for word, laid out in the copy-file format the drip README describes (headings become its heading markers; bold becomes plain).
   - 收件對象 is `newsletter-test`.
   - The CTA replaces 【CTA 待 Peter 確認】; ask Peter if he hasn't named one. The copy check refuses any 【…】, so no tag can reach Kit.
   - Every text is plain: the copy check stops at a link inside a sentence (`[text](url)`, an `<a>` tag or a bare `https://` address), any other HTML tag, and `**`. A link goes on its own `〔連結〕` row.
   - Every link to an earlier issue must load: `curl -s -o /dev/null -w '%{http_code}' <url>` gives 200. Kit keeps an address for an issue taken off the web, and it returns 404. A link that doesn't load comes out of both tabs and the copy file: keep the words that name the issue, drop its link, and tell Peter which issue it was.

   Commit the file: it is the copy's source of truth.
4. **Kit draft.**
   - Run `python3 kit_build.py newsletter --copy src/newsletters/<NAME>.md`. It prints what it would write.
   - Run it again with `--yes`. It must say it wrote the draft and read it back.
5. **Proof.** Run `python3 kit_build.py newsletter --copy src/newsletters/<NAME>.md --proof --yes` in the background; it usually takes 15–30 minutes and can take up to an hour. It sends a `[PROOF] <subject>` copy to `newsletter-test` only, waits for Kit to finish, and records the version. Wait for it to exit.
6. **Tell Peter** the proof is in his inbox, and ask for his go, only once the proof command has exited 0 with PROOF PASSED or PROOF ALREADY PASSED. Give him:
   - the subject and the preview
   - the slot: the next Tuesday 09:00 台北, unless he names another

   Any other ending: show Peter the output instead, and don't ask for a go. After NOT CONFIRMED YET, run the same command again; it waits for the same proof and never sends twice.

## Step 9: Schedule, on Peter's go

Run this only after Peter says go, in this conversation, for this issue. A go never carries over to another issue or another version.

1. Run `python3 kit_build.py newsletter --copy src/newsletters/<NAME>.md --schedule --at "YYYY-MM-DD HH:MM" --to everyone`. This is the dry run: `--at` is 台北 wall time, and it prints the plan and a 6-digit code.
2. Run the same command with `--yes --confirm <code>`. It writes once, reads back, and undoes any difference.
3. Report what Kit now holds:
   - the status
   - the time, in 台北 and in UTC
   - the audience
   - that it is public, in the tool's words: its page goes up on the web home once it sends, and step 0 of the next run records it. If the tool also printed a note that Kit already gives it a web address, pass that on too: its page may be up before the send.

「hold」 from Peter at any time stops everything: run `python3 kit_build.py newsletter --copy src/newsletters/<NAME>.md --unschedule --yes`, then report what Kit holds.

After the issue goes out, step 0 of the next run sets its card to `Published`, records its Web URL and measures it.

---

## House format (brief content-draft with this block verbatim)

**Container**
- One Google Doc per issue in the Docs folder, named `(NN) 電子報｜<title>`.
- Two tabs: Tab 1 正式版 (the copy that goes to Kit) and Tab 2 筆友書信體版本.
- Exemplars: (59) `1VrMSecK9pSVQRFoxOmYKS8xn5tAcAMllFUfUZC2X9pM`, (60) `1449GY5oyBshxmxyuiKsp7dmhunUW_nOeLZCHowunbTg`, (61) `1ZW50dFApBTPaYv-iSryizh7GMvmGV_cvxuiYKChosTo`.

**Past issues (both tabs)**
- A callback names the earlier issue in words: its month and its subject (「八月那封〈為什麼有了 AI，我反而更忙？〉」).
- Never name an issue by its number (「第 N 期」, (NN)): the subjects carry none, so readers never see them.
- When the brief gives that issue a Web URL, link its page:
  - In Tab 1, on a line of its own right after the paragraph that names it, with the issue's subject as the link text. The copy file makes that line a `〔連結〕` row (subject | Web URL): Kit's rows take plain text, so a link inside a sentence would reach readers as typed, and the copy check stops at one.
  - In Tab 2, on a few of the sentence's own words.
- An earlier issue with no web page is described in words (「上個月講時間管理那封」), never linked or numbered.

**Tab 1 正式版: 1,200–1,500 字**
- The chosen opening, word for word, with no heading.
- 4–5 sections with `##` headings (一、二、三…) of 12 字 or fewer. Each section has 2–4 substantial multi-sentence paragraphs, not one-line social-post fragments.
- At most 1–2 bold sentences in the whole piece.
- The ending is 《[2.2]》 §七 結尾固定. The CTA goes on the line above the question; until Peter names it, that line is `【CTA 待 Peter 確認】`.

**Tab 2 筆友書信體版本: 1,200–1,400 字**
1. Open with the chosen opening's sentences, word for word, one per line. A reader's question in it is the reader's own words, never an invented 「很多人問我」 (《[3.2]》 K).
2. Address the reader as 「你」 throughout. Anticipate at most one objection, and only a real one (《[3.2]》 J).
3. No headings. **No separator lines between paragraphs: never insert `–` / `—` / `---` lines; a blank line separates paragraphs** (Peter's rule, 2026-08-17).
4. Mostly one sentence per line; each sentence is its own paragraph.
5. No bold.
6. Explain jargon in the same sentence, in plain words.
7. End per 《[2.2]》 §七, with 「下禮拜見 ·」 as the last line.
8. Warm but not cutesy.

**Language and voice**
- zh-TW. Chinese headings and taglines carry no ending 句號; use 「·」 for series.
- Voice and structure: 《[2.2] 內文風格指南》 §三–§七 (開場四環節 · 開場怎麼寫 · 帶收據 · 語言使用 · 資訊節奏 · 電子報格式). It is Doc `1ect0fDoHZQ7srFEQvLNCSLsQk-UTawvbxpt3SteYP1M`; use its `# 最終產出` section.
- Forbidden patterns and their per-issue caps: 《[3.2] 禁用詞清單》 A–W. X is for sales mail only.
- The facts match across the tabs. Only 【CTA 待 Peter 確認】 may remain as a placeholder, and only until Ship.

## House style

Writing style is **not owned by this file**. The house voice lives in two Google Docs under
`[@] 寫作指南` (`12DBdFz3SK22ie9im_ThFMI7IBRXsTZsV`), read at runtime:

- 《[2.0] Zynkr 通用風格指南 House Voice》 `10bOIQwRm9Pxwgct4hlwCwK_B4Pipai1HqBPZKzyRHSE` —
  the universal core, plus the addendum for this surface
- 《[3.2] 禁用詞清單 Forbidden Words》 `1N5sHLP4qzmmhpCGsi6KElxi1z0MFe4QZ0Q_35T10Uyg`

Read both before producing client- or reader-facing text, and scan the draft against 《[3.2]》
before handing it over. If Drive is unreachable, say so in the output rather than proceeding
unchecked. Never re-implement either list inside this file.
