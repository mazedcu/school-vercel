from django.urls import path
from . import views

urlpatterns = [
    path('manage_users/', views.manage_users, name='manage_users'),

    # Custom password-reset views that catch SMTP errors gracefully
    path('password_reset/', views.SafePasswordResetView.as_view(), name='password_reset'),
]
