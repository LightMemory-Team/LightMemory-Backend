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
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='game_sessions')
    game_type = models.CharField(max_length=50)  # "market_route" / "market_shopping" / "market_sort"
    is_pretest = models.BooleanField(default=False)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.game_type} ({self.created_at.date()})"


class MarketRouteSession(models.Model):
    session = models.OneToOneField(GameSession, on_delete=models.CASCADE, related_name='market_route_session')
    final_stage = models.CharField(max_length=20)
    total_questions = models.IntegerField(default=20)
    answered_count = models.IntegerField()
    correct_count = models.IntegerField()
    timeout_count = models.IntegerField()
    accuracy = models.FloatField()
    avg_response_time_ms = models.IntegerField()
    total_score = models.IntegerField()

    def __str__(self):
        return f"MarketRoute結果 - session {self.session_id}"


class MarketRouteStepLog(models.Model):
    session = models.ForeignKey(GameSession, on_delete=models.CASCADE, related_name='market_route_steps')
    question_number = models.IntegerField()
    attempt_number = models.IntegerField()
    stage = models.CharField(max_length=20)
    target_position = models.CharField(max_length=10)
    answer_position = models.CharField(max_length=10, null=True, blank=True)
    is_correct = models.BooleanField()
    is_timeout = models.BooleanField()
    distractor_count = models.IntegerField()
    exposure_time_ms = models.IntegerField()
    response_time_ms = models.IntegerField(null=True, blank=True)
    paused_duration_ms = models.IntegerField()

    class Meta:
        indexes = [
            models.Index(fields=['session', 'question_number']),
        ]

    def __str__(self):
        return f"session {self.session_id} 第{self.question_number}題 第{self.attempt_number}次"