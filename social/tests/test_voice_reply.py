"""語音加油（VoiceReply）的測試：動態牆計數、刪除貼文時清除音檔、
長者看列表與轉文字。Firebase 與 Whisper 一律用 mock。"""

import os
import tempfile
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


def fake_download(path):
    """假的 download_from_firebase：建一個真的暫存檔，讓 view 能開檔、刪檔。"""
    fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(path)[1])
    os.write(fd, b"fake-audio")
    os.close(fd)
    fake_download.last_path = tmp_path
    return tmp_path


class VoiceReplyListTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="a", password="x")
        self.post = Post.objects.create(user=self.user, content="今天去逛花燈")
        self.url = f"/api/social/posts/{self.post.id}/voice-replies/"
        self.client.force_authenticate(self.user)

    @patch("social.views.media_url", side_effect=lambda p: f"https://signed/{p}")
    def test_list_newest_first_with_signed_audio_url(self, _):
        older = make_voice_reply(self.post, nickname="阿明", audio_path="vr/1.webm")
        newer = make_voice_reply(self.post, nickname="小玲", audio_path="vr/2.mp4")
        newer.transcribed_text = "加油"
        newer.save()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.data["success"], True)
        items = response.data["data"]["items"]
        self.assertEqual([i["voice_reply_id"] for i in items], [newer.id, older.id])
        self.assertEqual(items[0]["audio_url"], "https://signed/vr/2.mp4")
        self.assertEqual(items[0]["transcribed_text"], "加油")
        self.assertEqual(items[1]["transcribed_text"], "")
        self.assertEqual(items[1]["duration_sec"], 8)
        self.assertIn("+08:00", items[1]["created_at"])

    def test_empty_list(self):
        response = self.client.get(self.url)

        self.assertEqual(response.data["data"], {"items": []})

    def test_not_logged_in_returns_401(self):
        self.client.force_authenticate(None)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"]["code"], "NOT_AUTHENTICATED")

    def test_other_users_or_disabled_post_returns_404(self):
        other = User.objects.create_user(username="b", password="x")
        self.client.force_authenticate(other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"]["code"], "POST_NOT_FOUND")

        self.client.force_authenticate(self.user)
        Post.objects.filter(pk=self.post.pk).update(is_enabled=False)
        self.assertEqual(self.client.get(self.url).status_code, 404)


@patch("diary.external.download_from_firebase", side_effect=fake_download)
@patch("diary.external.transcribe_audio", return_value="阿嬤妳拍得好漂亮，加油！")
class VoiceReplyTranscribeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="a", password="x")
        self.post = Post.objects.create(user=self.user, content="今天去逛花燈")
        self.reply = make_voice_reply(self.post, audio_path="vr/1.webm")
        self.url = f"/api/social/voice-replies/{self.reply.id}/transcribe/"
        self.client.force_authenticate(self.user)

    def test_transcribes_and_saves_the_text(self, transcribe, download):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["data"],
            {
                "voice_reply_id": self.reply.id,
                "transcribed_text": "阿嬤妳拍得好漂亮，加油！",
            },
        )
        self.reply.refresh_from_db()
        self.assertEqual(self.reply.transcribed_text, "阿嬤妳拍得好漂亮，加油！")
        download.assert_called_once_with("vr/1.webm")
        # 暫存檔用完就刪
        self.assertFalse(os.path.exists(fake_download.last_path))

    def test_second_time_returns_saved_text_without_whisper(self, transcribe, download):
        self.client.post(self.url)
        transcribe.reset_mock()
        download.reset_mock()

        response = self.client.post(self.url)

        self.assertEqual(
            response.data["data"]["transcribed_text"], "阿嬤妳拍得好漂亮，加油！"
        )
        transcribe.assert_not_called()
        download.assert_not_called()

    def test_empty_result_is_saved_as_a_hint(self, transcribe, download):
        transcribe.return_value = ""

        response = self.client.post(self.url)

        self.assertEqual(
            response.data["data"]["transcribed_text"],
            "（聽不太清楚，請直接播放聽聽看）",
        )
        self.client.post(self.url)
        self.assertEqual(transcribe.call_count, 1)

    def test_whisper_failure_returns_502_and_saves_nothing(self, transcribe, download):
        transcribe.return_value = None

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 502)
        self.assertIs(response.data["success"], False)
        self.assertEqual(response.data["error"]["code"], "TRANSCRIBE_FAILED")
        self.reply.refresh_from_db()
        self.assertEqual(self.reply.transcribed_text, "")
        self.assertFalse(os.path.exists(fake_download.last_path))

    def test_download_failure_returns_502(self, transcribe, download):
        download.side_effect = None
        download.return_value = None

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["error"]["code"], "TRANSCRIBE_FAILED")
        transcribe.assert_not_called()

    def test_other_users_voice_reply_returns_404(self, transcribe, download):
        other = User.objects.create_user(username="b", password="x")
        self.client.force_authenticate(other)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"]["code"], "VOICE_REPLY_NOT_FOUND")
        transcribe.assert_not_called()

    def test_missing_voice_reply_returns_404(self, transcribe, download):
        response = self.client.post("/api/social/voice-replies/99999/transcribe/")

        self.assertEqual(response.status_code, 404)

    def test_not_logged_in_returns_401(self, transcribe, download):
        self.client.force_authenticate(None)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"]["code"], "NOT_AUTHENTICATED")
