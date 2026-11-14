# 後端安全與穩定性修正總覽（F1～F14、G1、G3、G4、G9、日記上傳限制）

更新日期：2026-11-14 · 範圍：`fix/features`（個別功能問題，F1～F14）與 `fix/global`（共通問題：G1、G3、G4、G9、日記上傳限制），都已合併

這份文件說明這一輪後端修正**改了什麼、為什麼改、前端要配合什麼**。給前端（Flutter）看，也可以當後端的修改紀錄。

> 重點先看第 1 節的「前端待辦」與「錯誤碼總表」。想知道某一項的來龍去脈，再看第 2 節對應的小節。
>
> **F8～F13 對前端幾乎沒有影響**（API 的格式與欄位都沒變），只有 F11（日期值）與 F13（AI 文字可能改成固定句型）值得知道。看 [F8～F13 一覽](#f8f13-給前端的總結)即可。
>
> **G3（`fix/global`）：登入、註冊、改密碼、刪帳號也有次數限制了**，超過會回 429，見 [G3](#g3--登入註冊改密碼刪帳號的次數限制fixglobal)。
>
> **G4（`fix/global`）：改密碼後舊的登入 token 會失效**，部署後所有人要重新登入一次，見 [G4](#g4--改密碼或重設密碼後舊的登入-token-失效fixglobal)。
>
> **F14 是新功能「點數與成就」（rewards）**，有 3 支新 API，而且 10 支既有 API 的回應多了一個 `rewards` 區塊，另外遊戲名稱與日記回應格式也有變動，前端要改。看 [F14](#f14--點數與成就rewards)。

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
| F8 | 遊戲歷史紀錄載入全站場次、查詢過多（慢） | 中 | 不用（回應不變） | [#97](https://github.com/LightMemory-Team/LightMemory-Backend/pull/97) |
| F9 | 儀表板重複掃描全站日記（慢） | 中 | 不用（回應不變） | [#98](https://github.com/LightMemory-Team/LightMemory-Backend/pull/98) |
| F10 | 週報每次點開都呼叫 AI 並寫資料庫 | 中 | 不用（第二次之後變快） | [#100](https://github.com/LightMemory-Team/LightMemory-Backend/pull/100)、[#101](https://github.com/LightMemory-Team/LightMemory-Backend/pull/101) |
| F11 | 台灣凌晨的日期用 UTC 算，少一天 | 低 | 👀 `played_date`、`joined_at` 值變正確，不要自己再轉 | [#99](https://github.com/LightMemory-Team/LightMemory-Backend/pull/99) |
| F12 | 移除後台的失智篩檢與警示等級模型 | 中 | 不用（從沒有對外 API） | [#102](https://github.com/LightMemory-Team/LightMemory-Backend/pull/102) |
| F13 | 日記 AI 輸出沒有用語檢查與驗證 | 高 | 👀 AI 文字可能是固定句型；欄位長度有上限 | [#96](https://github.com/LightMemory-Team/LightMemory-Backend/pull/96) |
| F14 | 點數與成就（rewards）納入，與 F1～F13 整合 | 新功能 | ⚠️ 3 支新 API、`rewards` 區塊、遊戲名稱、錯誤格式 | [#106](https://github.com/LightMemory-Team/LightMemory-Backend/pull/106)、[#107](https://github.com/LightMemory-Team/LightMemory-Backend/pull/107)（rewards 本體）、[#108](https://github.com/LightMemory-Team/LightMemory-Backend/pull/108)（合併） |
| G1 | `SECRET_KEY`、`DEBUG`、CORS 寫死在程式碼 | 高 | 👀 Flutter Web 的網址要由後端列進 CORS 白名單；手機 App 不受影響；部署後舊 token 失效，要重新登入 | [#109](https://github.com/LightMemory-Team/LightMemory-Backend/pull/109)、[#110](https://github.com/LightMemory-Team/LightMemory-Backend/pull/110) |
| G3 | 登入、註冊、改密碼、刪帳號沒有次數限制 | 高 | ⚠️ 要處理 429 | [#110](https://github.com/LightMemory-Team/LightMemory-Backend/pull/110) |
| G4 | 改密碼後舊的登入 token 還能用最久 30 天 | 高 | ⚠️ 換 token／API 回 401 要導回登入頁；改密碼成功後要換掉本機 token | [#112](https://github.com/LightMemory-Team/LightMemory-Backend/pull/112) |
| G9 | OpenAI 沒設 timeout，AI 一卡住請求就卡住 | 中 | 不用（超時沿用原本的固定內容） | [#111](https://github.com/LightMemory-Team/LightMemory-Backend/pull/111) |
| 上傳限制 | 日記照片、錄音沒有大小與類型限制 | 中 | ⚠️ 新錯誤碼 `IMAGE_TOO_LARGE`、`AUDIO_TOO_LARGE`；Flutter Web 照片要帶 `contentType` | [#113](https://github.com/LightMemory-Team/LightMemory-Backend/pull/113) |

- 測試：原本 764 個，現在 **982 個全部通過**（另有 1 個原本就預期失敗），新增 218 個測試。
- F1～F11、F13 **沒有修改資料表**；F12 刪除了兩張沒在用的資料表，F14 新增 `rewards` 的兩張資料表（後端部署時要跑 migration，前端無感）。
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
- [ ] 收到 `401` 時，清掉本機 token 並導回登入頁，不要無限重試（G4：改密碼後舊 token 會 401；換 token 的端點也會 401）。若日後前端有存 refresh token，才改成「先用 refresh token 換新、重送，失敗再導回登入頁」
- [ ] （G4）修改密碼成功後，用回應的 `data.access`、`data.refresh` 換掉本機舊 token（目前前端沒有改密碼功能，之後做才需要）
- [ ] （上傳限制）日記照片超過 10MB、錄音超過 25MB 會回 400 `IMAGE_TOO_LARGE`／`AUDIO_TOO_LARGE`，直接顯示 `error.message`；Flutter Web 送照片要帶 `contentType`
- [ ] 以 `error.code` 判斷錯誤，**不要比對 `error.message` 文字**
- [ ] （F11）冰箱檢查歷史的 `played_date`、會員統計的 `joined_at` **直接顯示後端給的日期**，不要自己再用 `completed_at` 去切字串或換算（F11）
- [ ] （F13）日記的 AI 問題、回應不要假設每次都不同；AI 不合格時會是固定句型（F13）
- [ ] （F14）遊戲結算、儀表板、週報、日記完成、日記分享的回應都要讀 `data.rewards`，有點數或新成就時跳出提示；`rewards.error` 不是 `null` 時溫和提示即可，不要當成請求失敗（F14）
- [ ] （F14）新增「點數總覽」「成就牆」「點數紀錄」三個畫面所需的 API 串接（F14）
- [ ] （F14）遊戲名稱改版：**不要在前端寫死遊戲名稱**，用後端給的 `name`／`title`（F14）
- [ ] （G3）**登入、註冊、修改密碼、刪除帳號**都要處理 **429**，顯示「操作太頻繁了，請稍後再試」，可讀 `Retry-After`（秒）。登入被鎖時**即使密碼正確也不能登入**，要提示等待（G3）
- [ ] （G4）**換 token 失敗（401）就導回登入頁，不要一直重試**；**修改密碼成功後，用回應裡的新 `access`／`refresh` 換掉本機儲存的舊 token**；部署後使用者要重新登入一次（G4）
- [ ] （F14）日記完成（`finalize`）、分享（`share`）以及回覆日記（`replies`）的錯誤回應現在有 `success: false`，用 `error.code` 判斷的話不用改（F14）

### 1.2 錯誤碼總表（這一輪新增或變更的）

| HTTP | `error.code` | 何時出現 | 建議處理 |
|---|---|---|---|
| 401 | `NOT_AUTHENTICATED` | token 過期、無效，或密碼改過後的舊 token（G4）。換 token 的端點 `login/refresh/` 也會回 401 | 清掉本機 token，導回登入頁（有存 refresh token 才先嘗試換新） |
| 400 | `IMAGE_TOO_LARGE`、`AUDIO_TOO_LARGE` | 日記照片超過 10MB、錄音超過 25MB（上傳限制） | 直接顯示 `error.message` |
| 404 | `USER_NOT_FOUND` | 遊戲開場／歷史端點**沒帶 token**（F1） | 視為 bug：檢查是否漏帶標頭；使用者端導回登入頁 |
| 403 | `FORBIDDEN` | 這場遊戲不屬於目前登入的人，或沒帶 token（F1、F2、F3） | 不要重試；回首頁或重新開始一場 |
| 404 | `SESSION_NOT_FOUND` | `session_id` 不存在（本來就有） | 重新開始一場 |
| 429 | `TOO_MANY_REQUESTS` | 忘記密碼（F4）、登入失敗太多次、註冊太頻繁、改密碼／刪帳號輸入密碼太頻繁（G3） | 顯示等待提示，依 `Retry-After`（秒）後再試 |
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

> 注意：日記的**錯誤**回應已統一成 `{success: false, data: null, error}`（F7、F14），**只有「上傳照片」`POST /api/diary/` 這一支**還是舊格式 `{"error": {"code", "message"}}`（沒有 `success`、`data`）。日記的成功回應有些也還沒統一（有的只有 `data`）。前端請看 `error.code` 判斷，兩種格式都適用。

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
      // 清掉本機 token 並導回登入頁（若有存 refresh token，可先換新再重送）
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

**檔案**：`games/utils.py`、`games/tests/test_utils.py`、`games/tests/test_anonymous.py`（新）

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

**檔案**：`games/utils.py`、`games/fridge_check/views.py`、`games/market_shopping/views.py`、`games/tests/test_session_owner.py`（新）

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

**檔案**：`games/session_service.py`、`games/market_sort/views.py`、`games/market_sort/tests/test_owner.py`（新）

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

**檔案**：`diary/media.py`（新）、`diary/external.py`、`diary/views.py`、`social/utils.py`、`public_share/views.py`、`dashboard/weekly_report.py`、`dashboard/views.py`、`users/views.py`、`diary/tests/test_media.py`（新）

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
- 錯誤格式是 `{ success: false, data: null, error: { code, message } }`（F14 起統一；原本沒有 `success` 欄位），一樣看 `error.code` 判斷。

**備註**：資料庫鎖定（`select_for_update`）只在 PostgreSQL 生效，測試用的 SQLite 會忽略它；建議在測試環境用兩個並行請求再驗證一次。

**檔案**：`diary/views.py`、`diary/tests/test_reply_validation.py`（新）

---

### F8～F13 給前端的總結

這六項是效能、時區、資料清理與內容安全，**API 路徑、欄位、錯誤碼都沒有變**。逐項說明：

#### F8 — 遊戲歷史紀錄變快（#97）

- 影響的端點：`fridge-check/history/`、`market-shopping/history/`，以及 `market-sort/submit/` 回應裡附的歷史。
- 原本會把全站所有人的場次都讀進來再挑自己的，現在資料庫直接只取自己的。**回應內容與格式完全不變**。
- 前端：不用改。

#### F9 — 儀表板變快（#98）

- 影響的端點：`GET /api/dashboard/`、`GET /api/dashboard/weekly-report/`。
- 一次請求內重複計算的「日記語言 z」現在只算一次，**數值與以前完全相同**。
- 前端：不用改。

#### F10 — 週報重複點開不再重複呼叫 AI（#100、#101）

- 影響的端點：`GET /api/dashboard/weekly-report/`。
- 同一週重複點開，只要週報的事實沒變，就**沿用上次的 AI 總結**，不會每次都換一句話，也不會每次都寫資料庫；第二次之後回應更快。事實變了（多玩了幾天…）才會重新產生總結。
- 如果上次 AI 失敗、顯示的是固定句型，**下次點開會自動重試**。
- `GET` 的回應內容與格式不變；快照裡的內部欄位不會出現在回應。
- 前端：不用改。首次點開仍會記一次 `viewed_at`（首頁「看看上週回顧」任務依此判斷完成），這個行為沒變。

#### F11 — 日期改用台灣時間（#99）👀

資料庫存 UTC（台灣是 UTC+8），以前直接切 UTC 日期，台灣 **00:00～08:00** 發生的事會少一天。現在後端先換成台灣日期：

| 欄位 | 端點 | 變化 |
|---|---|---|
| `played_date` | 冰箱檢查歷史 | 台灣凌晨玩的場次，日期比以前多一天（變成正確的台灣日期） |
| `joined_at` | 會員統計 | 凌晨註冊的人，加入日期比以前多一天 |
| 生日驗證 | 註冊、更新個人資料 | 「不能選未來日期」改以台灣的今天為準 |

- `completed_at`、`played_at` 等完整時間字串**原樣不變**（仍是 UTC 的 ISO 字串，例如 `2026-11-09T17:30:00+00:00`）。
- 前端：`played_date`、`joined_at` **直接顯示**。如果前端自己曾經從 `completed_at` 切前 10 個字當日期，請改用後端給的 `played_date`，或把完整時間字串轉成裝置的本地時間再取日期。
- `market_shopping`、`market_sort`、`memory_recall` 後端不取日期，前端用完整時間字串，不受影響。

#### F12 — 移除診斷性模型（#102）

- 移除了兩個**沒有任何 API** 的後台模型（失智篩檢量表 AD-8、健康儀表板的腦年齡與警示等級）。
- 前端：完全無感。順帶一提，App 內也不應出現這類字眼，這是產品定位（輔助維持認知活躍度，不做診斷）。

#### F13 — 日記 AI 內容加上用語檢查與驗證（#96）👀

影響日記的三個 AI 產出：首問、追問、完成日記內容（`DiaryFinalizeView`）；以及週報總結、首頁問候語。

| 項目 | 規則 |
|---|---|
| 首問、追問 | 空白或含醫療／負面／專有名詞（例如「診斷」「風險」「退化」「分數」）→ 改成固定句型：首問 `這張照片是在哪裡拍的呢？`、追問 `還有什麼想跟我分享的嗎？` |
| 完成日記的 `title`、`ai_response`、`post_text`、`invite_text` | 某一欄含禁用詞或不是字串 → **只有那一欄**改用預設值，其他欄保留 |
| `title` | 最多 **50** 字（超過會被截短） |
| `invite_text` | 最多 **100** 字（超過會被截短） |
| `category` | 只會是這六種之一：`food`、`clothing`、`housing`、`transport`、`education`、`entertainment`；其他值改用預設 |
| `hashtags`、`suggested_replies` | 過濾掉含禁用詞或空白的項目，**最多 5 個**；全被濾掉就用預設 |

- 前端：欄位與回應格式不變。需要知道的是 AI 的文字**有時會是固定句型**（和 AI 服務失敗時一樣），文字顯示區請不要假設每次都不同；`title` 的 UI 可以預期 ≤ 50 字、`invite_text` ≤ 100 字。
- **不會**檢查長者自己說的話（錄音轉文字、預設標題取自長者原話）。

---

### F14 — 點數與成就（rewards）

> 新功能：完成遊戲、寫日記、做今日任務可以拿點數，達成條件會解鎖成就。後端已經串好，**前端要把畫面接上**。所有 rewards 相關 API 都要登入（`Authorization: Bearer <access_token>`）。

#### 1. 三支新 API

| 方法與路徑 | 用途 |
|---|---|
| `GET /api/rewards/summary/` | 點數總覽（首頁、會員中心） |
| `GET /api/rewards/achievements/` | 成就牆（三類分組、是否解鎖、進度） |
| `GET /api/rewards/points/history/?page=1&page_size=10` | 點數紀錄（新的在前，分頁；`page_size` 預設 10、最多 50） |

**`summary/`**

```json
{ "success": true, "data": {
    "total_points": 135,
    "today_points": 35,
    "daily_cap": 100,
    "daily_remaining": 65,
    "achievements_unlocked": 3,
    "achievements_total": 25
}, "error": null }
```

**`achievements/`**：`data.categories` 是三組（`exploration` 探索類、`training` 訓練類、`milestone` 里程碑類），每組有 `label` 與 `achievements`：

```json
{ "code": "first_diary", "title": "說說我的故事", "description": "完成第一篇聲影日記",
  "unlocked": true, "unlocked_at": "2026-11-14T10:30:00+08:00",
  "progress": { "current": 1, "target": 1 },
  "points": 10, "icon": "first_diary" }
```

未解鎖的成就 `unlocked_at` 是 `null`，`progress.current` 是目前進度（不會超過 `target`）。`icon` 的值同 `code`，第一版所有成就共用同一組勳章圖案，前端依 `unlocked` 決定彩色或灰色。

**`points/history/`**：`data.items` 每筆 `{ id, reason, label, amount, created_at }`，`data.pagination` 有 `count`、`next`、`previous`（完整網址或 `null`）。`reason` 有 `game_complete`、`diary_complete`、`daily_task`、`all_tasks_done`、`achievement_unlock`。**`amount` 為 0 的紀錄（達每日上限時留下的）不會出現。** `page` 不是整數回 400 `INVALID_PARAM`；超過最後一頁回空的 `items`。

#### 2. 10 支既有 API 的回應多了 `data.rewards`

| API | 什麼時候帶 `rewards` |
|---|---|
| `POST /api/games/fridge-check/sessions/{id}/answers/` | **只有最後一題**（`is_completed` 為 `true`）；中間的題目沒有這個欄位 |
| `POST /api/games/market-shopping/sessions/{id}/item-answers/`、`…/change-answers/` | 場次結束的那一次回應 |
| `POST /api/games/market-route/finish/` | 每次呼叫（已結束的場次重複呼叫為 0 點） |
| `POST /api/games/memory-recall/finish/` | 每次呼叫（答題逾時自動結束的場次，前端接著呼叫的第一次 `finish/` 會拿到點數） |
| `POST /api/games/market-sort/submit/` | 場次結束的回應 |
| `GET /api/dashboard/` | 每次（第一次解鎖「認識自己」） |
| `GET /api/dashboard/weekly-report/` | 每次（第一次解鎖「回頭看看」，並完成「看看上週回顧」任務） |
| `POST /api/diary/{id}/finalize/` | 日記完成時（已完成的日記再呼叫為 0 點） |
| `POST /api/diary/{id}/share/` | 每次（第一次分享解鎖「樂於分享」） |

`rewards` 區塊的格式（每次都一樣）：

```json
{
  "points_earned": 15,
  "breakdown": [
    { "reason": "diary_complete", "label": "完成一篇聲影日記", "points": 15 },
    { "reason": "daily_task", "label": "完成今日任務：聲影日記", "points": 5 }
  ],
  "daily_cap_reached": false,
  "total_points": 135,
  "new_achievements": [
    { "code": "first_diary", "category": "exploration", "title": "說說我的故事",
      "description": "完成第一篇聲影日記", "points": 10, "icon": "first_diary" }
  ],
  "error": null
}
```

- `points_earned` 是這一次**新增**的點數；**重複呼叫同一件事一律是 0 點**（不會重複入帳），`breakdown`、`new_achievements` 是空的，前端不用特別處理，只要 `points_earned > 0` 或 `new_achievements` 不是空的才跳提示。
- `daily_cap_reached` 為 `true`：今天遊戲、日記、今日任務的點數已達 100 點上限（成就點數不算在上限內）。
- **`error` 不是 `null`（`{ "code": "REWARDS_FAILED", "message": "這次的點數暫時沒有算到" }`）時，原本的請求仍然成功**，只是這次沒算到點數。請溫和提示或直接忽略，**不要當成遊戲或日記失敗**。
- `rewards` **不會**存進遊戲歷史或週報快照，所以歷史端點、再次查詢單場結果不會有這個欄位。

**點數規則**：完成一場遊戲 10 點、完成一篇日記 15 點、今日任務每項 +5 點、今日任務全部完成再 +20 點；以上每天合計最多 100 點。成就是一次性的獎勵（探索類 10 點、訓練類 20 點、里程碑類 30 點），不計入每日上限。

#### 3. 首頁今日任務多了點數

`GET /api/home/daily-tasks/` 的每項任務多一個 `points`（完成這項任務額外加的點數，目前是 5），並新增 `all_done_bonus`：

```json
"all_done_bonus": { "points": 20, "earned": false }
```

`earned` 為 `true` 代表今天的「全部完成加碼」已經領過了。

#### 4. 遊戲名稱統一為 App 內的正式名稱 ⚠️

`GET /api/home/games/`（遊戲卡片）、週報、首頁今日任務標題裡的遊戲名稱（`name`／`title`）有變：

| `game_id` | 原本 | 現在 |
|---|---|---|
| `market_route` | 菜市場找路 | **來去菜市場** |
| `memory_recall` | 煮菜過程 | **記憶配對** |
| `fridge_check` | 冰箱檢查 | **冰箱清點** |
| `market_sort` | 整理菜籃（`title` 是「整理菜籃遊戲」） | **整理菜籃**（`name`、`title` 一致） |
| `market_shopping` | 市場買菜 | 市場買菜（不變） |

前端如果有把名稱寫死在畫面或判斷裡，請改用後端給的值。

#### 5. 日記回應格式統一

- `POST /api/diary/{id}/finalize/`、`POST /api/diary/{id}/share/` 的回應改為 `{ "success": true, "data": {…}, "error": null }`（原本只有 `{ "data": {…} }`）。**資料都在 `data` 裡，位置沒變**，只是多了 `success`、`error`。
- 日記相關的**錯誤**一律是 `{ "success": false, "data": null, "error": { "code", "message" } }`（含 F7 的 400 `INVALID_ROUND_INDEX`、409 `ROUND_ALREADY_ANSWERED`）。原本沒有 `success`、`data` 欄位；用 `error.code` 判斷的不用改。
- 日記的**其他成功回應**（月曆、詳情、上傳、回覆…）目前仍是 `{ "data": {…} }`，之後 `fix/global` 會再統一。

#### 6. 呼叫順序與注意事項

- 日記 `finalize`：先完成日記，**成功寫入後**才發點。就算發點失敗，日記仍然完成，回應照樣是 201，只是 `rewards.error` 有值。
- 別人的遊戲場次不能結算、不能拿點數（回 403，見 F2／F3）；沒登入也不行。
- 同一場遊戲、同一篇日記重複送出，只會入帳一次（資料庫有唯一限制）。

---

### G3 — 登入、註冊、改密碼／刪帳號的次數限制（fix/global）

以前只有忘記密碼有次數限制（F4）。現在這幾支也有，超過一律回 **HTTP 429**，格式與 F4 相同：

```json
{
  "success": false,
  "data": null,
  "error": { "code": "TOO_MANY_REQUESTS", "message": "操作太頻繁了，請稍後再試" }
}
```

標頭 `Retry-After: <秒數>`（最多 3600）。

| 端點 | 限制 | 怎麼算 |
|---|---|---|
| `POST /api/users/login/` | 同一個帳號 **10 次／小時**；同一個來源 **60 次／小時** | **只算「失敗」**（帳密錯誤、帳號不存在、帳號停用）。成功登入不算，而且會把這個帳號的失敗次數歸零。沒填帳號或密碼（400）不算 |
| `POST /api/users/register/` | 同一個來源 **30 次／小時** | 成功、失敗（例如帳號已被註冊）都算 |
| `POST /api/users/me/password/`、`DELETE /api/users/me/` | 同一位使用者合計 **10 次／小時** | 兩個動作共用同一份；查看、修改個人資料（`GET`、`PATCH /me/`）**不限制** |

**前端要做的事**
- 登入頁：一般的 `401`（帳密錯誤）照舊；收到 `429` 要顯示「操作太頻繁了，請稍後再試」，並可依 `Retry-After` 顯示還要等多久。**帳號被鎖住時，即使輸入正確的密碼也會回 429，要等到期才能登入**，請不要讓使用者誤以為密碼不對。
- 註冊頁、修改密碼、刪除帳號：同樣處理 429。
- 一般使用者不會碰到：登入只算失敗，一小時內連續打錯 10 次密碼才會被鎖。多人共用同一個網路（例如日照中心）時，來源限制是 60 次／小時，也不太會碰到。

**限制與取捨**
- 知道別人帳號名稱的人，可以故意連續輸錯 10 次把對方鎖一小時（針對帳號限制的固有取捨，F4 同樣）。
- 次數是**每個後端 process 各自計算**，正式環境若跑多個 worker，實際上限會比表中寬鬆，要換共用快取（Redis）才精準。
- `POST /api/users/login/refresh/`（換 token）沒有限制。

**檔案**：`users/throttles.py`、`users/views.py`（新增 `LoginView`）、`users/urls.py`、`config/settings.py`、`users/tests/test_auth_throttle.py`（新）

---

### G4 — 改密碼或重設密碼後，舊的登入 token 失效（fix/global）

以前換密碼之後，舊的 token 還能用最久 30 天（密碼被盜用才換的話，攻擊者仍然進得來）。現在**密碼一改，這個帳號所有舊的 token 立刻失效**。

**會發生什麼**

| 情境 | 結果 |
|---|---|
| 部署這個版本後 | **所有人的舊 token 都失效，要重新登入一次**（舊 token 沒有密碼指紋） |
| 在手機 A 修改密碼 | 手機 A **不會被登出**（修改密碼的回應有新的 token）；同一個帳號在**其他裝置會被登出** |
| 忘記密碼重設成功 | 重設前所有裝置的 token 都失效（本來就要用新密碼重新登入） |
| 修改暱稱等個人資料、在另一台裝置登入 | 不影響既有 token |

**失效的 token 會回**：`401`，`error.code` 是 `NOT_AUTHENTICATED`（和 token 過期同一種）。**換 token（`POST /api/users/login/refresh/`）也會回 401**，所以：

```
請求 → 401 → 用 refresh token 換新的 access token
                ├─ 成功 → 用新的 access token 重送
                └─ 失敗（401）→ 清掉本機 token，導回登入頁
```

**前端要做的事**
1. 換 token 回 401 時，**清掉本機 token 並導回登入頁，不要無限重試**。
2. **修改密碼成功後（`POST /api/users/me/password/`）**，回應 `data.access`、`data.refresh` 是新的 token，**一定要換掉本機儲存的舊 token**；不換的話下一個請求就會 401。
3. 部署後使用者第一次會被要求重新登入，屬於預期行為。

**限制**：沒有「登出時作廢 token」（access 仍有效 1 天、refresh 30 天）；只有「換密碼」會作廢。

**檔案**：`config/settings.py`（`CHECK_REVOKE_TOKEN`）、`users/views.py`（`RefreshView`）、`users/urls.py`、`users/tests/test_token_revoke.py`（新）

---

### 日記照片與錄音的大小、類型限制（fix/global）

以前日記上傳不檢查檔案，現在有上限；超過或類型不對會回 **400**，**不會**建立日記或寫入回覆。

| API | 規則 | 錯誤碼（`error.code`） |
|---|---|---|
| `POST /api/diary/`（照片 `photo`） | 最大 10MB；副檔名 jpg／jpeg／png／webp／heic／heif（或類型是 `image/*`） | 太大：`IMAGE_TOO_LARGE`；空檔或不是圖片：`INVALID_IMAGE` |
| `POST /api/diary/<id>/replies/`（錄音 `audio`） | 最大 25MB；webm／ogg／opus／m4a／mp4／aac／mp3／wav／flac（或類型是 `audio/*`） | 太大：`AUDIO_TOO_LARGE`；空檔或不是音訊：`INVALID_AUDIO` |

**多出來的錯誤碼只有 `IMAGE_TOO_LARGE`、`AUDIO_TOO_LARGE`**；`INVALID_IMAGE`、`INVALID_AUDIO` 原本就有，現在多了「類型不對／空檔」也會出現。`error.message` 已經是給使用者看的中文（例如「這張照片太大了（不能超過 10MB），換一張試試看吧」），可以直接顯示。

**目前的 App 不用改也能正常運作**：照片已壓縮到寬度 1600（通常不到 1MB），錄音單輪最長 3 分鐘（約 1MB）。

**要注意**
- 被擋的錄音**不會占用該輪次**，使用者重錄後同一輪還能回答。
- **Flutter Web**：照片檔名若沒有副檔名、又沒有指定 `contentType`，會被判為 `INVALID_IMAGE`。手機 App 不受影響；Web 若遇到，請在 `MultipartFile.fromBytes` 補上 `contentType: MediaType('image', 'jpeg')`。
- 照片上傳這支 API 的錯誤格式維持舊的 `{"error": {"code", "message"}}`（沒有 `success`）；錄音回覆是 `{"success": false, "data": null, "error": {...}}`。

**檔案**：`diary/upload_checks.py`（新）、`diary/views.py`、`diary/tests/test_upload_limits.py`（新）

---

## 3. 還沒做的事（前端可以先知道方向）

> 以下**尚未實作**，只是方向，上線前會再更新本文件。請勿現在就照這節改程式。

### 屬於這一輪（`fix/features`）但還沒完成
- **忘記密碼的身分驗證**（F4 的後續）：**已決定維持現狀，不做**（目前只有次數限制，重設只需要帳號名稱）。前端不用準備額外欄位。
- **舊的公開檔案改成私有**（F5 的後續）：一次性腳本，前端無感，但舊網址會失效。
- **週報改成純讀取**（F10 的後續）：目前首次點開 `GET` 仍會寫入一次（記 `viewed_at`）。之後可能新增一個「標記已讀」端點，到時前端要在看完週報時多呼叫一次。

### 屬於共通問題（`fix/global`）：這一輪**不做**

2026-11-14 決定「後端先處理嚴重問題」，以下都**沒有排程**，前端不用準備；真的要做時會先通知並更新本文件。

| 項目 | 若日後要做，前端會受到的影響 |
|---|---|
| 預設所有 API 都需要登入（G2） | 現況每個端點都已在程式裡檢查登入，沒有漏洞，只是預防；做的話只影響新端點，前端無感 |
| 縮短 access token 有效期、refresh token 輪替、登出時作廢 token（JWT blacklist） | 目前 access 有效 1 天、refresh 30 天。要縮短前，前端必須先實作「401 → 用 refresh token 換新 → 重送」並**保存 refresh token**（前端目前只存 access token），所以會**先通知前端**、排時間再改 |
| 統一回應格式 `{ success, data, error }`（日記成功回應、社群、首頁、部分使用者端點目前不一致） | 建議前端把解析回應集中在一處，並相容有／沒有 `success` 欄位兩種格式；登入、註冊的格式改動影響最大，會先和前端確認 |

---

## 4. 後端維運注意（給部署與後端同學）

- **次數限制的計數存在 Django cache**。目前沒有設定 `CACHES`，用的是單一 process 的記憶體快取；多個 worker 時各自計數，實際上限會變寬鬆。正式環境請改用共用快取（例如 Redis）。
- **簽名網址需要 Firebase 金鑰有簽名權限**（目前的 `secrets/firebase-key.json` 具備）。有效秒數可在 settings 加 `MEDIA_SIGNED_URL_SECONDS` 覆蓋，預設 21600（6 小時）。
- **被鎖住的是帳號名稱**（F4）：知道對方帳號的人可以故意把它鎖一小時。這是次數限制的取捨。
- **同步刪除檔案**（F6）：檔案很多的帳號，刪除請求會比較久；之後可改成背景處理。
- **資料庫鎖**（F7）需要 PostgreSQL 才有實際效果。
- **F14 新增 `rewards` 的 migration**（`rewards/migrations/0001_initial.py`，兩張新表），部署時要 `python manage.py migrate`。
- **F12 的 migration 會永久刪除兩張資料表**（`assessments_ad8record`、`dashboard_healthdashboardrecord`）。部署前請先查筆數並備份（本機兩張都是 0 筆，正式環境未知）；migration 可倒退，但只會重建空表。
- **測試檔路徑改了**（#103）：測試都搬進各 app 的 `tests/` 資料夾，指令例如 `python manage.py test diary.tests.test_media --settings=config.settings_test`。

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
| F13 | #96 | `fix(ai_service): 補齊禁用詞，並對日記 AI 輸出加上過濾與驗證` |
| F8 | #97 | `perf(games): 歷史紀錄改在資料庫篩選使用者的場次，消除 N+1` |
| F9 | #98 | `perf(dashboard): 日記語言 z 一次請求只掃一次全站日記` |
| F11 | #99 | `fix(games): 遊戲與會員中心的日期改用台灣時間` |
| F10 | #100、#101 | `fix(dashboard): 週報重複點開不再重複呼叫 AI 與寫資料庫` |
| F12 | #102 | `refactor(assessments): 移除未使用的 AD-8 與健康儀表板診斷性模型` |
| F14 | #106、#107、#108 | `feat(rewards): 新增點數與成就系統…`、`feat(rewards): 9 支 API 串接 grant() 並回傳 rewards`＋`feat(rewards): 合併 rewards 點數與成就系統，並與 F1～F13 整合` |

> 只有 F1 的 commit 有 `!`（破壞性變更）。F2～F13 對「正常使用」的前端流程不造成破壞，但上面第 1.1 節列的項目仍需要確認。
>
> 更詳細的技術紀錄（程式怎麼改、測試、限制）見 [fix_features_changelog.md](fix_features_changelog.md)。

新增的測試檔：`games/tests/test_anonymous.py`、`games/tests/test_session_owner.py`、`games/market_sort/tests/test_owner.py`、`users/tests/test_password_reset_throttle.py`、`diary/tests/test_media.py`、`users/tests/test_delete_account_files.py`、`diary/tests/test_reply_validation.py`。F8～F14 的測試檔見 [fix_features_changelog.md](fix_features_changelog.md) 第 8～13 章與第 15 章。
