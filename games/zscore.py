"""跨遊戲共用的 z-score 計算工具（五款遊戲與聲影日記都用）。

純函式：輸入「這一場」與「歷史場次」的指標，回傳 z-score，不碰資料庫。
規則詳見 Google 文件〈菜市場找路 Z-score 設計〉：

1. 每個（階段的）原始指標由各遊戲自己定義，寫成 METRIC_RULES：
   {指標: (權重, 是否越低越好)}，例如正確率、反應時間
2. 每個指標跟自己的歷史分布比，算 z-score；越低越好的指標要反向
3. 加權平均 → 分數（metric_z_scores + weighted_metric_z_score）
4. 有分階段的遊戲（菜市場找路、煮菜過程）再依這場最高到達的階段，
   跨階段加權 → 維度分數（calculate_dimension_z_score）

冷啟動：個人歷史不滿 MIN_HISTORY_SESSIONS 場時，先借用全體使用者的
歷史當比較基準；全體也不夠時回傳 None（前端顯示「資料不足」，不給假分數）。
不使用寫死的常模：等測試資料累積夠了，再依真實資料決定。
"""

import statistics

STAGE_ORDER = ["basic", "intermediate", "advanced"]

MIN_HISTORY_SESSIONS = 3

# 收縮估計的強度 k：相當於「先借幾場全體資料」，個人場次越多越偏向個人
# 目前依保守設定為 3，等長者資料累積後，再用 個人內變異 ÷ 個人間變異 估計
PRIOR_STRENGTH = 3

# 每個指標的 z 限制在 ±2，避免單一極端值（例如某題反應特別慢）把整體分數拉爆；
# 每個指標都在 ±2 內，加權平均後的維度分數自然也在 ±2 內
Z_SCORE_CLAMP = 2

# 給長者看的分數範圍，最低 1 分（不出現 0 分）
MIN_DISPLAY_SCORE = 1
MAX_DISPLAY_SCORE = 100

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
    結果限制在 [-Z_SCORE_CLAMP, +Z_SCORE_CLAMP]。
    """
    if value is None or baseline is None:
        return None
    mean, std = baseline
    z = (value - mean) / std
    if lower_is_better:
        z = -z
    return max(-Z_SCORE_CLAMP, min(Z_SCORE_CLAMP, z))


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


def metric_z_scores(
    current_metrics, personal_history, population_history, metric_rules
):
    """每個指標各自跟歷史比，回傳 {指標: z 或 None}。

    current_metrics: 這一場的指標，例如 {"accuracy": 0.9, "avg_response_time_ms": 800}
    personal_history / population_history: 歷史場次清單，每場格式同
        current_metrics（不含這一場）
    metric_rules: 各指標的 (權重, 是否越低越好)，例如
        {"accuracy": (0.4, False), "avg_response_time_ms": (0.3, True)}
    """
    return {
        name: to_z_score(
            current_metrics.get(name),
            choose_baseline(
                [h.get(name) for h in personal_history],
                [h.get(name) for h in population_history],
            ),
            lower_is_better=lower_is_better,
        )
        for name, (_, lower_is_better) in metric_rules.items()
    }


def weighted_metric_z_score(z_by_metric, metric_rules):
    """把 metric_z_scores 的結果依 metric_rules 的權重加權；全部無資料回傳 None。"""
    return weighted_average(
        [(z_by_metric[name], weight) for name, (weight, _) in metric_rules.items()]
    )


def z_score_to_display_score(z_score):
    """把 z-score（±2 內）換算成給長者看的 1～100 分，五款遊戲和週報共用。

    z = -2 → 1、z = 0 → 50、z = +2 → 100；z 為 None（資料不足）回傳 None。
    """
    if z_score is None:
        return None
    score = round(50 + 25 * z_score)
    return max(MIN_DISPLAY_SCORE, min(MAX_DISPLAY_SCORE, score))


def pooled_population_baseline(histories_by_user):
    """全體基準：平均用所有場次，變異數用「個人內」波動的合併值。

    個人參照的 z 需要的是「同一個人每次之間的波動」（個人內），不是「人跟人
    之間的差異」（個人間），後者通常大很多，會把冷啟動期間的 z 壓扁。

    histories_by_user: {user_id: [該使用者各場的值]}
    回傳 (平均, 個人內變異數)；個人內自由度（Σ(場次 − 1)）不足
    MIN_HISTORY_SESSIONS 時回傳 None。
    """
    all_values, sum_sq, dof = [], 0.0, 0
    for values in histories_by_user.values():
        values = [v for v in values if v is not None]
        all_values.extend(values)
        if len(values) >= 2:
            sum_sq += statistics.variance(values) * (len(values) - 1)
            dof += len(values) - 1
    if dof < MIN_HISTORY_SESSIONS or not all_values:
        return None
    return statistics.mean(all_values), sum_sq / dof


def shrunk_baseline(personal_values, population_baseline, k=PRIOR_STRENGTH):
    """收縮基準：個人資料少時偏向全體，越多越偏向個人。回傳 (平均, 標準差)。

    population_baseline 是 pooled_population_baseline 的結果；為 None（全體也
    不夠）時退回 compute_baseline（個人不滿 3 場就是 None）。
    n = 0 時完全用全體；n 越大越接近純個人的平均與標準差。
    """
    if population_baseline is None:
        return compute_baseline(personal_values)
    pop_mean, pop_within_var = population_baseline
    values = [v for v in personal_values if v is not None]
    n = len(values)
    mean = (n * statistics.mean(values) + k * pop_mean) / (n + k) if n else pop_mean
    personal_ss = statistics.variance(values) * (n - 1) if n >= 2 else 0.0
    var = (personal_ss + k * pop_within_var) / (max(n - 1, 0) + k)
    return (mean, var**0.5) if var > 0 else None


def effective_weights(z_by_metric, metric_rules, stage_weight=1.0):
    """這場實際有資料的指標，其有效權重（未正規化）。"""
    return [
        stage_weight * metric_rules[name][0]
        for name, z in z_by_metric.items()
        if z is not None
    ]


def prior_composite_variance(weights):
    """指標互不相關時，合成分數的理論變異數 = Σ(正規化權重²)。

    不需要任何資料就能算，而且是最保守的情況；沒有任何權重時回傳 None。
    """
    total = sum(weights)
    if not total:
        return None
    return sum((w / total) ** 2 for w in weights)


def restandardize(composite, reference_composites, prior_var, k=PRIOR_STRENGTH):
    """第二階段標準化：合成分數 ÷ 收縮後的合成分數標準差，再限制在 ±2。

    指標越多，加權平均後的波動越小；除以合成分數本身的標準差，讓每個維度
    最終的波動都回到 1，與指標數量無關。

    composite: 這一場的合成分數（第一階段已經減過平均，約為 0）
    reference_composites: 參考場次的合成分數，必須用「這一場同一組基準」算出來
    prior_var: prior_composite_variance 的結果
    """
    if composite is None or not prior_var:
        return None
    values = [c for c in reference_composites if c is not None]
    n = len(values)
    personal_ss = statistics.variance(values) * (n - 1) if n >= 2 else 0.0
    var = (personal_ss + k * prior_var) / (max(n - 1, 0) + k)
    z = composite / var**0.5
    return max(-Z_SCORE_CLAMP, min(Z_SCORE_CLAMP, z))


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
        # 每個階段只跟歷史上「同一階段」比
        z_by_metric = metric_z_scores(
            metrics,
            [h[stage] for h in personal_history if stage in h],
            [h[stage] for h in population_history if stage in h],
            metric_rules,
        )
        stage_scores.append(
            (weighted_metric_z_score(z_by_metric, metric_rules), stage_weights[stage])
        )

    return weighted_average(stage_scores)
