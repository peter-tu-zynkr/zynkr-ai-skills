# Q&A Knowledge Base Entry Format

Every entry in `knowledge-base/qa-master.md` must follow this schema exactly.

---

## Schema

```markdown
## Q: [Canonical question]
**Category:** ch1-intro | ch2-crud | ch3-process | ch4-skills-subagents | ch5-mcp | ch6-principles | general
**A:** [Answer — complete, self-contained, no pronouns that require prior context]
**Source:** [stream-title YYYY-MM-DD]
**Status:** confirmed | needs-review
```

---

## Field Rules

**Q (Canonical question)**
- Rephrase the question in clear, standard Chinese if the original was messy or mid-sentence
- Remove filler words and false starts
- End with a question mark

**Category**
- Match to the course chapter most relevant to the answer
- Use `general` only if the question doesn't fit any chapter

**A (Answer)**
- Write as a standalone answer — a reader with no stream context should understand it
- Keep to 1–4 sentences for simple factual answers
- Use a short list if the answer has 3+ components
- Do not include phrases like "as I said" or "earlier we discussed"

**Source**
- Format: `[stream slug] YYYY-MM-DD`
- Example: `claude-code-ops-demo 2026-03-15`

**Status**
- `confirmed` — answer is clearly stated in the transcript
- `needs-review` — answer was inferred, partial, or potentially outdated

---

## Classification Labels (for diff report)

When the agent compares extracted Q&As against the existing KB, it classifies each entry:

| Label | Meaning |
|-------|---------|
| `NEW` | Question not in KB; no similar question exists |
| `DUPLICATE` | Question already in KB with same or equivalent answer |
| `VARIANT` | Similar question in KB but phrasing or scope differs |
| `CONTRADICTS` | Same question in KB but answer conflicts |

---

## Example Entry

```markdown
## Q: Claude Code 可以直接讀取 Google Sheets 嗎？
**Category:** ch5-mcp
**A:** 可以，但需要先設定 MCP 連線。透過 Google Workspace MCP，Claude Code 可以讀取指定試算表的資料，也可以寫回欄位。建議先讀後寫，並在寫入前顯示預覽確認。
**Source:** claude-code-ops-demo 2026-03-15
**Status:** confirmed
```
