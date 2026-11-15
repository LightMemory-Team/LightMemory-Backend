"""分享頁的「語音加油」畫面：收在留言區，輸入框旁的麥克風＋參考句（C4）。

實際的錄音、上傳在瀏覽器裡跑（share.js），這裡只檢查頁面有沒有把需要的
元素和資料放出來；上傳 API 本身見 test_voice_reply_upload.py。
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from diary.models import Diary
from social.models import Post

User = get_user_model()


class SharePageVoiceReplyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="elder_lin", password="password123", nickname="林奶奶"
        )
        self.diary = Diary.objects.create(
            user=self.user,
            title="陽台的花開了",
            post_text="今天早上看到陽台的牽牛花開得好漂亮。",
            status="done",
            suggested_replies=[
                "花好漂亮！",
                "  ",
                "妳好會照顧植物",
                "下次帶我去看",
                "第四句",
            ],
        )
        self.post = Post.objects.create(
            user=self.user,
            diary=self.diary,
            content=self.diary.post_text,
            is_enabled=True,
            is_share_enabled=True,
        )
        self.url = f"/share/{self.post.share_token}/"

    def test_context_has_up_to_three_non_empty_suggested_replies(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["suggested_replies"],
            ["花好漂亮！", "妳好會照顧植物", "下次帶我去看"],
        )

    def test_voice_reply_lives_in_the_comment_area(self):
        html = self.client.get(self.url).content.decode()

        comment_area = html[html.index('class="comment-area"'):]
        comment_form = comment_area[
            comment_area.index('id="comment-form"'):comment_area.index("</form>")
        ]
        # 麥克風就在留言輸入框旁邊，文字留言照常保留
        self.assertIn('id="comment-input"', comment_form)
        self.assertIn('id="vr-mic-btn"', comment_form)
        self.assertIn('id="comment-submit"', comment_form)
        # 錄音、試聽、送出在留言區裡展開；最多 10 秒
        self.assertIn('id="vr-panel"', comment_area)
        self.assertIn('id="vr-send-btn"', comment_area)
        self.assertIn("00:00 / 00:10", comment_area)
        # 參考句也在留言區
        self.assertIn('data-text="花好漂亮！"', comment_area)
        self.assertIn("Material+Symbols+Outlined", html)
        # 不再有獨立的大卡片
        self.assertNotIn("留下語音加油", html)

    def test_old_diary_without_suggestions_has_no_chips(self):
        Diary.objects.filter(pk=self.diary.pk).update(suggested_replies=[])

        response = self.client.get(self.url)

        self.assertEqual(response.context["suggested_replies"], [])
        html = response.content.decode()
        self.assertNotIn('class="suggest-chip"', html)
        self.assertIn('id="vr-mic-btn"', html)

    def test_post_without_diary_still_renders_voice_section(self):
        post = Post.objects.create(user=self.user, content="沒有日記的貼文")

        response = self.client.get(f"/share/{post.share_token}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["suggested_replies"], [])
        self.assertIn('id="vr-mic-btn"', response.content.decode())
