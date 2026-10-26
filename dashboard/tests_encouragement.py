"""encouragement.py（儀表板機器人卡片的總體趨勢）的測試。

場次日期用「這週週一往前推 k 週」建立。每週 5 款遊戲用同一個 z，
那週的分數就是 50 + 25z，例如 z 0.4 → 60、0.8 → 70、1.2 → 80。
"""

from datetime import date, datetime, time, timedelta
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from diary.models import Diary, DiaryAnalysis
from games import session_service
from games.models import GameSession
from users.models import User

from .diary_zscore import METRIC_RULES as LANGUAGE_METRIC_RULES
from .encouragement import get_encouragement, weighted_overall_score
from .services import GAME_SOURCES, REQUIRED_SESSIONS

DASHBOARD_URL = "/api/dashboard/"


class WeightedOverallScoreTests(SimpleTestCase):
    WEEK_1 = date(2026, 10, 5)
    WEEK_2 = date(2026, 10, 12)
    WEEK_3 = date(2026, 10, 19)

    def test_recent_weeks_weigh_more(self):
        scores = {self.WEEK_1: 60, self.WEEK_2: 70, self.WEEK_3: 80}
        # (60 x 0.64 + 70 x 0.8 + 80 x 1) / (0.64 + 0.8 + 1) ≈ 71.5 → 71
        self.assertEqual(weighted_overall_score(scores, self.WEEK_3), 71)

    def test_weeks_after_base_week_are_ignored(self):
        scores = {self.WEEK_1: 60, self.WEEK_2: 70, self.WEEK_3: 80}
        # (60 x 0.8 + 70 x 1) / (0.8 + 1) ≈ 65.6 → 66
        self.assertEqual(weighted_overall_score(scores, self.WEEK_2), 66)

    def test_empty_weeks_still_count_as_distance(self):
        # WEEK_1 跟 WEEK_3 差 2 週 → 權重 0.8 x 0.8 = 0.64
        scores = {self.WEEK_1: 60, self.WEEK_3: 80}
        # (60 x 0.64 + 80 x 1) / 1.64 ≈ 72.2 → 72
        self.assertEqual(weighted_overall_score(scores, self.WEEK_3), 72)

    def test_no_data_is_none(self):
        self.assertIsNone(weighted_overall_score({}, self.WEEK_3))


class GetEncouragementTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="grandma", password="pw123456")
        today = timezone.localdate()
        self.this_monday = today - timedelta(days=today.weekday())

    def _week_time(self, weeks_ago):
        """那週週一 00:30（台灣時間）。"""
        day = self.this_monday - timedelta(weeks=weeks_ago)
        return timezone.make_aware(datetime.combine(day, time(0, 30)))

    def _finished(self, game, z_score, weeks_ago):
        session_id = session_service.create_session(game, user=self.user)["session_id"]
        moment = self._week_time(weeks_ago)
        GameSession.objects.filter(pk=session_id).update(
            status="finished",
            result={"z_score": z_score},
            created_at=moment - timedelta(minutes=5),
            finished_at=moment,
        )

    def _diary(self, sub_score, weeks_ago):
        diary = Diary.objects.create(user=self.user, status="done")
        Diary.objects.filter(pk=diary.pk).update(created_at=self._week_time(weeks_ago))
        DiaryAnalysis.objects.create(
            diary=diary,
            is_valid=True,
            **{name: sub_score for name in LANGUAGE_METRIC_RULES},
        )

    def _week_of_games(self, z_score, weeks_ago, times=1):
        for game in GAME_SOURCES:
            for _ in range(times):
                self._finished(game, z_score, weeks_ago)

    def _unlock(self, z_score, weeks_ago, *, diaries=REQUIRED_SESSIONS):
        """6 個能力都在 weeks_ago 那週玩滿 3 次，每個能力的 z 都是 z_score。

        日記：很久以前先寫 3 篇（小分數 1、2、3 → 平均 2、標準差 1，自己沒有 z），
        再在那週同一時間寫 diaries 篇小分數 2 + z 的日記（同時建立不互相比，
        語言 z 都剛好是 z）。
        """
        self._week_of_games(z_score, weeks_ago, times=REQUIRED_SESSIONS)
        for sub_score in (1, 2, 3):
            self._diary(sub_score, weeks_ago=52)
        for _ in range(diaries):
            self._diary(2 + z_score, weeks_ago)

    def test_diaries_not_enough_is_none(self):
        # 5 款遊戲都滿 3 場，但有分數的日記只有 2 篇
        self._unlock(0.4, weeks_ago=0, diaries=2)

        self.assertIsNone(get_encouragement(self.user))

    def test_only_one_week_has_no_trend(self):
        self._unlock(0.4, weeks_ago=0)

        self.assertEqual(
            get_encouragement(self.user),
            {"trend": None, "overall_score": 60, "previous_overall_score": None},
        )

    def test_improving_over_three_weeks_is_up(self):
        self._unlock(0.4, weeks_ago=2)  # 60
        self._week_of_games(0.8, weeks_ago=1)  # 70
        self._week_of_games(1.2, weeks_ago=0)  # 80

        self.assertEqual(
            get_encouragement(self.user),
            {"trend": "up", "overall_score": 71, "previous_overall_score": 66},
        )

    def test_small_change_is_steady(self):
        self._unlock(0.4, weeks_ago=1)  # 60
        self._week_of_games(0.48, weeks_ago=0)  # 62
        # (60 x 0.8 + 62) / 1.8 ≈ 61.1 → 61，跟 60 只差 1

        encouragement = get_encouragement(self.user)

        self.assertEqual(encouragement["overall_score"], 61)
        self.assertEqual(encouragement["trend"], "steady")

    def test_dropping_is_practice(self):
        self._unlock(0.4, weeks_ago=1)  # 60
        self._week_of_games(0.0, weeks_ago=0)  # 50
        # (60 x 0.8 + 50) / 1.8 ≈ 54.4 → 54，比 60 少 6

        encouragement = get_encouragement(self.user)

        self.assertEqual(encouragement["overall_score"], 54)
        self.assertEqual(encouragement["trend"], "practice")

    def test_previous_skips_weeks_without_data(self):
        self._unlock(0.4, weeks_ago=3)  # 60，中間兩週沒玩
        self._week_of_games(1.2, weeks_ago=0)  # 80
        # 現在：(60 x 0.8³ + 80) / (0.512 + 1) ≈ 73.2 → 73
        # 上一個有資料的週是 3 週前 → 60

        self.assertEqual(
            get_encouragement(self.user),
            {"trend": "up", "overall_score": 73, "previous_overall_score": 60},
        )

    def test_language_counts_in_weekly_score(self):
        self._unlock(0.4, weeks_ago=1)  # 60
        # 這週只寫一篇日記，沒玩遊戲：
        # 更早的日記 1、2、3、2.4、2.4、2.4 → 平均 2.2、標準差 0.669
        # z = (2.4 − 2.2) / 0.669 ≈ 0.299 → 57 分
        self._diary(2.4, weeks_ago=0)
        # (60 x 0.8 + 57) / 1.8 ≈ 58.3 → 58

        encouragement = get_encouragement(self.user)

        self.assertEqual(encouragement["overall_score"], 58)
        self.assertEqual(encouragement["previous_overall_score"], 60)

    def test_dashboard_api_includes_encouragement(self):
        self._unlock(0.4, weeks_ago=0)
        self.client.force_authenticate(user=self.user)

        response = self.client.get(DASHBOARD_URL)

        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["encouragement"]["overall_score"], 60)

    def test_dashboard_api_locked_has_no_encouragement(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(DASHBOARD_URL)

        self.assertEqual(response.data["error"]["code"], "INSUFFICIENT_DATA")
        self.assertNotIn("encouragement", response.data["data"])


class SeedDemoEncouragementTests(TestCase):
    def test_seed_demo_has_encouragement(self):
        call_command("seed_demo", stdout=StringIO())
        user = User.objects.get(username="demo")

        self.assertIsNotNone(get_encouragement(user))
