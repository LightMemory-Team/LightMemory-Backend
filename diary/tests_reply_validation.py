"""日記回覆（replies）與完成日記（finalize）的輸入驗證、transaction 測試。

重點：
- round_index 不是整數、超出範圍 → 400，不再是 500
- 同一輪重複送出 → 409，不再是 500，而且不會白做語音辨識與上傳
- 寫入資料庫失敗時整段還原，不留下半完成的資料

執行：
    python manage.py test diary.tests_reply_validation --settings=config.settings_test
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Diary, DiaryAnalysis, DiaryReply
from .views import MAX_REPLY_ROUNDS, parse_round_index

User = get_user_model()

AUDIO_URL = "voice-diary/audio/new.wav"


class ParseRoundIndexTests(SimpleTestCase):
    def test_valid_values(self):
        for raw, expected in [
            (1, 1),
            ("1", 1),
            (" 2 ", 2),
            ("+3", 3),
            (MAX_REPLY_ROUNDS, 4),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(parse_round_index(raw), expected)

    def test_invalid_values(self):
        for raw in [
            None, "", "abc", "1.5", 1.0, True, False, 0, "0", -1, "-1",
            MAX_REPLY_ROUNDS + 1, "99999999999999999999", [1], {"a": 1},
        ]:  # fmt: skip
            with self.subTest(raw=raw):
                self.assertIsNone(parse_round_index(raw))


class ReplyTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reply_user", password="Str0ng!Pass2026"
        )
        self.client.force_authenticate(user=self.user)
        self.diary = Diary.objects.create(
            user=self.user, status="pending", first_question="第一題"
        )
        self.url = f"/api/diary/{self.diary.id}/replies/"

    def post_reply(self, round_index=1, with_audio=True):
        data = {}
        if with_audio:
            data["audio"] = SimpleUploadedFile(
                "a.wav", b"data", content_type="audio/wav"
            )
        if round_index is not None:
            data["round_index"] = round_index
        return self.client.post(self.url, data, format="multipart")


@patch("diary.views.ai_gen.generate_follow_up", return_value="還有嗎？")
@patch("diary.views.external.delete_from_firebase")
@patch("diary.views.external.upload_to_firebase", return_value=AUDIO_URL)
@patch("diary.views.external.transcribe_audio", return_value="今天天氣很好")
class DiaryReplyValidationTests(ReplyTestCase):
    def test_non_numeric_round_index_returns_400_without_doing_any_work(
        self, transcribe, upload, delete, followup
    ):
        for raw in ["abc", "1.5", "0", "-1", "5", "99999999999999999999"]:
            with self.subTest(round_index=raw):
                response = self.post_reply(raw)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data["error"]["code"], "INVALID_ROUND_INDEX")

        transcribe.assert_not_called()
        upload.assert_not_called()
        self.assertEqual(DiaryReply.objects.count(), 0)

    def test_missing_round_index_or_audio_is_still_invalid_audio(
        self, transcribe, upload, delete, followup
    ):
        for kwargs in [
            {"round_index": None},
            {"round_index": ""},
            {"with_audio": False},
        ]:
            with self.subTest(kwargs=kwargs):
                response = self.post_reply(**{"round_index": 1, **kwargs})

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data["error"]["code"], "INVALID_AUDIO")

    def test_valid_round_index_still_works(self, transcribe, upload, delete, followup):
        response = self.post_reply("1")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["round_index"], 1)
        self.assertEqual(DiaryReply.objects.filter(diary=self.diary).count(), 1)

    def test_duplicate_round_returns_409_without_doing_any_work(
        self, transcribe, upload, delete, followup
    ):
        DiaryReply.objects.create(diary=self.diary, round_index=1, transcript="第一次")

        response = self.post_reply(1)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"]["code"], "ROUND_ALREADY_ANSWERED")
        transcribe.assert_not_called()
        upload.assert_not_called()
        self.assertEqual(DiaryReply.objects.filter(diary=self.diary).count(), 1)

    def test_round_taken_by_a_concurrent_request_returns_409_and_cleans_up(
        self, transcribe, upload, delete, followup
    ):
        # 模擬：語音辨識進行中，另一個請求搶先把第 1 輪寫進去了
        def other_request_wins(_audio):
            DiaryReply.objects.create(
                diary=self.diary, round_index=1, transcript="搶先"
            )
            return "今天天氣很好"

        transcribe.side_effect = other_request_wins

        response = self.post_reply(1)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"]["code"], "ROUND_ALREADY_ANSWERED")
        delete.assert_called_once_with([AUDIO_URL])
        self.assertEqual(DiaryReply.objects.filter(diary=self.diary).count(), 1)
        self.diary.refresh_from_db()
        self.assertEqual(self.diary.status, "pending")

    def test_diary_finalized_during_upload_returns_400_and_cleans_up(
        self, transcribe, upload, delete, followup
    ):
        def finalized_meanwhile(_audio):
            Diary.objects.filter(pk=self.diary.pk).update(status="done")
            return "今天天氣很好"

        transcribe.side_effect = finalized_meanwhile

        response = self.post_reply(1)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "DIARY_ALREADY_FINALIZED")
        delete.assert_called_once_with([AUDIO_URL])
        self.assertEqual(DiaryReply.objects.filter(diary=self.diary).count(), 0)

    def test_failure_while_saving_rolls_everything_back(
        self, transcribe, upload, delete, followup
    ):
        followup.side_effect = RuntimeError("AI 掛了")

        response = self.post_reply(1)

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(DiaryReply.objects.filter(diary=self.diary).count(), 0)
        self.diary.refresh_from_db()
        self.assertEqual(self.diary.status, "pending")
        self.assertEqual(self.diary.pending_question, "")

    def test_fourth_round_is_done(self, transcribe, upload, delete, followup):
        for i in range(1, 4):
            DiaryReply.objects.create(diary=self.diary, round_index=i, transcript="x")

        response = self.post_reply(4)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["data"]["is_done"])
        followup.assert_not_called()


class DiaryFinalizeTransactionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="final_user", password="Str0ng!Pass2026"
        )
        self.client.force_authenticate(user=self.user)
        self.diary = Diary.objects.create(user=self.user, status="processing")
        DiaryReply.objects.create(
            diary=self.diary,
            round_index=1,
            transcript="我今天跟家人去公園散步，心情很開心，大家一起聊天吃午餐。",
        )
        self.url = f"/api/diary/{self.diary.id}/finalize/"

    @patch("diary.views.ai_gen.generate_finalize_content")
    def test_failure_rolls_back_analysis_and_status(self, finalize_content):
        finalize_content.side_effect = RuntimeError("AI 掛了")

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(DiaryAnalysis.objects.filter(diary=self.diary).count(), 0)
        self.diary.refresh_from_db()
        self.assertEqual(self.diary.status, "processing")
        self.assertEqual(self.diary.title, "")

    @patch("diary.views.ai_gen.generate_finalize_content")
    def test_second_finalize_does_not_call_ai_again(self, finalize_content):
        finalize_content.return_value = {
            "title": "公園散步",
            "ai_response": "r",
            "post_text": "p",
            "hashtags": ["散步"],
            "category": "日常",
            "suggested_replies": [],
            "invite_text": "i",
        }

        first = self.client.post(self.url)
        second = self.client.post(self.url)

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(finalize_content.call_count, 1)
        self.assertEqual(DiaryAnalysis.objects.filter(diary=self.diary).count(), 1)

    def test_no_valid_reply_returns_400_and_changes_nothing(self):
        DiaryReply.objects.all().delete()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "NO_VALID_REPLY")
        self.diary.refresh_from_db()
        self.assertEqual(self.diary.status, "processing")
