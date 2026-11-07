# LOB ↔ Cloud Folder ↔ Local Path Map

Canonical mapping used by the `admin-governance` skill. Update this file when:
- A new department is added
- A cloud folder is renamed/moved (ID stays the same — should be rare)
- The local repo layout changes

Source of truth: established 2026-05-27 by the local↔cloud governance work (see Zynkr CLAUDE.md `Knowledge Governance` if present, otherwise the strategy v2 doc). **Re-mapped 2026-11-03 to the nine Taxonomy v3 departments (`SKB-101`)**, after the Drive restructure put every folder under one department folder `[0]`–`[8]`. Folder IDs did not change in that move; only names and parents did.

## Mapping

The Drive root now holds nine department folders and nothing else of the company's (number 9 is reserved and has no folder). The local folders keep their v2 names until the year-end renumber, so one local path can feed a v3 department with a different number — the table says which.

| Dept | Local path (under `~/Desktop/Claude/zynkr/`) | Department folder ID | Sub-folders to scan (name · ID) | Notes |
|---|---|---|---|---|
| 0 | `0 strategy-planning/` | `11LFipvdXLn-qgLSSVdtS8wqpYEfFFNBq` `[0] 策略與規劃 (Strategy & Planning)` | `2026 H2 planning` `1S-u9bM4IbTxhYBDIVGglq1g41Z7Qh46R` (holds the H2 Planning Main Tracker + the 7 function-plan shortcuts) · files at the first level. Skip `Old` `1fBMby6I132lcArPfc5Nwp3n6NskkoKdU` | Cloud canonical. The Org Taxonomy Docs and the org chart keep a `[7.1]` title prefix until v3 is final; they belong here, not in `[7]` |
| 1 | `1.0 brand-marketing/` | `1UhFqsFsgdoRSOSn2kNWujuYY1u8G6flH` `[1] 行銷部門 (Marketing)` | `[1.0] 品牌與行銷部門` `13Brg4QCuPlEdHh5mA7dvjxXlud4BvqFx` · `[1.1] 內容行銷` `1mWEWzaLlKx8-XlnYEmNY1oSRCsGWRtry` · `[1.2] 顧客經營 CRM` `1RNI-E0HOnSIlE99n4rm3E-k_yg--4Xzd` · `[1.3] 聯盟行銷與業配` `1WH_tWIMV2_klCoWvKr0_eWHEmlSvFpO9` | SPLIT — cloud for brand assets, local for pipelines. Skip `[1.9] 封存 (Archive)` `1vqdQ2EpjpbUk8lBSjts7EKYHcObTVoUN` |
| 2 | `2.0 sales-consultant-offering/` | `1r25tCK_tnw2p0WlRH8r-F5WQI0ku2iwo` `[2] 業務部門 (Sales)` | `[2.0] 業務部門：策略和定價` `1ZapREC_tFSsYSA7BY18GaGDvxb41rIgd` · `[2.1] 業務部門：方法論 (Methodology / SOP)` `1Br5uEZv2XTIClarkA9pdRsjLNhIVOdP6` · `[2.2] 業務部門：陌生開發 (Outbound call)` `1puwXQwPlVliYY-eWHBLsePELUgVU9YQK` · `[2.4] 客戶關係管理 (CRM)` `1-ba7_UF1CNVTPYpBL6H_LuUhq6lYVwD2` | Cloud canonical. Skip `[2.9] 封存 (Archive)` `1tpU6fxnsfHPB5cDFMy7zZIJzaWD0Psyp` |
| 3 | `2.0 sales-consultant-offering/` (shared with 2) | `1h2OMwspqWkmnm1fIZei-gZNswlkaxbS6` `[3] 顧問部門 (Consult)` | `[3.0] 顧問部門：策略與方法論 (Strategy & Methodology)` `1EvQT-1WUyFpXq6c8ZKSLNi7iPQP5RoN7` · `[3.1] 顧問部門：專案 (Project tracking)` `1hkXPX7OXPFOU0BcloPbJSFp8O0zArM8t` · `[3.2] 顧問部門：結案專案 (Closed projects)` `1OP38Kx8oBxHuZjXL-LEsQETsNj0SSA7u` | Cloud canonical. `[3.0]` holds the 企業 AI 診斷 line (`[3.0] Enterprise AI Enablement 企業 AI 診斷 — README` `1lzTfVYHB8zWBjVRLDsgP7o5mRxQMYU80nYUK0qFYc84`); there is no separate 企業 AI 診斷 folder. `[3.1]` holds one numbered `[N]` folder per client project — list it, do not recurse into every project. Skip `[3.9] 封存 (Archive)` `1ykUTtAHPmPNtujonCTJ0W6qXHCW6jwu4` |
| 4 | `4.0 training-design/` | `13wXLL2vA4aaTMo2uX_MyeaTrju3606oV` `[4] 培訓部門 (Training)` | `[4.0] 知識產品專案 (專案表格和 SOP)` `1WIu-FdKFs4EF6LLBlGCyaOnWucSCB9A1` · `[4.2] 知識產品：知識素材 (Artifact)` `15n_eZC6bmZOV1Vb29mNvMUvq8YaH_V-E` · `[4.3] 知識產品：知識產品，課程和講義` `1ZcRVwihcyvNRQQD1bI2RXun7e2812J3K` · `[4.4] 活動與陪跑 (Events & Cohorts)` `11QZXKwXsKZlNo42d0jfXaW1eiV5mHogD` · `[4.5] 知識內容素材（直播）` `1-aXLBpLizM0PyMbYu7TIb3xw50BrFL6a` | LOCAL canonical for course content. `[4.1] 知識產品：透過錄影萃取知識 (Recording)` is a shortcut (`1H0LEi8eNS00XrHWHSSZ3mllfY2_1Ay3X`) to folder `1FUuhBBP1t6rYFVStdIqxoYa1cp8Wvz8g` inside My Drive › Google Meet, outside the company folder — not scanned |
| 5 | `3.0 operation/` | `126aFnX2k6P5RS1fde9hHYqB2OOzxcFUr` `[5] 流程優化部門 (Transform)` | `[5.0] 流程與 SOP (Process & SOP)` `1Y2St1Zaj3j3VS_iiPU_-TcltgR8LuBde` · `[5.1] 客服與知識庫 (Support & KB)` `1LpymoVhy4YrxDBi81Sw6CRQQbZAiSLQ6` · `[5.2] 專案管理 PMO｜Playbook & Templates` `1nnoKI115tWCMPOXTuWCbCW445v3BJZy6` | Cloud canonical (most active). `[5.2]` is the PMO Playbook + template home the `project-*` skills copy from (`SKB-011`). `[5.1]` holds only the KMS building plan; the `zynkr-kms` mirror of the Atlas 知識庫 lives in a members-only folder outside the company folder and stays out of this map (a machine-written backup, rewritten every run). Skip `[5.9] 封存 (Archive)` `1LCZW4V25z80KWfuV9A8Ea62YbWA5ltUH` |
| 6 | `5.0 product/` | `1ZL5X_G-uk8ka9Xjok3-GBw3TZp-SlG-o` `[6] 產品部門 (Product)` | `[6.0] 產品管理 (PM)` `1UNKjQdy3wACcRP7pbd-zwU7hK6Exh7D5` · `[6.1] 工程 (Eng)` `1lJZxEnL97nWKpL4mxRZ00nSyIaWimCzx` · `[6.2] Skills & Knowledge Library` `1Q0XwdR574cNUVlT7lYVbpzNbVsup2KAu` | Cloud canonical. **Scan `[6.0]` recursively**: its sub-folder `1R4DfLi07Z5SaYBB4Q8-8QuKMjh7o0JYm` (Lucid Workflow Engineering conventions) holds the engineering convention docs (**.md files by design** — agent-readable/writable; don't propose Docs conversion). Their read-only local mirror is `6.0 tech/engineering-conventions/` — flag mirror drift when the cloud copies change. Skip `[6.9] 封存 (Archive)` `16Na6nsBY8TfFoOngPd8RyLPHyRhBcXmv` (the 2025 助理開發 pipeline). The first level also holds an unnumbered partner-listing folder `1ue8q_X9QkR-yyHAE9res1VXj5aAr_j8a`: report it as NEW until it is filed (under `[6.0]`, or `[0]` for partnerships) |
| 7 | `7.0 people/` | `1WzvfHVjxjFMG2CDHHVxHHKKWDkIKRncZ` `[7] 人資部門 (HR)` | `[7.1] 人資，人力管理 🔒` `1t8HgbGePw7Dt9KuqBDEKXzGBEkqUkGr2` · `[7.2] 人資，合作夥伴管理 🔒` `1P71EGNNWDDTQ8gI0II5NfrYHjjojsp8A` · `[7.3] Onboarding` `1VHgwkW_HZPuKnyqLuqiX685SuDx36R4I` | Cloud canonical. Also list the first level of `[7]` (the 1-on-1 template sits there). `[7.4] 1^1 🔒` `1pPxFUyQ3Pol5qopxMAmz9ZVXS2kZ_uBa` (1-on-1 records) and `[7.5] 離職交接 Offboarding 🔒` `1RbpzxWI-IKksAT6WIOfpe9B86xc30ztA` (offboarding records) are personal records — never indexed. Skip `[7.9] 封存 (Archive)` `1AwZuQvgAgj5YwkA-f9fMoHQi2f6KbRXQ` |
| 8 | `8.0 finance-analytics/` | `1JXKcigFTC3q_hF4OTaRh3FEiFBAtOjG7` `[8] 財務部門 (Finance · 法務)` | `[8.0] 財務 💰` `16Uf0JN5SoS5v7_BUuW7Js5UeH0795Uf6` · `[8.1] Pitch 準備` `1GVzgNIkkYKF0P96DoMCxufJvRajLutWs` · `[8.2] 法務與合約 (Legal)` `10dlHVYThUSQXQlhjDAT__w06QmFqlIFK` | SPLIT — cloud for data, local for automation code. Also list the first level of `[8]` (one loose Doc sits there today). Legal joined Finance in v3; the local `9.0 legal/` folder is still out of scope |

## Special: the Drive root

Drive root folder ID: `1rqkpNt1NFmRXhXnVAXL_eoXVfON4qD32` (`[@] Zynkr 最懂你的 AI 顧問`, the company folder inside My Drive; not My Drive itself).

Since 2026-11-03 the root holds only the nine department folders. An item found directly at the root is misfiled: report it as **NEW (misfiled at root)** with the department it belongs in, rather than indexing it. The legacy `[5.1]–[5.6] 助理開發` series that used to sit at the root is now inside `[6.9] 封存` and is not scanned.

## Out of scope for admin-governance

- `6.0 tech/` — code, governed by git, not by `_INDEX.md`.
- `9.0 legal/` (local) — not part of the scan (separate governance); its cloud folder is `[8.2]`.
- `tools/`, `about-me/`, `0 about-me/` — utility folders, no cloud counterpart.
- Every `[N.9] 封存 (Archive)` folder.

## Index file paths

Each department's index is at `<local_path>/_INDEX.md`, so departments 2 and 3 share `~/Desktop/Claude/zynkr/2.0 sales-consultant-offering/_INDEX.md`, and department 5 reads `~/Desktop/Claude/zynkr/3.0 operation/_INDEX.md`.
