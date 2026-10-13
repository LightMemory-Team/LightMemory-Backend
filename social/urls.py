from django.urls import path

from . import views
from .views import (PostCommentsView, PostDetailView, PostLikeView, PostListView, CommentDeleteView)

urlpatterns = [
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/unread_count/', views.unread_count, name='unread_count'),
    path('notifications/<int:notification_id>/read/', views.mark_as_read, name='mark_as_read'),
    path('posts/', PostListView.as_view(), name='post_list'),
    path('posts/<int:post_id>/', PostDetailView.as_view(), name='post_detail'),
    path('posts/<int:post_id>/like/', PostLikeView.as_view(), name='post_like'),
    path('posts/<int:post_id>/comments/', PostCommentsView.as_view(), name='post_comments'),
    path('comments/<int:comment_id>/', CommentDeleteView.as_view(), name='comment_delete'),
]