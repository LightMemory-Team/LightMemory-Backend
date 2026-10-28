from django.contrib import admin

from .models import HealthDashboardRecord


@admin.register(HealthDashboardRecord)
class HealthDashboardRecordAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "report_type",
        "brain_age",
        "trend_alert_level",
        "generated_at",
    )
    list_filter = ("report_type", "trend_alert_level")
    search_fields = ("user__username", "user__last_name")
    list_select_related = ("user",)
