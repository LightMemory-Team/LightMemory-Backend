"""
未登入存取遊戲 API 的測試。

確認「資料庫有使用者、但請求沒帶 JWT」時，開場 API 不會再借用第一位使用者的身分，
而是回 404 USER_NOT_FOUND，且不會建立任何 GameSession。

執行：
    python manage.py test games.tests_anonymous
"""

from django.test import TestCase
from rest_framework.test import APIClient

from users.models import User

from .models import GameSession

# 各遊戲「開始一場遊戲」的端點
START_ENDPOINTS = [
    "/api/games/fridge-check/sessions/",
    "/api/games/market-shopping/sessions/",
    "/api/games/market-route/start/",
    "/api/games/memory-recall/start/",
]


class AnonymousGameAccessTests(TestCase):
    def setUp(self):
        # 資料庫裡有使用者，舊版 fallback 會誤用他的身分
        User.objects.create_user(username="existing", password="testpass123")
        self.client = APIClient()

    def test_anonymous_cannot_start_game(self):
        for url in START_ENDPOINTS:
            with self.subTest(url=url):
                response = self.client.post(url, {}, format="json")

                self.assertEqual(response.status_code, 404)
                self.assertFalse(response.data["success"])
                self.assertEqual(response.data["error"]["code"], "USER_NOT_FOUND")

    def test_anonymous_start_creates_no_session(self):
        for url in START_ENDPOINTS:
            self.client.post(url, {}, format="json")

        self.assertEqual(GameSession.objects.count(), 0)

    def test_logged_in_user_can_still_start_game(self):
        user = User.objects.create_user(username="player", password="testpass123")
        self.client.force_authenticate(user=user)

        response = self.client.post("/api/games/fridge-check/sessions/")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(GameSession.objects.filter(user=user).count(), 1)
