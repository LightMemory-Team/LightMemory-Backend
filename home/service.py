"""首頁用的共用小工具。

「今天」「本週」一律以台灣時間（settings.TIME_ZONE）計算，
週一為一週的開始。
"""

from datetime import datetime, time, timedelta

from django.utils import timezone

from games.models import GameSession


def week_start(today=None):
    """回傳 today 所在那一週的週一（date）。today 預設為台灣時間的今天。"""
    today = today or timezone.localdate()
    return today - timedelta(days=today.weekday())


def _start_of_day(day):
    """某一天 00:00（台灣時間）的 aware datetime。"""
    return timezone.make_aware(datetime.combine(day, time.min))


def played_game_ids(user, start_date, end_date):
    """start_date～end_date（含）之間，使用者玩完的遊戲 id（game code）集合。

    只算 status="finished" 的場次：開了遊戲又中途離開的不算「玩過」。
    """
    codes = GameSession.objects.filter(
        user=user,
        status="finished",
        created_at__gte=_start_of_day(start_date),
        created_at__lt=_start_of_day(end_date + timedelta(days=1)),
    ).values_list("game__code", flat=True)
    return set(codes)
