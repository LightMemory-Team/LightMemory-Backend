from django.urls import path

from games.market_shopping import views as market_shopping_views


urlpatterns = [
    path(
        "market-shopping/sessions/",
        market_shopping_views.create_session,
        name="market-shopping-session-create",
    ),
    path(
        "market-shopping/sessions/<int:session_id>/item-answers/",
        market_shopping_views.submit_item_answer,
        name="market-shopping-item-answer",
    ),
    path(
        "market-shopping/sessions/<int:session_id>/change-answers/",
        market_shopping_views.submit_change_answer,
        name="market-shopping-change-answer",
    ),
]   