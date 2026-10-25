from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Comment, Notification, Post

User = get_user_model()


class WallApiTests(APITestCase):
    def setUp(self):
        self.a = User.objects.create_user(username='a', password='x', last_name='林', first_name='奶奶')
        self.b = User.objects.create_user(username='b', password='x')
        self.post = Post.objects.create(user=self.a, content='今天去逛花燈')
        self.hidden = Post.objects.create(user=self.a, content='停用', is_enabled=False)
        self.b_post = Post.objects.create(user=self.b, content='別人的貼文')
        self.client.force_authenticate(self.a)

    def test_list_shows_only_my_enabled_posts(self):
        r = self.client.get('/api/social/posts/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['pagination']['count'], 1)
        item = r.data['data'][0]
        self.assertEqual(item['post_id'], self.post.id)
        self.assertTrue(item['is_mine'])
        self.assertIsNotNone(item['share_url'])
        self.assertNotIn('like_count', item)
        self.assertNotIn('is_liked', item)

    def test_other_user_cannot_see_or_touch_my_post(self):
        self.client.force_authenticate(self.b)
        r = self.client.get('/api/social/posts/')
        self.assertEqual([p['post_id'] for p in r.data['data']], [self.b_post.id])
        self.assertEqual(self.client.get(f'/api/social/posts/{self.post.id}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/social/posts/{self.post.id}/comments/').status_code, 404)
        self.assertEqual(
            self.client.post(f'/api/social/posts/{self.post.id}/comments/', {'text': 'hi'}).status_code, 404)
        self.assertEqual(self.client.delete(f'/api/social/posts/{self.post.id}/').status_code, 404)
        self.assertTrue(Post.objects.filter(pk=self.post.id).exists())

    def test_detail_404_for_disabled_or_missing(self):
        self.assertEqual(self.client.get(f'/api/social/posts/{self.hidden.id}/').status_code, 404)
        self.assertEqual(self.client.get('/api/social/posts/9999/').status_code, 404)

    def test_like_endpoint_removed(self):
        url = f'/api/social/posts/{self.post.id}/like/'
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_comment_validation_and_anonymous(self):
        url = f'/api/social/posts/{self.post.id}/comments/'
        self.assertEqual(self.client.post(url, {'text': ' '}).data['error']['code'], 'INVALID_TEXT')
        self.assertEqual(self.client.post(url, {'text': 'a' * 201}).status_code, 400)
        r = self.client.post(url, {'text': '好漂亮'})
        self.assertEqual(r.status_code, 201)
        data = r.data['data']
        self.assertEqual(data['text'], '好漂亮')
        self.assertEqual(data['sender_name'], '匿名')
        self.assertNotIn('author', data)
        self.assertTrue(data['is_mine'])
        self.assertEqual(Notification.objects.count(), 0)

    def test_comment_list_hides_commenter_names(self):
        Comment.objects.create(post=self.post, user=self.a, content='謝謝')
        Comment.objects.create(post=self.post, user=self.b, content='早期留言')
        r = self.client.get(f'/api/social/posts/{self.post.id}/comments/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['pagination']['count'], 2)
        for item in r.data['data']:
            self.assertEqual(item['sender_name'], '匿名')
            self.assertNotIn('author', item)
        self.assertEqual([c['is_mine'] for c in r.data['data']], [True, False])

    def test_delete_post_removes_comments(self):
        url = f'/api/social/posts/{self.post.id}/'
        Comment.objects.create(post=self.post, user=self.a, content='hi')
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(Post.objects.filter(pk=self.post.id).exists())
        self.assertEqual(Comment.objects.count(), 0)
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_delete_comment_only_by_post_author(self):
        comment = Comment.objects.create(post=self.post, user=self.a, content='hi')
        url = f'/api/social/comments/{comment.id}/'

        self.client.force_authenticate(self.b)  # 不是貼文作者,看不到這則留言
        r = self.client.delete(url)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.data['error']['code'], 'COMMENT_NOT_FOUND')
        self.assertTrue(Comment.objects.filter(pk=comment.id).exists())

        self.client.force_authenticate(self.a)  # 貼文作者可刪
        self.assertEqual(self.client.delete(url).status_code, 204)

        r = self.client.delete(url)  # 已刪除,再刪回 404
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.data['error']['code'], 'COMMENT_NOT_FOUND')