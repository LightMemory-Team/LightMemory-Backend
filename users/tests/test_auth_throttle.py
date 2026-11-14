"""登入、註冊、改密碼／刪帳號的請求次數限制測試（G3）。

- 登入：只算「失敗」。同一個帳號 10 次、同一個來源 60 次失敗後回 429；
  成功登入不算，而且會把那個帳號的失敗次數歸零
- 註冊：同一個來源 30 次（成功失敗都算）
- 改密碼、刪帳號：同一位使用者合計 10 次（要輸入密碼確認身分）
- 來源 IP 只信 X-Forwarded-For 的最後一個值（NUM_PROXIES=1），假造的前綴騙不了

限速的次數預設寫在 settings，測試環境把上限調得很高（避免別的測試累積到上限），
所以這裡用 patch 套上「正式環境的次數」再測。

執行：
    python manage.py test users.tests.test_auth_throttle --settings=config.settings_test
"""

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import BaseThrottle, SimpleRateThrottle

from config.tests.test_settings import GOOD_KEY, load_settings
from users.throttles import LoginUsernameThrottle as LoginUsernameThrottleModule

User = get_user_model()

LOGIN_URL = "/api/users/login/"
REGISTER_URL = "/api/users/register/"
PASSWORD_URL = "/api/users/me/password/"
ME_URL = "/api/users/me/"

# 正式環境的次數（跟 config/settings.py 一致；有測試確認兩邊相同）
RATES = {
    "login_ip": "60/hour",
    "login_username": "10/hour",
    "register_ip": "30/hour",
    "password_confirm_user": "10/hour",
}
LOGIN_USERNAME_LIMIT = 10
LOGIN_IP_LIMIT = 60
REGISTER_LIMIT = 30
CONFIRM_LIMIT = 10

PASSWORD = "Str0ng!Pass2026"


def register_payload(username):
    return {
        "username": username,
        "password": PASSWORD,
        "nickname": "測試",
        "gender": "female",
        "birth_date": "1950-01-01",
        "region": "north",
        "emergency_contact_name": "王小明",
        "emergency_contact_phone": "0987654321",
    }


class ThrottleTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.enterContext(patch.dict(SimpleRateThrottle.THROTTLE_RATES, RATES))

    def assert_too_many(self, response):
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertFalse(response.data["success"])
        self.assertIsNone(response.data["data"])
        self.assertEqual(response.data["error"]["code"], "TOO_MANY_REQUESTS")
        self.assertIn("Retry-After", response)


class LoginThrottleTests(ThrottleTestCase):
    def setUp(self):
        super().setUp()
        User.objects.create_user(username="alice", password=PASSWORD)

    def login(self, username="alice", password="wrong-password", **extra):
        return self.client.post(
            LOGIN_URL,
            {"username": username, "password": password},
            format="json",
            **extra,
        )

    def test_a_wrong_password_is_still_a_plain_401_below_the_limit(self):
        for _ in range(LOGIN_USERNAME_LIMIT):
            self.assertEqual(self.login().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_too_many_failures_for_one_username_return_429(self):
        for _ in range(LOGIN_USERNAME_LIMIT):
            self.login()

        self.assert_too_many(self.login())

    def test_the_retry_after_header_is_a_sensible_number_of_seconds(self):
        for _ in range(LOGIN_USERNAME_LIMIT):
            self.login()

        response = self.login()

        retry_after = int(response["Retry-After"])
        self.assertGreater(retry_after, 3500)  # 剛鎖住，大約還要等一小時
        self.assertLessEqual(retry_after, 3600)

    def test_the_lock_expires_after_an_hour(self):
        for _ in range(LOGIN_USERNAME_LIMIT):
            self.login()
        self.assert_too_many(self.login())

        real_timer = LoginUsernameThrottleModule.timer
        with patch.object(
            LoginUsernameThrottleModule,
            "timer",
            staticmethod(lambda: real_timer() + 3601),
        ):
            response = self.login(password=PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_even_the_correct_password_is_blocked_once_locked(self):
        for _ in range(LOGIN_USERNAME_LIMIT):
            self.login()

        response = self.login(password=PASSWORD)

        self.assert_too_many(response)
        self.assertNotIn("access", response.data)

    def test_failures_for_an_unknown_username_count_too(self):
        # 否則可以靠「有沒有被擋」猜出帳號存不存在
        for _ in range(LOGIN_USERNAME_LIMIT):
            response = self.login("nobody")
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        self.assert_too_many(self.login("nobody"))

    def test_other_usernames_are_not_affected(self):
        User.objects.create_user(username="bob", password=PASSWORD)
        for _ in range(LOGIN_USERNAME_LIMIT):
            self.login("alice")

        self.assertEqual(self.login("bob", PASSWORD).status_code, status.HTTP_200_OK)

    def test_the_username_is_matched_ignoring_case_and_spaces(self):
        for username in ["alice", "ALICE", " Alice "] * 4:
            self.login(username)

        self.assert_too_many(self.login("alice"))

    def test_successful_logins_are_never_counted(self):
        for _ in range(LOGIN_USERNAME_LIMIT * 3):
            response = self.login(password=PASSWORD)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn("access", response.data)

    def test_a_successful_login_resets_the_username_failures(self):
        for _ in range(LOGIN_USERNAME_LIMIT - 1):
            self.login()
        self.assertEqual(self.login(password=PASSWORD).status_code, 200)

        # 歸零後，又可以失敗整整 10 次才會被擋
        for _ in range(LOGIN_USERNAME_LIMIT):
            self.assertEqual(self.login().status_code, status.HTTP_401_UNAUTHORIZED)
        self.assert_too_many(self.login())

    def test_requests_without_credentials_are_not_counted(self):
        for _ in range(LOGIN_USERNAME_LIMIT * 2):
            response = self.client.post(LOGIN_URL, {}, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertEqual(self.login(password=PASSWORD).status_code, 200)

    def test_an_inactive_account_counts_as_a_failure(self):
        User.objects.filter(username="alice").update(is_active=False)
        for _ in range(LOGIN_USERNAME_LIMIT):
            self.assertEqual(
                self.login(password=PASSWORD).status_code, status.HTTP_401_UNAUTHORIZED
            )

        self.assert_too_many(self.login(password=PASSWORD))

    def test_one_source_trying_many_usernames_is_limited(self):
        for i in range(LOGIN_IP_LIMIT):
            self.assertEqual(
                self.login(f"user{i}", REMOTE_ADDR="10.0.0.1").status_code,
                status.HTTP_401_UNAUTHORIZED,
            )

        self.assert_too_many(self.login("one-more", REMOTE_ADDR="10.0.0.1"))

    def test_another_source_is_not_affected_by_that_limit(self):
        for i in range(LOGIN_IP_LIMIT):
            self.login(f"user{i}", REMOTE_ADDR="10.0.0.1")

        response = self.login("alice", PASSWORD, REMOTE_ADDR="10.0.0.2")

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class RegisterThrottleTests(ThrottleTestCase):
    def register(self, username, **extra):
        return self.client.post(
            REGISTER_URL, register_payload(username), format="json", **extra
        )

    def test_too_many_registrations_from_one_source_return_429(self):
        for i in range(REGISTER_LIMIT):
            self.assertEqual(
                self.register(f"user{i}").status_code, status.HTTP_201_CREATED
            )

        self.assert_too_many(self.register("one-more"))
        self.assertFalse(User.objects.filter(username="one-more").exists())

    def test_failed_registrations_count_too(self):
        # 用「帳號已被註冊」反覆試探也要算
        User.objects.create_user(username="taken", password=PASSWORD)
        for _ in range(REGISTER_LIMIT):
            response = self.register("taken")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assert_too_many(self.register("taken"))

    def test_another_source_can_still_register(self):
        for i in range(REGISTER_LIMIT):
            self.register(f"user{i}", REMOTE_ADDR="10.0.0.1")

        response = self.register("newcomer", REMOTE_ADDR="10.0.0.2")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class PasswordConfirmThrottleTests(ThrottleTestCase):
    """修改密碼、刪除帳號：合計算同一位使用者的次數。"""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="carol", password=PASSWORD)
        self.client.force_authenticate(user=self.user)

    def change(self, old_password="wrong-old"):
        return self.client.post(
            PASSWORD_URL,
            {"old_password": old_password, "new_password": "New!Pass2026x"},
            format="json",
        )

    def delete_account(self, password="wrong-password"):
        return self.client.delete(ME_URL, {"password": password}, format="json")

    def test_wrong_old_passwords_are_limited(self):
        for _ in range(CONFIRM_LIMIT):
            self.assertEqual(self.change().status_code, status.HTTP_400_BAD_REQUEST)

        self.assert_too_many(self.change())

    def test_the_correct_old_password_is_blocked_once_locked(self):
        for _ in range(CONFIRM_LIMIT):
            self.change()

        self.assert_too_many(self.change(PASSWORD))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))  # 密碼沒被改

    def test_a_normal_password_change_still_works(self):
        response = self.change(PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data["data"])

    def test_wrong_passwords_when_deleting_the_account_are_limited(self):
        for _ in range(CONFIRM_LIMIT):
            self.assertEqual(
                self.delete_account().status_code, status.HTTP_400_BAD_REQUEST
            )

        self.assert_too_many(self.delete_account(PASSWORD))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())  # 帳號還在

    def test_changing_and_deleting_share_the_same_count(self):
        for _ in range(CONFIRM_LIMIT):
            self.change()

        self.assert_too_many(self.delete_account(PASSWORD))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_a_normal_account_deletion_still_works(self):
        response = self.delete_account(PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_viewing_and_editing_the_profile_is_not_limited(self):
        for _ in range(CONFIRM_LIMIT * 3):
            self.assertEqual(self.client.get(ME_URL).status_code, 200)
            patched = self.client.patch(ME_URL, {"nickname": "新暱稱"}, format="json")
            self.assertEqual(patched.status_code, 200)

    def test_the_limit_is_per_user(self):
        other = User.objects.create_user(username="dave", password=PASSWORD)
        for _ in range(CONFIRM_LIMIT):
            self.change()
        self.assert_too_many(self.change())

        other_client = APIClient()
        other_client.force_authenticate(user=other)
        response = other_client.post(
            PASSWORD_URL,
            {"old_password": PASSWORD, "new_password": "New!Pass2026x"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_an_anonymous_request_gets_401_not_429(self):
        response = APIClient().post(PASSWORD_URL, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ClientAddressTests(ThrottleTestCase):
    """來源 IP 只信 X-Forwarded-For 的最後一個值（Cloudflare 接在最後）。"""

    def login(self, username, forwarded_for):
        return self.client.post(
            LOGIN_URL,
            {"username": username, "password": "wrong-password"},
            format="json",
            HTTP_X_FORWARDED_FOR=forwarded_for,
        )

    def test_a_forged_prefix_cannot_dodge_the_source_limit(self):
        # 攻擊者每次都在前面加不同的假 IP；真正的來源（最後一個）都一樣
        for i in range(LOGIN_IP_LIMIT):
            self.login(f"user{i}", f"6.6.6.{i % 250}, 203.0.113.9")

        self.assert_too_many(self.login("one-more", "7.7.7.7, 203.0.113.9"))

    def test_different_real_sources_behind_the_proxy_are_counted_separately(self):
        for i in range(LOGIN_IP_LIMIT):
            self.login(f"user{i}", "203.0.113.9")

        self.assert_too_many(self.login("x", "203.0.113.9"))
        self.assertEqual(
            self.login("y", "203.0.113.10").status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_the_proxy_count_decides_which_address_is_trusted(self):
        def ident(num_proxies, header, remote="127.0.0.1"):
            rest = {**settings.REST_FRAMEWORK, "NUM_PROXIES": num_proxies}
            request = type("R", (), {"META": {"REMOTE_ADDR": remote}})()
            if header is not None:
                request.META["HTTP_X_FORWARDED_FOR"] = header
            with override_settings(REST_FRAMEWORK=rest):
                return BaseThrottle().get_ident(request)

        self.assertEqual(ident(1, "6.6.6.6, 203.0.113.9"), "203.0.113.9")
        self.assertEqual(ident(1, None), "127.0.0.1")  # 沒有代理標頭就用連線來源
        self.assertEqual(ident(0, "6.6.6.6, 203.0.113.9"), "127.0.0.1")  # 不信任標頭


class SettingsTests(SimpleTestCase):
    def test_the_production_rates_are_what_this_file_assumes(self):
        s = load_settings({"DJANGO_SECRET_KEY": GOOD_KEY})

        self.assertEqual(s.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], RATES)

    def test_every_scope_has_a_rate_in_the_test_settings_too(self):
        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]

        self.assertEqual(set(rates), set(RATES))

    def test_proxy_count_defaults_to_one_and_can_be_changed(self):
        default = load_settings({"DJANGO_SECRET_KEY": GOOD_KEY})
        direct = load_settings(
            {"DJANGO_SECRET_KEY": GOOD_KEY, "DJANGO_NUM_PROXIES": "0"}
        )

        self.assertEqual(default.REST_FRAMEWORK["NUM_PROXIES"], 1)
        self.assertEqual(direct.REST_FRAMEWORK["NUM_PROXIES"], 0)
