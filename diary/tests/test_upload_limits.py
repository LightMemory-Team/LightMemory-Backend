"""日記照片與錄音的大小、類型限制測試。

重點：
- 太大、空檔、類型不對的檔案會在「上傳 Firebase、Whisper 辨識之前」就被擋下（400），
  不會建立日記、也不會呼叫任何外部服務
- 前端實際送出的格式（照片沒帶類型、錄音是 audio/webm）要能通過
- 剛好等於上限的檔案可以通過，多 1 byte 就不行

執行：
    python manage.py test diary.tests.test_upload_limits --settings=config.settings_test
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework.test import APIClient, APITestCase

from diary import upload_checks
from diary.models import Diary, DiaryReply

User = get_user_model()

PHOTO_URL = "/api/diary/"
FIREBASE_PATH = "voice-diary/x/abc.bin"


def photo(name="p.jpg", content=b"data", content_type="image/jpeg"):
    return SimpleUploadedFile(name, content, content_type=content_type)


def audio(name="a.webm", content=b"data", content_type="audio/webm"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class FakeFile:
    """只用來測 upload_checks 的假檔案（不真的配置大記憶體）。"""

    def __init__(self, name, size, content_type=""):
        self.name = name
        self.size = size
        self.content_type = content_type


@patch("diary.views.ai_gen.generate_first_question", return_value="第一題")
@patch("diary.views.external.upload_to_firebase", return_value=FIREBASE_PATH)
class PhotoUploadTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="Old!Pass2026")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def upload(self, file):
        return self.client.post(PHOTO_URL, {"photo": file}, format="multipart")

    def assert_rejected(self, response, code, upload):
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], code)
        upload.assert_not_called()
        self.assertEqual(Diary.objects.count(), 0)

    def test_a_normal_photo_is_accepted(self, upload, _ai):
        response = self.upload(photo())

        self.assertEqual(response.status_code, 201)
        upload.assert_called_once()

    def test_the_frontends_real_upload_has_no_content_type(self, upload, _ai):
        # 前端用 MultipartFile.fromBytes 送照片，沒有指定類型（會變 octet-stream）
        response = self.upload(
            photo("IMG_0001.JPG", content_type="application/octet-stream")
        )

        self.assertEqual(response.status_code, 201)

    def test_common_photo_formats_are_accepted(self, upload, _ai):
        for name in ("a.jpg", "a.jpeg", "a.PNG", "a.webp", "a.heic", "a.heif"):
            with self.subTest(name=name):
                response = self.upload(
                    photo(name, content_type="application/octet-stream")
                )
                self.assertEqual(response.status_code, 201)

    def test_a_photo_exactly_at_the_limit_is_accepted(self, upload, _ai):
        response = self.upload(photo(content=b"x" * upload_checks.MAX_PHOTO_BYTES))

        self.assertEqual(response.status_code, 201)

    def test_a_photo_over_the_limit_is_rejected(self, upload, _ai):
        response = self.upload(
            photo(content=b"x" * (upload_checks.MAX_PHOTO_BYTES + 1))
        )

        self.assert_rejected(response, "IMAGE_TOO_LARGE", upload)

    def test_an_empty_file_is_rejected(self, upload, _ai):
        response = self.upload(photo(content=b""))

        # Django 會把空檔案當作沒有收到檔案
        self.assert_rejected(response, "INVALID_IMAGE", upload)

    def test_a_non_image_is_rejected(self, upload, _ai):
        for name, content_type in (
            ("evil.html", "text/html"),
            ("run.exe", "application/octet-stream"),
            ("notes.txt", "text/plain"),
            ("noextension", "application/octet-stream"),
            ("song.mp3", "audio/mpeg"),
        ):
            with self.subTest(name=name):
                response = self.upload(photo(name, content_type=content_type))
                self.assert_rejected(response, "INVALID_IMAGE", upload)

    def test_a_missing_photo_is_still_rejected(self, upload, _ai):
        response = self.client.post(PHOTO_URL, {}, format="multipart")

        self.assert_rejected(response, "INVALID_IMAGE", upload)


@patch("diary.views.ai_gen.generate_follow_up", return_value="還有嗎？")
@patch("diary.views.external.delete_from_firebase")
@patch("diary.views.external.upload_to_firebase", return_value=FIREBASE_PATH)
@patch("diary.views.external.transcribe_audio", return_value="今天天氣很好")
class AudioUploadTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="Old!Pass2026")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.diary = Diary.objects.create(
            user=self.user, status="pending", first_question="第一題"
        )
        self.url = f"/api/diary/{self.diary.id}/replies/"

    def reply(self, file):
        return self.client.post(
            self.url, {"audio": file, "round_index": 1}, format="multipart"
        )

    def assert_rejected(self, response, code, transcribe, upload):
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], code)
        # 還沒辨識、還沒上傳，也沒有寫入回覆
        transcribe.assert_not_called()
        upload.assert_not_called()
        self.assertEqual(DiaryReply.objects.count(), 0)

    def test_the_frontends_real_recording_is_accepted(self, transcribe, upload, *_):
        # 前端錄的是 Opus（webm），宣告類型是 audio/webm
        response = self.reply(audio("round_audio.webm", content_type="audio/webm"))

        self.assertEqual(response.status_code, 201)
        transcribe.assert_called_once()

    def test_a_content_type_with_codecs_is_accepted(self, transcribe, upload, *_):
        response = self.reply(audio("blob", content_type="audio/webm; codecs=opus"))

        self.assertEqual(response.status_code, 201)

    def test_common_audio_formats_are_accepted(self, transcribe, upload, *_):
        for name, content_type in (
            ("a.m4a", "audio/mp4"),
            ("a.mp3", "audio/mpeg"),
            ("a.wav", "audio/wav"),
            ("a.ogg", "application/octet-stream"),
            ("a.webm", "video/webm"),
        ):
            with self.subTest(name=name):
                DiaryReply.objects.all().delete()
                response = self.reply(audio(name, content_type=content_type))
                self.assertEqual(response.status_code, 201)

    def test_audio_exactly_at_the_limit_is_accepted(self, transcribe, upload, *_):
        response = self.reply(audio(content=b"x" * upload_checks.MAX_AUDIO_BYTES))

        self.assertEqual(response.status_code, 201)

    def test_audio_over_the_limit_is_rejected_before_transcribing(
        self, transcribe, upload, *_
    ):
        response = self.reply(audio(content=b"x" * (upload_checks.MAX_AUDIO_BYTES + 1)))

        self.assert_rejected(response, "AUDIO_TOO_LARGE", transcribe, upload)

    def test_a_non_audio_file_is_rejected_before_transcribing(
        self, transcribe, upload, *_
    ):
        for name, content_type in (
            ("evil.html", "text/html"),
            ("photo.jpg", "image/jpeg"),
            ("run.exe", "application/octet-stream"),
            ("noextension", "application/octet-stream"),
        ):
            with self.subTest(name=name):
                response = self.reply(audio(name, content_type=content_type))
                self.assert_rejected(response, "INVALID_AUDIO", transcribe, upload)

    def test_a_rejected_recording_does_not_use_up_the_round(
        self, transcribe, upload, *_
    ):
        self.reply(audio("evil.html", content_type="text/html"))

        # 重新送正確的錄音，同一輪還能回答
        response = self.reply(audio())

        self.assertEqual(response.status_code, 201)

    def test_the_diary_stays_unchanged_after_a_rejection(self, transcribe, upload, *_):
        self.reply(audio(content=b"x" * (upload_checks.MAX_AUDIO_BYTES + 1)))

        self.diary.refresh_from_db()
        self.assertEqual(self.diary.status, "pending")


class CheckFunctionTests(SimpleTestCase):
    """直接測檢查函式的邊界（不用真的產生大檔案）。"""

    def test_photo_size_boundary(self):
        limit = upload_checks.MAX_PHOTO_BYTES
        self.assertIsNone(upload_checks.check_photo(FakeFile("a.jpg", limit)))
        self.assertEqual(
            upload_checks.check_photo(FakeFile("a.jpg", limit + 1))[0],
            "IMAGE_TOO_LARGE",
        )

    def test_audio_size_boundary(self):
        limit = upload_checks.MAX_AUDIO_BYTES
        self.assertIsNone(upload_checks.check_audio(FakeFile("a.webm", limit)))
        self.assertEqual(
            upload_checks.check_audio(FakeFile("a.webm", limit + 1))[0],
            "AUDIO_TOO_LARGE",
        )

    def test_zero_byte_files_are_rejected(self):
        self.assertEqual(
            upload_checks.check_photo(FakeFile("a.jpg", 0))[0], "INVALID_IMAGE"
        )
        self.assertEqual(
            upload_checks.check_audio(FakeFile("a.webm", 0))[0], "INVALID_AUDIO"
        )

    def test_a_missing_name_does_not_crash(self):
        self.assertEqual(
            upload_checks.check_photo(FakeFile(None, 10))[0], "INVALID_IMAGE"
        )
        self.assertEqual(
            upload_checks.check_audio(FakeFile("", 10))[0], "INVALID_AUDIO"
        )

    def test_the_limits_are_sane(self):
        # 前端的照片壓縮後通常不到 1MB、錄音最長 3 分鐘；上限不能小到誤擋正常檔案，
        # 也不能大到失去意義
        self.assertGreaterEqual(upload_checks.MAX_PHOTO_BYTES, 5 * 1024 * 1024)
        self.assertLessEqual(upload_checks.MAX_PHOTO_BYTES, 20 * 1024 * 1024)
        self.assertGreaterEqual(upload_checks.MAX_AUDIO_BYTES, 10 * 1024 * 1024)
        self.assertLessEqual(upload_checks.MAX_AUDIO_BYTES, 50 * 1024 * 1024)
