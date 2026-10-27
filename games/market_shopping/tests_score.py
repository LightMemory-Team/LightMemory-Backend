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


def _history(*raw_scores):
    """過去場次的 result 清單，只需要 raw_score。"""
    return [{"raw_score": raw_score} for raw_score in raw_scores]


# 平均 70、樣本標準差 10
PERSONAL_HISTORY = _history(60.0, 70.0, 80.0)


class MarketShoppingZScoreTests(SimpleTestCase):
    def _z(self, raw_score, personal=PERSONAL_HISTORY, population=()):
        return calculate_math_z_score(raw_score, personal, list(population))

    def test_at_personal_mean(self):
        """分數等於自己的歷史平均時，Z = 0.0，標準分數為 50。"""
        res = self._z(70.0)
        self.assertEqual(res["z_score"], 0.0)
        self.assertEqual(res["standard_score"], 50)

    def test_one_std_above(self):
        """高於自己平均 1 個標準差 (80 分)，Z = 1.0，標準分數為 75。"""
        res = self._z(80.0)
        self.assertEqual(res["z_score"], 1.0)
        self.assertEqual(res["standard_score"], 75)

    def test_one_std_below(self):
        """低於自己平均 1 個標準差 (60 分)，Z = -1.0，標準分數為 25。"""
        res = self._z(60.0)
        self.assertEqual(res["z_score"], -1.0)
        self.assertEqual(res["standard_score"], 25)

    def test_upper_clamp(self):
        """100 分 -> raw Z = (100 - 70) / 10 = +3.0 -> clamp 為 2.0，標準分數為 100。"""
        res = self._z(100.0)
        self.assertEqual(res["z_score"], 2.0)
        self.assertEqual(res["standard_score"], 100)

    def test_lower_clamp(self):
        """30 分 -> raw Z = (30 - 70) / 10 = -4.0 -> clamp 為 -2.0，標準分數最低 1。"""
        res = self._z(30.0)
        self.assertEqual(res["z_score"], -2.0)
        self.assertEqual(res["standard_score"], 1)

    def test_rounding(self):
        """Z-score 3 位小數，standard_score 整數。"""
        # 85.5 分 -> Z = 1.55
        # standard_score = round(50 + 25 * 1.55) = round(88.75) = 89
        res = self._z(85.5)
        self.assertEqual(res["z_score"], 1.55)
        self.assertEqual(res["standard_score"], 89)

    def test_cold_start_uses_population(self):
        """自己不滿 3 場時，改跟全體使用者的歷史比。"""
        res = self._z(80.0, personal=_history(95.0), population=PERSONAL_HISTORY)
        self.assertEqual(res["z_score"], 1.0)

    def test_not_enough_history_is_none(self):
        """自己和全體都不滿 3 場：資料不足，不給假分數。"""
        res = self._z(80.0, personal=[], population=_history(70.0))
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

        result = calculate_final_result(fake_session, PERSONAL_HISTORY, [])

        # 1. 驗證原始指標
        # accuracy = 8 / 10 * 100 = 80.0
        self.assertEqual(result["accuracy"], 80.0)
        self.assertEqual(result["raw_score"], 80.0)
        self.assertEqual(result["total_correct"], 9)
        self.assertEqual(result["first_try_correct_count"], 8)
        self.assertEqual(result["total_questions"], TOTAL_QUESTIONS)
        self.assertEqual(result["difficulty"], "hard")

        # 2. 驗證 Z-score 與 standard_score（raw_score 跟自己的歷史比）
        # Z = (80.0 - 70) / 10 = 1.0
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

        result = calculate_final_result(fake_session, PERSONAL_HISTORY, [])

        # accuracy = 80.0, speed_score = 85.0
        # raw_score = 80.0 * 0.7 + 85.0 * 0.3 = 56.0 + 25.5 = 81.5
        self.assertEqual(result["accuracy"], 80.0)
        self.assertEqual(result["speed_score"], 85.0)
        self.assertEqual(result["raw_score"], 81.5)
        # Z = (81.5 - 70) / 10 = 1.15
        self.assertEqual(result["z_score"], 1.15)
        # standard_score = round(50 + 25 * 1.15) = round(78.75) = 79
        self.assertEqual(result["standard_score"], 79)
        self.assertEqual(result["average_reaction_time_ms"], 3000)

    def test_no_history_gives_null_scores(self):
        """歷史不足時 z_score、standard_score 為 None，其他欄位照常計算。"""
        fake_session = {"state": {"total_correct": 9, "first_try_correct_count": 8}}

        result = calculate_final_result(fake_session, [], [])

        self.assertIsNone(result["z_score"])
        self.assertIsNone(result["standard_score"])
        self.assertEqual(result["raw_score"], 80.0)


class CompleteSessionUsesHistoryTests(TestCase):
    """結束一場時，會從資料庫抓這場之前的場次當比較基準。"""

    def setUp(self):
        self.user = User.objects.create_user(username="grandma", password="pw123456")
        self.other = User.objects.create_user(username="other", password="pw123456")

    def _finished(self, user, raw_score, minutes_ago):
        session = create_game_session(user)
        GameSession.objects.filter(pk=session["session_id"]).update(
            status="finished",
            is_pretest=False,  # 模擬「已經玩過的正式場次」
            result={"raw_score": raw_score},
            finished_at=timezone.now() - timedelta(minutes=minutes_ago),
        )

    def _play(self, user):
        """玩一場：一次答對 8 題、速度分 85 → raw_score 81.5。"""
        session = create_game_session(user)
        session["state"].update(
            first_try_correct_count=8,
            speed_score=85.0,
            answer_count=20,
            total_reaction_time_ms=60000,
        )
        return complete_session(session)["result"]

    def test_compares_with_own_previous_sessions(self):
        for minutes_ago, raw_score in [(30, 60.0), (20, 70.0), (10, 80.0)]:
            self._finished(self.user, raw_score, minutes_ago)
        self._finished(self.other, 10.0, 5)  # 別人的分數不影響（自己已滿 3 場）

        result = self._play(self.user)

        self.assertEqual(result["z_score"], 1.15)
        self.assertEqual(result["standard_score"], 79)

    def test_new_user_borrows_population_history_after_familiarization(self):
        for minutes_ago, raw_score in [(30, 60.0), (20, 70.0), (10, 80.0)]:
            self._finished(self.other, raw_score, minutes_ago)
        self._play(self.user)  # 第一場是熟悉場

        result = self._play(self.user)

        self.assertEqual(result["z_score"], 1.15)

    def test_first_session_is_familiarization_even_with_population_history(self):
        for minutes_ago, raw_score in [(30, 60.0), (20, 70.0), (10, 80.0)]:
            self._finished(self.other, raw_score, minutes_ago)

        session = create_game_session(self.user)
        session["state"].update(total_correct=8, speed_score=76, answer_count=10)
        result = complete_session(session)["result"]

        self.assertTrue(session["is_pretest"])
        self.assertIsNone(result["z_score"])
        self.assertIsNone(result["standard_score"])

    def test_familiarization_session_is_not_history(self):
        self._play(self.user)  # 熟悉場
        for minutes_ago, raw_score in [(30, 60.0), (20, 70.0), (10, 80.0)]:
            self._finished(self.user, raw_score, minutes_ago)

        result = self._play(self.user)

        self.assertEqual(result["z_score"], 1.15)

    def test_first_session_in_system_is_null(self):
        result = self._play(self.user)

        self.assertIsNone(result["z_score"])
        self.assertIsNone(result["standard_score"])
