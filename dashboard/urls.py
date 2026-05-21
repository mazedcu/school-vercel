from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
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
]
