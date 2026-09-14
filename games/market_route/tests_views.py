"""
System test：菜市場找路（market_route）API 端到端流程。

用 APITestCase 打真實 URL，驗證回傳格式與規格書欄位一致。
目前 6 支 API 都回傳假資料（見 views.py 註解），這裡先確認：
    - status code 正確
    - 統一回傳格式 { success, data, error }
    - data 裡的欄位與型別符合規格書

執行：
    python manage.py test games.market_route.tests_views
"""

from rest_framework import status
from rest_framework.test import APITestCase

CONFIG_URL = "/api/games/market-route/config/"
START_URL = "/api/games/market-route/start/"
ROUND_URL = "/api/games/market-route/round/"
ROUND_ANSWER_URL = "/api/games/market-route/round/answer/"
FINISH_URL = "/api/games/market-route/finish/"


def result_url(session_id):
    return f"/api/games/market-route/result/{session_id}/"


class ConfigApiTests(APITestCase):
    """GET /api/games/market-route/config/"""

    def test_returns_expected_fields(self):
        response = self.client.get(CONFIG_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        data = response.data["data"]
        self.assertIn(data["current_stage"], ["basic", "intermediate", "advanced"])
        self.assertEqual(data["total_questions"], 20)
        self.assertIsInstance(data["stage_exposure_range"], dict)


class StartApiTests(APITestCase):
    """POST /api/games/market-route/start/"""

    def test_returns_session_id(self):
        response = self.client.post(START_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        data = response.data["data"]
        self.assertIn("session_id", data)
        self.assertIn("current_stage", data)


class RoundApiTests(APITestCase):
    """GET /api/games/market-route/round/"""

    def test_returns_question_content(self):
        response = self.client.get(ROUND_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        data = response.data["data"]
        self.assertIn(data["target_position"], ["center", "q1", "q2", "q3", "q4"])
        self.assertIsInstance(data["distractor_items"], list)
        self.assertIsInstance(data["exposure_time_ms"], int)


class RoundAnswerApiTests(APITestCase):
    """POST /api/games/market-route/round/answer/"""

    def _post_answer(self, **overrides):
        payload = {
            "session_id": 501,
            "question_number": 1,
            "attempt_number": 1,
            "answer_position": "q1",
            "is_timeout": False,
            "response_time_ms": 400,
            "paused_duration_ms": 0,
        }
        payload.update(overrides)
        return self.client.post(ROUND_ANSWER_URL, payload, format="json")

    def test_correct_answer_returns_next_question(self):
        response = self._post_answer(answer_position="q1")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertTrue(data["is_correct"])
        self.assertEqual(data["action"], "next_question")

    def test_wrong_answer_returns_retry(self):
        response = self._post_answer(answer_position="q3")

        data = response.data["data"]
        self.assertFalse(data["is_correct"])
        self.assertEqual(data["action"], "retry")

    def test_timeout_returns_next_question(self):
        response = self._post_answer(is_timeout=True, answer_position=None)

        data = response.data["data"]
        self.assertFalse(data["is_correct"])
        self.assertEqual(data["action"], "next_question")


class FinishApiTests(APITestCase):
    """POST /api/games/market-route/finish/"""

    def test_returns_session_summary(self):
        response = self.client.post(FINISH_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        data = response.data["data"]
        self.assertEqual(data["total_questions"], 20)
        self.assertIsInstance(data["accuracy"], float)
        self.assertIn("total_score", data)


class ResultApiTests(APITestCase):
    """GET /api/games/market-route/result/<session_id>/"""

    def test_returns_session_result(self):
        response = self.client.get(result_url(501))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        session_result = response.data["data"]["session_result"]
        self.assertIn("total_score", session_result)
        self.assertIn("final_stage", session_result)
