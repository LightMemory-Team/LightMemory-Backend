"""遊戲歷史的日期要用台灣時間（F11）。

遊戲結果的 completed_at 存 UTC。台灣是 UTC+8，所以台灣 00:00～08:00 玩的場次，
UTC 日期會比台灣日期少一天，不能直接切字串取日期。

執行：
    python manage.py test games.tests_local_date --settings=config.settings_test
"""

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from games.tests_list_user_sessions import FRIDGE, FRIDGE_RESULT, make_session
from games.utils import local_date_from_iso

User = get_user_model()


class LocalDateFromIsoTests(SimpleTestCase):
    def test_utc_evening_is_the_next_day_in_taiwan(self):
        # UTC 16:00 = 台灣隔天 00:00
        self.assertEqual(local_date_from_iso("2026-11-09T16:00:00+00:00"), "2026-11-10")
        self.assertEqual(
            local_date_from_iso("2026-11-09T17:30:45.123456+00:00"), "2026-11-10"
        )

    def test_just_before_midnight_in_taiwan_stays_the_same_day(self):
        self.assertEqual(local_date_from_iso("2026-11-09T15:59:59+00:00"), "2026-11-09")

    def test_utc_morning_is_the_same_day(self):
        self.assertEqual(local_date_from_iso("2026-11-09T01:00:00+00:00"), "2026-11-09")

    def test_already_taiwan_offset_is_kept(self):
        self.assertEqual(local_date_from_iso("2026-11-10T00:30:00+08:00"), "2026-11-10")
        self.assertEqual(local_date_from_iso("2026-11-09T23:30:00+08:00"), "2026-11-09")

    def test_other_offsets_are_converted(self):
        # 美東 2026-11-09 20:00（UTC-5）= UTC 隔天 01:00 = 台灣隔天 09:00
        self.assertEqual(local_date_from_iso("2026-11-09T20:00:00-05:00"), "2026-11-10")

    def test_month_and_year_boundaries(self):
        self.assertEqual(local_date_from_iso("2026-12-31T20:00:00+00:00"), "2027-01-01")
        self.assertEqual(local_date_from_iso("2026-02-28T16:00:00+00:00"), "2026-03-01")

    def test_without_timezone_falls_back_to_the_first_ten_characters(self):
        self.assertEqual(local_date_from_iso("2026-11-09T17:30:00"), "2026-11-09")

    def test_unparseable_values_fall_back_without_raising(self):
        self.assertEqual(local_date_from_iso("2026-11-09 not a time"), "2026-11-09")
        self.assertEqual(local_date_from_iso("2026-13-45T99:99:99+00:00"), "2026-13-45")
        self.assertEqual(local_date_from_iso(""), "")


class FridgeCheckHistoryDateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="me", password="Str0ng!Pass2026")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def history(self):
        response = self.client.get("/api/games/fridge-check/history/")
        self.assertEqual(response.status_code, 200)
        return response.data["data"]["history"]

    def test_played_date_is_the_taiwan_date(self):
        completed_at = "2026-11-09T17:30:00+00:00"  # 台灣 11/10 01:30
        make_session(
            FRIDGE, self.user, result={**FRIDGE_RESULT, "completed_at": completed_at}
        )

        item = self.history()[0]

        self.assertEqual(item["played_date"], "2026-11-10")

    def test_timestamps_are_returned_unchanged(self):
        completed_at = "2026-11-09T17:30:00+00:00"
        make_session(
            FRIDGE, self.user, result={**FRIDGE_RESULT, "completed_at": completed_at}
        )

        item = self.history()[0]

        self.assertEqual(item["played_at"], completed_at)
        self.assertEqual(item["completed_at"], completed_at)

    def test_daytime_session_keeps_its_date(self):
        make_session(
            FRIDGE,
            self.user,
            result={**FRIDGE_RESULT, "completed_at": "2026-11-09T05:00:00+00:00"},
        )

        self.assertEqual(self.history()[0]["played_date"], "2026-11-09")
