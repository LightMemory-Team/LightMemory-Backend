# 菜市場找路 API 本機測試教學

這份文件教你怎麼在本機手動測試「菜市場找路」（market_route）的 6 支 API。
資料存在 PostgreSQL 的 `GameSession`（每場遊戲）與 `GameStepLog`（每次作答）。

## 前置準備：啟動伺服器

在專案資料夾（`LightMemory-Backend`）底下開一個終端機視窗：

```bash
source venv/bin/activate
python manage.py runserver
```

看到類似訊息代表伺服器已啟動，**這個視窗要保持開著**：

```
Starting development server at http://127.0.0.1:8000/
```

接下來的步驟，請另外開一個新的終端機視窗操作（保留跑伺服器的視窗）。

> **關於登入**：開發階段沒帶 token 時，後端會暫時用資料庫裡的**第一位使用者**
> 當作玩家（見 `games/utils.py` 的 `get_current_user`），所以下面的 curl 不帶
> token 也能跑。要用自己的帳號測，每個指令加上
> `-H "Authorization: Bearer <access_token>"`。
>
> 注意：**帶了過期或錯誤的 token 會直接被擋 401**，就算 API 允許不登入也一樣，
> 而且回傳格式是 DRF 的 `{"detail": ..., "code": "token_not_valid"}`，
> 不是 `{success, data, error}`。

## 完整流程：跑一場遊戲

### 0. 看遊戲設定（可略過）

```bash
curl http://127.0.0.1:8000/api/games/market-route/config/
```

| 欄位 | 值 | 說明 |
|---|---|---|
| `total_questions` | 20 | 一場題數 |
| `timeout_seconds` | 20 | 每次作答時限 |
| `promote_streak` | 5 | 連對幾題升階 |
| `demote_streak` | 5 | 連錯幾次降階 |
| `fast_promote_streak` | 3 | 連續「快速答對」幾題升階 |
| `fast_response_ratio` | 0.5 | 反應時間 ≤ 曝光時間 × 這個比例，算快速答對 |
| `max_wrong_attempts` | 3 | 同一題最多作答幾次 |
| `stage_exposure_range` | 見回傳 | 各階段曝光時間 `[最寬鬆, 最緊]`（毫秒） |

### 1. 開始一場遊戲

```bash
curl -X POST http://127.0.0.1:8000/api/games/market-route/start/
```

回傳範例：

```json
{"success":true,"data":{"session_id":"3f2a9c1e-5b7d-4e8a-9c21-7d4e5f6a8b90","current_stage":"basic"},"error":null}
```

`session_id` 是 **UUID 字串**（不是數字），後面每一步都要帶這個值。
UUID 很長，建議先存成終端機變數，後面的指令直接用 `$SID`：

```bash
SID=3f2a9c1e-5b7d-4e8a-9c21-7d4e5f6a8b90
```

> 前端請用 `String` 接 `session_id`。用 `int` 解析會丟 `TypeError`，
> 遊戲會卡在轉圈畫面。

### 2. 拿題目

```bash
curl "http://127.0.0.1:8000/api/games/market-route/round/?session_id=$SID"
```

回傳範例：

```json
{"success":true,"data":{"question_number":1,"stage":"basic","target_item":"鮭魚","target_position":"center","distractor_items":[],"exposure_time_ms":2000},"error":null}
```

- `target_position` 就是這一題的正確答案位置：basic 固定 `center`，
  intermediate／advanced 是 `q1`～`q4`。
- `target_item` 從「鯛魚／鮭魚／鱸魚」隨機抽，**跟階段無關**。
- advanced 的 `distractor_items` 會有一個魚骨頭，位置**一定跟魚不同**。

### 3. 送出答案

把 `answer_position` 換成上一步看到的 `target_position`，就是答對；換成別的值就是答錯。

```bash
curl -X POST http://127.0.0.1:8000/api/games/market-route/round/answer/ \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"attempt_number\":1,\"answer_position\":\"center\",\"is_timeout\":false,\"response_time_ms\":300}"
```

送出欄位：

| 欄位 | 說明 |
|---|---|
| `session_id` | UUID 字串 |
| `attempt_number` | 這一題第幾次作答（1～3），影響基礎分 |
| `answer_position` | `center` / `q1`～`q4`；超時送 `null` |
| `is_timeout` | 是否超時 |
| `response_time_ms` | 反應時間，用來判斷快速答對與速度加成 |

> 前端另外送的 `question_number`、`paused_duration_ms` 後端**不會讀**。
> 後端用自己記錄的「目前這一題」判斷對錯，不靠前端的題號。

回傳的 `action` 告訴你下一步：

| action | 意思 | 下一步 |
|---|---|---|
| `next_question` | 進下一題 | 回第 2 步拿新題目 |
| `retry` | 答錯但這一題還沒錯滿 3 次 | **不用**拿新題目，同一題 `attempt_number + 1` 再送一次 |
| `promoted` | 答對且升階 | 回第 2 步 |
| `demoted` | 答錯（含超時）且連錯滿 5 次，退一階；優先於 `retry` | 回第 2 步 |

升降階規則：

- **升階**：連對 5 題，或連續 3 題「快速答對」，任一成立就升；已在 advanced 不再升。
- **降階**：連錯 5 次退一階。每一次作答都算（包含同一題重看後再錯、超時），
  答對就歸零；已在 basic 不再降。
- 升階或降階後，曝光時間重設成新階段最寬鬆的值。

### 4. 重複第 2、3 步

一直重複「拿題目 → 送出答案」，直到跑完 20 題（或想結束測試）。
後端**不會**自己在第 20 題結束，由前端數題數、呼叫 `finish/`。

### 5. 結束遊戲

```bash
curl -X POST http://127.0.0.1:8000/api/games/market-route/finish/ \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\"}"
```

會回傳整場統計：

| 欄位 | 說明 |
|---|---|
| `total_questions` | 固定 20 |
| `answered_count` | 實際作答過的題數 |
| `correct_count` / `timeout_count` | 答對次數 / 超時次數 |
| `accuracy` | `correct_count / answered_count`，0～1 |
| `avg_response_time_ms` | 平均反應時間 |
| `final_stage` | 結束時的階段 |
| `total_score` | **原始分數**加總（不是 0～100），20 題全對最高約 360 分 |

`finish/` 呼叫第二次會直接回傳第一次的結果，不會重算。

### 6. 查詢結果

```bash
curl "http://127.0.0.1:8000/api/games/market-route/result/$SID/"
```

內容跟 `finish/` 一樣，但外面**多包一層 `session_result`**：

```json
{"success":true,"data":{"session_result":{"total_questions":20,"total_score":214,"...":"..."}},"error":null}
```

## 錯誤代碼

錯誤回傳格式：

```json
{"success":false,"data":null,"error":{"code":"SESSION_NOT_FOUND","message":"找不到指定的 session"}}
```

| code | HTTP | 什麼時候發生 | 適用 API |
|---|---|---|---|
| `USER_NOT_FOUND` | 404 | 沒登入，而且資料庫裡一位使用者都沒有 | start |
| `SESSION_NOT_FOUND` | 404 | `session_id` 打錯或不存在 | round / round/answer / finish / result |
| `FORBIDDEN` | 403 | 這場遊戲不是目前使用者的 | round / round/answer / finish / result |
| `SESSION_ALREADY_FINISHED` | 409 | 已經 `finish/` 了還想出題或作答 | round / round/answer |
| `ROUND_NOT_STARTED` | 400 | 沒有進行中的題目：還沒呼叫 `round/`，或上一題已經換題了（`retry` 以外的 action）卻沒拿新題目 | round/answer |
| `SESSION_NOT_FINISHED` | 400 | 還沒呼叫 `finish/` 就查結果 | result |

## 小提醒

- 測試資料在資料庫裡，想看或刪除可以到 Django admin
  （`http://127.0.0.1:8000/admin/`）的 **Game sessions**。
- 自動化測試：`python manage.py test games.market_route`。
