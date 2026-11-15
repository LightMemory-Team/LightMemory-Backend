"""
fridge_check Z-Score 與計分邏輯單元測試。
驗證 Z-score 跟自己的歷史比（冷啟動借全體）、±2 clamp 限制、
跨遊戲 standard_score（50 + 25z）換算以及 calculate_final_result 整合。
"""

from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from games.fridge_check.constants import DIFFICULTY_HARD
from games.fridge_check.services import (
    TOTAL_QUESTIONS,
    calculate_final_result,
    calculate_visual_spatial_z_score,
    complete_session,
    create_game_session,
)
from games.models import GameSession
from users.models import User


def _history(*pairs):
    """過去場次的 result 清單：每場 (正確率, 速度分)，都有反應時間資料。"""
    return [
        {"accuracy": accuracy, "speed_score": speed, "average_reaction_time_ms": 2000}
        for accuracy, speed in pairs
    ]


# 正確率平均 70／標準差 10，速度分平均 70／標準差 10。
# 三場的兩個指標 z 是 (-1, 0)、(0, -1)、(+1, +1)，
# 等權重合成 -0.5、-0.5、+1，變異數和 1.5。
PERSONAL_HISTORY = _history((60, 70), (70, 60), (80, 80))

# 兩個指標等權重、互不相關的理論變異數 = 0.5² + 0.5² = 0.5；
# 收縮後的合成分數變異數 = (1.5 + 3 × 0.5) ÷ (2 + 3) = 0.6
COMPOSITE_SD = 0.6**0.5


class FridgeCheckZScoreTests(SimpleTestCase):
    def _z(self, accuracy, speed, personal=PERSONAL_HISTORY, population=None):
        return calculate_visual_spatial_z_score(
            accuracy, speed, personal, population or {}
        )

    def test_at_personal_mean(self):
        """兩個指標都等於自己的歷史平均時，Z = 0.0，標準分數為 50。"""
        res = self._z(70, 70)
        self.assertEqual(res["z_score"], 0.0)
        self.assertEqual(res["standard_score"], 50)

    def test_above_average_is_standardized(self):
        """正確率 75（z = +0.5）、速度分 70（z = 0）：合成 0.25，÷ √0.6 ≈ 0.323。"""
        res = self._z(75, 70)
        self.assertEqual(res["z_score"], 0.323)
        # standard_score = round(50 + 25 * 0.323) = round(58.075) = 58
        self.assertEqual(res["standard_score"], 58)

    def test_below_average_is_standardized(self):
        """正確率 65（z = -0.5）、速度分 70 → 合成 -0.25 → -0.323。"""
        res = self._z(65, 70)
        self.assertEqual(res["z_score"], -0.323)
        # round(50 - 25 * 0.323) = round(41.925) = 42
        self.assertEqual(res["standard_score"], 42)

    def test_upper_clamp(self):
        """兩個指標 z 都是 +3，各自限制成 +2，合成 2，標準化後仍限制在 2.0。"""
        res = self._z(100, 100)
        self.assertEqual(res["z_score"], 2.0)
        self.assertEqual(res["standard_score"], 100)

    def test_lower_clamp(self):
        """兩個指標 z 都是 -4 → 限制成 -2 → 最終 -2.0，標準分數最低 1。"""
        res = self._z(30, 30)
        self.assertEqual(res["z_score"], -2.0)
        self.assertEqual(res["standard_score"], 1)

    def test_no_speed_data_uses_accuracy_only(self):
        """這場沒有反應時間資料（速度分 None）：只剩正確率，單一指標的 z 就是 z。"""
        res = self._z(80, None)
        self.assertEqual(res["z_score"], 1.0)
        self.assertEqual(res["standard_score"], 75)

    def test_history_without_speed_data_does_not_count_speed(self):
        """歷史場次沒有反應時間資料時，速度分 0 只代表「沒資料」，不能拿來當基準。"""
        no_speed_history = [
            {"accuracy": a, "speed_score": 0, "average_reaction_time_ms": None}
            for a in (60, 70, 80)
        ]
        res = self._z(80, 90, personal=no_speed_history)
        self.assertEqual(res["z_score"], 1.0)
        self.assertEqual(res["standard_score"], 75)

    def test_cold_start_borrows_population(self):
        """自己沒有歷史時，借其他使用者的基準（兩位各 3 場）。

        自己沒有參考場次，合成分數的變異數完全用理論值 0.5：0.25 ÷ √0.5 ≈ 0.354。
        """
        population = {"u1": PERSONAL_HISTORY, "u2": PERSONAL_HISTORY}
        res = self._z(75, 70, personal=[], population=population)
        self.assertEqual(res["z_score"], 0.354)
        # round(50 + 25 * 0.354) = round(58.85) = 59
        self.assertEqual(res["standard_score"], 59)

    def test_one_other_user_is_not_enough_population(self):
        """只有一位其他使用者（個人內自由度 2，不到 3）：資料不足，不給假分數。"""
        res = self._z(80, 70, personal=[], population={"u1": PERSONAL_HISTORY})
        self.assertIsNone(res["z_score"])
        self.assertIsNone(res["standard_score"])


class FridgeCheckFinalResultTests(SimpleTestCase):
    FAKE_SESSION = {
        "state": {
            "total_correct": 8,
            "speed_score": 76,
            "medium_correct": 3,
            "hard_correct": 2,
            "skipped_question_count": 1,
            "total_reaction_time_ms": 24500,
            "answer_count": 10,
            "current_stage": "hard",
        }
    }

    def test_calculate_final_result_includes_z_score_and_standard_score(self):
        """測試 calculate_final_result 完整回傳欄位與原本計分一致性。"""
        result = calculate_final_result(self.FAKE_SESSION, PERSONAL_HISTORY, {})

        # 1. 驗證原本計分公式不變
        # accuracy = 8 / 10 * 100 = 80.0
        self.assertEqual(result["accuracy"], 80.0)
        # speed_score = 76
        self.assertEqual(result["speed_score"], 76)
        # difficulty_bonus = 3 * 0.5 + 2 * 1.0 = 3.5
        self.assertEqual(result["difficulty_bonus"], 3.5)
        # error_penalty = 1 * 2 = 2
        # raw_score = 80.0 * 0.7 + 76 * 0.3 = 78.8
        self.assertEqual(result["raw_score"], 78.8)
        # raw_final_score = 78.8 + 3.5 - 2 = 80.3
        self.assertEqual(result["final_score"], 80.3)

        # 2. 驗證 Z-score 與 standard_score（正確率、速度分各自跟自己的歷史比）
        # z_正確率 = (80 - 70) / 10 = +1、z_速度分 = (76 - 70) / 10 = +0.6
        # 合成 0.8 → 標準化 0.8 ÷ √0.6 ≈ 1.033
        self.assertEqual(result["z_score"], 1.033)
        # standard_score = round(50 + 25 * 1.033) = round(75.825) = 76
        self.assertEqual(result["standard_score"], 76)

        # 3. 驗證基本欄位存在
        self.assertEqual(result["total_correct"], 8)
        self.assertEqual(result["total_questions"], TOTAL_QUESTIONS)
        self.assertEqual(result["final_difficulty"], "hard")
        self.assertEqual(result["average_reaction_time_ms"], 2450)
        self.assertIn("completed_at", result)

    def test_no_history_gives_null_scores(self):
        """歷史不足時 z_score、standard_score 為 None，其他欄位照常計算。"""
        result = calculate_final_result(self.FAKE_SESSION, [], {})

        self.assertIsNone(result["z_score"])
        self.assertIsNone(result["standard_score"])
        self.assertEqual(result["final_score"], 80.3)


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


def _final_result(session):
    """只測總分公式，不需要歷史。"""
    return calculate_final_result(session, [], {})


class CalculateFinalScoreTests(SimpleTestCase):
    def test_perfect_without_bonus_is_100(self):
        # 100 * 0.7 + 100 * 0.3 = 100
        result = _final_result(_make_session())

        self.assertEqual(result["final_score"], 100)

    def test_difficulty_bonus_can_exceed_100(self):
        # 100 + (3 * 0.5 + 4 * 1.0) = 105.5，不能被截斷成 100
        result = _final_result(_make_session(medium_correct=3, hard_correct=4))

        self.assertEqual(result["difficulty_bonus"], 5.5)
        self.assertEqual(result["final_score"], 105.5)

    def test_error_penalty_is_subtracted(self):
        # 正確率 80 * 0.7 + 速度 70 * 0.3 = 77，跳 2 題扣 4 → 73
        result = _final_result(
            _make_session(total_correct=8, speed_score=70, skipped_question_count=2)
        )

        self.assertEqual(result["final_score"], 73)

    def test_negative_score_is_floored_at_zero(self):
        # 全錯且 10 題都跳過：0 + 0 - 20 → 不顯示負分，以 0 計
        result = _final_result(
            _make_session(total_correct=0, speed_score=0, skipped_question_count=10)
        )

        self.assertEqual(result["final_score"], 0)


class CompleteSessionUsesHistoryTests(TestCase):
    """結束一場時，會從資料庫抓這場之前的場次當比較基準。"""

    def setUp(self):
        self.user = User.objects.create_user(username="grandma", password="pw123456")
        self.other = User.objects.create_user(username="other", password="pw123456")

    def _finished(self, user, accuracy, speed, minutes_ago):
        session = create_game_session(user)
        GameSession.objects.filter(pk=session["session_id"]).update(
            status="finished",
            is_pretest=False,  # 模擬「已經玩過的正式場次」
            result={
                "accuracy": accuracy,
                "speed_score": speed,
                "average_reaction_time_ms": 2000,
            },
            finished_at=timezone.now() - timedelta(minutes=minutes_ago),
        )

    def _finished_history(self, user):
        """同單元測試的 PERSONAL_HISTORY：(60, 70)、(70, 60)、(80, 80)。"""
        for minutes_ago, (accuracy, speed) in [
            (30, (60, 70)),
            (20, (70, 60)),
            (10, (80, 80)),
        ]:
            self._finished(user, accuracy, speed, minutes_ago)

    def _play(self, user):
        """玩一場：8 題答對（正確率 80）、速度分 76。"""
        session = create_game_session(user)
        session["state"].update(total_correct=8, speed_score=76, answer_count=10)
        return complete_session(session)["result"]

    def test_compares_with_own_previous_sessions(self):
        self._finished_history(self.user)
        self._finished(self.other, 10, 10, 5)  # 全體只有 1 場，不夠當基準，不影響結果

        result = self._play(self.user)

        self.assertEqual(result["z_score"], 1.033)
        self.assertEqual(result["standard_score"], 76)

    def test_new_user_borrows_population_history_after_familiarization(self):
        # 兩位其他使用者各 3 場 → 個人內自由度 4，夠當全體基準
        third = User.objects.create_user(username="third", password="pw123456")
        self._finished_history(self.other)
        self._finished_history(third)
        self._play(self.user)  # 第一場是熟悉場，不進歷史

        result = self._play(self.user)

        # 自己沒有參考場次，合成分數的變異數完全用理論值 0.5
        self.assertEqual(result["z_score"], 1.131)
        self.assertEqual(result["standard_score"], 78)

    def test_first_session_is_familiarization_even_with_population_history(self):
        third = User.objects.create_user(username="third", password="pw123456")
        self._finished_history(self.other)
        self._finished_history(third)

        session = create_game_session(self.user)
        session["state"].update(total_correct=8, speed_score=76, answer_count=10)
        result = complete_session(session)["result"]

        self.assertTrue(session["is_pretest"])
        self.assertIsNone(result["z_score"])
        self.assertIsNone(result["standard_score"])

    def test_familiarization_session_is_not_history(self):
        self._play(self.user)  # 熟悉場
        self._finished_history(self.user)

        result = self._play(self.user)

        self.assertEqual(result["z_score"], 1.033)

    def test_first_session_in_system_is_null(self):
        result = self._play(self.user)

        self.assertIsNone(result["z_score"])
        self.assertIsNone(result["standard_score"])
