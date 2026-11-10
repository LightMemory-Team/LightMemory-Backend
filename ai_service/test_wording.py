"""用語檢查（ai_service/wording.py）的測試。

執行：
    python manage.py test ai_service.test_wording --settings=config.settings_test
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from .greeting import generate_greeting
from .weekly_summary import generate_weekly_summary
from .wording import BANNED_WORDS, contains_banned_word, find_banned_word


def fake_ai_reply(text):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


class FindBannedWordTests(SimpleTestCase):
    def test_medical_claims_are_caught(self):
        for text in [
            "多動腦可以預防失智",
            "每天玩遊戲能延緩退化",
            "這樣可以降低失智風險喔",
            "請找醫生診斷看看",
            "有助於治療",
            "療效很好",
            "阿茲海默症的長輩也適合",
            "輕度認知障礙",
            "記憶力下降要注意",
            "病情有進展",
            "症狀改善了",
        ]:
            with self.subTest(text=text):
                self.assertTrue(contains_banned_word(text))

    def test_negative_words_are_caught(self):
        for text in ["你退步了", "最近變差了", "狀況惡化", "能力衰退"]:
            with self.subTest(text=text):
                self.assertTrue(contains_banned_word(text))

    def test_jargon_is_caught_regardless_of_case_and_spacing(self):
        for text in [
            "你的分數很高",
            "z 分數上升",
            "Z分數上升",
            "Z-Score",
            "標準差",
            "認知彈性",
        ]:
            with self.subTest(text=text):
                self.assertTrue(contains_banned_word(text))

    def test_normal_warm_sentences_pass(self):
        for text in [
            "今天也要保持大腦活力喔。",
            "聽起來是很開心的一天！",
            "這張照片是在哪裡拍的呢？",
            "你今天過得真充實！",
            "生病的時候要多休息喔",  # 單字「病」不列入，避免誤傷
            "動物園（Zoo）好好玩",  # 單字 z 不列入
            "這週你玩了 4 天，比上週多 1 天！",
        ]:
            with self.subTest(text=text):
                self.assertFalse(contains_banned_word(text))

    def test_returns_the_matching_word(self):
        self.assertEqual(find_banned_word("可以延緩衰退"), "延緩")

    def test_non_string_input_is_not_banned(self):
        for value in [None, 123, ["失智"], {"a": "失智"}]:
            with self.subTest(value=value):
                self.assertIsNone(find_banned_word(value))

    def test_no_single_character_in_the_list(self):
        # 單一個字會誤傷正常句子，清單裡不該有
        self.assertEqual([w for w in BANNED_WORDS if len(w) == 1], [])


class OtherModulesUseTheSharedListTests(SimpleTestCase):
    FACTS = {"active_day_count": 4, "more_days": 1}
    FALLBACK = "這週你玩了 4 天，比上週多 1 天！"

    def setUp(self):
        cache.clear()

    @patch("ai_service.weekly_summary._client")
    def test_weekly_summary_rejects_newly_banned_words(self, mock_client):
        for text in ["持續遊玩可延緩衰退喔", "降低風險的好習慣", "越來越好沒有退化"]:
            with self.subTest(text=text):
                mock_client.return_value.chat.completions.create.return_value = (
                    fake_ai_reply(text)
                )

                with self.assertLogs("ai_service.weekly_summary", level="WARNING"):
                    summary = generate_weekly_summary(self.FACTS)

                self.assertEqual(summary, self.FALLBACK)

    @patch("ai_service.weekly_summary._client")
    def test_weekly_summary_no_longer_rejects_letter_z(self, mock_client):
        mock_client.return_value.chat.completions.create.return_value = fake_ai_reply(
            "這週超棒，Zzz 也要好好睡！"
        )

        summary = generate_weekly_summary(self.FACTS)

        self.assertEqual(summary, "這週超棒，Zzz 也要好好睡！")

    @patch("ai_service.greeting._client")
    def test_greeting_rejects_newly_banned_words(self, mock_client):
        mock_client.return_value.chat.completions.create.return_value = fake_ai_reply(
            "預防失智從今天開始"
        )

        with self.assertLogs("ai_service.greeting", level="WARNING"):
            greeting, from_ai = generate_greeting(date(2026, 11, 10))

        self.assertFalse(from_ai)
