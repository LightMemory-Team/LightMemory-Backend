from rest_framework.decorators import api_view
from rest_framework.response import Response
from users.models import User
from games.models import Game
from datetime import date

# Create your views here.
'''
目前的建議跟問候僅作api 連接測試，之後放入service.py
'''
# 首頁連線
@api_view(['GET'])
def ping(request):
    return Response({"message": "index api is connected"})

# 使用者名稱 != username
@api_view(['GET'])
def get_user(request):
    user_name = User.objects.first() # 目前還沒有登入驗證先取資料庫第一筆
    if user_name is None:
        return Response({"user_name_error": "查無使用者"}, status=404)
    return Response({"user_name": user_name.last_name})

# 問候語
@api_view(['GET'])
def greet(request):
    tips = ["今天也要保持大腦活力喔。", "早安,今天心情如何呢？", "陽光正好,適合散散步。"]
    today = date.today()
    index = today.toordinal() % len(tips)
    if tips is None:
            return Response({"daily_tip_error": "查無今日問安"}, status=404)
    return Response({"daily_tip": tips[index]})

# 每日建議
@api_view(['GET'])
def daily_suggetion(request):
    daily_suggestion = {
        "text": "完成一場菜市場遊戲",
        "action_route": "game_market_sort"
        }
    if daily_suggestion is None:
            return Response({"daily_suggetion_error": "查無建議事項"}, status=404)
    return Response({"daily_suggestion": daily_suggestion})

# 遊戲卡片列表
@api_view(['GET'])
def games_list(request):
    games = Game.objects.all()
    data = [
        {
            "id": game.id,
            "title": game.game_name,
            "is_developed": game.is_enabled,
        }
        for game in games
    ]
    return Response({"games": data})
