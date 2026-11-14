"""後台「維護任務」頁（/admin/demo/）的每個按鈕要做的事。

全部只動 admin_demo 這個帳號的資料，而且可以重複按：先刪掉同類的舊資料再重建，
不會越按越多。每個任務回傳一句給後台顯示的結果訊息。
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from dashboard.alerts import get_score_alerts
from dashboard.management.commands.seed_demo import (
    DIARY_THEMES,
    QUESTION_COUNTS,
    RESULT_BUILDERS,
    SEED_PREFIX,
    create_diary_analysis,
    ensure_games,
    seed_demo_data,
)
from dashboard.models import WeeklyReport
from dashboard.services import GAME_SOURCES, GAME_TITLES
from diary.models import Diary, DiaryReply
from games.models import GameRecord, GameSession
from games.zscore import z_score_to_display_score
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


# ── 按鈕 3：一篇已發佈到動態牆的日記 ────────────────────────


def feed_audio_path(theme_index):
    # seed/ 開頭：不會被拿去當其他人的比較基準；重按同一個主題靠它找到舊的那篇
    return f"{SEED_PREFIX}/feed-{theme_index}.m4a"


def seed_feed_post(user, theme_choice):
    """建立一篇今天的完整日記（照片、問答、分析），並發佈到動態牆。

    主題用 seed_demo 的 DIARY_THEMES（照片已在 Firebase Storage）。
    同一個主題重按只留一篇；換主題再按就多一篇。
    """
    if theme_choice not in {str(i) for i in range(len(DIARY_THEMES))}:
        raise DemoTaskError("請先選擇日記主題")
    theme = DIARY_THEMES[int(theme_choice)]

    # 刪日記會連帶刪掉它的貼文、問答、分析、留言
    audio_path = feed_audio_path(theme_choice)
    Diary.objects.filter(user=user, audio_path=audio_path).delete()

    created_at = timezone.now() - timedelta(minutes=10)
    diary = Diary.objects.create(
        user=user,
        audio_path=audio_path,
        image_path=theme["image_url"],
        transcription=theme["transcription"],
        diary_text=theme["transcription"],
        title=theme["title"],
        first_question=theme["first_question"],
        ai_response=theme["ai_response"],
        status="done",
        post_text=theme["post_text"],
        hashtags=theme["hashtags"],
        category=theme["category"],
        suggested_replies=["好溫馨！", "看起來好棒！", "下次也帶我去！"],
        invite_text="一起來分享你的生活吧！",
    )
    # created_at 是 auto_now_add，只能建立後再改
    Diary.objects.filter(pk=diary.pk).update(created_at=created_at)
    for round_index, transcript in enumerate(theme["replies"], start=1):
        reply = DiaryReply.objects.create(
            diary=diary, round_index=round_index, transcript=transcript
        )
        DiaryReply.objects.filter(pk=reply.pk).update(
            created_at=created_at + timedelta(minutes=2 * round_index)
        )
    create_diary_analysis(diary, 0.3)

    # 跟 App 的分享 API（diary/views.py DiaryShareView）一樣的建立方式
    Post.objects.create(
        diary=diary,
        user=user,
        post_type="diary",
        content=diary.post_text,
        image_path=diary.image_path,
    )
    return f"已發佈日記「{theme['title']}」到動態牆"


# ── 按鈕 4：點數與成就 ───────────────────────────────────


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


# ── 按鈕 5：點數更新至 500 點 ─────────────────────────────

DEMO_POINTS = 500
# 調整用的那一筆點數紀錄：(user, reason, source_id) 唯一，重按時靠它找到舊的
POINTS_ADJUST_SOURCE_ID = "demo-points-adjust"
# 借用「解鎖成就」：不算進每日 100 點上限（demo 時玩遊戲照樣加點），
# 也不用為了新增類別多一個 migration
POINTS_ADJUST_REASON = "achievement_unlock"


def set_points(user, target=DEMO_POINTS):
    """補一筆差額，讓總點數剛好是 target（目前比較多就補負數）。"""
    PointTransaction.objects.filter(
        user=user, reason=POINTS_ADJUST_REASON, source_id=POINTS_ADJUST_SOURCE_ID
    ).delete()
    difference = target - rewards_services.total_points(user)
    if difference:
        PointTransaction.objects.create(
            user=user,
            reason=POINTS_ADJUST_REASON,
            source_id=POINTS_ADJUST_SOURCE_ID,
            amount=difference,
            label="Demo 點數調整",
        )
    total = rewards_services.total_points(user)
    return f"總點數已更新為 {total} 點（補了 {difference:+d} 點）"


# ── 按鈕 6：分數極端值（儀表板小提醒） ─────────────────────

# 比小提醒的門檻（dashboard/alerts.py 的 ALERT_Z_THRESHOLD = -1.5）再低一點，
# 一定會觸發；換算成顯示分數是 5 分
ALERT_Z = -1.8


def alert_session_id(user, game_code):
    # seed- 開頭：不會被拿去當其他人的比較基準，重算分數指令也不會動它
    return f"{SEED_PREFIX}-alert-{user.id}-{game_code}"


def seed_score_alert(user, game_code):
    """在選的遊戲補一場「昨天、比平常低很多」的場次，儀表板就會出現小提醒。

    小提醒只看近 14 天，所以放在昨天；同一款遊戲重按只會留一場。
    """
    if game_code not in GAME_SOURCES:
        raise DemoTaskError("請先選擇要產生極端值的遊戲")

    game = ensure_games()[game_code]
    client_session_id = alert_session_id(user, game_code)
    GameSession.objects.filter(user=user, client_session_id=client_session_id).delete()

    finished_at = timezone.now() - timedelta(days=1)
    session = GameSession.objects.create(
        game=game,
        user=user,
        client_session_id=client_session_id,
        status="finished",
        question_number=QUESTION_COUNTS[game_code],
        # 結算結果的格式照各遊戲真正存的（跟 seed_demo 共用）
        result=RESULT_BUILDERS[game_code](ALERT_Z, finished_at),
        state={"user_id": user.id, "is_pretest": False},
        finished_at=finished_at,
    )
    # created_at 是 auto_now_add，只能建立後再改（每場玩 4 分鐘）
    GameSession.objects.filter(pk=session.pk).update(
        created_at=finished_at - timedelta(minutes=4)
    )

    score = z_score_to_display_score(ALERT_Z)
    return (
        f"已在「{GAME_TITLES[game_code]}」補一場昨天的低分（{score} 分），"
        "儀表板會出現小提醒"
    )


# ── 按鈕 7：全部清除 ─────────────────────────────────────


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
        "post_count": Post.objects.filter(user=user, is_enabled=True).count(),
        "total_points": rewards_services.total_points(user),
        "achievement_count": UserAchievement.objects.filter(user=user).count(),
        # 儀表板現在會顯示的小提醒（遊戲名稱）
        "alert_games": [alert["game_title"] for alert in get_score_alerts(user)],
        "share_url": share_url(post) if post else None,
    }


# 頁面上的按鈕（順序就是畫面上的順序）
TASKS = {
    "seed_history": {
        "label": "產生三個月遊戲＋日記紀錄",
        "help": "五款遊戲各 30 場、聲影日記 30 篇。儀表板雷達圖會解鎖，週報也有內容。",
        "run": seed_history,
    },
    "seed_feed_post": {
        "label": "產生動態牆日記",
        "help": "選一個主題，建立一篇今天的完整日記（照片、問答）並發佈到動態牆。"
        "換主題再按就多一篇；之後按「產生分享頁留言」會留言在最新這篇。",
        "run": seed_feed_post,
        "choices": [(str(i), theme["title"]) for i, theme in enumerate(DIARY_THEMES)],
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
    "set_points": {
        "label": "點數更新至 500 點",
        "help": "補一筆差額讓總點數剛好 500 點，重按也一樣。"
        "注意：「產生點數與成就」會重算點數，要按的話請先按它再按這個。",
        "run": set_points,
    },
    "seed_score_alert": {
        "label": "產生分數極端值（小提醒）",
        "help": "選一款遊戲，補一場昨天比平常低很多的紀錄，儀表板會出現「建議多注意」"
        "的小提醒。想要多則就換一款再按。",
        "run": seed_score_alert,
        # 頁面上多一個下拉選單，選到的值會傳給 run 的第二個參數
        "choices": [(code, GAME_TITLES[code]) for code in GAME_SOURCES],
    },
    "clear_all": {
        "label": "清除 admin_demo 所有資料",
        "help": "刪掉遊戲、日記、分享、通知、點數，回到全新帳號的狀態（帳號保留）。",
        "run": clear_all,
        "danger": True,
    },
}
