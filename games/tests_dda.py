"""
共用 DDA（動態難度調整）核心引擎單元測試。
測試 games.dda 中的 DDAConfig, DDAStrategy, NoOpStrategy 與 apply_answer。
"""

from django.test import TestCase

from games.dda import (
    DEFAULT_STAGE_MULTIPLIER,
    DDAConfig,
    DDAStrategy,
    NoOpStrategy,
    apply_answer,
)


class CoreDDATests(TestCase):
    def setUp(self):
        self.config = DDAConfig(
            stage_order=["basic", "intermediate", "advanced"],
            promote_streak=3,
        )
        self.strategy = NoOpStrategy()

    def test_correct_answer_increments_streak(self):
        """答對時連對次數 +1，未達門檻不升階。"""
        state = {"current_stage": "basic", "correct_streak": 0}
        updated, action = apply_answer(
            state, self.config, self.strategy, is_correct=True
        )

        self.assertEqual(action, "no_promotion")
        self.assertEqual(updated["current_stage"], "basic")
        self.assertEqual(updated["correct_streak"], 1)
        # 向後相容欄位
        self.assertEqual(updated["difficulty"], "basic")
        self.assertEqual(updated["consecutive_correct"], 1)

    def test_promotion_when_streak_reaches_threshold(self):
        """連對達標（3 次）時順利升階，且連對計數歸零。"""
        state = {"current_stage": "basic", "correct_streak": 2}
        updated, action = apply_answer(
            state, self.config, self.strategy, is_correct=True
        )

        self.assertEqual(action, "promoted")
        self.assertEqual(updated["current_stage"], "intermediate")
        self.assertEqual(updated["correct_streak"], 0)
        self.assertEqual(updated["difficulty"], "intermediate")
        self.assertEqual(updated["consecutive_correct"], 0)

    def test_no_promotion_at_max_stage(self):
        """已達最高階段（advanced）時不再升階，連對計數繼續累積。"""
        state = {"current_stage": "advanced", "correct_streak": 2}
        updated, action = apply_answer(
            state, self.config, self.strategy, is_correct=True
        )

        self.assertEqual(action, "no_promotion")
        self.assertEqual(updated["current_stage"], "advanced")
        self.assertEqual(updated["correct_streak"], 3)

    def test_wrong_answer_resets_streak(self):
        """答錯時連對計數歸零，難度階段維持不變。"""
        state = {"current_stage": "intermediate", "correct_streak": 2}
        updated, action = apply_answer(
            state, self.config, self.strategy, is_correct=False
        )

        self.assertEqual(action, "no_promotion")
        self.assertEqual(updated["current_stage"], "intermediate")
        self.assertEqual(updated["correct_streak"], 0)
        self.assertEqual(updated["difficulty"], "intermediate")
        self.assertEqual(updated["consecutive_correct"], 0)

    def test_extra_promote_check(self):
        """自訂額外升階判定（例如快速作答）可提前觸發升階。"""
        state = {"current_stage": "basic", "correct_streak": 0}

        def fast_check(st, is_fast):
            return is_fast

        updated, action = apply_answer(
            state,
            self.config,
            self.strategy,
            is_correct=True,
            is_fast=True,
            extra_promote_check=fast_check,
        )

        self.assertEqual(action, "promoted")
        self.assertEqual(updated["current_stage"], "intermediate")
        self.assertEqual(updated["correct_streak"], 0)

    def test_custom_strategy_hooks(self):
        """測試自訂 Strategy 各生命週期 hook 的回傳值正確合併至 updated_fields。"""

        class CustomStrategy:
            def on_correct(self, state, config, *, is_fast=False):
                return {"custom_score": state.get("custom_score", 0) + 10}

            def on_wrong(self, state, config):
                return {"custom_wrong": state.get("custom_wrong", 0) + 1}

            def on_promote(self, state, config, new_stage):
                return {"promoted_to": new_stage}

        custom_strategy = CustomStrategy()

        # on_correct
        state = {"current_stage": "basic", "correct_streak": 0, "custom_score": 0}
        updated, action = apply_answer(
            state, self.config, custom_strategy, is_correct=True
        )
        self.assertEqual(updated["custom_score"], 10)

        # on_wrong
        state = {"current_stage": "basic", "correct_streak": 1, "custom_wrong": 0}
        updated, action = apply_answer(
            state, self.config, custom_strategy, is_correct=False
        )
        self.assertEqual(updated["custom_wrong"], 1)

        # on_promote
        state = {"current_stage": "basic", "correct_streak": 2}
        updated, action = apply_answer(
            state, self.config, custom_strategy, is_correct=True
        )
        self.assertEqual(action, "promoted")
        self.assertEqual(updated["promoted_to"], "intermediate")

    def test_backward_compatibility_reading_old_fields(self):
        """若 state 只有舊欄位名稱 difficulty 與 consecutive_correct，也能正常讀取。"""
        state = {"difficulty": "basic", "consecutive_correct": 2}
        updated, action = apply_answer(
            state, self.config, self.strategy, is_correct=True
        )

        self.assertEqual(action, "promoted")
        self.assertEqual(updated["current_stage"], "intermediate")
        self.assertEqual(updated["difficulty"], "intermediate")

    def test_default_stage_multiplier(self):
        """驗證三階段計分倍率預設常數。"""
        self.assertEqual(DEFAULT_STAGE_MULTIPLIER["basic"], 1.0)
        self.assertEqual(DEFAULT_STAGE_MULTIPLIER["intermediate"], 1.3)
        self.assertEqual(DEFAULT_STAGE_MULTIPLIER["advanced"], 1.6)
        self.assertEqual(DEFAULT_STAGE_MULTIPLIER["easy"], 1.0)
        self.assertEqual(DEFAULT_STAGE_MULTIPLIER["medium"], 1.3)
        self.assertEqual(DEFAULT_STAGE_MULTIPLIER["hard"], 1.6)
