# F1～F7 後端修改紀錄（詳細版）

更新日期：2026-11-09 · 分支：`fix/features`（F1～F7 已全部合併） · PR：#87～#93

## 這份文件是什麼

這是 `fix/features` 這一輪修正的**完整技術紀錄**：每一項當初發現什麼問題、攻擊者可以怎麼利用、程式改了什麼（附修改前後的程式碼）、為什麼這樣設計、怎麼測試、還有什麼限制。

和另一份文件的分工：

| 文件 | 讀者 | 重點 |
|---|---|---|
| [frontend_api_changes.md](frontend_api_changes.md) | 前端（Flutter） | API 行為變了什麼、前端要做什麼、錯誤碼 |
| **本文件** | 後端開發者、專題組員 | 程式怎麼改、為什麼這樣改、怎麼驗證、有什麼限制 |

遇到不熟悉的名詞，請看最後的「[附錄 B：名詞小辭典](#附錄-b名詞小辭典)」。

---

## 0. 總覽

### 0.1 一覽表

| 編號 | 問題（一句話） | 類型 | 嚴重度 | PR | 涉及 app |
|---|---|---|---|---|---|
| F1 | 未登入的遊戲請求被當成「資料庫第一位使用者」 | 認證繞過 | 高 | #87 | games |
| F2 | 作答端點不檢查 session 屬於誰 | IDOR（越權存取） | 高 | #88 | games |
| F3 | market_sort 可讀取／覆蓋他人場次 | IDOR（越權存取） | 高 | #89 | games |
| F4 | 忘記密碼 API 沒有次數限制 | 暴力破解防護 | 中 | #90 | users |
| F5 | 日記照片與錄音是永久公開網址 | 個資外洩 | 高 | #91 | diary、social、dashboard、public_share、users |
| F6 | 刪除帳號後雲端檔案還在 | 個資殘留 | 中 | #92 | users、diary |
| F7 | `round_index` 不合法或重複會 500；寫入沒有 transaction | 輸入驗證＋資料一致性 | 中 | #93 | diary |

### 0.2 規模與測試

下表的「程式」不含文件與測試檔；行數是 `git diff --numstat` 的新增／刪除。

| 編號 | 程式新增／刪除 | 測試新增 | 新增測試數 | 全部測試數 |
|---|---|---|---|---|
| （起點） | — | — | — | 764 |
| F1 | +2／−5 | +55（新檔）、+3／−3 | 3 | 767 |
| F2 | +45／−2 | +161（新檔） | 11 | 778 |
| F3 | +33／−7 | +129（新檔） | 7 | 785 |
| F4 | +51／−0 | +111（新檔）、+3 | 9 | 794 |
| F5 | +95／−15 | +235（新檔） | 15 | 809 |
| F6 | +104／−3 | +224（新檔） | 13 | 822 |
| F7 | +119／−52 | +239（新檔） | 13 | 835 |
| **合計** | **+449／−84** | **約 +1,160** | **71** | **835（另 1 個原本就預期失敗）** |

- F1～F7 合計（不含 `doc/`）：23 個檔案、約新增 1,600 行、刪除 86 行（程式加測試）。
- 這一輪**沒有修改任何資料表**，沒有新增 migration。

### 0.3 共同的做法

七項修正都遵守同樣的規則，之後做 `fix/global` 也沿用：

1. **一個編號 = 一個小分支 = 一個 PR**，commit 訊息用 Conventional Commits（`fix(games)!: …`）。
2. **測試和程式放同一個 commit**，而且一定驗證過「**把修正拿掉，新測試會失敗**」，確認測試不是隨便寫寫就會過。
3. **不改資料表**：用既有欄位解決（例如 F5 把「網址」改存「路徑」，仍用同一個欄位）。
4. **向下相容舊資料**：舊的完整網址、示範資料照常運作。
5. **外部服務失敗不拖垮 API**：Firebase 簽名或刪檔失敗只記錄，不讓整支 API 500。
6. **錯誤格式沿用該區原本的格式**，不趁機改格式（統一格式是 `fix/global` 的事）。
7. **只對自己改到的檔案跑 ruff**；既有檔案本來就有的格式問題不順手重排，避免 PR 混進無關差異。

---

## 1. F1 — 移除「未登入就取第一位使用者」的 fallback

**PR #87** · `fix(games)!: 移除未登入時改用第一位使用者的 fallback` · 分支 `fix/games-auth-fallback`

### 1.1 問題與風險

`games/utils.py` 的 `get_current_user()` 原本長這樣：

```python
def get_current_user(request):
    # 開發測試階段若未登入，暫時取第一位使用者，讓前端還沒串登入也能測試
    if request.user.is_authenticated:
        return request.user
    return User.objects.first()
```

遊戲相關的 `@api_view` 又沒有設定 `permission_classes`，而全域預設是 `AllowAny`（任何人都能存取）。所以：

- 任何人**不用登入**，就能用「資料庫第一位使用者」（通常是管理員或最早註冊的人）的身分開始遊戲、寫入成績。
- 第一位使用者的歷史成績可以被未登入的人讀到（`history` 端點）。
- 前端漏帶 token **不會有任何錯誤**，資料卻默默寫進別人的帳號，很難發現。

使用處共 13 個（`fridge_check`、`market_shopping`、`market_route`、`memory_recall` 的 view）。

### 1.2 修改

```python
def get_current_user(request):
    """有登入（JWT）時回傳登入者；未登入時回傳 None，
    呼叫端要自己回 404 USER_NOT_FOUND。"""
    if request.user.is_authenticated:
        return request.user
    return None
```

同時移除不再需要的 `from users.models import User`。

### 1.3 設計決策

- **為什麼不改 view？** 各遊戲 view 本來就寫了 `if user is None: 回 404 USER_NOT_FOUND`（當初是為了「資料庫沒有任何使用者」的情況），所以只改這一個函式，13 個使用處自動得到正確行為。改動面積最小，風險最低。
- **為什麼未登入是 404 而不是 401？** 這是沿用 view 既有的回應，不在這個 PR 順便改。「全域預設要登入、未登入一律 401」是 `fix/global` 的 G2。
- **`market_route`／`memory_recall` 的 session 端點怎麼辦？** 它們先查 session，再用 `user is None or session 的 user_id != user.id` 判斷，未登入時自然落到 403 `FORBIDDEN`。這兩處原本就有擁有者檢查，只是之前被 fallback 蓋掉了。

### 1.4 測試

| 檔案 | 內容 |
|---|---|
| `games/tests_utils.py`（修改） | 登入者回傳自己；**未登入即使資料庫有使用者也回 `None`**（原本是「回傳第一位」的測試，改成相反的預期）；資料庫沒有使用者回 `None` |
| `games/tests_anonymous.py`（新） | 資料庫有使用者、但沒登入時，4 個開場端點（`fridge-check/sessions/`、`market-shopping/sessions/`、`market-route/start/`、`memory-recall/start/`）都回 404 `USER_NOT_FOUND`；**不會建立任何 `GameSession`**；已登入的使用者仍可正常開始遊戲 |

既有的 365 個 games 測試沒有任何一個依賴 fallback（修改後全過）。

### 1.5 已知限制

- 作答類端點（`fridge-check` 的 `answers/`、`market-shopping` 的 `item-answers/`、`change-answers/`）**不呼叫** `get_current_user`，所以 F1 沒有擋到它們，要靠 F2。
- 未登入仍回 404 而非 401（見 1.3）。

---

## 2. F2 — 作答端點檢查 session 擁有者

**PR #88** · `fix(games): 遊戲作答前檢查 session 擁有者` · 分支 `fix/games-session-owner`

### 2.1 問題與風險（IDOR）

IDOR（Insecure Direct Object Reference，不安全的直接物件參照）：系統只憑網址上的 id 找資料，卻不確認「這筆資料是不是你的」。

```python
# 修改前（fridge_check/views.py、market_shopping/views.py）
session = services.get_session(session_id)
if session is None:
    return ... 404 SESSION_NOT_FOUND
if session["status"] == "finished":
    return ... 400 SESSION_COMPLETED
# 直接判題、寫入作答紀錄
```

只要知道（或猜到）別人的 `session_id`，就能替對方作答、改掉對方的成績與紀錄。對照組：`market_route`、`memory_recall` 早就有擁有者檢查。

### 2.2 修改

**1) 新增共用函式**（`games/utils.py`）：

```python
def forbidden_unless_owner(request, session):
    """session 是本人的 → 回傳 None；
    不是本人、或沒登入 → 回傳 403 FORBIDDEN 的 Response。"""
    user = get_current_user(request)
    if user is None or session["user_id"] != user.id:
        return Response(
            {"success": False, "data": None,
             "error": {"code": "FORBIDDEN", "message": "這場遊戲不屬於目前的使用者"}},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None
```

**2) 三個作答端點在「找到 session」之後呼叫它**：

```python
forbidden = forbidden_unless_owner(request, session)
if forbidden is not None:
    return forbidden
```

| 端點 | 檔案 |
|---|---|
| `fridge-check/sessions/<id>/answers/` | `games/fridge_check/views.py`（`submit_answer`） |
| `market-shopping/sessions/<id>/item-answers/` | `games/market_shopping/views.py`（`submit_item_answer`） |
| `market-shopping/sessions/<id>/change-answers/` | 同上（`submit_change_answer`） |

### 2.3 設計決策

- **判斷順序：格式 → 找 session → 擁有者 → 是否已結束 → 判題。** 擁有者檢查放在「是否已結束」之前，否則別人可以藉由 `SESSION_COMPLETED` 與否探測對方的 session 狀態。放在「找 session」之後，所以不存在的 id 仍回 404（不洩漏「存在但不是你的」之外的資訊）。
- **為什麼做成共用函式？** 同樣的檢查要放在三個地方，而且 `market_route` / `memory_recall` 各有自己的一套。先抽出一個給新程式用，不去動已經正確的舊程式，降低風險。
- **`session["user_id"]` 從哪來？** `session_service._to_dict()` 直接讀資料庫外鍵 `session.user_id`，**不依賴**各遊戲塞在 `state` 裡的 `user_id`（舊寫法），所以不會被遊戲自己的狀態影響。
- **回應格式**：沿用 `market_route` 既有的 403 body，前端可以共用同一段處理。

### 2.4 測試（`games/tests_session_owner.py`，11 個）

| 類別 | 測試 |
|---|---|
| 冰箱檢查（4） | 本人可作答；**別人 → 403 且沒寫入作答紀錄**；**未登入 → 403 且沒寫入**；不存在的 session 仍是 404 |
| 市場買菜（7） | 選菜：本人可作答／別人 403 且沒寫入／未登入 403；找零：本人不被擋／別人 403 且沒寫入／未登入 403；不存在仍是 404 |

「沒寫入」是用 `session_service.get_session(...)["step_records"]` 數量確認，證明被擋下時不只是回了 403，資料也真的沒被動到。

驗證：還原兩個 view 的修改後，**6 個**「別人／未登入」測試失敗。

### 2.5 已知限制

- `market_sort` 不在這個 PR（它的問題在 `get_or_create_session`，見 F3）。
- 擁有者檢查的邏輯在 view 層；service 層（`session_service.get_session`）本身不檢查。

---

## 3. F3 — market_sort 的 session 擁有者檢查

**PR #89** · `fix(games): market_sort 比對 session 擁有者，避免讀取或覆蓋他人場次` · 分支 `fix/games-market-sort-owner`

### 3.1 問題與風險

`market_sort` 的 `MarketSortSubmitView` 本來就要求登入（`IsAuthenticated`），問題在 service：

```python
# 修改前（games/session_service.py）
def get_or_create_session(game_type, session_id, initial_state=None, user=None, is_pretest=False):
    game = _get_game(game_type)
    try:
        session = GameSession.objects.get(game=game, client_session_id=str(session_id))
        return _to_dict(session), False          # ← 完全不看 session 是誰的
    except GameSession.DoesNotExist:
        ...建立新的
```

`client_session_id` 是前端自己產生的，資料庫的唯一限制是 `(game, client_session_id)`，**不含 user**。所以 B 送出 A 用過的 id：

| A 的場次狀態 | B 送出相同 id 的後果 |
|---|---|
| 已完成 | `_build_response(request.user, session)` 用 **A 的** `session["result"]` 當 B 的 `current_score` → **洩漏 A 的成績** |
| 還沒結束 | 程式往下走：驗證 → 計分 → `finish_session(...)` → **用 B 的資料覆蓋 A 的 session** |

### 3.2 修改

**service 層**（`games/session_service.py`）：

```python
class SessionOwnerMismatch(Exception):
    """session_id 已經存在，但屬於另一位使用者時拋出。"""

# get_or_create_session 找到既有 session 時：
requester_id = user.id if user is not None else (initial_state or {}).get("user_id")
if requester_id is not None and session.user_id != requester_id:
    raise SessionOwnerMismatch(session_id)
return _to_dict(session), False
```

**view 層**（`games/market_sort/views.py`）：把 `get_or_create_session(...)` 包進 `try`，接住例外回 403：

```python
except session_service.SessionOwnerMismatch:
    return Response(
        {"success": False, "data": None,
         "error": {"code": "FORBIDDEN", "message": "這場遊戲不屬於目前的使用者"}},
        status=status.HTTP_403_FORBIDDEN,
    )
```

### 3.3 設計決策

- **為什麼在 service 層擋，不是只在 view 擋？** service 是共用層，在這裡擋可以保證「**根本不會取得別人的 session**」，後面不管 view 怎麼寫都不可能誤用到。view 只負責把例外轉成 403。
- **為什麼用例外，而不是回傳特殊值？** 這個函式回傳 `(session, created)`，再多一種回傳形狀容易被呼叫端漏處理；例外不會被默默忽略。
- **`requester_id` 為什麼有兩個來源？** `get_or_create_session` 的 `user` 參數是可選的，舊寫法是把 `user_id` 放進 `initial_state`（`_resolve_user` 也是這樣相容）。兩個來源都沒有時（`None`）不檢查，維持舊行為，避免影響沒傳 user 的呼叫端。
- **保留唯一限制不變。** 如果改成 `(game, user, client_session_id)` 唯一，要新增 migration 並可能破壞既有資料；而且「全站唯一」本身是合理的。因此 B 用到 A 的 id 時回 403，要求前端用 UUID。

### 3.4 測試（`games/market_sort/tests_owner.py`，7 個）

| 類別 | 測試 |
|---|---|
| API 層（4） | 別人送出**已完成**場次的 id → 403，不洩漏成績；別人送出**未結束**場次的 id → 403，且 session 的 `user` 仍是原主、`status` 仍是 `in_progress`、`result` 仍是空（**沒被覆蓋**）；本人重送同一個 id → 冪等（回相同結果）；別人用**不同**的 id 正常建立 |
| service 層（3） | 同一人取得既有 session（`created=False`）；他人拋 `SessionOwnerMismatch`；只用 `initial_state["user_id"]` 識別的他人也會拋 |

驗證：還原 `views.py` 與 `session_service.py` 後，**4 個**測試失敗（2 failure＋2 error）。

寫測試時修了一個自己的錯誤假設：未結束的 session 的 `result` 是 `None`，不是 `{}`；修正的是測試，不是程式。

### 3.5 已知限制

- 用到別人 id 的使用者會一直收到 403（他得換新的 id）。前端用 UUID 即可避免。
- `session_service` 其他函式（`update_session`、`save_step`、`finish_session`）仍用 `session_id` 直接查，不檢查擁有者；目前只有通過 `get_or_create_session` 的流程會呼叫它們，風險已被擋在入口。

---

## 4. F4 — 忘記密碼 API 加入請求次數限制

**PR #90** · `fix(users): 忘記密碼 API 加入請求次數限制` · 分支 `fix/users-password-reset-throttle`

### 4.1 問題與風險

`PasswordResetCheckView`（確認帳號存在）與 `PasswordResetView`（設定新密碼）都是 `AllowAny`，而且：

- 沒有任何次數限制，可以無限次嘗試，也可以用程式大量掃描帳號是否存在。
- 重設密碼只需要帳號名稱（沒有舊密碼、驗證碼）。

### 4.2 範圍說明（重要）

討論時有三個方案：

| 方案 | 說明 | 結果 |
|---|---|---|
| 生日＋手機號碼 | 重設時多送註冊時的生日與手機，兩者都對才能改 | 未採用 |
| **只加次數限制** | 限制同帳號／同來源的嘗試次數 | **採用（使用者選擇）** |
| 簡訊／Email 驗證碼 | 最安全，但要串接服務、新增欄位 | 工程量大，之後再做 |

因此 **F4 並沒有解決「知道帳號名稱就能重設密碼」這件事**，只是讓暴力破解與大量掃描變貴。這點已寫進 PR 描述與前端文件。

### 4.3 修改

新增 `users/throttles.py`，兩個 DRF throttle 類別（用 `SimpleRateThrottle`）：

```python
class PasswordResetIPThrottle(SimpleRateThrottle):
    scope = "password_reset_ip"
    rate = "30/hour"
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}

class PasswordResetUsernameThrottle(SimpleRateThrottle):
    scope = "password_reset_username"
    rate = "10/hour"
    def get_cache_key(self, request, view):
        data = request.data if isinstance(request.data, dict) else {}
        username = str(data.get("username", "")).strip().lower()
        if not username:
            return None            # 沒帶帳號：不計入，後面的欄位驗證會回 400
        digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}
```

兩支 View 各加一行：

```python
throttle_classes = [PasswordResetIPThrottle, PasswordResetUsernameThrottle]
```

超過限制時，DRF 丟出 `Throttled`，專案原本的 `config/exceptions.py` 已經會轉成：

```json
{"success": false, "data": null,
 "error": {"code": "TOO_MANY_REQUESTS", "message": "操作太頻繁了，請稍後再試"}}
```

HTTP 429，並帶 `Retry-After` 標頭。

### 4.4 設計決策

- **為什麼 `rate` 寫在類別上，不放 `settings.py`？** DRF 的 `DEFAULT_THROTTLE_RATES` 是全域設定，而 `settings.py` 的調整屬於 `fix/global`（G1～G3）。放在類別上讓 F4 完全獨立，不會和另一個分支改同一個檔案而衝突。
- **兩層，而且「帳號」才是主要防線。** IP 可以偽造（例如自己加 `X-Forwarded-For` 標頭），攻擊者換 IP 就能繞過 IP 限制；但要重設的是哪個帳號是固定的，所以針對帳號的限制才擋得住「針對某人反覆嘗試」。
- **兩支 API 共用同一個 `scope`，所以共用計數。** 「確認帳號」＋「設定新密碼」一輪算 2 次，10 次／小時 ≈ 5 輪完整流程，給輸錯的長者留了餘裕。
- **帳號名稱先 `strip().lower()` 再雜湊。** 避免 `" 0912345678 "` 與 `"0912345678"` 被當成不同帳號繞過；雜湊避免特殊字元或過長字串變成 cache key 的問題。
- **沒帶 `username` 時 `get_cache_key` 回 `None`。** DRF 約定回傳 `None` 表示不計入，後面 serializer 會回 400 `VALIDATION_ERROR`，維持原本行為。
- **帳號不存在仍回 404 `ACCOUNT_NOT_FOUND`。** 沒有改成不洩漏，因為註冊的 `USERNAME_TAKEN` 一樣可以探測帳號，而且改掉會讓輸錯帳號的長者得不到提示。

### 4.5 測試

`users/tests/test_password_reset_throttle.py`（新，9 個）：

| 測試 | 驗證 |
|---|---|
| 同一帳號被限制 | 第 10 次 200、第 11 次 429，body 格式正確且有 `Retry-After` |
| 不存在的帳號也計次 | 否則攻擊者可以用不存在的帳號無限試 |
| 確認與重設共用計數 | 先 10 次確認，第 11 次的重設 429 |
| 被擋的重設不會改密碼 | 密碼仍是舊的 |
| 忽略大小寫與空白 | `" 0912345678 "` 與原帳號共用計數 |
| 其他帳號不受影響 | 一個帳號被鎖，另一個仍可用 |
| 同一來源掃描多帳號 | 30 個不同帳號後第 31 次 429 |
| 沒帶帳號不被限制 | 連送 12 次仍是 400 |
| 一般流程不受影響 | 確認帳號 → 重設密碼成功，新密碼可用 |

既有的 `users/tests/test_password_reset.py` 在兩個 `setUp` 加 `cache.clear()`，因為計數存在 cache，不清的話前面測試累積的次數會讓後面的測試誤觸 429。

驗證：拿掉 View 的 `throttle_classes` 後，**6 個**限速測試失敗。

### 4.6 已知限制

- **沒有身分驗證**（見 4.2）。
- **計數存在記憶體快取。** `settings.py` 沒有設定 `CACHES`，Django 預設是單一 process 的 `LocMemCache`。用 gunicorn 開多個 worker 時，每個 worker 各自計數，實際上限等於「10 × worker 數」。正式環境要改用 Redis 等共用快取。
- **可被拿來鎖別人。** 被限制的是帳號名稱，知道別人帳號的人可以故意連打 10 次，讓對方一小時內無法使用忘記密碼。這是次數限制本身的取捨。
- 登入、註冊、改密碼的限速不在 F4（屬於 `fix/global` 的 G3）。

---

## 5. F5 — 日記照片與錄音改用簽名網址，不再公開

**PR #91** · `fix(diary): 日記照片與錄音改用簽名網址，不再公開` · 分支 `fix/diary-private-media`

### 5.1 問題與風險

```python
# 修改前（diary/external.py）
blob.upload_from_file(file_obj, ...)
blob.make_public()
return blob.public_url           # 永久有效、任何人拿到網址就能看
```

日記是 55 歲以上長者的私人內容（照片、說話錄音）。網址一旦外流（截圖、轉傳、瀏覽器歷史），**永遠**有效。

### 5.2 修改概念

```
        上傳時                              讀取時
  檔案 ──► Firebase（私有）           資料庫存的「路徑」
  資料庫存「路徑」                        │
  voice-diary/images/3f2a.jpg            ▼
                                    media_url(路徑) ──► 有時效的簽名網址 ──► 前端
```

- **簽名網址（signed URL）**：Firebase 用服務帳號金鑰替「某個檔案、某段時間」簽一個網址，過期後失效，且不需要把檔案設成公開。

### 5.3 修改內容

**1) `diary/external.py`：上傳預設私有**

```python
def upload_to_firebase(file_obj, folder, public=False):
    ...
    if public:                       # 只有頭像用
        blob.make_public()
        return blob.public_url
    return blob.name                 # 日記預設：回傳「檔案路徑」
```

頭像（`users/views.py` 的 `save_avatar_file`）改傳 `public=True`，**行為維持不變**。

**2) 新增 `diary/media.py`：`media_url()`**

```python
def media_url(stored):
    if not stored or is_full_url(stored):   # 空值、舊的完整網址、示範資料 → 原樣回傳
        return stored
    try:
        bucket = storage.bucket(app=firebase_app)
        seconds = getattr(settings, "MEDIA_SIGNED_URL_SECONDS", 6 * 60 * 60)
        return bucket.blob(stored).generate_signed_url(
            version="v4", expiration=timedelta(seconds=seconds), method="GET")
    except Exception as e:
        logger.error(...)
        return None                          # 簽名失敗 → null，不讓 API 500
```

**3) 11 個讀取點都改成 `media_url(...)`**

| 檔案 | 位置 |
|---|---|
| `diary/views.py`（8 處） | 月曆、上傳照片的回應、完成日記、日記詳情（照片＋每輪錄音）、回覆日記的回應、複習（昨天／去年同日） |
| `social/utils.py` | `serialize_post`（動態牆貼文、貼文詳情、分享日記） |
| `public_share/views.py` | 公開分享頁的照片 |
| `dashboard/weekly_report.py`、`dashboard/views.py` | 週報（見下） |

**4) 週報的特殊處理**

週報 API 會把整份內容存成快照（`WeeklyReport.report`，一個 JSONField）。簽名網址有時效，**不能存進快照**，否則存下的是會過期的網址。做法：

```python
# dashboard/views.py
record.report = data                                  # 快照存「路徑」
...
return Response({"success": True,
                 "data": weekly_report.with_signed_media(data), "error": None})
# with_signed_media(): 複製一份，只把 diary.entries[].photo_url 換成簽名網址，不改動原 dict
```

### 5.4 設計決策

- **為什麼把「路徑」存進原本的 `image_path`／`audio_path` 欄位，而不是新增欄位？** 不用 migration（符合專案「避免改資料表」的原則），而且 `startswith("http")` 就能區分新舊格式，舊資料零成本相容。
- **為什麼用 v4 簽名網址？** v4 是 Google 目前建議的版本，支援到 7 天有效期。
- **為什麼預設 6 小時？** 太短（例如 15 分鐘）：長者把畫面開著，圖片會裂掉；太長：外流後的風險視窗變大。6 小時涵蓋一次完整使用，也可用 `settings.MEDIA_SIGNED_URL_SECONDS` 調整。
- **為什麼頭像維持公開？** 頭像本來就是要顯示給別人看的資料（動態牆、留言），任務範圍是「日記照片與錄音」。以 `public` 參數控制，兩種需求用同一個函式。
- **為什麼簽名失敗回 `None` 而不是丟例外？** 一張圖片簽不出來不該讓整個日記月曆（可能 30 筆）都 500。前端拿到 `null` 顯示預設圖即可，錯誤會寫進 log。
- **公開分享頁的 `og:image`**（給 LINE／Facebook 預覽用）也會是簽名網址，6 小時內有效；社群平台通常在分享當下就會抓取，影響很小。

### 5.5 測試（`diary/tests_media.py`，15 個）

不連真的 Firebase：用假的 bucket（`MagicMock`）與假的 `config.firebase` 模組。

| 類別 | 測試 |
|---|---|
| `media_url` 單元（5） | 空值原樣回傳；完整網址原樣回傳且**完全不碰 Firebase**；路徑 → 簽名網址（驗證 `version=v4`、`method=GET`、`expiration=6 小時`）；可用 settings 調有效期；簽名失敗回 `None`、不丟例外 |
| 上傳可見性（2） | 預設上傳**不呼叫** `make_public`、回傳路徑；`public=True` 才公開並回傳公開網址 |
| 日記 API（5） | 詳情回簽名的照片與錄音網址；舊的公開網址照常運作；月曆回簽名網址；簽名失敗時 API 仍 200、欄位為 `null`；上傳照片後資料庫存的是路徑、回應是簽名網址 |
| 其他端點（3） | 動態牆貼文回簽名網址（且回應中不含原始路徑）；公開分享頁用簽名網址；**週報快照存路徑、回應是簽名網址** |

驗證：還原所有來源修改後，**9 個**測試失敗。

### 5.6 已知限制（重要）

- **既有的檔案仍然是公開的。** 之前上傳的檔案已經被 `make_public()`，資料庫存的完整網址仍可被任何人開啟。需要另外寫一次性腳本：把舊檔案改回私有（`blob.make_private()`）並把資料庫的完整網址轉成路徑。這會動到線上資料，要先備份、先在測試環境演練。
- 簽名需要服務帳號金鑰（`secrets/firebase-key.json`）具備簽名權限；目前的金鑰可以。
- 每次呼叫 API 都重新簽名（本機 RSA 運算，不連網路），一頁 30 筆可接受；若之後量變大可考慮快取。
- 前端圖片快取若用完整網址當 key，每次取得的網址都不同會重複下載（已在前端文件說明）。

---

## 6. F6 — 刪除帳號時一併清除雲端與本機檔案

**PR #92** · `fix(users): 刪除帳號時一併清除雲端與本機檔案` · 分支 `fix/users-delete-cloud-files`

### 6.1 問題與風險

```python
# 修改前（users/views.py）
request.user.delete()      # 資料庫的資料級聯刪除，但 Firebase 上的檔案完全沒動
```

使用者刪除帳號，期待自己的資料消失；但日記照片、錄音、頭像還留在 Firebase，而且（F5 之前上傳的）是公開網址，帳號刪掉後別人仍然看得到。

### 6.2 修改

**1) `diary/external.py` 新增兩個函式**

- `blob_name_from_stored(value, bucket_name)`：把資料庫存的值換算成 bucket 內的檔案路徑。

  | 輸入 | 結果 |
  |---|---|
  | `voice-diary/images/a.jpg`（路徑） | 原樣回傳 |
  | `https://storage.googleapis.com/<本 bucket>/voice-diary/avatars/a%20b.jpg` | `voice-diary/avatars/a b.jpg`（還原 URL 編碼） |
  | `https://firebasestorage.googleapis.com/v0/b/<本 bucket>/o/voice-diary%2Faudio%2Fx.wav?alt=media` | `voice-diary/audio/x.wav` |
  | 空值、`/media/...`（本機）、別人網站、**別的 bucket**、示範資料網址 | `None`（**不能刪**） |

- `delete_from_firebase(stored_values)`：盡力刪除，回傳成功數量。重複只刪一次；不是本 bucket 的略過；單一檔案失敗只記錄、繼續下一個；Firebase 連不上回 0；**全程不丟例外**。沒有要刪的檔案時**不會連線 Firebase**。

**2) `users/views.py`**

```python
def collect_user_media(user):
    # 頭像、日記照片、日記錄音、回覆錄音、貼文照片 → set（自動去重）
    ...

def remove_user_media(values):
    local = {v for v in values if v.startswith(settings.MEDIA_URL)}
    delete_from_firebase(values - local)         # 雲端
    for value in local:                          # 本機 media 的頭像
        default_storage.delete(value[len(settings.MEDIA_URL):])   # 失敗只記錄

# MeView.delete
user = request.user
media = collect_user_media(user)                  # ① 先收集（刪了就找不到了）
with transaction.atomic():
    user.delete()                                 # ② 刪資料庫
    transaction.on_commit(lambda: remove_user_media(media))   # ③ 確定寫入後才刪檔案
return Response(status=status.HTTP_204_NO_CONTENT)
```

### 6.3 設計決策

- **為什麼先收集、再刪？** `user.delete()` 會級聯刪除日記、回覆、貼文，這些資料列一消失就查不到有哪些檔案了。
- **為什麼用 `transaction.on_commit`？** 如果先刪檔案、再刪資料庫，資料庫刪除失敗（例如例外）時，帳號還在，檔案卻沒了。`on_commit` 保證「資料庫真的刪成功才動檔案」。反過來，檔案刪除失敗只會留下沒人參照的孤兒檔案（可以之後清理），風險比較小。
- **為什麼刪檔案失敗不擋住刪帳號？** 使用者要刪帳號是他的權利，不能因為 Firebase 暫時掛了就讓他刪不掉。失敗會寫 log。
- **為什麼要辨識 URL？** 頭像和 F5 以前的日記檔案存的是完整網址；不辨識就刪不到。但**也因此必須嚴格比對 bucket**：示範資料、別人的網址不能亂刪。
- **為什麼 `values - local`？** 本機 `/media/...` 路徑交給 `default_storage` 刪；不要讓它們進 Firebase 流程。

### 6.4 測試（`users/tests/test_delete_account_files.py`，13 個）

| 類別 | 測試 |
|---|---|
| `blob_name_from_stored`（4） | 路徑原樣；`storage.googleapis.com` 網址（含 URL 編碼）；`firebasestorage.googleapis.com` 網址；7 種「不是我們的」都回 `None`（空值、本機路徑、外部網址、別的 bucket、示範資料、只有 bucket 沒有檔名） |
| `delete_from_firebase`（4） | 沒東西刪就不連 Firebase；重複只刪一次、外部略過；一個失敗不影響其他；Firebase 連不上回 0 |
| 刪帳號 API（4） | **刪的檔案清單剛好是預期的 4 個**（頭像、日記照片、回覆錄音、舊公開網址；排除示範資料與重複的貼文照片）；密碼錯誤什麼都不刪；雲端失敗仍 204 且帳號已刪；**不會動到別人的檔案** |
| 本機頭像（1） | 暫存目錄的頭像檔案被刪 |

測試時用 `captureOnCommitCallbacks(execute=True)`：Django 的 `TestCase` 把整個測試包在 transaction 裡，不會真的 commit，所以 `on_commit` 要用這個方式觸發。

驗證：只還原 `users/views.py` → 2 個測試失敗；整個移除新函式 → 測試模組 `ImportError`。

### 6.5 已知限制

- **同步逐一刪除**：檔案很多的帳號（例如 30 篇日記 × 5 個檔案）回應會變慢。之後可改成背景處理（Celery／thread）。
- **不重試**：刪除失敗只留 log，檔案成為孤兒；需要定期清理的腳本才能補。
- 更換或移除頭像時，**舊頭像檔案不會被刪**（不在範圍內）。
- `collect_user_media` 沒有涵蓋「其他人對這個使用者貼文的留言」之類的檔案——目前留言沒有檔案，所以沒問題。

---

## 7. F7 — 回覆日記：驗證 `round_index` 並加上 transaction

**PR #93** · `fix(diary): 回覆日記驗證 round_index，寫入改用 transaction` · 分支 `fix/diary-reply-validation`

### 7.1 問題與風險

`DiaryReplyView.post` 與 `DiaryFinalizeView.post`（`diary/views.py`）有五個問題：

| # | 問題 | 後果 |
|---|---|---|
| 1 | `round_index = int(round_index)` 沒有 try | 傳 `"abc"`、`"1.5"` → `ValueError` → **500** |
| 2 | `round_index` 是 32 位元整數欄位，沒限制範圍 | 傳 `99999999999999999999` → 資料庫 `DataError` → **500** |
| 3 | `if not round_index` 把整數 `0` 當成「沒傳」 | 錯誤訊息誤導（說錄音沒收到） |
| 4 | `(diary, round_index)` 有唯一限制，重複輪次直接寫入 | 同一輪送兩次（網路重試）→ `IntegrityError` → **500**；而且語音辨識與上傳都白做了 |
| 5 | 新增回覆、更新日記狀態、（finalize）寫分析結果與 AI 內容都**不在同一個 transaction** | 中途失敗留下半完成資料；同一篇同時 finalize 兩次會重複分析、**重複呼叫 AI（花錢）** |

### 7.2 修改

**1) 輸入驗證**

```python
MAX_REPLY_ROUNDS = 4        # 與 is_done 的判斷一致

def parse_round_index(raw):
    """只接受 1～4 的整數；字串 "1"（multipart）與整數 1（JSON）都可以。"""
    if isinstance(raw, bool): return None            # True 不能當 1
    if isinstance(raw, int):  value = raw
    elif isinstance(raw, str):
        try: value = int(raw.strip())
        except ValueError: return None               # "abc"、"1.5"
    else: return None                                # 1.0、[1]、{...}、None
    return value if 1 <= value <= MAX_REPLY_ROUNDS else None
```

**2) 回覆流程**（先便宜的檢查，再做昂貴的事，最後才寫資料庫）

```text
找日記 ─► 已完成? ─► 檢查 audio 與 round_index 是否有送
                       │ 沒送 → 400 INVALID_AUDIO（維持原樣）
                       ▼
                    parse_round_index → 不合法 → 400 INVALID_ROUND_INDEX
                       ▼
                    這一輪已回答過? → 409 ROUND_ALREADY_ANSWERED  ← 在 Whisper 之前
                       ▼
                    Whisper 語音辨識 → Firebase 上傳        （慢，在 transaction 之外）
                       ▼
        with transaction.atomic():                          （快，只有資料庫與 AI 追問）
            鎖住這篇日記（select_for_update）
            再檢查一次：日記剛被完成? / 這一輪剛被搶走?
              → 是：刪除剛上傳的錄音，回 400 / 409
            新增 DiaryReply、更新 diary 狀態與 pending_question
```

**3) finalize 整段放進 transaction**

```python
with transaction.atomic():
    diary = Diary.objects.select_for_update().get(pk=diary.pk)
    if diary.status == "done":                       # 第二個同時請求等到鎖後，看到已完成
        return self._build_response(diary, http_status=200)   # → 直接回傳，不重複呼叫 AI
    ...分析、DiaryAnalysis.update_or_create、AI 產生內容、diary.save()
```

任何一步丟出例外 → 整個 transaction 還原 → 日記維持原狀態（不會「有分析結果、卻停在 processing」）。

### 7.3 設計決策

- **為什麼上限是 4？** 程式本來就以 `reply_count >= 4` 判斷 `is_done`，一篇日記最多問答 4 輪；把常數抽成 `MAX_REPLY_ROUNDS`，驗證和 `is_done` 用同一個值。
- **為什麼「缺少」和「不合法」用不同的錯誤碼？** 缺少維持原本的 `INVALID_AUDIO`（既有前端可能依賴）；「有送但不合法」才是新的 `INVALID_ROUND_INDEX`。
- **為什麼 Whisper／Firebase 上傳放在 transaction 之外？** 這兩步要幾秒鐘，如果包在 transaction 裡，資料庫連線與鎖會被佔住這麼久。transaction 裡只放快的資料庫操作。
- **那「AI 追問」（`generate_follow_up`）為什麼在鎖裡面？** 它要用到「鎖內重新計算的回覆數」才能決定是不是最後一輪（`is_done`）。這一步目前有內建 fallback（失敗會回預設問題），而且只鎖**同一篇日記**，不影響別人。
- **為什麼重新檢查還要刪除剛上傳的錄音？** 上傳已經完成才發現這輪被別人搶先，這個錄音沒有任何資料列參照，不刪就是孤兒檔案。使用 F6 新增的 `delete_from_firebase`（盡力而為）。
- **finalize 為什麼把 AI 也放進 transaction？** 為了讓第二個請求**等**第一個完成而不是各自呼叫一次 AI（省錢＋一致）。代價是鎖住這一篇日記幾秒，只有「同一篇日記的重複請求」會被擋，可以接受。
- **為什麼回覆重複輪次回 409 而不是 400？** 409 Conflict 的語意就是「請求和資源目前狀態衝突」，前端可以把它當成「這一輪已經成功」（常見於網路重試）。
- **錯誤格式維持 `{"error": {...}}`**（沒有 `success`）：這是 `diary` app 既有的格式，統一格式是 `fix/global`（G5/G6）。為了不在三個地方重複寫同樣的 `Response({...})`，順便加了一個 `_error(code, message, status)` 小函式。

### 7.4 測試（`diary/tests_reply_validation.py`，13 個）

| 類別 | 測試 |
|---|---|
| `parse_round_index`（2） | 合法值：`1`、`"1"`、`" 2 "`、`"+3"`、`4`；非法值：`None`、`""`、`"abc"`、`"1.5"`、`1.0`、`True`、`False`、`0`、`-1`、`5`、超大數字、`[1]`、`{"a": 1}` |
| 回覆 API（8） | 不合法值（6 種）→ 400 且 **Whisper／上傳完全沒被呼叫**、沒寫入；缺少 round_index 或 audio → 仍是 `INVALID_AUDIO`；合法值正常；重複輪次 → 409 且沒做任何事；**辨識期間被別的請求搶走這一輪** → 409、錄音被刪除、只有 1 筆回覆、日記狀態沒變；**上傳期間日記被完成** → 400、錄音被刪除、沒新增回覆；**儲存時 AI 失敗** → 500，且回覆沒新增、日記狀態與 `pending_question` 都維持原狀（transaction 還原）；第 4 輪 → `is_done=True` 且不呼叫 AI 追問 |
| finalize（3） | AI 失敗 → 分析結果與日記狀態都還原；連打兩次 → 第一次 201、第二次 200、**AI 只被呼叫 1 次**、分析只有 1 筆；沒有有效回覆 → 400 且什麼都沒改 |

「被別的請求搶走」是用 `side_effect` 在語音辨識的 mock 裡先寫入同一輪／把日記改成 done 來**模擬並行**，不用真的開多執行緒（測試才穩定）。

驗證：還原 `diary/views.py` 後 **12 個**斷言失敗（含 subTest）。

### 7.5 已知限制

- **`select_for_update` 在測試用的 SQLite 上會被忽略**，真正的行列鎖只在 PostgreSQL 生效。上面的「並行」測試驗證的是**程式邏輯**（鎖內再檢查一次、失敗還原），不是資料庫鎖本身。建議在 PostgreSQL 環境用兩個並行請求再實測一次。
- 回覆流程裡，AI 追問仍在鎖內（見 7.3）；finalize 的 AI 呼叫也在鎖內，如果 AI 服務極慢，同一篇日記的重複請求會等比較久。後續可為 OpenAI 加 timeout（`fix/global` 的 G9）。
- `diary/views.py` 本來就有的 ruff 問題（過長的行、沒用到的 `date` import、import 排序）**沒有順手處理**，避免 PR 混進無關差異。

---

## 8. 驗證方式與結果

### 8.1 指令

```bash
source venv/bin/activate

# 全部測試（目前 835 個，1 個預期失敗）
python manage.py test --settings=config.settings_test

# 單一模組（以 F5 為例）
python manage.py test diary.tests_media --settings=config.settings_test

# 只對自己改到的檔案檢查（不要 ruff format . 全專案，會動到約 50 個無關檔案）
ruff format <改到的檔案>
ruff check <改到的檔案>
```

### 8.2 「拿掉修正，測試會失敗」的結果

| 編號 | 還原的內容 | 結果 |
|---|---|---|
| F1 | （測試本身改成新預期） | 365 個既有 games 測試全過 |
| F2 | 兩個 view 的檢查 | 6 個失敗 |
| F3 | `views.py`＋`session_service.py` | 4 個失敗（2 failure＋2 error） |
| F4 | 兩支 View 的 `throttle_classes` | 6 個失敗 |
| F5 | 所有讀取點與上傳 | 9 個失敗（8 failure＋1 error） |
| F6 | `users/views.py` | 2 個失敗；整個移除新函式 → `ImportError` |
| F7 | `diary/views.py` | 12 個斷言失敗 |

### 8.3 還沒有做的驗證

- 沒有在真的 PostgreSQL＋多 worker＋真的 Firebase 環境實測（F4 的共用快取、F5 的簽名、F6 的刪檔、F7 的鎖）。以上都是用 mock 驗證程式邏輯。**合併到正式環境前，建議在測試環境手動走一遍。**

---

## 9. 開發過程備註

- **測試的假設錯誤**（F3）：我以為未結束 session 的 `result` 是 `{}`，實際是 `None`。修正的是測試。
- **指令失誤**（F5）：驗證「拿掉修正會失敗」時，我一個 `git stash push` 指令因為檔名引用錯誤沒有成功，後面的 `git stash pop` 卻照常執行，把你原本 `feat/score_standardization` 的舊 WIP stash（一行文件修改）取出來了。發現後立刻放回原樣，內容完全一致。之後所有還原驗證改用 `git diff > patch` ＋ `git apply -R`，不再碰 stash。
- **程式碼多寫一行**（F6）：`collect_user_media` 一度多了一行無意義的程式，馬上自己發現並刪掉，之後有測試保護。
- **合併方式**：#87 依你的指示「直接 merge」；#88～#93 在你詢問「為什麼還沒 merge」之後，我以同樣方式用 merge commit 合併。

---

## 10. 尚未處理的事與後續建議

### 10.1 `fix/features` 的後續（建議優先）

| 優先 | 項目 | 說明 |
|---|---|---|
| 高 | **忘記密碼的身分驗證** | F4 只做了次數限制。建議加「生日＋手機號碼」兩個欄位的驗證（`User.birth_date`、`User.phone` 已存在，不用改資料表）。注意：兩個欄位目前都可以為空，舊帳號沒填的人無法自助重設，需要規劃替代流程 |
| 高 | **舊的公開檔案改成私有** | F5 的後續，一次性腳本，先備份再演練 |
| 中 | 頭像更換／移除時刪除舊檔案 | F6 的延伸 |
| 中 | 刪帳號時檔案改成背景刪除，並提供孤兒檔案清理腳本 | F6 的限制 |
| 低 | F2 的檢查改成 `market_route`／`memory_recall` 也共用 `forbidden_unless_owner` | 目前兩套並存，功能都正確 |
| 低 | F8～F13（效能、時區、診斷性模型清理等） | 見計畫檔 |

### 10.2 `fix/global`（共通問題，規劃中）

| 編號 | 項目 | 備註 |
|---|---|---|
| G1 | `SECRET_KEY`、`DEBUG`、CORS 改讀環境變數 | `SECRET_KEY` 目前寫死在程式碼且已進 git |
| G2 | 預設權限改成 `IsAuthenticated` | 會讓前端大改，建議前端處理完 F1～F7 後再做 |
| G3 | 登入、註冊、改密碼加入限速 | 沿用 F4 的做法；`DEFAULT_THROTTLE_RATES` 屬於這裡 |
| G4 | JWT blacklist 與 rotation、縮短 token 效期 | 需要 migration，要先確認 |
| G5～G6 | 統一回應格式 `common/responses.py` | `diary` 目前沒有 `success` 欄位 |
| G8 | 遊戲 session 加 transaction／鎖 | F7 對日記做了，遊戲那邊（`update_session`、`save_step`）還沒 |
| G9 | OpenAI 加 timeout 與 retry | F7 的鎖會因此受益 |
| G11～G14 | CI、pre-commit、部署文件、外部服務單元測試 | |

---

## 11. 檔案索引

依檔案列出「哪些編號動過它」，方便日後查「這一行是為什麼寫的」。

| 檔案 | 編號 | 說明 |
|---|---|---|
| `games/utils.py` | F1、F2 | `get_current_user` 改回 `None`；新增 `forbidden_unless_owner` |
| `games/session_service.py` | F3 | 新增 `SessionOwnerMismatch`；`get_or_create_session` 檢查擁有者 |
| `games/fridge_check/views.py` | F2 | `submit_answer` 加擁有者檢查 |
| `games/market_shopping/views.py` | F2 | `submit_item_answer`、`submit_change_answer` 加擁有者檢查 |
| `games/market_sort/views.py` | F3 | 接住 `SessionOwnerMismatch` 回 403 |
| `users/throttles.py`（新） | F4 | 兩個忘記密碼限速類別 |
| `users/views.py` | F4、F5、F6 | 套用限速；頭像 `public=True`；`collect_user_media`／`remove_user_media`；刪帳號流程 |
| `diary/media.py`（新） | F5 | `media_url()` |
| `diary/external.py` | F5、F6 | `upload_to_firebase(public=)`；`blob_name_from_stored`、`delete_from_firebase` |
| `diary/views.py` | F5、F7 | 讀取點套 `media_url`；回覆驗證與 transaction |
| `social/utils.py` | F5 | `serialize_post` 套 `media_url` |
| `public_share/views.py` | F5 | 分享頁照片套 `media_url` |
| `dashboard/weekly_report.py`、`dashboard/views.py` | F5 | `with_signed_media`；快照存路徑 |
| `games/tests_utils.py`、`games/tests_anonymous.py` | F1 | |
| `games/tests_session_owner.py` | F2 | |
| `games/market_sort/tests_owner.py` | F3 | |
| `users/tests/test_password_reset.py`、`test_password_reset_throttle.py` | F4 | |
| `diary/tests_media.py` | F5 | |
| `users/tests/test_delete_account_files.py` | F6 | |
| `diary/tests_reply_validation.py` | F7 | |
| `doc/frontend_api_changes.md` | 全部 | 前端對照文件 |

---

## 附錄 A：PR 與 commit 對照

| 編號 | PR | 分支 | commit 標題 |
|---|---|---|---|
| F1 | #87 | `fix/games-auth-fallback` | `fix(games)!: 移除未登入時改用第一位使用者的 fallback` ＋ `docs: 新增前端 API 變更說明（遊戲未登入行為）` |
| F2 | #88 | `fix/games-session-owner` | `fix(games): 遊戲作答前檢查 session 擁有者` ＋ `docs: 更新前端文件，補上 F2 作答端點擁有者檢查` |
| F3 | #89 | `fix/games-market-sort-owner` | `fix(games): market_sort 比對 session 擁有者，避免讀取或覆蓋他人場次` |
| F4 | #90 | `fix/users-password-reset-throttle` | `fix(users): 忘記密碼 API 加入請求次數限制` |
| F5 | #91 | `fix/diary-private-media` | `fix(diary): 日記照片與錄音改用簽名網址，不再公開` |
| F6 | #92 | `fix/users-delete-cloud-files` | `fix(users): 刪除帳號時一併清除雲端與本機檔案` |
| F7 | #93 | `fix/diary-reply-validation` | `fix(diary): 回覆日記驗證 round_index，寫入改用 transaction` |
| 文件 | #94 | `docs/fix-features-summary` | `docs: 整合 F1～F7 後端修正說明，供前端對照修改` |

只有 F1 帶 `!`（Conventional Commits 的破壞性變更標記）；其餘對正常使用的前端流程不造成破壞。

---

## 附錄 B：名詞小辭典

| 名詞 | 白話說明 |
|---|---|
| **JWT** | 登入後後端發給前端的一張「通行證」（一長串字），之後每次請求都要帶在 `Authorization: Bearer ...` 標頭裡，證明你是誰。有 access（短效）和 refresh（長效，用來換新的 access）兩種 |
| **IDOR** | 越權存取。系統只看網址上的 id 就給資料，沒檢查「這是不是你的」。例如把網址的 `session_id` 換成別人的就能看到或改到別人的資料 |
| **403 / 401 / 404 / 409 / 429** | 403＝你已登入但沒有權限；401＝沒登入或 token 無效；404＝找不到；409＝和目前狀態衝突（例如這輪已經回答過）；429＝請求太頻繁 |
| **throttle（限流）** | 限制同一個對象在一段時間內能呼叫幾次，擋暴力破解與濫用 |
| **暴力破解** | 用程式一直試（密碼、帳號），靠次數撞對 |
| **cache（快取）** | 暫存資料的地方。限流的「已經用了幾次」就記在這裡。預設存在程式的記憶體，重啟或多個 worker 時不共用 |
| **worker** | 正式環境會同時開多個程式行程（例如 gunicorn）一起處理請求，每個就是一個 worker |
| **transaction（交易）** | 一組資料庫操作「要嘛全部成功、要嘛全部取消」。像轉帳：扣款與入帳必須一起成功，中途失敗就全部還原 |
| **`select_for_update`（行鎖）** | 在 transaction 裡「鎖住」某一筆資料，其他請求要改同一筆就得排隊等，避免兩個請求同時改造成錯亂（race condition）。只有 PostgreSQL 等資料庫真的會鎖，SQLite 會忽略 |
| **race condition（競態條件）** | 兩件事幾乎同時發生，結果取決於誰先誰後，導致資料不一致。例如同一輪回覆同時送兩次 |
| **`on_commit`** | 註冊一段程式，等「資料庫真的寫入成功」之後才執行。F6 用它確保資料庫刪成功才刪雲端檔案 |
| **冪等（idempotent）** | 同一個請求送一次或送很多次，結果都一樣。例如重送同一個 `session_id` 會拿到同樣的結果，不會重複計分 |
| **簽名網址（signed URL）** | 雲端儲存替「某個檔案、某段時間」產生的臨時網址，過期就失效。檔案本身保持私有 |
| **Firebase Storage / bucket / blob** | Google 的檔案儲存服務。bucket＝一個儲存空間（像資料夾的根）；blob＝裡面的一個檔案 |
| **migration** | 修改資料表結構的紀錄檔。這一輪沒有新增 |
| **mock（模擬）** | 測試時用假物件代替真的外部服務（Firebase、OpenAI、Whisper），這樣測試又快又穩，也不會花錢 |
| **Conventional Commits** | commit 訊息的固定格式：`類型(範圍): 描述`，例如 `fix(games): ...`；類型後加 `!` 代表會破壞既有行為 |
| **merge target（合併目標）** | 小分支做完要合併進去的分支。這一輪是 `fix/features` |
