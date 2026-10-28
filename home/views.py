from datetime import date

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from games.catalog import GAMES
from social.utils import get_display_name

from . import service

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
    return Response({"user_name": get_display_name(request.user)})


# 問候語
@api_view(["GET"])
def greet(request):
    tips = [
        "今天也要保持大腦活力喔。",
        "早安,今天心情如何呢？",
        "陽光正好,適合散散步。",
    ]
    today = date.today()
    index = today.toordinal() % len(tips)
    if tips is None:
        return Response({"daily_tip_error": "查無今日問安"}, status=404)
    return Response({"daily_tip": tips[index]})


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


# 遊戲卡片列表：所有已開發的遊戲，並標示本週（週一到今天）有沒有玩過
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def games_list(request):
    today = timezone.localdate()
    played = service.played_game_ids(request.user, service.week_start(today), today)
    games = [
        {**game, "played_this_week": game["id"] in played}
        for game in GAMES
        if game["is_developed"]
    ]
    return Response({"games": games})
