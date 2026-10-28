import uuid

from django.conf import settings
from django.db import models

from users.models import User


class GameCategory(models.Model):
    category_name = models.CharField(max_length=50)
    category_description = models.TextField(blank=True)

    def __str__(self):
        return self.category_name


class Game(models.Model):
    DIFFICULTY_CHOICES = [
        ("basic", "初階"),
        ("intermediate", "中階"),
        ("advanced", "進階"),
    ]

    category = models.ForeignKey(
        GameCategory, on_delete=models.CASCADE, related_name="games"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    default_difficulty = models.CharField(
        max_length=20, choices=DIFFICULTY_CHOICES, blank=True
    )
    is_active = models.BooleanField(default=True)
    code = models.CharField(max_length=50, unique=True)  # 例如 "market_route"

    def __str__(self):
        return self.name


class GameSession(models.Model):
    STATUS_CHOICES = [
        ("in_progress", "進行中"),
        ("finished", "結束"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.PROTECT, related_name="sessions")
    client_session_id = models.CharField(max_length=64, null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="game_sessions"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="in_progress")
    question_number = models.PositiveIntegerField(default=0)
    current_question = models.JSONField(null=True, blank=True)
    result = models.JSONField(null=True, blank=True)
    state = models.JSONField(default=dict)
    is_pretest = models.BooleanField(default=False)
    avg_response_time_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["game", "user"])]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "client_session_id"],
                name="unique_client_session_per_game",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.game.code} ({self.status})"


class GameStepLog(models.Model):
    session = models.ForeignKey(GameSession, on_delete=models.CASCADE, related_name="step_logs")
    step_number = models.IntegerField()
    is_correct = models.BooleanField(null=True, blank=True)
    response_time_ms = models.IntegerField(null=True, blank=True)
    detail = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"session {self.session_id} 第{self.step_number}步"


class GameRecord(models.Model):
    DIFFICULTY_CHOICES = [
        ("basic", "初階"),
        ("intermediate", "中階"),
        ("advanced", "進階"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="game_records"
    )
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="records")
    score = models.IntegerField(null=True, blank=True)  # 統一0~100，各遊戲原始分數需經normalize_to_100轉換
    accuracy = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    response_time = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, blank=True)
    played_at = models.DateTimeField(null=True, blank=True)
    played_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} - {self.game} ({self.score}分)"