from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from diary.models import Diary
from social.models import Comment, Notification, Post

User = get_user_model()


class PublicShareTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='elder_lin',
            password='password123',
            last_name='林',
            first_name='奶奶',
        )
        self.diary = Diary.objects.create(
            user=self.user,
            title='陽台的花開了',
            post_text='今天早上看到陽台的牽牛花開得好漂亮。',
            image_path='https://example.com/flower.jpg',
            hashtags=['牽牛花', '好心情'],
            status='done',
        )
        self.post = Post.objects.create(
            user=self.user,
            diary=self.diary,
            content=self.diary.post_text,
            image_path=self.diary.image_path,
            is_enabled=True,
            is_share_enabled=True,
        )
        self.share_token = self.post.share_token

    @patch('public_share.views.render')
    def test_share_page_render_success(self, mock_render):
        """正常分享頁面載入，包含所有必要變數並呼叫 share.html 渲染"""
        from django.http import HttpResponse
        mock_render.return_value = HttpResponse("OK", status=200)

        url = f'/share/{self.share_token}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_render.assert_called_once()
        args, kwargs = mock_render.call_args
        self.assertEqual(args[1], 'public_share/share.html')
        context = args[2]
        self.assertIn('林奶奶', context['author_name'])
        self.assertEqual(context['title'], '陽台的花開了')
        self.assertEqual(context['photo_url'], 'https://example.com/flower.jpg')
        self.assertEqual(context['share_token'], self.share_token)
        self.assertEqual(context['hashtags'], ['牽牛花', '好心情'])

    @patch('public_share.views.render')
    def test_share_page_not_found_for_invalid_token(self, mock_render):
        """無效 token 呼叫 share_expired.html 並回傳 404"""
        from django.http import HttpResponse
        mock_render.return_value = HttpResponse("Not Found", status=404)

        url = '/share/non_existent_token_123/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        mock_render.assert_called_once()
        args, kwargs = mock_render.call_args
        self.assertEqual(args[1], 'public_share/share_expired.html')
        self.assertEqual(kwargs.get('status'), 404)

    @patch('public_share.views.render')
    def test_share_page_expired_when_disabled(self, mock_render):
        """當貼文停用或分享關閉時，呼叫 share_expired.html 並回傳 404"""
        from django.http import HttpResponse
        mock_render.return_value = HttpResponse("Not Found", status=404)

        self.post.is_share_enabled = False
        self.post.save()

        url = f'/share/{self.share_token}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        args, kwargs = mock_render.call_args
        self.assertEqual(args[1], 'public_share/share_expired.html')
        self.assertEqual(kwargs.get('status'), 404)

        # 貼文停用
        mock_render.reset_mock()
        self.post.is_share_enabled = True
        self.post.is_enabled = False
        self.post.save()

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        args, kwargs = mock_render.call_args
        self.assertEqual(args[1], 'public_share/share_expired.html')
        self.assertEqual(kwargs.get('status'), 404)

    def test_public_comment_success(self):
        """親友免登入成功留言，回傳 201 與標準格式，並建立 Notification"""
        url = f'/api/share/{self.share_token}/comments/'
        payload = {
            'nickname': '小玲',
            'content': '花真的好美喔，奶奶好棒！',
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        res_data = response.json()
        self.assertTrue(res_data['success'])
        self.assertIsNone(res_data['error'])
        self.assertEqual(res_data['data']['nickname'], '小玲')
        self.assertEqual(res_data['data']['content'], '花真的好美喔，奶奶好棒！')
        self.assertIn('comment_id', res_data['data'])
        self.assertIn('created_at', res_data['data'])

        # 驗證資料庫建立
        comment = Comment.objects.get(id=res_data['data']['comment_id'])
        self.assertEqual(comment.nickname, '小玲')
        self.assertIsNone(comment.user)
        self.assertEqual(comment.post, self.post)

        # 驗證通知建立
        notification = Notification.objects.filter(user=self.user, notification_type='comment').first()
        self.assertIsNotNone(notification)
        self.assertIn('小玲', notification.message)
        self.assertIsNone(notification.actor)

    def test_public_comment_invalid_nickname(self):
        """暱稱空白或超過 12 字回傳 400 INVALID_NICKNAME"""
        url = f'/api/share/{self.share_token}/comments/'

        # 空白暱稱
        r1 = self.client.post(url, {'nickname': '  ', 'content': '很漂亮'}, format='json')
        self.assertEqual(r1.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r1.json()['error']['code'], 'INVALID_NICKNAME')

        # 超過 12 字
        r2 = self.client.post(url, {'nickname': '我是小玲我是小玲我是小玲我是小玲', 'content': '很漂亮'}, format='json')
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r2.json()['error']['code'], 'INVALID_NICKNAME')

    def test_public_comment_invalid_content(self):
        """留言空白或超過 200 字回傳 400 INVALID_CONTENT"""
        url = f'/api/share/{self.share_token}/comments/'

        # 空白內容
        r1 = self.client.post(url, {'nickname': '小玲', 'content': '   '}, format='json')
        self.assertEqual(r1.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r1.json()['error']['code'], 'INVALID_CONTENT')

        # 超過 200 字
        r2 = self.client.post(url, {'nickname': '小玲', 'content': '好' * 201}, format='json')
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r2.json()['error']['code'], 'INVALID_CONTENT')

    def test_public_comment_expired_or_invalid_share_token(self):
        """分享無效時留言回傳 404 SHARE_NOT_FOUND"""
        url = '/api/share/invalid_token/comments/'
        r = self.client.post(url, {'nickname': '小玲', 'content': '讚'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(r.json()['error']['code'], 'SHARE_NOT_FOUND')

        # 分享停用
        self.post.is_share_enabled = False
        self.post.save()
        r2 = self.client.post(f'/api/share/{self.share_token}/comments/', {'nickname': '小玲', 'content': '讚'}, format='json')
        self.assertEqual(r2.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(r2.json()['error']['code'], 'SHARE_NOT_FOUND')

    def test_public_comment_rate_limiting(self):
        """留言頻率超過上限回傳 429 TOO_MANY_REQUESTS"""
        url = f'/api/share/{self.share_token}/comments/'
        cache_key = 'share_comment_rate:127.0.0.1'
        cache.set(cache_key, 10, timeout=60)

        response = self.client.post(
            url,
            {'nickname': '小玲', 'content': '測試灌水'},
            format='json',
            REMOTE_ADDR='127.0.0.1'
        )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.json()['error']['code'], 'TOO_MANY_REQUESTS')

    def test_post_author_can_manage_public_comment(self):
        """貼文作者可以在動態牆看到親友留言並執行刪除"""
        # 1. 親友公開留言
        comment = Comment.objects.create(
            post=self.post,
            user=None,
            nickname='孫子小明',
            content='奶奶好棒！',
        )

        # 2. 長輩登入查看貼文留言
        self.client.force_authenticate(user=self.user)
        r = self.client.get(f'/api/social/posts/{self.post.id}/comments/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        data = r.json()['data']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['text'], '奶奶好棒！')
        self.assertFalse(data[0]['is_mine'])

        # 3. 貼文作者刪除留言
        comment_id = data[0]['comment_id']
        del_res = self.client.delete(f'/api/social/comments/{comment_id}/')
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Comment.objects.filter(id=comment.id).exists())

