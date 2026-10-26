"""聲影日記的語言 z-score：儀表板與週報「語言」軸用。

不改 diary 原本的分析：每篇日記的 5 個小分數（每個 0～4 分）已經由
diary/analysis.py 算好、存在 DiaryAnalysis，這裡只拿來換算成 z。

比照遊戲的做法（games/zscore.py）：每篇日記的每個小分數跟「更早的有效日記」
比，z 限制在 ±2、再加權成一篇的語言 z；儀表板再取近 7 天多篇的平均。
自己更早的日記不滿 3 篇時借全體使用者更早的日記，全體也不夠就是 None
（資料不足，不給假分數）。不使用寫死的常模：等測試資料累積夠了，再依真實
資料決定。歷史都存在 DiaryAnalysis，z 隨時都能現算，不用存進資料表。
"""

from games.zscore import metric_z_scores, weighted_metric_z_score

# {指標: (權重, 是否越低越好)}；5 個小分數都是越高越好。
# 權重同 diary/analysis.py 的 communication_score，讓「溝通分數」和「語言 z」
# 的意思一致；那邊改權重時這裡也要改（tests_diary_zscore.py 會檢查兩邊一致）
METRIC_RULES = {
    "fluency_score": (0.20, False),
    "information_score": (0.20, False),
    "sentence_score": (0.20, False),
    "naming_score": (0.15, False),
    "semantic_score": (0.25, False),
}


def calculate_language_z_score(scores, personal_history, population_history):
    """依一篇日記的 5 個小分數，跟更早的日記比，算出語言 z（±2 內，小數 3 位）。

    scores: {指標名稱: 分數}，例如 DiaryAnalysis 的欄位值。
    personal_history / population_history: 更早的有效日記小分數清單（不含這篇），
        格式同 scores。
    任一指標沒有值（例如無效日記沒有算分）、或歷史不足時回傳 None。
    """
    if any(scores.get(name) is None for name in METRIC_RULES):
        return None
    z_by_metric = metric_z_scores(
        scores, personal_history, population_history, METRIC_RULES
    )
    z_score = weighted_metric_z_score(z_by_metric, METRIC_RULES)
    return None if z_score is None else round(z_score, 3)
