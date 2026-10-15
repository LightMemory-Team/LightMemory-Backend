"""session_service.list_previous_step_records 的測試。"""

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
