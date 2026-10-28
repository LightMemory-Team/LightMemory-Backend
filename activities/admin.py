from django.contrib import admin

from .models import ActivityRecord, HealthInformation


@admin.register(HealthInformation)
class HealthInformationAdmin(admin.ModelAdmin):
    list_display = (
        "activity_name",
        "activity_type",
        "activity_region",
        "start_time",
        "end_time",
        "fee",
    )
    list_filter = ("activity_type", "activity_region")
    search_fields = ("activity_name", "activity_location")


@admin.register(ActivityRecord)
class ActivityRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "activity", "status", "recorded_at", "is_enabled")
    list_filter = ("status", "is_enabled")
    search_fields = ("user__username", "user__last_name", "activity__activity_name")
    list_select_related = ("user", "activity")
