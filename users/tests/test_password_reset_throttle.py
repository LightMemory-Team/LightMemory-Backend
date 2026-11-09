"""忘記密碼 API 的請求次數限制測試。

執行：
    python manage.py test users.tests.test_password_reset_throttle \
        --settings=config.settings_test
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

CHECK_URL = "/api/users/password-reset/check/"
RESET_URL = "/api/users/password-reset/"

USERNAME_LIMIT = 10
IP_LIMIT = 30


class PasswordResetThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user(username="0912345678", password="Old!Pass2026")

    def _check(self, username="0912345678"):
        return self.client.post(CHECK_URL, {"username": username}, format="json")

    def _reset(self, username="0912345678"):
        return self.client.post(
            RESET_URL,
            {
                "username": username,
                "new_password": "New!Pass2026x",
                "new_password_confirm": "New!Pass2026x",
            },
            format="json",
        )

    def assert_too_many(self, response):
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertFalse(response.data["success"])
        self.assertIsNone(response.data["data"])
        self.assertEqual(response.data["error"]["code"], "TOO_MANY_REQUESTS")
        self.assertIn("Retry-After", response)

    def test_same_username_is_limited(self):
        for _ in range(USERNAME_LIMIT):
            self.assertEqual(self._check().status_code, status.HTTP_200_OK)

        self.assert_too_many(self._check())

    def test_unknown_username_attempts_also_count(self):
        for _ in range(USERNAME_LIMIT):
            self.assertEqual(
                self._check("0900000000").status_code, status.HTTP_404_NOT_FOUND
            )

        self.assert_too_many(self._check("0900000000"))

    def test_check_and_reset_share_the_same_count(self):
        for _ in range(USERNAME_LIMIT):
            self._check()

        self.assert_too_many(self._reset())

    def test_blocked_reset_does_not_change_password(self):
        for _ in range(USERNAME_LIMIT):
            self._check()

        self._reset()

        user = User.objects.get(username="0912345678")
        self.assertTrue(user.check_password("Old!Pass2026"))

    def test_username_limit_ignores_case_and_spaces(self):
        for _ in range(USERNAME_LIMIT):
            self._check()

        self.assert_too_many(self._check(" 0912345678 "))

    def test_other_username_is_not_affected(self):
        User.objects.create_user(username="0987654321", password="Old!Pass2026")
        for _ in range(USERNAME_LIMIT):
            self._check()

        self.assertEqual(self._check("0987654321").status_code, status.HTTP_200_OK)

    def test_one_source_scanning_many_usernames_is_limited(self):
        for i in range(IP_LIMIT):
            self.assertEqual(
                self._check(f"scan{i}").status_code, status.HTTP_404_NOT_FOUND
            )

        self.assert_too_many(self._check("scan-one-more"))

    def test_missing_username_is_a_validation_error_not_throttled(self):
        for _ in range(USERNAME_LIMIT + 2):
            response = self.client.post(CHECK_URL, {}, format="json")

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_normal_flow_still_works_under_the_limit(self):
        self.assertEqual(self._check().status_code, status.HTTP_200_OK)

        response = self._reset()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user = User.objects.get(username="0912345678")
        self.assertTrue(user.check_password("New!Pass2026x"))
