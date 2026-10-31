# Intent Taxonomy — the Atlas 知識庫 (collection `kb`)

Each resolved question is classified into exactly one intent. The intent decides **which section**
the card is filed in: the draft's `collection`, `kb.<slug>`. The live list is the walk in Step 3
of the skill — the rows of kind `collection` that `list_knowledge(collection: "kb")` lists, each
filed directly under `kb`; this file is the authoring reference. Keep the two in sync.

Keep this list small and stable. When a question genuinely doesn't fit, **propose a new section
to Peter** (don't silently overload `kb.other`). Once he approves, draft it as a collection (see
`new-section-playbook.md`); once he has published it, add a row here so it becomes first-class.

Every section also owns one Doc in the Drive backup mirror — a new section gains a Doc and a
registry row in `drive-mirror.md`. `nn` is that Doc's number.

| Section key | nn | Section | Covers | zh-TW / EN aliases |
|---|---|---|---|---|
| `kb.core-facts` | 01 | Core Facts 核心事實 | Canonical `fact` cards only — pricing tables, policies, durations. NOT a Q&A intent. | 核心事實, canonical, facts |
| `kb.pricing-quoting` | 02 | Pricing & Quoting 報價與費用 | Rates, quotes, how a session/course is priced, day-rates, per-hour, per-head | 費用, 報價, 價格, 收費, 鐘點, 一小時多少, quote, price, pricing, cost, rate, how much |
| `kb.course-content` | 03 | Course Content & Curriculum 課程內容與課綱 | What a course covers, syllabus, level, prerequisites, which course to pick, methodology frameworks | 課程內容, 課綱, 大綱, 程度, 適合誰, 先修, 哪一門課, GUIDE, IPO, curriculum, syllabus, topics, prerequisite |
| `kb.scheduling-logistics` | 04 | Scheduling & Logistics 時間與場地 | Dates, times, duration, headcount, location, online vs in-person, booking | 時間, 日期, 時數, 人數, 地點, 線上, 實體, 預約, 場次, schedule, time, duration, headcount, location, online, in-person, booking |
| `kb.team-training-enterprise` | 05 | Team Training & Enterprise 企業內訓 | Group/corporate training, in-house workshops, custom programs, B2B | 團隊訓練, 企業內訓, 包班, 客製, 公司, 內訓, team training, corporate, enterprise, in-house, custom |
| `kb.technical-howto` | 06 | Technical How-To 技術操作 | Product/tooling setup & usage: MCP, Claude Code, skills, accounts/tools | MCP, Claude Code, skills, subagent, 設定, 安裝, 怎麼用, 操作, setup, install, configure, how to, integration |
| `kb.access-account` | 07 | Access & Account 帳號與存取 | Login, access to materials/recordings, account issues, links not working | 帳號, 登入, 存取, 錄影, 回放, 教材連結, 拿不到, account, login, access, recording, materials, link |
| `kb.refund-policy` | 08 | Refunds & Policy 退費與政策 | Refunds, cancellations, rescheduling policy, terms, invoices/receipts | 退費, 退款, 取消, 改期, 轉讓, 政策, 發票, 收據, refund, cancel, reschedule, policy, invoice, receipt |
| `kb.other` | 09 | Other 其他 | Genuinely doesn't fit above **and** isn't worth a new section yet | — |
| `kb.instructor-profile` | 10 | Instructor Profile 講師介紹 | Instructor background, experience, bio (Dennis / Peter) | 講師, 老師, 背景, 經歷, Dennis, Peter, 介紹, instructor, teacher, bio, background |
| `kb.brand-product-vision` | 11 | Brand & Product Vision 品牌與願景 | Zynkr brand, vision, mission, product direction, "about us" | 品牌, 願景, 使命, 產品方向, 公司理念, Zynkr, brand, vision, mission, about |
| `kb.ai-workflow-architecture` | 12 | AI Workflow Architecture AI 工作流架構 | AI workflow / automation architecture, memory & KB design, RAG | 架構, 流程設計, pipeline, 自動化架構, 知識庫架構, RAG, workflow, architecture, automation, memory, retrieval |
| `kb.tone-style` | 13 | Tone of Voice & Style 語氣與風格 | ALWAYS-READ style rules as `fact` cards: `tone-voice-rules` + `term-mapping-table` (the anti-Chinglish 用語對照表). NOT a Q&A intent. | 語氣, 風格, 用語對照表, 晶晶體, tone, voice, style, wording, term mapping |
| `kb.gov-subsidy` | 14 | Government Subsidy 政府補助 | 企業申請政府補助（AI 導入/轉型）：核銷機制, 資格, 時程, 提案要點. Facts: `gov-subsidy-mechanics` / `-ai-programs` / `-proposal-elements` / `-timeline` (in `kb.core-facts`). The partner's revenue-share terms stay in Drive `[2.7] 政府補助 knowledge` — never in the 知識庫. | 補助, 補助案, 補助款, 政府計畫, 專案補助, 核銷, 數位發展部, subsidy, grant, government funding, moda |

> **Core Facts** (`fact` cards) are NOT a Q&A intent — canonical numbers live in `kb.core-facts`,
> and reference cards **cite** them (`cites: ["<key>"]`). A company fact (`company.…`) is never
> filed in a section: cards cite it by key.
> **Tone-style** likewise holds only the two style fact cards; a wording rule from Peter is a
> correction packet for `term-mapping-table`, not a new card.

## Classification notes
- Prefer the **most specific** fit. "How much for in-house team training?" is
  `kb.pricing-quoting` if the answer is the rate, or `kb.team-training-enterprise` if the answer
  is program scope — judge by *what Peter actually answered*, not what was asked.
- A single thread can yield **multiple cards** under different intents (e.g. a pricing answer
  + a scheduling answer). Split them — each gets its own `collection`.
- `kb.other` is a holding pen, not a destination. If two or more of its cards start looking
  alike, that's the signal to propose a new section → `new-section-playbook.md`.
- History: sections 10–12 grew in during the 2026-06-05 enrichment; section 13 (`tone-style`)
  was added at the 2026-07-15 platform cutover, carrying the old "13 Tone of Voice & Style"
  doc's content as fact cards. ATL-114 moved all 14 from the CRM into Atlas as collections
  `kb.<slug>` under the root collection `kb` (知識庫), keeping their slugs, their aliases (in
  each section's body) and their mirror numbers.
