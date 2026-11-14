"""download_from_firebase()（語音加油轉文字前下載音檔）的測試，不連真的 Firebase。"""

import os
from unittest.mock import patch

from django.test import SimpleTestCase

from diary import external

from .test_media import fake_firebase


class DownloadFromFirebaseTests(SimpleTestCase):
    def test_downloads_to_a_temp_file_with_the_same_extension(self):
        def write_file(filename):
            with open(filename, "wb") as f:
                f.write(b"audio-bytes")

        with fake_firebase() as bucket:
            bucket.blob.return_value.download_to_filename.side_effect = write_file
            tmp_path = external.download_from_firebase("voice-diary/vr/a.webm")

        try:
            bucket.blob.assert_called_once_with("voice-diary/vr/a.webm")
            self.assertTrue(tmp_path.endswith(".webm"))
            with open(tmp_path, "rb") as f:
                self.assertEqual(f.read(), b"audio-bytes")
        finally:
            os.remove(tmp_path)

    def test_failure_returns_none_and_leaves_no_temp_file(self):
        created = []
        real_named_tmp = external.tempfile.NamedTemporaryFile

        def tracking_tmp(*args, **kwargs):
            tmp = real_named_tmp(*args, **kwargs)
            created.append(tmp.name)
            return tmp

        with (
            fake_firebase() as bucket,
            patch.object(external.tempfile, "NamedTemporaryFile", tracking_tmp),
            self.assertLogs("diary.external", level="ERROR"),
        ):
            bucket.blob.return_value.download_to_filename.side_effect = RuntimeError(
                "404"
            )
            result = external.download_from_firebase("voice-diary/vr/missing.webm")

        self.assertIsNone(result)
        self.assertEqual(len(created), 1)
        self.assertFalse(os.path.exists(created[0]))
