from django.urls import path
from . import views

urlpatterns = [
    path('share/<str:share_token>/', views.SharePageView.as_view(), name='share_page'),
    path('api/share/<str:share_token>/comments/', views.PublicShareCommentView.as_view(), name='public_share_comment'),
    path(
        'api/share/<str:share_token>/voice-replies/',
        views.PublicShareVoiceReplyView.as_view(),
        name='public_share_voice_reply',
    ),
]
