# Mode C · 公司窗口一封開發信

> `sales-outbound` 的 Mode C 完整做法。Mode A、Mode B 不受影響。
>
> `SKB-119` 把 `SKB-106` 的五封序列改成**一封開發信；寄出時 CRM 只建公司（加研究卡 note 與未回提醒任務），
> 不建聯絡人、交易，對方回覆後才建**。專案資料夾一律等交易到 `qualified` 由 `/project-init` 開（owner，2026-11-09）。
>
> **認領是名單那一列，不是 deal**（owner，2026-11-09，`sales.crm-data-standards` §5 的 Mode C 段）：冷開發的公司
> 還沒回話，不佔 `max-open-deals`。
>
> 這份文件裡的 `<your-…>` 是佔位符，執行時替換成真實值，真實值不寫進這個公開 repo。
> 公司事實從 Atlas 讀，key 與讀法在 SKILL.md 的 Mode C 段；`<your-sales-account>` 是執行者自己的帳號。
>
> 信的長相沿用 Mode B 的規矩：`sequence-5touch.md` 步驟 3.5 去 AI 感六條、步驟 4 外洩防線、
> 步驟 5 建草稿的地雷；頁尾照 `email-format.md`。**這份只寫跟 Mode B 不一樣的地方**。
>
> **政策的三個數字不寫在這裡。** 一批幾家（`outbound-batch-max`）、每週時段下限（`outbound-min-slots-per-week`）、
> 等回信幾天（`mode-c-reply-days`，下面寫成 `<n>`）都是 Atlas `company.sales-pipeline-rules` 開頭的行，
> 讀法見 SKILL.md 的 Inference defaults 最後那一行；讀不到或少了那一行，就停下來問。只寄一封、一天一批
> 是 Mode C 本身的形狀，寫在這裡。

## 何時用 Mode C

使用者說「Mode C」「公司名單」「工商名錄」「對公司窗口開發」，或指著公司名單要做開發。
對方回信後，使用者說「{公司} 回信了」「Mode C 有回覆」時，跳到**步驟 6（有回覆才做）**。

| | Mode B | Mode C |
|---|---|---|
| 對象 | 上過課的學員（個人） | 公司名單上的**公司**，收件人是公司窗口信箱（service@、info@、業務窗口） |
| 名單 | `Outbound touches` 的 `AI名單` 分頁 | 公司名單 `<your-company-directory-sheet-id>` 的 `總表` 分頁 |
| 客製依據 | 職業、AI 類型、參與場次 | **company research**（官網、產品、產業） |
| 封數 | 五封 | **一封** |
| ask | 一對一諮詢（這次免費） | **30 分鐘 discovery call** 一起發想 AI 應用痛點 |
| 稱呼 | 「Hi {名}」「你」 | 不知道收信人是誰：「您好，」「您」「貴公司」 |
| 認領紀錄 | `認領人` 欄寫帳號 | A 欄寫**認領人名字**、B 欄寫 `已認領` |
| CRM（寄出時） | 寫信前先認領：聯絡人＋認領人的 deal＋「五封未回」任務（`SKB-105`） | **只建公司**＋研究卡 note＋掛在公司的未回提醒任務；不建聯絡人、不建交易 |
| 有回覆後 | 照 Mode A 跟進 | 建聯絡人（回信的人）＋交易（或把回信人掛到既有交易）；專案資料夾等 `qualified` |

## 名單

- 公司名單 `<your-company-directory-sheet-id>`，分頁 `總表`。可能是上傳的 .xlsx 而不是原生 Google 試算表；
  兩種都沒有寫格子的 API，認領一律從瀏覽器的 Sheets 介面寫（步驟 1）。
- 欄位：`A 認領人 · B 狀態 · C 規模 · D 資本額(萬元) · E 行業 · F 子分類 · G 公司 · H email · I 電話 · J 縣市 · K 地址 · L 網址 · M 統編 · N 登記名稱 · O 登記狀態 · P 設立日 · Q 查詢 · R 來源 · S 頁面`
- `規模` 有：大型公司、中型公司、中小型公司、小公司、規模未查到。筆數會變，開跑當場重讀，不要引用快照。

### 選公司

1. 下載一份讀：`mcp__google-workspace__get_drive_file_download_url(file_id=<your-company-directory-sheet-id>)`，用 openpyxl 讀 `總表`。
2. 跳過：A 欄已有人、`登記狀態` 不是「核准設立」、`email` 空白或明顯不是信箱（例如 `www.` 開頭）。
3. **同一個統編或同一個網域只做一家**（名單裡有分公司、分店重複），挑總公司或資本額大的那筆。
4. **先查 CRM**：`mcp__zynkr__list_companies` 用公司名與網域各查一次、`list_contacts(search=<email 網域>)`、`list_deals(search=<公司簡稱>)`。CRM 已經有這家公司、這個網域的聯絡人或未結案交易，就跳過換下一家。
5. 排序沒有硬規定時，先挑 `中小型公司` 以上（名單的 `規模` 依資本額分，只拿來排順序）、`網址` 有值的（research 才有東西可看）。挑完把清單給使用者點頭再認領。

## 步驟 1 · 認領

在名單該列：**A 欄填認領人名字**、**B 欄填 `已認領`**。認領人是執行者本人時，CRM 的負責人用 `mcp__zynkr__whoami` 的 `email` 對 `list_workspace_members`；替別人認領時問他的公司信箱，不要從名字猜。同時**問認領人「這家主要要賣什麼」**（例：部門工作坊），答案寫進公司 description，步驟 6 建交易時沿用，不要自己從研究卡推。

- 走瀏覽器，網址加 `?authuser=<your-sales-account>` 確保是公司帳號。用名稱方塊（左上角）輸入 `A{列號}` 跳格；寫前先看該列 A 欄是空的、G 欄公司名對得上。
- 中文格一律「名稱方塊跳格 → 點公式列 → 輸入 → Enter」，一格一格做（見步驟 5 的地雷）。
- 寫完重新下載讀回，A、B 兩格是寫進去的值才算認領完成。.xlsx 在 Office 編輯模式下，Drive 下載到的版本會比畫面慢幾十秒到十分鐘；讀回沒看到就等一下再下載，不要重寫。
- 一批最多 `outbound-batch-max` 家，一天一批（同 Mode B）。

## 步驟 2 · Company research

每家公司產出一張研究卡（不進信，寫進 CRM 公司的 description 與一筆公司 note，見步驟 4），只寫查得到的東西，查不到寫「查不到」：

| 項目 | 來源 |
|---|---|
| 主要產品／服務、客戶是 B2B 還是 B2C | 名單 `網址` 的官網：首頁＋產品頁＋關於我們 |
| 產業、子分類、資本額、設立年 | 名單欄位 |
| 規模（員工數） | 只看員工數證據：官網、徵才頁、人力銀行；查不到寫「員工數查不到」。名單的 `規模` 欄依資本額分，**不寫進研究卡**（`company.company-directory-sheet`） |
| 營運特徵：外銷、多據點、電商、工廠、門市、代理品牌 | 官網、網路搜尋公司名 |
| 近期動態（徵才、新廠、新產品、展覽） | 網路搜尋，標日期與出處 |
| 推測最可能卡人工的兩到三個環節 | 由上面推，**標明是推論** |
| 信裡要提哪條工作流 | 步驟 3 的對照表 |

- 官網打不開或只有一頁，就照名單的 `行業／子分類` 寫，信裡講到產業層級為止，不要假裝看過他們的內部流程。
- **不要編**：沒查到的數字、客戶名、員工數不寫進信。
- 每個事實留出處網址，寫進公司 note。

## 步驟 3 · 那一封信

原本五封的重點濃縮成一封：**research 開場 → 具體痛點畫面 → 一條我們建好的工作流（短）→ 補助一句 → 30 分鐘邀約＋時段**。
寄出日由認領人定（建議平日上午）；時段一律取自 `<your-company-contact-email>` 日曆的 `Available` 事件扣掉既有會議，
三格落在寄出日 +2 到 +8 天，取法照 `sequence-5touch.md` 步驟 1。讀不到就停下來問，不要編時段。

主旨（建議）：`想邀請 {公司簡稱} 一起發想 AI 應用的痛點`

```
您好，

我是 Zynkr 的 {寄件人}。

{research 開場：一兩句講我們看到的、跟他們實際業務有關的事，例如產品線、產線、認證、客群}

像貴公司這樣的{產業／營運型態}，我們常聽到最花人力的是三件事：{具體畫面 1}；{具體畫面 2}；{具體畫面 3}。

{工作流兩三句：我們建好的哪條流程對應上面哪個畫面；什麼時候啟動、AI 做什麼、人在哪一步把關}

{補助一句，取自 Atlas 卡片 gov-subsidy-mechanics；卡片讀不到或字數超過就整句省略}

這些是同業常見的情況，不一定都對得上貴公司。想邀請貴公司花約 30 分鐘線上聊聊，聊清楚三件事：
1. 上面哪一件在貴公司最花人力
2. 哪一段最適合先交給 AI
3. 第一步可以怎麼開始

聊完我們會把聊到的痛點整理成一頁回給您，不用急著決定要不要做。

不曉得以下有沒有方便的時間（台北時間）？
1. {時段一}
2. {時段二}
3. {時段三}
4. 或其他方便的時間

確認後我會寄出會議邀請，{日曆擁有者的稱呼} 也會一起參加。如果這封信沒有寄到負責的同仁，也麻煩幫忙轉給適合的人，謝謝。

--

關於 Zynkr
（照 email-format.md 資訊區塊）

Best regards,
{寄件人}
```

寫法：
- **正文只准兩處列點**：要聊的三件事、時段（《[2.2]》§八）。痛點畫面寫成一段、用「；」分隔，不列點。頁尾「關於 Zynkr」資訊區塊不算。
- 痛點畫面要跟研究卡的「推測最可能卡人工的環節」對得上，是這家公司**這禮拜真的會遇到**的事
  （例：工廠＝客戶來信問交期要翻 ERP 回覆；外銷＝報價單與出貨文件重打；門市／電商＝訂單、庫存、物流狀態在三個系統各一份；醫材或食品代工＝確效與稽核文件重新彙整）。
  推論用「常聽到」「通常」表述，不要寫成「貴公司一定有」。
- 工作流段落**最多三句**，步驟取自內部 Drive `<your-workflow-library-folder-id>` 的工作流實際案例總表，不要自己編。先用研究卡挑，挑不出來用下表：

  | 名單 `行業` | 優先用哪條（總表裡的名稱） |
  |---|---|
  | 工業製造 | 訂單成立轉出貨 · 安全水位補貨建議 · 採購核准轉應付 |
  | 商業服務、休閒娛樂、教育學術、委託仲介 | 名單解析與分級 · 成交交接與服務開通 |
  | 日常用品、美食餐飲、衣服飾品、美容時尚（有電商或門市） | 訂單成立轉出貨 · 物流狀態通知 |
  | 交通運輸 | 物流狀態通知 |
  | 資訊電腦 | 客訴轉 issue · 修復上線主動回覆 |
  | 醫療保健、建築裝潢 | 合約簽署後歸檔 · 成交轉開票資料 |
  | 其他、研究卡看不出來 | 重要事件即時通知（零風險、唯讀，最適合當第一個案子） |

- 補助那句只用 `gov-subsidy-mechanics` 卡片 `---` 以上寫得到的內容，卡片沒寫的不寫；政府補助內部文件絕對不可外發（SKILL.md Mode B 第 3 條）。
- **寫 30 分鐘、不寫價格。** 這是對 `sequence-5touch.md` 步驟 3.5「時數一律不進客戶看得到的東西」的例外，理由是《[3.2] 禁用詞清單》類別 X 要求邀約寫出時長；不提價格就算不出時薪。不要加任何金額。（owner 2026-11-09 核准，只限 Mode C；Mode B 照舊不寫時數，因為它的第一封寫金額。）
- `{日曆擁有者的稱呼}` 是提供時段的那位，寫名字就好，職稱沒查證不寫。
- 第一句要講對方做過的具體事（產線、認證、產品），不要空寒暄。破折號用半形 — ，不用「——」；不用「貴司」「一站式」。
- 全封用「您」「貴公司」，不要中途改回「你／你們」。
- **長度**：正文（不含頁尾）照《[2.2]》§八 280–400 字。信是五封濃縮來的，容易超過；先砍補助那句，再壓工作流，痛點和邀約不砍。

**外洩防線（同 Mode B 步驟 4）**：
- **不附檔、不貼資料夾或簡報連結。** 工作流資料是網域限定，外部點開是 403；卡片上的難度分級、階段編號、工作流編號也都不進信。
- 串接鏈上的軟體名可以提，但只當例子，不要寫成「我們跟 X 有串好」。
- 卡片底下的「資料來源」那行不進信。

### 建 Gmail 草稿

照 `sequence-5touch.md` 步驟 5：`mcp__google-workspace__draft_gmail_message`，`body_format="html"`、`include_signature=true`。
只有一封，主旨**不加** `【M/D 寄】`。建完 `search_gmail_messages(query="in:drafts to:<email>")` 確認剛好 1 封，
再 `get_gmail_message_content` 看結尾有簽名卡，才算建好。寄出由認領人自己按。

## 步驟 4 · CRM：只建公司＋貼標籤

**只建公司，不建聯絡人、不建交易**（收件人是公司窗口；還沒回話就不佔 `max-open-deals`、不算 cooking）。

1. 建之前**再查一次重**：`list_companies` 用公司名與網域各查一次；有就不建，改用既有那筆的 `id`，並回報。
2. `mcp__zynkr__create_company` 先預覽再 `confirm:true`：`name`（名單 `公司`）、`domain`（email 網域；個人信箱網域如 gmail 就改用官網網域，都沒有就不帶）、`tax_id`（統編）、`industry`（依研究卡寫實際產業）、`phone`、`address`、`city`、`country`、`owner_id`＝認領人（`list_workspace_members` 對 email，對不到就停下來問）、`description`（研究卡摘要＋獨立一行 `公司名單冷開發（Mode C，YYYY-MM-DD，認領人 <名字>）`（日期＝寄出日；別的業務技能建 lead 前查公司時讀這一行，格式照抄）＋主推項目＋窗口信箱＋資本額＋名單列號；員工數查不到要寫查不到）。
3. **`create_company` 沒有 `lifecycle_stage` 參數，建出來預設是 `opportunity`**：建完立刻 `update_company(id, lifecycle_stage="lead")` 預覽，再加 `confirm:true` 寫入，`list_companies` 讀回確認。
4. `create_note(company_id=…)` 先預覽再 `confirm:true`，subject `[Mode C] 研究卡＋開發信`，body 放：完整研究卡（附出處網址）、信裡用的工作流名稱、三個時段、信的全文（或主旨＋摘要）、「草稿已建，尚未寄出（YYYY-MM-DD）」。原本放在交付文件的東西都在這筆 note，**不再另做 Google 文件**。
5. 標籤依 `company.crm-tag-rules`。公司能貼的組只有 關係／產品／規模／待確認；`來源` 只能貼聯絡人，這一步不建聯絡人所以不貼，冷開發這件事寫進 description。
   - 規模：只看員工數證據（官網、徵才頁）。查到就貼對應 `size` 值；**查不到就貼待確認 `規模不明`**。資本額不能換算成人數。
   - 待確認：名單 `電話` 空白 → `電話缺漏`。
   - 關係、產品不貼（對方還沒回話，沒有證據）。
   - 全部 `source:"rule"`，`apply_tag` 先預覽再 `confirm:true`，寫完 `list_tags(entity_type="company", entity_id)` 讀回。貼不上照 Mode B 7.4 的降級規則記 `標籤建議` note。
6. **未回提醒任務**：`mcp__zynkr__create_task(company_id=…)` 先預覽再 `confirm:true`：
   - `subject`：`Mode C <n> 天未回 → 接觸紀錄改暫時沒需求`，`<n>` 換成 `mode-c-reply-days` 的值，其餘**照抄**（`/sales-manager` REVIEW 靠這個標題找 Mode C 公司，並從標題讀回 `<n>` 算寄出日；`company.sales-pipeline-rules` 也用它數 Mode C 寄出量）
   - `due_at`：寄出日＋`<n>` 天，台北 09:00（`T01:00:00Z`）；`assignee_id`：認領人
   - `body`：寄出日、窗口信箱、名單列號、接觸紀錄列號
   - 寄出日改了就把舊任務 `set_task_status` 關掉、照新日期重建（同 Mode B 0.3）。

## 步驟 5 · 寫接觸紀錄

寫進 `Outbound touches`（`<your-outbound-touches-sheet-id>`）的 `接觸紀錄` 分頁，附加一列，格式照 `sequence-5touch.md` 步驟 6：
`時間戳 | Email＝公司窗口信箱 | 姓名＝{公司名}（公司窗口） | 接觸人員＝帳號前綴 | Email | 接觸日期 | 已聯絡，待回覆 | Remark`。
Remark 開頭寫「陌開一封信（Mode C，公司窗口）」，接名單列號、CRM 公司、信的摘要，結尾「※ YYYY-MM-DD 由 {認領人} 建立 Gmail 草稿 1 封，尚未寄出。」

**瀏覽器輸入的實測地雷（2026-11-04）**：
- 中文格要「名稱方塊跳格 → 點公式列 → 輸入 → Enter」**一格一格做**。從前一格按 Tab 跳過來再點公式列，中文會整格變空（規律不明，所以一律走名稱方塊）。ASCII 開頭的格可以直接打字＋Tab。
- 寫完一定重新下載讀回（原生試算表用 `get_drive_file_download_url(export_format="xlsx")` ＋ openpyxl 讀 `接觸紀錄` 分頁），逐格核對，不要只看畫面。

**寄出時到這裡就結束**：回報公司 URL、草稿主旨、時段、接觸紀錄列號、提醒任務到期日。沒有交易、沒有專案資料夾。

## 步驟 6 · 有回覆才做：建聯絡人＋交易

觸發：Gmail 收到這家公司（窗口信箱或同網域）的回信，或使用者說「{公司} 回信了」。
先 `search_gmail_messages(query="from:<窗口信箱> OR from:@<網域>")` 讀回信內容；**退信、自動回覆不算回覆**。
「不需要」：接觸紀錄改 `暫時沒需求`，把步驟 4 的未回提醒任務關掉（第 5 點的找法），結束，不建交易。

1. **認領關卡，用回信人的 email**（`sales.crm-data-standards` §5 的六步，加上公司）：
   - email 去空白、轉小寫；`list_contacts(search=<email>, limit=100)`，只留 `email` 或 `secondary_email` 完全相等的。
   - `list_deals(stage=…, limit=100)` 對 `new`、`contacted`、`qualified`、`proposal` 各叫一次，留下 `contact_id` 是上面找到的聯絡人、**或** `company_id` 是步驟 4 這家公司的。不要用 `list_deals(search=)` 查：它只比對交易名稱與編號，名稱不是公司名的交易會漏掉。
   - **任何一次剛好回 100 筆，這個查法就不可靠：停下來說明**，不要建。
2. **建聯絡人（回信的人）**：照 Mode A 的 find-or-create（第 1 點已找到就沿用），`company_id` 掛步驟 4 的公司、`owner_id`＝認領人。
   `first_name` 照回信署名寫；署名只有部門、沒有人名，就問認領人，不要從信箱或部門猜。
   來源標籤取 `company.crm-tag-rules` 的 `outbound-mode-a-source` 那一行的值（我們先寫、對方原本不認識我們；2026-11-03 版是 冷開發），`source:"rule"`；讀不到那一行就不貼，照 Mode B 7.4 的降級規則記 `標籤建議` note。缺職稱、電話照同一份政策貼待確認。
   聯絡人 `lifecycle_stage` 照 Mode A 對有回應的人的設法；公司的 `lifecycle_stage` 維持步驟 4 設的 `lead`，不在這裡改。
3. **已有未結案交易（第 1 點找到）就不新建交易**：
   - 那筆交易沒有聯絡人 → `update_deal(id, contact_id=<回信人>)` 先預覽再 `confirm:true`，`get_deal` 讀回。這樣別的業務技能用 email 查得到它。
   - 那筆交易已經有別的聯絡人 → 不動它，回報「<交易編號> 已掛 <聯絡人>，回信人另建為同公司聯絡人」。
   - 負責人不是認領人 → 不搶，回報「<交易編號> · <stage> · 負責人 <名字>」，交給負責人跟進。
   - 然後跳到第 5 點（任務掛在那筆交易上）。
4. **沒有未結案交易 → 建交易**：先數認領人名下未結案交易，跟 `company.sales-pipeline-rules` 的 `max-open-deals` 比；到達或超過照樣建（規則 1：lead 不丟），回報寫「已到上限」。
   `mcp__zynkr__create_deal` 先預覽再 `confirm:true`：
   - `name`：照 `sales.crm-data-standards` §1，人在前、公司、再來是要的東西：`{回信人名字}（{公司簡稱}）{主推項目}`
   - `company_id`：步驟 4 的公司；`contact_id`：第 2 點的聯絡人
   - `owner_id`：認領人；`lead_source="outbound"`（規則 9，不得空白）；`deal_type="new_business"`
   - `stage="contacted"`：我們寄過信、對方回了
   - `service_tier`：把主推項目對到 `company.crm-tag-rules` 的 `product-values`，再查 `product-to-service-tier`；對不上就問認領人
   - `value`：沒有報價就不帶，不要估
   - `notes`：**第一行以 `Mode C` 開頭**（`company.sales-pipeline-rules` 靠這個把交易歸到 Mode C 那一組），寫名單列號、主推項目、開發信寄出日、回信日與回信重點（對方原話一兩句）。**不寫 `專案資料夾：`**——那一行只由 `/project-init` 在 `qualified` 時寫。
   - `get_deal(id)` 讀回核對 name、stage、lead_source、company_id、contact_id、owner_id、notes 第一行。
5. **任務**：
   - 關掉未回提醒：`list_tasks(filter="open", limit=200)`，找 `parent_kind="company"`、`parent_id`＝這家公司、`subject` 以 `Mode C <數字> 天未回` 開頭的（不論數字多少：政策改過天數，舊任務還是建的那天的數字），`set_task_status` 設為完成。找不到就回報，不要重建。
   - 追蹤任務：`create_task(deal_id=…)`，下一步照回信內容（約時段、回答問題）；到期日依 `company.sales-pipeline-rules` 規則 4（新回覆、沒有歷史 → `followup-fast-days`）。
6. 接觸紀錄那一列的狀態改成表示「對方已回覆」的值：先讀該欄現有的值（已知有「已聯絡，待回覆」「暫時沒需求」），沒有對應的值就問認領人，不要自己發明；Remark 補回信日與交易編號。
7. 之後的跟進交給 `/sales-follow-up`（會議後）或 `/sales-discovery-prep`（約到 discovery call）；交易到 `qualified` 時 `/project-init` 開專案資料夾。

## 停止條件

- 一封就停，**不補寄第二封**。**寄出後 `<n>` 天內沒有回覆就算不成立**：接觸紀錄狀態改 `暫時沒需求`，關掉未回提醒任務。`mode-c-reply-days` 是 Mode C 自己的回覆期限，跟同一份政策的 `stale-days` 是兩回事，不要混用（owner 2026-11-09 定的，`SKB-126` 把它跟序列數字一起搬進政策）；CRM 沒有交易所以不用結案，公司留著（之後查重會擋掉重複開發）。
- 管線指標：寄出時不建交易，所以不佔 `max-open-deals`、不算 cooking；有回覆建了交易之後才算進去。
- 一天一批、一批不超過 `outbound-batch-max` 家。
- 公司聯絡人日曆該週 `Available` 少於 `outbound-min-slots-per-week` 格，就不開新批次（同 Mode B）。
- `/sales-manager` REVIEW 讀步驟 4 的未回提醒任務：沒交易的 Mode C 公司靠它出現在每週盤點，過期就提請「接觸紀錄改暫時沒需求＋關任務」。回覆有沒有來，仍以步驟 6 的 Gmail 查詢為準。
