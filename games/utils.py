"""各遊戲共用的小工具。"""

from rest_framework import status
from rest_framework.response import Response


def get_current_user(request):
    """取得目前使用者。

    有登入（JWT）時回傳登入者；未登入時回傳 None，
    呼叫端要自己回 404 USER_NOT_FOUND。
    """
    if request.user.is_authenticated:
        return request.user
    return None


def forbidden_unless_owner(request, session):
    """檢查 session 是不是目前使用者的。

    session 是 session_service 回傳的 dict（有 "user_id"）。
    是本人的 → 回傳 None，呼叫端繼續處理；
    不是本人、或沒登入 → 回傳 403 FORBIDDEN 的 Response，呼叫端直接 return 它。

    用法：
        forbidden = forbidden_unless_owner(request, session)
        if forbidden is not None:
            return forbidden
    """
    user = get_current_user(request)
    if user is None or session["user_id"] != user.id:
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "FORBIDDEN",
                    "message": "這場遊戲不屬於目前的使用者",
                },
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return None
