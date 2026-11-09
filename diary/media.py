"""日記照片、錄音的網址轉換。

日記的照片與錄音是私人內容，上傳到 Firebase Storage 後不再設成公開。
資料庫（image_path、audio_path）存的是「檔案路徑」，例如
    voice-diary/images/3f2a....jpg
回傳給前端時才用 media_url() 換成有時效的簽名網址，過期後網址就失效。

相容舊資料：以 http:// 或 https:// 開頭的值（舊的公開網址、示範資料）原樣回傳。

簽名網址的有效秒數預設 6 小時，可在 settings 加 MEDIA_SIGNED_URL_SECONDS 覆蓋。
"""

import logging
from datetime import timedelta

from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_SIGNED_URL_SECONDS = 6 * 60 * 60


def is_full_url(value):
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def media_url(stored):
    """把資料庫存的值轉成前端可以直接開啟的網址。

    - 空值（None、空字串）→ 原樣回傳
    - 完整網址（舊資料、示範資料）→ 原樣回傳
    - 檔案路徑 → 簽名網址；簽名失敗時回傳 None（並記錄錯誤），不讓整支 API 掛掉
    """
    if not stored or is_full_url(stored):
        return stored
    try:
        from firebase_admin import storage

        from config.firebase import firebase_app

        bucket = storage.bucket(app=firebase_app)
        seconds = getattr(
            settings, "MEDIA_SIGNED_URL_SECONDS", DEFAULT_SIGNED_URL_SECONDS
        )
        return bucket.blob(stored).generate_signed_url(
            version="v4", expiration=timedelta(seconds=seconds), method="GET"
        )
    except Exception as e:
        logger.error(f"產生簽名網址失敗（{stored}）: {e}")
        return None
