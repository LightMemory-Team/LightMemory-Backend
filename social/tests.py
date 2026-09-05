"""
System test：Notification API 端到端流程。

用 APIClient 打真實 URL，驗證前端實際會拿到的行為。

對應端點：
    GET   /api/social/notifications/
    GET   /api/social/notifications/unread_count/
    PATCH /api/social/notifications/<id>/read/

執行：
    python manage.py test social.tests --settings=config.settings_test
"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Notification

User = get_user_model()

LIST_URL = '/api/social/notifications/'
UNREAD_COUNT_URL = '/api/social/notifications/unread_count/'


def read_url(notification_id):
    return f'/api/social/notifications/{notification_id}/read/'


class NotificationListTests(APITestCase):
    """GET /api/social/notifications/"""

    def setUp(self):
        self.user = User.objects.create_user(username='wang_yulan', password='Str0ng!Pass2026')

    def test_list_returns_empty_when_no_notifications(self):
        response = self.client.get(LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'notifications': []})

    def test_list_returns_created_notification(self):
        Notification.objects.create(
            user=self.user,
            notification_type='like',
            message='小明對你的貼文按讚了',
            target_url='/posts/1',
        )

        response = self.client.get(LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['notifications']), 1)
        self.assertEqual(response.data['notifications'][0]['message'], '小明對你的貼文按讚了')
        self.assertEqual(response.data['notifications'][0]['notification_type_display'], '按讚')

    def test_list_orders_newest_first(self):
        first = Notification.objects.create(
            user=self.user, notification_type='comment', message='第一則'
        )
        second = Notification.objects.create(
            user=self.user, notification_type='comment', message='第二則'
        )

        response = self.client.get(LIST_URL)

        self.assertEqual(response.data['notifications'][0]['message'], '第二則')
        self.assertEqual(response.data['notifications'][1]['message'], '第一則')

    def test_list_returns_404_when_no_user_exists(self):
        User.objects.all().delete()

        response = self.client.get(LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class UnreadCountTests(APITestCase):
    """GET /api/social/notifications/unread_count/"""

    def setUp(self):
        self.user = User.objects.create_user(username='wang_yulan', password='Str0ng!Pass2026')

    def test_unread_count_returns_zero_when_no_notifications(self):
        response = self.client.get(UNREAD_COUNT_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['unread_notification_count'], 0)

    def test_unread_count_ignores_already_read_notifications(self):
        Notification.objects.create(
            user=self.user, notification_type='comment', message='未讀通知', is_read=False
        )
        Notification.objects.create(
            user=self.user, notification_type='comment', message='已讀通知', is_read=True
        )

        response = self.client.get(UNREAD_COUNT_URL)

        self.assertEqual(response.data['unread_notification_count'], 1)


class MarkAsReadTests(APITestCase):
    """PATCH /api/social/notifications/<id>/read/"""

    def setUp(self):
        self.user = User.objects.create_user(username='wang_yulan', password='Str0ng!Pass2026')
        self.notification = Notification.objects.create(
            user=self.user, notification_type='comment', message='測試通知', is_read=False
        )

    def test_mark_as_read_success(self):
        response = self.client.patch(read_url(self.notification.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)

    def test_mark_as_read_with_invalid_id_returns_404(self):
        response = self.client.patch(read_url(99999))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)