"""儀表板「小提醒」：近期某款遊戲有一場表現比平常低很多時，提醒長者多注意。

每場遊戲結算時存的 z_score（GameSession.result）本來就是「跟自己過去的表現比」
（games/zscore.py：個人基準＋收縮估計，限制在 ±2），這裡只挑出偏低的場次。

- 只提示偏低、不提示偏高：目的是「建議多注意」
- z_score 為 None（歷史不足）與熟悉場（is_pretest）不算
- 聲影日記（語言）不納入：日記的 z 是現算的，另議
- 文案是生活化的提醒，不是醫療判斷，不出現「異常」「退化」等字眼
"""

from datetime import timedelta

from django.utils import timezone

from games.models import GameSession
from games.zscore import z_score_to_display_score

from .services import GAME_SOURCES, GAME_TITLES, dimension_for_source

# z ≤ -1.5 約是自己平常表現的最低 7%；demo 資料太常觸發時可調成 -1.8
ALERT_Z_THRESHOLD = -1.5
ALERT_LOOKBACK_DAYS = 14
MAX_ALERTS = 5


def _alert_message(played_at, game_title):
    return (
        f"{played_at.month}/{played_at.day} 玩「{game_title}」的表現比平常低一些，"
        "可能當天比較累，建議多注意一下，休息後再玩一次看看。"
    )


def get_score_alerts(user, now=None):
    """近 14 天內，每款遊戲最近一場 z ≤ 門檻的場次，新到舊，最多 5 筆。

    沒有符合的場次時回傳空陣列。
    """
    now = now or timezone.now()
    sessions = (
        GameSession.objects.filter(
            user=user,
            status="finished",
            is_pretest=False,
            game__code__in=GAME_SOURCES,
            finished_at__gte=now - timedelta(days=ALERT_LOOKBACK_DAYS),
            finished_at__lte=now,
        )
        .order_by("-finished_at")
        .values_list("game__code", "result", "finished_at")
    )

    alerts = []
    alerted_games = set()
    for game_id, result, finished_at in sessions:
        if game_id in alerted_games:
            continue
        z_score = (result or {}).get("z_score")
        if z_score is None or z_score > ALERT_Z_THRESHOLD:
            continue

        alerted_games.add(game_id)
        played_at = timezone.localtime(finished_at)
        dimension = dimension_for_source(game_id)
        alerts.append(
            {
                "game_id": game_id,
                "game_title": GAME_TITLES[game_id],
                "dimension": dimension["dimension"],
                "dimension_label": dimension["label"],
                "played_at": played_at,
                "display_score": z_score_to_display_score(z_score),
                "message": _alert_message(played_at, GAME_TITLES[game_id]),
            }
        )
        if len(alerts) >= MAX_ALERTS:
            break
    return alerts
