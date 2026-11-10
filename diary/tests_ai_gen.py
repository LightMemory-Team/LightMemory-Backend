"""日記 AI 產生（diary/ai_gen.py）的過濾與驗證測試。

重點：AI 回來的內容有醫療宣稱、型別不對、太長時，要改成安全的值，
而且不能讓日記流程因為 AI 的輸出格式而出錯。

執行：
    python manage.py test diary.tests_ai_gen --settings=config.settings_test
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from diary import ai_gen
from diary.models import Diary

CLIENT = "diary.ai_gen._client"


def fake_reply(text):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


def client_returning(text):
    client = patch(CLIENT).start()
    client.return_value.chat.completions.create.return_value = fake_reply(text)
    return client


class QuestionTests(SimpleTestCase):
    def tearDown(self):
        patch.stopall()

    def test_clean_question_is_returned(self):
        client_returning("這張照片裡的花好漂亮，是在哪裡拍的呢？")

        self.assertEqual(
            ai_gen.generate_first_question(), "這張照片裡的花好漂亮，是在哪裡拍的呢？"
        )

    def test_banned_first_question_uses_fallback(self):
        client_returning("這張照片能預防失智嗎？")

        with self.assertLogs("diary.ai_gen", level="WARNING"):
            result = ai_gen.generate_first_question()

        self.assertEqual(result, ai_gen.FIRST_QUESTION_FALLBACK)

    def test_banned_follow_up_uses_fallback(self):
        client_returning("你的記憶力下降了嗎？")

        with self.assertLogs("diary.ai_gen", level="WARNING"):
            result = ai_gen.generate_follow_up("今天去公園")

        self.assertEqual(result, ai_gen.FOLLOW_UP_FALLBACK)

    def test_empty_reply_uses_fallback(self):
        client_returning("   ")

        self.assertEqual(
            ai_gen.generate_follow_up("今天去公園"), ai_gen.FOLLOW_UP_FALLBACK
        )

    def test_ai_error_uses_fallback_and_logs(self):
        patch(CLIENT, side_effect=RuntimeError("沒有網路")).start()

        with self.assertLogs("diary.ai_gen", level="WARNING"):
            result = ai_gen.generate_follow_up("今天去公園")

        self.assertEqual(result, ai_gen.FOLLOW_UP_FALLBACK)

    def test_prompts_include_the_safety_rules(self):
        client = client_returning("好的")

        ai_gen.generate_first_question()
        ai_gen.generate_follow_up("今天去公園")
        ai_gen.generate_finalize_content("今天去公園")

        for call in client.return_value.chat.completions.create.call_args_list:
            system_prompt = call.kwargs["messages"][0]["content"]
            self.assertIn(ai_gen.SAFETY_RULES, system_prompt)


class FinalizeContentTests(SimpleTestCase):
    TEXT = "我今天跟家人去公園散步，心情很開心"
    GOOD = {
        "title": "公園散步🌳",
        "ai_response": "聽起來是很美好的一天，謝謝你的分享！",
        "post_text": "今天和家人去公園散步，好開心。",
        "hashtags": ["#散步", "#家人", "#公園"],
        "category": "entertainment",
        "suggested_replies": ["太棒了！", "真好～", "下次也帶我去"],
        "invite_text": "今天去公園散步，來看看吧！",
    }

    def tearDown(self):
        patch.stopall()

    def generate(self, payload):
        text = (
            payload
            if isinstance(payload, str)
            else json.dumps(payload, ensure_ascii=False)
        )
        client_returning(text)
        return ai_gen.generate_finalize_content(self.TEXT)

    def test_good_content_is_kept(self):
        self.assertEqual(self.generate(self.GOOD), self.GOOD)

    def test_markdown_fenced_json_is_accepted(self):
        result = self.generate(
            "```json\n" + json.dumps(self.GOOD, ensure_ascii=False) + "\n```"
        )

        self.assertEqual(result["title"], "公園散步🌳")

    def test_banned_field_falls_back_to_default_but_others_are_kept(self):
        payload = {**self.GOOD, "ai_response": "常散步可以延緩失智喔"}

        with self.assertLogs("diary.ai_gen", level="WARNING"):
            result = self.generate(payload)

        self.assertEqual(result["ai_response"], "謝謝你今天的分享！")
        self.assertEqual(result["title"], "公園散步🌳")
        self.assertEqual(result["post_text"], self.GOOD["post_text"])

    def test_too_long_values_are_cut_to_fit_the_database(self):
        payload = {**self.GOOD, "title": "題" * 80, "invite_text": "邀" * 300}

        result = self.generate(payload)

        title_limit = Diary._meta.get_field("title").max_length
        invite_limit = Diary._meta.get_field("invite_text").max_length
        self.assertEqual(len(result["title"]), title_limit)
        self.assertEqual(len(result["invite_text"]), invite_limit)

    def test_unknown_category_uses_default(self):
        result = self.generate({**self.GOOD, "category": "亂寫的"})

        self.assertEqual(result["category"], "entertainment")

    def test_all_allowed_categories_pass_the_database_limit(self):
        limit = Diary._meta.get_field("category").max_length
        for category in ai_gen.ALLOWED_CATEGORIES:
            with self.subTest(category=category):
                self.assertLessEqual(len(category), limit)
                self.assertEqual(
                    self.generate({**self.GOOD, "category": category})["category"],
                    category,
                )

    def test_wrong_types_use_defaults(self):
        payload = {
            "title": 123,
            "ai_response": ["不是字串"],
            "post_text": None,
            "hashtags": "#不是清單",
            "suggested_replies": {"a": 1},
            "invite_text": 4.5,
        }

        result = self.generate(payload)

        self.assertEqual(result["title"], self.TEXT[:10])
        self.assertEqual(result["ai_response"], "謝謝你今天的分享！")
        self.assertEqual(result["hashtags"], ["#聲影日記", "#每日記錄", "#長者生活"])
        self.assertEqual(
            result["suggested_replies"],
            ["聽起來很棒！", "下次也要告訴我喔～", "你今天過得真充實！"],
        )

    def test_list_items_with_banned_words_or_non_strings_are_dropped(self):
        payload = {
            **self.GOOD,
            "hashtags": ["#散步", "#預防失智", 5, "", "#家人"],
        }

        result = self.generate(payload)

        self.assertEqual(result["hashtags"], ["#散步", "#家人"])

    def test_list_with_nothing_left_uses_default(self):
        result = self.generate({**self.GOOD, "hashtags": ["#失智", "#治療"]})

        self.assertEqual(result["hashtags"], ["#聲影日記", "#每日記錄", "#長者生活"])

    def test_list_is_limited_in_length(self):
        result = self.generate(
            {**self.GOOD, "hashtags": [f"#tag{i}" for i in range(20)]}
        )

        self.assertEqual(len(result["hashtags"]), ai_gen.MAX_LIST_ITEMS)

    def test_json_that_is_not_an_object_uses_defaults(self):
        for payload in ["[1, 2, 3]", '"just a string"', "42", "null"]:
            with self.subTest(payload=payload):
                result = self.generate(payload)

                self.assertEqual(result["ai_response"], "謝謝你今天的分享！")
                self.assertEqual(result["category"], "entertainment")

    def test_invalid_json_uses_defaults_and_logs(self):
        client_returning("這不是 JSON")

        with self.assertLogs("diary.ai_gen", level="WARNING"):
            result = ai_gen.generate_finalize_content(self.TEXT)

        self.assertEqual(result["title"], self.TEXT[:10])
        self.assertEqual(result["ai_response"], "謝謝你今天的分享！")

    def test_ai_error_uses_defaults(self):
        patch(CLIENT, side_effect=RuntimeError("沒有網路")).start()

        with self.assertLogs("diary.ai_gen", level="WARNING"):
            result = ai_gen.generate_finalize_content(self.TEXT)

        self.assertEqual(result["post_text"], self.TEXT[:50])

    def test_clean_does_not_modify_the_input(self):
        defaults = {**self.GOOD, "title": "預設"}
        result_in = {"title": "新標題", "hashtags": ["#a"]}
        before = json.dumps(result_in), json.dumps(defaults)

        ai_gen.clean_finalize_content(result_in, defaults)

        self.assertEqual((json.dumps(result_in), json.dumps(defaults)), before)
