from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from games import session_service
from users.models import User

from .services import (
    TOTAL_QUESTIONS,
    build_question_payload,
    calculate_difficulty,
    calculate_metrics,
    calculate_score,
    evaluate_change_answer,
    evaluate_item_answer,
    generate_change_options,
    generate_question,
)


GAME_TYPE = "market_shopping"


def _get_reaction_time(request):
    """
    取得前端傳入的 reaction_time_ms。

    目前先允許不傳，避免前端尚未更新時 API 直接壞掉。
    若有傳，必須為 >= 0 的數字。
    """
    reaction_time_ms = request.data.get("reaction_time_ms")

    if reaction_time_ms is None:
        return None, None

    if (
        isinstance(reaction_time_ms, bool)
        or not isinstance(reaction_time_ms, (int, float))
        or reaction_time_ms < 0
    ):
        return None, Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "INVALID_REACTION_TIME",
                    "message": "reaction_time_ms 必須為大於等於 0 的數字",
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    return reaction_time_ms, None


def _get_current_user(request):
    """
    開發階段：
    - 已登入：使用 request.user
    - 未登入：暫時抓資料庫第一位 User
    """
    if request.user.is_authenticated:
        return request.user
    return User.objects.first()


def _completed_payload(result, is_correct, question_skipped=False):
    """統一整理整場結束時回傳給前端的資料。"""
    return {
        "is_correct": is_correct,
        "retry": False if question_skipped else None,
        "question_skipped": question_skipped,
        "is_completed": True,
        "score": result["score"],
        "total_correct": result["total_correct"],
        "first_try_correct_count": result["first_try_correct_count"],
        "total_questions": TOTAL_QUESTIONS,
        "accuracy": result["accuracy"],
        "metrics": result["metrics"],
        "difficulty": result["difficulty"],
        "completed_at": result["completed_at"],
    }


@api_view(["POST"])
def create_session(request):
    """建立一場新的市場買菜遊戲。"""
    difficulty = "easy"

    user = _get_current_user(request)

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

    question = generate_question(difficulty)

    initial_state = {
        "user_id": user.id,

        # DDA
        "difficulty": difficulty,
        "consecutive_correct": 0,

        # 整場統計
        "total_correct": 0,
        "first_try_correct_count": 0,

        # 本題找零資料
        "budget": question["budget"],
        "spent_amount": question["spent_amount"],
        "correct_change": question["correct_change"],

        # 本題作答狀態
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
        initial_state=initial_state,
    )

    session = session_service.update_session(
        GAME_TYPE,
        session["session_id"],
        question_number=1,
        current_question=current_question,
    )

    payload = build_question_payload(
        current_question,
        difficulty,
        session["question_number"],
    )
    payload["session_id"] = session["session_id"]

    return Response(
        {
            "success": True,
            "data": payload,
            "error": None,
        },
        status=status.HTTP_201_CREATED,
    )


def _complete_session(session_id):
    """
    完成整場遊戲並計算：
    - 選菜首次正確率
    - 找零首次正確率
    - 整題一次完成率
    - RT
    - CV
    - score
    """
    session = session_service.get_session(
        GAME_TYPE,
        session_id,
    )

    state = session["state"]

    metrics = calculate_metrics(
        session["step_records"],
        total_questions=TOTAL_QUESTIONS,
    )

    score = calculate_score(metrics)
    completed_at = timezone.now()

    result = {
        "score": score,
        "total_correct": state["total_correct"],
        "first_try_correct_count": state["first_try_correct_count"],
        "total_questions": TOTAL_QUESTIONS,

        # 舊前端仍可沿用 accuracy。
        # 內容等於「整題一次完成率」。
        "accuracy": metrics["complete_first_try_accuracy"],

        "difficulty": state["difficulty"],
        "metrics": metrics,
        "completed_at": completed_at.isoformat(),
    }

    session_service.finish_session(
        GAME_TYPE,
        session_id,
        result,
    )

    return result


def move_to_next_question(session):
    """完成目前題目後，產生下一題；若已是第 10 題則結束整場。"""
    session_id = session["session_id"]
    question_number = session["question_number"]
    state = session["state"]

    if question_number >= TOTAL_QUESTIONS:
        _complete_session(session_id)
        return None

    question = generate_question(
        state["difficulty"]
    )

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
        current_question,
        session["state"]["difficulty"],
        session["question_number"],
    )


@api_view(["POST"])
def submit_item_answer(request, session_id):
    """提交選菜答案。"""
    selected_food_codes = request.data.get("selected_food_codes")

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

    reaction_time_ms, error_response = _get_reaction_time(request)

    if error_response:
        return error_response

    session = session_service.get_session(
        GAME_TYPE,
        session_id,
    )

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

    answer_result = evaluate_item_answer(
        selected_food_codes,
        current_question["target_items"],
    )
    is_correct = answer_result["is_correct"]

    item_attempt_count = state["item_attempt_count"] + 1

    step_record = {
        "question_number": session["question_number"],
        "phase": "item",
        "attempt_number": item_attempt_count,
        "difficulty": state["difficulty"],
        "selected_food_codes": selected_food_codes,
        "is_correct": is_correct,
        "error_type": answer_result["error_type"],
        "missing_food_codes": answer_result["missing_food_codes"],
        "extra_food_codes": answer_result["extra_food_codes"],
        "reaction_time_ms": reaction_time_ms,
    }

    session_service.save_step(
        GAME_TYPE,
        session_id,
        step_record,
    )

    state_update = {
        "item_attempt_count": item_attempt_count,
    }

    if item_attempt_count == 1:
        state_update["item_first_try_correct"] = is_correct

    # -------------------------
    # 選菜答錯
    # -------------------------
    if not is_correct:
        current_wrong_count = state["current_wrong_count"] + 1

        state_update.update(
            {
                "current_wrong_count": current_wrong_count,
                "current_question_had_error": True,
                "consecutive_correct": 0,
            }
        )

        session = session_service.update_session(
            GAME_TYPE,
            session_id,
            state=state_update,
        )

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
                        "error_type": answer_result["error_type"],
                    },
                    "error": None,
                },
                status=status.HTTP_200_OK,
            )

        next_question = move_to_next_question(session)

        if next_question is None:
            final_session = session_service.get_session(
                GAME_TYPE,
                session_id,
            )
            result = final_session["result"]

            return Response(
                {
                    "success": True,
                    "data": _completed_payload(
                        result,
                        is_correct=False,
                        question_skipped=True,
                    ),
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

    # -------------------------
    # 選菜答對 → 進入找零
    # -------------------------
    session = session_service.update_session(
        GAME_TYPE,
        session_id,
        state=state_update,
    )

    state = session["state"]

    change_options = generate_change_options(
        state["correct_change"]
    )

    response_data = {
        "is_correct": True,
        "current_question": session["question_number"],
        "difficulty": state["difficulty"],
        "budget": state["budget"],
        "change_options": change_options,
    }

    if state["difficulty"] in ["easy", "medium"]:
        response_data["spent_amount"] = state["spent_amount"]

    if state["difficulty"] == "hard":
        response_data["purchased_items"] = [
            {
                "food_name": item["food_name"],
                "price": item["price"],
            }
            for item in session["current_question"]["target_items"]
        ]

    return Response(
        {
            "success": True,
            "data": response_data,
            "error": None,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
def submit_change_answer(request, session_id):
    """提交找零答案。"""
    selected_amount = request.data.get("selected_amount")

    if (
        isinstance(selected_amount, bool)
        or not isinstance(selected_amount, int)
    ):
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

    reaction_time_ms, error_response = _get_reaction_time(request)

    if error_response:
        return error_response

    session = session_service.get_session(
        GAME_TYPE,
        session_id,
    )

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

    answer_result = evaluate_change_answer(
        selected_amount,
        state["correct_change"],
    )
    is_correct = answer_result["is_correct"]

    change_attempt_count = state["change_attempt_count"] + 1

    step_record = {
        "question_number": session["question_number"],
        "phase": "change",
        "attempt_number": change_attempt_count,
        "difficulty": state["difficulty"],
        "selected_amount": selected_amount,
        "is_correct": is_correct,
        "error_type": answer_result["error_type"],
        "reaction_time_ms": reaction_time_ms,
    }

    session_service.save_step(
        GAME_TYPE,
        session_id,
        step_record,
    )

    state_update = {
        "change_attempt_count": change_attempt_count,
    }

    if change_attempt_count == 1:
        state_update["change_first_try_correct"] = is_correct

    # -------------------------
    # 找零答錯
    # -------------------------
    if not is_correct:
        current_wrong_count = state["current_wrong_count"] + 1

        state_update.update(
            {
                "current_wrong_count": current_wrong_count,
                "current_question_had_error": True,
                "consecutive_correct": 0,
            }
        )

        session = session_service.update_session(
            GAME_TYPE,
            session_id,
            state=state_update,
        )

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
                        "error_type": answer_result["error_type"],
                    },
                    "error": None,
                },
                status=status.HTTP_200_OK,
            )

        next_question = move_to_next_question(session)

        if next_question is None:
            final_session = session_service.get_session(
                GAME_TYPE,
                session_id,
            )
            result = final_session["result"]

            return Response(
                {
                    "success": True,
                    "data": _completed_payload(
                        result,
                        is_correct=False,
                        question_skipped=True,
                    ),
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

    # -------------------------
    # 找零答對 → 整題完成
    # -------------------------
    state_update["total_correct"] = state["total_correct"] + 1

    if not state["current_question_had_error"]:
        state_update["first_try_correct_count"] = (
            state["first_try_correct_count"] + 1
        )
        consecutive_correct = state["consecutive_correct"] + 1
    else:
        consecutive_correct = 0

    dda_result = calculate_difficulty(
        state["difficulty"],
        consecutive_correct,
    )

    state_update["difficulty"] = dda_result["difficulty"]
    state_update["consecutive_correct"] = dda_result["consecutive_correct"]

    session = session_service.update_session(
        GAME_TYPE,
        session_id,
        state=state_update,
    )

    question_number = session["question_number"]

    if question_number >= TOTAL_QUESTIONS:
        result = _complete_session(session_id)

        return Response(
            {
                "success": True,
                "data": {
                    "is_correct": True,
                    "is_completed": True,
                    "score": result["score"],
                    "total_correct": result["total_correct"],
                    "first_try_correct_count": result[
                        "first_try_correct_count"
                    ],
                    "total_questions": TOTAL_QUESTIONS,
                    "accuracy": result["accuracy"],
                    "difficulty": result["difficulty"],
                    "metrics": result["metrics"],
                    "completed_at": result["completed_at"],
                },
                "error": None,
            },
            status=status.HTTP_200_OK,
        )

    next_question = move_to_next_question(session)

    return Response(
        {
            "success": True,
            "data": {
                "is_correct": True,
                "is_completed": False,
                "difficulty_upgraded": dda_result[
                    "difficulty_upgraded"
                ],
                "consecutive_correct": session["state"][
                    "consecutive_correct"
                ],
                "total_correct": session["state"]["total_correct"],
                "next_question": next_question,
            },
            "error": None,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
def get_market_shopping_history(request):
    """取得目前使用者最近 10 次市場買菜成績。"""
    user = _get_current_user(request)

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

    all_sessions = session_service.list_sessions(GAME_TYPE)

    finished_sessions = [
        session
        for session in all_sessions
        if session["status"] == "finished"
        and session["state"].get("user_id") == user.id
        and session.get("result") is not None
    ]

    finished_sessions.sort(
        key=lambda session: session["result"].get(
            "completed_at",
            "",
        ),
        reverse=True,
    )

    recent_sessions = finished_sessions[:10]
    recent_sessions.reverse()

    history = []

    for session in recent_sessions:
        result = session["result"]

        history.append(
            {
                "score": result.get(
                    "score",
                    result.get(
                        "first_try_correct_count",
                        0,
                    ),
                ),
                "accuracy": result.get(
                    "accuracy",
                    0,
                ),
                "played_at": result.get(
                    "completed_at"
                ),
            }
        )

    return Response(
        {
            "success": True,
            "data": history,
            "error": None,
        },
        status=status.HTTP_200_OK,
    )
