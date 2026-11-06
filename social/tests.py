"""
System test：Notification API 端到端流程。

用 APIClient 打真實 URL，完整經過 URL routing、middleware、
認證與序列化，驗證前端實際會拿到的行為。

對應端點：
    GET   /api/social/notifications/
    GET   /api/social/notifications/unread_count/
    PATCH /api/social/notifications/            （全部標為已讀）
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
        self.client.force_authenticate(user=self.user)

    def test_list_returns_empty_when_no_notifications(self):
        response = self.client.get(LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data, {'success': True, 'data': {'notifications': []}, 'error': None}
        )

    def test_list_returns_created_notification(self):
        Notification.objects.create(
            user=self.user,
            notification_type='like',
            message='小明對你的貼文按讚了',
            target_url='/posts/1',
        )

        response = self.client.get(LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIsNone(response.data['error'])
        notifications = response.data['data']['notifications']
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]['message'], '小明對你的貼文按讚了')
        self.assertEqual(notifications[0]['notification_type_display'], '按讚')

    def test_list_orders_newest_first(self):
        Notification.objects.create(
            user=self.user, notification_type='comment', message='第一則'
        )
        Notification.objects.create(
            user=self.user, notification_type='comment', message='第二則'
        )

        response = self.client.get(LIST_URL)

        notifications = response.data['data']['notifications']
        self.assertEqual(notifications[0]['message'], '第二則')
        self.assertEqual(notifications[1]['message'], '第一則')

    def test_list_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UnreadCountTests(APITestCase):
    """GET /api/social/notifications/unread_count/"""

    def setUp(self):
        self.user = User.objects.create_user(username='wang_yulan', password='Str0ng!Pass2026')
        self.client.force_authenticate(user=self.user)

    def test_unread_count_returns_zero_when_no_notifications(self):
        response = self.client.get(UNREAD_COUNT_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['unread_notification_count'], 0)

    def test_unread_count_ignores_already_read_notifications(self):
        Notification.objects.create(
            user=self.user, notification_type='comment', message='未讀通知', is_read=False
        )
        Notification.objects.create(
            user=self.user, notification_type='comment', message='已讀通知', is_read=True
        )

        response = self.client.get(UNREAD_COUNT_URL)

        self.assertEqual(response.data['data']['unread_notification_count'], 1)


class MarkAsReadTests(APITestCase):
    """PATCH /api/social/notifications/<id>/read/"""

    def setUp(self):
        self.user = User.objects.create_user(username='wang_yulan', password='Str0ng!Pass2026')
        self.client.force_authenticate(user=self.user)
        self.notification = Notification.objects.create(
            user=self.user, notification_type='comment', message='測試通知', is_read=False
        )

    def test_mark_as_read_success(self):
        response = self.client.patch(read_url(self.notification.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {'success': True, 'data': {'message': '已標記為已讀'}, 'error': None},
        )
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)

    def test_mark_as_read_with_invalid_id_returns_404(self):
        response = self.client.patch(read_url(99999))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data,
            {
                'success': False,
                'data': None,
                'error': {'code': 'NOTIFICATION_NOT_FOUND', 'message': '查無此通知'},
            },
        )

    def test_cannot_mark_other_users_notification(self):
        other = User.objects.create_user(username='other', password='Str0ng!Pass2026')
        theirs = Notification.objects.create(
            user=other, notification_type='comment', message='別人的通知'
        )

        response = self.client.patch(read_url(theirs.id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        theirs.refresh_from_db()
        self.assertFalse(theirs.is_read)


class MarkAllAsReadTests(APITestCase):
    """PATCH /api/social/notifications/（全部已讀）"""

    def setUp(self):
        self.user = User.objects.create_user(username='wang_yulan', password='Str0ng!Pass2026')
        self.other = User.objects.create_user(username='other', password='Str0ng!Pass2026')
        self.client.force_authenticate(user=self.user)

    def make(self, user, is_read=False):
        return Notification.objects.create(
            user=user, notification_type='comment', message='有人留言', is_read=is_read
        )

    def test_marks_all_own_unread_notifications_as_read(self):
        self.make(self.user)
        self.make(self.user)
        self.make(self.user, is_read=True)

        response = self.client.patch(LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {'success': True, 'data': {'message': '已全部標記為已讀'}, 'error': None},
        )
        self.assertFalse(Notification.objects.filter(user=self.user, is_read=False).exists())

    def test_unread_count_becomes_zero(self):
        self.make(self.user)

        self.client.patch(LIST_URL)
        response = self.client.get(UNREAD_COUNT_URL)

        self.assertEqual(response.data['data'], {'unread_notification_count': 0})

    def test_does_not_touch_other_users_notifications(self):
        mine = self.make(self.user)
        theirs = self.make(self.other)

        self.client.patch(LIST_URL)

        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertTrue(mine.is_read)
        self.assertFalse(theirs.is_read)

    def test_works_when_there_is_nothing_unread(self):
        response = self.client.patch(LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.patch(LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_still_works_after_marking_all_read(self):
        self.make(self.user)

        self.client.patch(LIST_URL)
        response = self.client.get(LIST_URL)

        notifications = response.data['data']['notifications']
        self.assertEqual(len(notifications), 1)
        self.assertTrue(notifications[0]['is_read'])
