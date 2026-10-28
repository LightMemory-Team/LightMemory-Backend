from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from social.models import Post
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


class DiaryShareEndpointTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='share_tester', password='Str0ng!Pass2026')
        self.other_user = User.objects.create_user(username='other_tester', password='Str0ng!Pass2026')
        self.client.force_authenticate(user=self.user)
        self.done_diary = Diary.objects.create(
            user=self.user,
            status='done',
            title='今天逛花燈',
            post_text='跟朋友去逛花燈很開心',
            image_path='https://example.com/lamp.jpg',
            hashtags=['#花燈'],
            category='entertainment',
            invite_text='來看看花燈吧',
            suggested_replies=['花燈真漂亮'],
        )
        self.pending_diary = Diary.objects.create(
            user=self.user,
            status='pending',
            title='未完成日記',
        )

    def test_share_creates_post_and_returns_201(self):
        url = f'/api/diary/{self.done_diary.id}/share/'
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data['data']
        self.assertEqual(data['diary_id'], self.done_diary.id)
        self.assertEqual(data['title'], '今天逛花燈')
        self.assertEqual(data['post_text'], '跟朋友去逛花燈很開心')
        self.assertEqual(data['photo_url'], 'https://example.com/lamp.jpg')
        self.assertEqual(data['post_type'], 'diary')
        self.assertTrue(data['is_mine'])
        self.assertTrue(data['is_share_enabled'])
        self.assertIsNotNone(data['share_url'])
        self.assertIn('/share/', data['share_url'])
        self.assertEqual(data['comment_count'], 0)

        # 驗證資料庫確實建立 Post
        post = Post.objects.get(diary=self.done_diary)
        self.assertEqual(post.user, self.user)
        self.assertEqual(post.content, self.done_diary.post_text)

    def test_share_already_shared_returns_200_and_same_post(self):
        url = f'/api/diary/{self.done_diary.id}/share/'
        res1 = self.client.post(url)
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        post_id1 = res1.data['data']['post_id']

        # 第二次分享
        res2 = self.client.post(url)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        post_id2 = res2.data['data']['post_id']
        self.assertEqual(post_id1, post_id2)
        self.assertEqual(Post.objects.filter(diary=self.done_diary).count(), 1)

    def test_share_undone_diary_returns_400(self):
        url = f'/api/diary/{self.pending_diary.id}/share/'
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'DIARY_NOT_DONE')

    def test_share_other_user_diary_returns_404(self):
        other_diary = Diary.objects.create(
            user=self.other_user,
            status='done',
            title='別人的日記',
        )
        url = f'/api/diary/{other_diary.id}/share/'
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error']['code'], 'DIARY_NOT_FOUND')

    def test_share_nonexistent_diary_returns_404(self):
        url = '/api/diary/99999/share/'
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error']['code'], 'DIARY_NOT_FOUND')

    def test_share_requires_authentication(self):
        self.client.force_authenticate(user=None)
        url = f'/api/diary/{self.done_diary.id}/share/'
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class DiaryDetailEndpointTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='detail_tester', password='Str0ng!Pass2026')
        self.other_user = User.objects.create_user(username='other_detail_tester', password='Str0ng!Pass2026')
        self.client.force_authenticate(user=self.user)
        self.diary = Diary.objects.create(
            user=self.user,
            status='done',
            title='花燈圈圈樂 ✨',
            image_path='https://example.com/lamp.jpg',
            first_question='今天去哪玩呢？',
            pending_question='還有遇到誰嗎？',
            post_text='這個週末跟朋友去逛花燈，玩得很開心。',
            hashtags=['#花燈', '#朋友聚會'],
            category='entertainment',
            invite_text='來看看她說了什麼吧！',
            ai_response='真是有趣的一天！',
        )
        self.reply1 = DiaryReply.objects.create(
            diary=self.diary,
            round_index=1,
            question='今天去哪玩呢？',
            transcript='我去逛花燈',
            audio_path='https://example.com/audio1.mp3',
            is_skipped=False,
        )
        self.reply2 = DiaryReply.objects.create(
            diary=self.diary,
            round_index=2,
            question='還有遇到誰嗎？',
            transcript='',
            audio_path='',
            is_skipped=True,
        )

    def test_detail_unshared_diary_returns_all_fields(self):
        url = f'/api/diary/{self.diary.id}/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(data['diary_id'], self.diary.id)
        self.assertEqual(data['title'], '花燈圈圈樂 ✨')
        self.assertEqual(data['status'], 'done')
        self.assertEqual(data['photo_url'], 'https://example.com/lamp.jpg')
        self.assertEqual(data['first_question'], '今天去哪玩呢？')
        self.assertEqual(data['pending_question'], '還有遇到誰嗎？')
        self.assertEqual(data['reply_count'], 2)
        self.assertFalse(data['is_finalizable'])  # non_skipped = 1 < 2
        self.assertTrue(data['is_done'])
        self.assertEqual(len(data['replies']), 2)
        self.assertEqual(data['replies'][0]['round_index'], 1)
        self.assertEqual(data['replies'][0]['audio_url'], 'https://example.com/audio1.mp3')
        self.assertFalse(data['replies'][0]['is_skipped'])
        self.assertTrue(data['replies'][1]['is_skipped'])

        # 未分享狀態驗證
        self.assertFalse(data['is_shared'])
        self.assertIsNone(data['post_id'])
        self.assertIsNone(data['share_url'])
        self.assertEqual(data['invite_text'], '來看看她說了什麼吧！')
        self.assertIsNotNone(data['date'])
        self.assertIsNotNone(data['created_at'])

    def test_detail_shared_diary_includes_post_info(self):
        post = Post.objects.create(
            user=self.user,
            diary=self.diary,
            content=self.diary.post_text,
            image_path=self.diary.image_path,
            post_type='diary',
        )
        url = f'/api/diary/{self.diary.id}/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertTrue(data['is_shared'])
        self.assertEqual(data['post_id'], post.id)
        self.assertIsNotNone(data['share_url'])
        self.assertIn(post.share_token, data['share_url'])

    def test_detail_other_user_diary_returns_404(self):
        other_diary = Diary.objects.create(user=self.other_user, title='別人的日記')
        url = f'/api/diary/{other_diary.id}/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error']['code'], 'DIARY_NOT_FOUND')

    def test_detail_nonexistent_returns_404(self):
        url = '/api/diary/99999/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error']['code'], 'DIARY_NOT_FOUND')

    def test_detail_requires_authentication(self):
        self.client.force_authenticate(user=None)
        url = f'/api/diary/{self.diary.id}/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class DiaryReviewEndpointTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='review_tester', password='Str0ng!Pass2026')
        self.other_user = User.objects.create_user(username='other_review_tester', password='Str0ng!Pass2026')
        self.client.force_authenticate(user=self.user)
        self.url = '/api/diary/review/'

    def test_review_returns_yesterday_and_last_year_diaries(self):
        today = timezone.localdate()
        yesterday_dt = timezone.now() - timedelta(days=1)
        try:
            last_year_dt = timezone.now().replace(year=today.year - 1)
        except ValueError:
            last_year_dt = timezone.now().replace(year=today.year - 1, day=28)

        # 昨天的日記（已分享）
        d_yesterday = Diary.objects.create(
            user=self.user,
            status='done',
            title='昨天的日記',
            post_text='昨天玩得很開心',
            image_path='https://example.com/photo1.jpg',
        )
        Diary.objects.filter(id=d_yesterday.id).update(created_at=yesterday_dt)
        DiaryReply.objects.create(
            diary=d_yesterday,
            round_index=1,
            transcript='第一輪逐字稿',
            audio_path='https://example.com/audio_yesterday.mp3',
        )
        post = Post.objects.create(
            user=self.user,
            diary=d_yesterday,
            content=d_yesterday.post_text,
            image_path=d_yesterday.image_path,
        )

        # 去年的日記（未分享）
        d_last_year = Diary.objects.create(
            user=self.user,
            status='done',
            title='去年的日記',
            post_text='去年的這一天',
            image_path='https://example.com/photo2.jpg',
        )
        Diary.objects.filter(id=d_last_year.id).update(created_at=last_year_dt)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']

        # 驗證昨天
        self.assertEqual(len(data['yesterday']), 1)
        item_y = data['yesterday'][0]
        self.assertEqual(item_y['diary_id'], d_yesterday.id)
        self.assertEqual(item_y['title'], '昨天的日記')
        self.assertEqual(item_y['audio_url'], 'https://example.com/audio_yesterday.mp3')
        self.assertTrue(item_y['is_shared'])
        self.assertEqual(item_y['post_id'], post.id)

        # 驗證去年
        self.assertEqual(len(data['last_year']), 1)
        item_ly = data['last_year'][0]
        self.assertEqual(item_ly['diary_id'], d_last_year.id)
        self.assertEqual(item_ly['title'], '去年的日記')
        self.assertIsNone(item_ly['audio_url'])
        self.assertFalse(item_ly['is_shared'])
        self.assertIsNone(item_ly['post_id'])

    def test_review_returns_empty_arrays_when_no_diaries(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['yesterday'], [])
        self.assertEqual(response.data['data']['last_year'], [])

    def test_review_excludes_undone_diaries(self):
        yesterday_dt = timezone.now() - timedelta(days=1)
        d = Diary.objects.create(user=self.user, status='pending', title='未完成的日記')
        Diary.objects.filter(id=d.id).update(created_at=yesterday_dt)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['yesterday'], [])

    def test_review_excludes_other_users_diaries(self):
        yesterday_dt = timezone.now() - timedelta(days=1)
        d = Diary.objects.create(user=self.other_user, status='done', title='別人的日記')
        Diary.objects.filter(id=d.id).update(created_at=yesterday_dt)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['yesterday'], [])

    def test_review_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
