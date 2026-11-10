"""日記照片、錄音改用簽名網址的測試。

執行：
    python manage.py test diary.tests_media --settings=config.settings_test
"""

import sys
import types
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from dashboard.models import WeeklyReport
from diary import external
from diary.media import media_url
from diary.models import Diary, DiaryReply
from social.models import Post

User = get_user_model()

SIGNED = "https://storage.example/signed?sig=abc"
PATH = "voice-diary/images/abc123.jpg"


@contextmanager
def fake_firebase(signed_url=SIGNED):
    """不連真的 Firebase：假的 bucket，blob 簽名時回傳 signed_url。"""
    bucket = MagicMock()
    bucket.blob.return_value.generate_signed_url.return_value = signed_url
    bucket.blob.return_value.name = "voice-diary/images/new.jpg"
    bucket.blob.return_value.public_url = "https://public.example/new.jpg"
    fake_config = types.ModuleType("config.firebase")
    fake_config.firebase_app = object()
    with (
        patch.dict(sys.modules, {"config.firebase": fake_config}),
        patch("firebase_admin.storage.bucket", return_value=bucket),
    ):
        yield bucket


class MediaUrlTests(SimpleTestCase):
    def test_empty_values_are_returned_as_is(self):
        self.assertIsNone(media_url(None))
        self.assertEqual(media_url(""), "")

    def test_full_urls_are_returned_unchanged(self):
        for url in ("https://a.example/x.jpg", "http://a.example/x.jpg"):
            with self.subTest(url=url):
                with fake_firebase() as bucket:
                    self.assertEqual(media_url(url), url)
                    bucket.blob.assert_not_called()

    def test_path_becomes_signed_url(self):
        with fake_firebase() as bucket:
            self.assertEqual(media_url(PATH), SIGNED)

        bucket.blob.assert_called_once_with(PATH)
        kwargs = bucket.blob.return_value.generate_signed_url.call_args.kwargs
        self.assertEqual(kwargs["version"], "v4")
        self.assertEqual(kwargs["method"], "GET")
        self.assertEqual(kwargs["expiration"], timedelta(hours=6))

    @override_settings(MEDIA_SIGNED_URL_SECONDS=600)
    def test_expiry_can_be_configured(self):
        with fake_firebase() as bucket:
            media_url(PATH)

        kwargs = bucket.blob.return_value.generate_signed_url.call_args.kwargs
        self.assertEqual(kwargs["expiration"], timedelta(seconds=600))

    def test_signing_failure_returns_none_instead_of_raising(self):
        with fake_firebase() as bucket:
            bucket.blob.return_value.generate_signed_url.side_effect = RuntimeError("x")

            self.assertIsNone(media_url(PATH))


class UploadVisibilityTests(SimpleTestCase):
    def _file(self):
        return SimpleUploadedFile("a.jpg", b"data", content_type="image/jpeg")

    def test_default_upload_stays_private_and_returns_path(self):
        with fake_firebase() as bucket:
            result = external.upload_to_firebase(self._file(), "images")

        self.assertEqual(result, "voice-diary/images/new.jpg")
        bucket.blob.return_value.make_public.assert_not_called()

    def test_public_upload_returns_public_url(self):
        with fake_firebase() as bucket:
            result = external.upload_to_firebase(self._file(), "avatars", public=True)

        self.assertEqual(result, "https://public.example/new.jpg")
        bucket.blob.return_value.make_public.assert_called_once()


class DiaryApiSignedUrlTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="media_user", password="Str0ng!Pass2026"
        )
        self.client.force_authenticate(user=self.user)

    def test_detail_returns_signed_photo_and_audio_urls(self):
        diary = Diary.objects.create(
            user=self.user, status="processing", image_path=PATH
        )
        DiaryReply.objects.create(
            diary=diary,
            round_index=1,
            question="q",
            transcript="t",
            audio_path="voice-diary/audio/r1.wav",
        )

        with fake_firebase():
            response = self.client.get(f"/api/diary/{diary.id}/")

        data = response.data["data"]
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(data["photo_url"], SIGNED)
        self.assertEqual(data["replies"][0]["audio_url"], SIGNED)

    def test_old_public_urls_still_work(self):
        old_url = "https://storage.googleapis.com/bucket/old.jpg"
        diary = Diary.objects.create(
            user=self.user, status="processing", image_path=old_url
        )

        response = self.client.get(f"/api/diary/{diary.id}/")

        self.assertEqual(response.data["data"]["photo_url"], old_url)

    def test_calendar_returns_signed_photo_url(self):
        Diary.objects.create(user=self.user, status="done", image_path=PATH)

        with fake_firebase():
            response = self.client.get("/api/diary/")

        diaries = response.data["data"]["diaries"]
        self.assertEqual(diaries[0]["photo_url"], SIGNED)

    def test_api_still_works_when_signing_fails(self):
        diary = Diary.objects.create(
            user=self.user, status="processing", image_path=PATH
        )

        with fake_firebase() as bucket:
            bucket.blob.return_value.generate_signed_url.side_effect = RuntimeError("x")
            response = self.client.get(f"/api/diary/{diary.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["data"]["photo_url"])

    @patch("diary.views.ai_gen.generate_first_question", return_value="問題")
    def test_upload_stores_path_and_returns_signed_url(self, _question):
        photo = SimpleUploadedFile("p.jpg", b"data", content_type="image/jpeg")

        with (
            fake_firebase(),
            patch("diary.views.external.upload_to_firebase", return_value=PATH),
        ):
            response = self.client.post(
                "/api/diary/", {"photo": photo}, format="multipart"
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["photo_url"], SIGNED)
        self.assertEqual(Diary.objects.get(user=self.user).image_path, PATH)


class OtherEndpointsSignedUrlTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="media_owner", password="Str0ng!Pass2026"
        )
        self.client.force_authenticate(user=self.user)

    def test_social_post_returns_signed_photo_url(self):
        diary = Diary.objects.create(
            user=self.user, status="done", title="t", image_path=PATH
        )
        Post.objects.create(user=self.user, diary=diary, content="c", image_path=PATH)

        with fake_firebase():
            response = self.client.get("/api/social/posts/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(SIGNED, str(response.data))
        self.assertNotIn(PATH, str(response.data))

    def test_share_page_uses_signed_photo_url(self):
        diary = Diary.objects.create(
            user=self.user, status="done", title="t", image_path=PATH
        )
        post = Post.objects.create(
            user=self.user, diary=diary, content="c", image_path=PATH
        )

        with fake_firebase():
            response = self.client.get(f"/share/{post.share_token}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, SIGNED.replace("&", "&amp;"))
        self.assertNotContains(response, PATH)

    def test_weekly_report_snapshot_keeps_path_but_response_is_signed(self):
        report = {
            "week_start": "2026-11-02",
            "diary": {
                "talk_seconds": 0,
                "entries": [
                    {"diary_id": 1, "photo_url": PATH, "title": "t", "post_text": "p"}
                ],
            },
        }

        with (
            fake_firebase(),
            patch(
                "dashboard.views.weekly_report.build_weekly_report_with_facts",
                return_value=(report, {"active_day_count": 0}),
            ),
        ):
            response = self.client.get("/api/dashboard/weekly-report/")

        entry = response.data["data"]["diary"]["entries"][0]
        self.assertEqual(entry["photo_url"], SIGNED)
        saved = WeeklyReport.objects.get(user=self.user).report
        self.assertEqual(saved["diary"]["entries"][0]["photo_url"], PATH)
