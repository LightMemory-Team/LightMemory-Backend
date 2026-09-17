"""菜市場找路題庫（靜態、唯讀）。

target 道具與干擾物道具都固定寫在 games/market_route/data/items.json，
之後美術/企劃要換題庫內容時直接改這個 JSON 檔即可，不用動程式碼。
"""

import json
from pathlib import Path

ITEMS_FILE = Path(__file__).resolve().parent / "data" / "items.json"


def load_items():
    """讀取 target 道具清單，回傳 [{"item": "鯛魚"}, ...]。"""
    with open(ITEMS_FILE, encoding="utf-8") as f:
        return json.load(f)["items"]


def load_distractor_item():
    """讀取干擾物道具名稱（固定一種，例如「魚骨頭」）。"""
    with open(ITEMS_FILE, encoding="utf-8") as f:
        return json.load(f)["distractor_item"]
