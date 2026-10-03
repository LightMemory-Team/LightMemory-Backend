from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from users.models import User

from . import services
from .constants import (
    MAX_WRONG_ATTEMPTS,
    TOTAL_QUESTIONS,
)


def get_current_user(request):
    """
    取得目前使用者。

    正式環境使用 request.user；
    開發測試階段若未登入，暫時取第一位 User。
    """
    if request.user.is_authenticated:
        return request.user

    return User.objects.first()


# =========================================================
# 建立遊戲 Session
# =========================================================

# 開始遊戲api
@api_view(["POST"])
def create_session(request):
    """
    POST /api/games/fridge-check/sessions/
    """

    user = get_current_user(request)

    if user is None:
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "找不到可使用的使用者",
                },
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    session = services.create_game_session(user)

    return Response(
        {
            "success": True,
            "data": {
                "session_id": session["session_id"],
                "difficulty": session["state"]["difficulty"],
                "current_question": session["question_number"],
                "total_questions": TOTAL_QUESTIONS,
                "consecutive_correct": (
                    session["state"]["consecutive_correct"]
                ),
                "wrong_count": (
                    session["state"]["current_wrong_count"]
                ),
                "question": services.build_question_response(
                    session
                ),
            },
            "error": None,
        },
        status=status.HTTP_201_CREATED,
    )


# =========================================================
# 提交答案
# =========================================================

# 作答、DDA、計分api
@api_view(["POST"])
def submit_answer(request, session_id):
    """
    POST /api/games/fridge-check/sessions/{session_id}/answers/
    """

    answer = request.data.get("answer")
    reaction_time_ms = request.data.get("reaction_time_ms")

    # -----------------------------------------------------
    # 基本格式驗證
    # -----------------------------------------------------

    if not isinstance(answer, dict):
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "INVALID_ANSWER",
                    "message": "answer 必須為物件",
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if (
        reaction_time_ms is not None
        and (
            not isinstance(reaction_time_ms, int)
            or isinstance(reaction_time_ms, bool)
            or reaction_time_ms < 0
        )
    ):
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "INVALID_REACTION_TIME",
                    "message": (
                        "reaction_time_ms 必須為大於或等於 0 的整數"
                    ),
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # -----------------------------------------------------
    # 取得 Session
    # -----------------------------------------------------

    session = services.get_session(session_id)

    if session is None:
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": "查無此遊戲場次",
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

    # -----------------------------------------------------
    # 判斷答案
    # -----------------------------------------------------

    is_correct = services.check_answer(
        session,
        answer,
    )

    # =====================================================
    # 答錯
    # =====================================================

    if not is_correct:

        session = services.record_wrong_answer(
            session,
            reaction_time_ms,
        )

        wrong_count = (
            session["state"]["current_wrong_count"]
        )

        # -------------------------------------------------
        # 還沒錯滿 3 次 → 原題重試
        # -------------------------------------------------

        if wrong_count < MAX_WRONG_ATTEMPTS:
            return Response(
                {
                    "success": True,
                    "data": {
                        "is_correct": False,
                        "retry": True,
                        "current_question": (
                            session["question_number"]
                        ),
                        "difficulty": (
                            session["state"]["difficulty"]
                        ),
                        "wrong_count": wrong_count,
                        "remaining_attempts": (
                            MAX_WRONG_ATTEMPTS
                            - wrong_count
                        ),
                        "consecutive_correct": (
                            session["state"][
                                "consecutive_correct"
                            ]
                        ),
                        "difficulty_changed": False,
                        "previous_difficulty": None,
                        "is_completed": False,
                        "next_question": None,
                    },
                    "error": None,
                },
                status=status.HTTP_200_OK,
            )

        # -------------------------------------------------
        # 錯滿 3 次 → 本題失敗
        # -------------------------------------------------

        session = services.record_skipped_question(
            session
        )

        # -------------------------------------------------
        # 如果這就是第 10 題 → 遊戲結束
        # -------------------------------------------------

        if session["question_number"] >= TOTAL_QUESTIONS:

            final_session = services.complete_session(
                session
            )

            result = final_session["result"]

            return Response(
                {
                    "success": True,
                    "data": {
                        "is_correct": False,
                        "retry": False,
                        "question_skipped": True,
                        "wrong_count": (
                            MAX_WRONG_ATTEMPTS
                        ),
                        "remaining_attempts": 0,
                        "is_completed": True,

                        "total_correct": (
                            result["total_correct"]
                        ),
                        "total_questions": (
                            result["total_questions"]
                        ),
                        "accuracy": (
                            result["accuracy"]
                        ),

                        "speed_score": (
                            result["speed_score"]
                        ),
                        "difficulty_bonus": (
                            result["difficulty_bonus"]
                        ),
                        "error_penalty": (
                            result["error_penalty"]
                        ),

                        "final_score": (
                            result["final_score"]
                        ),
                        "final_difficulty": (
                            result["final_difficulty"]
                        ),
                        "average_reaction_time_ms": (
                            result[
                                "average_reaction_time_ms"
                            ]
                        ),
                        "completed_at": (
                            result["completed_at"]
                        ),
                    },
                    "error": None,
                },
                status=status.HTTP_200_OK,
            )

        # -------------------------------------------------
        # 還沒到第 10 題 → 下一題
        # -------------------------------------------------

        next_session = services.move_to_next_question(
            session
        )

        return Response(
            {
                "success": True,
                "data": {
                    "is_correct": False,
                    "retry": False,
                    "question_skipped": True,

                    "wrong_count": (
                        MAX_WRONG_ATTEMPTS
                    ),
                    "remaining_attempts": 0,

                    "consecutive_correct": (
                        next_session["state"][
                            "consecutive_correct"
                        ]
                    ),
                    "difficulty": (
                        next_session["state"][
                            "difficulty"
                        ]
                    ),
                    "difficulty_changed": False,
                    "previous_difficulty": None,

                    "is_completed": False,

                    "next_question": (
                        services.build_question_response(
                            next_session
                        )
                    ),
                },
                "error": None,
            },
            status=status.HTTP_200_OK,
        )

    # =====================================================
    # 答對
    # =====================================================

    session, difficulty_result = (
        services.record_correct_answer(
            session,
            reaction_time_ms,
        )
    )

    # -----------------------------------------------------
    # 第 10 題答對 → 遊戲結束
    # -----------------------------------------------------

    if session["question_number"] >= TOTAL_QUESTIONS:

        final_session = services.complete_session(
            session
        )

        result = final_session["result"]

        return Response(
            {
                "success": True,
                "data": {
                    "is_correct": True,
                    "retry": False,
                    "is_completed": True,

                    "total_correct": (
                        result["total_correct"]
                    ),
                    "total_questions": (
                        result["total_questions"]
                    ),
                    "accuracy": (
                        result["accuracy"]
                    ),

                    "speed_score": (
                        result["speed_score"]
                    ),
                    "difficulty_bonus": (
                        result["difficulty_bonus"]
                    ),
                    "error_penalty": (
                        result["error_penalty"]
                    ),

                    "final_score": (
                        result["final_score"]
                    ),
                    "final_difficulty": (
                        result["final_difficulty"]
                    ),
                    "average_reaction_time_ms": (
                        result[
                            "average_reaction_time_ms"
                        ]
                    ),
                    "completed_at": (
                        result["completed_at"]
                    ),
                },
                "error": None,
            },
            status=status.HTTP_200_OK,
        )

    # -----------------------------------------------------
    # 還沒到第 10 題 → 下一題
    # -----------------------------------------------------

    next_session = services.move_to_next_question(
        session
    )

    return Response(
        {
            "success": True,
            "data": {
                "is_correct": True,
                "retry": False,
                "is_completed": False,

                "wrong_count": 0,
                "remaining_attempts": (
                    MAX_WRONG_ATTEMPTS
                ),

                "consecutive_correct": (
                    next_session["state"][
                        "consecutive_correct"
                    ]
                ),

                "difficulty_changed": (
                    difficulty_result[
                        "difficulty_changed"
                    ]
                ),
                "previous_difficulty": (
                    difficulty_result[
                        "previous_difficulty"
                    ]
                ),

                "difficulty": (
                    next_session["state"][
                        "difficulty"
                    ]
                ),

                "total_correct": (
                    next_session["state"][
                        "total_correct"
                    ]
                ),

                "next_question": (
                    services.build_question_response(
                        next_session
                    )
                ),
            },
            "error": None,
        },
        status=status.HTTP_200_OK,
    )

# 歷史紀錄api
@api_view(["GET"])
def get_fridge_check_history(request):
    """
    GET /api/games/fridge-check/history/
    """

    user = get_current_user(request)

    if user is None:
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "找不到可使用的使用者",
                },
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    history = services.get_history(user.id)

    return Response(
        {
            "success": True,
            "data": {
                "history": history,
            },
            "error": None,
        },
        status=status.HTTP_200_OK,
    )