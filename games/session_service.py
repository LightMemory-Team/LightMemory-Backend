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


# demo 帳號的種子場次（dashboard 的 seed_demo 指令建立）的 client_session_id 前綴；
# 這些場次不是真人玩的，不能拿來當全體基準
SEED_CLIENT_SESSION_PREFIX = "seed-"


def _get_session_or_raise(game_type, session_id):
    session = _lookup(game_type, session_id)
    if session is None:
        raise SessionNotFound(session_id)
    return session


def _finished_sessions_before(session):
    """比 session 更早結束的已結束場次（不含這場本身、不含熟悉場）。

    熟悉場（is_pretest=True，每位使用者每款遊戲的第一場，還不熟所以分數偏低）
    不進任何歷史。只取比這場更早結束的場次（這場還沒結束就取全部已結束場次），
    所以不管 dashboard 什麼時候來算，同一場的結果都一樣。
    """
    previous_sessions = GameSession.objects.filter(
        game=session.game, status="finished", is_pretest=False
    ).exclude(pk=session.pk)
    if session.finished_at is not None:
        previous_sessions = previous_sessions.filter(
            finished_at__lt=session.finished_at
        )
    return previous_sessions


def _previous_finished_sessions(game_type, session_id, same_user):
    """「這場之前」已結束的場次（不含這場）。

    same_user=True 只取同一位使用者；False 取全體使用者（含本人）。
    篩選規則見 _finished_sessions_before。找不到 session 會拋出 SessionNotFound。
    """
    session = _get_session_or_raise(game_type, session_id)
    previous_sessions = _finished_sessions_before(session)
    if same_user:
        previous_sessions = previous_sessions.filter(user_id=session.user_id)
    return previous_sessions


def _other_users_previous_sessions(game_type, session_id):
    """全體基準用：「這場之前」其他使用者的已結束場次。

    在 _finished_sessions_before 之外，再排除：
    - 本人（本人的場次是個人歷史，不重複算進全體）
    - is_staff 使用者（測試帳號）
    - demo 種子場次（client_session_id 以 SEED_CLIENT_SESSION_PREFIX 開頭）
    """
    session = _get_session_or_raise(game_type, session_id)
    return (
        _finished_sessions_before(session)
        .exclude(user_id=session.user_id)
        .filter(user__is_staff=False)
        .exclude(client_session_id__startswith=SEED_CLIENT_SESSION_PREFIX)
    )


def _step_records_by_session(sessions):
    """一次查出 sessions 所有的作答紀錄，依場次分組：{session_id: [紀錄, ...]}。

    一次查完再分組，避免每場各查一次資料庫。沒有作答紀錄的場次不會出現。
    """
    records_by_session = {}
    step_logs = (
        GameStepLog.objects.filter(session__in=sessions)
        .order_by("session_id", "step_number")
        .values("session_id", "step_number", "is_correct", "response_time_ms", "detail")
    )
    for log in step_logs:
        session_key = log.pop("session_id")
        records_by_session.setdefault(session_key, []).append(log)
    return records_by_session


def list_previous_results(game_type, session_id, *, same_user=True):
    """列出「這場之前」已結束場次的結算結果（result），給 z-score 當歷史比較基準用。

    給沒有逐題作答紀錄、或直接用結算指標算 z 的遊戲（整理菜籃、冰箱檢查、
    市場買菜）。回傳 list，每個元素是一場的 result dict，依結束時間排序。
    篩選規則同 list_previous_step_records。
    """
    results = (
        _previous_finished_sessions(game_type, session_id, same_user)
        .order_by("finished_at")
        .values_list("result", flat=True)
    )
    return [result for result in results if result]


def list_previous_step_records(game_type, session_id, *, same_user=True):
    """列出「這場之前」已結束場次的作答紀錄，給 z-score 當歷史比較基準用。

    回傳 list，每個元素是一場的 step_records（格式同 _to_dict 的
    step_records）。篩選規則見 _previous_finished_sessions。
    """
    previous_sessions = _previous_finished_sessions(game_type, session_id, same_user)
    return list(_step_records_by_session(previous_sessions).values())


def list_previous_results_by_user(game_type, session_id):
    """全體基準用：其他使用者「這場之前」的結算結果，依使用者分組。

    回傳 {user_id: [result, ...]}（每人的 result 依結束時間排序），給
    games/zscore.py 的 pooled_population_baseline 算「個人內變異」用。
    篩選規則見 _other_users_previous_sessions。
    """
    rows = (
        _other_users_previous_sessions(game_type, session_id)
        .order_by("finished_at")
        .values_list("user_id", "result")
    )
    results_by_user = {}
    for user_id, result in rows:
        if result:
            results_by_user.setdefault(user_id, []).append(result)
    return results_by_user


def list_previous_step_records_by_user(game_type, session_id):
    """全體基準用：其他使用者「這場之前」的作答紀錄，依使用者分組。

    回傳 {user_id: [step_records, ...]}，每個 step_records 是一場的作答紀錄
    （格式同 list_previous_step_records）。篩選規則同 list_previous_results_by_user。
    """
    sessions = _other_users_previous_sessions(game_type, session_id)
    owners = dict(sessions.values_list("pk", "user_id"))
    records_by_user = {}
    for session_pk, records in _step_records_by_session(sessions).items():
        records_by_user.setdefault(owners[session_pk], []).append(records)
    return records_by_user
