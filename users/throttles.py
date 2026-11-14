"""忘記密碼 API 的請求次數限制（throttle）。

兩層限制，任何一層超過都會回 429 TOO_MANY_REQUESTS（格式見 config/exceptions.py）：

1. PasswordResetUsernameThrottle：同一個帳號名稱每小時最多 10 次。
   擋住「針對某個帳號反覆嘗試」。IP 可以偽造，所以這層才是主要防線。
2. PasswordResetIPThrottle：同一個來源每小時最多 30 次。
   擋住「同一個來源掃很多個帳號」。

兩支忘記密碼 API（確認帳號、設定新密碼）共用同一份計數，
所以「先確認帳號再重設」一輪算 2 次。

注意：
- 計數存在 Django 的 cache。目前沒有設定 CACHES，用的是單一 process 的記憶體快取；
  部署成多個 worker 時，每個 worker 各自計數，實際上限會變寬鬆，
  正式環境要改用共用快取（例如 Redis）。
- 被鎖住的是「帳號名稱」，所以知道對方帳號的人也能故意把它鎖一小時。
"""

import hashlib

from rest_framework.throttling import SimpleRateThrottle


class PasswordResetIPThrottle(SimpleRateThrottle):
    scope = "password_reset_ip"
    rate = "30/hour"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class PasswordResetUsernameThrottle(SimpleRateThrottle):
    scope = "password_reset_username"
    rate = "10/hour"

    def get_cache_key(self, request, view):
        data = request.data if isinstance(request.data, dict) else {}
        username = str(data.get("username", "")).strip().lower()
        if not username:
            # 沒帶帳號：不計入，後面的欄位驗證會回 400
            return None
        # 帳號名稱雜湊後再當 cache key，避免特殊字元或過長的字串
        digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}


# ── G3：登入、註冊、改密碼／刪帳號 ─────────────────────────────────
#
# 次數寫在 settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]（上面 F4 的兩個類別
# 是直接寫在類別裡，沒有搬動）。要調整次數改設定檔即可。


def _username_key(request):
    """請求裡的帳號名稱（小寫、去空白）雜湊後的結果；沒帶帳號回傳 None。"""
    data = request.data if isinstance(request.data, dict) else {}
    username = str(data.get("username", "")).strip().lower()
    if not username:
        return None
    return hashlib.sha256(username.encode("utf-8")).hexdigest()


class FailureCountThrottle(SimpleRateThrottle):
    """只計算「失敗」的次數；成功的請求不算。

    一般的 DRF 限速每個請求都算一次。登入如果也這樣算，正常使用者一小時內
    登入幾次就被擋了。這個類別改成：
    - 請求進來時只「檢查」失敗次數有沒有超過上限，超過就回 429
    - 由 View 在確定失敗（帳密錯誤）時呼叫 record_failure() 才記一次
    - 登入成功時 View 可呼叫 clear() 把這個對象的失敗次數歸零
    """

    def allow_request(self, request, view):
        if self.rate is None:
            return True
        self.key = self.get_cache_key(request, view)
        if self.key is None:
            return True
        # now 與 history 是 DRF 的 wait()（算「請多久後再試」）要用的，一定要設
        self.now = self.timer()
        self.history = self._recent(self.key)
        if len(self.history) >= self.num_requests:
            return self.throttle_failure()
        return True

    def _recent(self, key):
        now = self.timer()
        return [t for t in self.cache.get(key, []) if t > now - self.duration]

    def record_failure(self, request, view):
        key = self.get_cache_key(request, view)
        if key is None or self.rate is None:
            return
        history = self._recent(key)
        history.insert(0, self.timer())
        self.cache.set(key, history, self.duration)

    def clear(self, request, view):
        key = self.get_cache_key(request, view)
        if key is not None:
            self.cache.delete(key)


class LoginIPThrottle(FailureCountThrottle):
    """同一個來源登入失敗太多次（掃很多個帳號）。"""

    scope = "login_ip"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class LoginUsernameThrottle(FailureCountThrottle):
    """同一個帳號登入失敗太多次（針對某個帳號猜密碼）。主要防線。

    帳號不存在也會算，所以不能靠「有沒有被擋」猜出帳號是否存在。
    """

    scope = "login_username"

    def get_cache_key(self, request, view):
        digest = _username_key(request)
        if digest is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": digest}


class RegisterIPThrottle(SimpleRateThrottle):
    """同一個來源短時間內大量註冊（建立垃圾帳號、用重複帳號訊息掃帳號）。

    不管成功或失敗，每個註冊請求都算一次。
    """

    scope = "register_ip"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class PasswordConfirmUserThrottle(SimpleRateThrottle):
    """已登入的使用者反覆輸入密碼確認身分：修改密碼、刪除帳號。

    這兩個動作都要再輸入一次密碼。如果有人偷到 access token，不限次數的話
    可以一直猜密碼。以「使用者」計算（不是 IP），兩個動作共用同一份次數。
    """

    scope = "password_confirm_user"

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": user.pk}
