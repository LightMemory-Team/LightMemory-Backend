"""煮菜過程（memory_recall）z-score 模組：儀表板「工作記憶」維度分數。

比照菜市場找路的 z-score 設計（Google 文件〈菜市場找路 Z-score 設計〉）：
每個階段各算指標，跟自己的歷史比（冷啟動借用全體使用者），再加權合成。
本遊戲沒有曝光時間，所以每階段只有正確率、平均反應時間兩個指標。

算出來的分數之後給 dashboard 用，目前不放進 finish/ 的回傳。
"""

import statistics

from games import session_service
from games.zscore import calculate_dimension_z_score

GAME_TYPE = "memory_recall"

# 指標名稱: (階段內權重, 是否越低越好)；一律等權重（Dawes, 1979：資料不足以估計
# 權重時，等權重通常不輸精算權重），等長者資料夠了再依因素分析調整
METRIC_RULES = {
    "accuracy": (1.0, False),
    "avg_response_time_ms": (1.0, True),
}


def calculate_stage_metrics(step_records):
    """從一場的作答紀錄算出各階段的正確率、平均反應時間，沒玩到的階段不會出現。

    單輪超時會直接結束遊戲、不會留下作答紀錄，所以這裡不需要另外排除超時。
    """
    records_by_stage = {}
    for record in step_records:
        records_by_stage.setdefault(record["detail"]["stage"], []).append(record)

    metrics = {}
    for stage, records in records_by_stage.items():
        correct_count = sum(1 for r in records if r["is_correct"])
        response_times = [
            r["response_time_ms"] for r in records if r["response_time_ms"] is not None
        ]
        metrics[stage] = {
            "accuracy": correct_count / len(records),
            "avg_response_time_ms": (
                statistics.mean(response_times) if response_times else None
            ),
        }
    return metrics


def calculate_working_memory_z_score(session_id):
    """算出某一場的工作記憶 z-score，前測（熟悉場）或歷史資料不足時回傳 None。

    前測不計分，所以前測那一場本身沒有 z-score，也不會進之後場次的歷史。
    只跟「這場之前」結束的場次比。
    找不到 session 會拋出 session_service.SessionNotFound。
    """
    session = session_service.get_session(GAME_TYPE, session_id)
    if session is None:
        raise session_service.SessionNotFound(session_id)
    if session["is_pretest"] or session["state"].get("is_pretest"):
        return None

    personal_history = [
        calculate_stage_metrics(records)
        for records in session_service.list_previous_step_records(GAME_TYPE, session_id)
    ]
    # 其他使用者的歷史依使用者分組（排除本人、熟悉場、測試帳號、demo 資料）
    population_history = {
        user_id: [calculate_stage_metrics(records) for records in sessions]
        for user_id, sessions in (
            session_service.list_previous_step_records_by_user(
                GAME_TYPE, session_id
            ).items()
        )
    }
    return calculate_dimension_z_score(
        calculate_stage_metrics(session["step_records"]),
        personal_history,
        population_history,
        METRIC_RULES,
    )
