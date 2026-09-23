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
