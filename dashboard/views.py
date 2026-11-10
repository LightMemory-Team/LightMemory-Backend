import json

from django.core.serializers.json import DjangoJSONEncoder
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


# 儀表板（雷達圖）：各認知維度近三個月（90 天）的 z-score 平均，各維度分開解鎖
@api_view(["GET"])
def dashboard(request):
    # DRF 預設的 401 格式是 {"detail": ...}，這裡自己回統一格式
    if not request.user.is_authenticated:
        return _error_response("NOT_AUTHENTICATED", "請先登入", status=401)

    # 日記的語言 z 要掃全站日記：算一次，雷達圖與機器人卡片共用
    diary_scores = services.diary_z_scores(request.user)

    return Response(
        {
            "success": True,
            "data": {
                "period_days": services.PERIOD_DAYS,
                "required_sessions": services.REQUIRED_SESSIONS,
                # 固定 6 個維度，各自帶解鎖狀態；沒解鎖的維度前端畫灰色軸、
                # 顯示「再玩 N 次就能看到」
                "dimensions": services.get_dashboard_dimensions(
                    request.user, diary_scores=diary_scores
                ),
                # 機器人卡片：總體分數的趨勢代碼，前端翻成鼓勵文字；
                # 6 個維度都解鎖前是 null
                "encouragement": encouragement.get_encouragement(
                    request.user, diary_scores=diary_scores
                ),
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
    week_start, _ = weekly_report.get_report_week(today)

    # 這一週之前存過快照的話，餵給 AI 的事實沒變就沿用上次的總結，不再呼叫 AI
    existing = WeeklyReport.objects.filter(
        user=request.user, week_start=week_start
    ).first()
    data, facts = weekly_report.build_weekly_report_with_facts(
        request.user,
        today,
        previous_snapshot=existing.report if existing else None,
    )

    # 記錄這一週的週報：存內容快照，並記下第一次點開的時間。
    # 首頁今日任務的「看看上週回顧」靠 viewed_at 判斷是否完成。
    # 快照存照片「路徑」與當時的 AI 事實（簽名網址有時效，不能存）。
    # get_or_create：有就拿出來、沒有才建立，同一週重複點開不會多存。
    # 內容沒變、viewed_at 也記過了就完全不寫資料庫，重複點開只是讀取。
    snapshot = json.loads(
        json.dumps(
            {**data, weekly_report.SUMMARY_FACTS_KEY: facts}, cls=DjangoJSONEncoder
        )
    )
    record, created = WeeklyReport.objects.get_or_create(
        user=request.user,
        week_start=week_start,
        defaults={"report": snapshot, "viewed_at": timezone.now()},
    )
    if not created:
        changed = []
        if record.report != snapshot:
            record.report = snapshot
            changed.append("report")
        if record.viewed_at is None:
            record.viewed_at = timezone.now()
            changed.append("viewed_at")
        if changed:
            record.save(update_fields=changed)

    return Response(
        {"success": True, "data": weekly_report.with_signed_media(data), "error": None}
    )
