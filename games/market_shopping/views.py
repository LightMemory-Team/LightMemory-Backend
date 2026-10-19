from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from games import session_service
from games.utils import get_current_user

from . import services

GAME_TYPE = services.GAME_TYPE
TOTAL_QUESTIONS = services.TOTAL_QUESTIONS


def _invalid_reaction_time_response(reaction_time_ms):
    """reaction_time_ms 可以不送；有送就必須是 >= 0 的整數，否則回傳 400。

    沒擋的話，字串會在累加反應時間時出錯（500）。檢查規則同冰箱檢查。
    """
    if reaction_time_ms is None or (
        isinstance(reaction_time_ms, int)
        and not isinstance(reaction_time_ms, bool)
        and reaction_time_ms >= 0
    ):
        return None
    return Response(
        {
            "success": False,
            "data": None,
            "error": {
                "code": "INVALID_REACTION_TIME",
                "message": "reaction_time_ms 必須為大於或等於 0 的整數",
            },
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


# 第一支 API：建立遊戲 Session
@api_view(["POST"])
def create_session(request):
    user = get_current_user(request)
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

    session = services.create_game_session(user)
    current_difficulty = session["state"].get(
        "current_stage", session["state"].get("difficulty", "easy")
    )

    payload = services.build_question_payload(
        session["current_question"], current_difficulty, session["question_number"]
    )
    payload["session_id"] = session["session_id"]

    return Response(
        {"success": True, "data": payload, "error": None},
        status=status.HTTP_201_CREATED,
    )


# 第二支 API：檢查選菜答案
@api_view(["POST"])
def submit_item_answer(request, session_id):
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

    reaction_time_ms = request.data.get("reaction_time_ms")
    error_response = _invalid_reaction_time_response(reaction_time_ms)
    if error_response is not None:
        return error_response

    session = services.get_session(session_id)
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

    is_correct = services.check_item_answer(session, selected_food_codes)
    session_service.save_step(
        GAME_TYPE,
        session_id,
        {
            "question_number": session["question_number"],
            "step_type": "select_items",
            "difficulty": session["state"].get(
                "current_stage", session["state"].get("difficulty", "easy")
            ),
            "is_correct": is_correct,
            "response_time_ms": reaction_time_ms,
            "selected_food_codes": selected_food_codes,
        },
    )

    # 選錯
    if not is_correct:
        session = services.record_item_wrong(session, reaction_time_ms=reaction_time_ms)
        current_wrong_count = session["state"]["current_wrong_count"]

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

        # 錯滿 3 次，跳題
        next_question = services.move_to_next_question(session)
        if next_question is None:
            final_session = services.get_session(session_id)
            result = final_session.get("result") or services.calculate_final_result(
                final_session
            )
            return Response(
                {
                    "success": True,
                    "data": {
                        "is_correct": False,
                        "retry": False,
                        "question_skipped": True,
                        "is_completed": True,
                        "total_correct": result["total_correct"],
                        "first_try_correct_count": result["first_try_correct_count"],
                        "total_questions": TOTAL_QUESTIONS,
                        "accuracy": result["accuracy"],
                        "speed_score": result.get("speed_score"),
                        "raw_score": result.get("raw_score"),
                        "z_score": result.get("z_score"),
                        "standard_score": result.get("standard_score"),
                        "average_reaction_time_ms": result.get(
                            "average_reaction_time_ms"
                        ),
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

    # 選對 → 進入找零
    session = services.record_item_correct(session, reaction_time_ms=reaction_time_ms)
    state = session["state"]
    change_options = services.generate_change_options(state["correct_change"])
    difficulty = state.get("current_stage", state.get("difficulty", "easy"))

    response_data = {
        "is_correct": True,
        "current_question": session["question_number"],
        "difficulty": difficulty,
        "budget": state["budget"],
        "change_options": change_options,
    }

    if difficulty in ["easy", "medium"]:
        response_data["spent_amount"] = state["spent_amount"]

    if difficulty == "hard":
        response_data["purchased_items"] = [
            {"food_name": item["food_name"], "price": item["price"]}
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

    reaction_time_ms = request.data.get("reaction_time_ms")
    error_response = _invalid_reaction_time_response(reaction_time_ms)
    if error_response is not None:
        return error_response

    session = services.get_session(session_id)
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

    is_correct = services.check_change_answer(session, selected_amount)
    session_service.save_step(
        GAME_TYPE,
        session_id,
        {
            "question_number": session["question_number"],
            "step_type": "calculate_change",
            "difficulty": session["state"].get(
                "current_stage", session["state"].get("difficulty", "easy")
            ),
            "is_correct": is_correct,
            "response_time_ms": reaction_time_ms,
            "selected_amount": selected_amount,
        },
    )

    # 找零答錯
    if not is_correct:
        session = services.record_change_wrong(
            session, reaction_time_ms=reaction_time_ms
        )
        current_wrong_count = session["state"]["current_wrong_count"]

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
        next_question = services.move_to_next_question(session)
        if next_question is None:
            final_session = services.get_session(session_id)
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
                        "first_try_correct_count": result["first_try_correct_count"],
                        "total_questions": TOTAL_QUESTIONS,
                        "accuracy": result["accuracy"],
                        "speed_score": result.get("speed_score"),
                        "raw_score": result.get("raw_score"),
                        "z_score": result.get("z_score"),
                        "standard_score": result.get("standard_score"),
                        "average_reaction_time_ms": result.get(
                            "average_reaction_time_ms"
                        ),
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

    # 找零答對
    session, difficulty_upgraded = services.record_change_correct_and_apply_dda(
        session, reaction_time_ms=reaction_time_ms
    )
    state = session["state"]
    question_number = session["question_number"]

    # 第 10 題完成 → 結束
    if question_number >= TOTAL_QUESTIONS:
        finished_session = services.complete_session(session)
        result = finished_session["result"]
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
                    "speed_score": result.get("speed_score"),
                    "raw_score": result.get("raw_score"),
                    "z_score": result.get("z_score"),
                    "standard_score": result.get("standard_score"),
                    "average_reaction_time_ms": result.get("average_reaction_time_ms"),
                    "difficulty": result["difficulty"],
                    "completed_at": result["completed_at"],
                },
                "error": None,
            },
            status=status.HTTP_200_OK,
        )

    # 出下一題
    next_question = services.move_to_next_question(session)
    return Response(
        {
            "success": True,
            "data": {
                "is_correct": True,
                "is_completed": False,
                "difficulty_upgraded": difficulty_upgraded,
                "consecutive_correct": state.get(
                    "correct_streak", state.get("consecutive_correct", 0)
                ),
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
    user = get_current_user(request)
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

    history = services.get_history(user.id)
    return Response(
        {"success": True, "data": history, "error": None},
        status=status.HTTP_200_OK,
    )
