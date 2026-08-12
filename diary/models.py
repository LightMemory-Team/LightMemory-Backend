from django.db import models
from users.models import User


class Diary(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='diaries')
    # Firebase Storage 圖片檔案的路徑 / URL
    image_path = models.CharField(max_length=255, blank=True)
    # Firebase Storage 語音檔案的路徑 / URL
    audio_path = models.CharField(max_length=255, blank=True)
    transcription = models.TextField(blank=True)
    diary_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} 的日記 ({self.created_at.date()})"


class DiaryAnalysis(models.Model):
    diary = models.ForeignKey(Diary, on_delete=models.CASCADE, related_name='analyses')
    language_fluency = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    logic_completeness = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    emotion_description_completeness = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    emotion_analysis_result = models.CharField(max_length=50, blank=True)
    ai_feedback = models.TextField(blank=True)
    analysis_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.diary} 的分析結果 ({self.analysis_time.date()})"