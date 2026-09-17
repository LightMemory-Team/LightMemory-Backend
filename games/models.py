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
class MarketSortResult(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="market_sort_results"
    )
    session_id = models.CharField(
        max_length=64,
        unique=True
    )  # 避免同一場遊戲不小心被存兩次
    is_complete = models.BooleanField(default=False)
    raw_metrics = models.JSONField(null=True, blank=True)
    z_scores = models.JSONField(null=True, blank=True)
    cognitive_flexibility_score = models.IntegerField(
        null=True,
        blank=True
    )
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (
            f"{self.user} 的整理菜籃結果 "
            f"({self.generated_at.date()}) - "
            f"{self.cognitive_flexibility_score}分"
        )


# 市場買菜：記錄一場 10 題遊戲進行中的資料
class MarketShoppingSession(models.Model):
    DIFFICULTY_CHOICES = [
        ("easy", "簡單"),
        ("medium", "中等"),
        ("hard", "困難"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="market_shopping_sessions"
    )

    # 目前難度
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default="easy"
    )

    # ===== 目前這一題的題目資料 =====
    target_items = models.JSONField()
    option_items = models.JSONField()

    # 找零相關資料
    budget = models.IntegerField(default=200)
    spent_amount = models.IntegerField()
    correct_change = models.IntegerField()

    # ===== 目前這一題的作答狀態 =====
    item_attempt_count = models.IntegerField(default=0)
    change_attempt_count = models.IntegerField(default=0)

    item_first_try_correct = models.BooleanField(
        null=True,
        blank=True
    )

    change_first_try_correct = models.BooleanField(
        null=True,
        blank=True
    )

    # ===== 整場 10 題的遊戲進度 =====
    current_question = models.IntegerField(default=1)
    total_questions = models.IntegerField(default=10)
    consecutive_correct = models.IntegerField(default=0)
    total_correct = models.IntegerField(default=0)
    first_try_correct_count = models.IntegerField(default=0)
    current_wrong_count = models.IntegerField(default=0)
    current_question_had_error = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)

    # ===== 時間 =====
    started_at = models.DateTimeField(auto_now_add=True)

    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    def __str__(self):
        return (
            f"{self.user} - 市場買菜 - "
            f"第{self.current_question}題 - {self.difficulty}"
        )