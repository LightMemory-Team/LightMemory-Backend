from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from users.models import User


class HealthDashboardRecord(models.Model):
    REPORT_TYPE_CHOICES = [
        ('weekly', '週報'),
        ('monthly', '月報'),
        ('manual', '手動產生'),
    ]

    ALERT_LEVEL_CHOICES = [
        ('low', '低'),
        ('medium', '中'),
        ('high', '高'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dashboard_records')
    attention_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    executive_function_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    language_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    working_memory_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    math_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    visual_spatial_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    brain_age = models.IntegerField(null=True, blank=True)
    trend_alert_level = models.CharField(max_length=10, choices=ALERT_LEVEL_CHOICES, blank=True)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} 的健康報告 ({self.generated_at.date()})"


class WeeklyReport(models.Model):
    """每個使用者每一週的週報紀錄。

    week_start 是「報告的那一週」的週一（週報看的是上一個完整的週）。
    使用者點開週報時建立／更新：report 存當時的週報內容快照，viewed_at 記錄
    第一次點開的時間。首頁今日任務的「看看上週回顧」看 viewed_at 判斷是否完成。
    同一個人同一週只存一筆，重複點開不會多存。
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="weekly_reports"
    )
    week_start = models.DateField()
    report = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    created_at = models.DateTimeField(auto_now_add=True)
    viewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-week_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "week_start"], name="unique_weekly_report_per_week"
            )
        ]

    def __str__(self):
        return f"{self.user} {self.week_start} 那週的週報"
