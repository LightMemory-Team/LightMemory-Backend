from django.urls import path

from . import views


urlpatterns = [
    # 建立 Session（支援 sessions/ 與 session/）
    path("sessions/", views.create_session, name="fridge-check-session-create"),
    path("session/", views.create_session, name="fridge-check-session-create-alias"),

    # 提交答案（支援 sessions/answers、sessions/answer、session/answers、session/answer）
    path("sessions/<str:session_id>/answers/", views.submit_answer, name="fridge-check-answer"),
    path("sessions/<str:session_id>/answer/", views.submit_answer, name="fridge-check-answer-singular"),
    path("session/<str:session_id>/answers/", views.submit_answer, name="fridge-check-session-singular-answer"),
    path("session/<str:session_id>/answer/", views.submit_answer, name="fridge-check-session-singular-answer-singular"),

    # 歷史紀錄
    path("history/", views.get_fridge_check_history, name="fridge-check-history"),
]