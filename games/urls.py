from django.urls import include, path

urlpatterns = [
    path("market-route/", include("games.market_route.urls")),
    path("market-sort/", include("games.market_sort.urls")),
    path("market-shopping/", include("games.market_shopping.urls")),
    path("memory-recall/", include("games.memory_recall.urls")),
]
