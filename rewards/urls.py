from django.urls import path

from . import views

urlpatterns = [
    path("summary/", views.summary_view),  # 點數總覽
    path("achievements/", views.achievements_view),  # 成就牆
    path("points/history/", views.points_history_view),  # 點數紀錄
]
