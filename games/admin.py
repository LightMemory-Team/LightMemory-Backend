from django.contrib import admin

from .models import Game, GameCategory, GameRecord, GameSession, GameStepLog

USER_SEARCH_FIELDS = ("user__username", "user__last_name")


@admin.register(GameCategory)
class GameCategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "category_name", "category_description")


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "default_difficulty", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("code", "name")
    list_select_related = ("category",)


class GameStepLogInline(admin.TabularInline):
    """在 GameSession 頁面直接看到這場的每一步作答紀錄（唯讀）。"""

    model = GameStepLog
    extra = 0
    can_delete = False
    ordering = ("step_number",)
    fields = ("step_number", "is_correct", "response_time_ms", "detail")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "game",
        "user",
        "status",
        "is_pretest",
        "question_number",
        "created_at",
        "finished_at",
    )
    list_filter = ("game", "status", "is_pretest")
    search_fields = ("client_session_id", *USER_SEARCH_FIELDS)
    list_select_related = ("game", "user")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    # 遊戲過程由 API 寫入，JSON 欄位設成唯讀，避免在後台手動改壞
    readonly_fields = (
        "id",
        "current_question",
        "state",
        "result",
        "created_at",
        "updated_at",
    )
    inlines = [GameStepLogInline]


@admin.register(GameStepLog)
class GameStepLogAdmin(admin.ModelAdmin):
    list_display = ("session", "step_number", "is_correct", "response_time_ms")
    list_filter = ("session__game", "is_correct")
    list_select_related = ("session__game", "session__user")


@admin.register(GameRecord)
class GameRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "game", "score", "accuracy", "difficulty", "played_at")
    list_filter = ("game", "difficulty")
    search_fields = USER_SEARCH_FIELDS
    list_select_related = ("user", "game")
