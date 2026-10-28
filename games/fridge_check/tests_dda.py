"""
fridge_check 專屬 DDA 邏輯單元測試。
測試冰箱檢查遊戲的難度升降與 DDA 引擎狀態更新。
"""

from django.test import TestCase
from django.contrib.auth import get_user_model

from games.fridge_check import services
from games.fridge_check.constants import (
    DIFFICULTY_EASY,
    DIFFICULTY_MEDIUM,
    DIFFICULTY_HARD,
)

User = get_user_model()


class FridgeCheckDDATests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="fridge_tester", password="password123"
        )
        self.session = services.create_game_session(self.user)

    def test_initial_difficulty_is_easy(self):
        """初始難度為 easy，連對題數為 0。"""
        state = self.session["state"]
        self.assertEqual(state["current_stage"], DIFFICULTY_EASY)
        self.assertEqual(state["correct_streak"], 0)

    def test_three_consecutive_correct_promotes_to_medium(self):
        """連續答對 3 題升至 medium，並回傳 difficulty_changed=True。"""
        session = self.session

        for _ in range(2):
            session, diff_res = services.record_correct_answer(session, reaction_time_ms=2000)
            self.assertFalse(diff_res["difficulty_changed"])
            self.assertEqual(session["state"]["current_stage"], DIFFICULTY_EASY)

        session, diff_res = services.record_correct_answer(session, reaction_time_ms=2000)
        self.assertTrue(diff_res["difficulty_changed"])
        self.assertEqual(diff_res["previous_difficulty"], DIFFICULTY_EASY)
        self.assertEqual(session["state"]["current_stage"], DIFFICULTY_MEDIUM)
        self.assertEqual(session["state"]["correct_streak"], 0)

    def test_medium_to_hard_promotion(self):
        """medium 難度再連對 3 題升至 hard。"""
        session = self.session
        # 先升到 medium
        for _ in range(3):
            session, _ = services.record_correct_answer(session, reaction_time_ms=2000)
        self.assertEqual(session["state"]["current_stage"], DIFFICULTY_MEDIUM)

        # 連對 3 題升到 hard
        for _ in range(2):
            session, diff_res = services.record_correct_answer(session, reaction_time_ms=2000)
            self.assertFalse(diff_res["difficulty_changed"])

        session, diff_res = services.record_correct_answer(session, reaction_time_ms=2000)
        self.assertTrue(diff_res["difficulty_changed"])
        self.assertEqual(diff_res["previous_difficulty"], DIFFICULTY_MEDIUM)
        self.assertEqual(session["state"]["current_stage"], DIFFICULTY_HARD)
        self.assertEqual(session["state"]["correct_streak"], 0)

    def test_wrong_answer_resets_streak(self):
        """答錯時連對次數歸零，current_wrong_count + 1。"""
        session = self.session
        session, _ = services.record_correct_answer(session, reaction_time_ms=2000)
        self.assertEqual(session["state"]["correct_streak"], 1)

        session = services.record_wrong_answer(session, reaction_time_ms=3000)
        self.assertEqual(session["state"]["correct_streak"], 0)
        self.assertEqual(session["state"]["current_wrong_count"], 1)
        self.assertTrue(session["state"]["current_question_had_error"])
