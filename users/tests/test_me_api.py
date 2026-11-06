"""GET／PATCH /api/users/me/ 的端到端測試。

執行：
    python manage.py test users.tests.test_me_api --settings=config.settings_test
"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

ME_URL = "/api/users/me/"


class MeApiTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="0912345678",
            password="Str0ng!Pass2026",
            nickname="玉蘭",
            gender="female",
            birth_date="1955-01-01",
            region="north",
            emergency_contact_name="王小明",
            emergency_contact_phone="0987654321",
        )
        self.client.force_authenticate(user=self.user)


class GetMeTests(MeApiTestCase):
    def test_returns_own_profile(self):
        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "username": "0912345678",
                "nickname": "玉蘭",
                "birth_date": "1955-01-01",
                "gender": "female",
                "region": "north",
                "emergency_contact_name": "王小明",
                "emergency_contact_phone": "0987654321",
            },
        )

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "NOT_AUTHENTICATED")

    def test_unfilled_optional_fields_are_null(self):
        self.user.region = ""
        self.user.emergency_contact_name = None
        self.user.emergency_contact_phone = ""
        self.user.save()

        response = self.client.get(ME_URL)

        self.assertIsNone(response.data["region"])
        self.assertIsNone(response.data["emergency_contact_name"])
        self.assertIsNone(response.data["emergency_contact_phone"])

    def test_returns_only_the_logged_in_users_data(self):
        User.objects.create_user(username="other", password="x", nickname="別人")

        response = self.client.get(ME_URL)

        self.assertEqual(response.data["nickname"], "玉蘭")


class PatchMeTests(MeApiTestCase):
    def test_patch_one_field_keeps_the_others(self):
        response = self.client.patch(ME_URL, {"region": "central"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.region, "central")
        self.assertEqual(self.user.nickname, "玉蘭")
        self.assertEqual(self.user.emergency_contact_name, "王小明")
        self.assertEqual(self.user.emergency_contact_phone, "0987654321")
        self.assertEqual(str(self.user.birth_date), "1955-01-01")

    def test_response_is_the_full_profile(self):
        response = self.client.patch(ME_URL, {"nickname": "小蘭"}, format="json")

        self.assertEqual(response.data["nickname"], "小蘭")
        self.assertEqual(response.data["username"], "0912345678")
        self.assertEqual(response.data["region"], "north")

    def test_username_cannot_be_changed(self):
        response = self.client.patch(
            ME_URL, {"username": "hacker", "nickname": "小蘭"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "0912345678")
        self.assertEqual(response.data["username"], "0912345678")

    def test_password_cannot_be_changed(self):
        self.client.patch(ME_URL, {"password": "Hacked!Pass999"}, format="json")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Str0ng!Pass2026"))

    def test_can_fill_in_optional_fields_after_registration(self):
        """註冊後的「選填資料」步驟：原本都是 null，之後用 PATCH 補上"""
        self.user.region = None
        self.user.emergency_contact_name = None
        self.user.emergency_contact_phone = None
        self.user.save()

        response = self.client.patch(
            ME_URL,
            {
                "region": "central",
                "emergency_contact_name": "王小明",
                "emergency_contact_phone": "0987654321",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["region"], "central")
        self.assertEqual(response.data["emergency_contact_name"], "王小明")

    def test_optional_fields_can_be_cleared(self):
        response = self.client.patch(
            ME_URL,
            {"region": None, "emergency_contact_name": ""},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["region"])
        self.assertIsNone(response.data["emergency_contact_name"])

    def test_blank_nickname_returns_400_with_fields(self):
        response = self.client.patch(ME_URL, {"nickname": "  "}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("nickname", response.data["error"]["fields"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, "玉蘭")

    def test_invalid_region_returns_400(self):
        response = self.client.patch(ME_URL, {"region": "moon"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("region", response.data["error"]["fields"])

    def test_future_birth_date_returns_400(self):
        response = self.client.patch(
            ME_URL, {"birth_date": "2999-01-01"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("birth_date", response.data["error"]["fields"])

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.patch(ME_URL, {"nickname": "x"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_put_is_not_allowed(self):
        response = self.client.put(ME_URL, {"nickname": "x"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response.data["error"]["code"], "METHOD_NOT_ALLOWED")


class MeWithRealTokenTests(APITestCase):
    """不用 force_authenticate，走真正的登入流程拿 token"""

    def test_register_login_then_get_me(self):
        self.client.post(
            "/api/users/register/",
            {
                "username": "yulan@example.com",
                "password": "Str0ng!Pass2026",
                "nickname": "玉蘭",
                "gender": "female",
                "birth_date": "1955-01-01",
            },
            format="json",
        )
        login = self.client.post(
            "/api/users/login/",
            {"username": "yulan@example.com", "password": "Str0ng!Pass2026"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["nickname"], "玉蘭")
        self.assertIsNone(response.data["region"])

    def test_garbage_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "NOT_AUTHENTICATED")
