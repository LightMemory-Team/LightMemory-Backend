"""語音加油（VoiceReply）的測試：動態牆計數、刪除貼文時清除音檔。"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from ..models import Post, VoiceReply

User = get_user_model()


def make_voice_reply(post, *, nickname="小玲", audio_path="voice-diary/vr/a.webm"):
    return VoiceReply.objects.create(
        post=post, nickname=nickname, audio_path=audio_path, duration_sec=8
    )


class VoiceReplyWallTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="a", password="x")
        self.post = Post.objects.create(user=self.user, content="今天去逛花燈")
        self.client.force_authenticate(self.user)

    def test_voice_reply_count_on_wall(self):
        make_voice_reply(self.post)
        make_voice_reply(self.post, nickname="阿明")
        other_post = Post.objects.create(user=self.user, content="另一篇")

        items = self.client.get("/api/social/posts/").data["data"]
        counts = {item["post_id"]: item["voice_reply_count"] for item in items}

        self.assertEqual(counts, {self.post.id: 2, other_post.id: 0})

    def test_voice_reply_count_with_comments_is_not_multiplied(self):
        # 同時有留言與語音時，兩個 Count 不能互相乘開
        make_voice_reply(self.post)
        make_voice_reply(self.post, nickname="阿明")
        for text in ("加油", "好漂亮", "讚"):
            self.post.comments.create(user=self.user, content=text)

        item = self.client.get(f"/api/social/posts/{self.post.id}/").data["data"]

        self.assertEqual(item["voice_reply_count"], 2)
        self.assertEqual(item["comment_count"], 3)

    def test_delete_post_removes_voice_replies_and_their_audio(self):
        make_voice_reply(self.post, audio_path="voice-diary/vr/1.webm")
        make_voice_reply(self.post, audio_path="voice-diary/vr/2.mp4")

        with (
            patch("social.views.delete_from_firebase") as delete_files,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.delete(f"/api/social/posts/{self.post.id}/")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(VoiceReply.objects.count(), 0)
        delete_files.assert_called_once()
        self.assertEqual(
            sorted(delete_files.call_args.args[0]),
            ["voice-diary/vr/1.webm", "voice-diary/vr/2.mp4"],
        )

    def test_delete_post_without_voice_replies_does_not_touch_firebase(self):
        with (
            patch("social.views.delete_from_firebase") as delete_files,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.delete(f"/api/social/posts/{self.post.id}/")

        self.assertEqual(response.status_code, 204)
        delete_files.assert_not_called()
