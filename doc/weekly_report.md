# 週報表 — API 規格書

> 給長者看的「上週回顧」：活動天數、六大能力本週 vs 上週、聲影日記、下週小目標，以及一句 AI 鼓勵的話。
>
> 用語原則：本 App 定位為「輔助維持認知活躍度」，週報只跟**自己**比、不跟同齡比，不出現專有名詞（z 分數、標準差、百分位、認知彈性）與負面字眼，不作任何診斷用途。

---

## 一、功能總覽

- **看哪一週**：上一個完整的週（週一～週日），比較對象是再前一週
  - 例：今天 10/20（二）→ 報告週 10/12（一）～10/18（日），比較週 10/5～10/11
- **不設解鎖門檻**：沒玩也有內容（數字是 0、句子仍然正向）
- **只讀資料**：不寫入任何資料表，每次請求當下計算
- **時區**：日期一律依台灣時間（`settings.TIME_ZONE = "Asia/Taipei"`）切分，晚上 11 點玩的算當天

---

## 二、六大能力與資料來源

| 順序 | 維度 `dimension` | 顯示名稱 | 資料來源 `source` | 每場／每篇的 z 從哪來 |
|---|---|---|---|---|
| 1 | `attention` | 注意力 | 菜市場找路 `market_route` | 結算時存入 `GameSession.result.z_score` |
| 2 | `working_memory` | 工作記憶 | 煮菜過程 `memory_recall` | 同上（前測不計分，為 `null`） |
| 3 | `executive_function` | 執行功能 | 整理菜籃 `market_sort` | 同上 |
| 4 | `visual_spatial` | 視覺空間 | 冰箱檢查 `fridge_check` | 同上 |
| 5 | `math` | 數學 | 市場買菜 `market_shopping` | 同上 |
| 6 | `language` | 語言 | 聲影日記 `diary` | 從 `DiaryAnalysis` 的 5 個小分數現算（跟更早的有效日記比），只算有效日記 |

- 陣列順序同儀表板雷達圖（`dashboard/services.py` 的 `DIMENSIONS`）
- 每款遊戲 z 的算法見 [`game_scoring_algorithms.md`](game_scoring_algorithms.md) 第 3～7 節，聲影日記見第 11-4 節
- 所有 z 都是**跟自己的歷史比**：自己不滿 3 場（篇）先借全體使用者的歷史，全體也不夠就算不出來；不使用寫死的常模
- 所有 z 都已限制在 **−2 ～ +2**；算不出來的場次（前測、歷史不足、無效日記）不算

---

## 三、計算規則

### 1. 活動

| 欄位 | 算法 |
|---|---|
| `daily_activity` | 週一到週日固定 7 筆；那天有**開始玩遊戲**（建立 `GameSession`，沒玩完也算）或**寫日記**（建立 `Diary`）就算 `is_active: true` |
| `highlights.active_day_count` | 報告週 `is_active` 的天數 |
| `highlights.session_count` | 報告週**已結束**的遊戲場次數（依結束時間，不含日記） |
| `highlights.streak_days` | 報告週內**最長連續**有活動的天數（例：一、三、五、六 → 2） |

> 專案沒有登入紀錄表，token 一次可用多天，所以用「有活動的日子」代替登入天數；只打開 App 沒玩也沒寫日記不算。

### 2. 能力分數（本週 vs 上週）

```
週分數 = round(50 + 25 × 那週的 z 平均)，限制在 1～100
```

| z 平均 | −2 | −1 | 0 | +1 | +2 |
|---|---|---|---|---|---|
| 週分數 | 1 | 25 | 50 | 75 | 100 |

- **哪一週**：遊戲依結束時間 `finished_at`、日記依建立時間 `created_at`
- **個人最佳 `best`**：從第一次有分數到報告週為止，每週分數的最高值（報告週之後的不算）
- **趨勢 `trend`**：

  | 本週 − 上週 | `trend` | 前端顯示 |
  |---|---|---|
  | ≥ +3 | `up` | 進步 |
  | −3 ～ +3 之間 | `steady` | 持平 |
  | ≤ −3 | `practice` | 多練習（不用「退步」） |
  | 任一週沒分數 | `null` | 不顯示標籤 |

- **整體表現 `overall`**：那週有分數的能力（含語言）取平均；`best` 是每週整體分數的最高值
- **`played`**：報告週有沒有碰過這個能力（遊戲有開始玩、或有寫日記）；有玩但沒有分數時（例：只寫了無效日記），`played: true`、分數為 `null`

### 3. 遊玩時間 `play_time`

- 每場 = 結算結果的 `play_seconds`，沒有的話用「結束時間 − 開始時間」；沒玩完的場次不算
- 整理菜籃玩完才一次送出、建立 session，所以改存 28 題反應時間加總（`play_seconds`），不含看題、轉場時間
- 單位是**秒**；介面圖沒有這一區，前端可自行決定要不要顯示

### 4. 聲影日記 `diary`

- `entries`：報告週 `status = "done"` 的日記，欄位沿用日記月曆 API（`diary_id`、`date`、`title`、`photo_url`、`post_text`）
- `talk_seconds`：每篇「最後一則回答時間 − 日記建立時間」加總（沒有存錄音長度，為近似值）；沒有回答的日記算 0

### 5. 下週小目標 `next_week_goal`

- 照雷達圖順序，挑第一個報告週**沒碰過**的能力 →「這週還沒玩{顯示名稱}，下週試試看」
- 語言是寫日記練的，不是遊戲，所以改說 →「這週還沒寫日記，下週寫一篇看看」
- 六個都碰過 →「每一項都玩過了，下週繼續保持！」
- 函式 `suggest_untried_source` 寫成共用，之後首頁「每日建議」也可以用

### 6. 一句話總結 `summary`（AI 產生）

1. 後端先整理**正向事實**（`ai_service/weekly_summary.py` 的 `build_positive_facts`）：
   - 報告週活動天數
   - 比上週多幾天（比上週少就不放）
   - 進步最多的能力：`trend == "up"` 中分數增加最多的那一個（沒有進步就不放）
2. 交給 OpenAI 寫一句話（設定 `OPENAI_API_KEY`、`OPENAI_MODEL`），限制：繁體中文、30 字內、語氣正向、不用專有名詞、不提醫療或失智
3. 以下情況改用**固定句型**，例如「這週你玩了 4 天，比上週多 1 天！進步最多的是工作記憶」：
   - 報告週 0 天（不呼叫 AI，回「好久不見，下週一起來動動腦吧！」）
   - AI 呼叫失敗（沒網路、沒額度）
   - AI 回的句子超過 40 字，或出現禁用詞（失智、診斷、治療、疾病、退步、變差、分數、z、標準差、百分位、認知彈性）

---

## 四、API 規格

### GET `/api/dashboard/weekly-report/`

**Request**

- Header：`Authorization: Bearer <access_token>`
- 沒有 query string、沒有 body

**Response Body（成功）**

```json
{
  "success": true,
  "data": {
    "week_start": "2026-10-12",
    "week_end": "2026-10-18",
    "summary": "這週你玩了 3 天，比上週多 2 天！進步最多的是執行功能",
    "highlights": { "active_day_count": 3, "session_count": 10, "streak_days": 2 },
    "daily_activity": [
      { "date": "2026-10-12", "weekday": "一", "is_active": false },
      { "date": "2026-10-13", "weekday": "二", "is_active": true },
      { "date": "2026-10-14", "weekday": "三", "is_active": true },
      { "date": "2026-10-15", "weekday": "四", "is_active": false },
      { "date": "2026-10-16", "weekday": "五", "is_active": true },
      { "date": "2026-10-17", "weekday": "六", "is_active": false },
      { "date": "2026-10-18", "weekday": "日", "is_active": false }
    ],
    "abilities": {
      "overall": { "this_week": 60, "last_week": 55, "best": 63, "trend": "up" },
      "dimensions": [
        { "dimension": "attention",          "label": "注意力",   "played": true, "this_week": 65, "last_week": 50, "best": 65, "trend": "up" },
        { "dimension": "working_memory",     "label": "工作記憶", "played": true, "this_week": 66, "last_week": 65, "best": 80, "trend": "steady" },
        { "dimension": "executive_function", "label": "執行功能", "played": true, "this_week": 58, "last_week": 40, "best": 58, "trend": "up" },
        { "dimension": "visual_spatial",     "label": "視覺空間", "played": true, "this_week": 56, "last_week": 58, "best": 58, "trend": "steady" },
        { "dimension": "math",               "label": "數學",     "played": true, "this_week": 45, "last_week": 65, "best": 65, "trend": "practice" },
        { "dimension": "language",           "label": "語言",     "played": true, "this_week": 70, "last_week": 55, "best": 70, "trend": "up" }
      ]
    },
    "play_time": {
      "total_seconds": 2400,
      "games": [
        { "source": "market_route",    "label": "菜市場找路",   "seconds": 480 },
        { "source": "memory_recall",   "label": "煮菜過程",     "seconds": 480 },
        { "source": "market_sort",     "label": "整理菜籃遊戲", "seconds": 480 },
        { "source": "fridge_check",    "label": "冰箱檢查",     "seconds": 480 },
        { "source": "market_shopping", "label": "市場買菜",     "seconds": 480 }
      ]
    },
    "diary": {
      "talk_seconds": 720,
      "entries": [
        {
          "diary_id": 3,
          "date": "2026-10-14",
          "title": "🌸 早上的公園散步",
          "photo_url": "https://...",
          "post_text": "今天早上去公園走了一圈，遇到老朋友。"
        }
      ]
    },
    "next_week_goal": "每一項都玩過了，下週繼續保持！",
    "disclaimer": "這不是醫療診斷，僅供自我了解"
  },
  "error": null
}
```

> 數值為示意。`summary` 由 AI 產生，每次內容可能不同。

**欄位說明**

| 欄位 | 型別 | 說明 |
|---|---|---|
| `week_start`、`week_end` | 字串 `YYYY-MM-DD` | 報告週的週一、週日 |
| `summary` | 字串 | 機器人的一句話總結，一定是正向的 |
| `highlights.active_day_count` | 整數 | 玩了幾天 |
| `highlights.session_count` | 整數 | 玩了幾場（已結束的遊戲場次） |
| `highlights.streak_days` | 整數 | 報告週內最長連續天數 |
| `daily_activity` | 陣列（固定 7 筆） | 本週打卡：`date`、`weekday`（一～日）、`is_active` |
| `abilities.overall` | 物件 | 整體表現：`this_week`、`last_week`、`best`、`trend` |
| `abilities.dimensions` | 陣列（固定 6 筆） | 六大能力，欄位同上，另有 `dimension`、`label`、`played` |
| `abilities.*.this_week`／`last_week`／`best` | 整數 1～100 或 `null` | 沒有分數時為 `null` |
| `abilities.*.trend` | `"up"`／`"steady"`／`"practice"` 或 `null` | 前端翻成「進步／持平／多練習」 |
| `play_time.total_seconds` | 整數（秒） | 五款遊戲遊玩時間總和 |
| `play_time.games` | 陣列（固定 5 筆） | 各遊戲 `source`、`label`、`seconds` |
| `diary.talk_seconds` | 整數（秒） | 本週對話時長（近似值） |
| `diary.entries` | 陣列 | 本週完成的日記：`diary_id`、`date`、`title`、`photo_url`、`post_text` |
| `next_week_goal` | 字串 | 下週小目標 |
| `disclaimer` | 字串 | 頁尾小字，固定為「這不是醫療診斷，僅供自我了解」 |

> 機器人的其他對話（「嗨，這一週我們一起回頭看看吧」「這週辛苦了，下週見！」等）是固定文字，由前端寫在畫面上，API 不回傳。

---

### 錯誤代碼一覽

| code | HTTP status | 說明 |
| --- | --- | --- |
| NOT\_AUTHENTICATED | 401 | 沒有帶 token |

> token 有帶但無效或過期時，DRF 會先擋下並回傳預設格式 `401 {"detail": "..."}`，不是統一格式。前端遇到 HTTP 401 一律當作需要重新登入。

---

## 五、程式位置

| 檔案 | 內容 |
|---|---|
| `dashboard/views.py` | `weekly_report_view`：檢查登入、回傳統一格式 |
| `dashboard/weekly_report.py` | 週報所有計算：報告週、活動、能力分數、遊玩時間、日記、下週小目標 |
| `dashboard/services.py` | `DIMENSIONS`（六大能力對照）、`diary_z_scores`（每篇日記的語言 z） |
| `dashboard/diary_zscore.py` | 單篇日記語言 z 的計算 |
| `ai_service/weekly_summary.py` | 一句話總結：正向事實、AI 呼叫、禁用詞檢查、固定句型 |
| `games/zscore.py` | `z_score_to_display_score`：z → 1～100 分（五款遊戲與週報共用） |
| `dashboard/tests_weekly_report.py`、`ai_service/tests.py` | 測試（AI 以 mock 取代，不會真的呼叫 OpenAI） |

---

## 六、尚待確認與備註事項

| 項目 | 說明 |
|---|---|
| 舊資料沒有 z | 各遊戲加入 `z_score` 前玩的場次不會出現在能力分數裡 |
| 常模待建立 | 目前一律跟自己的歷史比（冷啟動借全體）；等測試資料累積夠了，再用真實資料決定常模 |
| 冷啟動 | 全系統某款遊戲（或日記）不滿 3 場（篇）時，新使用者的前幾場算不出 z，該週沒有分數 |
| 聲影日記權重 | 沿用 `diary/analysis.py` 的 `communication_score` 權重，來源待確認 |
| 市場買菜速度分 | 前端需送 `reaction_time_ms`，否則速度分為 0、能力分只看正確率 |
| 整理菜籃遊玩時間 | 用反應時間加總，比實際遊玩時間短；更新前的場次為 0 |
| 對話時長 | 「最後回答 − 建立時間」的近似值 |
| AI 費用與速度 | 每次打開都呼叫一次 OpenAI（約 2～3 秒），之後可考慮快取 |
