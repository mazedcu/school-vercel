from django.urls import path
from . import app_download, views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('app/', app_download.app_page, name='app_page'),
    path('app/download/', app_download.app_download, name='app_download'),
    path('dashboard/', views.dashboard_router, name='dashboard_router'),

    # Dashboards
    path('admin_dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('accounts_dashboard/', views.accounts_dashboard, name='accounts_dashboard'),
    path('teacher_dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('student_dashboard/', views.student_dashboard, name='student_dashboard'),
    path('parent_dashboard/', views.parent_dashboard, name='parent_dashboard'),
    path('manage_notices/', views.manage_notices, name='manage_notices'),
    path('notice/<int:notice_id>/delete/', views.delete_notice, name='delete_notice'),
    path('academic_years/', views.manage_academic_years, name='manage_academic_years'),
    path('api/monthly-finance/', views.api_monthly_finance, name='api_monthly_finance'),
]
