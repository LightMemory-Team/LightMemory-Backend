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
- 各 app 自己手寫的 inline 錯誤回應（games 等）沒有動；social 的通知 API 已改用 `{success, data, error}`（見下方「通知 API 回傳格式」），動態牆仍是舊格式 `{data, pagination}`／`{error}`。
- 主動指定錯誤碼：`raise ApiError("USERNAME_TAKEN", "訊息", status_code=...)`。

## API 一覽

| 規格 | 實際網址 | 備註 |
|---|---|---|
| 取得／修改自己的資料 | `GET/PATCH /api/users/me/` | 需登入；`username` 唯讀；未填的選填欄位回 `null` |
| 註冊 | `POST /api/users/register/` | 必填 username、password、nickname、birth_date、gender；選填 region、緊急聯絡人 |
| 忘記密碼第 1 步 | `POST /api/users/password-reset/check/` | 免登入；不存在回 404 `ACCOUNT_NOT_FOUND` |
| 忘記密碼第 2 步 | `POST /api/users/password-reset/` | 免登入；兩次不同回 `PASSWORD_MISMATCH`。**尚無驗證碼，上線前要補** |
| 首頁問候 | `GET /api/home/user/` | 需登入；`user_name` 回暱稱（舊帳號退回姓名、再退回帳號）；`unread_notification_count` 是鈴鐺未讀數，和通知 `unread_count` 一致 |
| 首頁遊戲卡片 | `GET /api/home/games/` | 需登入；新增 `name`（短名稱，如「整理菜籃」）與 `played_this_week`；沿用 `title`（完整名稱）／`is_developed` |
| 今日任務 | `GET /api/home/daily-tasks/` | 需登入；當天第一次呼叫時產生並存進 `home.DailyTask` |
| 通知列表 | `GET /api/social/notifications/` | 回傳 `data.notifications[]`；沿用舊網址與欄位（`id`、`notification_type`、`message`、`target_url`） |
| 通知全部已讀 | `PATCH /api/social/notifications/` | 新增；只動自己的未讀通知 |
| 通知未讀數 | `GET /api/social/notifications/unread_count/` | 回傳 `data.unread_notification_count` |
| 通知單筆已讀 | `PATCH /api/social/notifications/<id>/read/` | 不是自己的或不存在回 404 `NOTIFICATION_NOT_FOUND` |
| 週報 | `GET /api/dashboard/weekly-report/` | 點開時寫入 `dashboard.WeeklyReport`（每人每週一筆） |

## 通知 API 回傳格式（統一格式）

通知 4 支 API 一律回 `{ "success": bool, "data": ..., "error": ... }`。**這是破壞性變更：前端要從 `response['notifications']` 改成 `response['data']['notifications']`。**

```json
// GET /api/social/notifications/
{ "success": true, "data": { "notifications": [
  { "id": 1, "notification_type": "comment", "notification_type_display": "留言",
    "message": "小明 在你的日記留言了", "target_url": "/posts/12/",
    "is_read": false, "created_at": "2026-11-02T09:00:00+08:00" } ] }, "error": null }

// GET /api/social/notifications/unread_count/
{ "success": true, "data": { "unread_notification_count": 3 }, "error": null }

// PATCH /api/social/notifications/  與  PATCH /api/social/notifications/<id>/read/
{ "success": true, "data": { "message": "已全部標記為已讀" }, "error": null }

// 找不到通知（HTTP 404）
{ "success": false, "data": null,
  "error": { "code": "NOTIFICATION_NOT_FOUND", "message": "查無此通知" } }
```

通知類型 `notification_type`：`comment`、`like`、`family_reply`、`diary_reminder`、`game_reminder`（目前只有 `comment` 會被系統建立）。`target_url` 指向動態牆貼文，沒有日記 ID 欄位。

## 通知流程

**怎麼產生**（目前只有一個來源）：親友打開分享連結留言 `POST /api/share/<share_token>/comments/`（免登入，同 IP 每分鐘最多 10 則）→ 建立 `Comment` → 同時建立一則 `Notification` 給日記主人：

| 欄位 | 值 |
|---|---|
| `notification_type` | `comment` |
| `message` | `{暱稱} 在你的日記留言了` |
| `target_url` | `/posts/{貼文 id}/` |
| `is_read` | `false` |

長輩自己在動態牆留言不會產生通知。

**前端怎麼串**（都要登入，前綴 `/api/social/`）：

1. 開首頁：`GET /api/home/user/` 讀 `unread_notification_count` 顯示鈴鐺紅點（和 `notifications/unread_count/` 是同一份數字）。
2. 點進通知頁：`GET notifications/`，新的在前；依 `notification_type` 換圖示、顯示 `message`、用 `created_at`（ISO 8601，帶時區）顯示時間、用 `is_read` 決定紅點。
3. 點某一則：`PATCH notifications/<id>/read/`；點「全部已讀」：`PATCH notifications/`（body 不需要，送 `{"is_read": true}` 也會被忽略）。
4. 點通知跳轉：`notification_type` 是 `comment` 時，從 `target_url`（如 `/posts/12/`）取出貼文 id，開動態牆貼文詳情。

**和前端原本預期不同的地方**：網址是 `/api/social/notifications/`（不是 `/api/notifications/`）；欄位是 `id`、`message`（不是 `notification_id`、`title`、`content`）；資料在 `data.notifications`。

**還沒做**：

- `like`、`family_reply`、`diary_reminder`、`game_reminder` 四種類型沒有程式會建立，路徑格式也未定。
- 沒有 `related_diary_id`；`target_url` 指向動態牆貼文。
- 通知列表沒有分頁，會一次回傳全部。

## 和規格不同的地方

- **通知**：網址維持 `/api/social/notifications/`，且沒有新增 `type`、`target_id`、`title`、`content`——現有欄位已能表達同樣的資訊（前端依 `notification_type` 換圖示、用 `message` 顯示、用 `target_url` 開動態牆貼文）。
- **首頁遊戲卡片**：規格範例寫 `name`、短名稱（整理菜籃）。實作兩個都給：`name` 是短名稱，`title` 是完整名稱（整理菜籃遊戲），前端用哪個都行。
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
