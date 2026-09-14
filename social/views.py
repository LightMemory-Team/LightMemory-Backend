from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from users.models import User
from .models import Notification
from .serializers import NotificationSerializer


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