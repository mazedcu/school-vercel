from django.urls import path
from . import views

urlpatterns = [
    path('manage_assessments/', views.manage_assessments, name='manage_assessments'),
    path('delete_assessment/<int:assessment_id>/', views.delete_assessment, name='delete_assessment'),
    path('enter_marks/<int:assessment_id>/', views.enter_marks, name='enter_marks'),
    path('student_report/', views.student_report, name='student_report'),
    path('student_report/<int:student_id>/', views.student_report, name='student_report_detail'),
    path('view_reports/', views.view_reports, name='view_reports'),
    path('grade_settings/', views.grade_settings_view, name='grade_settings'),
    path('subject_comments/', views.subject_comments_view, name='subject_comments'),
    path('report_settings/', views.report_settings, name='report_settings'),
    path('ct-progress/', views.ct_progress_report, name='ct_progress_report'),
    path('ct-progress/print/', views.ct_progress_report_print, name='ct_progress_report_print'),
    path('period_setup/', views.period_setup, name='period_setup'),
    path('period_reports/', views.period_report_select, name='period_report_select'),
    path('period_reports/<int:student_id>/', views.period_report_select, name='period_report_select_student'),
    path('period_report/<int:period_id>/<int:student_id>/', views.period_report, name='period_report'),
]

