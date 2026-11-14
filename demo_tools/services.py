"""後台「維護任務」頁（/admin/demo/）的每個按鈕要做的事。

全部只動 admin_demo 這個帳號的資料，而且可以重複按：先刪掉同類的舊資料再重建，
不會越按越多。每個任務回傳一句給後台顯示的結果訊息。
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from dashboard.management.commands.seed_demo import seed_demo_data
from dashboard.models import WeeklyReport
from dashboard.services import GAME_SOURCES, GAME_TITLES
from diary.models import Diary
from games.models import GameRecord, GameSession
from home.models import DailyTask
from rewards import services as rewards_services
from rewards.models import PointTransaction, UserAchievement
from social.models import Comment, Like, Notification, Post
from users.models import User

from .constants import DEMO_NICKNAME, DEMO_PASSWORD, DEMO_USERNAME

# 分享頁上的親友留言（暱稱, 內容），由舊到新
DEMO_COMMENTS = [
    ("女兒", "看到您每天都過得這麼充實，我好開心！"),
    ("老同學", "照片拍得真好，改天一起去走走！"),
    ("小孫子", "看起來好好吃！下次也要帶我去喔！"),
]


class DemoTaskError(Exception):
    """任務做不下去（例如還沒有日記可以分享），訊息會直接顯示在後台。"""


def ensure_demo_user(reset_password=False):
    """取得 admin_demo，沒有就建立。

    每次都確保它是 superuser、暱稱是 demo；新建立或 reset_password=True 時
    才把密碼設回預設值（平常按按鈕不會動到密碼）。
    """
    user, created = User.objects.get_or_create(username=DEMO_USERNAME)
    user.nickname = DEMO_NICKNAME
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    if created or reset_password:
        user.set_password(DEMO_PASSWORD)
    user.save()
    return user, created


# ── 按鈕 1：三個月的遊戲與日記紀錄 ─────────────────────────


def seed_history(user):
    """五款遊戲各 30 場、日記 30 篇（儀表板雷達圖解鎖、週報有內容）。"""
    seed_demo_data(user)
    # 週報會在 App 點開時重新產生；刪掉舊快照，才不會看到之前的內容
    WeeklyReport.objects.filter(user=user).delete()
    games = GameSession.objects.filter(user=user, status="finished").count()
    diaries = Diary.objects.filter(user=user).count()
    return f"已產生遊戲紀錄 {games} 場、聲影日記 {diaries} 篇"


# ── 按鈕 2：分享頁的親友留言 ──────────────────────────────


def _latest_diary(user):
    return (
        Diary.objects.filter(user=user, status="done").order_by("-created_at").first()
    )


def share_url(post):
    return f"{settings.SHARE_BASE_URL.rstrip('/')}/share/{post.share_token}/"


def seed_share_comments(user):
    """把最新一篇日記分享出去，加上親友留言與通知。"""
    diary = _latest_diary(user)
    if diary is None:
        raise DemoTaskError("還沒有日記可以分享，請先按「產生三個月遊戲＋日記紀錄」")

    # 跟 App 的分享 API（diary/views.py DiaryShareView）一樣的建立方式
    post, _ = Post.objects.get_or_create(
        diary=diary,
        defaults={
            "user": user,
            "post_type": "diary",
            "content": diary.post_text,
            "image_path": diary.image_path,
        },
    )
    target_url = f"/posts/{post.id}/"

    # 先刪掉之前按的，再重建
    nicknames = [nickname for nickname, _ in DEMO_COMMENTS]
    Comment.objects.filter(post=post, user=None, nickname__in=nicknames).delete()
    Notification.objects.filter(
        user=user, notification_type="comment", target_url=target_url
    ).delete()

    now = timezone.now()
    for minutes_ago, (nickname, content) in zip(
        (30, 20, 10), DEMO_COMMENTS, strict=True
    ):
        created_at = now - timedelta(minutes=minutes_ago)
        # 跟分享頁留言 API（public_share/views.py）一樣：留言 + 通知長輩
        comment = Comment.objects.create(
            post=post, user=None, nickname=nickname, content=content
        )
        notification = Notification.objects.create(
            user=user,
            actor=None,
            notification_type="comment",
            message=f"{nickname} 在你的日記留言了",
            target_url=target_url,
        )
        # created_at 是 auto_now_add，只能建立後再改（彈幕才有先後順序）
        Comment.objects.filter(pk=comment.pk).update(created_at=created_at)
        Notification.objects.filter(pk=notification.pk).update(created_at=created_at)

    return f"已分享日記「{diary.title}」並加上 {len(DEMO_COMMENTS)} 則親友留言"


# ── 按鈕 3：點數與成就 ───────────────────────────────────


def seed_rewards(user):
    """用最近的遊戲與日記發點數、解鎖成就（跟真的玩完一樣走 grant()）。"""
    latest_sessions = [
        session
        for code in GAME_SOURCES
        if (
            session := GameSession.objects.filter(
                user=user, game__code=code, status="finished"
            )
            .select_related("game")
            .order_by("-finished_at")
            .first()
        )
    ]
    if not latest_sessions:
        raise DemoTaskError("還沒有遊戲紀錄，請先按「產生三個月遊戲＋日記紀錄」")

    # 先清掉，重按時點數才不會只剩「已經發過」的 0 點
    PointTransaction.objects.filter(user=user).delete()
    UserAchievement.objects.filter(user=user).delete()

    for session in latest_sessions:
        rewards_services.grant(user, rewards_services.GAME_FINISH, session)
    diary = _latest_diary(user)
    if diary is not None:
        rewards_services.grant(user, rewards_services.DIARY_COMPLETE, diary)
    if Post.objects.filter(user=user).exists():
        rewards_services.grant(user, rewards_services.DIARY_SHARED)

    points = rewards_services.total_points(user)
    achievements = UserAchievement.objects.filter(user=user).count()
    return f"目前共 {points} 點、已解鎖 {achievements} 個成就"


# ── 按鈕 4：全部清除 ─────────────────────────────────────


def clear_all(user):
    """刪掉 admin_demo 的所有活動資料（含真的在 App 玩的場次），帳號本身保留。"""
    sessions, _ = GameSession.objects.filter(user=user).delete()
    diaries, _ = Diary.objects.filter(user=user).delete()
    for model in (
        Post,
        Notification,
        Like,
        PointTransaction,
        UserAchievement,
        WeeklyReport,
        DailyTask,
        GameRecord,
    ):
        model.objects.filter(user=user).delete()
    return "已清除 admin_demo 的所有展示資料（帳號保留）"


# ── 頁面上的「目前狀態」 ─────────────────────────────────


def get_status(user):
    finished = GameSession.objects.filter(user=user, status="finished")
    post = Post.objects.filter(user=user).order_by("-created_at").first()
    return {
        "games": [
            {
                "title": GAME_TITLES[code],
                "count": finished.filter(game__code=code).count(),
            }
            for code in GAME_SOURCES
        ],
        "diary_count": Diary.objects.filter(user=user).count(),
        "comment_count": Comment.objects.filter(post__user=user).count(),
        "total_points": rewards_services.total_points(user),
        "achievement_count": UserAchievement.objects.filter(user=user).count(),
        "share_url": share_url(post) if post else None,
    }


# 頁面上的按鈕（順序就是畫面上的順序）
TASKS = {
    "seed_history": {
        "label": "產生三個月遊戲＋日記紀錄",
        "help": "五款遊戲各 30 場、聲影日記 30 篇。儀表板雷達圖會解鎖，週報也有內容。",
        "run": seed_history,
    },
    "seed_share_comments": {
        "label": "產生分享頁留言",
        "help": "分享最新一篇日記，加上 3 則親友留言與通知（分享頁會出現彈幕）。",
        "run": seed_share_comments,
    },
    "seed_rewards": {
        "label": "產生點數與成就",
        "help": "用最近的遊戲與日記發點數、解鎖成就。",
        "run": seed_rewards,
    },
    "clear_all": {
        "label": "清除 admin_demo 所有資料",
        "help": "刪掉遊戲、日記、分享、通知、點數，回到全新帳號的狀態（帳號保留）。",
        "run": clear_all,
        "danger": True,
    },
}
