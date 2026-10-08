"""
market_shopping Z-Score 與計分邏輯單元測試。
驗證 Z-score 計算、±2 clamp 限制、跨遊戲 standard_score 換算以及 calculate_final_result 整合。
"""

import django
django.setup()

from django.test import SimpleTestCase

from games.market_shopping.services import (
    calculate_z_score,
    calculate_final_result,
    MARKET_SHOPPING_NORM,
    Z_SCORE_CLAMP,
    TOTAL_QUESTIONS,
)


class MarketShoppingZScoreTests(SimpleTestCase):
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

        # 85.5 分 -> Z = (85.5 - 70) / 10 = 1.55 -> standard_score = 50 + 20 * 1.55 = 81
        res = calculate_z_score(85.5)
        self.assertEqual(res["z_score"], 1.55)
        self.assertEqual(res["standard_score"], 81)


class MarketShoppingFinalResultTests(SimpleTestCase):
    def test_calculate_final_result_includes_z_score_and_standard_score(self):
        """測試 calculate_final_result 完整回傳欄位與分數換算。"""
        fake_session = {
            "state": {
                "total_correct": 9,
                "first_try_correct_count": 8,
                "current_stage": "hard",
            }
        }

        result = calculate_final_result(fake_session)

        # 1. 驗證原始指標
        # accuracy = 8 / 10 * 100 = 80.0
        self.assertEqual(result["accuracy"], 80.0)
        self.assertEqual(result["raw_score"], 80.0)
        self.assertEqual(result["total_correct"], 9)
        self.assertEqual(result["first_try_correct_count"], 8)
        self.assertEqual(result["total_questions"], TOTAL_QUESTIONS)
        self.assertEqual(result["difficulty"], "hard")

        # 2. 驗證 Z-score 與 standard_score
        # Z = (80.0 - 70) / 10 = 1.0
        self.assertEqual(result["z_score"], 1.0)
        # standard_score = round(50 + 20 * 1.0) = 70
        self.assertEqual(result["standard_score"], 70)
        self.assertIn("completed_at", result)
