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
