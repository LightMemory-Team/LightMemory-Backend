from django.contrib import admin

from .models import Comment, Like, Notification, Post

USER_SEARCH_FIELDS = ("user__username", "user__last_name")


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "created_at", "is_enabled")
    list_filter = ("is_enabled",)
    search_fields = ("content", *USER_SEARCH_FIELDS)
    list_select_related = ("user",)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "user", "created_at")
    search_fields = ("content", *USER_SEARCH_FIELDS)
    list_select_related = ("post__user", "user")


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ("post", "user", "created_at")
    list_select_related = ("post__user", "user")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "actor", "notification_type", "is_read", "created_at")
    list_filter = ("notification_type", "is_read")
    search_fields = ("message", *USER_SEARCH_FIELDS)
    list_select_related = ("user", "actor")
