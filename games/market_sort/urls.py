from django.urls import path

from .views import MarketSortSubmitView

urlpatterns = [
    path("submit/", MarketSortSubmitView.as_view(), name="market_sort_submit"),
]
