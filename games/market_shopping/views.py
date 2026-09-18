import random

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from games import session_service
from users.models import User

from .constants import BUDGET_OPTIONS, FOODS

GAME_TYPE = "market_shopping"
TOTAL_QUESTIONS = 10


def generate_question(difficulty):
    # 不同難度決定購物清單數量與選項數量
    if difficulty == "easy":
        target_count = 2
        option_count = 4
    else:
        target_count = 4
        option_count = 6

    # 隨機抽出正確購物清單
    target_items = random.sample(
        FOODS,
        target_count,
    )

    # 已經抽中的食材代碼
    target_codes = {item["food_code"] for item in target_items}

    # 剩下的食材當干擾選項
    remaining_foods = [food for food in FOODS if food["food_code"] not in target_codes]

    distractor_count = option_count - target_count

    distractors = random.sample(
        remaining_foods,
        distractor_count,
    )

    option_items = target_items + distractors
    random.shuffle(option_items)

    # 計算購物總金額
    spent_amount = sum(item["price"] for item in target_items)

    # 只挑足夠付款，而且一定有找零的預算
    available_budgets = [amount for amount in BUDGET_OPTIONS if amount > spent_amount]

    budget = random.choice(available_budgets)
    correct_change = budget - spent_amount

    return {
        "target_items": target_items,
        "option_items": option_items,
        "budget": budget,
        "spent_amount": spent_amount,
        "correct_change": correct_change,
    }


def _build_question_payload(current_question, difficulty, question_number):
    """組出「一題的內容」回應格式，create_session 跟換下一題共用同一份格式。"""
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


# 第一支 API
@api_view(["POST"])
def create_session(request):
    # 每一場固定從 easy 開始
    difficulty = "easy"

    # 有登入時使用登入者
    # 開發階段未登入時暫時抓第一位使用者
    if request.user.is_authenticated:
        user = request.user
    else:
        user = User.objects.first()

    if user is None:
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "查無使用者資料",
                },
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # 產生第 1 題
    question = generate_question(difficulty)

    initial_state = {
        "user_id": user.id,
        "difficulty": difficulty,
        "budget": question["budget"],
        "spent_amount": question["spent_amount"],
        "correct_change": question["correct_change"],
        "consecutive_correct": 0,
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

    # 建立一整場 10 題的遊戲 Session
    session = session_service.create_session(GAME_TYPE, initial_state=initial_state)
    session = session_service.update_session(
        GAME_TYPE,
        session["session_id"],
        question_number=1,
        current_question=current_question,
    )

    payload = _build_question_payload(
        current_question, difficulty, session["question_number"]
    )
    payload["session_id"] = session["session_id"]

    return Response(
        {"success": True, "data": payload, "error": None},
        status=status.HTTP_201_CREATED,
    )


def _complete_session(session_id, state, total_correct):
    """整場結束的收尾：算總結果、寫入 session 的 result。

    result 會完整保留在這個 session 的 JSON 檔案裡，歷史成績查詢
    （get_market_shopping_history）直接掃描所有 session 檔案取得，
    不另外寫資料庫。
    """
    completed_at = timezone.now()
    accuracy = round(
        state["first_try_correct_count"] / TOTAL_QUESTIONS * 100,
        2,
    )

    result = {
        "total_correct": total_correct,
        "first_try_correct_count": state["first_try_correct_count"],
        "total_questions": TOTAL_QUESTIONS,
        "accuracy": accuracy,
        "difficulty": state["difficulty"],
        "completed_at": completed_at.isoformat(),
    }

    session_service.finish_session(GAME_TYPE, session_id, result)

    return result


def move_to_next_question(session):
    session_id = session["session_id"]
    question_number = session["question_number"]
    state = session["state"]

    # 如果目前已經是第 10 題，整場結束
    if question_number >= TOTAL_QUESTIONS:
        _complete_session(session_id, state, state["total_correct"])
        return None

    # 依照目前難度產生新題目
    question = generate_question(state["difficulty"])

    current_question = {
        "target_items": question["target_items"],
        "option_items": question["option_items"],
    }

    # 新的一題，作答狀態全部重新計算
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

    return _build_question_payload(
        current_question, session["state"]["difficulty"], session["question_number"]
    )


# 第二支 API：檢查選菜答案
@api_view(["POST"])
def submit_item_answer(request, session_id):
    selected_food_codes = request.data.get("selected_food_codes")

    # 檢查格式
    if not isinstance(selected_food_codes, list):
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "INVALID_ITEM_ANSWER",
                    "message": "selected_food_codes 必須為陣列",
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 找這一場遊戲
    session = session_service.get_session(GAME_TYPE, session_id)
    if session is None:
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": "查無此遊戲局次",
                },
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # 已經結束的遊戲不能繼續答
    if session["status"] == "finished":
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "SESSION_COMPLETED",
                    "message": "此遊戲已完成",
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    state = session["state"]
    current_question = session["current_question"]

    correct_food_codes = [
        item["food_code"] for item in current_question["target_items"]
    ]

    # 記錄選菜作答次數
    item_attempt_count = state["item_attempt_count"] + 1

    # 不看點選順序，只檢查選到的食材是否一致
    is_correct = len(selected_food_codes) == len(correct_food_codes) and set(
        selected_food_codes
    ) == set(correct_food_codes)

    state_update = {"item_attempt_count": item_attempt_count}

    # 第一次作答，記錄是否第一次就答對
    if item_attempt_count == 1:
        state_update["item_first_try_correct"] = is_correct

    # =========================
    # 選錯
    # =========================
    if not is_correct:
        current_wrong_count = state["current_wrong_count"] + 1
        state_update["current_wrong_count"] = current_wrong_count
        state_update["current_question_had_error"] = True

        # 答錯會中斷連續答對
        state_update["consecutive_correct"] = 0

        session = session_service.update_session(
            GAME_TYPE, session_id, state=state_update
        )

        # 還沒有錯滿 3 次
        if current_wrong_count < 3:
            return Response(
                {
                    "success": True,
                    "data": {
                        "is_correct": False,
                        "retry": True,
                        "current_question": session["question_number"],
                        "wrong_count": current_wrong_count,
                        "remaining_attempts": 3 - current_wrong_count,
                    },
                    "error": None,
                },
                status=status.HTTP_200_OK,
            )

        # 已經錯滿 3 次，跳過這一題
        next_question = move_to_next_question(session)

        # 如果剛好是第 10 題，整場結束
        if next_question is None:
            final_session = session_service.get_session(GAME_TYPE, session_id)
            return Response(
                {
                    "success": True,
                    "data": {
                        "is_correct": False,
                        "retry": False,
                        "question_skipped": True,
                        "is_completed": True,
                        "total_correct": final_session["state"]["total_correct"],
                        "total_questions": TOTAL_QUESTIONS,
                    },
                    "error": None,
                },
                status=status.HTTP_200_OK,
            )

        # 還沒到第 10 題，直接回傳下一題
        return Response(
            {
                "success": True,
                "data": {
                    "is_correct": False,
                    "retry": False,
                    "question_skipped": True,
                    "is_completed": False,
                    "next_question": next_question,
                },
                "error": None,
            },
            status=status.HTTP_200_OK,
        )

    # =========================
    # 選對 → 進入找零
    # =========================

    session = session_service.update_session(GAME_TYPE, session_id, state=state_update)
    state = session["state"]

    correct_change = state["correct_change"]

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
        if amount >= 0 and amount != correct_change
    ]

    # 隨機取兩個錯誤答案
    wrong_answers = random.sample(
        possible_wrong_answers,
        2,
    )

    # 正解 + 2 個錯誤選項
    change_options = wrong_answers + [correct_change]
    random.shuffle(change_options)

    response_data = {
        "is_correct": True,
        "current_question": session["question_number"],
        "difficulty": state["difficulty"],
        "budget": state["budget"],
        "change_options": change_options,
    }

    # easy / medium 直接顯示花費總額
    if state["difficulty"] in ["easy", "medium"]:
        response_data["spent_amount"] = state["spent_amount"]

    # hard 不顯示總額，要自己加
    if state["difficulty"] == "hard":
        response_data["purchased_items"] = [
            {
                "food_name": item["food_name"],
                "price": item["price"],
            }
            for item in session["current_question"]["target_items"]
        ]

    return Response(
        {"success": True, "data": response_data, "error": None},
        status=status.HTTP_200_OK,
    )


# 第三支 API：檢查找零答案
@api_view(["POST"])
def submit_change_answer(request, session_id):
    selected_amount = request.data.get("selected_amount")

    # 檢查格式
    if not isinstance(selected_amount, int):
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "INVALID_CHANGE_ANSWER",
                    "message": "selected_amount 必須為整數",
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 找這一場遊戲
    session = session_service.get_session(GAME_TYPE, session_id)
    if session is None:
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": "查無此遊戲局次",
                },
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # 已完成的遊戲不能繼續作答
    if session["status"] == "finished":
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "SESSION_COMPLETED",
                    "message": "此遊戲已完成",
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    state = session["state"]

    # 找零作答次數 +1
    change_attempt_count = state["change_attempt_count"] + 1

    is_correct = selected_amount == state["correct_change"]

    state_update = {"change_attempt_count": change_attempt_count}

    # 記錄是否第一次就答對
    if change_attempt_count == 1:
        state_update["change_first_try_correct"] = is_correct

    # =========================
    # 找零答錯
    # =========================
    if not is_correct:
        current_wrong_count = state["current_wrong_count"] + 1
        state_update["current_wrong_count"] = current_wrong_count
        state_update["current_question_had_error"] = True

        # 答錯會中斷連續答對
        state_update["consecutive_correct"] = 0

        session = session_service.update_session(
            GAME_TYPE, session_id, state=state_update
        )

        # 還沒錯滿 3 次
        if current_wrong_count < 3:
            return Response(
                {
                    "success": True,
                    "data": {
                        "is_correct": False,
                        "retry": True,
                        "current_question": session["question_number"],
                        "wrong_count": current_wrong_count,
                        "remaining_attempts": 3 - current_wrong_count,
                    },
                    "error": None,
                },
                status=status.HTTP_200_OK,
            )

        # 錯滿 3 次，跳下一題
        next_question = move_to_next_question(session)

        # 第 10 題結束
        if next_question is None:
            final_session = session_service.get_session(GAME_TYPE, session_id)
            result = final_session["result"]

            return Response(
                {
                    "success": True,
                    "data": {
                        "is_correct": False,
                        "retry": False,
                        "question_skipped": True,
                        "is_completed": True,
                        "total_correct": result["total_correct"],
                        "total_questions": TOTAL_QUESTIONS,
                        "accuracy": result["accuracy"],
                        "completed_at": result["completed_at"],
                    },
                    "error": None,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "success": True,
                "data": {
                    "is_correct": False,
                    "retry": False,
                    "question_skipped": True,
                    "is_completed": False,
                    "next_question": next_question,
                },
                "error": None,
            },
            status=status.HTTP_200_OK,
        )

    # =========================
    # 找零答對 → 這題完成
    # =========================

    # 最後成功完成這一題
    state_update["total_correct"] = state["total_correct"] + 1

    # 整題從選菜到找零都沒有答錯過
    if not state["current_question_had_error"]:
        # 一次完成的題數 +1
        state_update["first_try_correct_count"] = state["first_try_correct_count"] + 1

        # 連續答對 +1
        state_update["consecutive_correct"] = state["consecutive_correct"] + 1
    else:
        # 曾經答錯過就中斷連續答對
        state_update["consecutive_correct"] = 0

    # =========================
    # 連續答對 3 題 → 升難度
    # =========================

    difficulty_upgraded = False
    difficulty = state["difficulty"]
    consecutive_correct = state_update["consecutive_correct"]

    if consecutive_correct >= 3:
        if difficulty == "easy":
            difficulty = "medium"
            consecutive_correct = 0
            difficulty_upgraded = True

        elif difficulty == "medium":
            difficulty = "hard"
            consecutive_correct = 0
            difficulty_upgraded = True

        state_update["difficulty"] = difficulty
        state_update["consecutive_correct"] = consecutive_correct

    session = session_service.update_session(GAME_TYPE, session_id, state=state_update)
    state = session["state"]
    question_number = session["question_number"]

    # =========================
    # 第 10 題完成 → 遊戲結束
    # =========================

    if question_number >= TOTAL_QUESTIONS:
        result = _complete_session(session_id, state, state["total_correct"])

        return Response(
            {
                "success": True,
                "data": {
                    "is_correct": True,
                    "is_completed": True,
                    "total_correct": result["total_correct"],
                    "first_try_correct_count": result["first_try_correct_count"],
                    "total_questions": TOTAL_QUESTIONS,
                    "accuracy": result["accuracy"],
                    "difficulty": result["difficulty"],
                    "completed_at": result["completed_at"],
                },
                "error": None,
            },
            status=status.HTTP_200_OK,
        )

    # =========================
    # 還沒第 10 題 → 出下一題
    # =========================

    next_question = move_to_next_question(session)

    return Response(
        {
            "success": True,
            "data": {
                "is_correct": True,
                "is_completed": False,
                "difficulty_upgraded": difficulty_upgraded,
                "consecutive_correct": state["consecutive_correct"],
                "total_correct": state["total_correct"],
                "next_question": next_question,
            },
            "error": None,
        },
        status=status.HTTP_200_OK,
    )


# 第四支 API：取得市場買菜歷史成績
@api_view(["GET"])
def get_market_shopping_history(request):
    # 有登入時使用登入者
    # 開發階段未登入時暫時抓第一位使用者
    if request.user.is_authenticated:
        user = request.user
    else:
        user = User.objects.first()

    if user is None:
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "查無使用者資料",
                },
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # 掃描這個遊戲類型底下所有 session，篩出這位使用者已完成的場次
    all_sessions = session_service.list_sessions(GAME_TYPE)
    finished_sessions = [
        s
        for s in all_sessions
        if s["status"] == "finished" and s["state"].get("user_id") == user.id
    ]

    # 取得最近 10 次遊戲紀錄
    finished_sessions.sort(key=lambda s: s["result"]["completed_at"], reverse=True)
    recent_sessions = finished_sessions[:10]

    # 折線圖由舊到新顯示
    recent_sessions.reverse()

    history = [
        {
            "score": session["result"]["first_try_correct_count"],
            "accuracy": session["result"]["accuracy"],
            "played_at": session["result"]["completed_at"],
        }
        for session in recent_sessions
    ]

    return Response(
        {"success": True, "data": history, "error": None},
        status=status.HTTP_200_OK,
    )
