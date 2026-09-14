from django.urls import path, include

urlpatterns = [
    path('market-sort/', include('games.market_sort.urls')),
]