from django.urls import path
from .views import (
    DiaryCalendarView,
    DiaryReviewView,
    DiaryDetailView,
    DiaryReplyView,
    DiaryFinalizeView,
    DiaryShareView,
)

urlpatterns = [
    path('', DiaryCalendarView.as_view(), name='diary_calendar'),
    path('review/', DiaryReviewView.as_view(), name='diary_review'),
    path('<int:diary_id>/', DiaryDetailView.as_view(), name='diary_detail'),
    path('<int:diary_id>/replies/', DiaryReplyView.as_view(), name='diary_reply'),
    path('<int:diary_id>/finalize/', DiaryFinalizeView.as_view(), name='diary_finalize'),
    path('<int:diary_id>/share/', DiaryShareView.as_view(), name='diary_share'),
]
