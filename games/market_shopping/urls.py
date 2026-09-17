from django.urls import path

from . import views


urlpatterns = [
    path(
        "sessions/",
        views.create_session,
        name="market-shopping-session-create",
    ),
    path(
        "sessions/<int:session_id>/item-answers/",
        views.submit_item_answer,
        name="market-shopping-item-answer",
    ),
    path(
        "sessions/<int:session_id>/change-answers/",
        views.submit_change_answer,
        name="market-shopping-change-answer",
    ),
    path(
        "history/",
        views.get_market_shopping_history,
        name="market-shopping-history",
    ),
]