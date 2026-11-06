"""greeting.py 的測試。

用 unittest.mock.patch 假裝 OpenAI 的回傳，測試不會真的呼叫 AI、不花錢。
每個測試前都會清空快取，避免上一個測試的問候語影響下一個。
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from .greeting import (
    FALLBACK_GREETINGS,
    build_fallback_greeting,
    generate_greeting,
    get_daily_greeting,
)

CLIENT_PATH = "ai_service.greeting._client"
TODAY = date(2026, 11, 2)


def fake_ai_reply(text):
    """組出跟 OpenAI chat.completions.create 回傳一樣形狀的物件。"""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


class BuildFallbackGreetingTests(SimpleTestCase):
    def test_same_day_same_greeting(self):
        self.assertEqual(build_fallback_greeting(TODAY), build_fallback_greeting(TODAY))

    def test_rotates_through_all_greetings(self):
        days = [date(2026, 11, day) for day in (2, 3, 4)]
        greetings = {build_fallback_greeting(day) for day in days}
        self.assertEqual(greetings, set(FALLBACK_GREETINGS))


class GenerateGreetingTests(SimpleTestCase):
    @patch(CLIENT_PATH)
    def test_ai_greeting_used(self, mock_client):
        mock_client.return_value.chat.completions.create.return_value = fake_ai_reply(
            "今天天氣真好呀。"
        )

        greeting, from_ai = generate_greeting(TODAY)

        self.assertEqual(greeting, "今天天氣真好呀。")
        self.assertTrue(from_ai)

    @patch(CLIENT_PATH)
    def test_reply_is_stripped(self, mock_client):
        mock_client.return_value.chat.completions.create.return_value = fake_ai_reply(
            "  早安，喝杯水吧。\n"
        )

        greeting, _ = generate_greeting(TODAY)

        self.assertEqual(greeting, "早安，喝杯水吧。")

    @patch(CLIENT_PATH)
    def test_ai_error_uses_fallback(self, mock_client):
        mock_client.return_value.chat.completions.create.side_effect = RuntimeError(
            "boom"
        )

        with self.assertLogs("ai_service.greeting", level="WARNING"):
            greeting, from_ai = generate_greeting(TODAY)

        self.assertEqual(greeting, build_fallback_greeting(TODAY))
        self.assertFalse(from_ai)

    @patch(CLIENT_PATH)
    def test_too_long_uses_fallback(self, mock_client):
        mock_client.return_value.chat.completions.create.return_value = fake_ai_reply(
            "今天也要保持大腦活力並且開心過每一天喔。"
        )

        with self.assertLogs("ai_service.greeting", level="WARNING"):
            greeting, from_ai = generate_greeting(TODAY)

        self.assertEqual(greeting, build_fallback_greeting(TODAY))
        self.assertFalse(from_ai)

    @patch(CLIENT_PATH)
    def test_banned_word_uses_fallback(self, mock_client):
        mock_client.return_value.chat.completions.create.return_value = fake_ai_reply(
            "預防失智，動動腦。"
        )

        with self.assertLogs("ai_service.greeting", level="WARNING"):
            greeting, from_ai = generate_greeting(TODAY)

        self.assertEqual(greeting, build_fallback_greeting(TODAY))
        self.assertFalse(from_ai)

    @patch(CLIENT_PATH)
    def test_empty_reply_uses_fallback(self, mock_client):
        mock_client.return_value.chat.completions.create.return_value = fake_ai_reply(
            None
        )

        with self.assertLogs("ai_service.greeting", level="WARNING"):
            greeting, from_ai = generate_greeting(TODAY)

        self.assertEqual(greeting, build_fallback_greeting(TODAY))
        self.assertFalse(from_ai)


class GetDailyGreetingTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @patch(CLIENT_PATH)
    def test_ai_called_only_once_per_day(self, mock_client):
        create = mock_client.return_value.chat.completions.create
        create.return_value = fake_ai_reply("今天天氣真好呀。")

        first = get_daily_greeting()
        second = get_daily_greeting()

        self.assertEqual(first, "今天天氣真好呀。")
        self.assertEqual(second, first)
        self.assertEqual(create.call_count, 1)

    @patch(CLIENT_PATH)
    def test_fallback_is_cached_too(self, mock_client):
        create = mock_client.return_value.chat.completions.create
        create.side_effect = RuntimeError("boom")

        with self.assertLogs("ai_service.greeting", level="WARNING"):
            first = get_daily_greeting()
        second = get_daily_greeting()

        self.assertIn(first, FALLBACK_GREETINGS)
        self.assertEqual(second, first)
        self.assertEqual(create.call_count, 1)
