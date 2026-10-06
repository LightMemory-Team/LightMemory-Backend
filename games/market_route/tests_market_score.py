"""market_score.py 的單元測試。"""

from django.test import SimpleTestCase

from .market_score import (
    calculate_base_score,
    calculate_speed_bonus,
    calculate_step_score,
    calculate_total_score,
)


class CalculateBaseScoreTests(SimpleTestCase):
    def test_first_attempt_correct(self):
        self.assertEqual(calculate_base_score(1, is_correct=True, is_timeout=False), 10)

    def test_second_attempt_correct(self):
        self.assertEqual(calculate_base_score(2, is_correct=True, is_timeout=False), 6)

    def test_third_attempt_correct(self):
        self.assertEqual(calculate_base_score(3, is_correct=True, is_timeout=False), 3)

    def test_wrong_answer_no_penalty(self):
        self.assertEqual(calculate_base_score(1, is_correct=False, is_timeout=False), 0)

    def test_timeout_no_penalty(self):
        self.assertEqual(calculate_base_score(1, is_correct=False, is_timeout=True), 0)


class CalculateSpeedBonusTests(SimpleTestCase):
    def test_fast_enough_gets_bonus(self):
        self.assertEqual(
            calculate_speed_bonus(
                is_correct=True, response_time_ms=400, exposure_time_ms=800
            ),
            2,
        )

    def test_exactly_at_threshold_gets_bonus(self):
        self.assertEqual(
            calculate_speed_bonus(
                is_correct=True, response_time_ms=400, exposure_time_ms=800
            ),
            2,
        )

    def test_too_slow_no_bonus(self):
        self.assertEqual(
            calculate_speed_bonus(
                is_correct=True, response_time_ms=500, exposure_time_ms=800
            ),
            0,
        )

    def test_wrong_answer_no_bonus_even_if_fast(self):
        self.assertEqual(
            calculate_speed_bonus(
                is_correct=False, response_time_ms=100, exposure_time_ms=800
            ),
            0,
        )

    def test_no_response_time_no_bonus(self):
        self.assertEqual(
            calculate_speed_bonus(
                is_correct=True, response_time_ms=None, exposure_time_ms=800
            ),
            0,
        )


class CalculateStepScoreTests(SimpleTestCase):
    def test_basic_stage_first_attempt_no_bonus(self):
        score = calculate_step_score(
            attempt_number=1,
            stage="basic",
            is_correct=True,
            is_timeout=False,
            response_time_ms=1500,
            exposure_time_ms=2000,
        )
        self.assertEqual(score, 10)

    def test_advanced_stage_first_attempt_with_speed_bonus(self):
        score = calculate_step_score(
            attempt_number=1,
            stage="advanced",
            is_correct=True,
            is_timeout=False,
            response_time_ms=400,
            exposure_time_ms=1000,
        )
        # 10 * 1.6 = 16，加上速度加成 2 分 = 18
        self.assertEqual(score, 18)

    def test_intermediate_stage_second_attempt(self):
        score = calculate_step_score(
            attempt_number=2,
            stage="intermediate",
            is_correct=True,
            is_timeout=False,
            response_time_ms=1200,
            exposure_time_ms=1500,
        )
        # 6 * 1.3 = 7.8 -> round(7.8) = 8
        self.assertEqual(score, 8)

    def test_timeout_scores_zero(self):
        score = calculate_step_score(
            attempt_number=1,
            stage="advanced",
            is_correct=False,
            is_timeout=True,
            response_time_ms=None,
            exposure_time_ms=1000,
        )
        self.assertEqual(score, 0)


class CalculateTotalScoreTests(SimpleTestCase):
    def test_sums_all_steps(self):
        step_results = [
            dict(
                attempt_number=1,
                stage="basic",
                is_correct=True,
                is_timeout=False,
                response_time_ms=1500,
                exposure_time_ms=2000,
            ),
            dict(
                attempt_number=1,
                stage="advanced",
                is_correct=True,
                is_timeout=False,
                response_time_ms=400,
                exposure_time_ms=1000,
            ),
        ]
        # 10 + 18 = 28
        self.assertEqual(calculate_total_score(step_results), 28)

    def test_empty_list_is_zero(self):
        self.assertEqual(calculate_total_score([]), 0)
