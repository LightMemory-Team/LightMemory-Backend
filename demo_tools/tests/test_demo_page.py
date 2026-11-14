"""後台「維護任務」頁（/admin/demo/）與 setup_admin_demo 指令的測試。

執行：
    python manage.py test demo_tools --settings=config.settings_test
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from diary.models import Diary
from games.models import GameSession
from rewards.models import PointTransaction, UserAchievement
from social.models import Comment, Notification, Post
from users.models import User

from ..constants import DEMO_NICKNAME, DEMO_PASSWORD, DEMO_USERNAME

URL = reverse("admin-demo")


class SetupAdminDemoCommandTests(TestCase):
    def test_creates_superuser_with_nickname_and_password(self):
        call_command("setup_admin_demo", stdout=StringIO())

        user = User.objects.get(username=DEMO_USERNAME)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertEqual(user.nickname, DEMO_NICKNAME)
        self.assertTrue(user.check_password(DEMO_PASSWORD))

    def test_running_again_resets_password(self):
        call_command("setup_admin_demo", stdout=StringIO())
        user = User.objects.get(username=DEMO_USERNAME)
        user.set_password("changed")
        user.save()

        call_command("setup_admin_demo", stdout=StringIO())

        user.refresh_from_db()
        self.assertTrue(user.check_password(DEMO_PASSWORD))
        self.assertEqual(User.objects.filter(username=DEMO_USERNAME).count(), 1)


class DemoPageAccessTests(TestCase):
    def test_anonymous_is_sent_to_admin_login(self):
        response = self.client.get(URL)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])

    def test_staff_without_superuser_is_forbidden(self):
        staff = User.objects.create_user(username="staff", password="pw", is_staff=True)
        self.client.force_login(staff)

        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_superuser_sees_page_and_admin_index_links_to_it(self):
        admin_user = User.objects.create_superuser(username="boss", password="pw")
        self.client.force_login(admin_user)

        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "產生三個月遊戲＋日記紀錄")

        index = self.client.get(reverse("admin:index"))
        self.assertContains(index, URL)


class DemoTaskTests(TestCase):
    def setUp(self):
        call_command("setup_admin_demo", stdout=StringIO())
        self.demo = User.objects.get(username=DEMO_USERNAME)
        self.client.force_login(self.demo)

    def run_task(self, task):
        return self.client.post(URL, {"task": task}, follow=True)

    def test_seed_history_creates_games_and_diaries_and_can_repeat(self):
        for _ in range(2):  # 按兩次結果一樣，不會越按越多
            response = self.run_task("seed_history")

            self.assertContains(response, "已產生遊戲紀錄 150 場、聲影日記 30 篇")
            self.assertEqual(
                GameSession.objects.filter(user=self.demo, status="finished").count(),
                150,
            )
            self.assertEqual(Diary.objects.filter(user=self.demo).count(), 30)

    def test_share_comments_without_diary_shows_hint(self):
        response = self.run_task("seed_share_comments")

        self.assertContains(response, "請先按")
        self.assertFalse(Post.objects.exists())

    def test_share_comments_creates_post_comments_and_notifications(self):
        self.run_task("seed_history")

        for _ in range(2):
            self.run_task("seed_share_comments")

        post = Post.objects.get(user=self.demo)
        self.assertEqual(Comment.objects.filter(post=post).count(), 3)
        self.assertEqual(
            Notification.objects.filter(
                user=self.demo, notification_type="comment"
            ).count(),
            3,
        )
        # 狀態表上有分享頁網址
        response = self.client.get(URL)
        self.assertContains(response, f"/share/{post.share_token}/")

    def test_rewards_gives_points_and_achievements(self):
        self.run_task("seed_history")

        self.run_task("seed_rewards")
        first_total = sum(
            PointTransaction.objects.filter(user=self.demo).values_list(
                "amount", flat=True
            )
        )
        self.run_task("seed_rewards")  # 重按點數一樣
        second_total = sum(
            PointTransaction.objects.filter(user=self.demo).values_list(
                "amount", flat=True
            )
        )

        self.assertGreater(first_total, 0)
        self.assertEqual(first_total, second_total)
        self.assertTrue(UserAchievement.objects.filter(user=self.demo).exists())

    def test_clear_all_removes_demo_data_but_keeps_account_and_other_users(self):
        other = User.objects.create_user(username="elder", password="pw")
        other_diary = Diary.objects.create(user=other, status="done")
        self.run_task("seed_history")
        self.run_task("seed_share_comments")
        self.run_task("seed_rewards")

        response = self.run_task("clear_all")

        self.assertContains(response, "已清除")
        self.assertFalse(GameSession.objects.filter(user=self.demo).exists())
        self.assertFalse(Diary.objects.filter(user=self.demo).exists())
        self.assertFalse(Post.objects.filter(user=self.demo).exists())
        self.assertFalse(Notification.objects.filter(user=self.demo).exists())
        self.assertFalse(PointTransaction.objects.filter(user=self.demo).exists())
        self.assertTrue(User.objects.filter(username=DEMO_USERNAME).exists())
        self.assertTrue(Diary.objects.filter(pk=other_diary.pk).exists())

    def test_unknown_task_shows_error(self):
        response = self.run_task("drop_database")

        self.assertContains(response, "找不到這個任務")


class ScoreAlertTaskTests(TestCase):
    """產生分數極端值：儀表板 API 的 alerts 要真的出現「建議多注意」的小提醒。"""

    def setUp(self):
        call_command("setup_admin_demo", stdout=StringIO())
        self.demo = User.objects.get(username=DEMO_USERNAME)
        self.client.force_login(self.demo)

    def press(self, game_code):
        return self.client.post(
            URL, {"task": "seed_score_alert", "choice": game_code}, follow=True
        )

    def dashboard_alerts(self):
        api = APIClient()
        api.force_authenticate(user=self.demo)
        return api.get("/api/dashboard/").data["data"]["alerts"]

    def test_page_has_game_dropdown(self):
        response = self.client.get(URL)

        self.assertContains(response, '<select name="choice"')
        self.assertContains(response, 'value="fridge_check"')

    def test_creates_low_score_session_and_dashboard_shows_alert(self):
        response = self.press("fridge_check")

        self.assertContains(response, "儀表板會出現小提醒")
        alerts = self.dashboard_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["game_id"], "fridge_check")
        self.assertIn("建議多注意", alerts[0]["message"])
        # 狀態表也看得到
        self.assertContains(self.client.get(URL), "1 則")

    def test_pressing_same_game_twice_keeps_one_session(self):
        self.press("market_route")
        self.press("market_route")

        self.assertEqual(
            GameSession.objects.filter(
                user=self.demo, client_session_id__contains="alert"
            ).count(),
            1,
        )
        self.assertEqual(len(self.dashboard_alerts()), 1)

    def test_different_games_add_more_alerts(self):
        self.press("fridge_check")
        self.press("market_route")

        games = {alert["game_id"] for alert in self.dashboard_alerts()}
        self.assertEqual(games, {"fridge_check", "market_route"})

    def test_alert_still_shows_after_seeding_history(self):
        self.client.post(URL, {"task": "seed_history"})
        self.press("memory_recall")

        games = [alert["game_id"] for alert in self.dashboard_alerts()]
        self.assertEqual(games, ["memory_recall"])

    def test_unknown_game_shows_hint(self):
        response = self.press("chess")

        self.assertContains(response, "請先選擇")
        self.assertFalse(GameSession.objects.filter(user=self.demo).exists())
