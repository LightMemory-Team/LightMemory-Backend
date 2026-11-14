"""點數與成就的核心邏輯。

對外只有一個入口 grant(user, event, ref)：遊戲結算、日記完成、看週報、
開儀表板、分享日記的 API 都呼叫它，回傳值直接放進回應的 data["rewards"]。

grant() 做三件事：
    1. 依事件入帳點數（遊戲 10、日記 15、今日任務 +5、全部完成 +20），
       遊戲／日記／任務的點數每天合計最多 100 點
    2. 檢查有沒有成就達標，達標就解鎖並入帳成就點數（一次性，不計入上限）
    3. 組出 rewards 區塊

重複呼叫是安全的：(user, reason, source_id) 唯一，同一件事只會入帳一次。
發點失敗（例外）時不會影響原本的 API，只回傳 0 點的空區塊。
"""

import logging

from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from .catalog import (
    ACHIEVEMENTS,
    ACHIEVEMENTS_BY_CODE,
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    EVENT_ACHIEVEMENTS,
    GAME_IDS,
    GAME_NAMES,
)
from .models import PointTransaction, UserAchievement

logger = logging.getLogger(__name__)

DAILY_CAP = 100

POINTS = {
    "game_complete": 10,
    "diary_complete": 15,
    "daily_task": 5,
    "all_tasks_done": 20,
}
# 計入每日 100 點上限的來源（成就點數不算）
COUNTED_REASONS = list(POINTS)

# 事件名稱
GAME_FINISH = "game_finish"
DIARY_COMPLETE = "diary_complete"
WEEKLY_REPORT_VIEWED = "weekly_report_viewed"
DASHBOARD_VIEWED = "dashboard_viewed"
DIARY_SHARED = "diary_shared"


# ── 小工具 ──────────────────────────────────────────


def total_points(user):
    return (
        PointTransaction.objects.filter(user=user).aggregate(total=Sum("amount"))[
            "total"
        ]
        or 0
    )


def today_points(user, today=None):
    """今天已經算進每日上限的點數。"""
    today = today or timezone.localdate()
    return (
        PointTransaction.objects.filter(
            user=user, reason__in=COUNTED_REASONS, created_at__date=today
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )


def empty_rewards(user=None):
    """沒有獲得任何點數時的 rewards 區塊（欄位一律存在，前端不用判斷）。"""
    try:
        total = total_points(user) if user is not None else 0
    except Exception:  # noqa: BLE001
        total = 0
    return {
        "points_earned": 0,
        "breakdown": [],
        "daily_cap_reached": False,
        "total_points": total,
        "new_achievements": [],
    }


def _record(user, reason, source_id, label, base, running):
    """入帳一筆點數，回傳 (是否新入帳, 實際入帳點數)。

    base 是這件事「應得」的點數，running 是今天已入帳的點數（用來算每日上限）。
    只入帳到 100 為止；沒額度時仍記一筆 amount=0，之後重複呼叫就不會再入帳。
    """
    allowed = max(0, min(base, DAILY_CAP - running))
    row, created = PointTransaction.objects.get_or_create(
        user=user,
        reason=reason,
        source_id=str(source_id),
        defaults={"amount": allowed, "label": label},
    )
    return created, (allowed if created else 0)


# ── 成就進度 ────────────────────────────────────────


class _Stats:
    """某位使用者的各種累積數字；用到才查，同一次檢查內只查一次。"""

    def __init__(self, user):
        self.user = user
        self._cache = {}

    def _get(self, key, func):
        if key not in self._cache:
            self._cache[key] = func()
        return self._cache[key]

    def game_counts(self):
        """{遊戲 id: 已結束場次}。熟悉場也算。"""
        from games.models import GameSession

        def load():
            counts = {}
            rows = GameSession.objects.filter(
                user=self.user, status="finished"
            ).values_list("game__code", flat=True)
            for code in rows:
                counts[code] = counts.get(code, 0) + 1
            return counts

        return self._get("game_counts", load)

    def diary_count(self):
        from diary.models import Diary

        return self._get(
            "diary_count",
            lambda: Diary.objects.filter(user=self.user, status="done").count(),
        )

    def all_tasks_days(self):
        return self._get(
            "all_tasks_days",
            lambda: PointTransaction.objects.filter(
                user=self.user, reason="all_tasks_done"
            ).count(),
        )

    def weekly_report_viewed(self):
        from dashboard.models import WeeklyReport

        return self._get(
            "weekly_report",
            lambda: WeeklyReport.objects.filter(
                user=self.user, viewed_at__isnull=False
            ).exists(),
        )

    def shared_post(self):
        from social.models import Post

        return self._get(
            "shared_post",
            lambda: Post.objects.filter(
                user=self.user, post_type="diary", diary__isnull=False
            ).exists(),
        )

    def week_games(self):
        """本週（週一到今天）玩完的不同遊戲數。"""
        from home import service

        def load():
            today = timezone.localdate()
            played = service.played_game_ids(
                self.user, service.week_start(today), today
            )
            return len(played & set(GAME_IDS))

        return self._get("week_games", load)

    def day_games(self):
        from home import service

        def load():
            today = timezone.localdate()
            played = service.played_game_ids(self.user, today, today)
            return len(played & set(GAME_IDS))

        return self._get("day_games", load)

    def active_days(self):
        """有活動（玩完遊戲或寫完日記）的不同日期數。"""
        from diary.models import Diary
        from games.models import GameSession

        def load():
            days = set(
                GameSession.objects.filter(user=self.user, status="finished")
                .annotate(day=TruncDate("created_at"))
                .values_list("day", flat=True)
            )
            days |= set(
                Diary.objects.filter(user=self.user, status="done")
                .annotate(day=TruncDate("created_at"))
                .values_list("day", flat=True)
            )
            return len(days)

        return self._get("active_days", load)

    def radar_unlocked(self):
        from dashboard import services as dashboard_services

        def load():
            items = dashboard_services.get_dashboard_dimensions(self.user)
            return sum(1 for item in items if item["unlocked"])

        return self._get("radar_unlocked", load)

    def points_total(self):
        return self._get("points_total", lambda: total_points(self.user))


def _progress(stats, ach):
    """這個成就目前的進度（未封頂的原始數字）。"""
    kind = ach["type"]
    if kind == "game_count":
        return stats.game_counts().get(ach["game"], 0)
    if kind == "total_games":
        return sum(stats.game_counts().values())
    if kind == "diary_count":
        return stats.diary_count()
    if kind == "all_tasks_days":
        return stats.all_tasks_days()
    if kind == "weekly_report":
        return 1 if stats.weekly_report_viewed() else 0
    if kind == "shared_post":
        return 1 if stats.shared_post() else 0
    if kind == "week_games":
        return stats.week_games()
    if kind == "day_games":
        return stats.day_games()
    if kind == "active_days":
        return stats.active_days()
    if kind == "radar_unlocked":
        return stats.radar_unlocked()
    if kind == "points_total":
        return stats.points_total()
    return 0  # "event" 類只能靠事件解鎖


def _achievement_payload(ach):
    return {
        "code": ach["code"],
        "category": ach["category"],
        "title": ach["title"],
        "description": ach["description"],
        "points": ach["points"],
        "icon": ach["icon"],
    }


def _unlock_achievements(user, event):
    """檢查所有還沒解鎖的成就，達標就解鎖並入帳點數，回傳新解鎖清單。"""
    unlocked_codes = set(
        UserAchievement.objects.filter(user=user).values_list("code", flat=True)
    )
    event_codes = set(EVENT_ACHIEVEMENTS.get(event, []))
    newly = []

    # 成就點數可能讓「點數小富翁」達標，所以最多多檢查幾輪
    for _ in range(3):
        stats = _Stats(user)
        found = []
        for ach in ACHIEVEMENTS:
            code = ach["code"]
            if code in unlocked_codes:
                continue
            if code in event_codes or _progress(stats, ach) >= ach["target"]:
                found.append(ach)
        if not found:
            break
        for ach in found:
            _, created = UserAchievement.objects.get_or_create(
                user=user, code=ach["code"]
            )
            unlocked_codes.add(ach["code"])
            if created:
                PointTransaction.objects.get_or_create(
                    user=user,
                    reason="achievement_unlock",
                    source_id=ach["code"],
                    defaults={
                        "amount": ach["points"],
                        "label": f"解鎖成就：{ach['title']}",
                    },
                )
                newly.append(ach)
    return newly


# ── 對外入口 ────────────────────────────────────────


def grant(user, event, ref=None):
    """處理一個事件，回傳 rewards 區塊。任何例外都不往外丟。"""
    try:
        with transaction.atomic():
            return _grant(user, event, ref)
    except Exception:  # noqa: BLE001
        logger.exception("發放點數失敗：user=%s event=%s ref=%s", user, event, ref)
        return empty_rewards(user)


def _grant(user, event, ref):
    from home import daily_tasks

    today = timezone.localdate()
    running = today_points(user, today)
    breakdown = []
    attempted = False  # 這次有沒有「新」處理到任何一件事

    def add(reason, source_id, label, base):
        nonlocal running, attempted
        created, got = _record(user, reason, source_id, label, base, running)
        if created:
            attempted = True
            running += got
            if got > 0:
                breakdown.append({"reason": reason, "label": label, "points": got})
        return created

    if event == GAME_FINISH:
        session = ref
        if not add("game_complete", session.pk, "完成一場遊戲", POINTS["game_complete"]):
            return empty_rewards(user)  # 這場已經發過了（重複呼叫 finish）
        _grant_task_points(user, today, add, daily_tasks, game_id=session.game.code)
    elif event == DIARY_COMPLETE:
        diary = ref
        if not add("diary_complete", diary.pk, "完成一篇聲影日記", POINTS["diary_complete"]):
            return empty_rewards(user)
        _grant_task_points(user, today, add, daily_tasks, task_type="diary")
    elif event == WEEKLY_REPORT_VIEWED:
        _grant_task_points(user, today, add, daily_tasks, task_type="weekly_report")

    new_achievements = _unlock_achievements(user, event)

    if not breakdown and not new_achievements and not attempted:
        return empty_rewards(user)

    return {
        "points_earned": sum(item["points"] for item in breakdown),
        "breakdown": breakdown,
        "daily_cap_reached": attempted and running >= DAILY_CAP,
        "total_points": total_points(user),
        "new_achievements": [_achievement_payload(a) for a in new_achievements],
    }


def _grant_task_points(user, today, add, daily_tasks, game_id=None, task_type="game"):
    """今日任務的 +5，以及全部完成的 +20。"""
    response = daily_tasks.build_response(user, today)
    done_by_id = {item["id"]: item["done"] for item in response["tasks"]}

    for item in response["tasks"]:
        if not item["done"]:
            continue
        if item["type"] != task_type:
            continue
        if task_type == "game" and item["game_id"] != game_id:
            continue
        if task_type == "game":
            name = GAME_NAMES.get(game_id, item["title"])
            label = f"完成今日任務：{name}"
        elif task_type == "diary":
            label = "完成今日任務：聲影日記"
        else:
            label = "完成今日任務：看看上週回顧"
        add("daily_task", f"{today}:{item['id']}", label, POINTS["daily_task"])

    if response["total_count"] and all(done_by_id.values()):
        add("all_tasks_done", str(today), "今日任務全部完成", POINTS["all_tasks_done"])


# ── 查詢用 ──────────────────────────────────────────


def summary(user):
    today = timezone.localdate()
    today_total = today_points(user, today)
    return {
        "total_points": total_points(user),
        "today_points": today_total,
        "daily_cap": DAILY_CAP,
        "daily_remaining": max(0, DAILY_CAP - today_total),
        "achievements_unlocked": UserAchievement.objects.filter(user=user).count(),
        "achievements_total": len(ACHIEVEMENTS),
    }


def achievement_wall(user):
    """成就牆：依三類分組，每項附是否解鎖、解鎖時間、進度。"""
    unlocked = {
        row.code: row.unlocked_at for row in UserAchievement.objects.filter(user=user)
    }
    stats = _Stats(user)
    groups = []
    for category in CATEGORY_ORDER:
        items = []
        for ach in ACHIEVEMENTS:
            if ach["category"] != category:
                continue
            code = ach["code"]
            is_unlocked = code in unlocked
            current = ach["target"] if is_unlocked else _progress(stats, ach)
            items.append(
                {
                    "code": code,
                    "title": ach["title"],
                    "description": ach["description"],
                    "unlocked": is_unlocked,
                    "unlocked_at": (
                        timezone.localtime(unlocked[code]).isoformat()
                        if is_unlocked
                        else None
                    ),
                    "progress": {
                        "current": min(current, ach["target"]),
                        "target": ach["target"],
                    },
                    "points": ach["points"],
                    "icon": ach["icon"],
                }
            )
        groups.append(
            {
                "category": category,
                "label": CATEGORY_LABELS[category],
                "achievements": items,
            }
        )
    return groups
