# 首頁改版 API 實作對照

對應「首頁改版 API 規格書」（2026-10-28）。這份文件只記錄**實作上和規格不同、或規格沒寫清楚**的地方，欄位細節請看規格書。

## 統一錯誤格式

所有 DRF 丟出的錯誤（`config/exceptions.py`）都是：

```json
{"success": false, "data": null,
 "error": {"code": "VALIDATION_ERROR", "message": "資料格式有誤，請再檢查一下",
           "fields": {"nickname": ["暱稱不能是空白"]}}}
```

- `fields` 只有欄位驗證錯誤才有。
- 註冊、登入、換發 token 的錯誤格式因此改變（原本是 DRF 預設的 `{"欄位": [...]}`、`{"detail": ...}`）。
- 各 app 自己手寫的 inline 錯誤回應（games、social 的 `mark_as_read_error` 等）沒有動。
- 主動指定錯誤碼：`raise ApiError("USERNAME_TAKEN", "訊息", status_code=...)`。

## API 一覽

| 規格 | 實際網址 | 備註 |
|---|---|---|
| 取得／修改自己的資料 | `GET/PATCH /api/users/me/` | 需登入；`username` 唯讀；未填的選填欄位回 `null` |
| 註冊 | `POST /api/users/register/` | 必填 username、password、nickname、birth_date、gender；選填 region、緊急聯絡人 |
| 忘記密碼第 1 步 | `POST /api/users/password-reset/check/` | 免登入；不存在回 404 `ACCOUNT_NOT_FOUND` |
| 忘記密碼第 2 步 | `POST /api/users/password-reset/` | 免登入；兩次不同回 `PASSWORD_MISMATCH`。**尚無驗證碼，上線前要補** |
| 首頁問候 | `GET /api/home/user/` | 需登入；`user_name` 回暱稱（舊帳號退回姓名、再退回帳號） |
| 首頁遊戲卡片 | `GET /api/home/games/` | 需登入；新增 `played_this_week`；沿用 `title`／`is_developed` |
| 今日任務 | `GET /api/home/daily-tasks/` | 需登入；當天第一次呼叫時產生並存進 `home.DailyTask` |
| 通知列表 | `GET /api/social/notifications/` | 沿用舊網址與欄位（`notification_type`、`message`、`target_url`） |
| 通知全部已讀 | `PATCH /api/social/notifications/` | 新增；只動自己的未讀通知 |
| 週報 | `GET /api/dashboard/weekly-report/` | 點開時寫入 `dashboard.WeeklyReport`（每人每週一筆） |

## 和規格不同的地方

- **通知**：網址維持 `/api/social/notifications/`，且沒有新增 `type`、`target_id`、`title`、`content`——現有欄位已能表達同樣的資訊（前端依 `notification_type` 換圖示、用 `message` 顯示、用 `target_url` 開動態牆貼文）。
- **首頁遊戲卡片**：規格範例寫 `name`、短名稱（整理菜籃），實作沿用 `title`（整理菜籃遊戲）以免前端壞掉。
- **首頁 `wall_posts`**：程式裡原本就沒有，所以只更新文件標記為已刪除。
- **User 欄位**：`phone`、`address`、`first_name`、`last_name` 只從 API 拿掉，資料庫欄位保留（避免破壞性 migration）。

## 今日任務的規則

- 每天 3 個遊戲任務 + 1 個聲影日記，必要時加 1 個「看看上週回顧」。
- 遊戲排序：本週（週一到今天）還沒玩完的優先 → 分數低的優先（未解鎖、或近 7 天沒分數視為最低）→ 依 attention、working_memory、executive_function、visual_spatial、math 固定順序。
- `done` 每次即時計算：遊戲＝今天有玩完一場；日記＝今天有一篇非失敗的日記；上週回顧＝已點開上週週報。
- 「玩過」只算 `status="finished"` 的場次。
- 上週回顧：上週有遊戲或日記紀錄、且還沒點開週報才會出現；點開那天顯示已完成，隔天起消失。

## 資料表

| 表 | App | 用途 |
|---|---|---|
| `DailyTask` | home | 每天產生的任務（同一天固定不變） |
| `WeeklyReport` | dashboard | 每人每週一筆週報快照，`viewed_at` 為第一次點開的時間 |
| `User` 新增欄位 | users | `nickname`、`emergency_contact_name`、`emergency_contact_phone`；`region` 改為可空 |
