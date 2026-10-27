"""recompute_scores 指令（python manage.py recompute_scores）的測試。

預期值沿用各遊戲 z-score 測試手算的數字（歷史 3 場 + 這一場），
這裡要確認的是指令有把「熟悉場」和「這場之前的歷史」傳對。
"""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from games import session_service
from games.market_route.tests_market_zscore import _step as route_step
from games.market_sort.services import calculate_executive_function_z_score
from games.memory_recall.tests_memory_zscore import _step as recall_step
from games.models import GameSession
from games.zscore import z_score_to_display_score
from users.models import User

# 冰箱檢查、市場買菜的歷史：(正確率, 速度分)，z 是 (-1, 0)、(0, -1)、(+1, +1)
TWO_METRIC_HISTORY = [(60, 70), (70, 60), (80, 80)]


def run_command(*args):
    out = StringIO()
    call_command("recompute_scores", *args, stdout=out)
    return out.getvalue()


class RecomputeScoresTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="grandma", password="pw123456")
        self.other = User.objects.create_user(username="other", password="pw123456")
        self.now = timezone.now()

    def _session(
        self,
        game,
        minutes_ago,
        *,
        user=None,
        result=None,
        steps=(),
        is_pretest=False,
        client_session_id=None,
    ):
        """建一場已結束的舊場次（跟新算法之前存的資料一樣：沒有熟悉場標記）。"""
        session_id = session_service.create_session(game, user=user or self.user)[
            "session_id"
        ]
        for step in steps:
            session_service.save_step(game, session_id, step)
        GameSession.objects.filter(pk=session_id).update(
            status="finished",
            is_pretest=is_pretest,
            client_session_id=client_session_id,
            result=result if result is not None else {"z_score": 9.0},
            finished_at=self.now - timedelta(minutes=minutes_ago),
        )
        return session_id

    def _reload(self, session_id):
        return GameSession.objects.get(pk=session_id)


class BackfillFamiliarizationTests(RecomputeScoresTestCase):
    def test_earliest_session_per_player_and_game_becomes_familiarization(self):
        mine = [self._session("fridge_check", m) for m in (50, 40, 30)]
        other = [self._session("fridge_check", m, user=self.other) for m in (45, 35)]
        route = [self._session("market_route", m) for m in (20, 10)]

        output = run_command()

        flags = lambda ids: [self._reload(i).is_pretest for i in ids]  # noqa: E731
        self.assertEqual(flags(mine), [True, False, False])
        self.assertEqual(flags(other), [True, False])
        self.assertEqual(flags(route), [True, False])  # 不同遊戲各算各的
        self.assertIn("新標記 3 場", output)

    def test_wrongly_flagged_later_session_is_cleared(self):
        first = self._session("fridge_check", 50)
        second = self._session("fridge_check", 40, is_pretest=True)

        run_command()

        self.assertTrue(self._reload(first).is_pretest)
        self.assertFalse(self._reload(second).is_pretest)

    def test_unfinished_sessions_are_ignored(self):
        finished = self._session("fridge_check", 50)
        unfinished = session_service.create_session("fridge_check", user=self.user)

        run_command()

        self.assertTrue(self._reload(finished).is_pretest)
        self.assertFalse(self._reload(unfinished["session_id"]).is_pretest)

    def test_seed_demo_sessions_are_left_alone(self):
        seed = self._session(
            "fridge_check",
            60,
            result={"z_score": 0.5, "standard_score": 62},
            client_session_id="seed-1-fridge_check-0-0",
        )
        real = self._session("fridge_check", 50)

        run_command()

        # 種子場次不當熟悉場、結果也不重算；真人的最早一場才是熟悉場
        self.assertFalse(self._reload(seed).is_pretest)
        self.assertEqual(self._reload(seed).result["z_score"], 0.5)
        self.assertTrue(self._reload(real).is_pretest)


class RecomputeTwoMetricGamesTests(RecomputeScoresTestCase):
    """冰箱檢查、市場買菜：正確率、速度分各自轉 z（手算值同各遊戲測試）。"""

    CASES = [
        # (遊戲, 這場的速度分, 預期 z, 預期標準分數)
        ("fridge_check", 76, 1.033, 76),
        ("market_shopping", 85, 1.614, 90),
    ]

    def _result(self, accuracy, speed, **extra):
        return {
            "accuracy": accuracy,
            "speed_score": speed,
            "average_reaction_time_ms": 2000,
            "z_score": 9.0,  # 舊算法存的值，要被改掉
            "standard_score": 99,
            **extra,
        }

    def _play_all(self, game, current_speed):
        familiarization = self._session(game, 60, result=self._result(30, 30))
        history = [
            self._session(game, minutes, result=self._result(accuracy, speed))
            for minutes, (accuracy, speed) in zip((50, 40, 30), TWO_METRIC_HISTORY)
        ]
        current = self._session(game, 10, result=self._result(80, current_speed))
        return familiarization, history, current

    def test_recomputes_z_and_standard_score(self):
        for game, speed, expected_z, expected_score in self.CASES:
            with self.subTest(game=game):
                _, _, current = self._play_all(game, speed)

                run_command()

                result = self._reload(current).result
                self.assertEqual(result["z_score"], expected_z)
                self.assertEqual(result["standard_score"], expected_score)

    def test_familiarization_and_short_history_become_null(self):
        familiarization, history, _ = self._play_all("fridge_check", 76)

        run_command()

        # 熟悉場：不算分；前 3 場沒有足夠的歷史（自己不滿 3 場、也沒有全體）：算不出
        for session_id in (familiarization, history[0]):
            result = self._reload(session_id).result
            self.assertIsNone(result["z_score"])
            self.assertIsNone(result["standard_score"])

    def test_other_result_fields_are_kept(self):
        session = self._session(
            "fridge_check", 10, result=self._result(80, 76, final_score=80.3)
        )

        run_command()

        result = self._reload(session).result
        self.assertEqual(result["final_score"], 80.3)
        self.assertEqual(result["accuracy"], 80)

    def test_old_result_without_accuracy_is_left_unchanged(self):
        old = {"raw_score": 70.0, "z_score": 0.3, "standard_score": 57}
        session = self._session("fridge_check", 10, result=old)

        run_command()

        self.assertEqual(self._reload(session).result, old)


class RecomputeStepRecordGamesTests(RecomputeScoresTestCase):
    def test_market_route_z_score_is_recomputed(self):
        history_steps = [
            [
                route_step(1, correct=False, rt=700),
                route_step(2, correct=False, rt=700, exposure=1900),
            ],
            [
                route_step(1, rt=800),
                route_step(2, correct=False, rt=800, exposure=1800),
            ],
            [route_step(1, rt=900), route_step(2, rt=900, exposure=1700)],
        ]
        current_steps = [
            route_step(1, rt=800),
            route_step(2, correct=False, rt=800, exposure=1700),
        ]
        old = {"total_score": 50, "z_score": 9.0}
        familiarization = self._session(
            "market_route",
            60,
            steps=[route_step(1, correct=False, rt=3000)],
            result=dict(old),
        )
        for minutes, steps in zip((50, 40, 30), history_steps):
            self._session("market_route", minutes, steps=steps, result=dict(old))
        current = self._session(
            "market_route", 10, steps=current_steps, result=dict(old)
        )

        run_command()

        # (1/3) ÷ √(11/45) ≈ 0.674，同 market_route 的 z-score 測試
        result = self._reload(current).result
        self.assertEqual(result["z_score"], 0.674)
        self.assertEqual(result["total_score"], 50)  # 這款的 total_score 不是 z 換算的
        self.assertIsNone(self._reload(familiarization).result["z_score"])

    def test_memory_recall_z_and_total_score_are_recomputed(self):
        history_steps = [
            [
                recall_step(1, correct=False, rt=1000),
                recall_step(2, correct=False, rt=1000),
            ],
            [recall_step(1, rt=1100), recall_step(2, correct=False, rt=1100)],
            [recall_step(1, rt=900), recall_step(2, rt=900)],
        ]
        current_steps = [recall_step(1, rt=950), recall_step(2, correct=False, rt=950)]
        old = {"total_score": 99, "z_score": 9.0}
        familiarization = self._session(
            "memory_recall",
            60,
            steps=[recall_step(1, correct=False, rt=3000)],
            result=dict(old),
        )
        for minutes, steps in zip((50, 40, 30), history_steps):
            self._session("memory_recall", minutes, steps=steps, result=dict(old))
        current = self._session(
            "memory_recall", 10, steps=current_steps, result=dict(old)
        )

        run_command()

        # 0.25 ÷ √0.6 ≈ 0.323 → round(50 + 25 x 0.323) = 58，同 memory_recall 的測試
        result = self._reload(current).result
        self.assertEqual(result["z_score"], 0.323)
        self.assertEqual(result["total_score"], 58)
        familiarization_result = self._reload(familiarization).result
        self.assertIsNone(familiarization_result["z_score"])
        self.assertIsNone(familiarization_result["total_score"])


class RecomputeMarketSortTests(RecomputeScoresTestCase):
    HISTORY = [
        {
            "overall_accuracy": 0.6,
            "switch_accuracy": 0.5,
            "switch_cost_rt": 1.0,
            "learning_speed": 2.0,
        },
        {
            "overall_accuracy": 0.7,
            "switch_accuracy": 0.6,
            "switch_cost_rt": 0.8,
            "learning_speed": 1.5,
        },
        {
            "overall_accuracy": 0.8,
            "switch_accuracy": 0.7,
            "switch_cost_rt": 0.6,
            "learning_speed": 1.0,
        },
    ]
    CURRENT = {
        "overall_accuracy": 0.75,
        "switch_accuracy": 0.65,
        "switch_cost_rt": 0.7,
        "learning_speed": 1.2,
    }

    def _result(self, raw_metrics):
        return {
            "raw_metrics": raw_metrics,
            "z_scores": {},
            "z_score": 9.0,
            "cognitive_flexibility_score": 99,
            "play_seconds": 200,
        }

    def _play_all(self):
        familiarization = self._session(
            "market_sort",
            60,
            result=self._result(
                {
                    "overall_accuracy": 0.1,
                    "switch_accuracy": 0.1,
                    "switch_cost_rt": 5.0,
                    "learning_speed": 9.0,
                }
            ),
        )
        for minutes, metrics in zip((50, 40, 30), self.HISTORY):
            self._session("market_sort", minutes, result=self._result(metrics))
        current = self._session("market_sort", 10, result=self._result(self.CURRENT))
        return familiarization, current

    def test_current_session_uses_history_without_familiarization(self):
        _, current = self._play_all()

        run_command()

        # 歷史只有後 3 場（熟悉場極端的數字不能混進去）
        expected_z, _ = calculate_executive_function_z_score(
            self.CURRENT, self.HISTORY, {}
        )
        result = self._reload(current).result
        self.assertIsNotNone(expected_z)
        self.assertEqual(result["z_score"], round(expected_z, 3))
        self.assertEqual(
            result["cognitive_flexibility_score"],
            z_score_to_display_score(result["z_score"]),
        )
        self.assertEqual(
            set(result["z_scores"]),
            {
                "overall_accuracy_z",
                "switch_accuracy_z",
                "switch_cost_rt_z",
                "learning_speed_z",
            },
        )
        self.assertEqual(result["raw_metrics"], self.CURRENT)

    def test_familiarization_has_null_scores(self):
        familiarization, _ = self._play_all()

        run_command()

        result = self._reload(familiarization).result
        self.assertIsNone(result["z_score"])
        self.assertIsNone(result["cognitive_flexibility_score"])
        self.assertTrue(all(z is None for z in result["z_scores"].values()))

    def test_old_result_without_raw_metrics_is_left_unchanged(self):
        old = {"z_score": 0.2, "cognitive_flexibility_score": 55}
        session = self._session("market_sort", 10, result=old)

        run_command()

        self.assertEqual(self._reload(session).result, old)


class RecomputeCommandBehaviorTests(RecomputeScoresTestCase):
    def _snapshot(self):
        return list(
            GameSession.objects.order_by("pk").values_list("pk", "is_pretest", "result")
        )

    def _play_fridge(self):
        for minutes, (accuracy, speed) in zip((50, 40, 30), TWO_METRIC_HISTORY):
            self._session(
                "fridge_check",
                minutes,
                result={
                    "accuracy": accuracy,
                    "speed_score": speed,
                    "average_reaction_time_ms": 2000,
                    "z_score": 9.0,
                    "standard_score": 99,
                },
            )

    def test_dry_run_changes_nothing_but_reports(self):
        self._play_fridge()
        before = self._snapshot()

        output = run_command("--dry-run")

        self.assertEqual(self._snapshot(), before)
        self.assertIn("dry-run", output)
        self.assertIn("新標記 1 場", output)

    def test_dry_run_reports_same_numbers_as_real_run(self):
        self._play_fridge()

        dry_output = run_command("--dry-run").replace("[dry-run，沒有寫入] ", "")
        real_output = run_command()

        self.assertEqual(dry_output, real_output)

    def test_running_twice_gives_the_same_result(self):
        self._play_fridge()

        run_command()
        after_first = self._snapshot()
        second_output = run_command()

        self.assertEqual(self._snapshot(), after_first)
        self.assertIn("新標記 0 場", second_output)

    def test_no_sessions_runs_cleanly(self):
        output = run_command()

        self.assertIn("新標記 0 場", output)
