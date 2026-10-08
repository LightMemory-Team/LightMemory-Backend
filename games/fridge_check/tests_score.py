"""
fridge_check Z-Score 與計分邏輯單元測試。
驗證 Z-score 計算、±2 clamp 限制、跨遊戲 standard_score 換算以及 calculate_final_result 整合。
"""

import django
django.setup()

from django.test import SimpleTestCase

from games.fridge_check.services import (
    calculate_z_score,
    calculate_final_result,
    FRIDGE_SCORE_NORM,
    Z_SCORE_CLAMP,
    TOTAL_QUESTIONS,
)


class FridgeCheckZScoreTests(SimpleTestCase):
    def test_calculate_z_score_at_mean(self):
        """當分數等於常模平均值時，Z = 0.0，標準分數為 50。"""
        res = calculate_z_score(70.0)
        self.assertEqual(res["z_score"], 0.0)
        self.assertEqual(res["standard_score"], 50)

    def test_calculate_z_score_one_std_above(self):
        """高於平均 1 個標準差 (80 分)，Z = 1.0，標準分數為 70。"""
        res = calculate_z_score(80.0)
        self.assertEqual(res["z_score"], 1.0)
        self.assertEqual(res["standard_score"], 70)

    def test_calculate_z_score_one_std_below(self):
        """低於平均 1 個標準差 (60 分)，Z = -1.0，標準分數為 30。"""
        res = calculate_z_score(60.0)
        self.assertEqual(res["z_score"], -1.0)
        self.assertEqual(res["standard_score"], 30)

    def test_calculate_z_score_upper_clamp(self):
        """
        高於上限 (+2 SD) 時 clamp 在 +2.0：
        100 分 -> raw Z = (100 - 70) / 10 = +3.0 -> clamp 為 2.0，標準分數為 90。
        """
        res = calculate_z_score(100.0)
        self.assertEqual(res["z_score"], 2.0)
        self.assertEqual(res["standard_score"], 90)

    def test_calculate_z_score_lower_clamp(self):
        """
        低於下限 (-2 SD) 時 clamp 在 -2.0：
        30 分 -> raw Z = (30 - 70) / 10 = -4.0 -> clamp 為 -2.0，標準分數為 10。
        """
        res = calculate_z_score(30.0)
        self.assertEqual(res["z_score"], -2.0)
        self.assertEqual(res["standard_score"], 10)

    def test_calculate_z_score_rounding(self):
        """測試小數點四捨五入（Z-score 3 位小數，standard_score 整數）。"""
        # 75 分 -> Z = (75 - 70) / 10 = 0.5 -> standard_score = 50 + 20 * 0.5 = 60
        res = calculate_z_score(75.0)
        self.assertEqual(res["z_score"], 0.5)
        self.assertEqual(res["standard_score"], 60)

        # 73.5 分 -> Z = (73.5 - 70) / 10 = 0.35 -> standard_score = 50 + 20 * 0.35 = 57
        res = calculate_z_score(73.5)
        self.assertEqual(res["z_score"], 0.35)
        self.assertEqual(res["standard_score"], 57)


class FridgeCheckFinalResultTests(SimpleTestCase):
    def test_calculate_final_result_includes_z_score_and_standard_score(self):
        """測試 calculate_final_result 完整回傳欄位與原本計分一致性。"""
        fake_session = {
            "state": {
                "total_correct": 8,
                "speed_score": 76,
                "medium_correct": 3,
                "hard_correct": 2,
                "skipped_question_count": 1,
                "total_reaction_time_ms": 24500,
                "answer_count": 10,
                "current_stage": "hard",
            }
        }

        result = calculate_final_result(fake_session)

        # 1. 驗證原本計分公式不變
        # accuracy = 8 / 10 * 100 = 80.0
        self.assertEqual(result["accuracy"], 80.0)
        # speed_score = 76
        self.assertEqual(result["speed_score"], 76)
        # difficulty_bonus = 3 * 0.5 + 2 * 1.0 = 3.5
        self.assertEqual(result["difficulty_bonus"], 3.5)
        # error_penalty = 1 * 2 = 2
        self.assertEqual(result["error_penalty"], 2)
        # raw_final_score = 80.0 * 0.7 + 76 * 0.3 + 3.5 - 2 = 56.0 + 22.8 + 3.5 - 2 = 80.3
        self.assertEqual(result["final_score"], 80.3)

        # 2. 驗證 Z-score 與 standard_score
        # Z = (80.3 - 70) / 10 = 1.03
        self.assertEqual(result["z_score"], 1.03)
        # standard_score = round(50 + 20 * 1.03) = round(70.6) = 71
        self.assertEqual(result["standard_score"], 71)

        # 3. 驗證基本欄位存在
        self.assertEqual(result["total_correct"], 8)
        self.assertEqual(result["total_questions"], TOTAL_QUESTIONS)
        self.assertEqual(result["final_difficulty"], "hard")
        self.assertEqual(result["average_reaction_time_ms"], 2450)
        self.assertIn("completed_at", result)
