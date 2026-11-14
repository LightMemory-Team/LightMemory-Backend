"""日記照片與錄音的上傳檢查（大小、類型）。

以前只有頭像有限制，日記的照片和錄音可以傳任意大小、任意類型的檔案：
- 錄音會交給本機的 Whisper 辨識，超大或亂塞的檔案會吃光 CPU、記憶體與時間
- 照片、錄音都會原樣存進 Firebase，任何登入者都能塞垃圾進去

這裡只做「便宜的檢查」（檔名副檔名、瀏覽器宣告的類型、檔案大小），
不解析檔案內容。檢查通過不代表檔案一定是正常的照片／錄音，
真的壞掉的檔案仍由後面的流程處理（辨識失敗會回 TRANSCRIPTION_FAILED）。
"""

import os

# 大小上限。前端的照片已壓縮（寬度 1600、品質 85，通常不到 1MB），
# 錄音單輪最長 3 分鐘（Opus 通常約 1MB），上限都留了很大的餘裕。
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_AUDIO_BYTES = 25 * 1024 * 1024

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
AUDIO_EXTENSIONS = {
    ".webm",
    ".ogg",
    ".opus",
    ".m4a",
    ".mp4",
    ".aac",
    ".mp3",
    ".wav",
    ".flac",
}
# 瀏覽器錄的 webm／mp4 錄音，有些會被標成 video/*
AUDIO_EXTRA_TYPES = {"video/webm", "video/mp4", "video/ogg"}

PHOTO_TOO_LARGE_MESSAGE = "這張照片太大了（不能超過 10MB），換一張試試看吧"
AUDIO_TOO_LARGE_MESSAGE = "這段錄音太大了（不能超過 25MB），請再錄一次"


def _extension(file_obj):
    return os.path.splitext((file_obj.name or "").lower())[1]


def _content_type(file_obj):
    # 例如 "audio/webm; codecs=opus" 只取前面的類型
    raw = getattr(file_obj, "content_type", "") or ""
    return raw.split(";")[0].strip().lower()


def check_photo(file_obj):
    """照片合格回傳 None，否則回傳 (錯誤碼, 給使用者看的訊息)。"""
    if file_obj.size == 0:
        return "INVALID_IMAGE", "這張照片無法使用，換一張試試看吧"
    if file_obj.size > MAX_PHOTO_BYTES:
        return "IMAGE_TOO_LARGE", PHOTO_TOO_LARGE_MESSAGE
    # 副檔名或宣告的類型，有一個像照片就放行（前端上傳照片時不一定帶類型）
    if _extension(file_obj) in PHOTO_EXTENSIONS or _content_type(file_obj).startswith(
        "image/"
    ):
        return None
    return "INVALID_IMAGE", "這張照片無法使用，換一張試試看吧"


def check_audio(file_obj):
    """錄音合格回傳 None，否則回傳 (錯誤碼, 給使用者看的訊息)。"""
    if file_obj.size == 0:
        return "INVALID_AUDIO", "這一段錄音沒有收到，請再錄一次"
    if file_obj.size > MAX_AUDIO_BYTES:
        return "AUDIO_TOO_LARGE", AUDIO_TOO_LARGE_MESSAGE
    content_type = _content_type(file_obj)
    if (
        _extension(file_obj) in AUDIO_EXTENSIONS
        or content_type.startswith("audio/")
        or content_type in AUDIO_EXTRA_TYPES
    ):
        return None
    return "INVALID_AUDIO", "這一段錄音沒有收到，請再錄一次"
