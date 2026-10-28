"""home 測試共用的小工具：建立遊戲場次。"""

from games.models import Game, GameCategory, GameSession


def make_session(user, game_code, *, status="finished", created_at=None):
    """建立一筆遊戲場次；created_at 可指定時間（用來模擬「昨天玩的」）。"""
    category, _ = GameCategory.objects.get_or_create(category_name="測試")
    game, _ = Game.objects.get_or_create(
        code=game_code, defaults={"name": game_code, "category": category}
    )
    session = GameSession.objects.create(game=game, user=user, status=status)
    if created_at is not None:
        # auto_now_add 欄位無法直接指定，建立後再用 update 改
        GameSession.objects.filter(pk=session.pk).update(created_at=created_at)
    return session
