from django.conf import settings
from django.db import models


class PointTransaction(models.Model):
    """點數流水帳：每一筆入帳都記一列，總點數 = 所有 amount 加總。

    不在 User 上直接存點數欄位，帳目才不會對不上。
    (user, reason, source_id) 唯一：同一件事重複呼叫 grant() 也只會入帳一次。
    達每日上限時，仍會用原本的 reason 記一筆 amount=0（或只入帳剩餘額度），
    這樣「這件事已經處理過」「今天任務全部完成」的事實不會消失。
    """

    REASON_CHOICES = [
        ("game_complete", "完成一場遊戲"),
        ("diary_complete", "完成一篇聲影日記"),
        ("daily_task", "完成今日任務"),
        ("all_tasks_done", "今日任務全部完成"),
        ("achievement_unlock", "解鎖成就"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="point_transactions",
    )
    amount = models.IntegerField()
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    # 遊戲：GameSession 主鍵；日記：diary_id；今日任務：「日期:task_id」；
    # 全部完成：日期；成就：成就 code
    source_id = models.CharField(max_length=64)
    # 給前端直接顯示的文字，例如「完成今日任務：整理菜籃」
    label = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "reason", "source_id"],
                name="unique_point_per_source",
            )
        ]
        indexes = [models.Index(fields=["user", "created_at"])]

    def __str__(self):
        return f"{self.user} {self.reason} {self.amount:+d}"


class UserAchievement(models.Model):
    """使用者已解鎖的成就。成就定義本身放在 rewards/catalog.py。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="achievements",
    )
    code = models.CharField(max_length=50)
    unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-unlocked_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "code"], name="unique_user_achievement"
            )
        ]

    def __str__(self):
        return f"{self.user} {self.code}"
