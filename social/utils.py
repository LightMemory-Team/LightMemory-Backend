from django.conf import settings
from django.db.models import Count, Exists, OuterRef
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param

from .models import Like, Post


def get_display_name(user):
    full = f"{user.last_name}{user.first_name}".strip()
    return full or user.username


def author_dict(user):
    return {
        "user_id": user.id,
        "display_name": get_display_name(user),
        "avatar_url": user.avatar_url,
    }


def error_response(code, message, status=400):
    return Response({"error": {"code": code, "message": message}}, status=status)


def paginate(request, queryset, serialize, default_size=10, max_size=50):
    try:
        page = max(int(request.query_params.get("page", 1)), 1)
    except ValueError:
        page = 1
    try:
        size = min(max(int(request.query_params.get("page_size", default_size)), 1), max_size)
    except ValueError:
        size = default_size

    count = queryset.count()
    start = (page - 1) * size
    items = list(queryset[start:start + size])
    base = request.build_absolute_uri()
    return Response({
        "data": serialize(items),
        "pagination": {
            "count": count,
            "next": replace_query_param(base, "page", page + 1) if start + size < count else None,
            "previous": replace_query_param(base, "page", page - 1) if page > 1 else None,
        },
    })


def post_queryset(user):
    """所有看得到的貼文,並附上按讚數、留言數、我是否按讚。"""
    return (
        Post.objects.filter(is_enabled=True)
        .select_related("user", "diary")
        .annotate(
            like_total=Count("likes", distinct=True),
            comment_total=Count("comments", distinct=True),
            liked_by_me=Exists(Like.objects.filter(post=OuterRef("pk"), user=user)),
        )
    )


def get_visible_post(user, post_id):
    return post_queryset(user).filter(pk=post_id).first()


def serialize_post(post, viewer):
    diary = post.diary
    is_mine = post.user_id == viewer.id
    base_time = diary.created_at if diary else post.created_at
    share_url = f"{settings.SHARE_BASE_URL.rstrip('/')}/share/{post.share_token}/"
    return {
        "post_id": post.id,
        "post_type": post.post_type,
        "diary_id": post.diary_id,
        "author": author_dict(post.user),
        "is_mine": is_mine,
        "title": diary.title if diary else "",
        "photo_url": post.image_path,
        "post_text": post.content,
        "hashtags": diary.hashtags if diary else [],
        "category": diary.category if diary else "",
        "date": timezone.localtime(base_time).date().isoformat(),
        "posted_at": timezone.localtime(post.created_at).isoformat(),
        "like_count": post.like_total,
        "is_liked": post.liked_by_me,
        "comment_count": post.comment_total,
        "voice_reply_count": 0,
        "share_url": share_url if is_mine else None,
        "is_share_enabled": post.is_share_enabled if is_mine else None,
        "invite_text": (diary.invite_text if diary else "") if is_mine else "",
        "suggested_replies": diary.suggested_replies if diary else [],
    }