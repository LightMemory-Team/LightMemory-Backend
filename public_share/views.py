from django.core.cache import cache
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from social.models import Comment, Notification, Post
from social.utils import get_display_name


def get_client_ip(request):
    """取得請求端的真實 IP，支援反向代理 / Cloudflare Tunnel (HTTP_X_FORWARDED_FOR)"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or 'unknown'


class SharePageView(View):
    """
    親友公開分享頁
    GET /share/<share_token>/
    回傳 HTML。若 token 不存在或分享已失效，回傳 404 及失效頁面。
    """

    def get(self, request, share_token):
        post = (
            Post.objects.filter(share_token=share_token)
            .select_related('user', 'diary')
            .first()
        )

        if not post or not post.is_enabled or not post.is_share_enabled:
            return render(request, 'public_share/share_expired.html', status=404)

        diary = post.diary
        base_time = diary.created_at if diary else post.created_at
        date_str = timezone.localtime(base_time).date().isoformat()
        photo_url = post.image_path or (diary.image_path if diary else '')
        title = (diary.title if diary and diary.title else '')
        hashtags = diary.hashtags if (diary and isinstance(diary.hashtags, list)) else []

        context = {
            'share_token': post.share_token,
            'author_name': get_display_name(post.user),
            'date': date_str,
            'photo_url': photo_url,
            'title': title,
            'post_text': post.content,
            'hashtags': hashtags,
        }

        return render(request, 'public_share/share.html', context)


class PublicShareCommentView(APIView):
    """
    親友公開留言 API
    POST /api/share/<share_token>/comments/
    免登入、無 SessionAuthentication / CSRF 限制，支援同 IP 頻率限制 (429)。
    """
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    RATE_LIMIT_COUNT = 10  # 每分鐘同 IP 最多 10 則
    RATE_LIMIT_SECONDS = 60

    def post(self, request, share_token):
        # 1. IP 頻率限制檢查 (防灌水)
        ip = get_client_ip(request)
        cache_key = f"share_comment_rate:{ip}"
        current_count = cache.get(cache_key, 0)
        if current_count >= self.RATE_LIMIT_COUNT:
            return Response(
                {
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "TOO_MANY_REQUESTS",
                        "message": "送出太過頻繁，請稍後再試",
                    },
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # 2. 貼文有效性檢查
        post = (
            Post.objects.filter(share_token=share_token)
            .select_related('user')
            .first()
        )
        if not post or not post.is_enabled or not post.is_share_enabled:
            return Response(
                {
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "SHARE_NOT_FOUND",
                        "message": "分享已失效",
                    },
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # 3. 欄位驗證
        nickname = request.data.get('nickname')
        content = request.data.get('content')

        if not isinstance(nickname, str):
            nickname = ''
        nickname = nickname.strip()
        if not (1 <= len(nickname) <= 12):
            return Response(
                {
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "INVALID_NICKNAME",
                        "message": "暱稱需介於 1 至 12 字",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(content, str):
            content = ''
        content_stripped = content.strip()
        if not content_stripped or len(content) > 200:
            return Response(
                {
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "INVALID_CONTENT",
                        "message": "留言不可空白，上限 200 字",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4. 建立留言
        comment = Comment.objects.create(
            post=post,
            user=None,
            nickname=nickname,
            content=content_stripped,
        )

        # 5. 計數 + 1 更新 Cache
        cache.set(cache_key, current_count + 1, timeout=self.RATE_LIMIT_SECONDS)

        # 6. 為長輩建立通知
        Notification.objects.create(
            user=post.user,
            actor=None,
            notification_type='comment',
            message=f"{nickname} 在你的日記留言了",
            target_url=f"/posts/{post.id}/",
        )

        # 7. 回傳 201 成功回應
        return Response(
            {
                "success": True,
                "data": {
                    "comment_id": comment.id,
                    "nickname": comment.nickname,
                    "content": comment.content,
                    "created_at": timezone.localtime(comment.created_at).isoformat(),
                },
                "error": None,
            },
            status=status.HTTP_201_CREATED,
        )
