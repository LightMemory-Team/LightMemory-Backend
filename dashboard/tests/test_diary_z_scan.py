"""日記語言 z 的全站掃描次數與結果一致性測試（F9）。

重點：
- 新版（先算一次、再篩選期間）的結果，和舊版逐次現算的結果完全一樣
- 沒有有效日記的使用者不會掃全站
- 一次儀表板／週報請求只掃一次全站日記（原本最多 4 次）

執行：
    python manage.py test dashboard.tests.test_diary_z_scan --settings=config.settings_test
"""

import random
from datetime import timedelta
from itertools import groupby
from operator import itemgetter
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from diary.models import Diary, DiaryAnalysis
from users.models import User

from .. import services
# 借用 test_dashboard_api 的測試資料 helper；只 import 模組、不 import 類別，避免被重複執行
from . import test_dashboard_api as dashboard_tests
from ..diary_zscore import METRIC_RULES, calculate_language_z_score


def make_diary(user, created_at, rng, *, is_valid=True, audio_path=""):
    diary = Diary.objects.create(user=user, status="done", audio_path=audio_path)
    Diary.objects.filter(pk=diary.pk).update(created_at=created_at)
    scores = {
        name: round(rng.uniform(0, 4), 2) if is_valid else None for name in METRIC_RULES
    }
    DiaryAnalysis.objects.create(diary=diary, is_valid=is_valid, **scores)
    return diary


def reference_diary_z_scores(user, start=None, end=None):
    """舊版 diary_z_scores 的原樣照抄（修改前的實作），當對照組。"""
    analyses = DiaryAnalysis.objects.filter(is_valid=True)
    if end is not None:
        analyses = analyses.filter(diary__created_at__lt=end)
    rows = analyses.order_by("diary__created_at").values(
        "diary__user_id",
        "diary__created_at",
        "diary__user__is_staff",
        "diary__audio_path",
        *METRIC_RULES,
    )
    personal_history, population_by_user = [], {}
    results = []
    for created_at, same_time_rows in groupby(
        rows, key=itemgetter("diary__created_at")
    ):
        same_time_rows = list(same_time_rows)
        in_period = start is None or created_at >= start
        for row in same_time_rows:
            if in_period and row["diary__user_id"] == user.id:
                z_score = calculate_language_z_score(
                    row, personal_history, population_by_user
                )
                if z_score is not None:
                    results.append((created_at, z_score))
        for row in same_time_rows:
            if row["diary__user_id"] == user.id:
                personal_history.append(row)
            elif services._counts_for_population(row):
                population_by_user.setdefault(row["diary__user_id"], []).append(row)
    return results


class DiaryZScoreEquivalenceTests(TestCase):
    """新版和舊版的結果必須完全一樣（含期間篩選）。"""

    def setUp(self):
        rng = random.Random(2026)
        self.now = timezone.now()
        users = {
            name: User.objects.create_user(username=name, password="pw123456")
            for name in ("a", "b", "c")
        }
        self.staff = User.objects.create_user(
            username="staff", password="pw123456", is_staff=True
        )
        self.demo = User.objects.create_user(username="demo", password="pw123456")
        self.me = users["a"]
        self.other_user_without_diaries = User.objects.create_user(
            username="nobody", password="pw123456"
        )

        # 打散在 200 天裡，彼此交錯；每人 8 篇，另外有測試帳號與 demo 日記
        for days_ago in range(200, 0, -5):
            who = rng.choice(list(users.values()))
            make_diary(who, self.now - timedelta(days=days_ago), rng)
        for days_ago in (150, 90, 40):
            make_diary(self.staff, self.now - timedelta(days=days_ago), rng)
            make_diary(
                self.demo,
                self.now - timedelta(days=days_ago),
                rng,
                audio_path="seed/x.m4a",
            )
        # 同一時間建立的日記（彼此不互相比）
        same_time = self.now - timedelta(days=60)
        for who in users.values():
            make_diary(who, same_time, rng)
        # 自己的無效日記不算
        make_diary(self.me, self.now - timedelta(days=30), rng, is_valid=False)
        # 自己最新一篇之後，別人還有更晚的日記（不該影響自己的結果）
        for days_ago in (3, 2, 1):
            make_diary(users["b"], self.now - timedelta(days=days_ago), rng)

    def periods(self):
        day = timedelta(days=1)
        return [
            (None, None),
            (self.now - 90 * day, None),
            (None, self.now - 30 * day),
            (self.now - 120 * day, self.now - 20 * day),
            (self.now - 10 * day, self.now),
            (self.now + day, None),
        ]

    def test_same_as_the_old_algorithm_for_every_period(self):
        compared_non_empty = 0
        for who in (self.me, User.objects.get(username="b"), self.staff):
            for start, end in self.periods():
                with self.subTest(user=who.username, start=start, end=end):
                    expected = reference_diary_z_scores(who, start, end)
                    actual = services.diary_z_scores(who, start, end)

                    self.assertEqual(actual, expected)
                    compared_non_empty += bool(expected)
        # 確認這份資料真的算得出 z，比較才有意義
        self.assertGreater(compared_non_empty, 5)

    def test_precomputed_scores_give_the_same_result_without_querying(self):
        scores = services.diary_z_scores(self.me)

        with CaptureQueriesContext(connection) as ctx:
            result = services.diary_z_scores(
                self.me, start=self.now - timedelta(days=90), scores=scores
            )

        self.assertEqual(len(ctx), 0)
        self.assertEqual(
            result,
            reference_diary_z_scores(self.me, start=self.now - timedelta(days=90)),
        )

    def test_average_and_unlock_progress_match_the_old_way(self):
        scores = services.diary_z_scores(self.me)
        start = self.now - timedelta(days=90)

        self.assertEqual(
            services.average_diary_z_score(self.me, start=start, scores=scores),
            services.average_diary_z_score(self.me, start=start),
        )
        self.assertEqual(
            services.get_unlock_progress(self.me, diary_scores=scores),
            services.get_unlock_progress(self.me),
        )
        end = self.now - timedelta(days=50)
        self.assertEqual(
            services.get_unlock_progress(self.me, end=end, diary_scores=scores),
            services.get_unlock_progress(self.me, end=end),
        )

    def assert_does_not_touch_anyone_elses_diaries(self, user):
        """沒有有效日記的使用者：只問一次「他有沒有」，不載入、不處理任何別人的日記。"""
        with (
            patch.object(
                services,
                "_counts_for_population",
                wraps=services._counts_for_population,
            ) as population_spy,
            CaptureQueriesContext(connection) as ctx,
        ):
            result = services.diary_z_scores(user)

        self.assertEqual(result, [])
        self.assertEqual(population_spy.call_count, 0)
        self.assertEqual(len(ctx), 1)
        self.assertIn("MAX(", ctx.captured_queries[0]["sql"].upper())

    def test_user_without_diaries_does_not_scan_everyone(self):
        self.assert_does_not_touch_anyone_elses_diaries(self.other_user_without_diaries)

    def test_user_with_only_invalid_diaries_does_not_scan_everyone(self):
        invalid_only = User.objects.create_user(
            username="invalid_only", password="pw123456"
        )
        make_diary(
            invalid_only, self.now - timedelta(days=5), random.Random(1), is_valid=False
        )

        self.assert_does_not_touch_anyone_elses_diaries(invalid_only)

    def test_diaries_after_the_users_latest_one_are_not_loaded(self):
        """他最新一篇之後的日記不會影響他的結果，所以不讀。"""
        with patch.object(
            services, "_counts_for_population", wraps=services._counts_for_population
        ) as spy:
            services.diary_z_scores(self.me)

        later_than_my_last = Diary.objects.filter(
            created_at__gt=Diary.objects.filter(user=self.me, analysis__is_valid=True)
            .order_by("-created_at")
            .first()
            .created_at
        ).count()
        total_other_rows = (
            DiaryAnalysis.objects.filter(is_valid=True)
            .exclude(diary__user=self.me)
            .count()
        )
        self.assertGreater(later_than_my_last, 0)
        self.assertLessEqual(spy.call_count, total_other_rows - later_than_my_last)


class ScanCountTests(APITestCase):
    """一次請求只掃一次全站日記。"""

    setUp = dashboard_tests.DashboardApiTests.setUp
    _finished_session = dashboard_tests.DashboardApiTests._finished_session
    _diary = dashboard_tests.DashboardApiTests._diary
    _unlock_diaries = dashboard_tests.DashboardApiTests._unlock_diaries
    _unlock_all_games = dashboard_tests.DashboardApiTests._unlock_all_games

    def scan_count(self, url):
        with patch.object(
            services, "_compute_diary_z_scores", wraps=services._compute_diary_z_scores
        ) as spy:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return spy.call_count, response

    def test_dashboard_scans_once_even_with_the_encouragement_card(self):
        self._unlock_all_games()

        count, response = self.scan_count("/api/dashboard/")

        # 機器人卡片有內容，代表有走到「週分數歷史」那條路徑
        self.assertIsNotNone(response.data["data"]["encouragement"])
        self.assertEqual(count, 1)

    def test_dashboard_scans_once_for_a_new_user(self):
        count, _ = self.scan_count("/api/dashboard/")

        self.assertEqual(count, 1)

    def test_weekly_report_scans_once(self):
        self._unlock_all_games()

        count, _ = self.scan_count("/api/dashboard/weekly-report/")

        self.assertEqual(count, 1)

    def test_dashboard_response_does_not_depend_on_sharing_the_scan(self):
        self._unlock_all_games()
        response = self.client.get("/api/dashboard/")
        dimensions = {d["dimension"]: d for d in response.data["data"]["dimensions"]}

        self.assertTrue(dimensions["language"]["unlocked"])
        expected_count = len(reference_diary_z_scores(self.user))
        self.assertEqual(dimensions["language"]["valid_count"], expected_count)
