from django.db import models
from users.models import User


class Diary(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='diaries')
    image_path = models.CharField(max_length=255, blank=True)
    audio_path = models.CharField(max_length=255, blank=True)   # 第1輪錄音
    transcription = models.TextField(blank=True)                 # finalize時寫入合併文字
    diary_text = models.TextField(blank=True)                    # 同transcription
    created_at = models.DateTimeField(auto_now_add=True)

    # 新增
    title = models.CharField(max_length=50, blank=True)
    first_question = models.TextField(blank=True)
    photo_description = models.TextField(blank=True)
    ai_response = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=[("pending", "等待分析"), ("processing", "分析中"),
                  ("done", "完成"), ("failed", "失敗")],
        default="pending",
    )
    post_text = models.TextField(blank=True)
    hashtags = models.JSONField(default=list, blank=True)
    category = models.CharField(max_length=20, blank=True)
    suggested_replies = models.JSONField(default=list, blank=True)
    invite_text = models.CharField(max_length=100, blank=True)
    pending_question = models.TextField(blank=True)  

    def __str__(self):
        return f"{self.user} 的日記 ({self.created_at.date()})"


class DiaryReply(models.Model):
    diary = models.ForeignKey(Diary, on_delete=models.CASCADE, related_name='replies')
    round_index = models.IntegerField()
    question = models.TextField(blank=True)
    transcript = models.TextField(blank=True)
    audio_path = models.CharField(max_length=255, blank=True)
    is_skipped = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('diary', 'round_index')]

    def __str__(self):
        return f"{self.diary} 第{self.round_index}輪"


class DiaryAnalysis(models.Model):
    diary = models.OneToOneField(Diary, on_delete=models.CASCADE, related_name='analysis')
    is_valid = models.BooleanField(default=True)
    invalid_reason = models.CharField(max_length=30, blank=True)
    fluency_score = models.FloatField(null=True, blank=True)
    information_score = models.FloatField(null=True, blank=True)
    sentence_score = models.FloatField(null=True, blank=True)
    naming_score = models.FloatField(null=True, blank=True)
    semantic_score = models.FloatField(null=True, blank=True)
    communication_score = models.FloatField(null=True, blank=True)  # 儀表板「語言」分數直接用這個
    total_score = models.FloatField(null=True, blank=True)
    average_score = models.FloatField(null=True, blank=True)
    risk_level = models.CharField(max_length=10, blank=True)
    ai_feedback = models.TextField(blank=True)
    analysis_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.diary} 的分析結果"