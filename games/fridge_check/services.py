from django.utils import timezone

from games import session_service
from games.dda import DDAConfig, NoOpStrategy, apply_answer
from games.zscore import (
    metric_z_scores,
    weighted_metric_z_score,
    z_score_to_display_score,
)

from .constants import (
    DIFFICULTY_EASY,
    DIFFICULTY_MEDIUM,
    DIFFICULTY_HARD,
    QUESTION_TYPE_RELATIVE,
    QUESTION_TYPE_LOCATE,
    QUESTION_TYPE_PLACE,
    TOTAL_QUESTIONS,
    PROMOTE_STREAK,
)
from .generators import generate_question


GAME_TYPE = "fridge_check"

# DDA 設定
DDA_CONFIG = DDAConfig(
    stage_order=[DIFFICULTY_EASY, DIFFICULTY_MEDIUM, DIFFICULTY_HARD],
    promote_streak=PROMOTE_STREAK,
)
DDA_STRATEGY = NoOpStrategy()

# 計分設定
ERROR_PENALTY_PER_SKIPPED_QUESTION = 2
MEDIUM_CORRECT_BONUS = 0.5
HARD_CORRECT_BONUS = 1.0

# Z-score 設定：只用原始能力分 raw_score 一個指標，越高越好
METRIC_RULES = {"raw_score": (1.0, False)}


def calculate_visual_spatial_z_score(raw_score, personal_history, population_history):
    """
    視覺空間 Z-score 與跨遊戲標準分數 (standard_score)。

    raw_score 跟自己過去場次的 raw_score 比（games/zscore.py）：
    自己不滿 3 場借全體使用者的歷史，全體也不夠就是 None（資料不足）。
    Z-score 限制在 ±2，standard_score = 50 + 25 * z_score（1～100）。

    personal_history / population_history: 過去場次的 result 清單（不含這場）
    """
    z_by_metric = metric_z_scores(
        {"raw_score": raw_score}, personal_history, population_history, METRIC_RULES
    )
    z_score = weighted_metric_z_score(z_by_metric, METRIC_RULES)
    if z_score is not None:
        z_score = round(z_score, 3)

    return {
        "z_score": z_score,
        "standard_score": z_score_to_display_score(z_score),
    }


def _previous_results(session):
    """這場之前已結束場次的 result（自己的、全體的），給 z-score 當比較基準。"""
    session_id = session["session_id"]
    return (
        session_service.list_previous_results(GAME_TYPE, session_id),
        session_service.list_previous_results(GAME_TYPE, session_id, same_user=False),
    )


def _build_current_question(question):
    """把 generator 產生的題目整理成 Session 儲存格式。"""
    return {
        "question_type": question["question_type"],
        "prompt": question["prompt"],
        "board": question["board"],
        "correct_answer": question["correct_answer"],
        "source_food": question.get("source_food"),
    }


def build_question_response(session):
    """
    組合回傳給前端的題目資料。
    correct_answer 不回傳給前端。
    """
    question = session["current_question"]

    return {
        "question_id": session["question_number"],
        "question_type": question["question_type"],
        "prompt": question["prompt"],
        "board": question["board"],
        "source_food": question.get("source_food"),
        "interaction_type": (
            "select_then_tap"
            if question["question_type"] == QUESTION_TYPE_PLACE
            else "tap"
        ),
    }


def create_game_session(user):
    """建立新的 Fridge Check Session。"""
    difficulty = DIFFICULTY_EASY
    question = generate_question(difficulty)

    initial_state = {
        "user_id": user.id,

        # DDA
        "current_stage": difficulty,
        "correct_streak": 0,
        "difficulty": difficulty,
        "consecutive_correct": 0,
        "current_wrong_count": 0,
        "current_question_had_error": False,

        # 基本成績
        "total_correct": 0,

        # 反應速度
        "speed_score": 0,
        "total_reaction_time_ms": 0,
        "answer_count": 0,

        # 難度加分
        "medium_correct": 0,
        "hard_correct": 0,

        # 錯三次被跳題
        "skipped_question_count": 0,
    }

    session = session_service.create_session(
        GAME_TYPE,
        initial_state=initial_state,
        user=user,
        is_pretest=session_service.is_first_session(GAME_TYPE, user),
    )

    session = session_service.update_session(
        GAME_TYPE,
        session["session_id"],
        question_number=1,
        current_question=_build_current_question(question),
    )

    return session


def get_session(session_id):
    """取得指定 Fridge Check Session。"""
    return session_service.get_session(GAME_TYPE, session_id)


def check_answer(session, answer):
    """依照題型判斷答案是否正確。"""
    question = session["current_question"]
    correct_answer = question["correct_answer"]
    question_type = question["question_type"]

    if question_type == QUESTION_TYPE_RELATIVE:
        return (
            answer.get("food_code")
            == correct_answer.get("food_code")
        )

    if question_type == QUESTION_TYPE_LOCATE:
        return (
            answer.get("position")
            == correct_answer.get("position")
        )

    if question_type == QUESTION_TYPE_PLACE:
        return (
            answer.get("food_code")
            == correct_answer.get("food_code")
            and answer.get("position")
            == correct_answer.get("position")
        )

    return False


def calculate_speed_score(reaction_time_ms):
    """
    單題答對時的反應速度分數。

    <= 3 秒：10
    <= 6 秒：8
    <= 10 秒：5
    > 10 秒：3

    答錯時不要呼叫此函式加分。
    """
    if reaction_time_ms is None:
        return 0

    seconds = reaction_time_ms / 1000

    if seconds <= 3:
        return 10

    if seconds <= 6:
        return 8

    if seconds <= 10:
        return 5

    return 3


def update_difficulty(state):
    """
    DDA（向後相容包裝函式，內部呼叫 games.dda 引擎）：
    連續完整答對 3 題後升階。

    easy -> medium
    medium -> hard
    hard 維持 hard
    """
    answered_difficulty = state.get("current_stage", state.get("difficulty", DIFFICULTY_EASY))
    updated_fields, action = apply_answer(
        state,
        DDA_CONFIG,
        DDA_STRATEGY,
        is_correct=True,
    )
    difficulty_changed = (action == "promoted")

    return {
        "difficulty": updated_fields["current_stage"],
        "consecutive_correct": updated_fields["correct_streak"],
        "difficulty_changed": difficulty_changed,
        "previous_difficulty": (
            answered_difficulty if difficulty_changed else None
        ),
    }


def record_correct_answer(session, reaction_time_ms):
    """
    答對一題後更新：
    - total_correct
    - speed_score
    - reaction time
    - 難度答對數
    - consecutive_correct / correct_streak
    - DDA
    """
    state = session["state"]

    # 注意：這裡一定要使用「升級前」的難度，
    # 因為這一題是在目前難度下完成的。
    answered_difficulty = state.get("current_stage", state.get("difficulty", DIFFICULTY_EASY))

    state_update = {
        "total_correct": state["total_correct"] + 1,
        "speed_score": (
            state["speed_score"]
            + calculate_speed_score(reaction_time_ms)
        ),
    }

    # 反應時間統計
    if reaction_time_ms is not None:
        state_update["total_reaction_time_ms"] = (
            state["total_reaction_time_ms"]
            + reaction_time_ms
        )
        state_update["answer_count"] = (
            state["answer_count"] + 1
        )

    # 難度加分統計
    if answered_difficulty == DIFFICULTY_MEDIUM:
        state_update["medium_correct"] = (
            state["medium_correct"] + 1
        )

    elif answered_difficulty == DIFFICULTY_HARD:
        state_update["hard_correct"] = (
            state["hard_correct"] + 1
        )

    # 透過 DDA 引擎更新難度狀態
    updated_fields, action = apply_answer(
        state,
        DDA_CONFIG,
        DDA_STRATEGY,
        is_correct=True,
    )
    difficulty_changed = (action == "promoted")
    previous_difficulty = answered_difficulty if difficulty_changed else None

    state_update.update(updated_fields)

    session = session_service.update_session(
        GAME_TYPE,
        session["session_id"],
        state=state_update,
    )

    difficulty_result = {
        "difficulty": updated_fields["current_stage"],
        "consecutive_correct": updated_fields["correct_streak"],
        "difficulty_changed": difficulty_changed,
        "previous_difficulty": previous_difficulty,
    }

    return session, difficulty_result


def record_wrong_answer(session, reaction_time_ms=None):
    """
    記錄一次錯誤。

    答錯：
    - 不取得速度分
    - current_wrong_count + 1
    - 本題標記曾經答錯
    - consecutive_correct / correct_streak 歸零

    reaction_time_ms 若有提供，仍可納入平均反應時間統計。
    """
    state = session["state"]

    updated_fields, _ = apply_answer(
        state,
        DDA_CONFIG,
        DDA_STRATEGY,
        is_correct=False,
    )

    state_update = {
        "current_wrong_count": (
            state["current_wrong_count"] + 1
        ),
        "current_question_had_error": True,
        **updated_fields,
    }

    if reaction_time_ms is not None:
        state_update["total_reaction_time_ms"] = (
            state["total_reaction_time_ms"]
            + reaction_time_ms
        )
        state_update["answer_count"] = (
            state["answer_count"] + 1
        )

    return session_service.update_session(
        GAME_TYPE,
        session["session_id"],
        state=state_update,
    )


def record_skipped_question(session):
    """同一題錯滿三次，被強制跳題。"""
    state = session["state"]

    updated_fields, _ = apply_answer(
        state,
        DDA_CONFIG,
        DDA_STRATEGY,
        is_correct=False,
    )

    return session_service.update_session(
        GAME_TYPE,
        session["session_id"],
        state={
            "skipped_question_count": (
                state["skipped_question_count"] + 1
            ),
            **updated_fields,
        },
    )


def move_to_next_question(session):
    """
    進入下一題。

    已完成 TOTAL_QUESTIONS 時回傳 None。
    """
    if session["question_number"] >= TOTAL_QUESTIONS:
        return None

    state = session["state"]
    current_difficulty = state.get("current_stage", state.get("difficulty", DIFFICULTY_EASY))

    question = generate_question(
        current_difficulty
    )

    session = session_service.update_session(
        GAME_TYPE,
        session["session_id"],
        question_number=session["question_number"] + 1,
        current_question=_build_current_question(question),
        state={
            "current_wrong_count": 0,
            "current_question_had_error": False,
        },
    )

    return session


def calculate_final_result(session, personal_history=None, population_history=None):
    """計算整場 Fridge Check 最終成績。

    personal_history / population_history 沒給時，從資料庫查這場之前的場次。
    """
    state = session["state"]

    # 1. 正確率 0 ~ 100
    accuracy = round(
        state["total_correct"]
        / TOTAL_QUESTIONS
        * 100,
        2,
    )

    # 2. 速度分
    # 10 題，每題最高 10，所以自然是 0 ~ 100
    speed_score = state["speed_score"]

    # 3. 原始能力指標 (正確率 70% + 速度分 30%)
    #    不含難度加分與跳題扣分，反映長者真實認知表現
    raw_score = round(
        accuracy * 0.7 + speed_score * 0.3,
        2,
    )

    # 4. 難度加分
    difficulty_bonus = round(
        state["medium_correct"] * MEDIUM_CORRECT_BONUS
        + state["hard_correct"] * HARD_CORRECT_BONUS,
        2,
    )

    # 5. 錯三次跳題扣分
    error_penalty = (
        state["skipped_question_count"]
        * ERROR_PENALTY_PER_SKIPPED_QUESTION
    )

    # 6. 遊戲最終總分 (包含難度加分與跳題扣分，作為長者端遊戲反饋)
    raw_final_score = (
        raw_score
        + difficulty_bonus
        - error_penalty
    )

    # 只限制下限為 0（避免負分），不設上限：難度加分可讓總分超過 100
    final_score = round(
        max(0, raw_final_score),
        2,
    )

    # 7. Z-score 與跨遊戲標準分數：由原始能力指標 raw_score 跟自己的歷史比；
    #    熟悉場不算分，給空歷史讓 z、標準分數都是 None
    if session.get("is_pretest"):
        personal_history, population_history = [], []
    elif personal_history is None or population_history is None:
        personal_history, population_history = _previous_results(session)
    z_result = calculate_visual_spatial_z_score(
        raw_score, personal_history, population_history
    )
    z_score = z_result["z_score"]
    standard_score = z_result["standard_score"]

    # 平均反應時間
    average_reaction_time_ms = (
        round(
            state["total_reaction_time_ms"]
            / state["answer_count"]
        )
        if state["answer_count"] > 0
        else None
    )

    return {
        "total_correct": state["total_correct"],
        "total_questions": TOTAL_QUESTIONS,

        "accuracy": accuracy,
        "speed_score": speed_score,
        "raw_score": raw_score,

        "medium_correct": state["medium_correct"],
        "hard_correct": state["hard_correct"],
        "difficulty_bonus": difficulty_bonus,

        "skipped_question_count": (
            state["skipped_question_count"]
        ),
        "error_penalty": error_penalty,

        "final_score": final_score,
        "z_score": z_score,
        "standard_score": standard_score,
        "final_difficulty": state.get("current_stage", state.get("difficulty", DIFFICULTY_EASY)),

        "average_reaction_time_ms": (
            average_reaction_time_ms
        ),

        "completed_at": timezone.now().isoformat(),
    }


def complete_session(session):
    """計算結果並將 Session 標記 finished。"""
    result = calculate_final_result(session)

    return session_service.finish_session(
        GAME_TYPE,
        session["session_id"],
        result,
    )


def get_history(user_id):
    """
    取得指定使用者的 Fridge Check 歷史紀錄。

    只取得：
    1. 屬於目前使用者
    2. 已完成的 session
    3. 有 result 的 session
    """

    sessions = session_service.list_sessions(GAME_TYPE)

    history = []

    for session in sessions:
        state = session.get("state", {})
        result = session.get("result")

        if state.get("user_id") != user_id:
            continue

        if session.get("status") != "finished":
            continue

        if not result:
            continue

        completed_at = result["completed_at"]
        average_reaction_time_ms = result["average_reaction_time_ms"]

        history.append(
            {
                # 舊版前端相容欄位
                "score": result["final_score"],
                "accuracy": result["accuracy"],
                "reaction_time": (
                    round(average_reaction_time_ms / 1000, 2)
                    if average_reaction_time_ms is not None
                    else None
                ),
                "final_difficulty": result["final_difficulty"],
                "played_at": completed_at,
                "played_date": completed_at[:10],

                # 新版完整資料
                "session_id": session["session_id"],
                "total_correct": result["total_correct"],
                "total_questions": result["total_questions"],
                "speed_score": result["speed_score"],
                "raw_score": result.get("raw_score"),
                "difficulty_bonus": result["difficulty_bonus"],
                "error_penalty": result["error_penalty"],
                "final_score": result["final_score"],
                "z_score": result.get("z_score"),
                "standard_score": result.get("standard_score"),
                "average_reaction_time_ms": average_reaction_time_ms,
                "completed_at": completed_at,
            }
        )

    # 最新的遊戲排前面
    history.sort(
        key=lambda item: item["completed_at"],
        reverse=True,
    )

    return history