"""給長者看的文字的「用語檢查」：AI 寫的句子不可以有醫療宣稱或負面字眼。

專案定位是「輔助維持認知活躍度」，不是醫療：不能說診斷、治療、療效，
也不能說「延緩失智」「降低失智風險」。AI 回來的句子（週報總結、首頁問候語、
日記追問與回應…）都先用這裡檢查一次，出現禁用詞就改用固定句型。

注意：
- 只列「多個字的詞」。單一個字（例如「病」「症」「z」）會誤傷正常句子，
  例如「生病了要多休息」「Zoo」，所以不列。
- 這只檢查 AI 產生的句子，不檢查長者自己說的內容。
"""

# 不能出現在給長者看的句子裡
BANNED_WORDS = [
    # 疾病名稱
    "失智",
    "痴呆",
    "癡呆",
    "阿茲海默",
    "認知障礙",
    "輕度認知",
    "認知功能",
    # 醫療行為與療效宣稱
    "診斷",
    "確診",
    "治療",
    "療效",
    "療程",
    "疾病",
    "病情",
    "病症",
    "症狀",
    "延緩",
    "風險",
    # 負面字眼
    "退步",
    "變差",
    "退化",
    "衰退",
    "惡化",
    "記憶力下降",
    # 專有名詞（長者看不懂，也像在評分）
    "分數",
    "z 分數",
    "z分數",
    "Z 分數",
    "Z分數",
    "z-score",
    "標準差",
    "百分位",
    "認知彈性",
    # 語言是寫日記練的，不是遊戲
    "玩語言",
]


def find_banned_word(text):
    """回傳 text 裡第一個禁用詞；沒有就回傳 None。text 不是字串也回傳 None。"""
    if not isinstance(text, str):
        return None
    lowered = text.lower()
    for word in BANNED_WORDS:
        if word.lower() in lowered:
            return word
    return None


def contains_banned_word(text):
    return find_banned_word(text) is not None
