"""首頁問候語：每天請 AI 寫一句，失敗就用固定問候語。

一天只呼叫一次 AI，結果存在 Django 快取裡，當天所有人看到同一句。
AI 回來的句子會再檢查一次：太長或出現禁用詞（醫療、專有名詞、負面字眼）
就改用固定問候語。
"""

import logging

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .weekly_summary import _client
from .wording import contains_banned_word

logger = logging.getLogger(__name__)

# 提示詞要求 10 字以內；檢查時多留 2 個字給標點符號（，。？）
MAX_GREETING_LENGTH = 12

# 一天一句的快取時間；AI 失敗時的固定句只快取一下，之後還有機會再問 AI
CACHE_SECONDS = 24 * 60 * 60
FALLBACK_CACHE_SECONDS = 10 * 60

FALLBACK_GREETINGS = [
    "今天也要保持大腦活力喔。",
    "早安，今天心情如何呢？",
    "陽光正好，適合散散步。",
]

SYSTEM_PROMPT = (
    "你是陪伴長輩的溫暖小幫手。請用繁體中文寫一句 10 字以內的問候語，"
    "語氣親切、正向。規則：只回這一句話，不要加引號或說明；"
    "不可提到醫療、診斷、失智或療效；不可使用負面字眼。"
    "語氣可以參考這些範例：\n" + "\n".join(FALLBACK_GREETINGS)
)


def build_fallback_greeting(today):
    """固定問候語：依日期輪流挑一句，同一天一定是同一句。"""
    return FALLBACK_GREETINGS[today.toordinal() % len(FALLBACK_GREETINGS)]


def _is_acceptable(greeting):
    return (
        bool(greeting)
        and len(greeting) <= MAX_GREETING_LENGTH
        and not contains_banned_word(greeting)
    )


def generate_greeting(today):
    """請 AI 寫一句問候語；AI 失敗或句子不合格就用固定問候語。

    回傳 (句子, 是否為 AI 寫的)。
    """
    fallback = build_fallback_greeting(today)
    try:
        response = _client().chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "請寫今天的問候語。"},
            ],
            max_tokens=40,
        )
        greeting = (response.choices[0].message.content or "").strip()
    except Exception:
        logger.warning("首頁問候語 AI 產生失敗，改用固定問候語", exc_info=True)
        return fallback, False

    if not _is_acceptable(greeting):
        logger.warning("首頁問候語 AI 不合格，改用固定問候語：%s", greeting)
        return fallback, False
    return greeting, True


def get_daily_greeting():
    """取得今天的問候語：當天第一次呼叫時產生並存快取，之後直接回傳。"""
    today = timezone.localdate()
    cache_key = f"home_greeting:{today.isoformat()}"

    greeting = cache.get(cache_key)
    if greeting is not None:
        return greeting

    greeting, from_ai = generate_greeting(today)
    cache.set(cache_key, greeting, CACHE_SECONDS if from_ai else FALLBACK_CACHE_SECONDS)
    return greeting
