"""
市場買菜（market_shopping）遊戲邏輯 — Service Layer

設計原則：
- 不處理 request / Response
- 不直接操作 session_service
- 不碰 Django model
- 只負責出題、答案判定、DDA、指標與分數計算
"""

import random
import statistics

from .constants import BUDGET_OPTIONS, FOODS


TOTAL_QUESTIONS = 10
PROMOTE_STREAK = 3

SCORE_WEIGHTS = {
    "item_accuracy": 0.35,
    "change_accuracy": 0.35,
    "complete_first_try_accuracy": 0.30,
}


# =========================================================
# 出題
# =========================================================


def generate_question(difficulty):
    """
    根據難度產生市場買菜題目。

    easy:
        2 個目標食材 / 4 個選項
    medium, hard:
        4 個目標食材 / 6 個選項
    """

    if difficulty == "easy":
        target_count = 2
        option_count = 4
    else:
        target_count = 4
        option_count = 6

    target_items = random.sample(
        FOODS,
        target_count,
    )

    target_codes = {
        item["food_code"]
        for item in target_items
    }

    remaining_foods = [
        food
        for food in FOODS
        if food["food_code"] not in target_codes
    ]

    distractor_count = option_count - target_count

    distractors = random.sample(
        remaining_foods,
        distractor_count,
    )

    option_items = target_items + distractors
    random.shuffle(option_items)

    spent_amount = sum(
        item["price"]
        for item in target_items
    )

    # 預算一定大於花費，確保一定有正數找零
    available_budgets = [
        amount
        for amount in BUDGET_OPTIONS
        if amount > spent_amount
    ]

    budget = random.choice(available_budgets)

    correct_change = budget - spent_amount

    return {
        "target_items": target_items,
        "option_items": option_items,
        "budget": budget,
        "spent_amount": spent_amount,
        "correct_change": correct_change,
    }


def build_question_payload(
    current_question,
    difficulty,
    question_number,
):
    """
    將目前題目轉換成前端需要的格式。
    """

    shopping_list = [
        {
            "food_code": item["food_code"],
            "food_name": item["food_name"],
        }
        for item in current_question["target_items"]
    ]

    selection_options = [
        {
            "food_code": item["food_code"],
            "food_name": item["food_name"],
        }
        for item in current_question["option_items"]
    ]

    return {
        "difficulty": difficulty,
        "current_question": question_number,
        "total_questions": TOTAL_QUESTIONS,
        "shopping_list": shopping_list,
        "selection_options": selection_options,
    }


# =========================================================
# 選菜判定
# =========================================================


def evaluate_item_answer(
    selected_food_codes,
    target_items,
):
    """
    判斷整組選菜答案。

    不考慮選取順序。

    error_type:
        missing_item
        extra_item
        mixed_item_error
        None
    """

    correct_codes = {
        item["food_code"]
        for item in target_items
    }

    selected_codes = set(selected_food_codes)

    missing_codes = correct_codes - selected_codes
    extra_codes = selected_codes - correct_codes

    is_correct = (
        len(selected_food_codes) == len(correct_codes)
        and not missing_codes
        and not extra_codes
    )

    error_type = None

    if not is_correct:

        if missing_codes and extra_codes:
            error_type = "mixed_item_error"

        elif missing_codes:
            error_type = "missing_item"

        elif extra_codes:
            error_type = "extra_item"

        else:
            # 理論上主要發生於重複選取相同 food_code
            error_type = "item_selection_error"

    return {
        "is_correct": is_correct,
        "error_type": error_type,
        "missing_food_codes": sorted(missing_codes),
        "extra_food_codes": sorted(extra_codes),
    }


# =========================================================
# 找零判定
# =========================================================


def evaluate_change_answer(
    selected_amount,
    correct_change,
):
    """
    判斷找零答案。

    error_type:
        change_too_low
        change_too_high
        None
    """

    is_correct = selected_amount == correct_change

    if is_correct:
        error_type = None

    elif selected_amount < correct_change:
        error_type = "change_too_low"

    else:
        error_type = "change_too_high"

    return {
        "is_correct": is_correct,
        "error_type": error_type,
    }


def generate_change_options(correct_change):
    """
    產生：
    1 個正確找零 + 2 個錯誤選項。
    """

    possible_wrong_answers = [
        correct_change - 20,
        correct_change - 10,
        correct_change - 5,
        correct_change + 5,
        correct_change + 10,
        correct_change + 20,
    ]

    possible_wrong_answers = [
        amount
        for amount in possible_wrong_answers
        if amount >= 0
        and amount != correct_change
    ]

    wrong_answers = random.sample(
        possible_wrong_answers,
        2,
    )

    change_options = (
        wrong_answers
        + [correct_change]
    )

    random.shuffle(change_options)

    return change_options


# =========================================================
# DDA
# =========================================================


def calculate_difficulty(
    difficulty,
    consecutive_correct,
):
    """
    連續完整答對 3 題升級：

    easy -> medium -> hard
    """

    difficulty_upgraded = False

    if consecutive_correct >= PROMOTE_STREAK:

        if difficulty == "easy":
            difficulty = "medium"
            consecutive_correct = 0
            difficulty_upgraded = True

        elif difficulty == "medium":
            difficulty = "hard"
            consecutive_correct = 0
            difficulty_upgraded = True

    return {
        "difficulty": difficulty,
        "consecutive_correct": consecutive_correct,
        "difficulty_upgraded": difficulty_upgraded,
    }


# =========================================================
# Reaction Time
# =========================================================


def _valid_reaction_times(records):
    """
    只留下有效的 reaction_time_ms。
    """

    return [
        record["reaction_time_ms"]
        for record in records
        if isinstance(record.get("reaction_time_ms"), (int, float))
        and record["reaction_time_ms"] >= 0
    ]


def _calculate_rt_stats(records):
    """
    計算平均 RT 與 CV。

    CV = 標準差 / 平均值
    """

    reaction_times = _valid_reaction_times(records)

    if not reaction_times:
        return {
            "mean_ms": None,
            "cv": None,
        }

    mean_rt = statistics.mean(reaction_times)

    if len(reaction_times) < 2:
        rt_cv = 0.0

    else:
        std_rt = statistics.stdev(reaction_times)

        if mean_rt == 0:
            rt_cv = 0.0
        else:
            rt_cv = std_rt / mean_rt

    return {
        "mean_ms": round(mean_rt, 2),
        "cv": round(rt_cv, 3),
    }


# =========================================================
# 一場結束：計算五大指標
# =========================================================


def calculate_metrics(
    step_records,
    total_questions=TOTAL_QUESTIONS,
):
    """
    計算市場買菜一整場的五大指標。

    1. 選菜首次正確率
    2. 找零首次正確率
    3. 整題一次完成率
    4. RT
    5. RT CV
    """

    # 只使用每個階段第一次作答，
    # 避免第二、第三次重試影響正式指標。
    first_item_records = [
        record
        for record in step_records
        if record.get("phase") == "item"
        and record.get("attempt_number") == 1
    ]

    first_change_records = [
        record
        for record in step_records
        if record.get("phase") == "change"
        and record.get("attempt_number") == 1
    ]

    # -------------------------
    # 指標 1：選菜首次正確率
    # -------------------------

    item_first_try_correct_count = sum(
        1
        for record in first_item_records
        if record.get("is_correct") is True
    )

    item_accuracy = (
        item_first_try_correct_count
        / total_questions
        * 100
    )

    # -------------------------
    # 指標 2：找零首次正確率
    # -------------------------

    checkout_question_count = len(first_change_records)

    change_first_try_correct_count = sum(
        1
        for record in first_change_records
        if record.get("is_correct") is True
    )

    if checkout_question_count > 0:
        change_accuracy = (
            change_first_try_correct_count
            / checkout_question_count
            * 100
        )
    else:
        change_accuracy = None

    # -------------------------
    # 指標 3：整題一次完成率
    # -------------------------

    item_by_question = {
        record["question_number"]: record
        for record in first_item_records
    }

    change_by_question = {
        record["question_number"]: record
        for record in first_change_records
    }

    complete_first_try_count = 0

    for question_number in range(
        1,
        total_questions + 1,
    ):
        item_record = item_by_question.get(
            question_number
        )

        change_record = change_by_question.get(
            question_number
        )

        if (
            item_record
            and change_record
            and item_record.get("is_correct") is True
            and change_record.get("is_correct") is True
        ):
            complete_first_try_count += 1

    complete_first_try_accuracy = (
        complete_first_try_count
        / total_questions
        * 100
    )

    # -------------------------
    # 指標 4、5：RT 與 CV
    # -------------------------

    item_rt = _calculate_rt_stats(
        first_item_records
    )

    change_rt = _calculate_rt_stats(
        first_change_records
    )

    overall_rt = _calculate_rt_stats(
        first_item_records
        + first_change_records
    )

    return {
        "item_first_try_correct_count":
            item_first_try_correct_count,

        "item_accuracy":
            round(item_accuracy, 2),

        "checkout_question_count":
            checkout_question_count,

        "change_first_try_correct_count":
            change_first_try_correct_count,

        "change_accuracy":
            (
                round(change_accuracy, 2)
                if change_accuracy is not None
                else None
            ),

        "complete_first_try_count":
            complete_first_try_count,

        "complete_first_try_accuracy":
            round(
                complete_first_try_accuracy,
                2,
            ),

        "item_rt_mean_ms":
            item_rt["mean_ms"],

        "change_rt_mean_ms":
            change_rt["mean_ms"],

        "overall_rt_mean_ms":
            overall_rt["mean_ms"],

        "item_rt_cv":
            item_rt["cv"],

        "change_rt_cv":
            change_rt["cv"],

        "overall_rt_cv":
            overall_rt["cv"],
    }


# =========================================================
# 正式 Score
# =========================================================


def calculate_score(metrics):
    """
    暫定正式分數：

    選菜首次正確率 35%
    找零首次正確率 35%
    整題一次完成率 30%

    RT / CV 暫時不納入總分，
    保留為獨立分析指標。
    """

    item_accuracy = metrics["item_accuracy"]

    # 若整場完全沒有進入找零，
    # 代表找零能力沒有成功完成測量。
    # 目前總分保守記為 0 分的找零項目，
    # 避免因「沒有作答」反而提高分數。
    change_accuracy = (
        metrics["change_accuracy"]
        if metrics["change_accuracy"] is not None
        else 0
    )

    complete_accuracy = (
        metrics["complete_first_try_accuracy"]
    )

    score = (
        item_accuracy
        * SCORE_WEIGHTS["item_accuracy"]
        + change_accuracy
        * SCORE_WEIGHTS["change_accuracy"]
        + complete_accuracy
        * SCORE_WEIGHTS[
            "complete_first_try_accuracy"
        ]
    )

    return round(score)