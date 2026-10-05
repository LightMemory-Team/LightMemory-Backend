"""三款遊戲共用的 session 狀態儲存（依「遊戲系統共用資料表規格書」第四、五節，
已從暫時的 JSON 檔案換成 Django ORM，透過 GameSession / GameStepLog 存取）。

設計目的：把「怎麼存資料」跟「遊戲邏輯」分開。各遊戲的 views.py 只呼叫這裡
的函式，不直接碰資料庫。8 個函式的名稱沿用 JSON 時期，另新增 user、
is_pretest、avg_response_time_ms 為可選參數。

共通欄位（每個 session 都有，回傳的 dict 都會有這些 key）：
    session_id, game_type, user_id, status, question_number, current_question,
    step_records, result, state, is_pretest, avg_response_time_ms

跟 JSON 時期不同、各遊戲要注意的兩點：
    - session_id 是 UUID 字串（或前端自己產生的 client_session_id），
      不是整數，網址要用 <str:session_id>
    - step_records 每筆的格式是
          {"step_number", "is_correct", "response_time_ms", "detail"}
      呼叫 save_step() 時傳入的整筆原始紀錄放在 detail 裡，
      遊戲專屬欄位（例如 stage、question_number）要從 r["detail"] 讀

game_type 對應到 Game.code（例如 "market_route"）；找不到對應的 Game 時，
會自動在「未分類」分類底下建立一筆，避免因為 seed 資料還沒建好就整個炸掉
（但正式環境還是應該先跑過 games/fixtures/initial_games.json 建好種子資料）。

user 是 GameSession 的必要欄位（外鍵、不可為空），所以建立 session 時一定
要知道是誰在玩，解析順序：
    1. 呼叫端明確傳入的 user 參數（建議所有新代碼都這樣傳）
    2. 找不到就退而求其次，從 initial_state 裡的 "user_id" 找
       （相容目前 market_sort、market_shopping 把 user_id 塞進
       initial_state 的舊寫法，這兩個檔案不用改）
    3. 兩者都沒有就拋出 ValueError，提醒呼叫端要傳 user
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Game, GameCategory, GameSession, GameStepLog


class SessionNotFound(Exception):
    """找不到指定的 session_id 時拋出。"""


def _to_dict(session):
    """將 GameSession ORM instance 轉換為外部呼叫者預期的 dict 結構。"""
    return {
        "session_id": session.client_session_id or str(session.id),
        "game_type": session.game.code,
        # 判斷 session 屬於誰（FORBIDDEN 檢查）用，直接讀外鍵，不依賴各遊戲的 state
        "user_id": session.user_id,
        "status": session.status,
        "question_number": session.question_number,
        "current_question": session.current_question,
        "step_records": list(
            session.step_logs.order_by("step_number").values(
                "step_number", "is_correct", "response_time_ms", "detail"
            )
        ),
        "result": session.result,
        "state": session.state,
        "is_pretest": session.is_pretest,
        "avg_response_time_ms": session.avg_response_time_ms,
    }


def _get_game(game_type):
    """依 code 找 Game；找不到就自動建一筆放在「未分類」分類底下。"""
    try:
        return Game.objects.get(code=game_type)
    except Game.DoesNotExist:
        category, _ = GameCategory.objects.get_or_create(
            category_name="未分類", defaults={"category_description": ""}
        )
        game, _ = Game.objects.get_or_create(
            code=game_type,
            defaults={"name": game_type, "category": category},
        )
        return game


def _resolve_user(user, initial_state):
    if user is not None:
        return user
    user_id = (initial_state or {}).get("user_id")
    if user_id is not None:
        User = get_user_model()
        return User.objects.get(pk=user_id)
    raise ValueError(
        "建立 GameSession 需要知道是誰在玩，請在呼叫 create_session /"
        "get_or_create_session 時傳入 user 參數（或暫時在 initial_state 放 user_id）"
    )


def _lookup(game_type, session_id):
    """依 game_type 與 session_id 查詢 GameSession。

    先嘗試把 session_id 當作主鍵 id（UUID）查詢，格式不符或找不到的話，
    再改用 client_session_id 查詢（前端自己產生、傳給後端的那個 id）。
    """
    game = _get_game(game_type)
    try:
        return GameSession.objects.get(game=game, id=session_id)
    except (GameSession.DoesNotExist, ValueError, ValidationError):
        return GameSession.objects.filter(
            game=game, client_session_id=str(session_id)
        ).first()


def create_session(game_type, initial_state=None, user=None, is_pretest=False):
    """建立新 session，寫入初始狀態，回傳完整 session 資料。

    initial_state：該遊戲專屬的初始欄位（例如 market_route 的 current_stage、
    exposure_time_ms），統一放進 state 裡，共用模組不理解其內容。
    """
    game = _get_game(game_type)
    owner = _resolve_user(user, initial_state)
    session = GameSession.objects.create(
        game=game,
        user=owner,
        state=initial_state or {},
        is_pretest=is_pretest,
    )
    return _to_dict(session)


def get_session(game_type, session_id):
    """讀取單一 session 狀態；找不到回傳 None。"""
    session = _lookup(game_type, session_id)
    return _to_dict(session) if session else None


def get_or_create_session(
    game_type, session_id, initial_state=None, user=None, is_pretest=False
):
    """依指定的 session_id 讀取 session；不存在就建立一筆新的。

    跟 create_session 不同：session_id 由呼叫端指定（例如前端自己產生），
    對應到 GameSession.client_session_id，不是資料庫的主鍵。

    回傳 (session_dict, created)，created 是 bool，告訴呼叫端這是不是剛建立的。
    """
    game = _get_game(game_type)
    try:
        session = GameSession.objects.get(game=game, client_session_id=str(session_id))
        return _to_dict(session), False
    except GameSession.DoesNotExist:
        owner = _resolve_user(user, initial_state)
        session = GameSession.objects.create(
            game=game,
            user=owner,
            client_session_id=str(session_id),
            state=initial_state or {},
            is_pretest=is_pretest,
        )
        return _to_dict(session), True


def list_sessions(game_type):
    """列出某個遊戲類型底下所有 session 的完整內容（未排序、未過濾）。"""
    game = _get_game(game_type)
    return [_to_dict(s) for s in GameSession.objects.filter(game=game)]


def update_session(game_type, session_id, state=None, **fields):
    """讀取 session、合併指定欄位、寫回，回傳更新後的完整 session。

    state（如果有給）會用來局部更新 session.state（合併，不是整個覆蓋），
    其餘遊戲共通欄位（例如 question_number）用 **fields 更新。

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
    """附加一筆作答嘗試（attempt）紀錄，寫進 GameStepLog。"""
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
    """標記 session 已結束，存入彙總結果（與可選的平均反應時間）。"""
    session = _lookup(game_type, session_id)
    if session is None:
        raise SessionNotFound(session_id)
    session.status = "finished"
    session.result = result
    if avg_response_time_ms is not None:
        session.avg_response_time_ms = avg_response_time_ms
    session.finished_at = timezone.now()
    session.save()
    return _to_dict(session)
