---
name: synthetic-zh
originalName: 報價審核流程
type: workflow
description: "客戶提出需求，AI 草擬報價，超過十萬的報價由主管核准，其餘自動寄出，客戶收到報價。"
executed_by: external-user
steps:
  - "## 需求"
  - "start | start | 開始 · 客戶提出需求"
  - "ask | input | 1.1 填寫需求表單"
  - "draft | llm | 1.2 草擬報價"
  - "price | knowledge | [RAG] 價目表 v4"
  - "## 核准"
  - "big | gate | 2.1 金額超過十萬？"
  - "approve | hitl | 2.2 主管核准"
  - "auto | deterministic | 2.3 自動寄出"
  - "log | store | 報價紀錄 (Airtable)"
  - "send | output | 2.4 客戶收到報價"
  - "end | end | 結束 · 報價已寄出"
flow:
  - "start -> ask"
  - "ask -> draft"
  - "draft -> big"
  - "big -> approve | 是"
  - "big -> auto | 否"
  - "approve -> send"
  - "auto -> send"
  - "send -> end"
  - "price ~> draft | 參考價格"
  - "approve ~> log | 核准紀錄"
  - "auto ~> log"
  - "log ~> send"
---

一個合成的流程，給工具自我測試用：中文標題的換行、`--lang zh-TW` 的泳道標題，以及 lint 通過。
