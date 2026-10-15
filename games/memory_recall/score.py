"""煮菜過程（memory_recall）計分模組。

純函式：輸入答題資料，回傳分數，不碰資料庫。
規則詳見規格書「五、計分邏輯」。
"""

BASE_SCORE = 10

DIFFICULTY_MULTIPLIER = {
    "basic": 1.0,
    "intermediate": 1.3,
    "advanced": 1.6,
}

# 結束畫面給長者看的分數範圍，最低 1 分（不出現 0 分）
MIN_DISPLAY_SCORE = 1
MAX_DISPLAY_SCORE = 100


def calculate_step_score(*, stage, is_correct):
    """算單輪得分：答對才有分，基礎分 x 難度係數；答錯 0 分，不倒扣。

    不設計速度加成：計時制下「快」已直接反映在時間內可作答題數上。
    """
    if not is_correct:
        return 0
    return round(BASE_SCORE * DIFFICULTY_MULTIPLIER[stage])


def calculate_total_score(step_results):
    """算單場總分：所有答對題目的單輪得分加總。

    step_results: list of dict，每筆為一輪的紀錄，含 stage、is_correct。
    """
    return sum(calculate_step_score(**step) for step in step_results)


def z_score_to_total_score(z_score):
    """把本場工作記憶 z-score（±2 內）換算成結束畫面的 1～100 分。

    z = -2 → 1、z = 0 → 50、z = +2 → 100；z 為 None（前測、歷史不足）回傳 None。
    """
    if z_score is None:
        return None
    score = round(50 + 25 * z_score)
    return max(MIN_DISPLAY_SCORE, min(MAX_DISPLAY_SCORE, score))
