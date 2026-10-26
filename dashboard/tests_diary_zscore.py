"""diary_zscore.py 與 services.diary_z_scores 的測試。"""

from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from diary.analysis import analyze_transcription
from diary.models import Diary, DiaryAnalysis
from users.models import User

from .diary_zscore import METRIC_RULES, calculate_language_z_score
from .services import diary_z_scores


def scores(fluency, information, sentence, naming, semantic):
    return {
        "fluency_score": fluency,
        "information_score": information,
        "sentence_score": sentence,
        "naming_score": naming,
        "semantic_score": semantic,
    }


def same_scores(value):
    """5 個小分數都一樣。"""
    return scores(value, value, value, value, value)


# 更早的 3 篇日記，每個小分數都是 1、2、3 → 平均 2、樣本標準差 1，
# 所以每個指標的 z 剛好是「小分數 − 2」
HISTORY = [same_scores(1), same_scores(2), same_scores(3)]


class CalculateLanguageZScoreTests(SimpleTestCase):
    def test_weighted_example(self):
        # z：+2、+0.67、+1、+0.8、+1.33
        # 0.2 x 2 + 0.2 x 0.67 + 0.2 x 1 + 0.15 x 0.8 + 0.25 x 1.33 = 1.1865
        z = calculate_language_z_score(scores(4, 2.67, 3, 2.8, 3.33), HISTORY, [])
        self.assertAlmostEqual(z, 1.1865, delta=0.001)

    def test_same_as_history_mean_is_zero(self):
        self.assertEqual(calculate_language_z_score(same_scores(2), HISTORY, []), 0)

    def test_each_metric_clamped_to_two(self):
        # 歷史很穩定（標準差小）時，流暢度 4 分 → (4 - 2) / 0.5 = 4 → 限制成 2
        stable = [same_scores(2), same_scores(2.5), same_scores(1.5)]
        z = calculate_language_z_score(scores(4, 2, 2, 2, 2), stable, [])
        self.assertAlmostEqual(z, 0.2 * 2, places=3)

    def test_missing_score_is_none(self):
        # 無效日記（錄音太短等）沒有小分數
        self.assertIsNone(
            calculate_language_z_score(scores(None, 2, 2, 2, 2), HISTORY, [])
        )

    def test_cold_start_uses_population(self):
        # 自己只有 1 篇更早的日記 → 借全體使用者的
        z = calculate_language_z_score(same_scores(3), [same_scores(4)], HISTORY)
        self.assertEqual(z, 1)

    def test_not_enough_history_is_none(self):
        self.assertIsNone(calculate_language_z_score(same_scores(3), [], HISTORY[:2]))

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(weight for weight, _ in METRIC_RULES.values()), 1.0)


class SameWeightsAsDiaryAnalysisTests(SimpleTestCase):
    """權重要跟 diary/analysis.py 的 communication_score 一致。

    歷史是平均 2、標準差 1 時，語言 z 應該剛好等於 communication_score − 2；
    diary 那邊改了權重，這個測試就會失敗。
    """

    def test_z_equals_communication_score_minus_two(self):
        result = analyze_transcription(
            "今天早上跟朋友去公園散步，然後一起去市場買菜，因為天氣很好所以很開心"
        )

        z = calculate_language_z_score(result, HISTORY, [])

        self.assertAlmostEqual(z, result["communication_score"] - 2, delta=0.01)


class DiaryZScoresTests(TestCase):
    """services.diary_z_scores：每篇只跟「更早建立」的有效日記比。"""

    def setUp(self):
        self.user = User.objects.create_user(username="grandma", password="pw123456")
        self.other = User.objects.create_user(username="other", password="pw123456")
        self.now = timezone.now()

    def _diary(self, sub_score, *, user=None, days_ago, is_valid=True):
        diary = Diary.objects.create(user=user or self.user, status="done")
        Diary.objects.filter(pk=diary.pk).update(
            created_at=self.now - timedelta(days=days_ago)
        )
        values = same_scores(sub_score if is_valid else None)
        DiaryAnalysis.objects.create(diary=diary, is_valid=is_valid, **values)

    def _history(self, user=None, days_ago=30):
        for value in (1, 2, 3):
            self._diary(value, user=user, days_ago=days_ago + value)

    def _z_scores(self, **kwargs):
        return [z for _, z in diary_z_scores(self.user, **kwargs)]

    def test_first_three_diaries_have_no_score(self):
        # 系統裡第一篇到第三篇：更早的日記不滿 3 篇，算不出 z
        self._history()

        self.assertEqual(self._z_scores(), [])

    def test_compares_with_own_earlier_diaries(self):
        self._history()
        self._diary(3, days_ago=1)

        self.assertEqual(self._z_scores(), [1])

    def test_diaries_before_period_still_count_as_history(self):
        # 期間只看近 7 天，但 30 天前的日記還是拿來當歷史
        self._history(days_ago=30)
        self._diary(3, days_ago=1)

        start = self.now - timedelta(days=7)
        self.assertEqual(self._z_scores(start=start), [1])

    def test_later_diaries_are_not_history(self):
        self._history()
        self._diary(3, days_ago=5)
        self._diary(0, days_ago=1)  # 比較晚寫的不影響 5 天前那篇

        end = self.now - timedelta(days=2)
        self.assertEqual(self._z_scores(end=end), [1])

    def test_same_time_diaries_do_not_compare_with_each_other(self):
        self._history()
        self._diary(3, days_ago=1)
        self._diary(3, days_ago=1)  # 同一時間建立：兩篇都只跟歷史比

        self.assertEqual(self._z_scores(), [1, 1])

    def test_new_user_borrows_population_history(self):
        # 自己第一篇，借別人的 3 篇當基準
        self._history(user=self.other)
        self._diary(3, days_ago=1)

        self.assertEqual(self._z_scores(), [1])

    def test_other_users_diaries_not_in_result(self):
        self._history()
        self._diary(3, user=self.other, days_ago=1)

        self.assertEqual(self._z_scores(), [])

    def test_invalid_diaries_are_skipped(self):
        self._history()
        self._diary(0, days_ago=2, is_valid=False)  # 不算結果，也不當歷史
        self._diary(3, days_ago=1)

        self.assertEqual(self._z_scores(), [1])
