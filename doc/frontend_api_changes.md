# 後端修正：前端需配合的變更說明

更新日期：2026-11-09 · 對應分支：`fix/games-auth-fallback`（合併目標 `fix/features`）

這份文件給 Flutter 前端閱讀，說明後端這一輪「安全與穩定性修正」中，**會改變 API 行為**的部分，以及前端需要確認或修改的地方。

> 目前只完成第 1 項（F1）。第 2 節是「預告」：已規劃、尚未實作的後端變更，列出來讓前端提早準備；實作時程與細節可能調整，**每項真正上線前會再更新這份文件**。

---

## 0. 一眼看懂

| 編號 | 變更 | 狀態 | 前端是否要改 |
|---|---|---|---|
| F1 | 遊戲 API：未登入不再被當成「資料庫第一位使用者」 | ✅ 後端已改完（待合併） | ⚠️ **要確認**：所有遊戲請求都要帶 JWT |
| 預告 | 預設所有 API 都需要登入、登入／註冊限速、忘記密碼加驗證、回應格式統一…… | ⏳ 尚未實作 | 見第 2 節 |

---

## 1. 已完成：F1 — 遊戲 API 不再借用第一位使用者

### 1.1 背景（為什麼要改）

之前為了讓前端「還沒串登入」也能測試遊戲，後端有一段開發用的捷徑：

> 如果請求**沒有帶 JWT（沒登入）**，就自動把請求當成「資料庫裡的第一位使用者」。

這在正式環境是嚴重的安全問題：

- 任何人**不用登入**就能用那位使用者的身分開始遊戲、寫入成績。
- 第一位使用者的歷史成績可以被未登入的人讀到。
- 前端如果忘記帶 token，**不會有任何錯誤**，資料卻默默寫進別人的帳號，很難發現。

現在這個捷徑已移除：**沒登入就是沒登入**，後端會明確回錯誤。

### 1.2 行為前後對照

| | 修改前 | 修改後 |
|---|---|---|
| 有帶有效 JWT | 用登入者身分 | 用登入者身分（**不變**） |
| 沒帶 JWT，DB 有使用者 | 偷用第一位使用者身分，**請求成功** | **回錯誤**（見 1.3） |
| 沒帶 JWT，DB 沒有任何使用者 | 404 `USER_NOT_FOUND` | 404 `USER_NOT_FOUND`（不變） |
| JWT 無效或過期 | 401 `NOT_AUTHENTICATED` | 401 `NOT_AUTHENTICATED`（**不變**，這是登入驗證層處理的） |

### 1.3 受影響的端點與「未登入」時的回應

基底網址：`/api/games/`。以下全部是**未帶 `Authorization` 標頭**時的新回應。

#### A. 開始一場遊戲／查歷史 → `404 USER_NOT_FOUND`

| 方法 | 路徑 | `error.message` |
|---|---|---|
| POST | `fridge-check/sessions/`（也包含別名 `fridge-check/session/`，以及底線版 `fridge_check/...`） | 找不到可使用的使用者 |
| GET | `fridge-check/history/`（同上有底線版） | 找不到可使用的使用者 |
| POST | `market-shopping/sessions/` | 查無使用者資料 |
| GET | `market-shopping/history/` | 查無使用者資料 |
| POST | `market-route/start/` | 查無使用者資料 |
| POST | `memory-recall/start/` | 查無使用者資料 |

回應範例（HTTP 404）：

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "USER_NOT_FOUND",
    "message": "查無使用者資料"
  }
}
```

> `error.code` 是固定字串，前端請用 `code` 判斷，不要用 `message` 比對文字。

#### B. 對既有 session 操作 → `404 SESSION_NOT_FOUND` 或 `403 FORBIDDEN`

這些端點需要 `session_id`。後端先找 session，再比對擁有者：

| 方法 | 路徑 |
|---|---|
| GET | `market-route/round/` |
| POST | `market-route/round/answer/` |
| POST | `market-route/finish/` |
| GET | `market-route/result/<session_id>/` |
| GET | `memory-recall/round/` |
| POST | `memory-recall/round/answer/` |
| POST | `memory-recall/finish/` |
| GET | `memory-recall/result/<session_id>/` |

未登入時：

- `session_id` 不存在 → `404`，`error.code = "SESSION_NOT_FOUND"`
- `session_id` 存在（屬於某位使用者）→ `403`，`error.code = "FORBIDDEN"`，`message = "這場遊戲不屬於目前的使用者"`

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "FORBIDDEN",
    "message": "這場遊戲不屬於目前的使用者"
  }
}
```

> 這兩種情形的處理方式相同：**請前端視為「登入狀態有問題」，導回登入或重新取得 token**。

### 1.4 沒有改變的端點（請注意！）

下列端點**這次沒有動**，所以「沒帶 token」的行為跟以前一樣（不一定會被擋）：

- `market-shopping/sessions/<session_id>/item-answers/`、`.../change-answers/`
- `fridge-check/sessions/<session_id>/answers/`（含 `answer`、`session` 單數等別名）
- `market-sort/` 底下的端點

這些端點的「檢查 session 是否屬於目前使用者」會在**下一輪修正（F2／F3）**處理。**前端不要因為它們目前沒被擋，就省略 token**，否則等下一輪上線會一次壞掉。

### 1.5 前端要做的事（請逐項確認）

1. **所有遊戲請求都要帶標頭**：

   ```
   Authorization: Bearer <access_token>
   ```

   包含上面第 1.4 節列的「目前沒被擋」的端點。

2. **檢查有沒有「沒登入也能玩」的測試流程**。之前為了測試，有些畫面可能直接呼叫遊戲 API 而沒帶 token，現在這些畫面會失敗。

3. **錯誤處理建議**：

   | 收到 | 代表 | 建議處理 |
   |---|---|---|
   | `401` + `NOT_AUTHENTICATED` | token 過期或無效 | 用 refresh token 換新（`POST /api/users/login/refresh/`），失敗再導回登入頁 |
   | `404` + `USER_NOT_FOUND` | 這次請求根本沒帶 token | 視為 bug：檢查 HTTP client 是否漏帶標頭；使用者端則導回登入頁 |
   | `403` + `FORBIDDEN` | 沒登入，或 session 不是這位使用者的 | 導回首頁／重新開始一場 |

4. **開發測試方式**：想在本機測遊戲，請先登入取得 token，不要再依賴「免登入」：

   ```bash
   # 1. 登入取得 token
   curl -X POST https://<後端網址>/api/users/login/ \
     -H "Content-Type: application/json" \
     -d '{"username": "<帳號>", "password": "<密碼>"}'
   # 回傳 {"access": "...", "refresh": "..."}

   # 2. 帶 token 開始遊戲
   curl -X POST https://<後端網址>/api/games/fridge-check/sessions/ \
     -H "Authorization: Bearer <access>"
   ```

5. **Flutter 範例**（以 `dio` 為例，用攔截器統一加標頭）：

   ```dart
   dio.interceptors.add(InterceptorsWrapper(
     onRequest: (options, handler) {
       final token = tokenStorage.accessToken; // 你們儲存 token 的地方
       if (token != null) {
         options.headers['Authorization'] = 'Bearer $token';
       }
       handler.next(options);
     },
     onError: (error, handler) {
       final code = error.response?.data?['error']?['code'];
       if (error.response?.statusCode == 401 && code == 'NOT_AUTHENTICATED') {
         // TODO: 用 refresh token 換新 access token 後重送請求；失敗則導回登入頁
       }
       handler.next(error);
     },
   ));
   ```

### 1.6 驗證結果（後端）

- 新增測試 `games/tests_anonymous.py`：資料庫有使用者、但沒登入時，4 個開場端點都回 `404 USER_NOT_FOUND`，且**不會建立任何 session**；已登入的使用者仍能正常開始遊戲。
- 更新 `games/tests_utils.py`：未登入應取得 `None`（不再取第一位使用者）。
- 全部測試通過（767 個，另有 1 個原本就預期失敗）。

### 1.7 修改的檔案（給有興趣看程式的人）

- `games/utils.py`：`get_current_user()` 未登入時回傳 `None`。
- `games/tests_utils.py`：更新對應測試。
- `games/tests_anonymous.py`：新增 view 層測試。

---

## 2. 預告：已規劃但尚未實作的變更

> ⚠️ 以下**還沒有改**，只是讓前端提早知道方向。上線前會更新本文件，請勿現在就照這節改程式。標 ❓ 的項目還需要和前端討論後才會定案。

### 2.1 預設所有 API 都需要登入（G2）— 破壞性

- 目前全域預設是「任何人都能存取」，要靠各 view 自己限制。計畫改成**預設需登入**，只有少數公開端點例外。
- 預計維持公開：註冊、登入、token 刷新、忘記密碼流程、分享頁（`public_share`）、首頁連線測試 `ping`。
- 其他端點（含 `home` 的 `greet`、`daily-suggetion`）未登入會回 `401 NOT_AUTHENTICATED`。
- 前端影響：確認**除上述公開端點外**，每個請求都帶 token。

### 2.2 遊戲 session 擁有者檢查（F2、F3）— 可能破壞性

- `fridge-check` 答題、`market-shopping` 答題（item／change）、`market-sort` 目前不檢查 session 屬於誰。
- 預計補上，錯誤回應與 1.3-B 相同：`404 SESSION_NOT_FOUND`／`403 FORBIDDEN`。
- 前端影響：只能操作**自己開的** session；`session_id`（以及 `market-sort` 的 `client_session_id`）要確實用同一個登入帳號建立與使用。

### 2.3 忘記密碼加入身分驗證（F4）— 破壞性 ❓

- 目前只憑帳號名稱就能重設密碼，風險很高。預計加入額外驗證與嘗試次數限制。
- **驗證方式（簡訊／Email 驗證碼，或其他方式）尚未決定**，確定後前端流程（`/api/users/password-reset/check/`、`/api/users/password-reset/`）會需要新增一個步驟與畫面。
- 另外也會調整「帳號不存在」的回應，避免被拿來探測帳號是否存在。

### 2.4 請求頻率限制（G3）— 新增 429

- 登入、註冊、改密碼、重設密碼預計加上限速。
- 超過次數會回 **HTTP 429**，前端請準備一個「操作太頻繁，請稍後再試」的提示。

### 2.5 Token 政策調整（G4）— 需前端配合 ❓

- 預計縮短 access token 有效期（目前 1 天，原本是測試期間放寬的）、啟用 refresh token 輪替，以及改密碼後舊 token 失效。
- 前端必須實作「**access token 過期 → 用 refresh token 自動換新 → 重送原請求**」的流程（若尚未做）。
- 若啟用輪替，每次 refresh 會回傳**新的 refresh token**，前端要存起來取代舊的。

### 2.6 統一回應格式（G5、G6）— 破壞性 ❓

專案規範的格式是：

```json
{ "success": true, "data": { }, "error": null }
```

目前有些 API 沒遵守，預計逐步統一：

| 模組 | 現況 | 預計 |
|---|---|---|
| 日記 `diary` | 成功只回 `{"data": ...}`，失敗只回 `{"error": ...}`，沒有 `success` | 補上 `success`，失敗時 `data: null` |
| 社群 `social` | 部分端點缺 `success`／`data` | 統一 |
| 首頁 `home`、部分 `users` | 直接回裸資料（例如 `{"message": ...}`） | 包進統一格式 |
| 登入、註冊 | 登入回 `{access, refresh}`，註冊回裸資料 | ❓ **改動影響最大，會先和前端確認再動** |

前端建議：現在就把「解析回應」集中在一個地方，並同時相容新舊格式（先看有沒有 `success` 欄位），之後切換會輕鬆很多。

### 2.7 其他會影響前端畫面或資料的項目

| 項目 | 影響 |
|---|---|
| 日記照片／錄音改用簽名網址（F5） | 回傳的檔案網址將**有時效**，不可永久存起來當連結；過期要重新向後端取得 |
| 刪除帳號時清除雲端檔案（F6） | 無介面變化；刪除後頭像、日記檔案網址會失效 |
| 日記 `round_index` 傳非數字（F7） | 由 500 錯誤改為 400 並附說明，前端請照 `error.code`／`message` 顯示 |
| 週報 `GET`（F10） | 查看週報時不再同步產生 AI 內容；若報告尚未備妥可能回「產生中」狀態（細節定案後補） |
| 遊戲完成時間日期（F11） | `played_date` 等日期會改為**台灣時間**的日期，台灣 00:00–08:00 玩的場次不再少一天 |

---

## 3. 給前端的檢查清單（現在就能做）

- [ ] 所有遊戲請求（含 1.4 節列的端點）都帶 `Authorization: Bearer <access_token>`
- [ ] 拿掉任何「不登入直接玩遊戲」的測試用流程
- [ ] 收到 `401 NOT_AUTHENTICATED` 時，會用 refresh token 換新 token 並重送
- [ ] 收到 `404 USER_NOT_FOUND`、`403 FORBIDDEN` 時，導回登入／首頁而不是顯示空白
- [ ] 以 `error.code` 判斷錯誤，不依賴 `error.message` 文字
- [ ] 回應解析集中在單一處，先相容「有／沒有 `success` 欄位」兩種格式
- [ ] 預留 HTTP 429（太頻繁）的提示畫面
