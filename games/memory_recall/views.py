import random
from datetime import datetime, timedelta

from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from games import session_service
from users.models import User

from .item_bank import load_advanced_groups, load_items
from .score import calculate_step_score, calculate_total_score

GAME_TYPE = "memory_recall"

STAGE_ORDER = ["basic", "intermediate", "advanced"]

MEMORIZE_TIME_MS = 1200
DELAY_MS = 1000

PRETEST_TOTAL_ROUNDS = 4
BASE_TIME_LIMIT_SECONDS = 60
PROMOTE_STREAK = 3
PROMOTE_BONUS_SECONDS = 15


def _current_user(request):
    """有登入時使用登入者，開發階段未登入時暫時抓第一位使用者。"""
    if request.user.is_authenticated:
        return request.user
    return User.objects.first()


def _has_finished_before(user_id):
    """判斷這位使用者是否已經玩過（有 finished 過）這款遊戲，不分前測或正式賽。

    只要玩完過一次（前測也算），之後每一場都是正式賽；前測只在「這款遊戲
    第一次玩」時觸發一次。
    """
    sessions = session_service.list_sessions(GAME_TYPE)
    return any(
        s["status"] == "finished" and s["state"].get("user_id") == user_id
        for s in sessions
    )


# 1. 取得本場遊戲設定
@api_view(["GET"])
def config(request):
    data = {
        "is_pretest": False,
        "current_stage": "basic",
        "pretest_total_rounds": PRETEST_TOTAL_ROUNDS,
        "base_time_limit_seconds": BASE_TIME_LIMIT_SECONDS,
        "promote_streak": PROMOTE_STREAK,
        "promote_bonus_seconds": PROMOTE_BONUS_SECONDS,
        "memorize_time_ms": MEMORIZE_TIME_MS,
        "delay_ms": DELAY_MS,
    }
    return Response({"success": True, "data": data, "error": None})


# 2. 開始一場遊戲，建立 session
@api_view(["POST"])
def start(request):
    user = _current_user(request)
    if user is None:
        return Response(
            {
                "success": False,
                "data": None,
                "error": {"code": "USER_NOT_FOUND", "message": "查無使用者資料"},
            },
            status=404,
        )

    is_pretest = not _has_finished_before(user.id)

    expires_at = None
    if not is_pretest:
        expires_at = (
            timezone.now() + timedelta(seconds=BASE_TIME_LIMIT_SECONDS)
        ).isoformat()

    initial_state = {
        "user_id": user.id,
        "is_pretest": is_pretest,
        "current_stage": "basic",
        "correct_streak": 0,
        "expires_at": expires_at,
    }
    session = session_service.create_session(GAME_TYPE, initial_state=initial_state)

    data = {
        "session_id": session["session_id"],
        "is_pretest": is_pretest,
        "current_stage": "basic",
        "expires_at": expires_at,
    }
    return Response({"success": True, "data": data, "error": None})


def _pick_question(stage):
    """依階段出題。advanced 先隨機選一個形狀分組，再用組內固定 3 個型態出題。"""
    if stage == "advanced":
        group = random.choice(load_advanced_groups())
        pool = group["items"]
        group_name = group["group"]
    else:
        pool = load_items(stage)
        group_name = None

    target = random.choice(pool)
    option_items = [item["item"] for item in pool]
    random.shuffle(option_items)

    return {
        "stage": stage,
        "group": group_name,
        "target_item": target["item"],
        "option_items": option_items,
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
    if session["status"] != "in_progress":
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "SESSION_ALREADY_FINISHED",
                    "message": "這場遊戲已經結束了",
                },
            },
            status=409,
        )

    question = _pick_question(session["state"]["current_stage"])
    round_number = session["question_number"] + 1
    question["round_number"] = round_number
    session_service.set_current_question(GAME_TYPE, session_id, question)

    data = {
        "round_number": round_number,
        "stage": question["stage"],
        "target_item": question["target_item"],
        "memorize_time_ms": MEMORIZE_TIME_MS,
        "delay_ms": DELAY_MS,
        "option_items": question["option_items"],
    }
    return Response({"success": True, "data": data, "error": None})


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
    if session["status"] != "in_progress":
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "SESSION_ALREADY_FINISHED",
                    "message": "這場遊戲已經結束了",
                },
            },
            status=409,
        )

    state = session["state"]
    is_pretest = state["is_pretest"]

    if not is_pretest and timezone.now() > datetime.fromisoformat(state["expires_at"]):
        return Response(
            {
                "success": False,
                "data": None,
                "error": {"code": "GAME_TIME_UP", "message": "遊戲時間已經到期"},
            },
            status=410,
        )

    round_number = request.data.get("round_number")
    current_question = session["current_question"]
    if current_question is None or round_number != current_question["round_number"]:
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "ROUND_MISMATCH",
                    "message": "送出的 round_number 與後端目前記錄的輪數不一致",
                },
            },
            status=400,
        )

    selected_item = request.data.get("selected_item")
    if selected_item not in current_question["option_items"]:
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "INVALID_ITEM",
                    "message": "selected_item 不在該輪 option_items 之中",
                },
            },
            status=400,
        )

    response_time_ms = request.data.get("response_time_ms")
    is_correct = selected_item == current_question["target_item"]
    stage = current_question["stage"]

    score_earned = (
        0 if is_pretest else calculate_step_score(stage=stage, is_correct=is_correct)
    )

    session_service.save_step(
        GAME_TYPE,
        session_id,
        {
            "round_number": round_number,
            "stage": stage,
            "is_correct": is_correct,
            "response_time_ms": response_time_ms,
            "detail": {
                "stage": stage,
                "group": current_question["group"],
                "target_item": current_question["target_item"],
                "option_items": current_question["option_items"],
                "selected_item": selected_item,
            },
        },
    )

    correct_streak = state["correct_streak"] + 1 if is_correct else 0
    bonus_seconds_granted = 0
    expires_at = state["expires_at"]

    stage_index = STAGE_ORDER.index(stage)
    promoted = (
        not is_pretest
        and is_correct
        and correct_streak >= PROMOTE_STREAK
        and stage_index < len(STAGE_ORDER) - 1
    )
    if promoted:
        stage = STAGE_ORDER[stage_index + 1]
        correct_streak = 0
        bonus_seconds_granted = PROMOTE_BONUS_SECONDS
        expires_at = (
            datetime.fromisoformat(expires_at)
            + timedelta(seconds=PROMOTE_BONUS_SECONDS)
        ).isoformat()

    question_number = session["question_number"] + 1

    if is_pretest:
        action = (
            "finished" if question_number >= PRETEST_TOTAL_ROUNDS else "next_question"
        )
    else:
        action = "promoted" if promoted else "next_question"

    session_service.update_session(
        GAME_TYPE,
        session_id,
        question_number=question_number,
        state={
            "current_stage": stage,
            "correct_streak": correct_streak,
            "expires_at": expires_at,
        },
    )

    data = {
        "is_correct": is_correct,
        "action": action,
        "current_stage": stage,
        "correct_streak": correct_streak,
        "bonus_seconds_granted": bonus_seconds_granted,
        "expires_at": expires_at,
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

    state = session["state"]
    is_pretest = state["is_pretest"]
    step_records = session["step_records"]

    total_rounds = len(step_records)
    total_correct = sum(1 for r in step_records if r["is_correct"])
    total_wrong = total_rounds - total_correct
    accuracy = round(total_correct / total_rounds, 2) if total_rounds else 0.0
    response_times = [
        r["response_time_ms"] for r in step_records if r["response_time_ms"] is not None
    ]
    avg_response_time_ms = (
        round(sum(response_times) / len(response_times)) if response_times else 0
    )

    total_score = calculate_total_score(
        [{"stage": r["stage"], "is_correct": r["is_correct"]} for r in step_records]
    )
    total_bonus_seconds = 0
    if not is_pretest:
        stage_index = STAGE_ORDER.index(state["current_stage"])
        total_bonus_seconds = stage_index * PROMOTE_BONUS_SECONDS

    result = {
        "total_rounds": total_rounds,
        "total_correct": total_correct,
        "total_wrong": total_wrong,
        "accuracy": accuracy,
        "avg_response_time_ms": avg_response_time_ms,
        "final_stage": state["current_stage"],
        "total_bonus_seconds": total_bonus_seconds,
        "total_score": None if is_pretest else total_score,
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
