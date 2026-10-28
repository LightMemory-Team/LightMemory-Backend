# 資料轉換json


from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class ProfileFieldsSerializer(serializers.ModelSerializer):
    """註冊與會員中心共用的個人資料欄位。

    選填欄位（region、緊急聯絡人）前端沒填時可能送空字串，統一存成 None，
    這樣 GET 回傳的「沒填」永遠是 null。
    """

    nickname = serializers.CharField(
        max_length=20,
        error_messages={
            "blank": "暱稱不能是空白",
            "required": "請輸入暱稱",
            "max_length": "暱稱最多 20 個字",
        },
    )
    region = serializers.ChoiceField(
        choices=User.REGION_CHOICES,
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    emergency_contact_name = serializers.CharField(
        max_length=50, required=False, allow_null=True, allow_blank=True
    )
    emergency_contact_phone = serializers.CharField(
        max_length=20, required=False, allow_null=True, allow_blank=True
    )

    def validate_nickname(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("暱稱不能是空白")
        return value

    def validate_birth_date(self, value):
        if value and value > date.today():
            raise serializers.ValidationError("生日不能是未來的日期")
        return value

    def validate_region(self, value):
        return value or None

    def validate_emergency_contact_name(self, value):
        return value or None

    def validate_emergency_contact_phone(self, value):
        return value or None


class RegisterSerializer(ProfileFieldsSerializer):
    # 不用 model 預設的 UniqueValidator：
    # 重複時要回 USERNAME_TAKEN，由 config.exceptions 轉換
    username = serializers.CharField(
        max_length=150, validators=[User.username_validator]
    )
    password = serializers.CharField(write_only=True, validators=[validate_password])

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
