from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from config.exceptions import ApiError

from .serializers import (
    MeSerializer,
    PasswordResetCheckSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
    validate_new_password,
)

User = get_user_model()

ACCOUNT_NOT_FOUND_MESSAGE = "找不到這個帳號"


def get_active_user_or_404(username):
    user = User.objects.filter(username=username, is_active=True).first()
    if user is None:
        raise ApiError(
            "ACCOUNT_NOT_FOUND",
            ACCOUNT_NOT_FOUND_MESSAGE,
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return user


# Create your views here.
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]  # 註冊時還沒有帳號，必須開放


class MeView(generics.RetrieveUpdateAPIView):
    """目前登入者自己的資料。

    me 的意思是「我」：用 access token 判斷是誰，所以網址不需要放使用者 ID，
    也就不會改到別人的資料。
    """

    serializer_class = MeSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


class PasswordResetCheckView(APIView):
    """忘記密碼第 1 步：確認帳號存在。

    忘記密碼的人本來就登不進去，所以不用登入。authentication_classes 設成空，
    是因為手機裡若殘留過期的 token，預設的 JWT 驗證會先把請求擋成 401。
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        get_active_user_or_404(serializer.validated_data["username"])
        return Response({"exists": True})


class PasswordResetView(APIView):
    """忘記密碼第 2 步：設定新密碼。

    已知風險：目前沒有驗證碼，任何人知道帳號就能改密碼，
    正式上線前要加入簡訊或 Email 驗證。
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = get_active_user_or_404(data["username"])

        if data["new_password"] != data["new_password_confirm"]:
            raise ApiError(
                "PASSWORD_MISMATCH",
                "兩次輸入的新密碼不一樣",
                fields={"new_password_confirm": ["兩次輸入的新密碼不一樣"]},
            )

        validate_new_password(data["new_password"], user)

        # set_password 會自動把密碼加密（雜湊），不能直接存明碼
        user.set_password(data["new_password"])
        user.save(update_fields=["password"])
        return Response({"message": "密碼已更新"})
