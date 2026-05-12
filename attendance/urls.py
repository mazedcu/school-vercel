from django.urls import path
from . import views, api_views

urlpatterns = [
    path('mark_attendance/', views.mark_attendance, name='mark_attendance'),
    path('my_attendance/', views.my_attendance, name='my_attendance'),
    path('api/sync/', api_views.sync_attendance, name='api_sync_attendance'),
]
