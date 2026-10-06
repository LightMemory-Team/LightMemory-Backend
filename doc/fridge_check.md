# 冰箱檢查 — 系統規格書

Oct 04, 2026 · @LightMemory-Backend

遊戲類別：空間與工作記憶認知訓練｜遊戲代碼：fridge_check

## 一、玩法總覽

玩法依據空間認知、工作記憶與視覺搜尋能力設計：畫面呈現一個冰箱九宮格層架，內部擺放各種食材，系統提出位置相關的題目，玩家依題意選出對應食材或座標。

**單輪作答流程**

1. **題目呈現階段**：畫面顯示冰箱食材陳列板（`board`）、題目提示（`prompt`）與題型（`question_type`）。
2. **玩家作答階段**：
   - 相對位置題 / 定位題：單次點選（`interaction_type: tap`）。
   - 擺放題：先選食材再點選放置位置（`interaction_type: select_then_tap`）。
3. **後端判題與 DDA 狀態更新**：
   - **答對**：記錄反應時間加分、累計連對次數，自動推進至下一題（或第 10 題結束結算）。
   - **答錯（未滿 3 次）**：中斷連對，標記重試（`retry: true`），允許在同一題繼續嘗試。
   - **答錯（錯滿 3 次）**：強制跳過該題（`question_skipped: true`），記錄跳題扣分，推進至下一題。

## 二、難度三階段與題型設計

難度由「冰箱擺放層數」與「題目複雜度」構成三個階段：

| 階段 | 代碼 | 冰箱陳列層數 | 空間網格 | 出現題型 |
| --- | --- | --- | --- | --- |
| 初階 | easy | 1 層（上層） | 1×3 (3 格) | 相對位置題 |
| 中階 | medium | 2 層（上、中層） | 2×3 (6 格) | 相對位置題、定位題 |
| 進階 | hard | 3 層（上、中、下層） | 3×3 (9 格) | 相對位置題、定位題、擺放題 |

### 三大題型說明

1. **相對位置題（`relative_position`）**：
   - 範例：「雞蛋的左邊是什麼？」
   - 作答格式：`{ "food_code": "tomato" }`
   - 互動型態：`tap`
2. **定位題（`locate_food`）**：
   - 範例：「胡蘿蔔在第幾層第幾個？」
   - 作答格式：`{ "position": "r2c1" }`
   - 互動型態：`tap`
3. **擺放題（`place_food`）**：
   - 範例：「請將番茄放到牛奶的右邊」
   - 作答格式：`{ "food_code": "tomato", "position": "r1c3" }`
   - 互動型態：`select_then_tap`

## 三、動態難度調整（DDA）規則

遊戲共 10 題（`TOTAL_QUESTIONS = 10`），每一場固定從初階（`easy`）開始。

- **核心架構**：整合 `games.dda` 共用引擎（`DDAConfig` + `NoOpStrategy` + `apply_answer`）。
- **升階門檻**：連續答對 3 題（`promote_streak = 3`）升一階：
  - `easy -> medium`
  - `medium -> hard`
  - `hard` 維持 `hard`（封頂）
- **升階判定**：升階時回傳 `difficulty_changed: true` 與 `previous_difficulty`，供前端播放難度升級動畫或音效。
- **不設計降階**：答錯時僅將連對次數歸零（`correct_streak = 0`），難度維持當前階段，避免長者挫折感。

## 四、計分邏輯

整場最終成績採多維度加權計算，包含正確率、反應速度、難度加分與跳題懲罰。正確率與速度分加權後滿分為 100，再加上難度加分，因此總分**可以超過 100**（不設上限）：

### 1. 正確率分數（Accuracy Score，權重 70%）
$$\text{accuracy} = \frac{\text{total\_correct}}{\text{total\_questions}} \times 100$$

### 2. 反應速度分數（Speed Score，權重 30%）
單題答對時，依反應時間毫秒數（`reaction_time_ms`）給予速度分數（10 題滿分 100 分）：

| 反應時間（秒） | 該題速度分 |
| --- | --- |
| $\le 3$ 秒 | 10 分 |
| $\le 6$ 秒 | 8 分 |
| $\le 10$ 秒 | 5 分 |
| $> 10$ 秒 | 3 分 |
| 答錯 | 0 分 |

### 3. 難度加分（Difficulty Bonus）
- medium 階段答對每題加 **+0.5 分**
- hard 階段答對每題加 **+1.0 分**

$$\text{difficulty\_bonus} = (\text{medium\_correct} \times 0.5) + (\text{hard\_correct} \times 1.0)$$

### 4. 跳題扣分懲罰（Error Penalty）
- 同一題答錯滿 3 次被強制跳過，每題扣 **2 分**：

$$\text{error\_penalty} = \text{skipped\_question\_count} \times 2$$

### 5. 最終總分（Final Score）
$$\text{raw\_final\_score} = (\text{accuracy} \times 0.7) + (\text{speed\_score} \times 0.3) + \text{difficulty\_bonus} - \text{error\_penalty}$$
$$\text{final\_score} = \text{round}(\max(0, \text{raw\_final\_score}), 2)$$

- 只限制下限為 0（避免跳題扣分造成負分），**不設上限**。
- 例：10 題全對且皆在 3 秒內、medium 答對 3 題、hard 答對 4 題 → $70 + 30 + 5.5 = 105.5$ 分。
- 舊版曾以 $\min(100, \cdot)$ 截斷，因此修正前完成的歷史紀錄，其 `final_score` 最高仍為 100。

## 五、資料表設計

沿用遊戲共用儲存架構：`GameSession`（共用場次表）+ `GameStepLog`（逐題明細）。

**GameSession（共用表）**

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | UUID (PK) | 主鍵 Session ID |
| game | FK → Game | 本遊戲關聯至 `code = "fridge_check"` |
| user | FK → User | 使用者 |
| status | varchar(20) | in\_progress / finished / abandoned |
| question\_number | int | 目前題號 (1 ~ 10) |
| current\_question | JSONField | 當前題目暫存資料（前端不回傳正解） |
| state | JSONField | 進行中即時狀態（DDA、計分與連對累積） |
| result | JSONField | 結算後成績摘要 |
| created\_at / finished\_at | datetime | 開始與結束時間戳記 |

**state 內容範例**

```json
{
  "user_id": 1,
  "current_stage": "medium",
  "difficulty": "medium",
  "correct_streak": 2,
  "consecutive_correct": 2,
  "total_correct": 5,
  "speed_score": 48,
  "total_reaction_time_ms": 13200,
  "answer_count": 6,
  "medium_correct": 2,
  "hard_correct": 0,
  "current_wrong_count": 0,
  "current_question_had_error": false,
  "skipped_question_count": 0
}
```

**result 內容範例（遊戲結束）**

```json
{
  "total_correct": 8,
  "total_questions": 10,
  "accuracy": 80.0,
  "speed_score": 76,
  "medium_correct": 3,
  "hard_correct": 2,
  "difficulty_bonus": 3.5,
  "skipped_question_count": 1,
  "error_penalty": 2,
  "final_score": 80.3,
  "final_difficulty": "hard",
  "average_reaction_time_ms": 2450,
  "completed_at": "2026-10-04T00:15:30.123456+08:00"
}
```

## 六、API 規格

共 3 支核心 API，統一回傳格式：`{ "success": bool, "data": {...}, "error": null }`，欄位一律 snake\_case。

### 1. POST `/api/games/fridge-check/sessions/`
建立新遊戲局次，並取得第 1 題資料。
*(別名路由支援：`POST /api/games/fridge-check/session/`)*

**回傳資料（`data`）**

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| session\_id | string (UUID) | 局次唯一識別碼，後續判題必帶 |
| difficulty | string | 初始難度（固定 "easy"） |
| current\_question | int | 題號（固定 1） |
| total\_questions | int | 總題數（固定 10） |
| consecutive\_correct | int | 連對次數（初始 0） |
| wrong\_count | int | 本題錯誤次數（初始 0） |
| question | object | 題目資料（含 question\_type, prompt, board, interaction\_type） |

**範例**

```json
{
  "success": true,
  "data": {
    "session_id": "017a5a6c-e092-46d2-8e38-6a6e7551d744",
    "difficulty": "easy",
    "current_question": 1,
    "total_questions": 10,
    "consecutive_correct": 0,
    "wrong_count": 0,
    "question": {
      "question_id": 1,
      "question_type": "relative_position",
      "prompt": "青椒的左邊是什麼？",
      "board": [
        { "position": "r1c1", "food_code": "carrot", "food_name": "胡蘿蔔" },
        { "position": "r1c2", "food_code": "tomato", "food_name": "番茄" },
        { "position": "r1c3", "food_code": "pepper", "food_name": "青椒" }
      ],
      "source_food": null,
      "interaction_type": "tap"
    }
  },
  "error": null
}
```

---

### 2. POST `/api/games/fridge-check/sessions/{session_id}/answers/`
送出單題作答答案，由後端執行判題、DDA 更新、重試判定或換題。
*(別名路由支援：`POST .../session/{id}/answer/`、`POST .../sessions/{id}/answer/`)*

**Request Body**

| 欄位 | 型別 | 必填 | 說明 |
| --- | --- | --- | --- |
| answer | object | 是 | 作答答案內容（`{ "food_code": "banana" }` 或 `{ "position": "r2c1" }`） |
| reaction\_time\_ms | int | 否 | 作答反應時間（毫秒） |

**Response Body（答對，換下一題）**

```json
{
  "success": true,
  "data": {
    "is_correct": true,
    "retry": false,
    "is_completed": false,
    "wrong_count": 0,
    "remaining_attempts": 3,
    "consecutive_correct": 1,
    "difficulty_changed": false,
    "previous_difficulty": null,
    "difficulty": "easy",
    "total_correct": 1,
    "next_question": {
      "question_id": 2,
      "question_type": "relative_position",
      "prompt": "雞蛋的左邊是什麼？",
      "board": [...],
      "source_food": null,
      "interaction_type": "tap"
    }
  },
  "error": null
}
```

**Response Body（答錯，重試）**

```json
{
  "success": true,
  "data": {
    "is_correct": false,
    "retry": true,
    "current_question": 1,
    "difficulty": "easy",
    "wrong_count": 1,
    "remaining_attempts": 2,
    "consecutive_correct": 0,
    "difficulty_changed": false,
    "previous_difficulty": null,
    "is_completed": false,
    "next_question": null
  },
  "error": null
}
```

**Response Body（第 10 題答完，遊戲結算完成）**

```json
{
  "success": true,
  "data": {
    "is_correct": true,
    "retry": false,
    "is_completed": true,
    "total_correct": 8,
    "total_questions": 10,
    "accuracy": 80.0,
    "speed_score": 76,
    "difficulty_bonus": 3.5,
    "error_penalty": 2,
    "final_score": 80.3,
    "final_difficulty": "hard",
    "average_reaction_time_ms": 2450,
    "completed_at": "2026-10-04T00:20:15.123456+08:00"
  },
  "error": null
}
```

---

### 3. GET `/api/games/fridge-check/history/`
取得當前登入使用者的冰箱檢查歷史遊玩紀錄（依完成時間由新到舊排序）。

**Response Body**

```json
{
  "success": true,
  "data": {
    "history": [
      {
        "score": 85.5,
        "accuracy": 90.0,
        "reaction_time": 2.15,
        "final_difficulty": "hard",
        "played_at": "2026-10-04T00:15:30.123456+08:00",
        "played_date": "2026-10-04",
        "session_id": "017a5a6c-e092-46d2-8e38-6a6e7551d744",
        "total_correct": 9,
        "total_questions": 10,
        "speed_score": 82,
        "difficulty_bonus": 4.0,
        "error_penalty": 0,
        "final_score": 85.5,
        "average_reaction_time_ms": 2150,
        "completed_at": "2026-10-04T00:15:30.123456+08:00"
      }
    ]
  },
  "error": null
}
```

---

### 錯誤代碼一覽

| code | HTTP status | 說明 | 適用 API |
| --- | --- | --- | --- |
| SESSION\_NOT\_FOUND | 404 | 找不到指定的 session\_id | sessions/{id}/answers/ |
| SESSION\_COMPLETED | 400 | 此遊戲局次已結束，不可重複提交 | sessions/{id}/answers/ |
| INVALID\_ANSWER | 400 | answer 欄位格式錯誤（非物件） | sessions/{id}/answers/ |
| INVALID\_REACTION\_TIME | 400 | reaction\_time\_ms 格式錯誤 | sessions/{id}/answers/ |
| USER\_NOT\_FOUND | 404 | 查無使用者資訊 | sessions/, history/ |

## 七、API 呼叫順序

```mermaid
flowchart TD
    A[POST /api/games/fridge-check/sessions/] -->|取得 session_id 與第 1 題| B[POST .../sessions/{id}/answers/]
    B -->|is_correct=False 且 wrong_count < 3| C[原題重試 retry: true]
    C --> B
    B -->|is_correct=False 且 wrong_count = 3| D[跳過本題 question_skipped: true]
    B -->|is_correct=True 未滿 10 題| E[更新 DDA，取得 next_question]
    D -->|未滿 10 題| E
    E --> B
    B -->|完成第 10 題| F[結算成績 is_completed: true]
    D -->|第 10 題跳題| F
    F --> G[GET /api/games/fridge-check/history/]
```

## 八、尚待確認與備註事項

- 前端若需播放難度升級特效，可監聽判題回應中的 `difficulty_changed == true` 與 `previous_difficulty`。
- 錯滿 3 次跳題時，後端會自動在該次回應附帶 `next_question`，前端直接切換下一題即可。
- 歷史紀錄提供舊版欄位（`score`, `accuracy`, `reaction_time`）與新版完整欄位雙重相容。
