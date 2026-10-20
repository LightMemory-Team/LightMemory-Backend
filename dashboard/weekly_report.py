"""週報表：給長者看的「上週回顧」。

看的是「上一個完整的週」（週一～週日），例如今天 10/15（四）就看
10/5～10/11。只讀資料、不寫入任何資料表。

設計原則：只跟自己比；不出現專有名詞（z 分數等）；不出現負面字眼。
「有活動的日子」代替登入天數：專案沒有登入紀錄表，而且 token 一次可用
很多天，所以改看那天有沒有開始玩遊戲或寫日記。
"""

import statistics
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.db.models import Max
from django.db.models.functions import TruncDate
from django.utils import timezone

from ai_service.weekly_summary import build_positive_facts, generate_weekly_summary
from diary.models import Diary
from games.memory_recall.score import z_score_to_total_score
from games.models import GameSession

from .services import (
    DIARY_SOURCE,
    DIMENSIONS,
    GAME_SOURCES,
    GAME_TITLES,
    diary_z_scores,
)

WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"]

DISCLAIMER = "這不是醫療診斷，僅供自我了解"

# 本週跟上週的分數差多少以上，才算「進步」或「多練習」；差距小於這個算「持平」
TREND_THRESHOLD = 3


def get_report_week(today):
    """回傳週報要看的那週（上一個完整的週）的 (週一, 週日)。"""
    this_monday = today - timedelta(days=today.weekday())
    week_start = this_monday - timedelta(days=7)
    return week_start, week_start + timedelta(days=6)


def _week_bounds(week_start):
    """那週的時間範圍 [週一 00:00, 下週一 00:00)，用台灣時間（settings.TIME_ZONE）。"""
    start = timezone.make_aware(datetime.combine(week_start, time.min))
    return start, start + timedelta(days=7)


def _game_sessions(user):
    return GameSession.objects.filter(user=user, game__code__in=GAME_SOURCES)


def get_daily_activity(user, week_start):
    """週一到週日每天有沒有活動（開始玩遊戲或寫日記），固定 7 筆。"""
    start, end = _week_bounds(week_start)
    active_dates = set()
    for queryset in (
        _game_sessions(user),
        Diary.objects.filter(user=user),
    ):
        active_dates.update(
            queryset.filter(created_at__gte=start, created_at__lt=end)
            # TruncDate 依台灣時間切日期，晚上 11 點玩的不會算到隔天
            .annotate(day=TruncDate("created_at"))
            .values_list("day", flat=True)
        )

    return [
        {
            "date": (week_start + timedelta(days=i)).isoformat(),
            "weekday": WEEKDAY_LABELS[i],
            "is_active": week_start + timedelta(days=i) in active_dates,
        }
        for i in range(7)
    ]


def longest_streak(daily_activity):
    """這週裡最長連續幾天有活動。"""
    longest = current = 0
    for day in daily_activity:
        current = current + 1 if day["is_active"] else 0
        longest = max(longest, current)
    return longest


def _finished_sessions_in_week(user, week_start):
    start, end = _week_bounds(week_start)
    return _game_sessions(user).filter(
        status="finished", finished_at__gte=start, finished_at__lt=end
    )


def count_finished_sessions(user, week_start):
    """這週玩完了幾場遊戲（以結束時間算）。"""
    return _finished_sessions_in_week(user, week_start).count()


def get_play_time(user, week_start):
    """這週各遊戲的遊玩秒數與總秒數，沒玩完的不算。

    每場 = 結算結果的 play_seconds（整理菜籃玩完才建立 session，只能用這個），
    沒有的話用「結束時間 − 開始時間」。
    """
    seconds_by_game = dict.fromkeys(GAME_SOURCES, 0)
    sessions = _finished_sessions_in_week(user, week_start).values_list(
        "game__code", "created_at", "finished_at", "result"
    )
    for code, created_at, finished_at, result in sessions:
        play_seconds = (result or {}).get("play_seconds")
        if play_seconds is None:
            play_seconds = round((finished_at - created_at).total_seconds())
        seconds_by_game[code] += play_seconds

    return {
        "total_seconds": sum(seconds_by_game.values()),
        "games": [
            {"source": code, "label": GAME_TITLES[code], "seconds": seconds}
            for code, seconds in seconds_by_game.items()
        ],
    }


def get_week_diaries(user, week_start):
    """這週完成的日記；欄位沿用 diary 月曆 API，另外算本週對話時長。

    對話時長：資料庫沒有存錄音長度，用「最後一則回答時間 − 日記建立時間」近似，
    沒有回答的日記算 0。
    """
    start, end = _week_bounds(week_start)
    diaries = (
        Diary.objects.filter(
            user=user, status="done", created_at__gte=start, created_at__lt=end
        )
        .annotate(last_reply_at=Max("replies__created_at"))
        .order_by("created_at")
    )

    talk_seconds = 0
    entries = []
    for d in diaries:
        if d.last_reply_at is not None:
            talk_seconds += round((d.last_reply_at - d.created_at).total_seconds())
        entries.append(
            {
                "diary_id": d.id,
                "date": timezone.localdate(d.created_at).isoformat(),
                "title": d.title,
                "photo_url": d.image_path,
                "post_text": d.post_text,
            }
        )
    return {"talk_seconds": talk_seconds, "entries": entries}


def get_played_sources(user, week_start):
    """這週有碰過的項目（遊戲 id 或 diary）；有開始玩、有寫日記就算。"""
    start, end = _week_bounds(week_start)
    played = set(
        _game_sessions(user)
        .filter(created_at__gte=start, created_at__lt=end)
        .values_list("game__code", flat=True)
    )
    if Diary.objects.filter(
        user=user, created_at__gte=start, created_at__lt=end
    ).exists():
        played.add(DIARY_SOURCE)
    return played


def suggest_untried_source(played_sources):
    """下週小目標：照雷達圖順序，挑第一個這週沒碰過的項目。

    寫成共用函式，之後首頁「每日建議」也可以用同一個邏輯。
    """
    for item in DIMENSIONS:
        if item["source"] not in played_sources:
            return f"這週還沒玩{item['label']}，下週試試看"
    return "每一項都玩過了，下週繼續保持！"


def _monday_of(moment):
    """某個時間點（台灣時間）所在那週的週一日期。"""
    day = timezone.localdate(moment)
    return day - timedelta(days=day.weekday())


def get_weekly_scores_history(user, until_week_start):
    """每週各能力的分數，回傳 {週一日期: {source: 分數}}。

    只取到 until_week_start 那週為止。source 是遊戲 id，或聲影日記的 "diary"。

    週分數 = 那週各場（遊戲依結束時間、日記依建立時間）z 的平均，再換成
    1～100 分（跟煮菜過程結束畫面同一個公式）。z 是 None 的場次、無效日記
    不算；那週沒有分數的能力不會出現。
    """
    _, end = _week_bounds(until_week_start)
    sessions = _game_sessions(user).filter(status="finished", finished_at__lt=end)

    z_by_week = defaultdict(lambda: defaultdict(list))
    for code, finished_at, result in sessions.values_list(
        "game__code", "finished_at", "result"
    ):
        z_score = (result or {}).get("z_score")
        if z_score is None:
            continue
        z_by_week[_monday_of(finished_at)][code].append(z_score)

    for created_at, z_score in diary_z_scores(user, end=end):
        z_by_week[_monday_of(created_at)][DIARY_SOURCE].append(z_score)

    return {
        week_start: {
            code: z_score_to_total_score(statistics.mean(z_scores))
            for code, z_scores in by_game.items()
        }
        for week_start, by_game in z_by_week.items()
    }


def _overall_score(scores_by_source):
    """整體表現 = 那週有分數的能力（含語言）取平均；一項都沒有就是 None。"""
    if not scores_by_source:
        return None
    return round(statistics.mean(scores_by_source.values()))


def get_trend(this_week, last_week):
    """進步 up／持平 steady／多練習 practice；任一週沒分數就是 None。

    用代碼回傳，前端翻成中文；退步用「多練習」，不出現負面字眼。
    """
    if this_week is None or last_week is None:
        return None
    diff = this_week - last_week
    if diff >= TREND_THRESHOLD:
        return "up"
    if diff <= -TREND_THRESHOLD:
        return "practice"
    return "steady"


def _ability(this_week, last_week, best):
    return {
        "this_week": this_week,
        "last_week": last_week,
        "best": best,
        "trend": get_trend(this_week, last_week),
    }


def build_abilities(user, week_start, played_sources):
    """「本週 vs 上週」：整體表現＋6 個能力的分數、個人最佳、趨勢。"""
    history = get_weekly_scores_history(user, week_start)
    this_scores = history.get(week_start, {})
    last_scores = history.get(week_start - timedelta(days=7), {})

    dimensions = []
    for item in DIMENSIONS:
        source = item["source"]
        base = {
            "dimension": item["dimension"],
            "label": item["label"],
            "played": source in played_sources,
        }
        best = max(
            (scores[source] for scores in history.values() if source in scores),
            default=None,
        )
        dimensions.append(
            {
                **base,
                **_ability(this_scores.get(source), last_scores.get(source), best),
            }
        )

    overall_best = max(
        (_overall_score(scores) for scores in history.values()), default=None
    )
    return {
        "overall": _ability(
            _overall_score(this_scores), _overall_score(last_scores), overall_best
        ),
        "dimensions": dimensions,
    }


def build_weekly_report(user, today):
    week_start, week_end = get_report_week(today)
    previous_week_start = week_start - timedelta(days=7)

    daily_activity = get_daily_activity(user, week_start)
    active_day_count = sum(1 for day in daily_activity if day["is_active"])
    previous_active_day_count = sum(
        1 for day in get_daily_activity(user, previous_week_start) if day["is_active"]
    )
    played_sources = get_played_sources(user, week_start)
    abilities = build_abilities(user, week_start, played_sources)
    summary = generate_weekly_summary(
        build_positive_facts(active_day_count, previous_active_day_count, abilities)
    )

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "summary": summary,
        "highlights": {
            "active_day_count": active_day_count,
            "session_count": count_finished_sessions(user, week_start),
            "streak_days": longest_streak(daily_activity),
        },
        "daily_activity": daily_activity,
        "abilities": abilities,
        "play_time": get_play_time(user, week_start),
        "diary": get_week_diaries(user, week_start),
        "next_week_goal": suggest_untried_source(played_sources),
        "disclaimer": DISCLAIMER,
    }
