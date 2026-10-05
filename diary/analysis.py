import re

WHISPER_HALLUCINATION_PATTERNS = ["謝謝觀看", "請訂閱", "字幕組", "按讚", "訂閱我的頻道"]
MIN_CONTENT_LENGTH = 15

CATEGORY_WORDS = {
    "person": ["爸爸", "媽媽", "兒子", "女兒", "孫子", "孫女", "朋友", "鄰居", "老公", "老婆", "同學", "家人"],
    "location": ["家", "公園", "市場", "醫院", "學校", "餐廳", "公司", "店", "路上"],
    "event": ["吃飯", "散步", "買菜", "聊天", "運動", "看病", "上班", "旅遊", "聚餐"],
    "object": ["飯", "菜", "水", "藥", "書", "手機", "車"],
    "emotion": ["開心", "難過", "生氣", "緊張", "放鬆", "感動", "擔心", "高興"],
    "time": ["今天", "昨天", "早上", "中午", "晚上", "剛剛", "上週"],
}
CONNECTIVES = ["然後", "接著", "因為", "所以", "但是", "而且", "後來", "之後"]


def normalize_text(text):
    return re.sub(r"\s+", "", (text or "").strip())


def get_content_length(text):
    return len(re.findall(r"[一-鿿A-Za-z0-9]", text))


def collapse_repetitions(text):
    text = re.sub(r"(.)\1{2,}", r"\1", text)
    text = re.sub(r"(.{2,6}?)\1{1,}", r"\1", text)
    return text


def assess_sample_quality(raw_text):
    text = normalize_text(raw_text)
    if get_content_length(text) < MIN_CONTENT_LENGTH:
        return "too_short"
    for pattern in WHISPER_HALLUCINATION_PATTERNS:
        if pattern in text:
            return "suspect_hallucination"
    return "ok"


def _tag_categories(text):
    matches = {cat: [] for cat in CATEGORY_WORDS}
    for cat, words in CATEGORY_WORDS.items():
        for w in words:
            if w in text:
                matches[cat].append(w)
    return matches


def get_risk_result(total_score):
    if total_score >= 16:
        return {"risk_level": "low", "suggestion": "本週語言表達狀況良好，內容具有一定完整性。建議持續維持日常對話、社交互動與規律生活。本結果僅供語言表達與健康趨勢追蹤參考，不能作為醫療診斷依據。"}
    elif total_score >= 11:
        return {"risk_level": "medium", "suggestion": "本週語言表達部分項目較不完整，建議家屬持續觀察後續紀錄是否出現相同情形。若類似狀況持續發生，可諮詢醫師或相關專業人員。本結果僅供健康趨勢追蹤參考，不能作為醫療診斷依據。"}
    return {"risk_level": "high", "suggestion": "本週描述內容較少或部分語言表達項目較弱，可能也受到錄音長度、環境聲音等因素影響。建議家屬多加關心並持續觀察多次紀錄。本結果僅供健康趨勢追蹤參考，不能作為醫療診斷依據。"}


def analyze_transcription(text):
    text = normalize_text(text)
    content_len = get_content_length(text)
    effective_len = get_content_length(collapse_repetitions(text))
    hesitation_count = sum(text.count(w) for w in ["嗯", "呃", "那個", "想不起來"])

    fluency_score = max(0, min(4, effective_len / 15 - hesitation_count * 0.5))

    cats = _tag_categories(text)
    hit_categories = sum(1 for v in cats.values() if v)
    information_score = min(4, hit_categories * (4 / 6))

    connective_count = sum(text.count(c) for c in CONNECTIVES)
    sentence_score = min(4, 1 + connective_count)

    unique_named = len(set(w for v in cats.values() for w in v))
    naming_score = min(4, unique_named * 0.7)

    core_hit = bool(cats["person"] or cats["event"])
    support_hit = sum(1 for k in ["location", "time", "emotion"] if cats[k])
    semantic_score = min(4, (2 if core_hit else 0) + support_hit * (2 / 3))

    communication_score = round(
        fluency_score * 0.20 + information_score * 0.20 + sentence_score * 0.20
        + naming_score * 0.15 + semantic_score * 0.25, 2
    )

    total_score = round(fluency_score + information_score + sentence_score + naming_score + semantic_score, 2)
    average_score = round(total_score / 5, 2)
    risk = get_risk_result(total_score)

    return {
        "fluency_score": round(fluency_score, 2),
        "information_score": round(information_score, 2),
        "sentence_score": round(sentence_score, 2),
        "naming_score": round(naming_score, 2),
        "semantic_score": round(semantic_score, 2),
        "communication_score": communication_score,
        "total_score": total_score,
        "average_score": average_score,
        "risk_level": risk["risk_level"],
        "ai_feedback": risk["suggestion"],
    }