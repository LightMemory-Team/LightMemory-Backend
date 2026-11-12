from django.contrib import admin

from .models import PointTransaction, UserAchievement


@admin.register(PointTransaction)
class PointTransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "reason", "amount", "label", "created_at")
    list_filter = ("reason",)
    search_fields = ("user__username", "label", "source_id")


@admin.register(UserAchievement)
class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ("user", "code", "unlocked_at")
    search_fields = ("user__username", "code")
