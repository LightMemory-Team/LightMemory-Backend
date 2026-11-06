"""聲影日記的語言 z-score：儀表板與週報「語言」軸用。

不改 diary 原本的分析：每篇日記的 5 個小分數（每個 0～4 分）已經由
diary/analysis.py 算好、存在 DiaryAnalysis，這裡只拿來換算成 z。

跟遊戲一樣（games/zscore.py）：每篇日記的每個小分數跟「更早的有效日記」比，
基準資料少時偏向全體使用者、越多越偏向自己（收縮估計），z 限制在 ±2，
等權重加權成一篇的語言 z，再做二階段標準化；儀表板再取近 7 天多篇的平均。
全體使用者的日記也不夠（個人內自由度不滿 3）時是 None（資料不足，不給
假分數）。不使用寫死的常模：等測試資料累積夠了，再依真實資料決定。
歷史都存在 DiaryAnalysis，z 隨時都能現算，不用存進資料表。
"""

from games.zscore import composite_z_score

# {指標: (權重, 是否越低越好)}；5 個小分數都是越高越好。
# 一律等權重（Dawes, 1979：資料不足以估計權重時，等權重通常不輸精算權重），
# 跟 diary/analysis.py 的 communication_score 權重無關；等資料夠了再依因素分析調整
METRIC_RULES = {
    "fluency_score": (1.0, False),
    "information_score": (1.0, False),
    "sentence_score": (1.0, False),
    "naming_score": (1.0, False),
    "semantic_score": (1.0, False),
}


def calculate_language_z_score(scores, personal_history, population_by_user):
    """依一篇日記的 5 個小分數，跟更早的日記比，算出語言 z（±2 內，小數 3 位）。

    scores: {指標名稱: 分數}，例如 DiaryAnalysis 的欄位值。
    personal_history: 自己更早的有效日記小分數清單（不含這篇），格式同 scores。
    population_by_user: 其他使用者更早的有效日記小分數，依使用者分組
        {user_id: [小分數, ...]}。
    任一指標沒有值（例如無效日記沒有算分）、或歷史不足時回傳 None。
    """
    if any(scores.get(name) is None for name in METRIC_RULES):
        return None
    z_score = composite_z_score(
        scores, personal_history, population_by_user, METRIC_RULES
    )
    return None if z_score is None else round(z_score, 3)
