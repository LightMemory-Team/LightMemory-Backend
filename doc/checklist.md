# 首頁 API 開發 Checklist

對照 [首頁_API需求文件.md](首頁_API需求文件.md) 第三節的欄位表,目前 `home` app 的完成狀態。

## 欄位完成狀態

| 欄位 | 狀態 | 對應函式 | 路由 | 備註 |
|---|---|---|---|---|
| `user_name` | ✅ 完成 | `get_user` | `/api/home/user/` | 需登入,回傳登入者的暱稱(`nickname`);舊帳號沒有暱稱時退回姓名、再退回帳號 |
| `daily_tip` | ✅ 完成 | `greet` | `/api/home/greet/` | 依日期(`toordinal() % len(tips)`)挑固定清單裡的句子 |
| `daily_suggestion`(`text` / `action_route`) | ✅ 完成 | `daily_suggestion` | `/api/home/daily_suggetion/` | 固定值,尚未依使用者進度變化 |
| `games[]`(`id` / `title` / `is_developed` / `played_this_week`) | ✅ 完成 | `games_list` | `/api/home/games/` | 需登入;內容來自 `games/catalog.py` 的 `GAMES`;`played_this_week` = 本週(週一到今天,台灣時間)有玩完該遊戲 |
| `unread_notification_count` | ❌ 未開始 | — | — | 需要 Notification model,歸屬 app 尚未決定 |
| `wall_posts[]`(`author_name` / `avatar_url` / `posted_at` / `content_text` / `like_count` / `comment_count`) | 🗑 已刪除 | — | — | 首頁改版後已沒有動態牆區塊,首頁 API 不再提供這組欄位(動態牆分頁本身不受影響) |

## 登入驗證（JWT）進度

| 項目 | 狀態 | 備註 |
|---|---|---|
| 驗證方式決定 | ✅ 完成 | 採用 JWT(`djangorestframework-simplejwt`) |
| 登入 API | ✅ 完成 | `POST /api/users/login/`,回傳 `access` / `refresh` token |
| Refresh API | ✅ 完成 | `POST /api/users/login/refresh/` |
| home 系列 API 套用驗證 | 🚧 進行中 | `user`、`games`(以及之後的 `daily-tasks`)已改成 `IsAuthenticated` + `request.user`;`ping`、`greet`、`daily_suggetion` 仍開放匿名 |

## 已知待處理事項

- [ ] 目前 4 個欄位是 4 支獨立 API,最終需求(需求文件第二節)是合併成**一支** `GET /api/home`,回傳整頁資料

- [ ] `greet`、`daily_suggetion` 仍是 `AllowAny` 的固定內容,之後若要依使用者變化再改成 `IsAuthenticated`

## 未開始

- [ ] `unread_notification_count`:決定 Notification model 放在哪個 app(`social` / `users` / 獨立 app)
- [x] `wall_posts[]`:首頁改版後已刪除,不需要做
