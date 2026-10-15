from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from users.models import User
from diary.models import Diary, DiaryReply
from social.models import Post


class Command(BaseCommand):
    help = "建立/重設測試帳號與動態回顧（昨天、去年今日）測試資料"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default="testuser",
            help="指定使用者帳號（預設: testuser）",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="Test123456!",
            help="測試密碼（預設: Test123456!）",
        )

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]

        user, created = User.objects.get_or_create(username=username)
        user.set_password(password)
        user.first_name = "奶奶"
        user.last_name = "林"
        user.avatar_url = "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=200"
        user.save()

        action = "建立" if created else "更新"
        self.stdout.write(self.style.SUCCESS(f"[OK] {action}測試帳號: {username} (密碼: {password})"))

        # 清除舊的測試日記（避免重複塞資料）
        old_diaries = Diary.objects.filter(
            user=user,
            title__in=["大安森林公園散步 ☀️", "元宵賞花燈 ✨"],
        )
        count = old_diaries.count()
        if count > 0:
            old_diaries.delete()
            self.stdout.write(f"[INFO] 清理了 {count} 筆舊測試日記")

        today = timezone.localdate()
        yesterday_date = today - timedelta(days=1)
        try:
            last_year_date = today.replace(year=today.year - 1)
        except ValueError:
            last_year_date = today.replace(year=today.year - 1, day=28)

        now = timezone.now()
        yesterday_dt = now - timedelta(days=1)
        try:
            last_year_dt = now.replace(year=today.year - 1)
        except ValueError:
            last_year_dt = now.replace(year=today.year - 1, day=28)

        # 1. 昨天的日記（未分享，方便前端測試 S-1 分享到動態牆）
        diary_yesterday = Diary.objects.create(
            user=user,
            status="done",
            title="大安森林公園散步 ☀️",
            image_path="https://images.unsplash.com/photo-1519331379826-f10be5486c6f?w=800",
            post_text="昨天下午天氣真好，跟老朋友去大安森林公園散步，看到很多漂亮的花，心情非常輕鬆愉快。",
            first_question="今天去了哪裡散步呢？",
            pending_question="",
            hashtags=["#大安森林公園", "#散步", "#好心情"],
            category="daily",
            invite_text="林奶奶昨天去大安森林公園散步，點進來看看她說了什麼吧！",
            suggested_replies=["散步真棒！", "今天天氣也很好呢！", "下次也帶我去～"],
            ai_response="多出門曬曬太陽散步對身心都很好，看花讓人心情開朗呢！",
        )
        Diary.objects.filter(id=diary_yesterday.id).update(created_at=yesterday_dt)

        DiaryReply.objects.create(
            diary=diary_yesterday,
            round_index=1,
            question="今天去了哪裡散步呢？",
            transcript="我昨天下午去大安森林公園散步，花開得很漂亮。",
            audio_path="https://actions.google.com/sounds/v1/ambiences/park_fountain.ogg",
            is_skipped=False,
        )
        DiaryReply.objects.create(
            diary=diary_yesterday,
            round_index=2,
            question="有遇到什麼有趣的事嗎？",
            transcript="遇到好幾隻可愛的小狗在草地上跑來跑去。",
            audio_path="https://actions.google.com/sounds/v1/ambiences/outdoor_ambience.ogg",
            is_skipped=False,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] 建立昨天日記 (ID: {diary_yesterday.id}, 日期: {yesterday_date}, 未分享)"
            )
        )

        # 2. 去年的今天日記（已分享，方便前端驗證 is_shared=true 與 post_id）
        diary_last_year = Diary.objects.create(
            user=user,
            status="done",
            title="元宵賞花燈 ✨",
            image_path="https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=800",
            post_text="去年的今天跟老朋友一起去逛花燈，吃了熱騰騰的湯圓，街上滿滿的人潮，非常熱鬧。",
            first_question="去年的今天去哪裡賞花燈呢？",
            pending_question="",
            hashtags=["#元宵節", "#賞花燈", "#美好回憶"],
            category="entertainment",
            invite_text="林奶奶去年的今天去逛花燈，點進來看看珍貴回憶！",
            suggested_replies=["花燈看起來好漂亮！", "湯圓最好吃了～", "真懷念～"],
            ai_response="熱鬧的節慶回憶最溫暖人心了！",
        )
        Diary.objects.filter(id=diary_last_year.id).update(created_at=last_year_dt)

        DiaryReply.objects.create(
            diary=diary_last_year,
            round_index=1,
            question="去年的今天去哪裡賞花燈呢？",
            transcript="去年的今天跟朋友一起去逛燈會，花燈好漂亮。",
            audio_path="https://actions.google.com/sounds/v1/ambiences/coffee_shop.ogg",
            is_skipped=False,
        )

        post = Post.objects.create(
            user=user,
            diary=diary_last_year,
            content=diary_last_year.post_text,
            image_path=diary_last_year.image_path,
            post_type="diary",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] 建立去年今日日記 (ID: {diary_last_year.id}, 日期: {last_year_date}, 已分享至 Post ID: {post.id})"
            )
        )
