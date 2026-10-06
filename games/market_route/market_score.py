"""菜市場找路（market_route）計分模組。

純函式：輸入答題資料，回傳分數，不碰資料庫。
規則詳見規格書「四、計分邏輯」。
"""

BASE_SCORE_BY_ATTEMPT = {
    1: 10,
    2: 6,
    3: 3,
}

DIFFICULTY_MULTIPLIER = {
    "basic": 1.0,
    "intermediate": 1.3,
    "advanced": 1.6,
}

SPEED_BONUS_SCORE = 2
SPEED_BONUS_RATIO = 0.5


def calculate_base_score(attempt_number, is_correct, is_timeout):
    """依這次嘗試的結果算基礎分。

    超時、跳題（第 3 次仍答錯）或答錯都是 0 分，不倒扣。
    """
    if is_timeout or not is_correct:
        return 0
    return BASE_SCORE_BY_ATTEMPT.get(attempt_number, 0)


def calculate_speed_bonus(is_correct, response_time_ms, exposure_time_ms):
    """答對且反應時間 <= 曝光時間的 50% → +2 分。"""
    if not is_correct or response_time_ms is None:
        return 0
    if response_time_ms <= exposure_time_ms * SPEED_BONUS_RATIO:
        return SPEED_BONUS_SCORE
    return 0


def calculate_step_score(
    *,
    attempt_number,
    stage,
    is_correct,
    is_timeout,
    response_time_ms,
    exposure_time_ms,
):
    """算單題（單次嘗試）得分：基礎分 x 難度係數 + 速度加成。"""
    base_score = calculate_base_score(attempt_number, is_correct, is_timeout)
    multiplier = DIFFICULTY_MULTIPLIER[stage]
    speed_bonus = calculate_speed_bonus(is_correct, response_time_ms, exposure_time_ms)
    return round(base_score * multiplier) + speed_bonus


def calculate_total_score(step_results):
    """算單場總分：20 題（每題可能多次嘗試）的單題得分加總。

    step_results: list of dict，每筆為一次嘗試，欄位同 calculate_step_score 的參數。
    """
    return sum(calculate_step_score(**step) for step in step_results)
