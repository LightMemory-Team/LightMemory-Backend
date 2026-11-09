from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views

urlpatterns = [
    # 登入
    path("login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),  # 檢查帳密
    path(
        "login/refresh/", TokenRefreshView.as_view(), name="token_refresh"
    ),  # 回傳token key
    # 註冊
    path("register/", views.RegisterView.as_view(), name="register"),
    # 忘記密碼（第 1 步確認帳號、第 2 步設定新密碼）
    path(
        "password-reset/check/",
        views.PasswordResetCheckView.as_view(),
        name="password_reset_check",
    ),
    path("password-reset/", views.PasswordResetView.as_view(), name="password_reset"),
    # 會員中心子功能
    path("me/password/", views.PasswordChangeView.as_view(), name="password_change"),
    path("me/avatar/", views.AvatarView.as_view(), name="avatar"),
    path("me/stats/", views.UserStatsView.as_view(), name="user_stats"),
    # 會員中心：取得／修改／刪除帳號
    path("me/", views.MeView.as_view(), name="me"),
]
