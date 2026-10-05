"""
System test：市場買菜（market_shopping）API 端到端流程。

用 APITestCase 打真實 URL，走完整場流程（建立 session → 選菜 → 找零 →
下一題 … → 完成 → history），確認 session_id（UUID 字串）能正確對上網址，
以及答對、答錯、完成時的回傳格式。

執行：
    python manage.py test games.market_shopping.tests_views
"""

import uuid

from rest_framework import status
from rest_framework.test import APITestCase

from games import session_service
from users.models import User

from .services import GAME_TYPE, TOTAL_QUESTIONS

SESSIONS_URL = "/api/games/market-shopping/sessions/"
HISTORY_URL = "/api/games/market-shopping/history/"


def item_answer_url(session_id):
    return f"{SESSIONS_URL}{session_id}/item-answers/"


def change_answer_url(session_id):
    return f"{SESSIONS_URL}{session_id}/change-answers/"


class MarketShoppingTestCase(APITestCase):
    """market_shopping 測試共用的準備動作。

    session 存在資料庫（GameSession），APITestCase 每個測試結束會自動
    rollback，不需要手動清資料，測試之間不會互相污染。
    """

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="testpass123")
        self.client.force_authenticate(user=self.user)

    def _create(self):
        """建立一場新遊戲，回傳第一題的 data（含 session_id）。"""
        return self.client.post(SESSIONS_URL).data["data"]

    def _answer_items(self, session_id, food_codes):
        return self.client.post(
            item_answer_url(session_id),
            {"selected_food_codes": food_codes},
            format="json",
        )

    def _answer_change(self, session_id, amount):
        return self.client.post(
            change_answer_url(session_id), {"selected_amount": amount}, format="json"
        )

    def _correct_change(self, session_id):
        """找零的正解只留在後端，測試直接讀 state。"""
        return session_service.get_session(GAME_TYPE, session_id)["state"][
            "correct_change"
        ]

    def _play_question_correctly(self, session_id, question):
        """選菜、找零都答對，回傳找零的回應 data。"""
        codes = [item["food_code"] for item in question["shopping_list"]]
        self._answer_items(session_id, codes)
        response = self._answer_change(session_id, self._correct_change(session_id))
        return response.data["data"]


class CreateSessionApiTests(MarketShoppingTestCase):
    """POST /api/games/market-shopping/sessions/"""

    def test_returns_first_question_with_uuid_session_id(self):
        response = self.client.post(SESSIONS_URL)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        data = response.data["data"]
        uuid.UUID(data["session_id"])  # 不是合法 UUID 會直接拋錯
        self.assertEqual(data["current_question"], 1)
        self.assertEqual(data["total_questions"], TOTAL_QUESTIONS)
        self.assertTrue(data["shopping_list"])


class ItemAnswerApiTests(MarketShoppingTestCase):
    """POST /api/games/market-shopping/sessions/<session_id>/item-answers/"""

    def test_correct_items_return_change_options(self):
        question = self._create()
        codes = [item["food_code"] for item in question["shopping_list"]]

        response = self._answer_items(question["session_id"], codes)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertTrue(data["is_correct"])
        self.assertIn(
            self._correct_change(question["session_id"]), data["change_options"]
        )

    def test_wrong_items_return_retry(self):
        question = self._create()

        response = self._answer_items(question["session_id"], ["not_a_food"])

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertFalse(data["is_correct"])
        self.assertTrue(data["retry"])
        self.assertEqual(data["wrong_count"], 1)

    def test_unknown_session_returns_404(self):
        response = self._answer_items(str(uuid.uuid4()), ["tomato"])

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "SESSION_NOT_FOUND")


class ChangeAnswerApiTests(MarketShoppingTestCase):
    """POST /api/games/market-shopping/sessions/<session_id>/change-answers/"""

    def test_correct_change_moves_to_next_question(self):
        question = self._create()

        data = self._play_question_correctly(question["session_id"], question)

        self.assertTrue(data["is_correct"])
        self.assertFalse(data["is_completed"])
        self.assertEqual(data["next_question"]["current_question"], 2)


class FullGameFlowTests(MarketShoppingTestCase):
    """完整玩完一場：每題都答對，最後完成並出現在 history。"""

    def test_full_game_finishes_and_appears_in_history(self):
        question = self._create()
        session_id = question["session_id"]

        for _ in range(TOTAL_QUESTIONS):
            data = self._play_question_correctly(session_id, question)
            if data["is_completed"]:
                break
            question = data["next_question"]

        self.assertTrue(data["is_completed"])
        self.assertEqual(data["total_correct"], TOTAL_QUESTIONS)
        session = session_service.get_session(GAME_TYPE, session_id)
        self.assertEqual(session["status"], "finished")

        response = self.client.get(HISTORY_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)
