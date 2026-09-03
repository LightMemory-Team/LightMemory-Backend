# 資料轉換json


from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = [
            'username', 'password',
            'first_name', 'last_name',
            'gender', 'birth_date', 'phone', 'address', 'region',
        ]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)
