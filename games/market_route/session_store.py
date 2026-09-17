"""菜市場找路 session 狀態儲存（暫時用 JSON 檔案，之後會換成資料庫）。

設計目的：把「怎麼存資料」跟「遊戲邏輯」分開。views.py 只呼叫這裡的函式，
不直接碰檔案或 JSON。之後 Issue #37/#36 換成真正的資料庫時，只需要重寫這個
檔案內部的實作（改成用 Django ORM 讀寫），views.py 完全不用改。

一個 session 一個 JSON 檔案（games/market_route/data/sessions/<id>.json），
不同 session 互不干擾；換成資料庫後，一個 session 自然對應一筆
GameSession/MarketRouteSession row。

這是單一開發者本機測試情境，不做檔案鎖（file locking）：
- 正常遊戲流程本來就是一支 API 打完才打下一支，不會同時併發寫同一個 session
- 加鎖對一個即將被資料庫取代的暫時方案來說是過度工程
唯一做的保護是寫檔用「先寫暫存檔、再原子性換名」，避免寫到一半當機造成檔案損毀。
"""

import json
import os
from pathlib import Path

from django.conf import settings

SESSION_DIR = Path(
    getattr(
        settings,
        "MARKET_ROUTE_SESSION_STORE_DIR",
        Path(__file__).resolve().parent / "data" / "sessions",
    )
)

STAGE_EXPOSURE_RANGE = {
    "basic": (2000, 1500),
    "intermediate": (1500, 1000),
    "advanced": (1000, 500),
}


class SessionNotFound(Exception):
    """找不到指定的 session_id 時拋出。"""


def _session_path(session_id):
    return SESSION_DIR / f"{session_id}.json"


def _read(session_id):
    path = _session_path(session_id)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(session_id, data):
    """寫檔：先寫暫存檔，再原子性換名，避免寫到一半當機造成檔案損毀。"""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    path = _session_path(session_id)
    tmp_path = path.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _next_session_id():
    """用現有檔案數量 + 1 當作簡易流水號（僅供暫時的 JSON 儲存使用）。"""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    existing_ids = [int(p.stem) for p in SESSION_DIR.glob("*.json") if p.stem.isdigit()]
    return max(existing_ids, default=0) + 1


def create_session():
    """建立新 session，寫入初始 DDA 狀態，回傳完整 session 資料。

    之後換 DB：對應 GameSession.objects.create(...)，session_id 改由
    資料庫自動產生的主鍵擔任。
    """
    session_id = _next_session_id()
    loose_exposure, _ = STAGE_EXPOSURE_RANGE["basic"]
    session = {
        "session_id": session_id,
        "status": "in_progress",
        "current_stage": "basic",
        "correct_streak": 0,
        "fast_correct_streak": 0,
        "wrong_attempts": 0,
        "exposure_time_ms": loose_exposure,
        "question_number": 0,
        "current_question": None,
        "step_records": [],
        "result": None,
    }
    _write(session_id, session)
    return session


def get_session(session_id):
    """讀取單一 session 狀態；找不到回傳 None。

    之後換 DB：對應 GameSession.objects.filter(id=session_id).first()。
    """
    return _read(session_id)


def update_session(session_id, **fields):
    """讀取 session、合併指定欄位、寫回，回傳更新後的完整 session。

    找不到 session 會拋出 SessionNotFound。
    之後換 DB：對應「取出 instance、逐一設定屬性、呼叫 .save()」。
    """
    session = _read(session_id)
    if session is None:
        raise SessionNotFound(session_id)
    session.update(fields)
    _write(session_id, session)
    return session


def save_step(session_id, step_record):
    """附加一筆作答嘗試（attempt）紀錄到 step_records。

    之後換 DB：對應 MarketRouteStepLog.objects.create(...)。
    """
    session = _read(session_id)
    if session is None:
        raise SessionNotFound(session_id)
    session["step_records"].append(step_record)
    _write(session_id, session)
    return session


def set_current_question(session_id, question):
    """update_session 的簡化包裝，只更新這一題的題目內容。"""
    return update_session(session_id, current_question=question)


def finish_session(session_id, result):
    """標記 session 已結束，存入彙總結果。

    之後換 DB：對應把彙總欄位寫進 MarketRouteSession 並設定 end_time。
    """
    return update_session(session_id, status="finished", result=result)
