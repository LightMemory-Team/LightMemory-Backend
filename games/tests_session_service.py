"""session_service 歷史場次查詢（list_previous_*）的測試。"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from users.models import User

from . import session_service
from .models import GameSession

GAME_TYPE = "market_route"


class ListPreviousStepRecordsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw123456")
        self.other_user = User.objects.create_user(
            username="other", password="pw123456"
        )
        self.base_time = timezone.now()

    def _play(self, user, minutes_ago, *, finished=True, steps=1):
        """建一場遊戲，存 steps 筆作答，finished 時設定結束時間。"""
        session = session_service.create_session(GAME_TYPE, user=user)
        session_id = session["session_id"]
        for _ in range(steps):
            session_service.save_step(
                GAME_TYPE,
                session_id,
                {"stage": "basic", "is_correct": True, "response_time_ms": 800},
            )
        if finished:
            GameSession.objects.filter(pk=session_id).update(
                status="finished",
                finished_at=self.base_time - timedelta(minutes=minutes_ago),
            )
        return session_id

    def test_returns_previous_finished_sessions_of_same_user(self):
        self._play(self.user, minutes_ago=30, steps=2)
        self._play(self.user, minutes_ago=20, steps=3)
        current = self._play(self.user, minutes_ago=10)

        history = session_service.list_previous_step_records(GAME_TYPE, current)

        self.assertEqual(sorted(len(records) for records in history), [2, 3])
        self.assertEqual(history[0][0]["detail"]["stage"], "basic")

    def test_excludes_sessions_finished_later(self):
        self._play(self.user, minutes_ago=30)
        current = self._play(self.user, minutes_ago=20)
        self._play(self.user, minutes_ago=10)  # 比這場晚結束

        history = session_service.list_previous_step_records(GAME_TYPE, current)

        self.assertEqual(len(history), 1)

    def test_excludes_unfinished_sessions(self):
        self._play(self.user, minutes_ago=30, finished=False)
        current = self._play(self.user, minutes_ago=10)

        history = session_service.list_previous_step_records(GAME_TYPE, current)

        self.assertEqual(history, [])

    def test_in_progress_session_uses_all_finished_sessions(self):
        self._play(self.user, minutes_ago=30)
        self._play(self.user, minutes_ago=20)
        current = self._play(self.user, minutes_ago=0, finished=False)

        history = session_service.list_previous_step_records(GAME_TYPE, current)

        self.assertEqual(len(history), 2)

    def test_same_user_false_includes_other_users(self):
        self._play(self.user, minutes_ago=30)
        self._play(self.other_user, minutes_ago=20)
        current = self._play(self.user, minutes_ago=10)

        personal = session_service.list_previous_step_records(GAME_TYPE, current)
        population = session_service.list_previous_step_records(
            GAME_TYPE, current, same_user=False
        )

        self.assertEqual(len(personal), 1)
        self.assertEqual(len(population), 2)

    def test_unknown_session_raises(self):
        with self.assertRaises(session_service.SessionNotFound):
            session_service.list_previous_step_records(
                GAME_TYPE, "00000000-0000-0000-0000-000000000000"
            )


class ListPreviousResultsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw123456")
        self.other_user = User.objects.create_user(
            username="other", password="pw123456"
        )
        self.base_time = timezone.now()

    def _play(self, user, minutes_ago, *, raw_score=None, finished=True):
        """建一場遊戲；finished 時存結算結果並設定結束時間。"""
        session = session_service.create_session(GAME_TYPE, user=user)
        session_id = session["session_id"]
        if finished:
            GameSession.objects.filter(pk=session_id).update(
                status="finished",
                result={"raw_score": raw_score},
                finished_at=self.base_time - timedelta(minutes=minutes_ago),
            )
        return session_id

    def test_returns_previous_results_in_finish_order(self):
        self._play(self.user, minutes_ago=20, raw_score=70)
        self._play(self.user, minutes_ago=30, raw_score=60)
        current = self._play(self.user, minutes_ago=10, raw_score=80)

        history = session_service.list_previous_results(GAME_TYPE, current)

        self.assertEqual([r["raw_score"] for r in history], [60, 70])

    def test_excludes_this_and_later_sessions(self):
        self._play(self.user, minutes_ago=30, raw_score=60)
        current = self._play(self.user, minutes_ago=20, raw_score=70)
        self._play(self.user, minutes_ago=10, raw_score=80)  # 比這場晚結束

        history = session_service.list_previous_results(GAME_TYPE, current)

        self.assertEqual([r["raw_score"] for r in history], [60])

    def test_in_progress_session_uses_all_finished_sessions(self):
        # 結算當下這場還沒標成已結束，要拿到「全部已結束」的場次
        self._play(self.user, minutes_ago=30, raw_score=60)
        self._play(self.user, minutes_ago=20, raw_score=70)
        self._play(self.user, minutes_ago=10, finished=False)
        current = self._play(self.user, minutes_ago=0, finished=False)

        history = session_service.list_previous_results(GAME_TYPE, current)

        self.assertEqual(len(history), 2)

    def test_same_user_false_includes_other_users(self):
        self._play(self.user, minutes_ago=30, raw_score=60)
        self._play(self.other_user, minutes_ago=20, raw_score=90)
        current = self._play(self.user, minutes_ago=0, finished=False)

        personal = session_service.list_previous_results(GAME_TYPE, current)
        population = session_service.list_previous_results(
            GAME_TYPE, current, same_user=False
        )

        self.assertEqual([r["raw_score"] for r in personal], [60])
        self.assertEqual([r["raw_score"] for r in population], [60, 90])

    def test_unknown_session_raises(self):
        with self.assertRaises(session_service.SessionNotFound):
            session_service.list_previous_results(
                GAME_TYPE, "00000000-0000-0000-0000-000000000000"
            )


class HistoryTestCase(TestCase):
    """新舊歷史查詢測試共用：建使用者、建一場可指定各種旗標的遊戲。"""

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw123456")
        self.other_user = User.objects.create_user(
            username="other", password="pw123456"
        )
        self.third_user = User.objects.create_user(
            username="third", password="pw123456"
        )
        self.base_time = timezone.now()

    def _play(
        self,
        user,
        minutes_ago,
        *,
        raw_score=50,
        finished=True,
        is_pretest=False,
        client_session_id=None,
        steps=0,
    ):
        """建一場遊戲；finished 時存結算結果並設定結束時間，steps 是作答筆數。"""
        session = session_service.create_session(
            GAME_TYPE, user=user, is_pretest=is_pretest
        )
        session_id = session["session_id"]
        for _ in range(steps):
            session_service.save_step(
                GAME_TYPE,
                session_id,
                {"stage": "basic", "is_correct": True, "response_time_ms": 800},
            )
        fields = {"client_session_id": client_session_id}
        if finished:
            fields.update(
                status="finished",
                result={"raw_score": raw_score},
                finished_at=self.base_time - timedelta(minutes=minutes_ago),
            )
        GameSession.objects.filter(pk=session_id).update(**fields)
        return session_id


class FamiliarizationSessionsExcludedTests(HistoryTestCase):
    """熟悉場（is_pretest=True）不進任何歷史，個人、全體都一樣。"""

    def test_personal_results_exclude_familiarization(self):
        self._play(self.user, minutes_ago=40, raw_score=10, is_pretest=True)
        self._play(self.user, minutes_ago=30, raw_score=60)
        current = self._play(self.user, minutes_ago=0, finished=False)

        history = session_service.list_previous_results(GAME_TYPE, current)

        self.assertEqual([r["raw_score"] for r in history], [60])

    def test_population_results_exclude_familiarization(self):
        self._play(self.other_user, minutes_ago=40, raw_score=10, is_pretest=True)
        self._play(self.other_user, minutes_ago=30, raw_score=60)
        current = self._play(self.user, minutes_ago=0, finished=False)

        history = session_service.list_previous_results(
            GAME_TYPE, current, same_user=False
        )

        self.assertEqual([r["raw_score"] for r in history], [60])

    def test_personal_step_records_exclude_familiarization(self):
        self._play(self.user, minutes_ago=40, is_pretest=True, steps=5)
        self._play(self.user, minutes_ago=30, steps=2)
        current = self._play(self.user, minutes_ago=0, finished=False)

        history = session_service.list_previous_step_records(GAME_TYPE, current)

        self.assertEqual([len(records) for records in history], [2])

    def test_familiarization_session_itself_is_not_its_own_history(self):
        # 熟悉場自己結算時，仍然只看它「之前」的歷史，不會把自己算進去
        current = self._play(self.user, minutes_ago=0, is_pretest=True)

        self.assertEqual(session_service.list_previous_results(GAME_TYPE, current), [])


class ListPreviousResultsByUserTests(HistoryTestCase):
    def test_groups_other_users_results_by_user(self):
        self._play(self.other_user, minutes_ago=50, raw_score=60)
        self._play(self.other_user, minutes_ago=40, raw_score=70)
        self._play(self.third_user, minutes_ago=30, raw_score=80)
        current = self._play(self.user, minutes_ago=0, finished=False)

        history = session_service.list_previous_results_by_user(GAME_TYPE, current)

        self.assertEqual(set(history), {self.other_user.id, self.third_user.id})
        self.assertEqual(
            [r["raw_score"] for r in history[self.other_user.id]], [60, 70]
        )
        self.assertEqual([r["raw_score"] for r in history[self.third_user.id]], [80])

    def test_excludes_current_user(self):
        self._play(self.user, minutes_ago=30, raw_score=60)
        self._play(self.other_user, minutes_ago=20, raw_score=70)
        current = self._play(self.user, minutes_ago=0, finished=False)

        history = session_service.list_previous_results_by_user(GAME_TYPE, current)

        self.assertEqual(list(history), [self.other_user.id])

    def test_excludes_familiarization_sessions(self):
        self._play(self.other_user, minutes_ago=30, raw_score=10, is_pretest=True)
        self._play(self.other_user, minutes_ago=20, raw_score=70)
        current = self._play(self.user, minutes_ago=0, finished=False)

        history = session_service.list_previous_results_by_user(GAME_TYPE, current)

        self.assertEqual([r["raw_score"] for r in history[self.other_user.id]], [70])

    def test_excludes_staff_users(self):
        self.other_user.is_staff = True
        self.other_user.save()
        self._play(self.other_user, minutes_ago=30, raw_score=60)
        self._play(self.third_user, minutes_ago=20, raw_score=70)
        current = self._play(self.user, minutes_ago=0, finished=False)

        history = session_service.list_previous_results_by_user(GAME_TYPE, current)

        self.assertEqual(list(history), [self.third_user.id])

    def test_excludes_seed_demo_sessions(self):
        self._play(
            self.other_user,
            minutes_ago=30,
            raw_score=60,
            client_session_id="seed-1-market_route-0-0",
        )
        self._play(self.other_user, minutes_ago=20, raw_score=70)
        current = self._play(self.user, minutes_ago=0, finished=False)

        history = session_service.list_previous_results_by_user(GAME_TYPE, current)

        self.assertEqual([r["raw_score"] for r in history[self.other_user.id]], [70])

    def test_client_session_id_that_only_contains_seed_is_kept(self):
        # 只有「開頭是 seed-」才排除；一般前端產生的 id 不受影響
        self._play(
            self.other_user, minutes_ago=30, raw_score=60, client_session_id="my-seed-1"
        )
        current = self._play(self.user, minutes_ago=0, finished=False)

        history = session_service.list_previous_results_by_user(GAME_TYPE, current)

        self.assertEqual(list(history), [self.other_user.id])

    def test_excludes_unfinished_and_later_sessions(self):
        self._play(self.other_user, minutes_ago=30, raw_score=60)
        self._play(self.other_user, minutes_ago=20, finished=False)
        current = self._play(self.user, minutes_ago=15, raw_score=75)
        self._play(self.other_user, minutes_ago=5, raw_score=90)  # 比這場晚結束

        history = session_service.list_previous_results_by_user(GAME_TYPE, current)

        self.assertEqual([r["raw_score"] for r in history[self.other_user.id]], [60])

    def test_no_other_users_is_empty(self):
        self._play(self.user, minutes_ago=30, raw_score=60)
        current = self._play(self.user, minutes_ago=0, finished=False)

        self.assertEqual(
            session_service.list_previous_results_by_user(GAME_TYPE, current), {}
        )

    def test_unknown_session_raises(self):
        with self.assertRaises(session_service.SessionNotFound):
            session_service.list_previous_results_by_user(
                GAME_TYPE, "00000000-0000-0000-0000-000000000000"
            )


class ListPreviousStepRecordsByUserTests(HistoryTestCase):
    def test_groups_other_users_step_records_by_user(self):
        self._play(self.other_user, minutes_ago=50, steps=2)
        self._play(self.other_user, minutes_ago=40, steps=3)
        self._play(self.third_user, minutes_ago=30, steps=1)
        current = self._play(self.user, minutes_ago=0, finished=False)

        history = session_service.list_previous_step_records_by_user(GAME_TYPE, current)

        self.assertEqual(set(history), {self.other_user.id, self.third_user.id})
        self.assertEqual(
            sorted(len(records) for records in history[self.other_user.id]), [2, 3]
        )
        self.assertEqual([len(r) for r in history[self.third_user.id]], [1])
        self.assertEqual(history[self.third_user.id][0][0]["detail"]["stage"], "basic")

    def test_applies_same_exclusions_as_results(self):
        self.other_user.is_staff = True
        self.other_user.save()
        # 其他人：本人、staff、熟悉場、種子場次都要被排除，只剩 third 的正式場次
        self._play(self.user, minutes_ago=60, steps=1)
        self._play(self.other_user, minutes_ago=50, steps=1)
        self._play(self.third_user, minutes_ago=40, steps=1, is_pretest=True)
        self._play(
            self.third_user,
            minutes_ago=30,
            steps=1,
            client_session_id="seed-9-market_route-0-0",
        )
        self._play(self.third_user, minutes_ago=20, steps=4)
        current = self._play(self.user, minutes_ago=0, finished=False)

        history = session_service.list_previous_step_records_by_user(GAME_TYPE, current)

        self.assertEqual(list(history), [self.third_user.id])
        self.assertEqual([len(r) for r in history[self.third_user.id]], [4])

    def test_sessions_without_steps_are_skipped(self):
        self._play(self.other_user, minutes_ago=30, steps=0)
        current = self._play(self.user, minutes_ago=0, finished=False)

        self.assertEqual(
            session_service.list_previous_step_records_by_user(GAME_TYPE, current), {}
        )

    def test_unknown_session_raises(self):
        with self.assertRaises(session_service.SessionNotFound):
            session_service.list_previous_step_records_by_user(
                GAME_TYPE, "00000000-0000-0000-0000-000000000000"
            )
