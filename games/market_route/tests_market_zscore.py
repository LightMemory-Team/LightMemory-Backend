"""market_zscore.py 的測試。"""

from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from games import session_service
from games.models import GameSession
from users.models import User

from .market_zscore import (
    GAME_TYPE,
    calculate_attention_z_score,
    calculate_stage_metrics,
)


def _step(
    question_number,
    *,
    attempt=1,
    stage="basic",
    correct=True,
    timeout=False,
    rt=800,
    exposure=2000,
):
    """組一筆跟 round_answer 存進 save_step 一樣格式的作答紀錄。"""
    return {
        "question_number": question_number,
        "attempt_number": attempt,
        "stage": stage,
        "is_correct": correct,
        "is_timeout": timeout,
        "response_time_ms": None if timeout else rt,
        "exposure_time_ms": exposure,
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
    def test_only_first_attempt_is_counted(self):
        records = _as_step_records(
            [
                _step(1, correct=False, rt=1000),
                _step(1, attempt=2, correct=True, rt=200),  # 重看後答對，不算
                _step(2, correct=True, rt=600),
            ]
        )
        basic = calculate_stage_metrics(records)["basic"]
        self.assertEqual(basic["accuracy"], 0.5)
        self.assertEqual(basic["avg_response_time_ms"], 800)

    def test_timeout_excluded_from_response_time(self):
        records = _as_step_records(
            [
                _step(1, rt=600),
                _step(2, correct=False, timeout=True),
            ]
        )
        basic = calculate_stage_metrics(records)["basic"]
        self.assertEqual(basic["accuracy"], 0.5)
        self.assertEqual(basic["avg_response_time_ms"], 600)

    def test_all_timeout_response_time_is_none(self):
        records = _as_step_records([_step(1, correct=False, timeout=True)])
        self.assertIsNone(
            calculate_stage_metrics(records)["basic"]["avg_response_time_ms"]
        )

    def test_converged_exposure_is_last_question_of_stage(self):
        records = _as_step_records(
            [
                _step(1, exposure=2000),
                _step(2, exposure=1900),
                _step(3, stage="intermediate", exposure=1500),
                _step(4, stage="intermediate", exposure=1400),
            ]
        )
        metrics = calculate_stage_metrics(records)
        self.assertEqual(metrics["basic"]["converged_exposure_ms"], 1900)
        self.assertEqual(metrics["intermediate"]["converged_exposure_ms"], 1400)

    def test_unplayed_stage_is_absent(self):
        records = _as_step_records([_step(1)])
        self.assertNotIn("advanced", calculate_stage_metrics(records))


class CalculateAttentionZScoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw123456")
        self.now = timezone.now()

    def _play(self, user, minutes_ago, steps):
        session_id = session_service.create_session(GAME_TYPE, user=user)["session_id"]
        for step in steps:
            session_service.save_step(GAME_TYPE, session_id, step)
        GameSession.objects.filter(pk=session_id).update(
            status="finished", finished_at=self.now - timedelta(minutes=minutes_ago)
        )
        return session_id

    def _play_history(self, user):
        """3 場 basic 歷史：
        正確率 0 / 0.5 / 1        → 平均 0.5、標準差 0.5
        反應時間 700 / 800 / 900  → 平均 800、標準差 100
        收斂曝光 1900 / 1800 / 1700 → 平均 1800、標準差 100
        """
        self._play(
            user,
            40,
            [
                _step(1, correct=False, rt=700),
                _step(2, correct=False, rt=700, exposure=1900),
            ],
        )
        self._play(
            user,
            30,
            [_step(1, rt=800), _step(2, correct=False, rt=800, exposure=1800)],
        )
        self._play(user, 20, [_step(1, rt=900), _step(2, rt=900, exposure=1700)])

    def test_compares_with_personal_history(self):
        self._play_history(self.user)
        current = self._play(
            self.user, 10, [_step(1, rt=700), _step(2, rt=700, exposure=1600)]
        )
        # z_正確率 = (1 - 0.5) / 0.5 = 1
        # z_反應時間 = -(700 - 800) / 100 = 1
        # z_曝光時間 = -(1600 - 1800) / 100 = 2
        # 0.4 * 1 + 0.3 * 1 + 0.3 * 2 = 1.3
        self.assertAlmostEqual(calculate_attention_z_score(current), 1.3)

    def test_cold_start_uses_other_users_history(self):
        other_user = User.objects.create_user(username="other", password="pw123456")
        self._play_history(other_user)
        current = self._play(
            self.user, 10, [_step(1, rt=700), _step(2, rt=700, exposure=1600)]
        )
        self.assertAlmostEqual(calculate_attention_z_score(current), 1.3)

    def test_no_history_is_none(self):
        current = self._play(self.user, 10, [_step(1)])
        self.assertIsNone(calculate_attention_z_score(current))

    def test_unknown_session_raises(self):
        with self.assertRaises(session_service.SessionNotFound):
            calculate_attention_z_score("00000000-0000-0000-0000-000000000000")
