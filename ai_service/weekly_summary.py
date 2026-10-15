"""週報表「機器人的一句話總結」：交給 AI 寫，失敗就用固定句型。

只把「正向的事實」交給 AI（多玩的天數、進步最多的能力），比上週少、
沒有進步的事不放進去，AI 就沒有材料講出負面的話。AI 回來的句子還會
再檢查一次：太長或出現禁用詞（醫療、專有名詞、負面字眼）就改用固定句型。
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

MAX_SUMMARY_LENGTH = 40

# 不能出現在給長者看的句子裡：醫療療效宣稱、專有名詞、負面字眼
BANNED_WORDS = [
    "失智",
    "診斷",
    "治療",
    "疾病",
    "退步",
    "變差",
    "分數",
    "z",
    "Z",
    "標準差",
    "百分位",
    "認知彈性",
]

SYSTEM_PROMPT = (
    "你是陪伴長輩的溫暖小幫手。根據提供的本週事實，用繁體中文寫一句"
    "30 字以內的鼓勵總結。規則：只能使用提供的事實，不可編造數字；"
    "語氣正向；不可出現負面字眼；不可使用專有名詞（例如分數、z 分數、"
    "標準差、百分位、認知彈性）；不可提到醫療、診斷、失智或療效。"
    "只回這一句話。"
)


def build_positive_facts(active_day_count, previous_active_day_count, abilities):
    """整理出要交給 AI 的正向事實。

    abilities 是週報的 abilities（build_abilities 的回傳）；
    「進步最多」是 trend 為 up 的能力中，本週比上週多最多分的那一個。
    """
    facts = {"active_day_count": active_day_count}

    more_days = active_day_count - previous_active_day_count
    if more_days > 0:
        facts["more_days"] = more_days

    improved = [d for d in abilities["dimensions"] if d["trend"] == "up"]
    if improved:
        most = max(improved, key=lambda d: d["this_week"] - d["last_week"])
        facts["most_improved"] = most["label"]
    return facts


def build_fallback_summary(facts):
    """固定句型：AI 失敗或不需要 AI 時使用，例如
    「這週你玩了 4 天，比上週多 1 天！進步最多的是工作記憶」。
    """
    if facts["active_day_count"] == 0:
        return "好久不見，下週一起來動動腦吧！"

    summary = f"這週你玩了 {facts['active_day_count']} 天"
    if "more_days" in facts:
        summary += f"，比上週多 {facts['more_days']} 天！"
    elif "most_improved" not in facts:
        return summary + "，繼續保持！"
    else:
        summary += "！"
    if "most_improved" in facts:
        summary += f"進步最多的是{facts['most_improved']}"
    return summary


def _facts_to_text(facts):
    lines = [f"本週有活動的天數：{facts['active_day_count']} 天"]
    if "more_days" in facts:
        lines.append(f"比上週多玩了 {facts['more_days']} 天")
    if "most_improved" in facts:
        lines.append(f"進步最多的能力：{facts['most_improved']}")
    return "\n".join(lines)


def _client():
    from openai import OpenAI

    return OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)


def _is_acceptable(summary):
    return (
        bool(summary)
        and len(summary) <= MAX_SUMMARY_LENGTH
        and not any(word in summary for word in BANNED_WORDS)
    )


def generate_weekly_summary(facts):
    """請 AI 依正向事實寫一句總結；這週沒活動、AI 失敗或句子不合格就用固定句型。"""
    fallback = build_fallback_summary(facts)
    if facts["active_day_count"] == 0:
        return fallback

    try:
        response = _client().chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _facts_to_text(facts)},
            ],
            max_tokens=80,
        )
        summary = (response.choices[0].message.content or "").strip()
    except Exception:
        logger.warning("週報 AI 總結產生失敗，改用固定句型", exc_info=True)
        return fallback

    if not _is_acceptable(summary):
        logger.warning("週報 AI 總結不合格，改用固定句型：%s", summary)
        return fallback
    return summary
