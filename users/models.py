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
    region = models.CharField(max_length=30, choices=REGION_CHOICES, blank=True)
    avatar_url = models.CharField(max_length=255, blank=True, null=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.last_name or self.username
    
class FamilyContact(models.Model):
    RELATIONSHIP_CHOICES = [
        ('spouse', '配偶'),
        ('child', '子女'),
        ('sibling', '手足'),
        ('other', '其他'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='family_contacts')
    family_name = models.CharField(max_length=50)
    relationship = models.CharField(max_length=20, choices=RELATIONSHIP_CHOICES, blank=True)
    phone = models.CharField(max_length=10, blank=True)
    email = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.family_name}({self.get_relationship_display()})"