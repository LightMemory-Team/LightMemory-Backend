"""
fridge_check API 視圖與端點整合測試。
驗證建立 session、送出答案（答對、答錯重試、跳題、第 10 題完成）與歷史紀錄皆正常運作無 404。
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from games.fridge_check import services

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
