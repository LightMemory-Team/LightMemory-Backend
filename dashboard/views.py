from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import encouragement, services, weekly_report


def _error_response(code, message, *, data=None, status=200):
    return Response(
        {
            "success": False,
            "data": data,
            "error": {"code": code, "message": message},
        },
        status=status,
    )


# 儀表板（雷達圖）：各認知維度近 7 天的 z-score 平均，各維度分開解鎖
@api_view(["GET"])
def dashboard(request):
    # DRF 預設的 401 格式是 {"detail": ...}，這裡自己回統一格式
    if not request.user.is_authenticated:
        return _error_response("NOT_AUTHENTICATED", "請先登入", status=401)

    return Response(
        {
            "success": True,
            "data": {
                "period_days": services.PERIOD_DAYS,
                "required_sessions": services.REQUIRED_SESSIONS,
                # 固定 6 個維度，各自帶解鎖狀態；沒解鎖的維度前端畫灰色軸、
                # 顯示「再玩 N 次就能看到」
                "dimensions": services.get_dashboard_dimensions(request.user),
                # 機器人卡片：總體分數的趨勢代碼，前端翻成鼓勵文字；
                # 6 個維度都解鎖前是 null
                "encouragement": encouragement.get_encouragement(request.user),
            },
            "error": None,
        }
    )


# 週報表：上一個完整的週（週一～週日）的回顧；活動、日記照常顯示，
# 能力分數只列已解鎖的維度
@api_view(["GET"])
def weekly_report_view(request):
    if not request.user.is_authenticated:
        return _error_response("NOT_AUTHENTICATED", "請先登入", status=401)

    return Response(
        {
            "success": True,
            "data": weekly_report.build_weekly_report(
                request.user, timezone.localdate()
            ),
            "error": None,
        }
    )
