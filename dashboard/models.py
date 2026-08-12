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