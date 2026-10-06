from django.contrib import admin

from .models import Diary, DiaryAnalysis


class DiaryAnalysisInline(admin.StackedInline):
    model = DiaryAnalysis
    extra = 0


@admin.register(Diary)
class DiaryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "created_at")
    search_fields = ("user__username", "user__last_name", "diary_text")
    list_select_related = ("user",)
    date_hierarchy = "created_at"
    inlines = [DiaryAnalysisInline]


@admin.register(DiaryAnalysis)
class DiaryAnalysisAdmin(admin.ModelAdmin):
    list_display = (
        "diary",
        "language_fluency",
        "logic_completeness",
        "emotion_description_completeness",
        "analysis_time",
    )
    list_select_related = ("diary__user",)
