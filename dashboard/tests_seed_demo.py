"""seed_demo 指令（python manage.py seed_demo）的測試。

週報的測試把「現在」固定成 2026-10-21（三）中午，報告週就是
10/12（一）～10/18（日），比較週是 10/5～10/11。
"""

from datetime import datetime, time
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from diary.models import Diary, DiaryAnalysis
from games.fridge_check.services import get_history as fridge_check_history
from games.market_shopping.services import get_history as market_shopping_history
from games.models import Game, GameSession
from users.models import User

from .services import (
    GAME_SOURCES,
    get_dashboard_dimensions,
    get_unlock_progress,
    is_unlocked,
)
from .weekly_report import build_weekly_report

FIXED_NOW = timezone.make_aware(datetime.combine(datetime(2026, 10, 21), time(12)))


def seed(**options):
    call_command("seed_demo", stdout=StringIO(), **options)
    return User.objects.get(username=options.get("username", "demo"))


class SeedDemoDataTests(TestCase):
    def test_creates_demo_account(self):
        user = seed()
        self.assertTrue(user.check_password("demo1234"))

    def test_creates_all_five_games(self):
        seed()
        self.assertEqual(
            set(Game.objects.values_list("code", flat=True)), set(GAME_SOURCES)
        )

    def test_three_per_batch_for_each_game(self):
        user = seed()
        for code in GAME_SOURCES:
            sessions = GameSession.objects.filter(user=user, game__code=code)
            # 前週、上週、這週各 3 場
            self.assertEqual(sessions.count(), 9)
            for result in sessions.values_list("result", flat=True):
                self.assertIsNotNone(result["z_score"])
        self.assertFalse(
            GameSession.objects.filter(user=user).exclude(status="finished").exists()
        )

    def test_three_diaries_per_batch(self):
        # 暖身、前週、上週、這週各 3 篇
        user = seed()
        self.assertEqual(Diary.objects.filter(user=user, status="done").count(), 12)
        self.assertEqual(
            DiaryAnalysis.objects.filter(diary__user=user, is_valid=True).count(), 12
        )

    def test_scores_are_fifty_plus_twenty_five_z(self):
        user = seed()
        score_fields = {
            "market_sort": "cognitive_flexibility_score",
            "fridge_check": "standard_score",
            "market_shopping": "standard_score",
            "memory_recall": "total_score",
        }
        for code, field in score_fields.items():
            for result in GameSession.objects.filter(
                user=user, game__code=code
            ).values_list("result", flat=True):
                self.assertEqual(
                    result[field], round(50 + 25 * result["z_score"]), code
                )

    def test_no_high_risk_diary(self):
        user = seed()
        self.assertFalse(
            DiaryAnalysis.objects.filter(diary__user=user, risk_level="high").exists()
        )

    def test_rerun_does_not_duplicate(self):
        seed()
        user = seed()
        self.assertEqual(GameSession.objects.filter(user=user).count(), 45)
        self.assertEqual(Diary.objects.filter(user=user).count(), 12)

    def test_rerun_keeps_real_records(self):
        user = seed()
        real_session = GameSession.objects.create(
            game=Game.objects.get(code="market_route"), user=user
        )
        real_diary = Diary.objects.create(user=user, title="真的日記")

        seed()

        self.assertTrue(GameSession.objects.filter(pk=real_session.pk).exists())
        self.assertTrue(Diary.objects.filter(pk=real_diary.pk).exists())

    def test_custom_username(self):
        user = seed(username="grandma", password="pw123456")
        self.assertTrue(user.check_password("pw123456"))
        self.assertEqual(GameSession.objects.filter(user=user).count(), 45)


class SeedDemoDashboardTests(TestCase):
    def test_dashboard_unlocked_with_every_dimension(self):
        user = seed()

        self.assertTrue(is_unlocked(get_unlock_progress(user)))
        # 這週那批在近 7 天內，雷達圖 6 個軸（含語言）都有分數
        for dimension in get_dashboard_dimensions(user):
            self.assertIsNotNone(dimension["z_score"], dimension["source"])

    def test_game_history_apis_work(self):
        # 歷史紀錄 API 用 result["欄位"] 取值，缺欄位會 KeyError
        user = seed()
        self.assertTrue(fridge_check_history(user.id))
        self.assertTrue(market_shopping_history(user.id))


@patch("dashboard.weekly_report.generate_weekly_summary", return_value="很棒")
class SeedDemoWeeklyReportTests(TestCase):
    def setUp(self):
        with patch("django.utils.timezone.now", return_value=FIXED_NOW):
            self.user = seed()
        self.today = timezone.localdate(FIXED_NOW)

    def test_report_week_has_three_active_days(self, mock_summary):
        report = build_weekly_report(self.user, self.today)

        self.assertEqual(report["week_start"], "2026-10-12")
        self.assertEqual(report["highlights"]["active_day_count"], 3)
        self.assertEqual(len(report["diary"]["entries"]), 3)
        self.assertGreater(report["play_time"]["total_seconds"], 0)
        self.assertGreater(report["diary"]["talk_seconds"], 0)

    def test_one_more_day_than_previous_week(self, mock_summary):
        build_weekly_report(self.user, self.today)

        facts = mock_summary.call_args.args[0]
        self.assertEqual(facts["more_days"], 1)

    def test_every_ability_has_trend(self, mock_summary):
        report = build_weekly_report(self.user, self.today)

        self.assertEqual(report["abilities"]["overall"]["trend"], "up")
        for dimension in report["abilities"]["dimensions"]:
            self.assertIsNotNone(dimension["trend"], dimension["label"])
