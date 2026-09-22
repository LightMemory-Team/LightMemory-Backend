from django.urls import path
from .views import DiaryCalendarView

urlpatterns = [
    path('', DiaryCalendarView.as_view(), name='diary_calendar'),
]