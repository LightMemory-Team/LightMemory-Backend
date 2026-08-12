from django.db import models
from users.models import User


class HealthInformation(models.Model):
    ACTIVITY_TYPE_CHOICES = [
        ('exercise', '運動'),
        ('lecture', '講座'),
        ('social', '社交活動'),
        ('checkup', '健康檢查'),
    ]

    REGION_CHOICES = [
        ('north', '北部'),
        ('central', '中部'),
        ('south', '南部'),
        ('east', '東部'),
    ]

    activity_name = models.CharField(max_length=50)
    activity_type = models.CharField(max_length=30, choices=ACTIVITY_TYPE_CHOICES, blank=True)
    activity_location = models.CharField(max_length=100, blank=True)
    activity_region = models.CharField(max_length=30, choices=REGION_CHOICES, blank=True)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    activity_description = models.TextField(blank=True)
    source_url = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.activity_name


class ActivityRecord(models.Model):
    STATUS_CHOICES = [
        ('registered', '已報名'),
        ('completed', '已完成'),
        ('cancelled', '已取消'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_records')
    activity = models.ForeignKey(HealthInformation, on_delete=models.CASCADE, related_name='records')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    is_enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user} - {self.activity} ({self.status})"