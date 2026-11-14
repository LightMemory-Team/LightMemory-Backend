"""遊戲 Demo 模式：只有 admin_demo 這個帳號，每款遊戲答 3 題就結束、分數固定 80。

複賽 demo 時給評審看完整的遊戲流程（開始 → 作答 → 結束畫面）而不用玩滿 10～28 題。
其他帳號完全不受影響：每個函式遇到一般使用者都回傳原本的值、不改任何東西。

- question_limit()：這場要出幾題（demo 3 題，其他人照各遊戲原本的題數）
- apply_demo_score()：結算時把顯示分數改成 80、z 改成 1.2
  （儀表板、週報是用 z 換算分數：50 + 25 × 1.2 = 80，才會跟結束畫面一致）
"""

from demo_tools.constants import DEMO_USERNAME
from users.models import User

DEMO_QUESTION_COUNT = 3
DEMO_SCORE = 80
DEMO_Z = 1.2

# 各遊戲結算結果裡「給玩家看的分數」欄位
SCORE_KEYS = {
    "market_route": ["total_score"],
    "memory_recall": ["total_score"],
    "fridge_check": ["final_score", "standard_score"],
    "market_shopping": ["standard_score"],
    "market_sort": ["cognitive_flexibility_score"],
}


def is_demo_user(user_or_id):
    """傳入 User 或 user id 都可以；沒有使用者（None）一律不是 demo。"""
    if user_or_id is None:
        return False
    if isinstance(user_or_id, User):
        return user_or_id.username == DEMO_USERNAME
    return User.objects.filter(pk=user_or_id, username=DEMO_USERNAME).exists()


def question_limit(user_or_id, default):
    """這位使用者每場要出幾題：demo 帳號 3 題，其他人照 default。"""
    return DEMO_QUESTION_COUNT if is_demo_user(user_or_id) else default


def session_question_limit(session, default):
    """同 question_limit，但傳入 session_service 的 session dict。"""
    return question_limit(session.get("user_id"), default)


def apply_demo_score(game_type, result):
    """就地把結算結果的分數改成 demo 固定分數（呼叫端已確認是 demo 帳號）。

    就地修改：market_route、memory_recall 的 view 回傳的是自己手上的 result，
    改同一個 dict，結束畫面拿到的才會是 80。
    """
    if not isinstance(result, dict):
        return result
    for key in SCORE_KEYS.get(game_type, []):
        result[key] = DEMO_SCORE
    result["z_score"] = DEMO_Z
    return result


def market_sort_result(questions, generated_at):
    """market_sort 的 demo 結算結果。

    正式計分至少要 28 題，demo 只有 3 題，所以不算原始指標（也不放 raw_metrics，
    這場就不會被拿去當任何人的比較基準），直接給固定分數。
    """
    return {
        "z_scores": {},
        "z_score": DEMO_Z,
        "cognitive_flexibility_score": DEMO_SCORE,
        "play_seconds": round(sum(q["reaction_time_ms"] for q in questions) / 1000),
        "generated_at": generated_at.isoformat(),
        "is_demo": True,
    }
