import random

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from users.models import User
from games.models import Game, GameRecord, MarketShoppingSession

from .constants import FOODS, BUDGET_OPTIONS


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
    target_codes = {
        item["food_code"]
        for item in target_items
    }

    # 剩下的食材當干擾選項
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

    # 計算購物總金額
    spent_amount = sum(
        item["price"]
        for item in target_items
    )

    # 只挑足夠付款，而且一定有找零的預算
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
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "查無使用者資料",
                }
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # 產生第 1 題
    question = generate_question(difficulty)

    # 建立一整場 10 題的遊戲 Session
    session = MarketShoppingSession.objects.create(
        user=user,
        difficulty=difficulty,
        target_items=question["target_items"],
        option_items=question["option_items"],
        budget=question["budget"],
        spent_amount=question["spent_amount"],
        correct_change=question["correct_change"],
        current_question=1,
        total_questions=10,
        consecutive_correct=0,
        total_correct=0,
        first_try_correct_count=0,
        current_wrong_count=0,
        current_question_had_error=False,
        is_completed=False,
    )

    shopping_list = [
        {
            "food_code": item["food_code"],
            "food_name": item["food_name"],
        }
        for item in session.target_items
    ]

    selection_options = [
        {
            "food_code": item["food_code"],
            "food_name": item["food_name"],
        }
        for item in session.option_items
    ]

    return Response(
        {
            "data": {
                "session_id": session.id,
                "difficulty": session.difficulty,
                "current_question": session.current_question,
                "total_questions": session.total_questions,
                "shopping_list": shopping_list,
                "selection_options": selection_options,
            }
        },
        status=status.HTTP_201_CREATED,
    )
def save_game_record(session):
    game = Game.objects.filter(game_name="市場買菜").first()

    if game is None:
        return None

    accuracy = round(
        session.first_try_correct_count
        / session.total_questions
        * 100,
        2,
    )

    record, created = GameRecord.objects.get_or_create(
        user=session.user,
        game=game,
        played_at=session.completed_at,
        defaults={
            "score": session.first_try_correct_count,
            "accuracy": accuracy,
            "difficulty": session.difficulty,
            "played_date": timezone.localtime(
                session.completed_at
            ).date(),
        },
    )

    return record

def move_to_next_question(session):
    # 如果目前已經是第 10 題，整場結束
    if session.current_question >= session.total_questions:
        session.is_completed = True
        session.completed_at = timezone.now()
        session.save()
        return None

    # 進入下一題
    session.current_question += 1

    # 依照目前難度產生新題目
    question = generate_question(session.difficulty)

    session.target_items = question["target_items"]
    session.option_items = question["option_items"]
    session.budget = question["budget"]
    session.spent_amount = question["spent_amount"]
    session.correct_change = question["correct_change"]

    # 新的一題，作答狀態全部重新計算
    session.item_attempt_count = 0
    session.change_attempt_count = 0

    session.item_first_try_correct = None
    session.change_first_try_correct = None

    session.current_wrong_count = 0
    session.current_question_had_error = False

    session.save()

    shopping_list = [
        {
            "food_code": item["food_code"],
            "food_name": item["food_name"],
        }
        for item in session.target_items
    ]

    selection_options = [
        {
            "food_code": item["food_code"],
            "food_name": item["food_name"],
        }
        for item in session.option_items
    ]

    return {
        "difficulty": session.difficulty,
        "current_question": session.current_question,
        "total_questions": session.total_questions,
        "shopping_list": shopping_list,
        "selection_options": selection_options,
    }

# 第二支 API：檢查選菜答案
@api_view(["POST"])
def submit_item_answer(request, session_id):
    selected_food_codes = request.data.get("selected_food_codes")

    # 檢查格式
    if not isinstance(selected_food_codes, list):
        return Response(
            {
                "error": {
                    "code": "INVALID_ITEM_ANSWER",
                    "message": "selected_food_codes 必須為陣列",
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 找這一場遊戲
    try:
        session = MarketShoppingSession.objects.get(id=session_id)
    except MarketShoppingSession.DoesNotExist:
        return Response(
            {
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": "查無此遊戲局次",
                }
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # 已經結束的遊戲不能繼續答
    if session.is_completed:
        return Response(
            {
                "error": {
                    "code": "SESSION_COMPLETED",
                    "message": "此遊戲已完成",
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    correct_food_codes = [
        item["food_code"]
        for item in session.target_items
    ]

    # 記錄選菜作答次數
    session.item_attempt_count += 1

    # 不看點選順序，只檢查選到的食材是否一致
    is_correct = (
        len(selected_food_codes) == len(correct_food_codes)
        and set(selected_food_codes) == set(correct_food_codes)
    )

    # 第一次作答，記錄是否第一次就答對
    if session.item_attempt_count == 1:
        session.item_first_try_correct = is_correct

    # =========================
    # 選錯
    # =========================
    if not is_correct:
        session.current_wrong_count += 1
        session.current_question_had_error = True

        # 答錯會中斷連續答對
        session.consecutive_correct = 0

        # 還沒有錯滿 3 次
        if session.current_wrong_count < 3:
            session.save()

            return Response(
                {
                    "data": {
                        "is_correct": False,
                        "retry": True,
                        "current_question": session.current_question,
                        "wrong_count": session.current_wrong_count,
                        "remaining_attempts": 3 - session.current_wrong_count,
                    }
                },
                status=status.HTTP_200_OK,
            )

        # 已經錯滿 3 次，跳過這一題
        next_question = move_to_next_question(session)

        # 如果剛好是第 10 題，整場結束
        if next_question is None:
            return Response(
                {
                    "data": {
                        "is_correct": False,
                        "retry": False,
                        "question_skipped": True,
                        "is_completed": True,
                        "total_correct": session.total_correct,
                        "total_questions": session.total_questions,
                    }
                },
                status=status.HTTP_200_OK,
            )

        # 還沒到第 10 題，直接回傳下一題
        return Response(
            {
                "data": {
                    "is_correct": False,
                    "retry": False,
                    "question_skipped": True,
                    "is_completed": False,
                    "next_question": next_question,
                }
            },
            status=status.HTTP_200_OK,
        )

    # =========================
    # 選對 → 進入找零
    # =========================

    session.save()

    correct_change = session.correct_change

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
        "current_question": session.current_question,
        "difficulty": session.difficulty,
        "budget": session.budget,
        "change_options": change_options,
    }

    # easy / medium 直接顯示花費總額
    if session.difficulty in ["easy", "medium"]:
        response_data["spent_amount"] = session.spent_amount

    # hard 不顯示總額，要自己加
    if session.difficulty == "hard":
        response_data["purchased_items"] = [
            {
                "food_name": item["food_name"],
                "price": item["price"],
            }
            for item in session.target_items
        ]

    return Response(
        {
            "data": response_data
        },
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
                "error": {
                    "code": "INVALID_CHANGE_ANSWER",
                    "message": "selected_amount 必須為整數",
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 找這一場遊戲
    try:
        session = MarketShoppingSession.objects.get(id=session_id)
    except MarketShoppingSession.DoesNotExist:
        return Response(
            {
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": "查無此遊戲局次",
                }
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # 已完成的遊戲不能繼續作答
    if session.is_completed:
        return Response(
            {
                "error": {
                    "code": "SESSION_COMPLETED",
                    "message": "此遊戲已完成",
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 找零作答次數 +1
    session.change_attempt_count += 1

    is_correct = selected_amount == session.correct_change

    # 記錄是否第一次就答對
    if session.change_attempt_count == 1:
        session.change_first_try_correct = is_correct

    # =========================
    # 找零答錯
    # =========================
    if not is_correct:
        session.current_wrong_count += 1
        session.current_question_had_error = True

        # 答錯會中斷連續答對
        session.consecutive_correct = 0

        # 還沒錯滿 3 次
        if session.current_wrong_count < 3:
            session.save()

            return Response(
                {
                    "data": {
                        "is_correct": False,
                        "retry": True,
                        "current_question": session.current_question,
                        "wrong_count": session.current_wrong_count,
                        "remaining_attempts": 3 - session.current_wrong_count,
                    }
                },
                status=status.HTTP_200_OK,
            )

        # 錯滿 3 次，跳下一題
        next_question = move_to_next_question(session)

        # 第 10 題結束
        if next_question is None:
            save_game_record(session)
            
            accuracy = round(
                session.total_correct
                / session.total_questions
                * 100,
                2,
            )

            return Response(
                {
                    "data": {
                        "is_correct": False,
                        "retry": False,
                        "question_skipped": True,
                        "is_completed": True,
                        "total_correct": session.total_correct,
                        "total_questions": session.total_questions,
                        "accuracy": accuracy,
                        "completed_at": session.completed_at,
                    }
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "data": {
                    "is_correct": False,
                    "retry": False,
                    "question_skipped": True,
                    "is_completed": False,
                    "next_question": next_question,
                }
            },
            status=status.HTTP_200_OK,
        )

    # =========================
    # 找零答對 → 這題完成
    # =========================

    # 最後成功完成這一題
    session.total_correct += 1

    # 整題從選菜到找零都沒有答錯過
    if not session.current_question_had_error:
        # 一次完成的題數 +1
        session.first_try_correct_count += 1

        # 連續答對 +1
        session.consecutive_correct += 1
    else:
        # 曾經答錯過就中斷連續答對
        session.consecutive_correct = 0

    # =========================
    # 連續答對 3 題 → 升難度
    # =========================

    difficulty_upgraded = False

    if session.consecutive_correct >= 3:
        if session.difficulty == "easy":
            session.difficulty = "medium"
            session.consecutive_correct = 0
            difficulty_upgraded = True

        elif session.difficulty == "medium":
            session.difficulty = "hard"
            session.consecutive_correct = 0
            difficulty_upgraded = True

    session.save()

    # =========================
    # 第 10 題完成 → 遊戲結束
    # =========================

    if session.current_question >= session.total_questions:
        session.is_completed = True
        session.completed_at = timezone.now()
        session.save()

        # 將本場成績正式存入 GameRecord
        save_game_record(session)

        accuracy = round(
            session.first_try_correct_count
            / session.total_questions
            * 100,
            2,
        )

        return Response(
            {
                "data": {
                    "is_correct": True,
                    "is_completed": True,
                    "total_correct": session.total_correct,
                    "first_try_correct_count": session.first_try_correct_count,
                    "total_questions": session.total_questions,
                    "accuracy": accuracy,
                    "difficulty": session.difficulty,
                    "completed_at": session.completed_at,
                }
            },
            status=status.HTTP_200_OK,
        )

    # =========================
    # 還沒第 10 題 → 出下一題
    # =========================

    next_question = move_to_next_question(session)

    return Response(
        {
            "data": {
                "is_correct": True,
                "is_completed": False,
                "difficulty_upgraded": difficulty_upgraded,
                "consecutive_correct": session.consecutive_correct,
                "total_correct": session.total_correct,
                "next_question": next_question,
            }
        },
        status=status.HTTP_200_OK,
    )