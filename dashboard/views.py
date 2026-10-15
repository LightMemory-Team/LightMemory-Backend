from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import services


def _error_response(code, message, *, data=None, status=200):
    return Response(
        {
            "success": False,
            "data": data,
            "error": {"code": code, "message": message},
        },
        status=status,
    )


# 儀表板（雷達圖）：各認知維度近 7 天的 z-score 平均
@api_view(["GET"])
def dashboard(request):
    # DRF 預設的 401 格式是 {"detail": ...}，這裡自己回統一格式
    if not request.user.is_authenticated:
        return _error_response("NOT_AUTHENTICATED", "請先登入", status=401)

    # 還沒玩夠不是前端送錯資料，屬於正常狀態，所以用 200；
    # 附上每款進度，前端可以顯示「煮菜過程還差 1 場」
    progress = services.get_unlock_progress(request.user)
    if not services.is_unlocked(progress):
        return _error_response(
            "INSUFFICIENT_DATA",
            "資料尚不足分析",
            data={
                "required_sessions": services.REQUIRED_SESSIONS,
                "progress": progress,
            },
        )

    return Response(
        {
            "success": True,
            "data": {
                "period_days": services.PERIOD_DAYS,
                "dimensions": services.get_dashboard_dimensions(request.user),
            },
            "error": None,
        }
    )
