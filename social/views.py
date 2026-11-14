import os

from django.core.files import File
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from diary import external
from diary.external import delete_from_firebase
from diary.media import media_url

from .models import Comment, Notification, VoiceReply
from .serializers import CommentSerializer, NotificationSerializer
from .utils import (
    error_response,
    failure_response,
    get_visible_post,
    paginate,
    post_queryset,
    serialize_post,
    success_response,
)


# 通知列表（GET）／全部標為已讀（PATCH）
@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def notification_list(request):
    user = request.user
    if request.method == 'PATCH':
        # 只動自己的未讀通知
        Notification.objects.filter(user=user, is_read=False).update(is_read=True)
        return success_response({"message": "已全部標記為已讀"})

    notifications = Notification.objects.filter(user=user).order_by('-created_at', '-id')
    serializer = NotificationSerializer(notifications, many=True)
    return success_response({"notifications": serializer.data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def unread_count(request):
    user = request.user
    count = Notification.objects.filter(user=user, is_read=False).count()
    return success_response({"unread_notification_count": count})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def mark_as_read(request, notification_id):
    try:
        notification = Notification.objects.get(id=notification_id, user=request.user)
    except Notification.DoesNotExist:
        return failure_response("NOTIFICATION_NOT_FOUND", "查無此通知", status=404)

    notification.is_read = True
    notification.save()
    return success_response({"message": "已標記為已讀"})

class PostListView(APIView):
    """S-2 動態牆列表"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = post_queryset(request.user).order_by('-created_at', '-id')
        return paginate(request, qs, lambda posts: [serialize_post(p, request.user) for p in posts])

class PostDetailView(APIView):
    """S-11 單則貼文詳情"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, post_id):
        post = get_visible_post(request.user, post_id)
        if not post:
            return error_response("POST_NOT_FOUND", "找不到這則貼文", 404)
        return Response({"data": serialize_post(post, request.user)})
    def delete(self, request, post_id):
        post = get_visible_post(request.user, post_id)
        if not post:
            return error_response("POST_NOT_FOUND", "找不到這則貼文", 404)
        # 語音加油的音檔在 Firebase：先記下路徑，資料庫刪除成功後才刪檔案
        audio_paths = list(post.voice_replies.values_list("audio_path", flat=True))
        with transaction.atomic():
            post.delete()
            if audio_paths:
                transaction.on_commit(lambda: delete_from_firebase(audio_paths))
        return Response(status=status.HTTP_204_NO_CONTENT)


class PostCommentsView(APIView):
    """S-13 留言列表 / S-14 新增留言"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, post_id):
        post = get_visible_post(request.user, post_id)
        if not post:
            return error_response("POST_NOT_FOUND", "找不到這則貼文", 404)
        comments = post.comments.select_related('user').order_by('created_at', 'id')
        return paginate(
            request, comments,
            lambda items: CommentSerializer(items, many=True, context={'request': request}).data,
        )

    def post(self, request, post_id):
        post = get_visible_post(request.user, post_id)
        if not post:
            return error_response("POST_NOT_FOUND", "找不到這則貼文", 404)

        text = request.data.get('text')
        text = text.strip() if isinstance(text, str) else ''
        if not text or len(text) > 200:
            return error_response("INVALID_TEXT", "留言不可為空，且不超過200字", 400)

        comment = Comment.objects.create(post_id=post.id, user=request.user, content=text)

        serializer = CommentSerializer(comment, context={'request': request})
        return Response({"data": serializer.data}, status=status.HTTP_201_CREATED)
    
class CommentDeleteView(APIView):
    """S-15 刪除留言(只有貼文作者能刪)"""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, comment_id):
        comment = (Comment.objects
                   .filter(pk=comment_id, post__is_enabled=True, post__user=request.user)
                   .first())
        if not comment:
            return error_response("COMMENT_NOT_FOUND", "找不到這則留言", 404)
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Whisper 聽不出內容時存這句，避免每次按「轉文字」都重跑
UNCLEAR_TRANSCRIPT = "（聽不太清楚，請直接播放聽聽看）"


def serialize_voice_reply(voice_reply):
    return {
        "voice_reply_id": voice_reply.id,
        "nickname": voice_reply.nickname,
        "audio_url": media_url(voice_reply.audio_path),
        "duration_sec": voice_reply.duration_sec,
        # 空字串代表還沒轉文字
        "transcribed_text": voice_reply.transcribed_text,
        "created_at": timezone.localtime(voice_reply.created_at).isoformat(),
    }


class PostVoiceRepliesView(APIView):
    """語音加油列表：GET /api/social/posts/<post_id>/voice-replies/（只限作者）"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, post_id):
        post = get_visible_post(request.user, post_id)
        if not post:
            return failure_response("POST_NOT_FOUND", "找不到這篇日記", 404)
        items = [serialize_voice_reply(v) for v in post.voice_replies.all()]
        return success_response({"items": items})


class VoiceReplyTranscribeView(APIView):
    """語音加油轉文字：POST /api/social/voice-replies/<id>/transcribe/（只限作者）

    長者按「轉文字」才跑 Whisper；轉過的直接回傳存好的結果，不再重跑。
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, voice_reply_id):
        voice_reply = VoiceReply.objects.filter(
            pk=voice_reply_id, post__user=request.user, post__is_enabled=True
        ).first()
        if not voice_reply:
            return failure_response("VOICE_REPLY_NOT_FOUND", "找不到這段語音", 404)

        if not voice_reply.transcribed_text:
            text = self._transcribe(voice_reply.audio_path)
            if text is None:
                return failure_response(
                    "TRANSCRIBE_FAILED",
                    "這段語音暫時轉不出文字，可以先直接播放聽聽看",
                    502,
                )
            voice_reply.transcribed_text = text or UNCLEAR_TRANSCRIPT
            voice_reply.save(update_fields=["transcribed_text"])

        return success_response(
            {
                "voice_reply_id": voice_reply.id,
                "transcribed_text": voice_reply.transcribed_text,
            }
        )

    @staticmethod
    def _transcribe(audio_path):
        """從 Firebase 下載音檔交給 Whisper，回傳文字；下載或轉換失敗回傳 None。"""
        tmp_path = external.download_from_firebase(audio_path)
        if tmp_path is None:
            return None
        try:
            with open(tmp_path, "rb") as f:
                return external.transcribe_audio(
                    File(f, name=os.path.basename(tmp_path))
                )
        finally:
            os.remove(tmp_path)
