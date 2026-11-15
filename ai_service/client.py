"""OpenAI client：全專案共用，統一設定 timeout 與重試。

為什麼要設 timeout：
OpenAI SDK 預設單次等待 10 分鐘、失敗重試 2 次。AI 服務一卡住，
使用者的請求（回覆日記、完成日記、看週報）就跟著卡住，最久可能卡 30 分鐘，
還會一直占著那個請求的處理程序（F7 的日記鎖也在這段時間內被握著）。

這裡改成：單次最多等 OPENAI_TIMEOUT_SECONDS 秒、最多重試 OPENAI_MAX_RETRIES 次，
所以最壞情況是 timeout × (重試次數 + 1)，預設約 30 秒。呼叫端都有 try/except，
逾時就退回固定內容，不會讓流程中斷。

重試只會用在暫時性的錯誤（連線失敗、逾時、429、5xx）；金鑰錯誤這類不會重試。
"""

from django.conf import settings


def get_client():
    from openai import OpenAI

    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )
