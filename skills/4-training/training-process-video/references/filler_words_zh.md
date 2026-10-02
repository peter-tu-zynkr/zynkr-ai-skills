# Filler Words & STT Noise — Chinese Transcripts

Reference list for cleaning livestream transcripts before processing.

---

## Filler / Disfluency Words (remove when purely verbal padding)

- 呃
- 嗯
- 就是
- 然後
- 那個
- 你知道
- 我覺得（when used as pure hedge, not expressing genuine opinion）
- 其實（when purely verbal padding, not introducing a contrast）
- 這個
- 好那
- 好那個
- 對對對
- OK 好
- 對啊
- 就是說
- 怎麼講

---

## STT Noise Patterns (fix on sight)

- **Homophone errors**: fix obvious misrecognitions based on context (e.g., 其時 → 其實, 再說 → 再來)
- **Duplicated fragments**: remove repeated sentence starts (e.g., "我們我們..." → "我們...")
- **Collapsed punctuation**: break up long unpunctuated runs into readable sentences
- **Abandoned starts**: remove false starts where the speaker restarted mid-sentence

---

## Keep (do not remove)

- Domain terms: IPO, GUIDE, SOP, RAG, FE/BE/DB, HITL, CRUD, MCP, CLI, IDE
- Meaningful discourse signals that mark logic transitions (e.g., "所以", "因此", "但是", "不過")
- All examples, numbers, and proper nouns
- "我覺得" when expressing a genuine opinion or stance
- "其實" when introducing a genuine contrast or correction
