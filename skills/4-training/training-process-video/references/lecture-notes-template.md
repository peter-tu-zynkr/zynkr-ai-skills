# Lecture Notes Template

Use this template when appending speaker notes to a chapter file (`claude-code-ops-ch*.md`).
Append the entire block below at the end of the target chapter file. Never modify existing content.

---

## Append Block Format

```markdown
## Lecture Notes from Livestreams

### [Stream Title] ([YYYY-MM-DD])
**Chapter alignment:** Ch[N] — [Chapter title]
**Content type:** example | explanation | case-study | demo
**Match score:** [0–3] — [one-line reason for the score]

[Speaker notes in first-person readable format. Write as if the lecturer is reading this aloud.
Keep sentences short. Preserve the speaker's terminology and examples exactly.
2–6 sentences is typical; longer content should be split into sub-points.]

**Key phrase:** > "[Most memorable or quotable line from this segment]"

---
```

---

## Field Rules

**Stream Title**
- Use the official stream title as given to the manager skill
- If no title was given, derive a short slug from the main topic

**Chapter alignment**
- State the chapter number and title from `4.4.1 course.md`

**Content type** — pick one:
- `example` — a concrete case or scenario the speaker walked through
- `explanation` — a conceptual clarification or definition
- `case-study` — a real-world scenario with a before/after or outcome
- `demo` — a live tool operation the speaker performed on screen

**Match score**
- `3` — directly addresses the chapter's core concept with new depth
- `2` — clearly relevant and adds value; minor overlap with existing notes
- `1` — tangentially related; low added value
- `0` — does not fit this chapter

Only content with score ≥ 2 is proposed to the user for approval.

**Key phrase**
- One direct quote from the transcript (verbatim preferred)
- If no memorable quote exists, omit this field

---

## Example

```markdown
## Lecture Notes from Livestreams

### Claude Code 營運直播 Day 1 (2026-03-15)
**Chapter alignment:** Ch4 — Skills 與 Subagents
**Content type:** example
**Match score:** 3 — directly demonstrates skill packaging for ops workflows

在這場直播裡，我們實際示範了把「每週週報整理」包成一個 skill 的完整過程。
首先定義輸入：散落在各處的 meeting notes 和 Slack 訊息。
然後定義處理邏輯：按照 done / in-progress / risk / next 四個欄位彙整。
最後定義輸出格式與交付位置。
這個流程就是 skill 的骨架，任何重複性任務都可以用同樣方式拆解。

**Key phrase:** > "先把規則說清楚，再讓 AI 執行，這才是對的順序。"

---
```
