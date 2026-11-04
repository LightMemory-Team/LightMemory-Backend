from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard),  # 儀表板（雷達圖）
    path("weekly-report/", views.weekly_report_view),  # 週報表
]
