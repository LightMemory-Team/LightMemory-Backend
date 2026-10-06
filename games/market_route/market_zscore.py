"""菜市場找路（market_route）z-score 模組：儀表板「注意力」維度分數。

規則詳見 Google 文件〈菜市場找路 Z-score 設計〉。不直接用 total_score，
因為難度係數會把「玩到多難」跟「玩得多好」混在一起；改成每個階段各算
3 個指標，跟自己的歷史比（冷啟動借用全體使用者），再加權合成。

算出來的分數之後給 dashboard 用，目前不放進 finish/ 的回傳。
"""

import statistics

from games import session_service
from games.zscore import calculate_dimension_z_score

GAME_TYPE = "market_route"

# 指標名稱: (階段內權重, 是否越低越好)；權重為初始建議值，長者測試後再調整
METRIC_RULES = {
    "accuracy": (0.4, False),
    "avg_response_time_ms": (0.3, True),
    "converged_exposure_ms": (0.3, True),
}


def calculate_stage_metrics(step_records):
    """從一場的作答紀錄算出各階段的 3 個指標，沒玩到的階段不會出現。

    只看每題的第 1 次嘗試，避免「答錯重看」拉低反應時間或墊高正確率。
    step_records 需依 step_number 排序（session_service 回傳的就是）。
    """
    first_attempts_by_stage = {}
    for record in step_records:
        detail = record["detail"]
        if detail["attempt_number"] != 1:
            continue
        first_attempts_by_stage.setdefault(detail["stage"], []).append(record)

    metrics = {}
    for stage, records in first_attempts_by_stage.items():
        correct_count = sum(1 for r in records if r["is_correct"])
        response_times = [
            r["response_time_ms"]
            for r in records
            if not r["detail"]["is_timeout"] and r["response_time_ms"] is not None
        ]
        metrics[stage] = {
            "accuracy": correct_count / len(records),
            "avg_response_time_ms": (
                statistics.mean(response_times) if response_times else None
            ),
            # 該階段最後一題的曝光時間，代表這人在此階段穩定下來的速度
            "converged_exposure_ms": records[-1]["detail"]["exposure_time_ms"],
        }
    return metrics


def calculate_attention_z_score(session_id):
    """算出某一場的注意力 z-score，歷史資料不足時回傳 None。

    只跟「這場之前」結束的場次比，所以同一場不管什麼時候算結果都一樣。
    找不到 session 會拋出 session_service.SessionNotFound。
    """
    session = session_service.get_session(GAME_TYPE, session_id)
    if session is None:
        raise session_service.SessionNotFound(session_id)

    personal_history = [
        calculate_stage_metrics(records)
        for records in session_service.list_previous_step_records(GAME_TYPE, session_id)
    ]
    population_history = [
        calculate_stage_metrics(records)
        for records in session_service.list_previous_step_records(
            GAME_TYPE, session_id, same_user=False
        )
    ]
    return calculate_dimension_z_score(
        calculate_stage_metrics(session["step_records"]),
        personal_history,
        population_history,
        METRIC_RULES,
    )
