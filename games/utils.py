"""各遊戲共用的小工具。"""

from django.utils import timezone
from django.utils.dateparse import parse_datetime
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


def local_date_from_iso(iso_string):
    """把存在 result 裡的 ISO 時間字串換算成「台灣時間」的日期字串（YYYY-MM-DD）。

    遊戲結果的 completed_at 是 UTC（例如 2026-11-09T17:30:00+00:00），
    直接切前 10 個字會得到 UTC 日期，台灣 00:00～08:00 玩的場次會少一天。
    這裡先轉成目前時區（settings.TIME_ZONE）再取日期。

    字串沒有時區資訊或格式不對時，退回直接取前 10 個字（跟舊行為一樣）。
    """
    try:
        parsed = parse_datetime(iso_string)
    except ValueError:
        parsed = None
    if parsed is None or timezone.is_naive(parsed):
        return str(iso_string)[:10]
    return timezone.localtime(parsed).date().isoformat()


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
