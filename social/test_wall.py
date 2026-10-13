from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Comment, Like, Notification, Post

User = get_user_model()


class WallApiTests(APITestCase):
    def setUp(self):
        self.a = User.objects.create_user(username='a', password='x', last_name='林', first_name='奶奶')
        self.b = User.objects.create_user(username='b', password='x')
        self.post = Post.objects.create(user=self.a, content='今天去逛花燈')
        self.hidden = Post.objects.create(user=self.a, content='停用', is_enabled=False)
        self.client.force_authenticate(self.b)

    def test_list_shows_all_enabled_posts(self):
        r = self.client.get('/api/social/posts/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['pagination']['count'], 1)
        item = r.data['data'][0]
        self.assertFalse(item['is_mine'])
        self.assertEqual(item['author']['display_name'], '林奶奶')
        self.assertIsNone(item['share_url'])

    def test_author_me_filter(self):
        r = self.client.get('/api/social/posts/?author=me')
        self.assertEqual(r.data['pagination']['count'], 0)
        self.client.force_authenticate(self.a)
        r = self.client.get('/api/social/posts/?author=me')
        self.assertEqual(r.data['pagination']['count'], 1)
        self.assertIsNotNone(r.data['data'][0]['share_url'])

    def test_detail_404_for_disabled_or_missing(self):
        self.assertEqual(self.client.get(f'/api/social/posts/{self.hidden.id}/').status_code, 404)
        self.assertEqual(self.client.get('/api/social/posts/9999/').status_code, 404)

    def test_like_is_idempotent_and_notifies_once(self):
        url = f'/api/social/posts/{self.post.id}/like/'
        self.assertEqual(self.client.post(url).data['data']['like_count'], 1)
        self.assertEqual(self.client.post(url).data['data']['like_count'], 1)
        self.client.delete(url)
        self.client.post(url)
        self.assertEqual(Like.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(notification_type='like').count(), 1)
        self.assertEqual(self.client.delete(url).data['data']['like_count'], 0)
        self.assertEqual(self.client.delete(url).status_code, 200)

    def test_author_like_own_post_no_notification(self):
        self.client.force_authenticate(self.a)
        self.client.post(f'/api/social/posts/{self.post.id}/like/')
        self.assertEqual(Notification.objects.count(), 0)

    def test_comment_validation_and_notification(self):
        url = f'/api/social/posts/{self.post.id}/comments/'
        self.assertEqual(self.client.post(url, {'text': ' '}).data['error']['code'], 'INVALID_TEXT')
        self.assertEqual(self.client.post(url, {'text': 'a' * 201}).status_code, 400)
        r = self.client.post(url, {'text': '好漂亮'})
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.data['data']['is_mine'])
        self.assertEqual(Notification.objects.filter(notification_type='comment').count(), 1)

    def test_any_user_can_list_comments(self):
        Comment.objects.create(post=self.post, user=self.a, content='謝謝')
        r = self.client.get(f'/api/social/posts/{self.post.id}/comments/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['pagination']['count'], 1)
        self.assertFalse(r.data['data'][0]['is_mine'])
    
    def test_delete_post_only_by_author(self):
        url = f'/api/social/posts/{self.post.id}/'
        r = self.client.delete(url)  # 目前登入的是 b,不是作者
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['error']['code'], 'NOT_POST_OWNER')

        Comment.objects.create(post=self.post, user=self.b, content='hi')
        Like.objects.create(post=self.post, user=self.b)
        self.client.force_authenticate(self.a)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(Post.objects.filter(pk=self.post.id).exists())
        self.assertEqual(Comment.objects.count(), 0)
        self.assertEqual(Like.objects.count(), 0)
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_delete_comment_permissions(self):
        other = User.objects.create_user(username='c', password='x')
        comment = Comment.objects.create(post=self.post, user=self.b, content='hi')
        url = f'/api/social/comments/{comment.id}/'

        self.client.force_authenticate(other)  # 不是留言者也不是貼文作者
        r = self.client.delete(url)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['error']['code'], 'NOT_ALLOWED')

        self.client.force_authenticate(self.a)  # 貼文作者可刪
        self.assertEqual(self.client.delete(url).status_code, 204)

        comment2 = Comment.objects.create(post=self.post, user=self.b, content='again')
        self.client.force_authenticate(self.b)  # 留言者本人可刪
        self.assertEqual(self.client.delete(f'/api/social/comments/{comment2.id}/').status_code, 204)

        r = self.client.delete(url)  # 已刪除,再刪回 404
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.data['error']['code'], 'COMMENT_NOT_FOUND')