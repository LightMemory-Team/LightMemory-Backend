"""zscore.py 的單元測試。"""

from django.test import SimpleTestCase

from .zscore import (
    calculate_dimension_z_score,
    choose_baseline,
    compute_baseline,
    to_z_score,
    weighted_average,
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

    def test_no_history_at_all_is_none(self):
        current = _session(basic=(0.8, 700))
        self.assertIsNone(calculate_dimension_z_score(current, [], [], RULES))

    def test_no_current_metrics_is_none(self):
        self.assertIsNone(calculate_dimension_z_score({}, BASIC_HISTORY, [], RULES))
