from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import encouragement, services, weekly_report
from .models import WeeklyReport


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

    today = timezone.localdate()
    data = weekly_report.build_weekly_report(request.user, today)

    # 記錄這一週的週報：存內容快照，並記下第一次點開的時間。
    # 首頁今日任務的「看看上週回顧」靠 viewed_at 判斷是否完成。
    # get_or_create：有就拿出來、沒有才建立，同一週重複點開不會多存。
    week_start, _ = weekly_report.get_report_week(today)
    record, _created = WeeklyReport.objects.get_or_create(
        user=request.user, week_start=week_start
    )
    record.report = data
    if record.viewed_at is None:
        record.viewed_at = timezone.now()
    record.save(update_fields=["report", "viewed_at"])

    return Response({"success": True, "data": data, "error": None})
