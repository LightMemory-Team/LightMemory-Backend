"""
遊戲作答端點的 session 擁有者檢查測試。

確認 fridge_check、market_shopping 的作答端點：
- 別人的 session → 403 FORBIDDEN，而且不會寫入任何作答紀錄
- 沒登入 → 403 FORBIDDEN
- 自己的 session → 正常作答
- session 不存在 → 仍然是 404 SESSION_NOT_FOUND（先找 session、再檢查擁有者）

執行：
    python manage.py test games.tests_session_owner
"""

from rest_framework.test import APIClient, APITestCase

from games import session_service
from games.fridge_check import services as fridge_services
from games.market_shopping import services as shopping_services
from users.models import User

FRIDGE_SESSIONS_URL = "/api/games/fridge-check/sessions/"
SHOPPING_SESSIONS_URL = "/api/games/market-shopping/sessions/"


class SessionOwnerTestCase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="testpass123")
        self.other = User.objects.create_user(username="other", password="testpass123")
        self.owner_client = APIClient()
        self.owner_client.force_authenticate(user=self.owner)
        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other)
        self.anonymous_client = APIClient()

    def assert_forbidden(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "FORBIDDEN")

    def step_count(self, game_type, session_id):
        return len(session_service.get_session(game_type, session_id)["step_records"])


class FridgeCheckOwnerTests(SessionOwnerTestCase):
    def setUp(self):
        super().setUp()
        data = self.owner_client.post(FRIDGE_SESSIONS_URL).data["data"]
        self.session_id = data["session_id"]
        session = fridge_services.get_session(self.session_id)
        self.answer_payload = {
            "answer": session["current_question"]["correct_answer"],
            "reaction_time_ms": 1000,
        }
        self.url = f"{FRIDGE_SESSIONS_URL}{self.session_id}/answers/"

    def test_owner_can_answer(self):
        response = self.owner_client.post(self.url, self.answer_payload, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])

    def test_other_user_gets_403_and_nothing_saved(self):
        response = self.other_client.post(self.url, self.answer_payload, format="json")

        self.assert_forbidden(response)
        self.assertEqual(self.step_count(fridge_services.GAME_TYPE, self.session_id), 0)

    def test_anonymous_gets_403_and_nothing_saved(self):
        response = self.anonymous_client.post(
            self.url, self.answer_payload, format="json"
        )

        self.assert_forbidden(response)
        self.assertEqual(self.step_count(fridge_services.GAME_TYPE, self.session_id), 0)

    def test_unknown_session_is_still_404(self):
        response = self.other_client.post(
            f"{FRIDGE_SESSIONS_URL}no-such-session/answers/",
            self.answer_payload,
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"]["code"], "SESSION_NOT_FOUND")


class MarketShoppingOwnerTests(SessionOwnerTestCase):
    def setUp(self):
        super().setUp()
        data = self.owner_client.post(SHOPPING_SESSIONS_URL).data["data"]
        self.session_id = data["session_id"]
        session = shopping_services.get_session(self.session_id)
        self.correct_codes = [
            item["food_code"] for item in session["current_question"]["target_items"]
        ]
        self.item_url = f"{SHOPPING_SESSIONS_URL}{self.session_id}/item-answers/"
        self.change_url = f"{SHOPPING_SESSIONS_URL}{self.session_id}/change-answers/"
        self.item_payload = {"selected_food_codes": self.correct_codes}
        self.change_payload = {"selected_amount": 10}

    def test_owner_can_answer_items(self):
        response = self.owner_client.post(
            self.item_url, self.item_payload, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])

    def test_other_user_cannot_answer_items(self):
        response = self.other_client.post(
            self.item_url, self.item_payload, format="json"
        )

        self.assert_forbidden(response)
        self.assertEqual(
            self.step_count(shopping_services.GAME_TYPE, self.session_id), 0
        )

    def test_anonymous_cannot_answer_items(self):
        response = self.anonymous_client.post(
            self.item_url, self.item_payload, format="json"
        )

        self.assert_forbidden(response)
        self.assertEqual(
            self.step_count(shopping_services.GAME_TYPE, self.session_id), 0
        )

    def test_owner_is_not_blocked_on_change_answers(self):
        response = self.owner_client.post(
            self.change_url, self.change_payload, format="json"
        )

        self.assertNotEqual(response.status_code, 403)

    def test_other_user_cannot_answer_change(self):
        response = self.other_client.post(
            self.change_url, self.change_payload, format="json"
        )

        self.assert_forbidden(response)
        self.assertEqual(
            self.step_count(shopping_services.GAME_TYPE, self.session_id), 0
        )

    def test_anonymous_cannot_answer_change(self):
        response = self.anonymous_client.post(
            self.change_url, self.change_payload, format="json"
        )

        self.assert_forbidden(response)

    def test_unknown_session_is_still_404(self):
        response = self.other_client.post(
            f"{SHOPPING_SESSIONS_URL}no-such-session/item-answers/",
            self.item_payload,
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"]["code"], "SESSION_NOT_FOUND")
