"""聲影日記的語言 z-score：儀表板與週報「語言」軸用。

不改 diary 原本的分析：每篇日記的 5 個小分數（每個 0～4 分）已經由
diary/analysis.py 算好、存在 DiaryAnalysis，這裡只拿來換算成 z。

比照整理菜籃（market_sort）的做法：每篇日記跟寫死的常模比、每個指標的 z
限制在 ±2、再加權成一篇的語言 z；儀表板再取近 7 天多篇的平均。

常模是暫定起始值：先用 0～4 分量表的中點（平均 2、標準差 1），這時一篇的
語言 z 剛好等於 communication_score − 2。累積足夠的日記後，再依真實資料
替每個指標換上自己的常模，程式結構不用改。常模固定，所以 z 隨時都能從
DiaryAnalysis 現算，不用存進資料表。
"""

from games.zscore import to_z_score, weighted_average

# 權重同 diary/analysis.py 的 communication_score，讓「溝通分數」和「語言 z」
# 的意思一致；那邊改權重時這裡也要改（tests_diary_zscore.py 會檢查兩邊一致）
DIARY_WEIGHTS = {
    "fluency_score": 0.20,
    "information_score": 0.20,
    "sentence_score": 0.20,
    "naming_score": 0.15,
    "semantic_score": 0.25,
}

# 指標名稱: (常模平均, 常模標準差)；暫定值，見模組說明
DIARY_NORMS = {
    "fluency_score": (2.0, 1.0),
    "information_score": (2.0, 1.0),
    "sentence_score": (2.0, 1.0),
    "naming_score": (2.0, 1.0),
    "semantic_score": (2.0, 1.0),
}


def calculate_diary_z_score(scores):
    """依一篇日記的 5 個小分數算出語言 z（±2 內，小數 3 位）。

    scores: {指標名稱: 分數}，例如 DiaryAnalysis 的欄位值。
    任一指標沒有值（例如無效日記沒有算分）就回傳 None。
    """
    weighted_z_scores = []
    for name, weight in DIARY_WEIGHTS.items():
        value = scores.get(name)
        if value is None:
            return None
        weighted_z_scores.append((to_z_score(value, DIARY_NORMS[name]), weight))
    return round(weighted_average(weighted_z_scores), 3)
