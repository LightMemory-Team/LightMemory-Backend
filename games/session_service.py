"""三款遊戲共用的 session 狀態儲存（使用關聯式資料庫實作）。

依據規格書第四節與第五節設計，作為 GameSession / GameStepLog 之 Facade。
對外維持 8 個函式簽名與回傳形狀不變（加上 is_pretest、avg_response_time_ms 等可選參數），
內部改為透過 Django ORM 操作 GameSession 與 GameStepLog。

共通欄位（每個遊戲都有）：
    session_id, game_type, status, question_number, current_question,
    step_records, result
擴充共通欄位：
    is_pretest, avg_response_time_ms
遊戲專屬欄位一律放在 `state`（一個 dict）裡，各遊戲自己決定要放什麼、怎麼讀寫。
"""

from django.core.exceptions import ValidationError
from django.utils import timezone

from games.models import Game, GameCategory, GameSession, GameStepLog


class SessionNotFound(Exception):
    """找不到指定的 session_id 時拋出。"""


def _to_dict(session: GameSession) -> dict:
    """將 GameSession ORM instance 轉換為外部呼叫者預期的 dict 結構。"""
    return {
        "session_id": session.client_session_id or str(session.id),
        "game_type": session.game.code,
        "status": session.status,
        "question_number": session.question_number,
        "current_question": session.current_question,
        "step_records": list(
            session.step_logs.values("step_number", "is_correct", "detail")
        ),
        "result": session.result,
        "state": session.state,
        "is_pretest": session.is_pretest,  # 框架 8 欄位之外的擴充
        "avg_response_time_ms": session.avg_response_time_ms,  # 框架 8 欄位之外的擴充
    }


def _get_game(game_type):
    try:
        return Game.objects.get(code=game_type)
    except Game.DoesNotExist:
        category, _ = GameCategory.objects.get_or_create(
            category_name="未分類", defaults={"category_description": ""}
        )
        game, _ = Game.objects.get_or_create(
            code=game_type,
            defaults={"game_name": game_type, "game_category": category},
        )
        return game


def create_session(game_type, initial_state=None, is_pretest=False):
    """建立新 session，寫入初始狀態，回傳完整 session 資料。

    initial_state：該遊戲專屬的初始欄位，統一放進 state 裡。
    is_pretest：是否為前測 session（可選，預設為 False）。
    """
    game = _get_game(game_type)
    session = GameSession.objects.create(
        game=game,
        state=initial_state or {},
        is_pretest=is_pretest,
    )
    return _to_dict(session)


def get_or_create_session(game_type, session_id, initial_state=None, is_pretest=False):
    """依指定的 session_id 讀取 session；不存在就建立一筆新的。

    回傳 (session_dict, created)，created 是 bool，告訴呼叫端這是不是剛建立的。
    """
    game = _get_game(game_type)
    session, created = GameSession.objects.get_or_create(
        game=game,
        client_session_id=str(session_id),
        defaults={"state": initial_state or {}, "is_pretest": is_pretest},
    )
    return _to_dict(session), created


def get_session(game_type, session_id):
    """讀取單一 session 狀態；找不到回傳 None。"""
    session = _lookup(game_type, session_id)
    return _to_dict(session) if session else None


def update_session(game_type, session_id, state=None, **fields):
    """讀取 session、合併指定欄位、寫回，回傳更新後的完整 session。

    state（如果有給）會用來局部更新 session.state，其餘共通欄位用 **fields 更新。
    找不到 session 會拋出 SessionNotFound。
    """
    session = _lookup(game_type, session_id)
    if session is None:
        raise SessionNotFound(session_id)
    if state:
        session.state = {**session.state, **state}
    for key, value in fields.items():
        setattr(session, key, value)
    session.save()
    return _to_dict(session)


def save_step(game_type, session_id, step_record):
    """附加一筆作答嘗試（attempt）紀錄到 GameStepLog。"""
    session = _lookup(game_type, session_id)
    if session is None:
        raise SessionNotFound(session_id)
    GameStepLog.objects.create(
        session=session,
        step_number=session.step_logs.count() + 1,
        is_correct=step_record.get("is_correct"),
        response_time_ms=step_record.get("response_time_ms"),
        detail=step_record,
    )
    return _to_dict(session)


def set_current_question(game_type, session_id, question):
    """update_session 的簡化包裝，只更新這一題的題目內容。"""
    return update_session(game_type, session_id, current_question=question)


def finish_session(game_type, session_id, result, avg_response_time_ms=None):
    """標記 session 已結束，存入彙總結果與平均反應時間。"""
    session = _lookup(game_type, session_id)
    if session is None:
        raise SessionNotFound(session_id)
    session.status = "finished"
    session.result = result
    session.avg_response_time_ms = avg_response_time_ms
    session.finished_at = timezone.now()
    session.save()
    return _to_dict(session)


def list_sessions(game_type):
    """列出某個遊戲類型底下所有 session 的完整內容（未排序、未過濾）。"""
    game = _get_game(game_type)
    return [_to_dict(s) for s in GameSession.objects.filter(game=game)]


def _lookup(game_type, session_id):
    """依 game_type 與 session_id 查詢 GameSession。

    先嘗試以 UUID 查詢主鍵 id，若格式不符或找不到，再以 client_session_id 查詢。
    """
    game = _get_game(game_type)
    try:
        return GameSession.objects.get(game=game, id=session_id)
    except (GameSession.DoesNotExist, ValueError, ValidationError):
        return GameSession.objects.filter(
            game=game,
            client_session_id=str(session_id),
        ).first()
