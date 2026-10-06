import importlib
import os
from unittest.mock import patch

from django.test import SimpleTestCase

FAKE_ENV = {
    "FIREBASE_PROJECT_ID": "test-project",
    "FIREBASE_STORAGE_BUCKET": "test-bucket.firebasestorage.app",
    "FIREBASE_CREDENTIALS_PATH": "secrets/test-key.json",
}


@patch.dict(os.environ, FAKE_ENV)
@patch("firebase_admin.credentials.Certificate")
@patch("firebase_admin.initialize_app")
class FirebaseAppConfigTests(SimpleTestCase):
    """確認 Firebase 設定是透過 decouple 從環境變數 / .env 讀取。"""

    def _get_firebase_app(self):
        # import config.firebase 時會在模組層級初始化一次，所以也要在 mock 底下 import
        with patch("firebase_admin.get_app", side_effect=ValueError):
            firebase = importlib.import_module("config.firebase")
            return firebase, firebase.get_firebase_app()

    def test_reads_project_id_and_bucket_from_env(self, mock_init, mock_cert):
        self._get_firebase_app()

        options = mock_init.call_args.args[1]
        self.assertEqual(options["projectId"], "test-project")
        self.assertEqual(options["storageBucket"], "test-bucket.firebasestorage.app")

    def test_reads_credentials_path_from_env(self, mock_init, mock_cert):
        firebase, _ = self._get_firebase_app()

        expected = str(firebase.BASE_DIR / "secrets/test-key.json")
        mock_cert.assert_called_with(expected)

    def test_returns_existing_app_without_reinitializing(self, mock_init, mock_cert):
        firebase, _ = self._get_firebase_app()
        mock_init.reset_mock()

        existing_app = object()
        with patch("firebase_admin.get_app", return_value=existing_app):
            self.assertIs(firebase.get_firebase_app(), existing_app)
        mock_init.assert_not_called()
