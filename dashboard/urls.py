from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard),  # 儀表板（雷達圖）
]
