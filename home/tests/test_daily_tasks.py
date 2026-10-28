"""今日任務：任務挑選、固定不變、done 計算、上週回顧。

「今天」都用參數或 mock 固定下來：
    MONDAY   = 2026-11-02（週一）
    TUESDAY  = 2026-11-03
上一週的週一是 2026-10-26。
"""

from datetime import date, datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from dashboard.models import WeeklyReport
from diary.models import Diary
from home import daily_tasks
from home.models import DailyTask

from .helpers import make_session

User = get_user_model()

MONDAY = date(2026, 11, 2)
TUESDAY = date(2026, 11, 3)
LAST_WEEK_START = date(2026, 10, 26)

URL = "/api/home/daily-tasks/"

SOURCES = [
    "market_route",  # attention
    "memory_recall",  # working_memory
    "market_sort",  # executive_function
    "fridge_check",  # visual_spatial
    "market_shopping",  # math
]


def taipei(*args):
    return timezone.make_aware(datetime(*args))


def fake_dimensions(**scores):
    """假的儀表板維度資料：有給分數的算已解鎖，沒給的算未解鎖。"""
    return [
        {
            "source": source,
            "unlocked": source in scores,
            "score": scores.get(source),
        }
        for source in SOURCES
    ]


def make_diary(user, created_at, status="done"):
    diary = Diary.objects.create(user=user, status=status)
    Diary.objects.filter(pk=diary.pk).update(created_at=created_at)
    return diary


class DailyTaskTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="x")

    def game_ids(self, today, dimensions=None):
        """產生（或讀取）今天的任務，回傳遊戲任務的 game_id（依順序）。"""
        with mock.patch(
            "home.daily_tasks.dashboard_services.get_dashboard_dimensions",
            return_value=dimensions or fake_dimensions(),
        ):
            tasks = daily_tasks.get_or_create_tasks(self.user, today)
        return [task.game_id for task in tasks if task.type == "game"]


class TaskSelectionTests(DailyTaskTestCase):
    def test_every_day_has_three_games_and_one_diary(self):
        with mock.patch(
            "home.daily_tasks.dashboard_services.get_dashboard_dimensions",
            return_value=fake_dimensions(),
        ):
            tasks = daily_tasks.get_or_create_tasks(self.user, MONDAY)

        self.assertEqual([t.type for t in tasks], ["game", "game", "game", "diary"])
        self.assertEqual(tasks[3].dimension, "language")
        self.assertIsNone(tasks[3].game_id)

    def test_new_user_gets_fixed_dimension_order(self):
        # 全部沒解鎖、本週都沒玩過 → 依 attention → working_memory → executive_function
        self.assertEqual(
            self.game_ids(MONDAY), ["market_route", "memory_recall", "market_sort"]
        )

    def test_game_tasks_carry_their_dimension(self):
        with mock.patch(
            "home.daily_tasks.dashboard_services.get_dashboard_dimensions",
            return_value=fake_dimensions(),
        ):
            tasks = daily_tasks.get_or_create_tasks(self.user, MONDAY)

        self.assertEqual(
            [(t.game_id, t.dimension) for t in tasks[:3]],
            [
                ("market_route", "attention"),
                ("memory_recall", "working_memory"),
                ("market_sort", "executive_function"),
            ],
        )

    def test_unplayed_dimensions_come_first(self):
        # 週一已玩過前三個 → 週二先推薦剩下沒玩過的 2 個，再補 1 個分數最低的
        for game_id in ["market_route", "memory_recall", "market_sort"]:
            make_session(self.user, game_id, created_at=taipei(2026, 11, 2, 9))
        dims = fake_dimensions(
            market_route=80, memory_recall=40, market_sort=60, fridge_check=90
        )

        self.assertEqual(
            self.game_ids(TUESDAY, dims),
            ["market_shopping", "fridge_check", "memory_recall"],
        )

    def test_lower_score_comes_first_within_the_same_group(self):
        dims = fake_dimensions(
            market_route=70,
            memory_recall=30,
            market_sort=50,
            fridge_check=90,
            market_shopping=60,
        )

        self.assertEqual(
            self.game_ids(MONDAY, dims),
            ["memory_recall", "market_sort", "market_shopping"],
        )

    def test_locked_dimension_counts_as_lowest(self):
        # market_route、memory_recall 已解鎖且分數低；其餘未解鎖 → 未解鎖的排前面
        dims = fake_dimensions(market_route=10, memory_recall=20)

        self.assertEqual(
            self.game_ids(MONDAY, dims),
            ["market_sort", "fridge_check", "market_shopping"],
        )

    def test_unlocked_but_no_recent_score_counts_as_lowest(self):
        dims = fake_dimensions(market_route=50, memory_recall=60, market_sort=70)
        dims[3]["unlocked"] = True  # fridge_check 已解鎖但近 7 天沒玩 → score 是 None

        self.assertEqual(self.game_ids(MONDAY, dims)[0], "fridge_check")

    def test_equal_scores_fall_back_to_fixed_order(self):
        dims = fake_dimensions(**{source: 50 for source in SOURCES})

        self.assertEqual(
            self.game_ids(MONDAY, dims),
            ["market_route", "memory_recall", "market_sort"],
        )

    def test_unfinished_play_does_not_count_as_played(self):
        make_session(
            self.user,
            "market_route",
            status="in_progress",
            created_at=taipei(2026, 11, 2, 9),
        )

        self.assertEqual(self.game_ids(TUESDAY)[0], "market_route")

    def test_last_weeks_play_does_not_count_as_played_this_week(self):
        make_session(self.user, "market_route", created_at=taipei(2026, 10, 30, 9))

        self.assertEqual(self.game_ids(MONDAY)[0], "market_route")


class StabilityTests(DailyTaskTestCase):
    def test_tasks_are_saved_once_and_reused_all_day(self):
        self.game_ids(MONDAY)
        first = list(
            DailyTask.objects.filter(user=self.user).values_list("id", "game_id")
        )

        self.game_ids(MONDAY)
        second = list(
            DailyTask.objects.filter(user=self.user).values_list("id", "game_id")
        )

        self.assertEqual(len(first), 4)
        self.assertEqual(first, second)

    def test_playing_a_game_does_not_reshuffle_todays_tasks(self):
        before = self.game_ids(MONDAY)

        make_session(self.user, "market_route", created_at=taipei(2026, 11, 2, 10))
        after = self.game_ids(MONDAY)

        self.assertEqual(before, after)

    def test_next_day_gets_a_new_set(self):
        self.game_ids(MONDAY)
        self.game_ids(TUESDAY)

        self.assertEqual(
            DailyTask.objects.filter(user=self.user, date=MONDAY).count(), 4
        )
        self.assertEqual(
            DailyTask.objects.filter(user=self.user, date=TUESDAY).count(), 4
        )

    def test_each_user_has_their_own_tasks(self):
        other = User.objects.create_user(username="other", password="x")
        self.game_ids(MONDAY)

        with mock.patch(
            "home.daily_tasks.dashboard_services.get_dashboard_dimensions",
            return_value=fake_dimensions(),
        ):
            daily_tasks.get_or_create_tasks(other, MONDAY)

        self.assertEqual(DailyTask.objects.filter(user=other).count(), 4)
        self.assertEqual(DailyTask.objects.filter(user=self.user).count(), 4)


class DoneTests(DailyTaskTestCase):
    def build(self, today):
        with mock.patch(
            "home.daily_tasks.dashboard_services.get_dashboard_dimensions",
            return_value=fake_dimensions(),
        ):
            return daily_tasks.build_response(self.user, today)

    def done_by_type(self, data):
        return {(t["type"], t["game_id"]): t["done"] for t in data["tasks"]}

    def test_nothing_done_at_first(self):
        data = self.build(MONDAY)

        self.assertEqual(data["completed_count"], 0)
        self.assertEqual(data["total_count"], 4)
        self.assertTrue(all(not t["done"] for t in data["tasks"]))

    def test_game_task_done_when_played_today(self):
        self.build(MONDAY)
        make_session(self.user, "market_route", created_at=taipei(2026, 11, 2, 15))

        data = self.build(MONDAY)

        self.assertTrue(self.done_by_type(data)[("game", "market_route")])
        self.assertFalse(self.done_by_type(data)[("game", "memory_recall")])
        self.assertEqual(data["completed_count"], 1)

    def test_game_played_yesterday_does_not_count_today(self):
        self.build(TUESDAY)
        make_session(self.user, "market_route", created_at=taipei(2026, 11, 2, 15))

        data = self.build(TUESDAY)

        self.assertFalse(self.done_by_type(data)[("game", "market_route")])

    def test_unfinished_game_is_not_done(self):
        self.build(MONDAY)
        make_session(
            self.user,
            "market_route",
            status="in_progress",
            created_at=taipei(2026, 11, 2, 15),
        )

        data = self.build(MONDAY)

        self.assertFalse(self.done_by_type(data)[("game", "market_route")])

    def test_diary_done_when_written_today(self):
        self.build(MONDAY)
        make_diary(self.user, taipei(2026, 11, 2, 20))

        data = self.build(MONDAY)

        self.assertTrue(self.done_by_type(data)[("diary", None)])

    def test_failed_diary_or_yesterdays_diary_is_not_done(self):
        self.build(MONDAY)
        make_diary(self.user, taipei(2026, 11, 2, 20), status="failed")
        make_diary(self.user, taipei(2026, 11, 1, 20))

        data = self.build(MONDAY)

        self.assertFalse(self.done_by_type(data)[("diary", None)])

    def test_diary_still_processing_counts_as_written(self):
        self.build(MONDAY)
        make_diary(self.user, taipei(2026, 11, 2, 20), status="processing")

        data = self.build(MONDAY)

        self.assertTrue(self.done_by_type(data)[("diary", None)])

    def test_weekly_progress_counts_distinct_dimensions_played_this_week(self):
        make_session(self.user, "market_route", created_at=taipei(2026, 11, 2, 9))
        make_session(self.user, "market_route", created_at=taipei(2026, 11, 2, 10))
        make_session(self.user, "fridge_check", created_at=taipei(2026, 11, 3, 9))

        data = self.build(TUESDAY)

        self.assertEqual(data["weekly_progress"], {"played_dimensions": 2, "goal": 5})

    def test_response_shape(self):
        data = self.build(MONDAY)

        self.assertEqual(data["date"], "2026-11-02")
        self.assertEqual(
            set(data["tasks"][0]),
            {"id", "type", "title", "game_id", "dimension", "done"},
        )
        self.assertEqual(data["tasks"][0]["title"], "玩「今天去菜市場」")
        self.assertEqual(data["tasks"][3]["title"], "寫一篇聲影日記")


class WeeklyReportTaskTests(DailyTaskTestCase):
    def build(self, today):
        with mock.patch(
            "home.daily_tasks.dashboard_services.get_dashboard_dimensions",
            return_value=fake_dimensions(),
        ):
            return daily_tasks.build_response(self.user, today)

    def types(self, data):
        return [t["type"] for t in data["tasks"]]

    def test_appears_when_last_week_has_records(self):
        make_session(self.user, "market_route", created_at=taipei(2026, 10, 28, 9))

        data = self.build(MONDAY)

        self.assertEqual(
            self.types(data), ["game", "game", "game", "diary", "weekly_report"]
        )
        report_task = data["tasks"][4]
        self.assertEqual(report_task["title"], "看看上週回顧")
        self.assertIsNone(report_task["game_id"])
        self.assertIsNone(report_task["dimension"])
        self.assertFalse(report_task["done"])

    def test_diary_alone_last_week_is_enough(self):
        make_diary(self.user, taipei(2026, 10, 28, 9))

        self.assertIn("weekly_report", self.types(self.build(MONDAY)))

    def test_does_not_appear_when_last_week_is_empty(self):
        self.assertNotIn("weekly_report", self.types(self.build(MONDAY)))

    def test_still_there_on_tuesday_if_not_opened(self):
        make_session(self.user, "market_route", created_at=taipei(2026, 10, 28, 9))
        self.build(MONDAY)

        self.assertIn("weekly_report", self.types(self.build(TUESDAY)))

    def test_done_on_the_day_it_is_opened_then_gone_next_day(self):
        make_session(self.user, "market_route", created_at=taipei(2026, 10, 28, 9))
        self.build(TUESDAY)  # 週二早上產生任務，這時還沒點開週報
        WeeklyReport.objects.create(
            user=self.user,
            week_start=LAST_WEEK_START,
            viewed_at=taipei(2026, 11, 3, 18),
        )

        same_day = self.build(TUESDAY)
        next_day = self.build(date(2026, 11, 4))

        self.assertTrue(same_day["tasks"][-1]["done"])
        self.assertEqual(same_day["tasks"][-1]["type"], "weekly_report")
        self.assertNotIn("weekly_report", self.types(next_day))

    def test_opened_before_first_home_visit_still_shows_done_that_day(self):
        make_session(self.user, "market_route", created_at=taipei(2026, 10, 28, 9))
        WeeklyReport.objects.create(
            user=self.user,
            week_start=LAST_WEEK_START,
            viewed_at=taipei(2026, 11, 3, 8),
        )

        data = self.build(TUESDAY)

        self.assertTrue(data["tasks"][-1]["done"])

    def test_report_row_without_viewed_at_does_not_count_as_viewed(self):
        make_session(self.user, "market_route", created_at=taipei(2026, 10, 28, 9))
        WeeklyReport.objects.create(user=self.user, week_start=LAST_WEEK_START)

        data = self.build(TUESDAY)

        self.assertFalse(data["tasks"][-1]["done"])

    def test_comes_back_next_monday_with_a_new_report(self):
        make_session(self.user, "market_route", created_at=taipei(2026, 10, 28, 9))
        WeeklyReport.objects.create(
            user=self.user,
            week_start=LAST_WEEK_START,
            viewed_at=taipei(2026, 11, 3, 18),
        )
        make_session(self.user, "market_route", created_at=taipei(2026, 11, 4, 9))

        next_monday = self.build(date(2026, 11, 9))

        self.assertIn("weekly_report", self.types(next_monday))
        self.assertFalse(next_monday["tasks"][-1]["done"])


class DailyTasksApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="x")
        self.client.force_authenticate(user=self.user)
        patcher = mock.patch("django.utils.timezone.localdate", return_value=MONDAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_requires_login(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "NOT_AUTHENTICATED")

    def test_new_user_gets_four_tasks(self):
        response = self.client.get(URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["date"], "2026-11-02")
        self.assertEqual(response.data["total_count"], 4)
        self.assertEqual(response.data["completed_count"], 0)
        self.assertEqual(
            response.data["weekly_progress"], {"played_dimensions": 0, "goal": 5}
        )

    def test_same_tasks_after_playing_but_task_is_checked(self):
        first = self.client.get(URL).data
        game_id = first["tasks"][0]["game_id"]

        make_session(self.user, game_id, created_at=taipei(2026, 11, 2, 12))
        second = self.client.get(URL).data

        self.assertEqual(
            [t["id"] for t in first["tasks"]], [t["id"] for t in second["tasks"]]
        )
        self.assertTrue(second["tasks"][0]["done"])
        self.assertEqual(second["completed_count"], 1)

    def test_other_users_do_not_see_each_others_tasks(self):
        self.client.get(URL)
        other = User.objects.create_user(username="other", password="x")
        self.client.force_authenticate(user=other)

        ids_other = {t["id"] for t in self.client.get(URL).data["tasks"]}
        ids_mine = set(
            DailyTask.objects.filter(user=self.user).values_list("id", flat=True)
        )

        self.assertFalse(ids_other & ids_mine)

    def test_opening_the_weekly_report_completes_the_task(self):
        """端到端：點開週報 API → 今日任務的「看看上週回顧」打勾"""
        make_session(self.user, "market_route", created_at=taipei(2026, 10, 28, 9))
        before = self.client.get(URL).data
        self.assertEqual(before["tasks"][-1]["type"], "weekly_report")
        self.assertFalse(before["tasks"][-1]["done"])

        report = self.client.get("/api/dashboard/weekly-report/")
        self.assertEqual(report.status_code, status.HTTP_200_OK)

        after = self.client.get(URL).data
        self.assertTrue(after["tasks"][-1]["done"])
        self.assertEqual(after["tasks"][-1]["id"], before["tasks"][-1]["id"])


class WeeklyReportRecordTests(APITestCase):
    """GET /api/dashboard/weekly-report/ 會把每一週的週報存下來"""

    URL = "/api/dashboard/weekly-report/"

    def setUp(self):
        self.user = User.objects.create_user(username="u", password="x")
        self.client.force_authenticate(user=self.user)
        patcher = mock.patch("django.utils.timezone.localdate", return_value=TUESDAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_first_open_creates_a_record_for_last_week(self):
        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        record = WeeklyReport.objects.get(user=self.user)
        self.assertEqual(record.week_start, LAST_WEEK_START)
        self.assertIsNotNone(record.viewed_at)
        self.assertEqual(
            record.report["week_start"], response.data["data"]["week_start"]
        )

    def test_opening_again_does_not_create_another_record(self):
        self.client.get(self.URL)
        first_viewed_at = WeeklyReport.objects.get(user=self.user).viewed_at

        self.client.get(self.URL)

        self.assertEqual(WeeklyReport.objects.filter(user=self.user).count(), 1)
        self.assertEqual(
            WeeklyReport.objects.get(user=self.user).viewed_at, first_viewed_at
        )

    def test_a_new_week_gets_its_own_record(self):
        self.client.get(self.URL)

        with mock.patch(
            "django.utils.timezone.localdate", return_value=date(2026, 11, 10)
        ):
            self.client.get(self.URL)

        self.assertEqual(
            sorted(WeeklyReport.objects.values_list("week_start", flat=True)),
            [LAST_WEEK_START, date(2026, 11, 2)],
        )

    def test_unauthenticated_request_creates_nothing(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(WeeklyReport.objects.exists())
