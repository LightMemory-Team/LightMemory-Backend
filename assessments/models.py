from django.db import models
from users.models import User


class Ad8Record(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ad8_records')
    total_score = models.IntegerField(null=True, blank=True)
    result_description = models.CharField(max_length=200, blank=True)
    completed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} 的AD-8測驗 ({self.completed_at.date()}) - {self.total_score}分"