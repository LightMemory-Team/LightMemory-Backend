"""各遊戲共用的小工具。"""


def get_current_user(request):
    """取得目前使用者。

    有登入（JWT）時回傳登入者；未登入時回傳 None，
    呼叫端要自己回 404 USER_NOT_FOUND。
    """
    if request.user.is_authenticated:
        return request.user
    return None
