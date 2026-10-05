from django.conf import settings


def _client():
    from openai import OpenAI
    return OpenAI(api_key=settings.OPENAI_API_KEY, base_url=getattr(settings, 'OPENAI_BASE_URL', None))


def generate_first_question(photo_description=""):
    try:
        client = _client()
        res = client.chat.completions.create(
            model=getattr(settings, 'OPENAI_MODEL', 'gpt-4.1-mini'),
            messages=[{"role": "system", "content": "根據照片描述，用繁體中文生成一個問句，引導長者分享這張照片的故事，只回問句。"},
                      {"role": "user", "content": photo_description or "一張照片"}],
            max_tokens=50,
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        print(f"生成首問失敗: {e}")
        return "這張照片是在哪裡拍的呢？"


def generate_follow_up(context_text):
    try:
        client = _client()
        res = client.chat.completions.create(
            model=getattr(settings, 'OPENAI_MODEL', 'gpt-4.1-mini'),
            messages=[{"role": "system", "content": "你是溫暖的聊天夥伴，針對長者剛剛說的內容，先溫暖回應，再問一個延伸問題，繁體中文，100字內。"},
                      {"role": "user", "content": context_text}],
            max_tokens=100,
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        print(f"生成追問失敗: {e}")
        return "還有什麼想跟我分享的嗎？"


def generate_finalize_content(combined_text):
    defaults = {
        "title": combined_text[:10] if combined_text else "今天的日記",
        "ai_response": "謝謝你今天的分享！",
        "post_text": combined_text[:50] if combined_text else "",
        "hashtags": ["#聲影日記", "#每日記錄", "#長者生活"],
        "category": "entertainment",
        "suggested_replies": ["聽起來很棒！", "下次也要告訴我喔～", "你今天過得真充實！"],
        "invite_text": "今天記錄了一段回憶，點進來看看吧！",
    }
    try:
        client = _client()
        res = client.chat.completions.create(
            model=getattr(settings, 'OPENAI_MODEL', 'gpt-4.1-mini'),
            messages=[{"role": "system", "content": "根據日記內容，用繁體中文生成：title(10字內含emoji)、ai_response(100字內溫暖回應)、post_text(第一人稱50字內)、hashtags(3個)、category(food/clothing/housing/transport/education/entertainment擇一)、suggested_replies(3句15字內)、invite_text(30字內邀請文案)。用JSON格式回傳。"},
                      {"role": "user", "content": combined_text}],
            max_tokens=400,
        )
        import json
        content = res.choices[0].message.content.strip()
        content = content.removeprefix("```json").removesuffix("```").strip()
        result = json.loads(content)
        return {**defaults, **result}
    except Exception as e:
        print(f"生成日記內容失敗: {e}")
        return defaults