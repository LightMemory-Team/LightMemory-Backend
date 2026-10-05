"""
market_route 專屬 DDA 邏輯單元測試。
測試 RouteDDAStrategy 與 _apply_dda 狀態機行為。
"""

from django.test import TestCase

from games.dda import apply_answer
from games.market_route.views import (
    DDA_CONFIG,
    DDA_STRATEGY,
    EXPOSURE_STEP_DOWN,
    EXPOSURE_STEP_UP,
    STAGE_EXPOSURE_RANGE,
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

        self.assertEqual(action, "next_question")
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

        self.assertEqual(action, "next_question")
        self.assertEqual(updated["current_stage"], "intermediate")
        self.assertEqual(updated["correct_streak"], 0)
        self.assertEqual(updated["fast_correct_streak"], 0)
        self.assertEqual(updated["exposure_time_ms"], 1500)
