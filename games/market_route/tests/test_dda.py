"""
market_route 專屬 DDA 邏輯單元測試。
測試 RouteDDAStrategy 與 _apply_dda 狀態機行為。
"""

from django.test import TestCase

from games.market_route.views import (
    _apply_dda,
)


class MarketRouteDDATests(TestCase):
    def test_correct_answer_reduces_exposure_time(self):
        """正常答對時，曝光時間減少 EXPOSURE_STEP_DOWN (100ms)。"""
        session = {
            "state": {
                "current_stage": "basic",
                "correct_streak": 0,
                "fast_correct_streak": 0,
                "wrong_attempts": 0,
                "exposure_time_ms": 2000,
            }
        }
        # response_time_ms 1500 > 2000 * 0.5 (1000)，故非 fast
        updated, action = _apply_dda(
            session, is_correct=True, is_timeout=False, response_time_ms=1500
        )

        self.assertEqual(action, "next_question")
        self.assertEqual(updated["current_stage"], "basic")
        self.assertEqual(updated["correct_streak"], 1)
        self.assertEqual(updated["fast_correct_streak"], 0)
        self.assertEqual(updated["exposure_time_ms"], 1900)

    def test_exposure_time_does_not_drop_below_tight_bound(self):
        """曝光時間不會低於該階段的緊繃下限（basic 下限為 1500ms）。"""
        session = {
            "state": {
                "current_stage": "basic",
                "correct_streak": 0,
                "fast_correct_streak": 0,
                "wrong_attempts": 0,
                "exposure_time_ms": 1550,
            }
        }
        updated, _ = _apply_dda(
            session, is_correct=True, is_timeout=False, response_time_ms=1500
        )
        self.assertEqual(updated["exposure_time_ms"], 1500)

    def test_wrong_answer_increases_exposure_time(self):
        """答錯時曝光時間增加 EXPOSURE_STEP_UP (150ms)，上限為 loose (2000ms)。"""
        session = {
            "state": {
                "current_stage": "basic",
                "correct_streak": 2,
                "fast_correct_streak": 1,
                "wrong_attempts": 0,
                "exposure_time_ms": 1700,
            }
        }
        updated, action = _apply_dda(
            session, is_correct=False, is_timeout=False, response_time_ms=500
        )

        self.assertEqual(action, "retry")
        self.assertEqual(updated["wrong_attempts"], 1)
        self.assertEqual(updated["correct_streak"], 0)
        self.assertEqual(updated["fast_correct_streak"], 0)
        self.assertEqual(updated["exposure_time_ms"], 1850)

    def test_max_wrong_attempts_moves_to_next_question(self):
        """累積錯滿 3 次時，action 變為 next_question，wrong_attempts 歸零。"""
        session = {
            "state": {
                "current_stage": "basic",
                "correct_streak": 0,
                "fast_correct_streak": 0,
                "wrong_attempts": 2,
                "exposure_time_ms": 1800,
            }
        }
        updated, action = _apply_dda(
            session, is_correct=False, is_timeout=False, response_time_ms=500
        )

        self.assertEqual(action, "next_question")
        self.assertEqual(updated["wrong_attempts"], 0)

    def test_standard_promotion_after_5_streaks(self):
        """連對 5 題升至 intermediate，曝光時間重置為該階段 loose (1500ms)。"""
        session = {
            "state": {
                "current_stage": "basic",
                "correct_streak": 4,
                "fast_correct_streak": 0,
                "wrong_attempts": 0,
                "exposure_time_ms": 1600,
            }
        }
        updated, action = _apply_dda(
            session, is_correct=True, is_timeout=False, response_time_ms=1500
        )

        self.assertEqual(action, "promoted")
        self.assertEqual(updated["current_stage"], "intermediate")
        self.assertEqual(updated["correct_streak"], 0)
        self.assertEqual(updated["exposure_time_ms"], 1500)

    def test_fast_promotion_after_3_fast_streaks(self):
        """連續 3 題在 50% 曝光時間內答對，觸發快速升階。"""
        session = {
            "state": {
                "current_stage": "basic",
                "correct_streak": 2,
                "fast_correct_streak": 2,
                "wrong_attempts": 0,
                "exposure_time_ms": 1800,
            }
        }
        # 曝光時間 1800ms，反應時間 800ms <= 900ms (50%)
        updated, action = _apply_dda(
            session, is_correct=True, is_timeout=False, response_time_ms=800
        )

        self.assertEqual(action, "promoted")
        self.assertEqual(updated["current_stage"], "intermediate")
        self.assertEqual(updated["correct_streak"], 0)
        self.assertEqual(updated["fast_correct_streak"], 0)
        self.assertEqual(updated["exposure_time_ms"], 1500)

    def test_demotion_after_5_wrong_streaks(self):
        """連錯 5 次退一階，優先於 retry，曝光時間重置為新階段 loose (2000ms)。"""
        session = {
            "state": {
                "current_stage": "intermediate",
                "correct_streak": 0,
                "fast_correct_streak": 0,
                "wrong_attempts": 1,
                "wrong_streak": 4,
                "exposure_time_ms": 1300,
            }
        }
        updated, action = _apply_dda(
            session, is_correct=False, is_timeout=False, response_time_ms=500
        )

        self.assertEqual(action, "demoted")
        self.assertEqual(updated["current_stage"], "basic")
        self.assertEqual(updated["wrong_streak"], 0)
        self.assertEqual(updated["wrong_attempts"], 0)
        self.assertEqual(updated["exposure_time_ms"], 2000)

    def test_timeout_counts_toward_demotion(self):
        """超時也算進降階的連錯次數。"""
        session = {
            "state": {
                "current_stage": "advanced",
                "correct_streak": 0,
                "fast_correct_streak": 0,
                "wrong_attempts": 0,
                "wrong_streak": 4,
                "exposure_time_ms": 800,
            }
        }
        updated, action = _apply_dda(
            session, is_correct=False, is_timeout=True, response_time_ms=None
        )

        self.assertEqual(action, "demoted")
        self.assertEqual(updated["current_stage"], "intermediate")
        self.assertEqual(updated["exposure_time_ms"], 1500)

    def test_no_demotion_at_basic(self):
        """已經在 basic 時連錯達標也不降階，照常 retry。"""
        session = {
            "state": {
                "current_stage": "basic",
                "correct_streak": 0,
                "fast_correct_streak": 0,
                "wrong_attempts": 0,
                "wrong_streak": 4,
                "exposure_time_ms": 2000,
            }
        }
        updated, action = _apply_dda(
            session, is_correct=False, is_timeout=False, response_time_ms=500
        )

        self.assertEqual(action, "retry")
        self.assertEqual(updated["current_stage"], "basic")
        self.assertEqual(updated["wrong_streak"], 5)

    def test_correct_answer_resets_wrong_streak(self):
        """答對時連錯次數歸零，之前的錯誤不會累積到之後的降階判斷。"""
        session = {
            "state": {
                "current_stage": "intermediate",
                "correct_streak": 0,
                "fast_correct_streak": 0,
                "wrong_attempts": 0,
                "wrong_streak": 4,
                "exposure_time_ms": 1300,
            }
        }
        updated, action = _apply_dda(
            session, is_correct=True, is_timeout=False, response_time_ms=1000
        )

        self.assertEqual(action, "next_question")
        self.assertEqual(updated["wrong_streak"], 0)
