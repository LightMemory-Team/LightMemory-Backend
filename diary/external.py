import uuid
import tempfile
import os


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
        print(f"Firebase上傳失敗: {e}")
        return ""


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
            return result.get("text", "").strip()
        finally:
            os.remove(tmp_path)
    except Exception as e:
        print(f"Whisper轉錄失敗: {e}")
        return ""