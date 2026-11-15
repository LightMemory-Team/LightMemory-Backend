"""會員中心的日期要用台灣時間（F11）。

- 會員統計的「加入日期」：資料庫存 UTC，台灣 00:00～08:00 註冊不能少一天
- 生日不能是未來：「今天」要以台灣時間為準

執行：
    python manage.py test users.tests.test_local_dates --settings=config.settings_test
"""

from datetime import datetime
from datetime import timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from users.views import calculate_user_stats

User = get_user_model()

ME_URL = "/api/users/me/"
STATS_URL = "/api/users/me/stats/"


class JoinedAtTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="0912345678", password="Str0ng!Pass2026"
        )

    def register_at(self, utc_datetime):
        User.objects.filter(pk=self.user.pk).update(registered_at=utc_datetime)
        self.user.refresh_from_db()

    def test_registered_after_taiwan_midnight_counts_as_the_next_day(self):
        # UTC 11/09 17:00 = 台灣 11/10 01:00
        self.register_at(datetime(2026, 11, 9, 17, 0, tzinfo=dt_timezone.utc))

        self.assertEqual(calculate_user_stats(self.user)["joined_at"], "2026-11-10")

    def test_registered_before_taiwan_midnight_keeps_the_day(self):
        # UTC 11/09 15:59 = 台灣 11/09 23:59
        self.register_at(datetime(2026, 11, 9, 15, 59, tzinfo=dt_timezone.utc))

        self.assertEqual(calculate_user_stats(self.user)["joined_at"], "2026-11-09")

    def test_stats_api_uses_the_taiwan_date(self):
        self.register_at(datetime(2026, 11, 9, 20, 0, tzinfo=dt_timezone.utc))
        self.client.force_authenticate(user=self.user)

        response = self.client.get(STATS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["joined_at"], "2026-11-10")

    def test_falls_back_to_date_joined_when_registered_at_is_missing(self):
        self.user.registered_at = None
        self.user.date_joined = datetime(2026, 11, 9, 17, 0, tzinfo=dt_timezone.utc)

        self.assertEqual(calculate_user_stats(self.user)["joined_at"], "2026-11-10")


class BirthDateTests(APITestCase):
    """把「現在」固定在台灣 2030-01-01 01:00（UTC 2029-12-31 17:00）。"""

    NOW = datetime(2029, 12, 31, 17, 0, tzinfo=dt_timezone.utc)

    def setUp(self):
        self.user = User.objects.create_user(
            username="0912345678", password="Str0ng!Pass2026"
        )
        self.client.force_authenticate(user=self.user)

    def patch_birth_date(self, value):
        with patch("django.utils.timezone.now", return_value=self.NOW):
            return self.client.patch(ME_URL, {"birth_date": value}, format="json")

    def test_today_in_taiwan_is_accepted_even_though_utc_is_still_yesterday(self):
        response = self.patch_birth_date("2030-01-01")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_tomorrow_in_taiwan_is_rejected(self):
        response = self.patch_birth_date("2030-01-02")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("birth_date", response.data["error"]["fields"])

    def test_a_normal_past_date_is_accepted(self):
        response = self.patch_birth_date("1955-01-01")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
