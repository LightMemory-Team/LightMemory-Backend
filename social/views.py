from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from users.models import User
from .models import Notification
from .serializers import NotificationSerializer

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import Post, Comment, Notification
from .serializers import CommentSerializer


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

class PostCommentsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, post_id):
        try:
            post = Post.objects.get(id=post_id)
        except Post.DoesNotExist:
            return Response({"error": {"code": "POST_NOT_FOUND", "message": "找不到這則貼文"}}, status=404)

        if post.user != request.user:
            return Response({"error": {"code": "POST_NOT_FOUND", "message": "找不到這則貼文"}}, status=404)

        comments = post.comments.order_by('created_at')
        serializer = CommentSerializer(comments, many=True)
        return Response({
            "data": serializer.data,
            "pagination": {"count": comments.count(), "next": None, "previous": None},
        })

    def post(self, request, post_id):
        try:
            post = Post.objects.get(id=post_id)
        except Post.DoesNotExist:
            return Response({"error": {"code": "POST_NOT_FOUND", "message": "找不到這則貼文"}}, status=404)

        text = request.data.get('text', '').strip()
        if not text or len(text) > 200:
            return Response({"error": {"code": "INVALID_TEXT", "message": "留言不可為空，且不超過200字"}}, status=400)

        comment = Comment.objects.create(post=post, user=request.user, content=text)

        if post.user != request.user:
            Notification.objects.create(
                user=post.user, actor=request.user,
                notification_type='comment', message="有人回應了你的日記",
                target_url=f"/posts/{post.id}/",
            )

        serializer = CommentSerializer(comment)
        return Response({"data": serializer.data}, status=status.HTTP_201_CREATED)