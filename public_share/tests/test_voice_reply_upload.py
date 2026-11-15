"""訪客上傳語音加油 API（POST /api/share/<token>/voice-replies/）的測試。

Firebase 上傳一律用 mock，不會真的上傳檔案。
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from social.models import Notification, Post, VoiceReply

User = get_user_model()

FAKE_PATH = "voice-diary/voice-replies/abc.webm"


def audio_file(name="reply.webm", content_type="audio/webm", size=1000):
    return SimpleUploadedFile(name, b"x" * size, content_type=content_type)


@patch("public_share.views.upload_to_firebase", return_value=FAKE_PATH)
class VoiceReplyUploadTests(TestCase):
    def setUp(self):
        cache.clear()  # 頻率限制計數存在 cache，避免測試之間互相影響
        self.client = APIClient()
        self.user = User.objects.create_user(username="elder", password="pw123456")
        self.post = Post.objects.create(user=self.user, content="陽台的花開了")
        self.url = f"/api/share/{self.post.share_token}/voice-replies/"

    def send(self, url=None, **overrides):
        data = {"nickname": "小玲", "audio_file": audio_file(), "duration_sec": "8"}
        data.update(overrides)
        data = {k: v for k, v in data.items() if v is not None}
        return self.client.post(url or self.url, data, format="multipart")

    def assert_error(self, response, http_status, code):
        self.assertEqual(response.status_code, http_status)
        self.assertIs(response.data["success"], False)
        self.assertIsNone(response.data["data"])
        self.assertEqual(response.data["error"]["code"], code)
        self.assertTrue(response.data["error"]["message"])

    def test_success_creates_voice_reply_and_notifies_the_author(self, upload):
        response = self.send()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIs(response.data["success"], True)
        data = response.data["data"]
        self.assertEqual(data["nickname"], "小玲")
        self.assertEqual(data["duration_sec"], 8)
        self.assertIn("+08:00", data["created_at"])

        reply = VoiceReply.objects.get(pk=data["voice_reply_id"])
        self.assertEqual(reply.post, self.post)
        self.assertEqual(reply.audio_path, FAKE_PATH)
        self.assertEqual(reply.transcribed_text, "")
        self.assertEqual(upload.call_args.args[1], "voice-replies")

        notification = Notification.objects.get(user=self.user)
        self.assertEqual(notification.notification_type, "voice_reply")
        self.assertEqual(notification.message, "小玲 送給你一段語音加油")
        self.assertEqual(notification.target_url, f"/posts/{self.post.id}/")

    def test_no_login_needed(self, upload):
        self.client.credentials()  # 沒有任何 token

        self.assertEqual(self.send().status_code, status.HTTP_201_CREATED)

    def test_ios_safari_mp4_is_accepted(self, upload):
        response = self.send(audio_file=audio_file("reply.mp4", "audio/mp4"))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_nickname_must_be_1_to_12_characters(self, upload):
        for nickname in ("", "   ", "一二三四五六七八九十一二三"):
            with self.subTest(nickname=nickname):
                self.assert_error(
                    self.send(nickname=nickname, audio_file=audio_file()),
                    status.HTTP_400_BAD_REQUEST,
                    "INVALID_NICKNAME",
                )
        self.assertEqual(VoiceReply.objects.count(), 0)

    def test_missing_audio_is_rejected(self, upload):
        self.assert_error(
            self.send(audio_file=None), status.HTTP_400_BAD_REQUEST, "INVALID_AUDIO"
        )

    def test_unsupported_format_is_rejected(self, upload):
        response = self.send(audio_file=audio_file("a.txt", "text/plain"))

        self.assert_error(response, status.HTTP_400_BAD_REQUEST, "INVALID_AUDIO")

    def test_file_over_2mb_is_rejected(self, upload):
        response = self.send(audio_file=audio_file(size=2 * 1024 * 1024 + 1))

        self.assert_error(response, status.HTTP_400_BAD_REQUEST, "INVALID_AUDIO")
        upload.assert_not_called()

    def test_duration_over_11_seconds_is_too_long(self, upload):
        response = self.send(duration_sec="12")

        self.assert_error(response, status.HTTP_400_BAD_REQUEST, "AUDIO_TOO_LONG")

    def test_11_seconds_is_still_ok(self, upload):
        self.assertEqual(
            self.send(duration_sec="11").status_code, status.HTTP_201_CREATED
        )

    def test_invalid_duration_is_rejected(self, upload):
        for duration in ("0", "-3", "abc", None):
            with self.subTest(duration=duration):
                self.assert_error(
                    self.send(duration_sec=duration, audio_file=audio_file()),
                    status.HTTP_400_BAD_REQUEST,
                    "INVALID_AUDIO",
                )

    def test_closed_or_unknown_share_returns_404(self, upload):
        self.assert_error(
            self.send(url="/api/share/no-such-token/voice-replies/"),
            status.HTTP_404_NOT_FOUND,
            "SHARE_NOT_FOUND",
        )
        Post.objects.filter(pk=self.post.pk).update(is_share_enabled=False)
        self.assert_error(self.send(), status.HTTP_404_NOT_FOUND, "SHARE_NOT_FOUND")
        upload.assert_not_called()

    def test_sixth_upload_in_a_minute_is_rate_limited(self, upload):
        for _ in range(5):
            self.assertEqual(self.send().status_code, status.HTTP_201_CREATED)

        self.assert_error(
            self.send(), status.HTTP_429_TOO_MANY_REQUESTS, "TOO_MANY_REQUESTS"
        )
        self.assertEqual(VoiceReply.objects.count(), 5)

    def test_failed_attempts_do_not_use_up_the_limit(self, upload):
        for _ in range(5):
            self.send(nickname="")

        self.assertEqual(self.send().status_code, status.HTTP_201_CREATED)

    def test_upload_failure_returns_500_and_saves_nothing(self, upload):
        upload.return_value = None

        self.assert_error(
            self.send(), status.HTTP_500_INTERNAL_SERVER_ERROR, "UPLOAD_FAILED"
        )
        self.assertEqual(VoiceReply.objects.count(), 0)
        self.assertFalse(Notification.objects.exists())
