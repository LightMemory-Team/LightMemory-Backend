"""目前 App 裡有哪些遊戲，供首頁遊戲卡片列表使用。

寫死在程式碼常數，不進資料庫：理由跟 market_shopping/constants.py 的
FOODS、market_route/views.py 的 STAGE_EXPOSURE_RANGE 一樣——這些是不常
變動的設定資料，不是玩家遊玩過程中產生的動態資料，改版直接改程式碼、
走 code review 和 git 紀錄即可，不需要額外的資料庫 migration 或後台
管理介面。

id 對應各遊戲共用 session 儲存時使用的 game_type（見 session_service.py）。
"""

GAMES = [
    {
        "id": "market_route",
        "title": "菜市場找路",
        "is_developed": True,
    },
    {
        "id": "market_shopping",
        "title": "市場買菜",
        "is_developed": True,
    },
    {
        "id": "market_sort",
        "title": "整理菜籃遊戲",
        "is_developed": True,
    },
    {
        "id": "memory_recall",
        "title": "煮菜過程",
        "is_developed": True,
    },
]
