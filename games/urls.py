from django.urls import include, path

urlpatterns = [
    path("market-route/", include("games.market_route.urls")),
]
