from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    GENDER_CHOICES = [
        ('male', '男'),
        ('female', '女'),
        ('other', '其他'),
    ]

    REGION_CHOICES = [
        ('north', '北部'),
        ('central', '中部'),
        ('south', '南部'),
        ('east', '東部'),
    ]

    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=10, blank=True)
    address = models.CharField(max_length=100, blank=True)
    region = models.CharField(
        max_length=30, choices=REGION_CHOICES, blank=True, null=True
    )
    # 首頁改版：暱稱取代姓名，首頁與啟動頁的問候都用它
    nickname = models.CharField(max_length=20, blank=True, default='')
    emergency_contact_name = models.CharField(max_length=50, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True, null=True)
    avatar_url = models.CharField(max_length=255, blank=True, null=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nickname or self.last_name or self.username