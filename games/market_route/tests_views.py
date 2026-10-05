"""
System test：菜市場找路（market_route）API 端到端流程。

用 APITestCase 打真實 URL，走完整場流程（start → round → round/answer →
finish → result），驗證回傳格式與規格書欄位一致：
    - status code 正確
    - 統一回傳格式 { success, data, error }
    - data 裡的欄位與型別符合規格書

執行：
    python manage.py test games.market_route.tests_views
"""

from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User

from .views import POSITIONS

CONFIG_URL = "/api/games/market-route/config/"
START_URL = "/api/games/market-route/start/"
ROUND_URL = "/api/games/market-route/round/"
ROUND_ANSWER_URL = "/api/games/market-route/round/answer/"
FINISH_URL = "/api/games/market-route/finish/"

ALL_POSITIONS = ["center", *POSITIONS]


def result_url(session_id):
    return f"/api/games/market-route/result/{session_id}/"


class MarketRouteTestCase(APITestCase):
    """market_route 測試共用的準備動作。

    session 存在資料庫（GameSession），APITestCase 每個測試結束會自動
    rollback，不需要手動清資料，測試之間不會互相污染。
    """

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="testpass123")
        self.client.force_authenticate(user=self.user)

    def _start(self):
        """開一場新遊戲，回傳 session_id。"""
        return self.client.post(START_URL).data["data"]["session_id"]

    def _get_round(self, session_id):
        return self.client.get(ROUND_URL, {"session_id": session_id}).data["data"]

    def _answer(self, session_id, answer_position, is_timeout=False):
        return self.client.post(
            ROUND_ANSWER_URL,
            {
                "session_id": session_id,
                "attempt_number": 1,
                "answer_position": answer_position,
                "is_timeout": is_timeout,
                "response_time_ms": 400,
                "paused_duration_ms": 0,
            },
            format="json",
        )

    def _finish(self, session_id):
        return self.client.post(FINISH_URL, {"session_id": session_id}, format="json")


class ConfigApiTests(MarketRouteTestCase):
    """GET /api/games/market-route/config/"""

    def test_returns_expected_fields(self):
        response = self.client.get(CONFIG_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        data = response.data["data"]
        self.assertIn(data["current_stage"], ["basic", "intermediate", "advanced"])
        self.assertEqual(data["total_questions"], 20)
        self.assertIsInstance(data["stage_exposure_range"], dict)


class StartApiTests(MarketRouteTestCase):
    """POST /api/games/market-route/start/"""

    def test_returns_session_id(self):
        response = self.client.post(START_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        data = response.data["data"]
        self.assertIn("session_id", data)
        self.assertEqual(data["current_stage"], "basic")

    def test_without_any_user_returns_404(self):
        self.client.force_authenticate(user=None)
        User.objects.all().delete()

        response = self.client.post(START_URL)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "USER_NOT_FOUND")


class RoundApiTests(MarketRouteTestCase):
    """GET /api/games/market-route/round/"""

    def test_returns_question_content(self):
        session_id = self._start()

        response = self.client.get(ROUND_URL, {"session_id": session_id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        data = response.data["data"]
        self.assertIn(data["target_position"], ALL_POSITIONS)
        self.assertIsInstance(data["distractor_items"], list)
        self.assertIsInstance(data["exposure_time_ms"], int)


class RoundAnswerApiTests(MarketRouteTestCase):
    """POST /api/games/market-route/round/answer/"""

    def test_correct_answer_returns_next_question(self):
        session_id = self._start()
        question = self._get_round(session_id)

        response = self._answer(session_id, question["target_position"])

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertTrue(data["is_correct"])
        self.assertEqual(data["action"], "next_question")

    def test_wrong_answer_returns_retry(self):
        session_id = self._start()
        question = self._get_round(session_id)
        wrong_position = next(
            p for p in ALL_POSITIONS if p != question["target_position"]
        )

        response = self._answer(session_id, wrong_position)

        data = response.data["data"]
        self.assertFalse(data["is_correct"])
        self.assertEqual(data["action"], "retry")

    def test_timeout_returns_next_question(self):
        session_id = self._start()
        self._get_round(session_id)

        response = self._answer(session_id, None, is_timeout=True)

        data = response.data["data"]
        self.assertFalse(data["is_correct"])
        self.assertEqual(data["action"], "next_question")
        self.assertEqual(data["wrong_attempts"], 0)

    def test_timeout_does_not_count_as_wrong_attempt(self):
        """答錯 2 次後超時換題，下一題答錯 1 次應該是 retry，不會被累計換題。"""
        session_id = self._start()
        question = self._get_round(session_id)
        wrong_position = next(
            p for p in ALL_POSITIONS if p != question["target_position"]
        )
        self._answer(session_id, wrong_position)
        self._answer(session_id, wrong_position)
        self._answer(session_id, None, is_timeout=True)

        next_question = self._get_round(session_id)
        wrong_position = next(
            p for p in ALL_POSITIONS if p != next_question["target_position"]
        )
        response = self._answer(session_id, wrong_position)

        data = response.data["data"]
        self.assertEqual(data["action"], "retry")
        self.assertEqual(data["wrong_attempts"], 1)


class FinishApiTests(MarketRouteTestCase):
    """POST /api/games/market-route/finish/"""

    def test_returns_session_summary(self):
        session_id = self._start()
        question = self._get_round(session_id)
        self._answer(session_id, question["target_position"])

        response = self._finish(session_id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        data = response.data["data"]
        self.assertEqual(data["total_questions"], 20)
        self.assertEqual(data["answered_count"], 1)
        self.assertEqual(data["correct_count"], 1)
        self.assertEqual(data["timeout_count"], 0)
        self.assertIsInstance(data["accuracy"], float)
        self.assertIn("total_score", data)


class ResultApiTests(MarketRouteTestCase):
    """GET /api/games/market-route/result/<session_id>/"""

    def test_returns_session_result(self):
        session_id = self._start()
        question = self._get_round(session_id)
        self._answer(session_id, question["target_position"])
        self._finish(session_id)

        response = self.client.get(result_url(session_id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        session_result = response.data["data"]["session_result"]
        self.assertIn("total_score", session_result)
        self.assertIn("final_stage", session_result)

    def test_result_before_finished_returns_400(self):
        session_id = self._start()

        response = self.client.get(result_url(session_id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "SESSION_NOT_FINISHED")
