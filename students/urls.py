from django.urls import path
from . import views

urlpatterns = [
    path('student_profiles/', views.student_profiles, name='student_profiles'),
    path('student_profile/<int:student_id>/', views.student_profile_detail, name='student_profile_detail'),
    path('teacher_profiles/', views.teacher_profiles, name='teacher_profiles'),
    path('teacher_profile/<int:teacher_id>/', views.teacher_profile_detail, name='teacher_profile_detail'),
]
