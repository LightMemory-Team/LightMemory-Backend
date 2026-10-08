"""
市場買菜（market_shopping）遊戲邏輯 Service Layer。
整合統一 DDA 引擎與 Session 狀態管理。
"""

import random
from django.utils import timezone

from games import session_service
from games.dda import DDAConfig, NoOpStrategy, apply_answer

from .constants import BUDGET_OPTIONS, FOODS

GAME_TYPE = "market_shopping"
TOTAL_QUESTIONS = 10
PROMOTE_STREAK = 3
STAGE_ORDER = ["easy", "medium", "hard"]

DDA_CONFIG = DDAConfig(
    stage_order=STAGE_ORDER,
    promote_streak=PROMOTE_STREAK,
)
DDA_STRATEGY = NoOpStrategy()

# 常模與 Z-score 設定
MARKET_SHOPPING_NORM = {
    "mean": 70.0,
    "std": 10.0,
}

Z_SCORE_CLAMP = 2.0


def calculate_z_score(raw_score):
    """
    依常模計算 Market Shopping 的 Z-score 與跨遊戲標準分數 (standard_score)。

    Z = (raw_score - mean) / std
    Z-score 限制在 [-Z_SCORE_CLAMP, +Z_SCORE_CLAMP]
    standard_score = 50 + 20 * z_score
    """
    mean = MARKET_SHOPPING_NORM["mean"]
    std = MARKET_SHOPPING_NORM["std"]

    if std == 0:
        z_score = 0.0
    else:
        z_score = (raw_score - mean) / std

    z_score = max(
        -Z_SCORE_CLAMP,
        min(Z_SCORE_CLAMP, z_score),
    )

    standard_score = 50 + 20 * z_score

    return {
        "z_score": round(z_score, 3),
        "standard_score": round(standard_score),
    }



def generate_question(difficulty="easy"):
    """依難度產生題目與購物清單。"""
    if difficulty == "easy":
        target_count = 2
        option_count = 4
    else:
        target_count = 4
        option_count = 6

    target_items = random.sample(FOODS, target_count)
    target_codes = {item["food_code"] for item in target_items}
    remaining_foods = [f for f in FOODS if f["food_code"] not in target_codes]
    distractor_count = option_count - target_count
    distractors = random.sample(remaining_foods, distractor_count)

    option_items = target_items + distractors
    random.shuffle(option_items)

    spent_amount = sum(item["price"] for item in target_items)
    available_budgets = [amt for amt in BUDGET_OPTIONS if amt > spent_amount]
    budget = random.choice(available_budgets)
    correct_change = budget - spent_amount

    return {
        "target_items": target_items,
        "option_items": option_items,
        "budget": budget,
        "spent_amount": spent_amount,
        "correct_change": correct_change,
    }


def build_question_payload(current_question, difficulty, question_number):
    """組出回傳給前端的題目資料。"""
    shopping_list = [
        {"food_code": item["food_code"], "food_name": item["food_name"]}
        for item in current_question["target_items"]
    ]
    selection_options = [
        {"food_code": item["food_code"], "food_name": item["food_name"]}
        for item in current_question["option_items"]
    ]
    return {
        "difficulty": difficulty,
        "current_question": question_number,
        "total_questions": TOTAL_QUESTIONS,
        "shopping_list": shopping_list,
        "selection_options": selection_options,
    }


def generate_change_options(correct_change):
    """產生 1 個正解與 2 個隨機錯誤找零選項。"""
    possible_wrong = [
        correct_change - 20,
        correct_change - 10,
        correct_change - 5,
        correct_change + 5,
        correct_change + 10,
        correct_change + 20,
    ]
    valid_wrong = [amt for amt in possible_wrong if amt >= 0 and amt != correct_change]
    wrong_answers = random.sample(valid_wrong, min(2, len(valid_wrong)))
    change_options = wrong_answers + [correct_change]
    random.shuffle(change_options)
    return change_options


def create_game_session(user):
    """建立新的 Market Shopping Session。"""
    difficulty = "easy"
    question = generate_question(difficulty)

    initial_state = {
        "user_id": user.id if user else None,
        # DDA 欄位
        "current_stage": difficulty,
        "correct_streak": 0,
        "difficulty": difficulty,
        "consecutive_correct": 0,
        # 題內狀態
        "budget": question["budget"],
        "spent_amount": question["spent_amount"],
        "correct_change": question["correct_change"],
        "total_correct": 0,
        "first_try_correct_count": 0,
        "current_wrong_count": 0,
        "current_question_had_error": False,
        "item_attempt_count": 0,
        "change_attempt_count": 0,
        "item_first_try_correct": None,
        "change_first_try_correct": None,
    }

    current_question = {
        "target_items": question["target_items"],
        "option_items": question["option_items"],
    }

    session = session_service.create_session(
        GAME_TYPE,
        user=user,
        initial_state=initial_state,
    )
    session = session_service.update_session(
        GAME_TYPE,
        session["session_id"],
        question_number=1,
        current_question=current_question,
    )
    return session


def get_session(session_id):
    """取得指定 Session。"""
    return session_service.get_session(GAME_TYPE, session_id)


def check_item_answer(session, selected_food_codes):
    """檢查選菜答案是否與正解完全一致（不看順序）。"""
    current_question = session["current_question"]
    correct_codes = [item["food_code"] for item in current_question["target_items"]]
    return len(selected_food_codes) == len(correct_codes) and set(
        selected_food_codes
    ) == set(correct_codes)


def check_change_answer(session, selected_amount):
    """檢查找零金額是否正確。"""
    return selected_amount == session["state"]["correct_change"]


def record_item_wrong(session):
    """記錄選菜錯誤，更新 DDA 連對為 0。"""
    state = session["state"]
    current_wrong = state["current_wrong_count"] + 1

    updated_fields, _ = apply_answer(
        state,
        DDA_CONFIG,
        DDA_STRATEGY,
        is_correct=False,
    )

    state_update = {
        "item_attempt_count": state["item_attempt_count"] + 1,
        "current_wrong_count": current_wrong,
        "current_question_had_error": True,
        **updated_fields,
    }
    if state["item_attempt_count"] == 0:
        state_update["item_first_try_correct"] = False

    return session_service.update_session(
        GAME_TYPE,
        session["session_id"],
        state=state_update,
    )


def record_change_wrong(session):
    """記錄找零錯誤，更新 DDA 連對為 0。"""
    state = session["state"]
    current_wrong = state["current_wrong_count"] + 1

    updated_fields, _ = apply_answer(
        state,
        DDA_CONFIG,
        DDA_STRATEGY,
        is_correct=False,
    )

    state_update = {
        "change_attempt_count": state["change_attempt_count"] + 1,
        "current_wrong_count": current_wrong,
        "current_question_had_error": True,
        **updated_fields,
    }
    if state["change_attempt_count"] == 0:
        state_update["change_first_try_correct"] = False

    return session_service.update_session(
        GAME_TYPE,
        session["session_id"],
        state=state_update,
    )


def record_change_correct_and_apply_dda(session):
    """
    找零答對，完成本題：
    - total_correct + 1
    - 若本題無任何錯誤，first_try_correct_count + 1，並計入連對
    - 透過 DDA 引擎 apply_answer 處理升階
    """
    state = session["state"]
    had_error = state["current_question_had_error"]
    total_correct = state["total_correct"] + 1
    first_try_correct_count = state["first_try_correct_count"]
    if not had_error:
        first_try_correct_count += 1

    state_update = {
        "change_attempt_count": state["change_attempt_count"] + 1,
        "total_correct": total_correct,
        "first_try_correct_count": first_try_correct_count,
    }
    if state["change_attempt_count"] == 0:
        state_update["change_first_try_correct"] = True

    # 只有從頭到尾完全沒錯才算 DDA 答對，否則算中斷
    if not had_error:
        updated_fields, action = apply_answer(
            state,
            DDA_CONFIG,
            DDA_STRATEGY,
            is_correct=True,
        )
        difficulty_upgraded = (action == "promoted")
    else:
        updated_fields, _ = apply_answer(
            state,
            DDA_CONFIG,
            DDA_STRATEGY,
            is_correct=False,
        )
        difficulty_upgraded = False

    state_update.update(updated_fields)

    session = session_service.update_session(
        GAME_TYPE,
        session["session_id"],
        state=state_update,
    )
    return session, difficulty_upgraded


def move_to_next_question(session):
    """進入下一題，若是第 10 題完成則回傳 None 並完成 session。"""
    session_id = session["session_id"]
    question_number = session["question_number"]
    state = session["state"]

    if question_number >= TOTAL_QUESTIONS:
        complete_session(session)
        return None

    current_difficulty = state.get("current_stage", state.get("difficulty", "easy"))
    question = generate_question(current_difficulty)

    current_question = {
        "target_items": question["target_items"],
        "option_items": question["option_items"],
    }

    new_state = {
        "budget": question["budget"],
        "spent_amount": question["spent_amount"],
        "correct_change": question["correct_change"],
        "item_attempt_count": 0,
        "change_attempt_count": 0,
        "item_first_try_correct": None,
        "change_first_try_correct": None,
        "current_wrong_count": 0,
        "current_question_had_error": False,
    }

    session = session_service.update_session(
        GAME_TYPE,
        session_id,
        question_number=question_number + 1,
        current_question=current_question,
        state=new_state,
    )

    return build_question_payload(
        current_question, current_difficulty, session["question_number"]
    )


def calculate_final_result(session):
    """計算整場最終成績。"""
    state = session["state"]
    completed_at = timezone.now()
    accuracy = round(
        state["first_try_correct_count"] / TOTAL_QUESTIONS * 100,
        2,
    )
    raw_score = accuracy

    z_result = calculate_z_score(raw_score)
    z_score = z_result["z_score"]
    standard_score = z_result["standard_score"]

    return {
        "total_correct": state["total_correct"],
        "first_try_correct_count": state["first_try_correct_count"],
        "total_questions": TOTAL_QUESTIONS,
        "accuracy": accuracy,
        "raw_score": raw_score,
        "z_score": z_score,
        "standard_score": standard_score,
        "difficulty": state.get("current_stage", state.get("difficulty", "easy")),
        "completed_at": completed_at.isoformat(),
    }


def complete_session(session):
    """標記 Session finished 並寫入 result。"""
    result = calculate_final_result(session)
    return session_service.finish_session(
        GAME_TYPE,
        session["session_id"],
        result,
    )


def get_history(user_id):
    """取得使用者的最近 10 場歷史紀錄（舊到新排序）。"""
    all_sessions = session_service.list_sessions(GAME_TYPE)
    finished_sessions = [
        s
        for s in all_sessions
        if s["status"] == "finished" and s["state"].get("user_id") == user_id
    ]

    finished_sessions.sort(
        key=lambda s: s["result"]["completed_at"], reverse=True
    )
    recent_sessions = finished_sessions[:10]
    recent_sessions.reverse()

    return [
        {
            "score": session["result"].get("standard_score", session["result"].get("first_try_correct_count")),
            "raw_score": session["result"].get("raw_score", session["result"].get("accuracy")),
            "z_score": session["result"].get("z_score"),
            "standard_score": session["result"].get("standard_score"),
            "accuracy": session["result"].get("accuracy"),
            "played_at": session["result"]["completed_at"],
        }
        for session in recent_sessions
    ]
