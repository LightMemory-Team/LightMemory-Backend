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


def _history(*raw_scores):
    """過去場次的 result 清單，只需要 raw_score。"""
    return [{"raw_score": raw_score} for raw_score in raw_scores]


# 平均 70、樣本標準差 10
PERSONAL_HISTORY = _history(60.0, 70.0, 80.0)


class FridgeCheckZScoreTests(SimpleTestCase):
    def _z(self, raw_score, personal=PERSONAL_HISTORY, population=()):
        return calculate_visual_spatial_z_score(raw_score, personal, list(population))

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
        # 73.5 分 -> Z = 0.35
        # standard_score = round(50 + 25 * 0.35) = round(58.75) = 59
        res = self._z(73.5)
        self.assertEqual(res["z_score"], 0.35)
        self.assertEqual(res["standard_score"], 59)

    def test_cold_start_uses_population(self):
        """自己不滿 3 場時，改跟全體使用者的歷史比。"""
        res = self._z(80.0, personal=_history(95.0), population=PERSONAL_HISTORY)
        self.assertEqual(res["z_score"], 1.0)

    def test_not_enough_history_is_none(self):
        """自己和全體都不滿 3 場：資料不足，不給假分數。"""
        res = self._z(80.0, personal=[], population=_history(70.0))
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
        result = calculate_final_result(self.FAKE_SESSION, PERSONAL_HISTORY, [])

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

        # 2. 驗證 Z-score 與 standard_score（raw_score 跟自己的歷史比）
        # Z = (78.8 - 70) / 10 = 0.88
        self.assertEqual(result["z_score"], 0.88)
        # standard_score = round(50 + 25 * 0.88) = 72
        self.assertEqual(result["standard_score"], 72)

        # 3. 驗證基本欄位存在
        self.assertEqual(result["total_correct"], 8)
        self.assertEqual(result["total_questions"], TOTAL_QUESTIONS)
        self.assertEqual(result["final_difficulty"], "hard")
        self.assertEqual(result["average_reaction_time_ms"], 2450)
        self.assertIn("completed_at", result)

    def test_no_history_gives_null_scores(self):
        """歷史不足時 z_score、standard_score 為 None，其他欄位照常計算。"""
        result = calculate_final_result(self.FAKE_SESSION, [], [])

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
    return calculate_final_result(session, [], [])


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

    def _finished(self, user, raw_score, minutes_ago):
        session = create_game_session(user)
        GameSession.objects.filter(pk=session["session_id"]).update(
            status="finished",
            is_pretest=False,  # 模擬「已經玩過的正式場次」
            result={"raw_score": raw_score},
            finished_at=timezone.now() - timedelta(minutes=minutes_ago),
        )

    def _play(self, user):
        """玩一場：8 題答對、速度分 76 → raw_score 78.8。"""
        session = create_game_session(user)
        session["state"].update(total_correct=8, speed_score=76, answer_count=10)
        return complete_session(session)["result"]

    def test_compares_with_own_previous_sessions(self):
        for minutes_ago, raw_score in [(30, 60.0), (20, 70.0), (10, 80.0)]:
            self._finished(self.user, raw_score, minutes_ago)
        self._finished(self.other, 10.0, 5)  # 別人的分數不影響（自己已滿 3 場）

        result = self._play(self.user)

        self.assertEqual(result["z_score"], 0.88)
        self.assertEqual(result["standard_score"], 72)

    def test_new_user_borrows_population_history_after_familiarization(self):
        for minutes_ago, raw_score in [(30, 60.0), (20, 70.0), (10, 80.0)]:
            self._finished(self.other, raw_score, minutes_ago)
        self._play(self.user)  # 第一場是熟悉場

        result = self._play(self.user)

        self.assertEqual(result["z_score"], 0.88)

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

        self.assertEqual(result["z_score"], 0.88)

    def test_first_session_in_system_is_null(self):
        result = self._play(self.user)

        self.assertIsNone(result["z_score"])
        self.assertIsNone(result["standard_score"])
