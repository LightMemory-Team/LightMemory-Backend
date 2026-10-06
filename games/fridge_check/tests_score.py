"""fridge_check 最終成績（calculate_final_result）的單元測試。"""

from django.test import SimpleTestCase

from games.fridge_check.constants import DIFFICULTY_HARD
from games.fridge_check.services import calculate_final_result


def _make_session(
    *,
    total_correct=10,
    speed_score=100,
    medium_correct=0,
    hard_correct=0,
    skipped_question_count=0,
):
    return {
        "state": {
            "total_correct": total_correct,
            "speed_score": speed_score,
            "medium_correct": medium_correct,
            "hard_correct": hard_correct,
            "skipped_question_count": skipped_question_count,
            "total_reaction_time_ms": 20000,
            "answer_count": 10,
            "current_stage": DIFFICULTY_HARD,
        }
    }


class CalculateFinalScoreTests(SimpleTestCase):
    def test_perfect_without_bonus_is_100(self):
        # 100 * 0.7 + 100 * 0.3 = 100
        result = calculate_final_result(_make_session())

        self.assertEqual(result["final_score"], 100)

    def test_difficulty_bonus_can_exceed_100(self):
        # 100 + (3 * 0.5 + 4 * 1.0) = 105.5，不能被截斷成 100
        result = calculate_final_result(_make_session(medium_correct=3, hard_correct=4))

        self.assertEqual(result["difficulty_bonus"], 5.5)
        self.assertEqual(result["final_score"], 105.5)

    def test_error_penalty_is_subtracted(self):
        # 正確率 80 * 0.7 + 速度 70 * 0.3 = 77，跳 2 題扣 4 → 73
        result = calculate_final_result(
            _make_session(total_correct=8, speed_score=70, skipped_question_count=2)
        )

        self.assertEqual(result["final_score"], 73)

    def test_negative_score_is_floored_at_zero(self):
        # 全錯且 10 題都跳過：0 + 0 - 20 → 不顯示負分，以 0 計
        result = calculate_final_result(
            _make_session(total_correct=0, speed_score=0, skipped_question_count=10)
        )

        self.assertEqual(result["final_score"], 0)
