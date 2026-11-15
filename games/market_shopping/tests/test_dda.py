"""
market_shopping 專屬 DDA 邏輯單元測試。
測試連對升階、答錯重置與 DDA 引擎整合。
"""

from django.test import TestCase
from django.contrib.auth import get_user_model

from games.market_shopping import services


User = get_user_model()


class MarketShoppingDDATests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="shopper_test", password="password123"
        )
        self.session = services.create_game_session(self.user)

    def test_initial_stage_is_easy(self):
        """初始難度階段為 easy，連對為 0。"""
        state = self.session["state"]
        self.assertEqual(state["current_stage"], "easy")
        self.assertEqual(state["correct_streak"], 0)

    def test_three_first_try_correct_promotes_to_medium(self):
        """連續 3 題完全答對（選菜與找零皆無錯誤），升至 medium。"""
        session = self.session

        for _ in range(2):
            session, upgraded = services.record_change_correct_and_apply_dda(session)
            self.assertFalse(upgraded)
            self.assertEqual(session["state"]["current_stage"], "easy")

        session, upgraded = services.record_change_correct_and_apply_dda(session)
        self.assertTrue(upgraded)
        self.assertEqual(session["state"]["current_stage"], "medium")
        self.assertEqual(session["state"]["correct_streak"], 0)

    def test_medium_to_hard_promotion(self):
        """medium 階段再連對 3 題升至 hard。"""
        session = self.session
        # 先升到 medium
        for _ in range(3):
            session, _ = services.record_change_correct_and_apply_dda(session)
        self.assertEqual(session["state"]["current_stage"], "medium")

        # 連對 3 題升到 hard
        for _ in range(2):
            session, upgraded = services.record_change_correct_and_apply_dda(session)
            self.assertFalse(upgraded)
        session, upgraded = services.record_change_correct_and_apply_dda(session)
        self.assertTrue(upgraded)
        self.assertEqual(session["state"]["current_stage"], "hard")
        self.assertEqual(session["state"]["correct_streak"], 0)

    def test_error_resets_streak(self):
        """若選菜或找零過程中有錯誤，該題完成時 streak 歸零且不升階。"""
        session = self.session
        # 第 1 題答對
        session, _ = services.record_change_correct_and_apply_dda(session)
        self.assertEqual(session["state"]["correct_streak"], 1)

        # 第 2 題選菜答錯一次
        session = services.record_item_wrong(session)
        self.assertEqual(session["state"]["correct_streak"], 0)
        self.assertTrue(session["state"]["current_question_had_error"])

        # 之後找零答對，但因為本題有錯，streak 維持 0 且不升階
        session, upgraded = services.record_change_correct_and_apply_dda(session)
        self.assertFalse(upgraded)
        self.assertEqual(session["state"]["correct_streak"], 0)
        self.assertEqual(session["state"]["current_stage"], "easy")
