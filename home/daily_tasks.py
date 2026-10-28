"""首頁「今日任務」：每天 3 個遊戲任務 + 1 個聲影日記，必要時再加上週回顧。

流程：
1. 當天第一次呼叫時產生任務並存進 DailyTask，之後同一天都回傳同一份。
2. done（是否完成）每次呼叫時即時計算，不另外存。

「今天」「本週」一律是台灣時間，週一為一週的開始。
"""

from django.db import IntegrityError, transaction
from django.utils import timezone

from dashboard import services as dashboard_services
from dashboard import weekly_report
from dashboard.models import WeeklyReport
from diary.models import Diary

from . import service
from .models import DailyTask

GAME_TASK_COUNT = 3
WEEKLY_GOAL = 5  # 一週內要把 5 個遊戲維度都玩到

# 5 個遊戲維度，順序同時也是「條件都一樣時」的固定優先順序
# （attention → working_memory → executive_function → visual_spatial → math）
GAME_DIMENSIONS = [
    {"dimension": item["dimension"], "game_id": item["source"]}
    for item in dashboard_services.DIMENSIONS
    if item["source"] != dashboard_services.DIARY_SOURCE
]

# 任務標題裡的遊戲短名稱（跟 games/catalog.py 的 title 不完全相同）
GAME_TASK_NAMES = {
    "market_route": "今天去菜市場",
    "memory_recall": "記憶配對",
    "market_sort": "整理菜籃",
    "fridge_check": "冰箱檢查",
    "market_shopping": "市場買菜",
}

DIARY_TITLE = "寫一篇聲影日記"
WEEKLY_REPORT_TITLE = "看看上週回顧"


def _rank_game_dimensions(user, today):
    """依推薦邏輯排序 5 個遊戲維度（最該練的排最前面）。

    1. 本週（週一到今天）還沒玩過的排前面
    2. 同一組裡分數較低的排前面；還沒解鎖分數、或近 7 天沒有分數的，
       視為最低（要先累積資料）
    3. 條件都一樣時，依 GAME_DIMENSIONS 的固定順序
    """
    played = service.played_game_ids(user, service.week_start(today), today)
    scores = {
        item["source"]: item["score"]
        for item in dashboard_services.get_dashboard_dimensions(user)
        if item["unlocked"] and item["score"] is not None
    }

    def sort_key(indexed):
        index, item = indexed
        game_id = item["game_id"]
        return (game_id in played, scores.get(game_id, -1), index)

    return [item for _, item in sorted(enumerate(GAME_DIMENSIONS), key=sort_key)]


def _viewed_at(user, report_week_start):
    """使用者第一次點開那週週報的時間；還沒點開過是 None。"""
    return (
        WeeklyReport.objects.filter(
            user=user, week_start=report_week_start, viewed_at__isnull=False
        )
        .values_list("viewed_at", flat=True)
        .first()
    )


def _should_include_weekly_report(user, today):
    """上週有遊戲或日記紀錄，且還沒點開過週報（或就是今天點開的）才出現。"""
    last_week_start, _ = weekly_report.get_report_week(today)
    if not weekly_report.get_played_sources(user, last_week_start):
        return False  # 上週完全沒有資料，週報是空的，點進去沒有意義

    viewed_at = _viewed_at(user, last_week_start)
    if viewed_at is None:
        return True
    # 點開的那天，任務還要顯示（已完成）；從隔天起就不再出現
    return timezone.localtime(viewed_at).date() == today


def _build_specs(user, today):
    specs = [
        {"type": "game", **item}
        for item in _rank_game_dimensions(user, today)[:GAME_TASK_COUNT]
    ]
    specs.append({"type": "diary", "dimension": "language", "game_id": None})
    if _should_include_weekly_report(user, today):
        specs.append({"type": "weekly_report", "dimension": None, "game_id": None})
    return specs


def get_or_create_tasks(user, today):
    """回傳今天的任務（DailyTask 清單，依 order 排序）；今天還沒有就先產生。"""
    tasks = list(DailyTask.objects.filter(user=user, date=today))
    if tasks:
        return tasks

    rows = [
        DailyTask(user=user, date=today, order=order, **spec)
        for order, spec in enumerate(_build_specs(user, today), start=1)
    ]
    try:
        with transaction.atomic():
            DailyTask.objects.bulk_create(rows)
    except IntegrityError:
        # 同時有另一個請求先產生好了，直接讀它建立的那份
        pass
    return list(DailyTask.objects.filter(user=user, date=today))


def _title(task):
    if task.type == "game":
        return f"玩「{GAME_TASK_NAMES[task.game_id]}」"
    if task.type == "diary":
        return DIARY_TITLE
    return WEEKLY_REPORT_TITLE


def build_response(user, today):
    """組出 GET /api/home/daily-tasks/ 的回應內容。"""
    tasks = get_or_create_tasks(user, today)

    played_today = service.played_game_ids(user, today, today)
    played_this_week = service.played_game_ids(user, service.week_start(today), today)
    wrote_diary = (
        Diary.objects.filter(user=user, created_at__date=today)
        .exclude(status="failed")
        .exists()
    )
    viewed_report = (
        _viewed_at(user, weekly_report.get_report_week(today)[0]) is not None
    )

    def is_done(task):
        if task.type == "game":
            return task.game_id in played_today
        if task.type == "diary":
            return wrote_diary
        return viewed_report

    items = [
        {
            "id": task.id,
            "type": task.type,
            "title": _title(task),
            "game_id": task.game_id,
            "dimension": task.dimension,
            "done": is_done(task),
        }
        for task in tasks
    ]
    game_ids = {item["game_id"] for item in GAME_DIMENSIONS}
    return {
        "date": today.isoformat(),
        "completed_count": sum(item["done"] for item in items),
        "total_count": len(items),
        "weekly_progress": {
            "played_dimensions": len(played_this_week & game_ids),
            "goal": WEEKLY_GOAL,
        },
        "tasks": items,
    }
