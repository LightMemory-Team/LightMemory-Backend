"""忘記密碼兩支 API 的測試。

執行：
    python manage.py test users.tests.test_password_reset \
        --settings=config.settings_test
"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

CHECK_URL = "/api/users/password-reset/check/"
RESET_URL = "/api/users/password-reset/"
LOGIN_URL = "/api/users/login/"


class PasswordResetCheckTests(APITestCase):
    def setUp(self):
        User.objects.create_user(username="0912345678", password="Old!Pass2026")

    def test_existing_account_returns_exists_true(self):
        response = self.client.post(
            CHECK_URL, {"username": "0912345678"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"exists": True})

    def test_unknown_account_returns_404(self):
        response = self.client.post(
            CHECK_URL, {"username": "0900000000"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "ACCOUNT_NOT_FOUND")

    def test_missing_username_returns_400(self):
        response = self.client.post(CHECK_URL, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("username", response.data["error"]["fields"])

    def test_inactive_account_is_treated_as_not_found(self):
        User.objects.filter(username="0912345678").update(is_active=False)

        response = self.client.post(
            CHECK_URL, {"username": "0912345678"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_no_login_required_even_with_expired_token(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer expired-or-garbage")

        response = self.client.post(
            CHECK_URL, {"username": "0912345678"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_is_not_allowed(self):
        response = self.client.get(CHECK_URL)

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class PasswordResetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="0912345678", password="Old!Pass2026"
        )
        self.payload = {
            "username": "0912345678",
            "new_password": "New!Pass2026x",
            "new_password_confirm": "New!Pass2026x",
        }

    def test_success_updates_password(self):
        response = self.client.post(RESET_URL, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"message": "密碼已更新"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New!Pass2026x"))
        self.assertFalse(self.user.check_password("Old!Pass2026"))

    def test_password_is_stored_hashed(self):
        self.client.post(RESET_URL, self.payload, format="json")

        self.user.refresh_from_db()
        self.assertNotEqual(self.user.password, "New!Pass2026x")

    def test_can_login_with_new_password_after_reset(self):
        self.client.post(RESET_URL, self.payload, format="json")

        new = self.client.post(
            LOGIN_URL,
            {"username": "0912345678", "password": "New!Pass2026x"},
            format="json",
        )
        old = self.client.post(
            LOGIN_URL,
            {"username": "0912345678", "password": "Old!Pass2026"},
            format="json",
        )

        self.assertEqual(new.status_code, status.HTTP_200_OK)
        self.assertEqual(old.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unknown_account_returns_404(self):
        response = self.client.post(
            RESET_URL, {**self.payload, "username": "0900000000"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "ACCOUNT_NOT_FOUND")

    def test_mismatched_passwords_return_400_and_change_nothing(self):
        response = self.client.post(
            RESET_URL,
            {**self.payload, "new_password_confirm": "Different!Pass1"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "PASSWORD_MISMATCH")
        self.assertIn("new_password_confirm", response.data["error"]["fields"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Old!Pass2026"))

    def test_weak_password_returns_400_with_field_message(self):
        response = self.client.post(
            RESET_URL,
            {**self.payload, "new_password": "123", "new_password_confirm": "123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("new_password", response.data["error"]["fields"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Old!Pass2026"))

    def test_missing_fields_return_400(self):
        response = self.client.post(RESET_URL, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        fields = response.data["error"]["fields"]
        for name in ["username", "new_password", "new_password_confirm"]:
            self.assertIn(name, fields)

    def test_only_the_named_account_is_changed(self):
        other = User.objects.create_user(username="other", password="Other!Pass2026")

        self.client.post(RESET_URL, self.payload, format="json")

        other.refresh_from_db()
        self.assertTrue(other.check_password("Other!Pass2026"))

    def test_no_login_required_even_with_expired_token(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer expired-or-garbage")

        response = self.client.post(RESET_URL, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
