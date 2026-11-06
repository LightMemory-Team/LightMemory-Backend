"""把舊場次依新算法重算（收縮基準＋二階段標準化＋熟悉場）。

    python manage.py recompute_scores --dry-run   # 只印出會改什麼，不寫入
    python manage.py recompute_scores             # 正式重算

分兩步（只改資料，不改資料表）：
1. 回填熟悉場：每位使用者、每款遊戲「最早結束」的場次標記成熟悉場
   （GameSession.is_pretest=True），其他場次標記成 False
2. 依序重算每場結算結果裡的 z_score 與 1～100 分數，寫回 result：
   - 熟悉場：z、分數都是 null
   - 其他場：用新算法跟「這場之前」的歷史比（歷史排除熟悉場）

demo 帳號的種子場次（client_session_id 以 seed- 開頭）的 z 是直接寫進去的，
不重算。日記的語言 z 是隨時現算的，不用處理。

可以重複執行：結果只跟資料有關，跑幾次都一樣。
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from games import session_service
from games.catalog import GAMES
from games.fridge_check import services as fridge_check
from games.market_route.market_zscore import calculate_attention_z_score
from games.market_shopping import services as market_shopping
from games.market_sort import services as market_sort_services
from games.market_sort.views import previous_raw_metrics
from games.memory_recall.memory_zscore import calculate_working_memory_z_score
from games.models import GameSession
from games.session_service import SEED_CLIENT_SESSION_PREFIX
from games.zscore import z_score_to_display_score

GAME_CODES = [game["id"] for game in GAMES]


def _round_or_none(value):
    return None if value is None else round(value, 3)


def _market_route(session, result):
    z_score = calculate_attention_z_score(session.pk)
    return {**result, "z_score": _round_or_none(z_score)}


def _memory_recall(session, result):
    z_score = _round_or_none(calculate_working_memory_z_score(session.pk))
    return {
        **result,
        "z_score": z_score,
        "total_score": z_score_to_display_score(z_score),
    }


def _market_sort(session, result):
    raw_metrics = result.get("raw_metrics")
    if not raw_metrics:  # 沒有原始指標的舊場次無法重算
        return result
    if session.is_pretest:
        z_score = None
        z_by_metric = {name: None for name in market_sort_services.METRIC_RULES}
    else:
        personal, population = previous_raw_metrics(session.pk)
        z_score, z_by_metric = (
            market_sort_services.calculate_executive_function_z_score(
                raw_metrics, personal, population
            )
        )
    z_score = _round_or_none(z_score)
    return {
        **result,
        "z_scores": {f"{name}_z": _round_or_none(z) for name, z in z_by_metric.items()},
        "z_score": z_score,
        "cognitive_flexibility_score": z_score_to_display_score(z_score),
    }


def _two_metric_game(module, z_function):
    """冰箱檢查、市場買菜：正確率、速度分兩個指標各自轉 z（見各 services）。"""

    def recompute(session, result):
        accuracy = result.get("accuracy")
        if accuracy is None:  # 沒有正確率的舊場次無法重算
            return result
        # 沒有反應時間資料的場次，速度分只代表「沒資料」，不列入
        has_speed_data = result.get("average_reaction_time_ms") is not None
        speed_score = result.get("speed_score") if has_speed_data else None
        if session.is_pretest:
            personal, population = [], {}
        else:
            personal = session_service.list_previous_results(
                module.GAME_TYPE, session.pk
            )
            population = session_service.list_previous_results_by_user(
                module.GAME_TYPE, session.pk
            )
        z_result = z_function(accuracy, speed_score, personal, population)
        return {
            **result,
            "z_score": z_result["z_score"],
            "standard_score": z_result["standard_score"],
        }

    return recompute


RECOMPUTERS = {
    "market_route": _market_route,
    "memory_recall": _memory_recall,
    "market_sort": _market_sort,
    "fridge_check": _two_metric_game(
        fridge_check, fridge_check.calculate_visual_spatial_z_score
    ),
    "market_shopping": _two_metric_game(
        market_shopping, market_shopping.calculate_math_z_score
    ),
}


def _real_finished_sessions():
    """真人玩完的場次（排除 demo 種子場次），依結束時間排序。"""
    return (
        GameSession.objects.filter(status="finished", game__code__in=GAME_CODES)
        .exclude(client_session_id__startswith=SEED_CLIENT_SESSION_PREFIX)
        .order_by("finished_at")
    )


def backfill_familiarization():
    """每位使用者每款遊戲最早結束的場次 → 熟悉場，其他 → 非熟悉場。

    回傳 (新標成熟悉場的場次數, 改回非熟悉場的場次數)。
    """
    first_by_player = {}
    for pk, user_id, game_id in _real_finished_sessions().values_list(
        "pk", "user_id", "game_id"
    ):
        first_by_player.setdefault((user_id, game_id), pk)
    first_pks = set(first_by_player.values())

    marked = (
        _real_finished_sessions()
        .filter(pk__in=first_pks, is_pretest=False)
        .update(is_pretest=True)
    )
    cleared = (
        _real_finished_sessions()
        .filter(is_pretest=True)
        .exclude(pk__in=first_pks)
        .update(is_pretest=False)
    )
    return marked, cleared


def recompute_results():
    """依序重算每場的結果，寫回資料庫。

    回傳 {遊戲 id: (場次數, 有變動的場次數)}。
    """
    summary = {code: [0, 0] for code in GAME_CODES}
    for session in _real_finished_sessions().select_related("game"):
        code = session.game.code
        summary[code][0] += 1
        old_result = session.result or {}
        new_result = RECOMPUTERS[code](session, old_result)
        if new_result != old_result:
            summary[code][1] += 1
            GameSession.objects.filter(pk=session.pk).update(result=new_result)
    return {code: tuple(counts) for code, counts in summary.items()}


class Command(BaseCommand):
    help = "把舊場次依新算法重算：回填熟悉場、重算 z_score 與 1～100 分數"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只印出會改什麼，不寫入資料庫",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        titles = {game["id"]: game["title"] for game in GAMES}

        # 全部包在一個 transaction：dry-run 先真的算一遍（重算要靠熟悉場標記），
        # 最後再 rollback，這樣 dry-run 印出來的數字跟正式跑的一樣
        with transaction.atomic():
            marked, cleared = backfill_familiarization()
            summary = recompute_results()
            if dry_run:
                transaction.set_rollback(True)

        prefix = "[dry-run，沒有寫入] " if dry_run else ""
        self.stdout.write(
            f"{prefix}熟悉場：新標記 {marked} 場、改回一般場次 {cleared} 場"
        )
        for code, (total, changed) in summary.items():
            self.stdout.write(
                f"{prefix}{titles[code]}：共 {total} 場，"
                f"重算後有 {changed} 場的結果改變"
            )
