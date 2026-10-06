"""各遊戲共用的小工具。"""

from users.models import User


def get_current_user(request):
    """取得目前使用者。

    有登入（JWT）時使用登入者；開發測試階段若未登入，暫時取第一位使用者，
    讓前端還沒串登入也能測試。資料庫沒有任何使用者時回傳 None，
    呼叫端要自己回 404 USER_NOT_FOUND。
    """
    if request.user.is_authenticated:
        return request.user
    return User.objects.first()
