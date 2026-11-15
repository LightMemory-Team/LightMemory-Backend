# fix/global 後端修改紀錄（詳細版）

更新日期：2026-11-14 · 分支：`fix/global`（合併目標） · 已完成：G1、G3、G9、G4 精簡版（改密碼後舊 token 失效）、日記上傳限制、遊戲改名、跳過本輪 API

## 這份文件是什麼

`fix/global` 處理**跨 app 的共同性問題**（設定、安全、工具、流程）。每個編號一個小分支、一個 PR，合併進 `fix/global`。和 `fix/features` 的分工：

| 分支 | 內容 | 紀錄 |
|---|---|---|
| `fix/features` | 單一功能的問題（F1～F14） | [fix_features_changelog.md](fix_features_changelog.md) |
| `fix/global` | 共同性問題（G1～G14） | **本文件** |

給前端看的是 [frontend_api_changes.md](frontend_api_changes.md)；本文件給後端開發者，寫「為什麼這樣改、怎麼驗證、有什麼限制」。

`fix/global` 一開始就是 `fix/features`（含 rewards）的最新狀態，之後只多出 G 系列的修改。

## 0. 總覽

| 編號 | 問題（一句話） | 類型 | PR | 前端要改嗎 |
|---|---|---|---|---|
| G1 | `SECRET_KEY`、`DEBUG`、CORS 寫死在程式碼裡 | 安全設定 | #109（另有補強，見 G1.5） | Flutter Web 的網址要列進 CORS；手機 App 不受影響 |
| G3 | 登入、註冊、改密碼、刪帳號沒有次數限制 | 暴力破解防護 | #110 | ⚠️ 要處理 429 |
| G9 | OpenAI 沒設 timeout，AI 一卡住請求就卡住（最久約 30 分鐘） | 可用性 | #111 | 不用 |
| G4 精簡版 | 改密碼或重設密碼後，舊的登入 token 還能用最久 30 天 | 帳號安全 | #112 | ⚠️ 所有人重新登入一次；密碼改過後換 token 會回 401 |
| 上傳限制 | 日記照片、錄音沒有大小與類型限制（只有頭像有） | 濫用防護 | #113 | ⚠️ 多 2 種 400 錯誤碼（見前端文件） |
| 料理準備 | `memory_recall` 後端叫「記憶配對」，前端遊戲內叫「料理準備」 | 一致性 | #116 | 只有名稱字串變了 |
| 跳過本輪 | 前端有「跳過」按鈕，後端沒有 API，前端用假資料 | 缺功能 | #117 | ⚠️ 要改成呼叫新 API |

尚未開始與**範圍調整**：使用者決定「後端先不考慮部署條件，只處理比較嚴重的問題」，所以剩下的依嚴重度排序，嚴重項目（含日記上傳限制）都已完成，另依前端回覆追加兩項（見第 6 章）；G2、G5～G8、G10～G14 先不做（見第 7 章）。

### 共同的做法
1. 一個編號 = 一個小分支 = 一個 PR，base 是 `fix/global`；commit 用 Conventional Commits，會破壞既有行為的加 `!`。
2. 測試與程式放同一個 commit；驗證「**把修正拿掉，新測試會失敗**」。
3. **全部測試通過才 commit**（用測試的結束代碼把關，不接 `tail`）。
4. ruff 只對自己改的檔案跑；**格式化後要檢查有沒有動到無關的舊程式碼**（G3 就遇到，見 G3.7）。

---

## 1. G1 — 安全設定改讀環境變數（PR #109）

### 1.1 問題與風險

`config/settings.py` 的安全設定寫死在程式碼裡：

| 設定 | 原本 | 風險 |
|---|---|---|
| `SECRET_KEY` | 固定字串，**已經公開在 Git 歷史裡** | 能偽造 session、重設密碼連結、JWT 簽章 |
| `DEBUG` | 固定 `True` | 出錯時把程式碼、設定、環境變數顯示給任何人 |
| `CORS_ALLOW_ALL_ORIGINS` | 固定 `True` | 任何網站的瀏覽器程式都能呼叫 API |

### 1.2 修改

全部改讀 `.env`（用 `python-decouple`），**預設值選安全的那一邊**：

| 變數 | 開發 | 正式環境 |
|---|---|---|
| `DJANGO_DEBUG` | 設 `True` | 沒設就是 `False` |
| `DJANGO_SECRET_KEY` | 不用設，用開發專用備用金鑰 | **一定要設**，沒設啟動就報錯；不能用 `django-insecure-` 開頭 |
| `DJANGO_CORS_ALLOW_ALL` | 預設跟著 `DEBUG`（開發允許全部） | 預設不允許 |
| `DJANGO_CORS_ALLOWED_ORIGINS` | — | 逗號分隔，明確列出（例如 Flutter Web 的網址） |
| `DJANGO_ALLOWED_HOSTS`、`DJANGO_CSRF_TRUSTED_ORIGINS` | 不設用原本預設值 | 逗號分隔 |

`settings_test.py` 先用 `os.environ.setdefault` 補一把測試用金鑰，所以測試與日後的 CI 不需要 `.env` 裡有金鑰。`.env.example`、`README.md`、`doc/cloudfare.md` 同步更新。

### 1.3 設計決策

- **為什麼拒絕 `django-insecure-` 開頭的金鑰？** Django 的 `startproject` 產生的金鑰都是這個開頭，包含曾經寫進這個專案、已經外洩的那一把。正式環境用到它就等於沒換。
- **為什麼 DEBUG 開啟時給備用金鑰？** 開發者不該為了跑本機服務去設定金鑰；備用金鑰是公開字串，所以 DEBUG 關閉時絕對不會被採用。
- **為什麼 CORS 預設跟著 DEBUG？** CORS 只影響瀏覽器（Flutter Web），手機 App 不受影響。開發時全開省事，正式環境預設全關才安全。

### 1.4 測試（`config/tests/test_settings.py`）

每個測試都「**全新載入 `settings.py`＋只看指定的環境變數**」（用 `importlib` 重新執行檔案，並把 `decouple.config` 換成只讀環境變數的版本），不受本機 `.env` 影響：DEBUG 預設關閉與各種寫法、正式環境沒金鑰／用 `django-insecure-` 金鑰會失敗、開發沒金鑰可以跑、外洩的金鑰不在原始碼裡、CORS 與 `ALLOWED_HOSTS` 的預設與覆蓋。

### 1.5 補強：金鑰設成空字串（commit `ca2c7fa`，併在 #110）

**問題**：`.env` 留著 `DJANGO_SECRET_KEY=` 卻沒填值時，`python-decouple` 讀成「有設定、值是空字串」，**不會用備用金鑰**，Django 報 `The SECRET_KEY setting must not be empty`，連本機開發都起不來。這是測試與演練都沒想到的情況，是使用者把金鑰「拿掉」時（清掉值、留下那一行）實際遇到的。

**修改**：空字串（含只有空白）視同沒設定。DEBUG 開啟用備用金鑰；DEBUG 關閉丟出 `ImproperlyConfigured`，訊息說明要在 `.env` 加哪一行、怎麼產生金鑰（取代原本 decouple 的 `UndefinedValueError`）。

**測試**：正式環境空字串與只有空白會失敗、開發空字串用備用金鑰、錯誤訊息提到 `DJANGO_SECRET_KEY`。

**驗證**：只把 `SECRET_KEY` 那段退回舊寫法，4 個失敗＋2 個錯誤；還原後 19 個全過。

> 驗證時我第一次用了不含 G3 設定的整份 `settings.py` 當「舊版」，結果 `settings_test.py` 需要的 `DEFAULT_THROTTLE_RATES` 不存在，整個載入就壞了——那不是在驗證測試。改成只退回 `SECRET_KEY` 那一段才是對的。**「拿掉修正」要只拿掉那一個修正。**

### 1.6 部署前注意（重要）

- **正式環境必須先在 `.env` 設新產生的 `DJANGO_SECRET_KEY`**，否則服務起不來。產生方式：`python -c "import secrets; print(secrets.token_urlsafe(50))"`。
- **舊金鑰已公開在 Git 歷史，只能靠換金鑰解決**（不改寫歷史）。換金鑰會讓所有人的登入 token 失效（JWT 用這把金鑰簽）、管理後台 session 失效，需要重新登入；資料庫資料不受影響。
- Flutter Web 的正式網址要列在 `DJANGO_CORS_ALLOWED_ORIGINS`。
- 開發環境不受影響（`.env` 已有 `DJANGO_DEBUG=True`）。

### 1.7 已知限制

- 正式環境的金鑰品質（長度、隨機性）只擋了 `django-insecure-` 開頭，沒有檢查長度；文件建議用 `secrets.token_urlsafe(50)`。
- `SIMPLE_JWT` 的效期與黑名單是 G4；部署文件是 G13。

---

## 2. G3 — 登入、註冊、改密碼／刪帳號的次數限制（PR #110）

### 2.1 問題與風險

只有忘記密碼有次數限制（F4）。其他要輸入密碼，或可以大量建立資料的 API 都沒有：

| API | 風險 |
|---|---|
| 登入 | 無限次猜密碼；用「帳號不存在」與「密碼錯誤」探測哪些帳號存在 |
| 註冊 | 無限次建帳號；用「帳號已被註冊」探測帳號 |
| 修改密碼、刪除帳號 | 要輸入密碼確認身分；偷到 access token 的人可以一直猜密碼 |

### 2.2 修改

**次數**寫在 `config/settings.py` 的 `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`（F4 的兩個類別是寫在類別裡，沒有搬動）：

| scope | 次數 | 套用在 | 怎麼算 |
|---|---|---|---|
| `login_username` | 10／小時 | `POST users/login/` | **只算失敗**，成功歸零 |
| `login_ip` | 60／小時 | `POST users/login/` | **只算失敗** |
| `register_ip` | 30／小時 | `POST users/register/` | 每個請求都算 |
| `password_confirm_user` | 10／小時 | `POST users/me/password/`、`DELETE users/me/` | 每個請求都算，兩個動作共用 |

**`users/throttles.py`** 新增：

- `FailureCountThrottle`（基底）：請求進來時只「檢查」失敗次數有沒有超過，**不記錄**；由 View 在確定失敗時呼叫 `record_failure()` 才記一次；`clear()` 可歸零。
- `LoginIPThrottle`、`LoginUsernameThrottle`：登入用。帳號名稱 `strip().lower()` 後做 SHA-256 當 cache key（避免特殊字元或過長）。
- `RegisterIPThrottle`、`PasswordConfirmUserThrottle`：一般的 DRF 計數限速（後者以 `user.pk` 當 key）。

**`users/views.py`**

- 新增 `LoginView(TokenObtainPairView)`：覆寫 `post()`，包住 simplejwt 原本的流程。收到 `AuthenticationFailed`（帳密錯誤、帳號不存在、帳號停用）→ 對每個限速記一次失敗再重新丟出；成功 → 只把「帳號」那個限速歸零（**來源的失敗次數不歸零**）。
- `RegisterView.throttle_classes = [RegisterIPThrottle]`。
- `PasswordChangeView.throttle_classes = [PasswordConfirmUserThrottle]`。
- `MeView.get_throttles()`：只有 `DELETE` 回傳限速，`GET`、`PATCH` 不限制。
- `users/urls.py`：`login/` 改指向 `LoginView`（路由名稱不變）。

### 2.3 設計決策

- **為什麼登入只算失敗？** 一般 DRF 限速每個請求都算。登入如果這樣算，正常使用者一小時內登入幾次（例如手機、平板、重開 App）就被擋了。只算失敗，正常使用幾乎碰不到上限。
- **為什麼成功登入要把帳號的失敗次數歸零？** 使用者前幾次打錯、第 9 次打對，之後不該再因為舊的失敗被鎖。**來源的次數不歸零**，否則攻擊者用自己的帳號登入成功就能洗掉來源的失敗紀錄。
- **為什麼「帳號不存在」也算失敗？** 否則攻擊者可以靠「有沒有被擋」猜出帳號存不存在。
- **為什麼沒填帳號或密碼（400）不算？** 這是前端的格式錯誤，不是猜密碼；而且沒有帳號名稱就算不出 key。
- **為什麼註冊每個請求都算？** 註冊沒有「成功才不算」的道理：成功建帳號本身就是被限制的行為（防垃圾帳號）。
- **為什麼改密碼與刪帳號以「使用者」而不是 IP 計算？** 這兩個 API 需要登入，使用者身分已知；以 IP 算反而讓共用網路的人互相影響。兩個動作共用同一份，因為它們都在「猜密碼」。
- **為什麼 `GET /me/`、`PATCH /me/` 不限？** 它們不輸入密碼，限制只會影響正常使用。

### 2.4 `NUM_PROXIES`：來源 IP 怎麼判斷（重要）

DRF 的 `get_ident()` 在沒設 `NUM_PROXIES` 時，會把**整串** `X-Forwarded-For` 當成來源。使用者可以自己在請求裡加這個標頭，每次加不同的假值，每個請求就得到不同的「來源」——**來源限制形同虛設**。F4 的來源限制也有這個漏洞。

**修改**：`REST_FRAMEWORK["NUM_PROXIES"] = config("DJANGO_NUM_PROXIES", default=1, cast=int)`。

- 設 `1`（預設）：只信 `X-Forwarded-For` 的**最後一個值**。部署文件寫的是 Cloudflare Tunnel：後端看到的連線都來自 cloudflared（本機），真正的來源由 Cloudflare 接在標頭**最後**，使用者自己加的假值排在前面，取最後一個就騙不了。沒有這個標頭（本機直連）就用連線來源。
- 設 `0`：完全忽略 `X-Forwarded-For`。**沒有代理、直接對外的部署必須設 0**，否則標頭可被假造。
- **為什麼不設 0 當預設？** 走 Tunnel 時所有連線的 `REMOTE_ADDR` 都是 `127.0.0.1`，設 0 會讓**全部使用者共用同一個來源**，來源限制（60 次／小時）等於全站共用，幾個人打錯密碼就全站被鎖。

> **我沒有在真的 Cloudflare Tunnel 上驗證過** Cloudflare 附加 `X-Forwarded-For` 的行為，是依 Cloudflare 文件。部署後請用兩個不同網路各試一次登入失敗，確認來源有被分開計算。

### 2.5 測試（`users/tests/test_auth_throttle.py`，32 個）

測試環境的上限調得很高（`settings_test.py`，避免別的測試累積到上限），所以這裡用 `patch.dict(SimpleRateThrottle.THROTTLE_RATES, …)` 套上正式的次數；每個測試 `cache.clear()`。

| 類別 | 驗證什麼 |
|---|---|
| 登入（14） | 未達上限仍是一般 401；達上限 429 且有 `Retry-After`；**正確密碼被鎖時也被擋**；帳號不存在也算；其他帳號不受影響；帳號大小寫與空白視為同一個；成功登入不計（連續 30 次成功都 200）；成功歸零後又可以失敗 10 次；沒填欄位不計；停用帳號算失敗；一個來源試很多帳號 60 次後被擋；另一個來源不受影響；`Retry-After` 在 3500～3600 秒；一小時後解鎖 |
| 註冊（3） | 30 次後 429 且**不會建立帳號**；失敗（帳號已被註冊）也算；另一來源不受影響 |
| 改密碼／刪帳號（9） | 錯誤舊密碼 10 次後 429；**正確密碼被鎖時也被擋，而且密碼沒被改**；正常改密碼不受影響；刪帳號 10 次錯誤後 429 且**帳號還在**；兩者共用同一份；正常刪帳號仍 204；查看與修改個人資料不限；各使用者獨立；未登入是 401 不是 429 |
| 來源判斷（3） | 假造前綴繞不過來源限制；`NUM_PROXIES=1` 時不同的真實來源分開計算；`NUM_PROXIES` 為 0／1 與沒有標頭時各取哪個位址 |
| 設定（3） | 正式環境的次數與測試所假設的一致（載入真正的 `settings.py` 比對）；測試設定也有每個 scope；`NUM_PROXIES` 預設 1、環境變數可改 |

**拿掉修正會失敗的驗證**：

| 還原的內容 | 結果 |
|---|---|
| `LoginView`、各 View 的限速與路由（全部不限速） | 17 個失敗＋1 個錯誤 |
| 只拿掉「登入成功就歸零」 | 1 個失敗 |
| 只拿掉 `NUM_PROXIES` | 1 個失敗（假 IP 繞過）＋1 個錯誤（預設值） |

### 2.6 開發過程發現的問題

- **被鎖時回 500（我自己寫的 bug）**：`FailureCountThrottle.allow_request` 一開始沒有設 `self.now` 與 `self.history`，而 DRF 在回 429 前會呼叫 `wait()`（算「請多久後再試」），它需要這兩個屬性，結果 `AttributeError` → 500。新測試第一次跑就有 9 個失敗，發現並修正。若沒有測試，使用者被鎖時看到的會是「系統正在休息」而不是「操作太頻繁」。
- **`ruff format` 順手改了舊程式碼**：我對 5 個檔案跑 `ruff format`，`users/views.py`（+89 行）、`config/settings_test.py` 的差異比預期大——它把舊的 `Response({...})` 排版、引號全改了，這會讓 PR 混進無關差異。我檢查 `git diff` 發現後，手動還原那些無關的行，`users/views.py` 只剩 G3 的 +45／−1。**對舊檔案跑格式化後，一定要看 diff。**
- **本機 `.env` 的空金鑰**：見 G1.5。

### 2.7 部署前注意

- **確認 `DJANGO_NUM_PROXIES`**：走 Cloudflare Tunnel 用預設 1；**沒有代理、直接對外必須設 0**。
- **多個 worker 時次數會變寬鬆**：計數存在各 process 自己的記憶體快取（專案沒有設定 `CACHES`）。正式環境要換共用快取（Redis），限速才精準。
- 部署後試一次：連續輸錯密碼 10 次，第 11 次應回 429。

### 2.8 已知限制

- **帳號鎖定可被濫用**：知道別人帳號名稱的人，可以故意連續輸錯 10 次，把對方鎖一小時（F4 同樣）。這是「針對帳號限制」的固有取捨；來源限制放寬到 60 次，帳號限制維持 10 次當主要防線。
- `POST users/login/refresh/`（換 token）沒有限制：需要持有 refresh token，不是猜密碼。
- `public_share/views.py` 的留言限速自己取 `X-Forwarded-For` 的**第一個**值（`get_client_ip`），可被假造，不在這個 PR 範圍；建議之後改用同一套來源判斷。
- 快取的讀取與寫入不是原子的（先讀、再寫），並行請求可能少算一兩次；對限速來說可接受。
- 登入被鎖時沒有「還剩幾次」的提示。

---

## 3. G9 — OpenAI 統一設定 timeout 與重試（PR #111）

### 3.1 問題與風險

OpenAI SDK 預設**單次等待 600 秒（10 分鐘）、失敗重試 2 次**，最壞情況一次呼叫可以卡 30 分鐘。AI 服務一卡住，使用者的請求就跟著卡住，而且一直占著那個請求的處理程序：

| 呼叫處 | 卡住時的影響 |
|---|---|
| `diary/ai_gen.py` 首問、追問 | 使用者錄音回覆後一直轉圈 |
| `diary/ai_gen.py` 完成日記 | 卡在 F7 的日記鎖（`select_for_update`）裡，同一篇日記的其他請求都在等 |
| `ai_service/weekly_summary.py` | 看週報一直轉圈 |
| `ai_service/greeting.py` | 當天第一位打開首頁的人卡住（之後有快取） |

四處原本就有 `try/except` 退回固定內容，所以**只缺 timeout**。一開始沒人發現，是因為 AI 正常時不會碰到。

### 3.2 修改

- 新增 `ai_service/client.py` 的 `get_client()`，全專案共用，統一設定：

  | 設定（`config/settings.py`，可在 `.env` 調整） | 預設 | 說明 |
  |---|---|---|
  | `OPENAI_TIMEOUT_SECONDS` | 15 | 單次最多等幾秒 |
  | `OPENAI_MAX_RETRIES` | 1 | 暫時性錯誤最多重試幾次 |

  最壞情況 ≈ 15 × (1 + 1) = **30 秒**，而不是 SDK 預設的 600 × 3 = **1800 秒**。
- `diary/ai_gen.py`、`ai_service/weekly_summary.py`、`ai_service/greeting.py` 原本各自 new 一個沒設 timeout 的 client，改成呼叫 `get_client()`。**各模組的 `_client` 名稱保留**（`greeting` 以 `from .client import get_client as _client` 取用），既有測試用 `patch("…._client")` 的做法不受影響。
- 逾時之後沿用原本的退回機制：首問、追問用固定句型，完成日記用預設值，週報總結用固定句型，問候語用固定問候語。API 的格式與欄位完全沒變，**前端不用改**。

### 3.3 設計決策

- **為什麼是 15 秒、重試 1 次？** 這幾個呼叫的 `max_tokens` 都在 400 以下，`gpt-4.1-mini` 通常幾秒內回完。15 秒夠寬鬆又不會讓人等太久；重試 1 次可以救回偶發的 429／5xx，再多就只是讓使用者多等。**我沒有用真的 OpenAI 量過「完成日記」**（最長的那個），若實際常逾時，調高 `OPENAI_TIMEOUT_SECONDS`。
- **為什麼重試不會拖很久？** SDK 只對暫時性錯誤（連線失敗、逾時、429、5xx）重試；金鑰錯誤（401）這類不會重試。
- **為什麼抽共用函式，而不是各處加參數？** 之前三處各寫一份，所以才會三處都漏。共用之後只有一個地方設定；測試裡另有一個檢查，確認專案裡沒有任何地方自己 `OpenAI(` 一個新的（防止之後有人又寫一個沒設 timeout 的）。
- **語音辨識（Whisper）不在這裡**：`diary/external.py` 的 `transcribe_audio` 用的是**本機執行**的 `whisper` 模型（`whisper.load_model("base")`），不是呼叫 OpenAI 的 API，沒有網路 timeout 問題。它的風險是上傳的錄音沒有大小限制，由另一項處理。

### 3.4 測試（`ai_service/tests/test_client.py`，15 個）

| 類別 | 驗證什麼 |
|---|---|
| 設定（5） | client 用到設定的 timeout 與重試；預設值（15 秒、1 次，最壞 ≤ 60 秒）；兩個值都能由環境變數覆蓋；三個模組的 `_client` 都走共用 client；**專案裡沒有任何地方自己 new `OpenAI(`** |
| 卡住（6） | 用**本機假伺服器（收到請求卻 5 秒不回應）**，timeout 設 0.3 秒：直接呼叫會在時限內放棄；首問、追問、完成日記、週報總結、首頁問候語各自退回固定內容，且耗時都小於 3 秒 |
| 重試（4） | 正常回應只打 1 次；500 重試 1 次後成功（共 2 次）；一直 500 時只打 2 次（不是 SDK 預設的 3 次）；401 不重試（只打 1 次） |

重點是「卡住」那類：**不是只檢查設定值，而是真的讓伺服器卡住，驗證程式會在時限內放棄**。

**拿掉修正會失敗的驗證**：把 `timeout`、`max_retries` 從 `get_client()` 拿掉 → 9 個失敗（整組測試跑了 102 秒，因為每個「卡住」的測試都被假伺服器拖滿 5 秒才放行）。

### 3.5 已知限制

- 逾時會讓**那一次**的 AI 內容變成固定句型，不會自動補寫。
- 15 秒是估計值（見 3.3）。
- 週報總結沿用 F10 的機制：AI 失敗留下的固定句型，下次點開週報會自動重試。
- 這個修正也讓 F7 的鎖「最多握 30 秒」，而不是 30 分鐘，但完成日記仍然是在鎖內呼叫 AI；若要完全移出鎖，需要改成兩段式流程，不在這次範圍。

---

## 4. G4 精簡版 — 改密碼或重設密碼後，舊的登入 token 全部作廢（PR #112）

計畫裡的 G4 原本是「JWT blacklist＋rotation＋縮短效期」，需要 `token_blacklist` 的 migration。使用者決定只處理嚴重問題，所以只做其中最有價值、**不需要資料表**的一塊：密碼改過之後，舊 token 作廢。

### 4.1 問題與風險

JWT 是「簽好就一直有效到過期」：access token 1 天、refresh token 30 天。改密碼（或忘記密碼重設）後，**舊的 token 完全不受影響**。

情境：帳號被盜用 → 本人發現後改密碼 → **攻擊者手上的 token 仍然可以用最久 30 天**，改密碼等於沒用。忘記密碼的重設也一樣。

### 4.2 修改

**`config/settings.py`**：`SIMPLE_JWT["CHECK_REVOKE_TOKEN"] = True`（simplejwt 5.5.1 內建）。

- 簽發 token 時，多放一個欄位 `hash_password`＝使用者**目前密碼欄位**的 MD5（只是「指紋」，不是密碼，也無法還原密碼）。
- 驗證 access token（`JWTAuthentication.get_user`）時，拿 token 裡的指紋跟使用者**現在**的密碼指紋比；對不上回 401（錯誤碼 `NOT_AUTHENTICATED`）。
- 密碼一改，指紋就變了，**這個使用者所有舊的 token（所有裝置）同時作廢**。

**`users/views.py` 新增 `PasswordAwareTokenRefreshSerializer`、`RefreshView`**（`users/urls.py` 的 `login/refresh/` 改指向它）：

simplejwt 內建的檢查**只在「拿 access token 打 API」時做**，換 token 的端點（`TokenRefreshSerializer`）不檢查。結果：

1. 密碼改了，攻擊者用**舊的 refresh token** 打換 token 端點 → 成功拿到新的 access token（它從 refresh token 複製了舊的指紋）。
2. 那個 access token 一用就被拒絕（401）。攻擊者拿不到東西，**但前端的「401 → 換 token → 重試」會一直循環**，不會回到登入頁。

所以讓換 token 這一步就失敗：檢查 refresh token 裡的指紋，對不上就丟 `TokenError`（simplejwt 把它轉成 401）。

順便修一個舊問題：帳號已刪除時，simplejwt 原本的換 token 會 `User.objects.get()` 丟 `DoesNotExist` → **500**，現在回 401。

### 4.3 設計決策

- **為什麼不做完整的 blacklist？** 需要新增資料表（`token_blacklist` 的 migration）。它能做到「登出時作廢這張 token」，但「換密碼後作廢」這個最重要的情境，用指紋就能解決，成本低很多。
- **為什麼用「密碼指紋」而不是紀錄 token 版本？** 不需要在使用者資料表加欄位（專案偏好不改資料表）。密碼改變本身就是需要作廢的事件。
- **為什麼改密碼的那個人不會被登出？** 修改密碼的 API 本來就會用新密碼簽發新的 token 放在回應裡（`RefreshToken.for_user(user)` 在 `set_password` 之後執行）。前端要換掉本機的 token。
- **忘記密碼重設沒有簽發 token**，所以本來就需要重新登入，不受影響。
- **為什麼 refresh token 沒有帶指紋的舊 token 也一律拒絕？** 舊 token（部署前簽發）沒有 `hash_password` 欄位，`None != 指紋` → 拒絕。代價是部署後所有人要重新登入一次；好處是沒有「舊 token 永遠繞過檢查」的後門。

### 4.4 測試（`users/tests/test_token_revoke.py`，21 個）

| 類別 | 驗證什麼 |
|---|---|
| 正常使用（5） | 設定有開；新登入可用；換 token 取得的 access token 可用；換 token 可重複；亂填的 refresh token 被拒絕 |
| 不誤殺（4） | **另一台裝置登入**（更新 `last_login`）不影響既有 token；修改暱稱不影響；別的使用者改密碼不影響我；改密碼失敗（舊密碼打錯）不影響 |
| 改密碼（5） | 舊 access token 作廢（401）；舊 refresh token 換不到新的 access token（401）；回應裡的新 token 可用（含換 token）；用新密碼可登入；**其他裝置的舊 session 也一起作廢** |
| 忘記密碼重設（2） | 舊 access／refresh 作廢；用新密碼可登入 |
| 舊 token（1） | 沒有指紋欄位的舊 token 被拒絕（把欄位從 token 拿掉模擬） |
| 帳號狀態（3） | 刪除的帳號換 token 回 **401 不是 500**；刪除的帳號 access token 被拒絕；停用的帳號換 token 被拒絕 |
| 內容（1） | token 只帶指紋（32 碼 MD5），不帶密碼雜湊本身（`pbkdf2`、salt 都不在裡面） |

**拿掉修正會失敗的驗證**：

| 還原的內容 | 結果 |
|---|---|
| 只把 `CHECK_REVOKE_TOKEN` 設回 `False` | 5 個失敗＋2 個錯誤 |
| 換 token 端點換回 simplejwt 原本的 | 5 個失敗（含「刪除帳號的 refresh token 回 500」） |

### 4.5 開發過程備註

- **測試手法的錯誤**：我第一次想用 `override_settings(SIMPLE_JWT=…關掉檢查…)` 來簽發「部署前的舊 token」，但 simplejwt 的 `tokens.py` 在載入時就把設定物件綁好了，`override_settings` 之後它仍然用舊的設定，簽出來的 token 還是有指紋，測試因此失敗。改成直接把 `hash_password` 欄位從簽好的 token 拿掉，更直接，也更像真實的舊 token。
- **`ruff format` 這次沒有整檔格式化**：`users/views.py` 有舊程式碼本來就不符合格式，整檔格式化會混進無關差異（G3 吃過虧）。我用 `ruff format --diff` 只看有沒有針對我新增程式碼的建議，手動調整我那一段。
- **`settings.py` 的 ruff 問題從 3 個變 4 個**：我新寫的註解超過 88 字元，已縮短，回到原本的 3 個（舊的）。

### 4.6 部署前注意

- **部署後所有人要重新登入一次**（舊 token 沒有指紋）。
- 同一個帳號在一台裝置改密碼後，**其他裝置會被登出**。

### 4.7 已知限制

- **沒有「登出時作廢這張 token」**（需要 blacklist 的資料表）。access token 仍有效 1 天、refresh 30 天；只有「換密碼」能作廢。
- **沒有「登出所有裝置」按鈕**（改一次密碼等於登出所有裝置）。
- 指紋來自「使用者目前的密碼欄位」。Django 登入時若發現密碼雜湊演算法需要升級（調高 pbkdf2 次數、換演算法）會自動重存，那個使用者其他裝置的 token 會在那一次被作廢。很少發生，影響只是重新登入一次。
- **忘記密碼本身沒有身分驗證**（使用者決定維持現狀）：攻擊者重設密碼後，**他自己**會拿到有效的登入，原本的使用者則被登出。這項修正讓「本人事後改密碼」能把攻擊者踢出去，但擋不住第一次的接管。

---

## 5. 日記照片與錄音的上傳限制

### 5.1 問題與風險

`POST /api/diary/`（上傳照片）與 `POST /api/diary/<id>/replies/`（上傳錄音）只檢查「有沒有檔案」，**不看大小、不看類型**（只有頭像有限制：2MB、僅圖片）。任何登入者都能：

- 傳一個幾百 MB 的檔案：錄音會交給**本機的 Whisper**（`diary/external.py`，不是付費 API）辨識，吃 CPU、記憶體與時間，整台後端被拖慢；
- 傳任何類型的檔案（網頁、執行檔…）：照片、錄音都會原樣存進 Firebase。

> 更正：我先前說「錄音會送去 Whisper 花錢」是錯的，Whisper 是本機模型。真正的風險是**資源耗盡**與**垃圾檔案**，不是費用。

### 5.2 修改

**新增 `diary/upload_checks.py`**：`check_photo(file)`、`check_audio(file)`，合格回傳 `None`，否則回傳 `(錯誤碼, 訊息)`。

| 項目 | 規則 |
|---|---|
| 照片大小 | 超過 10MB → 400 `IMAGE_TOO_LARGE` |
| 錄音大小 | 超過 25MB → 400 `AUDIO_TOO_LARGE` |
| 空檔（0 bytes） | 400 `INVALID_IMAGE`／`INVALID_AUDIO` |
| 照片類型 | 副檔名在 `jpg jpeg png webp heic heif`，**或**宣告的類型是 `image/*` |
| 錄音類型 | 副檔名在 `webm ogg opus m4a mp4 aac mp3 wav flac`，**或**宣告的類型是 `audio/*`、`video/webm`、`video/mp4`、`video/ogg` |
| 不符合 | 400 `INVALID_IMAGE`／`INVALID_AUDIO`（沿用原本的錯誤碼） |

**`diary/views.py`**：照片上傳在「沒有檔案」檢查之後、上傳 Firebase **之前**呼叫 `check_photo`；錄音回覆在「沒有檔案」檢查之後、**辨識與上傳之前**呼叫 `check_audio`。被擋的請求不會建立日記、不會寫入回覆、不會呼叫 Whisper 或 Firebase、不會占用該輪次（修好再送同一輪還能回答）。

### 5.3 設計決策

- **為什麼是 10MB／25MB？** 實際看了前端：照片用 `image_picker` 壓縮（寬度 1600、品質 85，通常不到 1MB）；錄音是 Opus（webm），單輪最長 180 秒，約 1MB。上限留 10～25 倍餘裕，不會誤擋正常使用，但足以擋掉惡意大檔。25MB 也容納 3 分鐘的未壓縮單聲道 WAV（約 16MB）。
- **為什麼類型檢查是「副檔名**或**宣告類型」？** 前端送照片時用 `MultipartFile.fromBytes` 且沒指定類型，伺服器看到的是 `application/octet-stream`，只能靠副檔名；錄音則有宣告 `audio/webm`。「或」才不會誤擋真實流程。
- **為什麼不檢查檔案內容（magic bytes）？** 這是便宜的第一道門檻。內容壞掉的檔案本來就由後面處理（辨識失敗回 `TRANSCRIPTION_FAILED`）；解析內容會讓既有測試與模擬資料全部要改，收益有限。日記檔案是私有的（F5，簽名網址），不會被當網頁開啟。
- **錯誤格式沿用各端點原本的**：照片上傳維持舊格式 `{"error": {...}}`，錄音回覆用 F14 統一的 `{success: false, data: null, error: {...}}`，不順手改格式。

### 5.4 測試（`diary/tests/test_upload_limits.py`，21 個）

| 類別 | 驗證什麼 |
|---|---|
| 照片上傳 | 正常；**前端真實格式（octet-stream）可過**；常見格式都可過；**剛好等於上限可過、多 1 byte 被擋**；空檔；非圖片（html、exe、txt、無副檔名、mp3）被擋；沒帶檔案仍被擋；**被擋時沒有呼叫上傳、沒有建立日記** |
| 錄音回覆 | **前端真實格式（audio/webm）可過**；帶 codecs 的類型可過；常見格式可過；**剛好等於上限可過、多 1 byte 被擋且沒呼叫辨識與上傳**；非音訊被擋；**被擋後同一輪還能再回答**；日記狀態不變 |
| 檢查函式 | 兩種大小的邊界；0 bytes；檔名是 `None` 或空字串不會崩潰；上限數值在合理範圍 |

**拿掉修正會失敗的驗證**：把 `diary/views.py` 還原成沒有檢查 → **14 個失敗**。完整測試 1090 個通過（另 1 個預期失敗）。

### 5.5 已知限制

- **檔案是先收完才檢查大小**：Django 會先把整個上傳內容收進暫存，才輪到這裡判斷。這能擋掉「Whisper 辨識與存 Firebase」的成本，但擋不住「傳輸本身」。要在入口就擋，需要在反向代理（Cloudflare、nginx）設請求大小上限。
- **只看副檔名與宣告類型**，可被偽造；偽造的檔案能通過檢查，之後可能在辨識時失敗，或當成「照片」存進 Firebase。
- **前端在 Flutter Web 時，照片檔名可能沒有副檔名**，且沒有宣告類型 → 會被當成 `INVALID_IMAGE`。手機 App（`image_picker` 檔名帶副檔名）不受影響；若 Web 版有這個情況，需要前端補上 `contentType`，或後端改成檢查檔案內容。
- 沒有限制「同一個人上傳的頻率」。

---

## 6. 依前端回覆追加（2026-11-14）

前端對照後端文件後回覆（2 項需要後端處理），範圍調整之外追加這兩項。

### 6.1 `memory_recall` 改名為「料理準備」（PR #116）

- **問題**：F14 把 `memory_recall` 叫「記憶配對」，前端遊戲內標題、教學、結算文案是「料理準備」（記憶配對的美術主題包裝）。首頁卡片讀後端 `name`，點進去卻是另一個名字。產品決定統一為「料理準備」。
- **修改**：`games/catalog.py`（首頁卡片 `name`、`title`）、`home/daily_tasks.py`（今日任務標題）、`rewards/catalog.py`（成就說明，由 `GAME_NAMES` 組出）三處。
- **新增 `home/tests/test_game_names.py`（6 個）**：三個地方各自寫死名稱，以前沒有任何東西把它們綁在一起。現在測試固定「正式名稱」表，三處必須都等於它、舊名稱不能殘留。拿掉修正 → 5 個失敗。
- 內部註解、docstring 仍寫「煮菜過程」（`games/memory_recall/`、`zscore.py` 等），那是開發者用語，沒有顯示給使用者，沒有改。

### 6.2 日記「跳過本輪」API

- **問題**：前端日記聊天頁有「跳過」按鈕，但後端**沒有對應 API**，前端 `skipReply` 一律回假資料，使用者以為跳過了、實際沒有紀錄。資料表早有 `DiaryReply.is_skipped`，`finalize` 與詳情也都認得它，只是沒有任何程式會寫入 `True`。
- **新增** `POST /api/diary/<id>/replies/skip/`（`DiaryReplySkipView`），body `{round_index}`。回應格式與 `replies` 一致（沒有 `transcript`、`audio_url`），用統一格式 `{success, data, error}`。
- **行為**
  - 寫入一筆 `is_skipped=True`、`transcript=""`、`audio_path=""` 的回覆；`question` 記下這一輪被問的問題。
  - 算一輪（`reply_count` +1），但不算有內容（`is_finalizable` 要有內容的 2 輪）。
  - 下一題用**固定句型**（3 句依輪次輪流），**不呼叫 AI、不辨識、不上傳**：沒有內容可以接著問，叫 AI 只會浪費時間與費用，也避免 AI 卡住。固定句型有測試通過用語檢查（F13 的禁用詞）。
  - 第 4 輪（最後一輪）回 `ai_reply: null`、`is_done: true`，並清空 `pending_question`。
  - 同 `replies` 的鎖與 transaction（`select_for_update`），同時送來的請求排隊；已回答或已跳過的輪次 → 409；`round_index` 不合法 → 400；已完成的日記 → 400；別人的日記 → 404；沒登入 → 401。
- **設計決策：前三輪都跳過時，第四輪不能跳過**（400 `SKIP_NOT_ALLOWED`）。否則四輪全跳過，日記沒有任何內容，`finalize` 只會回 `NO_VALID_REPLY`，使用者卡在一篇完成不了的日記。這個限制只擋「全部跳過」，其他組合都允許。
- **不處理前端的 `force=1`**：前端 `skipReply` 原本會送這個欄位，後端從來沒有這個功能，也不需要。
- **測試（`diary/tests/test_skip_reply.py`，23 個）**：基本行為（寫入、欄位、下一題、狀態）、跳過不呼叫 AI／辨識／上傳、固定句型過用語檢查且連續跳過不重複、與一般回覆混用時的計數（`reply_count`、`is_finalizable`、`is_done`）、詳情有顯示、驗證（無效 `round_index`、重複輪次、已完成、鎖內才完成的競態、全部跳過）、權限（401、別人的日記、不存在）、跳過後 `finalize` 只採用有內容的輪次（傳給 AI 的文字沒有多餘逗號）。
- **拿掉修正會失敗的驗證**（逐一拿掉）：「全部跳過」保護 → 2 個失敗；重複輪次檢查 → 2 個失敗；鎖內已完成檢查 → 1 個失敗；`is_skipped` 寫成 `False` → 4 個失敗；最後一輪不清 `pending_question` → 1 個失敗。
- **前端依賴的行為**（改了要先通知前端）：一篇日記最多 4 輪（`MAX_REPLY_ROUNDS`）；前端用 `reply_count >= 4` 判斷這輪是不是最後一輪。
- **已知限制**：固定句型只有 3 句，且與前面的內容無關；被跳過的輪次沒有「改成補錄」的機制（已跳過的輪次再送錄音會回 409）。

---

## 7. 範圍調整與尚未處理

**2026-11-14 使用者決定：後端先不考慮部署條件，只處理比較嚴重的問題。** 以下依此重新排序。

### 7.1 還要做（依序）

**沒有了**：使用者原本同意的 4 項嚴重問題，除了「忘記密碼身分驗證」（使用者決定維持現狀）外，其餘（OpenAI timeout、token 失效、上傳限制）都已完成。

### 7.2 評估過、這一輪不做

| 編號 | 項目 | 為什麼不做 |
|---|---|---|
| — | **忘記密碼的身分驗證** | 使用者決定維持只有次數限制（F4 起一直如此）。**這是目前已知最嚴重的洞**：重設密碼只需要帳號名稱，知道帳號的人就能接管該帳號。已告知，使用者決定維持現狀 |
| G2 | 預設權限改成 `IsAuthenticated` | 現況每個端點都在程式裡自己檢查登入與擁有者（已逐一核對遊戲的 `result/`、`round/`），沒有被繞過的路徑，只是預防新端點漏寫 |
| G4（其餘） | JWT blacklist（登出作廢）、rotation、縮短效期 | 需要 migration；最重要的「改密碼後作廢」已用更小的方式完成（第 4 章） |
| G5～G7 | 統一回應格式、時區與週界線共用 | 重構，不是嚴重問題 |
| G8 | 遊戲 session 的鎖與唯一約束 | 重複送出已有冪等保護（結算、發點）；需要 migration |
| G10 | 補索引 | 效能，需要 migration |
| G11、G12、G14 | CI、pre-commit、補測試 | 工具與流程 |
| G13 | 部署說明 | 先不考慮部署 |
| F5 後續 | 舊的公開檔案改成私有 | 要處理既有資料，屬於部署範圍 |

### 7.3 已知、記著但不處理

- `public_share/views.py` 的留言限速取 `X-Forwarded-For` 的**第一個**值，可被假造。

---

## 附錄：PR 與 commit 對照

| 編號 | PR | 分支 | commit 標題 |
|---|---|---|---|
| G1 | #109 | `fix/config-env-secrets` | `fix(config)!: SECRET_KEY、DEBUG、CORS 改讀環境變數` |
| G1 補強 | #110 | `fix/users-auth-throttle` | `fix(config): DJANGO_SECRET_KEY 設成空字串時視同沒設定` |
| G3 | #110 | `fix/users-auth-throttle` | `feat(users): 登入、註冊、改密碼與刪帳號加入請求次數限制` |
| G9 | #111 | `fix/ai-timeout` | `fix(ai): OpenAI 呼叫統一設定 timeout 與重試次數` |
| G4 精簡版 | #112 | `fix/jwt-revoke-on-password-change` | `fix(users)!: 改密碼或重設密碼後，舊的登入 token 全部作廢` |
| 上傳限制 | #113 | `fix/diary-upload-limits` | `fix(diary): 日記照片與錄音加上大小與類型限制` |
| 料理準備 | #116 | `fix/game-name-cooking-prep` | `fix(games)!: memory_recall 的遊戲名稱改為「料理準備」，與 App 內一致` |
| 跳過本輪 | #117 | `feat/diary-skip-reply` | `feat(diary): 新增日記跳過本輪 API` |

## 附錄：名詞小辭典

| 名詞 | 白話說明 |
|---|---|
| **throttle（限流）** | 限制同一個對象在一段時間內能做幾次，擋暴力破解與濫用 |
| **暴力破解** | 用程式一直試（密碼、帳號），靠次數撞對 |
| **`Retry-After`** | 429 回應的標頭，告訴前端「還要等幾秒才能再試」 |
| **`X-Forwarded-For`** | 經過代理時，代理加上的「原始來源 IP」標頭。使用者也能自己加，所以只能信「自己的代理加的那一個」 |
| **`NUM_PROXIES`** | 告訴 DRF 前面有幾層自己的代理，據此從 `X-Forwarded-For` 取出可信的來源 |
| **Cloudflare Tunnel** | 讓外部網路連到本機後端的通道；後端看到的連線都來自 cloudflared，真正來源在標頭裡 |
| **cache（快取）** | 暫存資料的地方，限流的「已經用了幾次」記在這裡；預設存在程式記憶體，多個 worker 時不共用 |
| **worker** | 正式環境同時開多個程式行程一起處理請求，每個就是一個 worker |
| **`python-decouple`** | 讀 `.env` 與環境變數的套件；`.env` 留著空值的那一行會被讀成「空字串」，不等於沒設 |
| **timeout（逾時）** | 等待對方回應的時間上限，超過就放棄。沒設的話對方一卡住，自己也會一直等下去 |
| **重試（retry）** | 失敗後再試一次。只該用在暫時性的錯誤（連線失敗、對方忙碌），金鑰錯誤這類重試也沒用 |
| **JWT** | 登入後後端發的「通行證」，簽好就一直有效到過期，本身無法被收回；要作廢只能靠額外機制 |
| **access／refresh token** | access 是日常用的短效通行證，refresh 是拿來換新 access 的長效憑證 |
| **blacklist（黑名單）** | 把「已作廢」的 token 記在資料表，驗證時查表。需要資料表 |
| **密碼指紋** | 這次用的作廢機制：token 記著簽發當時密碼的雜湊，密碼一改就對不上。不需要資料表，但只能處理「換密碼」這個事件 |
| **magic bytes** | 檔案開頭的幾個固定位元組，能判斷檔案「真正」的格式（例如 JPEG 開頭是 `FF D8 FF`）。這次沒用，只看副檔名與宣告類型 |
| **mutation（突變驗證）** | 故意把修正拿掉，確認測試會失敗，證明測試真的在保護這個修正 |
