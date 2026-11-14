from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from diary.models import Diary
from home import daily_tasks
from home.tests.helpers import make_session
from rewards import services
from rewards.models import PointTransaction, UserAchievement

User = get_user_model()


def amounts(user, reason):
    return list(
        PointTransaction.objects.filter(user=user, reason=reason).values_list(
            "amount", flat=True
        )
    )


class GrantTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="elder", password="x")
        self.today = timezone.localdate()
        # 沒有任何紀錄時，三個遊戲任務依固定順序：
        # market_route、memory_recall、market_sort（再加一篇日記）
        self.tasks = daily_tasks.get_or_create_tasks(self.user, self.today)

    def finish(self, game_code):
        session = make_session(self.user, game_code)
        return services.grant(self.user, services.GAME_FINISH, session)

    def test_game_in_daily_tasks_gets_game_and_task_points(self):
        rewards = self.finish("market_route")
        reasons = [item["reason"] for item in rewards["breakdown"]]
        self.assertEqual(reasons, ["game_complete", "daily_task"])
        self.assertEqual(rewards["points_earned"], 15)
        self.assertFalse(rewards["daily_cap_reached"])
        # 第一次完成「初次上市場」成就：+10，不算在 points_earned 裡
        codes = [a["code"] for a in rewards["new_achievements"]]
        self.assertIn("first_market_route", codes)
        self.assertEqual(rewards["total_points"], 15 + 10)

    def test_game_not_in_daily_tasks_only_gets_game_points(self):
        rewards = self.finish("fridge_check")
        self.assertEqual([i["reason"] for i in rewards["breakdown"]], ["game_complete"])
        self.assertEqual(rewards["points_earned"], 10)

    def test_same_session_twice_only_pays_once(self):
        session = make_session(self.user, "market_route")
        first = services.grant(self.user, services.GAME_FINISH, session)
        total = services.total_points(self.user)
        again = services.grant(self.user, services.GAME_FINISH, session)
        self.assertEqual(first["points_earned"], 15)
        self.assertEqual(again["points_earned"], 0)
        self.assertEqual(again["breakdown"], [])
        self.assertEqual(again["new_achievements"], [])
        self.assertEqual(again["total_points"], total)

    def test_second_play_of_same_task_game_does_not_repeat_task_bonus(self):
        self.finish("market_route")
        second = self.finish("market_route")
        self.assertEqual([i["reason"] for i in second["breakdown"]], ["game_complete"])

    def test_all_tasks_done_bonus(self):
        self.finish("market_route")
        self.finish("memory_recall")
        rewards = self.finish("market_sort")
        self.assertNotIn("all_tasks_done", [i["reason"] for i in rewards["breakdown"]])
        diary = Diary.objects.create(user=self.user, status="done")
        rewards = services.grant(self.user, services.DIARY_COMPLETE, diary)
        reasons = [i["reason"] for i in rewards["breakdown"]]
        self.assertEqual(reasons, ["diary_complete", "daily_task", "all_tasks_done"])
        self.assertEqual(rewards["points_earned"], 15 + 5 + 20)
        self.assertEqual(amounts(self.user, "all_tasks_done"), [20])
        self.assertIn("first_all_tasks", [a["code"] for a in rewards["new_achievements"]])
        # 全部完成的當天不會再發第二次
        again = self.finish("market_route")
        self.assertNotIn("all_tasks_done", [i["reason"] for i in again["breakdown"]])

    def test_daily_cap_is_100_and_achievements_are_not_counted(self):
        for _ in range(10):
            self.finish("fridge_check")
        self.assertEqual(services.today_points(self.user), 100)
        rewards = self.finish("fridge_check")
        self.assertEqual(rewards["points_earned"], 0)
        self.assertTrue(rewards["daily_cap_reached"])
        self.assertEqual(rewards["breakdown"], [])
        # 超過上限也記帳（amount=0），重複呼叫不會再發
        self.assertEqual(services.today_points(self.user), 100)
        # 成就點數另外算，不受上限影響
        self.assertTrue(
            PointTransaction.objects.filter(
                user=self.user, reason="achievement_unlock"
            ).exists()
        )
        self.assertGreater(services.total_points(self.user), 100)

    def test_cap_partially_pays_the_remainder(self):
        for _ in range(9):
            self.finish("fridge_check")
        diary = Diary.objects.create(user=self.user, status="done")
        rewards = services.grant(self.user, services.DIARY_COMPLETE, diary)
        # 已有 90 點，日記 15 點只剩 10 點額度；日記任務 +5 已無額度
        self.assertEqual(rewards["points_earned"], 10)
        self.assertTrue(rewards["daily_cap_reached"])

    def test_all_tasks_fact_survives_the_cap(self):
        for _ in range(7):
            self.finish("fridge_check")  # 70 點
        self.finish("market_route")  # +10 +5 = 85
        self.finish("memory_recall")  # +10 +5 = 100（滿）
        self.finish("market_sort")  # 沒額度，但仍要記帳
        diary = Diary.objects.create(user=self.user, status="done")
        services.grant(self.user, services.DIARY_COMPLETE, diary)
        # 沒領到 20 點，但「今天任務全部完成」這件事要留下來
        self.assertEqual(amounts(self.user, "all_tasks_done"), [0])
        self.assertTrue(UserAchievement.objects.filter(user=self.user, code="first_all_tasks").exists())

    def test_dashboard_viewed_unlocks_once(self):
        first = services.grant(self.user, services.DASHBOARD_VIEWED)
        self.assertEqual([a["code"] for a in first["new_achievements"]], ["first_dashboard"])
        self.assertEqual(first["points_earned"], 0)
        self.assertEqual(first["total_points"], 10)
        second = services.grant(self.user, services.DASHBOARD_VIEWED)
        self.assertEqual(second["new_achievements"], [])
        self.assertEqual(second["total_points"], 10)

    def test_week_and_day_games_achievements(self):
        for code in ["market_route", "memory_recall", "market_sort"]:
            rewards = self.finish(code)
        codes = [a["code"] for a in rewards["new_achievements"]]
        self.assertIn("day_three_games", codes)  # 同一天 3 款
        self.finish("fridge_check")
        self.finish("market_shopping")  # 到這裡 5 款都玩過
        self.assertTrue(
            UserAchievement.objects.filter(user=self.user, code="week_all_games").exists()
        )

    def test_weekly_report_viewed_gives_task_points(self):
        from dashboard.models import WeeklyReport

        # 讓「看看上週回顧」任務出現：上週要有紀錄
        make_session(
            self.user, "market_route", created_at=timezone.now() - timedelta(days=7)
        )
        # 任務是當天第一次呼叫時才產生，這裡 setUp 已經產生過，所以先清掉重來
        from home.models import DailyTask

        DailyTask.objects.filter(user=self.user).delete()
        tasks = daily_tasks.get_or_create_tasks(self.user, self.today)
        self.assertIn("weekly_report", [t.type for t in tasks])
        week_start = daily_tasks.weekly_report.get_report_week(self.today)[0]
        WeeklyReport.objects.create(
            user=self.user, week_start=week_start, viewed_at=timezone.now()
        )
        rewards = services.grant(self.user, services.WEEKLY_REPORT_VIEWED)
        self.assertEqual([i["reason"] for i in rewards["breakdown"]], ["daily_task"])
        self.assertIn("first_weekly_report", [a["code"] for a in rewards["new_achievements"]])

    def test_failure_returns_empty_block_and_does_not_raise(self):
        with mock.patch("rewards.services._grant", side_effect=RuntimeError("boom")):
            with self.assertLogs("rewards.services", level="ERROR"):
                rewards = services.grant(self.user, services.DASHBOARD_VIEWED)
        self.assertEqual(rewards["points_earned"], 0)
        self.assertEqual(rewards["breakdown"], [])
        self.assertEqual(rewards["new_achievements"], [])

    def test_users_are_isolated(self):
        other = User.objects.create_user(username="other", password="x")
        self.finish("market_route")
        self.assertEqual(services.total_points(other), 0)
