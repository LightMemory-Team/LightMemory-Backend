from django.urls import path

from . import views

urlpatterns = [
    path("config/", views.config, name="market_route_config"),
    path("start/", views.start, name="market_route_start"),
    path("round/", views.round_view, name="market_route_round"),
    path("round/answer/", views.round_answer, name="market_route_round_answer"),
    path("finish/", views.finish, name="market_route_finish"),
    path("result/<int:session_id>/", views.result, name="market_route_result"),
]
