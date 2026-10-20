"""diary_zscore.py 的單元測試。"""

from unittest.mock import patch

from django.test import SimpleTestCase

from diary.analysis import analyze_transcription

from .diary_zscore import DIARY_WEIGHTS, calculate_diary_z_score


def scores(fluency, information, sentence, naming, semantic):
    return {
        "fluency_score": fluency,
        "information_score": information,
        "sentence_score": sentence,
        "naming_score": naming,
        "semantic_score": semantic,
    }


class CalculateDiaryZScoreTests(SimpleTestCase):
    def test_weighted_example(self):
        # z：+2、+0.67、+1、+0.8、+1.33
        # 0.2 x 2 + 0.2 x 0.67 + 0.2 x 1 + 0.15 x 0.8 + 0.25 x 1.33 = 1.1865
        z = calculate_diary_z_score(scores(4, 2.67, 3, 2.8, 3.33))
        self.assertAlmostEqual(z, 1.1865, delta=0.001)

    def test_midpoint_is_zero(self):
        self.assertEqual(calculate_diary_z_score(scores(2, 2, 2, 2, 2)), 0)

    def test_range_is_plus_minus_two(self):
        self.assertEqual(calculate_diary_z_score(scores(4, 4, 4, 4, 4)), 2)
        self.assertEqual(calculate_diary_z_score(scores(0, 0, 0, 0, 0)), -2)

    def test_missing_score_is_none(self):
        # 無效日記（錄音太短等）沒有小分數
        self.assertIsNone(calculate_diary_z_score(scores(None, 2, 2, 2, 2)))

    @patch.dict("dashboard.diary_zscore.DIARY_NORMS", {"fluency_score": (2.0, 0.5)})
    def test_each_metric_clamped_after_norm_is_calibrated(self):
        # 之後換上較小的標準差時，流暢度 4 分 → (4 - 2) / 0.5 = 4 → 限制成 2
        z = calculate_diary_z_score(scores(4, 2, 2, 2, 2))
        self.assertAlmostEqual(z, 0.2 * 2, places=3)

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(DIARY_WEIGHTS.values()), 1.0)


class SameWeightsAsDiaryAnalysisTests(SimpleTestCase):
    """權重要跟 diary/analysis.py 的 communication_score 一致。

    常模是中點（平均 2、標準差 1）時，語言 z 應該剛好等於
    communication_score − 2；diary 那邊改了權重，這個測試就會失敗。
    """

    def test_z_equals_communication_score_minus_two(self):
        result = analyze_transcription(
            "今天早上跟朋友去公園散步，然後一起去市場買菜，因為天氣很好所以很開心"
        )

        z = calculate_diary_z_score(result)

        self.assertAlmostEqual(z, result["communication_score"] - 2, delta=0.01)
