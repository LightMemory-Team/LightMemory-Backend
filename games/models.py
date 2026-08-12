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