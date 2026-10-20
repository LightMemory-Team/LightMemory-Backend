"""儀表板（雷達圖）資料：各認知維度近幾天的 z-score 平均。

只讀資料、不寫入任何資料表：每次請求當下計算，所以數字永遠是最新的。
- 遊戲：從已結束場次 GameSession.result 裡的 z_score 計算。z_score 由各遊戲
  結算時存入，已限制在 ±2 內；算不出來（前測、歷史不足）時為 None。
- 聲影日記（語言）：從 DiaryAnalysis 的 5 個小分數現算每篇的語言 z
  （見 diary_zscore.py），只算有效的日記。
"""

import statistics
from datetime import timedelta

from django.utils import timezone

from diary.models import DiaryAnalysis
from games.catalog import GAMES
from games.models import GameSession

from .diary_zscore import DIARY_WEIGHTS, calculate_diary_z_score

# 雷達圖的軸，順序就是前端畫的順序；source 是資料來源（遊戲 id 或聲影日記）
DIMENSIONS = [
    {"dimension": "attention", "label": "注意力", "source": "market_route"},
    {"dimension": "working_memory", "label": "工作記憶", "source": "memory_recall"},
    {"dimension": "executive_function", "label": "執行功能", "source": "market_sort"},
    {"dimension": "visual_spatial", "label": "視覺空間", "source": "fridge_check"},
    {"dimension": "math", "label": "數學", "source": "market_shopping"},
    {"dimension": "language", "label": "語言", "source": "diary"},
]

DIARY_SOURCE = "diary"
GAME_SOURCES = [d["source"] for d in DIMENSIONS if d["source"] != DIARY_SOURCE]
GAME_TITLES = {game["id"]: game["title"] for game in GAMES}

PERIOD_DAYS = 7

# 每款遊戲累計至少要有幾場「算得出 z_score」的場次，儀表板才顯示
REQUIRED_SESSIONS = 3


def _z_scores_by_game(user, start=None, end=None):
    """撈出使用者各遊戲已結束場次的 z_score，回傳 {遊戲 id: [z, ...]}。

    z_score 是 None 的場次（前測、歷史不足）不算。
    start／end 有給就只取 finished_at 在 [start, end) 之間的場次。
    """
    sessions = GameSession.objects.filter(
        user=user, status="finished", game__code__in=GAME_SOURCES
    )
    if start is not None:
        sessions = sessions.filter(finished_at__gte=start)
    if end is not None:
        sessions = sessions.filter(finished_at__lt=end)

    z_scores = {source: [] for source in GAME_SOURCES}
    for code, result in sessions.values_list("game__code", "result"):
        z_score = (result or {}).get("z_score")
        if z_score is not None:
            z_scores[code].append(z_score)
    return z_scores


def average_z_scores(user, start=None, end=None):
    """各遊戲在期間內的 z 平均，回傳 {遊戲 id: (平均 z 或 None, 場次數)}。"""
    return {
        source: (round(statistics.mean(values), 3) if values else None, len(values))
        for source, values in _z_scores_by_game(user, start, end).items()
    }


def diary_z_scores(user, start=None, end=None):
    """期間內每篇有效日記的 (建立時間, 語言 z)。

    以日記建立時間（Diary.created_at）判斷是否在期間內；
    無效日記（錄音太短、疑似辨識錯誤）沒有小分數，不算。
    """
    analyses = DiaryAnalysis.objects.filter(diary__user=user, is_valid=True)
    if start is not None:
        analyses = analyses.filter(diary__created_at__gte=start)
    if end is not None:
        analyses = analyses.filter(diary__created_at__lt=end)

    results = []
    for row in analyses.values("diary__created_at", *DIARY_WEIGHTS):
        z_score = calculate_diary_z_score(row)
        if z_score is not None:
            results.append((row["diary__created_at"], z_score))
    return results


def average_diary_z_score(user, start=None, end=None):
    """期間內有效日記的語言 z 平均，回傳 (平均 z 或 None, 篇數)。"""
    z_scores = [z for _, z in diary_z_scores(user, start, end)]
    if not z_scores:
        return None, 0
    return round(statistics.mean(z_scores), 3), len(z_scores)


def get_unlock_progress(user):
    """各遊戲累計（不限期間）有 z_score 的場次數，給「資料尚不足分析」時顯示進度。"""
    z_scores = _z_scores_by_game(user)
    return [
        {
            "source": source,
            "label": GAME_TITLES[source],
            "session_count": len(z_scores[source]),
        }
        for source in GAME_SOURCES
    ]


def is_unlocked(progress):
    """五款遊戲都至少玩滿 REQUIRED_SESSIONS 場才解鎖。"""
    return all(item["session_count"] >= REQUIRED_SESSIONS for item in progress)


def get_dashboard_dimensions(user, days=PERIOD_DAYS):
    """雷達圖每個軸的近 days 天 z 平均；期間內沒玩過、沒寫日記就是 None。"""
    start = timezone.now() - timedelta(days=days)
    averages = average_z_scores(user, start=start)
    # 語言軸：近 days 天有效日記的語言 z 平均；session_count 是日記篇數
    averages[DIARY_SOURCE] = average_diary_z_score(user, start=start)

    dimensions = []
    for item in DIMENSIONS:
        z_score, session_count = averages[item["source"]]
        dimensions.append({**item, "z_score": z_score, "session_count": session_count})
    return dimensions
