from django.urls import path
from .views import DiaryCalendarView, DiaryReplyView, DiaryFinalizeView

urlpatterns = [
    path('', DiaryCalendarView.as_view(), name='diary_calendar'),
    path('<int:diary_id>/replies/', DiaryReplyView.as_view(), name='diary_reply'),
    path('<int:diary_id>/finalize/', DiaryFinalizeView.as_view(), name='diary_finalize'),
]