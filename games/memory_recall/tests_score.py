"""score.py 的單元測試。"""

from django.test import SimpleTestCase

from .score import calculate_step_score, calculate_total_score


class CalculateStepScoreTests(SimpleTestCase):
    def test_basic_stage_correct(self):
        self.assertEqual(calculate_step_score(stage="basic", is_correct=True), 10)

    def test_intermediate_stage_correct(self):
        # 10 * 1.3 = 13
        self.assertEqual(
            calculate_step_score(stage="intermediate", is_correct=True), 13
        )

    def test_advanced_stage_correct(self):
        # 10 * 1.6 = 16
        self.assertEqual(calculate_step_score(stage="advanced", is_correct=True), 16)

    def test_wrong_answer_no_penalty(self):
        self.assertEqual(calculate_step_score(stage="advanced", is_correct=False), 0)


class CalculateTotalScoreTests(SimpleTestCase):
    def test_sums_only_correct_steps(self):
        step_results = [
            {"stage": "basic", "is_correct": True},
            {"stage": "intermediate", "is_correct": True},
            {"stage": "advanced", "is_correct": False},
        ]
        # 10 + 13 + 0 = 23
        self.assertEqual(calculate_total_score(step_results), 23)

    def test_empty_list_is_zero(self):
        self.assertEqual(calculate_total_score([]), 0)
