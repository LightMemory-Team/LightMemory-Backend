"""
market_sort 的 session 擁有者檢查測試。

session_id 是前端自己產生的（client_session_id），同一款遊戲裡全站唯一。
確認別的使用者拿到（或猜到）同一個 session_id 時：
- 回 403 FORBIDDEN
- 看不到對方的成績
- 也不能覆蓋對方還沒結束的 session

執行：
    python manage.py test games.market_sort.tests.test_owner
"""

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from games import session_service
from games.models import GameSession

from .test_views import SUBMIT_URL, build_questions

User = get_user_model()

GAME_TYPE = "market_sort"


class MarketSortSessionOwnerTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", password="Str0ng!Pass2026"
        )
        self.other = User.objects.create_user(
            username="other", password="Str0ng!Pass2026"
        )
        self.owner_client = APIClient()
        self.owner_client.force_authenticate(user=self.owner)
        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other)

    def _payload(self, session_id, is_complete=True):
        return {
            "session_id": session_id,
            "is_complete": is_complete,
            "questions": build_questions(),
        }

    def assert_forbidden(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.data["success"])
        self.assertIsNone(response.data["data"])
        self.assertEqual(response.data["error"]["code"], "FORBIDDEN")

    def test_other_user_cannot_read_finished_session_of_owner(self):
        payload = self._payload("shared-id")
        owner_response = self.owner_client.post(SUBMIT_URL, payload, format="json")
        self.assertEqual(owner_response.status_code, 201)

        response = self.other_client.post(SUBMIT_URL, payload, format="json")

        self.assert_forbidden(response)

    def test_other_user_cannot_overwrite_unfinished_session_of_owner(self):
        self.owner_client.post(
            SUBMIT_URL, self._payload("shared-id", False), format="json"
        )

        response = self.other_client.post(
            SUBMIT_URL, self._payload("shared-id"), format="json"
        )

        self.assert_forbidden(response)
        session = GameSession.objects.get(client_session_id="shared-id")
        self.assertEqual(session.user, self.owner)
        self.assertEqual(session.status, "in_progress")
        self.assertIsNone(session.result)

    def test_owner_can_still_resubmit_same_session_id(self):
        payload = self._payload("my-id")
        first = self.owner_client.post(SUBMIT_URL, payload, format="json")
        second = self.owner_client.post(SUBMIT_URL, payload, format="json")

        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.data, second.data)

    def test_other_user_can_use_a_different_session_id(self):
        self.owner_client.post(SUBMIT_URL, self._payload("owner-id"), format="json")

        response = self.other_client.post(
            SUBMIT_URL, self._payload("other-id"), format="json"
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(GameSession.objects.filter(user=self.other).count(), 1)


class GetOrCreateSessionOwnerTests(APITestCase):
    """session_service.get_or_create_session 自己也要擋下別人的 session。"""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", password="Str0ng!Pass2026"
        )
        self.other = User.objects.create_user(
            username="other", password="Str0ng!Pass2026"
        )

    def test_same_user_gets_existing_session(self):
        session_service.get_or_create_session(GAME_TYPE, "abc", user=self.owner)

        session, created = session_service.get_or_create_session(
            GAME_TYPE, "abc", user=self.owner
        )

        self.assertFalse(created)
        self.assertEqual(session["user_id"], self.owner.id)

    def test_other_user_raises_owner_mismatch(self):
        session_service.get_or_create_session(GAME_TYPE, "abc", user=self.owner)

        with self.assertRaises(session_service.SessionOwnerMismatch):
            session_service.get_or_create_session(GAME_TYPE, "abc", user=self.other)

    def test_other_user_identified_by_initial_state_also_raises(self):
        session_service.get_or_create_session(GAME_TYPE, "abc", user=self.owner)

        with self.assertRaises(session_service.SessionOwnerMismatch):
            session_service.get_or_create_session(
                GAME_TYPE, "abc", initial_state={"user_id": self.other.id}
            )
