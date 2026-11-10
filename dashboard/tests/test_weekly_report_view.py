"""週報 GET（/api/dashboard/weekly-report/）的重複點開行為（F10）。

重點：
- 同一週重複點開，不再每次呼叫 AI（餵給 AI 的事實沒變就沿用上次的總結）
- 內容沒變、viewed_at 也記過了，就完全不寫資料庫
- 事實變了會重新產生；AI 失敗留下的固定句型下次會重試
- 快照裡的內部欄位不會出現在 API 回應

執行：
    python manage.py test dashboard.tests.test_weekly_report_view \
        --settings=config.settings_test
"""

from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from ai_service.weekly_summary import build_fallback_summary
from users.models import User

from ..models import WeeklyReport
from ..weekly_report import SUMMARY_FACTS_KEY

URL = "/api/dashboard/weekly-report/"
GENERATE = "dashboard.weekly_report.generate_weekly_summary"
FACTS = "dashboard.weekly_report.build_positive_facts"


class WeeklyReportViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw123456")
        self.client.force_authenticate(user=self.user)

    def get(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        return response

    def record(self):
        return WeeklyReport.objects.get(user=self.user)

    def writes(self, func):
        """執行 func，回傳過程中寫入資料庫的 SQL（INSERT／UPDATE／DELETE）。"""
        with CaptureQueriesContext(connection) as ctx:
            func()
        return [
            q["sql"]
            for q in ctx.captured_queries
            if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        ]

    @patch(GENERATE, return_value="AI 寫的總結")
    def test_first_open_creates_one_record_with_viewed_at(self, generate):
        self.get()

        record = self.record()
        self.assertIsNotNone(record.viewed_at)
        self.assertEqual(record.report["summary"], "AI 寫的總結")

    @patch(GENERATE, return_value="AI 寫的總結")
    def test_internal_facts_are_in_the_snapshot_but_not_in_the_response(self, generate):
        response = self.get()

        self.assertNotIn(SUMMARY_FACTS_KEY, response.data["data"])
        self.assertIn(SUMMARY_FACTS_KEY, self.record().report)

    @patch(GENERATE, return_value="AI 寫的總結")
    def test_opening_again_does_not_call_the_ai_again(self, generate):
        first = self.get()
        second = self.get()
        third = self.get()

        self.assertEqual(generate.call_count, 1)
        self.assertEqual(first.data["data"]["summary"], "AI 寫的總結")
        self.assertEqual(second.data, first.data)
        self.assertEqual(third.data, first.data)

    @patch(GENERATE, return_value="AI 寫的總結")
    def test_opening_again_writes_nothing_to_the_database(self, generate):
        self.get()

        writes = self.writes(self.get)

        self.assertEqual(writes, [])
        self.assertEqual(WeeklyReport.objects.filter(user=self.user).count(), 1)

    @patch(GENERATE, return_value="AI 寫的總結")
    def test_viewed_at_is_only_recorded_the_first_time(self, generate):
        self.get()
        first_viewed_at = self.record().viewed_at

        self.get()

        self.assertEqual(self.record().viewed_at, first_viewed_at)

    @patch(GENERATE, side_effect=["第一句總結", "第二句總結"])
    @patch(FACTS, side_effect=[{"active_day_count": 1}, {"active_day_count": 2}])
    def test_changed_facts_produce_a_new_summary(self, facts, generate):
        first = self.get()
        first_viewed_at = self.record().viewed_at

        second = self.get()

        self.assertEqual(first.data["data"]["summary"], "第一句總結")
        self.assertEqual(second.data["data"]["summary"], "第二句總結")
        self.assertEqual(generate.call_count, 2)
        record = self.record()
        self.assertEqual(record.report["summary"], "第二句總結")
        self.assertEqual(record.report[SUMMARY_FACTS_KEY], {"active_day_count": 2})
        self.assertEqual(record.viewed_at, first_viewed_at)

    @patch(GENERATE)
    @patch(FACTS, return_value={"active_day_count": 3})
    def test_a_fallback_sentence_from_a_failed_ai_is_retried(self, facts, generate):
        fallback = build_fallback_summary({"active_day_count": 3})
        generate.side_effect = [fallback, "AI 這次寫成功了"]

        first = self.get()
        second = self.get()
        third = self.get()

        self.assertEqual(first.data["data"]["summary"], fallback)
        self.assertEqual(second.data["data"]["summary"], "AI 這次寫成功了")
        self.assertEqual(third.data["data"]["summary"], "AI 這次寫成功了")
        self.assertEqual(generate.call_count, 2)

    @patch(GENERATE, return_value="AI 寫的總結")
    def test_changed_content_updates_the_snapshot_without_calling_the_ai(
        self, generate
    ):
        diaries = [
            {"talk_seconds": 0, "entries": []},
            {"talk_seconds": 60, "entries": [{"diary_id": 1, "photo_url": ""}]},
        ]
        with patch("dashboard.weekly_report.get_week_diaries", side_effect=diaries):
            self.get()
            first_viewed_at = self.record().viewed_at

            writes = self.writes(self.get)

        record = self.record()
        self.assertEqual(record.report["diary"]["talk_seconds"], 60)
        self.assertEqual(record.viewed_at, first_viewed_at)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(len(writes), 1)  # 只有快照那一次 UPDATE

    @patch(GENERATE, return_value="AI 寫的總結")
    def test_record_without_viewed_at_gets_it_on_the_next_open(self, generate):
        self.get()
        WeeklyReport.objects.filter(user=self.user).update(viewed_at=None)

        self.get()

        self.assertIsNotNone(self.record().viewed_at)

    @patch(GENERATE, return_value="AI 寫的總結")
    def test_other_users_are_not_affected(self, generate):
        self.get()
        other = User.objects.create_user(username="other", password="pw123456")
        self.client.force_authenticate(user=other)

        self.get()

        self.assertEqual(generate.call_count, 2)
        self.assertEqual(WeeklyReport.objects.count(), 2)
