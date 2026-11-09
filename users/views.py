from datetime import timedelta
import logging

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from config.exceptions import ApiError
from diary.external import delete_from_firebase
from diary.models import Diary, DiaryReply
from games.models import GameSession
from social.models import Post

from .serializers import (
    AccountDeleteSerializer,
    AvatarUploadSerializer,
    MeSerializer,
    PasswordChangeSerializer,
    PasswordResetCheckSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
    validate_new_password,
)
from .throttles import PasswordResetIPThrottle, PasswordResetUsernameThrottle

logger = logging.getLogger(__name__)

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


def collect_user_media(user):
    """收集這位使用者所有存在檔案儲存空間的檔案（資料庫裡存的路徑或網址）。

    包含頭像、日記照片、日記錄音、社群貼文照片。必須在刪除使用者「之前」呼叫，
    因為使用者一刪，這些資料列也會一起被刪掉。
    """
    values = {user.avatar_url}
    for image_path, audio_path in Diary.objects.filter(user=user).values_list(
        "image_path", "audio_path"
    ):
        values.update([image_path, audio_path])
    values.update(
        DiaryReply.objects.filter(diary__user=user).values_list("audio_path", flat=True)
    )
    values.update(Post.objects.filter(user=user).values_list("image_path", flat=True))
    return {v for v in values if v}


def remove_user_media(values):
    """刪除收集到的檔案：雲端（Firebase）的檔案，以及存在本機 media 的頭像。

    盡力而為：任何一個檔案刪不掉都只記錄，不會影響其他檔案，也不會丟例外。
    """
    from django.conf import settings

    local = {v for v in values if v.startswith(settings.MEDIA_URL)}
    delete_from_firebase(values - local)
    for value in local:
        try:
            default_storage.delete(value[len(settings.MEDIA_URL) :])
        except Exception as exc:
            logger.warning("本機檔案刪除失敗（%s）: %s", value, exc)


def save_avatar_file(avatar_file):
    """上傳頭像檔案，優先上傳至 Firebase Storage，若未設定則存至本機 media。"""
    try:
        from diary.external import upload_to_firebase

        url = upload_to_firebase(avatar_file, "avatars", public=True)
        if url:
            return url
    except Exception as exc:
        logger.warning("Firebase avatar upload failed: %s", exc)

    import os
    import uuid
    from django.conf import settings
    from django.core.files.storage import default_storage

    ext = os.path.splitext(avatar_file.name)[1] or ".jpg"
    filename = f"avatars/{uuid.uuid4().hex}{ext}"
    path = default_storage.save(filename, avatar_file)
    return f"{settings.MEDIA_URL}{path}"


def calculate_user_stats(user, today=None):
    """計算會員成就統計資料：
    - joined_at: 加入日期 (YYYY-MM-DD)
    - active_day_count: 累計有活動天數
    - session_count: 累計遊戲場次（不含熟悉場）
    - diary_count: 累計完成的日記篇數
    - streak_days: 目前連續活動天數（若今日尚無活動但昨日有，延續昨日連續天數）
    """
    if today is None:
        today = timezone.localdate()

    reg_date = (getattr(user, "registered_at", None) or user.date_joined).date()
    joined_at = reg_date.isoformat()

    session_count = GameSession.objects.filter(
        user=user, status="finished", is_pretest=False
    ).count()

    diary_count = Diary.objects.filter(user=user, status="done").count()

    game_dates = (
        GameSession.objects.filter(user=user)
        .annotate(day=TruncDate("created_at"))
        .values_list("day", flat=True)
    )
    diary_dates = (
        Diary.objects.filter(user=user)
        .annotate(day=TruncDate("created_at"))
        .values_list("day", flat=True)
    )

    active_dates = {d for d in game_dates if d is not None}
    active_dates.update(d for d in diary_dates if d is not None)

    active_day_count = len(active_dates)

    yesterday = today - timedelta(days=1)
    if today in active_dates:
        curr = today
    elif yesterday in active_dates:
        curr = yesterday
    else:
        curr = None

    streak_days = 0
    while curr and curr in active_dates:
        streak_days += 1
        curr -= timedelta(days=1)

    return {
        "joined_at": joined_at,
        "active_day_count": active_day_count,
        "session_count": session_count,
        "diary_count": diary_count,
        "streak_days": streak_days,
    }


# Create your views here.
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]  # 註冊時還沒有帳號，必須開放


class MeView(generics.RetrieveUpdateAPIView):
    """目前登入者自己的資料。

    - GET: 取得個人資料，回傳 {"success": True, "data": {...}, "error": None}
    - PATCH: 修改個人資料（僅能改暱稱、性別、地區、緊急聯絡人、興趣等，username 為 read-only 保持不變）
    - DELETE: 刪除帳號（需帶密碼確認身分），回傳 204
    """

    serializer_class = MeSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({"success": True, "data": serializer.data, "error": None})

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({"success": True, "data": serializer.data, "error": None})

    def delete(self, request, *args, **kwargs):
        serializer = AccountDeleteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        media = collect_user_media(user)
        with transaction.atomic():
            user.delete()
            # 資料庫刪除成功後才刪檔案：刪帳號失敗就不會留下沒檔案的帳號
            transaction.on_commit(lambda: remove_user_media(media))
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordChangeView(APIView):
    """修改密碼：POST /api/users/me/password/

    驗證舊密碼與新密碼強度，成功後更新密碼並回發新的 access / refresh token。
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        new_password = serializer.validated_data["new_password"]
        user.set_password(new_password)
        user.save(update_fields=["password"])

        refresh = RefreshToken.for_user(user)
        return Response({
            "success": True,
            "data": {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "message": "密碼已更新",
            },
            "error": None,
        })


class AvatarView(APIView):
    """會員頭像管理：

    - POST /api/users/me/avatar/ (multipart/form-data 欄位 avatar)
    - DELETE /api/users/me/avatar/ (移除頭像)
    """

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        serializer = AvatarUploadSerializer(data=request.FILES)
        serializer.is_valid(raise_exception=True)
        avatar_file = serializer.validated_data["avatar"]

        url = save_avatar_file(avatar_file)
        if not url:
            raise ApiError(
                "UPLOAD_FAILED",
                "頭像上傳失敗，請再試一次",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        user = request.user
        user.avatar_url = url
        user.save(update_fields=["avatar_url"])

        return Response({
            "success": True,
            "data": {"avatar_url": user.avatar_url},
            "error": None,
        })

    def delete(self, request):
        user = request.user
        user.avatar_url = None
        user.save(update_fields=["avatar_url"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserStatsView(APIView):
    """會員成就統計：GET /api/users/me/stats/"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        stats = calculate_user_stats(request.user)
        return Response({
            "success": True,
            "data": stats,
            "error": None,
        })


class PasswordResetCheckView(APIView):
    """忘記密碼第 1 步：確認帳號存在。"""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordResetIPThrottle, PasswordResetUsernameThrottle]

    def post(self, request):
        serializer = PasswordResetCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        get_active_user_or_404(serializer.validated_data["username"])
        return Response({"exists": True})


class PasswordResetView(APIView):
    """忘記密碼第 2 步：設定新密碼。"""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordResetIPThrottle, PasswordResetUsernameThrottle]

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

        user.set_password(data["new_password"])
        user.save(update_fields=["password"])
        return Response({"message": "密碼已更新"})
