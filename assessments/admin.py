from django.contrib import admin

from .models import Ad8Record


@admin.register(Ad8Record)
class Ad8RecordAdmin(admin.ModelAdmin):
    list_display = ("user", "total_score", "result_description", "completed_at")
    search_fields = ("user__username", "user__last_name")
    list_select_related = ("user",)
