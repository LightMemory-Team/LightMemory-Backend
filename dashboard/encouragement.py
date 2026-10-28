"""儀表板機器人卡片：看長者的總體狀況，回傳趨勢代碼給前端翻成鼓勵文字。

跟週報不同：週報只看「上週 vs 再前一週」，這裡看所有週的資料。
1. 每週分數：同週報（get_weekly_scores_history），那週有分數的能力取平均
2. 總體分數：以某一週為基準，把基準週和之前所有有資料的週加權平均，
   權重 = WEEK_WEIGHT_DECAY ^ (跟基準週差幾週)，越近的週越重
3. 「累計到最近一個有資料的週」vs「累計到再前一個有資料的週」的總體分數，
   差 ±3 分以上才算進步／多練習（門檻同週報）

跟儀表板同一個解鎖條件：6 個能力（5 款遊戲＋聲影日記）都各累積
REQUIRED_SESSIONS 次有分數的紀錄才給建議。只讀資料、不寫入任何資料表。
"""

from datetime import timedelta

from django.utils import timezone

from .services import get_trend, get_unlock_progress, is_unlocked, overall_score
from .weekly_report import get_weekly_scores_history

# 每往前一週，權重乘上這個數：基準週 1、前一週 0.8、再前一週 0.64…
WEEK_WEIGHT_DECAY = 0.8


def weighted_overall_score(weekly_scores, base_week):
    """以 base_week 為基準的總體分數：base_week 和之前有分數的週加權平均。

    weekly_scores: {週一日期: 那週分數}，只放有分數的週。
    距離照日曆週數算，中間沒資料的週也算（隔 2 週，權重就乘 2 次）。
    """
    pairs = [
        (score, WEEK_WEIGHT_DECAY ** ((base_week - week).days // 7))
        for week, score in weekly_scores.items()
        if week <= base_week
    ]
    if not pairs:
        return None
    total_weight = sum(weight for _, weight in pairs)
    return round(sum(score * weight for score, weight in pairs) / total_weight)


def get_encouragement(user):
    """回傳 {trend, overall_score, previous_overall_score}；6 個能力沒解鎖時回傳 None。

    trend 是 up（進步）／steady（持平）／practice（多練習）；只有一週資料時是 None。
    """
    if not is_unlocked(get_unlock_progress(user)):
        return None

    today = timezone.localdate()
    this_monday = today - timedelta(days=today.weekday())
    weekly_scores = {}
    for week, scores in get_weekly_scores_history(user, this_monday).items():
        score = overall_score(scores)
        if score is not None:
            weekly_scores[week] = score

    data_weeks = sorted(weekly_scores)
    current = (
        weighted_overall_score(weekly_scores, data_weeks[-1]) if data_weeks else None
    )
    previous = (
        weighted_overall_score(weekly_scores, data_weeks[-2])
        if len(data_weeks) >= 2
        else None
    )
    return {
        "trend": get_trend(current, previous),
        "overall_score": current,
        "previous_overall_score": previous,
    }
