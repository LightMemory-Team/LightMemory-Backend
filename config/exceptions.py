"""統一的 API 錯誤格式。

所有 DRF 丟出的錯誤都會被轉成：
    {"success": false, "data": null,
     "error": {"code": "...", "message": "...", "fields": {...}}}
其中 fields 只有欄位驗證錯誤才有。各 app 自己手寫的 inline 錯誤回應不受影響。
"""

import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import set_rollback

logger = logging.getLogger(__name__)

VALIDATION_MESSAGE = "資料格式有誤，請再檢查一下"
LOGIN_FAILED_MESSAGE = "帳號或密碼錯誤"
NOT_AUTHENTICATED_MESSAGE = "請先登入或重新登入"


class ApiError(exceptions.APIException):
    """主動丟出指定 code／message 的錯誤，例如 USERNAME_TAKEN。

    用法：raise ApiError("USERNAME_TAKEN", "這個帳號已經被註冊過")
    """

    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, code, message, status_code=None, fields=None):
        super().__init__(detail=message, code=code)
        self.error_code = code
        self.message = message
        self.fields = fields
        if status_code is not None:
            self.status_code = status_code


# 序列化器用 ValidationError(code=...) 標記的特殊錯誤，轉成規格定義的 error.code
SPECIAL_VALIDATION_CODES = {
    "username_taken": "USERNAME_TAKEN",
}


def _special_code(detail):
    """在驗證錯誤中找 SPECIAL_VALIDATION_CODES 裡的 code，找到就回傳 error.code。"""
    if isinstance(detail, dict):
        for sub in detail.values():
            found = _special_code(sub)
            if found:
                return found
    elif isinstance(detail, (list, tuple)):
        for sub in detail:
            found = _special_code(sub)
            if found:
                return found
    else:
        return SPECIAL_VALIDATION_CODES.get(getattr(detail, "code", None))
    return None


def _flatten(detail):
    """把 DRF 的 ErrorDetail 轉成 {欄位: [訊息, ...]}，巢狀欄位用點連起來。"""
    result = {}

    def walk(value, prefix):
        if isinstance(value, dict):
            for key, sub in value.items():
                walk(sub, f"{prefix}.{key}" if prefix else str(key))
        elif isinstance(value, (list, tuple)):
            if value and all(isinstance(v, (dict, list, tuple)) for v in value):
                for index, sub in enumerate(value):
                    walk(sub, f"{prefix}.{index}" if prefix else str(index))
            else:
                key = prefix or "non_field_errors"
                result.setdefault(key, []).extend(str(v) for v in value)
        else:
            key = prefix or "non_field_errors"
            result.setdefault(key, []).append(str(value))

    walk(detail, "")
    return result


def _body(code, message, fields=None):
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return {"success": False, "data": None, "error": error}


def _parts(exc):
    """回傳 (http 狀態碼, error.code, error.message, fields)。"""
    if isinstance(exc, ApiError):
        return exc.status_code, exc.error_code, exc.message, exc.fields

    if isinstance(exc, exceptions.ValidationError):
        fields = _flatten(exc.detail)
        special = _special_code(exc.detail)
        if special:
            first = next(iter(fields.values()))[0]
            return 400, special, first, fields
        # 只有「整體錯誤」（沒有指定欄位）時，直接把訊息當作 message
        if list(fields) == ["non_field_errors"]:
            return 400, "VALIDATION_ERROR", fields["non_field_errors"][0], None
        return 400, "VALIDATION_ERROR", VALIDATION_MESSAGE, fields

    if isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
        # simplejwt 登入失敗的 code 是 no_active_account
        if getattr(exc.detail, "code", None) == "no_active_account":
            return 401, "NOT_AUTHENTICATED", LOGIN_FAILED_MESSAGE, None
        return 401, "NOT_AUTHENTICATED", NOT_AUTHENTICATED_MESSAGE, None

    if isinstance(exc, exceptions.NotFound):
        return 404, "NOT_FOUND", "找不到這個內容，可能已經被刪除了", None

    if isinstance(exc, exceptions.PermissionDenied):
        return 403, "FORBIDDEN", "你沒有權限執行這個動作", None

    if isinstance(exc, exceptions.MethodNotAllowed):
        return 405, "METHOD_NOT_ALLOWED", "不支援這個操作方式", None

    if isinstance(exc, exceptions.Throttled):
        return 429, "TOO_MANY_REQUESTS", "操作太頻繁了，請稍後再試", None

    if isinstance(exc, exceptions.APIException):
        # 其他 DRF 錯誤（格式錯誤的 JSON 等），一律當作 400 類型
        return exc.status_code, "BAD_REQUEST", "請求的內容有誤，請再檢查一下", None

    return 500, "SERVER_ERROR", "系統正在休息一下，請稍後再試", None


def api_exception_handler(exc, context):
    """設定在 settings.REST_FRAMEWORK["EXCEPTION_HANDLER"]。"""
    # 先把 Django 原生的例外換成 DRF 的版本，後面就只需要判斷一種
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    http_status, code, message, fields = _parts(exc)

    if http_status >= 500:
        view = context.get("view") if context else None
        logger.error("Unhandled API exception in %s", view, exc_info=exc)

    set_rollback()
    response = Response(_body(code, message, fields), status=http_status)

    # 帶回 WWW-Authenticate 等標頭（例如 401 要有 Bearer 提示）
    headers = getattr(exc, "auth_header", None)
    if headers:
        response["WWW-Authenticate"] = headers
    wait = getattr(exc, "wait", None)
    if wait:
        response["Retry-After"] = str(int(wait))
    return response
