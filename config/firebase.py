from pathlib import Path

import firebase_admin
from decouple import config
from firebase_admin import credentials

# 專案根目錄
BASE_DIR = Path(__file__).resolve().parent.parent


def get_firebase_app():
    """
    初始化 Firebase Admin SDK。
    如果已經初始化過，就直接取得原本的 Firebase App。
    """

    try:
        return firebase_admin.get_app()

    except ValueError:
        # 從 .env 取得 Firebase 金鑰相對路徑（decouple 會自動讀根目錄的 .env）
        credentials_path = config(
            "FIREBASE_CREDENTIALS_PATH", default="secrets/firebase-key.json"
        )

        # 組合成完整路徑
        credentials_path = BASE_DIR / credentials_path

        # 讀取 Firebase Service Account 金鑰
        cred = credentials.Certificate(str(credentials_path))

        # 初始化 Firebase
        return firebase_admin.initialize_app(
            cred,
            {
                "projectId": config("FIREBASE_PROJECT_ID"),
                "storageBucket": config("FIREBASE_STORAGE_BUCKET"),
            },
        )


firebase_app = get_firebase_app()
