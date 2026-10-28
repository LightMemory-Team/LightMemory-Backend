from django.urls import include, path

urlpatterns = [
    path("market-route/", include("games.market_route.urls")),
    path("market-sort/", include("games.market_sort.urls")),
    path("market-shopping/", include("games.market_shopping.urls")),
    path("memory-recall/", include("games.memory_recall.urls")),
    path("fridge-check/", include("games.fridge_check.urls")),
    path("fridge_check/", include("games.fridge_check.urls")),
]
