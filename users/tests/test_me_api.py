from unittest.mock import patch
"""GET／PATCH／DELETE /api/users/me/ 及會員中心相關 API 的端到端測試。

執行：
    python manage.py test users.tests.test_me_api --settings=config.settings_test
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from diary.models import Diary
from games.models import Game, GameCategory, GameSession

User = get_user_model()

ME_URL = "/api/users/me/"
PASSWORD_URL = "/api/users/me/password/"
AVATAR_URL = "/api/users/me/avatar/"
STATS_URL = "/api/users/me/stats/"


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
        self.assertTrue(response.data["success"])
        self.assertIsNone(response.data["error"])
        self.assertEqual(
            response.data["data"],
            {
                "username": "0912345678",
                "nickname": "玉蘭",
                "birth_date": "1955-01-01",
                "gender": "female",
                "region": "north",
                "emergency_contact_name": "王小明",
                "emergency_contact_phone": "0987654321",
                "avatar_url": None,
                "interests": [],
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
        self.user.avatar_url = None
        self.user.interests = []
        self.user.save()

        response = self.client.get(ME_URL)

        data = response.data["data"]
        self.assertIsNone(data["region"])
        self.assertIsNone(data["emergency_contact_name"])
        self.assertIsNone(data["emergency_contact_phone"])
        self.assertIsNone(data["avatar_url"])
        self.assertEqual(data["interests"], [])

    def test_returns_only_the_logged_in_users_data(self):
        User.objects.create_user(username="other", password="x", nickname="別人")

        response = self.client.get(ME_URL)

        self.assertEqual(response.data["data"]["nickname"], "玉蘭")


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

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(data["nickname"], "小蘭")
        self.assertEqual(data["username"], "0912345678")
        self.assertEqual(data["region"], "north")

    def test_username_cannot_be_changed(self):
        response = self.client.patch(
            ME_URL, {"username": "hacker", "nickname": "小蘭"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "0912345678")
        self.assertEqual(response.data["data"]["username"], "0912345678")

    def test_password_cannot_be_changed(self):
        self.client.patch(ME_URL, {"password": "Hacked!Pass999"}, format="json")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Str0ng!Pass2026"))

    def test_can_fill_in_optional_fields_after_registration(self):
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
                "interests": ["散步", "泡茶"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(data["region"], "central")
        self.assertEqual(data["emergency_contact_name"], "王小明")
        self.assertEqual(data["emergency_contact_phone"], "0987654321")
        self.assertEqual(data["interests"], ["散步", "泡茶"])

    def test_optional_fields_can_be_cleared(self):
        response = self.client.patch(
            ME_URL,
            {"region": None, "emergency_contact_name": "", "emergency_contact_phone": ""},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertIsNone(data["region"])
        self.assertIsNone(data["emergency_contact_name"])
        self.assertIsNone(data["emergency_contact_phone"])

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

    def test_east_region_rejected(self):
        """需求一-1：前端僅認 north、central、south，east 應回 400"""
        response = self.client.patch(ME_URL, {"region": "east"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("region", response.data["error"]["fields"])

    def test_other_gender_rejected(self):
        """需求一-1：前端僅認 male、female，other 應回 400"""
        response = self.client.patch(ME_URL, {"gender": "other"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("gender", response.data["error"]["fields"])

    def test_invalid_emergency_contact_phone_rejected(self):
        """需求一-2：送 'abc' 應回 400 VALIDATION_ERROR 加 fields"""
        response = self.client.patch(
            ME_URL, {"emergency_contact_phone": "abc"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("emergency_contact_phone", response.data["error"]["fields"])

    def test_valid_emergency_contact_phone_accepted(self):
        """支援數字、+、-、空白，8~15 碼"""
        for phone in ["0912345678", "+886 912-345", "02-1234567"]:
            with self.subTest(phone=phone):
                response = self.client.patch(
                    ME_URL, {"emergency_contact_phone": phone}, format="json"
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(
                    response.data["data"]["emergency_contact_phone"], phone
                )

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


class PasswordChangeTests(MeApiTestCase):
    def test_change_password_success(self):
        response = self.client.post(
            PASSWORD_URL,
            {
                "old_password": "Str0ng!Pass2026",
                "new_password": "New!StrongPass2026",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIn("access", response.data["data"])
        self.assertIn("refresh", response.data["data"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New!StrongPass2026"))

    def test_wrong_old_password_returns_400(self):
        response = self.client.post(
            PASSWORD_URL,
            {
                "old_password": "WrongPassword123",
                "new_password": "New!StrongPass2026",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("old_password", response.data["error"]["fields"])

    def test_weak_new_password_returns_400(self):
        response = self.client.post(
            PASSWORD_URL,
            {
                "old_password": "Str0ng!Pass2026",
                "new_password": "123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("new_password", response.data["error"]["fields"])

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            PASSWORD_URL,
            {
                "old_password": "Str0ng!Pass2026",
                "new_password": "New!StrongPass2026",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class AccountDeleteTests(MeApiTestCase):
    def test_delete_account_success(self):
        response = self.client.delete(
            ME_URL, {"password": "Str0ng!Pass2026"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_wrong_password_returns_400(self):
        response = self.client.delete(
            ME_URL, {"password": "WrongPassword"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("password", response.data["error"]["fields"])
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.delete(
            ME_URL, {"password": "Str0ng!Pass2026"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class AvatarTests(MeApiTestCase):
    @patch("diary.external.upload_to_firebase", return_value="https://fake-firebase-url.com/avatars/avatar.jpg")
    def test_upload_avatar_success(self, mock_upload):
        avatar = SimpleUploadedFile("avatar.jpg", b"fake-jpg-binary", content_type="image/jpeg")
        response = self.client.post(AVATAR_URL, {"avatar": avatar}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["avatar_url"], "https://fake-firebase-url.com/avatars/avatar.jpg")

        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar_url, "https://fake-firebase-url.com/avatars/avatar.jpg")

    def test_upload_invalid_format_returns_400(self):
        text_file = SimpleUploadedFile("doc.txt", b"hello world", content_type="text/plain")
        response = self.client.post(AVATAR_URL, {"avatar": text_file}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("avatar", response.data["error"]["fields"])

    def test_delete_avatar_success(self):
        self.user.avatar_url = "https://example.com/avatar.jpg"
        self.user.save(update_fields=["avatar_url"])

        response = self.client.delete(AVATAR_URL)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.avatar_url)

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.delete(AVATAR_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserStatsTests(MeApiTestCase):
    def setUp(self):
        super().setUp()
        category = GameCategory.objects.create(category_name="認知訓練")
        self.game = Game.objects.create(name="菜市場找路", code="market_route", category=category)

    def test_user_stats_empty(self):
        response = self.client.get(STATS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        stats = response.data["data"]
        self.assertEqual(stats["active_day_count"], 0)
        self.assertEqual(stats["session_count"], 0)
        self.assertEqual(stats["diary_count"], 0)
        self.assertEqual(stats["streak_days"], 0)
        self.assertEqual(stats["joined_at"], timezone.localdate().isoformat())

    def test_user_stats_with_sessions_and_diaries(self):
        today = timezone.now()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)

        # 熟悉場（is_pretest=True）：不應計入 session_count
        pretest = GameSession.objects.create(
            user=self.user,
            game=self.game,
            status="finished",
            is_pretest=True,
        )
        GameSession.objects.filter(pk=pretest.pk).update(created_at=two_days_ago)

        # 正式完成場次
        session = GameSession.objects.create(
            user=self.user,
            game=self.game,
            status="finished",
            is_pretest=False,
        )
        # 手動調整 created_at 模擬昨日活動
        GameSession.objects.filter(pk=session.pk).update(created_at=yesterday)

        # 完成的日記（今日活動）
        Diary.objects.create(
            user=self.user,
            status="done",
            title="今日日記",
        )

        response = self.client.get(STATS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stats = response.data["data"]
        self.assertEqual(stats["session_count"], 1)  # 排除熟悉場
        self.assertEqual(stats["diary_count"], 1)
        self.assertEqual(stats["active_day_count"], 3)  # two_days_ago, yesterday, today
        self.assertEqual(stats["streak_days"], 3)  # 連續三天活動

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(STATS_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


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
        self.assertEqual(response.data["data"]["nickname"], "玉蘭")
        self.assertIsNone(response.data["data"]["region"])

    def test_garbage_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "NOT_AUTHENTICATED")
