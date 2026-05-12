from django.urls import path
from . import views

urlpatterns = [
    path('manage_users/', views.manage_users, name='manage_users'),
    path('parent_profiles/', views.parent_profiles, name='parent_profiles'),
    path('parent_profiles/<int:parent_id>/', views.parent_profile_detail, name='parent_profile_detail'),

    # Custom password-reset views that catch SMTP errors gracefully
    path('password_reset/', views.SafePasswordResetView.as_view(), name='password_reset'),
]
