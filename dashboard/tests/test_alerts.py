"""儀表板「小提醒」（dashboard/alerts.py、GET /api/dashboard/ 的 alerts）的測試。

直接在資料庫建立「已結束、帶 z_score」的場次，不用真的去玩遊戲。
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from games import session_service
from games.models import GameSession
from users.models import User

from ..alerts import ALERT_LOOKBACK_DAYS, MAX_ALERTS, get_score_alerts
from ..services import GAME_SOURCES

DASHBOARD_URL = "/api/dashboard/"


class ScoreAlertTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw123456")
        # 固定的「現在」：場次時間都從這裡往前推，結果不受執行時間影響
        self.now = timezone.now()

    def _session(self, game, z_score, *, days_ago=1, is_pretest=False, user=None):
        """建立一場 days_ago 天前結束、結算結果帶 z_score 的場次。"""
        session_id = session_service.create_session(
            game, user=user or self.user, is_pretest=is_pretest
        )["session_id"]
        GameSession.objects.filter(pk=session_id).update(
            status="finished",
            result={"z_score": z_score},
            finished_at=self.now - timedelta(days=days_ago),
        )
        return session_id

    def alerts(self):
        return get_score_alerts(self.user, now=self.now)

    def test_no_sessions_no_alerts(self):
        self.assertEqual(self.alerts(), [])

    def test_normal_score_is_not_alerted(self):
        self._session("market_route", -1.4)
        self._session("market_sort", 1.8)

        self.assertEqual(self.alerts(), [])

    def test_low_score_gives_one_alert_with_all_fields(self):
        self._session("market_shopping", -1.5, days_ago=2)

        [alert] = self.alerts()

        self.assertEqual(alert["game_id"], "market_shopping")
        self.assertEqual(alert["game_title"], "市場買菜")
        self.assertEqual(alert["dimension"], "math")
        self.assertEqual(alert["dimension_label"], "數學")
        # z = -1.5 → 50 + 25 × (-1.5) = 12.5，四捨五入到偶數為 12
        self.assertEqual(alert["display_score"], 12)
        played_at = timezone.localtime(self.now - timedelta(days=2))
        self.assertEqual(alert["played_at"], played_at)
        self.assertIn(f"{played_at.month}/{played_at.day}", alert["message"])
        self.assertIn("「市場買菜」", alert["message"])

    def test_message_uses_gentle_wording(self):
        self._session("fridge_check", -2.0)

        message = self.alerts()[0]["message"]

        self.assertIn("比平常低一些", message)
        for word in ("異常", "退化", "退步", "失智"):
            self.assertNotIn(word, message)

    def test_sessions_older_than_lookback_are_ignored(self):
        self._session("market_route", -2.0, days_ago=ALERT_LOOKBACK_DAYS + 1)

        self.assertEqual(self.alerts(), [])

    def test_session_without_z_score_is_ignored(self):
        self._session("market_route", None)

        self.assertEqual(self.alerts(), [])

    def test_pretest_session_is_ignored(self):
        self._session("market_route", -2.0, is_pretest=True)

        self.assertEqual(self.alerts(), [])

    def test_unfinished_session_is_ignored(self):
        session_id = self._session("market_route", -2.0)
        GameSession.objects.filter(pk=session_id).update(status="in_progress")

        self.assertEqual(self.alerts(), [])

    def test_other_users_sessions_are_ignored(self):
        other = User.objects.create_user(username="other", password="pw123456")
        self._session("market_route", -2.0, user=other)

        self.assertEqual(self.alerts(), [])

    def test_same_game_only_shows_the_latest_low_session(self):
        self._session("memory_recall", -1.9, days_ago=8)
        self._session("memory_recall", -1.6, days_ago=3)
        # 最近一場正常，不影響「最近一場偏低」的提醒
        self._session("memory_recall", 0.5, days_ago=1)

        [alert] = self.alerts()

        self.assertEqual(alert["display_score"], 10)  # z = -1.6
        self.assertEqual(
            alert["played_at"], timezone.localtime(self.now - timedelta(days=3))
        )

    def test_newest_first_and_at_most_max_alerts(self):
        for days_ago, game in enumerate(GAME_SOURCES, start=1):
            self._session(game, -2.0, days_ago=days_ago)

        alerts = self.alerts()

        self.assertEqual(len(alerts), MAX_ALERTS)
        self.assertEqual([a["game_id"] for a in alerts], GAME_SOURCES[:MAX_ALERTS])


class DashboardAlertsApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw123456")
        self.client.force_authenticate(user=self.user)

    def test_alerts_is_an_empty_list_when_nothing_to_alert(self):
        data = self.client.get(DASHBOARD_URL).data["data"]

        self.assertEqual(data["alerts"], [])

    def test_alerts_appear_in_dashboard_response(self):
        session_id = session_service.create_session("market_route", user=self.user)[
            "session_id"
        ]
        GameSession.objects.filter(pk=session_id).update(
            status="finished",
            result={"z_score": -1.8},
            finished_at=timezone.now() - timedelta(days=1),
        )

        response = self.client.get(DASHBOARD_URL)

        self.assertEqual(response.status_code, 200)
        [alert] = response.data["data"]["alerts"]
        self.assertEqual(alert["game_id"], "market_route")
        self.assertEqual(alert["dimension_label"], "注意力")
        # 原本的欄位不受影響
        self.assertIn("dimensions", response.data["data"])
        self.assertIn("rewards", response.data["data"])
