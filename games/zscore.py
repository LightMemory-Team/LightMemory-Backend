"""跨遊戲共用的 z-score 計算工具。

純函式：輸入「這一場」與「歷史場次」的各階段指標，回傳一個維度分數，
不碰資料庫。規則詳見 Google 文件〈菜市場找路 Z-score 設計〉：

1. 每個階段各算幾個原始指標（由各遊戲自己定義，例如正確率、反應時間）
2. 每個指標跟「同一階段」的歷史分布比，算 z-score；越低越好的指標要反向
3. 階段內加權平均 → 階段分數
4. 依這場最高到達的階段，跨階段加權 → 維度分數

冷啟動：個人歷史不滿 MIN_HISTORY_SESSIONS 場時，先借用全體使用者的
歷史當比較基準；全體也不夠時回傳 None（前端顯示「資料不足」，不給假分數）。
"""

import statistics

STAGE_ORDER = ["basic", "intermediate", "advanced"]

MIN_HISTORY_SESSIONS = 3

# 依這場「最高到達的階段」決定各階段權重，越高階越能反映能力上限
STAGE_WEIGHTS_BY_HIGHEST_STAGE = {
    "basic": {"basic": 1.0},
    "intermediate": {"basic": 0.3, "intermediate": 0.7},
    "advanced": {"basic": 0.2, "intermediate": 0.3, "advanced": 0.5},
}


def compute_baseline(values):
    """算歷史分布的 (平均, 標準差)。

    樣本數不足 MIN_HISTORY_SESSIONS，或標準差為 0（每場都一樣，無法相除）
    時回傳 None。
    """
    values = [v for v in values if v is not None]
    if len(values) < MIN_HISTORY_SESSIONS:
        return None
    std = statistics.stdev(values)
    if std == 0:
        return None
    return statistics.mean(values), std


def choose_baseline(personal_values, population_values):
    """冷啟動：個人歷史算得出基準就用個人的，否則改用全體使用者的。"""
    return compute_baseline(personal_values) or compute_baseline(population_values)


def to_z_score(value, baseline, *, lower_is_better=False):
    """z = (這次的值 - 歷史平均) / 歷史標準差。

    lower_is_better=True（例如反應時間）會乘 -1，讓所有 z 都是「越高越好」。
    """
    if value is None or baseline is None:
        return None
    mean, std = baseline
    z = (value - mean) / std
    return -z if lower_is_better else z


def weighted_average(scores_and_weights):
    """加權平均，跳過 None（無資料）的項目，剩下的權重重新等比例分配。

    全部都是 None 時回傳 None。
    """
    pairs = [
        (score, weight) for score, weight in scores_and_weights if score is not None
    ]
    if not pairs:
        return None
    total_weight = sum(weight for _, weight in pairs)
    return sum(score * weight for score, weight in pairs) / total_weight


def calculate_dimension_z_score(
    current_metrics, personal_history, population_history, metric_rules
):
    """算出一場遊戲的維度 z-score。

    current_metrics: 這一場的各階段指標，只放有玩到的階段，例如
        {"basic": {"accuracy": 0.9, "avg_response_time_ms": 800}}
    personal_history / population_history: 歷史場次清單，每場格式同
        current_metrics（不含這一場）
    metric_rules: 各指標的 (權重, 是否越低越好)，例如
        {"accuracy": (0.4, False), "avg_response_time_ms": (0.3, True)}
    """
    if not current_metrics:
        return None

    highest_stage = max(current_metrics, key=STAGE_ORDER.index)
    stage_weights = STAGE_WEIGHTS_BY_HIGHEST_STAGE[highest_stage]

    stage_scores = []
    for stage, metrics in current_metrics.items():
        z_scores = []
        for name, (weight, lower_is_better) in metric_rules.items():
            baseline = choose_baseline(
                [h[stage][name] for h in personal_history if stage in h],
                [h[stage][name] for h in population_history if stage in h],
            )
            z = to_z_score(metrics[name], baseline, lower_is_better=lower_is_better)
            z_scores.append((z, weight))
        stage_scores.append((weighted_average(z_scores), stage_weights[stage]))

    return weighted_average(stage_scores)
