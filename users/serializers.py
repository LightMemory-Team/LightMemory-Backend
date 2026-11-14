# 資料轉換json

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

User = get_user_model()


class ProfileFieldsSerializer(serializers.ModelSerializer):
    """註冊與會員中心共用的個人資料欄位。

    - gender: 限制僅能填 male 或 female
    - region: 限制僅能填 north、central、south（或 null/清空）
    - emergency_contact_phone: 需符合 8~15 碼數字（可含 +、-、空白）
    - interests: 興趣字串陣列
    選填欄位前端沒填時可能送空字串，統一存成 None，這樣 GET 回傳的「沒填」永遠是 null。
    """

    GENDER_CHOICES = [
        ("male", "男"),
        ("female", "女"),
    ]

    REGION_CHOICES = [
        ("north", "北部"),
        ("central", "中部"),
        ("south", "南部"),
    ]

    nickname = serializers.CharField(
        max_length=20,
        error_messages={
            "blank": "暱稱不能是空白",
            "required": "請輸入暱稱",
            "max_length": "暱稱最多 20 個字",
        },
    )
    gender = serializers.ChoiceField(
        choices=GENDER_CHOICES,
        required=False,
        error_messages={
            "required": "請選擇性別",
            "invalid_choice": "性別僅接受 male 或 female",
        },
    )
    region = serializers.ChoiceField(
        choices=REGION_CHOICES,
        required=False,
        allow_null=True,
        allow_blank=True,
        error_messages={
            "invalid_choice": "地區僅接受 north、central 或 south",
        },
    )
    emergency_contact_name = serializers.CharField(
        max_length=50, required=False, allow_null=True, allow_blank=True
    )
    emergency_contact_phone = serializers.CharField(
        max_length=20, required=False, allow_null=True, allow_blank=True
    )
    interests = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=list,
    )

    def validate_nickname(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("暱稱不能是空白")
        return value

    def validate_birth_date(self, value):
        if value and value > timezone.localdate():
            raise serializers.ValidationError("生日不能是未來的日期")
        return value

    def validate_region(self, value):
        return value or None

    def validate_emergency_contact_name(self, value):
        return value or None

    def validate_emergency_contact_phone(self, value):
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        # 只接受數字、+、-、空白，8~15 碼，且必須包含至少一個數字
        if not re.fullmatch(r"[0-9+\-\s]{8,15}", value) or not re.search(r"\d", value):
            raise serializers.ValidationError(
                "緊急聯絡人電話格式不正確（僅接受數字、+、-、空白，長度需為 8~15 碼）"
            )
        return value

    def validate_interests(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("興趣必須是字串陣列")
        cleaned = []
        for item in value:
            if isinstance(item, str):
                s = item.strip()
                if s and s not in cleaned:
                    cleaned.append(s)
        return cleaned


class RegisterSerializer(ProfileFieldsSerializer):
    # 不用 model 預設的 UniqueValidator：
    # 重複時要回 USERNAME_TAKEN，由 config.exceptions 轉換
    username = serializers.CharField(
        max_length=150, validators=[User.username_validator]
    )
    password = serializers.CharField(write_only=True, validators=[validate_password])
    gender = serializers.ChoiceField(
        choices=ProfileFieldsSerializer.GENDER_CHOICES,
        required=True,
        allow_blank=False,
        error_messages={
            "required": "請選擇性別",
            "invalid_choice": "性別僅接受 male 或 female",
        },
    )

    class Meta:
        model = User
        fields = [
            "username",
            "password",
            "nickname",
            "gender",
            "birth_date",
            "region",
            "emergency_contact_name",
            "emergency_contact_phone",
            "interests",
        ]
        extra_kwargs = {
            "gender": {"required": True, "allow_blank": False},
            "birth_date": {"required": True, "allow_null": False},
        }

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError(
                "這個帳號已經被註冊過", code="username_taken"
            )
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class MeSerializer(ProfileFieldsSerializer):
    """GET／PATCH /api/users/me/：帳號只能看不能改，密碼不在這裡改。"""

    avatar_url = serializers.CharField(read_only=True, allow_null=True)
    gender = serializers.ChoiceField(
        choices=ProfileFieldsSerializer.GENDER_CHOICES,
        required=False,
        allow_blank=False,
        error_messages={
            "invalid_choice": "性別僅接受 male 或 female",
        },
    )

    class Meta:
        model = User
        fields = [
            "username",
            "nickname",
            "birth_date",
            "gender",
            "region",
            "emergency_contact_name",
            "emergency_contact_phone",
            "avatar_url",
            "interests",
        ]
        read_only_fields = ["username", "avatar_url"]
        extra_kwargs = {
            "gender": {"allow_blank": False},
            "birth_date": {"allow_null": False},
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # 舊帳號的選填欄位可能存成空字串，對前端一律回 null（代表「沒填」）
        for key in ["region", "emergency_contact_name", "emergency_contact_phone", "avatar_url"]:
            data[key] = data.get(key) or None
        data["interests"] = data.get("interests") or []
        return data


class PasswordChangeSerializer(serializers.Serializer):
    """修改密碼：檢查舊密碼與新密碼強度。"""

    old_password = serializers.CharField(
        write_only=True,
        required=True,
        error_messages={"required": "請輸入舊密碼", "blank": "舊密碼不能是空白"},
    )
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        error_messages={"required": "請輸入新密碼", "blank": "新密碼不能是空白"},
    )

    def validate_old_password(self, value):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.check_password(value):
            raise serializers.ValidationError("舊密碼不正確")
        return value

    def validate_new_password(self, value):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        try:
            validate_password(value, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class AccountDeleteSerializer(serializers.Serializer):
    """刪除帳號：需再次確認密碼。"""

    password = serializers.CharField(
        write_only=True,
        required=True,
        error_messages={"required": "請輸入密碼以確認身分", "blank": "密碼不能是空白"},
    )

    def validate_password(self, value):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.check_password(value):
            raise serializers.ValidationError("密碼不正確")
        return value


class AvatarUploadSerializer(serializers.Serializer):
    """頭像上傳驗證。"""

    avatar = serializers.FileField(
        required=True,
        error_messages={"required": "請選擇要上傳的頭像檔案"},
    )

    ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]

    def validate_avatar(self, value):
        max_size = 2 * 1024 * 1024  # 2MB
        if value.size > max_size:
            raise serializers.ValidationError("檔案太大（不能超過 2MB）")

        import os
        ext = os.path.splitext(value.name.lower())[1]
        content_type = getattr(value, "content_type", "")
        if ext not in self.ALLOWED_EXTENSIONS or (content_type and content_type not in self.ALLOWED_TYPES):
            raise serializers.ValidationError("檔案格式不對（僅支援 JPEG、PNG、WEBP 圖片）")
        return value


class PasswordResetCheckSerializer(serializers.Serializer):
    """忘記密碼第 1 步：只需要帳號"""

    username = serializers.CharField()


class PasswordResetSerializer(serializers.Serializer):
    """忘記密碼第 2 步：帳號 + 新密碼 + 確認新密碼

    只檢查「欄位格式」；帳號是否存在、兩次密碼是否一致、密碼強度，
    因為需要知道是哪個使用者，放在 view 裡處理。
    """

    username = serializers.CharField()
    new_password = serializers.CharField(write_only=True)
    new_password_confirm = serializers.CharField(write_only=True)


def validate_new_password(password, user):
    """套用 Django 密碼強度驗證（規則跟註冊一樣），錯誤放在 new_password 欄位下"""
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"new_password": list(exc.messages)})
