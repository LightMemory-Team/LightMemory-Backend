from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from home.tests.helpers import make_session
from rewards import services

User = get_user_model()


class RewardsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="elder", password="x")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_requires_login(self):
        anon = APIClient()
        for path in ["summary/", "achievements/", "points/history/"]:
            response = anon.get(f"/api/rewards/{path}")
            self.assertEqual(response.status_code, 401)
            self.assertFalse(response.json()["success"])

    def test_summary_for_new_user(self):
        data = self.client.get("/api/rewards/summary/").json()
        self.assertTrue(data["success"])
        self.assertEqual(
            data["data"],
            {
                "total_points": 0,
                "today_points": 0,
                "daily_cap": 100,
                "daily_remaining": 100,
                "achievements_unlocked": 0,
                "achievements_total": 25,
            },
        )

    def test_summary_after_playing(self):
        services.grant(self.user, services.GAME_FINISH, make_session(self.user, "fridge_check"))
        data = self.client.get("/api/rewards/summary/").json()["data"]
        self.assertEqual(data["today_points"], 10)
        self.assertEqual(data["daily_remaining"], 90)
        self.assertEqual(data["total_points"], 20)  # 10 + 成就 10
        self.assertEqual(data["achievements_unlocked"], 1)

    def test_achievement_wall_groups_and_progress(self):
        services.grant(self.user, services.GAME_FINISH, make_session(self.user, "fridge_check"))
        data = self.client.get("/api/rewards/achievements/").json()["data"]
        categories = data["categories"]
        self.assertEqual([c["category"] for c in categories], ["exploration", "training", "milestone"])
        self.assertEqual([len(c["achievements"]) for c in categories], [10, 3, 12])
        explore = {a["code"]: a for a in categories[0]["achievements"]}
        done = explore["first_fridge_check"]
        self.assertTrue(done["unlocked"])
        self.assertIsNotNone(done["unlocked_at"])
        self.assertEqual(done["progress"], {"current": 1, "target": 1})
        locked = explore["first_market_route"]
        self.assertFalse(locked["unlocked"])
        self.assertIsNone(locked["unlocked_at"])
        self.assertEqual(locked["progress"], {"current": 0, "target": 1})
        milestone = {a["code"]: a for a in categories[2]["achievements"]}
        self.assertEqual(milestone["play30_fridge_check"]["progress"], {"current": 1, "target": 30})
        self.assertEqual(milestone["games_100"]["progress"], {"current": 1, "target": 100})

    def test_points_history_paging_and_hides_zero_rows(self):
        for _ in range(12):
            services.grant(self.user, services.GAME_FINISH, make_session(self.user, "fridge_check"))
        # 超過每日上限的紀錄 amount=0，不能出現在列表裡
        data = self.client.get("/api/rewards/points/history/").json()["data"]
        self.assertEqual(len(data["items"]), 10)
        self.assertTrue(all(item["amount"] > 0 for item in data["items"]))
        self.assertIsNotNone(data["pagination"]["next"])
        self.assertIsNone(data["pagination"]["previous"])
        count = data["pagination"]["count"]
        page2 = self.client.get("/api/rewards/points/history/?page=2&page_size=10").json()["data"]
        self.assertEqual(page2["pagination"]["count"], count)
        self.assertIsNotNone(page2["pagination"]["previous"])
        first = data["items"][0]
        self.assertEqual(set(first), {"id", "reason", "label", "amount", "created_at"})
        big = self.client.get("/api/rewards/points/history/?page_size=999").json()["data"]
        self.assertLessEqual(len(big["items"]), 50)
        beyond = self.client.get("/api/rewards/points/history/?page=99").json()["data"]
        self.assertEqual(beyond["items"], [])

    def test_bad_page_param(self):
        response = self.client.get("/api/rewards/points/history/?page=abc")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_PARAM")
