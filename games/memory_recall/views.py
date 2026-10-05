import random
from datetime import datetime, timedelta

from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from games import session_service
from games.dda import DDAConfig, apply_answer
from users.models import User

from .item_bank import load_advanced_groups, load_item_pools, load_items
from .score import calculate_step_score, calculate_total_score, normalize_to_100

GAME_TYPE = "memory_recall"

STAGE_ORDER = ["basic", "intermediate", "advanced"]

PRETEST_TOTAL_ROUNDS = 4
BASE_TIME_LIMIT_SECONDS = 60
PROMOTE_STREAK = 6
PROMOTE_BONUS_SECONDS = 15

# 測試用暫定值，正式上線前改為 20（規格書未定案，見 recall_memory.md 第九節討論）
ROUND_TIMEOUT_SECONDS = 10


def _current_user(request):
    """有登入時使用登入者，開發階段未登入時暫時抓第一位使用者。"""
    if request.user.is_authenticated:
        return request.user
    return User.objects.first()


def _get_session_or_error(session_id, user_id):
    """讀取 session，回傳 (session, error_response)，err 為 None 代表成功。

    統一處理 SESSION_NOT_FOUND、FORBIDDEN（session 不屬於這位使用者）兩種
    檢查，避免各支 API 重複同一段邏輯。
    """
    session = session_service.get_session(GAME_TYPE, session_id)
    if session is None:
        return None, Response(
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
    if session["state"].get("user_id") != user_id:
        return None, Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "FORBIDDEN",
                    "message": "這場遊戲不屬於目前的使用者",
                },
            },
            status=403,
        )
    return session, None


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
        "stage_item_pools": load_item_pools(),
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

    seed_item = _pick_seed("basic")
    initial_state = {
        # FORBIDDEN 檢查與 _has_finished_before 靠 state 的 user_id 判斷是誰的 session
        "user_id": user.id,
        "is_pretest": is_pretest,
        "current_stage": "basic",
        "correct_streak": 0,
        "current_item": seed_item,
        "expires_at": expires_at,
    }
    session = session_service.create_session(
        GAME_TYPE, initial_state=initial_state, user=user
    )

    data = {
        "session_id": session["session_id"],
        "is_pretest": is_pretest,
        "current_stage": "basic",
        "expires_at": expires_at,
        "seed_item": seed_item,
    }
    return Response({"success": True, "data": data, "error": None})


def _stage_item_names(stage):
    """回傳該階段所有物品名稱，advanced 會把各組攤平成一個清單。"""
    if stage == "advanced":
        return [i["item"] for g in load_advanced_groups() for i in g["items"]]
    return [i["item"] for i in load_items(stage)]


def _all_item_names():
    """回傳三個階段全部的物品名稱。"""
    return [name for stage in STAGE_ORDER for name in _stage_item_names(stage)]


def _item_stage(item):
    """回傳物品所屬的階段（各階段物品名稱不重複）。"""
    return next(stage for stage in STAGE_ORDER if item in _stage_item_names(stage))


def _find_group(item):
    """回傳物品所屬的高階分組，不是高階物品就回傳 None。"""
    for group in load_advanced_groups():
        if item in [i["item"] for i in group["items"]]:
            return group
    return None


def _pick_seed(stage):
    return random.choice(_stage_item_names(stage))


def _pick_distractor(stage, answer_item):
    """抽這一輪的干擾物：高階從全部物品隨機抽，其他階段從同階段物品隨機抽。"""
    pool = _all_item_names() if stage == "advanced" else _stage_item_names(stage)
    return random.choice([name for name in pool if name != answer_item])


def _pick_new_item(stage, option_items):
    """抽下一輪的正解：從目前階段抽，排除這一輪畫面上的選項。"""
    return random.choice(
        [name for name in _stage_item_names(stage) if name not in option_items]
    )


class MemoryRecallDDAStrategy:
    """memory_recall 的 DDA 策略：升階時加時間獎勵（不換種子，記憶鏈不中斷）。"""

    def on_correct(
        self, state: dict, config: DDAConfig, *, is_fast: bool = False
    ) -> dict:
        return {}

    def on_wrong(self, state: dict, config: DDAConfig) -> dict:
        return {}

    def on_promote(self, state: dict, config: DDAConfig, new_stage: str) -> dict:
        expires_at = state.get("expires_at")
        new_expires_at = expires_at
        if expires_at:
            new_expires_at = (
                datetime.fromisoformat(expires_at)
                + timedelta(seconds=PROMOTE_BONUS_SECONDS)
            ).isoformat()
        return {
            "expires_at": new_expires_at,
            "bonus_seconds_granted": PROMOTE_BONUS_SECONDS,
        }


DDA_CONFIG = DDAConfig(
    stage_order=STAGE_ORDER,
    promote_streak=PROMOTE_STREAK,
)
DDA_STRATEGY = MemoryRecallDDAStrategy()


# 3. 取得單一題目內容
@api_view(["GET"])
def round_view(request):
    user = _current_user(request)
    session_id = request.query_params.get("session_id")
    session, error_response = _get_session_or_error(
        session_id, user.id if user else None
    )
    if error_response is not None:
        return error_response
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
    answer_item = state["current_item"]
    # 卡片跟著正解的階段走：升階後第一輪的正解還是前一階段物品，卡片維持前一階段；
    # new_item 則跟著目前階段走，下一輪卡片才換成新階段
    stage = _item_stage(answer_item)
    distractor_item = _pick_distractor(stage, answer_item)
    option_items = [answer_item, distractor_item]
    random.shuffle(option_items)
    new_item = _pick_new_item(state["current_stage"], option_items)
    group = _find_group(answer_item)
    round_number = session["question_number"] + 1

    session_service.set_current_question(
        GAME_TYPE,
        session_id,
        {
            "round_number": round_number,
            "stage": stage,
            "group": group["group"] if group else None,
            "target_item": answer_item,
            "distractor_item": distractor_item,
            "option_items": option_items,
            "new_item": new_item,
            "round_expires_at": (
                None
                if state["is_pretest"]
                else (
                    timezone.now() + timedelta(seconds=ROUND_TIMEOUT_SECONDS)
                ).isoformat()
            ),
        },
    )

    # 正解只留在後端，回傳不含 target_item；new_item 是下一輪的正解，要給玩家記住
    data = {
        "round_number": round_number,
        "stage": stage,
        "option_items": option_items,
        "new_item": new_item,
    }
    return Response({"success": True, "data": data, "error": None})


# 4. 送出單題作答
@api_view(["POST"])
def round_answer(request):
    user = _current_user(request)
    session_id = request.data.get("session_id")
    session, error_response = _get_session_or_error(
        session_id, user.id if user else None
    )
    if error_response is not None:
        return error_response
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

    round_expires_at = current_question["round_expires_at"]
    if round_expires_at is not None and timezone.now() > datetime.fromisoformat(
        round_expires_at
    ):
        session_service.finish_session(GAME_TYPE, session_id, _build_result(session))
        return Response(
            {
                "success": False,
                "data": None,
                "error": {
                    "code": "ROUND_TIME_UP",
                    "message": "這一題已經超過作答時間，遊戲已結束",
                },
            },
            status=410,
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
                "new_item": current_question["new_item"],
                "selected_item": selected_item,
            },
        },
    )

    if is_pretest:
        # 前測不升階，只記連對數
        updated_state = {
            "current_stage": state["current_stage"],
            "correct_streak": state["correct_streak"] + 1 if is_correct else 0,
        }
        action_status = "no_promotion"
    else:
        # 升階看目前階段（state 的 current_stage），不看這一輪卡片的階段
        updated_state, action_status = apply_answer(
            state,
            DDA_CONFIG,
            DDA_STRATEGY,
            is_correct=is_correct,
        )
    promoted = action_status == "promoted"
    bonus_seconds_granted = updated_state.pop("bonus_seconds_granted", 0)
    # 記憶鏈不中斷：升階也一樣，這一輪的 new_item 就是下一輪的正解
    updated_state["current_item"] = current_question["new_item"]
    updated_state.setdefault("expires_at", state["expires_at"])

    current_stage = updated_state["current_stage"]
    correct_streak = updated_state["correct_streak"]
    expires_at = updated_state["expires_at"]

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
        state=updated_state,
    )

    data = {
        "is_correct": is_correct,
        "action": action,
        "current_stage": current_stage,
        "correct_streak": correct_streak,
        "bonus_seconds_granted": bonus_seconds_granted,
        "expires_at": expires_at,
        "score_earned": score_earned,
    }
    return Response({"success": True, "data": data, "error": None})


def _build_result(session):
    """依 session 目前的 step_records 彙總出 finish/ 要回傳、存檔的 result。"""
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
        [
            {"stage": r["detail"]["stage"], "is_correct": r["is_correct"]}
            for r in step_records
        ]
    )
    total_bonus_seconds = 0
    if not is_pretest:
        stage_index = STAGE_ORDER.index(state["current_stage"])
        total_bonus_seconds = stage_index * PROMOTE_BONUS_SECONDS

    return {
        "total_rounds": total_rounds,
        "total_correct": total_correct,
        "total_wrong": total_wrong,
        "accuracy": accuracy,
        "avg_response_time_ms": avg_response_time_ms,
        "final_stage": state["current_stage"],
        "total_bonus_seconds": total_bonus_seconds,
        "total_score": None if is_pretest else total_score,
        "score": None if is_pretest else normalize_to_100(total_score),
    }


# 5. 結束遊戲，計算總結果
@api_view(["POST"])
def finish(request):
    user = _current_user(request)
    session_id = request.data.get("session_id")
    session, error_response = _get_session_or_error(
        session_id, user.id if user else None
    )
    if error_response is not None:
        return error_response

    # 冪等性處理：已經結束過的 session 直接回傳既有結果，不重算不覆寫。
    if session["status"] == "finished":
        return Response({"success": True, "data": session["result"], "error": None})

    result = _build_result(session)
    session_service.finish_session(GAME_TYPE, session_id, result)
    return Response({"success": True, "data": result, "error": None})


# 6. 查詢單場結果
@api_view(["GET"])
def result(request, session_id):
    user = _current_user(request)
    session, error_response = _get_session_or_error(
        session_id, user.id if user else None
    )
    if error_response is not None:
        return error_response
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
