# 菜市場找路 API 本機測試教學（JSON 儲存暫時版）

這份文件教你怎麼在本機手動測試「菜市場找路」（market_route）的 6 支 API。
目前資料是暫時存在 JSON 檔案（`games/market_route/data/sessions/`），
之後會換成正式資料庫。

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

## 完整流程：跑一場遊戲

### 1. 開始一場遊戲

```bash
curl -X POST http://127.0.0.1:8000/api/games/market-route/start/
```

回傳範例：

```json
{"success":true,"data":{"session_id":1,"current_stage":"basic"},"error":null}
```

記下 `session_id`（例如 `1`），後面每一步都要帶這個值。

### 2. 拿題目

```bash
curl "http://127.0.0.1:8000/api/games/market-route/round/?session_id=1"
```

回傳範例：

```json
{"success":true,"data":{"question_number":1,"stage":"basic","target_item":"鮭魚","target_position":"center","distractor_items":[],"exposure_time_ms":2000},"error":null}
```

`target_position` 就是這一題的正確答案位置。

### 3. 送出答案

把 `answer_position` 換成上一步看到的 `target_position`，就是答對；換成別的值就是答錯。

```bash
curl -X POST http://127.0.0.1:8000/api/games/market-route/round/answer/ \
  -H "Content-Type: application/json" \
  -d '{"session_id":1,"attempt_number":1,"answer_position":"center","is_timeout":false,"response_time_ms":300,"paused_duration_ms":0}'
```

回傳會告訴你這次是否答對、下一步動作（`action`）：

| action | 意思 |
|---|---|
| `next_question` | 進下一題 |
| `retry` | 答錯但還沒到 3 次，同一題再試 |
| `promoted`（目前實作以 `current_stage` 變化呈現） | 升階 |

### 4. 重複第 2、3 步

一直重複「拿題目 → 送出答案」，直到跑完 20 題（或想結束測試）。

### 5. 結束遊戲

```bash
curl -X POST http://127.0.0.1:8000/api/games/market-route/finish/ \
  -H "Content-Type: application/json" \
  -d '{"session_id":1}'
```

會回傳整場統計（正確率、總分、平均反應時間等）。

### 6. 查詢結果

```bash
curl http://127.0.0.1:8000/api/games/market-route/result/1/
```

會回傳跟 `finish/` 一樣的彙總結果（適合前端「回顧畫面」用）。

## 小提醒

- 如果 `result/<session_id>/` 查詢一個**還沒呼叫 finish/** 的 session，會回傳
  `{"success":false,"error":"這場遊戲尚未結束"}`，這是正常行為。
- 如果 `session_id` 打錯或不存在，會回傳 404 跟
  `{"success":false,"error":"找不到指定的 session"}`。
- 想清空所有測試資料重新開始，可以刪除整個資料夾（伺服器會自動重建）：

  ```bash
  rm -rf games/market_route/data/sessions
  ```

- 這個資料夾不會進 git（已設定在 `.gitignore`），所以不用擔心測試資料被 commit 上去。
