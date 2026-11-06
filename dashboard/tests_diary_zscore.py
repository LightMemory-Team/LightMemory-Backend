"""diary_zscore.py 與 services.diary_z_scores 的測試。"""

from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from diary.models import Diary, DiaryAnalysis
from users.models import User

from .diary_zscore import METRIC_RULES, calculate_language_z_score
from .services import SEED_DIARY_AUDIO_PREFIX, diary_z_scores


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
# 所以每個指標的 z 剛好是「小分數 − 2」；三篇的合成分數是 -1、0、+1（變異數和 2）
HISTORY = [same_scores(1), same_scores(2), same_scores(3)]

# 5 個指標等權重、互不相關的理論變異數 = 5 × 0.2² = 0.2；
# 收縮後的合成分數變異數 = (2 + 3 × 0.2) ÷ (2 + 3) = 0.52
COMPOSITE_VAR = (2 + 3 * 0.2) / (2 + 3)

# 小分數都是 3（z = +1）→ 合成 1 → 1 ÷ √0.52 ≈ 1.387
Z_OF_SCORE_THREE = 1.387


class CalculateLanguageZScoreTests(SimpleTestCase):
    def test_weighted_example(self):
        # z：+2、+0.67、+1、+0.8、+1.33 → 等權重合成 5.8 ÷ 5 = 1.16
        z = calculate_language_z_score(scores(4, 2.67, 3, 2.8, 3.33), HISTORY, {})
        self.assertAlmostEqual(z, 1.16 / COMPOSITE_VAR**0.5, delta=0.001)

    def test_same_as_history_mean_is_zero(self):
        self.assertEqual(calculate_language_z_score(same_scores(2), HISTORY, {}), 0)

    def test_each_metric_clamped_to_two(self):
        # 歷史很穩定（標準差 0.5）時，流暢度 4 分 → (4 - 2) / 0.5 = 4 → 限制成 2，
        # 其他指標 z = 0 → 合成 2 ÷ 5 = 0.4；參考場次合成 0、+1、-1（變異數和 2）
        stable = [same_scores(2), same_scores(2.5), same_scores(1.5)]
        z = calculate_language_z_score(scores(4, 2, 2, 2, 2), stable, {})
        self.assertAlmostEqual(z, 0.4 / COMPOSITE_VAR**0.5, places=3)

    def test_final_z_stays_within_two(self):
        z = calculate_language_z_score(same_scores(4), HISTORY, {})
        self.assertEqual(z, 2)

    def test_missing_score_is_none(self):
        # 無效日記（錄音太短等）沒有小分數
        self.assertIsNone(
            calculate_language_z_score(scores(None, 2, 2, 2, 2), HISTORY, {})
        )

    def test_cold_start_borrows_population(self):
        # 自己只有 1 篇更早的日記（4 分），全體是兩位使用者各 3 篇
        # （平均 2、個人內標準差 1）
        # 基準平均 (4 + 3 × 2) ÷ 4 = 2.5 → 3 分的 z = +0.5 → 合成 0.5；
        # 自己只有 1 篇參考，合成分數的變異數完全用理論值 0.2
        population = {"u1": HISTORY, "u2": HISTORY}
        z = calculate_language_z_score(same_scores(3), [same_scores(4)], population)
        self.assertAlmostEqual(z, 0.5 / 0.2**0.5, places=3)

    def test_one_other_user_is_not_enough_population(self):
        # 只有一位其他使用者 3 篇（個人內自由度 2，不到 3）→ 沒有基準
        self.assertIsNone(
            calculate_language_z_score(same_scores(3), [], {"u1": HISTORY})
        )

    def test_weights_are_equal(self):
        weights = {weight for weight, _ in METRIC_RULES.values()}
        self.assertEqual(len(weights), 1)


class DiaryZScoresTests(TestCase):
    """services.diary_z_scores：每篇只跟「更早建立」的有效日記比。"""

    def setUp(self):
        self.user = User.objects.create_user(username="grandma", password="pw123456")
        self.other = User.objects.create_user(username="other", password="pw123456")
        self.third = User.objects.create_user(username="third", password="pw123456")
        self.now = timezone.now()

    def _diary(self, sub_score, *, user=None, days_ago, is_valid=True, audio_path=""):
        diary = Diary.objects.create(
            user=user or self.user, status="done", audio_path=audio_path
        )
        Diary.objects.filter(pk=diary.pk).update(
            created_at=self.now - timedelta(days=days_ago)
        )
        values = same_scores(sub_score if is_valid else None)
        DiaryAnalysis.objects.create(diary=diary, is_valid=is_valid, **values)

    def _history(self, user=None, days_ago=30, **kwargs):
        for value in (1, 2, 3):
            self._diary(value, user=user, days_ago=days_ago + value, **kwargs)

    def _z_scores(self, **kwargs):
        return [z for _, z in diary_z_scores(self.user, **kwargs)]

    def test_first_three_diaries_have_no_score(self):
        # 系統裡第一篇到第三篇：更早的日記不滿 3 篇，算不出 z
        self._history()

        self.assertEqual(self._z_scores(), [])

    def test_compares_with_own_earlier_diaries(self):
        self._history()
        self._diary(3, days_ago=1)

        self.assertEqual(self._z_scores(), [Z_OF_SCORE_THREE])

    def test_diaries_before_period_still_count_as_history(self):
        # 期間只看近 7 天，但 30 天前的日記還是拿來當歷史
        self._history(days_ago=30)
        self._diary(3, days_ago=1)

        start = self.now - timedelta(days=7)
        self.assertEqual(self._z_scores(start=start), [Z_OF_SCORE_THREE])

    def test_later_diaries_are_not_history(self):
        self._history()
        self._diary(3, days_ago=5)
        self._diary(0, days_ago=1)  # 比較晚寫的不影響 5 天前那篇

        end = self.now - timedelta(days=2)
        self.assertEqual(self._z_scores(end=end), [Z_OF_SCORE_THREE])

    def test_same_time_diaries_do_not_compare_with_each_other(self):
        self._history()
        self._diary(3, days_ago=1)
        self._diary(3, days_ago=1)  # 同一時間建立：兩篇都只跟歷史比

        self.assertEqual(self._z_scores(), [Z_OF_SCORE_THREE, Z_OF_SCORE_THREE])

    def test_new_user_borrows_population_history(self):
        # 兩位其他使用者各 3 篇當基準（平均 2、個人內標準差 1），自己第一篇 2.5 分：
        # z = +0.5 → 合成 0.5；自己沒有參考場次，變異數用理論值 0.2 → 0.5 ÷ √0.2 ≈ 1.118
        self._history(user=self.other)
        self._history(user=self.third)
        self._diary(2.5, days_ago=1)

        self.assertEqual(self._z_scores(), [1.118])

    def test_one_other_user_is_not_enough_population(self):
        self._history(user=self.other)
        self._diary(2.5, days_ago=1)

        self.assertEqual(self._z_scores(), [])

    def test_staff_users_are_not_population(self):
        self.other.is_staff = True
        self.other.save()
        self._history(user=self.other)
        self._history(user=self.third)
        self._diary(2.5, days_ago=1)

        self.assertEqual(self._z_scores(), [])

    def test_seed_demo_diaries_are_not_population(self):
        seed_path = f"{SEED_DIARY_AUDIO_PREFIX}0-0.m4a"
        self._history(user=self.other, audio_path=seed_path)
        self._history(user=self.third, audio_path=seed_path)
        self._diary(2.5, days_ago=1)

        self.assertEqual(self._z_scores(), [])

    def test_own_diaries_are_not_counted_as_population(self):
        # 自己只有 2 篇更早的日記；自己的不重複算進全體，全體（別人）也沒有 → 算不出
        self._diary(1, days_ago=10)
        self._diary(2, days_ago=9)
        self._diary(3, days_ago=1)

        self.assertEqual(self._z_scores(), [])

    def test_other_users_diaries_not_in_result(self):
        self._history()
        self._diary(3, user=self.other, days_ago=1)

        self.assertEqual(self._z_scores(), [])

    def test_invalid_diaries_are_skipped(self):
        self._history()
        self._diary(0, days_ago=2, is_valid=False)  # 不算結果，也不當歷史
        self._diary(3, days_ago=1)

        self.assertEqual(self._z_scores(), [Z_OF_SCORE_THREE])
