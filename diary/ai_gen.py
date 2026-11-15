"""日記的 AI 產生：首問、追問、完成日記時的標題／回應／貼文內容。

AI 寫的句子會直接顯示給長者，所以回來之後一定要檢查：
- 出現醫療宣稱或負面字眼（見 ai_service/wording.py）→ 改用固定句型
- 欄位型別不對、太長 → 修正成資料庫放得下的值，避免寫入時才出錯
AI 失敗（沒網路、金鑰錯誤、回傳格式不對）也一律退回固定句型，不讓日記流程中斷。
"""

import json
import logging

from django.conf import settings

from ai_service.wording import contains_banned_word

logger = logging.getLogger(__name__)

# 每個提示詞都附上：不能有醫療宣稱、不評論長者的記憶或認知狀況
SAFETY_RULES = (
    "規則：不可提到醫療、診斷、疾病、失智或療效；"
    "不可評論或猜測長者的記憶力、認知狀況或健康；不可使用負面字眼。"
)

FIRST_QUESTION_PROMPT = (
    "根據照片描述，用繁體中文生成一個問句，引導長者分享這張照片的故事，只回問句。"
)
FOLLOW_UP_PROMPT = (
    "你是溫暖的聊天夥伴，針對長者剛剛說的內容，"
    "先溫暖回應，再問一個延伸問題，繁體中文，100字內。"
)
FINALIZE_PROMPT = (
    "根據日記內容，用繁體中文生成：title(10字內含emoji)、"
    "ai_response(100字內溫暖回應)、post_text(第一人稱50字內)、hashtags(3個)、"
    "category(food/clothing/housing/transport/education/entertainment擇一)、"
    "suggested_replies(3句15字內)、invite_text(30字內邀請文案)。用JSON格式回傳。"
)

FIRST_QUESTION_FALLBACK = "這張照片是在哪裡拍的呢？"
FOLLOW_UP_FALLBACK = "還有什麼想跟我分享的嗎？"

ALLOWED_CATEGORIES = {
    "food",
    "clothing",
    "housing",
    "transport",
    "education",
    "entertainment",
}

# 對應 Diary 模型的欄位長度（title max_length=50、invite_text max_length=100）
TITLE_MAX_LENGTH = 50
INVITE_TEXT_MAX_LENGTH = 100
MAX_LIST_ITEMS = 5


def _client():
    from openai import OpenAI

    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=getattr(settings, "OPENAI_BASE_URL", None),
    )


def _model():
    return getattr(settings, "OPENAI_MODEL", "gpt-4.1-mini")


def _safe_text(text, fallback, what):
    """AI 回來的句子是空的或有禁用詞，就改用固定句型。"""
    if not isinstance(text, str) or not text.strip():
        return fallback
    if contains_banned_word(text):
        logger.warning("日記 AI %s出現禁用詞，改用固定句型：%s", what, text)
        return fallback
    return text.strip()


def generate_first_question(photo_description=""):
    try:
        res = _client().chat.completions.create(
            model=_model(),
            messages=[
                {"role": "system", "content": FIRST_QUESTION_PROMPT + SAFETY_RULES},
                {"role": "user", "content": photo_description or "一張照片"},
            ],
            max_tokens=50,
        )
        return _safe_text(
            res.choices[0].message.content, FIRST_QUESTION_FALLBACK, "首問"
        )
    except Exception as e:
        logger.warning("生成首問失敗: %s", e)
        return FIRST_QUESTION_FALLBACK


def generate_follow_up(context_text):
    try:
        res = _client().chat.completions.create(
            model=_model(),
            messages=[
                {"role": "system", "content": FOLLOW_UP_PROMPT + SAFETY_RULES},
                {"role": "user", "content": context_text},
            ],
            max_tokens=100,
        )
        return _safe_text(res.choices[0].message.content, FOLLOW_UP_FALLBACK, "追問")
    except Exception as e:
        logger.warning("生成追問失敗: %s", e)
        return FOLLOW_UP_FALLBACK


def _clean_list(value, default):
    """清單欄位（hashtags、suggested_replies）：只留下沒有禁用詞的字串，沒有剩就用預設。"""
    if not isinstance(value, list):
        return default
    items = [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip() and not contains_banned_word(item)
    ]
    return items[:MAX_LIST_ITEMS] or default


def clean_finalize_content(result, defaults):
    """檢查 AI 產生的日記內容，每個欄位不合格就用 defaults 裡的值。

    不修改傳入的 dict，回傳新的 dict。
    """
    if not isinstance(result, dict):
        return dict(defaults)

    cleaned = dict(defaults)
    for key in ("title", "ai_response", "post_text", "invite_text"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            if contains_banned_word(value):
                logger.warning("日記 AI %s出現禁用詞，改用預設值：%s", key, value)
            else:
                cleaned[key] = value.strip()

    # 超過資料庫欄位長度會在儲存時出錯，先截短
    cleaned["title"] = cleaned["title"][:TITLE_MAX_LENGTH]
    cleaned["invite_text"] = cleaned["invite_text"][:INVITE_TEXT_MAX_LENGTH]

    if result.get("category") in ALLOWED_CATEGORIES:
        cleaned["category"] = result["category"]
    cleaned["hashtags"] = _clean_list(result.get("hashtags"), defaults["hashtags"])
    cleaned["suggested_replies"] = _clean_list(
        result.get("suggested_replies"), defaults["suggested_replies"]
    )
    return cleaned


def generate_finalize_content(combined_text):
    defaults = {
        "title": combined_text[:10] if combined_text else "今天的日記",
        "ai_response": "謝謝你今天的分享！",
        "post_text": combined_text[:50] if combined_text else "",
        "hashtags": ["#聲影日記", "#每日記錄", "#長者生活"],
        "category": "entertainment",
        "suggested_replies": [
            "聽起來很棒！",
            "下次也要告訴我喔～",
            "你今天過得真充實！",
        ],
        "invite_text": "今天記錄了一段回憶，點進來看看吧！",
    }
    try:
        res = _client().chat.completions.create(
            model=_model(),
            messages=[
                {"role": "system", "content": FINALIZE_PROMPT + SAFETY_RULES},
                {"role": "user", "content": combined_text},
            ],
            max_tokens=400,
        )
        content = res.choices[0].message.content.strip()
        content = content.removeprefix("```json").removesuffix("```").strip()
        return clean_finalize_content(json.loads(content), defaults)
    except Exception as e:
        logger.warning("生成日記內容失敗: %s", e)
        return defaults
