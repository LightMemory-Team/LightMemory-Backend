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
            GAME_TYPE,
            initial_state={"is_pretest": is_pretest},
            user=user,
            is_pretest=is_pretest,
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
        反應時間 1000 / 1100 / 900  → 平均 1000、標準差 100（越低越好）

        各場兩個指標的 z 是 (-1, 0)、(0, -1)、(+1, +1)，等權重合成 -0.5、-0.5、+1，
        變異數和 1.5。
        """
        self._play(
            user,
            40,
            [_step(1, correct=False, rt=1000), _step(2, correct=False, rt=1000)],
        )
        self._play(user, 30, [_step(1, rt=1100), _step(2, correct=False, rt=1100)])
        self._play(user, 20, [_step(1, rt=900), _step(2, rt=900)])

    # 這一場：正確率 0.5（z = 0）、平均反應時間 950（z = +0.5）→ 合成 0.25
    CURRENT_STEPS = [_step(1, rt=950), _step(2, correct=False, rt=950)]
    CURRENT_COMPOSITE = 0.25

    def test_compares_with_personal_history(self):
        self._play_history(self.user)
        current = self._play(self.user, 10, self.CURRENT_STEPS)
        # 兩指標等權重的理論變異數 0.5；收縮後 (1.5 + 3 × 0.5) ÷ (2 + 3) = 0.6
        self.assertAlmostEqual(
            calculate_working_memory_z_score(current),
            self.CURRENT_COMPOSITE / 0.6**0.5,
        )

    def test_pretest_is_not_history(self):
        # 前測是熟悉場，不進歷史：結果跟沒有它一樣
        self._play(
            self.user,
            50,
            [_step(1, correct=False, rt=3000), _step(2, correct=False, rt=3000)],
            is_pretest=True,
        )
        self._play_history(self.user)
        current = self._play(self.user, 10, self.CURRENT_STEPS)
        self.assertAlmostEqual(
            calculate_working_memory_z_score(current),
            self.CURRENT_COMPOSITE / 0.6**0.5,
        )

    def test_pretest_column_alone_is_none(self):
        # 只有 GameSession.is_pretest 欄位、state 沒有旗標，也算前測
        self._play_history(self.user)
        session_id = session_service.create_session(
            GAME_TYPE, user=self.user, is_pretest=True
        )["session_id"]
        session_service.save_step(GAME_TYPE, session_id, _step(1))
        self.assertIsNone(calculate_working_memory_z_score(session_id))

    def test_pretest_session_itself_is_none(self):
        self._play_history(self.user)
        pretest = self._play(self.user, 10, [_step(1)], is_pretest=True)
        self.assertIsNone(calculate_working_memory_z_score(pretest))

    def test_cold_start_borrows_other_users_history(self):
        # 兩位其他使用者各 3 場（個人內自由度 4）；自己沒有參考場次，
        # 合成分數的變異數完全用理論值 0.5
        for name in ("other1", "other2"):
            other = User.objects.create_user(username=name, password="pw123456")
            self._play_history(other)
        current = self._play(self.user, 10, self.CURRENT_STEPS)
        self.assertAlmostEqual(
            calculate_working_memory_z_score(current),
            self.CURRENT_COMPOSITE / 0.5**0.5,
        )

    def test_one_other_user_is_not_enough_population(self):
        other = User.objects.create_user(username="other", password="pw123456")
        self._play_history(other)
        current = self._play(self.user, 10, self.CURRENT_STEPS)
        self.assertIsNone(calculate_working_memory_z_score(current))

    def test_no_history_is_none(self):
        current = self._play(self.user, 10, [_step(1)])
        self.assertIsNone(calculate_working_memory_z_score(current))

    def test_unknown_session_raises(self):
        with self.assertRaises(session_service.SessionNotFound):
            calculate_working_memory_z_score("00000000-0000-0000-0000-000000000000")
