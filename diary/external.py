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


def upload_to_firebase(file_obj, folder):
    try:
        from firebase_admin import storage
        from config.firebase import firebase_app
        bucket = storage.bucket(app=firebase_app)
        ext = file_obj.name.split('.')[-1] if '.' in file_obj.name else 'bin'
        blob = bucket.blob(f"voice-diary/{folder}/{uuid.uuid4().hex}.{ext}")
        blob.upload_from_file(file_obj, content_type=getattr(file_obj, 'content_type', None))
        blob.make_public()
        return blob.public_url
    except Exception as e:
        logger.error(f"Firebase上傳失敗: {e}")
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