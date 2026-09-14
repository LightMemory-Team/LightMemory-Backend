"""
整理菜籃遊戲（market-sort）計算邏輯 — Service Layer

設計原則：
- 這個模組不 import Django 的 models 或 request/response 相關的東西，
  只負責「輸入資料 → 算出結果」，方便獨立測試、也方便未來如果要在
  Django shell 或 celery 背景工作裡呼叫，不用假裝自己是一個 API 請求。
- 邊界案例一律用例外處理，不用預設值悄悄蓋過去，讓 View 層自己決定
  要回傳哪個 error.code 給前端。
"""

import statistics


# ---- 自訂例外：讓 View 層可以分別接住不同的錯誤情況 ----

class InsufficientDataError(Exception):
    """資料不足以計算某項指標時拋出（例如 switch 題數為 0）"""
    pass


# ---- 常數設定：常模、加權、階段題數 ----
# ⚠️ 常模數字目前為假資料，待實際測試數據校正，見計算邏輯文件第5節

NORM_REFERENCE = {
    "switch_cost_rt": {"mean": 1.5, "std": 0.5, "direction": "smaller_is_better"},
    "persistent_error_rate": {"mean": 0.30, "std": 0.10, "direction": "smaller_is_better"},
    "switch_accuracy": {"mean": 0.60, "std": 0.15, "direction": "larger_is_better"},
    "learning_speed": {"mean": 6, "std": 2, "direction": "smaller_is_better"},
}

WEIGHTS = {
    "switch_cost_rt": 0.30,
    "persistent_error_rate": 0.35,
    "switch_accuracy": 0.20,
    "learning_speed": 0.15,
}

# 28題版四階段累計題數：階段一結束於第5題、階段二第10題...
STAGE_BOUNDARIES = [5, 10, 15, 28]


# ---- Step2：4 項不受題數影響的原始指標 ----

def calculate_raw_metrics(questions: list[dict]) -> dict:
    """
    輸入：單場的 questions[] 陣列（每題含 is_correct, reaction_time_ms, trial_type, error_type）
    輸出：switch_cost_rt, switch_cost_accuracy, switch_accuracy, persistent_error_rate, rt_cv
    """
    repeat_q = [q for q in questions if q["trial_type"] == "repeat"]
    switch_q = [q for q in questions if q["trial_type"] == "switch"]

    if not switch_q:
        raise InsufficientDataError("這場資料沒有任何 switch 題，無法計算切換相關指標")
    if not repeat_q:
        raise InsufficientDataError("這場資料沒有任何 repeat 題，無法計算切換相關指標")

    repeat_correct = [q for q in repeat_q if q["is_correct"]]
    switch_correct = [q for q in switch_q if q["is_correct"]]

    if not repeat_correct:
        raise InsufficientDataError("repeat 題全部答錯，無法計算 repeat 平均反應時間")
    if not switch_correct:
        raise InsufficientDataError("switch 題全部答錯，無法計算 switch 平均反應時間")

    # 指標1：切換成本 RT
    repeat_rt_avg = statistics.mean(q["reaction_time_ms"] for q in repeat_correct) / 1000
    switch_rt_avg = statistics.mean(q["reaction_time_ms"] for q in switch_correct) / 1000
    switch_cost_rt = switch_rt_avg - repeat_rt_avg

    # 指標2：切換成本正確率（僅供參考，不用於 z 分數）與 switch 自身正確率（用於 z 分數）
    repeat_accuracy = len(repeat_correct) / len(repeat_q)
    switch_accuracy = len(switch_correct) / len(switch_q)
    switch_cost_accuracy = repeat_accuracy - switch_accuracy

    # 指標3：持續性錯誤率
    persistent_errors = [q for q in switch_q if q["error_type"] == "persistent"]
    persistent_error_rate = len(persistent_errors) / len(switch_q)

    # 指標5：反應時間 CV
    all_correct_rts = [q["reaction_time_ms"] / 1000 for q in repeat_correct + switch_correct]
    rt_mean = statistics.mean(all_correct_rts)
    if len(all_correct_rts) < 2:
        rt_cv = 0.0  # 樣本數不足以算標準差，記為0而非報錯
    else:
        rt_std = statistics.stdev(all_correct_rts)
        rt_cv = 0.0 if rt_std == 0 else rt_std / rt_mean  # 全部時間都一樣時，標準差為0，CV記為0

    return {
        "switch_cost_rt": round(switch_cost_rt, 2),
        "switch_cost_accuracy": round(switch_cost_accuracy, 3),
        "switch_accuracy": round(switch_accuracy, 3),
        "persistent_error_rate": round(persistent_error_rate, 3),
        "rt_cv": round(rt_cv, 3),
    }


# ---- Step2：規則學習速度（依題號反推階段，含邊界案例處理）----

def calculate_learning_speed(questions: list[dict]) -> float:
    """
    輸入：依 question_index 排序的 questions[]（需含 is_correct, trial_type）
    輸出：3 次大階段邊界切換的「追上新規則所需題數」平均值

    邊界規則（對應計算邏輯文件 3.2 節）：
    - 整段都沒追上 → 記為該區段實際題數（不排除）
    - 區段內提前又發生下一次 switch → 觀察區間提前截斷
    """
    if len(questions) < STAGE_BOUNDARIES[-1]:
        raise InsufficientDataError(
            f"題目數量不足（收到 {len(questions)} 題，需要 {STAGE_BOUNDARIES[-1]} 題），無法計算學習速度"
        )

    catch_up_lengths = []

    for start, end in zip(STAGE_BOUNDARIES[:-1], STAGE_BOUNDARIES[1:]):
        count = 0
        caught_up = False

        for k in range(start, min(end, len(questions))):
            count += 1
            if questions[k]["is_correct"]:
                catch_up_lengths.append(count)
                caught_up = True
                break
            if k > start and questions[k]["trial_type"] == "switch":
                catch_up_lengths.append(count)
                caught_up = True
                break

        if not caught_up:
            catch_up_lengths.append(count)

    return sum(catch_up_lengths) / len(catch_up_lengths)


# ---- Step3~5：z分數、加權、換算0-100分 ----

def to_z_score(value: float, metric_name: str) -> float:
    norm = NORM_REFERENCE[metric_name]
    if norm["direction"] == "smaller_is_better":
        return (norm["mean"] - value) / norm["std"]
    else:
        return (value - norm["mean"]) / norm["std"]


def calculate_cognitive_flexibility_score(questions: list[dict]) -> dict:
    """
    整合入口：輸入完整 questions[]，跑完 Step2~5，回傳完整結果。
    這支函式就是未來 View 唯一需要呼叫的東西。
    """
    raw_metrics = calculate_raw_metrics(questions)
    learning_speed = calculate_learning_speed(questions)
    raw_metrics["learning_speed"] = round(learning_speed, 2)

    z_scores = {
        "switch_cost_rt_z": round(to_z_score(raw_metrics["switch_cost_rt"], "switch_cost_rt"), 3),
        "persistent_error_rate_z": round(to_z_score(raw_metrics["persistent_error_rate"], "persistent_error_rate"), 3),
        "switch_accuracy_z": round(to_z_score(raw_metrics["switch_accuracy"], "switch_accuracy"), 3),
        "learning_speed_z": round(to_z_score(learning_speed, "learning_speed"), 3),
    }

    weighted_z = (
        z_scores["switch_cost_rt_z"] * WEIGHTS["switch_cost_rt"]
        + z_scores["persistent_error_rate_z"] * WEIGHTS["persistent_error_rate"]
        + z_scores["switch_accuracy_z"] * WEIGHTS["switch_accuracy"]
        + z_scores["learning_speed_z"] * WEIGHTS["learning_speed"]
    )

    final_score = 50 + 20 * weighted_z
    final_score = max(10, min(90, final_score))

    return {
        "raw_metrics": raw_metrics,
        "z_scores": z_scores,
        "cognitive_flexibility_score": round(final_score),
    }

def determine_encouragement_tier(current_score: int, highest_score: int) -> str:
    """
    ⚠️ 門檻為暫定值，待確認
    """
    diff = highest_score - current_score
    if diff <= 0:
        return "new_best"
    elif diff <= 15:
        return "close_to_best"
    else:
        return "keep_going"