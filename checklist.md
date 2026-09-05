# 首頁 API 開發 Checklist

對照 [首頁_API需求文件.md](首頁_API需求文件.md) 第三節的欄位表,目前 `home` app 的完成狀態。

## 欄位完成狀態

| 欄位 | 狀態 | 對應函式 | 路由 | 備註 |
|---|---|---|---|---|
| `user_name` | ✅ 完成 | `get_user` | `/api/home/user/` | 目前先固定拿 `User.objects.first()`,還沒有登入驗證 |
| `daily_tip` | ✅ 完成 | `greet` | `/api/home/greet/` | 依日期(`toordinal() % len(tips)`)挑固定清單裡的句子 |
| `daily_suggestion`(`text` / `action_route`) | ✅ 完成 | `daily_suggestion` | `/api/home/daily_suggetion/` | 固定值,尚未依使用者進度變化 |
| `games[]`(`id` / `title` / `is_developed`) | ✅ 完成 | `games_list` | `/api/home/games/` | 對應 `Game` model,`title`←`game_name`、`is_developed`←`is_enabled`;`games_game` 表目前是空的,需要手動新增資料才有內容 |
| `unread_notification_count` | ❌ 未開始 | — | — | 需要 Notification model,歸屬 app 尚未決定 |
| `wall_posts[]`(`author_name` / `avatar_url` / `posted_at` / `content_text` / `like_count` / `comment_count`) | ⏸ 待會議確認 | — | — | 決定改由 Firebase 處理,是否還要由 Django 回傳待跟團隊對齊 |

## 登入驗證（JWT）進度

| 項目 | 狀態 | 備註 |
|---|---|---|
| 驗證方式決定 | ✅ 完成 | 採用 JWT(`djangorestframework-simplejwt`) |
| 登入 API | ✅ 完成 | `POST /api/users/login/`,回傳 `access` / `refresh` token |
| Refresh API | ✅ 完成 | `POST /api/users/login/refresh/` |
| home 系列 API 套用驗證 | ❌ 未開始 | 目前 `home` 底下所有 view 仍是 `AllowAny`,還沒改成 `IsAuthenticated` + `request.user` |

## 已知待處理事項

- [ ] 目前 4 個欄位是 4 支獨立 API,最終需求(需求文件第二節)是合併成**一支** `GET /api/home`,回傳整頁資料

- [ ] `user_name` 等欄位目前沒有登入驗證,先固定抓第一筆使用者;JWT 登入 API 已完成,但 `home` 系列 view 尚未改成 `IsAuthenticated` + `request.user`,仍是待處理項目

## 未開始

- [ ] `unread_notification_count`:決定 Notification model 放在哪個 app(`social` / `users` / 獨立 app)
- [ ] `wall_posts[]`:等會議確認 Firebase 串接方式後再決定 Django 端要不要處理
