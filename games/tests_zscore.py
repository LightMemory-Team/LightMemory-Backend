"""zscore.py 的單元測試。"""

import random
import statistics

from django.test import SimpleTestCase

from .zscore import (
    PRIOR_STRENGTH,
    calculate_dimension_z_score,
    choose_baseline,
    compute_baseline,
    effective_weights,
    metric_z_scores,
    pooled_population_baseline,
    prior_composite_variance,
    restandardize,
    shrunk_baseline,
    to_z_score,
    weighted_average,
    weighted_metric_z_score,
    z_score_to_display_score,
)

# 平均 0.6、樣本標準差 0.1
HISTORY_VALUES = [0.5, 0.6, 0.7]


class ComputeBaselineTests(SimpleTestCase):
    def test_returns_mean_and_sample_std(self):
        mean, std = compute_baseline(HISTORY_VALUES)
        self.assertAlmostEqual(mean, 0.6)
        self.assertAlmostEqual(std, 0.1)

    def test_less_than_three_sessions_is_none(self):
        self.assertIsNone(compute_baseline([0.5, 0.7]))

    def test_none_values_are_not_counted(self):
        self.assertIsNone(compute_baseline([0.5, None, 0.7]))

    def test_zero_std_is_none(self):
        # 每場都一樣，標準差 0 無法相除
        self.assertIsNone(compute_baseline([0.8, 0.8, 0.8]))


class ChooseBaselineTests(SimpleTestCase):
    def test_uses_personal_when_enough_sessions(self):
        baseline = choose_baseline(HISTORY_VALUES, [10, 20, 30])
        self.assertAlmostEqual(baseline[0], 0.6)

    def test_cold_start_falls_back_to_population(self):
        baseline = choose_baseline([0.5], [10, 20, 30])
        self.assertAlmostEqual(baseline[0], 20)

    def test_both_insufficient_is_none(self):
        self.assertIsNone(choose_baseline([0.5], [10, 20]))


class ToZScoreTests(SimpleTestCase):
    def test_higher_is_better(self):
        # (0.8 - 0.6) / 0.1 = 2
        self.assertAlmostEqual(to_z_score(0.8, (0.6, 0.1)), 2.0)

    def test_lower_is_better_is_reversed(self):
        # 反應時間 700 比平均 800 快 → -1 * (700 - 800) / 100 = +1
        self.assertAlmostEqual(to_z_score(700, (800, 100), lower_is_better=True), 1.0)

    def test_missing_value_or_baseline_is_none(self):
        self.assertIsNone(to_z_score(None, (0.6, 0.1)))
        self.assertIsNone(to_z_score(0.8, None))

    def test_above_two_is_clamped(self):
        # (1.0 - 0.6) / 0.1 = 4 → 限制成 2
        self.assertAlmostEqual(to_z_score(1.0, (0.6, 0.1)), 2.0)

    def test_below_minus_two_is_clamped(self):
        # (0.2 - 0.6) / 0.1 = -4 → 限制成 -2
        self.assertAlmostEqual(to_z_score(0.2, (0.6, 0.1)), -2.0)

    def test_lower_is_better_is_clamped_after_reversing(self):
        # 反應時間 1200 比平均 800 慢很多 → -1 * (1200 - 800) / 100 = -4 → -2
        self.assertAlmostEqual(to_z_score(1200, (800, 100), lower_is_better=True), -2.0)


class WeightedAverageTests(SimpleTestCase):
    def test_weighted_sum(self):
        # 0.4 * 1 + 0.6 * 2 = 1.6
        self.assertAlmostEqual(weighted_average([(1, 0.4), (2, 0.6)]), 1.6)

    def test_none_is_skipped_and_weights_rescaled(self):
        # 只剩 (1, 0.4) → 1 * 0.4 / 0.4 = 1
        self.assertAlmostEqual(weighted_average([(1, 0.4), (None, 0.6)]), 1.0)

    def test_all_none_is_none(self):
        self.assertIsNone(weighted_average([(None, 0.4), (None, 0.6)]))


RULES = {
    "accuracy": (0.5, False),
    "avg_response_time_ms": (0.5, True),
}


def _session(**stages):
    """組一場歷史資料：_session(basic=(正確率, 反應時間), ...)"""
    return {
        stage: {"accuracy": acc, "avg_response_time_ms": rt}
        for stage, (acc, rt) in stages.items()
    }


# basic：正確率平均 0.6／標準差 0.1，反應時間平均 800／標準差 100
BASIC_HISTORY = [
    _session(basic=(0.5, 700)),
    _session(basic=(0.6, 800)),
    _session(basic=(0.7, 900)),
]


class CalculateDimensionZScoreTests(SimpleTestCase):
    def test_only_basic_uses_basic_weight_one(self):
        current = _session(basic=(0.8, 700))
        # z_正確率 = +2、z_反應時間 = +1 → 0.5 * 2 + 0.5 * 1 = 1.5
        score = calculate_dimension_z_score(current, BASIC_HISTORY, [], RULES)
        self.assertAlmostEqual(score, 1.5)

    def test_cross_stage_weights_by_highest_stage(self):
        # intermediate 歷史跟 basic 一樣的分布
        history = [
            _session(basic=(0.5, 700), intermediate=(0.5, 700)),
            _session(basic=(0.6, 800), intermediate=(0.6, 800)),
            _session(basic=(0.7, 900), intermediate=(0.7, 900)),
        ]
        # basic 階段分數 1.5；intermediate 剛好等於平均 → 0
        current = _session(basic=(0.8, 700), intermediate=(0.6, 800))
        # 0.3 * 1.5 + 0.7 * 0 = 0.45
        score = calculate_dimension_z_score(current, history, [], RULES)
        self.assertAlmostEqual(score, 0.45)

    def test_cold_start_uses_population_history(self):
        current = _session(basic=(0.8, 700))
        personal = BASIC_HISTORY[:1]  # 個人只有 1 場
        score = calculate_dimension_z_score(current, personal, BASIC_HISTORY, RULES)
        self.assertAlmostEqual(score, 1.5)

    def test_stage_without_history_is_skipped(self):
        # 第一次玩到 intermediate，沒有任何歷史 → 只算 basic
        current = _session(basic=(0.8, 700), intermediate=(0.9, 500))
        score = calculate_dimension_z_score(current, BASIC_HISTORY, [], RULES)
        self.assertAlmostEqual(score, 1.5)

    def test_dimension_score_stays_within_two(self):
        # z_正確率 = (1.0 - 0.6) / 0.1 = 4 → 2；z_反應時間 = -(300 - 800) / 100 = 5 → 2
        current = _session(basic=(1.0, 300))
        score = calculate_dimension_z_score(current, BASIC_HISTORY, [], RULES)
        self.assertAlmostEqual(score, 2.0)

    def test_no_history_at_all_is_none(self):
        current = _session(basic=(0.8, 700))
        self.assertIsNone(calculate_dimension_z_score(current, [], [], RULES))

    def test_no_current_metrics_is_none(self):
        self.assertIsNone(calculate_dimension_z_score({}, BASIC_HISTORY, [], RULES))


# 單一指標、沒有分階段的遊戲（冰箱檢查、市場買菜）用的規則
SCORE_RULES = {"raw_score": (1.0, False)}


def _history(*values):
    return [{"raw_score": v} for v in values]


class MetricZScoresTests(SimpleTestCase):
    """冷啟動三種情況：自己 ≥ 3 場、自己不滿 3 場借全體、全體也不夠。"""

    def test_uses_personal_history_when_enough(self):
        # 自己：平均 70、標準差 10 → (80 - 70) / 10 = 1；全體的資料不會用到
        z = metric_z_scores(
            {"raw_score": 80},
            _history(60, 70, 80),
            _history(10, 20, 30),
            SCORE_RULES,
        )
        self.assertAlmostEqual(z["raw_score"], 1.0)

    def test_falls_back_to_population_when_personal_not_enough(self):
        # 自己只有 2 場 → 改用全體：平均 50、標準差 10 → (60 - 50) / 10 = 1
        z = metric_z_scores(
            {"raw_score": 60},
            _history(90, 95),
            _history(40, 50, 60),
            SCORE_RULES,
        )
        self.assertAlmostEqual(z["raw_score"], 1.0)

    def test_no_data_when_population_also_not_enough(self):
        z = metric_z_scores({"raw_score": 60}, _history(90), _history(50), SCORE_RULES)
        self.assertIsNone(z["raw_score"])

    def test_lower_is_better_is_reversed(self):
        z = metric_z_scores(
            {"rt": 900},
            [{"rt": 700}, {"rt": 800}, {"rt": 900}],
            [],
            {"rt": (1.0, True)},
        )
        self.assertAlmostEqual(z["rt"], -1.0)

    def test_old_history_without_metric_is_ignored(self):
        # 舊場次沒有這個欄位（例如改版前），當作無資料略過
        z = metric_z_scores(
            {"raw_score": 80},
            [{}, *_history(60, 70, 80)],
            [],
            SCORE_RULES,
        )
        self.assertAlmostEqual(z["raw_score"], 1.0)


class WeightedMetricZScoreTests(SimpleTestCase):
    RULES = {"a": (0.6, False), "b": (0.4, False)}

    def test_weighted_by_rules(self):
        score = weighted_metric_z_score({"a": 1.0, "b": -1.0}, self.RULES)
        self.assertAlmostEqual(score, 0.2)

    def test_missing_metric_reweights(self):
        self.assertAlmostEqual(
            weighted_metric_z_score({"a": 1.0, "b": None}, self.RULES), 1.0
        )

    def test_all_missing_is_none(self):
        self.assertIsNone(weighted_metric_z_score({"a": None, "b": None}, self.RULES))


class ZScoreToDisplayScoreTests(SimpleTestCase):
    def test_minus_two_becomes_minimum_one(self):
        # 50 + 25 * -2 = 0 → 最低 1 分
        self.assertEqual(z_score_to_display_score(-2), 1)

    def test_zero_becomes_fifty(self):
        self.assertEqual(z_score_to_display_score(0), 50)

    def test_plus_two_becomes_hundred(self):
        self.assertEqual(z_score_to_display_score(2), 100)

    def test_one_becomes_seventy_five(self):
        self.assertEqual(z_score_to_display_score(1), 75)

    def test_none_stays_none(self):
        # 資料不足時沒有 z，分數回傳 null
        self.assertIsNone(z_score_to_display_score(None))


class PooledPopulationBaselineTests(SimpleTestCase):
    def test_not_enough_within_person_degrees_of_freedom_is_none(self):
        # 兩個人各 2 場：自由度 = 1 + 1 = 2，不到 3
        self.assertIsNone(pooled_population_baseline({1: [1, 3], 2: [10, 12]}))

    def test_one_session_per_user_has_no_within_person_data(self):
        self.assertIsNone(pooled_population_baseline({1: [1], 2: [2], 3: [3]}))

    def test_pools_within_person_variance_not_between_person(self):
        # 每個人自己的變異數都是 2；人跟人之間差很多（1～22），不能被算進去
        histories = {"A": [1, 3], "B": [10, 12], "C": [20, 22]}
        mean, within_var = pooled_population_baseline(histories)
        self.assertAlmostEqual(within_var, 2)
        self.assertAlmostEqual(mean, 68 / 6)
        # 全部混在一起算的變異數會遠大於 2
        all_values = [v for values in histories.values() for v in values]
        self.assertGreater(statistics.variance(all_values), 50)

    def test_none_values_are_ignored(self):
        histories = {"A": [1, None, 3, 5], "B": [2, 4]}
        self.assertIsNotNone(pooled_population_baseline(histories))

    def test_empty_is_none(self):
        self.assertIsNone(pooled_population_baseline({}))


class ShrunkBaselineTests(SimpleTestCase):
    POPULATION = (0.0, 4.0)  # 全體：平均 0、個人內變異數 4（標準差 2）

    def test_no_personal_history_uses_population(self):
        mean, std = shrunk_baseline([], self.POPULATION)
        self.assertAlmostEqual(mean, 0.0)
        self.assertAlmostEqual(std, 2.0)

    def test_one_session_still_has_a_baseline(self):
        # 熟悉場之後的第一場就能算 z：n = 1 時標準差仍用全體的
        mean, std = shrunk_baseline([10], self.POPULATION)
        self.assertAlmostEqual(mean, 10 * 1 / (1 + PRIOR_STRENGTH))
        self.assertAlmostEqual(std, 2.0)

    def test_many_sessions_close_to_pure_personal(self):
        values = [50 + (i % 5 - 2) for i in range(100)]
        mean, std = shrunk_baseline(values, self.POPULATION)
        personal_mean, personal_std = compute_baseline(values)
        self.assertLess(abs(mean - personal_mean) / personal_mean, 0.05)
        self.assertLess(abs(std - personal_std) / personal_std, 0.05)

    def test_mean_moves_monotonically_toward_personal(self):
        # 個人每場都是 10、全體平均 0：n 越大，基準平均越接近 10
        means = [shrunk_baseline([10] * n, self.POPULATION)[0] for n in range(0, 11)]
        self.assertEqual(means[0], 0.0)
        self.assertEqual(means, sorted(means))
        self.assertEqual(len(set(means)), len(means))
        self.assertLess(means[-1], 10)

    def test_population_not_enough_falls_back_to_personal_baseline(self):
        self.assertEqual(
            shrunk_baseline(HISTORY_VALUES, None), compute_baseline(HISTORY_VALUES)
        )
        self.assertIsNone(shrunk_baseline([0.5, 0.7], None))

    def test_none_values_are_not_counted(self):
        self.assertEqual(
            shrunk_baseline([None, 10], self.POPULATION),
            shrunk_baseline([10], self.POPULATION),
        )

    def test_zero_variance_is_none(self):
        self.assertIsNone(shrunk_baseline([5, 5, 5], (0.0, 0.0)))


class EffectiveWeightsTests(SimpleTestCase):
    RULES = {"a": (0.5, False), "b": (0.3, True), "c": (0.2, False)}

    def test_all_metrics_present(self):
        z_by_metric = {"a": 1.0, "b": 0.5, "c": -1.0}
        self.assertEqual(effective_weights(z_by_metric, self.RULES), [0.5, 0.3, 0.2])

    def test_missing_metric_is_left_out(self):
        z_by_metric = {"a": 1.0, "b": None, "c": -1.0}
        self.assertEqual(effective_weights(z_by_metric, self.RULES), [0.5, 0.2])

    def test_stage_weight_is_multiplied(self):
        z_by_metric = {"a": 1.0, "b": 0.5, "c": -1.0}
        self.assertEqual(
            effective_weights(z_by_metric, self.RULES, stage_weight=0.5),
            [0.25, 0.15, 0.1],
        )


class PriorCompositeVarianceTests(SimpleTestCase):
    def test_single_metric_is_one(self):
        self.assertAlmostEqual(prior_composite_variance([1.0]), 1.0)

    def test_five_equal_weights_is_point_two(self):
        self.assertAlmostEqual(prior_composite_variance([1] * 5), 0.2)

    def test_weights_are_normalized_first(self):
        self.assertAlmostEqual(
            prior_composite_variance([2, 2]), prior_composite_variance([0.5, 0.5])
        )

    def test_no_weights_is_none(self):
        self.assertIsNone(prior_composite_variance([]))


class RestandardizeTests(SimpleTestCase):
    def test_no_reference_uses_prior_only(self):
        # 沒有參考場次：標準差 = √prior_var
        self.assertAlmostEqual(restandardize(0.5, [], 0.25), 1.0)

    def test_missing_composite_or_prior_is_none(self):
        self.assertIsNone(restandardize(None, [0.1, 0.2], 0.25))
        self.assertIsNone(restandardize(0.5, [0.1, 0.2], None))

    def test_extreme_composite_is_clamped_to_two(self):
        self.assertEqual(restandardize(100, [0.1, -0.1, 0.2], 0.2), 2)
        self.assertEqual(restandardize(-100, [0.1, -0.1, 0.2], 0.2), -2)

    def test_clamped_values_become_one_to_hundred_display_scores(self):
        self.assertEqual(z_score_to_display_score(restandardize(100, [], 0.2)), 100)
        self.assertEqual(z_score_to_display_score(restandardize(-100, [], 0.2)), 1)

    def test_none_reference_values_are_ignored(self):
        self.assertAlmostEqual(
            restandardize(0.3, [None, 0.1, -0.1], 0.2),
            restandardize(0.3, [0.1, -0.1], 0.2),
        )

    def test_many_references_follow_personal_spread(self):
        # 參考場次很多時，標準差接近個人自己的標準差（約 0.5），不是理論的 1
        references = [0.5 * (-1) ** i for i in range(100)]
        z = restandardize(0.5, references, 1.0)
        self.assertGreater(z, 0.9)
        self.assertLess(z, 1.1)


class SecondStageStandardizationTests(SimpleTestCase):
    """整份規格最重要的驗收：1 個指標與 5 個指標，最終 z 的波動要一致。"""

    SESSIONS = 200

    def _final_z_scores(self, metric_count, seed):
        rng = random.Random(seed)
        rules = {f"m{i}": (1.0, False) for i in range(metric_count)}
        baseline = (0.0, 1.0)  # 每個指標原始值 ~ N(0, 1)，基準已知
        composites, finals = [], []
        for _ in range(self.SESSIONS):
            z_by_metric = {
                name: to_z_score(rng.gauss(0, 1), baseline) for name in rules
            }
            composite = weighted_average(
                [(z, rules[name][0]) for name, z in z_by_metric.items()]
            )
            prior_var = prior_composite_variance(effective_weights(z_by_metric, rules))
            finals.append(restandardize(composite, composites, prior_var))
            composites.append(composite)  # 算完才放進歷史
        return finals

    def test_final_z_spread_is_the_same_for_one_and_five_metrics(self):
        sd_one = statistics.stdev(self._final_z_scores(1, seed=1))
        sd_five = statistics.stdev(self._final_z_scores(5, seed=2))
        self.assertLess(abs(sd_one - sd_five), 0.15)

    def test_without_restandardizing_five_metrics_would_be_much_narrower(self):
        # 對照組：不做第二階段時，5 個指標的波動明顯比 1 個小
        def composite_sd(metric_count, seed):
            rng = random.Random(seed)
            composites = []
            for _ in range(self.SESSIONS):
                zs = [
                    to_z_score(rng.gauss(0, 1), (0.0, 1.0)) for _ in range(metric_count)
                ]
                composites.append(sum(zs) / metric_count)
            return statistics.stdev(composites)

        self.assertGreater(composite_sd(1, 1) - composite_sd(5, 2), 0.3)

    def test_final_z_stays_within_two(self):
        finals = self._final_z_scores(5, seed=3)
        self.assertTrue(all(-2 <= z <= 2 for z in finals))
