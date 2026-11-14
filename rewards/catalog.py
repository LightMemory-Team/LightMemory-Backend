"""成就定義（第一版共 25 個，「計數＋門檻」型）。

寫死在程式碼常數，不進資料庫（跟 games/catalog.py 同樣做法）。
要新增或調整成就，只要改這個檔案，不需要 migration。

每個成就的欄位：
    code        唯一代碼，也是 icon 欄位的值（第一版所有成就共用同一組勳章圖案）
    title       成就名稱
    description 解鎖條件說明（遊戲名稱一律用 App 內正式名稱）
    category    exploration（探索）／training（訓練）／milestone（里程碑）
    type        怎麼算進度，對應 rewards/services.py 裡的 _progress()
    target      門檻
    game        只有跟單一遊戲有關的成就才有
點數依 category 決定：探索 10、訓練 20、里程碑 30（一次性，不計入每日上限）。
"""

CATEGORY_ORDER = ["exploration", "training", "milestone"]
CATEGORY_LABELS = {
    "exploration": "探索類",
    "training": "訓練類",
    "milestone": "里程碑類",
}
CATEGORY_POINTS = {"exploration": 10, "training": 20, "milestone": 30}

# 5 款遊戲的 App 內正式名稱（game_id → 名稱）
GAME_NAMES = {
    "market_route": "來去菜市場",
    "memory_recall": "記憶配對",
    "market_sort": "整理菜籃",
    "fridge_check": "冰箱清點",
    "market_shopping": "市場買菜",
}
GAME_IDS = list(GAME_NAMES)


def _a(code, title, description, category, type_, target=1, game=None):
    return {
        "code": code,
        "title": title,
        "description": description,
        "category": category,
        "type": type_,
        "target": target,
        "game": game,
        "points": CATEGORY_POINTS[category],
        "icon": code,
    }


ACHIEVEMENTS = [
    # ── 探索類（每個 10 點）──────────────────────────
    _a("first_market_route", "初次上市場", f"第一次完成「{GAME_NAMES['market_route']}」",
       "exploration", "game_count", 1, "market_route"),
    _a("first_memory_recall", "記憶初體驗", f"第一次完成「{GAME_NAMES['memory_recall']}」",
       "exploration", "game_count", 1, "memory_recall"),
    _a("first_market_sort", "整理初登場", f"第一次完成「{GAME_NAMES['market_sort']}」",
       "exploration", "game_count", 1, "market_sort"),
    _a("first_fridge_check", "冰箱小管家", f"第一次完成「{GAME_NAMES['fridge_check']}」",
       "exploration", "game_count", 1, "fridge_check"),
    _a("first_market_shopping", "第一次買菜", f"第一次完成「{GAME_NAMES['market_shopping']}」",
       "exploration", "game_count", 1, "market_shopping"),
    _a("first_diary", "說說我的故事", "完成第一篇聲影日記",
       "exploration", "diary_count", 1),
    _a("first_all_tasks", "今日目標達成", "第一次把今日任務全部完成",
       "exploration", "all_tasks_days", 1),
    _a("first_weekly_report", "回頭看看", "第一次打開上週回顧",
       "exploration", "weekly_report", 1),
    _a("first_dashboard", "認識自己", "第一次查看儀表板",
       "exploration", "event", 1),
    _a("first_share", "樂於分享", "第一次分享日記到動態牆",
       "exploration", "shared_post", 1),
    # ── 訓練類（每個 20 點）──────────────────────────
    _a("week_all_games", "五感全開", "同一週內 5 款遊戲都玩過",
       "training", "week_games", 5),
    _a("day_three_games", "多元練習", "同一天玩 3 款不同的遊戲",
       "training", "day_games", 3),
    _a("all_tasks_7", "每日小目標", "累積 7 天把今日任務全部完成",
       "training", "all_tasks_days", 7),
    # ── 里程碑類（每個 30 點）────────────────────────
    _a("play30_market_route", "市場尋寶家", f"「{GAME_NAMES['market_route']}」累積 30 場",
       "milestone", "game_count", 30, "market_route"),
    _a("play30_memory_recall", "記憶高手", f"「{GAME_NAMES['memory_recall']}」累積 30 場",
       "milestone", "game_count", 30, "memory_recall"),
    _a("play30_market_sort", "收納專家", f"「{GAME_NAMES['market_sort']}」累積 30 場",
       "milestone", "game_count", 30, "market_sort"),
    _a("play30_fridge_check", "冰箱總管", f"「{GAME_NAMES['fridge_check']}」累積 30 場",
       "milestone", "game_count", 30, "fridge_check"),
    _a("play30_market_shopping", "算盤達人", f"「{GAME_NAMES['market_shopping']}」累積 30 場",
       "milestone", "game_count", 30, "market_shopping"),
    _a("diary_10", "日記滿十篇", "聲影日記累積 10 篇",
       "milestone", "diary_count", 10),
    _a("games_100", "菜市場常客", "遊戲總共累積 100 場",
       "milestone", "total_games", 100),
    _a("radar_all_unlocked", "六項全能", "雷達圖六個維度全部解鎖",
       "milestone", "radar_unlocked", 6),
    _a("all_tasks_30", "持之以恆", "累積 30 天把今日任務全部完成",
       "milestone", "all_tasks_days", 30),
    _a("active_30", "一路相伴", "累積使用 30 天",
       "milestone", "active_days", 30),
    _a("active_90", "三個月的陪伴", "累積使用 90 天",
       "milestone", "active_days", 90),
    _a("points_1000", "點數小富翁", "點數累積 1,000 點",
       "milestone", "points_total", 1000),
]

ACHIEVEMENTS_BY_CODE = {a["code"]: a for a in ACHIEVEMENTS}

# 沒有資料表可以回頭查的成就，只能靠事件直接解鎖：事件名稱 → 成就 code
EVENT_ACHIEVEMENTS = {"dashboard_viewed": ["first_dashboard"]}
