from django.urls import path

from .views import MarketSortConfigView, MarketSortSubmitView

urlpatterns = [
    path("config/", MarketSortConfigView.as_view(), name="market_sort_config"),
    path("submit/", MarketSortSubmitView.as_view(), name="market_sort_submit"),
]
