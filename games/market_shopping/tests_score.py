"""
market_shopping Z-Score 與計分邏輯單元測試。
驗證 Z-score 跟自己的歷史比（冷啟動借全體）、±2 clamp 限制、
跨遊戲 standard_score（50 + 25z）換算以及 calculate_final_result 整合。
"""

from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from games.market_shopping.services import (
    TOTAL_QUESTIONS,
    calculate_final_result,
    calculate_math_z_score,
    calculate_speed_score,
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


class MarketShoppingZScoreTests(SimpleTestCase):
    def _z(self, accuracy, speed, personal=PERSONAL_HISTORY, population=None):
        return calculate_math_z_score(accuracy, speed, personal, population or {})

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


class MarketShoppingSpeedScoreTests(SimpleTestCase):
    def test_calculate_speed_score_tiers(self):
        """驗證單步反應速度分數分級。"""
        self.assertEqual(calculate_speed_score(2000), 5.0)
        self.assertEqual(calculate_speed_score(3000), 5.0)
        self.assertEqual(calculate_speed_score(4500), 4.0)
        self.assertEqual(calculate_speed_score(6000), 4.0)
        self.assertEqual(calculate_speed_score(8000), 2.5)
        self.assertEqual(calculate_speed_score(10000), 2.5)
        self.assertEqual(calculate_speed_score(12000), 1.5)
        self.assertEqual(calculate_speed_score(None), 0.0)


class MarketShoppingFinalResultTests(SimpleTestCase):
    def test_calculate_final_result_includes_z_score_and_standard_score(self):
        """測試 calculate_final_result 完整回傳欄位與分數換算。

        無速度分時 raw_score 維持純正確率（相容舊前端）。
        """
        fake_session = {
            "state": {
                "total_correct": 9,
                "first_try_correct_count": 8,
                "current_stage": "hard",
            }
        }

        result = calculate_final_result(fake_session, PERSONAL_HISTORY, {})

        # 1. 驗證原始指標
        # accuracy = 8 / 10 * 100 = 80.0
        self.assertEqual(result["accuracy"], 80.0)
        self.assertEqual(result["raw_score"], 80.0)
        self.assertEqual(result["total_correct"], 9)
        self.assertEqual(result["first_try_correct_count"], 8)
        self.assertEqual(result["total_questions"], TOTAL_QUESTIONS)
        self.assertEqual(result["difficulty"], "hard")

        # 2. 驗證 Z-score 與 standard_score
        # 沒有速度資料，只剩正確率：Z = (80.0 - 70) / 10 = 1.0
        self.assertEqual(result["z_score"], 1.0)
        # standard_score = round(50 + 25 * 1.0) = 75
        self.assertEqual(result["standard_score"], 75)
        self.assertIn("completed_at", result)

    def test_calculate_final_result_with_speed_score_continuous_standard_score(self):
        """加入作答速度分後，raw_score 與 standard_score 形成連續細緻分佈。

        打破只看正確率時只有 5 種離散數值的限制。
        """
        fake_session = {
            "state": {
                "total_correct": 9,
                "first_try_correct_count": 8,
                "speed_score": 85.0,
                "answer_count": 20,
                "total_reaction_time_ms": 60000,
                "current_stage": "hard",
            }
        }

        result = calculate_final_result(fake_session, PERSONAL_HISTORY, {})

        # accuracy = 80.0, speed_score = 85.0
        # raw_score = 80.0 * 0.7 + 85.0 * 0.3 = 56.0 + 25.5 = 81.5
        self.assertEqual(result["accuracy"], 80.0)
        self.assertEqual(result["speed_score"], 85.0)
        self.assertEqual(result["raw_score"], 81.5)
        # z_正確率 = (80 - 70) / 10 = +1、z_速度分 = (85 - 70) / 10 = +1.5
        # 合成 1.25 → 標準化 1.25 ÷ √0.6 ≈ 1.614
        self.assertEqual(result["z_score"], 1.614)
        # standard_score = round(50 + 25 * 1.614) = round(90.35) = 90
        self.assertEqual(result["standard_score"], 90)
        self.assertEqual(result["average_reaction_time_ms"], 3000)

    def test_no_history_gives_null_scores(self):
        """歷史不足時 z_score、standard_score 為 None，其他欄位照常計算。"""
        fake_session = {"state": {"total_correct": 9, "first_try_correct_count": 8}}

        result = calculate_final_result(fake_session, [], {})

        self.assertIsNone(result["z_score"])
        self.assertIsNone(result["standard_score"])
        self.assertEqual(result["raw_score"], 80.0)


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
        """玩一場：一次答對 8 題（正確率 80）、速度分 85。"""
        session = create_game_session(user)
        session["state"].update(
            first_try_correct_count=8,
            speed_score=85.0,
            answer_count=20,
            total_reaction_time_ms=60000,
        )
        return complete_session(session)["result"]

    def test_compares_with_own_previous_sessions(self):
        self._finished_history(self.user)
        self._finished(self.other, 10, 10, 5)  # 全體只有 1 場，不夠當基準，不影響結果

        result = self._play(self.user)

        self.assertEqual(result["z_score"], 1.614)
        self.assertEqual(result["standard_score"], 90)

    def test_new_user_borrows_population_history_after_familiarization(self):
        # 兩位其他使用者各 3 場 → 個人內自由度 4，夠當全體基準
        third = User.objects.create_user(username="third", password="pw123456")
        self._finished_history(self.other)
        self._finished_history(third)
        self._play(self.user)  # 第一場是熟悉場，不進歷史

        result = self._play(self.user)

        # 自己沒有參考場次，合成分數的變異數完全用理論值 0.5
        self.assertEqual(result["z_score"], 1.768)
        self.assertEqual(result["standard_score"], 94)

    def test_first_session_is_familiarization_even_with_population_history(self):
        third = User.objects.create_user(username="third", password="pw123456")
        self._finished_history(self.other)
        self._finished_history(third)

        session = create_game_session(self.user)
        session["state"].update(
            first_try_correct_count=8,
            speed_score=85.0,
            answer_count=20,
            total_reaction_time_ms=60000,
        )
        result = complete_session(session)["result"]

        self.assertTrue(session["is_pretest"])
        self.assertIsNone(result["z_score"])
        self.assertIsNone(result["standard_score"])

    def test_familiarization_session_is_not_history(self):
        self._play(self.user)  # 熟悉場
        self._finished_history(self.user)

        result = self._play(self.user)

        self.assertEqual(result["z_score"], 1.614)

    def test_first_session_in_system_is_null(self):
        result = self._play(self.user)

        self.assertIsNone(result["z_score"])
        self.assertIsNone(result["standard_score"])
