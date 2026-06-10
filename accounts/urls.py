from django.urls import path
from . import views

urlpatterns = [
    path('manage_users/', views.manage_users, name='manage_users'),
    path('parent_profiles/', views.parent_profiles, name='parent_profiles'),
    path('parent_profiles/<int:parent_id>/', views.parent_profile_detail, name='parent_profile_detail'),

    # Recycle Bin
    path('recycle_bin/', views.recycle_bin, name='recycle_bin'),
    path('recycle_bin/restore/<int:user_id>/', views.restore_user, name='restore_user'),
    path('recycle_bin/permanent_delete/<int:user_id>/', views.permanent_delete_user, name='permanent_delete_user'),

    # Custom password-reset views that catch SMTP errors gracefully
    path('password_reset/', views.SafePasswordResetView.as_view(), name='password_reset'),
]
