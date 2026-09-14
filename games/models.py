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


# 市場買菜：記錄一場 10 題遊戲進行中的資料
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

    # 目前難度，開始遊戲時固定 easy
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default='easy'
    )

    # ===== 目前這一題的題目資料 =====

    # 要記住的購物清單
    target_items = models.JSONField()

    # 畫面上可選擇的所有食材
    option_items = models.JSONField()

    # 找零相關資料
    budget = models.IntegerField(default=200)
    spent_amount = models.IntegerField()
    correct_change = models.IntegerField()

    # ===== 目前這一題的作答狀態 =====

    # 選菜答了幾次
    item_attempt_count = models.IntegerField(default=0)

    # 找零答了幾次
    change_attempt_count = models.IntegerField(default=0)

    # 選菜是否第一次就答對
    item_first_try_correct = models.BooleanField(
        null=True,
        blank=True
    )

    # 找零是否第一次就答對
    change_first_try_correct = models.BooleanField(
        null=True,
        blank=True
    )

    # ===== 整場 10 題的遊戲進度 =====

    # 目前第幾題
    current_question = models.IntegerField(default=1)

    # 一場固定 10 題
    total_questions = models.IntegerField(default=10)

    # 目前連續答對幾題
    consecutive_correct = models.IntegerField(default=0)

    # 整場總共答對幾題
    total_correct = models.IntegerField(default=0)

    # 完全沒有答錯、一次完成的題數
    first_try_correct_count = models.IntegerField(default=0)

    # 目前這一題答錯幾次
    current_wrong_count = models.IntegerField(default=0)

    # 目前這題是否曾經答錯過
    current_question_had_error = models.BooleanField(default=False)

    # 整場遊戲是否完成
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