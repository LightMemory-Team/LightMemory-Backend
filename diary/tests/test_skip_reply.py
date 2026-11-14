"""日記「跳過本輪」API 測試（POST /api/diary/<id>/replies/skip/）。

重點：
- 跳過會寫入一筆 is_skipped=True 的回覆，回傳格式與 replies 一致，
  下一個問題是固定句型（不呼叫 AI、不辨識、不上傳）
- 跳過的輪次算一輪（reply_count 增加），但不算「有內容的回覆」
  （is_finalizable 要 2 輪有內容）；finalize 也不採用跳過的輪次
- 同一輪已回答或已跳過 → 409；round_index 不合法 → 400；已完成的日記 → 400
- 四輪全部跳過、日記會沒有任何內容 → 最後一輪不能跳過（400 SKIP_NOT_ALLOWED）
- 只有日記本人能跳過；沒登入 401；別人的日記 404

執行：
    python manage.py test diary.tests.test_skip_reply --settings=config.settings_test
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient, APITestCase

from ai_service.wording import contains_banned_word

from ..models import Diary, DiaryReply
from ..views import MAX_REPLY_ROUNDS, SKIP_FOLLOW_UP_QUESTIONS

User = get_user_model()

AUDIO_URL = "voice-diary/audio/new.webm"


class SkipTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="Old!Pass2026")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.diary = Diary.objects.create(
            user=self.user, status="pending", first_question="第一題"
        )
        self.skip_url = f"/api/diary/{self.diary.id}/replies/skip/"
        self.reply_url = f"/api/diary/{self.diary.id}/replies/"

    def skip(self, round_index=1, url=None, **kwargs):
        data = {} if round_index is None else {"round_index": round_index}
        return self.client.post(
            url or self.skip_url, data, format=kwargs.pop("format", "json")
        )

    def reply(self, round_index):
        audio = SimpleUploadedFile("a.webm", b"data", content_type="audio/webm")
        return self.client.post(
            self.reply_url,
            {"audio": audio, "round_index": round_index},
            format="multipart",
        )

    def assert_error(self, response, http_status, code):
        self.assertEqual(response.status_code, http_status)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], code)

    def replies(self):
        return DiaryReply.objects.filter(diary=self.diary).order_by("round_index")


class SkipBasicsTests(SkipTestCase):
    def test_skipping_creates_a_skipped_reply_and_returns_the_next_question(self):
        response = self.skip(1)

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["success"])
        data = response.data["data"]
        self.assertEqual(data["round_index"], 1)
        self.assertEqual(data["reply_count"], 1)
        self.assertFalse(data["is_finalizable"])
        self.assertFalse(data["is_done"])
        self.assertIn(data["ai_reply"], SKIP_FOLLOW_UP_QUESTIONS)

        reply = self.replies().get()
        self.assertTrue(reply.is_skipped)
        self.assertEqual(reply.round_index, 1)
        self.assertEqual(reply.transcript, "")
        self.assertEqual(reply.audio_path, "")
        self.assertEqual(reply.question, "第一題")

    def test_the_response_has_the_same_fields_as_a_normal_reply_minus_audio(self):
        data = self.skip(1).data["data"]

        self.assertEqual(
            set(data),
            {"round_index", "ai_reply", "reply_count", "is_finalizable", "is_done"},
        )

    def test_the_diary_moves_to_processing_and_remembers_the_next_question(self):
        data = self.skip(1).data["data"]

        self.diary.refresh_from_db()
        self.assertEqual(self.diary.status, "processing")
        self.assertEqual(self.diary.pending_question, data["ai_reply"])

    def test_the_next_reply_uses_the_skip_question_as_its_question(self):
        asked = self.skip(1).data["data"]["ai_reply"]

        with (
            patch("diary.views.external.transcribe_audio", return_value="好天氣"),
            patch("diary.views.external.upload_to_firebase", return_value=AUDIO_URL),
            patch("diary.views.ai_gen.generate_follow_up", return_value="還有嗎？"),
        ):
            self.assertEqual(self.reply(2).status_code, 201)

        self.assertEqual(self.replies().get(round_index=2).question, asked)

    def test_form_data_is_accepted_as_well_as_json(self):
        response = self.skip(1, format="multipart")

        self.assertEqual(response.status_code, 201)

    def test_skipping_never_calls_ai_transcription_or_upload(self):
        with (
            patch("diary.views.ai_gen.generate_follow_up") as ai,
            patch("diary.views.external.transcribe_audio") as transcribe,
            patch("diary.views.external.upload_to_firebase") as upload,
        ):
            self.skip(1)

        ai.assert_not_called()
        transcribe.assert_not_called()
        upload.assert_not_called()

    def test_all_fixed_questions_pass_the_wording_check(self):
        for question in SKIP_FOLLOW_UP_QUESTIONS:
            with self.subTest(question=question):
                self.assertFalse(contains_banned_word(question))

    def test_consecutive_skips_do_not_repeat_the_same_question(self):
        first = self.skip(1).data["data"]["ai_reply"]
        second = self.skip(2).data["data"]["ai_reply"]

        self.assertNotEqual(first, second)


class SkipCountingTests(SkipTestCase):
    @patch("diary.views.ai_gen.generate_follow_up", return_value="還有嗎？")
    @patch("diary.views.external.upload_to_firebase", return_value=AUDIO_URL)
    @patch("diary.views.external.transcribe_audio", return_value="今天天氣很好")
    def test_skipped_rounds_count_as_rounds_but_not_as_content(self, *_):
        self.reply(1)  # 有內容
        data = self.skip(2).data["data"]

        self.assertEqual(data["reply_count"], 2)
        self.assertFalse(data["is_finalizable"])  # 只有 1 輪有內容

        self.reply(3)  # 第 2 輪有內容 → 可完成
        data = self.skip(4).data["data"]

        self.assertEqual(data["reply_count"], 4)
        self.assertTrue(data["is_finalizable"])
        self.assertTrue(data["is_done"])
        self.assertIsNone(data["ai_reply"])

    def test_the_last_round_clears_the_pending_question(self):
        with (
            patch("diary.views.external.transcribe_audio", return_value="一些內容"),
            patch("diary.views.external.upload_to_firebase", return_value=AUDIO_URL),
            patch("diary.views.ai_gen.generate_follow_up", return_value="還有嗎？"),
        ):
            self.reply(1)
        for r in (2, 3, 4):
            self.skip(r)

        self.diary.refresh_from_db()
        self.assertEqual(self.diary.pending_question, "")

    def test_the_diary_detail_shows_the_skipped_round(self):
        self.skip(1)

        response = self.client.get(f"/api/diary/{self.diary.id}/")

        replies = response.data["data"]["replies"]
        self.assertEqual(len(replies), 1)
        self.assertTrue(replies[0]["is_skipped"])
        self.assertEqual(response.data["data"]["reply_count"], 1)


class SkipValidationTests(SkipTestCase):
    def test_invalid_round_index_is_400(self):
        for raw in (None, "", "abc", "1.5", 0, -1, MAX_REPLY_ROUNDS + 1, True, [1]):
            with self.subTest(round_index=raw):
                response = self.skip(raw)
                self.assert_error(response, 400, "INVALID_ROUND_INDEX")

        self.assertEqual(self.replies().count(), 0)

    def test_a_round_that_was_already_skipped_is_409(self):
        self.skip(1)

        self.assert_error(self.skip(1), 409, "ROUND_ALREADY_ANSWERED")
        self.assertEqual(self.replies().count(), 1)

    def test_a_round_that_was_already_answered_is_409(self):
        DiaryReply.objects.create(diary=self.diary, round_index=1, transcript="說過了")

        self.assert_error(self.skip(1), 409, "ROUND_ALREADY_ANSWERED")
        self.assertFalse(self.replies().get().is_skipped)

    def test_a_finished_diary_cannot_be_skipped(self):
        self.diary.status = "done"
        self.diary.save()

        self.assert_error(self.skip(1), 400, "DIARY_ALREADY_FINALIZED")
        self.assertEqual(self.replies().count(), 0)

    def test_a_diary_finished_by_a_concurrent_request_cannot_be_skipped(self):
        # 模擬：驗證通過後、取得鎖之前，日記被另一個請求完成了
        real = Diary.objects.select_for_update

        def finish_then_lock():
            Diary.objects.filter(pk=self.diary.pk).update(status="done")
            return real()

        with patch.object(
            Diary.objects, "select_for_update", side_effect=finish_then_lock
        ):
            response = self.skip(1)

        self.assert_error(response, 400, "DIARY_ALREADY_FINALIZED")
        self.assertEqual(self.replies().count(), 0)

    def test_skipping_every_round_is_not_allowed_on_the_last_one(self):
        for r in range(1, MAX_REPLY_ROUNDS):
            self.assertEqual(self.skip(r).status_code, 201)

        response = self.skip(MAX_REPLY_ROUNDS)

        self.assert_error(response, 400, "SKIP_NOT_ALLOWED")
        self.assertEqual(self.replies().count(), MAX_REPLY_ROUNDS - 1)

    def test_a_rejected_last_skip_can_still_be_answered_with_audio(self):
        for r in range(1, MAX_REPLY_ROUNDS):
            self.skip(r)
        self.skip(MAX_REPLY_ROUNDS)  # 被擋

        with (
            patch("diary.views.external.transcribe_audio", return_value="終於有話說"),
            patch("diary.views.external.upload_to_firebase", return_value=AUDIO_URL),
        ):
            response = self.reply(MAX_REPLY_ROUNDS)

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["data"]["is_done"])


class SkipPermissionTests(SkipTestCase):
    def test_not_logged_in_is_401(self):
        response = APIClient().post(self.skip_url, {"round_index": 1}, format="json")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.replies().count(), 0)

    def test_someone_elses_diary_is_404(self):
        bob = User.objects.create_user(username="bob", password="Old!Pass2026")
        client = APIClient()
        client.force_authenticate(bob)

        response = client.post(self.skip_url, {"round_index": 1}, format="json")

        self.assert_error(response, 404, "DIARY_NOT_FOUND")
        self.assertEqual(self.replies().count(), 0)

    def test_a_missing_diary_is_404(self):
        response = self.skip(1, url="/api/diary/999999/replies/skip/")

        self.assert_error(response, 404, "DIARY_NOT_FOUND")


class SkipThenFinalizeTests(SkipTestCase):
    @patch("diary.views.ai_gen.generate_follow_up", return_value="還有嗎？")
    @patch("diary.views.external.upload_to_firebase", return_value=AUDIO_URL)
    @patch("diary.views.external.transcribe_audio", return_value="今天去公園散步")
    def test_finalize_only_uses_the_rounds_with_content(self, *_):
        self.skip(1)
        self.reply(2)
        self.skip(3)

        with patch("diary.views.ai_gen.generate_finalize_content") as gen:
            gen.return_value = {
                "title": "公園散步",
                "ai_response": "真好",
                "post_text": "今天去公園",
                "hashtags": [],
                "category": "daily",
                "suggested_replies": [],
                "invite_text": "來看看",
            }
            response = self.client.post(f"/api/diary/{self.diary.id}/finalize/")

        self.assertEqual(response.status_code, 201)
        gen.assert_called_once_with("今天去公園散步")  # 沒有多出空字串、逗號

    def test_finalizing_after_skipping_everything_so_far_is_rejected(self):
        self.skip(1)
        self.skip(2)

        response = self.client.post(f"/api/diary/{self.diary.id}/finalize/")

        self.assert_error(response, 400, "NO_VALID_REPLY")
