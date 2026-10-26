"""儀表板 API（GET /api/dashboard/）的測試。

直接在資料庫建立「已結束、帶 z_score」的場次，不用真的去玩五款遊戲。
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from diary.models import Diary, DiaryAnalysis
from games import session_service
from games.models import GameSession
from users.models import User

from .services import DIMENSIONS, GAME_SOURCES, REQUIRED_SESSIONS

DASHBOARD_URL = "/api/dashboard/"


class DashboardApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw123456")
        self.client.force_authenticate(user=self.user)
        # 日記用固定的「現在」：同一個 days_ago 建立時間完全相同，不會互相比
        self.now = timezone.now()

    def _finished_session(self, game, z_score, *, user=None, days_ago=1):
        """建立一場 days_ago 天前結束、結算結果帶 z_score 的場次。"""
        session_id = session_service.create_session(game, user=user or self.user)[
            "session_id"
        ]
        GameSession.objects.filter(pk=session_id).update(
            status="finished",
            result={"z_score": z_score},
            finished_at=timezone.now() - timedelta(days=days_ago),
        )

    def _diary(self, sub_score, *, user=None, days_ago=1, is_valid=True):
        """建立一篇 days_ago 天前的日記，5 個小分數都是 sub_score。

        _unlock_all_games 會先建好歷史（平均 2、標準差 1），
        這篇的語言 z 就是 sub_score − 2。
        """
        diary = Diary.objects.create(user=user or self.user, status="done")
        Diary.objects.filter(pk=diary.pk).update(
            created_at=self.now - timedelta(days=days_ago)
        )
        scores = {
            name: (sub_score if is_valid else None)
            for name in (
                "fluency_score",
                "information_score",
                "sentence_score",
                "naming_score",
                "semantic_score",
            )
        }
        DiaryAnalysis.objects.create(diary=diary, is_valid=is_valid, **scores)

    def _unlock_diaries(self):
        """寫 6 篇超過 7 天的日記，其中 3 篇有語言 z，滿足日記的解鎖條件。

        31 天前 0.5、2、3.5：自己沒有更早的日記，算不出 z
        8 天前 1.5、2、2.5：同一時間建立，都跟前 3 篇比 → 有 z
        6 篇合起來平均 2、標準差 1，之後的日記語言 z 就是小分數 − 2；
        都超過 7 天，不會算進語言軸的平均。
        """
        for value in (0.5, 2, 3.5):
            self._diary(value, days_ago=31)
        for value in (1.5, 2, 2.5):
            self._diary(value, days_ago=8)

    def _unlock_all_games(self, z_score=0.0, days_ago=1, *, diaries=True):
        """五款遊戲各玩 REQUIRED_SESSIONS 場、寫滿日記，讓儀表板解鎖。"""
        for game in GAME_SOURCES:
            for _ in range(REQUIRED_SESSIONS):
                self._finished_session(game, z_score, days_ago=days_ago)
        if diaries:
            self._unlock_diaries()

    def _dimension(self, response, dimension):
        return next(
            d
            for d in response.data["data"]["dimensions"]
            if d["dimension"] == dimension
        )

    # ---- 錯誤回傳 ----

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(DASHBOARD_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "NOT_AUTHENTICATED")

    def test_no_data_is_insufficient(self):
        response = self.client.get(DASHBOARD_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "INSUFFICIENT_DATA")
        data = response.data["data"]
        self.assertEqual(data["required_sessions"], 3)
        # 五款遊戲＋聲影日記
        self.assertEqual(
            [p["source"] for p in data["progress"]], [*GAME_SOURCES, "diary"]
        )
        self.assertTrue(all(p["session_count"] == 0 for p in data["progress"]))

    def test_one_game_with_two_sessions_is_insufficient(self):
        self._unlock_all_games()
        # 煮菜過程刪到只剩 2 場
        GameSession.objects.filter(game__code="memory_recall").first().delete()

        response = self.client.get(DASHBOARD_URL)

        self.assertEqual(response.data["error"]["code"], "INSUFFICIENT_DATA")
        progress = {p["source"]: p for p in response.data["data"]["progress"]}
        self.assertEqual(progress["memory_recall"]["session_count"], 2)
        self.assertEqual(progress["memory_recall"]["label"], "煮菜過程")
        self.assertEqual(progress["market_route"]["session_count"], 3)

    def test_sessions_without_z_score_do_not_count(self):
        self._unlock_all_games()
        GameSession.objects.filter(game__code="memory_recall").first().delete()
        # 前測、歷史不足的場次 z_score 是 None，不算進解鎖的 3 場
        self._finished_session("memory_recall", None)

        response = self.client.get(DASHBOARD_URL)

        self.assertEqual(response.data["error"]["code"], "INSUFFICIENT_DATA")

    def test_in_progress_sessions_do_not_count(self):
        self._unlock_all_games()
        GameSession.objects.filter(game__code="memory_recall").first().delete()
        session_service.create_session("memory_recall", user=self.user)

        response = self.client.get(DASHBOARD_URL)

        self.assertEqual(response.data["error"]["code"], "INSUFFICIENT_DATA")

    def test_other_users_sessions_do_not_count(self):
        other = User.objects.create_user(username="other", password="pw123456")
        for game in GAME_SOURCES:
            for _ in range(REQUIRED_SESSIONS):
                self._finished_session(game, 1.0, user=other)

        response = self.client.get(DASHBOARD_URL)

        self.assertEqual(response.data["error"]["code"], "INSUFFICIENT_DATA")

    # ---- 解鎖後的資料 ----

    def test_unlocked_returns_six_dimensions_in_order(self):
        self._unlock_all_games()

        response = self.client.get(DASHBOARD_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIsNone(response.data["error"])
        data = response.data["data"]
        self.assertEqual(data["period_days"], 7)
        self.assertEqual(
            [d["dimension"] for d in data["dimensions"]],
            [d["dimension"] for d in DIMENSIONS],
        )

    def test_average_of_recent_sessions(self):
        self._unlock_all_games(z_score=0.0)
        self._finished_session("market_route", 1.5)

        response = self.client.get(DASHBOARD_URL)

        attention = self._dimension(response, "attention")
        # (0 + 0 + 0 + 1.5) / 4 = 0.375
        self.assertEqual(attention["z_score"], 0.375)
        self.assertEqual(attention["session_count"], 4)
        self.assertEqual(attention["source"], "market_route")
        self.assertEqual(attention["label"], "注意力")

    def test_sessions_older_than_seven_days_excluded_from_average(self):
        self._unlock_all_games(z_score=0.0)
        self._finished_session("market_route", 2.0, days_ago=8)

        attention = self._dimension(self.client.get(DASHBOARD_URL), "attention")

        self.assertEqual(attention["z_score"], 0.0)
        self.assertEqual(attention["session_count"], 3)

    def test_unlocked_but_not_played_recently_is_null(self):
        # 10 天前就解鎖了，但近 7 天都沒玩：照樣顯示儀表板，各軸 z 是 null
        self._unlock_all_games(days_ago=10)

        response = self.client.get(DASHBOARD_URL)

        self.assertTrue(response.data["success"])
        math = self._dimension(response, "math")
        self.assertIsNone(math["z_score"])
        self.assertEqual(math["session_count"], 0)

    # ---- 語言軸（聲影日記）----

    def test_diary_required_to_unlock(self):
        # 遊戲都玩滿了，但沒寫日記 → 還是資料不足
        self._unlock_all_games(diaries=False)

        response = self.client.get(DASHBOARD_URL)

        self.assertEqual(response.data["error"]["code"], "INSUFFICIENT_DATA")
        progress = {p["source"]: p for p in response.data["data"]["progress"]}
        self.assertEqual(progress["diary"]["label"], "聲影日記")
        self.assertEqual(progress["diary"]["session_count"], 0)
        self.assertEqual(progress["market_route"]["session_count"], 3)

    def test_diaries_without_z_score_do_not_count(self):
        # 只寫了 3 篇，沒有更早的日記可比，算不出語言 z → 不算
        self._unlock_all_games(diaries=False)
        for value in (1, 2, 3):
            self._diary(value, days_ago=10)

        response = self.client.get(DASHBOARD_URL)

        self.assertEqual(response.data["error"]["code"], "INSUFFICIENT_DATA")
        progress = {p["source"]: p for p in response.data["data"]["progress"]}
        self.assertEqual(progress["diary"]["session_count"], 0)

    def test_language_null_without_recent_diary(self):
        # 解鎖用的日記都超過 7 天，近 7 天沒寫 → 語言軸是 null
        self._unlock_all_games()

        response = self.client.get(DASHBOARD_URL)

        self.assertTrue(response.data["success"])
        language = self._dimension(response, "language")
        self.assertEqual(language["source"], "diary")
        self.assertIsNone(language["z_score"])
        self.assertEqual(language["session_count"], 0)

    def test_language_is_average_of_recent_diaries(self):
        self._unlock_all_games()
        # 兩篇同一時間建立，都只跟歷史比
        self._diary(3)  # 語言 z = +1
        self._diary(2.5)  # 語言 z = +0.5

        language = self._dimension(self.client.get(DASHBOARD_URL), "language")

        # (1 + 0.5) / 2 = 0.75
        self.assertEqual(language["z_score"], 0.75)
        self.assertEqual(language["session_count"], 2)

    def test_language_excludes_invalid_old_and_other_users_diaries(self):
        self._unlock_all_games()  # 8 天前那 3 篇有 z，但超過 7 天不算平均
        self._diary(3)  # 語言 z = +1，唯一算進去的
        self._diary(4, is_valid=False)  # 無效日記（錄音太短等）
        other = User.objects.create_user(username="other", password="pw123456")
        self._diary(0, user=other)

        language = self._dimension(self.client.get(DASHBOARD_URL), "language")

        self.assertEqual(language["z_score"], 1.0)
        self.assertEqual(language["session_count"], 1)

    def test_diaries_do_not_unlock_dashboard(self):
        # 日記寫再多，遊戲沒玩滿還是資料不足
        for _ in range(5):
            self._diary(3)

        response = self.client.get(DASHBOARD_URL)

        self.assertEqual(response.data["error"]["code"], "INSUFFICIENT_DATA")
