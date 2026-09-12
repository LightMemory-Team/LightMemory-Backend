from django.db import models
from users.models import User


class GameCategory(models.Model):
    category_name = models.CharField(max_length=20)
    category_description = models.TextField(blank=True)

    def __str__(self):
        return self.category_name


class Game(models.Model):
    DIFFICULTY_CHOICES = [
        ('easy', '簡單'),
        ('medium', '中等'),
        ('hard', '困難'),
    ]

    game_category = models.ForeignKey(GameCategory, on_delete=models.CASCADE, related_name='games')
    game_name = models.CharField(max_length=50)
    game_description = models.TextField(blank=True)
    default_difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, blank=True)
    is_enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.game_name


class GameRecord(models.Model):
    DIFFICULTY_CHOICES = [
        ('easy', '簡單'),
        ('medium', '中等'),
        ('hard', '困難'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='game_records')
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='records')
    score = models.IntegerField(null=True, blank=True)
    accuracy = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    reaction_time = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, blank=True)
    played_at = models.DateTimeField(null=True, blank=True)
    played_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} - {self.game} ({self.score}分)"


# 市場買菜：記錄單次遊戲進行中的資料
class MarketShoppingSession(models.Model):
    DIFFICULTY_CHOICES = [
        ('easy', '簡單'),
        ('medium', '中等'),
        ('hard', '困難'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='market_shopping_sessions'
    )

    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES
    )

    # 第一畫面：要記住的購物清單
    target_items = models.JSONField()

    # 第二畫面：可選擇的所有食材
    option_items = models.JSONField()

    # 第三畫面：找零相關資料
    budget = models.IntegerField(default=200)
    spent_amount = models.IntegerField()
    correct_change = models.IntegerField()

    # 記錄使用者答了幾次
    item_attempt_count = models.IntegerField(default=0)
    change_attempt_count = models.IntegerField(default=0)

    # 是否第一次就答對
    item_first_try_correct = models.BooleanField(
        null=True,
        blank=True
    )
    change_first_try_correct = models.BooleanField(
        null=True,
        blank=True
    )

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.user} - 市場買菜 - {self.difficulty}"