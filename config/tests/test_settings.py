"""安全設定改讀環境變數的測試（G1）。

SECRET_KEY、DEBUG、CORS、ALLOWED_HOSTS、CSRF_TRUSTED_ORIGINS 不再寫死在程式碼裡。
重點：
- DEBUG 沒設就是關閉（預設安全）
- DEBUG 關閉時一定要自己設 DJANGO_SECRET_KEY，沒設就報錯；
  不能用 django-insecure- 開頭的金鑰
- DEBUG 開啟（開發）沒設金鑰也能跑，用開發專用的備用金鑰
- CORS：開發預設允許所有來源，正式環境預設不允許，要明確列出
- 曾經寫進程式碼的那把金鑰不能再出現在 settings.py

每個測試都用「全新載入 settings.py ＋ 只看指定的環境變數」，不受本機 .env 影響。

執行：
    python manage.py test config.tests.test_settings --settings=config.settings_test
"""

import importlib.util
import os
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

import decouple
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "settings.py"

# settings.py 一定要有的資料庫設定（跟這次要測的安全設定無關，隨便填）
DB_ENV = {
    "DB_NAME": "x",
    "DB_USER": "x",
    "DB_PASSWORD": "x",
    "DB_HOST": "x",
    "DB_PORT": "5432",
}
GOOD_KEY = "a-long-random-production-key-0123456789"
# 曾經寫死在 settings.py、已經公開在 Git 歷史裡的金鑰
LEAKED_KEY = "django-insecure-ils*(wye_q#y7@6z_68x^t^*q@#*o_b^zl+@%*h*b=-_x#w^%z"


def load_settings(env):
    """全新載入 settings.py，環境變數只有 env（加上必要的資料庫設定），不讀 .env 檔。"""
    reader = decouple.Config(decouple.RepositoryEmpty())  # 只看環境變數
    spec = importlib.util.spec_from_file_location("settings_under_test", SETTINGS_FILE)
    module = importlib.util.module_from_spec(spec)
    with (
        patch.dict(os.environ, {**DB_ENV, **env}, clear=True),
        patch.object(decouple, "config", reader),
    ):
        spec.loader.exec_module(module)
    return module


class DebugTests(SimpleTestCase):
    def test_debug_is_off_when_not_set(self):
        s = load_settings({"DJANGO_SECRET_KEY": GOOD_KEY})

        self.assertFalse(s.DEBUG)

    def test_debug_accepts_common_spellings(self):
        for raw, expected in [
            ("True", True),
            ("true", True),
            ("1", True),
            ("False", False),
            ("false", False),
            ("0", False),
        ]:
            with self.subTest(raw=raw):
                s = load_settings({"DJANGO_DEBUG": raw, "DJANGO_SECRET_KEY": GOOD_KEY})
                self.assertEqual(s.DEBUG, expected)


class SecretKeyTests(SimpleTestCase):
    def test_production_without_a_key_fails_to_start(self):
        with self.assertRaises(ImproperlyConfigured):
            load_settings({})

    def test_production_with_an_empty_key_fails_to_start(self):
        # .env 留著「DJANGO_SECRET_KEY=」卻沒填值，不能當成有設
        for empty in ("", "   "):
            with self.subTest(value=repr(empty)):
                with self.assertRaises(ImproperlyConfigured):
                    load_settings({"DJANGO_SECRET_KEY": empty})

    def test_the_error_tells_you_what_to_do(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            load_settings({})

        self.assertIn("DJANGO_SECRET_KEY", str(ctx.exception))

    def test_production_uses_the_key_from_the_environment(self):
        s = load_settings({"DJANGO_SECRET_KEY": GOOD_KEY})

        self.assertEqual(s.SECRET_KEY, GOOD_KEY)

    def test_production_rejects_insecure_prefixed_keys(self):
        for key in (
            LEAKED_KEY,
            "django-insecure-dev-only-do-not-use-in-production",
            "django-insecure-anything",
        ):
            with self.subTest(key=key[:30]):
                with self.assertRaises(ImproperlyConfigured):
                    load_settings({"DJANGO_SECRET_KEY": key})

    def test_development_works_without_a_key(self):
        s = load_settings({"DJANGO_DEBUG": "True"})

        self.assertTrue(s.DEBUG)
        self.assertTrue(s.SECRET_KEY)
        self.assertTrue(s.SECRET_KEY.startswith("django-insecure-"))

    def test_development_with_an_empty_key_uses_the_dev_key(self):
        # 本機把金鑰清空但留著那一行：不能讓服務壞掉
        for empty in ("", "   "):
            with self.subTest(value=repr(empty)):
                s = load_settings({"DJANGO_DEBUG": "True", "DJANGO_SECRET_KEY": empty})
                self.assertTrue(s.SECRET_KEY.startswith("django-insecure-"))

    def test_development_still_prefers_a_key_from_the_environment(self):
        s = load_settings({"DJANGO_DEBUG": "True", "DJANGO_SECRET_KEY": GOOD_KEY})

        self.assertEqual(s.SECRET_KEY, GOOD_KEY)

    def test_the_leaked_key_is_no_longer_in_the_source(self):
        source = SETTINGS_FILE.read_text(encoding="utf-8")

        self.assertNotIn(LEAKED_KEY, source)
        self.assertNotIn("ils*(wye_q", source)

    def test_the_running_settings_do_not_use_the_leaked_key(self):
        from django.conf import settings

        self.assertNotEqual(settings.SECRET_KEY, LEAKED_KEY)


class CorsTests(SimpleTestCase):
    def test_development_allows_every_origin_by_default(self):
        s = load_settings({"DJANGO_DEBUG": "True"})

        self.assertTrue(s.CORS_ALLOW_ALL_ORIGINS)

    def test_production_allows_no_origin_by_default(self):
        s = load_settings({"DJANGO_SECRET_KEY": GOOD_KEY})

        self.assertFalse(s.CORS_ALLOW_ALL_ORIGINS)
        self.assertEqual(s.CORS_ALLOWED_ORIGINS, [])

    def test_production_origins_come_from_the_environment(self):
        s = load_settings(
            {
                "DJANGO_SECRET_KEY": GOOD_KEY,
                "DJANGO_CORS_ALLOWED_ORIGINS": "https://app.example.com, https://www.example.com",
            }
        )

        self.assertFalse(s.CORS_ALLOW_ALL_ORIGINS)
        self.assertEqual(
            s.CORS_ALLOWED_ORIGINS,
            ["https://app.example.com", "https://www.example.com"],
        )

    def test_allow_all_can_be_switched_explicitly(self):
        on = load_settings(
            {"DJANGO_SECRET_KEY": GOOD_KEY, "DJANGO_CORS_ALLOW_ALL": "True"}
        )
        off = load_settings({"DJANGO_DEBUG": "True", "DJANGO_CORS_ALLOW_ALL": "False"})

        self.assertTrue(on.CORS_ALLOW_ALL_ORIGINS)
        self.assertFalse(off.CORS_ALLOW_ALL_ORIGINS)


class HostsTests(SimpleTestCase):
    def test_defaults_keep_the_current_behaviour(self):
        s = load_settings({"DJANGO_SECRET_KEY": GOOD_KEY})

        self.assertEqual(
            s.ALLOWED_HOSTS,
            ["localhost", "127.0.0.1", "testserver", ".trycloudflare.com"],
        )
        self.assertEqual(s.CSRF_TRUSTED_ORIGINS, ["https://*.trycloudflare.com"])

    def test_hosts_and_csrf_origins_come_from_the_environment(self):
        s = load_settings(
            {
                "DJANGO_SECRET_KEY": GOOD_KEY,
                "DJANGO_ALLOWED_HOSTS": "api.example.com,localhost",
                "DJANGO_CSRF_TRUSTED_ORIGINS": "https://api.example.com",
            }
        )

        self.assertEqual(s.ALLOWED_HOSTS, ["api.example.com", "localhost"])
        self.assertEqual(s.CSRF_TRUSTED_ORIGINS, ["https://api.example.com"])


@skipUnless(
    settings.SETTINGS_MODULE == "config.settings_test",
    "只檢查 config.settings_test；用一般 settings 跑時，沒設金鑰本來就會用開發用金鑰",
)
class TestSettingsTests(SimpleTestCase):
    def test_the_test_settings_do_not_need_a_key_in_the_environment(self):
        # settings_test 會先補一把測試用金鑰，所以沒有 .env 也能跑測試（CI 用得到）
        from django.conf import settings

        self.assertTrue(settings.SECRET_KEY)
        self.assertFalse(settings.SECRET_KEY.startswith("django-insecure-"))
