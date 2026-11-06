"""GET /api/home/greet/ 首頁問候語。

用 mock 假裝 AI 的回傳，不會真的呼叫 OpenAI。
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from ai_service.greeting import FALLBACK_GREETINGS

CLIENT_PATH = "ai_service.greeting._client"


def fake_ai_reply(text):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


class GreetApiTests(APITestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @patch(CLIENT_PATH)
    def test_returns_ai_greeting(self, mock_client):
        mock_client.return_value.chat.completions.create.return_value = fake_ai_reply(
            "陽光正好，出門走走。"
        )

        response = self.client.get("/api/home/greet/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"daily_tip": "陽光正好，出門走走。"})

    @patch(CLIENT_PATH)
    def test_ai_failure_returns_fallback_not_error(self, mock_client):
        mock_client.return_value.chat.completions.create.side_effect = RuntimeError(
            "boom"
        )

        with self.assertLogs("ai_service.greeting", level="WARNING"):
            response = self.client.get("/api/home/greet/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(response.json()["daily_tip"], FALLBACK_GREETINGS)
