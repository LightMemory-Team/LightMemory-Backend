"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

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
    # 會員中心：取得／修改自己的資料
    path("me/", views.MeView.as_view(), name="me"),
]
