"""刪除帳號時一併清除雲端與本機檔案的測試。

執行：
    python manage.py test users.tests.test_delete_account_files \
        --settings=config.settings_test
"""

import os
import sys
import tempfile
import types
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from diary.external import blob_name_from_stored, delete_from_firebase
from diary.models import Diary, DiaryReply
from social.models import Post

User = get_user_model()

ME_URL = "/api/users/me/"
BUCKET = "test-bucket.firebasestorage.app"
PASSWORD = "Str0ng!Pass2026"


@contextmanager
def fake_firebase():
    """不連真的 Firebase：假的 bucket，可以檢查哪些檔案被要求刪除。"""
    bucket = MagicMock()
    bucket.name = BUCKET
    fake_config = types.ModuleType("config.firebase")
    fake_config.firebase_app = object()
    with (
        patch.dict(sys.modules, {"config.firebase": fake_config}),
        patch("firebase_admin.storage.bucket", return_value=bucket),
    ):
        yield bucket


def deleted_names(bucket):
    return sorted(call.args[0] for call in bucket.blob.call_args_list)


class BlobNameFromStoredTests(SimpleTestCase):
    def test_path_is_returned_as_is(self):
        self.assertEqual(
            blob_name_from_stored("voice-diary/images/a.jpg", BUCKET),
            "voice-diary/images/a.jpg",
        )

    def test_storage_googleapis_url_of_this_bucket(self):
        url = f"https://storage.googleapis.com/{BUCKET}/voice-diary/avatars/a%20b.jpg"

        self.assertEqual(
            blob_name_from_stored(url, BUCKET), "voice-diary/avatars/a b.jpg"
        )

    def test_firebasestorage_url_of_this_bucket(self):
        url = (
            f"https://firebasestorage.googleapis.com/v0/b/{BUCKET}"
            "/o/voice-diary%2Faudio%2Fx.wav?alt=media"
        )

        self.assertEqual(blob_name_from_stored(url, BUCKET), "voice-diary/audio/x.wav")

    def test_things_that_are_not_ours_return_none(self):
        for value in (
            None,
            "",
            "/media/avatars/a.jpg",
            "https://example.com/a.jpg",
            "https://storage.googleapis.com/other-bucket/voice-diary/a.jpg",
            "https://actions.google.com/sounds/v1/ambiences/coffee_shop.ogg",
            f"https://storage.googleapis.com/{BUCKET}/",
        ):
            with self.subTest(value=value):
                self.assertIsNone(blob_name_from_stored(value, BUCKET))


class DeleteFromFirebaseTests(SimpleTestCase):
    def test_nothing_to_delete_does_not_touch_firebase(self):
        with fake_firebase() as bucket:
            self.assertEqual(delete_from_firebase([None, ""]), 0)

        bucket.blob.assert_not_called()

    def test_duplicates_are_deleted_once_and_foreign_files_skipped(self):
        values = [
            "voice-diary/images/a.jpg",
            "voice-diary/images/a.jpg",
            f"https://storage.googleapis.com/{BUCKET}/voice-diary/images/a.jpg",
            "https://example.com/not-ours.jpg",
        ]

        with fake_firebase() as bucket:
            count = delete_from_firebase(values)

        self.assertEqual(count, 1)
        self.assertEqual(deleted_names(bucket), ["voice-diary/images/a.jpg"])

    def test_one_failure_does_not_stop_the_others(self):
        with fake_firebase() as bucket:
            bucket.blob.return_value.delete.side_effect = [RuntimeError("x"), None]

            count = delete_from_firebase(["voice-diary/a.jpg", "voice-diary/b.jpg"])

        self.assertEqual(count, 1)
        self.assertEqual(len(bucket.blob.call_args_list), 2)

    def test_firebase_unavailable_returns_zero(self):
        with patch("firebase_admin.storage.bucket", side_effect=RuntimeError("no")):
            fake_config = types.ModuleType("config.firebase")
            fake_config.firebase_app = object()
            with patch.dict(sys.modules, {"config.firebase": fake_config}):
                self.assertEqual(delete_from_firebase(["voice-diary/a.jpg"]), 0)


class DeleteAccountFilesTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="0912345678",
            password=PASSWORD,
            avatar_url=f"https://storage.googleapis.com/{BUCKET}/voice-diary/avatars/me.jpg",
        )
        self.client.force_authenticate(user=self.user)
        diary = Diary.objects.create(
            user=self.user, status="done", image_path="voice-diary/images/d1.jpg"
        )
        DiaryReply.objects.create(
            diary=diary,
            round_index=1,
            question="q",
            transcript="t",
            audio_path="voice-diary/audio/r1.wav",
        )
        # 舊資料：公開網址；示範資料：別人的網址
        Diary.objects.create(
            user=self.user,
            status="done",
            image_path=f"https://storage.googleapis.com/{BUCKET}/voice-diary/images/old.jpg",
        )
        Diary.objects.create(
            user=self.user, status="done", image_path="https://example.com/seed.jpg"
        )
        Post.objects.create(
            user=self.user,
            diary=diary,
            content="c",
            image_path="voice-diary/images/d1.jpg",
        )

    def _delete(self, password=PASSWORD):
        return self.client.delete(ME_URL, {"password": password}, format="json")

    def test_cloud_files_are_deleted_with_the_account(self):
        with fake_firebase() as bucket, self.captureOnCommitCallbacks(execute=True):
            response = self._delete()

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(
            deleted_names(bucket),
            [
                "voice-diary/audio/r1.wav",
                "voice-diary/avatars/me.jpg",
                "voice-diary/images/d1.jpg",
                "voice-diary/images/old.jpg",
            ],
        )

    def test_wrong_password_deletes_nothing(self):
        with fake_firebase() as bucket, self.captureOnCommitCallbacks(execute=True):
            response = self._delete("WrongPassword")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        bucket.blob.assert_not_called()

    def test_cloud_failure_does_not_block_account_deletion(self):
        with fake_firebase() as bucket, self.captureOnCommitCallbacks(execute=True):
            bucket.blob.return_value.delete.side_effect = RuntimeError("boom")
            response = self._delete()

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_other_users_files_are_not_touched(self):
        other = User.objects.create_user(username="other", password=PASSWORD)
        Diary.objects.create(
            user=other, status="done", image_path="voice-diary/images/other.jpg"
        )

        with fake_firebase() as bucket, self.captureOnCommitCallbacks(execute=True):
            self._delete()

        self.assertNotIn("voice-diary/images/other.jpg", deleted_names(bucket))


class DeleteAccountLocalAvatarTests(APITestCase):
    def test_local_avatar_file_is_removed(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            override_settings(MEDIA_ROOT=tmp, MEDIA_URL="/media/"),
        ):
            saved = default_storage.save("avatars/me.jpg", ContentFile(b"x"))
            user = User.objects.create_user(
                username="local", password=PASSWORD, avatar_url=f"/media/{saved}"
            )
            self.client.force_authenticate(user=user)

            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.delete(
                    ME_URL, {"password": PASSWORD}, format="json"
                )

            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertFalse(os.path.exists(os.path.join(tmp, saved)))
