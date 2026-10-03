from django.urls import path

from . import views

urlpatterns = [
    path("config/", views.config, name="memory_recall_config"),
    path("start/", views.start, name="memory_recall_start"),
    path("round/", views.round_view, name="memory_recall_round"),
    path("round/answer/", views.round_answer, name="memory_recall_round_answer"),
    path("finish/", views.finish, name="memory_recall_finish"),
    path("result/<int:session_id>/", views.result, name="memory_recall_result"),
]
