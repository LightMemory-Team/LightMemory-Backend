"""煮菜過程（memory_recall）題庫（靜態、唯讀）。

三階段物品庫固定寫在 games/memory_recall/data/items.json，之後美術/企劃要
換題庫內容（尤其是高階的分組）時直接改這個 JSON 檔即可，不用動程式碼。
"""

import json
from pathlib import Path

ITEMS_FILE = Path(__file__).resolve().parent / "data" / "items.json"


def _load():
    with open(ITEMS_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_items(stage):
    """回傳 basic/intermediate 階段的物品清單，例如 [{"item": "馬鈴薯"}, ...]。"""
    return _load()[stage]


def load_advanced_groups():
    """回傳 advanced 階段的分組清單，例如 [{"group": "馬鈴薯組", "items": [...]}]。"""
    return _load()["advanced"]
