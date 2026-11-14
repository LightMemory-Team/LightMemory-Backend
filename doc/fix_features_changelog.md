# F1～F14 後端修改紀錄（詳細版）

更新日期：2026-11-14 · 分支：`fix/features`（F1～F14 已全部合併） · PR：#87～#93、#96～#103、F14 合併 PR（見附錄 A）

## 這份文件是什麼

這是 `fix/features` 這一輪修正的**完整技術紀錄**：每一項當初發現什麼問題、攻擊者可以怎麼利用、程式改了什麼（附修改前後的程式碼）、為什麼這樣設計、怎麼測試、還有什麼限制。

和另一份文件的分工：

| 文件 | 讀者 | 重點 |
|---|---|---|
| [frontend_api_changes.md](frontend_api_changes.md) | 前端（Flutter） | API 行為變了什麼、前端要做什麼、錯誤碼 |
| **本文件** | 後端開發者、專題組員 | 程式怎麼改、為什麼這樣改、怎麼驗證、有什麼限制 |

> **F14 是把另一條線（`feat/stage3` 的 rewards）合進來**，與 F1～F13 性質不同，詳見[第 15 章](#15-f14--把-rewards點數與成就納入-fixfeatures)。
>
> **關於測試檔的路徑**：#103 把所有測試搬進各 app 的 `tests/` 資料夾（見[第 14 章](#14-測試檔搬進各-app-的-tests-資料夾pr-103)）。本文件一律寫**搬移後**的新路徑。

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
| F8 | 遊戲歷史紀錄載入全站場次，且每場各查一次資料庫（N+1） | 效能 | 中 | #97 | games |
| F9 | 一次儀表板請求重複掃描全站日記 4 次（週報 2 次） | 效能 | 中 | #98 | dashboard |
| F10 | 週報每次 GET 都呼叫 AI 並寫資料庫 | 成本＋GET 不安全 | 中 | #100、#101 | dashboard |
| F11 | 台灣凌晨的日期用 UTC 計算，少一天 | 時區 | 低 | #99 | games、users |
| F12 | 後台留著失智篩檢與警示等級的診斷性模型 | 產品定位／資料清理 | 中 | #102 | assessments、dashboard |
| F13 | 日記 AI 輸出完全沒檢查；禁用詞不全且誤殺字母 z | 內容安全＋輸入驗證 | 高 | #96 | ai_service、diary |
| F14 | 把 rewards（點數與成就）納入；與 F1～F13 合併後的掃描次數、發點時機問題 | 新功能整合 | 中 | #106、#107＋F14 合併 PR | rewards、diary、dashboard、games、home |
| （整理） | 測試檔散在各 app 根目錄 | 專案結構 | — | #103 | 全部 |

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
- F1～F7 **沒有修改任何資料表**，沒有新增 migration。

F8 起各 PR 的規模（`gh pr view` 的新增／刪除行數，**含測試與文件**）與測試數：

| 編號 | PR | 新增／刪除 | 檔案數 | 新增測試數 | 全部測試數 |
|---|---|---|---|---|---|
| F13 | #96 | +579／−48 | 6 | 30 | 865 |
| F8 | #97 | +377／−29 | 5 | 17 | 882 |
| F9 | #98 | +368／−33 | 5 | 10 | 892 |
| F11 | #99 | +214／−5 | 6 | 18 | 910 |
| F10 | #100 | +247／−14 | 3 | 10 | 920（合併時有 1 個失敗，見 10.5） |
| F10 修正 | #101 | +2／−1 | 1 | 0 | 920 全過 |
| F12 | #102 | +115／−93 | 9 | 6 | 926 |
| 測試搬移 | #103 | +90／−99 | 66 | 0 | 926 |
| F14 | （合併 PR） | 見 15.7 | — | 16（stage3 另帶 40） | 982 |
| **F8～F14 合計** | | | | **147** | **982（另 1 個原本就預期失敗）** |

- 實際合併順序是 F13 → F8 → F9 → F11 → F10 → F12，不是編號順序。
- **F12（刪除兩張表）與 F14（新增 rewards 的兩張表）是這一輪僅有修改資料表的項目**；F8～F11、F13 都沒有動資料表。

### 0.3 共同的做法

F1～F13 都遵守同樣的規則，之後做 `fix/global` 也沿用：

1. **一個編號 = 一個小分支 = 一個 PR**，commit 訊息用 Conventional Commits（`fix(games)!: …`）。
2. **測試和程式放同一個 commit**，而且一定驗證過「**把修正拿掉，新測試會失敗**」，確認測試不是隨便寫寫就會過。
3. **盡量不改資料表**：用既有欄位解決（例如 F5 把「網址」改存「路徑」，F10 把 AI 事實存進原本就是 JSON 的快照）。唯一的例外是 F12，而且事先問過你。
4. **向下相容舊資料**：舊的完整網址、示範資料照常運作。
5. **全部測試通過才 commit**：F10 之後（見 10.5）所有指令都用測試的結束代碼把關，不再只看輸出的最後幾行。
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
| `games/tests/test_utils.py`（修改） | 登入者回傳自己；**未登入即使資料庫有使用者也回 `None`**（原本是「回傳第一位」的測試，改成相反的預期）；資料庫沒有使用者回 `None` |
| `games/tests/test_anonymous.py`（新） | 資料庫有使用者、但沒登入時，4 個開場端點（`fridge-check/sessions/`、`market-shopping/sessions/`、`market-route/start/`、`memory-recall/start/`）都回 404 `USER_NOT_FOUND`；**不會建立任何 `GameSession`**；已登入的使用者仍可正常開始遊戲 |

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

### 2.4 測試（`games/tests/test_session_owner.py`，11 個）

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

### 3.4 測試（`games/market_sort/tests/test_owner.py`，7 個）

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

### 5.5 測試（`diary/tests/test_media.py`，15 個）

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

### 7.4 測試（`diary/tests/test_reply_validation.py`，13 個）

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

## 8. F8 — 遊戲歷史紀錄改在資料庫篩選，消除 N+1

### 8.1 問題與風險

三款遊戲的「歷史紀錄」（`fridge-check/history/`、`market-shopping/history/`，以及 `market-sort/submit/` 回應裡附的歷史）都呼叫 `session_service.list_sessions`。它做了三件浪費的事：

1. 載入**全站所有使用者**的該遊戲場次（不管是誰的）。
2. 每一場的 `_to_dict` 又各自查一次 `step_logs`（逐題作答紀錄）和一次 `session.game`，這就是 **N+1 查詢**（1 次查場次，加上 N 場 × 2 次額外查詢）。
3. 全部載入之後，才在 Python 裡用 `state["user_id"]` 篩出「自己的」場次。

使用者與場次越多越慢；而且「看自己的歷史」每次都付出「全站的代價」。這不是安全漏洞，是會隨使用者成長而惡化的效能問題。

### 8.2 修改

**`games/session_service.py`**

```python
def list_user_sessions(game_type, user_id, status=None, with_steps=False):
    game = _get_game(game_type)
    sessions = GameSession.objects.filter(game=game, user_id=user_id).select_related("game")
    if status is not None:
        sessions = sessions.filter(status=status)
    if with_steps:
        sessions = sessions.prefetch_related("step_logs")
    return [_to_dict(s, with_steps=with_steps) for s in sessions]
```

- 在**資料庫**就用外鍵 `user` 與 `status` 篩選，只讀這位使用者自己的場次。
- `select_related("game")`：把 `game` 用 JOIN 一起查回來，不再每場各查一次。
- `with_steps` 預設 `False`：歷史紀錄用不到逐題紀錄，`step_records` 會是空 list，也就不查 `step_logs`。需要時傳 `True`，會用 `prefetch_related("step_logs")` **一次**載入，而不是每場各查一次。
- `_to_dict(session, with_steps=True)`：逐題紀錄改用 `session.step_logs.all()` 取出後在 Python 排序，有 prefetch 時直接用快取，不再多查。
- 原本的 `list_sessions` 保留（給需要全站資料的情況），但也加上 `select_related`／`prefetch_related`，查詢次數不再隨場次數增加。

**三個呼叫端改用新函式**：`games/fridge_check/services.py`、`games/market_shopping/services.py`、`games/market_sort/views.py`，都是 `list_user_sessions(..., status="finished")`。

### 8.3 設計決策

- **為什麼用外鍵 `user`，不用 `state["user_id"]`？** `state["user_id"]` 是各遊戲建立場次時自己塞進 JSON 的舊寫法。我確認過所有建立場次的路徑（各遊戲 services、`market_sort`、`seed_demo`）都**同時**寫入外鍵與 `state`，兩者一致；以外鍵為準比較可靠，也能用到資料庫索引 `(game, user)`。
- **為什麼 `with_steps` 預設關閉？** 預設值選「最省」的，需要的人明確開啟，避免不小心又變回 N+1。
- **為什麼不順便改成資料庫排序？** 歷史的排序依據是 `result` JSON 裡的時間字串，而且現在只剩單一使用者的資料量，改動收益小、風險大，這次不動。

### 8.4 測試（`games/tests/test_list_user_sessions.py`，17 個）

`ListUserSessionsTests`（資料行為）：

- 只回這位使用者的場次、沒有場次回空 list
- `status` 篩選；只回被要求的那個遊戲
- **擁有者以外鍵 `user` 為準**，`state` 裡的 `user_id` 與外鍵不同時不受影響
- `with_steps` 預設不載入逐題紀錄；開啟時依題號順序載入
- 回傳的 dict 鍵與修改前相同（不破壞既有呼叫端）

`QueryCountTests`（查詢次數，用 `CaptureQueriesContext`）：

- `list_user_sessions`、`list_user_sessions(with_steps=True)`、`list_sessions` 在場次變多時，查詢次數**不再增加**
- `list_sessions` 仍回傳依序排好的逐題紀錄

`HistoryEndpointTests`（端點）：

- 冰箱檢查歷史只回我已完成的場次；查詢次數不隨場次增加
- 逛市場歷史回我最近 10 場（舊的在前）；查詢次數不隨場次增加
- 歷史不會載入他人的場次

這個檔案同時匯出 `make_session`、`FRIDGE`、`FRIDGE_RESULT` 等測試資料 helper，F11 的日期測試借用它們。

### 8.5 已知限制

- `list_sessions` 仍存在（目前只剩測試使用），保留給需要全站資料的用途；已避免 N+1，但仍會載入全部場次。
- 其他地方的全站掃描（`dashboard` 的日記 z-score）不在這個 PR，見 F9。

---

## 9. F9 — 日記語言 z 一次請求只掃一次全站日記

### 9.1 問題與風險

`dashboard/services.diary_z_scores` 要讀「**全站所有有效日記**」並依時間逐篇比對，才算得出一位使用者每篇日記的語言 z（每篇要跟更早的自己，以及其他人的日記比，才能得到相對位置）。這是儀表板最貴的一步，而**一次請求會呼叫它很多次**：

| 請求 | 原本掃描次數 | 呼叫來源 |
|---|---|---|
| `GET /api/dashboard/` | 4 次 | 雷達圖：語言軸平均＋解鎖進度；機器人卡片：解鎖進度＋週分數歷史 |
| `GET /api/dashboard/weekly-report/` | 2 次 | 解鎖進度＋週分數歷史 |

每次都從頭讀全站、重算一遍，結果卻完全相同。

### 9.2 修改

**`dashboard/services.py`**

```python
def _compute_diary_z_scores(user):
    # 兩個不影響結果的省時做法：
    # - 這位使用者沒有任何有效日記 → 不可能有結果，不掃全站
    # - 每篇日記的 z 只取決於「更早」的日記，所以只掃到他最新一篇為止
    last_created_at = DiaryAnalysis.objects.filter(
        is_valid=True, diary__user=user
    ).aggregate(last=Max("diary__created_at"))["last"]
    if last_created_at is None:
        return []
    analyses = DiaryAnalysis.objects.filter(
        is_valid=True, diary__created_at__lte=last_created_at
    )
    ...
```

- 原本 `diary_z_scores` 的主體搬到 `_compute_diary_z_scores(user)`，產生這位使用者**全部**有效日記的 `(建立時間, 語言 z)`。
- **提早結束**：沒有有效日記的人（新使用者、沒寫過日記的人佔大多數）直接回 `[]`，不掃全站。
- **只掃到他最新一篇為止**：之後才建立的日記不會影響他。
- `diary_z_scores(user, start, end, scores=None)`：先有完整結果、再依期間篩選；可傳入已算好的 `scores`，就不重算。
- 這些函式都加了**選用參數** `diary_scores`／`scores`（有預設值，既有呼叫不必改）：`average_diary_z_score`、`get_unlock_progress`、`get_dashboard_dimensions`、`get_weekly_scores_history`、`build_abilities`（`dashboard/weekly_report.py`）、`get_encouragement`（`dashboard/encouragement.py`）。
- `dashboard/views.py` 的儀表板 View 與 `build_weekly_report` 在請求開頭**先算一次**，再往下傳 → **每次請求只掃 1 次**。

### 9.3 為什麼結果完全相同

每篇日記的 z 只由「**更早建立**」的有效日記決定，所以：

- 先算出全部、再依期間篩選 = 只算期間內的（`end` 以後的日記不影響 `end` 以前的）。
- 只讀到使用者最新一篇為止 = 讀全部（之後的資料不會影響他）。

### 9.4 刻意「沒有」做的事：跨請求快取

計畫原本寫「快取」。評估後**沒有加**：

- 任何人寫一篇日記，**所有人**的全體基準都會變；要精準失效必須掛 signal 並用共用快取。
- 專案沒有設定 `CACHES`，預設是各 process 自己的記憶體快取：多 worker 時別的 worker 不知道失效，解鎖進度會用到**過期資料**。
- 測試之間會共用快取，容易產生難查的測試污染。
- 上面的做法已把每次請求的成本從 4 倍降到 1 倍，且**沒有任何過期資料的風險**。

等之後換成共用快取（Redis，屬於 `fix/global`）再加跨請求快取比較安全。

### 9.5 測試（`dashboard/tests/test_diary_z_scan.py`，10 個）

`DiaryZScoreEquivalenceTests`（結果與舊版相同）：

- 把舊演算法原樣放進測試當對照，用多位使用者、同時間建立的日記、測試帳號（`is_staff`）、示範日記（`seed/`）、無效日記，對**每一種期間**逐一比對，結果完全相同
- 傳入預先算好的分數時結果相同，而且不查資料庫
- 平均語言 z 與解鎖進度和舊做法一致
- 沒有日記的人、只有無效日記的人**不會掃全站**
- 使用者最新日記**之後**才建立的日記不會被載入

`ScanCountTests`（掃描次數）：

- 儀表板含「機器人卡片」時只掃 1 次（原本 4 次）；新使用者也只掃 1 次
- 週報只掃 1 次（原本 2 次）
- 儀表板回應內容不因為「共用掃描結果」而改變

這個檔案借用 `test_dashboard_api.DashboardApiTests` 的 `setUp` 與資料 helper（用 `from . import test_dashboard_api as dashboard_tests`，只 import **模組**、不 import 類別，否則 Django 會把那個類別的測試再跑一遍）。

### 9.6 已知限制

- 單次掃描仍是 O(全站有效日記數)，只是少了重複與提早結束。日記量很大時還需要預先彙總或共用快取。
- 建議替 `DiaryAnalysis(is_valid)` 與 `Diary(created_at)` 補索引（`fix/global` G10，需要 migration）。

---

## 10. F10 — 週報重複點開不再重複呼叫 AI 與寫資料庫

### 10.1 問題與風險

`GET /api/dashboard/weekly-report/` 每次請求都會：

1. **重新呼叫 OpenAI** 產生一句總結——花錢，而且在 request 內同步等待，沒有 timeout。
2. **把整份快照寫進資料庫**（`record.save()`），即使內容完全沒變。

GET 應該是「安全、可重複」的讀取。同一週重複點開（很常見：看完回首頁再點開）卻每次付出 AI 成本與一次寫入。

### 10.2 修改

**快照多存「當時餵給 AI 的事實」**（`WeeklyReport.report` 是 JSON，不需要新欄位）：

```python
SUMMARY_FACTS_KEY = "_summary_facts"   # dashboard/weekly_report.py
```

這個欄位**只存在快照裡，不會出現在 API 回應**。

**`dashboard/weekly_report.py`**

```python
def _reusable_summary(facts, previous_snapshot):
    # 能沿用的條件：
    # - 上次餵給 AI 的事實跟這次完全一樣（同樣的輸入，不需要再花一次 AI）
    # - 上次的總結不是「AI 失敗時的固定句型」（失敗就該在下次重試）
    ...

def build_weekly_report_with_facts(user, today, previous_snapshot=None):
    """回傳 (週報內容, 餵給 AI 的事實)"""
```

- 事實和上次**完全一樣**、而且上次的總結**不是 AI 失敗後的固定句型** → 沿用，不呼叫 AI。
- 事實變了（多玩了幾天、進步的能力變了…），或上次是固定句型（代表當時 AI 失敗）→ 重新產生。失敗的情況因此會在下次點開時**自動重試**。
- `build_weekly_report(user, today)` 保留原本的回傳，既有呼叫端與測試不用改。

**`dashboard/views.py` 的 `weekly_report_view`**

- 先查這一週有沒有舊快照，有就把它傳進去。
- 首次建立改用 `get_or_create(defaults=...)`，一次寫入。
- 已存在時，**內容沒變且 `viewed_at` 也記過了 → 完全不寫資料庫**；有變只用 `save(update_fields=[...])` 更新有變的欄位。
- `viewed_at` 仍只記**第一次**點開的時間，首頁今日任務（「看看上週回顧」）不受影響。

### 10.3 為什麼沿用總結是安全的

同樣的事實 = 同樣的 AI 輸入，重新問一次也只是換個說法，沒有新資訊。事實一變就會重新產生，所以不會出現過期的數字。

### 10.4 測試（`dashboard/tests/test_weekly_report_view.py`，10 個）

- 首次點開建立 1 筆紀錄並記下 `viewed_at`
- 內部事實在快照裡、**不在回應裡**
- 連續點開 3 次，AI 只被呼叫 1 次，三次回應相同
- 第二次點開用 `CaptureQueriesContext` 驗證**沒有任何 INSERT／UPDATE／DELETE**
- `viewed_at` 只記第一次
- 事實變了 → 重新產生，`viewed_at` 不變
- AI 失敗留下的固定句型，下次點開會重試，成功後之後沿用
- 內容（日記）變了但事實沒變 → 更新快照、不呼叫 AI、只一次 UPDATE
- 紀錄沒有 `viewed_at` 時，下次點開補上
- 其他使用者互不影響

### 10.5 後續修正（PR #101）

#100 合併後，完整測試出現 1 個錯誤：F5 的測試 `test_weekly_report_snapshot_keeps_path_but_response_is_signed` 仍用 `patch` 替換舊函式 `build_weekly_report`，但 View 現在呼叫 `build_weekly_report_with_facts`，替身沒生效，View 建出真實（沒有日記）的週報，測試取 `entries[0]` 時 `IndexError`。**只修測試的替換目標**，程式沒有問題。

這個疏失的原因是我在 #100 合併前把測試輸出接了 `tail`，測試失敗沒有讓流程停下。之後每個 PR 都改成「測試沒有全過就不 commit、不 push」（見第 17 章的說明）。

### 10.6 已知限制

- **首次點開仍會寫入一次**（記 `viewed_at` 與快照）。要讓 GET 完全變成純讀取，需要前端配合新增「標記已讀」端點，這次不動 API 契約，建議之後與前端討論。
- 沒有替 OpenAI 加 timeout／retry（`fix/global` G9）。

---

## 11. F11 — 遊戲與會員中心的日期改用台灣時間

### 11.1 問題與風險

資料庫與遊戲結果存 **UTC**，台灣是 **UTC+8**。直接取 UTC 的日期，會讓台灣 **00:00～08:00** 發生的事少一天。找到三處：

| 位置 | 原本 | 影響 |
|---|---|---|
| 冰箱檢查歷史 `played_date` | `completed_at[:10]`（直接切 UTC 字串前 10 個字） | 凌晨玩的場次日期少一天 |
| 會員統計 `joined_at` | `registered_at.date()`（UTC 日期） | 凌晨註冊的人「加入日期」少一天 |
| 生日驗證 | `date.today()`（作業系統日期） | 與 Django `TIME_ZONE` 設定脫鉤，換伺服器時區行為就變 |

### 11.2 修改

**`games/utils.py` 新增 `local_date_from_iso()`**

```python
def local_date_from_iso(iso_string):
    try:
        parsed = parse_datetime(iso_string)
    except ValueError:
        parsed = None
    if parsed is None or timezone.is_naive(parsed):
        return str(iso_string)[:10]          # 沒有時區資訊或格式不對：退回舊行為，不丟例外
    return timezone.localtime(parsed).date().isoformat()
```

- `games/fridge_check/services.py`：`played_date` 改用它；`completed_at`、`played_at` **原樣回傳**。
- `users/views.py`：`joined_at` 先 `timezone.localtime()` 再取日期。
- `users/serializers.py`：生日驗證改用 `timezone.localdate()`。

### 11.3 刻意「沒有」改儲存格式

`completed_at` 仍存 UTC 字串（`…+00:00`）。如果改成存台灣時間（`…+08:00`），新舊資料混用不同偏移的字串，而歷史是用**字串排序**找最新的，會排錯順序。要改格式得連歷史資料一起轉換，風險不值得；只在「取日期」時換算。

### 11.4 測試

- `games/tests/test_local_date.py`（11 個）
  - `LocalDateFromIsoTests`：UTC 晚上 = 台灣隔天；台灣午夜前一刻仍是當天；UTC 早上 = 同一天；已是 +08:00 的字串維持；其他時區偏移會換算；月底、年底換日；沒有時區資訊與無法解析的字串退回前 10 個字、不丟例外
  - `FridgeCheckHistoryDateTests`：`played_date` 是台灣日期、`completed_at`／`played_at` 原樣回傳、白天玩的場次日期不變。借用 F8 的 `make_session` 等 helper
- `users/tests/test_local_dates.py`（7 個）
  - `JoinedAtTests`：台灣午夜後註冊算隔天、午夜前保持當天、統計 API 用台灣日期、`registered_at` 缺少時退回 `date_joined`
  - `BirthDateTests`：UTC 還是昨天但台灣已是今天時，今天的生日被接受；明天被拒絕；正常的過去日期被接受

### 11.5 其他遊戲

`market_shopping`、`market_sort`、`memory_recall` 的 `completed_at`／`generated_at` 前端使用完整時間字串，後端沒有取日期，所以**不受影響**。

---

## 12. F12 — 移除未使用的診斷性模型（有 migration）

### 12.1 問題與風險

專案定位是「輔助維持認知活躍度」，**不做診斷**。盤點時發現兩個沒有被任何 API 或程式使用、只剩後台頁面的診斷性質模型：

| 模型 | 內容 | 使用處 |
|---|---|---|
| `assessments.Ad8Record` | AD-8（**失智症篩檢量表**）分數與結果 | 只有後台 |
| `dashboard.HealthDashboardRecord` | 腦年齡、趨勢警示等級（低／中／高） | 只有後台 |

儀表板與週報早就改成**即時計算**，不依賴這兩張表。留著它們有兩個問題：一是和產品定位衝突（後台看得到「篩檢結果」「警示等級」）；二是日後有人誤以為要寫入。

這項需要修改資料表，依專案慣例**先問過你**（你選擇「完整移除，要 migration」）。

### 12.2 修改

- 刪除兩個模型與後台註冊。
- **新增兩個 migration**（各刪除一張資料表）：
  - `assessments/migrations/0002_delete_ad8record.py`（依賴 `0001_initial`）
  - `dashboard/migrations/0003_delete_healthdashboardrecord.py`（依賴 `0002_weeklyreport`）
- `assessments` 變成**空 app**（保留在 `INSTALLED_APPS`）：已經套用過 `0001` 的資料庫需要它才能執行刪表 migration；若連 app 一起拿掉，這些資料庫會留下孤立的 migration 紀錄。
- `README.md`、`doc/DATABASE_SETUP.md`：移除相關說明與 ER 圖。

### 12.3 測試（`dashboard/tests/test_removed_models.py`，6 個）

原本放在 `config/`，PR #103 才搬到 `dashboard/tests/`。

| 測試 | 驗證什麼 |
|---|---|
| 兩個模型不存在 | `apps.get_model()` 找不到 `Ad8Record`、`HealthDashboardRecord`（`LookupError`） |
| `WeeklyReport` 模型還在 | 同一個 app 的其他模型沒被誤刪 |
| 沒有遺漏的 migration | `makemigrations --check --dry-run` 不報錯（模型與 migration 同步） |
| 資料表被刪除 | 套用最新 migration 後兩張表都不存在 |
| 可倒退再重新套用 | migrate 到 `assessments 0001`／`dashboard 0002` 時兩張表存在，再 migrate 到最新又消失 |
| `WeeklyReport` 資料表沒被動到 | `dashboard_weeklyreport` 仍在 |

後兩類用 `TransactionTestCase` + `MigrationExecutor` 實際倒退與前進；`tearDown` 一定把資料庫恢復到最新，不會影響其他測試。`makemigrations --check` 需要資料庫，所以放 `TestCase` 而不是 `SimpleTestCase`。

### 12.4 部署前注意（重要）

- 套用 migration 會**永久刪除**這兩張資料表。本機資料庫兩張表都是 **0 筆**；**正式環境我無法確認，部署前請先 `SELECT COUNT(*)` 並備份**。
- migration 可以倒退，但只會重建**空的**資料表，原本的資料不會回來。
- 若 `fix/global` 也新增 `dashboard` 或 `assessments` 的 migration，合併時要留意編號衝突（目前 `fix/global` 尚未開始）。

### 12.5 沒有處理的相關項目

- `diary.DiaryAnalysis.risk_level`（low／medium／high）與 `ai_feedback`：API 不會輸出，只有後台與示範資料使用；移除要動日記分析與 `seed_demo`，範圍較大，另外處理。
- `activities.HealthInformation`、`ActivityRecord` 等其他未使用模型不在這次範圍。

---

## 13. F13 — 補齊禁用詞，並對日記 AI 輸出加過濾與驗證

### 13.1 問題與風險

專案定位是「輔助維持認知活躍度」，**不能**出現醫療療效宣稱（延緩失智、降低風險…）。檢查前的狀況：

- 只有**週報總結**與**首頁問候語**會檢查 AI 的句子；**日記的 AI 產生（首問、追問、完成日記內容）完全沒檢查**，AI 回什麼就直接顯示給長者。
- 禁用詞不完整（沒有「延緩」「風險」「退化」「惡化」「阿茲海默」等）。
- 把單一字母 `z`／`Z` 列為禁用詞，會誤殺任何含 z 的句子。
- AI 回傳的欄位沒驗證型別與長度；`title`（資料庫 50）、`invite_text`（100）超長在 PostgreSQL 會 `DataError` 變 500；而 F7 之後 finalize 是 transaction，整個會還原。

### 13.2 修改

**新增 `ai_service/wording.py`**：集中禁用詞，分成疾病名稱、醫療與療效宣稱、負面字眼、專有名詞（分數、標準差、百分位…）、「玩語言」等類別。

```python
def find_banned_word(text):
    """回傳 text 裡第一個禁用詞；沒有就回傳 None。text 不是字串也回傳 None。"""

def contains_banned_word(text): ...
```

- **只列多字詞**。單一個字（「病」「症」「z」）會誤傷正常句子，例如「生病了要多休息」。
- 比對不分大小寫。
- `z`／`Z` 改為「z 分數」「z-score」等完整詞。
- `ai_service/weekly_summary.py`、`ai_service/greeting.py` 改用這份共用清單。

**`diary/ai_gen.py`（整檔重寫）**

| 項目 | 做法 |
|---|---|
| 提示詞 | 三個提示詞（首問、追問、完成日記）都附上 `SAFETY_RULES`：不提醫療、不評論長者記憶力與健康、不用負面字眼 |
| 首問、追問 | `_safe_text()`：空白或有禁用詞 → 固定句型（與 AI 失敗時相同） |
| 完成日記 | `clean_finalize_content()` 逐欄檢查：禁用詞或型別錯誤 → 該欄用預設值 |
| 長度 | `title` 截到 `TITLE_MAX_LENGTH = 50`、`invite_text` 截到 `INVITE_TEXT_MAX_LENGTH = 100`（對應資料庫欄位） |
| `category` | 限定在 `ALLOWED_CATEGORIES`，不在範圍就用預設 |
| 清單欄位 | `hashtags`、`suggested_replies` 過濾後最多 5 筆，沒剩就用預設 |
| 記錄 | `print` 改成 `logger.warning` |

### 13.3 測試

`ai_service/tests/test_wording.py`

- `FindBannedWordTests`：醫療宣稱、負面字眼會被擋；專有名詞不分大小寫與空白都會被擋；正常溫暖的句子（含「生病」）會通過；回傳的是命中的那個詞；非字串輸入不算禁用；**清單裡沒有任何單一字元**
- `OtherModulesUseTheSharedListTests`：週報總結與問候語會擋新增的禁用詞；週報總結**不再因為字母 z 被誤殺**

`diary/tests/test_ai_gen.py`

- `QuestionTests`：乾淨的問題照常回傳；首問、追問含禁用詞 → 固定句型；AI 回空白 → 固定句型；AI 出錯 → 固定句型並記 log；三個提示詞都附上安全規則
- `FinalizeContentTests`：好的內容原樣保留（含被 markdown 圍欄包住的 JSON）；某欄有禁用詞只有該欄用預設值，其他欄保留；超長的 `title`／`invite_text` 截到資料庫允許長度；不明分類用預設、所有允許的分類都不超過資料庫欄位長度；錯誤型別用預設；清單裡的禁用詞與非字串被丟棄、剩下沒東西用預設、最多 5 筆；JSON 不是物件、JSON 壞掉、AI 出錯都用預設；清理過程不會修改傳入的資料

合計新增 30 個，全部測試 865 個。

### 13.4 已知限制

- 只檢查 **AI 產生的句子**，**不檢查長者自己說的話**（日記預設的 `title`／`post_text` 取自長者原話）。
- 禁用詞是字串比對，不是語意判斷；換個說法（例如「讓腦袋不再生鏽」）擋不到，仍要靠提示詞約束。
- 單一字（病、症）刻意不列，所以「生病」這類句子可以出現。

---

## 14. 測試檔搬進各 app 的 `tests/` 資料夾（PR #103）

這不是 F 編號的問題修正，而是整理專案結構：你指出測試檔大多散在各 app 的根目錄（`tests.py`、`tests_*.py`），只有 `users/`、`home/` 有 `tests/` 資料夾。這個 PR 統一改成每個 app 都用 `tests/` 套件。**只搬檔案，沒有改測試內容。**

### 14.1 搬移規則

| 原本 | 搬到 |
|---|---|
| `<app>/tests.py` | `<app>/tests/test_<主題>.py` |
| `<app>/tests_x.py` | `<app>/tests/test_x.py` |
| `<app>/test_x.py` | `<app>/tests/test_x.py` |
| `games/<遊戲>/tests_x.py` | `games/<遊戲>/tests/test_x.py` |
| `config/tests_removed_models.py` | `dashboard/tests/test_removed_models.py`（它測的是 assessments／dashboard 的模型） |

`tests.py` 沒有主題名稱，所以依內容命名：

| 原檔 | 新檔 |
|---|---|
| `ai_service/tests.py` | `ai_service/tests/test_weekly_summary.py` |
| `dashboard/tests.py` | `dashboard/tests/test_dashboard_api.py` |
| `diary/tests.py` | `diary/tests/test_diary_api.py` |
| `public_share/tests.py` | `public_share/tests/test_public_share.py` |
| `social/tests.py` | `social/tests/test_social.py` |
| `games/market_sort/tests.py` | `games/market_sort/tests/test_views.py`（與其他遊戲一致） |

- 共 **46 個測試檔**用 `git mv` 搬動（Git 會把它們認成「重新命名」，保留修改歷史）。
- 每個新的 `tests/` 資料夾補一個空的 `__init__.py`（Python 套件需要；Django 的測試探索會找 `tests/` 底下 `test*.py` 的檔案）。
- 刪除 `activities`、`assessments`、`games` 三個只有 Django 範本註解（`# Create your tests here.`）的空 `tests.py`。
- `users/tests/`、`home/tests/` 原本就是這個結構，不動。

### 14.2 連帶修改

1. **相對 import 多一層**：檔案深了一層，`from .models import …` 要改成 `from ..models import …`（涵蓋 `.services`、`.views`、`.utils`、`.weekly_report`、`.management…` 等）。
2. **測試之間互相借用的 import**：
   - `games/market_sort/tests/test_owner.py`：`from .tests import …` → `from .test_views import …`
   - `dashboard/tests/test_diary_z_scan.py`：`from . import tests as dashboard_tests` → `from . import test_dashboard_api as dashboard_tests`
   - `games/tests/test_local_date.py`：`games.tests_list_user_sessions` → `games.tests.test_list_user_sessions`
   - `games/tests/test_recompute_scores.py`：`games.market_route.tests_market_zscore` → `games.market_route.tests.test_market_zscore`，`games.memory_recall.tests_memory_zscore` 同理
3. **執行指令**：測試檔開頭 docstring 的 `python manage.py test …` 與 `doc/` 裡的測試路徑（`frontend_api_changes.md`、`game_scoring_algorithms.md`、`score_standardization_changes.md`、`weekly_report.md`，以及本文件）一併更新。

### 14.3 執行方式的變更

```bash
# 舊
python manage.py test diary.tests_media --settings=config.settings_test
# 新
python manage.py test diary.tests.test_media --settings=config.settings_test

# 整個 app
python manage.py test diary --settings=config.settings_test

# 全部（不變）
python manage.py test --settings=config.settings_test
```

> 本文件第 1～7 章提到的測試檔，路徑是**搬移後**的新位置；當時這些 PR（#87～#93）合併時，它們還是 `games/tests_anonymous.py` 這種平放的檔名。

### 14.4 驗證

- 完整測試 **926 個通過、1 個預期失敗**，與搬移前**完全相同**（沒有漏跑、也沒有重複跑）。
- 搬移後專案中沒有殘留的 `tests.py`／`tests_*.py`。
- **刻意沒有對舊檔跑 `ruff format`**：舊的測試檔（例如 `social/tests/test_wall.py`）本來就有格式與行長問題，在純搬移的 PR 裡混進格式差異，會讓 Git 無法把它們認成「單純重新命名」，也讓 review 變困難。

### 14.5 已知限制

- 舊的指令（`diary.tests_media`…）、舊的文件連結或書籤會失效。專案內的我都改了，個人筆記需要自己更新。
- 目前 `games/` 底下還有 `tests_dda.py` 等演算法測試與 API 測試混在同一個 `tests/` 裡，沒有再細分。

---

## 15. F14 — 把 rewards（點數與成就）納入 `fix/features`

### 15.1 背景

`rewards`（完成遊戲、寫日記拿點數，達成條件解鎖成就）是另一條線開發的，合進了 `feat/stage3`（PR #106 本體、#107 把 `grant()` 串到各 API）。F1～F13 則在 `fix/features`。兩條線從同一個起點（`9d87c30`）分開，各自改了同一批檔案（`diary/views.py`、`dashboard/views.py`、`games/`…），要合在一起才能一起上線。

| 分支 | 內容 |
|---|---|
| `feat/stage3` | 多 8 個 commit，都是 rewards：新 app、成就清單、`grant()`、3 支查詢 API、遊戲結算／儀表板／週報／日記完成與分享共 10 個既有端點串接發點、首頁任務點數、遊戲名稱統一、日記 `finalize`／`share` 統一回應格式 |
| `fix/features` | F1～F13 與文件、測試搬移（#103） |

### 15.2 合併做法

使用者的工作目錄正在跑別的東西，所以**不在原本的資料夾切分支**，改用 `git worktree`（同一個 Git 倉庫、另一個資料夾、另一個分支）：

```bash
git worktree add ../LightMemory-Backend-wt -b merge/rewards-into-fix-features origin/fix/features
cp .env ../LightMemory-Backend-wt/        # .env 不在版本控制裡
git merge origin/feat/stage3
```

事先用 `git merge-tree`（只預測、不改動任何分支）算出會有 3 個檔案衝突，實際合併與預測一致：

| 衝突檔 | 兩邊各改了什麼 | 解法 |
|---|---|---|
| `diary/views.py` | F7 新增 `_error(code, message, http_status)`；rewards 也新增一個**同名同簽名**的 `_error`，而且回傳格式多了 `success: false`、`data: null` | 只留**一份**，採統一格式。F7 那份定義在檔案較後面，如果沒刪，它會蓋掉前面的統一格式（Python 後面的同名函式覆蓋前面的），所以必須刪掉。F7 的 400／409 錯誤因此也有了 `success`、`data` 欄位（只多欄位，用 `error.code` 判斷的前端不受影響）。`DiaryFinalizeView` 保留 F7 的 `transaction.atomic`、F13 的清理，**發點放在 atomic 之外**（見 15.4） |
| `dashboard/views.py` | F9 的 `diary_scores`、F5 的 `with_signed_media`、F10 的 `get_or_create`／「沒變就不寫」 vs. rewards 的 `rewards` 區塊 | 兩邊都保留。儀表板 `data` 加 `rewards`；週報在 `viewed_at` 寫入**之後**才 `grant()`，回應是 `{**簽名網址後的週報, "rewards": …}`，**不存進快照** |
| `dashboard/tests/test_weekly_report.py` | rewards 改的是搬移前的 `dashboard/tests_weekly_report.py`（#103 搬了它），Git 沒能自動跟上 | 手動把 stage3 的修改（多 import `WeeklyReport`、遊戲名稱、一個新測試）套到新位置 |

其餘檔案（五款遊戲的 `views.py`、`games/session_service.py`、`home/daily_tasks.py`、各測試）Git 自動合併成功。**自動合併成功不代表行為正確**，所以合併後跑了完整測試。

### 15.3 合併後測試發現的問題

第一次跑完整測試：966 個、**5 個失敗**。都是「兩邊各自正確、合在一起就出問題」的地方：

**（1）F9 的「一次請求只掃一次全站日記」被打回去（3 個失敗）**

| 請求 | F9 之後 | 合併 rewards 後 |
|---|---|---|
| `GET /api/dashboard/`（有機器人卡片） | 1 次 | 2 次 |
| `GET /api/dashboard/`（新使用者） | 1 次 | 3 次 |
| `GET /api/dashboard/weekly-report/` | 1 次 | 3 次 |

原因：`grant()` 會判斷成就。「六項全能」要算雷達圖解鎖了幾個維度，呼叫 `get_dashboard_dimensions`（含全站日記掃描）；發今日任務點數時，`home/daily_tasks` 的 `_rank_game_dimensions` 又呼叫一次。這些各自重掃一遍。

**（2）兩個「連續呼叫兩次、回應應該相同」的測試失敗**

- F10 的 `test_opening_again_does_not_call_the_ai_again`：比較第一次與第二次週報的整個回應
- F3 的 `test_owner_can_still_resubmit_same_session_id`：比較第一次與第二次交卷的整個回應

合併後回應多了 `rewards`，**第一次本來就會有點數與成就，第二次是 0 點**，兩次不可能完全相同。這是預期的行為改變，不是 bug。

**（3）過時的註解**

`games/session_service.py` 的 `grant_rewards` 註解寫「點數發給 `session.user`，不用 `request.user`，因為多數遊戲 API 允許未登入呼叫」。F1 之後未登入一律 404，F2／F3 之後只有場次擁有者能結算，這句話已經不成立。

### 15.4 修改與設計決策

**① `shared_diary_scan()`：範圍內共用同一次全站日記掃描**（`dashboard/services.py`）

- 用 `contextvars`（Python 的「目前執行環境」變數，每個請求／執行緒各自獨立）放一個暫存。**進入範圍時開一個空暫存、離開時丟掉**。範圍內，`diary_z_scores(user)` 對同一位使用者只算第一次，之後直接用結果。
- 範圍可以巢狀：內層直接沿用外層的結果。範圍外的呼叫行為完全不變（每次現算）。
- 三個地方套用：`dashboard` View、`weekly_report_view`（用 `@services.with_shared_diary_scan` 裝飾）、`rewards.services.grant()`（`with transaction.atomic(), shared_diary_scan():`）。
- **為什麼不沿用 F9 的「把 `scores` 一路傳下去」？** 要從 View 傳進 `grant()`，再傳進成就判斷、`home.daily_tasks.build_response`、`dashboard.services`，跨三個 app、四層函式。範圍式共用不用改這些函式的參數。F9 的 `scores=` 參數仍保留，兩者並存。
- **為什麼不做跨請求快取？** 同 9.4：任何人寫日記全體基準都會變，多 worker 時會有過期資料。這個範圍只活在**單一請求內**，離開就丟，不可能過期。
- **限制**：範圍內若又新增了日記，暫存不會更新。所以要在寫入「之後」才進入範圍（`finalize` 先存日記、再 `grant()`，`grant()` 自己開範圍，順序正確）。

**② 日記完成的發點放在 transaction「之外」**（`DiaryFinalizeView`）

- F7 把 `finalize` 整個包進 `transaction.atomic()` 並鎖住日記。如果發點也放在裡面，會**拉長持鎖時間**（發點要查一堆資料），而且發點失敗不該影響日記完成。
- `grant()` 本來就是「盡力而為」：內部包了 `transaction.atomic()`，任何例外都吞掉，只回 `rewards.error`。所以放在外面最合理：日記先確定寫入，再發點。
- 因此 atomic 區塊內要記住「是不是已經完成過」（`already_done`），結束後依此回 200 或 201；兩個同時送來的請求，後面那個拿到鎖才看到 `done` 時也走這條路，不會重複分析、重複呼叫 AI，`grant()` 也不會重複入帳。

**③ 統一的 `_error`（diary）**：只留一份，見 15.2。

**④ 兩個測試改成「除了 `rewards` 以外相同」**：第一次 `points_earned > 0`，第二次 `== 0`。這同時是「重複送出不會重複入帳」的驗證。

**⑤ 更新 `grant_rewards` 的過時註解。**

### 15.5 測試（`rewards/tests/test_with_fixes.py`，16 個新增）

| 類別 | 驗證什麼 |
|---|---|
| `DiaryFinalizeRewardsTests`（5） | 發點時日記的 transaction 已結束（用 `connection.savepoint_ids` 的層數比較）；發點失敗（模擬 `_grant` 丟例外）日記仍完成、回 201、`rewards.error` 有值；日記完成失敗（AI 壞掉，500）**不會發任何點數**；連續兩次 `finalize` 回 201／200、第二次 0 點、`diary_complete` 只入帳 1 筆；拿到鎖才看到 `done` 的並行情況回 200、不重複產生內容 |
| `GameRewardsOwnershipTests`（3） | 他人想結算我的場次：403、場次仍是進行中、**沒有任何人拿到點數**；沒登入：403、沒有點數；擁有者拿到點數、別人沒有 |
| `SharedDiaryScanScopeTests`（7） | 範圍外每次都掃；範圍內同一人只掃一次（含 `average_diary_z_score`）；不同使用者各掃一次；巢狀範圍沿用外層；離開範圍就丟掉；範圍內發生例外後範圍不會卡住；明確傳入 `scores` 完全不掃 |
| `GrantScansTheSiteOnceTests`（1） | 完成一場遊戲（發點含成就判斷與今日任務）最多掃 1 次 |

**拿掉修正會失敗的驗證**：

| 還原的內容 | 結果 |
|---|---|
| 共用掃描範圍（`dashboard/services.py`、`views.py`、`rewards/services.py`） | 10 個失敗：新測試 7 個（範圍相關 6 個、遊戲結算掃描 1 個）＋F9 原本的 3 個掃描測試 |
| 發點放回 transaction 內（模擬舊寫法） | 2 個失敗（`savepoint` 層數、第二次 `finalize` 的 0 點） |

### 15.6 對 rewards 本體的檢視

| 項目 | 結果 |
|---|---|
| 時區 | 用 `timezone.localdate()`，與 F11 一致，沒問題 |
| 併發重複入帳 | `get_or_create` ＋資料庫唯一約束（`unique_point_per_source`、`unique_user_achievement`），沒問題 |
| 給長者看的文字 | `catalog.py`、`services.py`、`views.py` 逐一比對 F13 的禁用詞清單，**沒有命中** |
| migration | `rewards/0001_initial` 只依賴 `AUTH_USER_MODEL`，與 F12 的兩個 migration 不同 app，編號不衝突；`makemigrations --check` 無待建項目 |
| 遊戲名稱 | `games/catalog.py`、`rewards/catalog.py` 的 `GAME_NAMES`、`home/daily_tasks.py` 的 `GAME_TASK_NAMES` 三處**逐一比對一致**（見下方「前端影響」） |
| 全站掃描 | 見 15.3（1），已修正 |

**前端影響**（完整說明在 [frontend_api_changes.md](frontend_api_changes.md) 的 F14）：3 支新 API、10 支既有 API 多 `rewards` 區塊、首頁任務的 `points` 與 `all_done_bonus`、**遊戲名稱改回 App 內的正式名稱**（`market_route` 菜市場找路 → 來去菜市場、`memory_recall` 煮菜過程 → 記憶配對、`fridge_check` 冰箱檢查 → 冰箱清點、`market_sort` 的 `title` 整理菜籃遊戲 → 整理菜籃）、日記 `finalize`／`share` 與 F7 錯誤的格式統一。

### 15.7 規模與測試

- 測試：926 → 966（stage3 帶來 40 個，其中 rewards 21 個）→ **982**（F14 新增 16 個），全部通過，另 1 個原本就預期失敗。
- F14 動到資料表：**新增 `rewards` 的兩張表**（`PointTransaction`、`UserAchievement`），一個 migration。

### 15.8 已知限制

- **`grant()` 吞掉所有例外**：發點失敗只會在 log 與 `rewards.error` 看到，沒有補發機制。使用者那次的點數就是沒了（重送請求可以補，因為每件事只入帳一次）。
- **共用範圍只在單一請求內有效**；每次發點仍可能掃一次全站日記（原本的設計是每個請求最多 1 次，現在也是）。日記量很大時還需要預先彙總或共用快取（`fix/global`）。
- **`feat/stage3` 之後若有新 commit，需要再合一次進 `fix/features`**。這次是單向合併。
- 遊戲名稱改動、日記回應格式改動，**需要前端配合**，已寫在前端文件。

---

## 16. 驗證方式與結果

### 16.1 指令

```bash
source venv/bin/activate

# 全部測試（目前 982 個，1 個預期失敗）
python manage.py test --settings=config.settings_test

# 單一模組（以 F5 為例；測試搬進 tests/ 之後的路徑）
python manage.py test diary.tests.test_media --settings=config.settings_test

# 只對自己改到的檔案檢查（不要 ruff format . 全專案，會動到約 50 個無關檔案）
ruff format <改到的檔案>
ruff check <改到的檔案>
```

### 16.2 「拿掉修正，測試會失敗」的結果

| 編號 | 還原的內容 | 結果 |
|---|---|---|
| F1 | （測試本身改成新預期） | 365 個既有 games 測試全過 |
| F2 | 兩個 view 的檢查 | 6 個失敗 |
| F3 | `views.py`＋`session_service.py` | 4 個失敗（2 failure＋2 error） |
| F4 | 兩支 View 的 `throttle_classes` | 6 個失敗 |
| F5 | 所有讀取點與上傳 | 9 個失敗（8 failure＋1 error） |
| F6 | `users/views.py` | 2 個失敗；整個移除新函式 → `ImportError` |
| F7 | `diary/views.py` | 12 個斷言失敗 |
| F8 | 只還原三個呼叫端 | 「歷史不載入他人場次」測試失敗 |
| F8 | 連 `session_service.py` 一起還原 | 7 個失敗（N+1 與查詢次數） |
| F9 | `dashboard/services.py` 與呼叫端 | 8 個失敗（掃描次數、提早結束、傳入預先算好的結果）；另 2 個「與舊版結果一致」的測試兩邊都通過——它們的用途是保護這次重構沒有改變結果 |
| F10 | `dashboard/views.py` | 6 個失敗（重複呼叫 AI、重複寫入、事實變更、固定句型重試…） |
| F11 | 三個使用處 | 5 個失敗 |
| F12 | 模型與 migration | 4 個失敗 |
| F13 | `ai_gen.py`、`wording.py` | 約 20 個失敗 |
| F14 | 共用掃描範圍（`dashboard/services.py`、`views.py`、`rewards/services.py`） | 10 個失敗：新測試 7 個＋F9 原本的 3 個掃描測試 |
| F14 | 發點放回 transaction 內（模擬舊寫法） | 2 個失敗 |

### 16.3 還沒有做的驗證

- 沒有在真的 PostgreSQL＋多 worker＋真的 Firebase 環境實測（F4 的共用快取、F5 的簽名、F6 的刪檔、F7 的鎖）。以上都是用 mock 驗證程式邏輯。**合併到正式環境前，建議在測試環境手動走一遍。**
- **F12 的 migration 沒有在正式資料庫上演練**。本機兩張表都是 0 筆，但正式環境未知；套用前請先確認筆數並備份（見 12.4）。
- F8、F9 的效能改善是用「查詢次數」驗證（場次變多時查詢數不增加、掃描次數降低），**沒有在大量資料下量測實際秒數**。
- F10 的 AI 沿用邏輯用 mock 驗證；沒有用真的 OpenAI 回應測過。
- **F14 的 rewards 沒有在 PostgreSQL 上實測**：併發重複入帳靠資料庫唯一約束，測試用的 SQLite 也有唯一約束，但並行請求的實際行為（`get_or_create` 撞到唯一約束的重試）建議在 PostgreSQL 用兩個並行請求再驗證一次。
- F14 的掃描次數是用 spy 計算 `_compute_diary_z_scores` 的呼叫次數驗證，沒有量測實際秒數。

---

## 17. 開發過程備註

- **測試的假設錯誤**（F3）：我以為未結束 session 的 `result` 是 `{}`，實際是 `None`。修正的是測試。
- **指令失誤**（F5）：驗證「拿掉修正會失敗」時，我一個 `git stash push` 指令因為檔名引用錯誤沒有成功，後面的 `git stash pop` 卻照常執行，把你原本 `feat/score_standardization` 的舊 WIP stash（一行文件修改）取出來了。發現後立刻放回原樣，內容完全一致。之後所有還原驗證改用 `git diff > patch` ＋ `git apply -R`，不再碰 stash。
- **程式碼多寫一行**（F6）：`collect_user_media` 一度多了一行無意義的程式，馬上自己發現並刪掉，之後有測試保護。
- **合併方式**：#87 依你的指示「直接 merge」；#88～#93 在你詢問「為什麼還沒 merge」之後，我以同樣方式用 merge commit 合併；之後的 PR 也照這個做法。
- **F10 帶著失敗的測試被合併**（#100，已由 #101 修正）：我把完整測試的輸出接 `tail`，管線的結束代碼是 `tail` 的（永遠成功），測試失敗沒有讓流程停下。**修正**：之後每個 PR 的指令都改成 `if ! python manage.py test … > 輸出檔; then exit 1; fi`，測試沒有全過就不 commit、不 push。這件事我當時就在 PR #101 的說明裡寫明了。
- **F14：預測衝突的方式**：合併前用 `git merge-tree` 預測衝突檔案（只讀、不改動分支），預測的 3 個檔案與實際完全一致。第一次比較 `stage3` 與 `fix/features` 的差異時，我把 `git diff` 的方向看反了（把 `fix/features` 的內容當成 `stage3` 的），之後重新抓遠端並確認分支關係才發現，沒有造成任何修改。
- **F14：worktree 的追蹤分支**：`git worktree add … -b merge/rewards-into-fix-features origin/fix/features` 會讓新分支預設「追蹤」`origin/fix/features`，直接 `git push` 會推到合併目標。我立刻用 `git branch --unset-upstream` 解除，之後都用明確的 `git push -u origin <分支>`。
- **F14：測試把潛在問題抓出來**：合併後第一次跑完整測試有 5 個失敗，其中 3 個（掃描次數）是 F9 的保護網抓到 rewards 帶來的重複掃描；這是 F9 當初寫「掃描次數」測試的目的。
- **整檔重寫 `diary/ai_gen.py`**（F13）：我第一次用取代腳本改這個檔案，結果把檔案弄壞了，所以改成整份重寫。重寫後有測試保護。
- **測試類別被重複執行**（F9）：`test_diary_z_scan.py` 想借用 `DashboardApiTests` 的 helper，一開始用 `from … import DashboardApiTests`，結果 Django 把它當成這個檔案裡的測試類別又跑一遍（測試數變成 28 而不是 10）。改成只 import **模組**、用 `模組.類別.方法` 取用。
- **測試的假設錯誤**（F8、F10）：我以為未結束場次的 `result` 是 `{}`、`market_shopping` 歷史的 `data` 是 dict，實際分別是 `None` 與 list，修正的是測試，不是程式。
- **`SimpleTestCase` 不能碰資料庫**（F12）：`makemigrations --check` 需要資料庫，放在 `SimpleTestCase` 會被擋，改放 `TestCase`。
- **既有的 ruff 問題沒有順手處理**：`diary/views.py`、`users/serializers.py`、`ai_service` 的部分舊檔本來就有，我只對自己改到的檔案跑 ruff，避免 PR 混進無關差異。
- **搬移測試時的失誤與修正**（#103）：我用腳本批次搬檔與改 import。第一版的相對 import 規則寫錯（正規表示式要求點後面接空白，但 `.models` 後面沒有空白），結果大部分檔案沒有被修正；我在 review 搬移後的差異時發現，馬上補上規則重跑，並確認全部測試通過後才 commit。另外取代舊路徑時，`diary.tests`（舊的 `tests.py`）被取代後，又被後面的規則重複取代，造成 docstring 裡的指令變成 `diary.tests.test_diary_api.test_media`，也已經修正。過程中還有一個誤把 `grep -r` 的檔案清單留空、掃描了整個 `venv/` 而卡住的指令，已中止，沒有造成任何修改。

---

## 18. 尚未處理的事與後續建議

### 18.1 `fix/features` 的後續（建議優先）

| 優先 | 項目 | 說明 |
|---|---|---|
| 高 | **忘記密碼的身分驗證** | F4 只做了次數限制。建議加「生日＋手機號碼」兩個欄位的驗證（`User.birth_date`、`User.phone` 已存在，不用改資料表）。注意：兩個欄位目前都可以為空，舊帳號沒填的人無法自助重設，需要規劃替代流程 |
| 高 | **舊的公開檔案改成私有** | F5 的後續，一次性腳本，先備份再演練 |
| 中 | 頭像更換／移除時刪除舊檔案 | F6 的延伸 |
| 中 | 刪帳號時檔案改成背景刪除，並提供孤兒檔案清理腳本 | F6 的限制 |
| 低 | F2 的檢查改成 `market_route`／`memory_recall` 也共用 `forbidden_unless_owner` | 目前兩套並存，功能都正確 |
| 中 | **正式環境套用 F12 的 migration 前** | 先確認 `assessments_ad8record`、`dashboard_healthdashboardrecord` 兩張表的筆數並備份 |
| 中 | `DiaryAnalysis.risk_level`、`ai_feedback` 清理 | F12 刻意沒動；要連 `seed_demo` 一起改 |
| 中 | 週報改成純讀取 | F10 首次點開仍會寫一次；要與前端新增「標記已讀」端點 |
| 中 | 日記語言 z 的跨請求快取／預先彙總 | F9 只做到「一次請求只掃一次」；等有共用快取（Redis）再做 |
| 低 | 日記預設的 `title`／`post_text` 也加用語檢查 | F13 只檢查 AI 產生的句子，不檢查長者原話 |
| 中 | rewards 在 PostgreSQL 上做並行重複結算的實測 | F14 的限制；唯一約束已保護，但沒實測 |
| 中 | `feat/stage3` 之後的新 commit 需要再合進 `fix/features` | F14 是單向合併 |
| 低 | rewards 發點失敗的補發機制 | 目前只回 `rewards.error`，重送請求可以補發 |
| 低 | `games/` 的 `tests/` 內部再依類型分組 | #103 只把檔案搬進去，沒有再細分 |

### 18.2 `fix/global`（共通問題，規劃中）

| 編號 | 項目 | 備註 |
|---|---|---|
| G1 | `SECRET_KEY`、`DEBUG`、CORS 改讀環境變數 | `SECRET_KEY` 目前寫死在程式碼且已進 git |
| G2 | 預設權限改成 `IsAuthenticated` | 會讓前端大改，建議前端處理完 F1～F7 後再做 |
| G3 | 登入、註冊、改密碼加入限速 | 沿用 F4 的做法；`DEFAULT_THROTTLE_RATES` 屬於這裡 |
| G4 | JWT blacklist 與 rotation、縮短 token 效期 | 需要 migration，要先確認 |
| G5～G6 | 統一回應格式 `common/responses.py` | F14 之後 `diary` 的 `finalize`／`share` 與錯誤已統一；`rewards/views.py` 也有一份 `_ok`，要一起合併；`diary` 其餘成功回應仍沒有 `success` 欄位 |
| G8 | 遊戲 session 加 transaction／鎖 | F7 對日記做了，遊戲那邊（`update_session`、`save_step`）還沒 |
| G10 | 補常用查詢索引 | F8、F9 的查詢會用到 `GameSession(game, user)`、`DiaryAnalysis(is_valid)`、`Diary(created_at)` |
| G9 | OpenAI 加 timeout 與 retry | F7 的鎖、F10 的週報都會因此受益 |
| G11～G14 | CI、pre-commit、部署文件、外部服務單元測試 | |

---

## 19. 檔案索引

依檔案列出「哪些編號動過它」，方便日後查「這一行是為什麼寫的」。

| 檔案 | 編號 | 說明 |
|---|---|---|
| `games/utils.py` | F1、F2、F11 | `get_current_user` 改回 `None`；新增 `forbidden_unless_owner`、`local_date_from_iso` |
| `games/session_service.py` | F3、F8、F14 | 新增 `SessionOwnerMismatch`；`get_or_create_session` 檢查擁有者；新增 `list_user_sessions`、`_to_dict(with_steps=)`，`list_sessions` 加 `select_related`／`prefetch_related`；F14 更新 `grant_rewards` 的過時註解 |
| `games/fridge_check/views.py` | F2 | `submit_answer` 加擁有者檢查 |
| `games/market_shopping/views.py` | F2 | `submit_item_answer`、`submit_change_answer` 加擁有者檢查 |
| `games/market_sort/views.py` | F3、F8 | 接住 `SessionOwnerMismatch` 回 403；歷史改用 `list_user_sessions` |
| `games/fridge_check/services.py` | F8、F11 | 歷史改用 `list_user_sessions`；`played_date` 改用 `local_date_from_iso` |
| `games/market_shopping/services.py` | F8 | 歷史改用 `list_user_sessions` |
| `users/throttles.py`（新） | F4 | 兩個忘記密碼限速類別 |
| `users/views.py` | F4、F5、F6、F11 | 套用限速；頭像 `public=True`；`collect_user_media`／`remove_user_media`；刪帳號流程；`joined_at` 用台灣日期 |
| `users/serializers.py` | F11 | 生日驗證用 `timezone.localdate()` |
| `diary/media.py`（新） | F5 | `media_url()` |
| `diary/external.py` | F5、F6 | `upload_to_firebase(public=)`；`blob_name_from_stored`、`delete_from_firebase` |
| `diary/views.py` | F5、F7、F14 | 讀取點套 `media_url`；回覆驗證與 transaction；F14 統一 `_error`／`_ok`、`finalize` 發點放在 atomic 之外 |
| `social/utils.py` | F5 | `serialize_post` 套 `media_url` |
| `public_share/views.py` | F5 | 分享頁照片套 `media_url` |
| `dashboard/weekly_report.py`、`dashboard/views.py` | F5、F9、F10、F14 | `with_signed_media`；快照存路徑；F9 傳遞預先算好的日記分數；F10 `SUMMARY_FACTS_KEY`、`_reusable_summary`、`build_weekly_report_with_facts`、不重複寫入；F14 兩個 View 加 `rewards` 並套用共用掃描範圍 |
| `dashboard/services.py` | F9、F14 | `_compute_diary_z_scores`、`diary_z_scores(scores=)`、各函式的 `diary_scores` 選用參數；F14 新增 `shared_diary_scan`、`with_shared_diary_scan`、`_scores_for` |
| `dashboard/encouragement.py` | F9 | `get_encouragement` 接受預先算好的分數 |
| `rewards/`（新，來自 stage3） | F14 | `models.py`、`services.py`（`grant()`）、`catalog.py`、`views.py`、`urls.py`、`migrations/0001_initial.py`；F14 在 `services.py` 的 `grant()` 套用 `shared_diary_scan()` |
| `rewards/tests/test_with_fixes.py`（新） | F14 | 16 個合併互動測試 |
| `ai_service/wording.py`（新） | F13 | 共用禁用詞與 `find_banned_word`、`contains_banned_word` |
| `ai_service/weekly_summary.py`、`ai_service/greeting.py` | F13 | 改用共用禁用詞 |
| `diary/ai_gen.py` | F13 | 整檔重寫：安全規則、輸出清理與驗證、長度限制 |
| `assessments/models.py`、`assessments/admin.py`、`assessments/migrations/0002_delete_ad8record.py` | F12 | 移除 `Ad8Record`（app 保留為空） |
| `dashboard/models.py`、`dashboard/migrations/0003_delete_healthdashboardrecord.py` | F12 | 移除 `HealthDashboardRecord` |
| `README.md`、`doc/DATABASE_SETUP.md` | F12 | 移除相關說明與 ER 圖 |
| `games/tests/test_utils.py`、`games/tests/test_anonymous.py` | F1 | |
| `games/tests/test_session_owner.py` | F2 | |
| `games/market_sort/tests/test_owner.py` | F3 | |
| `users/tests/test_password_reset.py`、`test_password_reset_throttle.py` | F4 | |
| `diary/tests/test_media.py` | F5 | |
| `users/tests/test_delete_account_files.py` | F6 | |
| `diary/tests/test_reply_validation.py` | F7 | |
| `games/tests/test_list_user_sessions.py` | F8 | |
| `dashboard/tests/test_diary_z_scan.py` | F9 | |
| `dashboard/tests/test_weekly_report_view.py` | F10 | |
| `games/tests/test_local_date.py`、`users/tests/test_local_dates.py` | F11 | |
| `dashboard/tests/test_removed_models.py` | F12 | 原在 `config/`，#103 搬移 |
| `ai_service/tests/test_wording.py`、`diary/tests/test_ai_gen.py` | F13 | |
| 全部 `*/tests/` | 整理 | #103 把所有測試搬進各 app 的 `tests/` |
| `doc/frontend_api_changes.md` | F1～F14 | 前端對照文件（F8～F13 對前端幾乎沒有介面變化；F14 有新 API 與多處變動） |

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
| F13 | #96 | `fix/ai-banned-words` | `fix(ai_service): 補齊禁用詞，並對日記 AI 輸出加上過濾與驗證` |
| F8 | #97 | `perf/games-list-sessions` | `perf(games): 歷史紀錄改在資料庫篩選使用者的場次，消除 N+1` |
| F9 | #98 | `perf/dashboard-diary-zscore-cache` | `perf(dashboard): 日記語言 z 一次請求只掃一次全站日記` |
| F11 | #99 | `fix/games-local-date` | `fix(games): 遊戲與會員中心的日期改用台灣時間` |
| F10 | #100 | `fix/dashboard-weekly-report-get` | `fix(dashboard): 週報重複點開不再重複呼叫 AI 與寫資料庫` |
| F10 修正 | #101 | `test/diary-media-weekly-report-patch` | `test(diary): 週報簽名網址測試改為替換 build_weekly_report_with_facts` |
| F12 | #102 | `refactor/remove-diagnostic-models` | `refactor(assessments): 移除未使用的 AD-8 與健康儀表板診斷性模型` |
| 整理 | #103 | `test/move-tests-into-app-packages` | `test: 測試檔搬到各 app 的 tests/ 資料夾` |
| F14 | #106、#107 | `feat/rewards-system`、`feat/rewards-integration`（合進 `feat/stage3`） | `feat(rewards): 新增點數與成就系統（資料表、成就清單、grant()、查詢 API）` 等 |
| F14 | PR_F14 | `merge/rewards-into-fix-features` | `feat(rewards): 合併 rewards 點數與成就系統，並與 F1～F13 整合` |

只有 F1 帶 `!`（Conventional Commits 的破壞性變更標記）；其餘對正常使用的前端流程不造成破壞。F12 雖然動到資料表，但這兩個模型從來沒有對外 API，所以沒有 `!`。

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
| **migration** | 修改資料表結構的紀錄檔。F1～F7 沒有新增；F12 新增了兩個（刪除兩張表） |
| **mock（模擬）** | 測試時用假物件代替真的外部服務（Firebase、OpenAI、Whisper），這樣測試又快又穩，也不會花錢 |
| **Conventional Commits** | commit 訊息的固定格式：`類型(範圍): 描述`，例如 `fix(games): ...`；類型後加 `!` 代表會破壞既有行為 |
| **N+1 查詢** | 先用 1 次查詢取得 N 筆資料，再對每一筆各查一次關聯資料，總共 N+1 次。資料越多越慢。用 `select_related`（JOIN）或 `prefetch_related`（批次查詢）一次取回 |
| **`select_related` / `prefetch_related`** | Django 預先把關聯資料一起查回來的兩種方法：前者用 JOIN（適合一對一、多對一），後者另外用一次查詢批次取（適合一對多） |
| **UTC / Asia/Taipei** | UTC 是世界標準時間；台灣是 UTC+8。UTC 16:00 就是台灣隔天 00:00，直接取 UTC 的日期會讓台灣凌晨少一天 |
| **z 分數（z-score）** | 一個數值相對於「某群體平均」差幾個標準差。專案用它把不同遊戲、不同指標放到同一把尺上比較；不會顯示給長者看 |
| **快照（snapshot）** | 把某一刻算出的結果整份存起來。週報用它記下「那一週當時的內容」 |
| **`DeleteModel` migration** | 刪除一個模型（資料表）的 migration。套用會刪除資料表與全部資料；倒退只會重建空表 |
| **禁用詞** | 不能出現在給長者看的句子裡的詞，例如醫療與療效宣稱。AI 產生的句子會先過一遍檢查 |
| **`git worktree`** | 同一個 Git 倉庫、另一個資料夾、另一個分支同時存在。F14 用它在不干擾使用者正在使用的工作目錄的情況下合併 |
| **`contextvars`** | Python 的「目前執行環境」變數：每個請求／執行緒各自一份。`shared_diary_scan` 用它存「這個範圍內已經掃過的結果」，離開範圍就丟掉 |
| **rewards／點數與成就** | 完成遊戲、寫日記、做今日任務拿點數（每天上限 100），達成條件解鎖成就（一次性獎勵）。各 API 回應的 `data.rewards` 就是這一次的結果 |
| **merge target（合併目標）** | 小分支做完要合併進去的分支。這一輪是 `fix/features` |
