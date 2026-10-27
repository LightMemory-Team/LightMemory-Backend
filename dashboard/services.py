"""儀表板（雷達圖）資料：各認知維度近幾天的 z-score 平均。

只讀資料、不寫入任何資料表：每次請求當下計算，所以數字永遠是最新的。
- 遊戲：從已結束場次 GameSession.result 裡的 z_score 計算。z_score 由各遊戲
  結算時存入，已限制在 ±2 內；算不出來（前測、歷史不足）時為 None。
- 聲影日記（語言）：從 DiaryAnalysis 的 5 個小分數現算每篇的語言 z
  （跟更早的有效日記比，見 diary_zscore.py），只算有效的日記。
"""

import statistics
from datetime import timedelta
from itertools import groupby
from operator import itemgetter

from django.utils import timezone

from diary.models import DiaryAnalysis
from games.catalog import GAMES
from games.models import GameSession

from .diary_zscore import METRIC_RULES as LANGUAGE_METRIC_RULES
from .diary_zscore import calculate_language_z_score

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

# demo 帳號的種子日記（seed_demo 指令建立）的錄音路徑前綴；
# 這些日記不是真人寫的，不能拿來當全體基準
SEED_DIARY_AUDIO_PREFIX = "seed/"
GAME_SOURCES = [d["source"] for d in DIMENSIONS if d["source"] != DIARY_SOURCE]
GAME_TITLES = {game["id"]: game["title"] for game in GAMES}

PERIOD_DAYS = 7

# 兩段期間的分數差多少以上，才算「進步」或「多練習」；差距小於這個算「持平」
# 週報（本週 vs 上週）和儀表板機器人卡片（近 7 天 vs 前 7 天）共用
TREND_THRESHOLD = 3

# 每款遊戲、聲影日記累計至少要有幾場（篇）「算得出 z_score」的紀錄，儀表板才顯示
REQUIRED_SESSIONS = 3

DIARY_LABEL = "聲影日記"


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


def _counts_for_population(row):
    """這篇日記能不能當「全體基準」：排除測試帳號、demo 帳號的種子日記。"""
    is_seed = (row["diary__audio_path"] or "").startswith(SEED_DIARY_AUDIO_PREFIX)
    return not row["diary__user__is_staff"] and not is_seed


def diary_z_scores(user, start=None, end=None):
    """期間內這位使用者每篇有效日記的 (建立時間, 語言 z)。

    以日記建立時間（Diary.created_at）判斷是否在期間內；
    無效日記（錄音太短、疑似辨識錯誤）沒有小分數，不算。

    每篇跟「更早建立」的有效日記比：自己的當個人歷史，其他使用者的依使用者
    分組當全體基準（排除測試帳號、demo 日記），基準資料少時偏向全體、越多
    越偏向自己（見 games/zscore.py）。所以期間以前的日記、別人的日記也要
    拿來當歷史。一次查出 end 以前全部的有效日記、依建立時間掃過去，避免每篇
    各查一次資料庫。歷史不足、算不出 z 的日記不列入。
    """
    analyses = DiaryAnalysis.objects.filter(is_valid=True)
    if end is not None:
        analyses = analyses.filter(diary__created_at__lt=end)
    rows = analyses.order_by("diary__created_at").values(
        "diary__user_id",
        "diary__created_at",
        "diary__user__is_staff",
        "diary__audio_path",
        *LANGUAGE_METRIC_RULES,
    )

    personal_history, population_by_user = [], {}
    results = []
    for created_at, same_time_rows in groupby(
        rows, key=itemgetter("diary__created_at")
    ):
        same_time_rows = list(same_time_rows)
        in_period = start is None or created_at >= start
        for row in same_time_rows:
            if in_period and row["diary__user_id"] == user.id:
                z_score = calculate_language_z_score(
                    row, personal_history, population_by_user
                )
                if z_score is not None:
                    results.append((created_at, z_score))
        # 算完同一時間的日記才放進歷史：同時建立的日記不互相比
        for row in same_time_rows:
            if row["diary__user_id"] == user.id:
                personal_history.append(row)
            elif _counts_for_population(row):
                population_by_user.setdefault(row["diary__user_id"], []).append(row)
    return results


def average_diary_z_score(user, start=None, end=None):
    """期間內有效日記的語言 z 平均，回傳 (平均 z 或 None, 篇數)。"""
    z_scores = [z for _, z in diary_z_scores(user, start, end)]
    if not z_scores:
        return None, 0
    return round(statistics.mean(z_scores), 3), len(z_scores)


def get_unlock_progress(user):
    """各遊戲、聲影日記累計（不限期間）有 z_score 的場次（篇）數。

    給「資料尚不足分析」時顯示進度。

    日記要算得出語言 z 才算：更早的日記不滿 3 篇（自己的和全體的都不夠）時，
    那篇沒有 z，不算進去。
    """
    z_scores = _z_scores_by_game(user)
    progress = [
        {
            "source": source,
            "label": GAME_TITLES[source],
            "session_count": len(z_scores[source]),
        }
        for source in GAME_SOURCES
    ]
    progress.append(
        {
            "source": DIARY_SOURCE,
            "label": DIARY_LABEL,
            "session_count": len(diary_z_scores(user)),
        }
    )
    return progress


def is_unlocked(progress):
    """5 款遊戲和聲影日記都至少累積 REQUIRED_SESSIONS 場（篇）才解鎖。"""
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


def overall_score(scores_by_source):
    """整體表現 = 有分數的能力（含語言）取平均；一項都沒有就是 None。"""
    if not scores_by_source:
        return None
    return round(statistics.mean(scores_by_source.values()))


def get_trend(this_score, last_score):
    """進步 up／持平 steady／多練習 practice；任一期沒分數就是 None。

    用代碼回傳，前端翻成中文；退步用「多練習」，不出現負面字眼。
    """
    if this_score is None or last_score is None:
        return None
    diff = this_score - last_score
    if diff >= TREND_THRESHOLD:
        return "up"
    if diff <= -TREND_THRESHOLD:
        return "practice"
    return "steady"
