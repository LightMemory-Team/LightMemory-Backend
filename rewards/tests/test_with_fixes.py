"""rewards 與 F1～F13 修正互相影響的地方（F14）。

rewards 和 F 系列是分開開發的，合併後這些組合才會同時出現：
- 日記完成：發點放在 transaction 之外；發點失敗不能讓日記完成失敗，
  日記完成失敗也不能發點（F7 ＋ rewards）
- 他人的場次、沒登入：不能靠結算端點幫自己或別人發點（F1／F2 ＋ rewards）
- 一次請求只掃一次全站日記：發點時的成就判斷、今日任務不能把它打回去（F9 ＋ rewards）

執行：
    python manage.py test rewards.tests.test_with_fixes --settings=config.settings_test
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient, APITestCase

from dashboard import services as dashboard_services
from diary.models import Diary, DiaryReply
from games import session_service
from games.fridge_check import services as fridge_services
from games.fridge_check.services import TOTAL_QUESTIONS
from rewards import services as rewards_services
from rewards.models import PointTransaction
from users.models import User

FINALIZE_CONTENT = {
    "title": "公園散步",
    "ai_response": "聽起來真愉快！",
    "post_text": "今天去公園散步",
    "hashtags": ["#散步"],
    "category": "entertainment",
    "suggested_replies": ["真棒！"],
    "invite_text": "來看看吧",
}
GENERATE = "diary.views.ai_gen.generate_finalize_content"
FRIDGE_SESSIONS = "/api/games/fridge-check/sessions/"
WRONG_ANSWER = {"food_code": "non_existent_food", "position": [99, 99]}


class DiaryFinalizeRewardsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="finalize_rewards", password="Str0ng!Pass2026"
        )
        self.client.force_authenticate(user=self.user)
        self.diary = Diary.objects.create(user=self.user, status="processing")
        DiaryReply.objects.create(
            diary=self.diary, round_index=1, transcript="我今天跟家人去公園散步"
        )
        DiaryReply.objects.create(
            diary=self.diary, round_index=2, transcript="然後我們一起吃了午餐"
        )
        self.url = f"/api/diary/{self.diary.id}/finalize/"

    @patch(GENERATE, return_value=FINALIZE_CONTENT)
    def test_rewards_are_granted_after_the_transaction_has_committed(self, _content):
        baseline = len(connection.savepoint_ids)
        depths = []

        def spy(user, event, ref=None):
            depths.append(len(connection.savepoint_ids))
            return rewards_services.empty_rewards(user)

        with patch("diary.views.rewards_services.grant", side_effect=spy):
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 201)
        # 發點時，日記的 transaction（鎖）已經結束，沒有多包一層
        self.assertEqual(depths, [baseline])

    @patch(GENERATE, return_value=FINALIZE_CONTENT)
    def test_a_rewards_failure_does_not_stop_the_diary_from_finishing(self, _content):
        with patch("rewards.services._grant", side_effect=RuntimeError("boom")):
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["status"], "done")
        self.assertIsNotNone(response.data["data"]["rewards"]["error"])
        self.diary.refresh_from_db()
        self.assertEqual(self.diary.status, "done")
        self.assertEqual(PointTransaction.objects.count(), 0)

    def test_a_failed_finalize_grants_nothing(self):
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(user=self.user)

        with patch(GENERATE, side_effect=RuntimeError("AI 壞了")):
            response = client.post(self.url)

        self.assertEqual(response.status_code, 500)
        self.diary.refresh_from_db()
        self.assertNotEqual(self.diary.status, "done")
        self.assertEqual(PointTransaction.objects.count(), 0)

    @patch(GENERATE, return_value=FINALIZE_CONTENT)
    def test_the_second_finalize_gets_zero_points_and_200(self, _content):
        first = self.client.post(self.url)
        second = self.client.post(self.url)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertGreater(first.data["data"]["rewards"]["points_earned"], 0)
        self.assertEqual(second.data["data"]["rewards"]["points_earned"], 0)
        self.assertEqual(
            PointTransaction.objects.filter(
                user=self.user, reason="diary_complete"
            ).count(),
            1,
        )

    def test_a_request_that_sees_done_only_after_the_lock_returns_200(self):
        # 模擬並行：先讀到的是處理中，等拿到鎖時，另一個請求已經把日記完成了
        Diary.objects.filter(pk=self.diary.pk).update(status="done", title="已完成")
        real_get = Diary.objects.get

        def stale_get(*args, **kwargs):
            diary = real_get(*args, **kwargs)
            diary.status = "processing"
            return diary

        with (
            patch(GENERATE, return_value=FINALIZE_CONTENT) as content,
            patch.object(Diary.objects, "get", side_effect=stale_get),
        ):
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["title"], "已完成")
        content.assert_not_called()  # 不會重複產生內容


class GameRewardsOwnershipTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="testpass123")
        self.other = User.objects.create_user(username="other", password="testpass123")
        self.owner_client = APIClient()
        self.owner_client.force_authenticate(user=self.owner)
        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other)
        data = self.owner_client.post(FRIDGE_SESSIONS).data["data"]
        self.session_id = data["session_id"]
        # 把場次推到最後一題：只要作答就會結算、發點
        session_service.update_session(
            fridge_services.GAME_TYPE, self.session_id, question_number=TOTAL_QUESTIONS
        )
        self.url = f"{FRIDGE_SESSIONS}{self.session_id}/answers/"

    def answer(self, client):
        return client.post(
            self.url, {"answer": WRONG_ANSWER, "reaction_time_ms": 1000}, format="json"
        )

    def test_another_user_cannot_finish_my_session_or_collect_points(self):
        for _ in range(3):
            response = self.answer(self.other_client)

        self.assertEqual(response.status_code, 403)
        session = session_service.get_session(
            fridge_services.GAME_TYPE, self.session_id
        )
        self.assertEqual(session["status"], "in_progress")
        self.assertEqual(PointTransaction.objects.count(), 0)

    def test_an_anonymous_request_cannot_finish_a_session_or_collect_points(self):
        for _ in range(3):
            response = self.answer(APIClient())

        self.assertEqual(response.status_code, 403)
        self.assertEqual(PointTransaction.objects.count(), 0)

    def test_the_owner_gets_the_points_and_nobody_else_does(self):
        for _ in range(3):
            response = self.answer(self.owner_client)

        self.assertGreaterEqual(response.data["data"]["rewards"]["points_earned"], 10)
        self.assertTrue(PointTransaction.objects.filter(user=self.owner).exists())
        self.assertFalse(PointTransaction.objects.filter(user=self.other).exists())


class SharedDiaryScanScopeTests(SimpleTestCase):
    """shared_diary_scan：範圍內同一位使用者只掃一次，離開範圍就丟掉。"""

    def setUp(self):
        self.alice = SimpleNamespace(id=1)
        self.bob = SimpleNamespace(id=2)
        patcher = patch.object(
            dashboard_services, "_compute_diary_z_scores", return_value=[]
        )
        self.compute = patcher.start()
        self.addCleanup(patcher.stop)

    def test_without_a_scope_every_call_scans_again(self):
        dashboard_services.diary_z_scores(self.alice)
        dashboard_services.diary_z_scores(self.alice)

        self.assertEqual(self.compute.call_count, 2)

    def test_inside_a_scope_the_same_user_is_scanned_once(self):
        with dashboard_services.shared_diary_scan():
            dashboard_services.diary_z_scores(self.alice)
            dashboard_services.diary_z_scores(self.alice)
            dashboard_services.average_diary_z_score(self.alice)

        self.assertEqual(self.compute.call_count, 1)

    def test_each_user_is_scanned_separately(self):
        with dashboard_services.shared_diary_scan():
            dashboard_services.diary_z_scores(self.alice)
            dashboard_services.diary_z_scores(self.bob)
            dashboard_services.diary_z_scores(self.alice)

        self.assertEqual(self.compute.call_count, 2)

    def test_a_nested_scope_reuses_the_outer_result(self):
        with dashboard_services.shared_diary_scan():
            dashboard_services.diary_z_scores(self.alice)
            with dashboard_services.shared_diary_scan():
                dashboard_services.diary_z_scores(self.alice)
            dashboard_services.diary_z_scores(self.alice)

        self.assertEqual(self.compute.call_count, 1)

    def test_the_result_is_dropped_when_the_scope_ends(self):
        with dashboard_services.shared_diary_scan():
            dashboard_services.diary_z_scores(self.alice)
        with dashboard_services.shared_diary_scan():
            dashboard_services.diary_z_scores(self.alice)
        dashboard_services.diary_z_scores(self.alice)

        self.assertEqual(self.compute.call_count, 3)

    def test_an_error_inside_the_scope_does_not_leave_it_open(self):
        with self.assertRaises(RuntimeError):
            with dashboard_services.shared_diary_scan():
                raise RuntimeError("x")

        dashboard_services.diary_z_scores(self.alice)
        dashboard_services.diary_z_scores(self.alice)

        self.assertEqual(self.compute.call_count, 2)

    def test_an_explicit_scores_argument_never_scans(self):
        with dashboard_services.shared_diary_scan():
            dashboard_services.diary_z_scores(self.alice, scores=[])

        self.assertEqual(self.compute.call_count, 0)


class GrantScansTheSiteOnceTests(TestCase):
    """發點（成就判斷＋今日任務）一次最多掃一次全站日記。"""

    def setUp(self):
        self.user = User.objects.create_user(username="scanner", password="testpass123")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_finishing_a_game_scans_at_most_once(self):
        data = self.client.post(FRIDGE_SESSIONS).data["data"]
        session_id = data["session_id"]
        session_service.update_session(
            fridge_services.GAME_TYPE, session_id, question_number=TOTAL_QUESTIONS
        )
        url = f"{FRIDGE_SESSIONS}{session_id}/answers/"

        with patch.object(
            dashboard_services,
            "_compute_diary_z_scores",
            wraps=dashboard_services._compute_diary_z_scores,
        ) as spy:
            for _ in range(3):
                response = self.client.post(
                    url,
                    {"answer": WRONG_ANSWER, "reaction_time_ms": 1000},
                    format="json",
                )

        self.assertTrue(response.data["data"]["is_completed"])
        self.assertGreaterEqual(response.data["data"]["rewards"]["points_earned"], 10)
        self.assertLessEqual(spy.call_count, 1)
