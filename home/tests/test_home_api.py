"""GET /api/home/user/ 與 GET /api/home/games/"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from games.catalog import GAMES
from social.models import Notification

from .helpers import make_session

User = get_user_model()

USER_URL = "/api/home/user/"
GAMES_URL = "/api/home/games/"


class HomeUserTests(APITestCase):
    def test_requires_login(self):
        response = self.client.get(USER_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_returns_nickname_of_logged_in_user_not_first_user(self):
        User.objects.create_user(username="first", password="x", nickname="別人")
        me = User.objects.create_user(username="me", password="x", nickname="玉蘭")
        self.client.force_authenticate(user=me)

        response = self.client.get(USER_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data, {"user_name": "玉蘭", "unread_notification_count": 0}
        )

    def test_legacy_account_without_nickname_falls_back(self):
        legacy = User.objects.create_user(
            username="old", password="x", last_name="林", first_name="奶奶"
        )
        bare = User.objects.create_user(username="0912345678", password="x")

        self.client.force_authenticate(user=legacy)
        self.assertEqual(self.client.get(USER_URL).data["user_name"], "林奶奶")

        self.client.force_authenticate(user=bare)
        self.assertEqual(self.client.get(USER_URL).data["user_name"], "0912345678")


class HomeUnreadCountTests(APITestCase):
    """鈴鐺的未讀數要和通知 API 的 unread_count 一致"""

    def setUp(self):
        self.user = User.objects.create_user(username="u", password="x")
        self.other = User.objects.create_user(username="o", password="x")
        self.client.force_authenticate(user=self.user)

    def make(self, user, is_read=False):
        return Notification.objects.create(
            user=user, notification_type="comment", message="有人留言", is_read=is_read
        )

    def test_counts_only_own_unread_notifications(self):
        self.make(self.user)
        self.make(self.user)
        self.make(self.user, is_read=True)
        self.make(self.other)

        response = self.client.get(USER_URL)

        self.assertEqual(response.data["unread_notification_count"], 2)

    def test_matches_notification_unread_count_api(self):
        self.make(self.user)

        home = self.client.get(USER_URL).data["unread_notification_count"]
        social = self.client.get("/api/social/notifications/unread_count/").data[
            "data"
        ]["unread_notification_count"]

        self.assertEqual(home, social)

    def test_becomes_zero_after_mark_all_read(self):
        self.make(self.user)

        self.client.patch("/api/social/notifications/")

        self.assertEqual(self.client.get(USER_URL).data["unread_notification_count"], 0)


class HomeGamesTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="x")
        self.client.force_authenticate(user=self.user)

    def games(self):
        return {g["id"]: g for g in self.client.get(GAMES_URL).data["games"]}

    def test_requires_login(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(GAMES_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_returns_every_developed_game_with_played_flag(self):
        response = self.client.get(GAMES_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["games"]), len(GAMES))
        for game in response.data["games"]:
            self.assertIn("id", game)
            self.assertIn("title", game)
            self.assertTrue(game["name"])
            self.assertIs(game["played_this_week"], False)

    def test_every_game_has_its_dimension_label(self):
        games = self.games()

        expected = {
            "market_route": ("attention", "注意力"),
            "memory_recall": ("working_memory", "工作記憶"),
            "market_sort": ("executive_function", "執行功能"),
            "fridge_check": ("visual_spatial", "視覺空間"),
            "market_shopping": ("math", "數學"),
        }
        for game_id, (dimension, label) in expected.items():
            self.assertEqual(games[game_id]["dimension"], dimension)
            self.assertEqual(games[game_id]["dimension_label"], label)

    def test_played_this_week_true_after_finishing_a_game(self):
        make_session(self.user, "fridge_check")

        games = self.games()

        self.assertIs(games["fridge_check"]["played_this_week"], True)
        self.assertIs(games["market_sort"]["played_this_week"], False)

    def test_unfinished_session_does_not_count(self):
        make_session(self.user, "fridge_check", status="in_progress")

        self.assertIs(self.games()["fridge_check"]["played_this_week"], False)

    def test_last_weeks_play_does_not_count(self):
        # 固定「現在」是週三，上週的紀錄不算本週
        wednesday = timezone.make_aware(timezone.datetime(2026, 11, 4, 12, 0))
        make_session(
            self.user, "fridge_check", created_at=wednesday - timedelta(days=7)
        )

        with mock.patch("django.utils.timezone.now", return_value=wednesday):
            games = self.games()

        self.assertIs(games["fridge_check"]["played_this_week"], False)

    def test_other_users_play_does_not_count(self):
        other = User.objects.create_user(username="other", password="x")
        make_session(other, "fridge_check")

        self.assertIs(self.games()["fridge_check"]["played_this_week"], False)

    def test_response_has_no_wall_posts(self):
        """新首頁已經沒有動態牆區塊"""
        response = self.client.get(GAMES_URL)

        self.assertNotIn("wall_posts", response.data)
