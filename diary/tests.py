from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Diary, DiaryReply, DiaryAnalysis
from unittest.mock import patch

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

class DiaryUploadEndpointTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='upload_tester', password='Str0ng!Pass2026')
        self.client.force_authenticate(user=self.user)

    @patch('diary.views.ai_gen.generate_first_question', return_value="這張照片有什麼故事呢？")
    @patch('diary.views.external.upload_to_firebase', return_value="https://fake-firebase-url.com/test.jpg")
    def test_upload_creates_diary_with_first_question(self, mock_upload, mock_question):
        photo = SimpleUploadedFile("test.jpg", b"content", content_type="image/jpeg")
        response = self.client.post(CALENDAR_URL, {'photo': photo}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['data']['first_question'], "這張照片有什麼故事呢？")
        self.assertEqual(response.data['data']['photo_url'], "https://fake-firebase-url.com/test.jpg")

    def test_upload_without_photo_returns_400(self):
        response = self.client.post(CALENDAR_URL, {}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_IMAGE')


class DiaryReplyEndpointTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='reply_tester', password='Str0ng!Pass2026')
        self.client.force_authenticate(user=self.user)
        self.diary = Diary.objects.create(user=self.user, status='pending', first_question="第一題")

    @patch('diary.views.ai_gen.generate_follow_up', return_value="還有嗎？")
    @patch('diary.views.external.transcribe_audio', return_value="今天天氣很好")
    @patch('diary.views.external.upload_to_firebase', return_value="https://fake-firebase-url.com/audio.wav")
    def test_reply_saves_transcript_and_returns_follow_up(self, mock_upload, mock_transcribe, mock_followup):
        audio = SimpleUploadedFile("test.wav", b"content", content_type="audio/wav")
        response = self.client.post(f'/api/diary/{self.diary.id}/replies/', {'audio': audio, 'round_index': 1}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['data']['transcript'], "今天天氣很好")
        self.assertEqual(response.data['data']['ai_reply'], "還有嗎？")
        self.assertFalse(response.data['data']['is_done'])

    def test_reply_to_finalized_diary_returns_400(self):
        self.diary.status = 'done'
        self.diary.save()
        audio = SimpleUploadedFile("test.wav", b"content", content_type="audio/wav")
        response = self.client.post(f'/api/diary/{self.diary.id}/replies/', {'audio': audio, 'round_index': 1}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'DIARY_ALREADY_FINALIZED')


class DiaryFinalizeEndpointTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='finalize_tester', password='Str0ng!Pass2026')
        self.client.force_authenticate(user=self.user)
        self.diary = Diary.objects.create(user=self.user, status='processing')
        DiaryReply.objects.create(diary=self.diary, round_index=1, transcript="我今天跟家人去公園散步，心情很開心")
        DiaryReply.objects.create(diary=self.diary, round_index=2, transcript="然後我們一起吃了午餐")

    @patch('diary.views.ai_gen.generate_finalize_content', return_value={
        "title": "公園散步", "ai_response": "聽起來真愉快！", "post_text": "今天去公園散步",
        "hashtags": ["#散步"], "category": "entertainment", "suggested_replies": ["真棒！"], "invite_text": "來看看吧",
    })
    def test_finalize_creates_analysis_and_returns_done(self, mock_content):
        response = self.client.post(f'/api/diary/{self.diary.id}/finalize/')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['data']['status'], 'done')
        self.assertEqual(response.data['data']['title'], "公園散步")
        self.assertTrue(DiaryAnalysis.objects.filter(diary=self.diary).exists())

    def test_finalize_without_any_reply_returns_400(self):
        empty_diary = Diary.objects.create(user=self.user, status='pending')
        response = self.client.post(f'/api/diary/{empty_diary.id}/finalize/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'NO_VALID_REPLY')