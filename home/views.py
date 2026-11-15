from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ai_service.greeting import get_daily_greeting
from dashboard.services import dimension_for_source
from games.catalog import GAMES
from social.models import Notification
from social.utils import get_display_name

from . import daily_tasks, service

# Create your views here.
"""
目前的建議跟問候僅作api 連接測試，之後放入service.py
"""


# 首頁連線
@api_view(["GET"])
def ping(request):
    return Response({"message": "index api is connected"})


# 首頁問候「早安，玉蘭！」用的名字：回傳暱稱（舊帳號沒有暱稱時退回姓名／帳號）
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user(request):
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    return Response(
        {
            "user_name": get_display_name(request.user),
            "unread_notification_count": unread_count,
        }
    )


# 問候語：每天由 AI 產生一句 10 字以內的話（失敗時用固定問候語）
@api_view(["GET"])
def greet(request):
    return Response({"daily_tip": get_daily_greeting()})


# 每日建議
@api_view(["GET"])
def daily_suggetion(request):
    daily_suggestion = {
        "text": "完成一場菜市場遊戲",
        "action_route": "game_market_sort",
    }
    if daily_suggestion is None:
        return Response({"daily_suggetion_error": "查無建議事項"}, status=404)
    return Response({"daily_suggestion": daily_suggestion})


# 遊戲卡片列表：所有已開發的遊戲，並標示本週（週一到今天）有沒有玩過、
# 對應的認知維度（dimension／dimension_label）
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def games_list(request):
    today = timezone.localdate()
    played = service.played_game_ids(request.user, service.week_start(today), today)
    games = []
    for game in GAMES:
        if not game["is_developed"]:
            continue
        # 卡片上的認知維度標籤（跟儀表板雷達圖同一份對應）
        dimension = dimension_for_source(game["id"])
        games.append(
            {
                **game,
                "played_this_week": game["id"] in played,
                "dimension": dimension["dimension"] if dimension else None,
                "dimension_label": dimension["label"] if dimension else None,
            }
        )
    return Response({"games": games})


# 今日任務：當天第一次呼叫時產生並存起來，之後同一天回傳同一份；done 每次即時計算
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def daily_tasks_view(request):
    return Response(daily_tasks.build_response(request.user, timezone.localdate()))
