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

import uuid

from rest_framework import status
from rest_framework.test import APITestCase

from games.models import GameSession
from users.models import User

from .views import DEMOTE_STREAK, FAST_PROMOTE_STREAK, POSITIONS

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

    def _wrong_position(self, question):
        return next(p for p in ALL_POSITIONS if p != question["target_position"])

    def _promote_to_intermediate(self, session_id):
        """連續快速答對 FAST_PROMOTE_STREAK 題升到中階，回傳最後一次作答的回應。

        _answer 的 response_time_ms 是 400，低於曝光時間的 50%，每題都算快速答對。
        """
        for _ in range(FAST_PROMOTE_STREAK):
            question = self._get_round(session_id)
            response = self._answer(session_id, question["target_position"])
        return response


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

    def test_promotion_returns_promoted_and_moves_to_next_question(self):
        session_id = self._start()

        response = self._promote_to_intermediate(session_id)

        data = response.data["data"]
        self.assertEqual(data["action"], "promoted")
        self.assertEqual(data["current_stage"], "intermediate")
        next_question = self._get_round(session_id)
        self.assertEqual(next_question["question_number"], FAST_PROMOTE_STREAK + 1)

    def test_wrong_streak_returns_demoted_and_resets_exposure(self):
        """升到中階後連錯 DEMOTE_STREAK 次（跨題累計）退回初階。"""
        session_id = self._start()
        self._promote_to_intermediate(session_id)

        actions = []
        question = self._get_round(session_id)
        for _ in range(DEMOTE_STREAK):
            response = self._answer(session_id, self._wrong_position(question))
            action = response.data["data"]["action"]
            actions.append(action)
            if action == "next_question":
                question = self._get_round(session_id)

        # 同一題錯 3 次換題，換題後再錯 2 次湊滿 5 次，降階優先於 retry
        self.assertEqual(
            actions, ["retry", "retry", "next_question", "retry", "demoted"]
        )
        self.assertEqual(response.data["data"]["current_stage"], "basic")
        next_question = self._get_round(session_id)
        self.assertEqual(next_question["stage"], "basic")
        self.assertEqual(next_question["exposure_time_ms"], 2000)


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


class ErrorHandlingTests(MarketRouteTestCase):
    """各支 API 的錯誤檢查：找不到、不是自己的、已結束、還沒出題。"""

    def test_round_with_unknown_session_returns_404(self):
        response = self.client.get(ROUND_URL, {"session_id": str(uuid.uuid4())})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "SESSION_NOT_FOUND")

    def test_other_user_accessing_session_returns_403(self):
        session_id = self._start()
        question = self._get_round(session_id)
        other_user = User.objects.create_user(
            username="other_tester", password="testpass123"
        )
        self.client.force_authenticate(user=other_user)

        responses = [
            self.client.get(ROUND_URL, {"session_id": session_id}),
            self._answer(session_id, question["target_position"]),
            self._finish(session_id),
            self.client.get(result_url(session_id)),
        ]

        for response in responses:
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(response.data["error"]["code"], "FORBIDDEN")

    def test_round_and_answer_after_finished_return_409(self):
        session_id = self._start()
        question = self._get_round(session_id)
        self._finish(session_id)

        responses = [
            self.client.get(ROUND_URL, {"session_id": session_id}),
            self._answer(session_id, question["target_position"]),
        ]

        for response in responses:
            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
            self.assertEqual(response.data["error"]["code"], "SESSION_ALREADY_FINISHED")

    def test_answer_before_round_returns_400(self):
        session_id = self._start()

        response = self._answer(session_id, "center")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "ROUND_NOT_STARTED")

    def test_answer_after_moving_on_requires_new_round(self):
        """換題後沒有呼叫 round/ 就再作答，不能重複作答已經結束的題目。"""
        session_id = self._start()
        question = self._get_round(session_id)
        self._answer(session_id, question["target_position"])

        response = self._answer(session_id, question["target_position"])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "ROUND_NOT_STARTED")

    def test_retry_keeps_same_question_answerable(self):
        """retry 停在同一題，不用重新呼叫 round/ 就能再作答。"""
        session_id = self._start()
        question = self._get_round(session_id)
        self._answer(session_id, self._wrong_position(question))

        response = self._answer(session_id, question["target_position"])

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["data"]["is_correct"])

    def test_calling_finish_twice_returns_same_result_without_recalculating(self):
        session_id = self._start()
        question = self._get_round(session_id)
        self._answer(session_id, question["target_position"])

        first = self._finish(session_id).data["data"]
        finished_at = GameSession.objects.get(id=session_id).finished_at
        second = self._finish(session_id)

        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["data"], first)
        self.assertEqual(
            GameSession.objects.get(id=session_id).finished_at, finished_at
        )


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
