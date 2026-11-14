"""OpenAI client 的 timeout 與重試測試（G9）。

重點：
- 全專案的 AI 呼叫（日記首問／追問／完成、週報總結、首頁問候語）都用同一個 client，
  設定同樣的 timeout 與重試次數
- 預設是 15 秒、重試 1 次（SDK 預設是等 600 秒、重試 2 次）
- **AI 卡住時真的會在時限內放棄並退回固定內容**：用一個「收到請求卻不回應」的
  本機假伺服器測，不是只檢查設定值
- 暫時性錯誤（5xx）會重試一次，金鑰錯誤（401）不會重試

執行：
    python manage.py test ai_service.tests.test_client --settings=config.settings_test
"""

import json
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from ai_service import client as ai_client
from ai_service import greeting, weekly_summary
from ai_service.client import get_client
from config.tests.test_settings import GOOD_KEY, load_settings
from diary import ai_gen


class FakeOpenAI:
    """模擬 OpenAI 的本機伺服器。

    mode：
        "hang"   收到請求後一直不回應（模擬 AI 卡住）
        "ok"     正常回傳一句話
        "500"    回 500（暫時性錯誤）
        "500-then-ok"  第一次回 500，之後正常
        "401"    回 401（金鑰錯誤）
    """

    def __init__(self, mode):
        self.mode = mode
        self.requests = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                outer.requests += 1
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                mode = outer.mode
                if mode == "500-then-ok":
                    mode = "500" if outer.requests == 1 else "ok"
                if mode == "hang":
                    time.sleep(5)  # 比測試設定的 timeout 長很多
                    return
                if mode in ("500", "401"):
                    self.send_response(int(mode))
                    self.send_header("Content-Type", "application/json")
                    body = json.dumps({"error": {"message": "x"}}).encode()
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                body = json.dumps(
                    {
                        "id": "x",
                        "object": "chat.completion",
                        "created": 0,
                        "model": "m",
                        "choices": [
                            {
                                "index": 0,
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "早安"},
                            }
                        ],
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def ai_settings(url, timeout=0.3, retries=0):
    return override_settings(
        OPENAI_BASE_URL=url,
        OPENAI_API_KEY="test-key",
        OPENAI_TIMEOUT_SECONDS=timeout,
        OPENAI_MAX_RETRIES=retries,
    )


class ClientSettingsTests(SimpleTestCase):
    def test_the_client_uses_the_configured_timeout_and_retries(self):
        with override_settings(
            OPENAI_API_KEY="k", OPENAI_TIMEOUT_SECONDS=7, OPENAI_MAX_RETRIES=3
        ):
            client = get_client()

        self.assertEqual(client.timeout, 7)
        self.assertEqual(client.max_retries, 3)

    def test_the_defaults_are_much_shorter_than_the_sdk_defaults(self):
        s = load_settings({"DJANGO_SECRET_KEY": GOOD_KEY})

        self.assertEqual(s.OPENAI_TIMEOUT_SECONDS, 15)
        self.assertEqual(s.OPENAI_MAX_RETRIES, 1)
        # 最壞情況：15 秒 × (1 次重試 + 1) = 30 秒，而不是 SDK 預設的 600 × 3 = 1800 秒
        worst = s.OPENAI_TIMEOUT_SECONDS * (s.OPENAI_MAX_RETRIES + 1)
        self.assertLessEqual(worst, 60)

    def test_both_values_can_be_changed_from_the_environment(self):
        s = load_settings(
            {
                "DJANGO_SECRET_KEY": GOOD_KEY,
                "OPENAI_TIMEOUT_SECONDS": "5.5",
                "OPENAI_MAX_RETRIES": "0",
            }
        )

        self.assertEqual(s.OPENAI_TIMEOUT_SECONDS, 5.5)
        self.assertEqual(s.OPENAI_MAX_RETRIES, 0)

    def test_every_ai_caller_goes_through_the_shared_client(self):
        # 三個模組各自的 _client 都要走共用的 get_client，
        # 不能各自 new 一個沒設 timeout 的
        with override_settings(
            OPENAI_API_KEY="k", OPENAI_TIMEOUT_SECONDS=9, OPENAI_MAX_RETRIES=2
        ):
            for client in (
                ai_gen._client(),
                weekly_summary._client(),
                greeting._client(),
            ):
                self.assertEqual(client.timeout, 9)
                self.assertEqual(client.max_retries, 2)

    def test_no_module_builds_its_own_openai_client(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2]
        offenders = [
            str(path.relative_to(root))
            for path in root.rglob("*.py")
            if "venv" not in path.parts
            and "tests" not in path.parts
            and path != pathlib.Path(ai_client.__file__)
            and "OpenAI(" in path.read_text(encoding="utf-8")
        ]

        self.assertEqual(offenders, [])


class HangingServerTests(SimpleTestCase):
    """AI 卡住時，各處都要在時限內放棄並退回固定內容。"""

    def test_a_hanging_ai_gives_up_within_the_timeout(self):
        with FakeOpenAI("hang") as fake, ai_settings(fake.url):
            started = time.monotonic()
            with self.assertRaises(Exception):
                get_client().chat.completions.create(
                    model="m", messages=[{"role": "user", "content": "hi"}]
                )
            elapsed = time.monotonic() - started

        self.assertLess(elapsed, 3)  # 假伺服器會卡 5 秒；timeout 是 0.3 秒

    def test_diary_first_question_falls_back_when_the_ai_hangs(self):
        with FakeOpenAI("hang") as fake, ai_settings(fake.url):
            started = time.monotonic()
            question = ai_gen.generate_first_question("一張照片")
            elapsed = time.monotonic() - started

        self.assertEqual(question, ai_gen.FIRST_QUESTION_FALLBACK)
        self.assertLess(elapsed, 3)

    def test_diary_follow_up_falls_back_when_the_ai_hangs(self):
        with FakeOpenAI("hang") as fake, ai_settings(fake.url):
            started = time.monotonic()
            question = ai_gen.generate_follow_up("今天去公園")
            elapsed = time.monotonic() - started

        self.assertEqual(question, ai_gen.FOLLOW_UP_FALLBACK)
        self.assertLess(elapsed, 3)

    def test_finalizing_a_diary_uses_the_defaults_when_the_ai_hangs(self):
        with FakeOpenAI("hang") as fake, ai_settings(fake.url):
            started = time.monotonic()
            content = ai_gen.generate_finalize_content("今天去公園散步")
            elapsed = time.monotonic() - started

        self.assertEqual(content["ai_response"], "謝謝你今天的分享！")
        self.assertEqual(content["title"], "今天去公園散步")
        self.assertLess(elapsed, 3)

    def test_weekly_summary_falls_back_when_the_ai_hangs(self):
        facts = {"active_day_count": 3}
        with FakeOpenAI("hang") as fake, ai_settings(fake.url):
            started = time.monotonic()
            summary = weekly_summary.generate_weekly_summary(facts)
            elapsed = time.monotonic() - started

        self.assertEqual(summary, weekly_summary.build_fallback_summary(facts))
        self.assertLess(elapsed, 3)

    def test_greeting_falls_back_when_the_ai_hangs(self):
        today = date(2026, 11, 14)
        with FakeOpenAI("hang") as fake, ai_settings(fake.url):
            started = time.monotonic()
            text, from_ai = greeting.generate_greeting(today)
            elapsed = time.monotonic() - started

        self.assertEqual(text, greeting.build_fallback_greeting(today))
        self.assertFalse(from_ai)
        self.assertLess(elapsed, 3)


class RetryTests(SimpleTestCase):
    def ask(self):
        return get_client().chat.completions.create(
            model="m", messages=[{"role": "user", "content": "hi"}]
        )

    def test_a_healthy_ai_answers_normally(self):
        with FakeOpenAI("ok") as fake, ai_settings(fake.url, timeout=5):
            reply = self.ask()

        self.assertEqual(reply.choices[0].message.content, "早安")
        self.assertEqual(fake.requests, 1)

    def test_a_temporary_error_is_retried_once(self):
        with (
            FakeOpenAI("500-then-ok") as fake,
            ai_settings(fake.url, timeout=5, retries=1),
        ):
            with patch("openai._base_client.time.sleep"):  # 不真的等重試間隔
                reply = self.ask()

        self.assertEqual(reply.choices[0].message.content, "早安")
        self.assertEqual(fake.requests, 2)

    def test_retries_stop_at_the_configured_number(self):
        with FakeOpenAI("500") as fake, ai_settings(fake.url, timeout=5, retries=1):
            with patch("openai._base_client.time.sleep"):
                with self.assertRaises(Exception):
                    self.ask()

        self.assertEqual(fake.requests, 2)  # 第一次＋重試 1 次，不是 SDK 預設的 3 次

    def test_a_wrong_api_key_is_not_retried(self):
        with FakeOpenAI("401") as fake, ai_settings(fake.url, timeout=5, retries=1):
            with self.assertRaises(Exception):
                self.ask()

        self.assertEqual(fake.requests, 1)
