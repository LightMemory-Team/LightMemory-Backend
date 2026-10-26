"""
整理菜籃遊戲（market-sort）計算邏輯 — Service Layer

設計原則：
- 這個模組不 import Django 的 models 或 request/response 相關的東西，
  只負責「輸入資料 → 算出結果」，方便獨立測試、也方便未來如果要在
  Django shell 或 celery 背景工作裡呼叫，不用假裝自己是一個 API 請求。
- 邊界案例一律用例外處理，不用預設值悄悄蓋過去，讓 View 層自己決定
  要回傳哪個 error.code 給前端。

【2026-09-30 短期修正】
Wen 用這支檔案原本的公式模擬 2000 場「答對 4/28」的情況，平均分數 76.6
分，跟實測的 77 分一致，證實現行公式會讓幾乎沒答對的人也拿到高分，主因
是 persistent_error_rate 在目前的玩法下永遠算得出 0（規則判斷用的兩個
enum 型別本來就不可能相等），單這一項就固定多拿約 21 分。

這次是「不改玩法」的短期修正（長期是否改成固定兩籃玩法，讓 persistent
error 真的判得出來，待團隊會議決定，不在這次範圍內）：
    1. 拿掉 persistent_error_rate，因為現在的玩法測不到
    2. 加入「整體正確率」，權重最高，讓亂答的分數真的會降
    3. 常模數字修正（尤其學習速度的平均值，原本的 6 題比 28 題版最多可能
       發生的 5 次還大，導致這項 z 分數永遠是正的）
    4. 每項 z 分數先限制在 ±2 再加權，避免單一項爆掉把總分拉走
    5. 切換成本 RT 設最低門檻：repeat 題、switch 題都要各自答對 3 題以上
       才計算，不夠就跳過，權重自動分給其他項目
    6. switch 題全部答錯時不再回 400（ALL_SWITCH_INCORRECT），照樣給分，
       只是分數會落在低分區——因為就算切換成本沒得算，其他 3 項指標
       仍然足以反映玩家的表現
    7. 第 1 題不算進 switch 題的統計（前端另外會把第 1 題的 trial_type
       改標成 repeat，這裡的過濾是防止時序不一致時後端還是拿到錯誤標記）

詳見 Wen 2026-09-29 的分析文件「整理菜籃計分問題與修改建議」。

【2026-10-26 改成跟自己的歷史比】
團隊討論後決定不再使用寫死的常模（上面第 3 點的數字沒有實際資料支撐）：
    1. 每個指標改跟自己過去場次的原始指標比（games/zscore.py），自己不滿
       3 場借全體使用者的歷史，全體也不夠就是 None（資料不足，不給假分數）
    2. 分數改成 50 + 25z（1～100），跟其他遊戲、週報一致
等測試資料累積夠了，再依真實資料決定常模。
"""

import statistics

from games.zscore import (
    metric_z_scores,
    weighted_metric_z_score,
    z_score_to_display_score,
)

# ---- 自訂例外：讓 View 層可以分別接住不同的錯誤情況 ----


class InsufficientDataError(Exception):
    """資料不足以計算某項指標時拋出（例如整場都沒有 switch 題，屬於資料
    格式問題，不是「玩家表現不好」——玩家表現不好不會再讓這裡出錯，
    只會反映在分數上）"""

    def __init__(self, message, code="CALCULATION_ERROR"):
        super().__init__(message)
        self.code = code


# ---- 常數設定：指標規則、階段題數 ----

# {指標: (權重, 是否越低越好)}；每個指標跟自己的歷史比，z 限制在 ±2
METRIC_RULES = {
    "overall_accuracy": (0.40, False),
    "switch_accuracy": (0.25, False),
    "switch_cost_rt": (0.20, True),
    "learning_speed": (0.15, True),
}

# switch_cost_rt 至少要 repeat、switch 各答對這麼多題才計算，不夠就跳過
MIN_CORRECT_FOR_SWITCH_COST_RT = 3

# 28題版四階段累計題數：階段一結束於第5題、階段二第10題...
STAGE_BOUNDARIES = [5, 10, 15, 28]


# ---- Step2：原始指標（整體正確率、switch 正確率、切換成本 RT）----


def calculate_raw_metrics(questions: list[dict]) -> dict:
    """
    輸入：單場的 questions[] 陣列（每題含 question_index, is_correct,
    reaction_time_ms, trial_type, error_type）
    輸出：overall_accuracy, switch_accuracy, switch_cost_rt（資料不足時為
    None）、以及僅供參考、不參與計分的 switch_cost_accuracy、rt_cv

    第 1 題不算進 switch 題的統計（見檔案開頭的說明），如果它被標成
    switch，這裡會直接跳過，不會被算進 switch_q 也不會算進 repeat_q。
    """
    repeat_q = [q for q in questions if q["trial_type"] == "repeat"]
    switch_q = [
        q for q in questions if q["trial_type"] == "switch" and q["question_index"] != 1
    ]

    if not switch_q:
        raise InsufficientDataError(
            "這場資料沒有任何 switch 題，無法計算切換相關指標", code="NO_SWITCH_TRIALS"
        )
    if not repeat_q:
        raise InsufficientDataError(
            "這場資料沒有任何 repeat 題，無法計算切換相關指標", code="NO_REPEAT_TRIALS"
        )

    repeat_correct = [q for q in repeat_q if q["is_correct"]]
    switch_correct = [q for q in switch_q if q["is_correct"]]

    # 指標1：整體正確率（分母用實際題數，market_sort 固定送 28 題）
    overall_accuracy = sum(1 for q in questions if q["is_correct"]) / len(questions)

    # 指標2：switch 正確率（switch 題全錯時就是 0，不再視為錯誤情況）
    switch_accuracy = len(switch_correct) / len(switch_q)

    # 指標3：切換成本 RT — 兩邊都要至少答對 MIN_CORRECT_FOR_SWITCH_COST_RT
    # 題才計算，不夠穩定就跳過，回傳 None 讓上層知道要跳過這項、把權重
    # 分給其他指標
    if (
        len(repeat_correct) >= MIN_CORRECT_FOR_SWITCH_COST_RT
        and len(switch_correct) >= MIN_CORRECT_FOR_SWITCH_COST_RT
    ):
        repeat_rt_avg = (
            statistics.mean(q["reaction_time_ms"] for q in repeat_correct) / 1000
        )
        switch_rt_avg = (
            statistics.mean(q["reaction_time_ms"] for q in switch_correct) / 1000
        )
        switch_cost_rt = round(switch_rt_avg - repeat_rt_avg, 2)
    else:
        switch_cost_rt = None

    # 以下兩項僅供參考、不參與計分（是否保留待團隊確認，見分析文件問題9）
    repeat_accuracy = len(repeat_correct) / len(repeat_q)
    switch_cost_accuracy = round(repeat_accuracy - switch_accuracy, 3)

    all_correct_rts = [
        q["reaction_time_ms"] / 1000 for q in repeat_correct + switch_correct
    ]
    if len(all_correct_rts) < 2:
        rt_cv = 0.0  # 樣本數不足以算標準差，記為0而非報錯
    else:
        rt_mean = statistics.mean(all_correct_rts)
        rt_std = statistics.stdev(all_correct_rts)
        rt_cv = 0.0 if rt_std == 0 else round(rt_std / rt_mean, 3)

    return {
        "overall_accuracy": round(overall_accuracy, 3),
        "switch_accuracy": round(switch_accuracy, 3),
        "switch_cost_rt": switch_cost_rt,
        "switch_cost_accuracy": switch_cost_accuracy,
        "rt_cv": rt_cv,
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
            f"題目數量不足（收到 {len(questions)} 題，"
            f"需要 {STAGE_BOUNDARIES[-1]} 題），無法計算學習速度",
            code="INSUFFICIENT_QUESTION_COUNT",
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


# ---- Step3~5：z分數（含 ±2 上下限）、加權（略過的指標自動不計入分母）、換算分數 ----


def calculate_executive_function_z_score(
    raw_metrics: dict, personal_history: list[dict], population_history: list[dict]
) -> tuple:
    """
    執行功能（認知彈性）z：4 個指標各自跟歷史比、限制在 ±2，再依 METRIC_RULES 加權。

    personal_history / population_history: 過去場次的 raw_metrics 清單（不含這場）。
    沒有資料的指標（切換成本 RT 答對題數不夠、或歷史不足）跳過，權重自動分給
    其他項目。回傳 (加權 z 或 None, {指標: z 或 None})。
    """
    z_by_metric = metric_z_scores(
        raw_metrics, personal_history, population_history, METRIC_RULES
    )
    return weighted_metric_z_score(z_by_metric, METRIC_RULES), z_by_metric


def _round_or_none(value):
    return None if value is None else round(value, 3)


def calculate_cognitive_flexibility_score(
    questions: list[dict],
    personal_history: list[dict] = (),
    population_history: list[dict] = (),
) -> dict:
    """
    整合入口：輸入完整 questions[] 與歷史原始指標，跑完 Step2~5，回傳完整結果。
    這支函式就是 View 唯一需要呼叫的東西。

    歷史不足（自己和全體都不滿 3 場）時 z_score、cognitive_flexibility_score
    為 None，前端顯示「資料不足」。
    """
    raw_metrics = calculate_raw_metrics(questions)
    learning_speed = calculate_learning_speed(questions)
    raw_metrics["learning_speed"] = round(learning_speed, 2)

    weighted_z, z_by_metric = calculate_executive_function_z_score(
        raw_metrics, list(personal_history), list(population_history)
    )
    z_score = _round_or_none(weighted_z)

    return {
        "raw_metrics": raw_metrics,
        "z_scores": {f"{name}_z": _round_or_none(z) for name, z in z_by_metric.items()},
        # 加權後的整體 z（±2 內），給 dashboard 用
        "z_score": z_score,
        "cognitive_flexibility_score": z_score_to_display_score(z_score),
    }


def determine_encouragement_tier(current_score, highest_score):
    """
    ⚠️ 門檻為暫定值，待確認
    固定三種值，對應結算畫面的星星／打勾／旗子三個等級圖示；
    這場或歷史沒有分數（資料不足）時回傳 None。
    """
    if current_score is None or highest_score is None:
        return None
    diff = highest_score - current_score
    if diff <= 0:
        return "great"
    elif diff <= 15:
        return "good"
    else:
        return "keep_trying"
