from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Diary

User = get_user_model()

CALENDAR_URL = '/api/diary/'


class DiaryCalendarEndpointTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='diary_tester', password='Str0ng!Pass2026')
        self.client.force_authenticate(user=self.user)

    def test_calendar_returns_done_diaries(self):
        Diary.objects.create(
            user=self.user, title="測試日記", status="done", post_text="內容",
        )
        response = self.client.get(CALENDAR_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']['diaries']), 1)
        self.assertTrue(response.data['data']['has_today_diary'])

    def test_pending_diary_not_included(self):
        Diary.objects.create(
            user=self.user, title="未完成", status="pending",
        )
        response = self.client.get(CALENDAR_URL)

        self.assertEqual(len(response.data['data']['diaries']), 0)
        self.assertFalse(response.data['data']['has_today_diary'])

    def test_unauthenticated_request_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(CALENDAR_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)