"""
memory_recall 專屬 DDA 邏輯單元測試。
測試記憶回想遊戲的 DDA 升階、時間獎勵與種子物品抽取。
"""

from datetime import datetime, timedelta
from django.test import TestCase

from games.dda import apply_answer
from games.memory_recall.views import (
    DDA_CONFIG,
    DDA_STRATEGY,
    PROMOTE_BONUS_SECONDS,
    MemoryRecallDDAStrategy,
)


class MemoryRecallDDATests(TestCase):
    def test_correct_answer_increments_streak(self):
        """答對時連對 +1，未達 3 題不升階。"""
        state = {
            "current_stage": "basic",
            "correct_streak": 0,
            "expires_at": "2026-10-03T12:00:00+00:00",
        }
        updated, action = apply_answer(
            state, DDA_CONFIG, DDA_STRATEGY, is_correct=True
        )

        self.assertEqual(action, "no_promotion")
        self.assertEqual(updated["current_stage"], "basic")
        self.assertEqual(updated["correct_streak"], 1)

    def test_promotion_adds_bonus_seconds_and_new_seed(self):
        """連對 3 題升至 intermediate，時間延長 15 秒，並抽出新階段種子。"""
        initial_expires = "2026-10-03T12:00:00+00:00"
        state = {
            "current_stage": "basic",
            "correct_streak": 2,
            "expires_at": initial_expires,
        }
        updated, action = apply_answer(
            state, DDA_CONFIG, DDA_STRATEGY, is_correct=True
        )

        self.assertEqual(action, "promoted")
        self.assertEqual(updated["current_stage"], "intermediate")
        self.assertEqual(updated["correct_streak"], 0)
        self.assertEqual(updated["bonus_seconds_granted"], PROMOTE_BONUS_SECONDS)
        self.assertIsNotNone(updated["current_item"])
        self.assertIsNotNone(updated["seed_item"])

        # 驗證過期時間增加了 15 秒
        expected_dt = datetime.fromisoformat(initial_expires) + timedelta(
            seconds=PROMOTE_BONUS_SECONDS
        )
        self.assertEqual(
            datetime.fromisoformat(updated["expires_at"]), expected_dt
        )

    def test_intermediate_to_advanced_promotion(self):
        """intermediate 連對 3 題升至 advanced。"""
        initial_expires = "2026-10-03T12:00:00+00:00"
        state = {
            "current_stage": "intermediate",
            "correct_streak": 2,
            "expires_at": initial_expires,
        }
        updated, action = apply_answer(
            state, DDA_CONFIG, DDA_STRATEGY, is_correct=True
        )

        self.assertEqual(action, "promoted")
        self.assertEqual(updated["current_stage"], "advanced")
        self.assertEqual(updated["correct_streak"], 0)

    def test_wrong_answer_resets_streak(self):
        """答錯時連對次數歸零，不延長時間。"""
        initial_expires = "2026-10-03T12:00:00+00:00"
        state = {
            "current_stage": "intermediate",
            "correct_streak": 2,
            "expires_at": initial_expires,
        }
        updated, action = apply_answer(
            state, DDA_CONFIG, DDA_STRATEGY, is_correct=False
        )

        self.assertEqual(action, "no_promotion")
        self.assertEqual(updated["current_stage"], "intermediate")
        self.assertEqual(updated["correct_streak"], 0)
