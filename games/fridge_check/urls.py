from django.urls import path

from . import views


urlpatterns = [
    path(
        "sessions/",
        views.create_session,
        name="fridge-check-session-create",
    ),
    path(
        "sessions/<int:session_id>/answers/",
        views.submit_answer,
        name="fridge-check-answer",
    ),
    path(
        "history/",
        views.get_fridge_check_history,
        name="fridge-check-history",
    ),
]