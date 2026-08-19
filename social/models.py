from django.db import models
from users.models import User


class Post(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='posts')
    content_text = models.TextField(blank=True)
    like_count = models.IntegerField(default=0)
    comment_count = models.IntegerField(default=0)
    posted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} 的動態 ({self.posted_at.date()})"
