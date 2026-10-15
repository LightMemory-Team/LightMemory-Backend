"""weekly_summary.py 的測試。

用 unittest.mock.patch 假裝 OpenAI 的回傳，測試不會真的呼叫 AI、不花錢。
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from .weekly_summary import (
    build_fallback_summary,
    build_positive_facts,
    generate_weekly_summary,
)

CLIENT_PATH = "ai_service.weekly_summary._client"


def ability(label, trend, this_week=None, last_week=None):
    return {
        "label": label,
        "trend": trend,
        "this_week": this_week,
        "last_week": last_week,
    }


def abilities(*dimensions):
    return {"overall": {}, "dimensions": list(dimensions)}


def fake_ai_reply(text):
    """組出跟 OpenAI chat.completions.create 回傳一樣形狀的物件。"""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


class BuildPositiveFactsTests(SimpleTestCase):
    def test_more_days_included(self):
        facts = build_positive_facts(4, 3, abilities())
        self.assertEqual(facts, {"active_day_count": 4, "more_days": 1})

    def test_fewer_days_not_included(self):
        # 比上週少不交給 AI，AI 就沒有材料講負面的話
        facts = build_positive_facts(2, 5, abilities())
        self.assertEqual(facts, {"active_day_count": 2})

    def test_most_improved_is_biggest_gain_among_up(self):
        facts = build_positive_facts(
            4,
            4,
            abilities(
                ability("注意力", "up", 73, 70),
                ability("工作記憶", "up", 78, 66),
                ability("數學", "practice", 60, 66),
                ability("語言", None),
            ),
        )
        self.assertEqual(facts["most_improved"], "工作記憶")

    def test_no_improvement_not_included(self):
        facts = build_positive_facts(
            4, 4, abilities(ability("注意力", "steady", 70, 69))
        )
        self.assertNotIn("most_improved", facts)


class BuildFallbackSummaryTests(SimpleTestCase):
    def test_more_days_and_improved(self):
        facts = {"active_day_count": 4, "more_days": 1, "most_improved": "工作記憶"}
        self.assertEqual(
            build_fallback_summary(facts),
            "這週你玩了 4 天，比上週多 1 天！進步最多的是工作記憶",
        )

    def test_more_days_only(self):
        facts = {"active_day_count": 4, "more_days": 1}
        self.assertEqual(
            build_fallback_summary(facts), "這週你玩了 4 天，比上週多 1 天！"
        )

    def test_improved_only(self):
        facts = {"active_day_count": 2, "most_improved": "注意力"}
        self.assertEqual(
            build_fallback_summary(facts), "這週你玩了 2 天！進步最多的是注意力"
        )

    def test_nothing_special_stays_positive(self):
        facts = {"active_day_count": 2}
        self.assertEqual(build_fallback_summary(facts), "這週你玩了 2 天，繼續保持！")

    def test_zero_days(self):
        self.assertEqual(
            build_fallback_summary({"active_day_count": 0}),
            "好久不見，下週一起來動動腦吧！",
        )


class GenerateWeeklySummaryTests(SimpleTestCase):
    FACTS = {"active_day_count": 4, "more_days": 1}

    @patch(CLIENT_PATH)
    def test_uses_ai_reply(self, mock_client):
        create = mock_client.return_value.chat.completions.create
        create.return_value = fake_ai_reply("  這週來了 4 天，比上週更勤快，真棒！ ")

        summary = generate_weekly_summary(self.FACTS)

        self.assertEqual(summary, "這週來了 4 天，比上週更勤快，真棒！")
        # 交給 AI 的只有正向事實
        user_message = create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("4 天", user_message)
        self.assertIn("多玩了 1 天", user_message)

    @patch(CLIENT_PATH)
    def test_zero_days_does_not_call_ai(self, mock_client):
        summary = generate_weekly_summary({"active_day_count": 0})

        self.assertEqual(summary, "好久不見，下週一起來動動腦吧！")
        mock_client.assert_not_called()

    @patch(CLIENT_PATH, side_effect=Exception("沒有網路"))
    def test_ai_error_uses_fallback(self, mock_client):
        with self.assertLogs("ai_service.weekly_summary", level="WARNING"):
            summary = generate_weekly_summary(self.FACTS)

        self.assertEqual(summary, "這週你玩了 4 天，比上週多 1 天！")

    @patch(CLIENT_PATH)
    def test_banned_word_uses_fallback(self, mock_client):
        mock_client.return_value.chat.completions.create.return_value = fake_ai_reply(
            "多動腦可以預防失智喔！"
        )

        with self.assertLogs("ai_service.weekly_summary", level="WARNING"):
            summary = generate_weekly_summary(self.FACTS)

        self.assertEqual(summary, "這週你玩了 4 天，比上週多 1 天！")

    @patch(CLIENT_PATH)
    def test_too_long_uses_fallback(self, mock_client):
        mock_client.return_value.chat.completions.create.return_value = fake_ai_reply(
            "很棒" * 30
        )

        with self.assertLogs("ai_service.weekly_summary", level="WARNING"):
            summary = generate_weekly_summary(self.FACTS)

        self.assertEqual(summary, "這週你玩了 4 天，比上週多 1 天！")

    @patch(CLIENT_PATH)
    def test_empty_reply_uses_fallback(self, mock_client):
        mock_client.return_value.chat.completions.create.return_value = fake_ai_reply(
            None
        )

        with self.assertLogs("ai_service.weekly_summary", level="WARNING"):
            summary = generate_weekly_summary(self.FACTS)

        self.assertEqual(summary, "這週你玩了 4 天，比上週多 1 天！")
