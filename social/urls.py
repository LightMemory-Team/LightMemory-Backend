# social/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/unread_count/', views.unread_count, name='unread_count'),
    path('notifications/<int:notification_id>/read/', views.mark_as_read, name='mark_as_read'),
]