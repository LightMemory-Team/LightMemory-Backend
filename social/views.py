from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Comment, Like, Notification
from .serializers import CommentSerializer, NotificationSerializer
from .utils import (error_response, get_display_name, get_visible_post,
                    paginate, post_queryset, serialize_post)


# 通知列表
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def notification_list(request):
    user = request.user
    notifications = Notification.objects.filter(user=user).order_by('-created_at')
    serializer = NotificationSerializer(notifications, many=True)
    return Response({"notifications": serializer.data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def unread_count(request):
    user = request.user
    count = Notification.objects.filter(user=user, is_read=False).count()
    return Response({"unread_notification_count": count})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def mark_as_read(request, notification_id):
    try:
        notification = Notification.objects.get(id=notification_id, user=request.user)
    except Notification.DoesNotExist:
        return Response({"mark_as_read_error": "查無此通知"}, status=404)

    notification.is_read = True
    notification.save()
    return Response({"message": "已標記為已讀"})

class PostListView(APIView):
    """S-2 動態牆列表"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = post_queryset(request.user).order_by('-created_at', '-id')
        if request.query_params.get('author') == 'me':
            qs = qs.filter(user=request.user)
        return paginate(request, qs, lambda posts: [serialize_post(p, request.user) for p in posts])


class PostDetailView(APIView):
    """S-11 單則貼文詳情"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, post_id):
        post = get_visible_post(request.user, post_id)
        if not post:
            return error_response("POST_NOT_FOUND", "找不到這則貼文", 404)
        return Response({"data": serialize_post(post, request.user)})


class PostLikeView(APIView):
    """S-8 按讚 / 取消按讚"""
    permission_classes = [permissions.IsAuthenticated]

    def _respond(self, request, post_id):
        post = get_visible_post(request.user, post_id)
        return Response({"data": serialize_post(post, request.user)})

    def post(self, request, post_id):
        post = get_visible_post(request.user, post_id)
        if not post:
            return error_response("POST_NOT_FOUND", "找不到這則貼文", 404)

        _, created = Like.objects.get_or_create(post_id=post.id, user=request.user)
        target = f"/posts/{post.id}/"
        if created and post.user_id != request.user.id:
            already_notified = Notification.objects.filter(
                user=post.user, actor=request.user,
                notification_type='like', target_url=target,
            ).exists()
            if not already_notified:
                Notification.objects.create(
                    user=post.user, actor=request.user,
                    notification_type='like',
                    message=f"{get_display_name(request.user)}說你的日記很讚",
                    target_url=target,
                )
        return self._respond(request, post_id)

    def delete(self, request, post_id):
        post = get_visible_post(request.user, post_id)
        if not post:
            return error_response("POST_NOT_FOUND", "找不到這則貼文", 404)
        Like.objects.filter(post_id=post.id, user=request.user).delete()
        return self._respond(request, post_id)

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

        if post.user_id != request.user.id:
            Notification.objects.create(
                user=post.user, actor=request.user,
                notification_type='comment',
                message=f"{get_display_name(request.user)}回應了你的日記",
                target_url=f"/posts/{post.id}/",
            )

        serializer = CommentSerializer(comment, context={'request': request})
        return Response({"data": serializer.data}, status=status.HTTP_201_CREATED)