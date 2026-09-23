"""三款遊戲共用的 session 狀態儲存（暫時用 JSON 檔案，之後會換成資料庫）。

設計目的：把「怎麼存資料」跟「遊戲邏輯」分開。各遊戲的 views.py 只呼叫這裡
的函式，不直接碰檔案或 JSON。之後換成真正的資料庫時，只需要重寫這個檔案
內部的實作（改成用 Django ORM 讀寫），各遊戲的 views.py 完全不用改。

共通欄位（每個遊戲都有）：
    session_id, game_type, status, question_number, current_question,
    step_records, result
遊戲專屬欄位（例如 market_route 的 current_stage、correct_streak）一律放在
`state`（一個 dict）裡，各遊戲自己決定要放什麼、怎麼讀寫。

一個 session 一個 JSON 檔案（games/data/sessions/<game_type>/<id>.json），
不同遊戲、不同 session 互不干擾；換成資料庫後，一個 session 自然對應一筆
GameSession row，`game_type` 會變成該筆資料的一個欄位。

這是單一開發者本機測試情境，不做檔案鎖（file locking）：
- 正常遊戲流程本來就是一支 API 打完才打下一支，不會同時併發寫同一個 session
- 加鎖對一個即將被資料庫取代的暫時方案來說是過度工程
唯一做的保護是寫檔用「先寫暫存檔、再原子性換名」，避免寫到一半當機造成檔案損毀。
"""

import json
import os
from pathlib import Path

from django.conf import settings

SESSION_ROOT_DIR = Path(
    getattr(
        settings,
        "GAME_SESSION_STORE_DIR",
        Path(__file__).resolve().parent / "data" / "sessions",
    )
)


class SessionNotFound(Exception):
    """找不到指定的 session_id 時拋出。"""


def _session_dir(game_type):
    return SESSION_ROOT_DIR / game_type


def _session_path(game_type, session_id):
    return _session_dir(game_type) / f"{session_id}.json"


def _read(game_type, session_id):
    path = _session_path(game_type, session_id)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(game_type, session_id, data):
    """寫檔：先寫暫存檔，再原子性換名，避免寫到一半當機造成檔案損毀。"""
    session_dir = _session_dir(game_type)
    session_dir.mkdir(parents=True, exist_ok=True)
    path = _session_path(game_type, session_id)
    tmp_path = path.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _next_session_id(game_type):
    """用現有檔案數量 + 1 當作簡易流水號（僅供暫時的 JSON 儲存使用）。"""
    session_dir = _session_dir(game_type)
    session_dir.mkdir(parents=True, exist_ok=True)
    existing_ids = [int(p.stem) for p in session_dir.glob("*.json") if p.stem.isdigit()]
    return max(existing_ids, default=0) + 1


def create_session(game_type, initial_state=None):
    """建立新 session，寫入初始狀態，回傳完整 session 資料。

    initial_state：該遊戲專屬的初始欄位（例如 market_route 的 current_stage、
    exposure_time_ms），統一放進 state 裡，共用模組不理解其內容。

    之後換 DB：對應 GameSession.objects.create(...)，session_id 改由
    資料庫自動產生的主鍵擔任。
    """
    session_id = _next_session_id(game_type)
    session = {
        "session_id": session_id,
        "game_type": game_type,
        "status": "in_progress",
        "question_number": 0,
        "current_question": None,
        "step_records": [],
        "result": None,
        "state": initial_state or {},
    }
    _write(game_type, session_id, session)
    return session


def get_session(game_type, session_id):
    """讀取單一 session 狀態；找不到回傳 None。

    之後換 DB：對應 GameSession.objects.filter(id=session_id).first()。
    """
    return _read(game_type, session_id)


def get_or_create_session(game_type, session_id, initial_state=None):
    """依指定的 session_id 讀取 session；不存在就建立一筆新的。

    跟 create_session 不同：session_id 由呼叫端指定（例如前端自己產生、
    後端不需要也不會另外編號），不是自動流水號。用於「client 端已經有
    session_id，第一次送資料時才需要建立紀錄」的情境（例如 market_sort）。

    回傳 (session, created)，created 是 bool，告訴呼叫端這是不是剛建立的。

    之後換 DB：對應 GameSession.objects.get_or_create(id=session_id, defaults=...)。
    """
    session = _read(game_type, session_id)
    if session is not None:
        return session, False

    session = {
        "session_id": session_id,
        "game_type": game_type,
        "status": "in_progress",
        "question_number": 0,
        "current_question": None,
        "step_records": [],
        "result": None,
        "state": initial_state or {},
    }
    _write(game_type, session_id, session)
    return session, True


def list_sessions(game_type):
    """列出某個遊戲類型底下所有 session 的完整內容（未排序、未過濾）。

    用於需要跨場次查詢的情境（例如算歷史最高分、最近成績趨勢），一般的
    單場遊戲流程不需要用到這個函式。

    之後換 DB：對應 GameSession.objects.filter(...)，可以直接在資料庫層
    做篩選、排序，效能會比現在「讀出全部再用 Python 篩選」好很多。
    """
    session_dir = _session_dir(game_type)
    if not session_dir.exists():
        return []
    sessions = []
    for path in session_dir.glob("*.json"):
        with open(path, encoding="utf-8") as f:
            sessions.append(json.load(f))
    return sessions


def update_session(game_type, session_id, state=None, **fields):
    """讀取 session、合併指定欄位、寫回，回傳更新後的完整 session。

    state（如果有給）會用來局部更新 session["state"]，其餘遊戲共通欄位
    （例如 question_number）用 **fields 更新。

    找不到 session 會拋出 SessionNotFound。
    之後換 DB：對應「取出 instance、逐一設定屬性、呼叫 .save()」。
    """
    session = _read(game_type, session_id)
    if session is None:
        raise SessionNotFound(session_id)
    session.update(fields)
    if state:
        session["state"].update(state)
    _write(game_type, session_id, session)
    return session


def save_step(game_type, session_id, step_record):
    """附加一筆作答嘗試（attempt）紀錄到 step_records。

    之後換 DB：對應 GameStepLog.objects.create(...)。
    """
    session = _read(game_type, session_id)
    if session is None:
        raise SessionNotFound(session_id)
    session["step_records"].append(step_record)
    _write(game_type, session_id, session)
    return session


def set_current_question(game_type, session_id, question):
    """update_session 的簡化包裝，只更新這一題的題目內容。"""
    return update_session(game_type, session_id, current_question=question)


def finish_session(game_type, session_id, result):
    """標記 session 已結束，存入彙總結果。

    之後換 DB：對應把彙總欄位寫進 GameSession 並設定 end_time。
    """
    return update_session(game_type, session_id, status="finished", result=result)
