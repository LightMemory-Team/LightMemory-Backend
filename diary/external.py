import uuid
import tempfile
import os
import logging

logger = logging.getLogger(__name__)

# 簡體轉繁體
try:
    from opencc import OpenCC
    _cc = OpenCC('s2twp')
except ImportError:
    logger.warning("opencc 未安裝，將跳過簡轉繁（請執行 pip install opencc-python-reimplemented）")
    _cc = None


def upload_to_firebase(file_obj, folder, public=False):
    """上傳檔案到 Firebase Storage。

    public=False（預設，日記照片與錄音）：檔案保持私有，回傳「檔案路徑」，
    要給前端時用 diary.media.media_url() 換成有時效的簽名網址。
    public=True（頭像）：檔案設成公開，回傳永久公開網址。
    上傳失敗回傳 None。
    """
    try:
        from firebase_admin import storage
        from config.firebase import firebase_app
        bucket = storage.bucket(app=firebase_app)
        ext = file_obj.name.split('.')[-1] if '.' in file_obj.name else 'bin'
        blob = bucket.blob(f"voice-diary/{folder}/{uuid.uuid4().hex}.{ext}")
        blob.upload_from_file(file_obj, content_type=getattr(file_obj, 'content_type', None))
        if public:
            blob.make_public()
            return blob.public_url
        return blob.name
    except Exception as e:
        logger.error(f"Firebase上傳失敗: {e}")
        return None


def download_from_firebase(path):
    """把 Firebase 上的私有檔案下載成本機暫存檔，回傳暫存檔路徑；失敗回傳 None。

    path 是 upload_to_firebase() 回傳的檔案路徑。暫存檔用完後由呼叫端刪除。
    """
    tmp_path = None
    try:
        from firebase_admin import storage

        from config.firebase import firebase_app

        bucket = storage.bucket(app=firebase_app)
        suffix = os.path.splitext(path)[1] or '.bin'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
        bucket.blob(path).download_to_filename(tmp_path)
        return tmp_path
    except Exception as e:
        logger.error(f"Firebase下載失敗（{path}）: {e}")
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        return None


_whisper_model = None

def transcribe_audio(file_obj):
    try:
        global _whisper_model
        if _whisper_model is None:
            import whisper
            _whisper_model = whisper.load_model("base")
        suffix = '.' + file_obj.name.split('.')[-1] if '.' in file_obj.name else '.wav'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            for chunk in file_obj.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        try:
            result = _whisper_model.transcribe(tmp_path, language="zh")
            text = result.get("text", "").strip()
        finally:
            os.remove(tmp_path)
    except Exception as e:
        logger.error(f"Whisper轉錄失敗: {e}")
        return None

    if _cc and text:
        text = _cc.convert(text)
    return text


def blob_name_from_stored(value, bucket_name):
    """把資料庫存的值換算成 bucket 裡的檔案路徑。

    - 檔案路徑（日記照片、錄音，例如 voice-diary/images/x.jpg）→ 原樣回傳
    - 這個 bucket 的完整網址（頭像、舊的公開日記檔案）→ 取出網址裡的檔案路徑
    - 其他（空值、本機 /media/ 路徑、別的網站的網址、示範資料）→ None，不能刪
    """
    from urllib.parse import unquote, urlparse

    if not value or not isinstance(value, str):
        return None
    if not value.startswith(("http://", "https://")):
        return None if value.startswith("/") else value

    parsed = urlparse(value)
    segments = parsed.path.split("/", 3)  # ["", 第一段, 第二段, 其餘]
    if parsed.netloc == "storage.googleapis.com":
        # https://storage.googleapis.com/<bucket>/<檔案路徑>
        if len(segments) == 4 and segments[1] == bucket_name:
            return unquote(parsed.path.split("/", 2)[2]) or None
    elif parsed.netloc == "firebasestorage.googleapis.com":
        # https://firebasestorage.googleapis.com/v0/b/<bucket>/o/<編碼後的檔案路徑>
        parts = parsed.path.split("/")
        if len(parts) >= 6 and parts[2] == "b" and parts[3] == bucket_name and parts[4] == "o":
            return unquote("/".join(parts[5:])) or None
    return None


def delete_from_firebase(stored_values):
    """盡力刪除這些檔案，回傳成功刪除的數量。

    stored_values 是資料庫裡存的值（路徑或網址），重複的只刪一次；
    不是這個 bucket 的檔案會略過。刪除失敗只記錄，不丟例外，
    所以不會因為雲端問題擋住呼叫端（例如刪除帳號）。
    """
    candidates = {v for v in stored_values if v}
    if not candidates:
        return 0
    try:
        from firebase_admin import storage
        from config.firebase import firebase_app
        bucket = storage.bucket(app=firebase_app)
    except Exception as e:
        logger.error(f"Firebase 連線失敗，無法刪除檔案: {e}")
        return 0

    names = {blob_name_from_stored(v, bucket.name) for v in candidates} - {None}
    deleted = 0
    for name in sorted(names):
        try:
            bucket.blob(name).delete()
            deleted += 1
        except Exception as e:
            logger.error(f"Firebase 刪除檔案失敗（{name}）: {e}")
    return deleted
