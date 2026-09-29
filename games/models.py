import uuid

from django.conf import settings
from django.db import models

from users.models import User


class GameCategory(models.Model):
    category_name = models.CharField(max_length=20)
    category_description = models.TextField(blank=True)

    def __str__(self):
        return self.category_name


class Game(models.Model):
    DIFFICULTY_CHOICES = [
        ("easy", "簡單"),
        ("medium", "中等"),
        ("hard", "困難"),
    ]

    game_category = models.ForeignKey(
        GameCategory, on_delete=models.CASCADE, related_name="games"
    )
    game_name = models.CharField(max_length=50)
    game_description = models.TextField(blank=True)
    code = models.CharField(max_length=50, unique=True, null=True, blank=True)
    default_difficulty = models.CharField(
        max_length=20, choices=DIFFICULTY_CHOICES, blank=True
    )
    is_enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.game_name


class GameRecord(models.Model):
    DIFFICULTY_CHOICES = [
        ("easy", "簡單"),
        ("medium", "中等"),
        ("hard", "困難"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="game_records"
    )
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="records")
    score = models.IntegerField(null=True, blank=True)
    accuracy = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    reaction_time = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, blank=True)
    played_at = models.DateTimeField(null=True, blank=True)
    played_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} - {self.game} ({self.score}分)"


class GameSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.PROTECT, related_name="sessions")
    client_session_id = models.CharField(max_length=64, null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="game_sessions",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=[("in_progress", "進行中"), ("finished", "已完成")],
        default="in_progress",
    )
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
        game_code = self.game.code if self.game else "unknown"
        return f"{game_code} - {self.client_session_id or self.id}"


class GameStepLog(models.Model):
    session = models.ForeignKey(
        GameSession, on_delete=models.CASCADE, related_name="step_logs"
    )
    step_number = models.PositiveIntegerField()
    is_correct = models.BooleanField(null=True, blank=True)
    response_time_ms = models.PositiveIntegerField(null=True, blank=True)
    detail = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.session_id} - step {self.step_number}"
