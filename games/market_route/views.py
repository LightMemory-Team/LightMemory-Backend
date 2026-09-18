import random

from rest_framework.decorators import api_view
from rest_framework.response import Response

from games import session_service

from .item_bank import load_distractor_item, load_items
from .market_score import calculate_step_score, calculate_total_score

GAME_TYPE = "market_route"

STAGE_EXPOSURE_RANGE = {
    "basic": (2000, 1500),
    "intermediate": (1500, 1000),
    "advanced": (1000, 500),
}

STAGE_ORDER = ["basic", "intermediate", "advanced"]
PROMOTE_STREAK = 5
FAST_PROMOTE_STREAK = 3
FAST_RESPONSE_RATIO = 0.5
MAX_WRONG_ATTEMPTS = 3
EXPOSURE_STEP_DOWN = 100
EXPOSURE_STEP_UP = 150
POSITIONS = ["q1", "q2", "q3", "q4"]


# 1. 取得本場遊戲設定
@api_view(["GET"])
def config(request):
    data = {
        "is_pretest": False,
        "current_stage": "basic",
        "total_questions": 20,
        "timeout_seconds": 20,
        "promote_streak": PROMOTE_STREAK,
        "fast_promote_streak": FAST_PROMOTE_STREAK,
        "fast_response_ratio": FAST_RESPONSE_RATIO,
        "max_wrong_attempts": MAX_WRONG_ATTEMPTS,
        "stage_exposure_range": {
            "basic": [2000, 1500],
            "intermediate": [1500, 1000],
            "advanced": [1000, 500],
        },
    }
    return Response({"success": True, "data": data, "error": None})


# 2. 開始一場遊戲，建立 session
@api_view(["POST"])
def start(request):
    loose_exposure, _ = STAGE_EXPOSURE_RANGE["basic"]
    initial_state = {
        "current_stage": "basic",
        "correct_streak": 0,
        "fast_correct_streak": 0,
        "wrong_attempts": 0,
        "exposure_time_ms": loose_exposure,
    }
    session = session_service.create_session(GAME_TYPE, initial_state=initial_state)
    data = {
        "session_id": session["session_id"],
        "current_stage": session["state"]["current_stage"],
    }
    return Response({"success": True, "data": data, "error": None})


def _pick_question(stage, exposure_time_ms, question_number):
    """依階段出題，advanced 階段的干擾物固定是魚骨頭，位置排除 target 保證不重疊。"""
    items = load_items()
    target = random.choice(items)

    if stage == "basic":
        target_position = "center"
        distractor_items = []
    else:
        target_position = random.choice(POSITIONS)
        distractor_items = []
        if stage == "advanced":
            distractor_position = random.choice(
                [p for p in POSITIONS if p != target_position]
            )
            distractor_items = [
                {"item": load_distractor_item(), "position": distractor_position}
            ]

    return {
        "question_number": question_number,
        "stage": stage,
        "target_item": target["item"],
        "target_position": target_position,
        "distractor_items": distractor_items,
        "exposure_time_ms": exposure_time_ms,
    }


# 3. 取得單一題目內容
@api_view(["GET"])
def round_view(request):
    session_id = request.query_params.get("session_id")
    session = session_service.get_session(GAME_TYPE, session_id)
    if session is None:
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": "找不到指定的 session",
                },
            },
            status=404,
        )

    question = _pick_question(
        session["state"]["current_stage"],
        session["state"]["exposure_time_ms"],
        session["question_number"] + 1,
    )
    session_service.set_current_question(GAME_TYPE, session_id, question)
    return Response({"success": True, "data": question, "error": None})


def _apply_dda(session, is_correct, is_timeout, response_time_ms):
    """依規格書「三、DDA 規則」計算答題後的新狀態，回傳 (更新欄位 dict, action)。

    額外規則（快速升階）：連續 5 題答對才升階，容易因為長者不小心誤觸提前
    達標。所以加一個更嚴格但門檻更低的條件：連續 3 題「答對且反應時間在
    當下曝光時間的 50% 以內」也視為熟練，直接升階。只要有一題答錯、或答對
    但不夠快，這個快速連續計數就歸零重算。
    """
    state = session["state"]
    stage = state["current_stage"]
    loose, tight = STAGE_EXPOSURE_RANGE[stage]
    exposure_time_ms = state["exposure_time_ms"]

    if is_correct:
        correct_streak = state["correct_streak"] + 1
        wrong_attempts = 0

        is_fast = (not is_timeout) and (
            response_time_ms is not None
            and response_time_ms <= exposure_time_ms * FAST_RESPONSE_RATIO
        )
        fast_correct_streak = state["fast_correct_streak"] + 1 if is_fast else 0

        if (
            correct_streak >= PROMOTE_STREAK
            or fast_correct_streak >= FAST_PROMOTE_STREAK
        ):
            stage_index = STAGE_ORDER.index(stage)
            if stage_index < len(STAGE_ORDER) - 1:
                stage = STAGE_ORDER[stage_index + 1]
            exposure_time_ms, _ = STAGE_EXPOSURE_RANGE[stage]
            correct_streak = 0
            fast_correct_streak = 0
        else:
            exposure_time_ms = max(tight, exposure_time_ms - EXPOSURE_STEP_DOWN)
        action = "next_question"
    else:
        correct_streak = 0
        fast_correct_streak = 0
        wrong_attempts = state["wrong_attempts"] + 1
        if wrong_attempts >= MAX_WRONG_ATTEMPTS:
            action = "next_question"
            wrong_attempts = 0
        else:
            exposure_time_ms = min(loose, exposure_time_ms + EXPOSURE_STEP_UP)
            action = "retry"

    updated_fields = {
        "current_stage": stage,
        "correct_streak": correct_streak,
        "fast_correct_streak": fast_correct_streak,
        "wrong_attempts": wrong_attempts,
        "exposure_time_ms": exposure_time_ms,
    }
    return updated_fields, action


# 4. 送出單題作答
@api_view(["POST"])
def round_answer(request):
    session_id = request.data.get("session_id")
    session = session_service.get_session(GAME_TYPE, session_id)
    if session is None:
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": "找不到指定的 session",
                },
            },
            status=404,
        )

    attempt_number = request.data.get("attempt_number")
    answer_position = request.data.get("answer_position")
    is_timeout = request.data.get("is_timeout", False)
    response_time_ms = request.data.get("response_time_ms")

    current_question = session["current_question"]
    is_correct = (not is_timeout) and answer_position == current_question[
        "target_position"
    ]

    state = session["state"]

    # 用套用 DDA 規則「之前」的 stage/exposure 記錄這次嘗試，因為那才是玩家
    # 實際作答當下面對的難度。
    score_earned = calculate_step_score(
        attempt_number=attempt_number,
        stage=state["current_stage"],
        is_correct=is_correct,
        is_timeout=is_timeout,
        response_time_ms=response_time_ms,
        exposure_time_ms=state["exposure_time_ms"],
    )
    session_service.save_step(
        GAME_TYPE,
        session_id,
        {
            "question_number": current_question["question_number"],
            "attempt_number": attempt_number,
            "stage": state["current_stage"],
            "is_correct": is_correct,
            "is_timeout": is_timeout,
            "response_time_ms": response_time_ms,
            "exposure_time_ms": state["exposure_time_ms"],
        },
    )

    updated_fields, action = _apply_dda(
        session, is_correct, is_timeout, response_time_ms
    )
    question_number = session["question_number"]
    if action == "next_question":
        question_number += 1
    session_service.update_session(
        GAME_TYPE, session_id, question_number=question_number, state=updated_fields
    )

    data = {
        "is_correct": is_correct,
        "action": action,
        "current_stage": updated_fields["current_stage"],
        "correct_streak": updated_fields["correct_streak"],
        "fast_correct_streak": updated_fields["fast_correct_streak"],
        "wrong_attempts": updated_fields["wrong_attempts"],
        "score_earned": score_earned,
    }
    return Response({"success": True, "data": data, "error": None})


# 5. 結束遊戲，計算總結果
@api_view(["POST"])
def finish(request):
    session_id = request.data.get("session_id")
    session = session_service.get_session(GAME_TYPE, session_id)
    if session is None:
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": "找不到指定的 session",
                },
            },
            status=404,
        )

    step_records = session["step_records"]
    answered_question_numbers = {r["question_number"] for r in step_records}
    correct_count = sum(1 for r in step_records if r["is_correct"])
    timeout_count = sum(1 for r in step_records if r["is_timeout"])
    response_times = [
        r["response_time_ms"] for r in step_records if r["response_time_ms"] is not None
    ]
    avg_response_time_ms = (
        round(sum(response_times) / len(response_times)) if response_times else 0
    )
    answered_count = len(answered_question_numbers)
    accuracy = round(correct_count / answered_count, 2) if answered_count else 0.0

    # step_records 多存了 question_number（給上面彙總用），market_score.py
    # 的計分函式不需要這個欄位，計分前先過濾掉。
    scoring_inputs = [
        {k: v for k, v in r.items() if k != "question_number"} for r in step_records
    ]

    result = {
        "total_questions": 20,
        "answered_count": answered_count,
        "correct_count": correct_count,
        "timeout_count": timeout_count,
        "accuracy": accuracy,
        "avg_response_time_ms": avg_response_time_ms,
        "final_stage": session["state"]["current_stage"],
        "total_score": calculate_total_score(scoring_inputs),
    }
    session_service.finish_session(GAME_TYPE, session_id, result)
    return Response({"success": True, "data": result, "error": None})


# 6. 查詢單場結果
@api_view(["GET"])
def result(request, session_id):
    session = session_service.get_session(GAME_TYPE, session_id)
    if session is None:
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": "找不到指定的 session",
                },
            },
            status=404,
        )
    if session["status"] != "finished":
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "SESSION_NOT_FINISHED",
                    "message": "這場遊戲尚未結束",
                },
            },
            status=400,
        )

    return Response(
        {"success": True, "data": {"session_result": session["result"]}, "error": None}
    )
