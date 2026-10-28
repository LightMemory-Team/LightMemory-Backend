from django.conf import settings
from django.db import models


class DailyTask(models.Model):
    """每天產生的「今日任務」。

    任務一旦產生就固定：使用者玩完一個遊戲後，不會因為「本週已玩過」而重新排序、
    換掉其他任務，所以要存起來。是否完成（done）每次請求即時計算，不存。
    """

    TYPE_CHOICES = [
        ("game", "遊戲"),
        ("diary", "聲影日記"),
        ("weekly_report", "上週回顧"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="daily_tasks"
    )
    date = models.DateField()  # 台灣時間的日期
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    game_id = models.CharField(max_length=50, null=True, blank=True)  # 只有遊戲任務有值
    dimension = models.CharField(max_length=30, null=True, blank=True)  # 上週回顧為空
    order = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["order"]
        constraints = [
            # 同一個人同一天同一個位置只會有一筆；同時擋住兩個請求同時產生任務
            models.UniqueConstraint(
                fields=["user", "date", "order"], name="unique_daily_task_order"
            )
        ]

    def __str__(self):
        return f"{self.user} {self.date} #{self.order} {self.type}"
