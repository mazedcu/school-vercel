from django.urls import path
from . import views, api_views

urlpatterns = [
    path('mark_attendance/', views.mark_attendance, name='mark_attendance'),
    path('my_attendance/', views.student_attendance_report, name='my_attendance'),
    path('student-report/<int:student_id>/', views.student_attendance_report, name='student_attendance_report'),
    path('report/', views.attendance_report, name='attendance_report'),
    path('api/sync/', api_views.sync_attendance, name='api_sync_attendance'),
    
    # Teacher Attendance
    path('mark_teacher_attendance/', views.mark_teacher_attendance, name='mark_teacher_attendance'),
    path('teacher_report/', views.teacher_attendance_report, name='teacher_attendance_report'),
]
