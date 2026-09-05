from rest_framework.decorators import api_view
from rest_framework.response import Response
from users.models import User
from .models import Notification
from .serializers import NotificationSerializer


# 通知列表（需求文件未明確要求，依常見通知功能邏輯推測補上，待確認是否保留）
@api_view(['GET'])
def notification_list(request):
    user = User.objects.first()  # 目前還沒有登入驗證先取資料庫第一筆
    if user is None:
        return Response({"notification_list_error": "查無使用者"}, status=404)

    notifications = Notification.objects.filter(user=user).order_by('-created_at')
    serializer = NotificationSerializer(notifications, many=True)
    return Response({"notifications": serializer.data})


# 未讀通知數量（首頁API需求文件明確要求，給鈴鐺徽章用）
@api_view(['GET'])
def unread_count(request):
    user = User.objects.first()
    if user is None:
        return Response({"unread_count_error": "查無使用者"}, status=404)

    count = Notification.objects.filter(user=user, is_read=False).count()
    return Response({"unread_notification_count": count})


# 標記單一通知為已讀（需求文件未明確要求，依常見通知功能邏輯推測補上，待確認是否保留）
@api_view(['PATCH'])
def mark_as_read(request, notification_id):
    try:
        notification = Notification.objects.get(id=notification_id)
    except Notification.DoesNotExist:
        return Response({"mark_as_read_error": "查無此通知"}, status=404)

    notification.is_read = True
    notification.save()
    return Response({"message": "已標記為已讀"})