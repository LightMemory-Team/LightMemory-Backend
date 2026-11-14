"""分享頁的彈幕資料與「成功送出」彈窗。

彈幕的飄動、彈窗的開關在瀏覽器裡跑（share.js），這裡只檢查頁面有沒有把
之前的人留下的內容正確帶出來，以及彈窗需要的元素。
"""

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from public_share.views import DANMAKU_LIMIT
from social.models import Comment, Post, VoiceReply

User = get_user_model()


class SharePageDanmakuTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="elder_lin", password="password123", nickname="林奶奶"
        )
        self.post = Post.objects.create(
            user=self.user,
            content="今天早上看到陽台的牽牛花開得好漂亮。",
            is_enabled=True,
            is_share_enabled=True,
        )
        self.url = f"/share/{self.post.share_token}/"

    def _set_created_at(self, obj, minutes_ago):
        type(obj).objects.filter(pk=obj.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes_ago)
        )

    def test_no_comments_gives_empty_list(self):
        response = self.client.get(self.url)

        self.assertEqual(response.context["danmaku_items"], [])
        html = response.content.decode()
        self.assertIn('id="danmaku-data"', html)

    def test_comments_and_voice_replies_newest_first(self):
        old = Comment.objects.create(post=self.post, nickname="小玲", content="花好漂亮！")
        voice = VoiceReply.objects.create(
            post=self.post,
            nickname="阿明",
            audio_path="voice-replies/a.webm",
            duration_sec=5,
            transcribed_text="阿嬤加油",
        )
        new = Comment.objects.create(post=self.post, nickname="小華", content="下次帶我去看")
        self._set_created_at(old, 30)
        self._set_created_at(voice, 20)
        self._set_created_at(new, 10)

        items = self.client.get(self.url).context["danmaku_items"]

        self.assertEqual(
            items,
            [
                {"name": "小華", "text": "下次帶我去看", "kind": "comment"},
                {"name": "阿明", "text": "送了一段語音加油", "kind": "voice"},
                {"name": "小玲", "text": "花好漂亮！", "kind": "comment"},
            ],
        )

    def test_voice_reply_does_not_leak_audio_or_transcript(self):
        VoiceReply.objects.create(
            post=self.post,
            nickname="阿明",
            audio_path="voice-replies/secret.webm",
            duration_sec=5,
            transcribed_text="只有作者看得到的內容",
        )

        html = self.client.get(self.url).content.decode()

        self.assertNotIn("secret.webm", html)
        self.assertNotIn("只有作者看得到的內容", html)

    def test_long_comment_is_truncated_and_whitespace_collapsed(self):
        Comment.objects.create(
            post=self.post, nickname="小玲", content="第一行\n\n" + "好" * 40
        )

        item = self.client.get(self.url).context["danmaku_items"][0]

        self.assertEqual(item["text"], "第一行 " + "好" * 26 + "…")

    def test_comment_by_logged_in_user_uses_display_name(self):
        Comment.objects.create(post=self.post, user=self.user, content="謝謝大家")

        item = self.client.get(self.url).context["danmaku_items"][0]

        self.assertEqual(item["name"], "林奶奶")

    def test_limited_to_latest_items(self):
        for i in range(DANMAKU_LIMIT + 5):
            Comment.objects.create(post=self.post, nickname="小玲", content=f"第{i}則")

        items = self.client.get(self.url).context["danmaku_items"]

        self.assertEqual(len(items), DANMAKU_LIMIT)

    def test_other_posts_comments_are_not_included(self):
        other = Post.objects.create(user=self.user, content="另一篇", is_share_enabled=True)
        Comment.objects.create(post=other, nickname="路人", content="別篇的留言")

        self.assertEqual(self.client.get(self.url).context["danmaku_items"], [])

    def test_danmaku_json_is_escaped(self):
        Comment.objects.create(
            post=self.post, nickname="小玲", content="</script><script>alert(1)</script>"
        )

        html = self.client.get(self.url).content.decode()

        self.assertNotIn("<script>alert(1)", html)
        start = html.index('id="danmaku-data"')
        raw = html[html.index(">", start) + 1:html.index("</script>", start)]
        self.assertEqual(json.loads(raw)[0]["text"], "</script><script>alert(1)</scr…")

    def test_success_modal_and_no_sent_list(self):
        html = self.client.get(self.url).content.decode()

        modal = html[html.index('id="success-modal"'):]
        self.assertIn('role="dialog"', modal)
        self.assertIn("成功送出", modal)
        self.assertIn("再留言一篇", modal)
        # 送出後改跳彈窗，不再在留言區列「已送出」
        self.assertNotIn('id="sent-list"', html)

    def test_media_band_hidden_without_photo_and_comments(self):
        html = self.client.get(self.url).content.decode()
        media_tag = html[html.index('id="post-media"'):]
        media_tag = media_tag[:media_tag.index(">")]
        self.assertIn("hidden", media_tag)

        Comment.objects.create(post=self.post, nickname="小玲", content="花好漂亮！")
        html = self.client.get(self.url).content.decode()
        media_tag = html[html.index('id="post-media"'):]
        media_tag = media_tag[:media_tag.index(">")]
        self.assertNotIn("hidden", media_tag)
