"""
fridge_check API 視圖與端點整合測試。
驗證建立 session、送出答案（答對、答錯重試、跳題、第 10 題完成）與歷史紀錄皆正常運作無 404。
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from games import session_service
from games.fridge_check import services
from games.fridge_check.constants import TOTAL_QUESTIONS

User = get_user_model()


class FridgeCheckApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="fridge_view_user", password="password123"
        )
        self.client.force_authenticate(user=self.user)

    def test_create_session_endpoint(self):
        """測試 POST /api/games/fridge-check/sessions/"""
        response = self.client.post("/api/games/fridge-check/sessions/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertIn("session_id", response.data["data"])
        self.assertIn("question", response.data["data"])

    def test_first_session_is_familiarization(self):
        """第一次玩這款遊戲，建立場次的回應標示為熟悉場（不算分）"""
        response = self.client.post("/api/games/fridge-check/sessions/")
        self.assertTrue(response.data["data"]["is_pretest"])

    def test_create_session_alias_endpoint(self):
        """測試單數別名 POST /api/games/fridge-check/session/"""
        response = self.client.post("/api/games/fridge-check/session/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])

    def test_submit_answer_correct(self):
        """測試提交正確答案"""
        session_res = self.client.post("/api/games/fridge-check/sessions/")
        session_id = session_res.data["data"]["session_id"]

        session = services.get_session(session_id)
        correct_answer = session["current_question"]["correct_answer"]

        answer_payload = {
            "answer": correct_answer,
            "reaction_time_ms": 1500,
        }
        response = self.client.post(
            f"/api/games/fridge-check/sessions/{session_id}/answers/",
            data=answer_payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertTrue(response.data["data"]["is_correct"])

        # 驗證 save_step 有正確記錄該題作答
        updated_session = services.get_session(session_id)
        self.assertEqual(len(updated_session["step_records"]), 1)
        self.assertTrue(updated_session["step_records"][0]["is_correct"])
        self.assertEqual(updated_session["step_records"][0]["response_time_ms"], 1500)

    def test_submit_answer_wrong_retry(self):
        """測試提交錯誤答案，允許 retry"""
        session_res = self.client.post("/api/games/fridge-check/sessions/")
        session_id = session_res.data["data"]["session_id"]

        answer_payload = {
            "answer": {"food_code": "non_existent_food", "position": [99, 99]},
            "reaction_time_ms": 2000,
        }
        response = self.client.post(
            f"/api/games/fridge-check/sessions/{session_id}/answers/",
            data=answer_payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertFalse(response.data["data"]["is_correct"])
        self.assertTrue(response.data["data"]["retry"])
        self.assertEqual(response.data["data"]["wrong_count"], 1)

    def test_get_history_endpoint(self):
        """測試 GET /api/games/fridge-check/history/"""
        response = self.client.get("/api/games/fridge-check/history/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIn("history", response.data["data"])


class FridgeCheckRewardsTests(TestCase):
    """第 10 題結束（is_completed 為 true）的回應才帶 rewards。"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="fridge_rewards_user", password="password123"
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/api/games/fridge-check/sessions/")
        self.session_id = response.data["data"]["session_id"]
        self.url = f"/api/games/fridge-check/sessions/{self.session_id}/answers/"

    def _answer(self, answer):
        return self.client.post(
            self.url, {"answer": answer, "reaction_time_ms": 1500}, format="json"
        )

    def test_full_game_returns_rewards_only_on_last_question(self):
        for _ in range(TOTAL_QUESTIONS):
            session = services.get_session(self.session_id)
            data = self._answer(session["current_question"]["correct_answer"]).data[
                "data"
            ]
            if data["is_completed"]:
                break
            # 還沒結束的題目沒有 rewards
            self.assertNotIn("rewards", data)

        self.assertTrue(data["is_completed"])
        self.assertGreaterEqual(data["rewards"]["points_earned"], 10)

    def test_skipping_last_question_returns_rewards(self):
        session_service.update_session(
            services.GAME_TYPE, self.session_id, question_number=TOTAL_QUESTIONS
        )
        wrong = {"food_code": "non_existent_food", "position": [99, 99]}

        for _ in range(3):
            response = self._answer(wrong)

        data = response.data["data"]
        self.assertTrue(data["is_completed"])
        self.assertTrue(data["question_skipped"])
        self.assertGreaterEqual(data["rewards"]["points_earned"], 10)
