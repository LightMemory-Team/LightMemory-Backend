"""memory_zscore.py 的測試。"""

from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from games import session_service
from games.models import GameSession
from users.models import User

from .memory_zscore import (
    GAME_TYPE,
    calculate_stage_metrics,
    calculate_working_memory_z_score,
)


def _step(round_number, *, stage="basic", correct=True, rt=1000):
    """組一筆跟 round_answer 存進 save_step 一樣格式的作答紀錄。"""
    return {
        "round_number": round_number,
        "stage": stage,
        "is_correct": correct,
        "response_time_ms": rt,
        "detail": {"stage": stage},
    }


def _as_step_records(steps):
    """轉成 session_service 回傳的 step_records 格式。"""
    return [
        {
            "step_number": i,
            "is_correct": s["is_correct"],
            "response_time_ms": s["response_time_ms"],
            "detail": s,
        }
        for i, s in enumerate(steps, start=1)
    ]


class CalculateStageMetricsTests(SimpleTestCase):
    def test_accuracy_and_response_time_per_stage(self):
        records = _as_step_records(
            [
                _step(1, correct=True, rt=800),
                _step(2, correct=False, rt=1200),
                _step(3, stage="intermediate", correct=True, rt=900),
            ]
        )
        metrics = calculate_stage_metrics(records)
        self.assertEqual(metrics["basic"]["accuracy"], 0.5)
        self.assertEqual(metrics["basic"]["avg_response_time_ms"], 1000)
        self.assertEqual(metrics["intermediate"]["accuracy"], 1.0)

    def test_missing_response_time_is_skipped(self):
        records = _as_step_records([_step(1, rt=None), _step(2, rt=600)])
        self.assertEqual(
            calculate_stage_metrics(records)["basic"]["avg_response_time_ms"], 600
        )

    def test_unplayed_stage_is_absent(self):
        records = _as_step_records([_step(1)])
        self.assertNotIn("advanced", calculate_stage_metrics(records))


class CalculateWorkingMemoryZScoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw123456")
        self.now = timezone.now()

    def _play(self, user, minutes_ago, steps, *, is_pretest=False):
        session_id = session_service.create_session(
            GAME_TYPE, initial_state={"is_pretest": is_pretest}, user=user
        )["session_id"]
        for step in steps:
            session_service.save_step(GAME_TYPE, session_id, step)
        GameSession.objects.filter(pk=session_id).update(
            status="finished", finished_at=self.now - timedelta(minutes=minutes_ago)
        )
        return session_id

    def _play_history(self, user):
        """3 場 basic 歷史：
        正確率 0 / 0.5 / 1          → 平均 0.5、標準差 0.5
        反應時間 900 / 1000 / 1100  → 平均 1000、標準差 100
        """
        self._play(
            user, 40, [_step(1, correct=False, rt=900), _step(2, correct=False, rt=900)]
        )
        self._play(user, 30, [_step(1, rt=1000), _step(2, correct=False, rt=1000)])
        self._play(user, 20, [_step(1, rt=1100), _step(2, rt=1100)])

    def test_compares_with_personal_history(self):
        self._play_history(self.user)
        current = self._play(self.user, 10, [_step(1, rt=800), _step(2, rt=800)])
        # z_正確率 = (1 - 0.5) / 0.5 = 1
        # z_反應時間 = -(800 - 1000) / 100 = 2
        # 0.5 * 1 + 0.5 * 2 = 1.5
        self.assertAlmostEqual(calculate_working_memory_z_score(current), 1.5)

    def test_pretest_counts_as_history(self):
        self._play(
            self.user,
            40,
            [_step(1, correct=False, rt=900), _step(2, correct=False, rt=900)],
            is_pretest=True,
        )
        self._play(self.user, 30, [_step(1, rt=1000), _step(2, correct=False, rt=1000)])
        self._play(self.user, 20, [_step(1, rt=1100), _step(2, rt=1100)])
        current = self._play(self.user, 10, [_step(1, rt=800), _step(2, rt=800)])
        self.assertAlmostEqual(calculate_working_memory_z_score(current), 1.5)

    def test_pretest_session_itself_is_none(self):
        self._play_history(self.user)
        pretest = self._play(self.user, 10, [_step(1)], is_pretest=True)
        self.assertIsNone(calculate_working_memory_z_score(pretest))

    def test_cold_start_uses_other_users_history(self):
        other_user = User.objects.create_user(username="other", password="pw123456")
        self._play_history(other_user)
        current = self._play(self.user, 10, [_step(1, rt=800), _step(2, rt=800)])
        self.assertAlmostEqual(calculate_working_memory_z_score(current), 1.5)

    def test_no_history_is_none(self):
        current = self._play(self.user, 10, [_step(1)])
        self.assertIsNone(calculate_working_memory_z_score(current))

    def test_unknown_session_raises(self):
        with self.assertRaises(session_service.SessionNotFound):
            calculate_working_memory_z_score("00000000-0000-0000-0000-000000000000")
