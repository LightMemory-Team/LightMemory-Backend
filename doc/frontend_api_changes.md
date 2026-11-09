# 後端安全與穩定性修正總覽（F1～F7）

更新日期：2026-11-09 · 範圍：`fix/features` 分支（個別功能問題），F1～F7 已全部合併進去

這份文件說明這一輪後端修正**改了什麼、為什麼改、前端要配合什麼**。給前端（Flutter）看，也可以當後端的修改紀錄。

> 重點先看第 1 節的「前端待辦」與「錯誤碼總表」。想知道某一項的來龍去脈，再看第 2 節對應的小節。

---

## 0. 總覽

| 編號 | 問題 | 嚴重度 | 前端要改嗎 | PR |
|---|---|---|---|---|
| F1 | 遊戲 API 未登入時，會被當成「資料庫第一位使用者」 | 高 | ⚠️ 遊戲請求一律要帶 JWT | [#87](https://github.com/LightMemory-Team/LightMemory-Backend/pull/87) |
| F2 | 冰箱檢查、市場買菜的作答端點不檢查 session 屬於誰 | 高 | ⚠️ 作答要用建立該場遊戲的同一個帳號 | [#88](https://github.com/LightMemory-Team/LightMemory-Backend/pull/88) |
| F3 | 市場分類（market_sort）可讀取／覆蓋他人的場次 | 高 | ⚠️ `session_id` 用 UUID，換帳號要換新的 | [#89](https://github.com/LightMemory-Team/LightMemory-Backend/pull/89) |
| F4 | 忘記密碼 API 沒有任何次數限制 | 中 | ⚠️ 要處理 HTTP 429 | [#90](https://github.com/LightMemory-Team/LightMemory-Backend/pull/90) |
| F5 | 日記照片與錄音是永久公開網址 | 高 | ⚠️ 網址變成有時效，不可永久儲存 | [#91](https://github.com/LightMemory-Team/LightMemory-Backend/pull/91) |
| F6 | 刪除帳號後，雲端檔案沒有被刪 | 中 | 不用（可選：刪帳號後清本機快取） | [#92](https://github.com/LightMemory-Team/LightMemory-Backend/pull/92) |
| F7 | 回覆日記時 `round_index` 不合法或重複會 500；寫入沒有 transaction | 中 | ⚠️ 要處理 400／409 | [#93](https://github.com/LightMemory-Team/LightMemory-Backend/pull/93) |

- 測試：原本 764 個，現在 **835 個全部通過**（另有 1 個原本就預期失敗），新增 71 個測試。
- 這一輪**沒有修改資料表**，不需要 migration。
- 每一項都有驗證過「把修正拿掉，新測試就會失敗」，確認測試真的有在保護。

---

## 1. 給前端的重點

### 1.1 前端待辦清單

- [ ] **所有遊戲請求都帶 `Authorization: Bearer <access_token>`**（F1、F2、F3），包含作答端點與 `market-sort`
- [ ] 登出再換帳號登入時，**清掉舊的 `session_id`**（F2、F3）
- [ ] `market-sort` 的 `session_id` **用 UUID**，不要用 `test_1` 這類簡單的值（F3）
- [ ] 忘記密碼兩支 API 要處理 **429**，顯示「操作太頻繁，請稍後再試」，可讀 `Retry-After` 標頭（F4）
- [ ] 日記的 `photo_url`、`audio_url` **不要永久儲存**，也不要用完整網址當圖片快取 key；用 `diary_id` 當 key（F5）
- [ ] `photo_url`、`audio_url` 可能是 **`null`**（簽名失敗），要有預設圖／隱藏播放鈕（F5）
- [ ] 回覆日記（`replies`）要處理 **400 `INVALID_ROUND_INDEX`** 與 **409 `ROUND_ALREADY_ANSWERED`**（F7）
- [ ] 收到 `401 NOT_AUTHENTICATED` 時，用 refresh token 換新 token 並重送；失敗再導回登入頁
- [ ] 以 `error.code` 判斷錯誤，**不要比對 `error.message` 文字**

### 1.2 錯誤碼總表（這一輪新增或變更的）

| HTTP | `error.code` | 何時出現 | 建議處理 |
|---|---|---|---|
| 401 | `NOT_AUTHENTICATED` | token 過期或無效（本來就有） | 用 refresh token 換新 token，重送請求 |
| 404 | `USER_NOT_FOUND` | 遊戲開場／歷史端點**沒帶 token**（F1） | 視為 bug：檢查是否漏帶標頭；使用者端導回登入頁 |
| 403 | `FORBIDDEN` | 這場遊戲不屬於目前登入的人，或沒帶 token（F1、F2、F3） | 不要重試；回首頁或重新開始一場 |
| 404 | `SESSION_NOT_FOUND` | `session_id` 不存在（本來就有） | 重新開始一場 |
| 429 | `TOO_MANY_REQUESTS` | 忘記密碼嘗試太頻繁（F4） | 顯示等待提示，依 `Retry-After`（秒）後再試 |
| 400 | `INVALID_ROUND_INDEX` | 日記回覆的 `round_index` 不是 1～4 的整數（F7） | 修正前端送出的值 |
| 409 | `ROUND_ALREADY_ANSWERED` | 日記這一輪已經回答過（F7） | 視為這一輪已成功，重新取得日記狀態 |

錯誤回應的格式（遊戲與使用者相關端點）：

```json
{
  "success": false,
  "data": null,
  "error": { "code": "FORBIDDEN", "message": "這場遊戲不屬於目前的使用者" }
}
```

> 注意：`diary` 相關端點的錯誤格式是 `{"error": {"code", "message"}}`，**沒有** `success` 與 `data` 欄位（這是既有的不一致，之後會統一，見第 3 節）。前端請先看 `error.code` 即可，兩種格式都適用。

### 1.3 Flutter 範例（攔截器）

```dart
dio.interceptors.add(InterceptorsWrapper(
  onRequest: (options, handler) {
    final token = tokenStorage.accessToken;
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  },
  onError: (error, handler) {
    final status = error.response?.statusCode;
    final code = error.response?.data?['error']?['code'];
    if (status == 401 && code == 'NOT_AUTHENTICATED') {
      // 用 refresh token 換新 access token 後重送；失敗則導回登入頁
    } else if (status == 429) {
      final wait = error.response?.headers.value('retry-after'); // 秒
      // 顯示「操作太頻繁，請稍後再試」
    }
    handler.next(error);
  },
));
```

---

## 2. 各項說明

基底網址：`/api/`。

### F1 — 遊戲 API 不再借用第一位使用者

**問題**：為了讓前端「還沒串登入」也能測試，後端有一段開發用捷徑：請求沒帶 JWT 時，自動當成「資料庫第一位使用者」。任何人不用登入就能用那位使用者的身分開始遊戲、寫入成績；前端漏帶 token 也不會有錯誤，資料卻默默寫進別人的帳號。

**修改**：`get_current_user()` 未登入時回傳 `None`，不再取第一位使用者。

**行為對照**

| | 修改前 | 修改後 |
|---|---|---|
| 有帶有效 JWT | 用登入者身分 | 用登入者身分（不變） |
| 沒帶 JWT，DB 有使用者 | 偷用第一位使用者，**請求成功** | **回錯誤** |
| JWT 無效或過期 | 401 `NOT_AUTHENTICATED` | 不變 |

**未登入時的新回應**（基底 `games/`）

| 方法 | 路徑 | 回應 |
|---|---|---|
| POST | `fridge-check/sessions/`（含別名 `session/`，以及底線版 `fridge_check/...`） | 404 `USER_NOT_FOUND` |
| GET | `fridge-check/history/` | 404 `USER_NOT_FOUND` |
| POST | `market-shopping/sessions/` | 404 `USER_NOT_FOUND` |
| GET | `market-shopping/history/` | 404 `USER_NOT_FOUND` |
| POST | `market-route/start/` | 404 `USER_NOT_FOUND` |
| POST | `memory-recall/start/` | 404 `USER_NOT_FOUND` |
| GET／POST | `market-route/round/`、`round/answer/`、`finish/`、`result/<session_id>/` | `session_id` 不存在 → 404 `SESSION_NOT_FOUND`；存在 → 403 `FORBIDDEN` |
| GET／POST | `memory-recall/round/`、`round/answer/`、`finish/`、`result/<session_id>/` | 同上 |

**前端要做**：所有遊戲請求都帶 token。本機測試遊戲時請先登入取得 token：

```bash
curl -X POST https://<後端網址>/api/users/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "<帳號>", "password": "<密碼>"}'
# 回傳 {"access": "...", "refresh": "..."}

curl -X POST https://<後端網址>/api/games/fridge-check/sessions/ \
  -H "Authorization: Bearer <access>"
```

**檔案**：`games/utils.py`、`games/tests_utils.py`、`games/tests_anonymous.py`（新）

---

### F2 — 冰箱檢查、市場買菜的作答端點檢查擁有者

**問題**：這些端點只用網址上的 `session_id` 找 session，不確認它屬於誰。知道（或猜到）別人的 `session_id` 就能替對方作答、改掉對方成績。

**修改**：新增共用函式 `forbidden_unless_owner()`，作答端點在找到 session 後呼叫它。

**受影響端點**

| 方法 | 路徑 |
|---|---|
| POST | `games/fridge-check/sessions/<session_id>/answers/`（含 `answer`、`session` 單數別名與底線版） |
| POST | `games/market-shopping/sessions/<session_id>/item-answers/` |
| POST | `games/market-shopping/sessions/<session_id>/change-answers/` |

**判斷順序**：欄位格式 → 找 session → 檢查擁有者 → 是否已結束 → 判題

| 情況 | HTTP | `error.code` |
|---|---|---|
| 請求內容格式錯誤 | 400 | 與以前相同（`INVALID_ANSWER` 等） |
| `session_id` 不存在 | 404 | `SESSION_NOT_FOUND`（不變） |
| **session 是別人的，或沒帶 token** | **403** | **`FORBIDDEN`**（新增） |
| 自己的 session，但已結束 | 400 | `SESSION_COMPLETED`（不變） |
| 自己的 session，正常作答 | 200 | — |

被擋下時，後端**不會**寫入任何作答紀錄，也不會改變 session 狀態。

**前端要做**：作答請求要帶「建立（開始）這場遊戲的同一個帳號」的 token。**登出換帳號時，清掉先前的 `session_id`**，否則舊帳號開的遊戲用新帳號作答會收到 403。

**檔案**：`games/utils.py`、`games/fridge_check/views.py`、`games/market_shopping/views.py`、`games/tests_session_owner.py`（新）

---

### F3 — market_sort（市場分類）檢查擁有者

**問題**：`market_sort` 本來就要求登入，但後端用「`client_session_id`（前端自己產生）」找 session 時完全不看是誰。別的使用者送出相同的 id：
- 對方的場次**已完成** → 會拿到**對方的成績**（資料外洩）
- 對方的場次**還沒結束** → 會用自己的資料計分並**覆蓋**對方的 session

**修改**：`get_or_create_session` 找到屬於別人的 session 時丟出 `SessionOwnerMismatch`（不回傳、不修改）；`market_sort` 接住並回 403。

**受影響端點**：`POST games/market-sort/submit/`（body 的 `session_id`）

| 情況 | HTTP | `error.code` |
|---|---|---|
| 自己的新 `session_id` 或重送自己的 | 201 | —（重送回相同結果，冪等） |
| `session_id` 已被**別的帳號**用過 | **403** | **`FORBIDDEN`** |

**前端要做**
- `session_id` **請用 UUID**。同一款遊戲內全站唯一，如果不同使用者剛好用到同一個簡單的值（例如 `test_1`），後來的人會一直收到 403。
- 換帳號登入時不要沿用舊的 `session_id`。

**檔案**：`games/session_service.py`、`games/market_sort/views.py`、`games/market_sort/tests_owner.py`（新）

---

### F4 — 忘記密碼 API 加入次數限制

**問題**：`password-reset/check/` 與 `password-reset/` 是公開的，沒有任何次數限制，可被無限次嘗試或大量掃描帳號。

**修改**：新增兩層限制，超過就回 429（兩支 API 共用計數，所以「確認帳號再重設」一輪算 2 次）：

| 限制 | 次數 | 說明 |
|---|---|---|
| 同一個帳號名稱 | 每小時 10 次 | 主要防線；帳號名稱會去除空白、忽略大小寫 |
| 同一個來源（IP） | 每小時 30 次 | 擋同一來源掃很多帳號 |

**受影響端點**：`POST users/password-reset/check/`、`POST users/password-reset/`

```json
{
  "success": false,
  "data": null,
  "error": { "code": "TOO_MANY_REQUESTS", "message": "操作太頻繁了，請稍後再試" }
}
```

HTTP 429，標頭 `Retry-After: <秒數>`。沒帶 `username` 時仍是 400 `VALIDATION_ERROR`（不計入次數）。

**前端要做**：處理 429，顯示等待提示。一般使用者不會碰到上限（約 5 輪完整流程／小時）。

**⚠️ 這一項「沒有」解決的事**：只做了次數限制，**沒有新增身分驗證**。知道帳號名稱的人，仍然能在限制內重設該帳號的密碼。建議下一步加上「註冊時的生日＋手機號碼」當第二驗證因素（不需新服務、不改資料庫）。另外，「帳號不存在」仍回 404 `ACCOUNT_NOT_FOUND`（註冊的 `USERNAME_TAKEN` 同樣能探測帳號，且改掉會讓輸錯帳號的長者得不到提示）。

**檔案**：`users/throttles.py`（新）、`users/views.py`、`users/tests/test_password_reset_throttle.py`（新）

---

### F5 — 日記照片與錄音不再公開

**問題**：上傳日記照片與語音後會呼叫 `make_public()`，網址永久有效、任何人拿到就能看。日記是長者的私人內容。

**修改**
- 上傳預設保持**私有**，資料庫存「檔案路徑」（例如 `voice-diary/images/3f2a....jpg`）
- 回傳給前端時才換成 **v4 簽名網址**，預設 **6 小時**有效，過期後網址失效
- 舊資料（`http(s)://` 開頭的完整網址）和示範資料**原樣回傳**，不受影響
- 簽名失敗時該欄位回 `null`（並記錄錯誤），不讓整支 API 掛掉
- **頭像維持公開網址**（行為不變）

**網址有簽名的欄位**

| 端點 | 欄位 |
|---|---|
| `GET／POST diary/`（月曆、上傳照片） | `photo_url` |
| `GET diary/<id>/` | `photo_url`、`replies[].audio_url` |
| `POST diary/<id>/replies/` | `audio_url` |
| `POST diary/<id>/finalize/` | `photo_url` |
| `GET diary/review/` | `yesterday[]`、`last_year[]` 裡的 `photo_url`、`audio_url` |
| 社群貼文（`social/posts/`、貼文詳情、`POST diary/<id>/share/`） | `photo_url` |
| 公開分享頁 `GET /share/<share_token>/` | 頁面上的圖片網址 |
| `GET dashboard/weekly-report/` | `diary.entries[].photo_url` |

**前端要做**
1. **不要把 `photo_url` / `audio_url` 當成永久連結存起來**。過期後重新呼叫 API 取得新的。
2. 每次取得的網址都不同（含簽名）。圖片快取如果用完整網址當 key，會被當成新圖片重複下載；**建議用 `diary_id` 當快取 key**。
3. 欄位可能是 `null`：準備預設圖，錄音播放鈕要能隱藏。
4. 6 小時內有效：畫面開著超過 6 小時不重新整理，圖片會載入失敗，載入失敗時請重新抓一次資料。

**⚠️ 尚未處理**：**既有的檔案仍然是公開的**。之前上傳的檔案已經被設成公開，資料庫存的完整網址仍可被任何人開啟。需要另外寫一次性腳本把舊檔案改回私有並轉成路徑（會動到線上資料，要先備份與確認）。

**其他細節**：週報會把內容存成快照，快照存的是**路徑**，回傳 API 時才換成簽名網址（簽名網址有時效，不能存進快照）。

**檔案**：`diary/media.py`（新）、`diary/external.py`、`diary/views.py`、`social/utils.py`、`public_share/views.py`、`dashboard/weekly_report.py`、`dashboard/views.py`、`users/views.py`、`diary/tests_media.py`（新）

---

### F6 — 刪除帳號時一併清除檔案

**問題**：`DELETE users/me/` 只刪資料庫（含級聯的日記、貼文），Firebase Storage 裡的日記照片、錄音、頭像都留著。而且舊檔案是公開網址，帳號刪掉後別人仍然看得到。

**修改**
- 刪除前先收集這個人的所有檔案：頭像、日記照片、日記錄音、回覆錄音、貼文照片
- 資料庫刪除成功**之後**才刪檔案（`transaction.on_commit`）
- 認得兩種 Firebase 網址格式（`storage.googleapis.com`、`firebasestorage.googleapis.com`）與路徑；**別人網站的網址、示範資料、本機路徑不會被誤刪**
- 本機 `media/` 的頭像一併刪除
- 檔案刪除失敗**不會**擋住帳號刪除（只記錄錯誤）

**受影響端點**：`DELETE users/me/`（body：`{"password": "..."}`）

| 情況 | 回應 |
|---|---|
| 密碼正確 | 204，帳號與檔案刪除 |
| 密碼錯誤 | 400 `VALIDATION_ERROR`，**什麼都不刪** |
| 雲端刪除失敗 | 仍然 204，帳號照常刪除 |

**前端要做**：不用改。刪除成功後建議清掉本機的 token 與快取，並導回登入頁。

**已知限制**：檔案是同步逐一刪除，檔案很多的帳號回應會比較慢；刪除失敗不會重試。頭像「更換」或「移除」時舊檔案不會被刪（不在這一項範圍）。

**檔案**：`diary/external.py`、`users/views.py`、`users/tests/test_delete_account_files.py`（新）

---

### F7 — 回覆日記：驗證 `round_index` 並加上 transaction

**問題**
- `POST diary/<id>/replies/` 直接 `int(round_index)`：傳 `"abc"`、`"1.5"` 或超大數字會 **500**
- 同一輪重複送出會撞到唯一限制，也是 **500**（例如網路重試）
- 新增回覆與更新日記狀態不在同一個 transaction，中途失敗會留下半完成資料
- `POST diary/<id>/finalize/` 同時送兩次會重複分析、重複呼叫 AI；AI 失敗還會留下「有分析結果、日記卻停在處理中」

**修改**
- `round_index` 只接受 **1～4 的整數**（`"1"` 字串與 `1` 整數都可）
- 重複的輪次在語音辨識與上傳**之前**就擋下，不白做
- 寫入資料庫的部分放進 transaction 並鎖住該篇日記；鎖內再檢查一次（被別的請求搶先、或日記剛完成），失敗時回錯誤並**刪除剛上傳的錄音**
- finalize 整段放進 transaction：失敗全部還原；同時來的第二個請求等第一個完成後直接回 200，不重複呼叫 AI

**`POST diary/<id>/replies/`**（multipart：`audio`、`round_index`）

| 情況 | HTTP | `error.code` |
|---|---|---|
| 缺少 `audio`，或沒帶 `round_index` | 400 | `INVALID_AUDIO`（不變） |
| `round_index` 不是 1～4 的整數（`"abc"`、`"1.5"`、`0`、`-1`、`5`、超大數字） | 400 | **`INVALID_ROUND_INDEX`**（原本是 500） |
| 這一輪已經回答過 | **409** | **`ROUND_ALREADY_ANSWERED`**（原本是 500） |
| 日記已完成 | 400 | `DIARY_ALREADY_FINALIZED`（不變） |
| 語音辨識／上傳失敗 | 500 | `TRANSCRIPTION_FAILED`／`UPLOAD_FAILED`（不變） |
| 成功 | 201 | — |

**`POST diary/<id>/finalize/`**：行為不變——第一次完成回 201，已完成再送回 200。差別是同時送兩次也只會呼叫一次 AI。

**前端要做**
- 收到 **409 `ROUND_ALREADY_ANSWERED`**：通常是網路重試造成，代表這一輪**已經成功**。用 `GET diary/<id>/` 同步狀態（`replies`、`pending_question`），不要顯示錯誤。
- 收到 **400 `INVALID_ROUND_INDEX`**：前端送出的值有誤，檢查 `round_index` 是 1～4。
- 錯誤格式沒有 `success` 欄位，請看 `error.code`。

**備註**：資料庫鎖定（`select_for_update`）只在 PostgreSQL 生效，測試用的 SQLite 會忽略它；建議在測試環境用兩個並行請求再驗證一次。

**檔案**：`diary/views.py`、`diary/tests_reply_validation.py`（新）

---

## 3. 還沒做的事（前端可以先知道方向）

> 以下**尚未實作**，只是方向，上線前會再更新本文件。請勿現在就照這節改程式。

### 屬於這一輪（`fix/features`）但還沒完成
- **忘記密碼的身分驗證**（F4 的後續）：預計加「生日＋手機號碼」。上線時前端要在重設密碼流程加兩個輸入欄位。
- **舊的公開檔案改成私有**（F5 的後續）：一次性腳本，前端無感，但舊網址會失效。

### 屬於共通問題（`fix/global` 分支，規劃中）
| 項目 | 前端影響 |
|---|---|
| 預設所有 API 都需要登入，只有註冊、登入、token 刷新、忘記密碼、分享頁等公開 | 除公開端點外，每個請求都要帶 token |
| 登入、註冊、改密碼加入次數限制 | 會有 429，同 F4 |
| 縮短 access token 有效期、refresh token 輪替、改密碼後舊 token 失效 | 必須實作「過期 → 用 refresh 換新 → 重送」；若啟用輪替，refresh 時要存新的 refresh token |
| 統一回應格式 `{ success, data, error }`（日記、社群、首頁、部分使用者端點目前不一致） | 建議現在就把解析回應集中在一處，並相容有／沒有 `success` 欄位兩種格式。登入、註冊的格式改動影響最大，會先和前端確認 |
| 遊戲完成時間改用台灣時間日期 | `played_date` 等日期在台灣 00:00–08:00 不再少一天 |

---

## 4. 後端維運注意（給部署與後端同學）

- **次數限制的計數存在 Django cache**。目前沒有設定 `CACHES`，用的是單一 process 的記憶體快取；多個 worker 時各自計數，實際上限會變寬鬆。正式環境請改用共用快取（例如 Redis）。
- **簽名網址需要 Firebase 金鑰有簽名權限**（目前的 `secrets/firebase-key.json` 具備）。有效秒數可在 settings 加 `MEDIA_SIGNED_URL_SECONDS` 覆蓋，預設 21600（6 小時）。
- **被鎖住的是帳號名稱**（F4）：知道對方帳號的人可以故意把它鎖一小時。這是次數限制的取捨。
- **同步刪除檔案**（F6）：檔案很多的帳號，刪除請求會比較久；之後可改成背景處理。
- **資料庫鎖**（F7）需要 PostgreSQL 才有實際效果。

---

## 5. 附錄：PR 與 commit 對照

| 編號 | PR | commit 標題 |
|---|---|---|
| F1 | #87 | `fix(games)!: 移除未登入時改用第一位使用者的 fallback` |
| F2 | #88 | `fix(games): 遊戲作答前檢查 session 擁有者` |
| F3 | #89 | `fix(games): market_sort 比對 session 擁有者，避免讀取或覆蓋他人場次` |
| F4 | #90 | `fix(users): 忘記密碼 API 加入請求次數限制` |
| F5 | #91 | `fix(diary): 日記照片與錄音改用簽名網址，不再公開` |
| F6 | #92 | `fix(users): 刪除帳號時一併清除雲端與本機檔案` |
| F7 | #93 | `fix(diary): 回覆日記驗證 round_index，寫入改用 transaction` |

> 只有 F1 的 commit 有 `!`（破壞性變更）。F2～F7 對「正常使用」的前端流程不造成破壞，但上面第 1.1 節列的項目仍需要確認。

新增的測試檔：`games/tests_anonymous.py`、`games/tests_session_owner.py`、`games/market_sort/tests_owner.py`、`users/tests/test_password_reset_throttle.py`、`diary/tests_media.py`、`users/tests/test_delete_account_files.py`、`diary/tests_reply_validation.py`。
